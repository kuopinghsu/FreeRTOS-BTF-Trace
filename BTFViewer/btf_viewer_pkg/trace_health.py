"""Deterministic structural trace-health checks.

Lockstep with ``web/src/utils/traceHealth.js``.

This is distinct from *Trace Health (TICK)* (``trace_quality``/``tickHealth``),
which only measures tick-interval regularity and surfaces BTF metadata flags.
This module verifies that the *parsed event model* is internally consistent
enough to trust the statistics BTFViewer derives from it, and records which
metrics become limited when it is not.

``build_trace_health_result`` is a pure function of the parsed trace: the same
input always produces the same result. No wall-clock time, no randomness, no
network.
"""
from __future__ import annotations

import math
import re
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from .trace_quality import collect_trace_quality_warnings

if TYPE_CHECKING:  # pragma: no cover
    from .parser import BtfTrace

# ---------------------------------------------------------------------------
# Status + check identifiers (stable — persisted in exports and referenced by
# tests, so do not rename without a schema bump).
# ---------------------------------------------------------------------------
STATUS_PASS = "pass"
STATUS_CAUTION = "caution"
STATUS_INSUFFICIENT = "insufficient"

_STATUS_LABELS = {
    STATUS_PASS: "Pass",
    STATUS_CAUTION: "Caution",
    STATUS_INSUFFICIENT: "Insufficient data",
}

CHECK_EMPTY_TRACE = "empty_trace"
CHECK_TIMESTAMP_UNITS = "timestamp_units"
CHECK_TIMESTAMP_SKIPS = "timestamp_skips"
CHECK_CORE_INTERVAL_OVERLAP = "core_interval_overlap"
CHECK_UNKNOWN_CORE = "unknown_core"
CHECK_MISSING_TASK_IDENTITY = "missing_task_identity"
CHECK_UNMATCHED_INTERVALS = "unmatched_intervals"
CHECK_SYNC_PAIRING = "sync_pairing_issues"
CHECK_CAPTURE_TRUNCATION = "capture_truncation"
CHECK_LONG_GAP = "long_data_gap"
CHECK_METRIC_PREREQUISITES = "metric_prerequisites"

TRACE_HEALTH_CHECK_IDS = (
    CHECK_EMPTY_TRACE,
    CHECK_TIMESTAMP_UNITS,
    CHECK_TIMESTAMP_SKIPS,
    CHECK_CORE_INTERVAL_OVERLAP,
    CHECK_UNKNOWN_CORE,
    CHECK_MISSING_TASK_IDENTITY,
    CHECK_UNMATCHED_INTERVALS,
    CHECK_SYNC_PAIRING,
    CHECK_CAPTURE_TRUNCATION,
    CHECK_LONG_GAP,
    CHECK_METRIC_PREREQUISITES,
)

_SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2}

_KNOWN_TIME_SCALES = ("ps", "ns", "us", "µs", "ms", "s")

# A gap in scheduled activity is only reported when it is a large fraction of
# the analysed span — deterministic and unit-independent.
_LONG_GAP_SPAN_FRACTION = 0.20

# Fraction of a core's slices that may overlap before the timeline is treated
# as structurally broken (error) rather than merely suspicious (warning).
_OVERLAP_ERROR_RATIO = 0.02

# Evidence timestamps kept per check (keeps exports compact).
_EVIDENCE_CAP = 4

_VALID_CORE_RE = re.compile(r"^(?:Core_|CPU|C)(\d{1,2})$", re.IGNORECASE)
_PLACEHOLDER_TASK_RE = re.compile(r"^\[[^\]]*\]\s*$")


def trace_health_status_label(status: str) -> str:
    """Human label for a status token."""
    return _STATUS_LABELS.get(str(status or ""), "Unknown")


def _fmt(format_ns: Optional[Callable[[int], Any]], value: int) -> str:
    if callable(format_ns):
        try:
            return str(format_ns(int(value)))
        except Exception:  # pragma: no cover - defensive
            return str(int(value))
    return str(int(value))


def _scoped_segments(trace: Any, lo: Optional[int], hi: Optional[int]) -> list:
    segs = list(getattr(trace, "segments", None) or [])
    if lo is None and hi is None:
        return segs
    lo_v = -math.inf if lo is None else lo
    hi_v = math.inf if hi is None else hi
    return [s for s in segs if s.end > lo_v and s.start < hi_v]


def _scoped_times(times: Any, lo: Optional[int], hi: Optional[int]) -> list:
    seq = list(times or [])
    if lo is None and hi is None:
        return seq
    lo_v = -math.inf if lo is None else lo
    hi_v = math.inf if hi is None else hi
    return [t for t in seq if lo_v <= t <= hi_v]


