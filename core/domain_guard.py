"""Deterministic domain checks for LegalMind AI."""

import re


# Recognizable legal instruments and document types.
_LEGAL_DOCUMENT_PATTERNS = [
    r"\bemployment agreement\b",
    r"\bnon[- ]disclosure agreement\b",
    r"\bconfidentiality agreement\b",
    r"\blease agreement\b",
    r"\brental agreement\b",
    r"\bservice agreement\b",
    r"\bconsulting agreement\b",
    r"\bindependent contractor agreement\b",
    r"\bsale and purchase agreement\b",
    r"\bpurchase agreement\b",
    r"\bloan agreement\b",
    r"\bpartnership agreement\b",
    r"\blicen[cs]e agreement\b",
    r"\bterms and conditions\b",
    r"\blegal notice\b",
    r"\bdemand letter\b",
    r"\baffidavit\b",
    r"\bpower of attorney\b",
    r"\blast will and testament\b",
    r"\bdeed of\b",
    r"\bcourt order\b",
    r"\bjudgment\b",
    r"\bdecree\b",
    r"\bcourt summons\b",
    r"\bsubpoena\b",
    r"\bstatement of claim\b",
    r"\blegal complaint\b",
    r"\bpetition\b",
    r"\bpleading\b",
    r"\barbitration award\b",
    r"\bstatute\b",
    r"\bact of parliament\b",
    r"\bact,?\s+\d{4}\b",
    r"\bregulations?\b",
    r"\bmemorandum of understanding\b",
    r"\bmemorandum of association\b",
    r"\bthis agreement\b",
]

# Legal structure indicators. These are supporting evidence, not proof alone.
_LEGAL_STRUCTURE_PATTERNS = [
    r"\bgoverning law\b",
    r"\bjurisdiction\b",
    r"\bindemnif(?:y|ication)\b",
    r"\bhereby\b",
    r"\bwhereas\b",
    r"\bterms of this agreement\b",
    r"\bparty(?:ies)? to this agreement\b",
    r"\bshall\b",
    r"\bbreach of contract\b",
    r"\btermination\b",
    r"\bobligations?\b",
    r"\bplaintiff\b",
    r"\bdefendant\b",
    r"\bpetitioner\b",
    r"\brespondent\b",
    r"\bthe court orders\b",
    r"\bunder section\s+\d+\b",
    r"\bsubject to the provisions\b",
    r"\bgoverned by the laws of\b",
    r"\beither party may\b",
    r"\bwritten notice\b",
]


def is_legal_document(text: str) -> bool:
    """Return True only when extracted text contains meaningful legal signals."""
    content = (text or "").lower()

    if len(content.strip()) < 30:
        return False

    document_hits = sum(
        bool(re.search(pattern, content, re.IGNORECASE))
        for pattern in _LEGAL_DOCUMENT_PATTERNS
    )
    structure_hits = sum(
        bool(re.search(pattern, content, re.IGNORECASE))
        for pattern in _LEGAL_STRUCTURE_PATTERNS
    )

    # Require a recognizable legal document type and supporting legal structure.
    return document_hits >= 1 and structure_hits >= 1 or document_hits >= 2


# Obvious unrelated topics. This is intentionally conservative:
# ordinary questions about the uploaded legal document remain allowed.
_OFF_TOPIC_PATTERNS = [
    r"\b(weather|forecast|temperature outside)\b",
    r"\b(recipe|cook(?:ing)?|bake(?:ing)?)\b",
    r"\b(football|cricket|basketball|tennis|soccer|match score)\b",
    r"\b(movie|film|celebrity|song lyrics|music recommendation)\b",
    r"\b(restaurant|tourist attraction|holiday destination|flight booking)\b",
    r"\b(write|debug|fix|explain)\s+(?:a\s+)?(?:python|javascript|java|html|css|sql)\s+(?:program|code|script)\b",
    r"\b(stock price|crypto price|bitcoin price|share market)\b",
]


def is_out_of_domain_question(question: str) -> bool:
    """Identify clearly unrelated questions without blocking document-specific QA."""
    content = (question or "").strip().lower()
    return any(
        re.search(pattern, content, re.IGNORECASE)
        for pattern in _OFF_TOPIC_PATTERNS
    )
