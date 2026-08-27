"""Trace quality / integrity warnings from BTF metadata (parity with web traceQuality.js)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .parser import BtfTrace

_QUALITY_KEYS = ("ringOverflow", "taskTableOverflow", "truncated")

_MESSAGES = {
    "ringOverflow": "Trace ring buffer overflow — oldest events may be missing.",
    "taskTableOverflow": "Task table overflow — tracing was disabled for new tasks.",
    "truncated": "Trace was truncated before normal stop.",
}

def _truthy_meta(value: Any) -> bool:
    if value is True or value == 1:
        return True
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    return False

def collect_trace_quality_warnings(trace: Optional["BtfTrace"]) -> List[str]:
    """Human-readable warning lines from parsed BTF meta."""
    if trace is None:
        return []
    meta = trace.meta or {}
    out: List[str] = []

    for key in ("_version_warning", "_versionWarning"):
        msg = meta.get(key)
        if msg:
            out.append(str(msg).strip())

    for key in ("_trace_quality_warning", "_traceQualityWarning"):
        msg = meta.get(key)
        if msg:
            out.append(str(msg).strip())

    flags = meta.get("traceQuality") or meta.get("trace_quality")
    if isinstance(flags, dict):
        if flags.get("ringOverflow") or flags.get("ring_overflow"):
            out.append(_MESSAGES["ringOverflow"])
        if flags.get("taskTableOverflow") or flags.get("task_table_overflow"):
            out.append(_MESSAGES["taskTableOverflow"])
        if flags.get("truncated"):
            out.append(_MESSAGES["truncated"])
    elif isinstance(flags, str) and flags.strip():
        out.append(flags.strip())

    for key in _QUALITY_KEYS:
        if _truthy_meta(meta.get(key)):
            out.append(_MESSAGES[key])

    comment = meta.get("comment")
    if comment:
        c = str(comment).lower()
        if "overflow" in c or "truncat" in c:
            line = str(comment).strip()
            if line not in out:
                out.append(line)

    # Preserve order, drop duplicates.
    seen: set[str] = set()
    unique: List[str] = []
    for line in out:
        if line and line not in seen:
            seen.add(line)
            unique.append(line)
    return unique

def trace_quality_summary(trace: Optional["BtfTrace"]) -> Optional[str]:
    warnings = collect_trace_quality_warnings(trace)
    if not warnings:
        return None
    return " · ".join(warnings)


_QUALITY_GROUPS = {
    "incomplete_capture": (
        "ringOverflow",
        "taskTableOverflow",
        "truncated",
        "overflow",
        "truncat",
    ),
    "missing_event_type": ("sti", "instrument", "missing event"),
    "invalid_pairing": ("pair", "unmatched", "interval"),
    "timestamp_order": ("order", "timestamp", "version"),
    "unsupported_measurement": ("unsupported", "not instrumented"),
}

_AFFECTED_BY_GROUP = {
    "incomplete_capture": [
        "Timeline Anomalies", "Worst Events", "Response Time", "AI conclusions",
    ],
    "missing_event_type": [
        "Blocking Time", "Mutex Blocking", "Waiter × Owner", "Dispatch latency",
    ],
    "invalid_pairing": ["Period / Jitter", "Recurring Patterns", "Intervals"],
    "timestamp_order": ["All time-ordered statistics", "Critical Path"],
    "unsupported_measurement": [
        "Response Time", "Task Health", "Priority Inheritance",
    ],
}


def _classify_warning(line: str) -> str:
    low = str(line or "").lower()
    for group, needles in _QUALITY_GROUPS.items():
        if any(n in low for n in needles):
            return group
    return "incomplete_capture"


def trace_quality_report(trace: Optional["BtfTrace"]) -> Dict[str, Any]:
    """Grouped trace-quality details for Review details."""
    warnings = collect_trace_quality_warnings(trace)
    if not warnings:
        return {"ok": True, "summary": "", "groups": [], "actions": []}
    grouped: Dict[str, List[str]] = {}
    for line in warnings:
        grouped.setdefault(_classify_warning(line), []).append(line)
    groups = []
    for gid, lines in grouped.items():
        groups.append({
            "id": gid,
            "title": gid.replace("_", " ").title(),
            "lines": lines,
            "affected": list(_AFFECTED_BY_GROUP.get(gid, [])),
        })
    return {
        "ok": False,
        "summary": trace_quality_summary(trace) or "",
        "groups": groups,
        "actions": [
            {"id": "continue", "label": "Continue with limitations"},
            {"id": "guidance", "label": "Open capture guidance"},
        ],
    }
