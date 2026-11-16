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
        visible = []
        for r in risk_list:
            ev_text = ""
            if hasattr(r, "evidence_text") and r.evidence_text:
                ev_text = r.evidence_text
            elif r.evidence:
                ev_text = str(r.evidence)
            # Task 3 rule: If a risk has no quote, hide it. Do not show a warning state.
            if ev_text and len(ev_text.strip()) >= 5:
                visible.append((r, ev_text))

        if not visible:
            st.markdown(
                '<p style="color:var(--mut);text-align:center;padding:20px;">No risks with supporting evidence in this category.</p>',
                unsafe_allow_html=True,
            )
            return

        for r, ev_text in visible:
            sev = r.severity.lower()
            sev_class = f"lm-risk-{sev}"
            sev_badge = f'<span class="lm-sev lm-sev-{sev}">{sev.upper()}</span>'
            clause_no = str(r.clause or "").replace("Clause", "").strip()
            has_valid_clause = bool(clause_no and clause_no != r.title and len(clause_no) <= 10)
            clause_prefix = f"Clause {clause_no}: " if has_valid_clause else ""
            title_text = r.title or r.clause or "Risk"
            clause_label = f"Clause {clause_no}" if has_valid_clause else "Flagged clause"
            page_label = f" · p.{r.page}" if r.page else ""
            explanation = r.explanation or ""

            # Affected party
            affected_party = "Client" if sev == "high" else ("Both" if sev == "medium" else "Employer")
            exp_l = explanation.lower()
            if "employee" in exp_l or "worker" in exp_l:
                affected_party = "Employee"
            elif "client" in exp_l or "customer" in exp_l:
                affected_party = "Client"

            ev_html = (
                f'<div class="lm-ev"><b>{clause_label}{page_label}</b>'
                f'<br>"{ev_text}"</div>'
            )

            lawyer_q = ""
            if r.lawyer_question:
                lawyer_q = (
                    f'<p style="font-size:12px;color:var(--mut);margin:8px 0 0;">'
                    f'💡 <b>Recommended action:</b> {r.lawyer_question}</p>'
                )

            st.markdown(
                f'<div class="lm-card lm-risk {sev_class}">'
                f'<div class="lm-row"><b>{clause_prefix}{title_text}</b>{sev_badge}</div>'
                f'<p style="font-size:12px;color:var(--mut);margin:2px 0 6px 0;">Affected party: <b>{affected_party}</b> · Severity: <b>{sev.upper()}</b></p>'
                f'<p style="margin:6px 0;"><b>Business impact:</b> {explanation}</p>'
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

    # ── Missing-Clause Checklist (Task 3 & 5) ─────────────────────────────────
    if result.playbook:
        pb = result.playbook
        st.markdown("<hr style='border:0;border-top:1px solid var(--line);margin:24px 0;'>", unsafe_allow_html=True)
        st.markdown(f"<h2>Missing-Clause Checklist ({pb.playbook} Playbook)</h2>", unsafe_allow_html=True)
        st.markdown(
            f'<p class="lm-sub">Audited against standard {pb.playbook} provisions: '
            f'<b style="color:var(--lo);">{pb.present_count} Present</b>, '
            f'<b style="color:var(--me);">{pb.partial_count} Partial</b>, '
            f'<b style="color:var(--hi);">{pb.absent_count} Absent</b></p>',
            unsafe_allow_html=True,
        )

        absent_findings = [f for f in pb.findings if f.status == "absent"]
        partial_findings = [f for f in pb.findings if f.status == "partial"]
        present_findings = [f for f in pb.findings if f.status == "present"]

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("<b>Omitted / Missing Safeguards:</b>", unsafe_allow_html=True)
            for f in absent_findings:
                st.markdown(f'<div class="lm-card" style="border-left:4px solid var(--hi);padding:10px 14px;margin-bottom:8px;">'
                            f'<div class="lm-row"><b>{f.provision}</b><span class="lm-sev lm-sev-high">ABSENT</span></div>'
                            f'<p style="font-size:12px;color:var(--mut);margin:4px 0 0;">Provision is not found in the uploaded contract.</p>'
                            f'</div>', unsafe_allow_html=True)

        with col2:
            st.markdown("<b>Partial or Present Safeguards:</b>", unsafe_allow_html=True)
            for f in partial_findings:
                st.markdown(f'<div class="lm-card" style="border-left:4px solid var(--me);padding:10px 14px;margin-bottom:8px;">'
                            f'<div class="lm-row"><b>{f.provision}</b><span class="lm-sev lm-sev-medium">PARTIAL</span></div>'
                            f'<p style="font-size:12px;color:var(--mut);margin:4px 0 0;">{f.note or "Partially addressed."}</p>'
                            f'</div>', unsafe_allow_html=True)
            for f in present_findings[:4]:
                st.markdown(f'<div class="lm-card" style="border-left:4px solid var(--lo);padding:10px 14px;margin-bottom:8px;">'
                            f'<div class="lm-row"><b>{f.provision}</b><span class="lm-sev lm-sev-low">PRESENT</span></div>'
                            f'<p style="font-size:12px;color:var(--mut);margin:4px 0 0;">Addressed in contract.</p>'
                            f'</div>', unsafe_allow_html=True)

    st.markdown(
        '<p style="font-size:12px;color:var(--mut);">Flags are AI-assisted pointers for review, not legal advice.</p>',
        unsafe_allow_html=True,
    )
    agents_caption(result)
