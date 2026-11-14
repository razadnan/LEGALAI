"""Central configuration. Values come from environment variables / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

try:  # python-dotenv is optional at import time
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    app_title: str = "LegalMind AI"
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", "")))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.5-flash"))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    embedding_model: str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "gemini-embedding-001"))
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "auto"))

    base_dir: Path = BASE_DIR
    upload_dir: Path = BASE_DIR / "storage" / "uploads"
    processed_dir: Path = BASE_DIR / "storage" / "processed"
    vector_db_dir: Path = BASE_DIR / "storage" / "vector_db"
    reports_dir: Path = BASE_DIR / "storage" / "reports"

    max_upload_mb: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_MB", "20")))
    allowed_extensions: tuple[str, ...] = (".pdf", ".docx")
    max_question_chars: int = 1000

    @property
    def has_gemini_key(self) -> bool:
        k = (self.gemini_api_key or "").strip()
        return bool(k and not k.startswith("your-") and not k.startswith("sk-your"))

    @property
    def has_openai_key(self) -> bool:
        k = (self.openai_api_key or "").strip()
        return bool(k and not k.startswith("sk-your") and not k.startswith("your-"))

    @property
    def has_api_key(self) -> bool:
        return self.has_gemini_key or self.has_openai_key

    @property
    def active_provider(self) -> str:
        prov = self.llm_provider.lower()
        if prov in ("gemini", "google") and self.has_gemini_key:
            return "gemini"
        if prov == "openai" and self.has_openai_key:
            return "openai"
        if self.has_gemini_key:
            return "gemini"
        if self.has_openai_key:
            return "openai"
        return "none"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def ensure_dirs(self) -> None:
        for d in (self.upload_dir, self.processed_dir, self.vector_db_dir, self.reports_dir):
            Path(d).mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
