"""Cursor scoping workflow helpers.

Lockstep with ``web/src/utils/cursorScope.js``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


def should_offer_use_as_scope(
    cursor_times: Sequence[int],
    *,
    limit_to_cursors: bool = False,
) -> bool:
    return len([t for t in (cursor_times or []) if t is not None]) >= 2 and not limit_to_cursors


def format_use_as_scope_prompt(cursor_times: Sequence[int]) -> str:
    placed = sorted(t for t in (cursor_times or []) if t is not None)
    if len(placed) < 2:
        return ""
    return f"Use C1–C{len(placed)} as analysis Scope"


def multi_cursor_span_warning(cursor_times: Sequence[int]) -> Optional[str]:
    placed = sorted(t for t in (cursor_times or []) if t is not None)
    if len(placed) <= 2:
        return None
    return (
        f"{len(placed)} cursors define C1–C{len(placed)} as earliest-to-latest span; "
        "verify this includes the intended incident only."
    )


def cursor_range_actions() -> List[Dict[str, str]]:
    return [
        {"id": "fit", "label": "Fit range"},
        {"id": "analyze", "label": "Analyze range"},
        {"id": "save_btf", "label": "Save range as BTF"},
        {"id": "clear", "label": "Clear range"},
    ]
