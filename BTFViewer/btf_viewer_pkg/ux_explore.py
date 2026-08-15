"""Deterministic timeline explore helpers (anomalies, worst events, scope).

Host harvest walks BTF slices; ranking and scope stay shared with
``web/src/utils/uxExplore.js``.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

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
}

MUTEX_HANDOFF_SLACK_NS = 1_000_000
PERIOD_MISS_RATIO = 1.5
PERIOD_EXTRA_RATIO = 0.5
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
}

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
    """Top-N longest exec / block / inter episodes (deduped)."""
    lim = max(1, min(40, int(limit or 12)))
    seen: set = set()
    ranked: List[dict] = []
    rows = [
        e for e in (events or [])
        if isinstance(e, dict) and e.get("kind") in ("exec", "block", "inter")
    ]
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


def detect_timeline_anomalies(events: Sequence[dict], limit: int = 12) -> List[dict]:
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
    return {
        "headline": headline,
        "regressions": top_compare_regressions(cands, limit),
    }


def harvest_ux_events(trace: Any, lo: Optional[int] = None, hi: Optional[int] = None) -> List[dict]:
    """Collect exec / block / inter / migration episodes from a loaded trace."""
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
    rows.sort(key=lambda s: int(s.start))
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
            "min_ev": _ev_for(min_g),
            "max_ev": _ev_for(max_g),
            "p50_ev": _ev_for(int(expected)),
            "p95_ev": _ev_for(p95),
            "p99_ev": _ev_for(p99),
            "worst_ev": dict(worst),
            "miss_ev": dict(miss_ev) if miss_ev else dict(worst),
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
