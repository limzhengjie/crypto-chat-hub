# AlphaLens MVP

> AI-powered crypto research agent — live Binance data, GPT-4o chatbot with tool use, Polymarket prediction markets feed, and downloadable PDF reports.

---

## What it does

AlphaLens streams live market data from Binance, computes technical indicators, runs a GPT-4o research agent with 8 data tools, and surfaces live Polymarket prediction markets — all in one Streamlit dashboard.

### Tabs

| Tab | What it does |
|-----|-------------|
| **Dashboard** | Live candlestick charts, RSI/MACD panels, Bollinger Bands, order book depth |
| **Chatbot** | Ask anything — agent fetches from CoinGecko, DefiLlama, Binance Futures, Polymarket. Quick research buttons (Full Deep Dive, Technical Setup, Sentiment, etc). Download responses as PDF or Word. |
| **Prediction Markets** | Live Polymarket feed with coin filter, time period filter, market consensus summary, price distribution histograms, sparkline charts. 2000+ markets, filtered to tracked assets with >$10K volume. |

---

## Prediction Markets

The Prediction Markets tab fetches all active crypto markets from Polymarket and presents them as an information feed — what does the crowd think about price targets?

### Features

- **Market Consensus** — one-liner per coin: "BTC: 95% chance above $80,000 by Mar 31"
- **Price Distribution Histograms** — top 2 events by volume show bar charts of probability at each strike price
- **Sparkline Cards** — individual market cards with Polymarket/Robinhood-style probability charts
- **Coin Filter** — filter by BTC, ETH, SOL, and 15+ other coins
- **Time Period Filter** — Today, This Week, This Month, Long-term
- **Polymarket Watermark** — source attribution on every card (ready for multi-source: Kalshi, etc)
- **60s Cache + Parallel Fetch** — ThreadPoolExecutor fires all API calls simultaneously, cached for speed

### Data Sources

Markets are fetched via the Polymarket Gamma API events endpoint with crypto tag slugs (`crypto`, `bitcoin`, `ethereum`, `solana`, `defi`), plus a keyword sweep fallback. 40+ token-to-symbol mappings with word-boundary matching to avoid false positives (e.g., "MegaETH" doesn't match "ETH").

---

## Chatbot / Research Agent

GPT-4o (or Gemini) agent with 8 real-time data tools:

| Tool | Source | Data |
|------|--------|------|
| `get_market_data` | CoinGecko | Price, market cap, rank, 24h/7d/30d changes, ATH, supply |
| `get_tvl` | DefiLlama | Total Value Locked for DeFi chains |
| `get_funding_rate` | Binance Futures | Perpetual futures funding rate + sentiment |
| `get_open_interest` | Binance Futures | Open interest (contract count) |
| `get_technical_analysis` | Binance (live) | RSI, MACD, Bollinger Bands, moving averages |
| `get_prediction_markets` | Polymarket | Live crowd-sourced probabilities for price targets |
| `get_prediction_accuracy` | Polymarket | Historical calibration — how accurate were past predictions |

### Quick Research Buttons

One-click prompts: Full Deep Dive, Technical Setup, Market Sentiment, Prediction Markets, Key Risks, Worth Buying?

### PDF Reports

Any chatbot response >100 chars gets a "Download PDF" button. Reports are generated with:
- Dark header with amber accent stripe
- Section dividers, proper typography
- Page numbers and footer
- Disclaimer

---

## Data Flow

```
Binance REST API  →  SQLite (500 historical candles per symbol)
        │
        ▼
Binance WebSocket  →  Live kline + order book streams  →  SQLite
        │
        ▼
Streamlit Dashboard  ←  indicators.py (SMA, EMA, BB, RSI, MACD)

Polymarket Gamma API  →  Events endpoint (tag_slug: crypto/bitcoin/ethereum/solana/defi)
        │                  + Markets endpoint (keyword sweep)
        ▼                  ThreadPoolExecutor (10 workers, parallel)
Live prediction market cards with sparklines, price distributions, consensus summary
        │
        ▼
GPT-4o Agent  ←  8 tools (CoinGecko, DefiLlama, Binance, Polymarket)
        │
        ▼
Cited research response  →  PDF/Word export
```

---

## Requirements

- Python 3.9+
- An OpenAI or Gemini API key

No Binance or Polymarket API keys required — all endpoints used are public.

---

## Setup

```bash
cd alphalens-mvp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your API key (gpt_api_key or GEMINI_API_KEY)
streamlit run app.py   # opens at http://localhost:8501
```

---

## Project Structure

```
alphalens-mvp/
├── app.py                  Streamlit entry point — all 3 tabs, themes, PDF export
├── requirements.txt
├── .env.example
└── src/
    ├── database.py         SQLite schema, upsert, queries
    ├── history.py          Binance REST → historical kline backfill
    ├── ws_client.py        Binance WebSocket kline stream → SQLite
    ├── orderbook.py        Binance WebSocket depth stream → in-memory book
    ├── indicators.py       SMA, EMA, Bollinger Bands, RSI, MACD
    ├── agent.py            GPT-4o/Gemini research agent with tool-use loop
    ├── tools.py            8 data-fetching tools + OpenAI function definitions
    ├── polymarket.py       Polymarket Gamma API client — parallel fetch, caching, CLOB history
    └── prompts/
        └── quick_prompts.py  One-click research prompt templates
```

---

## Themes

4 professional themes (sidebar dropdown):

| Theme | Style |
|-------|-------|
| **Studio** (default) | Amber accent, slate backgrounds, 6px radius — Bloomberg/Grafana |
| **Studio Light** | White background, dark text, amber accent — light mode |
| **Artemis** | Indigo accent, zinc grays, 8px radius — clean analytics |
| **Terminal** | Teal accent, GitHub-dark, 6px radius — data-dense |
| **Minimal** | White accent, pure black, barely-there borders — Robinhood/Linear |
