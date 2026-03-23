from __future__ import annotations

import sqlite3
import os
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "alphalens.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        # If the table exists but is missing the `interval` column (old schema),
        # drop it so we start fresh with the correct schema.
        cols = [r[1] for r in conn.execute("PRAGMA table_info(klines)").fetchall()]
        if cols and "interval" not in cols:
            conn.execute("DROP TABLE IF EXISTS klines")
            conn.execute("DROP INDEX IF EXISTS idx_symbol_time")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS klines (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol       TEXT    NOT NULL,
                interval     TEXT    NOT NULL DEFAULT '1m',
                open_time    INTEGER NOT NULL,
                open         REAL    NOT NULL,
                high         REAL    NOT NULL,
                low          REAL    NOT NULL,
                close        REAL    NOT NULL,
                volume       REAL    NOT NULL,
                is_closed    INTEGER NOT NULL DEFAULT 0,
                UNIQUE(symbol, interval, open_time)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_symbol_interval_time "
            "ON klines (symbol, interval, open_time)"
        )
        conn.commit()


def upsert_kline(
    symbol: str,
    interval: str,
    open_time: int,
    open: float,
    high: float,
    low: float,
    close: float,
    volume: float,
    is_closed: bool,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO klines (symbol, interval, open_time, open, high, low, close, volume, is_closed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, interval, open_time) DO UPDATE SET
                high      = excluded.high,
                low       = excluded.low,
                close     = excluded.close,
                volume    = excluded.volume,
                is_closed = excluded.is_closed
            """,
            (symbol, interval, open_time, open, high, low, close, volume, int(is_closed)),
        )
        conn.commit()


def get_klines(symbol: str, interval: str = "1m", limit: int = 100) -> list:
    """Return up to `limit` most recent klines for a symbol+interval, oldest-first."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT open_time, open, high, low, close, volume
            FROM (
                SELECT open_time, open, high, low, close, volume
                FROM klines
                WHERE symbol = ? AND interval = ?
                ORDER BY open_time DESC
                LIMIT ?
            )
            ORDER BY open_time ASC
            """,
            (symbol, interval, limit),
        ).fetchall()
    return [tuple(r) for r in rows]


def get_latest_price(symbol: str, interval: str = "1m") -> Optional[float]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT close FROM klines WHERE symbol = ? AND interval = ? "
            "ORDER BY open_time DESC LIMIT 1",
            (symbol, interval),
        ).fetchone()
    return row[0] if row else None
