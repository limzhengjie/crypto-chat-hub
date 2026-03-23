"""Polymarket Gamma API client — fetches active crypto prediction markets."""

from __future__ import annotations

import json
import re
from datetime import datetime

import requests

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

CRYPTO_KEYWORDS = [
    "bitcoin",
    "btc",
    "ethereum",
    "eth",
    "solana",
    "sol",
    "bnb",
    "xrp",
    "doge",
    "dogecoin",
    "cardano",
    "ada",
    "avalanche",
    "avax",
    "crypto",
    "cryptocurrency",
]

TOKEN_TO_SYMBOL = {
    "bitcoin": "BTCUSDT",
    "btc": "BTCUSDT",
    "ethereum": "ETHUSDT",
    "eth": "ETHUSDT",
    "solana": "SOLUSDT",
    "sol": "SOLUSDT",
    "bnb": "BNBUSDT",
    "xrp": "XRPUSDT",
    "dogecoin": "DOGEUSDT",
    "doge": "DOGEUSDT",
    "cardano": "ADAUSDT",
    "ada": "ADAUSDT",
    "avalanche": "AVAXUSDT",
    "avax": "AVAXUSDT",
}

# Match "$70,200" or "70,200" (bare number after "above/below")
_PRICE_RE = re.compile(r"\$?([\d,]+(?:\.\d+)?)\s*[kK]?")
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
    """Match question text to a tracked Binance symbol."""
    q = question.lower()
    # Check longer keywords first to avoid false positives
    for keyword in sorted(TOKEN_TO_SYMBOL, key=len, reverse=True):
        if keyword in q:
            return TOKEN_TO_SYMBOL[keyword]
    return None


def fetch_crypto_markets() -> list[dict]:
    """Fetch active crypto prediction markets from Polymarket Gamma API.

    Paginates through multiple pages to find all crypto markets.
    """
    raw_markets: list[dict] = []
    seen_ids: set[str] = set()

    for offset in (0, 100, 200):
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
                timeout=15,
            )
            resp.raise_for_status()
            page = resp.json()
        except Exception:
            break

        if not page:
            break

        for m in page:
            mid = m.get("id", "")
            if mid not in seen_ids:
                seen_ids.add(mid)
                raw_markets.append(m)
        if len(page) < 100:
            break

    markets: list[dict] = []
    for m in raw_markets:
        question = m.get("question", "")
        q_lower = question.lower()

        if not any(kw in q_lower for kw in CRYPTO_KEYWORDS):
            continue

        symbol = _match_symbol(question)
        if not symbol:
            continue

        threshold, direction = _parse_threshold(question)

        try:
            prices = json.loads(m.get("outcomePrices", "[]"))
            yes_price = float(prices[0]) if prices else None
        except (json.JSONDecodeError, ValueError, IndexError):
            yes_price = None

        if yes_price is None:
            continue

        expiry = None
        end_date = m.get("endDate")
        if end_date:
            try:
                expiry = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            except ValueError:
                pass

        # Extract CLOB token ID for price history
        try:
            token_ids = json.loads(m.get("clobTokenIds", "[]"))
            clob_token_id = token_ids[0] if token_ids else None
        except (json.JSONDecodeError, IndexError):
            clob_token_id = None

        markets.append(
            {
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
            }
        )

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
