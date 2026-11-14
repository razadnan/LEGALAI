"""Dashboard / Overview page — matches the prototype's Overview view."""
from __future__ import annotations

import streamlit as st

from orchestration.workflow import get_runtime, run_workflow
from ui.components import document_selector, render_analysis, render_risks, show_messages


def render() -> None:
    rt = get_runtime()

    # ── If no docs, redirect hint ─────────────────────────────────────────────
    ids = rt.registry.list_ids()
    if not ids:
        st.markdown("<h1>Overview</h1>", unsafe_allow_html=True)
        st.markdown(
            '<div class="lm-card" style="text-align:center;padding:40px 16px;">'
            '<div style="font-size:40px;">📄</div>'
            '<p style="font-weight:700;">No documents uploaded yet.</p>'
            '<p class="lm-sub">Go to <b>Upload</b> to get started.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
        if st.button("⬆  Upload a document", type="primary"):
            st.session_state["page"] = "upload"
            st.rerun()
        return

    doc_id = document_selector(rt.registry, key="overview_doc")
    if not doc_id:
        return
    st.session_state["active_document_id"] = doc_id
    doc = rt.registry.get(doc_id)

    # ── Page header ───────────────────────────────────────────────────────────
    with st.spinner("Loading analysis…"):
        result = run_workflow("risk", [doc_id])
    show_messages(result)

    analysis = result.analysis
    doc_type = analysis.document_type if analysis else "Legal Document"
    n_pages = doc.page_count

    # Header row with doc type + quick action
    col_title, col_btn = st.columns([4, 1])
    with col_title:
        st.markdown(f"<h1>{doc_type}</h1>", unsafe_allow_html=True)
        st.markdown(
            f'<p class="lm-sub">{doc.filename} · {n_pages} page(s) · analysed just now</p>',
            unsafe_allow_html=True,
        )
    with col_btn:
        if st.button("Ask a question →", type="primary"):
            st.session_state["page"] = "chat"
            st.rerun()

    # ── Metrics grid ──────────────────────────────────────────────────────────
    if analysis:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Document type", analysis.document_type or "—")
        c2.metric("Parties", len(analysis.parties) if analysis.parties else 0)
        c3.metric("Key dates", len(analysis.important_dates) if analysis.important_dates else 0)
        c4.metric("Obligations", len(analysis.obligations) if analysis.obligations else 0)

        # ── Summary ───────────────────────────────────────────────────────────
        if analysis.summary:
            st.markdown(
                f'<div class="lm-card">'
                f'<h2>Summary</h2>'
                f'<p style="margin:0;line-height:1.6;">{analysis.summary}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # ── Info grid: Parties | Key dates | Obligations ──────────────────────
        col1, col2 = st.columns(2)

        with col1:
            # Parties card
            parties_html = ""
            if analysis.parties:
                for p in analysis.parties:
                    if hasattr(p, "name"):
                        role = getattr(p, "role", "")
                        parties_html += f"<dt>{role or 'Party'}</dt><dd>{p.name}</dd>"
                    else:
                        parties_html += f"<dt>Party</dt><dd>{p}</dd>"
            else:
                parties_html = "<dt>Parties</dt><dd>Not identified</dd>"

            st.markdown(
                f'<div class="lm-card"><h2>Parties</h2>'
                f'<dl class="lm-kv">{parties_html}</dl></div>',
                unsafe_allow_html=True,
            )

        with col2:
            # Key dates card
            dates_html = ""
            if analysis.important_dates:
                for d in analysis.important_dates:
                    page_note = f'<span style="color:var(--mut);font-size:12px;">p.{d.page}</span>' if getattr(d, "page", None) else ""
                    dates_html += f"<dt>{d.label}</dt><dd>{d.date} {page_note}</dd>"
            else:
                dates_html = "<dt>Dates</dt><dd>None identified</dd>"

            st.markdown(
                f'<div class="lm-card"><h2>Key dates &amp; terms</h2>'
                f'<dl class="lm-kv">{dates_html}</dl></div>',
                unsafe_allow_html=True,
            )

        # ── Obligations card ──────────────────────────────────────────────────
        if analysis.obligations:
            obl_items = ""
            for o in analysis.obligations:
                party = f"<b>{o.party}</b>: " if getattr(o, "party", None) else ""
                desc = getattr(o, "description", str(o))
                page = f' <span style="color:var(--mut);font-size:12px;">(p.{o.page})</span>' if getattr(o, "page", None) else ""
                obl_items += f"<li style='margin-bottom:4px;'>{party}{desc}{page}</li>"

            st.markdown(
                f'<div class="lm-card"><h2>Obligations</h2>'
                f'<ul style="margin:0;padding-left:18px;">{obl_items}</ul></div>',
                unsafe_allow_html=True,
            )

        # ── Risk snapshot card ────────────────────────────────────────────────
        risks = result.risks or []
        high_n = sum(1 for r in risks if r.severity == "high")
        med_n = sum(1 for r in risks if r.severity == "medium")
        low_n = sum(1 for r in risks if r.severity == "low")

        st.markdown(
            f'<div class="lm-card"><div class="lm-row">'
            f'<div><h2 style="margin:0;">Risk snapshot</h2>'
            f'<span style="color:var(--mut);font-size:13px;">{len(risks)} clauses flagged for review</span></div>'
            f'<div>'
            f'<span class="lm-chip"><span class="lm-sev lm-sev-high">HIGH</span> {high_n}</span>'
            f'<span class="lm-chip"><span class="lm-sev lm-sev-medium">MEDIUM</span> {med_n}</span>'
            f'<span class="lm-chip"><span class="lm-sev lm-sev-low">LOW</span> {low_n}</span>'
            f'</div></div></div>',
            unsafe_allow_html=True,
        )

        col_r, col_c = st.columns(2)
        with col_r:
            if st.button("⚠  View full risk analysis", use_container_width=True):
                st.session_state["page"] = "risks"
                st.rerun()
        with col_c:
            if st.button("⇄  Compare versions", use_container_width=True):
                st.session_state["page"] = "compare"
                st.rerun()

    else:
        st.info("Analysis not yet available. Upload and process a document first.")

    # ── Module status (collapsed) ─────────────────────────────────────────────
    with st.expander("Module status"):
        for name, status in rt.services.status.items():
            st.write(f"`{name}` → {status}")
