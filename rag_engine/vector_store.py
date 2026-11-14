"""Vector store with ChromaDB (persistent) and a pure-Python fallback.

One collection holds all documents; every query is filtered by document_id.
The collection name includes the embedder name so vectors from different
embedding models are never mixed.
"""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.schemas import Chunk
from rag_engine.embeddings import Embedder, get_embedder


def _chunk_to_meta(c: Chunk) -> dict:
    return {
        "document_id": c.document_id, "chunk_index": c.chunk_index,
        "page_start": c.page_start, "page_end": c.page_end,
        "clause": c.clause or "", "clause_ids": ",".join(c.clause_ids),
        "heading": c.heading,
    }


def _meta_to_chunk(chunk_id: str, text: str, m: dict) -> Chunk:
    ids = [x for x in (m.get("clause_ids") or "").split(",") if x]
    return Chunk(chunk_id=chunk_id, document_id=m["document_id"], chunk_index=int(m["chunk_index"]),
                 text=text, page_start=int(m["page_start"]), page_end=int(m["page_end"]),
                 clause=m.get("clause") or None, clause_ids=ids, heading=m.get("heading", ""))


class _MemoryBackend:
    """Dependency-free backend with JSON persistence."""

    def __init__(self, path: Path):
        self.path = path
        self.rows: Dict[str, dict] = {}
        if path.exists():
            try:
                self.rows = json.loads(path.read_text())
            except Exception:
                self.rows = {}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.rows))

    def upsert(self, chunks: List[Chunk], embeddings):
        for c, e in zip(chunks, embeddings):
            self.rows[c.chunk_id] = {"chunk": c.model_dump(), "embedding": e}
        self._save()

    def get(self, document_id: str) -> List[Chunk]:
        cs = [Chunk(**r["chunk"]) for r in self.rows.values() if r["chunk"]["document_id"] == document_id]
        return sorted(cs, key=lambda c: c.chunk_index)

    def query(self, document_id: str, qvec, n: int) -> List[Tuple[Chunk, float]]:
        scored = []
        for r in self.rows.values():
            if r["chunk"]["document_id"] != document_id:
                continue
            e = r["embedding"]
            dot = sum(a * b for a, b in zip(qvec, e))
            na = math.sqrt(sum(a * a for a in qvec)) or 1.0
            nb = math.sqrt(sum(b * b for b in e)) or 1.0
            scored.append((Chunk(**r["chunk"]), dot / (na * nb)))
        scored.sort(key=lambda x: -x[1])
        return scored[:n]

    def delete(self, document_id: str):
        self.rows = {k: v for k, v in self.rows.items() if v["chunk"]["document_id"] != document_id}
        self._save()


class _ChromaBackend:
    def __init__(self, persist_dir: Path, name: str):
        import chromadb
        persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(persist_dir))
        self.col = self.client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})

    def upsert(self, chunks: List[Chunk], embeddings):
        self.col.upsert(ids=[c.chunk_id for c in chunks], embeddings=embeddings,
                        documents=[c.text for c in chunks], metadatas=[_chunk_to_meta(c) for c in chunks])

    def get(self, document_id: str) -> List[Chunk]:
        r = self.col.get(where={"document_id": document_id}, include=["documents", "metadatas"])
        cs = [_meta_to_chunk(i, d, m) for i, d, m in zip(r["ids"], r["documents"], r["metadatas"])]
        return sorted(cs, key=lambda c: c.chunk_index)

    def query(self, document_id: str, qvec, n: int):
        total = len(self.col.get(where={"document_id": document_id}, include=[])["ids"])
        if total == 0:
            return []
        r = self.col.query(query_embeddings=[qvec], n_results=min(n, total),
                           where={"document_id": document_id}, include=["documents", "metadatas", "distances"])
        return [(_meta_to_chunk(i, d, m), 1.0 - dist)
                for i, d, m, dist in zip(r["ids"][0], r["documents"][0], r["metadatas"][0], r["distances"][0])]

    def delete(self, document_id: str):
        self.col.delete(where={"document_id": document_id})


class VectorStore:
    def __init__(self, persist_dir: Optional[str] = None, embedder: Optional[Embedder] = None,
                 backend: str = "auto"):
        self.persist_dir = Path(persist_dir or os.getenv("LEGALMIND_VECTOR_DB", "storage/vector_db"))
        self.embedder = embedder or get_embedder()
        name = re.sub(r"[^a-zA-Z0-9_-]", "-", f"legalmind_{self.embedder.name}")[:60].strip("-_")
        backend = backend.lower()
        if backend in ("auto", "chroma"):
            try:
                self._b = _ChromaBackend(self.persist_dir, name)
                self.backend = "chroma"
            except Exception:
                if backend == "chroma":
                    raise
                self._b = _MemoryBackend(self.persist_dir / f"{name}.json")
                self.backend = "memory"
        else:
            self._b = _MemoryBackend(self.persist_dir / f"{name}.json")
            self.backend = "memory"

    # ---- write ----
    def add_chunks(self, chunks: List[Chunk]) -> int:
        if not chunks:
            return 0
        self.delete_document(chunks[0].document_id)  # re-indexing replaces old vectors
        embs = self.embedder.embed_documents([c.text for c in chunks])
        self._b.upsert(chunks, embs)
        return len(chunks)

    def delete_document(self, document_id: str):
        self._b.delete(document_id)

    # ---- read ----
    def has_document(self, document_id: str) -> bool:
        return bool(self._b.get(document_id))

    def get_chunks(self, document_id: str) -> List[Chunk]:
        return self._b.get(document_id)

    def similarity_search(self, document_id: str, query: str, top_k: int = 10) -> List[Tuple[Chunk, float]]:
        return self._b.query(document_id, self.embedder.embed_query(query), top_k)


_default: Optional[VectorStore] = None


def get_default_store() -> VectorStore:
    global _default
    if _default is None:
        _default = VectorStore()
    return _default


def set_default_store(store: Optional[VectorStore]) -> None:
    global _default
    _default = store
