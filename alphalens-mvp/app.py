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
from src.metric_tooltip import render_metric_with_tooltip
from src.ws_client import BinanceKlineStream
from src.orderbook import BinanceOrderBookStream
from src.history import fetch_historical_klines
from src.agent import run_agent

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
    "get_prediction_accuracy": "📊 Checking Polymarket accuracy data",
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

SCANNER_COIN_OPTIONS = [
    "All",
    "BTC",
    "ETH",
    "SOL",
    "BNB",
    "XRP",
    "DOGE",
    "ADA",
    "AVAX",
    "LINK",
    "DOT",
    "UNI",
    "NEAR",
    "ARB",
    "SUI",
    "APT",
    "PEPE",
    "TON",
    "TIA",
]

SCANNER_TIME_OPTIONS = ["All", "Today", "This Week", "This Month", "Long-term"]
_DASH_INTERVAL_OPTS = ["1m", "3m", "5m"]


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


def _report_to_pdf_bytes(report_text: str, symbol: str) -> bytes:
    """Convert markdown-like report text to a professional PDF."""
    from fpdf import FPDF
    from datetime import datetime, timezone

    DARK, ACCENT, WHITE = (13, 15, 18), (245, 158, 11), (255, 255, 255)
    GRAY, BODY, BORDER = (140, 140, 140), (50, 50, 50), (220, 220, 220)
    M = 25
    now_str = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")

    def _safe(text: str) -> str:
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"__([^_]+)__", r"\1", text)
        text = re.sub(r"_([^_]+)_", r"\1", text)
        return text.encode("latin-1", errors="ignore").decode("latin-1")

    class ReportPDF(FPDF):
        def header(self):
            if self.page_no() == 1:
                self.set_fill_color(*DARK)
                self.rect(0, 0, 210, 46, style="F")
                self.set_fill_color(*ACCENT)
                self.rect(0, 46, 210, 1.5, style="F")
                self.set_xy(M, 10)
                self.set_text_color(*WHITE)
                self.set_font("Helvetica", style="B", size=20)
                self.cell(w=0, h=8, text="AlphaLens Research Report")
                self.set_xy(M, 22)
                self.set_font("Helvetica", style="B", size=26)
                self.cell(w=0, h=10, text=_safe(symbol))
                self.set_xy(M, 36)
                self.set_text_color(170, 170, 170)
                self.set_font("Helvetica", size=8)
                self.cell(w=0, h=5, text=_safe(f"Generated {now_str}  |  Binance  CoinGecko  DefiLlama  Polymarket"))
                self.set_y(52)
                self.set_font("Helvetica", style="I", size=7)
                self.set_text_color(*GRAY)
                self.set_x(M)
                self.multi_cell(w=210 - 2 * M, h=4, text=_safe("For research purposes only. Not financial advice. AI-generated content."))
                self.ln(4)
            else:
                self.set_y(15)

        def footer(self):
            self.set_y(-14)
            self.set_draw_color(*BORDER)
            self.set_line_width(0.2)
            self.line(M, self.get_y(), 210 - M, self.get_y())
            self.ln(2)
            self.set_font("Helvetica", size=7)
            self.set_text_color(*GRAY)
            cw = 210 - 2 * M
            self.set_x(M)
            self.cell(w=cw / 2, h=4, text="AlphaLens")
            self.cell(w=cw / 2, h=4, text=f"Page {self.page_no()}", align="R")

    pdf = ReportPDF()
    pdf.set_margins(left=M, top=15, right=M)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    cw = 210 - 2 * M

    for raw_line in report_text.splitlines():
        line = raw_line.strip()
        if not line:
            pdf.ln(2)
            continue

        if line.startswith("### "):
            pdf.ln(2)
            pdf.set_font("Helvetica", style="B", size=10.5)
            pdf.set_text_color(*DARK)
            pdf.set_x(M)
            pdf.multi_cell(w=cw, h=5.5, text=_safe(line[4:]))
            pdf.ln(1)
        elif line.startswith("## "):
            pdf.ln(4)
            pdf.set_draw_color(*ACCENT)
            pdf.set_line_width(0.4)
            pdf.line(M, pdf.get_y(), M + cw, pdf.get_y())
            pdf.ln(2.5)
            pdf.set_font("Helvetica", style="B", size=13)
            pdf.set_text_color(*DARK)
            pdf.set_x(M)
            pdf.multi_cell(w=cw, h=6.5, text=_safe(line[3:]))
            pdf.ln(1.5)
        elif line.startswith("# "):
            pdf.set_font("Helvetica", style="B", size=15)
            pdf.set_text_color(*DARK)
            pdf.set_x(M)
            pdf.multi_cell(w=cw, h=7, text=_safe(line[2:]))
            pdf.ln(2)
        elif line.startswith(("- ", "* ")):
            pdf.set_font("Helvetica", size=9.5)
            pdf.set_text_color(*BODY)
            pdf.set_x(M + 4)
            pdf.multi_cell(w=cw - 4, h=5, text="- " + _safe(line[2:]))
        else:
            pdf.set_font("Helvetica", size=9.5)
            pdf.set_text_color(*BODY)
            pdf.set_x(M)
            pdf.multi_cell(w=cw, h=5, text=_safe(line))

    return bytes(pdf.output())


