"""BTF Viewer — Perfetto (Chrome Trace JSON) export.

Emits Chrome Trace Event Format JSON that opens in https://ui.perfetto.dev
(and chrome://tracing). Timestamps use the Chrome Trace convention of
microseconds. No protobuf dependency.

Do not edit builds/btf_viewer.py; run make -C BTFViewer bundle.
"""
from __future__ import annotations

from ._imports import *  # noqa: F403,F401
from .parser import (  # noqa: F401
    _is_interval_marker_channel,
    _task_display_name,
    _task_merge_key,
)
from .timeline_util import _to_ns

# Process IDs in the exported trace (stable layout for Perfetto UI).
_PID_CORES = 1
_PID_TASKS = 2
_PID_STI = 3
_PID_INTERVALS = 4


def _trace_us(value: float, time_scale: str) -> float:
    """Convert a native-scale timestamp to Chrome Trace microseconds."""
    return _to_ns(value, time_scale) / 1000.0


def _meta_process(pid: int, name: str) -> dict:
    return {"name": "process_name", "ph": "M", "pid": pid, "args": {"name": name}}


def _meta_thread(pid: int, tid: int, name: str) -> dict:
    return {
        "name": "thread_name", "ph": "M", "pid": pid, "tid": tid,
        "args": {"name": name},
    }


def build_perfetto_chrome_events(trace: "BtfTrace") -> List[dict]:
    """Build Chrome Trace Event list from a parsed *trace*."""
    scale = trace.time_scale or "ns"
    events: List[dict] = []

    # --- Cores / Tasks metadata ----------------------------------------
    events.append(_meta_process(_PID_CORES, "Cores"))
    core_tid: Dict[str, int] = {}
    for i, core in enumerate(trace.core_names or [], start=1):
        core_tid[core] = i
        events.append(_meta_thread(_PID_CORES, i, core))

    events.append(_meta_process(_PID_TASKS, "Tasks"))
    task_tid: Dict[str, int] = {}
    for i, mk in enumerate(trace.tasks or [], start=1):
        raw = trace.task_repr.get(mk, mk)
        label = _task_display_name(raw)
        task_tid[mk] = i
        events.append(_meta_thread(_PID_TASKS, i, label))

    # --- Segments: discover missing tracks + emit run slices (one pass) -
    for seg in trace.segments:
        if seg.core and seg.core not in core_tid:
            tid = len(core_tid) + 1
            core_tid[seg.core] = tid
            events.append(_meta_thread(_PID_CORES, tid, seg.core))

        mk = _task_merge_key(seg.task)
        raw = trace.task_repr.get(mk, seg.task)
        label = _task_display_name(raw)
        if mk not in task_tid:
            tid = len(task_tid) + 1
            task_tid[mk] = tid
            events.append(_meta_thread(_PID_TASKS, tid, label))

        ts = _trace_us(seg.start, scale)
        dur = _trace_us(seg.end - seg.start, scale)
        if dur < 0:
            dur = 0.0
        args = {"core": seg.core, "task": label}
        ctid = core_tid.get(seg.core)
        if ctid is not None:
            events.append({
                "name": label, "cat": "sched", "ph": "X",
                "ts": ts, "dur": dur,
                "pid": _PID_CORES, "tid": ctid, "args": args,
            })
        events.append({
            "name": "run", "cat": "sched", "ph": "X",
            "ts": ts, "dur": dur,
            "pid": _PID_TASKS, "tid": task_tid[mk], "args": args,
        })

    # --- Migrations as instant markers on the task track -----------------
    for mig in getattr(trace, "migrations", None) or []:
        tid = task_tid.get(mig.merge_key)
        if tid is None:
            continue
        events.append({
            "name": "migrate", "cat": "sched", "ph": "i", "s": "t",
            "ts": _trace_us(mig.ns, scale),
            "pid": _PID_TASKS, "tid": tid,
            "args": {
                "from_core": mig.from_core,
                "to_core": mig.to_core,
                "gap_ns": mig.gap_ns,
            },
        })

    # --- STI channels (skip interval_start/stop — those become Intervals) -
    sti_channels = [
        ch for ch in (trace.sti_channels or [])
        if not _is_interval_marker_channel(ch)
    ]
    tick_times = getattr(trace, "tick_sti_times", None) or []
    sti_events = [
        ev for ev in (trace.sti_events or [])
        if not _is_interval_marker_channel(ev.target)
    ]
    if sti_channels or tick_times or sti_events:
        events.append(_meta_process(_PID_STI, "STI"))
    sti_tid: Dict[str, int] = {}
    for i, ch in enumerate(sti_channels, start=1):
        sti_tid[ch] = i
        events.append(_meta_thread(_PID_STI, i, ch))

    for ev in sti_events:
        tid = sti_tid.get(ev.target)
        if tid is None:
            tid = len(sti_tid) + 1
            sti_tid[ev.target] = tid
            events.append(_meta_thread(_PID_STI, tid, ev.target))
        name = ev.note or ev.event or ev.target
        events.append({
            "name": name, "cat": "sti", "ph": "i", "s": "t",
            "ts": _trace_us(ev.time, scale),
            "pid": _PID_STI, "tid": tid,
            "args": {
                "channel": ev.target,
                "event": ev.event,
                "note": ev.note,
                "core": ev.core,
            },
        })

    if tick_times:
        tick_tid = len(sti_tid) + 1
        events.append(_meta_thread(_PID_STI, tick_tid, "TICK"))
        for t in tick_times:
            events.append({
                "name": "TICK", "cat": "sti", "ph": "i", "s": "t",
                "ts": _trace_us(t, scale),
                "pid": _PID_STI, "tid": tick_tid,
            })

    # --- Paired intervals ------------------------------------------------
    intervals = getattr(trace, "interval_instances", None) or []
    if intervals:
        events.append(_meta_process(_PID_INTERVALS, "Intervals"))
        id_tid: Dict[str, int] = {}
        for i, iid in enumerate(getattr(trace, "interval_ids", None) or [], start=1):
            id_tid[iid] = i
            events.append(_meta_thread(_PID_INTERVALS, i, iid))
        for inst in intervals:
            tid = id_tid.get(inst.id)
            if tid is None:
                tid = len(id_tid) + 1
                id_tid[inst.id] = tid
                events.append(_meta_thread(_PID_INTERVALS, tid, inst.id))
            ts = _trace_us(inst.start_ns, scale)
            dur = _trace_us(inst.stop_ns - inst.start_ns, scale)
            if dur < 0:
                dur = 0.0
            events.append({
                "name": inst.id, "cat": "interval", "ph": "X",
                "ts": ts, "dur": dur,
                "pid": _PID_INTERVALS, "tid": tid,
                "args": {
                    "start_core": inst.start_core,
                    "stop_core": inst.stop_core,
                    "task_id": inst.task_id or "",
                },
            })

    return events


def build_perfetto_chrome_trace(trace: "BtfTrace") -> dict:
    """Return a Chrome Trace JSON object for *trace*."""
    meta = dict(trace.meta or {})
    return {
        "traceEvents": build_perfetto_chrome_events(trace),
        "displayTimeUnit": "ns",
        "otherData": {
            "source": "RTOS BTF Viewer",
            "timeScale": trace.time_scale,
            "time_min": trace.time_min,
            "time_max": trace.time_max,
            "btf_meta": meta,
        },
    }


def export_perfetto(trace: "BtfTrace", path: str) -> None:
    """Write a Perfetto-compatible Chrome Trace JSON file to *path*."""
    payload = build_perfetto_chrome_trace(trace)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"), ensure_ascii=False)
