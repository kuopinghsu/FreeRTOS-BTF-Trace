"""Evidence round-trip navigation (UX-107).

Lockstep with ``web/src/utils/evidenceHistory.js``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def empty_evidence_history() -> Dict[str, Any]:
    return {"entries": [], "index": -1}


def push_evidence_entry(
    history: Optional[Dict[str, Any]],
    entry: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(history or empty_evidence_history())
    entries = list(out.get("entries") or [])
    idx = int(out.get("index") or -1)
    if idx >= 0 and idx < len(entries) - 1:
        entries = entries[: idx + 1]
    entries.append(dict(entry))
    out["entries"] = entries
    out["index"] = len(entries) - 1
    return out


def evidence_nav_state(history: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(history or empty_evidence_history())
    entries = list(out.get("entries") or [])
    idx = int(out.get("index") or -1)
    return {
        "can_back": idx > 0,
        "can_forward": 0 <= idx < len(entries) - 1,
        "current": entries[idx] if 0 <= idx < len(entries) else None,
        "count": len(entries),
    }


def step_evidence_history(
    history: Optional[Dict[str, Any]],
    direction: int,
) -> Dict[str, Any]:
    out = dict(history or empty_evidence_history())
    entries = list(out.get("entries") or [])
    idx = int(out.get("index") or -1)
    step = -1 if int(direction) < 0 else 1
    nxt = max(-1, min(len(entries) - 1, idx + step))
    out["index"] = nxt
    out["entries"] = entries
    return out


def format_evidence_inspector(entry: Optional[Dict[str, Any]]) -> str:
    if not isinstance(entry, dict):
        return ""
    parts = []
    for key, label in (
        ("task", "Task"),
        ("core", "Core"),
        ("event_type", "Event"),
        ("start", "Start"),
        ("end", "End"),
        ("duration", "Duration"),
        ("source_metric", "Source"),
        ("time", "Time"),
    ):
        val = entry.get(key)
        if val is not None and str(val).strip():
            parts.append(f"{label}: {val}")
    return " · ".join(parts)


SHOW_ON_TIMELINE_LABEL = "Show on timeline"
