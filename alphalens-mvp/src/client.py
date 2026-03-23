from __future__ import annotations

import json
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import Optional

import openai
from openai import OpenAI


# ── Rate limiter ────────────────────────────────────────────────────────────────

class RateLimiter:
    """Token-bucket rate limiter (thread-safe)."""

    def __init__(self, max_calls: int, period: float) -> None:
        self.max_calls = max_calls
        self.period = period
        self.lock = threading.Lock()
        self.allowance = float(max_calls)
        self.last_check = time.time()

    def acquire(self) -> None:
        while True:
            with self.lock:
                now = time.time()
                elapsed = now - self.last_check
                self.last_check = now
                self.allowance += elapsed * (self.max_calls / self.period)
                if self.allowance > self.max_calls:
                    self.allowance = float(self.max_calls)
                if self.allowance >= 1.0:
                    self.allowance -= 1.0
                    return
            time.sleep(0.01)


# ── GPT client (standard OpenAI — no Azure) ─────────────────────────────────────

class GPTClient:
    """
    Thin wrapper around openai.OpenAI for the AlphaLens MVP.

    Reads OPENAI_API_KEY from the environment (or .env via python-dotenv).
    Supports single call and parallel batch_call.
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        max_tokens: int = 1024,
        temperature: float = 0,
        top_p: float = 0.95,
        concurrency: int = 8,
        rate_limit: int = 500,       # requests per minute
    ) -> None:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("gpt_api_key")
        if not api_key:
            raise EnvironmentError(
                "No OpenAI API key found. Set OPENAI_API_KEY or gpt_api_key in your .env file."
            )
        self._client = OpenAI(api_key=api_key)
        self.rate_limiter = RateLimiter(max_calls=rate_limit, period=60)
        self.concurrency = concurrency
        self.defaults = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }

    def __call__(self, messages: list[dict], **kwargs) -> Optional[str]:
        """Single blocking call. Returns the assistant message string, or raises on failure."""
        self.rate_limiter.acquire()
        config = {**self.defaults, **kwargs}
        last_exc: Exception = RuntimeError("Unknown error")
        for attempt in range(3):
            try:
                resp = self._client.chat.completions.create(
                    messages=messages,
                    **config,
                )
                return resp.choices[0].message.content
            except openai.RateLimitError as exc:
                last_exc = exc
                print(f"[GPTClient] rate limit (attempt {attempt + 1}), retrying…")
                time.sleep(2 ** attempt)
            except Exception as exc:
                last_exc = exc
                print(f"[GPTClient] error (attempt {attempt + 1}): {exc}")
                time.sleep(1)
        raise last_exc

    def batch_call(
        self,
        prompts: list[list[dict]],
        batch_size: int = 100,
        **kwargs,
    ) -> list[Optional[str]]:
        """Parallel batch call. prompts is a list of message lists."""
        all_responses: list[Optional[str]] = []

        for i in range(0, len(prompts), batch_size):
            batch = prompts[i : i + batch_size]
            with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
                futures = [executor.submit(self, msg, **kwargs) for msg in batch]
                all_responses.extend(f.result() for f in futures)
            if i + batch_size < len(prompts):
                time.sleep(1)

        return all_responses
