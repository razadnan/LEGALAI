"""Evaluate the existing hybrid retriever against a small, labeled fixture."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Callable, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.schemas import DocumentData, Page  # noqa: E402
from rag_engine.chunking import chunk_document  # noqa: E402
from rag_engine.embeddings import (  # noqa: E402
    GeminiEmbedder,
    HashingEmbedder,
    OpenAIEmbedder,
    get_embedder,
)
from rag_engine.retrieval import RetrievedPassage, retrieve  # noqa: E402
from rag_engine.vector_store import VectorStore  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
DOCUMENT_ID = "RAG-BENCHMARK"


def load_benchmark() -> tuple[DocumentData, list[dict]]:
    text = (FIXTURES / "rag_benchmark_contract.txt").read_text(encoding="utf-8")
    pages = [Page(page_number=i, text=page.strip()) for i, page in enumerate(text.split("\f"), 1)]
    document = DocumentData(
        document_id=DOCUMENT_ID,
        filename="synthetic_employment_agreement.txt",
        pages=pages,
        file_type="txt",
    )
    questions = json.loads((FIXTURES / "rag_retrieval_benchmark.json").read_text(encoding="utf-8"))
    return document, questions


def is_relevant(passage: RetrievedPassage, gold_clauses: Iterable[str]) -> bool:
    for clause in gold_clauses:
        if clause == "PREAMBLE":
            if passage.chunk.heading == "Preamble":
                return True
        elif clause in passage.chunk.clause_ids:
            return True
    return False


def score_ranked_results(results: list[list[RetrievedPassage]], questions: list[dict]) -> dict:
    if len(results) != len(questions):
        raise ValueError("Each benchmark question must have exactly one ranked result list.")
    if not questions:
        raise ValueError("The benchmark contains no questions.")

    recalls: dict[str, float] = {}
    for k in (1, 3, 5):
        hits = [
            any(is_relevant(passage, question["gold_clauses"]) for passage in ranked[:k])
            for ranked, question in zip(results, questions)
        ]
        recalls[f"recall_at_{k}"] = mean(hits)

    reciprocal_ranks = []
    for ranked, question in zip(results, questions):
        rank = next(
            (i for i, passage in enumerate(ranked, 1) if is_relevant(passage, question["gold_clauses"])),
            None,
        )
        reciprocal_ranks.append(1 / rank if rank is not None else 0.0)
    return {**recalls, "mrr": mean(reciprocal_ranks)}


def resolve_embedder(mode: str):
    if mode == "offline":
        embedder = HashingEmbedder()
        return embedder, "local", embedder.name
    if mode != "production":
        raise ValueError(f"Unsupported embedding mode: {mode}")

    try:
        from config.settings import Settings

        settings = Settings()
    except Exception as exc:
        raise RuntimeError(
            f"Could not load application embedding configuration ({type(exc).__name__})."
        ) from None

    configured_provider = os.getenv("EMBEDDING_PROVIDER", "auto").strip().lower()
    if configured_provider not in {"auto", "local", "openai", "gemini", "google"}:
        raise RuntimeError("EMBEDDING_PROVIDER must be auto, openai, gemini, or local.")
    if configured_provider == "local":
        raise RuntimeError(
            "Production embedding mode resolved to the local hash embedder; use offline mode or configure a production provider."
        )
    if configured_provider == "openai" and not settings.has_openai_key:
        raise RuntimeError("The configured OpenAI embedding provider has no valid API key.")
    if configured_provider in {"gemini", "google"} and not settings.has_gemini_key:
        raise RuntimeError("The configured Gemini embedding provider has no valid API key.")

    try:
        embedder = get_embedder()
    except Exception as exc:
        raise RuntimeError(
            f"Could not initialize the configured production embedding provider ({type(exc).__name__}); check its dependency and configuration."
        ) from None

    if isinstance(embedder, HashingEmbedder):
        raise RuntimeError(
            "No production embedding provider was resolved; configure a valid provider and API key before using production mode."
        )
    if isinstance(embedder, GeminiEmbedder):
        return embedder, "gemini", embedder.model
    if isinstance(embedder, OpenAIEmbedder):
        return embedder, "openai", embedder.model
    raise RuntimeError("The configured embedding factory returned an unsupported provider.")


def rerank_passages(
    question: str,
    passages: list[RetrievedPassage],
    score_pairs: Callable[[list[list[str]]], Sequence[float]],
) -> list[RetrievedPassage]:
    pairs = [[question, passage.chunk.heading + "\n" + passage.chunk.text] for passage in passages]
    scores = score_pairs(pairs)
    if len(scores) != len(passages):
        raise ValueError("The reranker must return one score per candidate passage.")
    ranked = sorted(
        enumerate(zip(passages, scores)),
        key=lambda item: (-float(item[1][1]), item[0]),
    )
    return [passage for _, (passage, _) in ranked]


def evaluate_benchmark(document, questions, embedder, top_k: int, reranker=None):
    chunks = chunk_document(document)
    clause_ids = {clause for chunk in chunks for clause in chunk.clause_ids}
    headings = {chunk.heading for chunk in chunks}
    for item in questions:
        missing = [
            clause for clause in item["gold_clauses"]
            if clause != "PREAMBLE" and clause not in clause_ids
        ]
        if "PREAMBLE" in item["gold_clauses"] and "Preamble" not in headings:
            missing.append("PREAMBLE")
        if missing:
            raise ValueError(f"{item['id']} refers to missing gold source(s): {missing}")

    with tempfile.TemporaryDirectory(prefix="legalmind-rag-eval-") as temp_dir:
        store = VectorStore(persist_dir=temp_dir, embedder=embedder, backend="memory")
        start = perf_counter()
        try:
            store.add_chunks(chunks)
        except Exception as exc:
            raise RuntimeError(
                f"Document embedding failed ({type(exc).__name__}); check provider credentials, model name, quota, and network access. Details are suppressed."
            ) from None
        embedding_seconds = perf_counter() - start

        if len(store.get_chunks(DOCUMENT_ID)) != len(chunks):
            raise RuntimeError(
                "The embedding provider returned an incomplete document embedding result."
            )

        start = perf_counter()
        try:
            results = [
                retrieve(DOCUMENT_ID, item["question"], top_k=top_k, store=store)
                for item in questions
            ]
        except Exception as exc:
            raise RuntimeError(
                f"Query embedding or retrieval failed ({type(exc).__name__}); check provider credentials, model name, quota, and network access. Details are suppressed."
            ) from None
        retrieval_seconds = perf_counter() - start

        baseline = score_ranked_results(results, questions)
        reranked_results = None
        reranked_metrics = None
        reranking_seconds = 0.0
        if reranker is not None:
            start = perf_counter()
            try:
                reranked_results = [
                    rerank_passages(
                        item["question"],
                        ranked,
                        lambda pairs: reranker.predict(
                            pairs, batch_size=16, show_progress_bar=False
                        ),
                    )
                    for item, ranked in zip(questions, results)
                ]
            except Exception as exc:
                raise RuntimeError(
                    f"Cross-encoder scoring failed ({type(exc).__name__}); verify the locally cached model. Details are suppressed."
                ) from None
            reranking_seconds = perf_counter() - start
            reranked_metrics = score_ranked_results(reranked_results, questions)

    return {
        "chunks": chunks,
        "results": results,
        "reranked_results": reranked_results,
        "baseline": baseline,
        "reranked": reranked_metrics,
        "timings": {
            "document_embedding_seconds": embedding_seconds,
            "query_and_retrieval_seconds": retrieval_seconds,
            "reranking_seconds": reranking_seconds,
        },
    }


def load_cross_encoder(model_name: str):
    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        raise RuntimeError(
            "Install optional evaluation dependencies with "
            "'.\\.venv\\Scripts\\python.exe -m pip install -r requirements-eval.txt'."
        ) from None
    try:
        return CrossEncoder(model_name, max_length=512, local_files_only=True)
    except Exception as exc:
        raise RuntimeError(
            f"Could not load the locally cached cross-encoder ({type(exc).__name__}); no model download was attempted."
        ) from None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-k", type=int, default=5, help="Retrieval depth to measure (default: 5)")
    parser.add_argument(
        "--embedding-mode",
        choices=("offline", "production"),
        default="offline",
        help="Use deterministic local hashing (default) or the application's configured production embedder",
    )
    parser.add_argument(
        "--cross-encoder",
        help="Optional sentence-transformers CrossEncoder model name for reranking candidates",
    )
    args = parser.parse_args()
    if args.top_k < 5:
        parser.error("--top-k must be at least 5 to report Recall@5")

    total_start = perf_counter()
    reranker = None
    if args.cross_encoder:
        try:
            reranker = load_cross_encoder(args.cross_encoder)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from None

    try:
        embedder, provider, model = resolve_embedder(args.embedding_mode)
        document, questions = load_benchmark()
        evaluation = evaluate_benchmark(document, questions, embedder, args.top_k, reranker)
    except Exception as exc:
        if args.embedding_mode == "production":
            raise SystemExit(
                f"Production embedding evaluation failed ({type(exc).__name__}). Check the configured provider, API key, model, quota, and network; details are suppressed to protect secrets."
            ) from None
        raise

    chunks = evaluation["chunks"]
    results = evaluation["results"]
    reranked_results = evaluation["reranked_results"]
    baseline = evaluation["baseline"]
    reranked = evaluation["reranked"]
    timings = evaluation["timings"]

    print(f"Dataset: {len(questions)} questions; {len(chunks)} chunks")
    print(f"Embeddings: mode={args.embedding_mode}; provider={provider}; model={model}")
    print("Vector index: temporary isolated backend; production collections and storage are not used")
    print("RRF: " + " | ".join(f"{key}={value:.3f}" for key, value in baseline.items()))
    if reranked is not None:
        print(f"Cross-encoder ({args.cross_encoder}): " + " | ".join(
            f"{key}={value:.3f} ({value - baseline[key]:+.3f})"
            for key, value in reranked.items()
        ))

    print("\nPer-query first relevant rank:")
    for index, (item, ranked) in enumerate(zip(questions, results)):
        base_rank = next(
            (i for i, passage in enumerate(ranked, 1) if is_relevant(passage, item["gold_clauses"])),
            None,
        )
        line = f"{item['id']}: RRF={base_rank or 'miss'}"
        if reranked_results is not None:
            rerank_rank = next(
                (
                    i for i, passage in enumerate(reranked_results[index], 1)
                    if is_relevant(passage, item["gold_clauses"])
                ),
                None,
            )
            line += f" reranked={rerank_rank or 'miss'}"
        got = ranked[0].chunk.clause_ids if ranked else []
        print(f"{line} top_clause={','.join(got) or 'Preamble'}")

    total_seconds = perf_counter() - total_start
    print(
        "\nExecution time: "
        f"document_embeddings={timings['document_embedding_seconds']:.2f}s; "
        f"query_and_retrieval={timings['query_and_retrieval_seconds']:.2f}s; "
        f"reranking={timings['reranking_seconds']:.2f}s; "
        f"total={total_seconds:.2f}s"
    )


if __name__ == "__main__":
    main()
