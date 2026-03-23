"""
AlphaLens MVP
─────────────
Binance WebSocket (klines + order book)  →  SQLite  →  Streamlit  →  GPT-4o
"""

import os
import time

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from dotenv import load_dotenv

from src.database import init_db, get_klines
from src.ws_client import BinanceKlineStream
from src.orderbook import BinanceOrderBookStream
from src.history import fetch_historical_klines
from src.indicators import add_indicators
from src.llm_summary import summarize_trend

load_dotenv()

AVAILABLE_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT",
]

CHART_COLORS = ["#7c83fd", "#00e676", "#ff9800", "#e91e63"]

# ── Page config ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AlphaLens — Crypto Research",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── One-time DB init ─────────────────────────────────────────────────────────────
@st.cache_resource
def setup_db():
    init_db()

setup_db()

# ── Sidebar ──────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📈 AlphaLens")
    st.caption("Real-time crypto research · MVP")
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
    lookback: int = st.slider("Candles to display", min_value=20, max_value=500, value=100, step=10)

    st.divider()
    auto_refresh = st.toggle("Auto-refresh (5 s)", value=True)
    analyze_btn  = st.button("🤖  Analyze trend with AI", use_container_width=True)

    st.divider()
    st.caption("Data: Binance WebSocket + REST\nAI: GPT-4o")

primary = symbols[0]

# ── Historical data: fetch once per (symbol, interval) ──────────────────────────
if "history_loaded" not in st.session_state:
    st.session_state["history_loaded"] = set()

for sym in symbols:
    hist_key = f"hist_{sym}_{interval}"
    if hist_key not in st.session_state["history_loaded"]:
        with st.spinner(f"Loading 500 historical candles for {sym}…"):
            fetch_historical_klines(sym, interval, limit=500)
        st.session_state["history_loaded"].add(hist_key)

# ── Kline WebSocket streams: one per selected (symbol, interval) ─────────────────
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

# ── Order book stream: primary symbol only ───────────────────────────────────────
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

# ── Load kline data + compute indicators for all selected symbols ─────────────────
all_klines: dict[str, list] = {}
all_dfs: dict[str, pd.DataFrame] = {}

