"""
Data-fetching tools for the AlphaLens research agent.

Each tool queries one external source and returns a dict with a "source" field
for citation. Results are cached in-memory for 60s to stay within rate limits.
"""

from __future__ import annotations

import json
import re
import time

import pandas as pd
import requests

from src.database import get_klines
from src.history import fetch_historical_klines
from src.indicators import add_indicators, indicator_summary
from src.polymarket import fetch_crypto_markets

# ── Symbol → external ID mappings ───────────────────────────────────────────────

COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "DOGE": "dogecoin",
    "ADA": "cardano",
    "AVAX": "avalanche-2",
    "DOT": "polkadot",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "MATIC": "matic-network",
    "ATOM": "cosmos",
    "NEAR": "near",
    "ARB": "arbitrum",
    "OP": "optimism",
    "SUI": "sui",
    "APT": "aptos",
    "LTC": "litecoin",
    "FIL": "filecoin",
}

DEFILLAMA_CHAINS = {
    "ETH": "Ethereum",
    "SOL": "Solana",
    "BNB": "BSC",
    "ADA": "Cardano",
    "AVAX": "Avalanche",
    "DOT": "Polkadot",
    "MATIC": "Polygon",
    "NEAR": "Near",
    "ARB": "Arbitrum",
    "OP": "Optimism",
    "SUI": "Sui",
    "APT": "Aptos",
}

# ── Cache ────────────────────────────────────────────────────────────────────────

_cache: dict[str, tuple] = {}
CACHE_TTL = 60


def _cached_get(url: str, params: dict | None = None) -> dict:
    """HTTP GET with 60s in-memory cache."""
    key = f"{url}:{json.dumps(params, sort_keys=True)}"
    if key in _cache:
        data, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return data
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    _cache[key] = (data, time.time())
    return data


def _sym(symbol: str) -> str:
    """Strip USDT suffix → raw symbol."""
    return symbol.upper().replace("USDT", "")


# ── Tool functions ───────────────────────────────────────────────────────────────


def get_market_data(symbol: str) -> dict:
    """Market overview from CoinGecko: price, market cap, rank, changes, ATH, supply."""
    raw = _sym(symbol)
    coin_id = COINGECKO_IDS.get(raw)
    if not coin_id:
        return {"error": f"Unknown symbol: {raw}", "source": "CoinGecko"}

    try:
        data = _cached_get(
            f"https://api.coingecko.com/api/v3/coins/{coin_id}",
            {
                "localization": "false",
                "tickers": "false",
                "community_data": "false",
                "developer_data": "false",
            },
        )
    except Exception as e:
        return {"error": str(e), "source": "CoinGecko"}

    md = data.get("market_data", {})
    return {
        "source": "CoinGecko",
        "name": data.get("name"),
        "symbol": raw,
        "market_cap_rank": data.get("market_cap_rank"),
        "price_usd": md.get("current_price", {}).get("usd"),
        "market_cap_usd": md.get("market_cap", {}).get("usd"),
        "volume_24h_usd": md.get("total_volume", {}).get("usd"),
        "change_24h_pct": md.get("price_change_percentage_24h"),
        "change_7d_pct": md.get("price_change_percentage_7d"),
        "change_30d_pct": md.get("price_change_percentage_30d"),
        "ath_usd": md.get("ath", {}).get("usd"),
        "ath_change_pct": md.get("ath_change_percentage", {}).get("usd"),
        "circulating_supply": md.get("circulating_supply"),
        "max_supply": md.get("max_supply"),
        "fdv_usd": md.get("fully_diluted_valuation", {}).get("usd"),
    }


def get_tvl(symbol: str) -> dict:
    """Total Value Locked for a blockchain from DefiLlama."""
    raw = _sym(symbol)
    chain_name = DEFILLAMA_CHAINS.get(raw)
    if not chain_name:
        return {
            "error": f"No DeFi data for {raw} (not a tracked chain)",
            "source": "DefiLlama",
        }

    try:
        chains = _cached_get("https://api.llama.fi/v2/chains")
    except Exception as e:
        return {"error": str(e), "source": "DefiLlama"}

    for chain in chains:
        if chain.get("name", "").lower() == chain_name.lower():
            return {
                "source": "DefiLlama",
                "chain": chain.get("name"),
                "tvl_usd": chain.get("tvl"),
            }

    return {"error": f"Chain '{chain_name}' not found", "source": "DefiLlama"}


