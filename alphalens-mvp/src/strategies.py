"""
Trading strategy signals for prediction market edge detection.

Each strategy analyzes a different market dimension and returns a signal
with direction, strength, and a recommended action for prediction markets.

Strategies:
  1. Liquidation Cascade  — funding rate + open interest → overleveraged positions
  2. Momentum Regime      — RSI + MACD + SMA alignment → directional conviction
  3. TVL Divergence        — price vs DeFi capital flows → smart money signal
  4. Volatility Squeeze    — Bollinger Band width → breakout probability
"""

from __future__ import annotations

import math

from src.tools import get_funding_rate, get_open_interest, get_tvl, get_market_data
from src.database import get_klines
from src.indicators import add_indicators
from src.probability import compute_annualized_vol

import pandas as pd


def _get_df(symbol: str, interval: str = "1m", limit: int = 200) -> pd.DataFrame | None:
    rows = get_klines(symbol, interval=interval, limit=limit)
    if not rows or len(rows) < 20:
        return None
    df = pd.DataFrame(
        rows, columns=["open_time", "open", "high", "low", "close", "volume"]
    )
    return add_indicators(df)


# ── Strategy 1: Liquidation Cascade ──────────────────────────────────────────────


def liquidation_cascade(symbol: str) -> dict | None:
    """
    Detect overleveraged positioning via funding rate + open interest.

    High funding + high OI = longs are overleveraged → correction likely.
    Negative funding + high OI = shorts are overleveraged → squeeze likely.
    """
    fr = get_funding_rate(symbol)
    oi = get_open_interest(symbol)

    if "error" in fr or "error" in oi:
        return None

    rate = fr.get("current_rate_pct", 0)
    avg_rate = fr.get("avg_rate_pct", 0)
    annualized = fr.get("annualized_pct", 0)
    contracts = oi.get("open_interest_contracts", 0)

    # Signal fires when funding is extreme
    strength = 0.0
    direction = "neutral"
    details = []

    if rate > 0.03:
        # Longs paying shorts heavily — correction risk
        strength = min(1.0, rate / 0.1)  # max strength at 0.1%
        direction = "bearish"
        details.append(f"Funding {rate:.4f}% — longs overleveraged")
        if avg_rate > 0.02:
            strength = min(1.0, strength + 0.2)
            details.append(f"Avg rate {avg_rate:.4f}% — sustained pressure")
    elif rate < -0.03:
        # Shorts paying longs — squeeze risk
        strength = min(1.0, abs(rate) / 0.1)
        direction = "bullish"
        details.append(f"Funding {rate:.4f}% — shorts overleveraged")
        if avg_rate < -0.02:
            strength = min(1.0, strength + 0.2)
            details.append(f"Avg rate {avg_rate:.4f}% — sustained pressure")
    else:
        return None  # No signal

    return {
        "strategy": "Liquidation Cascade",
        "symbol": symbol,
        "direction": direction,
        "strength": round(strength * 100),
        "details": details,
        "prediction": (
            f"{'Correction' if direction == 'bearish' else 'Squeeze'} likely — "
            f"BUY {'NO' if direction == 'bearish' else 'YES'} on upside markets"
        ),
        "funding_rate": rate,
        "annualized": annualized,
        "open_interest": contracts,
    }


# ── Strategy 2: Momentum Regime ──────────────────────────────────────────────────


