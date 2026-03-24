"""
AlphaLens — AI-Powered Crypto Research Agent
─────────────────────────────────────────────
Dashboard : Binance WebSocket → SQLite → Plotly charts
Chat      : Ask anything → GPT-4o agent fetches from CoinGecko, DefiLlama, Binance → cited answer
Deep Dive : One-click comprehensive report from all data sources
"""

import io
import os
import re

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from dotenv import load_dotenv
from docx import Document

from src.database import init_db
from src.ws_client import BinanceKlineStream
from src.orderbook import BinanceOrderBookStream
from src.history import fetch_historical_klines
from src.agent import run_agent, deep_dive
from src.scanner import scan_markets
from src.strategies import run_all_strategies

load_dotenv()

AVAILABLE_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
]

CHART_COLORS = ["#7c83fd", "#00e676", "#ff9800", "#e91e63"]

TOOL_LABELS = {
    "get_market_data": "📊 Fetching market data from CoinGecko",
    "get_tvl": "🔗 Fetching TVL from DefiLlama",
    "get_funding_rate": "📈 Fetching funding rates from Binance Futures",
    "get_open_interest": "📉 Fetching open interest from Binance Futures",
    "get_technical_analysis": "🔬 Running technical analysis on Binance data",
    "get_prediction_markets": "🎯 Fetching prediction markets from Polymarket",
}

DEEP_DIVE_TOKENS = [
    "BTC",
    "ETH",
    "SOL",
    "BNB",
    "XRP",
    "DOGE",
    "ADA",
    "AVAX",
    "DOT",
    "LINK",
    "UNI",
    "NEAR",
    "ARB",
    "OP",
]


def _report_to_docx_bytes(report_text: str, symbol: str) -> bytes:
    """Convert markdown-like report text to a .docx file in memory."""
    def _add_markdown_runs(paragraph, text: str) -> None:
        """
        Render simple markdown emphasis to Word runs.
        Supports: **bold**, __bold__, *italic*, _italic_.
        """
        pattern = r"(\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|_[^_]+_)"
        idx = 0
        for match in re.finditer(pattern, text):
            start, end = match.span()
            if start > idx:
                paragraph.add_run(text[idx:start])

            token = match.group(0)
            if token.startswith("**") and token.endswith("**"):
                run = paragraph.add_run(token[2:-2])
                run.bold = True
            elif token.startswith("__") and token.endswith("__"):
                run = paragraph.add_run(token[2:-2])
                run.bold = True
            elif token.startswith("*") and token.endswith("*"):
                run = paragraph.add_run(token[1:-1])
                run.italic = True
            elif token.startswith("_") and token.endswith("_"):
                run = paragraph.add_run(token[1:-1])
                run.italic = True
            idx = end

        if idx < len(text):
            paragraph.add_run(text[idx:])

    doc = Document()
    doc.add_heading(f"AlphaLens Deep Dive Report - {symbol}", level=0)

    for raw_line in report_text.splitlines():
        line = raw_line.strip()

        if not line:
            # Keep section spacing in the generated document.
            doc.add_paragraph("")
            continue
        if line.startswith("### "):
            p = doc.add_heading("", level=3)
            _add_markdown_runs(p, line[4:].strip())
        elif line.startswith("## "):
            p = doc.add_heading("", level=2)
            _add_markdown_runs(p, line[3:].strip())
        elif line.startswith("# "):
            p = doc.add_heading("", level=1)
            _add_markdown_runs(p, line[2:].strip())
        elif line.startswith(("- ", "* ")):
            p = doc.add_paragraph(style="List Bullet")
            _add_markdown_runs(p, line[2:].strip())
        else:
            p = doc.add_paragraph()
            _add_markdown_runs(p, line)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue()

# ── Page config ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AlphaLens — Crypto Research Agent",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Theme definitions ─────────────────────────────────────────────────────────────
THEMES = {
    "Midnight Indigo": {
        "bg": "#0b0e14",
        "sidebar": "#0f1218",
        "card": "linear-gradient(145deg, #181d2a 0%, #141926 100%)",
        "border": "rgba(124,131,253,0.22)",
        "border_subtle": "rgba(124,131,253,0.10)",
        "accent": "#7c83fd",
        "accent_hover": "#9196ff",
        "accent_text": "#c0c4ff",
        "accent_bg": "linear-gradient(135deg, #7c83fd22 0%, #7c83fd11 100%)",
        "label": "rgba(255,255,255,0.55)",
        "chat_bg": "#1c2135",          # noticeably lighter than page bg
        "chat_text": "#dde1ff",        # soft lavender-white — crisp on dark blue
        "code_bg": "#0f1320",
        "status_bg": "#141820",
        "btn_bg": "linear-gradient(135deg, #7c83fd 0%, #6366f1 100%)",
        "btn_hover": "linear-gradient(135deg, #9196ff 0%, #818cf8 100%)",
        "expander_bg": "#141820",
    },
    "Carbon Black": {
        "bg": "#0a0a0a",
        "sidebar": "#111111",
        "card": "linear-gradient(145deg, #1a1a1a 0%, #161616 100%)",
        "border": "rgba(0,230,118,0.20)",
        "border_subtle": "rgba(255,255,255,0.08)",
        "accent": "#00e676",
        "accent_hover": "#69f0ae",
        "accent_text": "#69f0ae",
        "accent_bg": "rgba(0,230,118,0.09)",
        "label": "rgba(255,255,255,0.5)",
        "chat_bg": "#1c1c1c",          # dark charcoal — clear step up from page
        "chat_text": "#e8ffe8",        # very light mint — pops on charcoal
        "code_bg": "#0d0d0d",
        "status_bg": "#141414",
        "btn_bg": "linear-gradient(135deg, #00e676 0%, #00c853 100%)",
        "btn_hover": "linear-gradient(135deg, #69f0ae 0%, #00e676 100%)",
        "expander_bg": "#141414",
    },
    "Glass Frost": {
        "bg": "#0d1117",
        "sidebar": "#111820",
        "card": "linear-gradient(135deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.03) 100%)",
        "border": "rgba(88,166,255,0.22)",
        "border_subtle": "rgba(255,255,255,0.08)",
        "accent": "#58a6ff",
        "accent_hover": "#79b8ff",
        "accent_text": "#93caff",
        "accent_bg": "rgba(88,166,255,0.12)",
        "label": "rgba(255,255,255,0.55)",
        "chat_bg": "#182030",          # deep navy — crisp against page
        "chat_text": "#d0e8ff",        # ice blue-white
        "code_bg": "#0d1117",
        "status_bg": "#111820",
        "btn_bg": "linear-gradient(135deg, #58a6ff 0%, #388bfd 100%)",
        "btn_hover": "linear-gradient(135deg, #79b8ff 0%, #58a6ff 100%)",
        "expander_bg": "#111820",
    },
    "Cyber Neon": {
        "bg": "#080612",
        "sidebar": "#0c0a18",
        "card": "linear-gradient(145deg, #16132e 0%, #110f26 100%)",
        "border": "rgba(0,255,255,0.20)",
        "border_subtle": "rgba(0,255,255,0.08)",
        "accent": "#00ffff",
        "accent_hover": "#66ffff",
        "accent_text": "#66ffff",
        "accent_bg": "rgba(0,255,255,0.09)",
        "label": "rgba(255,255,255,0.5)",
        "chat_bg": "#16132e",          # deep purple — clear vs near-black page
        "chat_text": "#d0ffff",        # cyan-tinted white — very readable
        "code_bg": "#0a0818",
        "status_bg": "#12102a",
        "btn_bg": "linear-gradient(135deg, #00ffff 0%, #00cccc 100%)",
        "btn_hover": "linear-gradient(135deg, #66ffff 0%, #00ffff 100%)",
        "expander_bg": "#12102a",
    },
}


