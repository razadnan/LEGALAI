"""Developer 1 - document analysis.

Turns DocumentData into structured information: document type, parties, dates, key terms,
payment terms, obligations and key clauses (+ risk findings from risk_analyzer).

Approach: deterministic, rule-based extraction that works offline and is fully traceable
(every item carries page + clause + verbatim evidence). An OPTIONAL LLM pass can add items,
but anything it returns is kept only if its quoted evidence is found verbatim in the
document, so the model cannot invent clauses or page references.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from core.schemas import (DocumentAnalysis, DocumentData, Evidence, ImportantDate, KeyClause,
                          KeyTerm, Obligation, Party, PaymentTerm)

# =================================================================== text helpers
def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


class PageIndex:
    """Locate / verify snippets against the page text."""

    def __init__(self, doc: DocumentData):
        self.pages = {p.page_number: norm(p.text) for p in doc.pages}
        self.all = " ".join(self.pages[k] for k in sorted(self.pages))

    def locate(self, snippet: str) -> Optional[int]:
        key = norm(snippet)[:70]
        if not key:
            return None
        for pn in sorted(self.pages):
            if key in self.pages[pn]:
                return pn
        return None

    def contains(self, snippet: str) -> bool:
        s = norm(snippet)
        return bool(s) and s in self.all


# =================================================================== durations / dates / money
_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
          "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
          "thirty": 30, "forty-five": 45, "forty": 40, "sixty": 60, "ninety": 90,
          "one hundred": 100, "hundred": 100}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}
_WORDS.update({"fifty": 50, "seventy": 70, "eighty": 80, "thirteen": 13, "fourteen": 14,
               "eighteen": 18, "twenty-four": 24})
_UNITS = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
_COMPOUND = "(?:" + "|".join(_TENS) + ")-(?:" + "|".join(_UNITS) + ")"
_WORD_ALT = _COMPOUND + "|" + "|".join(sorted(map(re.escape, _WORDS), key=len, reverse=True))
DUR = (rf"(?P<num>\d+|{_WORD_ALT})\s*(?:\(\s*(?P<paren>\d+)\s*\)\s*)?"
       r"(?P<unit>(?:business|working|calendar)\s+days?|days?|weeks?|months?|years?)\b")
DUR_RE = re.compile(DUR, re.I)
_UNIT_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}


def parse_duration(m: re.Match) -> dict:
    num = m.group("num").lower()
    if m.group("paren"):
        n = int(m.group("paren"))
    elif num.isdigit():
        n = int(num)
    elif num in _WORDS:
        n = _WORDS[num]
    else:
        tens, unit_word = num.split("-")
        n = _TENS[tens] + _WORDS[unit_word]
    unit = "day" if "day" in m.group("unit").lower() else m.group("unit").lower().rstrip("s")
    text = m.string[m.start("num"):m.end("unit")]
    return {"n": n, "unit": unit, "text": text, "days": n * _UNIT_DAYS[unit]}


_MONTHS = ("January|February|March|April|May|June|July|August|September|October|November|"
           "December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec")
DATE_RE = re.compile(
    rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?(?:{_MONTHS})\.?,?\s+\d{{4}}\b"
    rf"|\b(?:{_MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b"
    r"|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b")
_MONTH_NUM = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September",
     "October", "November", "December"], 1)}


def parse_date(text: str) -> Optional[str]:
    t = text.strip()
    if m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", t):
        return t
    if m := re.match(r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?([A-Za-z]+)\.?,?\s+(\d{4})", t):
        mon = next((v for k, v in _MONTH_NUM.items() if k.startswith(m.group(2).lower()[:3])), None)
        return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}" if mon else None
    if m := re.match(r"([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", t):
        mon = next((v for k, v in _MONTH_NUM.items() if k.startswith(m.group(1).lower()[:3])), None)
        return f"{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}" if mon else None
    return None  # numeric d/m/y formats are ambiguous; left un-normalised on purpose


MONEY_RE = re.compile(r"(?:INR|Rs\.?|\u20b9|USD|US\$|\$|EUR|\u20ac|GBP|\u00a3)\s?\d[\d,]*(?:\.\d+)?"
                      r"(?:\s?(?:million|billion|lakhs?|crores?|thousand))?", re.I)
PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s?%")

# =================================================================== clause segmentation
_ABBR = re.compile(r"\b(Pvt|Ltd|Inc|Mr|Ms|Mrs|Dr|No|Nos|Rs|St|Co|Corp|vs|etc|Sr|Jr|Art|Sec|Cl)\.", re.I)


def split_sentences(text: str) -> list[str]:
    t = _ABBR.sub(lambda m: m.group(1) + "\x00", text)
    t = t.replace("e.g.", "e\x00g\x00").replace("i.e.", "i\x00e\x00")
    parts = re.split(r'(?<=[.;])\s+(?=[A-Z("])', t)
    return [p.replace("\x00", ".").strip() for p in parts if len(p.strip()) >= 20]


_CAT_KEYWORDS = {
    "termination": ["terminat", "notice period", "resign", "expiry"],
    "confidentiality": ["confidential", "non-disclosure", "trade secret", "proprietary information"],
    "payment": ["salary", "remuneration", "compensation", "fee", "payable", "invoice", "payment",
                "bonus", "wages", "reimburs"],
    "non_compete": ["non-compet", "non compet", "restraint of trade", "compete", "solicit"],
    "intellectual_property": ["intellectual property", "invention", "copyright", "patent",
                              "work product"],
    "indemnity": ["indemn", "hold harmless"],
    "liability": ["limitation of liability", "liable", "liability"],
    "governing_law": ["governing law", "governed by", "jurisdiction", "courts of"],
    "dispute_resolution": ["arbitrat", "dispute", "mediation"],
    "term": ["commence", "probation", "term of", "effective date", "renew"],
    "duties": ["duties", "position", "responsibilit", "scope of"],
    "amendment": ["amend", "modif", "variation"],
    "assignment": ["assign"],
}
IMPORTANT_CATEGORIES = ["termination", "confidentiality", "payment", "non_compete",
                        "intellectual_property", "indemnity", "liability", "governing_law",
                        "dispute_resolution", "amendment", "term"]


def categorize(title: str, text: str) -> str:
    title_l, text_l = title.lower(), text.lower()[:400]
    best, best_score = "general", 0
    for cat, kws in _CAT_KEYWORDS.items():
        score = sum(3 * title_l.count(k) + text_l.count(k) for k in kws)
        if score > best_score:
            best, best_score = cat, score
    return best


@dataclass
class Clause:
    clause_id: str
    title: str
    section_title: str
    page: int
    text: str = ""
    category: str = "general"
    is_heading: bool = False


@dataclass
class Unit:
    """One sentence with its position - the basic evidence unit."""
    text: str
    clause_id: str
    title: str
    category: str
    page: int


@dataclass
class Context:
    doc: DocumentData
    idx: PageIndex
    clauses: list[Clause]
    units: list[Unit]
    doc_type: str = "Legal document"
    basis: list[str] = field(default_factory=list)

    def evidence(self, unit: Unit) -> Evidence:
        text = unit.text[:600]
        return Evidence(page=unit.page, clause=None if unit.clause_id == "preamble" else unit.clause_id,
                        text=text, verified=self.idx.contains(text))


_DOTTED = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){1,3})\.?\s+(\S.*)$")
_TOP = re.compile(r"^(\d{1,2})[.)]\s+(\S.*)$")
_ARTICLE = re.compile(r"^(?:ARTICLE|Article|SECTION|Section|CLAUSE|Clause)\s+(\d+(?:\.\d+)*|[IVXL]+)\s*[.:\-]?\s*(.*)$")


def segment_clauses(doc: DocumentData) -> list[Clause]:
    clauses: list[Clause] = []
    cur = Clause("preamble", "Preamble", "Preamble", 1)
    section = "Preamble"
    for page in doc.pages:
        for line in (ln.strip() for ln in page.text.split("\n")):
            if not line:
                continue
            m_art, m_dot, m_top = _ARTICLE.match(line), _DOTTED.match(line), _TOP.match(line)
            starts_upper = lambda s: bool(s) and (s[0].isupper() or s[0] in '("')
            if m_art and m_art.group(2):
                new = Clause(m_art.group(1), m_art.group(2).strip(), m_art.group(2).strip(), page.page_number,
                             is_heading=True)
                section = new.title
            elif m_dot and starts_upper(m_dot.group(2)):
                new = Clause(m_dot.group(1), section, section, page.page_number, m_dot.group(2))
            elif m_top and starts_upper(m_top.group(2)):
                rest = m_top.group(2)
                if len(rest) <= 70 and not rest.endswith((".", ";", ",")):
                    new = Clause(m_top.group(1), rest, rest, page.page_number, is_heading=True)
                    section = rest
                else:
                    new = Clause(m_top.group(1), section, section, page.page_number, rest)
            else:
                cur.text = (cur.text + " " + line).strip()
                continue
            clauses.append(cur)
            cur = new
    clauses.append(cur)
    for c in clauses:
        c.category = categorize(c.section_title, c.text)
    return [c for c in clauses if c.text or c.is_heading]


def build_units(doc: DocumentData, clauses: list[Clause], idx: PageIndex) -> list[Unit]:
    units = []
    for c in clauses:
        for s in split_sentences(c.text):
            units.append(Unit(s, c.clause_id, c.title, c.category, idx.locate(s) or c.page))
    return units


# =================================================================== document type
_TYPE_KEYWORDS = {
    "Employment Agreement": ["employment", "employee", "employer", "probation", "salary"],
    "Non-Disclosure Agreement": ["non-disclosure", "disclosing party", "receiving party", "confidential information"],
    "Lease / Rental Agreement": ["lease", "landlord", "tenant", "rent", "premises", "lessor", "lessee"],
    "Service Agreement": ["services", "service provider", "client", "statement of work", "deliverables"],
    "Consulting / Contractor Agreement": ["consultant", "independent contractor", "contractor"],
    "Sale / Purchase Agreement": ["purchase price", "seller", "buyer", "sale of"],
    "Loan Agreement": ["lender", "borrower", "loan", "principal amount", "repayment"],
    "Partnership Agreement": ["partnership", "partners", "profit sharing", "capital contribution"],
    "License Agreement": ["licensor", "licensee", "licence", "license grant"],
}


def classify_document(doc: DocumentData) -> tuple[str, list[str]]:
    text = doc.full_text.lower()
    head = text[:500]
    best, best_score, best_hits = "Legal document", 0, []
    for typ, kws in _TYPE_KEYWORDS.items():
        hits = [k for k in kws if k in text]
        score = len(hits) + 3 * sum(1 for k in kws if k in head)
        if typ.split()[0].lower() in head:
            score += 5
        if score > best_score:
            best, best_score, best_hits = typ, score, hits
    return (best, best_hits) if best_score >= 3 else ("Legal document (type unclear)", best_hits)


# =================================================================== context builder
def build_context(doc: DocumentData | dict) -> Context:
    if isinstance(doc, dict):
        doc = DocumentData.model_validate(doc)
    idx = PageIndex(doc)
    clauses = segment_clauses(doc)
    units = build_units(doc, clauses, idx)
    typ, basis = classify_document(doc)
    return Context(doc, idx, clauses, units, typ, basis)


# =================================================================== extractors
ROLE_WORDS = {"employer", "employee", "company", "client", "contractor", "consultant", "service provider",
              "customer", "vendor", "supplier", "landlord", "tenant", "lessor", "lessee", "licensor",
              "licensee", "disclosing party", "receiving party", "buyer", "seller", "lender",
              "borrower", "purchaser", "provider", "principal", "partner", "first party", "second party"}
_ROLE_PAREN = re.compile(r"\(\s*(?:hereinafter\s+)?(?:referred\s+to\s+as\s+)?(?:the\s+)?[\"']?([A-Za-z ]{3,30}?)[\"']?\s*\)", re.I)
_NAME_CUT = re.compile(r",\s*(?:a|an|having|incorporated|residing|located|whose|with|of|S/o|D/o|W/o)\b|\s+\(|,\s*$", re.I)


def clean_party_name(name: str) -> str:
    """Strip preamble phrases, numbering, and punctuation from extracted party names."""
    n = re.sub(r"^(?:the\s+following\s+parties:?|the\s+parties:?|between:?|among:?)\s*", "", name.strip(), flags=re.I)
    n = re.sub(r"^(?:(?:party\s+[12ab]|first\s+party|second\s+party)[:\s-]*|(?:\(?\d+\)?|\(?[a-z]\)|\(?[ivx]+\))[.\s-]*)\s*", "", n, flags=re.I)
    n = re.sub(r"^(?:and|&)\s+", "", n, flags=re.I)
    return n.strip(" ,;:\"'")


def extract_parties(ctx: Context) -> list[Party]:
    pre = "\n".join(p.text for p in ctx.doc.pages[:2])
    pre = re.sub(r"\s+", " ", pre)[:4000]
    parties, last_end = [], 0
    for m in _ROLE_PAREN.finditer(pre):
        role = m.group(1).strip().lower()
        if role not in ROLE_WORDS:
            continue
        seg = pre[last_end:m.start()]
        last_end = m.end()
        if re.search(r"\bbetween\b", seg, re.I):
            seg = re.split(r"\bbetween\b", seg, flags=re.I)[-1]
        seg = re.sub(r"^[\s,;]*(?:and|&)\s+", "", seg.strip(), flags=re.I)
        raw_name = _NAME_CUT.split(seg.strip(), maxsplit=1)[0].strip(" ,;\"'")
        name = clean_party_name(raw_name)
        if 3 <= len(name) <= 100:
            parties.append(Party(name=name, role=role.title(),
                                 evidence=_pre_evidence(ctx, name)))
    if not parties:
        # Check for tabular / key-value format e.g. "Employer Acme Technologies Pvt Ltd" or "Employer: Acme..."
        roles = ["employer", "employee", "company", "client", "contractor", "consultant", "service provider",
                 "vendor", "supplier", "landlord", "tenant", "lessor", "lessee", "licensor", "licensee"]
        role_pat = r"(?:" + "|".join(roles) + r")"
        non_party_verbs = {"hereby", "shall", "must", "appoints", "pay", "pays", "devote", "agrees", "entitled", "reporting", "commencing", "party", "name", "registered"}
        table_matches = re.finditer(
            rf"\b({role_pat})[:\s]+([A-Z][A-Za-z0-9 .,&-]+?)(?=\s+(?:Plot|Flat|Street|Road|having|residing|located|CIN|Address|Particulars|\d{{1,5}}\b|\n\n|\Z))",
            pre, re.I
        )
        seen_names = set()
        for tm in table_matches:
            r_str = tm.group(1).strip().title()
            n_str = clean_party_name(tm.group(2).strip())
            words = set(n_str.lower().split())
            if 3 <= len(n_str) <= 80 and len(n_str.split()) <= 7 and not (words & non_party_verbs):
                if n_str.lower() not in seen_names:
                    seen_names.add(n_str.lower())
                    parties.append(Party(name=n_str, role=r_str, evidence=_pre_evidence(ctx, n_str)))

    if not parties:
        m = re.search(r"between\s+(.{3,100}?)\s+and\s+(.{3,100}?)(?:[,.(]|\s+having|\s+whereas)", pre, re.I)
        if m:
            parties = [Party(name=clean_party_name(g.strip()), evidence=_pre_evidence(ctx, g.strip())) for g in m.groups()
                       if len(clean_party_name(g.strip())) >= 3]
    return parties


def _pre_evidence(ctx: Context, name: str) -> Evidence:
    pn = ctx.idx.locate(name) or 1
    return Evidence(page=pn, clause=None, text=name, verified=ctx.idx.contains(name))


_DATE_LABELS = [("effective", "Effective date"), ("commenc", "Commencement date"),
                ("terminat", "Termination date"), ("expir", "Expiry date"), ("renew", "Renewal date"),
                ("probation", "Probation"), ("due", "Payment due date"), ("payable", "Payment date"),
                ("dated", "Agreement date"), ("made on", "Agreement date"), ("entered into", "Agreement date"),
                ("executed", "Execution date"), ("signed", "Execution date"), ("witness", "Execution date")]


def extract_dates(ctx: Context) -> list[ImportantDate]:
    out, seen = [], set()
    for u in ctx.units:
        for m in DATE_RE.finditer(u.text):
            before = u.text[max(0, m.start() - 90): m.start()].lower()
            pos = {kw: before.rfind(kw) for kw, _ in _DATE_LABELS}
            best = max(((p, lab) for (kw, lab) in _DATE_LABELS if (p := pos[kw]) >= 0), default=None)
            label = best[1] if best else "Date mentioned"
            key = (m.group(0), label)
            if key in seen:
                continue
            seen.add(key)
            out.append(ImportantDate(label=label, value=m.group(0), iso_date=parse_date(m.group(0)),
                                     evidence=ctx.evidence(u)))
    return out


def _first_dur(text: str) -> Optional[dict]:
    m = DUR_RE.search(text)
    return parse_duration(m) if m else None


_NOTICE_A = re.compile(DUR + r"['\u2019]?\s*(?:prior\s+|advance\s+)?(?:written\s+)?notice", re.I)
_NOTICE_B = re.compile(r"notice\s+(?:period\s+)?of\s+(?:not\s+less\s+than\s+)?" + DUR, re.I)
_PROBATION_CTX = re.compile(r"(?:during|within)\s+(?:the\s+|such\s+)?(?:probation\w*|which)", re.I)


def find_notice_periods(ctx: Context) -> list[dict]:
    """[{kind: 'standard'|'probation', dur, unit}] with the unit that contains it."""
    found = []
    for u in ctx.units:
        if "notice" not in u.text.lower():
            continue
        m = _NOTICE_A.search(u.text) or _NOTICE_B.search(u.text)
        if not m:
            continue
        kind = "probation" if _PROBATION_CTX.search(u.text) else "standard"
        found.append({"kind": kind, "dur": parse_duration(m), "unit": u})
    return found


def extract_key_terms(ctx: Context) -> list[KeyTerm]:
    terms: list[KeyTerm] = []
    for n in find_notice_periods(ctx):
        label = "Notice period (probation)" if n["kind"] == "probation" else "Notice period"
        terms.append(KeyTerm(label=label, value=n["dur"]["text"], evidence=ctx.evidence(n["unit"])))
    for u in ctx.units:
        t = u.text
        if m := re.search(r"probation\w*\s+period\s+of\s+" + DUR, t, re.I):
            terms.append(KeyTerm(label="Probation period", value=parse_duration(m)["text"], evidence=ctx.evidence(u)))
        if u.category == "non_compete" and (d := _first_dur(t)) and "Non-compete duration" not in {x.label for x in terms}:
            terms.append(KeyTerm(label="Non-compete duration", value=d["text"], evidence=ctx.evidence(u)))
        if m := re.search(r"governed\s+by\s+(?:and\s+construed\s+in\s+accordance\s+with\s+)?the\s+laws?\s+of\s+([A-Z][\w ]+?)(?:[,.;]|\s+and\b)", t):
            terms.append(KeyTerm(label="Governing law", value=m.group(1).strip(), evidence=ctx.evidence(u)))
        if m := re.search(r"courts?\s+(?:of|in|at)\s+([A-Z][\w ]+?)\s+(?:shall|will|have|alone)", t):
            terms.append(KeyTerm(label="Jurisdiction", value=m.group(1).strip(), evidence=ctx.evidence(u)))
        if u.category == "confidentiality" or "confidential" in t.lower():
            if re.search(r"in\s+perpetuity|perpetual|indefinite", t, re.I):
                terms.append(KeyTerm(label="Confidentiality duration", value="perpetual / indefinite",
                                     evidence=ctx.evidence(u)))
            elif m := re.search(r"(?:for|period\s+of)\s+(?:a\s+period\s+of\s+)?" + DUR, t, re.I):
                terms.append(KeyTerm(label="Confidentiality duration", value=parse_duration(m)["text"],
                                     evidence=ctx.evidence(u)))
    # de-duplicate by (label, value)
    uniq, seen = [], set()
    for t in terms:
        if (t.label, t.value) not in seen:
            seen.add((t.label, t.value))
            uniq.append(t)
    return uniq


_PAY_KW = re.compile(r"salary|remuneration|compensation|wages|bonus|\bfees?\b|invoice|payable|\bpaid\b|"
                     r"reimburs|interest|per annum|per month|deduct", re.I)
_FREQ = re.compile(r"monthly|quarterly|annual(?:ly)?|weekly|per annum|per month|"
                   r"within\s+" + DUR, re.I)


def extract_payment_terms(ctx: Context) -> list[PaymentTerm]:
    out = []
    for u in ctx.units:
        if not _PAY_KW.search(u.text):
            continue
        amounts = [a.strip().rstrip(".,;") for a in MONEY_RE.findall(u.text)] + PERCENT_RE.findall(u.text)
        if not amounts and u.category != "payment":
            continue
        if not amounts and not re.search(r"payable|paid|deduct|reimburs", u.text, re.I):
            continue
        low = u.text.lower()
        if re.search(r"salary|remuneration|compensation|wages", low):
            kind = "salary"
        elif re.search(r"\bbonus\b|incentive|commission", low):
            kind = "bonus"
        elif re.search(r"\bfees?\b|invoice|retainer", low):
            kind = "fees"
        elif re.search(r"reimburs", low):
            kind = "reimbursement"
        elif re.search(r"late\s*payment|interest", low):
            kind = "late_payment_interest"
        elif re.search(r"deduct|recovery|set\s*off", low):
            kind = "deduction"
        else:
            kind = "payment"
        f = _FREQ.search(u.text)
        out.append(PaymentTerm(kind=kind, description=u.text[:400], amounts=amounts,
                               frequency=f.group(0) if f else None, evidence=ctx.evidence(u)))
    return out


_OBL_RE = re.compile(r"\b(shall not|must not|may not|cannot|shall|must|agrees? to|undertakes? to|"
                     r"is required to|are required to)\b", re.I)

_NON_PARTY_TERMS = {
    "agreement", "this agreement", "employment", "leave", "first three months",
    "it", "provision", "provisions", "template", "document", "contract", "dispute",
    "disputes", "laws", "law", "courts", "court", "section", "clause", "notice",
    "information", "work product", "materials", "amendment", "remaining provisions"
}

_MODAL_SUBJECT_RE = re.compile(
    r"(?:(?:^|[,;.]|\bafter\b|\bduring\b|\bon\b)\s*(?:the\s+)?)?"
    r"([A-Z][A-Za-z]+(?:\s+[A-Z]?[a-z]+){0,2}|either party|each party|both parties|neither party)"
    r"\s+(?:shall\s+not|must\s+not|may\s+not|cannot|shall|must|agrees?\s+to|undertakes?\s+to|is\s+required\s+to|are\s+required\s+to)\b",
    re.I
)


def extract_obligations(ctx: Context, limit: int = 60) -> list[Obligation]:
    out = []
    for u in ctx.units:
        # Skip boilerplates, demo disclaimers, recitals, and pure contract mechanics
        if re.search(r"\b(?:demo note|fictional agreement|template|recitals?|whereas)\b", u.text, re.I):
            continue
        if u.clause_id == "preamble":
            continue
        # Skip contract mechanics clauses that describe the document rather than party conduct
        if re.search(r"^(?:this agreement shall be governed|employment shall commence|"
                     r"the first \w+ months shall be|any amendment must be|"
                     r"if a provision is held unenforceable)", u.text.strip(), re.I):
            continue

        m = _OBL_RE.search(u.text)
        if not m:
            continue

        subj_match = _MODAL_SUBJECT_RE.search(u.text)
        party = None
        if subj_match:
            cand = subj_match.group(1).strip()
            cand_clean = re.sub(r"^(?:the\s+)", "", cand, flags=re.I).strip()
            if cand_clean.lower() not in _NON_PARTY_TERMS and not any(np in cand_clean.lower() for np in ("agreement", "template", "document")):
                party = cand_clean

        prohibition = m.group(1).lower() in {"shall not", "must not", "may not", "cannot"}
        out.append(Obligation(party=party,
                              kind="prohibition" if prohibition else "obligation",
                              text=u.text[:500], category=u.category, evidence=ctx.evidence(u)))
        if len(out) >= limit:
            break
    return out


def extract_key_clauses(ctx: Context) -> list[KeyClause]:
    out = []
    for c in ctx.clauses:
        if c.clause_id != "preamble" and c.category in IMPORTANT_CATEGORIES and len(c.text) >= 40:
            out.append(KeyClause(clause_id=c.clause_id, title=c.title, category=c.category,
                                 page=c.page, text=c.text[:700]))
    return out


# =================================================================== public API
def analyze_document(document_data: DocumentData | dict, use_llm: bool = False) -> dict:
    """Interface agreed with Developer 3:

        analyze_document(document_data) -> {"document_type", "parties", "important_dates",
                                            "obligations", "risk_findings", ...extra fields}
    Rule-based by default. use_llm=True adds a verified LLM refinement pass when an
    OPENAI_API_KEY is configured; if unavailable it silently falls back to rules only.
    """
    from document_intelligence.risk_analyzer import find_risks  # local import avoids a cycle

    ctx = build_context(document_data)
    analysis = DocumentAnalysis(
        document_id=ctx.doc.document_id, document_type=ctx.doc_type, classification_basis=ctx.basis,
        parties=extract_parties(ctx), important_dates=extract_dates(ctx),
        key_terms=extract_key_terms(ctx), payment_terms=extract_payment_terms(ctx),
        obligations=extract_obligations(ctx), key_clauses=extract_key_clauses(ctx),
        risk_findings=find_risks(ctx), notes=list(ctx.doc.warnings))
    if not analysis.parties:
        analysis.notes.append("Parties could not be identified reliably; please review manually.")
    if use_llm:
        from document_intelligence.llm_client import enrich_analysis
        analysis = enrich_analysis(ctx, analysis)
    return analysis.model_dump(mode="json")
