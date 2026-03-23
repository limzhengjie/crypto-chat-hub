# AlphaLens MVP

> Real-time crypto research agent — Binance live data, technical analysis, GPT-4o research chat, and Polymarket prediction market scanner with edge detection.

---

## What it does

AlphaLens streams live market data from Binance, computes technical indicators, plots interactive charts, runs a GPT-4o research agent, and scans Polymarket for mispriced crypto prediction markets — all grounded in real numbers.

### Tabs

| Tab | What it does |
|-----|-------------|
| **Dashboard** | Live candlestick charts, RSI/MACD panels, Bollinger Bands, order book depth |
| **Research Chat** | Ask anything about crypto — agent fetches from CoinGecko, DefiLlama, Binance Futures |
| **Deep Dive** | One-click comprehensive multi-source report for any token |
| **Prediction Scanner** | Live Polymarket feed with GBM probability model, strategy signals, edge detection |

---

## Prediction Scanner

The scanner fetches active crypto prediction markets from Polymarket, matches them to Binance price data, and runs a probability model to find mispriced contracts.

### How it works

1. **Fetch** — Paginates through Polymarket's Gamma API for all active crypto markets
2. **Backfill** — Auto-fetches 500 candles from Binance for any symbol encountered
3. **Estimate** — GBM (geometric Brownian motion) probability model using annualized volatility + indicator adjustments (RSI, MACD, funding rate)
4. **Filter** — Shows markets with edge > 0.1% and volume > $500

### Strategy Signals

| Strategy | Signal | Data Sources |
|----------|--------|-------------|
| **Liquidation Cascade** | Overleveraged longs/shorts via extreme funding + OI | Binance Futures |
| **Momentum Regime** | RSI + MACD + SMA alignment (3+ signals agree) | Binance candles |
| **TVL Divergence** | Price vs DeFi capital flows divergence | CoinGecko + DefiLlama |
| **Volatility Squeeze** | Bollinger Band width at minimum → breakout imminent | Binance candles |

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
        │
        ▼
Polymarket Gamma API  →  scanner.py  →  probability.py (GBM model)
        │                                     │
        ▼                                     ▼
Live prediction market cards       Strategy signals (4 strategies)
with sparklines, edge badges,      from Binance Futures, CoinGecko,
platform links, volume, countdown  DefiLlama
```

---

## Requirements

- Python 3.9+
- An [OpenAI API key](https://platform.openai.com/api-keys) with GPT-4o access

No Binance or Polymarket API keys required — all endpoints used are public.

---

## Setup

```bash
cd alphalens-mvp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your OpenAI key
streamlit run app.py   # opens at http://localhost:8501
```

---

## Project Structure

```
alphalens-mvp/
├── app.py                  Streamlit entry point (dashboard + scanner UI)
├── requirements.txt
├── .env.example
└── src/
    ├── database.py         SQLite schema, upsert, queries
    ├── history.py          Binance REST → historical kline backfill
    ├── ws_client.py        Binance WebSocket kline stream → SQLite
    ├── orderbook.py        Binance WebSocket depth stream → in-memory book
    ├── indicators.py       SMA, EMA, Bollinger Bands, RSI, MACD
    ├── agent.py            GPT-4o research agent with tool use
    ├── tools.py            Data-fetching tools (CoinGecko, DefiLlama, Binance Futures)
    ├── client.py           GPTClient + RateLimiter (OpenAI wrapper)
    ├── llm_summary.py      Data prep → prompt → GPT-4o → investment brief
    ├── polymarket.py       Polymarket Gamma API client + CLOB price history
    ├── probability.py      GBM probability estimation engine
    ├── scanner.py          Market scanner — fetch, match, estimate, filter
    ├── strategies.py       Trading strategy signals (4 strategies)
    └── prompts/
        └── trend_analysis.py
```
