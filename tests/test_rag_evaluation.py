import sys
from types import SimpleNamespace

import pytest

import config.settings
import scripts.evaluate_retrieval as evaluation
from scripts.evaluate_retrieval import (
    load_benchmark,
    load_cross_encoder,
    rerank_passages,
    score_ranked_results,
)
from rag_engine.chunking import chunk_document
from rag_engine.embeddings import GeminiEmbedder, HashingEmbedder
from rag_engine.retrieval import RetrievedPassage


def test_benchmark_gold_sources_exist_and_questions_are_unique():
    documents, questions = load_benchmark()
    chunks_by_document = {doc.document_id: chunk_document(doc) for doc in documents}

    assert len(documents) == 4
    assert len(questions) >= 60
    assert len({item["id"] for item in questions}) == len(questions)
    assert len({item["question"] for item in questions}) == len(questions)
    for item in questions:
        chunks = chunks_by_document[item["document_id"]]
        clause_ids = {clause for chunk in chunks for clause in chunk.clause_ids}
        headings = {chunk.heading for chunk in chunks}
        for clause in item["gold_clauses"]:
            assert clause == "PREAMBLE" and "Preamble" in headings or clause in clause_ids


def test_metrics_measure_first_relevant_rank_and_recall():
    documents, questions = load_benchmark()
    doc = next(doc for doc in documents if doc.document_id == questions[0]["document_id"])
    chunks = chunk_document(doc)
    by_clause = {clause: chunk for chunk in chunks for clause in chunk.clause_ids}
    first_question = questions[0]
    relevant = by_clause[first_question["gold_clauses"][0]]
    irrelevant = next(chunk for chunk in chunks if chunk.chunk_id != relevant.chunk_id)
    results = [
        [RetrievedPassage(chunk=irrelevant, score=1), RetrievedPassage(chunk=relevant, score=0.5)],
        *([[]] * (len(questions) - 1)),
    ]

    metrics = score_ranked_results(results, questions)

    assert metrics["recall_at_1"] == 0
    assert metrics["recall_at_3"] == 1 / len(questions)
    assert metrics["mrr"] == 0.5 / len(questions)


def test_reranker_orders_candidates_by_score_and_keeps_stable_ties():
    documents, _ = load_benchmark()
    chunks = chunk_document(documents[0])
    passages = [RetrievedPassage(chunk=chunk, score=1) for chunk in chunks[:3]]

    def score_pairs(pairs):
        assert len(pairs) == 3
        return [0.2, 0.9, 0.9]

    ranked = rerank_passages("question", passages, score_pairs)

    assert [passage.chunk.chunk_id for passage in ranked] == [
        passages[1].chunk.chunk_id,
        passages[2].chunk.chunk_id,
        passages[0].chunk.chunk_id,
    ]


def test_offline_embedding_mode_remains_local_and_deterministic():
    embedder, provider, model = evaluation.resolve_embedder("offline")

    assert isinstance(embedder, HashingEmbedder)
    assert provider == "local"
    assert model == "local-hash768"


def test_production_mode_uses_configured_application_embedder(monkeypatch):
    settings = SimpleNamespace(has_gemini_key=True, has_openai_key=False)
    embedder = GeminiEmbedder.__new__(GeminiEmbedder)
    embedder.model = "configured-gemini-model"
    embedder.name = f"gemini-{embedder.model}"
    monkeypatch.setattr(config.settings, "Settings", lambda: settings)
    monkeypatch.setattr(evaluation, "get_embedder", lambda: embedder)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "gemini")

    resolved, provider, model = evaluation.resolve_embedder("production")

    assert resolved is embedder
    assert provider == "gemini"
    assert model == "configured-gemini-model"


def test_production_mode_rejects_missing_configured_api_key(monkeypatch):
    settings = SimpleNamespace(has_gemini_key=False, has_openai_key=False)
    monkeypatch.setattr(config.settings, "Settings", lambda: settings)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "gemini")
    monkeypatch.setattr(
        evaluation,
        "get_embedder",
        lambda: pytest.fail("The provider factory must not run without a key."),
    )

    with pytest.raises(RuntimeError, match="no valid API key"):
        evaluation.resolve_embedder("production")


def test_production_mode_does_not_fall_back_to_hash_embeddings(monkeypatch):
    settings = SimpleNamespace(has_gemini_key=False, has_openai_key=False)
    monkeypatch.setattr(config.settings, "Settings", lambda: settings)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "auto")
    monkeypatch.setattr(evaluation, "get_embedder", HashingEmbedder)

    with pytest.raises(RuntimeError, match="No production embedding provider"):
        evaluation.resolve_embedder("production")


def test_production_provider_error_is_reported_without_raw_details(monkeypatch):
    settings = SimpleNamespace(has_gemini_key=True, has_openai_key=False)

    def fail_with_secret():
        raise RuntimeError("request failed with key=secret-value")

    monkeypatch.setattr(config.settings, "Settings", lambda: settings)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "gemini")
    monkeypatch.setattr(evaluation, "get_embedder", fail_with_secret)

    with pytest.raises(RuntimeError) as error:
        evaluation.resolve_embedder("production")

    assert "secret-value" not in str(error.value)
    assert "RuntimeError" in str(error.value)


def test_evaluation_uses_one_embedder_for_chunks_and_all_queries():
    documents, questions = load_benchmark()
    delegate = HashingEmbedder()

    class SpyEmbedder:
        name = "spy-local"

        def __init__(self):
            self.document_calls = 0
            self.query_calls = 0

        def embed_documents(self, texts):
            self.document_calls += 1
            return delegate.embed_documents(texts)

        def embed_query(self, text):
            self.query_calls += 1
            return delegate.embed_query(text)

    embedder = SpyEmbedder()
    result = evaluation.evaluate_benchmark(documents, questions, embedder, top_k=5)

    assert result["baseline"]["mrr"] > 0
    assert len(result["per_document"]) == len(documents)
    assert 0 <= result["macro_average"]["mrr"] <= 1
    assert embedder.document_calls == 1
    assert embedder.query_calls == len(questions)
    assert result["timings"]["document_embedding_seconds"] >= 0
    assert result["timings"]["query_and_retrieval_seconds"] >= 0


def test_missing_cached_cross_encoder_does_not_attempt_download(monkeypatch):
    def missing_model(model_name, **kwargs):
        assert model_name == "missing-local-model"
        assert kwargs["local_files_only"] is True
        raise OSError("private token should not be shown")

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(CrossEncoder=missing_model),
    )

    with pytest.raises(RuntimeError) as error:
        load_cross_encoder("missing-local-model")

    assert "private token" not in str(error.value)
    assert "no model download was attempted" in str(error.value)


def test_document_embedding_provider_error_is_sanitized():
    documents, questions = load_benchmark()

    class FailingEmbedder:
        name = "failing-provider"

        def embed_documents(self, texts):
            assert texts
            raise RuntimeError("provider response contained secret-value")

        def embed_query(self, text):
            raise AssertionError(f"unexpected query embedding for {text!r}")

    with pytest.raises(RuntimeError) as error:
        evaluation.evaluate_benchmark(documents, questions, FailingEmbedder(), top_k=5)

    assert "secret-value" not in str(error.value)
    assert "Document embedding failed" in str(error.value)
