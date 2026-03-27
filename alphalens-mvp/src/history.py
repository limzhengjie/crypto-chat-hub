"""
Backfill SQLite with historical klines from the Binance REST API.
No API key required — public endpoint.
"""

from __future__ import annotations

import requests

from .database import upsert_klines_batch


BINANCE_REST_URLS = [
    "https://api.binance.com/api/v3",
    "https://api.binance.us/api/v3",
    "https://data-api.binance.vision/api/v3",
]


def fetch_historical_klines(
    symbol: str,
    interval: str = "1m",
    limit: int = 500,
) -> int:
    """
    Fetch up to `limit` closed klines (max 1000) and upsert into SQLite.
    Returns the number of rows written, or 0 on failure.
    Tries multiple Binance API endpoints as fallback.

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
    data = None
    for base_url in BINANCE_REST_URLS:
        try:
            resp = requests.get(f"{base_url}/klines", params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as exc:
            print(f"[history] {symbol}/{interval} fetch failed ({base_url}): {exc}")
            continue
    if not data:
        return 0

    sym = symbol.upper()
    rows = [
        (
            sym,
            interval,
            int(k[0]),
            float(k[1]),
            float(k[2]),
            float(k[3]),
            float(k[4]),
            float(k[5]),
            1,
        )
        for k in data
    ]
    upsert_klines_batch(rows)

    print(f"[history] {symbol}/{interval}: loaded {len(data)} candles")
    return len(data)
