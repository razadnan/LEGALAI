"""LegalMind AI — Streamlit entry point.  Run with:  streamlit run app.py"""
import streamlit as st

from core.state import init_session
from orchestration.workflow import get_runtime
from ui import analysis, chatbot, comparison, dashboard, reports, upload
from ui.theme import inject_theme

st.set_page_config(
    page_title="LegalMind AI",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Navigation pages ──────────────────────────────────────────────────────────
PAGES = {
    "upload":   ("⬆", "Upload",    upload.render),
    "overview": ("▦", "Overview",  dashboard.render),
    "chat":     ("💬", "Ask AI",    chatbot.render),
    "risks":    ("⚠", "Risks",     analysis.render),
    "compare":  ("⇄", "Compare",   comparison.render),
    "report":   ("⬇", "Report",    reports.render),
}


@st.cache_resource(show_spinner="Starting LegalMind AI…")
def _boot():
    return get_runtime()


def _has_docs() -> bool:
    try:
        return bool(get_runtime().registry.list_ids())
    except Exception:
        return False


def main() -> None:
    inject_theme()
    _boot()
    init_session(st.session_state)

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        # Logo
        st.markdown(
            '<div class="lm-logo">'
            'LegalMind AI'
            '</div>',
            unsafe_allow_html=True,
        )

        # Current page from session (default = upload)
        if "page" not in st.session_state:
            st.session_state["page"] = "upload"

        docs_ready = _has_docs()

        for key, (icon, label, _) in PAGES.items():
            locked = key != "upload" and not docs_ready
            is_active = st.session_state["page"] == key

            # Style for active / locked / normal
            if locked:
                st.markdown(
                    f'<div style="display:flex;gap:10px;align-items:center;padding:10px 12px;'
                    f'border-radius:10px;color:#ccc;font-size:14px;cursor:not-allowed;">'
                    f'{icon} {label}</div>',
                    unsafe_allow_html=True,
                )
            else:
                active_style = (
                    "background:var(--brandsoft);color:var(--brand);font-weight:600;"
                    if is_active
                    else "color:var(--mut);"
                )
                # Use a real button so it's clickable
                btn_html = (
                    f'<button onclick="" style="display:flex;gap:10px;align-items:center;'
                    f'padding:10px 12px;border:0;background:{"var(--brandsoft)" if is_active else "none"};'
                    f'border-radius:10px;text-align:left;width:100%;{active_style}'
                    f'font-size:14px;cursor:pointer;">{icon} {label}</button>'
                )
                if st.button(
                    f"{icon}  {label}",
                    key=f"nav_{key}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    st.session_state["page"] = key
                    st.rerun()

        st.markdown('<div style="flex:1;min-height:40px;"></div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="lm-disclaimer">AI-assisted analysis.<br>Not legal advice.<br>'
            'Use anonymised contracts for demos.</div>',
            unsafe_allow_html=True,
        )

    # ── Main area ─────────────────────────────────────────────────────────────
    page_key = st.session_state.get("page", "upload")
    if page_key not in PAGES:
        page_key = "upload"

    _icon, _label, render_fn = PAGES[page_key]
    try:
        render_fn()
    except Exception as exc:
        st.error(
            "Something unexpected went wrong. Please retry; if it persists, restart the app."
        )
        st.caption(f"Technical detail: {type(exc).__name__}: {exc}")


main()