def _check(
    cid: str,
    severity: str,
    summary: str,
    *,
    affected_range: Optional[Dict[str, int]] = None,
    affected_entities: Optional[List[str]] = None,
    evidence_refs: Optional[List[str]] = None,
    metric_limitations: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "id": cid,
        "severity": severity,
        "summary": summary,
        "affected_range": affected_range,
        "affected_entities": list(affected_entities or []),
        "evidence_refs": list(evidence_refs or []),
        "metric_limitations": list(metric_limitations or []),
    }


# ---------------------------------------------------------------------------
# Individual checks — each returns a check dict or ``None``.
# ---------------------------------------------------------------------------
def _check_empty(segs: list, sti_events: list) -> Optional[dict]:
    if segs or sti_events:
        return None
    return _check(
        CHECK_EMPTY_TRACE, "error",
        "No task slices or STI events in the analysed range.",
        metric_limitations=["All statistics"],
    )


def _check_units(trace: Any) -> Optional[dict]:
    scale = str(getattr(trace, "time_scale", "") or "").strip().lower()
    if not scale or scale in _KNOWN_TIME_SCALES:
        return None
    return _check(
        CHECK_TIMESTAMP_UNITS, "error",
        f"Unrecognised timestamp unit '{scale}'. Tick/cycle-to-time conversion "
        "cannot be verified, so every time-based value is unreliable.",
        metric_limitations=["All time-based statistics"],
    )


def _check_skips(trace: Any) -> Optional[dict]:
    meta = getattr(trace, "meta", None) or {}
    raw = meta.get("_skipped_lines") or meta.get("skippedLines") or 0
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        return None
    return _check(
        CHECK_TIMESTAMP_SKIPS, "warning",
        f"{n:,} trace line(s) had an unparseable timestamp and were dropped "
        "before analysis.",
        metric_limitations=["Event counts", "Timeline coverage"],
    )


def _check_core_overlap(
    trace: Any, segs: list, format_ns: Optional[Callable[[int], Any]]
) -> Optional[dict]:
    by_core: Dict[str, list] = {}
    for s in segs:
        by_core.setdefault(s.core, []).append(s)
    overlaps = 0
    total = 0
    ev: List[str] = []
    cores: List[str] = []
    rng_lo: Optional[int] = None
    rng_hi: Optional[int] = None
    for core, cs in by_core.items():
        cs_sorted = sorted(cs, key=lambda s: (s.start, s.end))
        total += len(cs_sorted)
        prev_end = None
        core_hit = False
        for s in cs_sorted:
            if prev_end is not None and s.start < prev_end:
                overlaps += 1
                core_hit = True
                lo_ov, hi_ov = s.start, min(prev_end, s.end)
                rng_lo = lo_ov if rng_lo is None else min(rng_lo, lo_ov)
                rng_hi = hi_ov if rng_hi is None else max(rng_hi, hi_ov)
                if len(ev) < _EVIDENCE_CAP:
                    ev.append(f"{core} @ {_fmt(format_ns, s.start)}")
            if prev_end is None or s.end > prev_end:
                prev_end = s.end
        if core_hit:
            cores.append(core)
    if not overlaps:
        return None
    ratio = overlaps / max(1, total)
    severity = "error" if ratio > _OVERLAP_ERROR_RATIO else "warning"
    rng = None
    if rng_lo is not None and rng_hi is not None:
        rng = {"start": int(rng_lo), "end": int(rng_hi)}
    return _check(
        CHECK_CORE_INTERVAL_OVERLAP, severity,
        f"{overlaps:,} task slice(s) overlap in time on the same core "
        f"({ratio * 100:.1f}% of slices on {len(cores)} core(s)). Two tasks "
        "cannot run at once on one core, so the reconstructed schedule is "
        "inconsistent here.",
        affected_range=rng,
        affected_entities=sorted(cores),
        evidence_refs=ev,
        metric_limitations=[
            "Core Utilization", "Core Time Breakdown",
            "Preemption Chain Analysis", "Response Time",
        ],
    )


def _check_unknown_cores(trace: Any) -> Optional[dict]:
    bad: List[str] = []
    for name in getattr(trace, "core_names", None) or []:
        m = _VALID_CORE_RE.match(str(name).strip())
        if not m or not (0 <= int(m.group(1)) <= 31):
            bad.append(str(name))
    if not bad:
        return None
    return _check(
        CHECK_UNKNOWN_CORE, "warning",
        "Core identifier(s) outside the valid 0-31 range or in an unexpected "
        f"format: {', '.join(bad[:8])}.",
        affected_entities=bad,
        metric_limitations=["Core Migrations", "Core Affinity", "Task × Core"],
    )