def get_funding_rate(symbol: str) -> dict:
    """Perpetual futures funding rate from Binance Futures."""
    pair = _sym(symbol) + "USDT"

    try:
        data = _cached_get(
            "https://fapi.binance.com/fapi/v1/fundingRate",
            {"symbol": pair, "limit": 10},
        )
    except Exception as e:
        return {"error": str(e), "source": "Binance Futures"}

    if not data:
        return {"error": f"No funding data for {pair}", "source": "Binance Futures"}

    latest = float(data[-1]["fundingRate"])
    rates = [float(d["fundingRate"]) for d in data]

    return {
        "source": "Binance Futures",
        "symbol": pair,
        "current_rate_pct": round(latest * 100, 4),
        "avg_rate_pct": round(sum(rates) / len(rates) * 100, 4),
        "annualized_pct": round(latest * 3 * 365 * 100, 2),
        "sentiment": "bullish (longs pay shorts)"
        if latest > 0
        else "bearish (shorts pay longs)",
    }


def get_open_interest(symbol: str) -> dict:
    """Open interest for perpetual futures from Binance Futures."""
    pair = _sym(symbol) + "USDT"

    try:
        data = _cached_get(
            "https://fapi.binance.com/fapi/v1/openInterest",
            {"symbol": pair},
        )
    except Exception as e:
        return {"error": str(e), "source": "Binance Futures"}

    return {
        "source": "Binance Futures",
        "symbol": pair,
        "open_interest_contracts": float(data["openInterest"]),
    }


def get_technical_analysis(
    symbol: str, interval: str = "1m", lookback: int = 100
) -> dict:
    """Technical analysis from live Binance kline data in local SQLite."""
    pair = _sym(symbol) + "USDT"
    klines = get_klines(pair, interval=interval, limit=lookback)

    # No live stream for this symbol — fetch historical data on demand
    if not klines:
        fetch_historical_klines(pair, interval, limit=max(lookback, 200))
        klines = get_klines(pair, interval=interval, limit=lookback)

    if not klines:
        return {"error": f"Could not fetch data for {pair}", "source": "Binance"}

    df = pd.DataFrame(
        klines, columns=["open_time", "open", "high", "low", "close", "volume"]
    )
    df = add_indicators(df)
    summary = indicator_summary(df)

    latest = df.iloc[-1]
    earliest = df.iloc[0]
    pct = ((latest["close"] - earliest["close"]) / earliest["close"]) * 100

    return {
        "source": "Binance (live)",
        "symbol": pair,
        "interval": interval,
        "candles_analyzed": len(df),
        "current_price": round(float(latest["close"]), 4),
        "period_change_pct": round(pct, 2),
        "period_high": round(float(df["high"].max()), 4),
        "period_low": round(float(df["low"].min()), 4),
        "avg_volume": round(float(df["volume"].mean()), 2),
        **summary,
    }


def get_prediction_markets(symbol: str) -> dict:
    """Active Polymarket prediction markets for a crypto symbol."""
    target = _sym(symbol) + "USDT"
    try:
        markets = fetch_crypto_markets()
    except Exception as e:
        return {"error": str(e), "source": "Polymarket"}

    relevant = [m for m in markets if m.get("symbol") == target]
    if not relevant:
        return {
            "source": "Polymarket",
            "symbol": symbol,
            "markets": [],
            "message": f"No active prediction markets found for {symbol}.",
        }

    return {
        "source": "Polymarket",
        "symbol": symbol,
        "market_count": len(relevant),
        "markets": [
            {
                "question": m["question"],
                "yes_probability_pct": round(m["yes_price"] * 100, 1),
                "no_probability_pct": round(m["no_price"] * 100, 1),
                "volume_usd": round(m["volume"], 0),
                "liquidity_usd": round(m["liquidity"], 0),
                "expires": str(m["expiry"]),
                "url": f"https://polymarket.com/event/{m['slug']}",
            }
            for m in relevant[:8]
        ],
    }


