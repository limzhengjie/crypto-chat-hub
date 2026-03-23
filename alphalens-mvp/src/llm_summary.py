from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from .client import GPTClient
from .indicators import add_indicators, indicator_summary
from .prompts import SYSTEM_PROMPT, build_user_prompt

_client: Optional[GPTClient] = None


def _get_client() -> GPTClient:
    global _client
    if _client is None:
        _client = GPTClient(model="gpt-4o", max_tokens=1200, temperature=0)
    return _client


def summarize_trend(symbol: str, klines: list, interval: str = "1m") -> str:
    """
    Build a full investment brief for `symbol` using kline data + technical
    indicators, then call GPT-4o and return the markdown response.
    """
    if not klines:
        return "No data available to analyze."

    # Build DataFrame and compute all indicators
    df = pd.DataFrame(
        klines, columns=["open_time", "open", "high", "low", "close", "volume"]
    )
    df = add_indicators(df)

    closes = df["close"].tolist()
    first_close = closes[0]
    last_close  = closes[-1]
    pct_change  = ((last_close - first_close) / first_close) * 100
    period_high = df["high"].max()
    period_low  = df["low"].min()
    avg_volume  = df["volume"].mean()

    candle_rows = "\n".join(
        f"  {datetime.fromtimestamp(row.open_time / 1000, tz=timezone.utc).strftime('%H:%M')} UTC  "
        f"O={row.open:.4f}  H={row.high:.4f}  L={row.low:.4f}  "
        f"C={row.close:.4f}  V={row.volume:.1f}  "
        f"RSI={row.rsi:.1f}" if not pd.isna(row.rsi) else
        f"  {datetime.fromtimestamp(row.open_time / 1000, tz=timezone.utc).strftime('%H:%M')} UTC  "
        f"O={row.open:.4f}  H={row.high:.4f}  L={row.low:.4f}  "
        f"C={row.close:.4f}  V={row.volume:.1f}"
        for row in df.tail(20).itertuples()
    )

    ind = indicator_summary(df)

    user_msg = build_user_prompt(
        symbol=symbol,
        interval=interval,
        n_candles=len(klines),
        first_close=first_close,
        last_close=last_close,
        pct_change=pct_change,
        period_high=period_high,
        period_low=period_low,
        avg_volume=avg_volume,
        candle_rows=candle_rows,
        rsi_zone=ind.get("rsi_zone", "N/A"),
        macd_crossover=ind.get("macd_crossover", "N/A"),
        macd_hist=ind.get("macd_hist", "N/A"),
        macd_hist_dir=ind.get("macd_hist_dir", "N/A"),
        ma_context=ind.get("ma_context", "N/A"),
        bb_position=ind.get("bb_position", "N/A"),
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_msg},
    ]

    return _get_client()(messages)
