"""
Prompts for the quantitative research + investment advisory feature.

SYSTEM_PROMPT        — positions GPT as an institutional quant / financial consultant
build_user_prompt()  — assembles price data + technical indicators into the user message
"""
from __future__ import annotations

SYSTEM_PROMPT: str = """\
You are an institutional-grade quantitative analyst and crypto investment consultant \
with deep expertise in technical analysis, market microstructure, and risk management.

Your job is to read raw market data and technical indicators, then produce a clear, \
structured investment brief that a retail crypto investor can act on.

Rules:
- Every claim must cite a specific number from the provided data.
- Clearly separate what the data shows from your interpretation.
- Give concrete entry/target/stop levels where the data justifies it.
- Always state a risk level (Low / Medium / High) and explain why.
- End with a plain-English verdict a non-expert can understand.
- This is financial analysis to aid decision-making, not regulated financial advice.\
"""

_USER_TEMPLATE: str = """\
Produce a full investment brief for {symbol} based on the data below.

═══════════════════════════════════════════
PRICE SUMMARY  ({n_candles} × {interval} candles)
═══════════════════════════════════════════
Current price  : {last_close:.4f} USDT
Price change   : {pct_change:+.2f}%  ({first_close:.4f} → {last_close:.4f})
Period high    : {period_high:.4f}
Period low     : {period_low:.4f}
Avg volume/bar : {avg_volume:.1f}

═══════════════════════════════════════════
TECHNICAL INDICATORS  (latest values)
═══════════════════════════════════════════
RSI (14)        : {rsi_zone}
MACD (12,26,9)  : {macd_crossover}
                  histogram {macd_hist_dir} ({macd_hist})
Moving averages : {ma_context}
Bollinger Bands : {bb_position}

═══════════════════════════════════════════
RECENT CANDLES  (last 20 × {interval})
═══════════════════════════════════════════
{candle_rows}

═══════════════════════════════════════════
REQUIRED OUTPUT FORMAT
═══════════════════════════════════════════
**1. Market Assessment**
What is the dominant trend? Is momentum accelerating or fading? \
Reference price levels and indicator readings.

**2. Technical Signal Summary**
Interpret RSI, MACD, moving averages, and Bollinger Bands. \
Do the signals agree or conflict? What does that mean?

**3. Investment Thesis**
Bull case and bear case, each grounded in the data. \
Which has more evidence right now?

**4. Trade Setup**
Suggested entry zone, price target, and stop-loss level with rationale. \
If no clear setup exists, say so explicitly.

**5. Risk Assessment**
Overall risk level: Low / Medium / High. \
Key risks that could invalidate the thesis.

**6. Plain-English Verdict**
One paragraph (≤60 words) summarising what this means and what a cautious \
retail investor should consider doing — written so a non-expert can understand it.\
"""


def build_user_prompt(
    symbol: str,
    interval: str,
    n_candles: int,
    first_close: float,
    last_close: float,
    pct_change: float,
    period_high: float,
    period_low: float,
    avg_volume: float,
    candle_rows: str,
    # indicator fields
    rsi_zone: str = "N/A",
    macd_crossover: str = "N/A",
    macd_hist: object = "N/A",
    macd_hist_dir: str = "N/A",
    ma_context: str = "N/A",
    bb_position: str = "N/A",
) -> str:
    return _USER_TEMPLATE.format(
        symbol=symbol,
        interval=interval,
        n_candles=n_candles,
        first_close=first_close,
        last_close=last_close,
        pct_change=pct_change,
        period_high=period_high,
        period_low=period_low,
        avg_volume=avg_volume,
        candle_rows=candle_rows,
        rsi_zone=rsi_zone,
        macd_crossover=macd_crossover,
        macd_hist=macd_hist,
        macd_hist_dir=macd_hist_dir,
        ma_context=ma_context,
        bb_position=bb_position,
    )