def _check_task_identity(trace: Any) -> Optional[dict]:
    meta = getattr(trace, "meta", None) or {}
    overflow = False
    for key in ("taskTableOverflow", "task_table_overflow"):
        v = meta.get(key)
        if v is True or v == 1 or str(v).strip().lower() in ("1", "true", "yes"):
            overflow = True
    placeholders = 0
    repr_map = getattr(trace, "task_repr", None) or {}
    names = list(repr_map.values()) if repr_map else list(getattr(trace, "tasks", None) or [])
    for name in names:
        text = str(name or "").strip()
        if not text or _PLACEHOLDER_TASK_RE.match(text):
            placeholders += 1
    if not overflow and not placeholders:
        return None
    bits = []
    if overflow:
        bits.append("task-table overflow was flagged during capture")
    if placeholders:
        bits.append(f"{placeholders} task(s) have no readable name")
    summary = "; ".join(bits)
    summary = summary[:1].upper() + summary[1:]
    return _check(
        CHECK_MISSING_TASK_IDENTITY, "warning",
        summary + ". Per-task attribution for those slices is unreliable.",
        metric_limitations=["Top Tasks by CPU", "Task × Core", "Task Health"],
    )


def _check_unmatched_intervals(trace: Any) -> Optional[dict]:
    try:
        n = int(getattr(trace, "interval_unmatched_starts", 0) or 0)
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        return None
    return _check(
        CHECK_UNMATCHED_INTERVALS, "warning",
        f"{n:,} interval_start event(s) never received a matching "
        "interval_stop. Those spans are dropped from interval statistics.",
        metric_limitations=["Interval Analysis", "Period / Jitter"],
    )


def _check_sync_pairing(
    trace: Any, format_ns: Optional[Callable[[int], Any]]
) -> Optional[dict]:
    issues = list(getattr(trace, "sync_issues", None) or [])
    if not issues:
        return None
    ev: List[str] = []
    for i in issues[:_EVIDENCE_CAP]:
        kind = str(i.get("kind") or i.get("detail") or "issue")
        t = i.get("time_ns")
        ev.append(
            f"{kind} @ {_fmt(format_ns, t)}" if t is not None else kind
        )
    return _check(
        CHECK_SYNC_PAIRING, "warning",
        f"{len(issues):,} mutex/semaphore pairing issue(s) (orphan give, "
        "unmatched take, or lock held across a migration).",
        evidence_refs=ev,
        metric_limitations=[
            "Mutex / Semaphore", "Mutex Blocking",
            "Waiter × Owner", "Priority Inheritance",
        ],
    )


def _check_truncation(trace: Any) -> Optional[dict]:
    warnings = collect_trace_quality_warnings(trace)
    if not warnings:
        return None
    return _check(
        CHECK_CAPTURE_TRUNCATION, "warning",
        " ".join(warnings),
        metric_limitations=[
            "Timeline Anomalies", "Worst Events",
            "Response Time", "Execution Time Per Slice",
        ],
    )


def _check_long_gap(
    segs: list,
    lo: Optional[int],
    hi: Optional[int],
    trace: Any,
    format_ns: Optional[Callable[[int], Any]],
) -> Optional[dict]:
    if len(segs) < 2:
        return None
    span_lo = lo if lo is not None else getattr(trace, "time_min", None)
    span_hi = hi if hi is not None else getattr(trace, "time_max", None)
    if span_lo is None or span_hi is None or span_hi <= span_lo:
        return None
    span = span_hi - span_lo
    ordered = sorted(segs, key=lambda s: s.start)
    gap = 0
    gap_lo = gap_hi = 0
    covered = ordered[0].end
    for s in ordered[1:]:
        if s.start > covered:
            g = s.start - covered
            if g > gap:
                gap, gap_lo, gap_hi = g, covered, s.start
        if s.end > covered:
            covered = s.end
    if gap <= span * _LONG_GAP_SPAN_FRACTION:
        return None
    return _check(
        CHECK_LONG_GAP, "info",
        f"No task was scheduled for {_fmt(format_ns, gap)} "
        f"({gap / span * 100:.0f}% of the analysed span). This may be genuine "
        "idle time or a gap in the capture; rates and utilization include it "
        "in the denominator.",
        affected_range={"start": int(gap_lo), "end": int(gap_hi)},
        metric_limitations=["Scheduling Load Over Time", "Core Utilization"],
    )


