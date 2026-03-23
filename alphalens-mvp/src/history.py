"""
Backfill SQLite with historical klines from the Binance REST API.
No API key required — public endpoint.
"""
from __future__ import annotations

import requests

from .database import upsert_kline

BINANCE_REST = "https://api.binance.com/api/v3"


def fetch_historical_klines(
    symbol: str,
    interval: str = "1m",
    limit: int = 500,
) -> int:
    """
    Fetch up to `limit` closed klines (max 1000) and upsert into SQLite.
    Returns the number of rows written, or 0 on failure.

    Binance kline columns:
      0  open_time       ms timestamp
      1  open
      2  high
      3  low
      4  close
      5  volume
      6  close_time
      7+ (ignored)
    """
    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": min(limit, 1000),
    }
    try:
        resp = requests.get(f"{BINANCE_REST}/klines", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"[history] {symbol}/{interval} fetch failed: {exc}")
        return 0

    for k in data:
        upsert_kline(
            symbol=symbol.upper(),
            interval=interval,
            open_time=int(k[0]),
            open=float(k[1]),
            high=float(k[2]),
            low=float(k[3]),
            close=float(k[4]),
            volume=float(k[5]),
            is_closed=True,
        )

    print(f"[history] {symbol}/{interval}: loaded {len(data)} candles")
    return len(data)
