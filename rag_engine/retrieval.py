"""Hybrid retrieval: semantic (vector) + keyword (BM25) + explicit clause lookup,
fused with Reciprocal Rank Fusion."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Union

from core.exceptions import DocumentNotIndexedError
from core.schemas import Chunk, DocumentData
from rag_engine.chunking import chunk_document
from rag_engine.text_utils import tokenize
from rag_engine.vector_store import VectorStore, get_default_store

_CLAUSE_REF = re.compile(r"(?i)\b(?:clause|section|article|para(?:graph)?)\s+(\d{1,3}(?:\.\d{1,3}){0,4})\b")


@dataclass
class RetrievedPassage:
    chunk: Chunk
    score: float                 # fused score, normalised so best = 1.0
    semantic_score: float = 0.0  # cosine similarity (0 if not in semantic top-k)
    keyword_score: float = 0.0   # BM25
    overlap: int = 0             # query content tokens found in passage
    clause_match: bool = False   # user explicitly asked for this clause


def index_document(document_data: Union[DocumentData, dict], store: Optional[VectorStore] = None) -> int:
    """Chunk + embed + store a document. Returns number of chunks indexed."""
    doc = document_data if isinstance(document_data, DocumentData) else DocumentData(**document_data)
    store = store or get_default_store()
    return store.add_chunks(chunk_document(doc))


def extract_clause_refs(question: str) -> List[str]:
    return _CLAUSE_REF.findall(question)


def _bm25(query_toks: List[str], chunks: List[Chunk], k1: float = 1.5, b: float = 0.75) -> Dict[str, float]:
    docs = {c.chunk_id: tokenize(c.heading + " " + c.text) for c in chunks}
    n = len(docs) or 1
    avg = sum(len(t) for t in docs.values()) / n or 1.0
    df: Counter = Counter()
    for toks in docs.values():
        df.update(set(toks))
    scores = {}
    for cid, toks in docs.items():
        tf = Counter(toks)
        s = 0.0
        for q in set(query_toks):
            if q not in tf:
                continue
            idf = math.log(1 + (n - df[q] + 0.5) / (df[q] + 0.5))
            s += idf * tf[q] * (k1 + 1) / (tf[q] + k1 * (1 - b + b * len(toks) / avg))
        scores[cid] = s
    return scores


def retrieve(document_id: str, question: str, top_k: int = 5,
             store: Optional[VectorStore] = None) -> List[RetrievedPassage]:
    store = store or get_default_store()
    chunks = store.get_chunks(document_id)
    if not chunks:
        raise DocumentNotIndexedError(f"Document {document_id!r} is not indexed.")
    by_id = {c.chunk_id: c for c in chunks}
    q_toks = tokenize(question)

    sem = {c.chunk_id: s for c, s in store.similarity_search(document_id, question, top_k=top_k * 3)}
    kw = _bm25(q_toks, chunks)
    refs = extract_clause_refs(question)
    clause_hits = {c.chunk_id for c in chunks for r in refs
                   if any(cid == r or cid.startswith(r + ".") for cid in c.clause_ids)}

    K = 60
    fused: Dict[str, float] = Counter()
    for rank, cid in enumerate(sorted(sem, key=sem.get, reverse=True)):
        fused[cid] += 1.0 / (K + rank + 1)
    kw_ranked = [cid for cid, s in sorted(kw.items(), key=lambda x: -x[1]) if s > 0]
    for rank, cid in enumerate(kw_ranked[: top_k * 3]):
        fused[cid] += 1.0 / (K + rank + 1)
    for cid in clause_hits:                    # explicit "clause 8.2" requests win
        fused[cid] += 0.5

    ranked = sorted(fused, key=fused.get, reverse=True)[:top_k]
    best = fused[ranked[0]] if ranked else 1.0
    qset = set(q_toks)
    out = []
    for cid in ranked:
        c = by_id[cid]
        out.append(RetrievedPassage(
            chunk=c, score=fused[cid] / best, semantic_score=sem.get(cid, 0.0),
            keyword_score=kw.get(cid, 0.0),
            overlap=len(qset & set(tokenize(c.heading + " " + c.text))),
            clause_match=cid in clause_hits))
    return out
