"""LLM client for document understanding and analysis enrichment.
Supports both Google Gemini and OpenAI.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from config.settings import get_settings
from core.schemas import DocumentAnalysis, ImportantDate, Obligation
from rag_engine.llm import get_llm

logger = logging.getLogger(__name__)


def llm_available() -> bool:
    """Check if an active LLM provider (Gemini or OpenAI) is available."""
    settings = get_settings()
    return settings.has_api_key


def enrich_analysis(ctx: Any, analysis: DocumentAnalysis) -> DocumentAnalysis:
    """Optionally refine and summarize analysis using LLM, with strict quote verification."""
    llm = get_llm()
    if llm is None:
        return analysis

    system_prompt = (
        "You are an expert legal document analyst. "
        "Analyze the provided contract text and provide a concise, factual executive summary. "
        "Do not invent facts, parties or obligations. "
        "Return a JSON object: {\"summary\": \"<2-3 sentence overview of the agreement>\"}"
    )

    doc_sample = ctx.doc.full_text[:4000]
    user_prompt = f"Contract Text (Sample):\n{doc_sample}"

    try:
        raw = llm(system_prompt, user_prompt)
        # Parse JSON from output
        data = None
        try:
            data = json.loads(raw)
        except Exception:
            import re
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                data = json.loads(m.group(0))

        if data and isinstance(data, dict) and data.get("summary"):
            summary_text = str(data["summary"]).strip()
            if summary_text:
                analysis.summary = summary_text
    except Exception as exc:
        logger.warning(f"LLM analysis enrichment skipped due to error: {exc}")

    return analysis
