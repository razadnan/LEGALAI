"""Report page — matches the prototype's Generate report view with section picker + preview."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from orchestration.workflow import get_runtime, run_workflow
from ui.components import agents_caption, show_messages


SECTIONS = [
    ("Summary & parties", True),
    ("Key dates and compensation", True),
    ("Obligations", True),
    ("Risk findings with evidence", True),
    ("Version comparison", False),
]


def render() -> None:
    rt = get_runtime()
    st.markdown("<h1>Generate report</h1>", unsafe_allow_html=True)
    st.markdown(
        '<p class="lm-sub">Choose what to include, preview it, then download.</p>',
        unsafe_allow_html=True,
    )

    ids = rt.registry.list_ids()
    if not ids:
        st.markdown(
            '<div class="lm-card" style="text-align:center;padding:32px;">'
            '<div style="font-size:32px;">📄</div>'
            '<p style="font-weight:700;">No documents yet.</p>'
            '<p class="lm-sub">Go to <b>Upload</b> first.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    col_cfg, col_prev = st.columns([1, 1])

    with col_cfg:
        st.markdown('<div class="lm-card"><h2>Sections</h2>', unsafe_allow_html=True)

        selected = st.multiselect(
            "Documents (first is analyzed; select a second for version comparison)",
            ids,
            default=(
                [st.session_state["active_document_id"]]
                if st.session_state.get("active_document_id") in ids
                else ids[:1]
            ),
            max_selections=2,
            format_func=lambda i: f"{i} — {rt.registry.get(i).filename}",
        )

        question = st.text_input(
            "Optional: include a Q&A answer in the report",
            placeholder="e.g. What is the notice period?",
        )

        # Section toggles
        section_states = {}
        for label, default in SECTIONS:
            is_comparison = "comparison" in label.lower()
            disabled = is_comparison and len(selected) < 2
            checked = st.checkbox(
                label,
                value=default and not disabled,
                disabled=disabled,
                key=f"sec_{label}",
            )
            section_states[label] = checked

        st.markdown('</div>', unsafe_allow_html=True)

        generate_btn = st.button(
            "⬇  Generate PDF report",
            type="primary",
            disabled=not selected,
            use_container_width=True,
        )

    with col_prev:
        st.markdown('<div class="lm-card"><h2>Preview</h2>', unsafe_allow_html=True)

        # Build preview from cached analysis (if available)
        preview_lines = []
        if selected:
            doc_id = selected[0]
            doc = rt.registry.get(doc_id)
            cached = st.session_state.get("results", {})

            analysis = None
            for key, r in cached.items():
                if isinstance(key, (list, tuple)) and doc_id in key and hasattr(r, "analysis") and r.analysis:
                    analysis = r.analysis
                    break

            if section_states.get("Summary & parties"):
                preview_lines.append("<b>Summary</b>")
                if analysis and analysis.document_type:
                    # parties is list[str] after schema coercion; items may be "Name (Role)"
                    parties = ", ".join(str(p) for p in (analysis.parties or []))
                    preview_lines.append(
                        f"{analysis.document_type} between {parties or 'parties not identified'}."
                    )
                else:
                    preview_lines.append(f"Document: {doc.filename}")
                preview_lines.append("")

            if section_states.get("Key dates and compensation"):
                preview_lines.append("<b>Key terms</b>")
                if analysis and analysis.important_dates:
                    for d in analysis.important_dates[:3]:
                        preview_lines.append(f"• {d.label}: {d.date}")
                else:
                    preview_lines.append("Key dates not yet extracted.")
                preview_lines.append("")

            if section_states.get("Obligations"):
                preview_lines.append("<b>Obligations</b>")
                if analysis and analysis.obligations:
                    preview_lines.append(f"{len(analysis.obligations)} obligations extracted.")
                else:
                    preview_lines.append("Obligations not yet extracted.")
                preview_lines.append("")

            risks_result = None
            for key, r in cached.items():
                if isinstance(key, (list, tuple)) and doc_id in key and hasattr(r, "risks") and r.risks:
                    risks_result = r
                    break

            if section_states.get("Risk findings with evidence"):
                preview_lines.append("<b>Risk findings</b>")
                if risks_result and risks_result.risks:
                    for r in risks_result.risks:
                        preview_lines.append(f"• [{r.severity.upper()}] {r.clause or 'Clause'} — {r.explanation[:60]}…")
                else:
                    preview_lines.append("No risks found or not yet analyzed.")
                preview_lines.append("")

        preview_html = "<br>".join(preview_lines) if preview_lines else "<i style='color:var(--mut);'>Select sections to preview.</i>"
        st.markdown(
            f'<div class="lm-paper">'
            f'<h3>LegalMind AI – Contract Analysis</h3>'
            f'<span style="color:#777;">{selected[0] if selected else "—"}</span>'
            f'<hr>'
            f'{preview_html}'
            f'<hr><span style="color:#999;font-size:11px;">Generated by AI from the uploaded document. Not legal advice.</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Generate ──────────────────────────────────────────────────────────────
    if generate_btn:
        with st.spinner("Running agents and building the report…"):
            result = run_workflow("report", selected, question or None)
        show_messages(result)
        agents_caption(result)

        if result.report_path and Path(result.report_path).exists():
            st.session_state["last_report"] = {
                "name": Path(result.report_path).name,
                "bytes": Path(result.report_path).read_bytes(),
            }
        else:
            st.session_state["last_report"] = None

    report = st.session_state.get("last_report")
    if report:
        st.markdown(
            '<div class="lm-card" style="border-left:4px solid var(--lo);">'
            '<div class="lm-row">'
            '<div><b>✓ Report ready</b><br>'
            f'<span style="color:var(--mut);font-size:13px;">{report["name"]}</span>'
            '</div></div></div>',
            unsafe_allow_html=True,
        )
        st.download_button(
            "⬇  Download PDF",
            data=report["bytes"],
            file_name=report["name"],
            mime="application/pdf",
            use_container_width=True,
        )
