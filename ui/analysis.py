"""Analysis / Risks page — matches the prototype's Risks view with severity filter tabs + evidence cards."""
from __future__ import annotations

import streamlit as st

from orchestration.workflow import get_runtime, run_workflow
from ui.components import agents_caption, document_selector, render_analysis, render_risks, show_messages


def render() -> None:
    rt = get_runtime()
    st.markdown("<h1>Clauses worth a closer look</h1>", unsafe_allow_html=True)
    st.markdown(
        '<p class="lm-sub">Every flag shows its evidence. These are prompts for discussion with a lawyer, '
        'not legal advice.</p>',
        unsafe_allow_html=True,
    )

    doc_id = document_selector(rt.registry, key="risks_doc")
    if not doc_id:
        return
    st.session_state["active_document_id"] = doc_id

    with st.spinner("Running document and risk analysis…"):
        result = run_workflow("risk", [doc_id])
    show_messages(result)

    if result.analysis:
        with st.expander("📋 Document analysis summary", expanded=False):
            render_analysis(result.analysis)

    risks = result.risks or []

    if not risks:
        st.markdown(
            '<div class="lm-card" style="text-align:center;padding:32px;">'
            '<div style="font-size:32px;">✅</div>'
            '<p style="font-weight:700;margin:4px 0;">No clauses flagged for review</p>'
            '<p class="lm-sub">The document passed all risk checks.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
        agents_caption(result)
        return

    # ── Filter tabs ───────────────────────────────────────────────────────────
    high_risks = [r for r in risks if r.severity == "high"]
    med_risks = [r for r in risks if r.severity == "medium"]
    low_risks = [r for r in risks if r.severity == "low"]

    tab_all, tab_high, tab_med, tab_low = st.tabs([
        f"All  {len(risks)}",
        f"🔴 High  {len(high_risks)}",
        f"🟠 Medium  {len(med_risks)}",
        f"🟢 Low  {len(low_risks)}",
    ])

    def _render_risk_cards(risk_list):
        if not risk_list:
            st.markdown(
                '<p style="color:var(--mut);text-align:center;padding:20px;">No risks in this category.</p>',
                unsafe_allow_html=True,
            )
            return
        for r in risk_list:
            sev = r.severity.lower()
            sev_class = f"lm-risk-{sev}"
            sev_badge = (
                f'<span class="lm-sev lm-sev-{sev}">{sev.upper()}</span>'
            )
            clause_label = f"Clause {r.clause}" if r.clause else "Flagged clause"
            page_label = f" · p.{r.page}" if r.page else ""
            explanation = r.explanation or ""

            # Evidence
            ev_text = ""
            if hasattr(r, "evidence_text") and r.evidence_text:
                ev_text = r.evidence_text
            elif r.evidence:
                ev_text = str(r.evidence)

            ev_html = ""
            if ev_text:
                verified_note = ""
                if r.verified is False:
                    verified_note = '<div style="color:var(--me);font-size:12px;margin-top:4px;">⚠ Evidence could not be verified in document text.</div>'
                ev_html = (
                    f'<div class="lm-ev"><b>{clause_label}{page_label}</b>'
                    f'<br>{ev_text}{verified_note}</div>'
                )

            lawyer_q = ""
            if r.lawyer_question:
                lawyer_q = (
                    f'<p style="font-size:12px;color:var(--mut);margin:8px 0 0;">'
                    f'💡 Ask a lawyer: {r.lawyer_question}</p>'
                )

            st.markdown(
                f'<div class="lm-card lm-risk {sev_class}">'
                f'<div class="lm-row"><b>{r.clause or "Risk"}</b>{sev_badge}</div>'
                f'<p style="margin:6px 0;">{explanation}</p>'
                f'{ev_html}'
                f'{lawyer_q}'
                f'</div>',
                unsafe_allow_html=True,
            )

    with tab_all:
        _render_risk_cards(risks)
    with tab_high:
        _render_risk_cards(high_risks)
    with tab_med:
        _render_risk_cards(med_risks)
    with tab_low:
        _render_risk_cards(low_risks)

    st.markdown(
        '<p style="font-size:12px;color:var(--mut);">Flags are AI-assisted pointers for review, not legal advice.</p>',
        unsafe_allow_html=True,
    )
    agents_caption(result)
