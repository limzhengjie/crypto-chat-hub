"""
Binance partial depth WebSocket stream + thread-safe in-memory order book.

Stream: <symbol>@depth20@1000ms
  → full snapshot of top 20 bid/ask levels, pushed every 1 second.
  → each message REPLACES the book (not a delta).
"""

from __future__ import annotations

import json
import os
import ssl
import threading
import time
from typing import Optional

import websocket

BINANCE_WS_URLS = [
    "wss://stream.binance.com:9443/ws",
    "wss://stream.binance.us:9443/ws",
]


def _ws_sslopt() -> dict:
    """
    Build websocket-client SSL options.

    - Default: system verification (no overrides).
    - If BINANCE_WS_CA_CERT or SSL_CERT_FILE is set: trust that CA bundle.
    - If BINANCE_WS_INSECURE=1/true/yes: disable verification (dev fallback).
    """
    ca_cert = os.getenv("BINANCE_WS_CA_CERT") or os.getenv("SSL_CERT_FILE")
    if ca_cert:
        return {"cert_reqs": ssl.CERT_REQUIRED, "ca_certs": ca_cert}

    insecure = (os.getenv("BINANCE_WS_INSECURE") or "").strip().lower()
    if insecure in {"1", "true", "yes", "on"}:
        print("[OB] Warning: TLS verification disabled (BINANCE_WS_INSECURE).")
        return {"cert_reqs": ssl.CERT_NONE, "check_hostname": False}
    return {}


class OrderBook:
    """Thread-safe snapshot of the top-N bid and ask levels."""

    def __init__(self) -> None:
        self.bids: list[tuple[float, float]] = []  # [(price, qty)] highest first
        self.asks: list[tuple[float, float]] = []  # [(price, qty)] lowest first
        self.last_update_ms: int = 0
        self._lock = threading.Lock()

    def update(self, bids: list, asks: list, ts: int) -> None:
        with self._lock:
            self.bids = sorted(
                [(float(b[0]), float(b[1])) for b in bids],
                key=lambda x: x[0],
                reverse=True,  # highest bid first
            )
            self.asks = sorted(
                [(float(a[0]), float(a[1])) for a in asks],
                key=lambda x: x[0],  # lowest ask first
            )
            self.last_update_ms = ts

    def snapshot(self) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        with self._lock:
            return list(self.bids), list(self.asks)

    @property
    def best_bid(self) -> Optional[float]:
        with self._lock:
            return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        with self._lock:
            return self.asks[0][0] if self.asks else None

    @property
    def spread(self) -> Optional[float]:
        with self._lock:
            if self.bids and self.asks:
                return round(self.asks[0][0] - self.bids[0][0], 8)
        return None

    @property
    def spread_pct(self) -> Optional[float]:
        with self._lock:
            if self.bids and self.asks:
                mid = (self.asks[0][0] + self.bids[0][0]) / 2
                return round((self.asks[0][0] - self.bids[0][0]) / mid * 100, 4)
        return None

    @property
    def mid_price(self) -> Optional[float]:
        with self._lock:
            if self.bids and self.asks:
                return (self.asks[0][0] + self.bids[0][0]) / 2
        return None

    @property
    def has_data(self) -> bool:
        with self._lock:
            return bool(self.bids and self.asks)


class BinanceOrderBookStream:
    """
    Subscribes to the Binance partial depth stream for one symbol and
    maintains a live OrderBook object updated on every tick.
    """

    def __init__(self, symbol: str = "BTCUSDT", depth: int = 20) -> None:
        self.symbol = symbol.upper()
        self.depth = depth
        self.book = OrderBook()
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self.is_running = False
        self._stopped = False

    def _on_open(self, ws) -> None:
        self.is_running = True
        print(f"[OB]  Connected  →  {self.symbol}@depth{self.depth}")

    def _on_message(self, ws, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        self.book.update(
            bids=msg.get("bids", []),
            asks=msg.get("asks", []),
            ts=msg.get("T", 0),
        )

    def _on_error(self, ws, error) -> None:
        print(f"[OB]  Error: {error}")

    def _on_close(self, ws, code, msg) -> None:
        self.is_running = False
        print(f"[OB]  Closed (code={code})")

    def _run_with_reconnect(self) -> None:
        stream_path = f"{self.symbol.lower()}@depth{self.depth}@1000ms"
        sslopt = _ws_sslopt()
        while not self._stopped:
            for base_url in BINANCE_WS_URLS:
                if self._stopped:
                    return
                url = f"{base_url}/{stream_path}"
                self._ws = websocket.WebSocketApp(
                    url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self._ws.run_forever(
                    ping_interval=30,
                    ping_timeout=10,
                    sslopt=sslopt,
                )
                if self._stopped:
                    return
            time.sleep(3)

    def start(self) -> None:
        self._stopped = False
        self._thread = threading.Thread(
            target=self._run_with_reconnect,
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stopped = True
        if self._ws:
            self._ws.close()
        self.is_running = False
