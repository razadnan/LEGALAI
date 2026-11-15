"""Stand-in implementations of Developer 1 / Developer 2 interfaces.

These exist ONLY so the application and tests run before the real modules are
merged (and offline, without an API key). They are heuristic and extractive -
no LLM is involved. ``Services`` (adapters.py) prefers the real modules and
reports which backend is active, so the UI never pretends these are the real AI.
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

from core.exceptions import AgentError, ModuleUnavailableError, UnsupportedFileError
from core.schemas import (AnswerResult, ComparisonChange, ComparisonResult, DocumentAnalysis,
                          DocumentData, ImportantDate, Obligation, Page, RiskFinding, Source)

CLAUSE_RE = re.compile(r"^\s*(?:(?:Section|Clause|Article)\s+)?(\d{1,2}(?:\.\d{1,2})*)[.):]?\s+\S")
CLAUSE_QUERY_RE = re.compile(r"(?:clause|section|article)\s+(\d{1,2}(?:\.\d{1,2})*)", re.I)
_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE_RE = re.compile(
    rf"\b(\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTHS})\s+\d{{4}}|(?:{_MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}"
    r"|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})\b", re.I)
STOPWORDS = set("a an the of to in on for and or is are was be my our your what who when where which how does do "
                "this that with by as at it its any can shall about explain tell me please".split())
VIRTUAL_PAGE_CHARS = 3000


# --------------------------------------------------------------------------- #
# Developer 1 stand-ins
# --------------------------------------------------------------------------- #
def _clean(text: str) -> str:
    text = text.replace("\r", "\n").replace(" ", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def process_document(file_path: str | Path, document_id: str) -> DocumentData:
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        pages = _read_pdf(path)
    elif ext == ".docx":
        pages = _read_docx(path)
    else:
        raise UnsupportedFileError(f"Unsupported extension {ext}")
    return DocumentData(document_id=document_id, filename=path.name,
                        pages=[Page(page_number=i + 1, text=_clean(t)) for i, t in enumerate(pages)])


def _read_pdf(path: Path) -> list[str]:
    try:
        import pymupdf as fitz  # PyMuPDF

        with fitz.open(path) as pdf:
            return [page.get_text() for page in pdf]
    except ImportError:
        pass
    try:
        from pypdf import PdfReader

        return [(p.extract_text() or "") for p in PdfReader(str(path)).pages]
    except ImportError as exc:
        raise ModuleUnavailableError("No PDF library installed", user_message=
                                     "PDF support requires PyMuPDF. Run: pip install -r requirements.txt") from exc
    except Exception as exc:
        raise UnsupportedFileError(f"Could not read PDF: {exc}",
                                   user_message="The PDF could not be read. It may be corrupted or encrypted.") from exc


def _read_docx(path: Path) -> list[str]:
    try:
        import docx
    except ImportError as exc:
        raise ModuleUnavailableError("python-docx missing", user_message=
                                     "DOCX support requires python-docx. Run: pip install -r requirements.txt") from exc
    try:
        paragraphs = [p.text for p in docx.Document(str(path)).paragraphs]
    except Exception as exc:
        raise UnsupportedFileError(f"Could not read DOCX: {exc}",
                                   user_message="The DOCX file could not be read. It may be corrupted.") from exc
    pages, current, size = [], [], 0  # DOCX has no fixed pagination: use virtual pages
    for para in paragraphs:
        current.append(para)
        size += len(para)
        if size >= VIRTUAL_PAGE_CHARS:
            pages.append("\n".join(current))
            current, size = [], 0
    if current:
        pages.append("\n".join(current))
    return pages


def split_clauses(doc: DocumentData) -> list[dict]:
    """Split a document into clause/paragraph units: {ref, page, text}."""
    units: list[dict] = []
    for page in doc.pages:
        cur: dict | None = None
        for line in page.text.split("\n"):
            m = CLAUSE_RE.match(line)
            if m:
                cur = {"ref": m.group(1), "page": page.page_number, "text": line.strip()}
                units.append(cur)
            elif not line.strip():
                if cur is not None and cur["ref"] is None:
                    cur = None
            elif cur is None:
                cur = {"ref": None, "page": page.page_number, "text": line.strip()}
                units.append(cur)
            else:
                cur["text"] += " " + line.strip()
    return units


_RISK_PATTERNS = [
    (r"non-?compete|restrain(?:t)? of trade|shall not (?:work|engage|be employed)", "Non-compete / restraint",
     "high", "Restricts future work and may be hard to enforce or very limiting.",
     "How long and how broad is this restriction, and is it enforceable where I live?"),
    (r"indemnif", "Indemnification", "high", "One party may have to cover the other's losses, potentially without limit.",
     "Is the indemnity capped or mutual?"),
    (r"unlimited liability|liability (?:shall|will) not be limited|without limit", "Unlimited liability", "high",
     "Liability does not appear to be capped.", "Can a liability cap be negotiated?"),
    (r"terminate[^.]{0,60}(?:at any time|without cause|sole discretion)|sole discretion", "Unilateral discretion / termination",
     "medium", "One party may act or terminate at its sole discretion.", "Do both parties get equal termination rights?"),
    (r"automatic(?:ally)? renew|auto-?renew", "Automatic renewal", "medium",
     "The agreement may renew without a fresh decision.", "What is the notice window to stop renewal?"),
    (r"penalt|liquidated damages", "Penalty / liquidated damages", "medium",
     "Fixed financial penalties may apply on breach.", "Are these amounts proportionate?"),
    (r"arbitration|exclusive jurisdiction|governing law", "Dispute resolution / jurisdiction", "low",
     "Sets where and how disputes are resolved.", "Is the chosen forum convenient and fair?"),
    (r"intellectual property|assigns? all|work product|invention", "IP assignment", "medium",
     "Ownership of work product or inventions may transfer to the other party.", "Does this cover work done outside working hours?"),
    (r"confidential", "Confidentiality obligations", "low",
     "Imposes confidentiality duties that may survive termination.", "How long do confidentiality duties last?"),
]


def analyze_document(doc: DocumentData) -> DocumentAnalysis:
    text = doc.full_text
    lower = text.lower()
    units = split_clauses(doc)

    if "employment" in lower[:2500]:
        dtype = "Employment Agreement"
    elif re.search(r"non-?disclosure|confidentiality agreement", lower[:2500]):
        dtype = "Non-Disclosure Agreement"
    elif "lease" in lower[:2500]:
        dtype = "Lease Agreement"
    elif re.search(r"services? agreement|statement of work", lower[:2500]):
        dtype = "Services Agreement"
    else:
        dtype = "Contract / Legal Document"

    parties: list[str] = []
    m = re.search(r"between\s+(.{3,120}?)\s+(?:\([^)]*\)\s*)?and\s+(.{3,120}?)(?:[,(.;\n]|\s+\()", text[:4000],
                  re.I | re.S)
    if m:
        parties = [re.sub(r"\s+", " ", g).strip(" .,") for g in m.groups()]

    dates, seen = [], set()
    for page in doc.pages:
        for dm in DATE_RE.finditer(page.text):
            if dm.group(1) in seen:
                continue
            seen.add(dm.group(1))
            ctx = re.sub(r"\s+", " ", page.text[max(0, dm.start() - 45):dm.start()]).strip(" :,-")
            dates.append(ImportantDate(label=ctx[-40:] or "Date", date=dm.group(1), page=page.page_number))

    obligations = []
    for u in units:
        for sentence in re.split(r"(?<=[.;])\s+", u["text"]):
            sm = re.search(r"\b(shall|must|agrees? to|is required to|undertakes? to)\b", sentence, re.I)
            if sm and len(obligations) < 15:
                subject = sentence[:sm.start()].strip(" ,:") or None
                obligations.append(Obligation(description=sentence[:300], party=subject[-60:] if subject else None,
                                              page=u["page"]))

    risks = analyze_risks(doc)
    summary = (f"{dtype} with {len(doc.pages)} page(s)"
               + (f" between {' and '.join(parties)}" if len(parties) == 2 else "")
               + f". {len(obligations)} obligation(s), {len(dates)} date(s) and {len(risks)} item(s) flagged for review "
               "were found by the fallback heuristic analyzer.")
    return DocumentAnalysis(document_type=dtype, parties=parties, important_dates=dates[:15],
                            obligations=obligations, risk_findings=risks, summary=summary)


def analyze_risks(doc: DocumentData) -> list[RiskFinding]:
    findings, used = [], set()
    for u in split_clauses(doc):
        for pattern, title, severity, why, question in _RISK_PATTERNS:
            if re.search(pattern, u["text"], re.I) and (title, u["ref"], u["page"]) not in used:
                used.add((title, u["ref"], u["page"]))
                label = f"Clause {u['ref']}: {title}" if u["ref"] else title
                findings.append(RiskFinding(clause=label, severity=severity, explanation=why,
                                            evidence=u["text"][:500], page=u["page"], lawyer_question=question))
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(findings, key=lambda f: order[f.severity])


# --------------------------------------------------------------------------- #
# Developer 2 stand-ins (extractive "RAG": keyword overlap, no embeddings)
# --------------------------------------------------------------------------- #
_INDEX: dict[str, DocumentData] = {}


def index_document(doc: DocumentData) -> None:
    _INDEX[doc.document_id] = doc


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS and len(t) > 1}


def answer_question(
    document_id: str,
    question: str,
    chat_history: list[dict[str, str]] | None = None,
) -> AnswerResult:
    doc = _INDEX.get(document_id)
    if doc is None:
        raise AgentError(f"{document_id} is not indexed", user_message="The document is not indexed yet.")
    units = split_clauses(doc)
    retrieval_question = question
    latest_user_question = next(
        (item["content"] for item in reversed(chat_history or []) if item.get("role") == "user" and item.get("content")),
        "",
    )
    if latest_user_question and re.search(
        r"\b(it|that|this|they|them|those|these|there|same)\b|^(?:what about|and|why|how so|explain it)\b",
        question.strip(),
        re.I,
    ):
        retrieval_question = f"{latest_user_question} {question}"
    q_tokens = _tokens(retrieval_question)
    wanted = CLAUSE_QUERY_RE.search(question)
    scored = []
    for u in units:
        score = len(q_tokens & _tokens(u["text"])) / (len(q_tokens) or 1)
        if wanted and u["ref"] and (u["ref"] == wanted.group(1) or u["ref"].startswith(wanted.group(1) + ".")):
            score += 1.0
        scored.append((score, u))
    top = [(s, u) for s, u in sorted(scored, key=lambda x: -x[0])[:3] if s > 0]
    if not top:
        return AnswerResult(answer="I could not find anything in the document that answers this question.", sources=[])
    best = top[0][1]
    ref = f"clause {best['ref']}, " if best["ref"] else ""
    answer = (f"The most relevant passage ({ref}page {best['page']}) says: {best['text'][:450]}\n\n"
              "(Extractive fallback answer - connect the RAG engine for a generated, evidence-checked answer.)")
    return AnswerResult(answer=answer, sources=[Source(page=u["page"], clause=u["ref"], text=u["text"][:500])
                                                for _, u in top])


def compare_documents(doc_a: DocumentData, doc_b: DocumentData) -> ComparisonResult:
    """Structured diff over clause/paragraph units (not one big prompt)."""
    a_units, b_units = split_clauses(doc_a), split_clauses(doc_b)
    norm = lambda u: re.sub(r"\s+", " ", u["text"]).strip().lower()  # noqa: E731
    sm = difflib.SequenceMatcher(None, [norm(u) for u in a_units], [norm(u) for u in b_units], autojunk=False)
    changes: list[ComparisonChange] = []

    def section(u):
        return f"Clause {u['ref']}" if u["ref"] else "Unnumbered paragraph"

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        olds, news = a_units[i1:i2], b_units[j1:j2]
        for k in range(max(len(olds), len(news))):
            o = olds[k] if k < len(olds) else None
            n = news[k] if k < len(news) else None
            if o and n:
                ctype, summ = "modified", f"{section(n)} was modified."
            elif o:
                ctype, summ = "removed", f"{section(o)} was removed."
            else:
                ctype, summ = "added", f"{section(n)} was added."
            changes.append(ComparisonChange(
                change_type=ctype, section=section(n or o), old_text=(o or {}).get("text", "")[:600],
                new_text=(n or {}).get("text", "")[:600], summary=summ,
                old_page=o["page"] if o else None, new_page=n["page"] if n else None))
    counts = {t: sum(c.change_type == t for c in changes) for t in ("added", "removed", "modified")}
    summary = (f"Compared {doc_a.filename} with {doc_b.filename}: {counts['modified']} modified, "
               f"{counts['added']} added, {counts['removed']} removed clause(s)/paragraph(s).")
    return ComparisonResult(summary=summary, changes=changes)
