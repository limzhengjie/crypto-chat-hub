"""
AlphaLens research agent — GPT-4o with tool use.

The agent loop: send user message → GPT-4o decides which tools to call →
execute tools → feed results back → repeat until GPT-4o responds with text.
"""

from __future__ import annotations

import json
import os
from typing import Callable

from openai import OpenAI

from src.tools import TOOL_DEFINITIONS, TOOL_DISPATCH

SYSTEM_PROMPT = """\
You are AlphaLens, an institutional-grade crypto research agent built for self-directed \
retail investors who want clarity without noise.

You have access to real-time data tools. You MUST call tools before making any claims. \
Never guess or hallucinate numbers.

Available tools:
- get_market_data       → price, market cap, rank, 24h/7d/30d changes, ATH, supply [CoinGecko]
- get_tvl               → DeFi TVL for blockchain ecosystems [DefiLlama]
- get_funding_rate      → perpetual futures funding rate — is the market overleveraged? [Binance]
- get_open_interest     → futures open interest — positioning size [Binance]
- get_technical_analysis → RSI, MACD, Bollinger Bands, moving averages [Binance live]
- get_prediction_markets → crowd-sourced probability markets for price events [Polymarket]

Rules:
- Cite source in [brackets] after every data point: "BTC is at $67,200 [Binance]"
- Separate what the data shows from your interpretation
- If a tool returns an error, say so — never fabricate data
- For investment questions, always present both bull and bear case
- End every substantive analysis with a Risk Level: Low / Medium / High
- Lead with the answer, then support with data — retail investors are busy
- You are a research tool, not a licensed financial advisor\
"""

DEEP_DIVE_PROMPT = """\
Generate a comprehensive investment research report for {symbol}.

Fetch ALL available data by calling these tools:
1. get_market_data — price, market cap, rank, changes, ATH, supply
2. get_tvl — DeFi TVL (skip if not applicable to this token)
3. get_funding_rate — derivatives sentiment
4. get_open_interest — derivatives positioning
5. get_technical_analysis — RSI, MACD, Bollinger Bands, moving averages

Then write the report in this structure:

## Executive Summary
3 bullets: what this asset is, where it stands now, and the key signal.

## Market Context
Price, market cap rank, 24h/7d/30d performance, ATH distance, supply dynamics.

## On-Chain & DeFi
TVL and ecosystem health. Skip this section entirely if not a DeFi chain.

## Technical Analysis
RSI, MACD, moving averages, Bollinger Bands, key support/resistance levels.

## Derivatives Sentiment
Funding rates, open interest, what the futures market is signaling.

## Investment Thesis
Bull case (3 data-backed points) vs Bear case (3 data-backed points).

## Risk Assessment
Risk level: Low / Medium / High. Key risks enumerated.

## Verdict
One paragraph (max 80 words) for a non-expert: what does this all mean?

Cite [Source] after every number.\
"""


def _get_client() -> tuple[OpenAI, str]:
    """Return (client, model_name) — prefers Gemini if key is present."""
    gemini_key = os.getenv("GEMINI_API_KEY")
    openai_key  = os.getenv("OPENAI_API_KEY") or os.getenv("gpt_api_key")

    if gemini_key:
        client = OpenAI(
            api_key=gemini_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        return client, "gemini-2.0-flash"

    client = OpenAI(api_key=openai_key)
    return client, "gpt-4o"


def run_agent(
    user_message: str,
    history: list[dict] | None = None,
    max_rounds: int = 6,
    on_tool_call: Callable[[str, dict], None] | None = None,
) -> tuple[str, list[dict]]:
    """
    Run the research agent loop.

    Returns (response_text, tool_log).
    tool_log: list of {"tool": name, "args": {}, "result": {}}.
    on_tool_call: optional callback fired before each tool executes (for UI progress).
    """
    client, model = _get_client()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    tool_log: list[dict] = []

    for _ in range(max_rounds):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            temperature=0,
        )
        msg = resp.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            return msg.content or "", tool_log

        for call in msg.tool_calls:
            name = call.function.name
            args = json.loads(call.function.arguments)

            if on_tool_call:
                on_tool_call(name, args)

            fn = TOOL_DISPATCH.get(name)
            result = fn(**args) if fn else {"error": f"Unknown tool: {name}"}
            tool_log.append({"tool": name, "args": args, "result": result})

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, default=str),
                }
            )

    return "Analysis complete (reached tool-call limit).", tool_log


def deep_dive(
    symbol: str,
    on_tool_call: Callable[[str, dict], None] | None = None,
) -> tuple[str, list[dict]]:
    """Generate a comprehensive research report for a token."""
    return run_agent(
        DEEP_DIVE_PROMPT.format(symbol=symbol),
        on_tool_call=on_tool_call,
    )
