import asyncio

from api import main
from core.schemas import AnswerResult, WorkflowResult


def test_chat_passes_plain_language_and_returns_agent_trace(monkeypatch):
    captured = {}

    monkeypatch.setattr(main, "_get_document", lambda _document_id: object())

    def workflow(*args):
        captured["args"] = args
        return WorkflowResult(
            task="auto",
            intent="qa",
            agents_invoked=["rag_agent"],
            answer=AnswerResult(answer="30 days"),
        )

    monkeypatch.setattr(main, "_workflow", workflow)
    request = main.ChatRequest(
        question="What about notice?",
        history=[main.ChatTurn(role="user", content="How does termination work?")],
        simple_language=True,
    )

    result = asyncio.run(main.chat("DOC001", request))

    assert captured["args"] == (
        "auto",
        ["DOC001"],
        "What about notice?",
        [{"role": "user", "content": "How does termination work?"}],
        True,
    )
    assert result.agents_invoked == ["rag_agent"]