def get_prediction_accuracy() -> dict:
    """Get Polymarket historical accuracy — how well calibrated are the predictions."""
    from src.polymarket import fetch_resolved_crypto_markets

    try:
        resolved = fetch_resolved_crypto_markets()
    except Exception as e:
        return {"error": str(e), "source": "Polymarket"}

    if not resolved:
        return {
            "source": "Polymarket",
            "message": "No resolved markets found",
            "calibration": [],
        }

    buckets = [
        (0, 0.3, "<30%"),
        (0.3, 0.5, "30-50%"),
        (0.5, 0.7, "50-70%"),
        (0.7, 0.85, "70-85%"),
        (0.85, 1.0, "85%+"),
    ]
    calibration = []
    for lo, hi, label in buckets:
        in_bucket = [r for r in resolved if lo <= r["prediction"] < hi]
        if len(in_bucket) >= 3:
            pct_yes = sum(1 for r in in_bucket if r["yes_won"]) / len(in_bucket) * 100
            calibration.append(
                {
                    "bucket": label,
                    "predicted_avg_pct": round((lo + hi) / 2 * 100, 1),
                    "actual_yes_pct": round(pct_yes, 1),
                    "sample_size": len(in_bucket),
                }
            )

    return {
        "source": "Polymarket",
        "total_resolved": len(resolved),
        "calibration": calibration,
    }


NEWS_FEEDS = {
    "CoinTelegraph": "https://cointelegraph.com/rss",
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Decrypt": "https://decrypt.co/feed",
    "The Block": "https://www.theblock.co/rss.xml",
    "Blockworks": "https://blockworks.co/feed",
    "Bitcoin Magazine": "https://bitcoinmagazine.com/.rss/full/",
}

_news_cache: dict[str, tuple] = {}
_NEWS_CACHE_TTL = 120


def _parse_rss(source_name: str, url: str) -> list[dict]:
    """Fetch and parse a single RSS feed into article dicts."""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime

    cache_key = f"rss:{url}"
    if cache_key in _news_cache:
        data, ts = _news_cache[cache_key]
        if time.time() - ts < _NEWS_CACHE_TTL:
            return data

    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "AlphaLens/1.0"})
        resp.raise_for_status()
    except Exception:
        return []

    articles = []
    try:
        root = ET.fromstring(resp.text)
        items = root.findall(".//item")[:10]
        for item in items:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()

            # Strip HTML tags from description
            desc = re.sub(r"<[^>]+>", "", desc)[:300]

            published_ts = 0
            if pub_date:
                try:
                    published_ts = int(parsedate_to_datetime(pub_date).timestamp())
                except Exception:
                    pass

            if title:
                articles.append(
                    {
                        "title": title,
                        "url": link,
                        "source_name": source_name,
                        "body": desc,
                        "published_on": published_ts,
                    }
                )
    except Exception:
        pass

    _news_cache[cache_key] = (articles, time.time())
    return articles


