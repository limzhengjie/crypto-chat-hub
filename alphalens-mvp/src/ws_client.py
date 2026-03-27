from __future__ import annotations

import json
import os
import ssl
import threading
from typing import Optional

import websocket

from .database import upsert_kline

BINANCE_WS_BASE = "wss://stream.binance.com:9443/ws"


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
        print("[WS] Warning: TLS verification disabled (BINANCE_WS_INSECURE).")
        return {"cert_reqs": ssl.CERT_NONE, "check_hostname": False}
    return {}


class BinanceKlineStream:
    """
    Subscribes to a single Binance kline WebSocket stream and persists
    every message to SQLite via upsert_kline().

    Usage:
        stream = BinanceKlineStream("BTCUSDT", "1m")
        stream.start()   # non-blocking — runs in daemon thread
        ...
        stream.stop()
    """

    def __init__(self, symbol: str = "BTCUSDT", interval: str = "1m") -> None:
        self.symbol = symbol.upper()
        self.interval = interval
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self.is_running = False

    # ------------------------------------------------------------------ #
    # WebSocket callbacks                                                  #
    # ------------------------------------------------------------------ #

    def _on_open(self, ws: websocket.WebSocketApp) -> None:
        self.is_running = True
        print(f"[WS] Connected  →  {self.symbol}@kline_{self.interval}")

    def _on_message(self, ws: websocket.WebSocketApp, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        if msg.get("e") != "kline":
            return

        k = msg["k"]
        upsert_kline(
            symbol=k["s"],
            interval=k["i"],
            open_time=k["t"],
            open=float(k["o"]),
            high=float(k["h"]),
            low=float(k["l"]),
            close=float(k["c"]),
            volume=float(k["v"]),
            is_closed=k["x"],
        )

    def _on_error(self, ws: websocket.WebSocketApp, error: Exception) -> None:
        print(f"[WS] Error: {error}")

    def _on_close(
        self, ws: websocket.WebSocketApp, code: int, msg: str
    ) -> None:
        self.is_running = False
        print(f"[WS] Closed  (code={code})")

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        url = f"{BINANCE_WS_BASE}/{self.symbol.lower()}@kline_{self.interval}"
        self._ws = websocket.WebSocketApp(
            url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._thread = threading.Thread(
            target=self._ws.run_forever,
            kwargs={
                "ping_interval": 30,
                "ping_timeout": 10,
                "sslopt": _ws_sslopt(),
            },
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._ws:
            self._ws.close()
        self.is_running = False
