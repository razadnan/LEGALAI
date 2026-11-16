"""Guards against invented evidence — Task 2: Deterministic Quote Verification.

Every citation (answer source) and every risk-finding evidence quote is checked
against the extracted document text page-by-page. Unverifiable items are rejected
or flagged so that no ungrounded claims are displayed.
"""
from __future__ import annotations

import re
from typing import Optional, Union

from core.schemas import DocumentData, RiskFinding, Source

_MIN_FRAGMENT = 20
MIN_QUOTE_SIMILARITY = 0.85


def normalize_text(text: str) -> str:
    """Normalize text for robust comparison across PDF line-breaks and formatting."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[“”‘’]", "'", text)
    text = re.sub(r"[^\w\s$%.,;:()-]", "", text)
    return text.strip()


def quote_exists_on_page(
    quote: str,
    page_text: str,
    min_similarity: float = MIN_QUOTE_SIMILARITY,
) -> bool:
    """Deterministic check whether quote exists on the given page text.

    Uses normalized exact substring match as primary verification.
    Also handles multi-line wrapping and PDF hyphenation via sliding word windows.
    (Note: SequenceMatcher on a short quote vs whole page scores near zero,
    so substring matching is strictly used here per design review.)
    """
    if not quote or not page_text:
        return False
    norm_q = normalize_text(quote)
    norm_p = normalize_text(page_text)
    if not norm_q or not norm_p:
        return False

    # 1. Exact normalized substring match
    if norm_q in norm_p:
        return True

    # 2. Fragment check (for quotes with ellipses '...')
    fragments = [f.strip() for f in re.split(r"[.][.][.]|\u2026", norm_q) if len(f.strip()) >= 15]
    if len(fragments) > 1:
        if all(f in norm_p for f in fragments):
            return True

    # 3. Word window match (handles line break hyphenation or single dropped punctuation)
    words = norm_q.split()
    if len(words) >= 4:
        first_three = " ".join(words[:3])
        last_three = " ".join(words[-3:])
        if first_three in norm_p and last_three in norm_p:
            start = norm_p.find(first_three)
            end = norm_p.find(last_three, start)
            if end != -1 and (end - start) <= len(norm_q) * 1.5:
                return True

    return False


def validate_source(source: Union[dict, Source], document_pages: dict[int, str]) -> bool:
    """Validate that source has a valid page and its quote exists on that page."""
    page = getattr(source, "page", None) if isinstance(source, Source) else source.get("page")
    quote = getattr(source, "text", "") if isinstance(source, Source) else (source.get("quote") or source.get("text", ""))
    if page is None or not quote:
        return False
    page_text = document_pages.get(page)
    if page_text is None:
        return False
    return quote_exists_on_page(quote, page_text)


def confidence_score(snippet: str, haystack: str) -> float:
    """Return 0.0-1.0 confidence that snippet is supported by haystack."""
    if not snippet or len(snippet.strip()) < 10:
        return 0.0
    norm_s = normalize_text(snippet)
    norm_h = normalize_text(haystack)
    if norm_s in norm_h:
        return 1.0
    fragments = [f.strip() for f in re.split(r"[.][.][.]|\u2026", norm_s) if len(f.strip()) >= _MIN_FRAGMENT]
    if not fragments:
        return 0.0
    found = sum(1 for f in fragments if f in norm_h)
    ratio = found / len(fragments)
    if ratio >= 1.0:
        return 0.9
    if ratio >= 0.5:
        return 0.4
    return 0.0


def text_is_supported(snippet: str, haystack: str) -> bool:
    """True if snippet appears on haystack or its key fragments appear."""
    norm_s = normalize_text(snippet)
    norm_h = normalize_text(haystack)
    if not norm_s:
        return False
    if norm_s in norm_h:
        return True
    fragments = [f.strip() for f in re.split(r"[.][.][.]|\u2026", norm_s) if len(f.strip()) >= _MIN_FRAGMENT]
    if not fragments:
        return norm_s in norm_h
    return all(f in norm_h for f in fragments)


def verify_text(snippet: str, page: Optional[int], doc: DocumentData) -> bool:
    if page is not None:
        page_text = doc.page_text(page)
        if page_text is None:
            return False
        return quote_exists_on_page(snippet, page_text)
    return text_is_supported(snippet, doc.full_text)


def verify_sources(sources: list[Source], doc: DocumentData) -> tuple[list[Source], list[str]]:
    """Validate all sources against page text. Unverifiable sources are marked."""
    warnings: list[str] = []
    out = []
    page_map = {p.page_number: p.text for p in doc.pages}
    for s in sources:
        ok = validate_source(s, page_map)
        out.append(s.model_copy(update={"verified": ok}))
        if not ok:
            where = f"page {s.page}" if s.page is not None else "the document"
            warnings.append(f"A cited passage could not be verified against {where} - treat it with caution.")
    return out, sorted(set(warnings))


def verify_risks(risks: list[RiskFinding], doc: DocumentData) -> tuple[list[RiskFinding], list[str]]:
    out, unverified = [], 0
    page_map = {p.page_number: p.text for p in doc.pages}
    for r in risks:
        ev_text = r.evidence_text
        if ev_text and len(ev_text.strip()) >= 15:
            if r.page is not None and r.page in page_map:
                ok = quote_exists_on_page(ev_text, page_map[r.page])
            else:
                ok = text_is_supported(ev_text, doc.full_text)
        else:
            ok = None if r.finding_type == "missing_clause" else False
        out.append(r.model_copy(update={"verified": ok}))
        if ok is False:
            unverified += 1
    warnings = [f"{unverified} risk finding(s) have evidence that could not be verified in the document."] if unverified else []
    return out, warnings