def _inject_theme(t: dict) -> None:
    """Inject CSS for the selected theme."""
    # Button text needs to be dark on bright accent themes
    btn_text = "#000" if t["accent"] in ("#00e676", "#00ffff") else "#fff"
    st.markdown(
        f"""
        <style>
        .stApp {{ background: {t["bg"]}; }}
        section[data-testid="stSidebar"] {{
            background: {t["sidebar"]};
            border-right: 1px solid {t["border_subtle"]};
        }}

        /* ── Sidebar text: force readable white on all dark themes ── */
        section[data-testid="stSidebar"] * {{
            color: rgba(255,255,255,0.88) !important;
        }}
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] strong {{
            color: #ffffff !important;
        }}
        section[data-testid="stSidebar"] .stSelectbox label,
        section[data-testid="stSidebar"] .stMultiSelect label,
        section[data-testid="stSidebar"] .stSlider label,
        section[data-testid="stSidebar"] .stToggle label,
        section[data-testid="stSidebar"] p {{
            color: rgba(255,255,255,0.85) !important;
            font-size: 0.82rem;
        }}
        section[data-testid="stSidebar"] .stCaption,
        section[data-testid="stSidebar"] small {{
            color: rgba(255,255,255,0.50) !important;
        }}
        /* Sidebar selectbox / multiselect drop area */
        section[data-testid="stSidebar"] [data-baseweb="select"] * {{
            color: rgba(255,255,255,0.88) !important;
            background-color: {t["expander_bg"]} !important;
        }}
        /* Sidebar buttons — nuke the default white background on every state */
        section[data-testid="stSidebar"] button {{
            background-color: {t["expander_bg"]} !important;
            background: {t["expander_bg"]} !important;
            color: rgba(255,255,255,0.88) !important;
            border: 1px solid {t["border"]} !important;
            border-radius: 8px !important;
            font-size: 0.78rem !important;
            transition: border-color 0.15s, background-color 0.15s;
        }}
        section[data-testid="stSidebar"] button:hover {{
            background-color: {t["expander_bg"]} !important;
            border-color: {t["accent"]} !important;
        }}
        /* Every text node inside sidebar buttons */
        section[data-testid="stSidebar"] button *,
        section[data-testid="stSidebar"] button p,
        section[data-testid="stSidebar"] button span,
        section[data-testid="stSidebar"] button div {{
            color: rgba(255,255,255,0.88) !important;
            background: transparent !important;
        }}
        /* Slider track label */
        section[data-testid="stSidebar"] [data-testid="stSliderTickBarMin"],
        section[data-testid="stSidebar"] [data-testid="stSliderTickBarMax"] {{
            color: rgba(255,255,255,0.45) !important;
        }}

        /* Metric cards */
        [data-testid="stMetric"] {{
            background: {t["card"]};
            border: 1px solid {t["border"]};
            border-radius: 14px;
            padding: 18px 22px 14px;
        }}
        [data-testid="stMetricLabel"] {{
            font-size: 0.72rem !important;
            font-weight: 600 !important;
            color: {t["label"]} !important;
            text-transform: uppercase;
            letter-spacing: 0.8px;
        }}
        [data-testid="stMetricValue"] {{
            font-size: 1.55rem !important;
            font-weight: 700 !important;
            color: #ffffff !important;
            font-variant-numeric: tabular-nums;
            letter-spacing: -0.3px;
        }}
        [data-testid="stMetricDelta"] {{
            font-size: 0.82rem !important;
            font-weight: 500 !important;
        }}
        [data-testid="stMetricDelta"] svg {{ display: none; }}

        /* Tabs */
        .stTabs [data-baseweb="tab-list"] {{
            gap: 0;
            background: {t["sidebar"]};
            border-radius: 12px;
            padding: 4px;
            border: 1px solid {t["border_subtle"]};
        }}
        .stTabs [data-baseweb="tab"] {{
            border-radius: 10px;
            padding: 10px 24px;
            font-weight: 600;
            font-size: 0.85rem;
            color: rgba(255,255,255,0.5);
            letter-spacing: 0.2px;
        }}
        .stTabs [aria-selected="true"] {{
            background: {t["accent_bg"]} !important;
            color: {t["accent_text"]} !important;
            border-bottom: none !important;
        }}
        .stTabs [data-baseweb="tab-highlight"] {{ display: none; }}
        .stTabs [data-baseweb="tab-border"] {{ display: none; }}

        /* Expanders */
        .streamlit-expanderHeader {{
            background: {t["expander_bg"]} !important;
            border-radius: 10px !important;
            border: 1px solid {t["border"]} !important;
            font-weight: 600 !important;
        }}

        /* Dataframes */
        [data-testid="stDataFrame"] {{
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid {t["border"]};
        }}

        /* Dividers */
        hr {{ border-color: {t["border_subtle"]} !important; }}

        /* Chat bubbles */
        [data-testid="stChatMessage"] {{
            background: {t["chat_bg"]};
            border: 1px solid {t["border"]};
            border-radius: 16px;
            padding: 18px 22px;
            margin-bottom: 10px;
        }}
        /* Nuclear contrast fix — catch every text node inside chat */
        [data-testid="stChatMessage"] *:not(svg):not(path) {{
            color: {t["chat_text"]} !important;
        }}
        [data-testid="stChatMessage"] h1,
        [data-testid="stChatMessage"] h2,
        [data-testid="stChatMessage"] h3,
        [data-testid="stChatMessage"] h4,
        [data-testid="stChatMessage"] strong,
        [data-testid="stChatMessage"] b {{
            color: #ffffff !important;
            font-weight: 700 !important;
        }}
        [data-testid="stChatMessage"] em,
        [data-testid="stChatMessage"] i {{
            color: {t["accent_text"]} !important;
        }}
        [data-testid="stChatMessage"] code {{
            color: {t["accent_text"]} !important;
            background: {t["code_bg"]} !important;
            border-radius: 5px;
            padding: 2px 6px;
            font-size: 0.85em;
        }}
        [data-testid="stChatMessage"] pre code {{
            color: {t["chat_text"]} !important;
            background: transparent !important;
            padding: 0;
        }}
        [data-testid="stChatMessage"] pre {{
            background: {t["code_bg"]} !important;
            border-radius: 10px;
            padding: 14px 18px;
            border: 1px solid {t["border_subtle"]};
        }}
        [data-testid="stChatMessage"] blockquote {{
            border-left: 3px solid {t["accent"]};
            padding-left: 14px;
            margin-left: 0;
            opacity: 0.85;
        }}
        [data-testid="stChatMessage"] a {{
            color: {t["accent_text"]} !important;
            text-decoration: underline;
        }}
        /* Chat input */
        .stChatInputContainer {{
            border-color: {t["border"]} !important;
            border-radius: 14px !important;
            background: {t["chat_bg"]} !important;
        }}
        .stChatInputContainer textarea {{
            color: #ffffff !important;
        }}
        /* Thin accent scrollbar on chat window */
        [data-testid="stVerticalBlockBorderWrapper"] {{
            scrollbar-width: thin;
            scrollbar-color: {t["accent"]}55 transparent;
        }}
        [data-testid="stVerticalBlockBorderWrapper"]::-webkit-scrollbar {{
            width: 4px;
        }}
        [data-testid="stVerticalBlockBorderWrapper"]::-webkit-scrollbar-thumb {{
            background: {t["accent"]}66;
            border-radius: 4px;
        }}

        /* Buttons */
        .stButton > button[kind="primary"] {{
            background: {t["btn_bg"]};
            color: {btn_text} !important;
            border: none;
            border-radius: 10px;
            font-weight: 600;
        }}
        .stButton > button[kind="primary"]:hover {{
            background: {t["btn_hover"]};
        }}

        /* Status badge */
        .status-bar {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: {t["status_bg"]};
            border: 1px solid {t["border"]};
            border-radius: 20px;
            padding: 6px 16px;
            font-size: 0.78rem;
            color: rgba(255,255,255,0.55);
            font-weight: 500;
            letter-spacing: 0.3px;
        }}
        .status-bar .dot {{
            width: 8px; height: 8px;
            border-radius: 50%;
            background: #00e676;
            box-shadow: 0 0 6px #00e67688;
            display: inline-block;
        }}
        .status-bar .dot.off {{
            background: #ff1744;
            box-shadow: 0 0 6px #ff174488;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── One-time DB init ─────────────────────────────────────────────────────────────
@st.cache_resource
def setup_db():
    init_db()


setup_db()

# ── Session state defaults ───────────────────────────────────────────────────────
if "history_loaded" not in st.session_state:
    st.session_state["history_loaded"] = set()
if "chat_messages" not in st.session_state:
    st.session_state["chat_messages"] = []
if "conversations" not in st.session_state:
    st.session_state["conversations"] = []   # [{id, title, messages}]
if "active_conv_id" not in st.session_state:
    st.session_state["active_conv_id"] = None


def _archive_current_chat() -> None:
    """Save or update the current chat into the conversations list."""
    import time as _time
    msgs = st.session_state.get("chat_messages", [])
    if not msgs:
        return
    user_msgs = [m for m in msgs if m["role"] == "user"]
    title = (user_msgs[0]["content"][:42] + "…") if user_msgs else "Untitled"
    conv_id = st.session_state.get("active_conv_id")
    convs = st.session_state["conversations"]
    if conv_id:
        for c in convs:
            if c["id"] == conv_id:
                c["messages"] = [dict(m) for m in msgs]
                c["title"] = title
                return
    new_id = str(int(_time.time() * 1000))
    convs.append({"id": new_id, "title": title, "messages": [dict(m) for m in msgs]})
    st.session_state["active_conv_id"] = new_id

# ── Sidebar ──────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📈 AlphaLens")
    st.caption("AI-Powered Crypto Research Agent")
    st.divider()

    symbols: list[str] = st.multiselect(
        "Assets (up to 4)",
        AVAILABLE_SYMBOLS,
        default=["BTCUSDT"],
        max_selections=4,
    )
    if not symbols:
        symbols = ["BTCUSDT"]

    interval: str = st.selectbox("Candle interval", ["1m", "3m", "5m"], index=0)
    lookback: int = st.slider(
        "Candles to display", min_value=20, max_value=500, value=100, step=10
    )

    st.divider()
    auto_refresh = st.toggle("Auto-refresh (5 s)", value=True)

    st.divider()
    theme_name: str = st.selectbox(
        "Theme",
        list(THEMES.keys()),
        index=0,
        key="theme_select",
    )

    st.divider()
    st.caption("Data: Binance · CoinGecko · DefiLlama · Polymarket\nAI: GPT-4o / Gemini")

    # ── Conversation history ─────────────────────────────────────────────────
    st.divider()
    st.markdown(
        "<div style='font-size:0.72rem; font-weight:700; letter-spacing:0.08em; "
        "color:rgba(255,255,255,0.4); margin-bottom:8px;'>CONVERSATIONS</div>",
        unsafe_allow_html=True,
    )

    has_messages = bool(st.session_state.get("chat_messages"))

    nc_col, cl_col = st.columns(2)
    with nc_col:
        # Only meaningful if there's actually something to archive
        if st.button(
            "＋ New Chat",
            use_container_width=True,
            key="new_chat_btn",
            disabled=not has_messages,
        ):
            _archive_current_chat()
            st.session_state["chat_messages"] = []
            st.session_state["active_conv_id"] = None
            st.rerun()
    with cl_col:
        if st.button("🗑 Clear All", use_container_width=True, key="clear_all_btn"):
            st.session_state["conversations"] = []
            st.session_state["chat_messages"] = []
            st.session_state["active_conv_id"] = None
            st.rerun()

    convs = st.session_state["conversations"]
    if not convs and not has_messages:
        st.caption("Start chatting — your conversations will appear here.")
    else:
        active_id = st.session_state.get("active_conv_id")
        # Show in-progress chat at the top if it has messages but isn't saved yet
        if has_messages and active_id is None:
            st.markdown(
                "<div style='font-size:0.73rem; color:rgba(255,255,255,0.5); "
                "padding:6px 10px; border:1px solid rgba(255,255,255,0.1); "
                "border-radius:6px; margin-bottom:4px;'>▶ Current chat (unsaved)</div>",
                unsafe_allow_html=True,
            )
        for conv in reversed(convs):
            is_active = conv["id"] == active_id
            label = ("▶ " if is_active else "") + conv["title"]
            if st.button(
                label,
                key=f"conv_{conv['id']}",
                use_container_width=True,
                help=f"{len(conv['messages'])} messages",
            ):
                _archive_current_chat()
                st.session_state["chat_messages"] = [dict(m) for m in conv["messages"]]
                st.session_state["active_conv_id"] = conv["id"]
                st.rerun()

_inject_theme(THEMES[theme_name])

primary = symbols[0]

# ── Historical data: fetch once per (symbol, interval) ──────────────────────────
for sym in symbols:
    hist_key = f"hist_{sym}_{interval}"
    if hist_key not in st.session_state["history_loaded"]:
        with st.spinner(f"Loading historical candles for {sym}…"):
            fetch_historical_klines(sym, interval, limit=500)
        st.session_state["history_loaded"].add(hist_key)

# ── Kline WebSocket streams ──────────────────────────────────────────────────────
active_ks = {f"ks_{sym}_{interval}" for sym in symbols}

for k in list(st.session_state.keys()):
    if k.startswith("ks_") and k not in active_ks:
        v = st.session_state[k]
        if isinstance(v, BinanceKlineStream):
            v.stop()
            del st.session_state[k]

for sym in symbols:
    ks_key = f"ks_{sym}_{interval}"
    if ks_key not in st.session_state:
        s = BinanceKlineStream(sym, interval)
        s.start()
        st.session_state[ks_key] = s

# ── Order book stream: primary symbol ────────────────────────────────────────────
ob_key = f"ob_{primary}"

for k in list(st.session_state.keys()):
    if k.startswith("ob_") and k != ob_key:
        v = st.session_state[k]
        if isinstance(v, BinanceOrderBookStream):
            v.stop()
            del st.session_state[k]

if ob_key not in st.session_state:
    obs = BinanceOrderBookStream(primary)
    obs.start()
    st.session_state[ob_key] = obs

# ── Header ───────────────────────────────────────────────────────────────────────
primary_stream = st.session_state.get(f"ks_{primary}_{interval}")
is_live = primary_stream and primary_stream.is_running
title = " · ".join(symbols) if len(symbols) > 1 else primary
st.title(f"{title}")
dot_cls = "" if is_live else " off"
status_text = "Live" if is_live else "Disconnected"
st.markdown(
    f'<div class="status-bar">'
    f'<span class="dot{dot_cls}"></span> {status_text}'
    f" &nbsp;·&nbsp; {interval} candles"
    f" &nbsp;·&nbsp; {lookback} loaded"
    f" &nbsp;·&nbsp; {len(symbols)} stream(s)"
    f"</div>",
    unsafe_allow_html=True,
)

# ════════════════════════════════════════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════════════════════════════════════════

tab_dashboard, tab_research, tab_scanner = st.tabs(
    [
        "📊 Dashboard",
        "💬 Chatbot",
        "🎯 Prediction Scanner",
    ]
)

# ════════════════════════════════════════════════════════════════════════════════
# TAB 1 — DASHBOARD (charts + order book)
# Fragment re-renders every 5s independently — chat and deep dive are untouched.
# ════════════════════════════════════════════════════════════════════════════════

with tab_dashboard:

    @st.fragment(run_every=5 if auto_refresh else None)
    def _dashboard():
        from src.database import get_klines
        from src.indicators import add_indicators

        dfs: dict[str, pd.DataFrame] = {}
        for _s in symbols:
            _k = get_klines(_s, interval=interval, limit=lookback)
            if _k:
                _d = pd.DataFrame(
                    _k, columns=["open_time", "open", "high", "low", "close", "volume"]
                )
                _d["datetime"] = pd.to_datetime(_d["open_time"], unit="ms", utc=True)
                _d = add_indicators(_d)
                dfs[_s] = _d

        if len(symbols) == 1:
            df = dfs.get(primary)
            if df is None or df.empty:
                st.info("⏳ Waiting for candle data…")
                return

            latest = df.iloc[-1]
            earliest = df.iloc[0]
            pct = ((latest["close"] - earliest["close"]) / earliest["close"]) * 100
            dollar_chg = latest["close"] - earliest["close"]

            # Row 1 — price metrics
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(
                "Price (USDT)",
                f"${latest['close']:,.2f}",
                f"{dollar_chg:+,.2f} ({pct:+.2f}%)",
            )
            c2.metric("Period High", f"${df['high'].max():,.2f}")
            c3.metric("Period Low", f"${df['low'].min():,.2f}")
            c4.metric("Volume", f"{df['volume'].sum():,.0f}")

            # Row 2 — technical indicators
            rsi_val = latest.get("rsi")
            macd_val = latest.get("macd")
            sig_val = latest.get("macd_signal")
            bb_up = latest.get("bb_upper")
            bb_lo = latest.get("bb_lower")

            t1, t2, t3 = st.columns(3)
            t1.metric(
                "RSI (14)",
                f"{rsi_val:.1f}" if rsi_val and not pd.isna(rsi_val) else "—",
                "overbought"
                if (rsi_val and rsi_val > 70)
                else "oversold"
                if (rsi_val and rsi_val < 30)
                else "neutral",
            )
            t2.metric(
                "MACD",
                f"{macd_val:.4f}" if macd_val and not pd.isna(macd_val) else "—",
                "▲ bullish"
                if (macd_val and sig_val and macd_val > sig_val)
                else "▼ bearish",
            )
            if bb_up and bb_lo and not pd.isna(bb_up):
                bw = bb_up - bb_lo
                bpos = (latest["close"] - bb_lo) / bw * 100 if bw > 0 else 50
                t3.metric(
                    "BB Position",
                    f"{bpos:.0f}%",
                    "near top"
                    if bpos > 80
                    else "near bottom"
                    if bpos < 20
                    else "mid-band",
                )
            else:
                t3.metric("BB Position", "—")

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=df["datetime"],
                    y=df["bb_upper"],
                    mode="lines",
                    line=dict(color="rgba(255,200,0,0.3)", width=1),
                    name="BB Upper",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=df["datetime"],
                    y=df["bb_lower"],
                    mode="lines",
                    line=dict(color="rgba(255,200,0,0.3)", width=1),
                    fill="tonexty",
                    fillcolor="rgba(255,200,0,0.05)",
                    name="BB Lower",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=df["datetime"],
                    y=df["bb_mid"],
                    mode="lines",
                    line=dict(color="rgba(255,200,0,0.5)", width=1, dash="dot"),
                    name="BB Mid",
                    showlegend=False,
                )
            )
            fig.add_trace(
                go.Candlestick(
                    x=df["datetime"],
                    open=df["open"],
                    high=df["high"],
                    low=df["low"],
                    close=df["close"],
                    name="Price",
                    increasing_line_color="#00e676",
                    decreasing_line_color="#ff1744",
                    increasing_fillcolor="#00e676",
                    decreasing_fillcolor="#ff1744",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=df["datetime"],
                    y=df["sma_20"],
                    mode="lines",
                    line=dict(color="#7c83fd", width=1.5),
                    name="SMA 20",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=df["datetime"],
                    y=df["sma_50"],
                    mode="lines",
                    line=dict(color="#ff9800", width=1.5),
                    name="SMA 50",
                )
            )
            fig.add_trace(
                go.Bar(
                    x=df["datetime"],
                    y=df["volume"],
                    name="Volume",
                    yaxis="y2",
                    marker_color=[
                        "rgba(0,230,118,0.2)" if c >= o else "rgba(255,23,68,0.2)"
                        for o, c in zip(df["open"], df["close"])
                    ],
                )
            )
            fig.update_layout(
                template="plotly_dark",
                height=540,
                margin=dict(l=0, r=0, t=40, b=0),
                title=dict(
                    text=f"{primary} · {interval}  |  SMA20  SMA50  BB",
                    font=dict(size=14),
                ),
                xaxis=dict(showgrid=True, gridcolor="#2a2a2a"),
                yaxis=dict(title="Price (USDT)", showgrid=True, gridcolor="#2a2a2a"),
                yaxis2=dict(
                    title="Volume", overlaying="y", side="right", showgrid=False
                ),
                xaxis_rangeslider_visible=False,
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.02, font=dict(size=11)
                ),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, width="stretch")

            with st.expander("📊 Technical Indicators — RSI & MACD", expanded=True):
                fig_ind = make_subplots(
                    rows=2,
                    cols=1,
                    shared_xaxes=True,
                    row_heights=[0.5, 0.5],
                    vertical_spacing=0.08,
                    subplot_titles=("RSI (14)", "MACD (12, 26, 9)"),
                )
                fig_ind.add_trace(
                    go.Scatter(
                        x=df["datetime"],
                        y=df["rsi"],
                        mode="lines",
                        line=dict(color="#7c83fd", width=2),
                        name="RSI",
                    ),
                    row=1,
                    col=1,
                )
                fig_ind.add_hline(
                    y=70,
                    line_dash="dash",
                    line_color="rgba(255,23,68,0.5)",
                    annotation_text="Overbought 70",
                    row=1,
                    col=1,
                )
                fig_ind.add_hline(
                    y=30,
                    line_dash="dash",
                    line_color="rgba(0,230,118,0.5)",
                    annotation_text="Oversold 30",
                    row=1,
                    col=1,
                )
                fig_ind.add_hline(
                    y=50,
                    line_dash="dot",
                    line_color="rgba(255,255,255,0.15)",
                    row=1,
                    col=1,
                )
                hist_colors = [
                    "rgba(0,230,118,0.6)" if v >= 0 else "rgba(255,23,68,0.6)"
                    for v in df["macd_hist"].fillna(0)
                ]
                fig_ind.add_trace(
                    go.Bar(
                        x=df["datetime"],
                        y=df["macd_hist"],
                        name="Histogram",
                        marker_color=hist_colors,
                    ),
                    row=2,
                    col=1,
                )
                fig_ind.add_trace(
                    go.Scatter(
                        x=df["datetime"],
                        y=df["macd"],
                        mode="lines",
                        line=dict(color="#7c83fd", width=2),
                        name="MACD",
                    ),
                    row=2,
                    col=1,
                )
                fig_ind.add_trace(
                    go.Scatter(
                        x=df["datetime"],
                        y=df["macd_signal"],
                        mode="lines",
                        line=dict(color="#ff9800", width=1.5, dash="dot"),
                        name="Signal",
                    ),
                    row=2,
                    col=1,
                )
                fig_ind.add_hline(
                    y=0, line_color="rgba(255,255,255,0.15)", row=2, col=1
                )
                fig_ind.update_layout(
                    template="plotly_dark",
                    height=420,
                    margin=dict(l=0, r=0, t=40, b=0),
                    plot_bgcolor="#0e1117",
                    paper_bgcolor="#0e1117",
                    legend=dict(
                        orientation="h", yanchor="bottom", y=1.02, font=dict(size=11)
                    ),
                    showlegend=True,
                )
                fig_ind.update_yaxes(showgrid=True, gridcolor="#2a2a2a")
                fig_ind.update_xaxes(showgrid=True, gridcolor="#2a2a2a")
                st.plotly_chart(fig_ind, width="stretch")

        else:
            metric_cols = st.columns(len(symbols))
            for i, sym in enumerate(symbols):
                df = dfs.get(sym)
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    earliest = df.iloc[0]
                    pct = (
                        (latest["close"] - earliest["close"]) / earliest["close"]
                    ) * 100
                    metric_cols[i].metric(
                        sym, f"${latest['close']:,.4f}", f"{pct:+.2f}%"
                    )
                else:
                    metric_cols[i].metric(sym, "—", "loading…")

            fig_comp = go.Figure()
            for i, sym in enumerate(symbols):
                df = dfs.get(sym)
                if df is not None and not df.empty:
                    base = df["close"].iloc[0]
                    normalized = (df["close"] / base - 1) * 100
                    fig_comp.add_trace(
                        go.Scatter(
                            x=df["datetime"],
                            y=normalized,
                            mode="lines",
                            name=sym,
                            line=dict(
                                color=CHART_COLORS[i % len(CHART_COLORS)], width=2
                            ),
                        )
                    )
            fig_comp.add_hline(
                y=0, line_dash="dash", line_color="rgba(255,255,255,0.15)"
            )
            fig_comp.update_layout(
                template="plotly_dark",
                height=360,
                margin=dict(l=0, r=0, t=40, b=0),
                title=dict(
                    text="Relative % Change (normalized to period start = 0%)",
                    font=dict(size=14),
                ),
                yaxis=dict(
                    title="% Change", showgrid=True, gridcolor="#2a2a2a", ticksuffix="%"
                ),
                xaxis=dict(showgrid=True, gridcolor="#2a2a2a"),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                hovermode="x unified",
            )
            st.plotly_chart(fig_comp, width="stretch")

            for row_start in range(0, len(symbols), 2):
                cols = st.columns(min(2, len(symbols) - row_start))
                for col_idx, sym in enumerate(symbols[row_start : row_start + 2]):
                    df = dfs.get(sym)
                    with cols[col_idx]:
                        if df is not None and not df.empty:
                            fig_mini = go.Figure()
                            fig_mini.add_trace(
                                go.Candlestick(
                                    x=df["datetime"],
                                    open=df["open"],
                                    high=df["high"],
                                    low=df["low"],
                                    close=df["close"],
                                    name=sym,
                                    showlegend=False,
                                    increasing_line_color="#00e676",
                                    decreasing_line_color="#ff1744",
                                    increasing_fillcolor="#00e676",
                                    decreasing_fillcolor="#ff1744",
                                )
                            )
                            fig_mini.update_layout(
                                template="plotly_dark",
                                height=280,
                                margin=dict(l=0, r=0, t=30, b=0),
                                title=dict(text=sym, font=dict(size=13)),
                                xaxis=dict(showgrid=False, showticklabels=False),
                                yaxis=dict(
                                    showgrid=True,
                                    gridcolor="#2a2a2a",
                                    tickfont=dict(size=10),
                                ),
                                xaxis_rangeslider_visible=False,
                                plot_bgcolor="#0e1117",
                                paper_bgcolor="#0e1117",
                            )
                            st.plotly_chart(fig_mini, width="stretch")
                        else:
                            st.info(f"⏳ {sym} — waiting for data…")

        # ── Order book ───────────────────────────────────────────────────────
        st.divider()
        st.markdown(f"### 📖 Order Book — {primary}")
        ob_stream: BinanceOrderBookStream = st.session_state[ob_key]

        if not ob_stream.book.has_data:
            st.info("⏳ Waiting for order book data…")
        else:
            book = ob_stream.book
            bids, asks = book.snapshot()
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Best Bid", f"${book.best_bid:,.2f}" if book.best_bid else "—")
            m2.metric("Best Ask", f"${book.best_ask:,.2f}" if book.best_ask else "—")
            m3.metric("Spread", f"${book.spread:,.2f}" if book.spread else "—")
            m4.metric("Spread %", f"{book.spread_pct:.4f}%" if book.spread_pct else "—")

            top_n = 10
            bid_df = pd.DataFrame(bids[:top_n], columns=["Price", "Qty"])
            ask_df = pd.DataFrame(asks[:top_n], columns=["Price", "Qty"])
            bid_df["Total (USDT)"] = (bid_df["Price"] * bid_df["Qty"]).round(2)
            ask_df["Total (USDT)"] = (ask_df["Price"] * ask_df["Qty"]).round(2)

            def _green_shade(col):
                mx = col.max() or 1
                return [
                    f"background-color: rgba(0,230,118,{v / mx * 0.55:.2f})"
                    for v in col
                ]

            def _red_shade(col):
                mx = col.max() or 1
                return [
                    f"background-color: rgba(255,23,68,{v / mx * 0.45:.2f})"
                    for v in col
                ]

            ob_col1, ob_col2 = st.columns(2)
            with ob_col1:
                st.markdown("**Bids 🟢** — buyers")
                st.dataframe(
                    bid_df.style.format(
                        {"Price": "{:.4f}", "Qty": "{:.5f}", "Total (USDT)": "{:,.2f}"}
                    ).apply(_green_shade, subset=["Total (USDT)"]),
                    width="stretch",
                    hide_index=True,
                )
            with ob_col2:
                st.markdown("**Asks 🔴** — sellers")
                st.dataframe(
                    ask_df.style.format(
                        {"Price": "{:.4f}", "Qty": "{:.5f}", "Total (USDT)": "{:,.2f}"}
                    ).apply(_red_shade, subset=["Total (USDT)"]),
                    width="stretch",
                    hide_index=True,
                )

            with st.expander("Market Depth Chart", expanded=False):
                bid_prices = [b[0] for b in bids]
                ask_prices = [a[0] for a in asks]
                bid_cum, ask_cum, cum = [], [], 0
                for b in bids:
                    cum += b[1]
                    bid_cum.append(cum)
                cum = 0
                for a in asks:
                    cum += a[1]
                    ask_cum.append(cum)
                fig_depth = go.Figure()
                fig_depth.add_trace(
                    go.Scatter(
                        x=bid_prices,
                        y=bid_cum,
                        mode="lines",
                        name="Bids",
                        line=dict(color="#00e676", width=2),
                        fill="tozeroy",
                        fillcolor="rgba(0,230,118,0.1)",
                    )
                )
                fig_depth.add_trace(
                    go.Scatter(
                        x=ask_prices,
                        y=ask_cum,
                        mode="lines",
                        name="Asks",
                        line=dict(color="#ff1744", width=2),
                        fill="tozeroy",
                        fillcolor="rgba(255,23,68,0.1)",
                    )
                )
                fig_depth.update_layout(
                    template="plotly_dark",
                    height=300,
                    margin=dict(l=0, r=0, t=20, b=0),
                    xaxis=dict(
                        title="Price (USDT)", showgrid=True, gridcolor="#2a2a2a"
                    ),
                    yaxis=dict(
                        title="Cumulative Volume", showgrid=True, gridcolor="#2a2a2a"
                    ),
                    plot_bgcolor="#0e1117",
                    paper_bgcolor="#0e1117",
                    legend=dict(orientation="h"),
                )
                st.plotly_chart(fig_depth, width="stretch")

    _dashboard()

# ════════════════════════════════════════════════════════════════════════════════
# TAB 2 — CHATBOT  (fragment so reruns never touch the active tab)
# ════════════════════════════════════════════════════════════════════════════════

with tab_research:
    from src.prompts.quick_prompts import QUICK_PROMPTS

    @st.fragment
    def _chatbot(sym: str) -> None:
        """Isolated fragment — all reruns stay inside this tab."""
        api_key = (
            os.getenv("OPENAI_API_KEY")
            or os.getenv("gpt_api_key")
            or os.getenv("GEMINI_API_KEY")
        )

        # ── Consume any pending quick-prompt BEFORE rendering history ─────────
        pending = st.session_state.pop("research_pending", None)

        # ── Fixed-height scrollable chat window ───────────────────────────────
        chat_window = st.container(height=520, border=False)
        with chat_window:
            if not st.session_state["chat_messages"]:
                with st.chat_message("assistant"):
                    st.markdown(
                        f"**AlphaLens Chatbot** — ask anything about "
                        f"**{sym}** or any crypto.\n\n"
                        "I pull live data from Binance, CoinGecko, DefiLlama, "
                        "Binance Futures, and Polymarket — then give you a cited answer.\n\n"
                        "Use the quick buttons below or type your own question."
                    )
            for msg in st.session_state["chat_messages"]:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        # Auto-scroll to bottom
        st.components.v1.html(
            """
            <script>
            (function() {
                var wrappers = window.parent.document.querySelectorAll(
                    '[data-testid="stVerticalBlockBorderWrapper"]'
                );
                wrappers.forEach(function(el) { el.scrollTop = el.scrollHeight; });
            })();
            </script>
            """,
            height=0,
        )

        # ── Quick-action buttons ───────────────────────────────────────────────
        st.markdown(
            "<div style='margin:1rem 0 0.4rem; font-size:0.78rem; "
            "color:rgba(255,255,255,0.45); letter-spacing:0.06em;'>"
            "QUICK RESEARCH</div>",
            unsafe_allow_html=True,
        )
        btn_cols = st.columns(len(QUICK_PROMPTS))
        for i, (label, emoji, tmpl) in enumerate(QUICK_PROMPTS):
            with btn_cols[i]:
                if st.button(
                    f"{emoji} {label}", use_container_width=True, key=f"qp_{i}"
                ):
                    # Store prompt and let the fragment rerun pick it up —
                    # no explicit st.rerun() so we never leave this tab.
                    st.session_state["research_pending"] = tmpl.format(symbol=sym)
                    st.rerun(scope="fragment")

        # ── Chat input ────────────────────────────────────────────────────────
        user_typed = st.chat_input(
            f"Ask about {sym} or any crypto… (e.g. 'Is ETH overbought?')"
        )

        prompt_to_run = pending or (user_typed or None)

        if prompt_to_run:
            if not api_key:
                st.error(
                    "No API key. Set `GEMINI_API_KEY` (free) or `gpt_api_key` in `.env`."
                )
            else:
                st.session_state["chat_messages"].append(
                    {"role": "user", "content": prompt_to_run}
                )
                with st.chat_message("user"):
                    st.markdown(prompt_to_run)

                with st.chat_message("assistant"):
                    with st.status("🔍 Fetching data…", expanded=True) as status:

                        def _on_tool(name: str, args: dict) -> None:
                            _sym = args.get("symbol", sym)
                            _label = TOOL_LABELS.get(name, name)
                            status.write(f"{_label} for **{_sym}**…")

                        history = [
                            {"role": m["role"], "content": m["content"]}
                            for m in st.session_state["chat_messages"][-10:]
                        ]

                        try:
                            response, tool_log = run_agent(
                                prompt_to_run,
                                history=history[:-1],
                                on_tool_call=_on_tool,
                            )
                        except Exception as e:
                            response = f"Error: {e}"
                            tool_log = []

                        if tool_log:
                            sources = sorted(
                                set(
                                    t["result"]["source"]
                                    for t in tool_log
                                    if isinstance(t.get("result"), dict)
                                    and "source" in t["result"]
                                )
                            )
                            status.update(
                                label=f"✅ Data from: {', '.join(sources)}",
                                state="complete",
                                expanded=False,
                            )
                        else:
                            status.update(
                                label="✅ Done", state="complete", expanded=False
                            )

                    st.markdown(response)

                    if len(response) > 1500 and "##" in response:
                        _sym_safe = sym.lower()
                        _ts = pd.Timestamp.utcnow().strftime("%Y%m%d-%H%M%S")
                        st.download_button(
                            "⬇️ Download as Word (.docx)",
                            data=_report_to_docx_bytes(response, sym),
                            file_name=f"alphalens-{_sym_safe}-{_ts}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"dl_{_ts}",
                        )

                st.session_state["chat_messages"].append(
                    {"role": "assistant", "content": response}
                )
                _archive_current_chat()
                # Fragment-scoped rerun — stays on this tab
                st.rerun(scope="fragment")

    _chatbot(primary.replace("USDT", ""))

# ════════════════════════════════════════════════════════════════════════════════
# TAB 4 — LIVE PREDICTION MARKETS
# ════════════════════════════════════════════════════════════════════════════════

with tab_scanner:
    st.markdown("### 🎯 Live Prediction Markets")
    st.caption("Auto-refreshing every 30s · Polymarket · Real-time Binance prices")

    if "mkt_history" not in st.session_state:
        st.session_state["mkt_history"] = {}

    def _fmt_time(hours: float) -> str:
        if hours <= 0:
            return "Expired"
        if hours < 1:
            return f"{int(hours * 60)}m left"
        if hours < 24:
            return f"{int(hours)}h {int((hours % 1) * 60)}m left"
        d = int(hours / 24)
        h = int(hours % 24)
        return f"{d}d {h}h left"

    def _fmt_vol(v: float) -> str:
        if v >= 1_000_000:
            return f"${v / 1_000_000:.1f}M"
        if v >= 1_000:
            return f"${v / 1_000:.0f}K"
        return f"${v:.0f}"

    @st.fragment(run_every=30 if auto_refresh else None)
    def _live_markets():
        from datetime import datetime, timezone
        from src.polymarket import fetch_price_history

        try:
            opps, arbs = scan_markets(
                interval=interval, edge_threshold=0, on_progress=None
            )
        except Exception:
            opps, arbs = [], []

        if not opps:
            st.info(
                "No crypto prediction markets found right now. "
                "Markets may be inactive or APIs temporarily unreachable."
            )
            return

        # Track price history per market
        now = datetime.now(timezone.utc)
        for opp in opps:
            key = opp["id"] or opp["question"][:60]
            if key not in st.session_state["mkt_history"]:
                # Seed with Polymarket CLOB history if available
                seed: list[tuple[float, float]] = []
                tid = opp.get("clob_token_id")
                if tid:
                    raw = fetch_price_history(tid, interval="1w", fidelity=40)
                    seed = [(t, p * 100) for t, p in raw]
                st.session_state["mkt_history"][key] = seed
            st.session_state["mkt_history"][key].append(
                (now.timestamp(), opp["market_odds"])
            )
            st.session_state["mkt_history"][key] = st.session_state["mkt_history"][key][
                -120:
            ]

        # ── Arbitrage alerts ─────────────────────────────────────────────
        if arbs:
            for arb in arbs:
                t = arb.get("threshold")
                t_str = f"${t:,.0f}" if t else ""
                st.success(
                    f"**ARBITRAGE** {arb['symbol'].replace('USDT', '')} {t_str} — "
                    f"{arb['action']} → **{arb['guaranteed_profit']:.1f}¢ guaranteed profit**"
                )

        # ── Live Market cards — edge > 0.1% and volume > $500 ────────
        visible = [
            o
            for o in opps
            if o.get("volume", 0) >= 500
            and (abs(o["edge"]) > 0.1 or not o.get("threshold"))
        ]

        st.markdown(f"#### Live Markets ({len(visible)})")
        for row_start in range(0, len(visible), 2):
            cols = st.columns(2)
            for col_idx, opp in enumerate(visible[row_start : row_start + 2]):
                with cols[col_idx]:
                    _render_market_card(opp)

        # ── Strategy Signals ─────────────────────────────────────────────
        tracked = list({o["symbol"] for o in opps})
        strat_signals = run_all_strategies(tracked, interval)

        if strat_signals:
            st.divider()
            st.markdown("#### Strategy Signals")
            for row_start in range(0, len(strat_signals), 3):
                scols = st.columns(min(3, len(strat_signals) - row_start))
                for ci, sig in enumerate(strat_signals[row_start : row_start + 3]):
                    with scols[ci]:
                        d = sig["direction"]
                        icon = {"bullish": "🟢", "bearish": "🔴", "neutral": "🟡"}.get(
                            d, "⚪"
                        )
                        with st.container(border=True):
                            st.markdown(
                                f"{icon} **{sig['strategy']}** — "
                                f"{sig['symbol'].replace('USDT', '')}"
                            )
                            st.metric(
                                "Strength", f"{sig['strength']}%", sig["direction"]
                            )
                            st.caption(sig["prediction"])
                            for detail in sig["details"][:3]:
                                st.caption(f"· {detail}")

    def _market_url(opp: dict) -> str:
        if opp["platform"] == "Polymarket":
            slug = opp.get("slug") or opp.get("id", "")
            return f"https://polymarket.com/event/{slug}"

    def _render_market_card(opp: dict) -> None:
        edge_val = opp["edge"]
        odds = opp["market_odds"]
        odds_color = "#00e676" if odds >= 50 else "#ff1744"
        url = _market_url(opp)

        # Platform badge styling
        if opp["platform"] == "Polymarket":
            badge_color = "#4a6cf7"
            badge_icon = "◆"
        else:
            badge_color = "#00b4d8"
            badge_icon = "◆"

        with st.container(border=True):
            # Question (clickable)
            st.markdown(
                f'<a href="{url}" target="_blank" style="color: inherit; text-decoration: none;">'
                f'<span style="font-weight: 600; font-size: 0.92rem; line-height: 1.4;">'
                f"{opp['question']}</span></a>",
                unsafe_allow_html=True,
            )

            # Big chance % + edge badge
            if abs(edge_val) >= 1:
                e_color = "#00e676" if edge_val > 0 else "#ff1744"
                e_label = opp["action"]
                edge_html = (
                    f'<span style="background:{e_color}22; color:{e_color}; '
                    f"padding: 2px 10px; border-radius: 8px; font-size: 0.78rem; "
                    f'font-weight: 600; margin-left: 12px;">'
                    f"{edge_val:+.1f}% {e_label}</span>"
                )
            elif opp.get("threshold"):
                edge_html = (
                    '<span style="background:rgba(255,255,255,0.06); color:rgba(255,255,255,0.4); '
                    "padding: 2px 10px; border-radius: 8px; font-size: 0.78rem; "
                    'font-weight: 500; margin-left: 12px;">~0% edge</span>'
                )
            else:
                edge_html = (
                    '<span style="background:rgba(255,255,255,0.06); color:rgba(255,255,255,0.35); '
                    "padding: 2px 10px; border-radius: 8px; font-size: 0.78rem; "
                    'font-weight: 500; margin-left: 12px;">no model</span>'
                )

            st.markdown(
                f'<div style="margin: 8px 0 4px;">'
                f'<span style="font-size: 1.8rem; font-weight: 700; color: {odds_color};">'
                f"{odds:.0f}%</span>"
                f'<span style="font-size: 0.82rem; color: rgba(255,255,255,0.45); '
                f'margin-left: 6px; font-weight: 500;">Chance</span>'
                f"{edge_html}"
                f"</div>",
                unsafe_allow_html=True,
            )

            # Sparkline
            key = opp["id"] or opp["question"][:60]
            history = st.session_state.get("mkt_history", {}).get(key, [])
            if len(history) >= 2:
                from datetime import datetime, timezone

                times = [datetime.fromtimestamp(t, tz=timezone.utc) for t, _ in history]
                prices = [p for _, p in history]
                first_p, last_p = prices[0], prices[-1]
                line_color = "#00e676" if last_p >= first_p else "#ff1744"
                fill_color = (
                    "rgba(0,230,118,0.08)"
                    if last_p >= first_p
                    else "rgba(255,23,68,0.08)"
                )
                fig = go.Figure()
                fig.add_trace(
                    go.Scatter(
                        x=times,
                        y=prices,
                        mode="lines",
                        line=dict(color=line_color, width=2),
                        fill="tozeroy",
                        fillcolor=fill_color,
                        showlegend=False,
                    )
                )
                fig.update_layout(
                    height=65,
                    margin=dict(l=0, r=0, t=0, b=0),
                    xaxis=dict(visible=False),
                    yaxis=dict(visible=False),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig, width="stretch")

            # Footer row: vol + time left + price | platform watermark
            st.markdown(
                f'<div style="display: flex; justify-content: space-between; '
                f"align-items: center; margin-top: 6px; padding-top: 8px; "
                f'border-top: 1px solid rgba(255,255,255,0.06);">'
                # Left side — stats
                f'<div style="display: flex; gap: 14px; font-size: 0.75rem; '
                f'color: rgba(255,255,255,0.4); font-weight: 500;">'
                f"<span>${opp['current_price']:,.2f}</span>"
                f"<span>{_fmt_vol(opp['volume'])} VOL</span>"
                f"<span>{_fmt_time(opp['hours_left'])}</span>"
                f"</div>"
                # Right side — platform watermark
                f'<a href="{url}" target="_blank" style="text-decoration: none;">'
                f'<span style="color: {badge_color}; font-size: 0.78rem; font-weight: 600; '
                f'letter-spacing: 0.3px;">'
                f"{badge_icon} {opp['platform']}</span></a>"
                f"</div>",
                unsafe_allow_html=True,
            )

            # Signals line (only for markets with model estimates)
            if opp["signals"]:
                threshold_str = (
                    f"${opp['threshold']:,.0f}" if opp.get("threshold") else ""
                )
                st.caption(
                    f"{threshold_str} target · "
                    + " · ".join(opp["signals"])
                    + f" · {opp['confidence']}% confidence"
                )

    _live_markets()
