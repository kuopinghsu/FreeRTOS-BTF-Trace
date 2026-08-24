"""Disabled-state prerequisite checks (Step 3).

Lockstep with ``web/src/utils/disabledReason.js``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

DISABLED_REASONS: Dict[str, str] = {
    "no_trace": "Open a trace first",
    "two_traces": "Open at least two traces",
    "cursors2": "Place at least two cursors (C1–Cn)",
    "ai_config": "Configure an AI provider in Settings",
    "smp_only": "Requires a multi-core trace",
    "no_evidence": "No Timeline Evidence for this finding",
    "unavailable": "Unavailable",
}


def check_prerequisite(
    requires: str,
    ctx: Dict[str, Any],
    fallback: str = "",
) -> Tuple[bool, str]:
    req = str(requires or "none")
    if not req or req == "none":
        return True, ""
    if req == "trace":
        if ctx.get("has_trace"):
            return True, ""
        return False, fallback or DISABLED_REASONS["no_trace"]
    if req == "two_traces":
        if int(ctx.get("trace_count") or 0) >= 2:
            return True, ""
        return False, fallback or DISABLED_REASONS["two_traces"]
    if req == "cursors2":
        if int(ctx.get("cursor_count") or 0) >= 2:
            return True, ""
        return False, fallback or DISABLED_REASONS["cursors2"]
    if req == "ai_config":
        if ctx.get("ai_configured"):
            return True, ""
        return False, fallback or DISABLED_REASONS["ai_config"]
    if req == "smp":
        if ctx.get("is_multi_core"):
            return True, ""
        return False, fallback or DISABLED_REASONS["smp_only"]
    return True, ""


def build_prerequisite_context(
    *,
    trace: Any = None,
    compare_tab_count: int = 0,
    cursor_count: int = 0,
    ai_configured: bool = True,
) -> Dict[str, Any]:
    cores = 0
    if trace is not None:
        meta = getattr(trace, "meta", None) or {}
        if isinstance(meta, dict):
            cores = len(meta.get("cores") or [])
        elif hasattr(trace, "cores"):
            cores = len(getattr(trace, "cores") or [])
    return {
        "has_trace": trace is not None,
        "trace_count": compare_tab_count,
        "cursor_count": cursor_count,
        "is_multi_core": cores > 1,
        "ai_configured": ai_configured,
    }
