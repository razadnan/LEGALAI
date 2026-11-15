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


def _load_document(filename: str, document_id: str) -> DocumentData:
    text = (FIXTURES / filename).read_text(encoding="utf-8")
    pages = [Page(page_number=i, text=page.strip()) for i, page in enumerate(text.split("\f"), 1)]
    return DocumentData(document_id=document_id, filename=filename, pages=pages, file_type="txt")


def load_benchmark() -> tuple[list[DocumentData], list[dict]]:
    documents = [
        _load_document("rag_benchmark_contract.txt", "RAG-BENCHMARK-EMPLOYMENT"),
        _load_document("rag_benchmark_nda.txt", "RAG-BENCHMARK-NDA"),
        _load_document("rag_benchmark_lease.txt", "RAG-BENCHMARK-LEASE"),
        _load_document("rag_benchmark_services.txt", "RAG-BENCHMARK-SERVICES"),
    ]
    questions = json.loads((FIXTURES / "rag_retrieval_benchmark.json").read_text(encoding="utf-8"))
    questions.extend(
        json.loads((FIXTURES / "rag_retrieval_benchmark_additional.json").read_text(encoding="utf-8"))
    )
    for item in questions:
        item.setdefault("document_id", documents[0].document_id)
    return documents, questions


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


def evaluate_benchmark(documents, questions, embedder, top_k: int, reranker=None):
    chunks_by_document = {document.document_id: chunk_document(document) for document in documents}
    chunks = [chunk for document_chunks in chunks_by_document.values() for chunk in document_chunks]
    documents_by_id = {document.document_id: document for document in documents}
    for item in questions:
        document_chunks = chunks_by_document.get(item["document_id"])
        if document_chunks is None:
            raise ValueError(f"{item['id']} refers to unknown document {item['document_id']!r}.")
        clause_ids = {clause for chunk in document_chunks for clause in chunk.clause_ids}
        headings = {chunk.heading for chunk in document_chunks}
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

        if any(
            len(store.get_chunks(document.document_id)) != len(chunks_by_document[document.document_id])
            for document in documents
        ):
            raise RuntimeError(
                "The embedding provider returned an incomplete document embedding result."
            )

        start = perf_counter()
        try:
            results = [
                retrieve(item["document_id"], item["question"], top_k=top_k, store=store)
                for item in questions
            ]
        except Exception as exc:
            raise RuntimeError(
                f"Query embedding or retrieval failed ({type(exc).__name__}); check provider credentials, model name, quota, and network access. Details are suppressed."
            ) from None
        retrieval_seconds = perf_counter() - start

        baseline = score_ranked_results(results, questions)
        per_document = {}
        for document in documents:
            indexes = [i for i, item in enumerate(questions) if item["document_id"] == document.document_id]
            if indexes:
                per_document[document.filename] = score_ranked_results(
                    [results[i] for i in indexes], [questions[i] for i in indexes]
                )
        macro_average = {
            key: mean(metrics[key] for metrics in per_document.values())
            for key in baseline
        }
        reranked_results = None
        reranked_metrics = None
        reranked_per_document = None
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
            reranked_per_document = {
                name: score_ranked_results(
                    [reranked_results[i] for i, item in enumerate(questions)
                     if documents_by_id[item["document_id"]].filename == name],
                    [item for item in questions if documents_by_id[item["document_id"]].filename == name],
                )
                for name in per_document
            }

    return {
        "chunks": chunks,
        "results": results,
        "reranked_results": reranked_results,
        "baseline": baseline,
        "per_document": per_document,
        "macro_average": macro_average,
        "reranked": reranked_metrics,
        "reranked_per_document": reranked_per_document,
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
            "'.\\.venv\\Scripts\\python.exe -m pip install sentence-transformers==5.7.0'."
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
        documents, questions = load_benchmark()
        evaluation = evaluate_benchmark(documents, questions, embedder, args.top_k, reranker)
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

    print(f"Dataset: {len(documents)} synthetic contracts; {len(questions)} questions; {len(chunks)} chunks")
    print(f"Embeddings: mode={args.embedding_mode}; provider={provider}; model={model}")
    print("Vector index: temporary isolated backend; production collections and storage are not used")
    print("RRF: " + " | ".join(f"{key}={value:.3f}" for key, value in baseline.items()))
    print(f"Macro average across {len(evaluation['per_document'])} contracts: " + " | ".join(
        f"{key}={value:.3f}" for key, value in evaluation["macro_average"].items()
    ))
    for filename, metrics in evaluation["per_document"].items():
        print(f"  {filename}: " + " | ".join(f"{key}={value:.3f}" for key, value in metrics.items()))
    if reranked is not None:
        print(f"Cross-encoder ({args.cross_encoder}): " + " | ".join(
            f"{key}={value:.3f} ({value - baseline[key]:+.3f})"
            for key, value in reranked.items()
        ))
        print("Reranked macro average: " + " | ".join(
            f"{key}={value:.3f}" for key, value in {
                key: mean(metrics[key] for metrics in evaluation["reranked_per_document"].values())
                for key in reranked
            }.items()
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
