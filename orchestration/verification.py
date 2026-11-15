"""Guards against invented evidence.

Every citation (answer source) and every risk-finding evidence quote is checked
against the extracted document text. Unverifiable items are flagged (never
silently dropped) so the UI and PDF report can warn the reader.
"""
from __future__ import annotations

import re
from typing import Optional

from core.schemas import DocumentData, RiskFinding, Source

_MIN_FRAGMENT = 20


def _norm(text: str) -> str:
    return re.sub(r"[\s ]+", " ", text or "").strip().lower()


def text_is_supported(snippet: str, haystack: str) -> bool:
    """True if every substantial fragment of ``snippet`` appears in ``haystack``.

    Snippets may contain ellipses ("...") where the producer shortened the text,
    so each fragment between ellipses is checked separately.
    """
    snippet_n, hay = _norm(snippet), _norm(haystack)
    if not snippet_n:
        return False
    fragments = [f.strip() for f in re.split(r"\.\.\.|…", snippet_n) if len(f.strip()) >= _MIN_FRAGMENT]
    if not fragments:
        return snippet_n in hay
    return all(f in hay for f in fragments)


def verify_text(snippet: str, page: Optional[int], doc: DocumentData) -> bool:
    if page is not None:
        page_text = doc.page_text(page)
        if page_text is None:
            return False  # cited page does not exist
        return text_is_supported(snippet, page_text)
    return text_is_supported(snippet, doc.full_text)


def verify_sources(sources: list[Source], doc: DocumentData) -> tuple[list[Source], list[str]]:
    warnings: list[str] = []
    out = []
    for s in sources:
        ok = verify_text(s.text, s.page, doc)
        out.append(s.model_copy(update={"verified": ok}))
        if not ok:
            where = f"page {s.page}" if s.page is not None else "the document"
            warnings.append(f"A cited passage could not be verified against {where} - treat it with caution.")
    return out, sorted(set(warnings))


def verify_risks(risks: list[RiskFinding], doc: DocumentData) -> tuple[list[RiskFinding], list[str]]:
    out, unverified = [], 0
    for r in risks:
        # evidence_text is a @property that handles list[Evidence] and plain str correctly
        ev_text = r.evidence_text
        # Only try to verify non-trivial evidence text
        if ev_text and len(ev_text.strip()) >= 15:
            ok = verify_text(ev_text, r.page, doc)
        else:
            # Missing-clause findings have no evidence quote by design; mark as None (unknown)
            ok = None if r.finding_type == "missing_clause" else False
        out.append(r.model_copy(update={"verified": ok}))
        if ok is False:
            unverified += 1
    warnings = [f"{unverified} risk finding(s) have evidence that could not be verified in the document."] if unverified else []
    return out, warnings
