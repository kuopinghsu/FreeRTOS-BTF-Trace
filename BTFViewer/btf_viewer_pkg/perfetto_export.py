"""BTF Viewer — Perfetto (Chrome Trace JSON) export.

Emits Chrome Trace Event Format JSON that opens in https://ui.perfetto.dev
(and chrome://tracing). Timestamps use the Chrome Trace convention of
microseconds. No protobuf dependency.

Do not edit builds/btf_viewer.py; run make -C BTFViewer bundle.
"""
from __future__ import annotations

from ._imports import *  # noqa: F403,F401
from .config import _STI_EXPANDABLE_RE, _is_tag_sti_channel
from .parser import (  # noqa: F401
    _SYNC_OBJECT_TARGETS,
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
_PID_TAGS = 5
_PID_SYNC = 6


def _tag_label(channel: str) -> str:
    m = _STI_EXPANDABLE_RE.match(channel or "")
    if not m:
        return channel
    digit = m.group(1)
    return f"Tag {digit}" if digit is not None else "Tag"


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


def _normalize_range(
    lo: Optional[int], hi: Optional[int],
) -> Tuple[Optional[int], Optional[int]]:
    if lo is None and hi is None:
        return None, None
    if (lo is None) ^ (hi is None):
        raise ValueError("lo and hi must both be set or both omitted")
    if hi <= lo:
        raise ValueError("hi must be greater than lo")
    return int(lo), int(hi)


def _in_range(t: int, lo: Optional[int], hi: Optional[int]) -> bool:
    if lo is None:
        return True
    return lo <= t < hi


def _clip_span(
    start: int, end: int, lo: Optional[int], hi: Optional[int],
) -> Optional[Tuple[int, int]]:
    """Return clipped [start, end) overlapping [lo, hi), or None if no overlap."""
    if lo is None:
        if end <= start:
            return None
        return start, end
    if end <= lo or start >= hi:
        return None
    cs = max(start, lo)
    ce = min(end, hi)
    if ce <= cs:
        return None
    return cs, ce


def _skip_sti_channel(channel: str, skip_sync: bool) -> bool:
    if _is_interval_marker_channel(channel):
        return True
    if _is_tag_sti_channel(channel):
        return True
    if skip_sync and channel in _SYNC_OBJECT_TARGETS:
        return True
    return False


def _iter_sync_objects(trace: "BtfTrace"):
    objs = getattr(trace, "sync_objects", None) or {}
    if hasattr(objs, "values"):
        return objs.values()
    return ()


def build_perfetto_chrome_events(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[dict]:
    """Build Chrome Trace Event list from a parsed *trace*.

    Optional *lo* / *hi* are native trace timestamps (same units as the BTF
    ``#timeScale``).  Both must be set together; spans are clipped to the
    window and point events outside ``[lo, hi)`` are dropped.
    """
    lo, hi = _normalize_range(lo, hi)
    scale = trace.time_scale or "ns"
    events: List[dict] = []
    skip_sync_sti = bool(getattr(trace, "has_sync_object_instrumentation", False))

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
        clipped = _clip_span(seg.start, seg.end, lo, hi)
        if clipped is None:
            continue
        c_start, c_end = clipped

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

        ts = _trace_us(c_start, scale)
        dur = _trace_us(c_end - c_start, scale)
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
        if not _in_range(mig.ns, lo, hi):
            continue
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

    # --- STI channels (skip interval / tag / sync-when-paired) -----------
    sti_channels = [
        ch for ch in (trace.sti_channels or [])
        if not _skip_sti_channel(ch, skip_sync_sti)
    ]
    tick_times = [
        t for t in (getattr(trace, "tick_sti_times", None) or [])
        if _in_range(t, lo, hi)
    ]
    sti_events = [
        ev for ev in (trace.sti_events or [])
        if not _skip_sti_channel(ev.target, skip_sync_sti)
        and _in_range(ev.time, lo, hi)
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
    interval_events: List[dict] = []
    id_tid: Dict[str, int] = {}
    for i, iid in enumerate(getattr(trace, "interval_ids", None) or [], start=1):
        id_tid[iid] = i
    for inst in intervals:
        clipped = _clip_span(inst.start_ns, inst.stop_ns, lo, hi)
        if clipped is None:
            continue
        c_start, c_end = clipped
        tid = id_tid.get(inst.id)
        if tid is None:
            tid = len(id_tid) + 1
            id_tid[inst.id] = tid
        ts = _trace_us(c_start, scale)
        dur = _trace_us(c_end - c_start, scale)
        if dur < 0:
            dur = 0.0
        interval_events.append({
            "name": inst.id, "cat": "interval", "ph": "X",
            "ts": ts, "dur": dur,
            "pid": _PID_INTERVALS, "tid": tid,
            "args": {
                "start_core": inst.start_core,
                "stop_core": inst.stop_core,
                "task_id": inst.task_id or "",
            },
        })
    if interval_events:
        events.append(_meta_process(_PID_INTERVALS, "Intervals"))
        for iid, tid in sorted(id_tid.items(), key=lambda kv: kv[1]):
            events.append(_meta_thread(_PID_INTERVALS, tid, iid))
        events.extend(interval_events)

    # --- Tag counter tracks ----------------------------------------------
    tag_channels = list(getattr(trace, "tag_channels", None) or [])
    tag_by_ch = getattr(trace, "tag_samples_by_channel", None) or {}
    tag_events: List[dict] = []
    tag_tid: Dict[str, int] = {}
    for i, ch in enumerate(tag_channels, start=1):
        tag_tid[ch] = i
    for ch in tag_channels:
        samples = tag_by_ch.get(ch) or []
        tid = tag_tid[ch]
        label = _tag_label(ch)
        for sample in samples:
            t = sample.time_ns
            if not _in_range(t, lo, hi):
                continue
            tag_events.append({
                "name": label, "cat": "tag", "ph": "C",
                "ts": _trace_us(t, scale),
                "pid": _PID_TAGS, "tid": tid,
                "args": {
                    "value": float(sample.value),
                    "channel": ch,
                    "core": getattr(sample, "core", "") or "",
                },
            })
    if tag_events:
        events.append(_meta_process(_PID_TAGS, "Tags"))
        for ch, tid in sorted(tag_tid.items(), key=lambda kv: kv[1]):
            events.append(_meta_thread(_PID_TAGS, tid, _tag_label(ch)))
        events.extend(tag_events)

    # --- Sync object hold slices -----------------------------------------
    if skip_sync_sti:
        sync_tid: Dict[str, int] = {}
        sync_events: List[dict] = []
        next_tid = 1
        for obj in _iter_sync_objects(trace):
            kind = obj.get("kind") or "sync"
            ptr = obj.get("ptr") or ""
            key = obj.get("key") or f"{kind}:{ptr}"
            thread_name = f"{kind} {ptr}".strip()
            tid = sync_tid.get(key)
            if tid is None:
                tid = next_tid
                next_tid += 1
                sync_tid[key] = tid

            create_ns = obj.get("create_ns")
            if create_ns is not None and _in_range(create_ns, lo, hi):
                sync_events.append({
                    "name": "create", "cat": "sync", "ph": "i", "s": "t",
                    "ts": _trace_us(create_ns, scale),
                    "pid": _PID_SYNC, "tid": tid,
                    "args": {"kind": kind, "ptr": ptr, "object": thread_name},
                })
            delete_ns = obj.get("delete_ns")
            if delete_ns is not None and _in_range(delete_ns, lo, hi):
                sync_events.append({
                    "name": "delete", "cat": "sync", "ph": "i", "s": "t",
                    "ts": _trace_us(delete_ns, scale),
                    "pid": _PID_SYNC, "tid": tid,
                    "args": {"kind": kind, "ptr": ptr, "object": thread_name},
                })

            for hold in obj.get("holds") or []:
                clipped = _clip_span(hold["start_ns"], hold["stop_ns"], lo, hi)
                if clipped is None:
                    continue
                c_start, c_end = clipped
                holder = hold.get("holder_label") or "hold"
                dur = _trace_us(c_end - c_start, scale)
                if dur < 0:
                    dur = 0.0
                sync_events.append({
                    "name": holder, "cat": "sync", "ph": "X",
                    "ts": _trace_us(c_start, scale), "dur": dur,
                    "pid": _PID_SYNC, "tid": tid,
                    "args": {
                        "kind": kind,
                        "ptr": ptr,
                        "object": thread_name,
                        "take_core": hold.get("take_core") or "",
                        "give_core": hold.get("give_core") or "",
                        "signal": bool(hold.get("signal")),
                    },
                })

        if sync_events:
            events.append(_meta_process(_PID_SYNC, "Sync"))
            name_by_tid: Dict[int, str] = {}
            for obj in _iter_sync_objects(trace):
                key = obj.get("key") or f"{obj.get('kind')}:{obj.get('ptr')}"
                tid = sync_tid.get(key)
                if tid is None:
                    continue
                name_by_tid[tid] = (
                    f"{obj.get('kind') or 'sync'} {obj.get('ptr') or ''}"
                ).strip()
            for tid in sorted(name_by_tid):
                events.append(_meta_thread(_PID_SYNC, tid, name_by_tid[tid]))
            events.extend(sync_events)

    return events


def build_perfetto_chrome_trace(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> dict:
    """Return a Chrome Trace JSON object for *trace*."""
    meta = dict(trace.meta or {})
    other = {
        "source": "RTOS BTF Viewer",
        "timeScale": trace.time_scale,
        "time_min": trace.time_min,
        "time_max": trace.time_max,
        "btf_meta": meta,
    }
    if lo is not None and hi is not None:
        other["export_lo"] = lo
        other["export_hi"] = hi
    return {
        "traceEvents": build_perfetto_chrome_events(trace, lo=lo, hi=hi),
        "displayTimeUnit": "ns",
        "otherData": other,
    }


def export_perfetto(
    trace: "BtfTrace",
    path: str,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> None:
    """Write a Perfetto-compatible Chrome Trace JSON file to *path*."""
    payload = build_perfetto_chrome_trace(trace, lo=lo, hi=hi)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"), ensure_ascii=False)
