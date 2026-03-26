"""
Quick-action prompt templates for the Research tab.

Each entry is (button_label, emoji, prompt_template).
{symbol} is replaced with the active ticker (e.g. "BTC") before sending.

Design principle: "users don't know what they don't know."
Each button answers a question a retail trader should be asking but often isn't.
"""

from __future__ import annotations

QUICK_PROMPTS: list[tuple[str, str, str]] = [
    (
        "Full Deep Dive",
        "📋",
        (
            "Generate a comprehensive investment research report for {symbol}. "
            "Call ALL available tools: get_market_data, get_tvl (if applicable), "
            "get_funding_rate, get_open_interest, get_technical_analysis, "
            "get_prediction_markets, and get_crypto_news. "
            "Structure the report with: Executive Summary, Market Context, "
            "Technical Analysis, Derivatives Sentiment, Prediction Market Signals, "
            "Latest News & Narratives, "
            "Investment Thesis (bull vs bear), Risk Assessment, and a plain-English Verdict. "
            "Cite [Source] after every number."
        ),
    ),
    (
        "Technical Setup",
        "📈",
        (
            "What is the current technical setup for {symbol}? "
            "Use get_technical_analysis to get live RSI, MACD, Bollinger Bands, and "
            "moving averages. Then tell me: "
            "1) What is the trend direction and momentum? "
            "2) Are there any clear patterns or signals firing right now? "
            "3) What are the key price levels to watch? "
            "4) Give me a suggested entry zone, target, and stop-loss. "
            "Be specific with price numbers."
        ),
    ),
    (
        "Market Sentiment",
        "🌊",
        (
            "What is the current market sentiment for {symbol}? "
            "Use get_funding_rate and get_open_interest to check if the futures market "
            "is overleveraged. Also call get_technical_analysis for momentum signals. "
            "I want to know: Is the crowd bullish or bearish? "
            "Are longs or shorts at risk of getting squeezed or liquidated? "
            "What does this mean for price direction in the next few hours?"
        ),
    ),
    (
        "Prediction Markets",
        "🎯",
        (
            "What are the active Polymarket prediction markets for {symbol}? "
            "Use get_prediction_markets to get the live crowd-sourced probabilities. "
            "Then use get_market_data to get the current price context. "
            "For each market, explain: What is being bet on? "
            "What probability is the crowd pricing in? "
            "Does the current price action support or contradict these bets? "
            "Are there any markets with interesting risk/reward for a trader?"
        ),
    ),
    (
        "Key Risks",
        "⚠️",
        (
            "What are the biggest risks for {symbol} right now? "
            "Use get_technical_analysis to check for bearish signals, "
            "get_funding_rate and get_open_interest to check for overleverage risk, "
            "and get_market_data for macro context (ATH distance, market cap rank). "
            "Give me: the top 3 risks ranked by severity, "
            "what price levels would confirm each risk materialising, "
            "and how a cautious investor should position given these risks."
        ),
    ),
    (
        "Worth Buying?",
        "💰",
        (
            "Should I buy {symbol} right now? "
            "Use get_technical_analysis to assess the setup, "
            "get_funding_rate to check if the market is already crowded, "
            "get_market_data for broader context, "
            "and get_prediction_markets to see what the crowd thinks. "
            "Give me a clear verdict: YES / NO / WAIT — with the reasoning. "
            "If yes or wait, give me a specific entry price, price target, "
            "stop-loss, and position size suggestion (as % of portfolio). "
            "Be honest about uncertainty."
        ),
    ),
    (
        "News Briefing",
        "📰",
        (
            "What are the latest news and narratives around {symbol}? "
            "Use get_crypto_news to get the latest headlines. "
            "Also use get_market_data for price context. "
            "Summarize: 1) The top 3-5 most important stories and what they mean, "
            "2) Is the overall news sentiment bullish, bearish, or mixed? "
            "3) Are there any catalysts or events coming up? "
            "4) How does the news narrative align with the current price action? "
            "Cite the source outlet for each story."
        ),
    ),
]
