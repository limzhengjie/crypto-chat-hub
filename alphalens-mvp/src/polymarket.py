"""Polymarket Gamma API client — fetches active crypto prediction markets."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime

import requests

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

# In-memory cache: (markets_list, timestamp). Avoids re-fetching on every 30s refresh.
_markets_cache: tuple[list[dict], float] = ([], 0)
_CACHE_TTL = 60  # seconds

TOKEN_TO_SYMBOL = {
    "bitcoin": "BTCUSDT",
    "btc": "BTCUSDT",
    "ethereum": "ETHUSDT",
    "eth": "ETHUSDT",
    "ether": "ETHUSDT",
    "solana": "SOLUSDT",
    "sol": "SOLUSDT",
    "bnb": "BNBUSDT",
    "xrp": "XRPUSDT",
    "ripple": "XRPUSDT",
    "dogecoin": "DOGEUSDT",
    "doge": "DOGEUSDT",
    "cardano": "ADAUSDT",
    "ada": "ADAUSDT",
    "avalanche": "AVAXUSDT",
    "avax": "AVAXUSDT",
    "chainlink": "LINKUSDT",
    "link": "LINKUSDT",
    "polkadot": "DOTUSDT",
    "dot": "DOTUSDT",
    "uniswap": "UNIUSDT",
    "uni": "UNIUSDT",
    "near": "NEARUSDT",
    "arbitrum": "ARBUSDT",
    "arb": "ARBUSDT",
    "optimism": "OPUSDT",
    "sui": "SUIUSDT",
    "aptos": "APTUSDT",
    "apt": "APTUSDT",
    "litecoin": "LTCUSDT",
    "ltc": "LTCUSDT",
    "pepe": "PEPEUSDT",
    "shiba": "SHIBUSDT",
    "shib": "SHIBUSDT",
    "polygon": "MATICUSDT",
    "matic": "MATICUSDT",
    "cosmos": "ATOMUSDT",
    "atom": "ATOMUSDT",
    "filecoin": "FILUSDT",
    "fil": "FILUSDT",
    "aave": "AAVEUSDT",
    "maker": "MKRUSDT",
    "mkr": "MKRUSDT",
    "render": "RENDERUSDT",
    "sei": "SEIUSDT",
    "tia": "TIAUSDT",
    "celestia": "TIAUSDT",
    "jupiter": "JUPUSDT",
    "jup": "JUPUSDT",
    "wif": "WIFUSDT",
    "bonk": "BONKUSDT",
    "ton": "TONUSDT",
    "toncoin": "TONUSDT",
    "stx": "STXUSDT",
    "stacks": "STXUSDT",
}

# Tags to search on Polymarket events API for crypto markets
CRYPTO_TAG_SLUGS = ["crypto", "bitcoin", "ethereum", "solana", "defi"]

_BARE_PRICE_RE = re.compile(
    r"(?:above|below|between|over|under)\s+\$?([\d,]+(?:\.\d+)?)", re.I
)


def _parse_threshold(question: str) -> tuple[float | None, str]:
    """Extract price threshold and direction from market question."""
    q = question.lower()
    direction = (
        "below"
        if any(
            w in q
            for w in ["below", "under", "drop", "fall", "crash", "less than", "down"]
        )
        else "above"
    )

    # Try explicit dollar sign first
    dollar_match = re.search(r"\$([\d,]+(?:\.\d+)?)\s*[kK]?", question)
    if dollar_match:
        raw = dollar_match.group(1).replace(",", "")
        price = float(raw)
        end = dollar_match.end()
        if end < len(question) and question[end].lower() == "k":
            price *= 1000
        return price, direction

    # Try bare number after directional keyword ("above 70,200")
    bare_match = _BARE_PRICE_RE.search(question)
    if bare_match:
        raw = bare_match.group(1).replace(",", "")
        price = float(raw)
        return price, direction

    return None, direction


def _match_symbol(question: str) -> str | None:
    """Match question text to a tracked Binance symbol using word boundaries."""
    q = question.lower()
    # Check longer keywords first to avoid false positives
    for keyword in sorted(TOKEN_TO_SYMBOL, key=len, reverse=True):
        if re.search(r"\b" + re.escape(keyword) + r"\b", q):
            return TOKEN_TO_SYMBOL[keyword]
    return None


def _parse_market(m: dict, event_id: str = "", event_title: str = "") -> dict | None:
    """Parse a raw Gamma API market dict into our standard format. Returns None if unusable or expired."""
    if m.get("closed"):
        return None
    question = m.get("question", "")

    # Try to match to a tracked symbol
    symbol = _match_symbol(question)
    if not symbol:
        # Still include if it came from a crypto event — use generic label
        symbol = "CRYPTOUSDT"

    threshold, direction = _parse_threshold(question)

    try:
        prices = json.loads(m.get("outcomePrices", "[]"))
        yes_price = float(prices[0]) if prices else None
    except (json.JSONDecodeError, ValueError, IndexError):
        yes_price = None

    if yes_price is None:
        return None

    expiry = None
    end_date = m.get("endDate")
    if end_date:
        try:
            expiry = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except ValueError:
            pass

    try:
        token_ids = json.loads(m.get("clobTokenIds", "[]"))
        clob_token_id = token_ids[0] if token_ids else None
    except (json.JSONDecodeError, IndexError):
        clob_token_id = None

    return {
        "platform": "Polymarket",
        "id": m.get("id", ""),
        "question": question,
        "symbol": symbol,
        "threshold": threshold,
        "direction": direction,
        "yes_price": yes_price,
        "no_price": round(1 - yes_price, 4),
        "volume": float(m.get("volume", 0) or 0),
        "liquidity": float(m.get("liquidity", 0) or 0),
        "expiry": expiry,
        "slug": m.get("slug", ""),
        "clob_token_id": clob_token_id,
        "event_id": event_id,
        "event_title": event_title,
    }


def _fetch_events_page(tag_slug: str, offset: int) -> list[dict]:
    """Fetch one page of events for a tag. Returns raw event dicts."""
    try:
        resp = requests.get(
            f"{GAMMA_API}/events",
            params={
                "closed": "false",
                "active": "true",
                "limit": 50,
                "offset": offset,
                "order": "volume",
                "ascending": "false",
                "tag_slug": tag_slug,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


def _fetch_markets_page(offset: int) -> list[dict]:
    """Fetch one page of markets. Returns raw market dicts."""
    try:
        resp = requests.get(
            f"{GAMMA_API}/markets",
            params={
                "closed": "false",
                "active": "true",
                "limit": 100,
                "offset": offset,
                "order": "volume",
                "ascending": "false",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


def fetch_crypto_markets() -> list[dict]:
    """Fetch active crypto prediction markets from Polymarket.

    Uses the events endpoint with crypto tag slugs to get all crypto-related
    events, plus a keyword sweep on the markets endpoint. All API calls run
    in parallel via ThreadPoolExecutor for speed. Results cached for 60s.
    """
    global _markets_cache
    cached, ts = _markets_cache
    if cached and time.time() - ts < _CACHE_TTL:
        return cached

    from concurrent.futures import ThreadPoolExecutor, as_completed

    seen_ids: set[str] = set()
    markets: list[dict] = []

    # Build all the requests we need to make
    futures = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        # Strategy 1: events by tag (first 2 pages per tag = 100 events each)
        for tag_slug in CRYPTO_TAG_SLUGS:
            for offset in (0, 50):
                futures.append(pool.submit(_fetch_events_page, tag_slug, offset))

        # Strategy 2: keyword sweep (5 pages of 100)
        for page_offset in range(0, 500, 100):
            futures.append(pool.submit(_fetch_markets_page, page_offset))

        # Collect events results
        all_keywords = set(TOKEN_TO_SYMBOL.keys()) | {
            "crypto",
            "cryptocurrency",
            "defi",
            "nft",
            "web3",
        }
        for future in as_completed(futures):
            result = future.result()
            if not result:
                continue

            # Events response: list of events with nested markets
            if isinstance(result[0], dict) and "markets" in result[0]:
                for event in result:
                    eid = str(event.get("id", ""))
                    etitle = event.get("title", "")
                    for m in event.get("markets", []):
                        mid = m.get("id", "")
                        if mid in seen_ids:
                            continue
                        seen_ids.add(mid)
                        parsed = _parse_market(m, event_id=eid, event_title=etitle)
                        if parsed:
                            markets.append(parsed)
            else:
                # Markets response: flat list
                for m in result:
                    mid = m.get("id", "")
                    if mid in seen_ids:
                        continue
                    q_lower = m.get("question", "").lower()
                    if not any(kw in q_lower for kw in all_keywords):
                        continue
                    seen_ids.add(mid)
                    parsed = _parse_market(m)
                    if parsed:
                        markets.append(parsed)

    _markets_cache = (markets, time.time())
    return markets


def fetch_price_history(
    token_id: str, interval: str = "1w", fidelity: int = 50
) -> list[tuple[int, float]]:
    """Fetch price history for a Polymarket YES token from the CLOB API."""
    try:
        resp = requests.get(
            f"{CLOB_API}/prices-history",
            params={
                "market": token_id,
                "interval": interval,
                "fidelity": str(fidelity),
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    history = []
    for point in data.get("history", []):
        try:
            history.append((int(point["t"]), float(point["p"])))
        except (KeyError, ValueError):
            continue
    return history


# Cache for resolved markets (expensive, changes slowly)
_resolved_cache: tuple[list[dict], float] = ([], 0)
_RESOLVED_CACHE_TTL = 600  # 10 minutes


def fetch_resolved_crypto_markets() -> list[dict]:
    """Fetch recently resolved crypto prediction markets for accuracy tracking.

    Returns list of {question, yes_won, last_yes_price, volume} dicts.
    last_yes_price is the final YES price before resolution (0-1).
    """
    global _resolved_cache
    cached, ts = _resolved_cache
    if cached and time.time() - ts < _RESOLVED_CACHE_TTL:
        return cached

    from concurrent.futures import ThreadPoolExecutor

    def _fetch_page(offset: int) -> list[dict]:
        try:
            resp = requests.get(
                f"{GAMMA_API}/events",
                params={
                    "closed": "true",
                    "limit": 20,
                    "offset": offset,
                    "order": "volume",
                    "ascending": "false",
                    "tag_slug": "crypto",
                },
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return []

    results = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        pages = list(pool.map(_fetch_page, range(0, 100, 20)))

    for events in pages:
        for event in events:
            for m in event.get("markets", []):
                try:
                    prices = json.loads(m.get("outcomePrices", "[]"))
                    if not prices or len(prices) < 2:
                        continue
                    yes_final = float(prices[0])
                    # On resolved markets, outcomePrices becomes [1,0] or [0,1]
                    if yes_final not in (0.0, 1.0):
                        continue
                    yes_won = yes_final == 1.0
                    vol = float(m.get("volume", 0) or 0)
                    if vol < 1000:
                        continue
                    # Get the last traded price as the market's prediction
                    last_price = float(m.get("lastTradePrice", 0) or 0)
                    # Also check oneDayPriceChange to reconstruct pre-resolution price
                    one_day_change = float(m.get("oneDayPriceChange", 0) or 0)
                    pre_resolution = max(0, min(1, last_price - one_day_change))
                    # Use pre-resolution price if it looks reasonable, else lastTradePrice
                    prediction = (
                        pre_resolution if 0.01 < pre_resolution < 0.99 else last_price
                    )
                    if prediction in (0.0, 1.0):
                        continue
                    results.append(
                        {
                            "question": m.get("question", ""),
                            "yes_won": yes_won,
                            "prediction": prediction,
                            "volume": vol,
                        }
                    )
                except (ValueError, KeyError):
                    continue

    _resolved_cache = (results, time.time())
    return results
