import pytest

from config.settings import Settings


@pytest.mark.parametrize(
    "placeholder",
    ["", "your_gemini_api_key_here", "your-openai-api-key-here", "sk-your-openai-key-here"],
)
def test_settings_reject_placeholder_api_keys(placeholder):
    settings = Settings(gemini_api_key=placeholder, openai_api_key=placeholder)

    assert not settings.has_gemini_key
    assert not settings.has_openai_key
    assert settings.active_provider == "none"


def test_settings_accept_configured_gemini_key():
    settings = Settings(
        gemini_api_key="AIzaSy-example-configured-key",
        openai_api_key="sk-your-openai-key-here",
        llm_provider="gemini",
    )

    assert settings.has_gemini_key
    assert not settings.has_openai_key
    assert settings.active_provider == "gemini"


def test_explicit_gemini_provider_does_not_fall_back_to_openai():
    settings = Settings(
        gemini_api_key="your_gemini_api_key_here",
        openai_api_key="sk-valid-example-key",
        llm_provider="gemini",
    )

    assert settings.has_openai_key
    assert settings.active_provider == "none"


def test_auto_provider_prefers_gemini_when_both_keys_are_configured():
    settings = Settings(
        gemini_api_key="AIzaSy-example-configured-key",
        openai_api_key="sk-valid-example-key",
        llm_provider="auto",
    )

    assert settings.active_provider == "gemini"


def test_gemini_embeddings_reject_placeholder_key(monkeypatch):
    from rag_engine.embeddings import get_embedder
    from core.exceptions import LLMError

    monkeypatch.setenv("GEMINI_API_KEY", "your_gemini_api_key_here")
    with pytest.raises(LLMError, match="valid GEMINI_API_KEY"):
        get_embedder("gemini")