for sym in symbols:
    klines = get_klines(sym, interval=interval, limit=lookback)
    all_klines[sym] = klines
    if klines:
        df = pd.DataFrame(
            klines, columns=["open_time", "open", "high", "low", "close", "volume"]
        )
        df["datetime"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df = add_indicators(df)
        all_dfs[sym] = df

# ── Page header ──────────────────────────────────────────────────────────────────
primary_stream = st.session_state.get(f"ks_{primary}_{interval}")
conn_badge = "🟢 Live" if (primary_stream and primary_stream.is_running) else "🔴 Disconnected"

title = " · ".join(symbols) if len(symbols) > 1 else primary
st.title(f"📈 {title}")
st.caption(f"{conn_badge}  ·  {interval} candles  ·  {lookback} loaded  ·  {len(symbols)} stream(s) active")

# ════════════════════════════════════════════════════════════════════════════════
# SECTION 1 — CHARTS
# ════════════════════════════════════════════════════════════════════════════════

if len(symbols) == 1:
    # ── Single symbol: metrics + candlestick + indicators ────────────────────
    df = all_dfs.get(primary)
    if df is None or df.empty:
        st.info("⏳ Waiting for candle data…")
        time.sleep(2)
        st.rerun()
    else:
        latest    = df.iloc[-1]
        earliest  = df.iloc[0]
        pct       = ((latest["close"] - earliest["close"]) / earliest["close"]) * 100
        dollar_chg = latest["close"] - earliest["close"]

        # Metric tiles — price + indicator snapshot
        c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
        c1.metric("Price (USDT)",  f"${latest['close']:,.4f}", f"{dollar_chg:+.4f} ({pct:+.2f}%)")
        c2.metric("Period High",   f"${df['high'].max():,.4f}")
        c3.metric("Period Low",    f"${df['low'].min():,.4f}")
        c4.metric("Volume",        f"{df['volume'].sum():,.0f}")
        rsi_val = latest.get("rsi")
        c5.metric("RSI (14)",
                  f"{rsi_val:.1f}" if rsi_val and not pd.isna(rsi_val) else "—",
                  "overbought" if (rsi_val and rsi_val > 70) else
                  "oversold"   if (rsi_val and rsi_val < 30) else "neutral")
        macd_val = latest.get("macd")
        sig_val  = latest.get("macd_signal")
        c6.metric("MACD",
                  f"{macd_val:.4f}" if macd_val and not pd.isna(macd_val) else "—",
                  "▲ bullish" if (macd_val and sig_val and macd_val > sig_val) else "▼ bearish")
        bb_up = latest.get("bb_upper")
        bb_lo = latest.get("bb_lower")
        if bb_up and bb_lo and not pd.isna(bb_up):
            bw   = bb_up - bb_lo
            bpos = (latest["close"] - bb_lo) / bw * 100 if bw > 0 else 50
            c7.metric("BB Position", f"{bpos:.0f}%",
                      "near top" if bpos > 80 else "near bottom" if bpos < 20 else "mid-band")
        else:
            c7.metric("BB Position", "—")

        # ── Main chart: Candlestick + SMA20 + SMA50 + Bollinger Bands + Volume ──
        fig = go.Figure()

        # Bollinger Bands (fill between upper and lower)
        fig.add_trace(go.Scatter(
            x=df["datetime"], y=df["bb_upper"],
            mode="lines", line=dict(color="rgba(255,200,0,0.3)", width=1),
            name="BB Upper", showlegend=True,
        ))
        fig.add_trace(go.Scatter(
            x=df["datetime"], y=df["bb_lower"],
            mode="lines", line=dict(color="rgba(255,200,0,0.3)", width=1),
            fill="tonexty", fillcolor="rgba(255,200,0,0.05)",
            name="BB Lower", showlegend=True,
        ))
        fig.add_trace(go.Scatter(
            x=df["datetime"], y=df["bb_mid"],
            mode="lines", line=dict(color="rgba(255,200,0,0.5)", width=1, dash="dot"),
            name="BB Mid", showlegend=False,
        ))

        # Candlesticks
        fig.add_trace(go.Candlestick(
            x=df["datetime"],
            open=df["open"], high=df["high"], low=df["low"], close=df["close"],
            name="Price",
            increasing_line_color="#00e676", decreasing_line_color="#ff1744",
            increasing_fillcolor="#00e676",  decreasing_fillcolor="#ff1744",
        ))

        # Moving averages
        fig.add_trace(go.Scatter(
            x=df["datetime"], y=df["sma_20"],
            mode="lines", line=dict(color="#7c83fd", width=1.5),
            name="SMA 20",
        ))
        fig.add_trace(go.Scatter(
            x=df["datetime"], y=df["sma_50"],
            mode="lines", line=dict(color="#ff9800", width=1.5),
            name="SMA 50",
        ))

        # Volume bars (secondary y-axis)
        fig.add_trace(go.Bar(
            x=df["datetime"], y=df["volume"],
            name="Volume", yaxis="y2",
            marker_color=[
                "rgba(0,230,118,0.2)" if c >= o else "rgba(255,23,68,0.2)"
                for o, c in zip(df["open"], df["close"])
            ],
        ))

        fig.update_layout(
            template="plotly_dark", height=540,
            margin=dict(l=0, r=0, t=40, b=0),
            title=dict(text=f"{primary} · {interval}  |  SMA20  SMA50  Bollinger Bands", font=dict(size=14)),
            xaxis=dict(showgrid=True, gridcolor="#2a2a2a"),
            yaxis=dict(title="Price (USDT)", showgrid=True, gridcolor="#2a2a2a"),
            yaxis2=dict(title="Volume", overlaying="y", side="right", showgrid=False),
            xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=11)),
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
        )
        st.plotly_chart(fig, use_container_width=True)

        # ── Technical indicator charts: RSI + MACD ───────────────────────────
        with st.expander("📊 Technical Indicators — RSI & MACD", expanded=True):
            fig_ind = make_subplots(
                rows=2, cols=1,
                shared_xaxes=True,
                row_heights=[0.5, 0.5],
                vertical_spacing=0.08,
                subplot_titles=("RSI (14)", "MACD (12, 26, 9)"),
            )

            # RSI
            fig_ind.add_trace(go.Scatter(
                x=df["datetime"], y=df["rsi"],
                mode="lines", line=dict(color="#7c83fd", width=2), name="RSI",
            ), row=1, col=1)
            fig_ind.add_hline(y=70, line_dash="dash", line_color="rgba(255,23,68,0.5)",
                              annotation_text="Overbought 70", row=1, col=1)
            fig_ind.add_hline(y=30, line_dash="dash", line_color="rgba(0,230,118,0.5)",
                              annotation_text="Oversold 30", row=1, col=1)
            fig_ind.add_hline(y=50, line_dash="dot",  line_color="rgba(255,255,255,0.15)",
                              row=1, col=1)

            # MACD histogram
            hist_colors = [
                "rgba(0,230,118,0.6)" if v >= 0 else "rgba(255,23,68,0.6)"
                for v in df["macd_hist"].fillna(0)
            ]
            fig_ind.add_trace(go.Bar(
                x=df["datetime"], y=df["macd_hist"],
                name="Histogram", marker_color=hist_colors, showlegend=True,
            ), row=2, col=1)
            fig_ind.add_trace(go.Scatter(
                x=df["datetime"], y=df["macd"],
                mode="lines", line=dict(color="#7c83fd", width=2), name="MACD",
            ), row=2, col=1)
            fig_ind.add_trace(go.Scatter(
                x=df["datetime"], y=df["macd_signal"],
                mode="lines", line=dict(color="#ff9800", width=1.5, dash="dot"), name="Signal",
            ), row=2, col=1)
            fig_ind.add_hline(y=0, line_color="rgba(255,255,255,0.15)", row=2, col=1)

            fig_ind.update_layout(
                template="plotly_dark", height=420,
                margin=dict(l=0, r=0, t=40, b=0),
                plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=11)),
                showlegend=True,
            )
            fig_ind.update_yaxes(showgrid=True, gridcolor="#2a2a2a")
            fig_ind.update_xaxes(showgrid=True, gridcolor="#2a2a2a")
            st.plotly_chart(fig_ind, use_container_width=True)

