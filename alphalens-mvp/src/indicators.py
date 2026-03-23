"""
Technical indicator computation from OHLCV DataFrames.

add_indicators(df)     → adds indicator columns in-place copy
indicator_summary(df)  → extracts latest values + derived signals for the LLM
"""
from __future__ import annotations

import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute and attach all technical indicators to a kline DataFrame.
    Expects columns: open, high, low, close, volume.
    Returns a new DataFrame (original is not mutated).
    """
    df = df.copy()
    close = df["close"]

    # ── Moving averages ──────────────────────────────────────────────────────
    df["sma_20"]   = close.rolling(20).mean()
    df["sma_50"]   = close.rolling(50).mean()
    df["ema_12"]   = close.ewm(span=12, adjust=False).mean()
    df["ema_26"]   = close.ewm(span=26, adjust=False).mean()

    # ── Bollinger Bands (20-period, ±2σ) ─────────────────────────────────────
    bb_mid         = close.rolling(20).mean()
    bb_std         = close.rolling(20).std(ddof=0)
    df["bb_upper"] = bb_mid + 2 * bb_std
    df["bb_lower"] = bb_mid - 2 * bb_std
    df["bb_mid"]   = bb_mid

    # ── RSI (14-period, Wilder smoothing via EWM) ─────────────────────────────
    delta          = close.diff()
    gain           = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
    loss           = (-delta).clip(lower=0).ewm(com=13, adjust=False).mean()
    df["rsi"]      = 100 - 100 / (1 + gain / loss.replace(0, float("nan")))

    # ── MACD (12, 26, 9) ──────────────────────────────────────────────────────
    df["macd"]        = df["ema_12"] - df["ema_26"]
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"]   = df["macd"] - df["macd_signal"]

    return df


def indicator_summary(df: pd.DataFrame) -> dict:
    """
    Extract the latest indicator values + human-readable derived signals
    to inject into the LLM prompt.
    """
    if len(df) < 2:
        return {}

    last = df.iloc[-1]
    prev = df.iloc[-2]

    def _f(key, decimals=4):
        v = last.get(key)
        return round(float(v), decimals) if v is not None and not pd.isna(v) else None

    close   = float(last["close"])
    rsi     = _f("rsi", 2)
    macd    = _f("macd", 6)
    sig     = _f("macd_signal", 6)
    hist    = _f("macd_hist", 6)
    phist   = float(prev.get("macd_hist", 0) or 0)
    sma20   = _f("sma_20")
    sma50   = _f("sma_50")
    bb_up   = _f("bb_upper")
    bb_lo   = _f("bb_lower")
    bb_mid  = _f("bb_mid")

    # RSI zone
    if rsi is not None:
        if rsi > 70:
            rsi_zone = f"overbought ({rsi})"
        elif rsi < 30:
            rsi_zone = f"oversold ({rsi})"
        else:
            rsi_zone = f"neutral ({rsi})"
    else:
        rsi_zone = "N/A"

    # MACD crossover detection
    macd_crossover = "none"
    if macd is not None and sig is not None:
        pm = float(prev.get("macd", 0) or 0)
        ps = float(prev.get("macd_signal", 0) or 0)
        if macd > sig and pm <= ps:
            macd_crossover = "bullish crossover (MACD just crossed above signal)"
        elif macd < sig and pm >= ps:
            macd_crossover = "bearish crossover (MACD just crossed below signal)"
        elif macd > sig:
            macd_crossover = "bullish (MACD above signal)"
        else:
            macd_crossover = "bearish (MACD below signal)"

    hist_direction = "expanding" if (hist and abs(hist) > abs(phist)) else "contracting"

    # Bollinger Band position
    bb_position = "N/A"
    if bb_up is not None and bb_lo is not None:
        bw = bb_up - bb_lo
        if bw > 0:
            pct = (close - bb_lo) / bw * 100
            if close > bb_up:
                bb_position = f"above upper band ({pct:.0f}% of width)"
            elif close < bb_lo:
                bb_position = f"below lower band ({pct:.0f}% of width)"
            else:
                bb_position = f"{pct:.0f}% of band width (upper={bb_up}, lower={bb_lo})"

    # MA trend
    ma_context_parts = []
    if sma20:
        rel = "above" if close > sma20 else "below"
        ma_context_parts.append(f"SMA20={sma20} (price {rel})")
    if sma50:
        rel = "above" if close > sma50 else "below"
        ma_context_parts.append(f"SMA50={sma50} (price {rel})")
    ma_context = ", ".join(ma_context_parts) or "N/A"

    return {
        "rsi":              rsi,
        "rsi_zone":         rsi_zone,
        "macd":             macd,
        "macd_signal":      sig,
        "macd_hist":        hist,
        "macd_hist_dir":    hist_direction,
        "macd_crossover":   macd_crossover,
        "sma_20":           sma20,
        "sma_50":           sma50,
        "bb_upper":         bb_up,
        "bb_lower":         bb_lo,
        "bb_mid":           bb_mid,
        "bb_position":      bb_position,
        "ma_context":       ma_context,
    }
