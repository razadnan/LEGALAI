import json

from core.schemas import Chunk
from rag_engine import chat_engine
from rag_engine.retrieval import RetrievedPassage


def _passage(text="Either party may terminate with 30 days written notice."):
    chunk = Chunk(
        chunk_id="chunk-1",
        document_id="DOC001",
        chunk_index=0,
        text=text,
        page_start=2,
        page_end=2,
        clause="8",
        clause_ids=["8"],
        heading="Termination",
    )
    return RetrievedPassage(chunk=chunk, score=1.0, overlap=1)


def test_chat_history_rewrites_follow_up_before_retrieval(monkeypatch):
    queries = []

    def retrieve(_document_id, question, top_k, store):
        queries.append(question)
        return [_passage()]

    calls = []

    def llm(system, prompt):
        calls.append((system, prompt))
        if system == chat_engine.REWRITE_SYSTEM_PROMPT:
            return "What is the termination notice period?"
        return json.dumps({"answerable": True, "answer": "30 days.", "used_sources": ["S1"]})

    monkeypatch.setattr(chat_engine, "retrieve", retrieve)
    result = chat_engine.answer_question(
        "DOC001",
        "What about that?",
        llm=llm,
        chat_history=[
            {"role": "user", "content": "What is the termination clause?"},
            {"role": "assistant", "content": "Either party can terminate with notice."},
        ],
    )

    assert queries == ["What is the termination notice period?"]
    assert len(calls) == 2
    assert result["grounded"] is True
    assert result["sources"][0]["clause"] == "8"


def test_ungrounded_answer_retries_once_with_more_passages(monkeypatch):
    requested_depths = []

    def retrieve(_document_id, _question, top_k, store):
        requested_depths.append(top_k)
        return [_passage()]

    responses = iter([
        '{"answerable":false,"answer":"","used_sources":[]}',
        '{"answerable":true,"answer":"30 days.","used_sources":["S1"]}',
    ])
    monkeypatch.setattr(chat_engine, "retrieve", retrieve)

    result = chat_engine.answer_question(
        "DOC001",
        "What is the termination notice period?",
        llm=lambda _system, _prompt: next(responses),
    )

    assert requested_depths == [5, 10]
    assert result["grounded"] is True
    assert any("Retried once" in warning for warning in result["warnings"])


def test_simple_language_only_changes_answer_instruction(monkeypatch):
    retrieval_calls = []
    system_prompts = []

    def retrieve(document_id, question, top_k, store):
        retrieval_calls.append((document_id, question, top_k, store))
        return [_passage()]

    def llm(system, _prompt):
        system_prompts.append(system)
        return '{"answerable":true,"answer":"30 days.","used_sources":["S1"]}'

    monkeypatch.setattr(chat_engine, "retrieve", retrieve)
    normal = chat_engine.answer_question("DOC001", "What is the notice period?", llm=llm)
    simple = chat_engine.answer_question(
        "DOC001",
        "What is the notice period?",
        llm=llm,
        simple_language=True,
    )

    assert retrieval_calls == [
        ("DOC001", "What is the notice period?", 5, None),
        ("DOC001", "What is the notice period?", 5, None),
    ]
    assert system_prompts[0] == chat_engine.SYSTEM_PROMPT
    assert chat_engine.SIMPLE_LANGUAGE_INSTRUCTION in system_prompts[1]
    assert normal["sources"] == simple["sources"]