# ── Page config ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AlphaLens — Crypto Research Agent",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Theme definitions ─────────────────────────────────────────────────────────────
# Inspired by: Artemis.ai, CoinGlass, Linear, Bloomberg
THEMES = {
    "Studio": {
        "bg": "#0d0f12",
        "sidebar": "#111418",
        "card": "#151820",
        "border": "#1f2937",
        "border_subtle": "#1a1f2b",
        "accent": "#f59e0b",
        "accent_hover": "#fbbf24",
        "accent_text": "#fcd34d",
        "label": "#6b7280",
        "text": "#d1d5db",
        "text_muted": "#9ca3af",
        "chat_bg": "#151820",
        "chat_text": "#d1d5db",
        "code_bg": "#0d0f12",
        "green": "#22c55e",
        "red": "#ef4444",
        "radius": "6px",
    },
    "Studio Light": {
        "bg": "#ffffff",
        "sidebar": "#f9fafb",
        "card": "#ffffff",
        "border": "#e5e7eb",
        "border_subtle": "#f3f4f6",
        "accent": "#d97706",
        "accent_hover": "#b45309",
        "accent_text": "#92400e",
        "label": "#6b7280",
        "text": "#111827",
        "text_muted": "#6b7280",
        "chat_bg": "#f9fafb",
        "chat_text": "#111827",
        "code_bg": "#f3f4f6",
        "green": "#16a34a",
        "red": "#dc2626",
        "radius": "6px",
    },
    "Artemis": {
        "bg": "#09090b",
        "sidebar": "#0c0c0f",
        "card": "#111113",
        "border": "#1e1e22",
        "border_subtle": "#18181b",
        "accent": "#6366f1",
        "accent_hover": "#818cf8",
        "accent_text": "#a5b4fc",
        "label": "#71717a",
        "text": "#e4e4e7",
        "text_muted": "#a1a1aa",
        "chat_bg": "#131316",
        "chat_text": "#e4e4e7",
        "code_bg": "#0c0c0f",
        "green": "#10b981",
        "red": "#ef4444",
        "radius": "8px",
    },
    "Terminal": {
        "bg": "#010409",
        "sidebar": "#0d1117",
        "card": "#0d1117",
        "border": "#21262d",
        "border_subtle": "#161b22",
        "accent": "#22ab94",
        "accent_hover": "#2dd4a8",
        "accent_text": "#6ee7b7",
        "label": "#7d8590",
        "text": "#c9d1d9",
        "text_muted": "#7d8590",
        "chat_bg": "#0d1117",
        "chat_text": "#c9d1d9",
        "code_bg": "#010409",
        "green": "#22ab94",
        "red": "#f23645",
        "radius": "6px",
    },
    "Minimal": {
        "bg": "#000000",
        "sidebar": "#0a0a0a",
        "card": "#0a0a0a",
        "border": "#1a1a1a",
        "border_subtle": "#141414",
        "accent": "#ffffff",
        "accent_hover": "#e5e5e5",
        "accent_text": "#e5e5e5",
        "label": "#666666",
        "text": "#ededed",
        "text_muted": "#888888",
        "chat_bg": "#0a0a0a",
        "chat_text": "#ededed",
        "code_bg": "#050505",
        "green": "#00c853",
        "red": "#ff3d00",
        "radius": "8px",
    },
}


