"""Deterministic timeline explore helpers (anomalies, worst events, scope).

Host harvest walks BTF slices; ranking and scope stay shared with
``web/src/utils/uxExplore.js``.
"""
from __future__ import annotations

import math
import re
from bisect import bisect_right
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from .parser import (
    _is_idle_task_name,
    _parse_task_name,
    _seg_fully_in_range,
    _task_display_name,
)

KIND_SECTION = {
    "exec": "exec",
    "block": "block",
    "inter": "inter",
    "migration": "migrations",
    "period": "period",
    "task_core": "task_core",
    "wait_owner": "wait_owner",
    "task_health": "task_health",
    "response": "response",
    "preempt": "preempt_matrix",
    "isr": "anomalies",
    "idle": "cores",
    "cpu": "cores",
    "deadline": "deadline",
    "pattern": "patterns",
    "crit_path": "crit_path",
    "jitter": "jitter",
    "mutex_block": "mutex_block",
    "core_time": "core_time",
    "distrib": "distrib",
}

MUTEX_HANDOFF_SLACK_NS = 1_000_000
PERIOD_MISS_RATIO = 1.5
PERIOD_EXTRA_RATIO = 0.5
PERIOD_BURST_RATIO = 0.25
HEALTH_MARK = {"ok": "✓", "warn": "⚠", "fail": "❌"}
HEALTH_BAND_SECTION = {
    "execution": "exec",
    "blocking": "block",
    "period": "period",
    "migration": "migrations",
    "deadline": "deadline",
    "cpu": "tasks",
}

KIND_LABEL = {
    "exec": "execution",
    "block": "blocking",
    "inter": "inter-arrival",
    "migration": "migration",
    "response": "response",
    "preempt": "preemption",
    "isr": "ISR",
    "idle": "idle",
    "cpu": "CPU",
    "deadline": "deadline",
    "crit_path": "critical path",
    "pattern": "pattern",
    "jitter": "jitter",
    "mutex_block": "mutex blocking",
}

_ISR_RE = re.compile(r"(isr|irq|interrupt)", re.IGNORECASE)
CORE_TIME_BINS = 16
BURST_WINDOW_NS = 1_000_000

