"""Clause-aware chunking.

Input : DocumentData (Developer 1 format: pages with page_number + text)
Output: list[Chunk] that respect clause boundaries and keep page references.

Strategy
1. Walk lines page by page, dropping blank lines and page-number footers.
2. Start a new segment whenever a line looks like a clause heading
   ("8.", "8.2", "Clause 8", "Section 4.1", "ARTICLE IV" ...).
3. Merge tiny segments with their parent clause so headings are never orphaned.
4. Split oversized segments into overlapping windows (line / sentence level)
   while tracking the exact page range of every window.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from core.exceptions import InvalidDocumentError
from core.schemas import Chunk, DocumentData

_HEADING_PATTERNS = [
    # "Clause 8", "Section 4.1: Payment"
    re.compile(r"^(?i:clause|section|article)\s+(?P<num>\d{1,3}(?:\.\d{1,3}){0,4})\b[.):\-–]?\s*(?P<title>(?:[A-Z(\"“].*)?)$"),
    # "8.2 Notice period ..."
    re.compile(r"^(?P<num>\d{1,3}(?:\.\d{1,3}){1,4})[.)]?\s+(?!(?i:times|percent|per|million|billion|days?|months?|years?|weeks?|hours?)\b)(?P<title>[A-Za-z(\"“].*)$"),
    # "8. TERMINATION" / "8) Termination"
    re.compile(r"^(?P<num>\d{1,3})[.)]\s+(?P<title>[A-Z(\"“].*)$"),
    # "ARTICLE IV - Confidentiality"
    re.compile(r"^(?i:article|section)\s+(?P<num>[IVXLC]{1,6})\b[.:\-–]?\s*(?P<title>.*)$"),
]
_FOOTER_RE = re.compile(r"^(?i:page\s+)?\d{1,4}(?:\s*(?i:of|/)\s*\d{1,4})?$")
_SENT_SPLIT = re.compile(r"(?<=[.;:])\s+(?=[A-Z(\"“])")


def _clean(line: str) -> str:
    return re.sub(r"\s+", " ", line.replace("\u00a0", " ")).strip()


def _words(text: str) -> int:
    return len(text.split())


def match_heading(line: str) -> Optional[Tuple[str, str]]:
    """Return (clause_number, heading_title) if the line starts a clause."""
    for pat in _HEADING_PATTERNS:
        m = pat.match(line)
        if m:
            num = m.group("num").upper() if not m.group("num")[0].isdigit() else m.group("num")
            title = (m.group("title") or "").strip()
            heading = " ".join(title.lstrip(" -–:.").split()[:10]).rstrip(".:;,")
            return num, heading
    return None


@dataclass
class _Segment:
    clause_ids: List[str] = field(default_factory=list)
    heading: str = ""
    units: List[Tuple[str, int]] = field(default_factory=list)  # (text, page)

    @property
    def words(self) -> int:
        return sum(_words(t) for t, _ in self.units)

    @property
    def parent(self) -> Optional[str]:
        return self.clause_ids[0].split(".")[0] if self.clause_ids else None


def _merge(a: _Segment, b: _Segment) -> _Segment:
    return _Segment(a.clause_ids + b.clause_ids, a.heading or b.heading, a.units + b.units)


def _expand_long_line(text: str, page: int, max_words: int) -> List[Tuple[str, int]]:
    if _words(text) <= max_words:
        return [(text, page)]
    out, buf = [], []
    for sent in _SENT_SPLIT.split(text):
        if buf and _words(" ".join(buf + [sent])) > max_words:
            out.append((" ".join(buf), page))
            buf = []
        buf.append(sent)
    if buf:
        out.append((" ".join(buf), page))
    return out


def _segments(doc: DocumentData, max_words: int) -> List[_Segment]:
    segs: List[_Segment] = []
    cur = _Segment(heading="Preamble")
    for page in sorted(doc.pages, key=lambda p: p.page_number):
        for raw in (page.text or "").splitlines():
            line = _clean(raw)
            if not line or _FOOTER_RE.match(line):
                continue
            hit = match_heading(line)
            if hit:
                if cur.units:
                    segs.append(cur)
                cur = _Segment(clause_ids=[hit[0]], heading=hit[1])
            for u in _expand_long_line(line, page.page_number, max_words):
                cur.units.append(u)
    if cur.units:
        segs.append(cur)
    return segs


def _merge_small(segs: List[_Segment], min_words: int, max_words: int) -> List[_Segment]:
    out: List[_Segment] = []
    carry: Optional[_Segment] = None
    for seg in segs:
        if carry is not None:
            if carry.parent == seg.parent:      # heading-only / tiny clause joins its first child
                seg = _merge(carry, seg)
            else:
                out.append(carry)
            carry = None
        if seg.clause_ids and seg.words < min_words:
            if out and out[-1].parent == seg.parent and out[-1].words + seg.words <= max_words * 1.5:
                out[-1] = _merge(out[-1], seg)
            else:
                carry = seg
        else:
            out.append(seg)
    if carry is not None:
        out.append(carry)
    return out


def _windows(units: List[Tuple[str, int]], max_words: int, overlap_words: int):
    """Yield lists of units, each <= max_words, with trailing overlap."""
    i, n = 0, len(units)
    while i < n:
        j, total = i, 0
        while j < n and (total + _words(units[j][0]) <= max_words or j == i):
            total += _words(units[j][0])
            j += 1
        yield units[i:j]
        if j >= n:
            break
        # step back to create overlap
        back, ow = j, 0
        while back - 1 > i and ow + _words(units[back - 1][0]) <= overlap_words:
            back -= 1
            ow += _words(units[back][0])
        i = back if back > i else j


def chunk_document(doc: DocumentData, max_words: int = 220, min_words: int = 20,
                   overlap_words: int = 30) -> List[Chunk]:
    """Split a document into clause-aware chunks with page references.

    Fix 2 improvements:
    - Preserve section numbers in chunk heading for retrieval boosting
    - Inject cross-reference annotations ([XREF: clause_ids]) into headings
      so BM25 and semantic search can resolve "see Section X" queries
    - Use larger max_words (220) so a full clause is kept intact
    """
    if not doc.pages or not any((p.text or "").strip() for p in doc.pages):
        raise InvalidDocumentError(f"Document {doc.document_id!r} has no extractable text.")
    segs = _merge_small(_segments(doc, max_words), min_words, max_words)

    # Cross-reference regex — Fix 2
    _XREF_RE = re.compile(
        r"\b(?:clause|section|article|schedule|exhibit|annex|appendix)\s+"
        r"(\d{1,3}(?:\.\d{1,3}){0,4})\b",
        re.I,
    )

    chunks: List[Chunk] = []
    for seg in segs:
        for win in _windows(seg.units, max_words, overlap_words):
            text = "\n".join(t for t, _ in win).strip()
            if not text:
                continue
            pages = [p for _, p in win]
            idx = len(chunks)

            # Fix 2: Enrich heading with cross-references found in this chunk's text
            heading = seg.heading
            xrefs = set(_XREF_RE.findall(text)) - set(seg.clause_ids)
            if xrefs:
                heading = heading + " [XREF:" + ",".join(sorted(xrefs)) + "]"

            # Fix 2: Prefix heading with primary clause number for direct lookup
            primary_clause = seg.clause_ids[0] if seg.clause_ids else None
            if primary_clause and primary_clause not in heading:
                heading = f"§{primary_clause} {heading}"

            chunks.append(Chunk(
                chunk_id=f"{doc.document_id}-c{idx:03d}",
                document_id=doc.document_id,
                chunk_index=idx,
                text=text,
                page_start=min(pages),
                page_end=max(pages),
                clause=primary_clause,
                clause_ids=list(seg.clause_ids),
                heading=heading,
            ))
    return chunks