def _inject_theme(t: dict) -> None:
    """Inject professional CSS — no gradients, no glow, just clean spacing."""
    r = t["radius"]
    is_light = t["bg"] in ("#ffffff", "#f9fafb", "#fafafa")
    btn_text = (
        "#fff"
        if is_light
        else ("#000" if t["accent"] in ("#ffffff", "#f59e0b") else "#fff")
    )
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        .stApp {{ background: {t["bg"]}; font-family: 'Inter', -apple-system, sans-serif; }}

        /* Sidebar */
        section[data-testid="stSidebar"] {{
            background: {t["sidebar"]};
            border-right: 1px solid {t["border_subtle"]};
        }}
        section[data-testid="stSidebar"] * {{ color: {t["text_muted"]} !important; }}
        section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3, section[data-testid="stSidebar"] strong {{
            color: {t["text"]} !important;
        }}
        section[data-testid="stSidebar"] .stCaption, section[data-testid="stSidebar"] small {{
            color: {t["label"]} !important;
        }}
        section[data-testid="stSidebar"] [data-baseweb="select"] * {{
            color: {t["text"]} !important; background-color: {t["card"]} !important;
        }}
        section[data-testid="stSidebar"] button {{
            background: {t["card"]} !important; color: {t["text_muted"]} !important;
            border: 1px solid {t["border"]} !important; border-radius: {r} !important;
            font-size: 0.78rem !important;
        }}
        section[data-testid="stSidebar"] button:hover {{ border-color: {t["accent"]} !important; }}
        section[data-testid="stSidebar"] button *, section[data-testid="stSidebar"] button span {{
            color: {t["text_muted"]} !important; background: transparent !important;
        }}

        /* Metrics */
        [data-testid="stMetric"] {{
            background: {t["card"]}; border: 1px solid {t["border"]};
            border-radius: {r}; padding: 16px 20px 12px;
        }}
        [data-testid="stMetricLabel"] {{
            font-size: 0.7rem !important; font-weight: 500 !important;
            color: {t["label"]} !important; text-transform: uppercase; letter-spacing: 0.06em;
        }}
        [data-testid="stMetricValue"] {{
            font-size: 1.4rem !important; font-weight: 600 !important;
            color: {t["text"]} !important; font-variant-numeric: tabular-nums;
        }}
        [data-testid="stMetricDelta"] {{ font-size: 0.78rem !important; font-weight: 500 !important; }}
        [data-testid="stMetricDelta"] svg {{ display: none; }}

        /* Metric help icon (native st.metric help=) — subtle, matches prior “i” intent */
        [data-testid="stMetric"] [data-testid="stMetricLabel"] button {{
            color: #6b7280 !important;
        }}
        [data-testid="stMetric"] [data-testid="stMetricLabel"] button:hover {{
            color: {t["text"]} !important;
        }}

        /* Tabs — clean underline style */
        .stTabs [data-baseweb="tab-list"] {{
            gap: 0; background: transparent; border-radius: 0;
            padding: 0; border: none; border-bottom: 1px solid {t["border"]};
        }}
        .stTabs [data-baseweb="tab"] {{
            border-radius: 0; padding: 10px 20px; font-weight: 500;
            font-size: 0.84rem; color: {t["text_muted"]}; letter-spacing: 0;
        }}
        .stTabs [aria-selected="true"] {{
            background: transparent !important; color: {t["text"]} !important;
            border-bottom: 2px solid {t["accent"]} !important;
        }}
        .stTabs [data-baseweb="tab-highlight"] {{ display: none; }}
        .stTabs [data-baseweb="tab-border"] {{ display: none; }}

        /* Expanders */
        .streamlit-expanderHeader {{
            background: {t["card"]} !important; border-radius: {r} !important;
            border: 1px solid {t["border"]} !important; font-weight: 500 !important;
        }}

        /* Dataframes */
        [data-testid="stDataFrame"] {{
            border-radius: {r}; overflow: hidden; border: 1px solid {t["border"]};
        }}

        /* Dividers */
        hr {{ border-color: {t["border_subtle"]} !important; }}

        /* Chat */
        [data-testid="stChatMessage"] {{
            background: {t["chat_bg"]}; border: 1px solid {t["border"]};
            border-radius: {r}; padding: 16px 20px; margin-bottom: 8px;
        }}
        [data-testid="stChatMessage"] *:not(svg):not(path) {{ color: {t["chat_text"]} !important; }}
        [data-testid="stChatMessage"] h1, [data-testid="stChatMessage"] h2,
        [data-testid="stChatMessage"] h3, [data-testid="stChatMessage"] strong {{
            color: {t["text"]} !important; font-weight: 600 !important;
        }}
        [data-testid="stChatMessage"] code {{
            color: {t["accent_text"]} !important; background: {t["code_bg"]} !important;
            border-radius: 4px; padding: 2px 5px; font-size: 0.85em;
        }}
        [data-testid="stChatMessage"] pre {{
            background: {t["code_bg"]} !important; border-radius: {r};
            padding: 12px 16px; border: 1px solid {t["border_subtle"]};
        }}
        [data-testid="stChatMessage"] pre code {{ color: {t["chat_text"]} !important; background: transparent !important; padding: 0; }}
        [data-testid="stChatMessage"] blockquote {{ border-left: 2px solid {t["border"]}; padding-left: 12px; margin-left: 0; }}
        [data-testid="stChatMessage"] a {{ color: {t["accent_text"]} !important; }}
        .stChatInputContainer {{
            border-color: {t["border"]} !important; border-radius: {r} !important;
            background: {t["card"]} !important;
        }}
        .stChatInputContainer textarea {{ color: {t["text"]} !important; }}

        /* Scrollbar */
        [data-testid="stVerticalBlockBorderWrapper"] {{ scrollbar-width: thin; scrollbar-color: {t["border"]} transparent; }}
        [data-testid="stVerticalBlockBorderWrapper"]::-webkit-scrollbar {{ width: 4px; }}
        [data-testid="stVerticalBlockBorderWrapper"]::-webkit-scrollbar-thumb {{ background: {t["border"]}; border-radius: 4px; }}

        /* Buttons */
        .stButton > button[kind="primary"] {{
            background: {t["accent"]}; color: {btn_text} !important;
            border: none; border-radius: {r}; font-weight: 600;
        }}
        .stButton > button[kind="primary"]:hover {{ background: {t["accent_hover"]}; }}

        /* Status badge */
        .status-bar {{
            display: inline-flex; align-items: center; gap: 8px;
            background: {t["card"]}; border: 1px solid {t["border"]};
            border-radius: 20px; padding: 5px 14px;
            font-size: 0.75rem; color: {t["text_muted"]}; font-weight: 500;
        }}
        .status-bar .dot {{
            width: 6px; height: 6px; border-radius: 50%;
            background: {t["green"]}; display: inline-block;
        }}
        .status-bar .dot.off {{ background: {t["red"]}; }}

        /* Containers with border — prediction market cards */
        [data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {{
            border-color: {t["border"]} !important;
            border-radius: {r} !important;
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
    st.session_state["conversations"] = []  # [{id, title, messages}]
if "active_conv_id" not in st.session_state:
    st.session_state["active_conv_id"] = None
if "active_tab" not in st.session_state:
    st.session_state["active_tab"] = "Dashboard"
if "dash_assets" not in st.session_state:
    st.session_state["dash_assets"] = ["BTCUSDT"]
if "dash_interval" not in st.session_state:
    st.session_state["dash_interval"] = "1m"
if "dash_lookback" not in st.session_state:
    st.session_state["dash_lookback"] = 100
if "auto_refresh" not in st.session_state:
    st.session_state["auto_refresh"] = True
if "scanner_coin_filter" not in st.session_state:
    st.session_state["scanner_coin_filter"] = ["All"]
if "scanner_time_filter" not in st.session_state:
    st.session_state["scanner_time_filter"] = "All"


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


# ── Sidebar (branding + theme) ─────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📈 AlphaLens")
    st.caption("AI-Powered Crypto Research Agent")
    st.divider()

    theme_name: str = st.selectbox(
        "Theme",
        list(THEMES.keys()),
        index=0,
        key="theme_select",
    )

_active_theme = THEMES[theme_name]
_inject_theme(_active_theme)
_is_light_theme = _active_theme["bg"] in ("#ffffff", "#f9fafb", "#fafafa")
_plotly_template = "plotly_white" if _is_light_theme else "plotly_dark"
_grid_color = "#e5e7eb" if _is_light_theme else "#2a2a2a"

# ════════════════════════════════════════════════════════════════════════════════
# TABS (main area — horizontal bar unchanged)
# ════════════════════════════════════════════════════════════════════════════════

tab_dashboard, tab_research, tab_scanner = st.tabs(
    [
        "📊 Dashboard",
        "💬 Chatbot",
        "🎯 Prediction Markets",
    ],
    on_change="rerun",
    key="alphalens_tabs",
)

if tab_dashboard.open:
    st.session_state["active_tab"] = "Dashboard"
elif tab_research.open:
    st.session_state["active_tab"] = "Chatbot"
elif tab_scanner.open:
    st.session_state["active_tab"] = "Prediction Markets"
else:
    st.session_state["active_tab"] = st.session_state.get("active_tab", "Dashboard")

# ── Sidebar (tab-specific controls + footer) ───────────────────────────────────
with st.sidebar:
    st.divider()
    _at = st.session_state.get("active_tab", "Dashboard")
    if _at == "Dashboard":
        st.multiselect(
            "Assets (up to 4)",
            AVAILABLE_SYMBOLS,
            default=["BTCUSDT"],
            max_selections=4,
            key="dash_assets",
        )
        _di = st.session_state.get("dash_interval", "1m")
        _di_ix = (
            _DASH_INTERVAL_OPTS.index(_di) if _di in _DASH_INTERVAL_OPTS else 0
        )
        st.selectbox(
            "Candle interval",
            _DASH_INTERVAL_OPTS,
            index=_di_ix,
            key="dash_interval",
        )
        st.slider(
            "Candles to display",
            min_value=20,
            max_value=500,
            value=int(st.session_state.get("dash_lookback", 100)),
            step=10,
            key="dash_lookback",
        )
        st.divider()
        st.toggle("Auto-refresh (5 s)", key="auto_refresh")
    elif _at == "Chatbot":
        st.markdown(
            "<div style='font-size:0.72rem; font-weight:700; letter-spacing:0.08em; "
            "color:rgba(255,255,255,0.4); margin-bottom:8px;'>CONVERSATIONS</div>",
            unsafe_allow_html=True,
        )

        has_messages = bool(st.session_state.get("chat_messages"))

        nc_col, cl_col = st.columns(2)
        with nc_col:
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
                    st.session_state["chat_messages"] = [
                        dict(m) for m in conv["messages"]
                    ]
                    st.session_state["active_conv_id"] = conv["id"]
                    st.rerun()
    elif _at == "Prediction Markets":
        st.toggle("Auto-refresh (5 s)", key="auto_refresh")
        st.multiselect(
            "Filter by coin",
            SCANNER_COIN_OPTIONS,
            default=["All"],
            key="scanner_coin_filter",
        )
        _tf = st.session_state.get("scanner_time_filter", "All")
        _tf_ix = (
            SCANNER_TIME_OPTIONS.index(_tf) if _tf in SCANNER_TIME_OPTIONS else 0
        )
        st.selectbox(
            "Time period",
            SCANNER_TIME_OPTIONS,
            index=_tf_ix,
            key="scanner_time_filter",
        )

    st.divider()
    st.caption("Data: Binance · CoinGecko · DefiLlama · Polymarket")
    st.caption("AI: GPT-4o / Gemini")

symbols = list(st.session_state.get("dash_assets") or ["BTCUSDT"])
if not symbols:
    symbols = ["BTCUSDT"]
interval = str(st.session_state.get("dash_interval", "1m"))
lookback = int(st.session_state.get("dash_lookback", 100))
auto_refresh = bool(st.session_state.get("auto_refresh", True))

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

# ════════════════════════════════════════════════════════════════════════════════
# TAB 1 — DASHBOARD (charts + order book)
# Fragment re-renders every 5s independently — chat and deep dive are untouched.
# ════════════════════════════════════════════════════════════════════════════════

with tab_dashboard:
    if tab_dashboard.open:
        st.session_state["active_tab"] = "Dashboard"
        _asset_title = " · ".join(symbols) if len(symbols) > 1 else primary
        st.markdown(f"### {_asset_title}")
        _dot_cls = "" if is_live else " off"
        _status_text = "Live" if is_live else "Disconnected"
        st.markdown(
            f'<div class="status-bar">'
            f'<span class="dot{_dot_cls}"></span> {_status_text}'
            f" &nbsp;·&nbsp; {interval} candles"
            f" &nbsp;·&nbsp; {lookback} loaded"
            f" &nbsp;·&nbsp; {len(symbols)} stream(s)"
            f"</div>",
            unsafe_allow_html=True,
        )

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
                render_metric_with_tooltip(
                    c1,
                    "Price (USDT)",
                    f"${latest['close']:,.2f}",
                    f"{dollar_chg:+,.2f} ({pct:+.2f}%)",
                )
                render_metric_with_tooltip(
                    c2,
                    "Period High",
                    f"${df['high'].max():,.2f}",
                )
                render_metric_with_tooltip(
                    c3,
                    "Period Low",
                    f"${df['low'].min():,.2f}",
                )
                render_metric_with_tooltip(
                    c4,
                    "Volume",
                    f"{df['volume'].sum():,.0f}",
                )

                # Row 2 — technical indicators
                rsi_val = latest.get("rsi")
                macd_val = latest.get("macd")
                sig_val = latest.get("macd_signal")
                bb_up = latest.get("bb_upper")
                bb_lo = latest.get("bb_lower")

                t1, t2, t3 = st.columns(3)
                render_metric_with_tooltip(
                    t1,
                    "RSI (14)",
                    f"{rsi_val:.1f}" if rsi_val and not pd.isna(rsi_val) else "—",
                    "overbought"
                    if (rsi_val and rsi_val > 70)
                    else "oversold"
                    if (rsi_val and rsi_val < 30)
                    else "neutral",
                )
                render_metric_with_tooltip(
                    t2,
                    "MACD",
                    f"{macd_val:.4f}" if macd_val and not pd.isna(macd_val) else "—",
                    "▲ bullish"
                    if (macd_val and sig_val and macd_val > sig_val)
                    else "▼ bearish",
                )
                if bb_up and bb_lo and not pd.isna(bb_up):
                    bw = bb_up - bb_lo
                    bpos = (latest["close"] - bb_lo) / bw * 100 if bw > 0 else 50
                    render_metric_with_tooltip(
                        t3,
                        "BB Position",
                        f"{bpos:.0f}%",
                        "near top"
                        if bpos > 80
                        else "near bottom"
                        if bpos < 20
                        else "mid-band",
                    )
                else:
                    render_metric_with_tooltip(t3, "BB Position", "—")

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
                    template=_plotly_template,
                    height=540,
                    margin=dict(l=0, r=0, t=40, b=0),
                    title=dict(
                        text=f"{primary} · {interval}  |  SMA20  SMA50  BB",
                        font=dict(size=14),
                    ),
                    xaxis=dict(showgrid=True, gridcolor=_grid_color),
                    yaxis=dict(title="Price (USDT)", showgrid=True, gridcolor=_grid_color),
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
                        template=_plotly_template,
                        height=420,
                        margin=dict(l=0, r=0, t=40, b=0),
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                        legend=dict(
                            orientation="h", yanchor="bottom", y=1.02, font=dict(size=11)
                        ),
                        showlegend=True,
                    )
                    fig_ind.update_yaxes(showgrid=True, gridcolor=_grid_color)
                    fig_ind.update_xaxes(showgrid=True, gridcolor=_grid_color)
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
                    template=_plotly_template,
                    height=360,
                    margin=dict(l=0, r=0, t=40, b=0),
                    title=dict(
                        text="Relative % Change (normalized to period start = 0%)",
                        font=dict(size=14),
                    ),
                    yaxis=dict(
                        title="% Change",
                        showgrid=True,
                        gridcolor=_grid_color,
                        ticksuffix="%",
                    ),
                    xaxis=dict(showgrid=True, gridcolor=_grid_color),
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
                                    template=_plotly_template,
                                    height=280,
                                    margin=dict(l=0, r=0, t=30, b=0),
                                    title=dict(text=sym, font=dict(size=13)),
                                    xaxis=dict(showgrid=False, showticklabels=False),
                                    yaxis=dict(
                                        showgrid=True,
                                        gridcolor=_grid_color,
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
                        template=_plotly_template,
                        height=300,
                        margin=dict(l=0, r=0, t=20, b=0),
                        xaxis=dict(
                            title="Price (USDT)", showgrid=True, gridcolor=_grid_color
                        ),
                        yaxis=dict(
                            title="Cumulative Volume", showgrid=True, gridcolor=_grid_color
                        ),
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                        legend=dict(orientation="h"),
                    )
                    st.plotly_chart(fig_depth, width="stretch")

        _dashboard()

# ════════════════════════════════════════════════════════════════════════════════
# TAB 2 — CHATBOT  (fragment so reruns never touch the active tab)
# ════════════════════════════════════════════════════════════════════════════════

with tab_research:
    if tab_research.open:
        st.session_state["active_tab"] = "Chatbot"

        @st.fragment
        def _chatbot(sym: str) -> None:
            """Isolated fragment — all reruns stay inside this tab."""
            api_key = (
                os.getenv("OPENAI_API_KEY")
                or os.getenv("gpt_api_key")
                or os.getenv("GEMINI_API_KEY")
            )

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
                for _mi, msg in enumerate(st.session_state["chat_messages"]):
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"].replace("$", r"\$"))
                        if msg["role"] == "assistant" and len(msg["content"]) > 100:
                            st.download_button(
                                "⬇️ Download PDF",
                                data=_report_to_pdf_bytes(msg["content"], sym),
                                file_name=f"alphalens-{sym.lower()}-{_mi}.pdf",
                                mime="application/pdf",
                                key=f"dl_hist_{_mi}",
                            )

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

            # ── Chat input ────────────────────────────────────────────────────────
            # Both chat_input and quick buttons live outside the fragment.
            # They store into _chat_user_input, consumed here on the next rerun.
            user_typed = st.session_state.pop("_chat_user_input", None)

            prompt_to_run = user_typed

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

                        st.markdown(response.replace("$", r"\$"))

                        if response and len(response) > 100:
                            _sym_safe = sym.lower()
                            _ts = pd.Timestamp.utcnow().strftime("%Y%m%d-%H%M%S")
                            _dl1, _dl2 = st.columns(2)
                            with _dl1:
                                st.download_button(
                                    "⬇️ Download PDF",
                                    data=_report_to_pdf_bytes(response, sym),
                                    file_name=f"alphalens-{_sym_safe}-{_ts}.pdf",
                                    mime="application/pdf",
                                    key=f"dl_pdf_{_ts}",
                                    use_container_width=True,
                                )
                            with _dl2:
                                st.download_button(
                                    "⬇️ Download Word",
                                    data=_report_to_docx_bytes(response, sym),
                                    file_name=f"alphalens-{_sym_safe}-{_ts}.docx",
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    key=f"dl_docx_{_ts}",
                                    use_container_width=True,
                                )

                    st.session_state["chat_messages"].append(
                        {"role": "assistant", "content": response}
                    )
                    _archive_current_chat()
                    st.rerun()

        _chatbot(primary.replace("USDT", ""))

        # Quick buttons + chat_input must live OUTSIDE the fragment (Streamlit 1.55+)
        from src.prompts.quick_prompts import QUICK_PROMPTS as _QP

        st.markdown(
            "<div style='margin:1rem 0 0.4rem; font-size:0.78rem; "
            "color:rgba(255,255,255,0.45); letter-spacing:0.06em;'>"
            "QUICK RESEARCH</div>",
            unsafe_allow_html=True,
        )
        _sym = primary.replace("USDT", "")
        _btn_cols = st.columns(len(_QP))
        for _i, (_label, _emoji, _tmpl) in enumerate(_QP):
            with _btn_cols[_i]:
                if st.button(
                    f"{_emoji} {_label}", use_container_width=True, key=f"qp_{_i}"
                ):
                    st.session_state["_chat_user_input"] = _tmpl.format(symbol=_sym)
                    st.rerun()

        _typed = st.chat_input(f"Ask about {_sym} or any crypto…")
        if _typed:
            st.session_state["_chat_user_input"] = _typed
            st.rerun()

# ════════════════════════════════════════════════════════════════════════════════
# TAB 4 — LIVE PREDICTION MARKETS
# ════════════════════════════════════════════════════════════════════════════════

with tab_scanner:
    if tab_scanner.open:
        st.session_state["active_tab"] = "Prediction Markets"
        st.markdown("### 🎯 Live Prediction Markets")
        st.caption("Auto-refreshing every 30s · Polymarket")

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
            from collections import defaultdict
            from src.polymarket import fetch_crypto_markets

            coin_filter = st.session_state.get("scanner_coin_filter", ["All"])
            time_filter = st.session_state.get("scanner_time_filter", "All")

            def _hours_until(expiry):
                if expiry is None:
                    return 168.0
                delta = (expiry - datetime.now(timezone.utc)).total_seconds() / 3600
                return max(0, delta)

            try:
                raw_markets = fetch_crypto_markets()
            except Exception:
                raw_markets = []

            # Only keep markets for coins in our tracked asset list
            tracked_symbols = set(AVAILABLE_SYMBOLS)
            markets = []
            for m in raw_markets:
                if m["symbol"] not in tracked_symbols:
                    continue
                vol = m.get("volume", 0)
                if vol < 10_000:
                    continue
                odds = m["yes_price"] * 100
                hours = _hours_until(m.get("expiry"))
                markets.append(
                    {
                        "id": m.get("id", ""),
                        "question": m["question"],
                        "symbol": m["symbol"],
                        "market_odds": round(odds, 1),
                        "volume": vol,
                        "liquidity": m.get("liquidity", 0),
                        "hours_left": round(hours, 1),
                        "slug": m.get("slug", ""),
                        "clob_token_id": m.get("clob_token_id"),
                        "threshold": m.get("threshold"),
                        "direction": m.get("direction", "above"),
                        "event_id": m.get("event_id", ""),
                        "event_title": m.get("event_title", ""),
                    }
                )

            if not markets:
                st.info(
                    "No crypto prediction markets with >$10K volume found. "
                    "Markets may be inactive or APIs temporarily unreachable."
                )
                return

            # Track current odds for all markets (cheap — no HTTP calls)
            now = datetime.now(timezone.utc)
            for mkt in markets:
                key = mkt["id"] or mkt["question"][:60]
                if key not in st.session_state["mkt_history"]:
                    st.session_state["mkt_history"][key] = []
                st.session_state["mkt_history"][key].append(
                    (now.timestamp(), mkt["market_odds"])
                )
                st.session_state["mkt_history"][key] = st.session_state["mkt_history"][key][
                    -120:
                ]

            # ── Filter by coin ────────────────────────────────────────────────
            selected_coins = coin_filter if coin_filter else ["All"]
            if "All" not in selected_coins:
                filter_pairs = {c + "USDT" for c in selected_coins}
                visible = [m for m in markets if m["symbol"] in filter_pairs]
            else:
                visible = list(markets)

            # ── Filter by time period ─────────────────────────────────────────
            if time_filter != "All":
                time_ranges = {
                    "Today": 24,
                    "This Week": 168,
                    "This Month": 744,
                    "Long-term": float("inf"),
                }
                max_h = time_ranges[time_filter]
                if time_filter == "Long-term":
                    visible = [m for m in visible if m["hours_left"] > 744]
                else:
                    prev_max = {"Today": 0, "This Week": 24, "This Month": 168}[time_filter]
                    visible = [m for m in visible if prev_max < m["hours_left"] <= max_h]

            # ── Sort by volume (highest first) ────────────────────────────────
            visible.sort(key=lambda o: o.get("volume", 0), reverse=True)

            # ── Summary stats ─────────────────────────────────────────────────
            total_vol = sum(o.get("volume", 0) for o in visible)
            coins_in_view = sorted(
                {
                    o["symbol"].replace("USDT", "")
                    for o in visible
                    if o["symbol"] != "CRYPTOUSDT"
                }
            )
            s1, s2, s3 = st.columns(3)
            s1.metric("Markets", len(visible))
            s2.metric("Total Volume", _fmt_vol(total_vol))
            s3.metric("Coins", " · ".join(coins_in_view) if coins_in_view else "—")

            # ── Implied price range summary ────────────────────────────────────
            coin_targets: dict[str, list[dict]] = defaultdict(list)
            for mkt in visible:
                if mkt.get("threshold") and mkt["symbol"] != "CRYPTOUSDT":
                    coin_targets[mkt["symbol"]].append(mkt)

            if coin_targets:
                from datetime import datetime, timedelta, timezone as _tz

                _now = datetime.now(_tz.utc)

                lines = []
                for sym_key in sorted(
                    coin_targets,
                    key=lambda s: sum(m["volume"] for m in coin_targets[s]),
                    reverse=True,
                )[:4]:
                    coin_name = sym_key.replace("USDT", "")
                    targets = coin_targets[sym_key]

                    # Group by event (= same resolution date), pick highest-volume event
                    by_event: dict[str, list[dict]] = defaultdict(list)
                    for t in targets:
                        eid = t.get("event_id") or "unknown"
                        by_event[eid].append(t)
                    top_event = max(
                        by_event.values(), key=lambda g: sum(m["volume"] for m in g)
                    )

                    # Pick the market with the highest probability
                    best = max(top_event, key=lambda t: t["market_odds"])

                    # Resolution date
                    h = best["hours_left"]
                    exp_dt = _now + timedelta(hours=h)
                    by_when = exp_dt.strftime("by %b %d")

                    lines.append(
                        f"**{coin_name}**: {best['market_odds']:.0f}% chance "
                        f"{best['direction']} ${best['threshold']:,.0f} {by_when}"
                    )

                if lines:
                    st.markdown(
                        '<div style="background:rgba(124,131,253,0.06);border:1px solid rgba(124,131,253,0.12);'
                        'border-radius:10px;padding:12px 16px;margin-bottom:16px;">'
                        '<div style="font-size:0.72rem;font-weight:600;color:rgba(255,255,255,0.4);'
                        'letter-spacing:0.08em;margin-bottom:6px;">MARKET CONSENSUS</div>'
                        + "<br>".join(lines)
                        + "</div>",
                        unsafe_allow_html=True,
                    )

            # ── Event grouping — top 2 by volume get histogram ─────────────────
            event_groups: dict[str, list[dict]] = defaultdict(list)
            for mkt in visible:
                eid = mkt.get("event_id")
                if eid and mkt.get("threshold"):
                    event_groups[eid].append(mkt)

            sorted_events = sorted(
                event_groups.items(),
                key=lambda x: sum(m["volume"] for m in x[1]),
                reverse=True,
            )
            histogram_ids: set[str] = set()
            histogram_count = 0
            for eid, group in sorted_events:
                if len(group) >= 3 and histogram_count < 2:
                    histogram_count += 1
                    histogram_ids.add(eid)
                    _render_event_group(group)

            # ── Sparkline cards (skip markets already in histograms) ──────────
            card_mkts = [m for m in visible if m.get("event_id", "") not in histogram_ids]
            for row_start in range(0, len(card_mkts), 2):
                cols = st.columns(2)
                for col_idx, mkt in enumerate(card_mkts[row_start : row_start + 2]):
                    with cols[col_idx]:
                        _render_market_card(mkt)

        def _render_event_group(group: list[dict]) -> None:
            """Render a price-target event as a distribution chart."""
            title = group[0].get("event_title") or group[0]["question"][:50]
            coin = group[0]["symbol"].replace("USDT", "")
            total_vol = sum(m["volume"] for m in group)
            direction = group[0].get("direction", "above")

            # Sort by threshold
            sorted_g = sorted(group, key=lambda m: m["threshold"] or 0)

            with st.container(border=True):
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:10px;">'
                    f'<span style="background:rgba(124,131,253,0.15);color:#a5abff;'
                    f'padding:2px 8px;border-radius:6px;font-size:0.72rem;font-weight:700;">{coin}</span>'
                    f'<span style="font-weight:600;font-size:0.95rem;">{title}</span>'
                    f'<span style="color:rgba(255,255,255,0.35);font-size:0.75rem;margin-left:auto;">'
                    f"{_fmt_vol(total_vol)} vol · {len(group)} markets · "
                    f'<span style="color:#2E5CFF;">Polymarket</span></span>'
                    f"</div>",
                    unsafe_allow_html=True,
                )

                # Bar chart — probability at each strike
                labels = []
                probs = []
                colors = []
                for m in sorted_g:
                    t = m["threshold"]
                    if t >= 1000:
                        labels.append(f"${t / 1000:.0f}K")
                    else:
                        labels.append(f"${t:,.0f}")
                    p = m["market_odds"]
                    probs.append(p)
                    colors.append(
                        "#00e676" if p >= 50 else "#ff1744" if p < 20 else "#ff9800"
                    )

                fig = go.Figure()
                fig.add_trace(
                    go.Bar(
                        x=labels,
                        y=probs,
                        marker_color=colors,
                        text=[f"{p:.0f}%" for p in probs],
                        textposition="outside",
                        textfont=dict(color="rgba(255,255,255,0.7)", size=11),
                        hovertemplate="%{x}: %{y:.1f}%<extra></extra>",
                    )
                )
                fig.update_layout(
                    height=200,
                    margin=dict(l=0, r=0, t=10, b=0),
                    xaxis=dict(
                        showgrid=False,
                        color="rgba(255,255,255,0.5)",
                        tickfont=dict(size=11),
                    ),
                    yaxis=dict(
                        visible=False, range=[0, max(probs) * 1.25] if probs else [0, 100]
                    ),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    dragmode=False,
                )
                fig.update_xaxes(fixedrange=True)
                fig.update_yaxes(fixedrange=True)
                st.plotly_chart(
                    fig,
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key=f"hist_{group[0]['event_id']}",
                )

        def _render_market_card(opp: dict) -> None:
            odds = opp["market_odds"]
            odds_color = "#00e676" if odds >= 50 else "#ff1744"
            coin = opp["symbol"].replace("USDT", "")

            with st.container(border=True):
                # Header: coin badge + question
                st.markdown(
                    f'<div style="display:flex;align-items:flex-start;gap:10px;">'
                    f'<span style="background:rgba(124,131,253,0.15);color:#a5abff;'
                    f"padding:2px 8px;border-radius:6px;font-size:0.72rem;"
                    f'font-weight:700;letter-spacing:0.5px;white-space:nowrap;margin-top:2px;">{coin}</span>'
                    f'<span style="font-weight:600;font-size:0.92rem;line-height:1.4;">'
                    f"{opp['question']}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                # Probability + change (lazy-seed price history on first render)
                key = opp["id"] or opp["question"][:60]
                history = st.session_state.get("mkt_history", {}).get(key, [])
                if len(history) <= 1 and opp.get("clob_token_id"):
                    from src.polymarket import fetch_price_history

                    raw = fetch_price_history(
                        opp["clob_token_id"], interval="1w", fidelity=40
                    )
                    seed = [(t, p * 100) for t, p in raw]
                    if seed:
                        st.session_state["mkt_history"][key] = seed + history
                        history = st.session_state["mkt_history"][key]
                change_html = ""
                if len(history) >= 2:
                    first_p, last_p = history[0][1], history[-1][1]
                    delta = last_p - first_p
                    if abs(delta) >= 0.1:
                        d_color = "#00e676" if delta > 0 else "#ff1744"
                        d_arrow = "+" if delta > 0 else ""
                        change_html = (
                            f'<span style="font-size:0.82rem;font-weight:600;color:{d_color};'
                            f'margin-left:10px;">{d_arrow}{delta:.1f}%</span>'
                        )

                st.markdown(
                    f'<div style="margin:8px 0 2px;">'
                    f'<span style="font-size:1.8rem;font-weight:700;color:{odds_color};">'
                    f"{odds:.0f}%</span>"
                    f'<span style="font-size:0.82rem;color:rgba(255,255,255,0.45);'
                    f'margin-left:6px;font-weight:500;">Chance</span>'
                    f"{change_html}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                # Chart — Polymarket/Robinhood style
                if len(history) >= 2:
                    from datetime import datetime, timezone

                    times = [datetime.fromtimestamp(t, tz=timezone.utc) for t, _ in history]
                    prices = [p for _, p in history]
                    first_p, last_p = prices[0], prices[-1]
                    line_color = "#00e676" if last_p >= first_p else "#ff1744"
                    fill_top = (
                        "rgba(0,230,118,0.15)"
                        if last_p >= first_p
                        else "rgba(255,23,68,0.15)"
                    )

                    fig = go.Figure()
                    fig.add_trace(
                        go.Scatter(
                            x=times,
                            y=prices,
                            mode="none",
                            fill="tozeroy",
                            fillcolor=fill_top,
                            showlegend=False,
                            hoverinfo="skip",
                        )
                    )
                    fig.add_trace(
                        go.Scatter(
                            x=times,
                            y=prices,
                            mode="lines",
                            line=dict(
                                color=line_color, width=2.5, shape="spline", smoothing=1.0
                            ),
                            showlegend=False,
                            hovertemplate="%{y:.1f}%<extra></extra>",
                        )
                    )
                    fig.add_trace(
                        go.Scatter(
                            x=[times[-1]],
                            y=[prices[-1]],
                            mode="markers",
                            marker=dict(
                                color=line_color,
                                size=7,
                                line=dict(width=2, color="#0b0e14"),
                            ),
                            showlegend=False,
                            hoverinfo="skip",
                        )
                    )
                    y_min = max(0, min(prices) - 5)
                    y_max = min(100, max(prices) + 5)
                    fig.update_layout(
                        height=110,
                        margin=dict(l=0, r=0, t=0, b=0),
                        xaxis=dict(visible=False, showgrid=False),
                        yaxis=dict(
                            visible=False,
                            showgrid=False,
                            range=[y_min, y_max],
                            fixedrange=True,
                        ),
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                        hoverlabel=dict(
                            bgcolor="#1a1e2e",
                            bordercolor="rgba(255,255,255,0.1)",
                            font=dict(color="#fff", size=12),
                        ),
                        dragmode=False,
                    )
                    fig.update_xaxes(fixedrange=True)
                    st.plotly_chart(
                        fig,
                        use_container_width=True,
                        config={"displayModeBar": False},
                        key=f"spark_{opp['id']}",
                    )

                # Footer: volume · time left | platform watermark
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;'
                    f"align-items:center;margin-top:4px;padding-top:8px;"
                    f'border-top:1px solid rgba(255,255,255,0.06);">'
                    f'<div style="display:flex;gap:14px;font-size:0.75rem;'
                    f'color:rgba(255,255,255,0.4);font-weight:500;">'
                    f"<span>{_fmt_vol(opp['volume'])} vol</span>"
                    f"<span>{_fmt_time(opp['hours_left'])}</span>"
                    f"</div>"
                    f'<span style="font-size:0.68rem;color:rgba(255,255,255,0.25);font-weight:500;'
                    f'letter-spacing:0.03em;color:#2E5CFF;">Polymarket</span>'
                    f"</div>",
                    unsafe_allow_html=True,
                )

        _live_markets()
