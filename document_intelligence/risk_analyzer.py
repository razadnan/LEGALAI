"""Developer 1 - explainable contract risk findings.

Rule-based and evidence-first: every clause-level finding quotes the exact sentence, page and
clause it came from, and that quote is verified against the document text. Missing-clause
findings are the only ones without a quote (the absence of a clause cannot be quoted) and are
labelled finding_type="missing_clause".

Findings are prompts for human/legal review, NOT legal conclusions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from core.schemas import DocumentData, Evidence, RiskFinding
from document_intelligence.document_analyzer import (DUR_RE, Context, Unit, build_context,
                                                     find_notice_periods, parse_duration)

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class Rule:
    key: str
    title: str
    category: str
    severity: str
    pattern: str
    explanation: str
    question: str
    predicate: Optional[Callable[[re.Match, Unit], Optional[str]]] = None
    # predicate returns None to reject the match, or a severity string to accept it


def _noncompete(m: re.Match, u: Unit) -> Optional[str]:
    d = DUR_RE.search(u.text)
    broad = re.search(r"worldwide|globally|anywhere|entire\s+country", u.text, re.I)
    if d and parse_duration(d)["days"] > 365:
        return "high"
    return "high" if broad and not d else "medium"


def _interest(m: re.Match, u: Unit) -> Optional[str]:
    rate = float(m.group(1))
    per = (m.group(2) or "").lower()
    if per.startswith("month") or "monthly" in m.group(0).lower():
        return "medium" if rate >= 2 else None
    return "medium" if rate >= 18 else None


def _confidential_perpetual(m: re.Match, u: Unit) -> Optional[str]:
    return "medium" if (u.category == "confidentiality" or "confiden" in u.text.lower()) else None


def _terminate(m: re.Match, u: Unit) -> Optional[str]:
    return "high" if re.search(r"without\s+(?:any\s+)?(?:prior\s+)?notice", u.text, re.I) else "medium"


RULES: list[Rule] = [
    Rule("unilateral_termination", "Termination without cause or notice", "termination", "high",
         r"terminat\w*[^.]{0,200}?(?:without\s+(?:any\s+)?(?:prior\s+)?(?:notice|cause|reason)|sole\s+discretion)",
         "One party may end the agreement immediately or at its sole discretion, which removes "
         "job/contract security and can make any stated notice period meaningless.",
         "Can this right be limited to defined causes, or made mutual, with a minimum notice period?",
         _terminate),
    Rule("non_compete", "Post-termination non-compete restriction", "non_compete", "medium",
         r"non-?\s?compet\w*|not\s+(?:to\s+)?(?:directly\s+or\s+indirectly\s+)?(?:engage|be\s+engaged|work|compete|carry\s+on)[^.]{0,120}compet",
         "Restricts future work after the relationship ends. Long duration or wide geography can "
         "limit livelihood and may be unenforceable depending on the jurisdiction.",
         "Is the duration, geography and scope of the restriction reasonable and enforceable here?",
         _noncompete),
    Rule("broad_indemnity", "Broad indemnification obligation", "indemnity", "medium",
         r"indemnif\w+[^.]{0,200}?(?:any\s+and\s+all|all)\s+(?:claims|losses|damages|liabilit|costs|expenses)",
         "Indemnifying 'any and all' losses can expose a party to open-ended financial liability, "
         "including for matters outside its control.",
         "Can the indemnity be limited to losses caused by wilful misconduct or negligence, with a cap?"),
    Rule("unlimited_liability", "Unlimited or uncapped liability", "liability", "high",
         r"unlimited\s+liab|without\s+(?:any\s+)?(?:limit|cap)\b|no\s+(?:limit|cap)\s+on\s+(?:the\s+)?liab|liable\s+for\s+all\s+(?:losses|damages)",
         "No ceiling on liability means a single dispute could produce losses far larger than the "
         "value of the contract.",
         "Should liability be capped (for example at fees paid in 12 months)?"),
    Rule("unilateral_amendment", "One-sided right to change the agreement", "amendment", "high",
         r"(?:may|can|reserves?\s+the\s+right\s+to)\s+(?:amend|modify|change|vary|revise|alter)[^.]{0,150}?(?:at\s+any\s+time|sole\s+discretion|without\s+(?:prior\s+)?(?:notice|consent))",
         "Allows one party to change terms without the other's agreement, which undermines the "
         "certainty of everything else in the contract.",
         "Can amendments require written consent of both parties?"),
    Rule("auto_renewal", "Automatic renewal", "term", "medium",
         r"automatic(?:ally)?\s+(?:renew|extend)|auto-?renew|evergreen",
         "The contract renews on its own; missing a cancellation window can lock a party in for "
         "another full term.",
         "What is the cancellation deadline, and is it clearly communicated?"),
    Rule("broad_ip_assignment", "Very broad intellectual-property assignment", "intellectual_property", "medium",
         r"(?:all|any)\s+(?:inventions?|works?|intellectual\s+property|work\s+product|ideas)[^.]{0,200}?(?:whether\s+or\s+not|irrespective|regardless|outside|not\s+related)",
         "Ownership extends to work made outside working hours or unrelated to the job, which can "
         "capture personal projects.",
         "Can the assignment be limited to work done in the course of the engagement using the company's resources?"),
    Rule("perpetual_confidentiality", "Perpetual / indefinite confidentiality", "confidentiality", "medium",
         r"in\s+perpetuity|perpetual(?:ly)?|indefinite(?:ly)?",
         "Confidentiality with no end date is hard to comply with and may be challenged for "
         "information that is no longer secret.",
         "Should confidentiality expire after a fixed period (except for genuine trade secrets)?",
         _confidential_perpetual),
    Rule("salary_deduction", "Open-ended deduction or set-off from pay", "payment", "high",
         r"deduct\w*[^.]{0,100}?(?:salary|wages|remuneration|compensation|final\s+settlement|dues)|(?:recover|set\s*off)[^.]{0,100}?(?:salary|wages|final\s+settlement)",
         "Letting one party deduct amounts it alone considers owed can reduce pay or payments "
         "without a fair process or limit.",
         "Can deductions be limited to amounts that are lawful, itemised and agreed or adjudicated?"),
    Rule("unpaid_extra_work", "Extra work without extra compensation", "duties", "medium",
         r"without\s+(?:any\s+)?additional\s+(?:compensation|pay|remuneration)|no\s+(?:additional|overtime)\s+(?:compensation|pay)",
         "Open-ended working hours or duties without extra pay may conflict with working-time "
         "rules and effectively lower hourly pay.",
         "Are working hours and overtime treatment defined and consistent with applicable law?"),
    Rule("discretionary_pay", "Discretionary bonus / incentive", "payment", "medium",
         r"(?:bonus|incentive|commission)[^.]{0,150}?(?:sole|absolute)\s+discretion",
         "A bonus at the payer's sole discretion is not guaranteed, so it should not be relied "
         "on as part of expected compensation.",
         "Can bonus criteria and timing be written down objectively?"),
    Rule("penalty_or_bond", "Penalty, forfeiture, or service-bond terms", "payment", "medium",
         r"liquidated\s+damages|\bpenalt(?:y|ies)\b|\bforfeit\w*|service\s+bond|training\s+(?:cost|expense)s?[^.]{0,60}(?:repay|reimburs|recover)",
         "Fixed penalties or repayment duties can be disproportionate and may be unenforceable if "
         "they exceed genuine loss.",
         "Is the amount a reasonable pre-estimate of loss, and does it reduce over time?"),
    Rule("high_interest", "High late-payment interest", "payment", "medium",
         r"interest[^.]{0,60}?(\d+(?:\.\d+)?)\s*%\s*(?:per\s+(month|annum|year)|monthly|p\.a\.)",
         "The stated late-payment rate is high and can compound a small delay into a large cost.",
         "Is this rate customary and lawful for this type of contract?", _interest),
    Rule("rights_waiver", "Waiver of legal rights", "dispute_resolution", "medium",
         r"waive\w*[^.]{0,60}(?:right|jury|class|claim)",
         "Waiving rights to sue, to a jury or to bring claims limits remedies if something goes wrong.",
         "Which rights are being waived and is that acceptable for this agreement?"),
    Rule("exclusive_jurisdiction", "Exclusive jurisdiction clause", "governing_law", "low",
         r"exclusive\s+jurisdiction|courts?\s+(?:of|in|at)\s+[A-Z][\w ]+?\s+(?:shall|will)\s+(?:alone|exclusively)",
         "Disputes must be brought in one location, which may be inconvenient or costly for one party.",
         "Is the chosen forum acceptable for both parties?"),
    Rule("assignment_without_consent", "Assignment without consent", "assignment", "medium",
         r"(?:may|can)\s+assign[^.]{0,100}without",
         "Rights or obligations may be transferred to a third party without the other side agreeing.",
         "Should assignment require prior written consent?"),
]
_COMPILED = [(r, re.compile(r.pattern, re.I | re.S)) for r in RULES]

_REQUIRED = {
    "Employment Agreement": ["termination", "confidentiality", "governing_law"],
    "Non-Disclosure Agreement": ["term", "governing_law"],
}
_MISSING_INFO = {
    "termination": ("No termination clause found", "medium",
                    "Without termination terms it is unclear how either party can exit and on what notice.",
                    "How can each party end this agreement, and on what notice?"),
    "confidentiality": ("No confidentiality clause found", "low",
                        "Sensitive information may be unprotected.",
                        "Should a confidentiality clause be added?"),
    "governing_law": ("No governing-law / jurisdiction clause found", "low",
                      "It is unclear which country's or state's law applies and where disputes are heard.",
                      "Which law governs and where are disputes resolved?"),
    "term": ("No term/duration clause found", "medium",
             "The period for which the agreement applies is not clearly stated.",
             "How long does the agreement (and confidentiality) last?"),
}


def find_risks(ctx: Context) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    seen: set[tuple[str, str]] = set()

    for u in ctx.units:
        for rule, rx in _COMPILED:
            m = rx.search(u.text)
            if not m:
                continue
            sev = rule.severity
            if rule.predicate:
                sev = rule.predicate(m, u)
                if sev is None:
                    continue
            key = (rule.key, u.clause_id)
            if key in seen:
                continue
            seen.add(key)
            findings.append(RiskFinding(
                risk_id="", title=rule.title, severity=sev, category=rule.category,
                explanation=rule.explanation, suggested_question=rule.question,
                evidence=[ctx.evidence(u)]))

    # notice period checks (parsed numbers, so not a plain regex rule)
    for n in find_notice_periods(ctx):
        days, u = n["dur"]["days"], n["unit"]
        if n["kind"] == "standard" and days < 15:
            title, sev, why, q = ("Very short notice period", "medium",
                                  f"A notice period of {n['dur']['text']} gives little time to find "
                                  "a replacement, transition work or arrange finances.",
                                  "Is a longer, mutual notice period appropriate?")
        elif n["kind"] == "standard" and days >= 90:
            title, sev, why, q = ("Long notice period", "low",
                                  f"A notice period of {n['dur']['text']} can restrict mobility and "
                                  "delay a move to a new role or supplier.",
                                  "Can the notice period be shortened or bought out?")
        else:
            continue
        key = ("notice", u.clause_id)
        if key not in seen:
            seen.add(key)
            findings.append(RiskFinding(risk_id="", title=title, severity=sev, category="termination",
                                        explanation=why, suggested_question=q, evidence=[ctx.evidence(u)]))

    # missing clauses (only for document types where we know what to expect)
    present = {c.category for c in ctx.clauses if c.text}
    text_l = ctx.doc.full_text.lower()
    required = _REQUIRED.get(ctx.doc_type, ["termination", "governing_law"]) \
        if not ctx.doc_type.startswith("Legal document") else []
    for cat in required:
        if cat in present:
            continue
        title, sev, why, q = _MISSING_INFO[cat]
        findings.append(RiskFinding(risk_id="", title=title, severity=sev, category=cat,
                                    finding_type="missing_clause", explanation=why,
                                    suggested_question=q, evidence=[]))

    findings.sort(
        key=lambda f: (
            SEVERITY_ORDER[f.severity],
            getattr(f.evidence[0], "page", 0)
            if (isinstance(f.evidence, list) and f.evidence)
            else (f.page or 99),
        )
    )
    for i, f in enumerate(findings, 1):
        f.risk_id = f"R{i:03d}"
    return findings


def analyze_risks(document_data: DocumentData | dict) -> list[dict]:
    """Standalone entry point: risk findings (as dicts) for a processed document."""
    return [f.model_dump(mode="json") for f in find_risks(build_context(document_data))]
