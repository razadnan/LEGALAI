"""LLM provider wrapper supporting Google Gemini and OpenAI with graceful fallback."""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from config.settings import get_settings
from core.exceptions import LLMError

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = "Fallback mode: Gemini is temporarily unavailable. Deterministic extraction and cached results remain available."


def _create_gemini_llm(api_key: str, model_name: str) -> Callable[[str, str], str]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    def _call(system_prompt: str, user_prompt: str) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.1,
        )
        # Task 4: One retry with 2s delay, then fallback
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config=config,
            )
            return response.text or ""
        except Exception as exc1:
            logger.warning(f"Gemini API initial call failed: {exc1}. Retrying in 2 seconds...")
            time.sleep(2)
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config=config,
                )
                return response.text or ""
            except Exception as exc2:
                logger.error(f"Gemini API retry failed: {exc2}")
                # User safety fix 3: Do not expose raw str(error) in UI, log it and raise clean fallback
                raise LLMError(FALLBACK_MESSAGE) from exc2

    return _call


def _create_openai_llm(api_key: str, model_name: str) -> Callable[[str, str], str]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    def _call(system_prompt: str, user_prompt: str) -> str:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            logger.error(f"OpenAI call failed: {exc}")
            raise LLMError(FALLBACK_MESSAGE) from exc

    return _call


def get_llm() -> Optional[Callable[[str, str], str]]:
    """Return configured LLM caller (Gemini or OpenAI), or None if offline."""
    settings = get_settings()
    provider = settings.active_provider

    if provider == "gemini":
        try:
            return _create_gemini_llm(settings.gemini_api_key, settings.gemini_model)
        except Exception as exc:
            logger.warning(f"Failed to initialize Gemini LLM: {exc}")
            return None

    if provider == "openai":
        try:
            return _create_openai_llm(settings.openai_api_key, settings.openai_model)
        except Exception as exc:
            logger.warning(f"Failed to initialize OpenAI LLM: {exc}")
            return None

    return None
