"""Upload page — matches the prototype's Upload view with drag-drop zone + progress steps."""
from __future__ import annotations

import streamlit as st

from core.exceptions import LegalMindError
from orchestration.workflow import get_runtime, process_upload, run_workflow
from ui.components import show_messages


def process_and_analyze(uploaded, *, analyze: bool = True):
    """Shared by Upload and Comparison pages. Returns the new document or None."""
    try:
        with st.spinner(f"Extracting text from {uploaded.name}…"):
            doc = process_upload(uploaded.name, uploaded.getvalue())
    except LegalMindError as exc:
        st.error(exc.user_message)
        return None
    if analyze:
        with st.spinner("Analyzing document (type, parties, dates, obligations)…"):
            result = run_workflow("summarize", [doc.document_id])
        show_messages(result)
    st.session_state["active_document_id"] = doc.document_id
    return doc


def render() -> None:
    s = get_runtime().settings

    # ── Page header ───────────────────────────────────────────────────────────
    st.markdown("<h1>Upload a contract</h1>", unsafe_allow_html=True)
    st.markdown(
        f'<p class="lm-sub">PDF or DOCX with selectable text · up to {s.max_upload_mb} MB · '
        f"Scanned PDFs are not supported.</p>",
        unsafe_allow_html=True,
    )

    # ── Upload zone ───────────────────────────────────────────────────────────
    st.markdown(
        """
        <div class="lm-card" style="text-align:center;padding:32px 16px;">
            <div style="font-size:40px;margin-bottom:8px;">📄</div>
            <p style="font-weight:700;margin:0 0 4px;">Drag &amp; drop your contract here</p>
            <p class="lm-sub" style="margin:0;">PDF or DOCX &nbsp;·&nbsp; up to {mb} MB &nbsp;·&nbsp;
            scanned PDFs not supported</p>
        </div>
        """.format(mb=s.max_upload_mb),
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader(
        "Choose a file",
        type=[ext.lstrip(".") for ext in s.allowed_extensions],
        label_visibility="collapsed",
    )

    if uploaded:
        st.markdown(
            f'<div class="lm-card"><div class="lm-row">'
            f'<b>📄 {uploaded.name}</b>'
            f'<span style="color:var(--mut);font-size:13px;">'
            f'{uploaded.size // 1024} KB</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

        already_processed = st.session_state.get("_last_upload") == uploaded.name
        if not already_processed:
            st.session_state["_last_upload"] = uploaded.name
        if not already_processed:
            # Animated steps progress
            steps = [
                "Extracting text and page numbers",
                "Detecting document type and parties",
                "Splitting into clauses",
                "Creating embeddings and indexing",
                "Preparing risk review",
            ]
            progress_placeholder = st.empty()

            with progress_placeholder.container():
                st.markdown(
                    f'<div class="lm-card">'
                    f'<div class="lm-row"><b>{uploaded.name}</b>'
                    f'<span style="color:var(--mut);font-size:13px;">Processing…</span></div>',
                    unsafe_allow_html=True,
                )
                prog_bar = st.progress(0)
                step_placeholder = st.empty()

            # Process document
            doc = None
            try:
                for i, step in enumerate(steps):
                    step_html = "".join(
                        f'<li class="lm-step {"lm-step-done" if j < i else "lm-step-run" if j == i else ""}">'
                        f'{"✓" if j < i else "◔" if j == i else "○"} {s}</li>'
                        for j, s in enumerate(steps)
                    )
                    step_placeholder.markdown(
                        f'<ul class="lm-steps">{step_html}</ul>',
                        unsafe_allow_html=True,
                    )
                    prog_bar.progress((i + 1) / len(steps))

                    if i == 0:  # actual work happens here
                        try:
                            doc = process_upload(uploaded.name, uploaded.getvalue())
                        except LegalMindError as exc:
                            progress_placeholder.empty()
                            st.error(exc.user_message)
                            return

                    elif i == 1 and doc:
                        result = run_workflow("summarize", [doc.document_id])
                        show_messages(result)

                # Complete
                prog_bar.progress(1.0)
                step_placeholder.markdown(
                    f'<ul class="lm-steps">'
                    + "".join(f'<li class="lm-step lm-step-done">✓ {s}</li>' for s in steps)
                    + "</ul>",
                    unsafe_allow_html=True,
                )

            except Exception as exc:
                progress_placeholder.empty()
                st.error(f"Processing failed: {exc}")
                return

            if doc:
                st.session_state["active_document_id"] = doc.document_id
                progress_placeholder.empty()

                # Success card
                st.markdown(
                    f'<div class="lm-card" style="border-left:4px solid var(--lo);">'
                    f'<div class="lm-row">'
                    f'<div><b>✓ {doc.filename}</b><br>'
                    f'<span style="color:var(--mut);font-size:13px;">'
                    f'{doc.document_id} · {doc.page_count} page(s) · ready</span></div>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    if st.button("▦  View Overview", use_container_width=True):
                        st.session_state["page"] = "overview"
                        st.rerun()
                with col_b:
                    if st.button("💬  Ask AI", use_container_width=True):
                        st.session_state["page"] = "chat"
                        st.rerun()
                with col_c:
                    if st.button("⚠  View Risks", use_container_width=True):
                        st.session_state["page"] = "risks"
                        st.rerun()

                with st.expander("Text preview (page 1)"):
                    st.text((doc.pages[0].text if doc.pages else "")[:1500])
    else:
        st.markdown(
            '<p style="color:var(--mut);font-size:13px;text-align:center;margin-top:8px;">'
            'or drag a file onto the zone above</p>',
            unsafe_allow_html=True,
        )
