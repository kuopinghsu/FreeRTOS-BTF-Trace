"""Pure find/search logic (no Qt widgets)."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from ..config import _MAX_FIND_REGEX_LEN
from ..parser import BtfTrace, TraceAnnotation, _task_display_name


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

    mode_key = mode.strip().lower()
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
        if _haystack_matches(q, mode_key, ann.note, regex_obj):
            hits.append(ann.ns)

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