_JUMP_RE = re.compile(r"jump:([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_TASK_RE = re.compile(r"\b([A-Za-z_][\w.-]*\[\d+\])")
_DELTA_RE = re.compile(
    r"^([+\-−])?\s*([\d.]+)\s*(ns|µs|us|μs|ms|s|/s|%)?$",
    re.IGNORECASE,
)
_UNIT_NS = {
    "ns": 1.0,
    "us": 1000.0,
    "µs": 1000.0,
    "μs": 1000.0,
    "ms": 1_000_000.0,
    "s": 1_000_000_000.0,
}
_SUMMARY_STRIP_LABELS = (
    "Span",
    "Span (cursor range)",
    "Context switches",
    "Migrations (total)",
    "Missed ticks (est.)",
    "Response P99 (worst task)",
    "Mutex blocking (total)",
    "Deadline misses",
)


def percentile_index(n: int, p: float) -> int:
    """Index of the p-quantile in a sorted n-sample list (stats-table formula)."""
    if n <= 0:
        return 0
    pp = max(0.0, min(1.0, float(p)))
    return min(n - 1, max(0, math.ceil(n * pp) - 1))


def find_event_at_percentile(events: Sequence[dict], p: float) -> Optional[dict]:
    """Return the event at percentile *p* when sorted by duration."""
    rows = [e for e in (events or []) if isinstance(e, dict)]
    if not rows:
        return None
    ordered = sorted(rows, key=lambda e: float(e.get("duration") or 0))
    return ordered[percentile_index(len(ordered), p)]


def collect_worst_events(events: Sequence[dict], limit: int = 12) -> List[dict]:
    """Top-N longest exec / block / inter / heuristic-response episodes (deduped)."""
    lim = max(1, min(40, int(limit or 12)))
    seen: set = set()
    ranked: List[dict] = []
    rows = [
        e for e in (events or [])
        if isinstance(e, dict) and e.get("kind") in ("exec", "block", "inter", "response")
    ]
    if not any(e.get("kind") == "response" for e in rows):
        rows.extend(analyze_response_times(events).get("events") or [])
    rows.sort(key=lambda e: (-float(e.get("duration") or 0), float(e.get("start") or 0)))
    for ev in rows:
        key = (ev.get("kind"), ev.get("start"), ev.get("task") or ev.get("mk"))
        if key in seen:
            continue
        seen.add(key)
        ranked.append(dict(ev))
        if len(ranked) >= lim:
            break
    return ranked


def detect_timeline_anomalies(
    events: Sequence[dict],
    limit: int = 12,
    mutex_waits: Optional[Sequence[dict]] = None,
    deadlines: Optional[dict] = None,
) -> List[dict]:
    """Flag long tails (mean+3σ or ≥ p99) and migration bursts."""
    lim = max(1, min(40, int(limit or 12)))
    rows = [e for e in (events or []) if isinstance(e, dict)]
    flagged: List[dict] = []
    seen: set = set()

    def _add(ev: dict, reason: str) -> None:
        key = (ev.get("kind"), ev.get("start"), ev.get("task") or ev.get("mk"))
        if key in seen:
            return
        seen.add(key)
        item = dict(ev)
        item["reason"] = reason
        item["section"] = KIND_SECTION.get(str(ev.get("kind") or ""), "exec")
        flagged.append(item)

    by_group: Dict[Tuple[str, str], List[dict]] = {}
    for ev in rows:
        kind = str(ev.get("kind") or "")
        if kind not in ("exec", "block", "inter"):
            continue
        task = str(ev.get("task") or ev.get("mk") or "")
        by_group.setdefault((kind, task), []).append(ev)

    for (kind, task), group in by_group.items():
        if len(group) < 4:
            continue
        vals = sorted(float(e.get("duration") or 0) for e in group)
        n = len(vals)
        mean = sum(vals) / n
        var = sum((v - mean) ** 2 for v in vals) / n
        sigma = math.sqrt(var)
        p99 = vals[percentile_index(n, 0.99)]
        thresh = mean + 3.0 * sigma if sigma > 0 else p99
        label = KIND_LABEL.get(kind, kind)
        for ev in group:
            dur = float(ev.get("duration") or 0)
            if dur <= 0:
                continue
            if sigma > 0 and dur > thresh:
                _add(ev, f"{label} > mean+3σ for {task or 'task'}")
            elif dur >= p99 and dur >= mean:
                _add(ev, f"{label} ≥ p99 for {task or 'task'}")

    for kind in ("exec", "block"):
        pool = [e for e in rows if e.get("kind") == kind]
        if not pool:
            continue
        best = max(pool, key=lambda e: float(e.get("duration") or 0))
        if float(best.get("duration") or 0) > 0:
            _add(best, f"longest {KIND_LABEL.get(kind, kind)} in scope")

    bursts = _migration_bursts(rows)
    for ev in bursts:
        _add(ev, ev.get("reason") or "migration burst")
    for ev in _kind_bursts(rows, "block", BURST_WINDOW_NS, 4, "preemption burst"):
        _add(ev, ev.get("reason") or "preemption burst")
    for ev in _kind_bursts(rows, "inter", BURST_WINDOW_NS, 4, "wakeup burst"):
        _add(ev, ev.get("reason") or "wakeup burst")
    isr_rows = [e for e in rows if e.get("kind") == "exec" and _is_isr_name(e.get("task"))]
    for ev in _kind_bursts(isr_rows, "exec", BURST_WINDOW_NS, 3, "ISR burst"):
        item = dict(ev)
        item["kind"] = "isr"
        _add(item, ev.get("reason") or "ISR burst")
    resp_events = (analyze_response_times(rows).get("events") or [])
    if len(resp_events) >= 4:
        vals = sorted(float(e.get("duration") or 0) for e in resp_events)
        n = len(vals)
        mean = sum(vals) / n
        var = sum((v - mean) ** 2 for v in vals) / n
        sigma = math.sqrt(var)
        p99 = vals[percentile_index(n, 0.99)]
        thresh = mean + 3.0 * sigma if sigma > 0 else p99
        for ev in resp_events:
            dur = float(ev.get("duration") or 0)
            if dur <= 0:
                continue
            if sigma > 0 and dur > thresh:
                _add(ev, f"response > mean+3σ for {ev.get('task') or 'task'}")
            elif dur >= p99 and dur >= mean:
                _add(ev, f"response ≥ p99 for {ev.get('task') or 'task'}")
    if resp_events:
        best_r = max(resp_events, key=lambda e: float(e.get("duration") or 0))
        if float(best_r.get("duration") or 0) > 0:
            _add(best_r, "longest response in scope")
    waits = [w for w in (mutex_waits or []) if isinstance(w, dict)]
    waits.extend(e for e in rows if e.get("kind") == "mutex_block")
    if len(waits) >= 4:
        vals = sorted(float(w.get("duration") or 0) for w in waits)
        n = len(vals)
        mean = sum(vals) / n
        p99 = vals[percentile_index(n, 0.99)]
        for w in waits:
            dur = float(w.get("duration") or 0)
            if dur <= 0 or dur < p99 or dur < mean:
                continue
            item = dict(w)
            item["kind"] = "mutex_block"
            item["task"] = w.get("waiter") or w.get("task")
            item["mk"] = w.get("waiter_mk") or w.get("mk")
            _add(item, f"mutex wait spike on {w.get('object') or 'mutex'}")
    elif waits:
        best_w = max(waits, key=lambda e: float(e.get("duration") or 0))
        if float(best_w.get("duration") or 0) > 0:
            item = dict(best_w)
            item["kind"] = "mutex_block"
            item["task"] = best_w.get("waiter") or best_w.get("task")
            item["mk"] = best_w.get("waiter_mk") or best_w.get("mk")
            _add(item, f"mutex wait spike on {best_w.get('object') or 'mutex'}")
    dl_map = {
        str(k): int(v) for k, v in (deadlines or {}).items()
        if int(v or 0) > 0
    }
    if dl_map:
        for ev in resp_events:
            mk = str(ev.get("mk") or "")
            lim_ns = dl_map.get(mk) or dl_map.get(str(ev.get("task") or ""))
            dur = int(ev.get("duration") or 0)
            if not lim_ns or dur <= lim_ns:
                continue
            item = dict(ev)
            item["kind"] = "deadline"
            _add(item, f"deadline miss ({dur} > {lim_ns})")
    for ev in core_busy_anomalies(rows):
        _add(ev, ev.get("reason") or "CPU utilization spike")
    for ev in idle_gap_anomalies(rows):
        _add(ev, ev.get("reason") or "unusual idle")

    flagged.sort(
        key=lambda e: (-float(e.get("duration") or 0), float(e.get("start") or 0)))
    return flagged[:lim]


def best_finding_scope(
    finding: dict,
    events: Sequence[dict],
    time_min: float,
    time_max: float,
) -> Optional[dict]:
    """Propose a cursor window covering a finding's evidence or worst episode."""
    if not isinstance(finding, dict):
        return None
    tmin = float(time_min)
    tmax = float(time_max)
    if tmax <= tmin:
        return None
    times: List[float] = []
    for ev in finding.get("evidence") or []:
        if not isinstance(ev, dict):
            continue
        for key in ("time", "start", "stop"):
            try:
                if ev.get(key) is not None:
                    times.append(float(ev[key]))
            except (TypeError, ValueError):
                continue
    blob = f"{finding.get('title') or ''} {finding.get('text') or ''}"
    for m in _JUMP_RE.finditer(blob):
        try:
            times.append(float(m.group(1)))
        except (TypeError, ValueError):
            continue
    task = str(finding.get("task") or "").strip()
    if not task:
        m = _TASK_RE.search(blob)
        if m:
            task = m.group(1)
    section = "exec"
    reason = "Evidence times from the selected finding"
    matched: Optional[dict] = None
    if times:
        lo, hi = min(times), max(times)
        if task:
            nearby = [
                e for e in (events or [])
                if isinstance(e, dict)
                and _event_matches_task(e, task)
                and float(e.get("start") or 0) <= hi
                and float(e.get("stop") or e.get("start") or 0) >= lo
            ]
            if nearby:
                matched = max(nearby, key=lambda e: float(e.get("duration") or 0))
        if matched is None and (events or []):
            mid = (lo + hi) / 2.0
            matched = min(
                (e for e in events if isinstance(e, dict)),
                key=lambda e: abs(float(e.get("start") or 0) - mid),
                default=None,
            )
    elif task:
        pool = [e for e in (events or []) if isinstance(e, dict) and _event_matches_task(e, task)]
        if pool:
            matched = max(pool, key=lambda e: float(e.get("duration") or 0))
            reason = f"Worst episode for {task}"
    if matched is None and (events or []):
        matched = max(
            (e for e in events if isinstance(e, dict)),
            key=lambda e: float(e.get("duration") or 0),
            default=None,
        )
        if matched is not None:
            reason = "Longest episode in scope"
    if times:
        lo, hi = min(times), max(times)
    elif matched is not None:
        lo = float(matched.get("start") or tmin)
        hi = float(matched.get("stop") or matched.get("start") or lo)
    else:
        return None
    if matched is not None:
        section = KIND_SECTION.get(str(matched.get("kind") or ""), "exec")
        if not task:
            task = str(matched.get("task") or "")
        lo = min(lo, float(matched.get("start") or lo))
        hi = max(hi, float(matched.get("stop") or hi))
        nearby = [
            e for e in (events or [])
            if isinstance(e, dict)
            and float(e.get("start") or 0) <= hi
            and float(e.get("stop") or e.get("start") or 0) >= lo
        ]
        reason = _scope_reason(nearby, task, reason)
    span = max(tmax - tmin, 1.0)
    pad = max(hi - lo, span * 0.01, 1000.0)
    lo = max(tmin, lo - pad)
    hi = min(tmax, hi + pad)
    if lo >= hi:
        hi = min(tmax, lo + max(pad, 1000.0))
        if lo >= hi:
            return None
    return {
        "lo": int(lo),
        "hi": int(hi),
        "reason": reason,
        "task": task,
        "section": section,
        "mk": str((matched or {}).get("mk") or ""),
    }


def finding_overlay_times(findings: Optional[Sequence[dict]], limit: int = 80) -> List[float]:
    """Timestamps to paint on the timeline for Analysis Findings (not user marks)."""
    times: List[float] = []
    seen = set()
    for finding in findings or []:
        if not isinstance(finding, dict):
            continue
        for ev in finding.get("evidence") or []:
            if not isinstance(ev, dict):
                continue
            for key in ("time", "start", "stop"):
                try:
                    if ev.get(key) is not None:
                        t = float(ev[key])
                    else:
                        continue
                except (TypeError, ValueError):
                    continue
                if t in seen:
                    continue
                seen.add(t)
                times.append(t)
        blob = f"{finding.get('title') or ''} {finding.get('text') or ''}"
        for m in _JUMP_RE.finditer(blob):
            try:
                t = float(m.group(1))
            except (TypeError, ValueError):
                continue
            if t in seen:
                continue
            seen.add(t)
            times.append(t)
        if len(times) >= limit:
            break
    return times[:limit]


def task_inspector_line(
    task: Any = "",
    quality_warnings: Optional[Sequence[str]] = None,
) -> str:
    """Status-bar inspector: selected task plus first quality warning."""
    # Callers pass merge keys (``\\0id\\0name``); show Name[id], not NULs.
    name = _task_display_name(str(task or "").strip()) if str(task or "").strip() else ""
    parts = [f"Task {name}" if name else "No task selected"]
    for q in quality_warnings or []:
        text = str(q or "").strip()
        if text:
            parts.append(text[:96])
            break
    return " · ".join(parts)


def parse_signed_delta(text: Any) -> Optional[Tuple[float, str]]:
    """Parse a Trace Compare Δ cell into ``(signed, kind)``."""
    s = str(text or "").strip().replace("−", "-")
    if not s or s in ("—", "–", "-"):
        return None
    m = _DELTA_RE.match(s)
    if not m:
        return None
    sign = -1.0 if m.group(1) == "-" else 1.0
    try:
        val = float(m.group(2))
    except (TypeError, ValueError):
        return None
    unit = (m.group(3) or "").lower()
    if unit in _UNIT_NS:
        return sign * val * _UNIT_NS[unit], "time"
    if unit == "%":
        return sign * val, "pct"
    if unit == "/s":
        return sign * val, "rate"
    return sign * val, "count"


def compare_candidates_from_tables(tables: dict) -> List[dict]:
    """Normalize Desktop list-rows and Web object-rows into regression candidates."""
    if not isinstance(tables, dict):
        return []
    out: List[dict] = []
    for row in tables.get("summary") or []:
        label, delta = _row_label_delta(row, "label", "delta", 0, 3)
        if not label or _skip_summary_label(label):
            continue
        parsed = parse_signed_delta(delta)
        if parsed is None:
            continue
        signed, kind = parsed
        out.append({
            "label": label,
            "metric": "summary",
            "delta": str(delta),
            "signed": signed,
            "kind": kind,
        })
    for key, metric, name_idx, delta_idx, name_key, delta_key in (
        ("execution", "exec max", 0, 7, "name", "deltaMax"),
        ("blocking", "block avg", 0, 7, "name", "delta"),
        ("inter_arrival", "inter avg", 0, 7, "name", "delta"),
        ("interArrival", "inter avg", 0, 7, "name", "delta"),
        ("response", "response p99", 0, 3, "name", "delta"),
        ("mutex_block", "mutex block", 0, 3, "name", "delta"),
        ("mutexBlock", "mutex block", 0, 3, "name", "delta"),
        ("deadlines", "deadline misses", 0, 3, "name", "delta"),
    ):
        for row in tables.get(key) or []:
            name, delta = _row_label_delta(row, name_key, delta_key, name_idx, delta_idx)
            if not name:
                continue
            parsed = parse_signed_delta(delta)
            if parsed is None:
                continue
            signed, kind = parsed
            out.append({
                "label": f"{name} {metric}",
                "metric": metric,
                "delta": str(delta),
                "signed": signed,
                "kind": kind,
            })
    return out


def top_compare_regressions(candidates: Sequence[dict], limit: int = 4) -> List[dict]:
    """Largest A−B increases (A worse) among compare candidates."""
    lim = max(1, min(12, int(limit or 4)))
    worse = [
        dict(c) for c in (candidates or [])
        if isinstance(c, dict) and float(c.get("signed") or 0) > 0
    ]
    time_rows = [c for c in worse if c.get("kind") == "time"]
    other = [c for c in worse if c.get("kind") != "time"]
    time_rows.sort(key=lambda c: -abs(float(c.get("signed") or 0)))
    other.sort(key=lambda c: -abs(float(c.get("signed") or 0)))
    picked = time_rows[: max(0, lim - 1)]
    if other and len(picked) < lim:
        picked.append(other[0])
    if len(picked) < lim:
        for c in time_rows + other:
            if c not in picked:
                picked.append(c)
            if len(picked) >= lim:
                break
    return picked[:lim]


def compare_summary_strip(tables: dict, limit: int = 4) -> dict:
    """Headline deltas plus the largest regressions for the Compare dialog."""
    cands = compare_candidates_from_tables(tables)
    headline: List[dict] = []
    for row in (tables or {}).get("summary") or []:
        label, delta = _row_label_delta(row, "label", "delta", 0, 3)
        if label in _SUMMARY_STRIP_LABELS:
            headline.append({"label": label.replace(" (cursor range)", ""), "delta": str(delta)})
    regs = top_compare_regressions(cands, limit)
    shared = list((tables or {}).get("shared_patterns") or [])
    return {
        "headline": headline,
        "regressions": regs,
        "shared_patterns": shared,
        "why": compare_why({"regressions": regs, "shared_patterns": shared}),
    }


def prepare_ux_events(trace: Any) -> List[dict]:
    """Walk slices once and store the full-trace harvest on *trace*."""
    cached = _ux_events_cache(trace)
    if cached is not None:
        return cached
    events = _harvest_ux_events_from_segments(trace, None, None)
    try:
        trace.ux_events_full = events
    except Exception:
        pass
    try:
        trace.uxEventsFull = events
    except Exception:
        pass
    return events


def _ux_events_cache(trace: Any) -> Optional[List[dict]]:
    if trace is None:
        return None
    cached = getattr(trace, "ux_events_full", None)
    if cached is None:
        cached = getattr(trace, "uxEventsFull", None)
    return cached if isinstance(cached, list) else None


def _filter_cached_ux_events(events: Sequence[dict], lo: int, hi: int) -> List[dict]:
    """Apply the same in-range rules as a scoped harvest walk."""
    out: List[dict] = []
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        kind = str(ev.get("kind") or "")
        start = int(ev.get("start") or 0)
        stop = int(ev.get("stop") or start)
        if kind == "migration":
            if lo <= start <= hi:
                out.append(ev)
        elif kind == "inter":
            jump = int(ev.get("jump_ns") or stop)
            if start >= lo and lo <= jump <= hi:
                out.append(ev)
        elif start >= lo and stop <= hi:
            out.append(ev)
    return out


def harvest_ux_events(trace: Any, lo: Optional[int] = None, hi: Optional[int] = None) -> List[dict]:
    """Collect exec / block / inter / migration episodes from a loaded trace."""
    cached = _ux_events_cache(trace)
    if cached is not None:
        if lo is None or hi is None:
            return cached
        return _filter_cached_ux_events(cached, int(lo), int(hi))
    return _harvest_ux_events_from_segments(trace, lo, hi)


def _harvest_ux_events_from_segments(
    trace: Any, lo: Optional[int], hi: Optional[int],
) -> List[dict]:
    """Walk segment maps. Used to build the load-time cache."""
    events: List[dict] = []
    if trace is None:
        return events
    smap = getattr(trace, "seg_map_by_merge_key", None)
    if smap is None:
        smap = getattr(trace, "segByMergeKey", None)
    if smap is None:
        return events
    items = smap.items() if hasattr(smap, "items") else []
    repr_map = getattr(trace, "task_repr", None)
    if repr_map is None:
        repr_map = getattr(trace, "taskRepr", None) or {}
    for mk, segs in items:
        raw = _map_get(repr_map, mk, mk)
        _, _, tname = _parse_task_name(str(raw))
        if _is_idle_task_name(tname) or tname == "TICK":
            continue
        name = _task_display_name(str(raw))
        ordered = _ordered_segs(segs)
        if not ordered:
            continue
        for seg in ordered:
            start = int(getattr(seg, "start", 0) or 0)
            end = int(getattr(seg, "end", 0) or 0)
            dur = end - start
            if dur <= 0:
                continue
            if lo is not None and hi is not None and not _seg_fully_in_range(seg, lo, hi):
                continue
            events.append(_event(
                "exec", name, str(mk), start, end, dur, start, getattr(seg, "core", ""),
            ))
        for i in range(1, len(ordered)):
            prev, nxt = ordered[i - 1], ordered[i]
            if lo is not None and hi is not None:
                if not (_seg_fully_in_range(prev, lo, hi) and _seg_fully_in_range(nxt, lo, hi)):
                    continue
            gap = int(nxt.start) - int(prev.end)
            if gap > 0:
                events.append(_event(
                    "block", name, str(mk), int(prev.end), int(nxt.start), gap,
                    int(nxt.start), getattr(nxt, "core", ""),
                ))
            arr = int(nxt.start) - int(prev.start)
            if arr > 0:
                if lo is not None and hi is not None and (
                        int(nxt.start) < lo or int(nxt.start) > hi):
                    continue
                events.append(_event(
                    "inter", name, str(mk), int(prev.start), int(nxt.start), arr,
                    int(nxt.start), getattr(nxt, "core", ""),
                ))
    for ev in getattr(trace, "migrations", None) or []:
        if isinstance(ev, dict):
            ns = int(ev.get("ns") or 0)
            mk = str(ev.get("mergeKey") or ev.get("merge_key") or "")
            gap = int(ev.get("gapNs") or ev.get("gap_ns") or 0)
        else:
            ns = int(getattr(ev, "ns", 0) or 0)
            mk = str(
                getattr(ev, "merge_key", None)
                or getattr(ev, "mergeKey", None)
                or ""
            )
            gap = int(
                getattr(ev, "gap_ns", None)
                or getattr(ev, "gapNs", None)
                or 0
            )
        if lo is not None and hi is not None and (ns < lo or ns > hi):
            continue
        raw = _map_get(repr_map, mk, mk)
        _, _, tname = _parse_task_name(str(raw))
        if _is_idle_task_name(tname) or tname == "TICK":
            continue
        events.append(_event(
            "migration", _task_display_name(str(raw)), mk, ns, ns + max(gap, 1),
            max(gap, 1), ns, "",
        ))
    return events


def _event(kind, task, mk, start, stop, duration, jump_ns, core) -> dict:
    return {
        "kind": kind,
        "task": task,
        "mk": mk,
        "start": int(start),
        "stop": int(stop),
        "duration": int(duration),
        "jump_ns": int(jump_ns),
        "core": str(core or ""),
        "section": KIND_SECTION.get(kind, "exec"),
        "reason": "",
    }


def _ordered_segs(segs) -> list:
    if segs is None:
        return []
    try:
        rows = list(segs)
    except TypeError:
        return []
    rows = [s for s in rows if hasattr(s, "start")]
    for i in range(1, len(rows)):
        if int(rows[i].start) < int(rows[i - 1].start):
            rows.sort(key=lambda s: int(s.start))
            break
    return rows


def _map_get(mapping, key, default):
    if mapping is None:
        return default
    getter = getattr(mapping, "get", None)
    if callable(getter):
        return getter(key, default)
    try:
        return mapping[key]
    except Exception:
        return default


def _event_matches_task(ev: dict, task: str) -> bool:
    t = str(task or "").strip().lower()
    if not t:
        return False
    return t in (
        str(ev.get("task") or "").strip().lower(),
        str(ev.get("mk") or "").strip().lower(),
    ) or t in str(ev.get("task") or "").lower()


def _migration_bursts(events: Sequence[dict], window_ns: int = 1000) -> List[dict]:
    by_mk: Dict[str, List[dict]] = {}
    for ev in events:
        if ev.get("kind") != "migration":
            continue
        by_mk.setdefault(str(ev.get("mk") or ev.get("task") or ""), []).append(ev)
    out: List[dict] = []
    for _mk, group in by_mk.items():
        group = sorted(group, key=lambda e: float(e.get("start") or 0))
        if len(group) < 3:
            continue
        i = 0
        while i < len(group):
            j = i
            while j + 1 < len(group) and (
                    float(group[j + 1].get("start") or 0)
                    - float(group[i].get("start") or 0) <= window_ns):
                j += 1
            count = j - i + 1
            if count >= 3:
                first, last = group[i], group[j]
                item = dict(last)
                item["start"] = int(first.get("start") or 0)
                item["stop"] = int(last.get("stop") or last.get("start") or 0)
                item["duration"] = max(
                    int(item["stop"]) - int(item["start"]), count)
                item["reason"] = f"{count} migrations within {window_ns} ns"
                out.append(item)
                i = j + 1
            else:
                i += 1
    return out


def _row_label_delta(row, name_key, delta_key, name_idx, delta_idx):
    if isinstance(row, dict):
        return str(row.get(name_key) or row.get("label") or ""), row.get(delta_key)
    if isinstance(row, (list, tuple)) and len(row) > max(name_idx, delta_idx):
        return str(row[name_idx] or ""), row[delta_idx]
    return "", None


def _skip_summary_label(label: str) -> bool:
    low = label.lower()
    return "load balance" in low or "tick health" in low or "tick mode" in low


def analyze_task_periods(events: Sequence[dict], min_gaps: int = 3) -> List[dict]:
    """Per-task period / jitter from inter-arrival episodes (p50 = expected)."""
    need = max(2, int(min_gaps or 3))
    by_mk: Dict[str, List[dict]] = {}
    for ev in events or []:
        if not isinstance(ev, dict) or ev.get("kind") != "inter":
            continue
        mk = str(ev.get("mk") or ev.get("task") or "")
        if not mk:
            continue
        by_mk.setdefault(mk, []).append(ev)
    rows: List[dict] = []
    for mk, group in by_mk.items():
        group = sorted(group, key=lambda e: float(e.get("start") or 0))
        gaps = [int(e.get("duration") or 0) for e in group if int(e.get("duration") or 0) > 0]
        if len(gaps) < need:
            continue
        ordered = sorted(gaps)
        n = len(ordered)
        mean = sum(ordered) / n
        expected = ordered[percentile_index(n, 0.50)]
        if expected <= 0:
            expected = int(round(mean)) or 1
        p95 = ordered[percentile_index(n, 0.95)]
        p99 = ordered[percentile_index(n, 0.99)]
        min_g, max_g = ordered[0], ordered[-1]
        var = sum((g - mean) ** 2 for g in ordered) / n
        std = math.sqrt(var)
        cv = (std / mean) if mean else 0.0
        rms = math.sqrt(sum((g - expected) ** 2 for g in ordered) / n)
        missed = sum(1 for g in ordered if g > expected * PERIOD_MISS_RATIO)
        extra = sum(1 for g in ordered if g < expected * PERIOD_EXTRA_RATIO)
        burst = sum(1 for g in ordered if g < expected * PERIOD_BURST_RATIO)

        def _ev_for(target: int) -> dict:
            for e in group:
                if int(e.get("duration") or 0) == target:
                    return dict(e)
            return dict(group[0])

        worst = max(group, key=lambda e: int(e.get("duration") or 0))
        miss_ev = None
        for e in group:
            if int(e.get("duration") or 0) > expected * PERIOD_MISS_RATIO:
                if miss_ev is None or int(e.get("duration") or 0) > int(miss_ev.get("duration") or 0):
                    miss_ev = e
        rows.append({
            "task": group[0].get("task") or mk,
            "mk": mk,
            "n": n,
            "expected_ns": int(expected),
            "min_ns": min_g,
            "avg_ns": int(round(mean)),
            "max_ns": max_g,
            "p50_ns": int(expected),
            "p95_ns": p95,
            "p99_ns": p99,
            "jitter_ns": max_g - min_g,
            "rms_ns": int(round(rms)),
            "cv": round(cv, 4),
            "missed": missed,
            "extra": extra,
            "burst": burst,
            "min_ev": _ev_for(min_g),
            "max_ev": _ev_for(max_g),
            "p50_ev": _ev_for(int(expected)),
            "p95_ev": _ev_for(p95),
            "p99_ev": _ev_for(p99),
            "worst_ev": dict(worst),
            "miss_ev": dict(miss_ev) if miss_ev else dict(worst),
            "samples": gaps,
            "spark": sparkline(gaps),
            "section": "period",
        })
    rows.sort(key=lambda r: (-int(r.get("missed") or 0), -float(r.get("cv") or 0),
                             str(r.get("task") or "")))
    return rows


def task_core_matrix(
    events: Sequence[dict],
    cores: Optional[Sequence[str]] = None,
    span_ns: int = 0,
    limit: int = 40,
) -> dict:
    """Per-task execution time on each core (percent of scoped span)."""
    core_list = [str(c) for c in (cores or []) if c]
    by_mk: Dict[str, dict] = {}
    for ev in events or []:
        if not isinstance(ev, dict) or ev.get("kind") != "exec":
            continue
        mk = str(ev.get("mk") or ev.get("task") or "")
        core = str(ev.get("core") or "")
        dur = int(ev.get("duration") or 0)
        if not mk or not core or dur <= 0:
            continue
        if core not in core_list:
            core_list.append(core)
        rec = by_mk.setdefault(mk, {
            "task": ev.get("task") or mk, "mk": mk, "ns": {}, "first": {},
        })
        rec["ns"][core] = rec["ns"].get(core, 0) + dur
        if core not in rec["first"]:
            rec["first"][core] = ev
    span = max(1, int(span_ns or 0))
    lim = max(1, min(80, int(limit or 40)))
    rows: List[dict] = []
    for mk, rec in by_mk.items():
        total = sum(rec["ns"].values())
        if total <= 0:
            continue
        cells = {}
        for c in core_list:
            ns = int(rec["ns"].get(c, 0))
            ev = rec["first"].get(c)
            cells[c] = {
                "ns": ns,
                "pct_span": 100.0 * ns / span,
                "pct_task": 100.0 * ns / total,
                "start": int(ev.get("start") or 0) if ev else 0,
                "stop": int(ev.get("stop") or 0) if ev else 0,
                "jump_ns": int((ev or {}).get("jump_ns") or (ev or {}).get("start") or 0),
            }
        rows.append({
            "task": rec["task"], "mk": mk, "total_ns": total,
            "cells": cells, "section": "task_core",
        })
    rows.sort(key=lambda r: (-int(r["total_ns"]), str(r.get("task") or "")))
    return {"cores": core_list, "rows": rows[:lim], "span_ns": span}


def harvest_mutex_holds(
    trace: Any, lo: Optional[int] = None, hi: Optional[int] = None,
) -> List[dict]:
    """Mutex hold episodes from desktop ``sync_objects`` or web ``syncObjects``."""
    objs = getattr(trace, "sync_objects", None)
    if objs is None:
        objs = getattr(trace, "syncObjects", None)
    if objs is None:
        return []
    values = objs.values() if hasattr(objs, "values") else []
    out: List[dict] = []
    for obj in values:
        if not isinstance(obj, dict):
            continue
        if str(obj.get("kind") or "").lower() != "mutex":
            continue
        key = str(obj.get("key") or "")
        for h in obj.get("holds") or []:
            if not isinstance(h, dict):
                continue
            start = int(h.get("start_ns") or h.get("startNs") or 0)
            stop = int(h.get("stop_ns") or h.get("stopNs") or 0)
            if stop <= start:
                continue
            if lo is not None and hi is not None and (stop < lo or start > hi):
                continue
            out.append({
                "object": key,
                "holder": str(h.get("holder_label") or h.get("holderLabel") or ""),
                "holder_mk": str(h.get("holder_mk") or h.get("holderMk") or ""),
                "start": start,
                "stop": stop,
                "duration": stop - start,
            })
    return out


def pair_mutex_waits(
    holds: Sequence[dict], slack_ns: int = MUTEX_HANDOFF_SLACK_NS,
) -> List[dict]:
    """Heuristic: the next distinct acquirer of a mutex waited out the prior hold."""
    by_obj: Dict[str, List[dict]] = {}
    for h in holds or []:
        if isinstance(h, dict):
            by_obj.setdefault(str(h.get("object") or ""), []).append(h)
    slack = max(0, int(slack_ns or 0))
    waits: List[dict] = []
    for obj, group in by_obj.items():
        group = sorted(group, key=lambda x: int(x.get("start") or 0))
        for i in range(1, len(group)):
            prev, nxt = group[i - 1], group[i]
            o_mk = str(prev.get("holder_mk") or "")
            w_mk = str(nxt.get("holder_mk") or "")
            if not o_mk or not w_mk or o_mk == w_mk:
                continue
            gap = int(nxt.get("start") or 0) - int(prev.get("stop") or 0)
            if gap < -1 or gap > slack:
                continue
            start = int(prev.get("start") or 0)
            stop = int(prev.get("stop") or 0)
            waits.append({
                "waiter": str(nxt.get("holder") or w_mk),
                "waiter_mk": w_mk,
                "owner": str(prev.get("holder") or o_mk),
                "owner_mk": o_mk,
                "object": obj,
                "start": start,
                "stop": stop,
                "duration": max(1, stop - start),
                "jump_ns": start,
                "section": "wait_owner",
            })
    return waits


def waiter_owner_matrix(waits: Sequence[dict], limit: int = 16) -> dict:
    """Aggregate waiter×owner wait time; keep the busiest tasks."""
    totals: Dict[Tuple[str, str], dict] = {}
    names: Dict[str, str] = {}
    for w in waits or []:
        if not isinstance(w, dict):
            continue
        wk = str(w.get("waiter_mk") or "")
        ok = str(w.get("owner_mk") or "")
        if not wk or not ok:
            continue
        rec = totals.setdefault((wk, ok), {"ns": 0, "count": 0, "worst": w})
        rec["ns"] += int(w.get("duration") or 0)
        rec["count"] += 1
        if int(w.get("duration") or 0) > int(rec["worst"].get("duration") or 0):
            rec["worst"] = w
        names[wk] = str(w.get("waiter") or wk)
        names[ok] = str(w.get("owner") or ok)
    invol: Dict[str, int] = {}
    for (wk, ok), rec in totals.items():
        invol[wk] = invol.get(wk, 0) + rec["ns"]
        invol[ok] = invol.get(ok, 0) + rec["ns"]
    lim = max(2, min(24, int(limit or 16)))
    tasks = sorted(invol, key=lambda mk: (-invol[mk], names.get(mk, mk)))[:lim]
    cells: Dict[str, dict] = {}
    for (wk, ok), rec in totals.items():
        if wk not in tasks or ok not in tasks:
            continue
        worst = rec["worst"]
        cells[f"{wk}|{ok}"] = {
            "ns": rec["ns"],
            "count": rec["count"],
            "start": int(worst.get("start") or 0),
            "stop": int(worst.get("stop") or 0),
            "jump_ns": int(worst.get("jump_ns") or worst.get("start") or 0),
            "waiter": names.get(wk, wk),
            "owner": names.get(ok, ok),
            "waiter_mk": wk,
            "owner_mk": ok,
            "section": "wait_owner",
        }
    return {
        "tasks": [{"mk": mk, "task": names.get(mk, mk)} for mk in tasks],
        "cells": cells,
    }


def health_inputs_from_events(
    events: Sequence[dict],
    span_ns: int = 0,
    deadline_mks: Optional[Iterable[str]] = None,
) -> List[dict]:
    """Fold harvested episodes into the inputs ``task_health_scores`` expects."""
    by_mk: Dict[str, dict] = {}
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        mk = str(ev.get("mk") or ev.get("task") or "")
        if not mk:
            continue
        rec = by_mk.setdefault(mk, {
            "task": ev.get("task") or mk, "mk": mk,
            "exec": [], "block": [], "inter": [], "mig": 0, "cpu_ns": 0,
        })
        kind = ev.get("kind")
        dur = int(ev.get("duration") or 0)
        if kind == "exec" and dur > 0:
            rec["exec"].append(dur)
            rec["cpu_ns"] += dur
        elif kind == "block" and dur > 0:
            rec["block"].append(dur)
        elif kind == "inter" and dur > 0:
            rec["inter"].append(dur)
        elif kind == "migration":
            rec["mig"] += 1
    span = max(1, int(span_ns or 0))
    dead = {str(x) for x in (deadline_mks or []) if x}
    out: List[dict] = []
    for mk, rec in by_mk.items():
        if not rec["exec"]:
            continue
        e_cv, e_ratio, e_n = _sample_cv_ratio(rec["exec"])
        b_cv, b_ratio, _ = _sample_cv_ratio(rec["block"])
        p_cv, _, _ = _sample_cv_ratio(rec["inter"])
        missed = 0
        if rec["inter"]:
            ordered = sorted(rec["inter"])
            expected = ordered[percentile_index(len(ordered), 0.50)]
            if expected > 0:
                missed = sum(1 for g in ordered if g > expected * PERIOD_MISS_RATIO)
        out.append({
            "task": rec["task"],
            "mk": mk,
            "exec_cv": e_cv,
            "exec_max_avg": e_ratio,
            "exec_n": e_n,
            "block_cv": b_cv,
            "block_max_avg": b_ratio,
            "period_cv": p_cv,
            "missed": missed,
            "mig_count": rec["mig"],
            "mig_ratio": rec["mig"] / max(e_n, 1),
            "cpu_pct": 100.0 * rec["cpu_ns"] / span,
            "deadline_miss": mk in dead or str(rec["task"]) in dead,
        })
    return out


def task_health_scores(inputs: Sequence[dict]) -> List[dict]:
    """Heuristic 0–100 score from measured stats (not an AI probability)."""
    rows: List[dict] = []
    for inp in inputs or []:
        if not isinstance(inp, dict):
            continue
        bands: Dict[str, str] = {}
        pen = 0
        e_band, e_pen = _worse_band(
            _dim(float(inp.get("exec_cv") or 0), 0.5, 1.0, 10, 20),
            _dim(float(inp.get("exec_max_avg") or 0), 3.0, 8.0, 10, 20),
        )
        bands["execution"] = e_band
        pen += e_pen
        b_band, b_pen = _worse_band(
            _dim(float(inp.get("block_cv") or 0), 0.6, 1.2, 10, 20),
            _dim(float(inp.get("block_max_avg") or 0), 4.0, 10.0, 10, 20),
        )
        bands["blocking"] = b_band
        pen += b_pen
        p_band, p_pen = _dim(float(inp.get("period_cv") or 0), 0.15, 0.40, 8, 16)
        missed = int(inp.get("missed") or 0)
        if missed >= 3:
            p_band, p_pen = "fail", max(p_pen, 16)
        elif missed > 0 and p_band == "ok":
            p_band, p_pen = "warn", max(p_pen, 8)
        bands["period"] = p_band
        pen += p_pen
        m_band, m_pen = _dim(float(inp.get("mig_ratio") or 0), 0.3, 0.7, 8, 16)
        bands["migration"] = m_band
        pen += m_pen
        if inp.get("deadline_miss"):
            bands["deadline"] = "fail"
            pen += 30
        else:
            bands["deadline"] = "ok"
        c_band, c_pen = _dim(float(inp.get("cpu_pct") or 0), 80.0, 95.0, 8, 16)
        bands["cpu"] = c_band
        pen += c_pen
        score = max(0, min(100, 100 - pen))
        rows.append({
            "task": inp.get("task"),
            "mk": inp.get("mk"),
            "score": score,
            "bands": bands,
            "marks": {k: HEALTH_MARK.get(v, v) for k, v in bands.items()},
            "section": "task_health",
            "disclaimer": (
                "Heuristic score from measured statistics, not an AI probability."
            ),
        })
    rows.sort(key=lambda r: (int(r.get("score") or 0), str(r.get("task") or "")))
    return rows


def _sample_cv_ratio(samples: Sequence[int]) -> Tuple[float, float, int]:
    vals = [int(v) for v in samples if int(v or 0) > 0]
    if not vals:
        return 0.0, 0.0, 0
    n = len(vals)
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / n
    cv = (math.sqrt(var) / mean) if mean else 0.0
    ratio = (max(vals) / mean) if mean else 0.0
    return cv, ratio, n


def _dim(value: float, warn_at: float, fail_at: float,
         warn_pen: int, fail_pen: int) -> Tuple[str, int]:
    if value >= fail_at:
        return "fail", fail_pen
    if value >= warn_at:
        return "warn", warn_pen
    return "ok", 0


def _worse_band(a: Tuple[str, int], b: Tuple[str, int]) -> Tuple[str, int]:
    rank = {"ok": 0, "warn": 1, "fail": 2}
    pick = a if rank.get(a[0], 0) >= rank.get(b[0], 0) else b
    return pick[0], max(a[1], b[1])


def _is_isr_name(name: Any) -> bool:
    return bool(_ISR_RE.search(str(name or "")))


def _scope_reason(events: Sequence[dict], task: str, fallback: str) -> str:
    kinds = {"exec": 0, "block": 0, "inter": 0, "migration": 0}
    for e in events or []:
        k = str(e.get("kind") or "")
        if k in kinds:
            kinds[k] += 1
    bits = []
    if kinds["exec"]:
        bits.append("activation" if kinds["inter"] else "execution")
    if kinds["block"]:
        bits.append(f"{kinds['block']} preemption/wait gap"
                    + ("s" if kinds["block"] != 1 else ""))
    if kinds["migration"]:
        bits.append(f"{kinds['migration']} migration"
                    + ("s" if kinds["migration"] != 1 else ""))
    if not bits:
        return fallback
    who = f" for {task}" if task else ""
    return "Contains" + who + ": " + ", ".join(bits)


def _kind_bursts(
    events: Sequence[dict],
    kind: str,
    window_ns: int,
    min_count: int,
    label: str,
) -> List[dict]:
    group = sorted(
        [e for e in events or [] if isinstance(e, dict) and e.get("kind") == kind],
        key=lambda e: float(e.get("start") or 0),
    )
    if len(group) < min_count:
        return []
    out: List[dict] = []
    i = 0
    while i < len(group):
        j = i
        while j + 1 < len(group) and (
                float(group[j + 1].get("start") or 0)
                - float(group[i].get("start") or 0) <= window_ns):
            j += 1
        count = j - i + 1
        if count >= min_count:
            first, last = group[i], group[j]
            item = dict(last)
            item["start"] = int(first.get("start") or 0)
            item["stop"] = int(last.get("stop") or last.get("start") or 0)
            item["duration"] = max(int(item["stop"]) - int(item["start"]), count)
            item["reason"] = f"{count} {label}s within {window_ns} ns"
            if label.endswith(" burst"):
                item["reason"] = f"{count} {label.replace(' burst', '')}s within {window_ns} ns"
            out.append(item)
            i = j + 1
        else:
            i += 1
    return out


def _duration_stats(samples: Sequence[int]) -> Optional[dict]:
    ordered = sorted(int(s) for s in samples if int(s or 0) > 0)
    if not ordered:
        return None
    n = len(ordered)
    mean = sum(ordered) / n
    var = sum((v - mean) ** 2 for v in ordered) / n
    std = math.sqrt(var)
    return {
        "n": n,
        "min_ns": ordered[0],
        "avg_ns": int(round(mean)),
        "max_ns": ordered[-1],
        "p50_ns": ordered[percentile_index(n, 0.50)],
        "p90_ns": ordered[percentile_index(n, 0.90)],
        "p95_ns": ordered[percentile_index(n, 0.95)],
        "p99_ns": ordered[percentile_index(n, 0.99)],
        "p999_ns": ordered[percentile_index(n, 0.999)],
        "jitter_ns": ordered[-1] - ordered[0],
        "std_ns": int(round(std)),
        "cv": round((std / mean) if mean else 0.0, 4),
    }


def analyze_response_times(events: Sequence[dict]) -> dict:
    """Heuristic ready→completion: previous slice end to this slice end.

    First slice of a task uses execution duration only. This is not a kernel
    release/completion pair — BTF often lacks those events.
    """
    by_mk: Dict[str, List[dict]] = {}
    for ev in events or []:
        if not isinstance(ev, dict) or ev.get("kind") != "exec":
            continue
        mk = str(ev.get("mk") or ev.get("task") or "")
        if mk:
            by_mk.setdefault(mk, []).append(ev)
    resp_events: List[dict] = []
    rows: List[dict] = []
    for mk, group in by_mk.items():
        group = sorted(group, key=lambda e: float(e.get("start") or 0))
        samples: List[int] = []
        task = str(group[0].get("task") or mk)
        for i, ev in enumerate(group):
            if i == 0:
                ready = int(ev.get("start") or 0)
            else:
                ready = int(group[i - 1].get("stop") or group[i - 1].get("start") or 0)
            complete = int(ev.get("stop") or ev.get("start") or 0)
            dur = max(0, complete - ready)
            if dur <= 0:
                continue
            samples.append(dur)
            item = _event(
                "response", task, mk, ready, complete, dur, ready, ev.get("core"),
            )
            item["exec_ns"] = int(ev.get("duration") or 0)
            item["wait_ns"] = max(0, dur - int(ev.get("duration") or 0))
            resp_events.append(item)
        stats = _duration_stats(samples)
        if not stats:
            continue
        slice_evs = resp_events[-len(samples):]
        worst = max(slice_evs, key=lambda e: int(e.get("duration") or 0))

        def _ev_for(target: int) -> dict:
            for e in slice_evs:
                if int(e.get("duration") or 0) == int(target):
                    return dict(e)
            return dict(worst)

        row = dict(stats)
        row.update({
            "task": task, "mk": mk, "section": "response",
            "worst_ev": dict(worst),
            "min_ev": _ev_for(stats["min_ns"]),
            "max_ev": _ev_for(stats["max_ns"]),
            "p50_ev": _ev_for(stats["p50_ns"]),
            "p90_ev": _ev_for(stats["p90_ns"]),
            "p95_ev": _ev_for(stats["p95_ns"]),
            "p99_ev": _ev_for(stats["p99_ns"]),
            "p999_ev": _ev_for(stats["p999_ns"]),
            "disclaimer": (
                "Heuristic ready→completion from adjacent slices, not an "
                "explicit BTF release/completion pair."
            ),
        })
        rows.append(row)
    rows.sort(key=lambda r: (-int(r.get("p99_ns") or 0), str(r.get("task") or "")))
    return {"rows": rows, "events": resp_events}


def _index_execs(events: Sequence[dict]) -> Dict[str, Tuple[List[dict], List[int]]]:
    """Same-core exec slices, start-sorted, for O(log n + overlaps) window scans."""
    by_core: Dict[str, List[dict]] = {}
    for ev in events or []:
        if not isinstance(ev, dict) or ev.get("kind") != "exec":
            continue
        core = str(ev.get("core") or "")
        if core:
            by_core.setdefault(core, []).append(ev)
    indexed: Dict[str, Tuple[List[dict], List[int]]] = {}
    for core, rows in by_core.items():
        rows.sort(key=lambda e: int(e.get("start") or 0))
        indexed[core] = (rows, [int(e.get("start") or 0) for e in rows])
    return indexed


def _iter_overlapping(
    rows: Sequence[dict], starts: Sequence[int], lo: int, hi: int,
) -> Iterator[dict]:
    """Yield non-overlapping slices that intersect [lo, hi)."""
    if not rows or hi <= lo:
        return
    i = bisect_right(starts, lo) - 1
    if i < 0:
        i = 0
    n = len(rows)
    while i < n:
        ev = rows[i]
        a = int(ev.get("start") or 0)
        if a >= hi:
            break
        b = int(ev.get("stop") or a)
        if b > lo:
            yield ev
        i += 1


def critical_path_rows(events: Sequence[dict], limit: int = 8) -> List[dict]:
    """Decompose the worst response windows into exec / preempt / wait / migration."""
    resp = analyze_response_times(events).get("events") or []
    if not resp:
        return []
    worst = sorted(resp, key=lambda e: -int(e.get("duration") or 0))[: max(1, min(20, limit))]
    by_core = _index_execs(events)
    migs_by_mk: Dict[str, List[dict]] = {}
    blocks_by_mk: Dict[str, List[dict]] = {}
    for m in events or []:
        if not isinstance(m, dict):
            continue
        kind = m.get("kind")
        mk = str(m.get("mk") or "")
        if kind == "migration" and mk:
            migs_by_mk.setdefault(mk, []).append(m)
        elif kind == "block" and mk:
            blocks_by_mk.setdefault(mk, []).append(m)
    out: List[dict] = []
    for ev in worst:
        lo = int(ev.get("start") or 0)
        hi = int(ev.get("stop") or lo)
        mk = str(ev.get("mk") or "")
        core = str(ev.get("core") or "")
        exec_ns = 0
        preempt_ns = 0
        exec_ev = None
        preempt_ev = None
        pools = [by_core[core]] if core and core in by_core else list(by_core.values())
        for rows, starts in pools:
            for other in _iter_overlapping(rows, starts, lo, hi):
                a = int(other.get("start") or 0)
                b = int(other.get("stop") or a)
                overlap = min(b, hi) - max(a, lo)
                if overlap <= 0:
                    continue
                if str(other.get("mk") or "") == mk:
                    exec_ns += overlap
                    if exec_ev is None or overlap > int(exec_ev.get("duration") or 0):
                        exec_ev = dict(other)
                        exec_ev["duration"] = overlap
                else:
                    preempt_ns += overlap
                    if preempt_ev is None or overlap > int(preempt_ev.get("duration") or 0):
                        preempt_ev = dict(other)
                        preempt_ev["start"] = max(a, lo)
                        preempt_ev["stop"] = min(b, hi)
                        preempt_ev["duration"] = overlap
                        preempt_ev["jump_ns"] = max(a, lo)
                        preempt_ev["section"] = "preempt_matrix"
        wait_ns = 0
        wait_ev = None
        for blk in blocks_by_mk.get(mk, ()):
            a = int(blk.get("start") or 0)
            b = int(blk.get("stop") or a)
            overlap = min(b, hi) - max(a, lo)
            if overlap <= 0:
                continue
            wait_ns += overlap
            if wait_ev is None or overlap > int(wait_ev.get("duration") or 0):
                wait_ev = dict(blk)
                wait_ev["start"] = max(a, lo)
                wait_ev["stop"] = min(b, hi)
                wait_ev["duration"] = overlap
                wait_ev["jump_ns"] = max(a, lo)
        mig_ns = 0
        mig_ev = None
        for m in migs_by_mk.get(mk, ()):
            t = int(m.get("start") or 0)
            if lo <= t <= hi:
                dur = int(m.get("duration") or 1)
                mig_ns += dur
                if mig_ev is None or dur > int(mig_ev.get("duration") or 0):
                    mig_ev = dict(m)
        total = max(1, int(ev.get("duration") or 0))
        other_ns = max(0, total - exec_ns - preempt_ns - wait_ns - mig_ns)
        out.append({
            "task": ev.get("task"),
            "mk": mk,
            "start": lo,
            "stop": hi,
            "jump_ns": lo,
            "duration": total,
            "exec_ns": exec_ns,
            "preempt_ns": preempt_ns,
            "wait_ns": wait_ns,
            "migration_ns": mig_ns,
            "other_ns": other_ns,
            "exec_ev": exec_ev or dict(ev),
            "preempt_ev": preempt_ev,
            "wait_ev": wait_ev,
            "mig_ev": mig_ev,
            "other_ev": dict(ev),
            "section": "crit_path",
            "kind": "crit_path",
            "reason": (
                f"exec {exec_ns} · preempt {preempt_ns} · wait {wait_ns} · "
                f"mig {mig_ns} · other {other_ns}"
            ),
        })
    return out


def preemption_pairs(events: Sequence[dict]) -> List[dict]:
    """Victim block × overlapping exec on the same core (or any core if unknown)."""
    by_core = _index_execs(events)
    pairs: List[dict] = []
    for block in events or []:
        if not isinstance(block, dict) or block.get("kind") != "block":
            continue
        blo = int(block.get("start") or 0)
        bhi = int(block.get("stop") or blo)
        if bhi <= blo:
            continue
        vmk = str(block.get("mk") or "")
        core = str(block.get("core") or "")
        pools = [by_core[core]] if core and core in by_core else list(by_core.values())
        for rows, starts in pools:
            for other in _iter_overlapping(rows, starts, blo, bhi):
                if str(other.get("mk") or "") == vmk:
                    continue
                a = int(other.get("start") or 0)
                b = int(other.get("stop") or a)
                overlap = min(b, bhi) - max(a, blo)
                if overlap <= 0:
                    continue
                pairs.append({
                    "victim": block.get("task"),
                    "victim_mk": vmk,
                    "preemptor": other.get("task"),
                    "preemptor_mk": str(other.get("mk") or ""),
                    "core": core or other.get("core") or "",
                    "start": max(a, blo),
                    "stop": min(b, bhi),
                    "duration": overlap,
                    "jump_ns": max(a, blo),
                    "section": "preempt_matrix",
                    "kind": "preempt",
                })
    return pairs


def preemption_story(
    pairs: Sequence[dict],
    victim_mk: str,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> str:
    """Time-ordered 'Victim → B → ISR → resumed' chain for one victim."""
    vmk = str(victim_mk or "")
    sel = []
    for p in pairs or []:
        if not isinstance(p, dict) or str(p.get("victim_mk") or "") != vmk:
            continue
        a = int(p.get("start") or 0)
        b = int(p.get("stop") or a)
        if lo is not None and hi is not None and (b <= lo or a >= hi):
            continue
        sel.append(p)
    sel.sort(key=lambda p: (int(p.get("start") or 0), -int(p.get("duration") or 0)))
    names: List[str] = []
    for p in sel:
        name = str(p.get("preemptor") or p.get("preemptor_mk") or "")
        if name and (not names or names[-1] != name):
            names.append(name)
        if len(names) >= 6:
            break
    victim = str((sel[0].get("victim") if sel else "") or vmk)
    if not names:
        return f"{victim} → resumed" if victim else ""
    return f"{victim} → " + " → ".join(names) + " → resumed"


def preemptor_ranking(pairs: Sequence[dict], limit: int = 16) -> List[dict]:
    by_v: Dict[str, dict] = {}
    for p in pairs or []:
        vmk = str(p.get("victim_mk") or "")
        pmk = str(p.get("preemptor_mk") or "")
        if not vmk or not pmk:
            continue
        rec = by_v.setdefault(vmk, {
            "task": p.get("victim"), "mk": vmk, "count": 0, "total_ns": 0,
            "max_ns": 0, "preemptors": {}, "worst": p, "section": "preempt_matrix",
        })
        rec["count"] += 1
        dur = int(p.get("duration") or 0)
        rec["total_ns"] += dur
        if dur > rec["max_ns"]:
            rec["max_ns"] = dur
            rec["worst"] = p
        pr = rec["preemptors"].setdefault(pmk, {
            "task": p.get("preemptor"), "mk": pmk, "count": 0, "total_ns": 0,
        })
        pr["count"] += 1
        pr["total_ns"] += dur
    rows = list(by_v.values())
    for rec in rows:
        tops = sorted(
            rec["preemptors"].values(),
            key=lambda r: (-int(r.get("count") or 0), -int(r.get("total_ns") or 0)),
        )[:4]
        rec["top"] = tops
        rec["top_label"] = ", ".join(
            f"{t.get('task')} ({t.get('count')})" for t in tops)
        rec["story"] = preemption_story(pairs, str(rec.get("mk") or ""))
    rows.sort(key=lambda r: (-int(r.get("total_ns") or 0), str(r.get("task") or "")))
    return rows[: max(1, min(40, limit))]


def preemption_matrix(pairs: Sequence[dict], limit: int = 12) -> dict:
    totals: Dict[Tuple[str, str], dict] = {}
    names: Dict[str, str] = {}
    invol: Dict[str, int] = {}
    for p in pairs or []:
        vk = str(p.get("victim_mk") or "")
        pk = str(p.get("preemptor_mk") or "")
        if not vk or not pk:
            continue
        rec = totals.setdefault((vk, pk), {"count": 0, "ns": 0, "worst": p})
        rec["count"] += 1
        rec["ns"] += int(p.get("duration") or 0)
        if int(p.get("duration") or 0) > int(rec["worst"].get("duration") or 0):
            rec["worst"] = p
        names[vk] = str(p.get("victim") or vk)
        names[pk] = str(p.get("preemptor") or pk)
        invol[vk] = invol.get(vk, 0) + int(p.get("duration") or 0)
        invol[pk] = invol.get(pk, 0) + int(p.get("duration") or 0)
    lim = max(2, min(16, int(limit or 12)))
    tasks = sorted(invol, key=lambda k: (-invol[k], names.get(k, k)))[:lim]
    task_set = set(tasks)
    cells = {}
    for (vk, pk), rec in totals.items():
        if vk not in task_set or pk not in task_set:
            continue
        worst = rec["worst"]
        cells[f"{vk}|{pk}"] = {
            "count": rec["count"],
            "ns": rec["ns"],
            "start": int(worst.get("start") or 0),
            "jump_ns": int(worst.get("jump_ns") or worst.get("start") or 0),
            "victim": names.get(vk, vk),
            "preemptor": names.get(pk, pk),
            "section": "preempt_matrix",
        }
    return {
        "tasks": [{"mk": mk, "task": names.get(mk, mk)} for mk in tasks],
        "cells": cells,
    }


def mutex_blocking_table(waits: Sequence[dict], limit: int = 24) -> List[dict]:
    by_key: Dict[Tuple[str, str], dict] = {}
    for w in waits or []:
        if not isinstance(w, dict):
            continue
        wk = str(w.get("waiter_mk") or "")
        obj = str(w.get("object") or "")
        if not wk or not obj:
            continue
        rec = by_key.setdefault((wk, obj), {
            "task": w.get("waiter"), "mk": wk, "object": obj,
            "owner": w.get("owner"), "count": 0, "total_ns": 0, "max_ns": 0,
            "worst": w, "section": "mutex_block",
        })
        dur = int(w.get("duration") or 0)
        rec["count"] += 1
        rec["total_ns"] += dur
        if dur > rec["max_ns"]:
            rec["max_ns"] = dur
            rec["worst"] = w
            rec["owner"] = w.get("owner")
    rows = list(by_key.values())
    rows.sort(key=lambda r: (-int(r.get("total_ns") or 0), str(r.get("task") or "")))
    return rows[: max(1, min(60, limit))]


def core_util_over_time(
    events: Sequence[dict],
    cores: Optional[Sequence[str]] = None,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
    bins: int = CORE_TIME_BINS,
) -> dict:
    execs = [e for e in events or [] if isinstance(e, dict) and e.get("kind") == "exec"]
    if not execs:
        return {"cores": list(cores or []), "bins": [], "bin_ns": 0, "lo": 0, "hi": 0}
    t0 = int(lo if lo is not None else min(int(e.get("start") or 0) for e in execs))
    t1 = int(hi if hi is not None else max(int(e.get("stop") or 0) for e in execs))
    if t1 <= t0:
        t1 = t0 + 1
    n = max(4, min(32, int(bins or CORE_TIME_BINS)))
    width = max(1, (t1 - t0) / n)
    core_list = [str(c) for c in (cores or []) if c]
    busy: Dict[str, List[float]] = {}
    for ev in execs:
        core = str(ev.get("core") or "")
        if not core:
            continue
        if core not in core_list:
            core_list.append(core)
        busy.setdefault(core, [0.0] * n)
        a = int(ev.get("start") or 0)
        b = int(ev.get("stop") or a)
        if b <= t0 or a >= t1:
            continue
        a = max(a, t0)
        b = min(b, t1)
        i0 = min(n - 1, max(0, int((a - t0) / width)))
        i1 = min(n - 1, max(0, int((b - 1 - t0) / width)))
        for i in range(i0, i1 + 1):
            blo = t0 + i * width
            bhi = t0 + (i + 1) * width
            busy[core][i] += max(0.0, min(b, bhi) - max(a, blo))
    rows = []
    for i in range(n):
        start = int(t0 + i * width)
        stop = int(t0 + (i + 1) * width)
        cells = {}
        peak = 0.0
        peak_core = ""
        for c in core_list:
            ns = (busy.get(c) or [0.0] * n)[i]
            pct = 100.0 * ns / width
            cells[c] = {"ns": int(ns), "pct": round(pct, 1)}
            if pct > peak:
                peak = pct
                peak_core = c
        rows.append({
            "index": i, "start": start, "stop": stop, "jump_ns": start,
            "cells": cells, "peak_pct": round(peak, 1), "peak_core": peak_core,
            "section": "core_time",
        })
    return {
        "cores": core_list, "bins": rows, "bin_ns": int(width),
        "lo": t0, "hi": t1, "section": "core_time",
    }


def core_busy_anomalies(events: Sequence[dict], bins: int = CORE_TIME_BINS) -> List[dict]:
    grid = core_util_over_time(events, bins=bins)
    out: List[dict] = []
    for row in grid.get("bins") or []:
        if float(row.get("peak_pct") or 0) < 90.0:
            continue
        out.append({
            "kind": "cpu",
            "task": row.get("peak_core") or "CPU",
            "mk": row.get("peak_core") or "",
            "start": row.get("start"),
            "stop": row.get("stop"),
            "duration": int(row.get("stop") or 0) - int(row.get("start") or 0),
            "jump_ns": row.get("jump_ns"),
            "core": row.get("peak_core") or "",
            "section": "cores",
            "reason": f"CPU {row.get('peak_core')} utilization spike {row.get('peak_pct')}%",
        })
    return out


def idle_gap_anomalies(events: Sequence[dict]) -> List[dict]:
    by_core: Dict[str, List[dict]] = {}
    for ev in events or []:
        if not isinstance(ev, dict) or ev.get("kind") != "exec":
            continue
        core = str(ev.get("core") or "")
        if core:
            by_core.setdefault(core, []).append(ev)
    out: List[dict] = []
    for core, group in by_core.items():
        group = sorted(group, key=lambda e: float(e.get("start") or 0))
        gaps = []
        for i in range(1, len(group)):
            gap = int(group[i].get("start") or 0) - int(group[i - 1].get("stop") or 0)
            if gap > 0:
                gaps.append((gap, int(group[i - 1].get("stop") or 0), int(group[i].get("start") or 0)))
        if len(gaps) < 4:
            continue
        vals = [g[0] for g in gaps]
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        sigma = math.sqrt(var)
        thresh = mean + 3.0 * sigma if sigma > 0 else max(vals)
        for gap, start, stop in gaps:
            if gap > thresh and gap >= mean:
                out.append({
                    "kind": "idle",
                    "task": core,
                    "mk": core,
                    "start": start,
                    "stop": stop,
                    "duration": gap,
                    "jump_ns": start,
                    "core": core,
                    "section": "cores",
                    "reason": f"unusual idle on {core}",
                })
    return out


_SPARK_BARS = "▁▂▃▄▅▆▇█"
DISTRIBUTION_KINDS = (
    "exec", "block", "inter", "response", "dispatch", "wakeup", "preempt",
)


def sparkline(values: Sequence[int], width: int = 16) -> str:
    """Compact unicode bars for a chronological sample series."""
    vals = [int(v) for v in values or [] if int(v or 0) >= 0]
    if not vals:
        return ""
    width = max(4, min(24, int(width or 16)))
    if len(vals) > width:
        step = len(vals) / width
        buckets: List[int] = []
        for i in range(width):
            lo = int(i * step)
            hi = max(lo + 1, int((i + 1) * step))
            chunk = vals[lo:hi]
            buckets.append(int(sum(chunk) / len(chunk)) if chunk else 0)
        vals = buckets
    lo_v, hi_v = min(vals), max(vals)
    span = hi_v - lo_v
    if span <= 0:
        return _SPARK_BARS[0] * len(vals)
    return "".join(
        _SPARK_BARS[min(7, int((v - lo_v) * 7 / span))] for v in vals
    )


def distribution_metric_samples(
    events: Sequence[dict],
    kind: str,
    mk: str,
    dispatch_by_mk: Optional[dict] = None,
) -> List[int]:
    """Nanosecond samples for Distribution Explorer (one task × metric)."""
    kind = str(kind or "exec")
    mk = str(mk or "")
    if not mk:
        return []
    if kind == "dispatch":
        raw = (dispatch_by_mk or {}).get(mk) or []
        return [int(v) for v in raw if int(v or 0) > 0]
    if kind in ("response", "wakeup"):
        out: List[int] = []
        for ev in analyze_response_times(events).get("events") or []:
            if str(ev.get("mk") or ev.get("task") or "") != mk:
                continue
            dur = int(ev.get("wait_ns") if kind == "wakeup" else ev.get("duration") or 0)
            if dur > 0:
                out.append(dur)
        return out
    if kind == "preempt":
        return [
            int(p.get("duration") or 0)
            for p in preemption_pairs(events)
            if str(p.get("victim_mk") or p.get("mk") or "") == mk
            and int(p.get("duration") or 0) > 0
        ]
    return [
        int(e.get("duration") or 0)
        for e in events or []
        if isinstance(e, dict)
        and str(e.get("kind") or "") == kind
        and str(e.get("mk") or e.get("task") or "") == mk
        and int(e.get("duration") or 0) > 0
    ]


def distribution_explorer(
    events: Sequence[dict],
    kind: str,
    mk: str,
    dispatch_by_mk: Optional[dict] = None,
) -> Optional[dict]:
    """Summary + sparkline for one Distribution Explorer selection."""
    samples = distribution_metric_samples(events, kind, mk, dispatch_by_mk)
    stats = _duration_stats(samples)
    if not stats:
        return None
    plot_kind = {
        "wakeup": "block",
        "preempt": "preempt",
    }.get(str(kind or ""), str(kind or "exec"))
    row = dict(stats)
    row.update({
        "kind": str(kind or "exec"),
        "mk": mk,
        "spark": sparkline(samples),
        "plot_kind": plot_kind,
        "section": "distrib",
        "n_samples": len(samples),
    })
    return row


def unified_jitter(
    events: Sequence[dict],
    dispatch_by_mk: Optional[dict] = None,
) -> List[dict]:
    by_mk: Dict[str, dict] = {}
    resp = analyze_response_times(events).get("events") or []

    def _ensure(mk: str, task: str) -> dict:
        return by_mk.setdefault(mk, {
            "task": task or mk, "mk": mk,
            "exec": [], "block": [], "inter": [], "response": [],
            "dispatch": [], "wakeup": [],
            "section": "jitter",
        })

    for ev in list(events or []) + resp:
        if not isinstance(ev, dict):
            continue
        mk = str(ev.get("mk") or ev.get("task") or "")
        kind = str(ev.get("kind") or "")
        if not mk or kind not in ("exec", "block", "inter", "response"):
            continue
        rec = _ensure(mk, str(ev.get("task") or mk))
        dur = int(ev.get("duration") or 0)
        if dur > 0:
            rec[kind].append(dur)
        if kind == "response":
            wait = int(ev.get("wait_ns") or 0)
            if wait > 0:
                rec["wakeup"].append(wait)
    for mk, samples in (dispatch_by_mk or {}).items():
        rec = _ensure(str(mk), str(mk))
        rec["dispatch"].extend(int(s) for s in samples or [] if int(s or 0) > 0)
    rows: List[dict] = []
    keys = ("exec", "block", "inter", "response", "dispatch", "wakeup")
    for rec in by_mk.values():
        row = {"task": rec["task"], "mk": rec["mk"], "section": "jitter"}
        empty = True
        for key in keys:
            stats = _duration_stats(rec[key])
            row[f"{key}_jitter_ns"] = int(stats["jitter_ns"]) if stats else 0
            row[f"{key}_cv"] = float(stats["cv"]) if stats else 0.0
            if stats:
                empty = False
        if empty:
            continue
        rows.append(row)
    rows.sort(key=lambda r: (
        -max(int(r.get("response_jitter_ns") or 0), int(r.get("exec_jitter_ns") or 0),
             int(r.get("dispatch_jitter_ns") or 0)),
        str(r.get("task") or ""),
    ))
    return rows


def recurring_patterns(anomalies: Sequence[dict], min_count: int = 2) -> List[dict]:
    by_key: Dict[Tuple[str, str], dict] = {}
    for ev in anomalies or []:
        if not isinstance(ev, dict):
            continue
        task = str(ev.get("task") or ev.get("mk") or "")
        kind = str(ev.get("kind") or "")
        if not task or not kind:
            continue
        rec = by_key.setdefault((task, kind), {
            "task": task, "mk": ev.get("mk") or task, "kind": kind,
            "count": 0, "worst": ev, "section": "patterns",
        })
        rec["count"] += 1
        if int(ev.get("duration") or 0) > int(rec["worst"].get("duration") or 0):
            rec["worst"] = ev
    rows = [r for r in by_key.values() if int(r.get("count") or 0) >= min_count]
    for rec in rows:
        worst = rec["worst"]
        rec["start"] = worst.get("start")
        rec["stop"] = worst.get("stop")
        rec["jump_ns"] = worst.get("jump_ns") or worst.get("start")
        rec["duration"] = worst.get("duration")
        rec["reason"] = (
            f"{rec['count']}× {KIND_LABEL.get(rec['kind'], rec['kind'])} "
            f"for {rec['task']}"
        )
    rows.sort(key=lambda r: (-int(r.get("count") or 0), -int(r.get("duration") or 0)))
    return rows


def top_blocking_contributors(
    events: Sequence[dict],
    mutex_waits: Optional[Sequence[dict]] = None,
    limit: int = 12,
) -> List[dict]:
    """Rank tasks by mutex wait, preemption overlap, and leftover idle gap."""
    pairs = preemption_pairs(events)
    preempt: Dict[str, dict] = {}
    for p in pairs:
        mk = str(p.get("victim_mk") or "")
        if not mk:
            continue
        rec = preempt.setdefault(mk, {
            "task": p.get("victim") or mk, "ns": 0, "worst": p,
        })
        dur = int(p.get("duration") or 0)
        rec["ns"] += dur
        if dur > int(rec["worst"].get("duration") or 0):
            rec["worst"] = p
    mutex: Dict[str, dict] = {}
    for w in mutex_waits or []:
        if not isinstance(w, dict):
            continue
        mk = str(w.get("waiter_mk") or w.get("mk") or "")
        if not mk:
            continue
        rec = mutex.setdefault(mk, {
            "task": w.get("waiter") or w.get("task") or mk, "ns": 0, "worst": w,
        })
        dur = int(w.get("duration") or 0)
        rec["ns"] += dur
        if dur > int(rec["worst"].get("duration") or 0):
            rec["worst"] = w
    block: Dict[str, dict] = {}
    for ev in events or []:
        if not isinstance(ev, dict) or ev.get("kind") != "block":
            continue
        mk = str(ev.get("mk") or "")
        if not mk:
            continue
        rec = block.setdefault(mk, {
            "task": ev.get("task") or mk, "ns": 0, "worst": ev,
        })
        dur = int(ev.get("duration") or 0)
        rec["ns"] += dur
        if dur > int(rec["worst"].get("duration") or 0):
            rec["worst"] = ev
    keys = set(preempt) | set(mutex) | set(block)
    rows: List[dict] = []
    for mk in keys:
        mutex_ns = int((mutex.get(mk) or {}).get("ns") or 0)
        preempt_ns = int((preempt.get(mk) or {}).get("ns") or 0)
        block_ns = int((block.get(mk) or {}).get("ns") or 0)
        idle_ns = max(0, block_ns - preempt_ns)
        total = mutex_ns + preempt_ns + idle_ns
        if total <= 0:
            continue
        worst = None
        for src in (mutex.get(mk), preempt.get(mk), block.get(mk)):
            if src is None:
                continue
            cand = src.get("worst")
            if cand is None:
                continue
            if worst is None or int(cand.get("duration") or 0) > int(worst.get("duration") or 0):
                worst = cand
        task = (
            (mutex.get(mk) or {}).get("task")
            or (preempt.get(mk) or {}).get("task")
            or (block.get(mk) or {}).get("task")
            or mk
        )
        rows.append({
            "task": task,
            "mk": mk,
            "mutex_ns": mutex_ns,
            "preempt_ns": preempt_ns,
            "idle_ns": idle_ns,
            "total_ns": total,
            "worst": worst or {},
            "section": "mutex_block",
            "reason": (
                f"mutex {mutex_ns} · preempt {preempt_ns} · idle {idle_ns}"
            ),
        })
    rows.sort(key=lambda r: (-int(r.get("total_ns") or 0), str(r.get("task") or "")))
    return rows[: max(1, min(40, int(limit or 12)))]


def recurring_patterns_across(
    anomalies_a: Sequence[dict],
    anomalies_b: Sequence[dict],
    min_count: int = 1,
) -> List[dict]:
    """Anomaly kinds that repeat for the same task in both traces."""

    def _index(anoms: Sequence[dict]) -> Dict[Tuple[str, str], dict]:
        by_key: Dict[Tuple[str, str], dict] = {}
        for ev in anoms or []:
            if not isinstance(ev, dict):
                continue
            task = str(ev.get("task") or ev.get("mk") or "")
            kind = str(ev.get("kind") or "")
            if not task or not kind:
                continue
            rec = by_key.setdefault((task, kind), {"count": 0, "worst": ev})
            rec["count"] += 1
            if int(ev.get("duration") or 0) > int(rec["worst"].get("duration") or 0):
                rec["worst"] = ev
        return by_key

    need = max(1, int(min_count or 1))
    a = _index(anomalies_a)
    b = _index(anomalies_b)
    rows: List[dict] = []
    for key in set(a) & set(b):
        if a[key]["count"] < need or b[key]["count"] < need:
            continue
        task, kind = key
        wa, wb = a[key]["worst"], b[key]["worst"]
        worst = wa if int(wa.get("duration") or 0) >= int(wb.get("duration") or 0) else wb
        rows.append({
            "task": task,
            "mk": worst.get("mk") or task,
            "kind": kind,
            "count_a": a[key]["count"],
            "count_b": b[key]["count"],
            "worst": worst,
            "start": worst.get("start"),
            "stop": worst.get("stop"),
            "jump_ns": worst.get("jump_ns") or worst.get("start"),
            "duration": worst.get("duration"),
            "section": "patterns",
            "reason": (
                f"{a[key]['count']}× / {b[key]['count']}× "
                f"{KIND_LABEL.get(kind, kind)} for {task}"
            ),
        })
    rows.sort(key=lambda r: (
        -(int(r.get("count_a") or 0) + int(r.get("count_b") or 0)),
        -int(r.get("duration") or 0),
    ))
    return rows


def compare_analysis_tables(
    trace_a: Any,
    trace_b: Any,
    lo_a: Optional[int] = None,
    hi_a: Optional[int] = None,
    lo_b: Optional[int] = None,
    hi_b: Optional[int] = None,
    deadlines: Optional[dict] = None,
) -> dict:
    """Response P99 / mutex / deadline / shared-pattern tables for Compare."""
    evs_a = harvest_ux_events(trace_a, lo_a, hi_a)
    evs_b = harvest_ux_events(trace_b, lo_b, hi_b)
    waits_a = pair_mutex_waits(harvest_mutex_holds(trace_a, lo_a, hi_a))
    waits_b = pair_mutex_waits(harvest_mutex_holds(trace_b, lo_b, hi_b))
    ra = analyze_response_times(evs_a).get("rows") or []
    rb = analyze_response_times(evs_b).get("rows") or []
    by_a = {str(r.get("task") or r.get("mk")): r for r in ra}
    by_b = {str(r.get("task") or r.get("mk")): r for r in rb}
    names = sorted(set(by_a) | set(by_b))
    response_rows = []
    worst_p99_a = worst_p99_b = 0
    for name in names:
        pa = int((by_a.get(name) or {}).get("p99_ns") or 0)
        pb = int((by_b.get(name) or {}).get("p99_ns") or 0)
        worst_p99_a = max(worst_p99_a, pa)
        worst_p99_b = max(worst_p99_b, pb)
        if pa or pb:
            response_rows.append({
                "name": name, "p99_a": pa, "p99_b": pb, "delta_ns": pa - pb,
            })
    response_rows.sort(key=lambda r: -abs(int(r.get("delta_ns") or 0)))
    ma = mutex_blocking_table(waits_a)
    mb = mutex_blocking_table(waits_b)
    mutex_a = {str(r.get("task") or r.get("mk")): r for r in ma}
    mutex_b = {str(r.get("task") or r.get("mk")): r for r in mb}
    mutex_rows = []
    mutex_ns_a = mutex_ns_b = 0
    for name in sorted(set(mutex_a) | set(mutex_b)):
        ta = int((mutex_a.get(name) or {}).get("total_ns") or 0)
        tb = int((mutex_b.get(name) or {}).get("total_ns") or 0)
        mutex_ns_a += ta
        mutex_ns_b += tb
        mutex_rows.append({
            "name": name, "total_a": ta, "total_b": tb, "delta_ns": ta - tb,
        })
    mutex_rows.sort(key=lambda r: -abs(int(r.get("delta_ns") or 0)))
    dl_map = {
        str(k): int(v) for k, v in (deadlines or {}).items() if int(v or 0) > 0
    }
    misses_a = misses_b = 0
    if dl_map:
        for ev in analyze_response_times(evs_a).get("events") or []:
            lim = dl_map.get(str(ev.get("mk") or "")) or dl_map.get(str(ev.get("task") or ""))
            if lim and int(ev.get("duration") or 0) > lim:
                misses_a += 1
        for ev in analyze_response_times(evs_b).get("events") or []:
            lim = dl_map.get(str(ev.get("mk") or "")) or dl_map.get(str(ev.get("task") or ""))
            if lim and int(ev.get("duration") or 0) > lim:
                misses_b += 1
    shared = recurring_patterns_across(
        detect_timeline_anomalies(evs_a, 12, waits_a, dl_map),
        detect_timeline_anomalies(evs_b, 12, waits_b, dl_map),
    )
    return {
        "response": response_rows[:15],
        "mutex_block": mutex_rows[:15],
        "metrics": {
            "response_p99_a": worst_p99_a,
            "response_p99_b": worst_p99_b,
            "mutex_ns_a": mutex_ns_a,
            "mutex_ns_b": mutex_ns_b,
            "deadline_misses_a": misses_a,
            "deadline_misses_b": misses_b,
        },
        "shared_patterns": shared[:6],
    }


def compare_why(strip: Optional[dict]) -> str:
    """Deterministic one-line explanation of compare regressions."""
    regs = list((strip or {}).get("regressions") or [])
    shared = list((strip or {}).get("shared_patterns") or [])
    if not regs and not shared:
        return "No positive regressions in the compared tables."
    labels = [str(r.get("label") or "") for r in regs]
    blob = " ".join(labels).lower()
    if regs:
        parts = [f"{r.get('label')} {r.get('delta')}" for r in regs[:4]]
        why = "Largest regressions: " + "; ".join(parts) + "."
    else:
        why = "No positive regressions in the compared tables."
    if "deadline" in blob:
        why += " Open Deadlines / CPU budget and Timeline Anomalies."
    elif "response" in blob and ("mutex" in blob or "block" in blob):
        why += " Response P99 moved with blocking — check Mutex Blocking and Critical Path."
    elif "response" in blob:
        why += " Open Response Time and click p99."
    elif "mutex" in blob:
        why += " Open Mutex Blocking and Waiter × Owner."
    elif "block" in blob and ("exec" in blob or "max" in blob):
        why += " Blocking and execution tails moved together — check Waiter × Owner and Worst Events."
    elif "migrat" in blob:
        why += " Open Task × Core and Timeline Anomalies for migration bursts."
    elif "block" in blob:
        why += " Open Waiter × Owner and Blocking p95/p99."
    else:
        why += " Open the matching Statistics table and click p95/p99."
    shared = list((strip or {}).get("shared_patterns") or [])
    if shared:
        top = shared[0]
        why += (
            f" Shared pattern: {top.get('reason') or top.get('kind') or 'anomaly'}."
        )
    return why