def get_crypto_news(symbol: str = "") -> dict:
    """Latest crypto news from major outlets, optionally filtered by coin keyword."""
    raw = _sym(symbol) if symbol else ""

    all_articles: list[dict] = []
    for name, url in NEWS_FEEDS.items():
        all_articles.extend(_parse_rss(name, url))

    # Sort by publish time (newest first)
    all_articles.sort(key=lambda a: a["published_on"], reverse=True)

    # Filter by symbol keyword in title or body
    if raw:
        keyword = raw.lower()
        # Also match full names for common coins
        aliases = {
            "BTC": ["bitcoin", "btc"],
            "ETH": ["ethereum", "eth", "ether"],
            "SOL": ["solana", "sol"],
            "BNB": ["bnb", "binance coin"],
            "XRP": ["xrp", "ripple"],
            "DOGE": ["doge", "dogecoin"],
            "ADA": ["ada", "cardano"],
            "AVAX": ["avax", "avalanche"],
            "DOT": ["dot", "polkadot"],
            "LINK": ["link", "chainlink"],
            "UNI": ["uni", "uniswap"],
            "NEAR": ["near protocol", "near"],
            "ARB": ["arb", "arbitrum"],
            "SUI": ["sui"],
            "APT": ["apt", "aptos"],
        }
        terms = aliases.get(raw, [keyword])
        all_articles = [
            a
            for a in all_articles
            if any(t in a["title"].lower() or t in a["body"].lower() for t in terms)
        ]

    articles = all_articles[:15]

    if not articles:
        return {
            "source": "RSS (CoinDesk, CoinTelegraph, The Block, Decrypt, Blockworks, Bitcoin Magazine)",
            "symbol": raw or "ALL",
            "articles": [],
            "message": f"No recent news found{' for ' + raw if raw else ''}.",
        }

    return {
        "source": "RSS (CoinDesk, CoinTelegraph, The Block, Decrypt, Blockworks, Bitcoin Magazine)",
        "symbol": raw or "ALL",
        "article_count": len(articles),
        "articles": articles,
    }


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_market_data",
            "description": (
                "Get market overview: price, market cap, rank, 24h/7d/30d price changes, "
                "ATH, circulating/max supply. Source: CoinGecko."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Crypto symbol, e.g. BTC, ETH, SOL",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tvl",
            "description": (
                "Get Total Value Locked (TVL) for a blockchain ecosystem. "
                "Only works for chains with DeFi (ETH, SOL, AVAX, etc). Source: DefiLlama."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Crypto symbol, e.g. ETH, SOL, AVAX",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_funding_rate",
            "description": (
                "Get perpetual futures funding rate. "
                "Positive = longs pay shorts (bullish sentiment). "
                "Negative = shorts pay longs (bearish). Source: Binance Futures."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Crypto symbol, e.g. BTC, ETH",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_open_interest",
            "description": "Get open interest for perpetual futures. Source: Binance Futures.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Crypto symbol, e.g. BTC, ETH",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_technical_analysis",
            "description": (
                "Get technical analysis from live price data: RSI, MACD, Bollinger Bands, "
                "moving averages, support/resistance levels. Source: Binance live data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Crypto symbol, e.g. BTC, ETH",
                    },
                    "interval": {
                        "type": "string",
                        "enum": ["1m", "3m", "5m"],
                        "description": "Candle interval",
                    },
                    "lookback": {
                        "type": "integer",
                        "description": "Number of candles to analyze",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_prediction_markets",
            "description": (
                "Get active Polymarket prediction markets for a crypto symbol. "
                "Returns crowd-sourced probability estimates for price targets and events. "
                "Source: Polymarket."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Crypto symbol, e.g. BTC, ETH, SOL",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_prediction_accuracy",
            "description": (
                "Get Polymarket historical accuracy — calibration data showing how often "
                "predictions at different confidence levels were correct. Use this to assess "
                "how much to trust current prediction market odds. Source: Polymarket."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_crypto_news",
            "description": (
                "Get latest crypto news headlines and summaries. "
                "Optionally filter by coin symbol. Returns title, source, "
                "and article URLs. Source: RSS feeds from CoinDesk, "
                "CoinTelegraph, The Block, Decrypt, Blockworks, Bitcoin Magazine."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Crypto symbol to filter news, e.g. BTC, ETH, SOL. Leave empty for all crypto news.",
                    },
                },
                "required": [],
            },
        },
    },
]

# ── Tool dispatch ─────────────────────────────────────────────────────────────────

TOOL_DISPATCH = {
    "get_market_data": get_market_data,
    "get_tvl": get_tvl,
    "get_funding_rate": get_funding_rate,
    "get_open_interest": get_open_interest,
    "get_technical_analysis": get_technical_analysis,
    "get_prediction_markets": get_prediction_markets,
    "get_prediction_accuracy": get_prediction_accuracy,
    "get_crypto_news": get_crypto_news,
}
