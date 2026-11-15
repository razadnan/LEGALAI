"""Adapters between Developer 3's orchestration layer and the other modules.

``Services`` resolves each integration function from the real Developer 1 / 2
modules when they exist and fall back to ``fallbacks`` otherwise. Errors raised
by *real* modules are wrapped in ``AgentError`` (never silently swallowed).

Expected real interfaces (agree on these on Day 1):

  document_intelligence.document_processor.process_document(file_path, document_id) -> dict
  document_intelligence.document_agent.analyze_document(document_data: dict) -> dict
  document_intelligence.risk_analyzer.analyze_risks(document_data: dict) -> list[dict]
  rag_engine.retrieval.index_document(document_data: dict) -> None
  rag_engine.chat_engine.answer_question(document_id: str, question: str, chat_history=None,
                                         simple_language=False) -> dict
  rag_engine.comparison_agent.compare_documents(doc_a: dict, doc_b: dict) -> dict
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Callable, Optional

from core.exceptions import AgentError, LegalMindError
from core.schemas import (AnswerResult, ComparisonResult, DocumentAnalysis, DocumentData, RiskFinding)
from orchestration import fallbacks

_CANDIDATES: dict[str, list[tuple[str, str]]] = {
    "process_document": [("document_intelligence.document_processor", "process_document")],
    "analyze_document": [("document_intelligence.document_agent", "analyze_document"),
                         ("document_intelligence.document_analyzer", "analyze_document")],
    "analyze_risks": [("document_intelligence.risk_analyzer", "analyze_risks")],
    "index_document": [("rag_engine.retrieval", "index_document"), ("rag_engine.vector_store", "index_document")],
    "answer_question": [("rag_engine.chat_engine", "answer_question")],
    "compare_documents": [("rag_engine.comparison_agent", "compare_document_data"),
                          ("rag_engine.comparison_agent", "compare_documents")],
}


def _resolve(name: str) -> tuple[Optional[Callable], str]:
    last_error = "module not found"
    for module_name, attr in _CANDIDATES[name]:
        try:
            return getattr(importlib.import_module(module_name), attr), f"real ({module_name})"
        except (ImportError, AttributeError) as exc:
            last_error = f"{module_name}: {exc}"
    return None, f"fallback ({last_error})"


def _dump(doc: DocumentData) -> dict:
    return doc.model_dump()


class Services:
    """Single entry point the supervisor uses to reach every AI capability."""

    def __init__(self, prefer_real: bool = True):
        self._real: dict[str, Optional[Callable]] = {}
        self.status: dict[str, str] = {}
        for name in _CANDIDATES:
            fn, status = _resolve(name) if prefer_real else (None, "fallback (forced)")
            self._real[name] = fn
            self.status[name] = status

    # -- helpers --------------------------------------------------------------
    def _call_real(self, name: str, *args: Any, **kwargs: Any) -> Any:
        try:
            return self._real[name](*args, **kwargs)
        except LegalMindError:
            raise
        except Exception as exc:  # real module bug / API failure: surface it clearly
            raise AgentError(f"{name} failed: {exc}",
                             user_message=f"The AI component '{name}' failed: {type(exc).__name__}. "
                                          "Please try again or check your API key and network.") from exc

    @property
    def uses_fallback(self) -> bool:
        return any(s.startswith("fallback") for s in self.status.values())

    # -- Developer 1 ----------------------------------------------------------
    def process_document(self, file_path: Path | str, document_id: str) -> DocumentData:
        if self._real["process_document"]:
            doc = DocumentData.model_validate(self._call_real("process_document", str(file_path), Path(file_path).name))
            doc.document_id = document_id
            return doc
        return fallbacks.process_document(file_path, document_id)

    def analyze_document(self, doc: DocumentData) -> DocumentAnalysis:
        if self._real["analyze_document"]:
            return DocumentAnalysis.model_validate(self._call_real("analyze_document", _dump(doc)))
        return fallbacks.analyze_document(doc)

    def analyze_risks(self, doc: DocumentData) -> list[RiskFinding]:
        if self._real["analyze_risks"]:
            raw = self._call_real("analyze_risks", _dump(doc)) or []
            return [RiskFinding.model_validate(r) for r in raw]
        return fallbacks.analyze_risks(doc)

    # -- Developer 2 ----------------------------------------------------------
    def index_document(self, doc: DocumentData) -> None:
        fallbacks.index_document(doc)  # cheap in-memory copy; keeps the fallback answerer usable
        if self._real["index_document"]:
            self._call_real("index_document", _dump(doc))

    def answer_question(
        self,
        document_id: str,
        question: str,
        chat_history: Optional[list[dict[str, str]]] = None,
        simple_language: bool = False,
    ) -> AnswerResult:
        if self._real["answer_question"]:
            return AnswerResult.model_validate(
                self._call_real(
                    "answer_question",
                    document_id,
                    question,
                    chat_history=chat_history,
                    simple_language=simple_language,
                )
            )
        return fallbacks.answer_question(document_id, question, chat_history=chat_history)

    def compare_documents(self, doc_a: DocumentData, doc_b: DocumentData) -> ComparisonResult:
        if self._real["compare_documents"]:
            fn = self._real["compare_documents"]
            if getattr(fn, "__name__", "") == "compare_documents":
                raw = self._call_real("compare_documents", doc_a.document_id, doc_b.document_id)
            else:
                raw = self._call_real("compare_documents", _dump(doc_a), _dump(doc_b))
            return ComparisonResult.model_validate(raw)
        return fallbacks.compare_documents(doc_a, doc_b)