def momentum_regime(symbol: str, interval: str = "1m") -> dict | None:
    """
    Multi-signal momentum confirmation: RSI + MACD + SMA alignment.

    When 3+ signals agree, directional conviction is high.
    """
    df = _get_df(symbol, interval)
    if df is None:
        return None

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    rsi = latest.get("rsi")
    macd = latest.get("macd")
    macd_sig = latest.get("macd_signal")
    sma20 = latest.get("sma_20")
    sma50 = latest.get("sma_50")
    close = float(latest["close"])

    if any(
        v is None or (isinstance(v, float) and math.isnan(v))
        for v in [rsi, macd, macd_sig]
    ):
        return None

    bullish_signals = 0
    bearish_signals = 0
    details = []

    # RSI
    if rsi > 50:
        bullish_signals += 1
        details.append(f"RSI {rsi:.0f} above 50")
    else:
        bearish_signals += 1
        details.append(f"RSI {rsi:.0f} below 50")

    # MACD crossover
    if macd > macd_sig:
        bullish_signals += 1
        details.append("MACD above signal line")
    else:
        bearish_signals += 1
        details.append("MACD below signal line")

    # MACD crossover event
    prev_macd = prev.get("macd", 0) or 0
    prev_sig = prev.get("macd_signal", 0) or 0
    if macd > macd_sig and prev_macd <= prev_sig:
        bullish_signals += 1
        details.append("MACD bullish crossover just fired")
    elif macd < macd_sig and prev_macd >= prev_sig:
        bearish_signals += 1
        details.append("MACD bearish crossover just fired")

    # Price vs SMA20
    if sma20 and not math.isnan(sma20):
        if close > sma20:
            bullish_signals += 1
            details.append(f"Price above SMA20 ({sma20:.2f})")
        else:
            bearish_signals += 1
            details.append(f"Price below SMA20 ({sma20:.2f})")

    # SMA20 vs SMA50 (golden/death cross)
    if sma20 and sma50 and not math.isnan(sma20) and not math.isnan(sma50):
        if sma20 > sma50:
            bullish_signals += 1
            details.append("SMA20 > SMA50 (golden cross zone)")
        else:
            bearish_signals += 1
            details.append("SMA20 < SMA50 (death cross zone)")

    total = bullish_signals + bearish_signals
    if total < 3:
        return None

    if bullish_signals > bearish_signals:
        direction = "bullish"
        strength = bullish_signals / total
    elif bearish_signals > bullish_signals:
        direction = "bearish"
        strength = bearish_signals / total
    else:
        return None  # No clear signal

    return {
        "strategy": "Momentum Regime",
        "symbol": symbol,
        "direction": direction,
        "strength": round(strength * 100),
        "details": details,
        "prediction": (
            f"Momentum is {direction} ({bullish_signals}B/{bearish_signals}S) — "
            f"BUY {'YES' if direction == 'bullish' else 'NO'} on upside markets"
        ),
        "bullish_count": bullish_signals,
        "bearish_count": bearish_signals,
    }


# ── Strategy 3: TVL Divergence ───────────────────────────────────────────────────


def tvl_divergence(symbol: str) -> dict | None:
    """
    Detect divergence between token price trend and TVL.

    Price dropping + TVL rising = smart money accumulating (bullish).
    Price rising + TVL dropping = capital flight despite price (bearish).
    """
    mkt = get_market_data(symbol)
    tvl_data = get_tvl(symbol)

    if "error" in mkt or "error" in tvl_data:
        return None

    change_7d = mkt.get("change_7d_pct")
    change_30d = mkt.get("change_30d_pct")
    tvl = tvl_data.get("tvl_usd")

    if change_7d is None or tvl is None:
        return None

    # We don't have historical TVL from DefiLlama's simple endpoint,
    # so we use price trend as a proxy for the divergence check.
    # High TVL + negative price action = accumulation
    # Low TVL + positive price action = distribution
    details = []
    direction = "neutral"
    strength = 0.0

    price = mkt.get("price_usd", 0)
    mcap = mkt.get("market_cap_usd", 0)

    if tvl and mcap and mcap > 0:
        tvl_to_mcap = tvl / mcap
        details.append(f"TVL/MCap ratio: {tvl_to_mcap:.2%}")

        if change_7d < -5 and tvl_to_mcap > 0.3:
            # Price down but strong TVL relative to market cap
            direction = "bullish"
            strength = min(1.0, abs(change_7d) / 20 + tvl_to_mcap)
            details.append(
                f"Price down {change_7d:.1f}% 7d but TVL strong (${tvl / 1e9:.1f}B)"
            )
            details.append("Smart money may be accumulating")
        elif change_7d > 5 and tvl_to_mcap < 0.1:
            # Price up but weak TVL — possibly unsustainable
            direction = "bearish"
            strength = min(1.0, change_7d / 20 + (0.3 - tvl_to_mcap))
            details.append(
                f"Price up {change_7d:.1f}% 7d but TVL weak (${tvl / 1e9:.1f}B)"
            )
            details.append("Rally may lack fundamental support")
        else:
            return None
    else:
        return None

    return {
        "strategy": "TVL Divergence",
        "symbol": symbol,
        "direction": direction,
        "strength": round(strength * 100),
        "details": details,
        "prediction": (
            f"TVL divergence is {direction} — "
            f"BUY {'YES' if direction == 'bullish' else 'NO'} on upside markets"
        ),
        "tvl_usd": tvl,
        "price_change_7d": change_7d,
    }


