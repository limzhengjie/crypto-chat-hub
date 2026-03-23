"""
Probability estimation engine for prediction markets.

Uses geometric Brownian motion with indicator-adjusted drift to estimate
P(price > threshold at expiry). This is the same math as Black-Scholes
for a digital option — which is exactly what a prediction market contract is.
"""

from __future__ import annotations

import math


def norm_cdf(x: float) -> float:
    """Standard normal CDF via math.erf (no scipy needed)."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def compute_annualized_vol(closes: list[float], interval: str) -> float:
    """Compute annualized volatility from a list of close prices."""
    if len(closes) < 10:
        return 0.0

    log_returns = [
        math.log(closes[i] / closes[i - 1])
        for i in range(1, len(closes))
        if closes[i - 1] > 0
    ]
    if len(log_returns) < 5:
        return 0.0

    n = len(log_returns)
    mean = sum(log_returns) / n
    variance = sum((r - mean) ** 2 for r in log_returns) / (n - 1)
    interval_vol = math.sqrt(variance)

    periods_per_year = {
        "1m": 365.25 * 24 * 60,
        "3m": 365.25 * 24 * 20,
        "5m": 365.25 * 24 * 12,
        "15m": 365.25 * 24 * 4,
        "1h": 365.25 * 24,
        "4h": 365.25 * 6,
        "1d": 365.25,
    }
    factor = periods_per_year.get(interval, 365.25 * 24 * 60)
    return interval_vol * math.sqrt(factor)


def estimate_probability(
    current_price: float,
    threshold: float,
    hours_to_expiry: float,
    annual_vol: float,
    direction: str = "above",
    rsi: float | None = None,
    macd_bullish: bool | None = None,
    funding_rate: float | None = None,
) -> tuple[float, float, list[str]]:
    """
    Estimate P(price crosses threshold by expiry).

    Returns (probability, confidence, signal_descriptions).
    """
    signals: list[str] = []

    if hours_to_expiry <= 0:
        at_target = (
            current_price > threshold
            if direction == "above"
            else current_price < threshold
        )
        return (1.0 if at_target else 0.0), 1.0, ["Expired"]

    if annual_vol <= 0:
        return 0.5, 0.0, ["No volatility data"]

    T = hours_to_expiry / (365.25 * 24)
    mu = 0.0  # base drift: assume no directional bias

    # ── Indicator adjustments to annualized drift ────────────────────────────
    if rsi is not None and not math.isnan(rsi):
        if rsi > 70:
            mu -= 0.15
            signals.append(f"RSI {rsi:.0f} overbought")
        elif rsi < 30:
            mu += 0.15
            signals.append(f"RSI {rsi:.0f} oversold")
        else:
            signals.append(f"RSI {rsi:.0f}")

    if macd_bullish is not None:
        if macd_bullish:
            mu += 0.08
            signals.append("MACD bullish")
        else:
            mu -= 0.08
            signals.append("MACD bearish")

    if funding_rate is not None:
        if funding_rate > 0.0003:
            mu -= 0.12
            signals.append(f"Funding +{funding_rate * 100:.3f}% overleveraged longs")
        elif funding_rate < -0.0003:
            mu += 0.12
            signals.append(f"Funding {funding_rate * 100:.3f}% overleveraged shorts")

    # GBM: d2 = (ln(S/K) + (μ - σ²/2)T) / (σ√T)
    d2 = (math.log(current_price / threshold) + (mu - 0.5 * annual_vol**2) * T) / (
        annual_vol * math.sqrt(T)
    )
    prob_above = norm_cdf(d2)

    prob = prob_above if direction == "above" else 1 - prob_above
    prob = max(0.01, min(0.99, prob))

    # Confidence: signal agreement + time horizon
    directional = [
        s
        for s in signals
        if "bullish" in s or "oversold" in s or "overleveraged shorts" in s
    ]
    bearish = [
        s
        for s in signals
        if "bearish" in s or "overbought" in s or "overleveraged longs" in s
    ]
    signal_count = len(directional) + len(bearish)
    if signal_count > 0:
        agreement = max(len(directional), len(bearish)) / signal_count
    else:
        agreement = 0.5
    time_factor = min(1.0, 168 / max(hours_to_expiry, 1))
    confidence = 0.3 + 0.4 * agreement + 0.3 * time_factor
    confidence = max(0.1, min(0.95, confidence))

    return prob, confidence, signals
