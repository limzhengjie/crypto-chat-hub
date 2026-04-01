# AlphaLens MVP

**AI-assisted crypto research PoC** — live Binance data, technical indicators, research chatbot (OpenAI / Gemini), Polymarket, RSS news, and a scanner — in one **Streamlit** app. Public market APIs only; you need an **LLM API key** for the chatbot.

---

## Install and run

**Requirements:** Python **3.9+**, internet access (Binance, RSS, optional LLM APIs).

### 1. Install

```bash
cd crypto-chat-hub/alphalens-mvp   # or your clone path

python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

cp .env.example .env
# Edit .env — add at least one LLM key, e.g.:
#   OPENAI_API_KEY=sk-...
#   # or
#   gpt_api_key=sk-...
#   # or (Google Gemini, OpenAI-compatible)
#   GEMINI_API_KEY=...
```

### 2. Run

```bash
source .venv/bin/activate
python3 -m streamlit run app.py
```

Open **http://localhost:8501**.

**Tip:** Use `python3 -m streamlit` (not bare `streamlit`) so the command uses your venv.

---

## Dependencies

Everything is pinned in **`requirements.txt`**. Main packages:

| Package | Purpose |
|---------|---------|
| `streamlit` | Web UI |
| `plotly` | Charts |
| `pandas` | Data / indicators |
| `websocket-client` | Binance streams |
| `openai` | Chat + tool use (OpenAI or Gemini endpoint) |
| `python-dotenv`, `requests`, `python-docx`, `fpdf2` | Config, HTTP, exports |

Install all at once: `python3 -m pip install -r requirements.txt`.

---

## Project overview

| Layer | Role |
|--------|------|
| **UI** | `app.py` — Streamlit dashboard (tabs, themes, charts, chat, exports) |
| **Data & streaming** | `src/` — SQLite, Binance REST + WebSocket, RSS, Polymarket |
| **Intelligence** | `src/agent.py` + `src/tools.py` — tool-calling loop with cited answers |
| **Config / secrets** | `.env` (see `.env.example`) — never commit real keys |

---

## Features (main tabs)

| Tab | Description |
|-----|-------------|
| **Dashboard** | Live candles, volume, RSI/MACD/Bollinger, order book, themed metrics |
| **Chatbot** | Q&A with tools (CoinGecko, DefiLlama, Binance Futures, TA DB, Polymarket, news); quick prompts; exports |
| **Signal Scanner** | Technical / scanner summaries across your watchlist |
| **Prediction Markets** | Polymarket views (filters, summaries, charts) |
| **News Feed** | RSS headlines; coin / time filters |

---

## Repository layout

This PoC uses a **flat layout** (Streamlit *is* the frontend). Rubric mapping:

| Rubric idea | In this repo |
|-------------|----------------|
| **Frontend** | `app.py` + Plotly / HTML styling |
| **Backend / services** | `src/*.py` |
| **Prompts** | `src/prompts/` |
| **Contracts** | *N/A* |
| **Scripts / notebooks** | *Optional* — add `scripts/` or `notebooks/` if needed |

### Directory tree

```
alphalens-mvp/
├── app.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── src/
    ├── agent.py
    ├── database.py
    ├── history.py
    ├── ws_client.py
    ├── orderbook.py
    ├── indicators.py
    ├── polymarket.py
    ├── tools.py
    ├── metric_tooltip.py
    └── prompts/
        ├── __init__.py
        └── quick_prompts.py
```

---

## Deploy the PoC

### Streamlit Community Cloud (quickest)

1. Push this repo to GitHub (without `.env` — use Cloud secrets).
2. [share.streamlit.io](https://streamlit.io/cloud) → New app → set entry file to **`app.py`**.
3. Under **Secrets**, add env vars (e.g. `OPENAI_API_KEY` or `GEMINI_API_KEY`) in TOML format.
4. Note: WebSockets + SQLite on Cloud are **ephemeral**; fine for demos, state resets on restart.

### Docker (optional)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address", "0.0.0.0", "--server.port", "8501"]
```

Build with `docker build -t alphalens .`, run with `-p 8501:8501` and pass secrets via `-e` (never bake keys into the image).

### VPS

Same as local run behind nginx/Caddy TLS; use `--server.address 0.0.0.0` and add auth for production.

---

## Data flow (high level)

```
Binance REST  ──► SQLite (historical klines)
Binance WS    ──► SQLite + in-memory order book
                         │
                         ▼
              Streamlit  ←  indicators, Plotly
Polymarket APIs ──► Scanner / Prediction tab / agent tools
RSS feeds     ──► News tab + agent tool
                         │
                         ▼
              LLM agent (tools) ──► cited answers, exports
```

---

## Agent tools (`src/tools.py`)

| Tool | Source (typical) |
|------|------------------|
| `get_market_data` | CoinGecko |
| `get_tvl` | DefiLlama |
| `get_funding_rate` / `get_open_interest` | Binance Futures |
| `get_technical_analysis` | Local DB (Binance-derived) |
| `get_prediction_markets` | Polymarket |
| `get_prediction_accuracy` | Polymarket |
| `get_crypto_news` | RSS outlets |

---

## Troubleshooting

| Issue | What to try |
|-------|-------------|
| `pip` / `streamlit` not found | Use `python3 -m pip` and `python3 -m streamlit run app.py` |
| Chatbot errors / quota | Set `GEMINI_API_KEY` or enable OpenAI billing; check `.env` |
| News feed empty | Outbound HTTP required; some networks block RSS — try another network or VPN |
| `TypeError` on `st.tabs` / `st.metric` | Use Streamlit **1.45+** per `requirements.txt`: `pip install -U streamlit` |

---

## License / disclaimer

Educational / research prototype. **Not financial advice.** Markets are risky; verify data and compliance in your jurisdiction.
