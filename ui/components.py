"""Reusable Streamlit components — styled to match the LegalMind AI HTML prototype."""
from __future__ import annotations

import streamlit as st

from core.schemas import AnswerResult, ComparisonResult, DocumentAnalysis, RiskFinding, WorkflowResult

SEVERITY_ICON = {"high": "🔴", "medium": "🟠", "low": "🟢"}
CHANGE_ICON = {"added": "🟢 Added", "removed": "🔴 Removed", "modified": "🟡 Modified"}


# ── Utility ───────────────────────────────────────────────────────────────────

def show_messages(result: WorkflowResult) -> None:
    for e in result.errors:
        st.error(e)
    for w in result.warnings:
        st.warning(w)


def document_selector(registry, label: str = "Document", key: str = "doc_sel", exclude: str | None = None):
    ids = [i for i in registry.list_ids() if i != exclude]
    if not ids:
        st.markdown(
            '<div class="lm-card" style="text-align:center;padding:24px;">'
            '<p style="color:var(--mut);">No documents yet. Go to <b>Upload</b> first.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
        return None
    names = {i: f"{i} — {registry.get(i).filename}" for i in ids}
    active = st.session_state.get("active_document_id")
    index = ids.index(active) if active in ids else 0
    choice = st.selectbox(label, ids, index=index, format_func=names.get, key=key,
                          label_visibility="collapsed" if label == "Document" else "visible")
    return choice


# ── Sources / Answer ──────────────────────────────────────────────────────────

def render_sources(answer: AnswerResult) -> None:
    if not answer.sources:
        return
    st.markdown('<p style="color:var(--mut);font-size:12px;margin:4px 0;">Supporting evidence</p>', unsafe_allow_html=True)
    for s in answer.sources:
        ref_parts = []
        if s.page:
            ref_parts.append(f"Page {s.page}")
        if s.clause:
            ref_parts.append(f"Clause {s.clause}")
        ref = " · ".join(ref_parts) or "Source"
        verified_note = ""
        if s.verified is True:
            verified_note = " ✅"
        elif s.verified is False:
            verified_note = " ⚠️ unverified"

        with st.expander(f"{ref}{verified_note}"):
            st.markdown(
                f'<div class="lm-ev">{s.text}</div>',
                unsafe_allow_html=True,
            )


# ── Risk findings ─────────────────────────────────────────────────────────────

def render_risks(risks: list[RiskFinding]) -> None:
    if not risks:
        st.markdown(
            '<div class="lm-card" style="text-align:center;padding:24px;">'
            '<p style="color:var(--lo);">✅ No clauses flagged for additional review.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    for r in risks:
        sev = r.severity.lower()
        sev_badge = f'<span class="lm-sev lm-sev-{sev}">{sev.upper()}</span>'
        clause_no = str(r.clause or "").replace("Clause", "").strip()
        has_valid_clause = bool(clause_no and clause_no != r.title and len(clause_no) <= 10)
        clause_prefix = f"Clause {clause_no}: " if has_valid_clause else ""
        title_text = r.title or r.clause or "Risk"
        clause_label = f"Clause {clause_no}" if has_valid_clause else "Flagged clause"
        page_label = f" · p.{r.page}" if r.page else ""
        explanation = r.explanation or ""

        ev_text = ""
        if hasattr(r, "evidence_text") and r.evidence_text:
            ev_text = r.evidence_text
        elif r.evidence:
            ev_text = str(r.evidence)

        ev_html = ""
        if ev_text:
            verified_note = ""
            if r.verified is False:
                verified_note = '<div style="color:var(--me);font-size:12px;margin-top:4px;">⚠ Evidence could not be verified.</div>'
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
            f'<div class="lm-card lm-risk lm-risk-{sev}">'
            f'<div class="lm-row"><b>{clause_prefix}{title_text}</b>{sev_badge}</div>'
            f'<p style="margin:6px 0;">{explanation}</p>'
            f'{ev_html}'
            f'{lawyer_q}'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<p style="font-size:12px;color:var(--mut);">Flags are AI-assisted pointers for review, not legal advice.</p>',
        unsafe_allow_html=True,
    )


# ── Document analysis ─────────────────────────────────────────────────────────

def render_analysis(a: DocumentAnalysis) -> None:
    # Metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Document type", a.document_type or "—")
    c2.metric("Parties", len(a.parties) if a.parties else 0)
    c3.metric("Key dates", len(a.important_dates) if a.important_dates else 0)
    c4.metric("Obligations", len(a.obligations) if a.obligations else 0)

    if a.summary:
        st.markdown(
            f'<div class="lm-card"><p style="margin:0;line-height:1.6;">{a.summary}</p></div>',
            unsafe_allow_html=True,
        )

    tab1, tab2, tab3 = st.tabs(["Parties & dates", "Obligations", "Risk flags"])

    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Parties**")
            if a.parties:
                for p in a.parties:
                    # parties is list[str] after schema coercion; items may be "Name (Role)"
                    p_str = str(p)
                    import re as _re
                    m = _re.match(r"^(.+?)\s+\((.+?)\)\s*$", p_str)
                    if m:
                        name_part, role_part = m.group(1).strip(), m.group(2).strip()
                        st.markdown(f"- **{role_part}:** {name_part}")
                    else:
                        st.markdown(f"- {p_str}")
            else:
                st.markdown("- Not identified")
        with col2:
            st.markdown("**Key dates**")
            if a.important_dates:
                for d in a.important_dates:
                    page = f" *(p.{d.page})*" if getattr(d, "page", None) else ""
                    st.markdown(f"- **{d.label}:** {d.date}{page}")
            else:
                st.caption("No dates found.")

    with tab2:
        if a.obligations:
            st.dataframe(
                [{"Party": o.party or "—", "Obligation": o.description, "Page": o.page}
                 for o in a.obligations],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("No obligations found.")

    with tab3:
        render_risks(a.risk_findings)


# ── Comparison ────────────────────────────────────────────────────────────────

def render_comparison(c: ComparisonResult) -> None:
    if c.summary:
        st.markdown(
            f'<div class="lm-card"><p style="margin:0;">{c.summary}</p></div>',
            unsafe_allow_html=True,
        )

    if not c.changes:
        st.success("No differences found.")
        return

    for ch in c.changes:
        change_label = CHANGE_ICON.get(ch.change_type, ch.change_type.title())
        section = ch.section or "Section"
        old_page = f" · p.{ch.old_page}" if getattr(ch, "old_page", None) else ""
        new_page = f" · p.{ch.new_page}" if getattr(ch, "new_page", None) else ""
        old_text = ch.old_text or "— not present —"
        new_text = ch.new_text or "— not present —"

        if ch.change_type == "removed":
            old_display = f"<del>{old_text}</del>"
            new_display = new_text
        elif ch.change_type == "added":
            old_display = old_text
            new_display = f"<ins>{new_text}</ins>"
        else:
            old_display = old_text
            new_display = new_text

        st.markdown(
            f'<div class="lm-card">'
            f'<div class="lm-row"><b>{section} <span style="color:var(--mut);font-weight:400;">· {change_label}</span></b></div>'
            f'<div class="lm-cmp">'
            f'<div class="lm-pane"><h4>Original{old_page}</h4>{old_display}</div>'
            f'<div class="lm-pane"><h4>Revised{new_page}</h4>{new_display}</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )


# ── Agents caption ────────────────────────────────────────────────────────────

def agents_caption(result: WorkflowResult) -> None:
    if result.agents_invoked:
        agent_chain = " → ".join(a.replace("_", " ") for a in result.agents_invoked)
        st.markdown(
            f'<p style="font-size:11px;color:var(--mut);margin-top:8px;">Routed to: {agent_chain}</p>',
            unsafe_allow_html=True,
        )