# ── Strategy 4: Volatility Squeeze ───────────────────────────────────────────────


def volatility_squeeze(symbol: str, interval: str = "1m") -> dict | None:
    """
    Detect Bollinger Band squeeze — low volatility precedes breakouts.

    When BB width is at a local minimum, a large move is coming.
    Combined with RSI direction, we can estimate breakout direction.
    """
    df = _get_df(symbol, interval, limit=200)
    if df is None or len(df) < 50:
        return None

    latest = df.iloc[-1]
    bb_upper = latest.get("bb_upper")
    bb_lower = latest.get("bb_lower")
    bb_mid = latest.get("bb_mid")
    close = float(latest["close"])
    rsi = latest.get("rsi")

    if any(
        v is None or (isinstance(v, float) and math.isnan(v))
        for v in [bb_upper, bb_lower, bb_mid]
    ):
        return None

    # BB width as % of mid
    bb_width = (bb_upper - bb_lower) / bb_mid * 100

    # Compute historical BB width to find if current is a squeeze
    widths = []
    for _, row in df.tail(50).iterrows():
        u, l, m = row.get("bb_upper"), row.get("bb_lower"), row.get("bb_mid")
        if u and l and m and not any(math.isnan(x) for x in [u, l, m]) and m > 0:
            widths.append((u - l) / m * 100)

    if len(widths) < 20:
        return None

    avg_width = sum(widths) / len(widths)
    min_width = min(widths)

    # Squeeze = current width within 20% of the minimum
    is_squeeze = bb_width <= min_width * 1.2

    # Annualized volatility
    closes = df["close"].tolist()
    annual_vol = compute_annualized_vol(closes, interval)

    details = [f"BB width: {bb_width:.2f}% (avg: {avg_width:.2f}%)"]
    details.append(f"Annualized vol: {annual_vol:.0f}%")

    if is_squeeze:
        details.append("SQUEEZE DETECTED — breakout imminent")
        # Direction hint from RSI
        if rsi and not math.isnan(rsi):
            if rsi > 55:
                direction = "bullish"
                details.append(f"RSI {rsi:.0f} leans bullish")
            elif rsi < 45:
                direction = "bearish"
                details.append(f"RSI {rsi:.0f} leans bearish")
            else:
                direction = "neutral"
                details.append(
                    f"RSI {rsi:.0f} — direction unclear, but big move coming"
                )
        else:
            direction = "neutral"

        strength = min(1.0, (avg_width / max(bb_width, 0.01)) * 0.5)
    else:
        # Check for high volatility regime instead
        if bb_width > avg_width * 1.5:
            details.append("HIGH VOLATILITY — bands expanding")
            direction = "neutral"
            strength = 0.3
        else:
            return None  # Normal regime, no signal

    return {
        "strategy": "Volatility Squeeze",
        "symbol": symbol,
        "direction": direction,
        "strength": round(strength * 100),
        "details": details,
        "prediction": (
            f"{'Squeeze breakout' if is_squeeze else 'High vol'} — "
            f"expect large move {'up' if direction == 'bullish' else 'down' if direction == 'bearish' else '(direction TBD)'}"
        ),
        "bb_width": round(bb_width, 2),
        "avg_bb_width": round(avg_width, 2),
        "is_squeeze": is_squeeze,
        "annual_vol": round(annual_vol),
    }


# ── Run all strategies ───────────────────────────────────────────────────────────


def run_all_strategies(symbols: list[str], interval: str = "1m") -> list[dict]:
    """Run all strategies across all tracked symbols. Returns list of fired signals."""
    signals = []
    for sym in symbols:
        for strategy_fn in [
            liquidation_cascade,
            momentum_regime,
            tvl_divergence,
            volatility_squeeze,
        ]:
            try:
                if strategy_fn in (momentum_regime, volatility_squeeze):
                    result = strategy_fn(sym, interval)
                else:
                    result = strategy_fn(sym)
            except Exception:
                continue
            if result:
                signals.append(result)

    # Sort by strength descending
    signals.sort(key=lambda s: s["strength"], reverse=True)
    return signals