else:
    # ── Multi-symbol: metrics row + normalized comparison + mini charts ────────

    # Metrics: one tile per symbol
    metric_cols = st.columns(len(symbols))
    for i, sym in enumerate(symbols):
        df = all_dfs.get(sym)
        if df is not None and not df.empty:
            latest   = df.iloc[-1]
            earliest = df.iloc[0]
            pct = ((latest["close"] - earliest["close"]) / earliest["close"]) * 100
            metric_cols[i].metric(sym, f"${latest['close']:,.4f}", f"{pct:+.2f}%")
        else:
            metric_cols[i].metric(sym, "—", "loading…")

    # Normalized % change comparison chart
    fig_comp = go.Figure()
    for i, sym in enumerate(symbols):
        df = all_dfs.get(sym)
        if df is not None and not df.empty:
            base = df["close"].iloc[0]
            normalized = (df["close"] / base - 1) * 100
            fig_comp.add_trace(go.Scatter(
                x=df["datetime"], y=normalized,
                mode="lines", name=sym,
                line=dict(color=CHART_COLORS[i % len(CHART_COLORS)], width=2),
            ))

    fig_comp.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.15)")
    fig_comp.update_layout(
        template="plotly_dark", height=360,
        margin=dict(l=0, r=0, t=40, b=0),
        title=dict(text="Relative % Change (all normalized to period start = 0%)", font=dict(size=14)),
        yaxis=dict(title="% Change", showgrid=True, gridcolor="#2a2a2a", ticksuffix="%"),
        xaxis=dict(showgrid=True, gridcolor="#2a2a2a"),
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified",
    )
    st.plotly_chart(fig_comp, use_container_width=True)

    # Individual mini-candlestick charts in a 2-column grid
    n_syms = len(symbols)
    for row_start in range(0, n_syms, 2):
        cols = st.columns(min(2, n_syms - row_start))
        for col_idx, sym in enumerate(symbols[row_start : row_start + 2]):
            df = all_dfs.get(sym)
            with cols[col_idx]:
                if df is not None and not df.empty:
                    fig_mini = go.Figure()
                    fig_mini.add_trace(go.Candlestick(
                        x=df["datetime"],
                        open=df["open"], high=df["high"],
                        low=df["low"],   close=df["close"],
                        name=sym, showlegend=False,
                        increasing_line_color="#00e676", decreasing_line_color="#ff1744",
                        increasing_fillcolor="#00e676",  decreasing_fillcolor="#ff1744",
                    ))
                    fig_mini.update_layout(
                        template="plotly_dark", height=280,
                        margin=dict(l=0, r=0, t=30, b=0),
                        title=dict(text=sym, font=dict(size=13)),
                        xaxis=dict(showgrid=False, showticklabels=False),
                        yaxis=dict(showgrid=True, gridcolor="#2a2a2a", tickfont=dict(size=10)),
                        xaxis_rangeslider_visible=False,
                        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                    )
                    st.plotly_chart(fig_mini, use_container_width=True)
                else:
                    st.info(f"⏳ {sym} — waiting for data…")

# ════════════════════════════════════════════════════════════════════════════════
# SECTION 2 — ORDER BOOK (primary symbol)
# ════════════════════════════════════════════════════════════════════════════════

st.divider()
st.markdown(f"### 📖 Order Book — {primary}")

ob_stream: BinanceOrderBookStream = st.session_state[ob_key]

if not ob_stream.book.has_data:
    st.info("⏳ Waiting for order book data…")
