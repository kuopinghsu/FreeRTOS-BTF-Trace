"""Universal Evidence Navigation (Step 2).

One shared contract for jumping from analytical results (Findings, Statistics,
AI, Migration, Compare) to concrete Timeline Evidence.

Rules (lockstep with ``web/src/utils/evidenceNav.js``):

* Center the Timeline on the Evidence timestamp.
* Place or reuse a single Evidence cursor at that time (does **not** redefine
  Scope / C1–Cn analysis window).
* Highlight the related Task when known.
* Never silently change Scope or Filters.
* When several representative events exist, prefer the longest / worst in the
  finding's evidence set (same ranking as ``best_finding_scope``).
* When no exact Evidence can be located, return ``ok=False`` with a reason —
  callers show a status message instead of inventing a jump.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from .ux_explore import best_finding_scope  # noqa: F401 — re-exported for callers

# Visible affordance glyph used next to actionable Evidence timestamps.
EVIDENCE_GLYPH = "\u2197"  # ↗

# Tooltip for Evidence-affordance cells (Statistics / Findings / Compare).
EVIDENCE_TOOLTIP = "Jump to Evidence (does not change Scope or Filters)"

_TIME_TOKEN_RE = re.compile(
    r"(?:jump:)?(\d+(?:\.\d+)?)\s*(ns|us|µs|μs|ms|s)?",
    re.IGNORECASE,
)

_UNIT_NS = {
    "": 1.0,
    "ns": 1.0,
    "us": 1_000.0,
    "µs": 1_000.0,
    "μs": 1_000.0,
    "ms": 1_000_000.0,
    "s": 1_000_000_000.0,
}


def parse_evidence_timestamps(*texts: str) -> List[int]:
    """Extract candidate timestamps (ns) from free-form Evidence strings."""
    out: List[int] = []
    seen = set()
    for text in texts:
        blob = str(text or "")
        for m in _TIME_TOKEN_RE.finditer(blob):
            try:
                value = float(m.group(1))
            except (TypeError, ValueError):
                continue
            unit = (m.group(2) or "").lower()
            # Bare integers in evidence_text are often counts, not times —
            # only accept unitless values when tagged with jump: or clearly large.
            raw = m.group(0)
            if not unit and "jump:" not in raw.lower():
                if value < 1_000_000:  # smaller than 1 ms as bare ns is ambiguous
                    continue
                scale = 1.0
            else:
                scale = _UNIT_NS.get(unit, 1.0)
            ns = int(value * scale)
            if ns in seen or ns < 0:
                continue
            seen.add(ns)
            out.append(ns)
    return out


def resolve_finding_evidence(
    finding: Optional[dict],
    events: Sequence[dict],
    time_min: float,
    time_max: float,
) -> Dict[str, Any]:
    """Resolve Timeline Evidence for an Analysis Finding without changing Scope.

    Returns a dict:
      ok, ns, task, mk, note, multi, reason
    """
    if not isinstance(finding, dict):
        return {
            "ok": False,
            "ns": None,
            "task": "",
            "mk": "",
            "note": "",
            "multi": False,
            "reason": "No finding selected",
        }

    times: List[float] = []
    for ev in finding.get("evidence") or []:
        if not isinstance(ev, dict):
            continue
        for key in ("time", "start", "stop", "ns"):
            try:
                if ev.get(key) is not None:
                    times.append(float(ev[key]))
            except (TypeError, ValueError):
                continue
    times.extend(
        float(t)
        for t in parse_evidence_timestamps(
            str(finding.get("evidence_text") or ""),
            str(finding.get("title") or ""),
            str(finding.get("text") or ""),
        )
    )

    scope = best_finding_scope(finding, events, time_min, time_max)
    task = str((scope or {}).get("task") or finding.get("task") or "").strip()
    mk = str((scope or {}).get("mk") or "").strip()
    multi = len(set(int(t) for t in times)) > 1

    ns: Optional[int] = None
    note = ""
    if times:
        # Prefer the latest evidence sample when several exist (tail / worst).
        ns = int(max(times))
        note = "Evidence timestamp from finding"
        if multi:
            note = "Representative (latest) Evidence among multiple samples"
    elif scope is not None:
        # Fall back to mid-point of recommended episode — still no Scope change.
        lo = int(scope.get("lo") or 0)
        hi = int(scope.get("hi") or lo)
        ns = (lo + hi) // 2
        note = str(scope.get("reason") or "Representative moment in finding episode")
        task = task or str(scope.get("task") or "")
        mk = mk or str(scope.get("mk") or "")

    if ns is None:
        return {
            "ok": False,
            "ns": None,
            "task": task,
            "mk": mk,
            "note": "",
            "multi": False,
            "reason": "No locatable Timeline Evidence for this finding",
        }

    tmin = int(time_min)
    tmax = int(time_max)
    if tmax > tmin:
        ns = max(tmin, min(tmax, ns))

    return {
        "ok": True,
        "ns": int(ns),
        "task": task,
        "mk": mk,
        "note": note,
        "multi": multi,
        "reason": "",
    }


def resolve_timestamp_evidence(
    ns: Any,
    *,
    task: str = "",
    mk: str = "",
    note: str = "",
    time_min: float = 0,
    time_max: float = 0,
) -> Dict[str, Any]:
    """Wrap a concrete timestamp (Statistics cell / AI jump / Compare delta)."""
    try:
        value = int(ns)
    except (TypeError, ValueError):
        return {
            "ok": False,
            "ns": None,
            "task": task or "",
            "mk": mk or "",
            "note": "",
            "multi": False,
            "reason": "Evidence timestamp is missing or invalid",
        }
    tmin = int(time_min or 0)
    tmax = int(time_max or 0)
    if tmax > tmin:
        value = max(tmin, min(tmax, value))
    return {
        "ok": True,
        "ns": value,
        "task": str(task or ""),
        "mk": str(mk or ""),
        "note": note or "Evidence timestamp",
        "multi": False,
        "reason": "",
    }
