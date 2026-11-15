"""Supervisor agent: intent classification + conditional routing.

Implemented as a LangGraph ``StateGraph`` (classify -> agents -> finalize). If
``langgraph`` is not installed, an equivalent built-in runner executes the same
node functions, so the app keeps working (``engine`` reports which is active).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, TypedDict

from config.settings import Settings, get_settings
from core.exceptions import InvalidRequestError, LegalMindError
from core.domain_guard import is_out_of_domain_question
from core.schemas import (AnswerResult, ComparisonResult, DocumentAnalysis, DocumentInfo, RiskFinding,
                          TaskType, WorkflowResult)
from core.state import DocumentRegistry
from orchestration.adapters import Services
from orchestration.verification import verify_risks, verify_sources

logger = logging.getLogger(__name__)
AGENT_NODES = ("document_agent", "risk_agent", "rag_agent", "comparison_agent", "report_generator")

_INJECTION_PATTERNS = [
    r"ignore (?:all |any )?(?:the )?(?:previous|prior|above) (?:instructions|prompts?)",
    r"disregard .{0,30}instructions", r"reveal .{0,40}(?:system prompt|api key|secret|password)",
    r"\bsystem prompt\b", r"you are now\b",
]


class AgentState(TypedDict, total=False):
    task: str
    question: Optional[str]
    chat_history: list[dict[str, str]]
    simple_language: bool
    document_ids: list[str]
    intent: str
    plan: list[str]
    completed: list[str]
    agents_invoked: list[str]
    analysis: Optional[DocumentAnalysis]
    answer: Optional[AnswerResult]
    risks: list[RiskFinding]
    comparison: Optional[ComparisonResult]
    report_path: Optional[str]
    errors: list[str]
    warnings: list[str]
    result: Any


# --------------------------------------------------------------------------- #
# Intent classification (rule-based: deterministic, testable, free of API calls)
# --------------------------------------------------------------------------- #
_CLAUSE_REF = re.compile(r"\b(?:clause|section|article)\s+\d", re.I)


def classify_intent(text: str, n_documents: int = 1) -> TaskType:
    t = (text or "").lower()
    if re.search(r"\b(compare|comparison|differences?|what changed|changes between|versions?)\b", t) or \
            (n_documents >= 2 and re.search(r"\b(changed|revised|redline)\b", t)):
        return TaskType.COMPARE
    if re.search(r"\b(report|pdf|export|download)\b", t):
        return TaskType.REPORT
    if re.search(r"\b(risks?|risky|red flags?|legal review|unfavou?rable|concerns?|dangerous|problematic)\b", t) \
            or "deserve" in t and "review" in t:
        return TaskType.RISK
    if _CLAUSE_REF.search(t):
        return TaskType.QA
    if re.search(r"\b(summar\w*|overview|tl;?dr|parties|key dates|important dates|obligations|what type of|document type)\b", t):
        return TaskType.SUMMARIZE
    return TaskType.QA


def resolve_intent(task: str, question: Optional[str], n_documents: int) -> TaskType:
    try:
        explicit = TaskType(task.strip().lower())
        if explicit is not TaskType.AUTO:
            return explicit
        text = question or ""
    except ValueError:  # free-text request such as "Summarize this contract"
        text = f"{task} {question or ''}"
    return classify_intent(text, n_documents)


def classify_intent_with_llm(text: str, n_documents: int) -> Optional[TaskType]:
    """Classify an automatic request with the configured LLM; return None to use rules."""
    from rag_engine.llm import get_llm

    try:
        llm = get_llm()
        if llm is None:
            return None
        system_prompt = (
            "Classify the user's request about an uploaded legal document. "
            "Return JSON only with one field, intent, whose value is one of "
            "qa, summarize, risk, compare, report. Use compare only when at least two "
            "documents are available; with one document, choose qa or another applicable intent."
        )
        user_prompt = json.dumps({"question": text, "document_count": n_documents}, ensure_ascii=True)
        raw = llm(system_prompt, user_prompt)
        match = re.search(r"\{.*\}", raw or "", re.S)
        value = json.loads(match.group(0)).get("intent") if match else None
        if value not in {item.value for item in TaskType if item is not TaskType.AUTO}:
            logger.warning("LLM intent classification returned an invalid result; using rule-based routing.")
            return None
        return TaskType(value)
    except Exception as exc:
        logger.warning("LLM intent classification failed (%s); using rule-based routing.", type(exc).__name__)
        return None


def build_plan(intent: TaskType, n_documents: int, has_question: bool) -> list[str]:
    if intent is TaskType.SUMMARIZE:
        return ["document_agent"]
    if intent is TaskType.QA:
        return ["rag_agent"]
    if intent is TaskType.RISK:
        return ["document_agent", "risk_agent"]
    if intent is TaskType.COMPARE:
        return ["comparison_agent"]
    plan = ["document_agent", "risk_agent"]  # REPORT
    if has_question:
        plan.append("rag_agent")
    if n_documents >= 2:
        plan.append("comparison_agent")
    return plan + ["report_generator"]


def sanitize_question(question: Optional[str], max_chars: int) -> tuple[Optional[str], list[str]]:
    if question is None:
        return None, []
    warnings = []
    clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", question).strip()
    if len(clean) > max_chars:
        clean = clean[:max_chars]
        warnings.append(f"The question was shortened to {max_chars} characters.")
    if any(re.search(p, clean, re.I) for p in _INJECTION_PATTERNS):
        warnings.append("The question contains instruction-like text. It is treated purely as a question "
                        "about the document; system instructions cannot be changed from the chat.")
    return clean or None, warnings


# --------------------------------------------------------------------------- #
# Result composition
# --------------------------------------------------------------------------- #
def _doc_infos(state: AgentState, registry: DocumentRegistry) -> list[DocumentInfo]:
    infos = []
    for i in state.get("document_ids", []):
        if registry.exists(i):
            d = registry.get(i)
            infos.append(DocumentInfo(document_id=d.document_id, filename=d.filename, page_count=d.page_count))
    return infos


def _compose_message(intent: str, state: AgentState) -> str:
    analysis, answer = state.get("analysis"), state.get("answer")
    risks, comparison = state.get("risks") or [], state.get("comparison")
    if intent == TaskType.QA.value:
        return answer.answer if answer else ""
    if intent == TaskType.COMPARE.value:
        return comparison.summary if comparison else ""
    if intent == TaskType.RISK.value:
        if not risks:
            return "No clauses were flagged for additional review."
        counts = {s: sum(r.severity == s for r in risks) for s in ("high", "medium", "low")}
        return (f"{len(risks)} clause(s) may deserve additional legal review "
                f"({counts['high']} high, {counts['medium']} medium, {counts['low']} low). "
                "This is not legal advice - discuss the flagged items with a qualified lawyer.")
    if intent == TaskType.REPORT.value:
        return "Your analysis report is ready to download." if state.get("report_path") else ""
    if analysis:  # summarize
        if analysis.summary:
            return analysis.summary
        parts = [f"Document type: {analysis.document_type}."]
        if analysis.parties:
            parts.append("Parties: " + "; ".join(analysis.parties) + ".")
        parts.append(f"{len(analysis.important_dates)} important date(s) and "
                     f"{len(analysis.obligations)} obligation(s) were extracted.")
        return " ".join(parts)
    return ""


def build_result(state: AgentState, registry: DocumentRegistry) -> WorkflowResult:
    intent = state.get("intent", "")
    return WorkflowResult(
        task=state.get("task", ""), intent=intent, agents_invoked=list(state.get("agents_invoked", [])),
        documents=_doc_infos(state, registry), question=state.get("question"),
        message=_compose_message(intent, state), analysis=state.get("analysis"), answer=state.get("answer"),
        risks=list(state.get("risks") or []), comparison=state.get("comparison"),
        report_path=state.get("report_path"), errors=list(state.get("errors", [])),
        warnings=list(state.get("warnings", [])))


# --------------------------------------------------------------------------- #
# Graph
# --------------------------------------------------------------------------- #
def next_node(state: AgentState) -> str:
    """Conditional edge: next unfinished step of the plan, else finalize."""
    done = set(state.get("completed", []))
    for step in state.get("plan", []):
        if step not in done:
            return step
    return "finalize"


class SupervisorGraph:
    def __init__(self, services: Services, registry: DocumentRegistry, settings: Optional[Settings] = None):
        self.services, self.registry = services, registry
        self.settings = settings or get_settings()
        self._indexed: set[str] = set()
        self._nodes = {
            "classify": self._classify, "document_agent": self._guard("document_agent", self._document_agent),
            "risk_agent": self._guard("risk_agent", self._risk_agent),
            "rag_agent": self._guard("rag_agent", self._rag_agent),
            "comparison_agent": self._guard("comparison_agent", self._comparison_agent),
            "report_generator": self._guard("report_generator", self._report_node),
            "finalize": self._finalize,
        }
        self.engine = "builtin"
        self._graph = self._compile()

    # -- construction -----------------------------------------------------------
    def _compile(self):
        try:
            from langgraph.graph import END, StateGraph
        except ImportError:
            return None
        g = StateGraph(AgentState)
        for name, fn in self._nodes.items():
            g.add_node(name, fn)
        g.set_entry_point("classify")
        targets = {n: n for n in (*AGENT_NODES, "finalize")}
        for source in ("classify", *AGENT_NODES):
            g.add_conditional_edges(source, next_node, targets)
        g.add_edge("finalize", END)
        self.engine = "langgraph"
        return g.compile()

    def invoke(self, state: AgentState) -> AgentState:
        if self._graph is not None:
            return self._graph.invoke(state)
        state = {**state, **self._nodes["classify"](state)}
        for _ in range(len(AGENT_NODES) + 1):  # plan can never exceed this many steps
            nxt = next_node(state)
            if nxt == "finalize":
                break
            state = {**state, **self._nodes[nxt](state)}
        return {**state, **self._nodes["finalize"](state)}

    # -- nodes ------------------------------------------------------------------
    def _guard(self, name: str, fn):
        def wrapped(state: AgentState) -> dict:
            update: dict = {}
            try:
                update = fn(state) or {}
            except LegalMindError as exc:
                update = {"errors": [*state.get("errors", []), f"{name}: {exc.user_message}"]}
            except Exception as exc:  # never let one agent crash the whole workflow
                update = {"errors": [*state.get("errors", []),
                                     f"{name}: unexpected error ({type(exc).__name__}). Please try again."]}
            update["completed"] = [*state.get("completed", []), name]
            update["agents_invoked"] = [*state.get("agents_invoked", []), name]
            return update
        return wrapped

    def _classify(self, state: AgentState) -> dict:
        ids = [i for i in state.get("document_ids", []) if i]
        question, warnings = sanitize_question(state.get("question"), self.settings.max_question_chars)
        update: dict = {"question": question, "warnings": list(state.get("warnings", [])) + warnings,
                        "errors": list(state.get("errors", [])), "completed": [], "agents_invoked": []}
        try:
            if not ids:
                raise InvalidRequestError("no documents", user_message="Please select or upload a document first.")
            missing = [i for i in ids if not self.registry.exists(i)]
            if missing:
                raise InvalidRequestError(f"missing {missing}",
                                          user_message=f"Document(s) not found: {', '.join(missing)}. Please upload again.")
            task = state.get("task", "")
            if task.strip().lower() == TaskType.AUTO.value and question:
                intent = classify_intent_with_llm(question, len(ids))
                if intent is None:
                    intent = classify_intent(question, len(ids))
            else:
                intent = resolve_intent(task, question, len(ids))
            if intent is TaskType.COMPARE and len(ids) < 2:
                raise InvalidRequestError("compare needs 2 docs",
                                          user_message="Comparison needs two documents. Upload a second version first.")
            if question and is_out_of_domain_question(question):
                raise InvalidRequestError(
                    "question outside legal domain",
                user_message=(
                    "This question is outside LegalMind AI's domain. "
                    "LegalMind AI is designed exclusively for legal document "
                    "analysis. Please ask a question about your uploaded legal "
                    "document or a legal matter."
                ),
 )
            update.update(intent=intent.value, plan=build_plan(intent, len(ids), bool(question)))
        except LegalMindError as exc:
            update.update(intent=state.get("intent") or "invalid", plan=[], errors=update["errors"] + [exc.user_message])
        return update

    def _primary(self, state: AgentState):
        return self.registry.get(state["document_ids"][0])

    def _document_agent(self, state: AgentState) -> dict:
        doc = self._primary(state)
        analysis = self.registry.get_analysis(doc.document_id)
        if analysis is None:
            analysis = self.services.analyze_document(doc)
            self.registry.save_analysis(doc.document_id, analysis)
        return {"analysis": analysis}

    def _risk_agent(self, state: AgentState) -> dict:
        doc = self._primary(state)
        analysis = state.get("analysis") or self.registry.get_analysis(doc.document_id)
        risks = list(analysis.risk_findings) if analysis and analysis.risk_findings else self.services.analyze_risks(doc)
        risks, warns = verify_risks(risks, doc)
        return {"risks": risks, "warnings": _merge(state.get("warnings"), warns), "analysis": analysis}

    def _rag_agent(self, state: AgentState) -> dict:
        doc = self._primary(state)
        question = state.get("question")
        if not question:
            raise InvalidRequestError("question missing", user_message="Please type a question about the document.")
        if doc.document_id not in self._indexed:  # index lazily, once per session
            self.services.index_document(doc)
            self._indexed.add(doc.document_id)
        answer = self.services.answer_question(
            doc.document_id,
            question,
            chat_history=state.get("chat_history", []),
            simple_language=state.get("simple_language", False),
        )
        sources, warns = verify_sources(answer.sources, doc)
        if not sources and "could not find" not in answer.answer.lower():
            warns.append("The answer has no supporting sources - do not rely on it without checking the document.")
        return {"answer": answer.model_copy(update={"sources": sources}), "warnings": _merge(state.get("warnings"), warns)}

    def _comparison_agent(self, state: AgentState) -> dict:
        ids = state["document_ids"]
        if len(ids) < 2:
            raise InvalidRequestError("compare needs 2", user_message="Comparison needs two documents.")
        a, b = self.registry.get(ids[0]), self.registry.get(ids[1])
        return {"comparison": self.services.compare_documents(a, b)}

    def _report_node(self, state: AgentState) -> dict:
        from reports.report_generator import generate_report

        path = Path(self.settings.reports_dir) / f"legalmind_report_{datetime.now():%Y%m%d_%H%M%S}.pdf"
        generate_report(build_result({**state, "report_path": None}, self.registry), output_path=path)
        return {"report_path": str(path)}

    def _finalize(self, state: AgentState) -> dict:
        return {"result": build_result(state, self.registry)}


def _merge(existing: Optional[list[str]], new: list[str]) -> list[str]:
    return list(dict.fromkeys([*(existing or []), *new]))
