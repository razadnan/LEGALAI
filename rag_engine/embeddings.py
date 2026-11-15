"""Embedding providers.

* OpenAIEmbedder  – production (text-embedding-3-small by default)
* HashingEmbedder – deterministic, offline, no API key. Used for tests, demos
                    without internet, and as automatic fallback.

get_embedder() picks one: EMBEDDING_PROVIDER = openai | local | auto (default).
"""
from __future__ import annotations

import math
import os
import time
import zlib
from typing import List, Protocol

from config.settings import is_configured_api_key
from core.exceptions import LLMError
from rag_engine.text_utils import tokenize


class Embedder(Protocol):
    name: str

    def embed_documents(self, texts: List[str]) -> List[List[float]]: ...
    def embed_query(self, text: str) -> List[float]: ...


class OpenAIEmbedder:
    def __init__(self, model: str | None = None, batch_size: int = 64):
        from openai import OpenAI  # lazy import
        self.model = model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self.batch_size = batch_size
        self.client = OpenAI()
        self.name = f"openai-{self.model}"

    def _embed(self, texts: List[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = [t.replace("\n", " ")[:8000] for t in texts[i:i + self.batch_size]]
            last = None
            for attempt in range(4):
                try:
                    r = self.client.embeddings.create(model=self.model, input=batch)
                    out.extend(d.embedding for d in r.data)
                    break
                except Exception as e:
                    last = e
                    time.sleep(1.5 * (attempt + 1))
            else:
                raise LLMError(f"Embedding request failed: {last}")
        return out

    def embed_documents(self, texts):
        return self._embed(list(texts))

    def embed_query(self, text):
        return self._embed([text])[0]


class HashingEmbedder:
    """Feature-hashing bag of words + bigrams + char 4-grams (L2-normalised)."""

    def __init__(self, dim: int = 768):
        self.dim = dim
        self.name = f"local-hash{dim}"

    def _vec(self, text: str) -> List[float]:
        v = [0.0] * self.dim
        toks = tokenize(text)

        def add(feat: str, w: float):
            h = zlib.crc32(feat.encode())
            v[h % self.dim] += w if (h >> 20) & 1 else -w

        for t in toks:
            add("u:" + t, 1.0)
            padded = f"#{t}#"
            for k in range(len(padded) - 3):
                add("c:" + padded[k:k + 4], 0.3)
        for a, b in zip(toks, toks[1:]):
            add(f"b:{a}_{b}", 0.5)
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


class GeminiEmbedder:
    """Production embeddings via Google Gemini text-embedding-004."""

    def __init__(self, model: str | None = None, api_key: str | None = None):
        from google import genai

        self.api_key = api_key or os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
        self.model = model or os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
        self.client = genai.Client(api_key=self.api_key)
        self.name = f"gemini-{self.model}"

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for i in range(0, len(texts), 50):
            batch = [t[:4000] for t in texts[i : i + 50]]
            try:
                res = self.client.models.embed_content(model=self.model, contents=batch)
                if hasattr(res, "embeddings") and res.embeddings:
                    for e in res.embeddings:
                        out.append(list(e.values))
            except Exception as exc:
                raise LLMError(f"Gemini embedding failed: {exc}") from exc
        return out

    def embed_query(self, text: str) -> List[float]:
        try:
            res = self.client.models.embed_content(model=self.model, contents=text[:4000])
            if hasattr(res, "embeddings") and res.embeddings:
                return list(res.embeddings[0].values)
            return []
        except Exception as exc:
            raise LLMError(f"Gemini query embedding failed: {exc}") from exc


def get_embedder(provider: str | None = None) -> Embedder:
    provider = (provider or os.getenv("EMBEDDING_PROVIDER", "auto")).lower()
    if provider == "local":
        return HashingEmbedder()
    if provider in ("gemini", "google"):
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
        if not is_configured_api_key(api_key):
            raise LLMError("Gemini embeddings require a valid GEMINI_API_KEY or GOOGLE_API_KEY.")
        return GeminiEmbedder()
    if provider == "openai":
        if not is_configured_api_key(os.getenv("OPENAI_API_KEY")):
            raise LLMError("OpenAI embeddings require a valid OPENAI_API_KEY.")
        return OpenAIEmbedder()
    # auto
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if is_configured_api_key(gemini_key):
        try:
            return GeminiEmbedder(api_key=gemini_key)
        except Exception:
            pass
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if is_configured_api_key(openai_key):
        try:
            return OpenAIEmbedder()
        except Exception:
            pass
    return HashingEmbedder()
