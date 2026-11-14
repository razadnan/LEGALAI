"""Shared Pydantic schemas - the integration contract between all developers.

The models are deliberately *tolerant* on input (they accept plain strings or
slightly different key names from Developer 1 / Developer 2 modules) and
*strict* on output (the UI and report generator only ever see these shapes).
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Severity = Literal["low", "medium", "high"]
ChangeType = Literal["added", "removed", "modified"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


def _first(d: dict, *keys: str, default: Any = None) -> Any:
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return default


# --------------------------------------------------------------------------- #
# Developer 1 -> Developer 2 / 3 : extracted document
# --------------------------------------------------------------------------- #
class Page(_Base):
    page_number: int
    text: str = ""


class DocumentData(_Base):
    document_id: str
    filename: str
    pages: list[Page] = Field(default_factory=list)
    file_type: str = "pdf"
    page_source: str = "native"
    warnings: list[str] = Field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def page_text(self, page_number: int) -> Optional[str]:
        for p in self.pages:
            if p.page_number == page_number:
                return p.text
        return None


class ClauseNode(_Base):
    """A numbered DOCX clause mapped to inclusive, zero-based paragraph indexes."""

    clause_id: str
    number: str
    heading: str = ""
    text: str = ""
    paragraph_start: int = Field(ge=0)
    paragraph_end: int = Field(ge=0)
    parent_id: Optional[str] = None
    children: list["ClauseNode"] = Field(default_factory=list)

    @model_validator(mode="after")
    def _valid_paragraph_range(self):
        if self.paragraph_end < self.paragraph_start:
            raise ValueError("paragraph_end must be at least paragraph_start")
        return self


class ProposedEdit(_Base):
    """An exact-text change proposal; it does not itself imply approval."""

    model_config = ConfigDict(extra="forbid")

    clause_id: str
    old_text: str
    new_text: str
    reason: str

    @field_validator("clause_id")
    @classmethod
    def _clause_id_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("clause_id must not be empty")
        return value

    @field_validator("old_text")
    @classmethod
    def _old_text_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("old_text must not be empty")
        return value

    @field_validator("reason")
    @classmethod
    def _reason_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reason must not be empty")
        return value


# --------------------------------------------------------------------------- #
# Developer 1 -> Developer 3 : analysis models
# --------------------------------------------------------------------------- #
class Evidence(_Base):
    page: Optional[int] = None
    clause: Optional[str] = None
    text: str = ""
    verified: Optional[bool] = None


class Party(_Base):
    name: str = ""
    role: Optional[str] = None
    evidence: Optional[Evidence] = None


class ImportantDate(_Base):
    label: str = "Date"
    date: str = ""
    value: Optional[str] = None
    iso_date: Optional[str] = None
    page: Optional[int] = None
    evidence: Optional[Evidence] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, v: Any):
        if isinstance(v, str):
            return {"label": "Date", "date": v, "value": v}
        if isinstance(v, dict):
            v = dict(v)
            val = _first(v, "value", "date", default="")
            v.setdefault("label", _first(v, "description", "type", "event", default="Date"))
            v.setdefault("date", val)
            v.setdefault("value", val)
            ev = v.get("evidence")
            if isinstance(ev, dict) and v.get("page") is None:
                v["page"] = ev.get("page")
            elif hasattr(ev, "page") and v.get("page") is None:
                v["page"] = ev.page
        return v


class KeyTerm(_Base):
    label: str = ""
    value: str = ""
    evidence: Optional[Evidence] = None


class PaymentTerm(_Base):
    kind: str = "payment"
    description: str = ""
    amounts: list[str] = Field(default_factory=list)
    frequency: Optional[str] = None
    evidence: Optional[Evidence] = None


class Obligation(_Base):
    description: str = ""
    party: Optional[str] = None
    page: Optional[int] = None
    kind: str = "obligation"
    text: Optional[str] = None
    category: Optional[str] = None
    evidence: Optional[Evidence] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, v: Any):
        if isinstance(v, str):
            return {"description": v, "text": v}
        if isinstance(v, dict):
            v = dict(v)
            desc = _first(v, "description", "text", "obligation", "clause", default="")
            v.setdefault("description", desc)
            v.setdefault("text", desc)
            ev = v.get("evidence")
            if isinstance(ev, dict) and v.get("page") is None:
                v["page"] = ev.get("page")
            elif hasattr(ev, "page") and v.get("page") is None:
                v["page"] = ev.page
        return v


class KeyClause(_Base):
    clause_id: str = ""
    title: str = ""
    category: str = "general"
    page: int = 1
    text: str = ""


class RiskFinding(_Base):
    clause: str = ""
    title: Optional[str] = None
    severity: Severity = "medium"
    category: str = ""
    finding_type: str = "clause"
    risk_id: str = ""
    explanation: str = ""
    evidence: Any = Field(default_factory=list)
    page: Optional[int] = None
    lawyer_question: str = ""
    suggested_question: Optional[str] = None
    verified: Optional[bool] = None  # set by Developer 3's evidence verification

    @property
    def evidence_text(self) -> str:
        if isinstance(self.evidence, list):
            parts = [getattr(e, "text", str(e)) for e in self.evidence if getattr(e, "text", str(e))]
            return " ".join(parts)
        return str(self.evidence or "")

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, v: Any):
        if isinstance(v, str):
            return {"clause": v, "explanation": v, "evidence": v}
        if isinstance(v, dict):
            v = dict(v)
            clause_val = _first(v, "clause", "title", "clause_ref", "name", default="")
            v.setdefault("clause", clause_val)
            v.setdefault("title", clause_val)
            expl = _first(v, "explanation", "reason", "description", default="")
            v.setdefault("explanation", expl)
            lq = _first(v, "lawyer_question", "suggested_question", "question", default="")
            v.setdefault("lawyer_question", lq)
            v.setdefault("suggested_question", lq)

            raw_ev = v.get("evidence")
            if isinstance(raw_ev, list) and raw_ev:
                first = raw_ev[0]
                if v.get("page") is None:
                    v["page"] = getattr(first, "page", None) if hasattr(first, "page") else (first.get("page") if isinstance(first, dict) else None)
            elif isinstance(raw_ev, dict) and v.get("page") is None:
                v["page"] = raw_ev.get("page")
        return v

    @field_validator("severity", mode="before")
    @classmethod
    def _severity(cls, v: Any):
        s = str(v or "medium").strip().lower()
        if s in ("critical", "severe"):
            return "high"
        return s if s in ("low", "medium", "high") else "medium"


class DocumentAnalysis(_Base):
    document_id: str = ""
    document_type: str = "Unknown"
    classification_basis: list[str] = Field(default_factory=list)
    parties: list[str] = Field(default_factory=list)
    important_dates: list[ImportantDate] = Field(default_factory=list)
    key_terms: list[KeyTerm] = Field(default_factory=list)
    payment_terms: list[PaymentTerm] = Field(default_factory=list)
    obligations: list[Obligation] = Field(default_factory=list)
    key_clauses: list[KeyClause] = Field(default_factory=list)
    risk_findings: list[RiskFinding] = Field(default_factory=list)
    summary: str = ""
    notes: list[str] = Field(default_factory=list)

    @field_validator("parties", mode="before")
    @classmethod
    def _parties(cls, v: Any):
        out = []
        for item in v or []:
            if isinstance(item, dict):
                name = _first(item, "name", "party", default="")
                role = item.get("role")
                out.append(f"{name} ({role})" if name and role else str(name or item))
            elif hasattr(item, "name"):
                name = item.name
                role = getattr(item, "role", None)
                out.append(f"{name} ({role})" if name and role else str(name))
            else:
                out.append(str(item))
        return out


# --------------------------------------------------------------------------- #
# Developer 2 -> Developer 3 : answers, retrieval chunks and comparison
# --------------------------------------------------------------------------- #
class Chunk(_Base):
    chunk_id: str
    document_id: str
    chunk_index: int
    text: str
    page_start: int
    page_end: int
    clause: Optional[str] = None
    clause_ids: list[str] = Field(default_factory=list)
    heading: str = ""


class Source(_Base):
    page: Optional[int] = None
    page_end: Optional[int] = None
    clause: Optional[str] = None
    text: str = ""
    source_id: Optional[str] = None
    score: Optional[float] = None
    verified: Optional[bool] = None  # set by Developer 3's citation verification

    @field_validator("clause", mode="before")
    @classmethod
    def _clause(cls, v: Any):
        return None if v in (None, "") else str(v)


class AnswerResult(_Base):
    answer: str = ""
    sources: list[Source] = Field(default_factory=list)
    grounded: bool = True
    mode: str = "llm"
    warnings: list[str] = Field(default_factory=list)


Answer = AnswerResult


class ComparisonChange(_Base):
    change_type: ChangeType = "modified"
    section: str = ""
    old_text: str = ""
    new_text: str = ""
    summary: str = ""
    old_page: Optional[int] = None
    new_page: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, v: Any):
        if isinstance(v, dict):
            v = dict(v)
            v.setdefault("section", _first(v, "heading", "category", default=""))
            v.setdefault("old_text", _first(v, "text_a", default=""))
            v.setdefault("new_text", _first(v, "text_b", default=""))
            v.setdefault("old_page", _first(v, "page_a", default=None))
            v.setdefault("new_page", _first(v, "page_b", default=None))
            v.setdefault("summary", _first(v, "explanation", default=""))
        return v

    @field_validator("change_type", mode="before")
    @classmethod
    def _ct(cls, v: Any):
        s = str(v or "modified").lower()
        return {"changed": "modified", "updated": "modified", "deleted": "removed",
                "new": "added", "inserted": "added"}.get(s, s if s in ("added", "removed", "modified") else "modified")


class ComparisonResult(_Base):
    summary: str = ""
    changes: list[ComparisonChange] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, v: Any):
        if isinstance(v, dict):
            v = dict(v)
            s = v.get("summary")
            if isinstance(s, dict):
                v["summary"] = (
                    f"{s.get('modified', 0)} modified · "
                    f"{s.get('added', 0)} added · "
                    f"{s.get('removed', 0)} removed · "
                    f"{s.get('unchanged', 0)} unchanged"
                )
        return v


# --------------------------------------------------------------------------- #
# Developer 3 : workflow
# --------------------------------------------------------------------------- #
class TaskType(str, Enum):
    SUMMARIZE = "summarize"
    QA = "qa"
    RISK = "risk"
    COMPARE = "compare"
    REPORT = "report"
    AUTO = "auto"


class DocumentInfo(_Base):
    document_id: str
    filename: str
    page_count: int = 0


class WorkflowResult(_Base):
    task: str
    intent: str = ""
    agents_invoked: list[str] = Field(default_factory=list)
    documents: list[DocumentInfo] = Field(default_factory=list)
    question: Optional[str] = None
    message: str = ""
    analysis: Optional[DocumentAnalysis] = None
    answer: Optional[AnswerResult] = None
    risks: list[RiskFinding] = Field(default_factory=list)
    comparison: Optional[ComparisonResult] = None
    report_path: Optional[str] = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors
