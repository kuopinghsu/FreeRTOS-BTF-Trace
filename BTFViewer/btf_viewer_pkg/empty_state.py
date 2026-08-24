"""Empty-state messages (Step 3).

Lockstep with ``web/src/utils/emptyState.js``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

EMPTY_STATES: Dict[str, Dict[str, Any]] = {
    "no_trace": {
        "message": "Open a BTF trace to begin.",
        "action": "open",
    },
    "no_stats": {
        "message": "Open a trace file to view statistics.",
        "action": "open",
    },
    "no_cursors": {
        "message": "Place two cursors to measure a range.",
        "action": None,
    },
    "no_compare": {
        "message": "Open at least two traces to compare.",
        "action": "open",
    },
    "no_find_query": {
        "message": "Enter a task name, annotation, or migration to search.",
        "action": None,
    },
    "no_find_hits": {
        "message": "No matches in the current Scope.",
        "action": None,
    },
    "no_marks": {
        "message": "No bookmarks or annotations yet.",
        "hint": "Double-click the Timeline or press B / A to add one.",
        "action": None,
    },
    "no_ai": {
        "message": "Ask about evidence already found in Statistics or the Timeline.",
        "action": None,
    },
    "no_ai_config": {
        "message": "Configure an AI provider in Settings to enable investigation.",
        "action": "settings",
    },
    "no_migration": {
        "message": "No migrations in the current Scope.",
        "hint": "Switch to Core View or widen Scope with cursors.",
        "action": None,
    },
    "no_heatmap": {
        "message": "No on-CPU slices in the current Scope.",
        "action": None,
    },
    "no_timeline": {
        "message": "Open a .btf file to begin.",
        "action": "open",
    },
}


def empty_state_message(key: str) -> str:
    spec = EMPTY_STATES.get(key) or {}
    msg = str(spec.get("message") or "")
    hint = spec.get("hint")
    if hint:
        return f"{msg} {hint}"
    return msg


def empty_state_action(key: str) -> Optional[str]:
    spec = EMPTY_STATES.get(key) or {}
    action = spec.get("action")
    return str(action) if action else None
