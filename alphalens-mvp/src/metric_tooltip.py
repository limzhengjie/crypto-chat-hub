"""
Dashboard metric tooltips via native ``st.metric(..., help=...)``.

Custom ``st.html`` cards were not reliably rendered in the app (sanitization /
fragment lifecycle), so tooltips use Streamlit's built-in help popover, which
supports Markdown and works on hover and click/tap.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

# Tooltip copy keyed by metric label (shown in Streamlit's help popover).
METRIC_TOOLTIP_BODIES: dict[str, str] = {
    "Price (USDT)": (
        "The latest traded price of the asset in USDT, updated in real time."
    ),
    "Period High": (
        "The highest price reached within the currently loaded candle window."
    ),
    "Period Low": (
        "The lowest price reached within the currently loaded candle window."
    ),
    "Volume": (
        "Total number of asset units traded during the selected candle period."
    ),
    "RSI (14)": (
        "Relative Strength Index over 14 periods. Above 70 = overbought, "
        "below 30 = oversold, 30–70 = neutral."
    ),
    "MACD": (
        "Moving Average Convergence Divergence. Measures momentum. "
        "Positive = bullish pressure, Negative = bearish pressure."
    ),
    "BB Position": (
        "Position of the current price within the Bollinger Bands. "
        "Near top = overbought zone, Near bottom = oversold zone."
    ),
}


def _metric_extras(label: str, delta: str | None) -> dict[str, Any]:
    """Extra ``st.metric`` kwargs. Only ``delta_color`` is supported (no ``delta_arrow`` in Streamlit 1.50)."""
    if not delta or not str(delta).strip():
        return {}
    d = str(delta).strip()
    if label in ("RSI (14)", "BB Position"):
        return {"delta_color": "off"}
    if label == "MACD":
        # Valid values: "normal" | "inverse" | "off" — not "green"/"red"
        if "bearish" in d.lower() or d.startswith("▼"):
            return {"delta_color": "inverse"}
        return {"delta_color": "normal"}
    return {}


def render_metric_with_tooltip(
    col: Any,
    label: str,
    value: str,
    delta: str | None = None,
    *,
    tooltip_body: str | None = None,
) -> None:
    """
    Render ``st.metric`` in ``col`` with a help tooltip (hover + click/tap).

    Pass ``tooltip_body`` to override copy; otherwise ``label`` must be in
    ``METRIC_TOOLTIP_BODIES``.
    """
    body = tooltip_body if tooltip_body is not None else METRIC_TOOLTIP_BODIES[label]
    extras = _metric_extras(label, delta)
    with col:
        if delta is not None and str(delta).strip():
            st.metric(
                label,
                value,
                str(delta).strip(),
                help=body,
                **extras,
            )
        else:
            st.metric(label, value, help=body, **extras)
