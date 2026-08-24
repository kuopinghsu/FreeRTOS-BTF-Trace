"""Numeric presentation helpers (Step 3).

Lockstep with ``web/src/utils/numericFormat.js``.
"""
from __future__ import annotations

from typing import Optional

PERCENTILE_DECIMALS = 3
NUMERIC_CELL_CLASS = "num-cell"


def _format_time_trim(value: float, scale: str) -> str:
    """Minimal parity with web formatTimeTrim — defers to timeline util when available."""
    try:
        from .timeline_util import format_time_trim  # noqa: WPS433

        return format_time_trim(value, scale)
    except Exception:
        v = float(value)
        return f"{v:g} {scale}"


def format_percentile(value: Optional[float], scale: str, kind: str = "") -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if not v and v != 0:
        return "—"
    return _format_time_trim(v, scale)


def format_ratio_pct(ratio: Optional[float]) -> str:
    if ratio is None:
        return "—"
    try:
        v = float(ratio)
    except (TypeError, ValueError):
        return "—"
    return f"{v * 100:.1f}%"


def format_cpu_pct(pct: Optional[float]) -> str:
    if pct is None:
        return "—"
    try:
        v = float(pct)
    except (TypeError, ValueError):
        return "—"
    if v >= 99.95:
        return "100%"
    if 0 < v < 0.05:
        return "<0.1%"
    return f"{v:.1f}%"


def numeric_cell_html(text: str, title: str = "") -> str:
    t = f' title="{title.replace(chr(34), "&quot;")}"' if title else ""
    return f'<td class="{NUMERIC_CELL_CLASS}"{t}>{text}</td>'


def format_signed_delta(delta: Optional[float], scale: str) -> str:
    if delta is None:
        return "—"
    try:
        v = float(delta)
    except (TypeError, ValueError):
        return "—"
    if v == 0:
        return "—"
    sign = "+" if v > 0 else "−"
    return f"{sign}{_format_time_trim(abs(v), scale)}"
