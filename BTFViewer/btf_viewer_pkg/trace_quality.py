"""Trace quality / integrity warnings from BTF metadata (parity with web traceQuality.js)."""
from __future__ import annotations

from typing import Any, List, Optional, TYPE_CHECKING

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
