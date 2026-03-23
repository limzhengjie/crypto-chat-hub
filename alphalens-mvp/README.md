# AlphaLens MVP

> Real-time crypto research tool — Binance live data → technical analysis → GPT-4o investment brief.

---

## What it does

AlphaLens streams live market data from Binance, computes technical indicators, plots interactive charts, and on demand generates an institutional-grade investment brief using GPT-4o — all grounded in real numbers, no hallucination.

---

## Full Project Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  STARTUP  (once per symbol/interval pair per session)           │
│                                                                 │
│  Binance REST API  ──►  SQLite (500 historical candles)         │
│  GET /api/v3/klines       backfill via src/history.py           │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│  LIVE STREAMING  (continuous, background daemon threads)        │
│                                                                 │
│  Binance WS  ──►  src/ws_client.py  ──►  SQLite upsert         │
│  kline stream       BinanceKlineStream    OHLCV per candle      │
│  (per symbol)       one thread/symbol     live candle updated   │
│                                           in-place each tick    │
│                                                                 │
│  Binance WS  ──►  src/orderbook.py  ──►  in-memory OrderBook   │
│  depth20 stream     BinanceOrderBook      top 20 bid/ask        │
│  (primary symbol)   Stream               updated every 1s      │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼  (every 5 seconds via st.rerun)
┌─────────────────────────────────────────────────────────────────┐
│  STREAMLIT DASHBOARD  (app.py)                                  │
│                                                                 │
│  SQLite  ──►  src/indicators.py  ──►  Plotly charts            │
│  get_klines()   add_indicators()       candlestick + MAs        │
│                 SMA 20/50              Bollinger Bands           │
│                 EMA 12/26             RSI panel                 │
│                 Bollinger Bands       MACD panel                │
│                 RSI (14)              volume bars               │
│                 MACD (12,26,9)                                  │
│                                                                 │
│  OrderBook  ──►  bid/ask tables  +  market depth chart         │
│                  spread, spread %                               │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼  (on button click only)
┌─────────────────────────────────────────────────────────────────┐
│  AI INVESTMENT BRIEF  (src/llm_summary.py)                      │
│                                                                 │
│  klines + indicators  ──►  src/prompts/trend_analysis.py       │
│                             SYSTEM_PROMPT  (quant analyst role) │
│                             build_user_prompt()                 │
│                             price stats + indicator readings    │
│                             last 20 candles with RSI per row    │
│                                   │                            │
│                                   ▼                            │
│                            GPT-4o  (via src/client.py)         │
│                            GPTClient + RateLimiter             │
│                                   │                            │
│                                   ▼                            │
│                      6-section investment brief:               │
│                      1. Market Assessment                       │
│                      2. Technical Signal Summary               │
│                      3. Investment Thesis (bull vs bear)       │
│                      4. Trade Setup (entry / target / stop)    │
│                      5. Risk Assessment                        │
│                      6. Plain-English Verdict                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Requirements

- Python 3.9+
- An [OpenAI API key](https://platform.openai.com/api-keys) with GPT-4o access

No Binance API key required — all market data endpoints used are public.

---

## Setup

### 1. Navigate to the project

```bash
cd alphalens-mvp
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Add your OpenAI API key

```bash
cp .env.example .env
```

Open `.env` and set your key — **no spaces around `=`**:

```
gpt_api_key=sk-proj-...
```

---

## Run

```bash
streamlit run app.py
```

Opens at **http://localhost:8501**.

---

## UI Controls

| Control | What it does |
|---------|-------------|
| **Assets** multiselect | Stream 1–4 symbols simultaneously |
| **Candle interval** | Switch between 1m / 3m / 5m |
| **Candles to display** | How many candles to show (20–500) |
| **Auto-refresh toggle** | Redraws charts from DB every 5 s |
| **Analyze trend with AI** | Generates full GPT-4o investment brief |

---

## Charts

| Chart | What it shows |
|-------|-------------|
| **Candlestick** | OHLC price with SMA 20, SMA 50, Bollinger Bands, volume bars |
| **RSI panel** | 14-period RSI with overbought (70) / oversold (30) lines |
| **MACD panel** | MACD line, signal line, histogram (green = bullish, red = bearish) |
| **Comparison chart** | Normalised % change from period start across all selected symbols |
| **Order book** | Live top-10 bid/ask table + market depth chart for primary symbol |

---

## Project Structure

```
alphalens-mvp/
├── app.py                        Streamlit entry point
├── requirements.txt
├── .env                          API key (git-ignored)
├── .env.example
├── .gitignore
└── src/
    ├── __init__.py
    ├── client.py                 GPTClient + RateLimiter (OpenAI wrapper)
    ├── database.py               SQLite schema, upsert, queries
    ├── history.py                Binance REST → historical kline backfill
    ├── ws_client.py              Binance WebSocket kline stream → SQLite
    ├── orderbook.py              Binance WebSocket depth stream → in-memory book
    ├── indicators.py             SMA, EMA, Bollinger Bands, RSI, MACD
    ├── llm_summary.py            Data prep → prompt → GPT-4o → investment brief
    └── prompts/
        ├── __init__.py
        └── trend_analysis.py     SYSTEM_PROMPT + build_user_prompt()
```

---

## Troubleshooting

| Error | Likely cause | Fix |
|-------|-------------|-----|
| `AuthenticationError` | Wrong or expired API key | Check `.env`, no spaces around `=` |
| `PermissionDeniedError` | Key lacks GPT-4o access | Enable billing or use `gpt-4o-mini` in `src/llm_summary.py` |
| `RateLimitError` | Quota exhausted | Check usage at platform.openai.com |
| Chart empty on startup | DB not yet populated | Wait for the history spinner to finish |
| Order book shows `—` | Depth stream still connecting | Wait a few seconds, auto-refreshes |
