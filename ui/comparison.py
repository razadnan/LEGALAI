"""Comparison page — matches the prototype's Compare view with two-pane diff + change type tabs."""
from __future__ import annotations

import streamlit as st

from orchestration.workflow import get_runtime, run_workflow
from ui.components import agents_caption, document_selector, show_messages
from ui.upload import process_and_analyze


def render() -> None:
    rt = get_runtime()
    st.markdown("<h1>Compare two versions</h1>", unsafe_allow_html=True)
    st.markdown(
        '<p class="lm-sub">Upload the revised agreement to see what changed, clause by clause.</p>',
        unsafe_allow_html=True,
    )

    ids = rt.registry.list_ids()

    # ── Upload revised version ────────────────────────────────────────────────
    with st.expander("⬆  Upload the revised version"):
        revised_up = st.file_uploader(
            "Revised contract (PDF or DOCX)",
            type=["pdf", "docx"],
            key="revised_upl",
        )
        if revised_up and st.button("Process revised version", key="proc_revised"):
            doc = process_and_analyze(revised_up, analyze=False)
            if doc:
                st.session_state["revised_id"] = doc.document_id
                st.success(f"Stored as {doc.document_id}.")
                st.rerun()

    if not ids:
        st.markdown(
            '<div class="lm-card" style="text-align:center;padding:32px;">'
            '<div style="font-size:32px;">📄</div>'
            '<p style="font-weight:700;">No documents uploaded yet.</p>'
            '<p class="lm-sub">Go to <b>Upload</b> first.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    # ── Document selectors ────────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            '<div class="lm-card"><h2>Original</h2>',
            unsafe_allow_html=True,
        )
        original = document_selector(rt.registry, "Original version", key="cmp_a")
        if original:
            doc_a = rt.registry.get(original)
            st.markdown(
                f'<span class="lm-chip">✓ {doc_a.filename} · {doc_a.page_count}p</span>',
                unsafe_allow_html=True,
            )
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown(
            '<div class="lm-card"><h2>Revised version</h2>',
            unsafe_allow_html=True,
        )
        others = [i for i in ids if i != original] if original else ids
        if not others:
            st.markdown(
                '<p class="lm-sub">Upload a second document to compare.</p>',
                unsafe_allow_html=True,
            )
            revised_id = None
        else:
            default = st.session_state.get("revised_id")
            revised_id = st.selectbox(
                "Revised version",
                others,
                key="cmp_b",
                index=others.index(default) if default in others else 0,
                format_func=lambda i: f"{i} — {rt.registry.get(i).filename}",
                label_visibility="collapsed",
            )
            if revised_id:
                doc_b = rt.registry.get(revised_id)
                st.markdown(
                    f'<span class="lm-chip">📄 {doc_b.filename} · {doc_b.page_count}p</span>',
                    unsafe_allow_html=True,
                )
        st.markdown('</div>', unsafe_allow_html=True)

    if not original or not revised_id:
        return

    if st.button("⇄  Compare", type="primary"):
        with st.spinner("Comparing clause by clause…"):
            result = run_workflow("compare", [original, revised_id])
        st.session_state["results"][("compare", original, revised_id)] = result

    result = st.session_state["results"].get(("compare", original, revised_id))
    if not result:
        return

    show_messages(result)

    comparison = result.comparison
    if not comparison:
        st.info("No comparison result available.")
        agents_caption(result)
        return

    # ── Comparison header ─────────────────────────────────────────────────────
    doc_a_name = rt.registry.get(original).filename
    doc_b_name = rt.registry.get(revised_id).filename
    st.markdown(
        f'<div class="lm-card"><h2 style="margin:0;">What changed</h2>'
        f'<p class="lm-sub">{doc_a_name} → {doc_b_name}</p>'
        f'<p style="margin:0;">{comparison.summary}</p></div>',
        unsafe_allow_html=True,
    )

    changes = comparison.changes or []
    if not changes:
        st.success("No differences found between the documents.")
        agents_caption(result)
        return

    # ── Filter tabs ───────────────────────────────────────────────────────────
    modified = [c for c in changes if c.change_type == "modified"]
    added = [c for c in changes if c.change_type == "added"]
    removed = [c for c in changes if c.change_type == "removed"]

    tab_all, tab_mod, tab_add, tab_rem = st.tabs([
        f"All  {len(changes)}",
        f"🟡 Modified  {len(modified)}",
        f"🟢 Added  {len(added)}",
        f"🔴 Removed  {len(removed)}",
    ])

    CHANGE_ICON = {"added": "🟢 Added", "removed": "🔴 Removed", "modified": "🟡 Modified"}
    SEV_CLASS = {"high": "lm-sev-high", "medium": "lm-sev-medium", "low": "lm-sev-low"}

    def _render_changes(change_list):
        if not change_list:
            st.markdown(
                '<p style="color:var(--mut);text-align:center;padding:20px;">No changes in this category.</p>',
                unsafe_allow_html=True,
            )
            return
        for c in change_list:
            sev = getattr(c, "severity", "medium") or "medium"
            sev_badge = f'<span class="lm-sev {SEV_CLASS.get(sev, "")}">{sev.upper()}</span>'
            change_label = CHANGE_ICON.get(c.change_type, c.change_type.title())
            section = c.section or "Section"

            old_page = f" · p.{c.old_page}" if getattr(c, "old_page", None) else ""
            new_page = f" · p.{c.new_page}" if getattr(c, "new_page", None) else ""

            old_text = c.old_text or "— not present —"
            new_text = c.new_text or "— not present —"

            # Wrap removed text in <del> and added in <ins> for the HTML diff panes
            if c.change_type == "removed":
                old_display = f"<del>{old_text}</del>"
                new_display = new_text
            elif c.change_type == "added":
                old_display = old_text
                new_display = f"<ins>{new_text}</ins>"
            else:
                old_display = old_text
                new_display = new_text

            st.markdown(
                f'<div class="lm-card">'
                f'<div class="lm-row"><b>{section} <span style="color:var(--mut);font-weight:400;">· {change_label}</span></b>{sev_badge}</div>'
                f'<div class="lm-cmp">'
                f'<div class="lm-pane"><h4>Original{old_page}</h4>{old_display}</div>'
                f'<div class="lm-pane"><h4>Revised{new_page}</h4>{new_display}</div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )

    with tab_all:
        _render_changes(changes)
    with tab_mod:
        _render_changes(modified)
    with tab_add:
        _render_changes(added)
    with tab_rem:
        _render_changes(removed)

    agents_caption(result)
