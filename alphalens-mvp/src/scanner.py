"""
Prediction market scanner — finds edge and arbitrage opportunities.

Orchestrates: fetch markets → match to tracked tokens → estimate probabilities
→ flag edge → detect cross-platform arbitrage.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from src.polymarket import fetch_crypto_markets as fetch_poly
from src.probability import estimate_probability, compute_annualized_vol
from src.database import get_klines
from src.history import fetch_historical_klines
from src.indicators import add_indicators


def _hours_until(expiry: datetime | None) -> float:
    """Hours from now until expiry. Returns 168 (1 week) if unknown."""
    if expiry is None:
        return 168.0
    now = datetime.now(timezone.utc)
    delta = (expiry - now).total_seconds() / 3600
    return max(0, delta)


# Track which symbols we've already backfilled this session
_backfilled: set[str] = set()


def _get_indicators(symbol: str, interval: str = "1m") -> dict | None:
    """Fetch current indicators for a symbol from the local DB.

    Auto-fetches historical klines from Binance if the symbol has no data yet.
    """
    rows = get_klines(symbol, interval=interval, limit=200)
    if (not rows or len(rows) < 20) and symbol not in _backfilled:
        _backfilled.add(symbol)
        fetch_historical_klines(symbol, interval, limit=500)
        rows = get_klines(symbol, interval=interval, limit=200)

    if not rows or len(rows) < 20:
        return None

    df = pd.DataFrame(
        rows, columns=["open_time", "open", "high", "low", "close", "volume"]
    )
    df = add_indicators(df)

    latest = df.iloc[-1]
    closes = df["close"].tolist()
    vol = compute_annualized_vol(closes, interval)

    rsi = latest.get("rsi")
    macd = latest.get("macd")
    macd_sig = latest.get("macd_signal")

    return {
        "price": float(latest["close"]),
        "rsi": float(rsi) if rsi is not None and not pd.isna(rsi) else None,
        "macd_bullish": bool(macd > macd_sig)
        if macd is not None and macd_sig is not None and not pd.isna(macd)
        else None,
        "annual_vol": vol,
    }


def scan_markets(
    interval: str = "1m",
    edge_threshold: float = 0.05,
    on_progress: callable = None,
) -> tuple[list[dict], list[dict]]:
    """
    Scan all prediction markets and return (opportunities, arbitrage_pairs).

    opportunities: markets where our estimate diverges from market odds by ≥ edge_threshold
    arbitrage_pairs: matched markets across platforms where combined cost < $1
    """
    if on_progress:
        on_progress("Fetching Polymarket markets...")
    all_markets = fetch_poly()

    if on_progress:
        on_progress(f"Found {len(all_markets)} Polymarket markets")

    # Cache indicator lookups per symbol
    indicator_cache: dict[str, dict | None] = {}

    opportunities: list[dict] = []
    for m in all_markets:
        symbol = m["symbol"]
        threshold = m.get("threshold")

        if symbol not in indicator_cache:
            if on_progress:
                on_progress(f"Loading indicators for {symbol}...")
            indicator_cache[symbol] = _get_indicators(symbol, interval)

        ind = indicator_cache[symbol]
        if ind is None:
            continue

        hours = _hours_until(m.get("expiry"))
        if hours <= 0:
            continue

        market_odds = m["yes_price"]

        # If we have a threshold, compute model probability
        if threshold is not None:
            prob, confidence, signals = estimate_probability(
                current_price=ind["price"],
                threshold=threshold,
                hours_to_expiry=hours,
                annual_vol=ind["annual_vol"],
                direction=m.get("direction", "above"),
                rsi=ind.get("rsi"),
                macd_bullish=ind.get("macd_bullish"),
                funding_rate=None,
            )
            edge = prob - market_odds
        else:
            # No threshold (e.g. "Up or Down" markets) — show market data only
            prob = market_odds  # no model estimate available
            confidence = 0
            signals = []
            edge = 0.0

        opportunities.append(
            {
                "platform": m["platform"],
                "id": m.get("id", ""),
                "question": m["question"],
                "symbol": symbol,
                "threshold": threshold,
                "direction": m.get("direction", "above"),
                "expiry": m.get("expiry"),
                "hours_left": round(hours, 1),
                "market_odds": round(market_odds * 100, 1),
                "our_estimate": round(prob * 100, 1),
                "edge": round(edge * 100, 1),
                "confidence": round(confidence * 100),
                "signals": signals,
                "current_price": ind["price"],
                "volume": m.get("volume", 0),
                "action": "BUY YES" if edge > 0 else "BUY NO" if edge < 0 else "—",
                "clob_token_id": m.get("clob_token_id"),
                "slug": m.get("slug", ""),
            }
        )

    # Sort by absolute edge descending
    opportunities.sort(key=lambda x: abs(x["edge"]), reverse=True)

    # Filter to only meaningful edges
    filtered = [o for o in opportunities if abs(o["edge"]) >= edge_threshold * 100]

    # ── Arbitrage detection ──────────────────────────────────────────────────
    if on_progress:
        on_progress("Scanning for arbitrage...")
    arb = find_arbitrage(all_markets)

    return filtered, arb


def find_arbitrage(markets: list[dict], max_spread_pct: float = 5.0) -> list[dict]:
    """
    Find arbitrage opportunities across platforms.

    Arbitrage exists when you can buy YES on one platform and NO on another
    for a combined cost < $1.00 (guaranteed profit regardless of outcome).
    """
    # Group by (symbol, threshold, direction) with some tolerance
    by_key: dict[str, list[dict]] = {}
    for m in markets:
        threshold = m.get("threshold")
        if threshold is None:
            continue
        # Round threshold to nearest 100 for matching
        rounded = round(threshold / 100) * 100
        key = f"{m['symbol']}_{rounded}_{m['direction']}"
        by_key.setdefault(key, []).append(m)

    arb_opportunities: list[dict] = []
    for key, group in by_key.items():
        if len(group) < 2:
            continue

        # Check all pairs across different platforms
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a["platform"] == b["platform"]:
                    continue

                # Check expiry proximity (within 48 hours)
                if a.get("expiry") and b.get("expiry"):
                    delta_h = abs(
                        (_hours_until(a["expiry"]) - _hours_until(b["expiry"]))
                    )
                    if delta_h > 48:
                        continue

                # Strategy 1: Buy YES on A, Buy NO on B
                cost_1 = a["yes_price"] + b["no_price"]
                # Strategy 2: Buy NO on A, Buy YES on B
                cost_2 = a["no_price"] + b["yes_price"]

                best_cost = min(cost_1, cost_2)
                if best_cost < 1.0:
                    profit = (1.0 - best_cost) * 100

                    if cost_1 <= cost_2:
                        action = (
                            f"BUY YES on {a['platform']}, BUY NO on {b['platform']}"
                        )
                        buy_yes_platform = a["platform"]
                        buy_no_platform = b["platform"]
                    else:
                        action = (
                            f"BUY YES on {b['platform']}, BUY NO on {a['platform']}"
                        )
                        buy_yes_platform = b["platform"]
                        buy_no_platform = a["platform"]

                    arb_opportunities.append(
                        {
                            "market_a": a["question"],
                            "market_b": b["question"],
                            "platform_a": a["platform"],
                            "platform_b": b["platform"],
                            "symbol": a["symbol"],
                            "threshold": a.get("threshold"),
                            "yes_a": round(a["yes_price"] * 100, 1),
                            "no_a": round(a["no_price"] * 100, 1),
                            "yes_b": round(b["yes_price"] * 100, 1),
                            "no_b": round(b["no_price"] * 100, 1),
                            "combined_cost": round(best_cost * 100, 1),
                            "guaranteed_profit": round(profit, 1),
                            "action": action,
                        }
                    )

    arb_opportunities.sort(key=lambda x: x["guaranteed_profit"], reverse=True)
    return arb_opportunities