def _check_prerequisites(
    trace: Any, segs: list, lo: Optional[int], hi: Optional[int]
) -> Optional[dict]:
    channels = {str(c).lower() for c in (getattr(trace, "sti_channels", None) or [])}
    tick_times = _scoped_times(getattr(trace, "tick_sti_times", None), lo, hi)
    cores = {s.core for s in segs} or set(getattr(trace, "core_names", None) or [])
    missing: List[str] = []
    limits: List[str] = []
    if not tick_times:
        missing.append("no TICK events")
        limits += ["Trace Health (TICK)"]
    if not getattr(trace, "has_sync_object_instrumentation", False) and not (
        channels & {"mutex", "sem", "queue"}
    ):
        missing.append("no mutex/semaphore/queue STI events")
        limits += ["Mutex / Semaphore", "Mutex Blocking", "Waiter × Owner"]
    if not (getattr(trace, "interval_ids", None) or "interval_start" in channels):
        missing.append("no interval_start/stop events")
        limits += ["Interval Analysis"]
    if not getattr(trace, "has_priority_instrumentation", False):
        missing.append("no priority (create pri:/set_priority) events")
        limits += ["Priority Inheritance"]
    if len(cores) < 2:
        missing.append("single core in scope")
        limits += ["Core Migrations", "Core Affinity", "Load Balance Score"]
    if not missing:
        return None
    return _check(
        CHECK_METRIC_PREREQUISITES, "info",
        "Some metrics need event types this trace does not contain: "
        + "; ".join(missing) + ".",
        metric_limitations=limits,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def build_trace_health_result(
    trace: Optional["BtfTrace"],
    lo: Optional[int] = None,
    hi: Optional[int] = None,
    *,
    format_ns: Optional[Callable[[int], Any]] = None,
) -> Dict[str, Any]:
    """Return a ``TraceHealthResult`` dict for *trace* over ``[lo, hi]``.

    Shape::

        {
          "status": "pass" | "caution" | "insufficient",
          "checks": [ {id, severity, summary, affected_range,
                       affected_entities, evidence_refs, metric_limitations} ],
          "issue_count": int,            # warning + error checks
          "metric_limitations": [str],   # de-duplicated union
          "scoped": bool,
        }
    """
    if trace is None:
        return {
            "status": STATUS_INSUFFICIENT,
            "checks": [_check(
                CHECK_EMPTY_TRACE, "error", "No trace is loaded.",
                metric_limitations=["All statistics"],
            )],
            "issue_count": 1,
            "metric_limitations": ["All statistics"],
            "scoped": False,
        }

    segs = _scoped_segments(trace, lo, hi)
    sti_events = _scoped_times(
        [e.time for e in (getattr(trace, "sti_events", None) or [])], lo, hi
    )

    checks: List[Dict[str, Any]] = []
    empty = _check_empty(segs, sti_events)
    if empty:
        checks.append(empty)
    else:
        for candidate in (
            _check_units(trace),
            _check_skips(trace),
            _check_core_overlap(trace, segs, format_ns),
            _check_unknown_cores(trace),
            _check_task_identity(trace),
            _check_unmatched_intervals(trace),
            _check_sync_pairing(trace, format_ns),
            _check_truncation(trace),
            _check_long_gap(segs, lo, hi, trace, format_ns),
            _check_prerequisites(trace, segs, lo, hi),
        ):
            if candidate:
                checks.append(candidate)

    checks.sort(key=lambda c: (-_SEVERITY_RANK.get(c["severity"], 0), c["id"]))

    severities = {c["severity"] for c in checks}
    if "error" in severities:
        status = STATUS_INSUFFICIENT
    elif "warning" in severities:
        status = STATUS_CAUTION
    else:
        status = STATUS_PASS

    limitations: List[str] = []
    seen = set()
    for c in checks:
        for m in c.get("metric_limitations") or []:
            if m not in seen:
                seen.add(m)
                limitations.append(m)

    return {
        "status": status,
        "checks": checks,
        "issue_count": sum(
            1 for c in checks if c["severity"] in ("warning", "error")
        ),
        "metric_limitations": limitations,
        "scoped": bool(lo is not None or hi is not None),
    }


def trace_health_summary(result: Optional[Dict[str, Any]]) -> str:
    """One-line summary for KPI tiles / plain-text exports."""
    if not result:
        return "Trace health: unknown"
    status = trace_health_status_label(result.get("status", ""))
    n = int(result.get("issue_count") or 0)
    if not n:
        return f"Trace health: {status}"
    return f"Trace health: {status} · {n} issue(s)"
