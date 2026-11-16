"""Fix 5: Missing-clause checklist.

Compares a document against a configurable playbook (SaaS, MSA, NDA, Employment,
Professional Services) and reports each provision as:
  present / absent / partial / conflicting

Every 'present' or 'partial' finding includes clause_number, exact_quote, page.
Every 'absent' finding is a gap to flag for review.
"""
from __future__ import annotations

import json
import re
from typing import Callable, Optional

from config.prompts import PLAYBOOK_SYSTEM_PROMPT, PLAYBOOKS, wrap_untrusted
from core.schemas import DocumentData, PlaybookFinding, PlaybookResult

_MAX_CHARS = 20_000


def _safe_json(text: str) -> Optional[list]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return None


def _detect_playbook(doc_type: str) -> str:
    dt = doc_type.lower()
    if any(w in dt for w in ("saas", "software", "subscription", "cloud")):
        return "SaaS"
    if any(w in dt for w in ("master", "msa", "framework", "master service")):
        return "MSA"
    if any(w in dt for w in ("nda", "non-disclosure", "non disclosure", "confidential")):
        return "NDA"
    if any(w in dt for w in ("employ", "staff", "worker", "labour", "labor")):
        return "Employment"
    if any(w in dt for w in ("service", "consulting", "professional", "statement of work")):
        return "Professional Services"
    return "MSA"


def _heuristic_check(provision: str, full_text: str) -> str:
    """Keyword-based fallback when no LLM is available."""
    _KEYWORD_MAP = {
        "limitation of liability": ["limitation of liability", "liability cap", "not liable",
                                    "maximum liability", "aggregate liability"],
        "sla": ["service level", "uptime", "availability", "response time"],
        "data protection": ["data protection", "gdpr", "personal data", "data processing",
                            "data controller"],
        "confidentiality": ["confidential", "non-disclosure", "proprietary information",
                            "trade secret"],
        "termination": ["terminat", "cancel this agreement", "end of agreement"],
        "governing law": ["governing law", "jurisdiction", "governed by the laws"],
        "intellectual property": ["intellectual property", "copyright", "ip ownership",
                                  "work product"],
        "indemnification": ["indemni", "hold harmless", "defend"],
        "insurance": ["insurance", "coverage", "insured", "policy"],
        "acceptance": ["acceptance", "accept the deliverable", "approval criteria"],
        "payment": ["payment", "invoice", "fee", "remuneration"],
        "warranty": ["warrant", "guarantee", "representation"],
        "dispute": ["dispute", "arbitration", "mediation"],
    }
    text_l = full_text.lower()
    prov_l = provision.lower()

    for key, kws in _KEYWORD_MAP.items():
        if key in prov_l or any(k in prov_l for k in kws):
            matches = sum(1 for kw in kws if kw in text_l)
            if matches >= 2:
                return "present"
            if matches == 1:
                return "partial"
            return "absent"

    # generic word match
    words = [w for w in re.sub(r"[^a-z\s]", "", prov_l).split() if len(w) > 4]
    matched = sum(1 for w in words if w in text_l)
    if matched >= 2:
        return "partial"
    return "absent"


def check_missing_clauses(
    doc: DocumentData,
    doc_type: str,
    llm: Optional[Callable[[str, str], str]] = None,
    playbook_name: Optional[str] = None,
) -> PlaybookResult:
    """Run the missing-clause checklist for a document."""
    playbook = playbook_name or _detect_playbook(doc_type)
    provisions = PLAYBOOKS.get(playbook, PLAYBOOKS["MSA"])
    full_text = doc.full_text
    truncated = full_text[:_MAX_CHARS]

    findings: list[PlaybookFinding] = []

    if llm is None:
        for prov in provisions:
            status = _heuristic_check(prov, full_text)
            findings.append(PlaybookFinding(
                provision=prov,
                status=status,
                note="Heuristic check (no LLM configured).",
            ))
    else:
        provision_list = "\n".join(f"- {p}" for p in provisions)
        prompt = (
            f"Contract type: {doc_type}\n"
            f"Check whether each of the following provisions is present in the contract below.\n"
            f"Provisions to check:\n{provision_list}\n\n"
            "Return a JSON array where each item has:\n"
            '  "provision": string (from the list above),\n'
            '  "status": "present"|"absent"|"partial"|"conflicting",\n'
            '  "clause_number": string or "",\n'
            '  "exact_quote": verbatim text max 200 chars or "",\n'
            '  "page": integer or null,\n'
            '  "note": brief explanation\n\n'
            f"{wrap_untrusted(truncated)}"
        )
        try:
            raw = llm(PLAYBOOK_SYSTEM_PROMPT, prompt)
            items = _safe_json(raw) or []
        except Exception:
            items = []

        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            prov = item.get("provision", "")
            if prov in seen:
                continue
            seen.add(prov)
            findings.append(PlaybookFinding(
                provision=prov,
                status=item.get("status", "absent"),
                clause=item.get("clause_number", ""),
                exact_quote=item.get("exact_quote", ""),
                note=item.get("note", ""),
                page=item.get("page"),
            ))

        # Fill in any provisions the LLM skipped
        found_provisions = {f.provision for f in findings}
        for prov in provisions:
            if prov not in found_provisions:
                status = _heuristic_check(prov, full_text)
                findings.append(PlaybookFinding(
                    provision=prov,
                    status=status,
                    note="LLM skipped this provision; heuristic fallback used.",
                ))

    present = sum(1 for f in findings if f.status == "present")
    absent = sum(1 for f in findings if f.status == "absent")
    partial = sum(1 for f in findings if f.status == "partial")
    conflicting = sum(1 for f in findings if f.status == "conflicting")

    return PlaybookResult(
        playbook=playbook,
        findings=findings,
        present_count=present,
        absent_count=absent,
        partial_count=partial,
        conflicting_count=conflicting,
    )
