"""Global CSS theme matching the LegalMind AI HTML prototype design."""

THEME_CSS = """
<style>
/* ── Reset / root ───────────────────────────────────────────────── */
:root {
    --bg: #f6f7fb;
    --card: #ffffff;
    --ink: #1b2033;
    --mut: #667080;
    --line: #e3e6f0;
    --brand: #4c3fd6;
    --brandsoft: #ecebfd;
    --hi: #d92d3a;
    --hisoft: #fdeaec;
    --me: #c77700;
    --mesoft: #fff3dc;
    --lo: #1f8a4c;
    --losoft: #e4f6ec;
}

/* Hide default Streamlit chrome */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { visibility: hidden; }
.stDeployButton { display: none; }
div[data-testid="stDecoration"] { display: none; }

/* ── App shell ───────────────────────────────────────────────────── */
.stApp {
    background: var(--bg) !important;
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    color: var(--ink);
}

/* ── Sidebar ─────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: var(--card) !important;
    border-right: 1px solid var(--line) !important;
    min-width: 230px !important;
    max-width: 230px !important;
}
[data-testid="stSidebar"] > div:first-child {
    padding: 18px 12px !important;
    display: flex;
    flex-direction: column;
    gap: 4px;
}

/* Sidebar logo */
.lm-logo {
    font-weight: 700;
    font-size: 18px;
    padding: 4px 10px 14px;
    display: flex;
    gap: 8px;
    align-items: center;
    color: var(--ink);
}
.lm-logo-icon {
    background: var(--brand);
    color: #fff;
    width: 28px;
    height: 28px;
    border-radius: 8px;
    display: grid;
    place-items: center;
    font-size: 15px;
}

/* Sidebar nav buttons */
[data-testid="stSidebar"] .stButton > button {
    display: flex !important;
    gap: 10px !important;
    align-items: center !important;
    padding: 10px 12px !important;
    border: 0 !important;
    background: none !important;
    border-radius: 10px !important;
    text-align: left !important;
    width: 100% !important;
    color: var(--mut) !important;
    font-size: 14px !important;
    font-weight: 400 !important;
    justify-content: flex-start !important;
    box-shadow: none !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: var(--bg) !important;
}
[data-testid="stSidebar"] .stRadio label {
    padding: 10px 12px;
    border-radius: 10px;
    cursor: pointer;
    color: var(--mut);
    font-size: 14px;
    display: block;
    width: 100%;
}
[data-testid="stSidebar"] .stRadio label:hover {
    background: var(--bg);
}

/* ── Main content ────────────────────────────────────────────────── */
.main .block-container {
    padding: 24px clamp(14px, 3vw, 36px) !important;
    max-width: 1100px !important;
}

/* ── Typography ──────────────────────────────────────────────────── */
h1 { font-size: 24px !important; margin: 0 0 4px !important; color: var(--ink) !important; }
h2 { font-size: 17px !important; margin: 0 0 10px !important; color: var(--ink) !important; }
.lm-sub { color: var(--mut); margin: 0 0 18px; font-size: 14px; }

/* ── Cards ───────────────────────────────────────────────────────── */
.lm-card {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 16px;
    margin-bottom: 14px;
}
.lm-grid {
    display: grid;
    gap: 14px;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
}

/* ── Buttons ─────────────────────────────────────────────────────── */
.stButton > button[kind="primary"],
div[data-testid="stFormSubmitButton"] > button {
    background: var(--brand) !important;
    color: #fff !important;
    border: 0 !important;
    border-radius: 10px !important;
    padding: 10px 16px !important;
    font-weight: 600 !important;
    box-shadow: none !important;
}
.stButton > button[kind="secondary"] {
    background: var(--card) !important;
    color: var(--ink) !important;
    border: 1px solid var(--line) !important;
    border-radius: 10px !important;
    padding: 10px 16px !important;
    font-weight: 400 !important;
    box-shadow: none !important;
}
.stButton > button:hover { opacity: 0.9 !important; }
.stButton > button:disabled { opacity: 0.5 !important; cursor: not-allowed !important; }

/* ── Chips ───────────────────────────────────────────────────────── */
.lm-chip {
    display: inline-flex;
    gap: 6px;
    align-items: center;
    padding: 4px 10px;
    border-radius: 99px;
    font-size: 12px;
    border: 1px solid var(--line);
    background: var(--card);
    margin: 2px 4px 2px 0;
    cursor: pointer;
}
.lm-chip:hover { border-color: var(--brand); color: var(--brand); }

/* ── Severity badges ─────────────────────────────────────────────── */
.lm-sev {
    font-size: 11px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 99px;
    text-transform: uppercase;
}
.lm-sev-high { background: var(--hisoft); color: var(--hi); }
.lm-sev-medium { background: var(--mesoft); color: var(--me); }
.lm-sev-low { background: var(--losoft); color: var(--lo); }

/* ── Upload drop zone ────────────────────────────────────────────── */
.lm-drop {
    border: 2px dashed var(--line);
    border-radius: 16px;
    padding: 40px 16px;
    text-align: center;
    background: var(--card);
    transition: .15s;
    margin-bottom: 14px;
}
.lm-drop:hover { border-color: var(--brand); background: var(--brandsoft); }

[data-testid="stFileUploader"] {
    background: var(--card);
    border: 2px dashed var(--line);
    border-radius: 16px;
    padding: 20px;
}

/* ── Progress steps ──────────────────────────────────────────────── */
.lm-steps { list-style: none; padding: 0; margin: 14px 0 0; }
.lm-step { display: flex; gap: 10px; align-items: center; padding: 6px 0; color: var(--mut); }
.lm-step-done { color: var(--lo); }
.lm-step-run { color: var(--brand); font-weight: 600; }

.lm-bar { height: 6px; background: var(--line); border-radius: 9px; overflow: hidden; margin-top: 12px; }
.lm-bar-fill { display: block; height: 100%; background: var(--brand); border-radius: 9px; }

/* ── KV pairs ────────────────────────────────────────────────────── */
.lm-kv { display: grid; grid-template-columns: 130px 1fr; gap: 6px 12px; margin: 0; }
.lm-kv dt { color: var(--mut); font-size: 13px; }
.lm-kv dd { margin: 0; font-size: 14px; }

/* ── Chat ────────────────────────────────────────────────────────── */
.lm-chat-user {
    max-width: 88%;
    padding: 10px 14px;
    border-radius: 14px;
    background: var(--brand);
    color: #fff;
    align-self: flex-end;
    margin-left: auto;
    margin-bottom: 8px;
}
.lm-chat-ai {
    max-width: 88%;
    padding: 10px 14px;
    border-radius: 14px;
    background: var(--bg);
    border: 1px solid var(--line);
    align-self: flex-start;
    margin-bottom: 8px;
}

/* ── Evidence block ──────────────────────────────────────────────── */
.lm-ev {
    margin-top: 8px;
    border-left: 3px solid var(--brand);
    background: var(--brandsoft);
    padding: 8px 12px;
    border-radius: 0 10px 10px 0;
    font-size: 13px;
    color: var(--ink);
}
.lm-ev mark {
    background: #ffe27a;
    color: #222;
    padding: 0 2px;
    border-radius: 3px;
}

/* ── Risk cards ──────────────────────────────────────────────────── */
.lm-risk {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 16px;
    margin-bottom: 14px;
    border-left: 4px solid var(--line);
}
.lm-risk-high { border-left-color: var(--hi) !important; }
.lm-risk-medium { border-left-color: var(--me) !important; }
.lm-risk-low { border-left-color: var(--lo) !important; }

/* ── Comparison panes ────────────────────────────────────────────── */
.lm-cmp { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }
.lm-pane { background: var(--bg); border-radius: 10px; padding: 10px; font-size: 13px; }
.lm-pane h4 { margin: 0 0 4px; font-size: 12px; color: var(--mut); text-transform: uppercase; }
del { background: var(--hisoft); color: var(--hi); }
ins { background: var(--losoft); color: var(--lo); text-decoration: none; }

/* ── Tabs ────────────────────────────────────────────────────────── */
.lm-tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }
.stTabs [data-baseweb="tab-list"] {
    gap: 6px;
    background: transparent;
    border-bottom: 1px solid var(--line);
}
.stTabs [data-baseweb="tab"] {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 99px;
    padding: 4px 14px;
    font-size: 13px;
    color: var(--mut);
}
.stTabs [aria-selected="true"] {
    background: var(--brandsoft) !important;
    border-color: var(--brand) !important;
    color: var(--brand) !important;
    font-weight: 600 !important;
}

/* ── Metrics ─────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 14px !important;
}
[data-testid="stMetricLabel"] { color: var(--mut) !important; font-size: 12px !important; }
[data-testid="stMetricValue"] { color: var(--ink) !important; font-size: 20px !important; font-weight: 700 !important; }

/* ── Expanders ───────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: var(--card);
    border: 1px solid var(--line) !important;
    border-radius: 14px !important;
    margin-bottom: 10px;
}
[data-testid="stExpander"] summary {
    font-weight: 600;
    color: var(--ink);
    padding: 12px 16px;
}

/* ── Alerts ──────────────────────────────────────────────────────── */
.stAlert {
    border-radius: 10px !important;
}

/* ── Input fields ────────────────────────────────────────────────── */
.stTextInput input, .stTextArea textarea, .stChatInput textarea {
    border-radius: 10px !important;
    border: 1px solid var(--line) !important;
    background: var(--card) !important;
    color: var(--ink) !important;
    font-family: inherit !important;
    padding: 11px 14px !important;
}
.stChatInput > div {
    border-radius: 10px !important;
    border: 1px solid var(--line) !important;
    background: var(--card) !important;
}

/* ── Selectbox ───────────────────────────────────────────────────── */
.stSelectbox > div > div {
    border-radius: 10px !important;
    border: 1px solid var(--line) !important;
    background: var(--card) !important;
}

/* ── Dataframe ───────────────────────────────────────────────────── */
.stDataFrame { border-radius: 10px; overflow: hidden; border: 1px solid var(--line); }

/* ── Chat messages (Streamlit native) ────────────────────────────── */
[data-testid="stChatMessage"] {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 12px 16px;
    margin-bottom: 8px;
}
[data-testid="stChatMessage"][data-testid*="user"] {
    background: var(--brandsoft);
    border-color: var(--brand);
}

/* ── Row helper ──────────────────────────────────────────────────── */
.lm-row { display: flex; justify-content: space-between; gap: 10px; align-items: center; flex-wrap: wrap; }

/* ── Disclaimer footer ───────────────────────────────────────────── */
.lm-disclaimer {
    font-size: 11px;
    color: var(--mut);
    padding: 6px 10px;
    margin-top: auto;
}

/* ── Paper preview (reports) ─────────────────────────────────────── */
.lm-paper {
    background: #fff;
    color: #222;
    border-radius: 8px;
    padding: 24px;
    border: 1px solid var(--line);
    font-size: 13px;
    line-height: 1.6;
}
.lm-paper hr { border: 0; border-top: 1px solid #ddd; margin: 12px 0; }

/* ── Spinner ─────────────────────────────────────────────────────── */
.stSpinner > div { border-top-color: var(--brand) !important; }
</style>
"""


def inject_theme():
    """Call this once at the top of app.py to inject the global CSS theme."""
    import streamlit as st
    st.markdown(THEME_CSS, unsafe_allow_html=True)


def sev_badge(severity: str) -> str:
    """Return an HTML severity badge matching the prototype style."""
    cls = {"high": "lm-sev-high", "medium": "lm-sev-medium", "low": "lm-sev-low"}.get(severity.lower(), "")
    return f'<span class="lm-sev {cls}">{severity.upper()}</span>'


def card_html(content: str, extra_class: str = "") -> str:
    """Wrap content in a card div."""
    return f'<div class="lm-card {extra_class}">{content}</div>'


def ev_html(label: str, text: str) -> str:
    """Return an evidence block matching the prototype's .ev style."""
    return f'<div class="lm-ev"><b>{label}</b><br>{text}</div>'
