"""Pure find/search logic (no Qt widgets)."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from ..config import _MAX_FIND_REGEX_LEN
from ..parser import BtfTrace, TraceAnnotation, _task_display_name

_FIND_MODES = frozenset({
    "contains", "exact", "regex", "migrations",
    "sti", "intervals", "lifecycle", "pointers",
})

# (label, mode_key, help text) — keep order in sync with web findAnalysis.js
# and config._PORTABLE_FIND_MODES.
FIND_MODE_CHOICES: Tuple[Tuple[str, str, str], ...] = (
    (
        "Contains",
        "contains",
        "Substring match on task names (merge key / display name) and "
        "annotation notes.",
    ),
    (
        "Exact",
        "exact",
        "Whole-string match on a task merge key, raw name, or display name.",
    ),
    (
        "Regex",
        "regex",
        "Case-insensitive regular expression on task names and annotation notes.",
    ),
    (
        "Migrations",
        "migrations",
        "Core-migration boundaries. Match a task name or a core "
        "(from / to), e.g. Core_0 or CS[22].",
    ),
    (
        "STI",
        "sti",
        "Software-trace items: channel, event verb, note, and core "
        "(tags, TICK, mutex notes, …).",
    ),
    (
        "Intervals",
        "intervals",
        "Paired interval_start / interval_stop spans and interval STI notes "
        "(id, task, times).",
    ),
    (
        "Lifecycle",
        "lifecycle",
        "Task create / delete / suspend / resume STI notes on the task channel.",
    ),
    (
        "Pointers",
        "pointers",
        "Mutex, semaphore, and queue object pointers (0x…) and sync-object notes.",
    ),
)

_FIND_MODE_ALIASES = {
    "sti events": "sti",
    "sti event": "sti",
    "tags": "sti",
    "tag": "sti",
}

_TASK_LIFE_RE = re.compile(r"^(create|delete|suspend|resume)\b", re.IGNORECASE)
_SYNC_NOTE_RE = re.compile(
    r"^(create|take|give|delete|send|recv)(?:\s+(0x[0-9a-f]+))?$", re.IGNORECASE)


def normalize_find_mode(mode: str) -> str:
    """Map a combo label or key onto one of ``_FIND_MODES``."""
    key = str(mode or "").strip().lower()
    key = _FIND_MODE_ALIASES.get(key, key)
    return key if key in _FIND_MODES else "contains"


def find_mode_help(mode: str) -> str:
    """One-line help for the Find mode combo selection."""
    want = normalize_find_mode(mode)
    for _label, key, tip in FIND_MODE_CHOICES:
        if key == want:
            return tip
    return FIND_MODE_CHOICES[0][2]


def recompute_find_hits(
    trace: Optional[BtfTrace],
    query: str,
    mode: str,
    annotations: List[TraceAnnotation],
) -> Tuple[List[int], str]:
    """Return (sorted unique hit timestamps in ns, status message)."""
    if trace is None:
        return [], "0 matches"
    q = query.strip()
    if not q:
        return [], "0 matches"

    mode_key = normalize_find_mode(mode)

    if mode_key == "migrations":
        return _find_migrations(trace, q)

    regex_obj = None
    if mode_key == "regex":
        if len(q) > _MAX_FIND_REGEX_LEN:
            return [], "Regex too long"
        try:
            regex_obj = re.compile(q, re.IGNORECASE)
        except re.error:
            return [], "Regex error"

    if mode_key == "sti":
        hits = _find_sti_hits(trace, q, regex_obj)
        unique = sorted(set(hits))
        return unique, f"{len(unique)} matches"
    if mode_key == "intervals":
        hits = _find_interval_hits(trace, q, regex_obj)
        unique = sorted(set(hits))
        return unique, f"{len(unique)} matches"
    if mode_key == "lifecycle":
        hits = _find_lifecycle_hits(trace, q, regex_obj)
        unique = sorted(set(hits))
        return unique, f"{len(unique)} matches"
    if mode_key == "pointers":
        hits = _find_pointer_hits(trace, q, regex_obj)
        unique = sorted(set(hits))
        return unique, f"{len(unique)} matches"

    hits: List[int] = []
    for mk, segs in trace.seg_map_by_merge_key.items():
        raw = trace.task_repr.get(mk, mk)
        disp = _task_display_name(raw)
        if mode_key == "exact":
            matched = (q.lower() == mk.lower()
                       or q.lower() == raw.lower()
                       or q.lower() == disp.lower())
        else:
            hay = f"{mk} {raw} {disp}"
            matched = _haystack_matches(q, mode_key, hay, regex_obj)
        if matched:
            hits.extend(s.start for s in segs)

    for ann in annotations:
        if isinstance(ann, dict):
            note = str(ann.get("note") or ann.get("label") or "")
            try:
                ns = int(ann.get("ns", ann.get("time")))
            except (TypeError, ValueError):
                continue
        else:
            note = str(getattr(ann, "note", None) or getattr(ann, "label", None) or "")
            try:
                ns = int(getattr(ann, "ns", None))
            except (TypeError, ValueError):
                continue
        if _haystack_matches(q, mode_key, note, regex_obj):
            hits.append(ns)

    unique = sorted(set(hits))
    label = f"{len(unique)} matches"
    return unique, label

def _find_migrations(trace: BtfTrace, query: str) -> Tuple[List[int], str]:
    q_lower = query.lower()
    hits: List[int] = []
    for m in getattr(trace, "migrations", ()):
        raw = trace.task_repr.get(m.merge_key, m.merge_key)
        disp = _task_display_name(raw)
        hay = f"{m.merge_key} {raw} {disp} {m.from_core} {m.to_core}"
        if (not q_lower or q_lower in hay.lower()
                or q_lower in m.from_core.lower()
                or q_lower in m.to_core.lower()):
            hits.append(m.ns)
    unique = sorted(set(hits))
    return unique, f"{len(unique)} migration matches"

def _find_sti_hits(trace: BtfTrace, query: str, regex_obj: Optional[re.Pattern]) -> List[int]:
    hits: List[int] = []
    q_lower = query.lower()
    for ev in getattr(trace, "sti_events", ()):
        hay = f"{ev.target} {ev.event or ''} {ev.note or ''} {ev.core or ''}"
        if _haystack_matches(query, "contains", hay, regex_obj):
            hits.append(ev.time)
        elif not regex_obj and q_lower == hay.lower():
            hits.append(ev.time)
    return hits

def _find_interval_hits(trace: BtfTrace, query: str, regex_obj: Optional[re.Pattern]) -> List[int]:
    hits: List[int] = []
    for inst in getattr(trace, "interval_instances", ()):
        hay = f"{inst.id} {inst.task_id or ''} {inst.start_ns} {inst.stop_ns}"
        if _haystack_matches(query, "contains", hay, regex_obj):
            hits.extend([inst.start_ns, inst.stop_ns])
    for ev in getattr(trace, "sti_events", ()):
        if not str(ev.target).startswith("interval_"):
            continue
        hay = f"{ev.target} {ev.note or ''}"
        if _haystack_matches(query, "contains", hay, regex_obj):
            hits.append(ev.time)
    return hits

def _parse_task_lifecycle_note(note: str) -> Optional[Tuple[str, str]]:
    raw = (note or "").strip()
    if not raw:
        return None
    m = _TASK_LIFE_RE.match(raw)
    if not m:
        return None
    action = m.group(1).lower()
    label = raw[m.end():].strip() or raw
    return action, label

def _find_lifecycle_hits(trace: BtfTrace, query: str, regex_obj: Optional[re.Pattern]) -> List[int]:
    hits: List[int] = []
    for ev in getattr(trace, "sti_events", ()):
        if ev.target != "task":
            continue
        parsed = _parse_task_lifecycle_note(ev.note)
        if not parsed:
            continue
        action, label = parsed
        hay = f"{action} {label} {ev.note or ''}"
        if _haystack_matches(query, "contains", hay, regex_obj):
            hits.append(ev.time)
    return hits

def _parse_sync_note(note: str) -> Optional[Tuple[str, str]]:
    m = _SYNC_NOTE_RE.match((note or "").strip())
    if not m:
        return None
    ptr = (m.group(2) or "0").lower()
    return m.group(1).lower(), ptr

def _find_pointer_hits(trace: BtfTrace, query: str, regex_obj: Optional[re.Pattern]) -> List[int]:
    hits: List[int] = []
    q = query.strip()
    for ev in getattr(trace, "sti_events", ()):
        parsed = _parse_sync_note(ev.note)
        ptr = parsed[1] if parsed else ""
        hay = f"{ev.target} {ev.note or ''} {ptr}"
        matched = False
        if regex_obj is not None:
            matched = bool(regex_obj.search(hay))
        elif q.lower() == ptr.lower() or q.lower() == (ev.note or "").lower():
            matched = True
        elif q.lower() in hay.lower():
            matched = True
        if matched:
            hits.append(ev.time)
    return hits

def _haystack_matches(
    query: str,
    mode: str,
    haystack: str,
    regex_obj: Optional[re.Pattern],
) -> bool:
    if mode == "contains":
        return query.lower() in haystack.lower()
    if mode == "exact":
        return query.lower() == haystack.lower()
    if regex_obj is not None:
        return bool(regex_obj.search(haystack))
    return False

# Bundle-safe alias: trace_tab_vm preamble imports are stripped in the monolith.
FIND_RECOMPUTE = recompute_find_hits
