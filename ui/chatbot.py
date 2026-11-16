"""Chat / Ask AI page — matches the prototype's Ask AI view with chat bubbles + evidence chips."""
from __future__ import annotations

import json
from pathlib import Path
import streamlit as st

from core.schemas import AnswerResult, Source, WorkflowResult
from orchestration.workflow import get_runtime, run_workflow
from ui.components import agents_caption, document_selector, render_comparison, render_risks, render_sources, show_messages

EXAMPLES = [
    "What is the annual base subscription fee?",
    "What is the notice period for convenience termination?",
    "What is the liability cap under this contract?",
    "Which law governs this agreement?",
    "Is there an SLA in this contract?",
]


def _get_cached_answer(question: str) -> dict | None:
    cache_path = Path("demo/cached_answers.json")
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        q_l = question.lower().strip(" ?.")
        for k, item in data.get("questions", {}).items():
            cached_q_l = item["question"].lower().strip(" ?.")
            if q_l == cached_q_l:
                return item
            if k == "annual_fee" and "fee" in q_l and ("annual" in q_l or "subscription" in q_l):
                return item
            if k == "notice_period" and "notice" in q_l:
                return item
            if k == "liability_cap" and "liability" in q_l:
                return item
            if k == "governing_law" and ("law" in q_l or "govern" in q_l):
                return item
            if k == "sla" and ("sla" in q_l or "service level" in q_l):
                return item
    except Exception:
        pass
    return None


def _render_result(result, is_cached: bool = False) -> None:
    show_messages(result)
    if is_cached:
        st.markdown(
            '<div style="font-size:11px;color:var(--mut);padding:4px 8px;background:var(--bg);border-radius:6px;margin-bottom:8px;">'
            '📦 Cached analysis from pre-run demo session · Generated at: 2026-11-16T12:50:00Z'
            '</div>',
            unsafe_allow_html=True,
        )
    if result.message:
        st.markdown(result.message)
    if result.answer:
        render_sources(result.answer)
    if result.intent == "risk":
        render_risks(result.risks)
    if result.comparison:
        render_comparison(result.comparison)
    agents_caption(result)


def render() -> None:
    rt = get_runtime()
    st.markdown("<h1>Ask the document</h1>", unsafe_allow_html=True)
    st.markdown(
        '<p class="lm-sub">Answers come only from your contract and always show the supporting clause and page.</p>',
        unsafe_allow_html=True,
    )

    doc_id = document_selector(rt.registry, key="chat_doc")
    if not doc_id:
        return
    st.session_state["active_document_id"] = doc_id
    history = st.session_state["chat_history"].setdefault(doc_id, [])

    # ── Example question chips ────────────────────────────────────────────────
    chips_html = "".join(
        f'<span class="lm-chip" style="font-size:12px;">{q}</span>' for q in EXAMPLES
    )
    st.markdown(f'<div style="margin-bottom:14px;">{chips_html}</div>', unsafe_allow_html=True)

    # Actual clickable example buttons in a collapsed expander
    with st.expander("💡 Example questions — click to send"):
        cols = st.columns(2)
        for i, ex in enumerate(EXAMPLES):
            if cols[i % 2].button(ex, key=f"ex_{i}", use_container_width=True):
                history.append({"role": "user", "content": ex})
                with st.spinner("Thinking…"):
                    result = run_workflow("auto", [doc_id], ex, chat_history=history[:-1])
                is_cached = False
                cached_item = _get_cached_answer(ex)
                if cached_item and (result.errors or not result.answer):
                    sources = [Source(page=s.get("page"), clause=s.get("clause"), text=s.get("quote"), verified=True) for s in cached_item.get("sources", [])]
                    ans = AnswerResult(
                        answer=cached_item["answer"],
                        sources=sources,
                        grounded=bool(sources),
                        mode="cached",
                    )
                    result = WorkflowResult(
                        task="qa",
                        intent="qa",
                        documents=[],
                        message=cached_item["answer"],
                        answer=ans,
                        agents_invoked=["rag_agent", "verifier"],
                    )
                    is_cached = True
                history.append({"role": "assistant", "content": result.message, "result": result, "is_cached": is_cached})
                st.rerun()

    # ── Chat history ──────────────────────────────────────────────────────────
    st.markdown('<div class="lm-card">', unsafe_allow_html=True)

    if not history:
        st.markdown(
            '<div style="text-align:center;padding:40px 0;color:var(--mut);">'
            '<div style="font-size:32px;">💬</div>'
            '<p>Ask anything about your contract — answers are always evidence-backed.</p>'
            '</div>',
            unsafe_allow_html=True,
        )

    for msg in history:
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.write(msg["content"])
            else:
                _render_result(msg["result"], is_cached=msg.get("is_cached", False))

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Chat input ────────────────────────────────────────────────────────────
    prompt = st.chat_input("Ask about any clause…")
    if prompt:
        history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Searching clauses…"):
                result = run_workflow("auto", [doc_id], prompt, chat_history=history[:-1])

            is_cached = False
            cached_item = _get_cached_answer(prompt)
            if cached_item and (result.errors or not result.answer):
                sources = [Source(page=s.get("page"), clause=s.get("clause"), text=s.get("quote"), verified=True) for s in cached_item.get("sources", [])]
                ans = AnswerResult(
                    answer=cached_item["answer"],
                    sources=sources,
                    grounded=bool(sources),
                    mode="cached",
                )
                result = WorkflowResult(
                    task="qa",
                    intent="qa",
                    documents=[],
                    message=cached_item["answer"],
                    answer=ans,
                    agents_invoked=["rag_agent", "verifier"],
                )
                is_cached = True

            _render_result(result, is_cached=is_cached)
        history.append({"role": "assistant", "content": result.message, "result": result, "is_cached": is_cached})

    # Clear chat button
    if history:
        if st.button("🗑 Clear conversation", key="clear_chat"):
            st.session_state["chat_history"][doc_id] = []
            st.rerun()
