"""Text processing and tokenization utilities for RAG engine."""
from __future__ import annotations

import re


def tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase alphanumeric tokens."""
    if not text:
        return []
    return re.findall(r"\b[a-zA-Z0-9_\u20b9$€£%.,-]+\b", text.lower())