else:
    book = ob_stream.book
    bids, asks = book.snapshot()

    # Spread metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Best Bid",  f"${book.best_bid:,.4f}"   if book.best_bid  else "—")
    m2.metric("Best Ask",  f"${book.best_ask:,.4f}"   if book.best_ask  else "—")
    m3.metric("Spread",    f"${book.spread:,.4f}"     if book.spread    else "—")
    m4.metric("Spread %",  f"{book.spread_pct:.4f}%"  if book.spread_pct else "—")

    # Bid / Ask tables side by side (top 10 levels)
    top_n = 10
    bid_df = pd.DataFrame(bids[:top_n], columns=["Price", "Qty"])
    ask_df = pd.DataFrame(asks[:top_n], columns=["Price", "Qty"])
    bid_df["Total (USDT)"] = (bid_df["Price"] * bid_df["Qty"]).round(2)
    ask_df["Total (USDT)"] = (ask_df["Price"] * ask_df["Qty"]).round(2)

    def _green_shade(col):
        mx = col.max() or 1
        return [f"background-color: rgba(0,230,118,{v/mx*0.55:.2f})" for v in col]

    def _red_shade(col):
        mx = col.max() or 1
        return [f"background-color: rgba(255,23,68,{v/mx*0.45:.2f})" for v in col]

    ob_col1, ob_col2 = st.columns(2)
    with ob_col1:
        st.markdown("**Bids 🟢** — buyers")
        st.dataframe(
            bid_df.style
                .format({"Price": "{:.4f}", "Qty": "{:.5f}", "Total (USDT)": "{:,.2f}"})
                .apply(_green_shade, subset=["Total (USDT)"]),
            use_container_width=True,
            hide_index=True,
        )
    with ob_col2:
        st.markdown("**Asks 🔴** — sellers")
        st.dataframe(
            ask_df.style
                .format({"Price": "{:.4f}", "Qty": "{:.5f}", "Total (USDT)": "{:,.2f}"})
                .apply(_red_shade, subset=["Total (USDT)"]),
            use_container_width=True,
            hide_index=True,
        )

    # Market depth chart (cumulative volume vs price)
    with st.expander("Market Depth Chart", expanded=False):
        bid_prices = [b[0] for b in bids]
        ask_prices = [a[0] for a in asks]

        bid_cum, ask_cum = [], []
        cum = 0
        for b in bids:
            cum += b[1]
            bid_cum.append(cum)
        cum = 0
        for a in asks:
            cum += a[1]
            ask_cum.append(cum)

        fig_depth = go.Figure()
        fig_depth.add_trace(go.Scatter(
            x=bid_prices, y=bid_cum,
            mode="lines", name="Bids",
            line=dict(color="#00e676", width=2),
            fill="tozeroy", fillcolor="rgba(0,230,118,0.1)",
        ))
        fig_depth.add_trace(go.Scatter(
            x=ask_prices, y=ask_cum,
            mode="lines", name="Asks",
            line=dict(color="#ff1744", width=2),
            fill="tozeroy", fillcolor="rgba(255,23,68,0.1)",
        ))
        fig_depth.update_layout(
            template="plotly_dark", height=300,
            margin=dict(l=0, r=0, t=20, b=0),
            xaxis=dict(title="Price (USDT)", showgrid=True, gridcolor="#2a2a2a"),
            yaxis=dict(title="Cumulative Volume", showgrid=True, gridcolor="#2a2a2a"),
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            legend=dict(orientation="h"),
        )
        st.plotly_chart(fig_depth, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════════
# SECTION 3 — AI TREND ANALYSIS
# ════════════════════════════════════════════════════════════════════════════════

st.divider()
ai_col, _ = st.columns([3, 1])

with ai_col:
    if analyze_btn:
        api_key_set = bool(os.getenv("OPENAI_API_KEY") or os.getenv("gpt_api_key"))
        if not api_key_set:
            st.error(
                "**No OpenAI API key found.**  "
                "Set `gpt_api_key` in your `.env` file, then restart the app."
            )
        else:
            klines = all_klines.get(primary, [])
            with st.spinner(f"GPT-4o is writing your investment brief for {primary}…"):
                try:
                    summary = summarize_trend(primary, klines, interval=interval)
                    st.session_state["ai_summary"]  = summary
                    st.session_state["ai_symbol"]   = primary
                    st.session_state["ai_candles"]  = len(klines)
                    st.session_state["ai_interval"] = interval
                except Exception as exc:
                    st.error(f"LLM error: {exc}")

    if "ai_summary" in st.session_state:
        st.markdown("### 🤖 Investment Brief")
        st.caption(
            f"Symbol: {st.session_state['ai_symbol']}  ·  "
            f"Interval: {st.session_state.get('ai_interval', interval)}  ·  "
            f"{st.session_state['ai_candles']} candles  ·  "
            f"Model: gpt-4o  ·  Includes RSI · MACD · MA · Bollinger Bands"
        )
        st.markdown(st.session_state["ai_summary"])

# ── Auto-refresh ──────────────────────────────────────────────────────────────────
if auto_refresh:
    time.sleep(5)
    st.rerun()
