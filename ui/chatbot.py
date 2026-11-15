"""Chat / Ask AI page — matches the prototype's Ask AI view with chat bubbles + evidence chips."""
from __future__ import annotations

import streamlit as st

from orchestration.workflow import get_runtime, run_workflow
from ui.components import agents_caption, document_selector, render_comparison, render_risks, render_sources, show_messages

EXAMPLES = [
    "What is my notice period?",
    "Who are the parties to this agreement?",
    "What are the payment obligations?",
    "Can I work for a competitor after leaving?",
    "What information is considered confidential?",
    "What happens if the agreement is terminated?",
]


def _render_result(result) -> None:
    show_messages(result)
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
                history.append({"role": "assistant", "content": result.message, "result": result})
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
                _render_result(msg["result"])

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
            _render_result(result)
        history.append({"role": "assistant", "content": result.message, "result": result})

    # Clear chat button
    if history:
        if st.button("🗑 Clear conversation", key="clear_chat"):
            st.session_state["chat_history"][doc_id] = []
            st.rerun()
