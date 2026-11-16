"""Fix 3: Legal reasoning layer.

After retrieval and extraction, this module:
- Classifies contract favorability (client / provider / balanced / unclear)
  with a cited rationale referencing specific clauses
- Identifies gaps (expected but absent provisions)
- Produces concrete, cited, actionable recommendations
- Writes a plain-language summary for non-lawyers

Every claim is grounded in retrieved passages or extracted fields.
Unsupported claims are not silently omitted — they trigger a gap entry.
"""
from __future__ import annotations

import json
import re
from typing import Callable, List, Optional

from config.prompts import REASONING_SYSTEM_PROMPT, REASONING_USER_TEMPLATE, wrap_untrusted
from core.schemas import LegalReasoningResult, PlaybookResult, RiskFinding, StructuredFields


def _safe_json(text: str) -> Optional[dict]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return None


def _heuristic_favorability(risks: list[RiskFinding]) -> str:
    high = sum(1 for r in risks if r.severity == "high")
    if high >= 3:
        return "provider-favorable"
    if high == 0 and len(risks) <= 1:
        return "balanced"
    return "unclear"


def _build_fields_summary(extracted_fields: Optional[StructuredFields]) -> str:
    if not extracted_fields:
        return "Not extracted."
    parts = []
    if extracted_fields.governing_law:
        parts.append(f"Governing law: {extracted_fields.governing_law}")
    if extracted_fields.notice_period:
        parts.append(f"Notice period: {extracted_fields.notice_period}")
    if extracted_fields.termination:
        parts.append(f"Termination: {len(extracted_fields.termination)} provision(s) found")
    if extracted_fields.liability:
        parts.append(f"Liability: {len(extracted_fields.liability)} provision(s) found")
    if extracted_fields.indemnity:
        parts.append(f"Indemnity: {len(extracted_fields.indemnity)} provision(s) found")
    if extracted_fields.intellectual_property:
        parts.append(f"IP: {len(extracted_fields.intellectual_property)} provision(s) found")
    if extracted_fields.data_protection:
        parts.append(f"Data protection: {len(extracted_fields.data_protection)} provision(s) found")
    return "\n".join(parts) or "No key fields extracted."


def produce_reasoning(
    doc_type: str,
    extracted_fields: Optional[StructuredFields],
    risks: List[RiskFinding],
    passages_text: str,
    playbook: Optional[PlaybookResult] = None,
    llm: Optional[Callable[[str, str], str]] = None,
) -> LegalReasoningResult:
    """Run the legal reasoning layer. Returns a LegalReasoningResult."""
    absent_provisions = [f.provision for f in (playbook.findings if playbook else [])
                         if f.status == "absent"]

    if llm is None:
        return LegalReasoningResult(
            favorability=_heuristic_favorability(risks),
            favorability_rationale=(
                "Heuristic analysis based on risk severity distribution. "
                "Configure a Gemini API key for clause-cited reasoning."
            ),
            gaps=absent_provisions,
            recommendations=(
                ["Configure a Gemini API key for full AI-powered legal recommendations."]
                if not risks else
                [f"Review [{r.severity.upper()}] risk in {r.clause or 'unknown clause'}: {r.explanation[:80]}"
                 for r in risks[:5]]
            ),
            summary_for_layperson=(
                f"This {doc_type} has {len(risks)} flagged risk(s). "
                + (f"{len(absent_provisions)} expected provision(s) were not found. " if absent_provisions else "")
                + "Consult a lawyer before signing."
            ),
        )

    fields_summary = _build_fields_summary(extracted_fields)
    if absent_provisions:
        fields_summary += f"\n\nMissing provisions (from {playbook.playbook} playbook): " + ", ".join(absent_provisions)

    risks_summary = "\n".join(
        f"[{r.severity.upper()}] {r.clause or 'unknown'}: {r.explanation[:100]}"
        for r in risks[:10]
    ) or "No risks identified."

    prompt = REASONING_USER_TEMPLATE.format(
        doc_type=doc_type,
        extracted_fields=fields_summary,
        risk_findings=risks_summary,
        passages=wrap_untrusted(passages_text[:6000]),
    )

    try:
        raw = llm(REASONING_SYSTEM_PROMPT, prompt)
        data = _safe_json(raw)
    except Exception as exc:
        # Graceful fallback to heuristic reasoning
        return LegalReasoningResult(
            favorability=_heuristic_favorability(risks),
            favorability_rationale=(
                f"Preliminary analysis based on risk distribution ({len(risks)} flagged risk(s)). "
                f"LLM reasoning layer unavailable ({type(exc).__name__})."
            ),
            gaps=absent_provisions,
            recommendations=(
                [f"Review [{r.severity.upper()}] risk in {r.clause or 'flagged clause'}: {r.explanation[:90]}"
                 for r in risks[:5]] or ["No critical risks identified for immediate redlining."]
            ),
            summary_for_layperson=(
                f"This {doc_type} contains {len(risks)} flagged risk(s) and {len(absent_provisions)} missing standard provision(s). "
                "Carefully review the termination and liability clauses with legal counsel before signing."
            ),
        )

    if not data:
        return LegalReasoningResult(
            favorability="unclear",
            favorability_rationale="LLM returned unreadable response for reasoning.",
            gaps=absent_provisions,
        )

    return LegalReasoningResult(
        favorability=data.get("favorability", "unclear"),
        favorability_rationale=data.get("favorability_rationale", ""),
        gaps=data.get("gaps", absent_provisions),
        recommendations=data.get("recommendations", []),
        summary_for_layperson=data.get("summary_for_layperson", ""),
    )
