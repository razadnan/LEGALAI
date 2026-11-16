"""Fix 7: Pipeline measurement.

Tracks:
- field-level extraction confidence
- retrieval recall@k (cited vs retrieved)
- citation support rate
- unsupported citation rate
- false-refusal rate
- clause-level citation counts
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from core.schemas import AnswerResult, PipelineMetrics, RiskFinding


@dataclass
class MetricsCollector:
    """Accumulate per-request metrics and compute a summary snapshot."""
    _extraction_confs: List[float] = field(default_factory=list)
    _cited_claims: int = 0
    _total_claims: int = 0
    _unsupported: int = 0
    _false_refusals: int = 0
    _total_queries: int = 0
    _relevant_retrieved: int = 0
    _total_retrieved: int = 0

    def record_extraction(self, confidence: float) -> None:
        self._extraction_confs.append(max(0.0, min(1.0, confidence)))

    def record_answer(self, answer: AnswerResult) -> None:
        self._total_queries += 1
        self._total_claims += 1
        n_sources = len(answer.sources) if answer.sources else 0
        self._total_retrieved += n_sources

        if answer.grounded and n_sources > 0:
            self._cited_claims += 1
            self._relevant_retrieved += n_sources
        elif not answer.grounded and answer.answer:
            if "not found" not in answer.answer.lower():
                self._unsupported += 1

    def record_risk_findings(self, risks: List[RiskFinding]) -> None:
        for r in risks:
            if r.finding_type == "missing_clause":
                continue
            self._total_claims += 1
            if r.verified is True:
                self._cited_claims += 1
            elif r.verified is False:
                self._unsupported += 1

    def record_false_refusal(self) -> None:
        self._false_refusals += 1

    def snapshot(self) -> PipelineMetrics:
        total = max(self._total_claims, 1)
        return PipelineMetrics(
            extraction_confidence=(
                sum(self._extraction_confs) / len(self._extraction_confs)
                if self._extraction_confs else 0.0
            ),
            retrieval_recall_at_k=(
                self._relevant_retrieved / max(self._total_retrieved, 1)
                if self._total_retrieved else 0.0
            ),
            citation_support_rate=self._cited_claims / total,
            unsupported_citation_rate=self._unsupported / total,
            false_refusal_rate=self._false_refusals / max(self._total_queries, 1),
            clauses_cited=self._cited_claims,
            total_claims=total,
            unsupported_claims=self._unsupported,
        )


# ── Module-level singleton (reset per Streamlit session) ─────────────────────
_collector: Optional[MetricsCollector] = None


def get_collector() -> MetricsCollector:
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector


def reset_collector() -> None:
    global _collector
    _collector = None
