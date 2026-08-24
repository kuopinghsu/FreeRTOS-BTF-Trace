"""Loading-state UX (Step 3).

Lockstep with ``web/src/utils/loadingState.js``.
"""
from __future__ import annotations

import re
from typing import Dict, Tuple

LOADING_STAGES: Dict[str, str] = {
    "reading": "Reading trace…",
    "parsing": "Parsing events…",
    "building": "Building Timeline…",
    "computing": "Computing Statistics…",
    "opening": "Opening trace…",
    "restoring": "Restoring session…",
    "demo": "Loading demo trace…",
}

_INTERNAL_STAGE_RULES: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"reading file", re.I), "reading"),
    (re.compile(r"restoring session", re.I), "restoring"),
    (re.compile(r"demo trace", re.I), "demo"),
    (re.compile(r"packing trace|opening trace", re.I), "opening"),
    (re.compile(r"preparing statistics|computing statistics", re.I), "computing"),
    (
        re.compile(
            r"building scene|building legend|building task lod|building core lod|"
            r"per-task core lod|finalising segment|building sti",
            re.I,
        ),
        "building",
    ),
    (
        re.compile(
            r"reconstruct|lookup|index|sort|pair|tag channel|finalis|cul|analys|"
            r"sti channel|tick health",
            re.I,
        ),
        "parsing",
    ),
)


def resolve_loading_stage(internal_msg: str = "") -> str:
    msg = str(internal_msg or "").strip()
    if not msg:
        return "reading"
    for pattern, stage in _INTERNAL_STAGE_RULES:
        if pattern.search(msg):
            return stage
    return "parsing"


def format_loading_message(internal_msg: str = "") -> str:
    stage = resolve_loading_stage(internal_msg)
    return LOADING_STAGES.get(stage, LOADING_STAGES["parsing"])


def format_loading_pct(pct: float) -> str:
    try:
        n = float(pct)
    except (TypeError, ValueError):
        return ""
    if not n or n <= 0:
        return ""
    if n >= 100:
        return "100"
    rounded = round(n / 5) * 5
    return str(max(5, min(99, int(rounded))))


def is_loading_cancellable(phase: str = "parse") -> bool:
    return phase in ("parse", "read")


def normalize_loading_progress(
    pct: float, internal_msg: str = "", phase: str = "parse"
) -> dict:
    return {
        "pct": float(pct or 0),
        "msg": format_loading_message(internal_msg),
        "pct_label": format_loading_pct(pct),
        "cancellable": is_loading_cancellable(phase),
    }
