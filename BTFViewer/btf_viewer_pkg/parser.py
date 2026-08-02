"""BTF Viewer — parser module (source). Do not edit btf_viewer.py; run make bundle."""
from __future__ import annotations

from ._imports import *  # noqa: F403,F401
from .config import *  # noqa: F403,F401

# ===========================================================================
# BTF Parser
# ===========================================================================
@dataclass
class RawEvent:
    """One raw parsed line from the BTF file before segment reconstruction."""
    time:       int   # absolute timestamp in the file's time_scale units
    source:     str   # emitting entity: 'Core_N' for task T-events
    src_inst:   int   # source instance id (column 2 in the BTF CSV)
    event_type: str   # 'T' for task events, 'STI' for trace items
    target:     str   # receiving entity: task name or STI channel
    tgt_inst:   int   # target instance id (column 5 in the BTF CSV)
    event:      str   # event verb: 'resume', 'preempt', 'trigger', ...
    note:       str   # optional annotation (e.g. 'task_create', mutex name)

# slots=True needs Python 3.10+; project supports 3.8+ so gate it.
_DC_SLOTS = {"slots": True} if sys.version_info >= (3, 10) else {}

@dataclass(**_DC_SLOTS)
class TaskSegment:
    """One contiguous execution slice of a task on a core."""
    task: str
    start: int          # ns
    end: int            # ns
    core: str           # e.g. "Core_0"

@dataclass(**_DC_SLOTS)
class MigrationEvent:
    """Core change between consecutive slices of the same logical task."""
    ns: int
    merge_key: str
    from_core: str
    to_core: str
    gap_ns: int = 0

# Ping-pong / STI-correlation windows in trace time units (~1 ms / 0.5 ms for us-scale).
_MIGRATION_PING_PONG_WINDOW = 1000
_MIGRATION_STI_WINDOW         = 500

@dataclass(**_DC_SLOTS)
class StiEvent:
    """An RTOS software trace item (mutex/semaphore/queue event, etc.)."""
    time: int
    core: str           # source core (e.g. "Core_0")
    target: str         # STI target name (e.g. "mutex_event")
    event: str          # event name (e.g. "trigger")
    note: str           # detail (e.g. "take_mutex")

@dataclass(**_DC_SLOTS)
class IntervalInstance:
    """Paired interval_start / interval_stop span."""
    id: str
    start_ns: int
    stop_ns: int
    start_core: str = ""
    stop_core: str = ""
    task_id: Optional[str] = None

@dataclass
class TagSample:
    """Numeric sample from a tag STI channel (tag0_event … tag7_event)."""
    channel: str
    time_ns: int
    value: float
    core: str = ""

@dataclass
class PriorityEpisode:
    """Task priority boosted above create pri:N base."""
    mk: str
    task_label: str
    base_pri: int
    peak_pri: int
    start_ns: int
    stop_ns: int
    inherited: bool = False
    inversion_suspect: bool = False
    medium_tasks: List[str] = field(default_factory=list)
    pattern: str = ""

@dataclass
class SyncIssueRef:
    """Mutex/sem pairing issue for statistics drill-down."""
    time_ns: int
    core: str = ""
    kind: str = ""
    detail: str = ""
    obj_key: Optional[str] = None
    ptr: str = ""

_MAX_TRACE_FILE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB guard vs. memory exhaustion on a huge/adversarial file

_META_KEY_RE = re.compile(r"^[\w.-]+$")
_CREATE_PRI_RE = re.compile(r"^create\s+pri:(\d+)\s*$", re.IGNORECASE)
_PRIORITY_STI_RE = re.compile(
    r"^(set_priority|priority_inherit|priority_disinherit)\s+(.+?)\s+pri:(\d+)\s*$",
    re.IGNORECASE,
)
_SYNC_OBJECT_NOTE_RE = re.compile(
    r"^(create|take|give|delete|send|recv)(?:\s+(0x[0-9a-f]+))?$", re.IGNORECASE)
_SYNC_OBJECT_TARGETS = frozenset({"mutex", "sem", "queue"})
_POST_CREATE_GIVE_MAX_NS = 1000
_INTERVAL_START_CHANNELS = frozenset({"interval_start"})
_INTERVAL_STOP_CHANNELS  = frozenset({"interval_stop"})
_INTERVAL_COLORS = (
    "#E74C3C", "#2ECC71", "#F39C12", "#3498DB", "#9B59B6",
    "#1ABC9C", "#E91E63", "#F1C40F", "#00BCD4", "#FF5722",
)
_TAG_COLORS = (
    "#E8C84A", "#3498DB", "#2ECC71", "#E74C3C", "#9B59B6",
    "#1ABC9C", "#F39C12", "#E91E63",
)

def _is_interval_marker_channel(channel: str) -> bool:
    return channel in _INTERVAL_START_CHANNELS or channel in _INTERVAL_STOP_CHANNELS

_INTERVAL_TID_RE = re.compile(
    r"^(\S+)\s+tid:((?:0[xX][0-9a-fA-F]+|\d+))\s*$", re.IGNORECASE)

def _parse_interval_note(note: str) -> Tuple[str, Optional[str], str]:
    """Return (interval_id, task_id, pairing_key) from STI note text."""
    raw = (note or "").strip() or "0"
    m = _INTERVAL_TID_RE.match(raw)
    if m:
        iid, tid_token = m.group(1), m.group(2)
        tid_val = _parse_int_token(tid_token)
        tid_display = _format_int_token_display(tid_token, tid_val)
        return iid, tid_display, f"{iid}\0tid:{tid_val}"
    return raw, None, raw

def _interval_pairing_key(ev: "StiEvent") -> str:
    return _parse_interval_note(ev.note)[2]

def _interval_display_id(ev: "StiEvent") -> str:
    iid, tid, _ = _parse_interval_note(ev.note)
    return iid if tid is not None else _

def _interval_color(interval_id: str) -> str:
    try:
        idx = abs(int(interval_id)) % len(_INTERVAL_COLORS)
    except ValueError:
        idx = 0
    return _INTERVAL_COLORS[idx]

def _interval_stripe_colors(color: QColor) -> Tuple[QColor, QColor]:
    """Dark/light pair for interval start/stop tick lines."""
    return color.darker(155), color.lighter(118)

def _interval_bars_for_viewport(
    instances: List["IntervalInstance"],
    time_min: int,
    px_per_ns: float,
    label_width: float,
    vp_ns_lo: int,
    vp_ns_hi: int,
    *,
    instances_nested_culled: bool = False,
) -> list:
    """Build [(scene_x, width_px, start_ns, stop_ns), ...] for visible intervals.

    *instances* must be sorted by start_ns.  Includes spans that began before the
    viewport but still overlap it (long-running nested intervals).
    """
    if not instances:
        return []
    visible: list = []
    for inst in instances:
        if inst.start_ns >= vp_ns_hi:
            break
        if inst.stop_ns <= vp_ns_lo:
            continue
        visible.append(inst)
    if not instances_nested_culled:
        visible = _interval_instances_cull_nested(visible)
    bars: list = []
    for inst in visible:
        x1f = label_width + (inst.start_ns - time_min) * px_per_ns
        x2f = label_width + (inst.stop_ns - time_min) * px_per_ns
        x1 = math.floor(x1f)
        x2 = math.ceil(x2f)
        w = x2 - x1
        if w < _INTERVAL_MIN_PX:
            continue
        bars.append((float(x1), float(w), inst.start_ns, inst.stop_ns))
    return bars

def _interval_instances_cull_nested(instances: list) -> list:
    """Drop instances fully covered by a longer one (time-domain containment).

    Keep this in time space (not pixel space) so zoom changes don't alter which
    parent interval survives culling.  O(n log n) via start-order sweep.
    """
    if len(instances) <= 1:
        return instances
    ordered = sorted(instances, key=lambda inst: (inst.start_ns, -inst.stop_ns))
    kept: list = []
    for inst in ordered:
        while (kept
               and kept[-1].start_ns >= inst.start_ns
               and kept[-1].stop_ns <= inst.stop_ns):
            kept.pop()
        if (kept
                and inst.start_ns >= kept[-1].start_ns
                and inst.stop_ns <= kept[-1].stop_ns):
            continue
        kept.append(inst)
    return kept

def _interval_instances_for_draw(trace: "BtfTrace",
                               interval_id: str) -> Tuple[list, bool]:
    """Return (instances, nested_already_culled) for timeline interval rows."""
    culled = trace.interval_instances_culled_by_id
    if culled and interval_id in culled:
        return culled[interval_id], True
    return trace.interval_instances_by_id.get(interval_id, []), False

def _core_util_pct_for(trace: "BtfTrace", core: str) -> float:
    """Full-trace core utilisation % (IDLE/TICK excluded), with parse-time cache."""
    if trace.core_util_pct and core in trace.core_util_pct:
        return trace.core_util_pct[core]
    segs = trace.core_segs.get(core, [])
    total_ns = max(trace.time_max - trace.time_min, 1)
    active_ns = sum(
        s.end - s.start for s in segs
        if (_tn := _parse_task_name(s.task)[2]) != "TICK"
        and not _is_idle_task_name(_tn))
    return 100.0 * active_ns / total_ns

def _build_interval_marker_index(
    sti_events: List[StiEvent],
) -> Dict[str, dict]:
    """Per-id sorted marker events for O(log n) viewport clipping."""
    by_id: Dict[str, dict] = {}
    for ev in sti_events:
        is_start = ev.target in _INTERVAL_START_CHANNELS
        if not is_start and ev.target not in _INTERVAL_STOP_CHANNELS:
            continue
        iid = _interval_display_id(ev)
        row = by_id.setdefault(iid, {"events": [], "times": []})
        row["events"].append((ev.time, is_start))
    for row in by_id.values():
        row["events"].sort(key=lambda t: (t[0], not t[1]))
        row["times"] = [t[0] for t in row["events"]]
    return by_id

def _interval_marker_ticks_for_viewport(
    trace: "BtfTrace",
    interval_id: str,
    time_min: int,
    px_per_ns: float,
    label_width: float,
    vp_ns_lo: int,
    vp_ns_hi: int,
) -> list:
    """[(scene_x, is_start), ...] for raw interval marker STI events in the viewport."""
    iid = str(interval_id)
    row = trace.interval_marker_by_id.get(iid)
    if not row:
        return []
    times = row["times"]
    events = row["events"]
    lo = bisect_left(times, vp_ns_lo)
    hi = bisect_left(times, vp_ns_hi)
    ticks: list = []
    for i in range(lo, hi):
        t, is_start = events[i]
        x = label_width + (t - time_min) * px_per_ns
        ticks.append((float(x), is_start))
    return ticks

def _interval_bars_for_viewport_vertical(
    instances: List["IntervalInstance"],
    time_min: int,
    px_per_ns: float,
    label_row_h: float,
    vp_ns_lo: int,
    vp_ns_hi: int,
    *,
    instances_nested_culled: bool = False,
) -> list:
    """Build [(scene_y, height_px, start_ns, stop_ns), ...] for vertical interval columns."""
    if not instances:
        return []
    visible: list = []
    for inst in instances:
        if inst.start_ns >= vp_ns_hi:
            break
        if inst.stop_ns <= vp_ns_lo:
            continue
        visible.append(inst)
    if not instances_nested_culled:
        visible = _interval_instances_cull_nested(visible)
    bars: list = []
    for inst in visible:
        y1f = label_row_h + (inst.start_ns - time_min) * px_per_ns
        y2f = label_row_h + (inst.stop_ns - time_min) * px_per_ns
        y1 = math.floor(y1f)
        y2 = math.ceil(y2f)
        h = y2 - y1
        if h < _INTERVAL_MIN_PX:
            continue
        bars.append((float(y1), float(h), inst.start_ns, inst.stop_ns))
    return bars

def _interval_marker_ticks_for_viewport_vertical(
    trace: "BtfTrace",
    interval_id: str,
    time_min: int,
    px_per_ns: float,
    label_row_h: float,
    vp_ns_lo: int,
    vp_ns_hi: int,
) -> list:
    """[(scene_y, is_start), ...] for raw interval marker events in the viewport."""
    iid = str(interval_id)
    row = trace.interval_marker_by_id.get(iid)
    if not row:
        return []
    times = row["times"]
    events = row["events"]
    lo = bisect_left(times, vp_ns_lo)
    hi = bisect_left(times, vp_ns_hi)
    ticks: list = []
    for i in range(lo, hi):
        t, is_start = events[i]
        y = label_row_h + (t - time_min) * px_per_ns
        ticks.append((float(y), is_start))
    return ticks

def _paint_interval_event_ticks(
    painter: QPainter,
    ticks: list,
    y: float,
    h: float,
    color: QColor,
    exp_left: float,
    exp_right: float,
) -> None:
    """Vertical ticks at each interval_start / interval_stop event."""
    if not ticks:
        return
    dark, light = _interval_stripe_colors(color)
    start_pen = QPen(dark)
    start_pen.setWidthF(1.0)
    stop_pen = QPen(light)
    stop_pen.setWidthF(1.0)
    stop_pen.setStyle(Qt.PenStyle.DashLine)
    y2 = y + h
    for x, is_start in ticks:
        if x < exp_left - 1.0 or x > exp_right + 1.0:
            continue
        painter.setPen(start_pen if is_start else stop_pen)
        xi = round(x) + 0.5
        painter.drawLine(QLineF(xi, y, xi, y2))

def _paint_interval_event_ticks_vertical(
    painter: QPainter,
    ticks: list,
    x: float,
    w: float,
    color: QColor,
    exp_top: float,
    exp_bottom: float,
) -> None:
    """Horizontal ticks at each interval_start / interval_stop event (vertical layout)."""
    if not ticks:
        return
    dark, light = _interval_stripe_colors(color)
    start_pen = QPen(dark)
    start_pen.setWidthF(1.0)
    stop_pen = QPen(light)
    stop_pen.setWidthF(1.0)
    stop_pen.setStyle(Qt.PenStyle.DashLine)
    x2 = x + w
    for y, is_start in ticks:
        if y < exp_top - 1.0 or y > exp_bottom + 1.0:
            continue
        painter.setPen(start_pen if is_start else stop_pen)
        yi = round(y) + 0.5
        painter.drawLine(QLineF(x, yi, x2, yi))

def _paint_interval_highlight_lines(
    painter: QPainter,
    times: list,
    y: float,
    h: float,
    time_min: int,
    label_width: float,
    px_per_ns: float,
    exp_left: float,
    exp_right: float,
    dark_ui: bool,
) -> None:
    """Bold vertical lines at drill-down start/stop/mark times."""
    if not times:
        return
    pen = QPen(QColor("#EBEBEB" if dark_ui else "#141414"))
    pen.setWidthF(2.0)
    painter.setPen(pen)
    y2 = y + h
    for t in times:
        x = label_width + (t - time_min) * px_per_ns
        if x < exp_left - 1.0 or x > exp_right + 1.0:
            continue
        xi = round(x) + 0.5
        painter.drawLine(QLineF(xi, y, xi, y2))

def _paint_interval_highlight_lines_vertical(
    painter: QPainter,
    times: list,
    x: float,
    w: float,
    time_min: int,
    label_row_h: float,
    px_per_ns: float,
    exp_top: float,
    exp_bottom: float,
    dark_ui: bool,
) -> None:
    """Bold horizontal lines at drill-down start/stop/mark times (vertical layout)."""
    if not times:
        return
    pen = QPen(QColor("#EBEBEB" if dark_ui else "#141414"))
    pen.setWidthF(2.0)
    painter.setPen(pen)
    x2 = x + w
    for t in times:
        y = label_row_h + (t - time_min) * px_per_ns
        if y < exp_top - 1.0 or y > exp_bottom + 1.0:
            continue
        yi = round(y) + 0.5
        painter.drawLine(QLineF(x, yi, x2, yi))

def _build_interval_data(
    sti_events: List[StiEvent],
) -> Tuple[List["IntervalInstance"], List[str], Dict[str, List["IntervalInstance"]], int]:
    """Pair interval marker STI events into measurable spans."""
    open_stacks: Dict[str, List[StiEvent]] = {}
    instances: List[IntervalInstance] = []
    unmatched = 0

    def _is_start(ev: StiEvent) -> bool:
        return ev.target in _INTERVAL_START_CHANNELS

    ordered = sorted(
        [ev for ev in sti_events if _is_start(ev) or ev.target in _INTERVAL_STOP_CHANNELS],
        key=lambda e: (e.time, 0 if _is_start(e) else 1),
    )
    for ev in ordered:
        pair_key = _interval_pairing_key(ev)
        display_id = _interval_display_id(ev)
        _, task_id, _ = _parse_interval_note(ev.note)
        if _is_start(ev):
            open_stacks.setdefault(pair_key, []).append(ev)
        else:
            stack = open_stacks.get(pair_key)
            if not stack:
                continue
            start_ev = stack.pop()
            if ev.time > start_ev.time:
                instances.append(IntervalInstance(
                    id=display_id,
                    start_ns=start_ev.time,
                    stop_ns=ev.time,
                    start_core=start_ev.core,
                    stop_core=ev.core,
                    task_id=task_id,
                ))
    for stack in open_stacks.values():
        unmatched += len(stack)

    by_id: Dict[str, List[IntervalInstance]] = defaultdict(list)
    for inst in instances:
        by_id[inst.id].append(inst)

    for lst in by_id.values():
        lst.sort(key=lambda inst: (inst.start_ns, inst.stop_ns))

    def _id_sort_key(s: str):
        try:
            return (0, int(s))
        except ValueError:
            return (1, s)

    ids = sorted(by_id.keys(), key=_id_sort_key)
    return instances, ids, dict(by_id), unmatched

def _interval_overlaps_range(inst: "IntervalInstance",
                             lo: Optional[int], hi: Optional[int]) -> bool:
    if lo is None or hi is None:
        return True
    return inst.stop_ns > lo and inst.start_ns < hi

def _interval_stats_rows(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    """Per-interval-id stats: (id, label, count, min, avg, max, p95) as formatted strings."""
    scale = trace.time_scale
    rows = []
    for iid in trace.interval_ids:
        samples = [
            inst.stop_ns - inst.start_ns
            for inst in trace.interval_instances_by_id.get(iid, [])
            if _interval_overlaps_range(inst, lo, hi)
        ]
        if not samples:
            continue
        samples.sort()
        total = sum(samples)
        count = len(samples)
        mn = samples[0]
        mx = samples[-1]
        avg = int(round(total / count))
        p95_idx = min(len(samples) - 1, max(0, int(math.ceil(0.95 * len(samples))) - 1))
        p95 = samples[p95_idx]
        rows.append((
            iid,
            f"Interval {iid}",
            count,
            _format_time(mn, scale),
            _format_time(avg, scale),
            _format_time(mx, scale),
            _format_time(p95, scale),
            mn, avg, mx, p95,
        ))
    return rows

def _interval_plot_points(
    trace: "BtfTrace",
    interval_id: str,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[Tuple[int, int, "IntervalInstance"]]:
    pts: List[Tuple[int, int, IntervalInstance]] = []
    for inst in trace.interval_instances_by_id.get(interval_id, []):
        if not _interval_overlaps_range(inst, lo, hi):
            continue
        dur = inst.stop_ns - inst.start_ns
        pts.append((inst.stop_ns, dur, inst))
    return pts

def _parse_tag_value(note: str) -> Optional[float]:
    raw = (note or "").strip()
    if not raw:
        return None
    try:
        if raw.lower().startswith("0x"):
            return float(int(raw, 16))
        return float(raw)
    except ValueError:
        return None

def _tag_channel_label(channel: str) -> str:
    m = _STI_EXPANDABLE_RE.match(channel or "")
    if not m:
        return channel
    digit = m.group(1)
    return f"Tag {digit}" if digit is not None else "Tag"

def _tag_color(channel: str) -> str:
    m = _STI_EXPANDABLE_RE.match(channel or "")
    idx = _safe_int(m.group(1)) % len(_TAG_COLORS) if m and m.group(1) is not None else 0
    return _TAG_COLORS[idx]

def _format_tag_value(value: float) -> str:
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:g}"

def _build_tag_data(
    sti_events: List["StiEvent"],
) -> Tuple[List[str], Dict[str, List[TagSample]]]:
    by_ch: Dict[str, List[TagSample]] = defaultdict(list)
    for ev in sti_events:
        if not _is_tag_sti_channel(ev.target):
            continue
        val = _parse_tag_value(ev.note)
        if val is None:
            continue
        by_ch[ev.target].append(TagSample(
            channel=ev.target,
            time_ns=ev.time,
            value=val,
            core=ev.core or "",
        ))
    for lst in by_ch.values():
        lst.sort(key=lambda s: (s.time_ns, s.value))
    channels = sorted(by_ch.keys(), key=_sti_channel_sort_key)
    return channels, dict(by_ch)

def _build_sti_derived(
    sti_events: List["StiEvent"],
) -> Tuple[
    List[str],
    Dict[str, List[StiEvent]],
    List[IntervalInstance],
    List[str],
    Dict[str, List[IntervalInstance]],
    int,
    Dict[str, dict],
    List[str],
    Dict[str, List[TagSample]],
]:
    """Single-pass STI post-processing: channels, intervals, markers, tags.

    Replaces separate walks via ``sti_by_target`` / ``_build_interval_data`` /
    ``_build_interval_marker_index`` / ``_build_tag_data``.
    """
    sti_by_target: Dict[str, List[StiEvent]] = defaultdict(list)
    channel_set: set = set()
    # (time, is_start_ord, is_start, ev, display_id, task_id, pair_key)
    markers: list = []
    by_ch: Dict[str, List[TagSample]] = defaultdict(list)
    _is_tag = _is_tag_sti_channel
    _parse_note = _parse_interval_note
    _parse_tag = _parse_tag_value
    _start_ch = _INTERVAL_START_CHANNELS
    _stop_ch = _INTERVAL_STOP_CHANNELS

    for ev in sti_events:
        tgt = ev.target
        sti_by_target[tgt].append(ev)
        if tgt in _start_ch:
            iid, task_id, pair_key = _parse_note(ev.note)
            display_id = iid if task_id is not None else pair_key
            markers.append((ev.time, 0, True, ev, display_id, task_id, pair_key))
        elif tgt in _stop_ch:
            iid, task_id, pair_key = _parse_note(ev.note)
            display_id = iid if task_id is not None else pair_key
            markers.append((ev.time, 1, False, ev, display_id, task_id, pair_key))
        else:
            channel_set.add(tgt)
            if _is_tag(tgt):
                val = _parse_tag(ev.note)
                if val is not None:
                    by_ch[tgt].append(TagSample(
                        channel=tgt,
                        time_ns=ev.time,
                        value=val,
                        core=ev.core or "",
                    ))

    sti_channels = sorted(channel_set, key=_sti_channel_sort_key)

    # --- Interval pairing + marker index from one sorted marker list ------
    markers.sort(key=lambda m: (m[0], m[1]))
    open_stacks: Dict[str, list] = {}
    instances: List[IntervalInstance] = []
    unmatched = 0
    marker_by_id: Dict[str, dict] = {}

    for _t, _ord, is_start, ev, display_id, task_id, pair_key in markers:
        row = marker_by_id.get(display_id)
        if row is None:
            row = {"events": [], "times": []}
            marker_by_id[display_id] = row
        row["events"].append((ev.time, is_start))

        if is_start:
            open_stacks.setdefault(pair_key, []).append(ev)
        else:
            stack = open_stacks.get(pair_key)
            if not stack:
                continue
            start_ev = stack.pop()
            if ev.time > start_ev.time:
                instances.append(IntervalInstance(
                    id=display_id,
                    start_ns=start_ev.time,
                    stop_ns=ev.time,
                    start_core=start_ev.core,
                    stop_core=ev.core,
                    task_id=task_id,
                ))

    for stack in open_stacks.values():
        unmatched += len(stack)

    # Markers were appended in global time order (starts before stops at equal
    # time), so per-id event lists are already sorted — only build times[].
    for row in marker_by_id.values():
        row["times"] = [t[0] for t in row["events"]]

    by_id: Dict[str, List[IntervalInstance]] = defaultdict(list)
    for inst in instances:
        by_id[inst.id].append(inst)
    for lst in by_id.values():
        lst.sort(key=lambda inst: (inst.start_ns, inst.stop_ns))

    def _id_sort_key(s: str):
        try:
            return (0, int(s))
        except ValueError:
            return (1, s)

    interval_ids = sorted(by_id.keys(), key=_id_sort_key)

    for lst in by_ch.values():
        lst.sort(key=lambda s: (s.time_ns, s.value))
    tag_channels = sorted(by_ch.keys(), key=_sti_channel_sort_key)

    return (
        sti_channels,
        dict(sti_by_target),
        instances,
        interval_ids,
        dict(by_id),
        unmatched,
        marker_by_id,
        tag_channels,
        dict(by_ch),
    )

def _tag_overlaps_range(sample: TagSample,
                        lo: Optional[int], hi: Optional[int]) -> bool:
    if lo is None or hi is None:
        return True
    return lo <= sample.time_ns <= hi

def _tag_stats_rows(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    """Per-tag-channel stats: (channel, label, count, min, avg, max, p95, raw…)."""
    rows = []
    for ch in trace.tag_channels:
        samples = [
            s.value
            for s in trace.tag_samples_by_channel.get(ch, [])
            if _tag_overlaps_range(s, lo, hi)
        ]
        if not samples:
            continue
        samples.sort()
        total = sum(samples)
        count = len(samples)
        mn = samples[0]
        mx = samples[-1]
        avg = total / count
        p95_idx = min(count - 1, max(0, int(math.ceil(0.95 * count)) - 1))
        p95 = samples[p95_idx]
        rows.append((
            ch,
            _tag_channel_label(ch),
            count,
            _format_tag_value(mn),
            _format_tag_value(avg),
            _format_tag_value(mx),
            _format_tag_value(p95),
            mn, avg, mx, p95,
        ))
    return rows

_LIFECYCLE_NOTE_RE = re.compile(r"^(create|delete|suspend|resume)\b", re.IGNORECASE)

def _task_lifecycle_rows(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    """Per-task lifecycle summary.

    Creation timestamps come from `trace.task_create_times` — task creation is
    recorded as a dedicated 'T' event, never as an STI 'task' channel note (the
    `task` channel only ever emits delete/suspend/resume/set_priority/…), so a
    row's create_ns would otherwise always be None. Delete/suspend/resume come
    from STI 'task' channel events as before.

    `run_count` is the number of times the task was dispatched onto a core
    (context-switch-in / segment count) — a scheduler-level metric, distinct
    from `suspend_count`/`resume_count` which only reflect explicit
    vTaskSuspend()/vTaskResume() API calls.

    Returns a list of tuples:
        (mk, label, create_ns, delete_ns, suspend_count, resume_count, alive_ns, event_count, run_count)
    Tasks are included if created in scope or with at least one STI lifecycle event.
    """
    def _in_scope(t: int) -> bool:
        return lo is None or hi is None or (lo <= t <= hi)

    by_mk: Dict[str, dict] = {}

    def _row(mk: str, label_hint: str) -> dict:
        if mk not in by_mk:
            # `task_repr` only covers tasks seen in a context-switch segment; a task
            # that is created but never scheduled (e.g. deleted/suspended before its
            # first run) falls back to `task_create_repr` (the raw name recorded at
            # creation time) rather than the internal merge-key string, which would
            # otherwise leak through as a garbled label (e.g. "289SF" instead of
            # "SF[289]").
            raw_repr = trace.task_repr.get(mk) or trace.task_create_repr.get(mk) or label_hint
            by_mk[mk] = {
                "mk": mk,
                "label": _task_display_name(raw_repr),
                "create_ns": None,
                "delete_ns": None,
                "suspend_count": 0,
                "resume_count": 0,
                "event_count": 0,
            }
        return by_mk[mk]

    for mk, create_ns in trace.task_create_times.items():
        if not _in_scope(create_ns):
            continue
        row = _row(mk, mk)
        row["create_ns"] = create_ns
        row["event_count"] += 1

    for ev in trace.sti_events:
        if ev.target != "task":
            continue
        note = (ev.note or "").strip()
        m = _LIFECYCLE_NOTE_RE.match(note)
        if not m:
            continue
        if not _in_scope(ev.time):
            continue
        action = m.group(1).lower()
        task_label = note[m.end():].strip() or note
        mk = _task_merge_key(task_label)
        row = _row(mk, task_label)
        row["event_count"] += 1
        if action == "create" and row["create_ns"] is None:
            row["create_ns"] = ev.time
        elif action == "delete":
            row["delete_ns"] = ev.time
        elif action == "suspend":
            row["suspend_count"] += 1
        elif action == "resume":
            row["resume_count"] += 1

    rows = []
    for d in sorted(by_mk.values(), key=lambda r: r["label"]):
        create_ns = d["create_ns"]
        delete_ns = d["delete_ns"]
        alive_ns = (delete_ns - create_ns) if (create_ns is not None and delete_ns is not None) else None
        mk = d["mk"]
        segs = trace.seg_map_by_merge_key.get(mk, ())
        if lo is not None and hi is not None:
            run_count = sum(1 for s in segs if _seg_overlaps_range(s, lo, hi))
        else:
            run_count = len(segs)
        rows.append((
            mk,
            d["label"],
            create_ns,
            delete_ns,
            d["suspend_count"],
            d["resume_count"],
            alive_ns,
            d["event_count"],
            run_count,
        ))
    return rows


# ---- Core-pair migration summary ------------------------------------------
def _core_pair_rows(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    """Per (from_core, to_core) pair migration summary.
    Returns: [(from_core, to_core, count, bounce_count, avg_gap_ns), ...]"""
    pairs: Dict[tuple, dict] = {}
    for m in trace.migrations:
        if lo is not None and m.ns < lo:
            continue
        if hi is not None and m.ns > hi:
            continue
        key = (m.from_core, m.to_core)
        if key not in pairs:
            pairs[key] = {"count": 0, "bounces": 0, "gap_sum": 0}
        d = pairs[key]
        d["count"] += 1
        if m.ns in trace.lock_bounce_migration_ns:
            d["bounces"] += 1
        d["gap_sum"] += m.gap_ns
    rows = []
    for (fc, tc), d in sorted(pairs.items(), key=lambda x: -x[1]["count"]):
        avg_gap = d["gap_sum"] // max(1, d["count"])
        rows.append((fc, tc, d["count"], d["bounces"], avg_gap))
    return rows


# ---- Per-core time budget breakdown ---------------------------------------
def _core_time_breakdown(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    """Per-core time breakdown into active / idle / tick / gap.
    Returns: [(core, active_ns, idle_ns, tick_ns, gap_ns, span_ns), ...]"""
    eff_lo = lo if lo is not None else trace.time_min
    eff_hi = hi if hi is not None else trace.time_max
    span = max(eff_hi - eff_lo, 1)
    result = []
    for core in trace.core_names:
        active_ns = idle_ns = tick_ns = seg_total = 0
        for seg in trace.core_segs.get(core, []):
            slo = max(seg.start, eff_lo)
            shi = min(seg.end, eff_hi)
            if slo >= shi:
                continue
            dur = shi - slo
            _, _, tname = _parse_task_name(seg.task)
            if _is_idle_task_name(tname):
                idle_ns += dur
            elif tname.upper() == "TICK":
                tick_ns += dur
            else:
                active_ns += dur
            seg_total += dur
        gap_ns = max(0, span - seg_total)
        result.append((core, active_ns, idle_ns, tick_ns, gap_ns, span))
    return result


# ---- Task core-affinity rows ---------------------------------------------
_AFFINITY_NOTE_RE = re.compile(
    r"^affinity_set\s+(.+?)\s+(0x[0-9a-fA-F]+|\d+)\s*$", re.IGNORECASE)


def _affinity_mask_at_time(
    history: List[tuple],
    t: int,
) -> Optional[int]:
    """Return the affinity mask in effect at time *t*.

    *history* is a time-sorted list of ``(timestamp, mask)`` pairs from
    ``affinity_set`` STI events.  Before the first set the scheduler treats
    the task as unrestricted (``tskNO_AFFINITY``), so this returns ``None``.
    """
    active: Optional[int] = None
    for ts, mask in history:
        if ts > t:
            break
        active = mask
    return active


def _cores_allowed_by_mask(mask: int, core_names: List[str]) -> set:
    """Cores whose bit is set in *mask* (Core_N → bit N)."""
    allowed: set = set()
    for core in core_names:
        # Bound idx to avoid an astronomically large left-shift if a crafted
        # trace names a core with a huge numeric suffix.
        idx = _safe_int(core.split("_")[-1], default=-1)
        if 0 <= idx < 4096 and (mask & (1 << idx)):
            allowed.add(core)
    return allowed


def _format_affinity_mask_history(history: List[tuple]) -> str:
    """Compact mask column: ``0x1`` or ``0x1 → 0x8`` when the mask changes."""
    parts: List[str] = []
    for _, mask in history:
        hx = f"0x{mask:X}"
        if not parts or parts[-1] != hx:
            parts.append(hx)
    return " \u2192 ".join(parts) if parts else ""


def _task_core_affinity_rows(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    """Per-task core affinity summary.

    Returns: ``[(label, mask_hex, observed_cores_str, violation_cores_str), ...]``.

    Violations are evaluated per execution slice against the mask in effect at
    the slice start.  Slices before the first ``affinity_set`` are unrestricted
    and do not count as violations (tasks may migrate freely until pinned).
    """
    # Collect time-ordered affinity history per task (merge key).
    histories: Dict[str, List[tuple]] = {}
    for ev in trace.sti_events:
        if ev.target != "task":
            continue
        note = (ev.note or "").strip()
        m = _AFFINITY_NOTE_RE.match(note)
        if not m:
            continue
        task_label = m.group(1).strip()
        raw_mask = m.group(2)
        mask_val = _safe_int(raw_mask, 16 if raw_mask.startswith(("0x", "0X")) else 10)
        mk = _task_merge_key(task_label)
        histories.setdefault(mk, []).append((ev.time, mask_val))

    if not histories:
        return []

    for hist in histories.values():
        hist.sort(key=lambda item: item[0])

    rows = []
    for mk, history in sorted(histories.items()):
        raw_repr = trace.task_repr.get(mk, mk)
        label = _task_display_name(raw_repr)
        obs: set = set()
        violations: set = set()
        for seg in trace.seg_map_by_merge_key.get(mk, []):
            if lo is not None and seg.end < lo:
                continue
            if hi is not None and seg.start > hi:
                continue
            obs.add(seg.core)
            mask = _affinity_mask_at_time(history, seg.start)
            if mask is None:
                continue
            allowed = _cores_allowed_by_mask(mask, trace.core_names)
            if allowed and seg.core not in allowed:
                violations.add(seg.core)
        if not obs:
            continue
        mask_hex = _format_affinity_mask_history(history)
        obs_str = ", ".join(sorted(obs))
        viol_str = ", ".join(sorted(violations)) if violations else "\u2014"
        rows.append((label, mask_hex, obs_str, viol_str))
    return rows


def _deadline_violations(
    trace: "BtfTrace",
    cpu_budget_pct: float,
    task_deadlines_ns: Dict[str, int],
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> Dict[str, list]:
    """Compute per-slice and CPU-budget violations (mirrors web deadlineAnalysis.js)."""
    slice_violations: List[tuple] = []
    cpu_violations: List[tuple] = []
    if not trace.seg_map_by_merge_key:
        return {"slice_violations": slice_violations, "cpu_violations": cpu_violations}
    scale = trace.time_scale
    span = max(1, (hi - lo) if (lo is not None and hi is not None)
               else (trace.time_max - trace.time_min))
    for mk, segs in trace.seg_map_by_merge_key.items():
        raw_repr = trace.task_repr.get(mk, mk)
        _, _, tname = _parse_task_name(raw_repr)
        if _is_idle_task_name(tname) or tname == "TICK":
            continue
        disp = _task_display_name(raw_repr)
        # Match deadline by merge key, task name, or display name
        limit_ns: Optional[int] = None
        for key in (mk, tname, disp):
            if key in task_deadlines_ns:
                limit_ns = task_deadlines_ns[key]
                break
        if limit_ns is not None and limit_ns > 0:
            for seg in segs:
                if lo is not None and hi is not None and (seg.end <= lo or seg.start >= hi):
                    continue
                dur = seg.end - seg.start
                if dur > limit_ns:
                    slice_violations.append((
                        disp,
                        _format_time(dur, scale),
                        _format_time(limit_ns, scale),
                        _format_time(dur - limit_ns, scale),
                        dur,  # sort key
                    ))
        if cpu_budget_pct > 0:
            active = 0
            for seg in segs:
                if lo is not None and hi is not None:
                    if seg.end <= lo or seg.start >= hi:
                        continue
                    active += min(seg.end, hi) - max(seg.start, lo)
                else:
                    active += seg.end - seg.start
            pct = 100.0 * active / span
            if pct > cpu_budget_pct:
                cpu_violations.append((disp, f"{pct:.1f}%", f"{cpu_budget_pct:.1f}%", pct))
    slice_violations.sort(key=lambda r: -r[4])
    cpu_violations.sort(key=lambda r: -r[3])
    return {
        "slice_violations": [(r[0], r[1], r[2], r[3]) for r in slice_violations],
        "cpu_violations": [(r[0], r[1], r[2]) for r in cpu_violations],
    }


def _tag_plot_points(
    trace: "BtfTrace",
    channel: str,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[Tuple[int, int, TagSample]]:
    pts: List[Tuple[int, int, TagSample]] = []
    for sample in trace.tag_samples_by_channel.get(channel, []):
        if not _tag_overlaps_range(sample, lo, hi):
            continue
        pts.append((sample.time_ns, sample.value, sample))
    return pts

def _tag_sample_detail_rows(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
    limit: int = 200,
) -> List[dict]:
    scale = trace.time_scale
    rows: List[dict] = []
    for ch in trace.tag_channels:
        for sample in trace.tag_samples_by_channel.get(ch, []):
            if not _tag_overlaps_range(sample, lo, hi):
                continue
            rows.append({
                "channel": ch,
                "label": _tag_channel_label(ch),
                "time_ns": sample.time_ns,
                "time": _format_time(sample.time_ns, scale),
                "value": _format_tag_value(sample.value),
                "value_num": sample.value,
                "core": sample.core,
            })
    rows.sort(key=lambda r: (-r["value_num"], r["time_ns"]))
    return rows[:limit] if limit > 0 else rows

def _parse_create_priority(note: str) -> Optional[int]:
    m = _CREATE_PRI_RE.match((note or "").strip())
    return _safe_int(m.group(1)) if m else None

def _parse_priority_sti_note(note: str) -> Optional[Tuple[str, str, int]]:
    m = _PRIORITY_STI_RE.match((note or "").strip())
    if not m:
        return None
    return m.group(1).lower(), m.group(2).strip(), _safe_int(m.group(3))

def _merge_key_from_priority_ref(task_ref: str) -> str:
    return _task_merge_key((task_ref or "").strip())

def _priority_medium_blockers(
    base_pri: int,
    peak_pri: int,
    task_base_priority: Dict[str, int],
    holder_mk: str,
    task_repr: Dict[str, str],
) -> List[str]:
    if peak_pri <= base_pri:
        return []
    out: List[str] = []
    for mk, pri in task_base_priority.items():
        if mk == holder_mk:
            continue
        if base_pri < pri < peak_pri:
            raw = task_repr.get(mk, mk)
            out.append(_task_display_name(raw))
    return sorted(out)

def _build_priority_data(
    sti_events: List["StiEvent"],
    create_pri_by_raw: Dict[str, int],
    time_max: int,
    raw_to_mk: Dict[str, str],
    task_repr: Dict[str, str],
) -> Tuple[Dict[str, int], List[PriorityEpisode], Dict[str, List[PriorityEpisode]], bool]:
    task_base_priority: Dict[str, int] = {}
    for raw, pri in create_pri_by_raw.items():
        mk = raw_to_mk.get(raw) or _task_merge_key(raw)
        if mk not in task_base_priority:
            task_base_priority[mk] = pri

    changes_by_mk: Dict[str, List[Tuple[int, int, str]]] = defaultdict(list)
    for ev in sti_events:
        if ev.target != "task":
            continue
        sp = _parse_priority_sti_note(ev.note)
        if not sp:
            continue
        kind, ref, new_pri = sp
        mk = _merge_key_from_priority_ref(ref)
        changes_by_mk[mk].append((ev.time, new_pri, kind))

    has_data = bool(task_base_priority) and any(changes_by_mk.values())
    if not has_data:
        return task_base_priority, [], {}, False

    episodes: List[PriorityEpisode] = []
    episodes_by_mk: Dict[str, List[PriorityEpisode]] = {}

    for mk, base_pri in task_base_priority.items():
        changes = sorted(changes_by_mk.get(mk, []))
        if not changes:
            continue
        effective = base_pri
        open_ep: Optional[Tuple[int, int, bool]] = None

        def _pattern_label(peak: int, inherited: bool, medium: List[str]) -> str:
            if inherited:
                if medium:
                    names = ", ".join(medium[:2])
                    extra = f" +{len(medium) - 2}" if len(medium) > 2 else ""
                    return f"Mutex inherit L/M/H ({names}{extra})"
                return "Mutex inherit"
            if medium:
                names = ", ".join(medium[:2])
                extra = f" +{len(medium) - 2}" if len(medium) > 2 else ""
                return f"L/M/H ({names}{extra})"
            if peak > base_pri:
                return "Boost"
            return "—"

        def _close(stop_ns: int) -> None:
            nonlocal open_ep
            if not open_ep or stop_ns <= open_ep[0]:
                open_ep = None
                return
            peak, inherited = open_ep[1], open_ep[2]
            medium = _priority_medium_blockers(
                base_pri, peak, task_base_priority, mk, task_repr)
            raw = task_repr.get(mk, mk)
            ep = PriorityEpisode(
                mk=mk,
                task_label=_task_display_name(raw),
                base_pri=base_pri,
                peak_pri=peak,
                start_ns=open_ep[0],
                stop_ns=stop_ns,
                inherited=inherited,
                inversion_suspect=inherited or bool(medium),
                medium_tasks=medium,
                pattern=_pattern_label(peak, inherited, medium),
            )
            episodes.append(ep)
            episodes_by_mk.setdefault(mk, []).append(ep)
            open_ep = None

        for t_ns, new_pri, kind in changes:
            prev = effective
            effective = new_pri
            is_inherit = kind == "priority_inherit"
            is_disinherit = kind == "priority_disinherit"
            if effective > base_pri and prev <= base_pri:
                open_ep = (t_ns, effective, is_inherit)
            elif open_ep is not None:
                start, peak, inherited = open_ep
                if effective > peak:
                    peak = effective
                if is_inherit:
                    inherited = True
                open_ep = (start, peak, inherited)
                if effective <= base_pri or is_disinherit:
                    _close(t_ns)
        if open_ep is not None:
            _close(time_max)

    episodes.sort(key=lambda e: (e.start_ns, e.stop_ns))
    return task_base_priority, episodes, episodes_by_mk, True

def _priority_overlaps_range(ep: PriorityEpisode, lo: Optional[int], hi: Optional[int]) -> bool:
    if lo is None or hi is None:
        return True
    return ep.stop_ns > lo and ep.start_ns < hi

def _priority_boost_bands_for_viewport(
    episodes: List[PriorityEpisode],
    horiz: bool,
    time_min: int,
    px_per_ns: float,
    offset: float,
    vp_ns_lo: int,
    vp_ns_hi: int,
) -> list:
    """Build [(primary_px, span_px, inversion_suspect), ...] for visible episodes."""
    bands: list = []
    for ep in episodes:
        if ep.stop_ns <= vp_ns_lo or ep.start_ns >= vp_ns_hi:
            continue
        t1 = max(ep.start_ns, vp_ns_lo)
        t2 = min(ep.stop_ns, vp_ns_hi)
        c1 = offset + (t1 - time_min) * px_per_ns
        span = (t2 - t1) * px_per_ns
        if span < 0.5:
            continue
        bands.append((c1, span, ep.inversion_suspect))
    return bands

def _priority_stats_rows(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    if not trace.has_priority_instrumentation:
        return []
    scale = trace.time_scale
    by_mk: Dict[str, list] = defaultdict(list)
    for ep in trace.priority_episodes:
        if _priority_overlaps_range(ep, lo, hi):
            by_mk[ep.mk].append(ep)
    rows = []
    for mk, eps in by_mk.items():
        base_pri = trace.task_base_priority.get(mk, eps[0].base_pri)
        peak_pri = max(ep.peak_pri for ep in eps)
        total_ns = 0
        inv_count = 0
        inherit_count = 0
        for ep in eps:
            clip_lo = lo if lo is not None else ep.start_ns
            clip_hi = hi if hi is not None else ep.stop_ns
            clip_lo = max(clip_lo, ep.start_ns)
            clip_hi = min(clip_hi, ep.stop_ns)
            if clip_hi > clip_lo:
                total_ns += clip_hi - clip_lo
            if ep.inversion_suspect:
                inv_count += 1
            if ep.inherited:
                inherit_count += 1
        if inherit_count:
            pattern = "Mutex inherit + L/M/H" if inv_count > inherit_count else "Mutex inherit"
        elif inv_count:
            pattern = "L/M/H pattern"
        else:
            pattern = "Boost only"
        label = eps[0].task_label
        rows.append((
            mk,
            label,
            base_pri,
            peak_pri,
            len(eps),
            _format_time(total_ns, scale),
            pattern,
            total_ns,
        ))
    rows.sort(key=lambda r: (-r[7], r[1]))
    return rows

def _priority_plot_points(
    trace: "BtfTrace",
    mk: str,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[Tuple[int, int, PriorityEpisode]]:
    pts: List[Tuple[int, int, PriorityEpisode]] = []
    for ep in trace.priority_episodes_by_mk.get(mk, []):
        if not _priority_overlaps_range(ep, lo, hi):
            continue
        dur = ep.stop_ns - ep.start_ns
        pts.append((ep.stop_ns, dur, ep))
    return pts

def _parse_sync_object_note(note: str) -> Optional[Tuple[str, str]]:
    m = _SYNC_OBJECT_NOTE_RE.match((note or "").strip())
    if not m:
        return None
    ptr = (m.group(2) or "0").lower()
    return m.group(1).lower(), ptr

def _sync_object_key(kind: str, ptr: str) -> str:
    return f"{kind}:{ptr}"

def _running_task_mk(core_segs: Dict[str, list], core: str, time_ns: int,
                     seg_starts: Optional[Dict[str, list]] = None,
                     mk_cache: Optional[Dict[str, str]] = None) -> Optional[str]:
    seg = _segment_at_core_time(core_segs, core, time_ns, seg_starts=seg_starts)
    if seg is None:
        return None
    raw = seg.task
    if mk_cache is None:
        return _task_merge_key(raw)
    mk = mk_cache.get(raw)
    if mk is None:
        mk = _task_merge_key(raw)
        mk_cache[raw] = mk
    return mk

def _segment_at_core_time(core_segs: Dict[str, list], core: str, time_ns: int,
                          seg_starts: Optional[Dict[str, list]] = None
                          ) -> Optional["TaskSegment"]:
    segs = core_segs.get(core) or []
    if not segs or time_ns is None:
        return None
    starts = seg_starts.get(core) if seg_starts is not None else None
    if starts is None:
        starts = [s.start for s in segs]
    lo = max(0, bisect_left(starts, time_ns) - 1)
    for i in range(lo, len(segs)):
        s = segs[i]
        if s.start > time_ns:
            break
        if s.end >= time_ns:
            return s
    return None

def _format_sync_issue_note(iss: dict) -> str:
    obj_key = iss.get("obj_key")
    if obj_key:
        kind = iss.get("kind_label") or iss.get("kind") or "sync"
        ptr = iss.get("ptr") or ""
        detail = iss.get("detail") or iss.get("kind") or ""
        return f"{kind} {ptr}: {detail}".strip()
    return iss.get("detail") or iss.get("kind") or "sync issue"

def _build_sync_object_data(
    sti_events: List["StiEvent"],
    core_segs: Dict[str, list],
    task_repr: Dict[str, str],
    time_max: int,
    core_seg_starts: Optional[Dict[str, list]] = None,
    mk_cache: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, dict], List[dict], bool]:
    objects: Dict[str, dict] = {}
    global_issues: List[dict] = []

    events = []
    for ev in sti_events:
        if ev.target not in _SYNC_OBJECT_TARGETS:
            continue
        parsed = _parse_sync_object_note(ev.note)
        if parsed:
            events.append((ev, parsed))
    events.sort(key=lambda x: (x[0].time, x[1][0]))
    if not events:
        return {}, [], False

    def _empty_obj(kind: str, ptr: str) -> dict:
        return {
            "key": _sync_object_key(kind, ptr),
            "kind": kind,
            "ptr": ptr,
            "create_ns": None,
            "delete_ns": None,
            "holds": [],
            "issues": [],
            "open_takes": [],
            "open_gives": [],
        }

    def _is_post_create_kernel_give(obj: dict, time_ns: int) -> bool:
        create_ns = obj.get("create_ns")
        return create_ns is not None and time_ns - create_ns <= _POST_CREATE_GIVE_MAX_NS

    def _record_hold(obj: dict, take: dict, give: dict, take_first: bool) -> None:
        start = take if take_first else give
        stop = give if take_first else take
        obj["holds"].append({
            "start_ns": start["time_ns"], "stop_ns": stop["time_ns"],
            "duration_ns": stop["time_ns"] - start["time_ns"],
            "holder_mk": take.get("task_mk"), "holder_label": take["task_label"],
            "take_core": take.get("core", ""), "give_core": give.get("core", ""),
            "signal": not take_first,
        })

    # Sync STI events are time-sorted: advance a per-core segment cursor instead
    # of bisecting on every event (O(S_core) total vs O(Z · log S) per core).
    _core_cursor: Dict[str, int] = {}

    def _task_mk_at(core: str, time_ns: int) -> Optional[str]:
        segs = core_segs.get(core) or []
        if not segs:
            return None
        i = _core_cursor.get(core, 0)
        n = len(segs)
        # Advance past segments that ended before time_ns.
        while i < n and segs[i].end < time_ns:
            i += 1
        _core_cursor[core] = i
        if i >= n:
            return None
        s = segs[i]
        if s.start > time_ns:
            return None
        # Covering segment (start <= time_ns <= end) after the advance loop.
        if s.end < time_ns:
            return None
        raw = s.task
        if mk_cache is None:
            return _task_merge_key(raw)
        mk = mk_cache.get(raw)
        if mk is None:
            mk = _task_merge_key(raw)
            mk_cache[raw] = mk
        return mk

    for ev, (action, ptr) in events:
        key = _sync_object_key(ev.target, ptr)
        task_mk = _task_mk_at(ev.core, ev.time)
        raw = task_repr.get(task_mk, task_mk) if task_mk else "?"
        task_label = _task_display_name(raw) if task_mk else "?"

        if action == "create":
            obj = _empty_obj(ev.target, ptr)
            obj["create_ns"] = ev.time
            objects[key] = obj
        else:
            if key not in objects:
                objects[key] = _empty_obj(ev.target, ptr)
            obj = objects[key]
            if action in ("take", "recv"):
                rec = {"time_ns": ev.time, "task_mk": task_mk, "task_label": task_label,
                       "core": ev.core or ""}
                if obj["kind"] == "sem" and obj["open_gives"]:
                    give = obj["open_gives"].pop(0)
                    _record_hold(obj, rec, give, False)
                elif obj["kind"] == "queue" and obj["open_gives"]:
                    send = obj["open_gives"].pop(0)
                    _record_hold(obj, send, rec, True)
                else:
                    obj["open_takes"].append(rec)
            elif action in ("give", "send"):
                if action == "give" and _is_post_create_kernel_give(obj, ev.time):
                    continue
                give_rec = {"time_ns": ev.time, "task_mk": task_mk, "task_label": task_label,
                            "core": ev.core or ""}
                if obj["kind"] == "mutex":
                    if not obj["open_takes"]:
                        obj["issues"].append({
                            "kind": "orphan_give", "severity": "error", "time_ns": ev.time,
                            "core": ev.core or "", "task_mk": task_mk, "task_label": task_label,
                            "detail": "give without matching take",
                        })
                    else:
                        take = obj["open_takes"].pop()
                        if (take.get("task_mk") and task_mk
                                and take["task_mk"] != task_mk):
                            obj["issues"].append({
                                "kind": "cross_task_give", "severity": "warning",
                                "time_ns": ev.time, "core": ev.core or "",
                                "task_mk": task_mk, "task_label": task_label,
                                "detail": f"give by {task_label}, held by {take['task_label']}",
                            })
                        _record_hold(obj, take, give_rec, True)
                        if (take.get("core") and give_rec.get("core")
                                and take["core"] != give_rec["core"]):
                            obj["issues"].append({
                                "kind": "CORE_MIGRATION_WHILE_HELD",
                                "severity": "warning",
                                "time_ns": ev.time,
                                "core": ev.core or "",
                                "task_mk": task_mk,
                                "task_label": task_label,
                                "detail": f"Lock bounced from {take['core']} to {ev.core}",
                            })
                elif obj["kind"] == "queue":
                    obj["open_gives"].append(give_rec)
                elif obj["open_takes"]:
                    take = obj["open_takes"].pop(0)
                    _record_hold(obj, take, give_rec, True)
                else:
                    obj["open_gives"].append(give_rec)
            elif action == "delete":
                obj["delete_ns"] = ev.time
                if obj["open_takes"]:
                    obj["issues"].append({
                        "kind": "delete_while_held", "severity": "warning", "time_ns": ev.time,
                        "core": ev.core or "", "task_mk": task_mk, "task_label": task_label,
                        "detail": f"delete while {len(obj['open_takes'])} take(s) unmatched",
                    })
                obj["open_takes"] = []
                obj["open_gives"] = []

    end_mutex_holds: List[Tuple[dict, Optional[str], str]] = []
    for obj in objects.values():
        for take in obj["open_takes"]:
            obj["issues"].append({
                "kind": "unmatched_take", "severity": "warning", "time_ns": take["time_ns"],
                "core": take.get("core", ""), "task_mk": take.get("task_mk"),
                "task_label": take.get("task_label", ""),
                "detail": "take without matching give before trace end",
            })
            if obj["kind"] == "mutex":
                end_mutex_holds.append((obj, take.get("task_mk"), take.get("task_label", "")))
        for give in obj["open_gives"]:
            kind = "unmatched_send" if obj["kind"] == "queue" else "unmatched_give"
            detail = ("send without matching recv before trace end"
                      if obj["kind"] == "queue"
                      else "give without matching take before trace end")
            obj["issues"].append({
                "kind": kind, "severity": "warning", "time_ns": give["time_ns"],
                "core": give.get("core", ""), "task_mk": give.get("task_mk"),
                "task_label": give.get("task_label", ""),
                "detail": detail,
            })
        obj["open_takes"] = []
        obj["open_gives"] = []

    holders = {h[1] for h in end_mutex_holds if h[1]}
    if len(end_mutex_holds) >= 2 and len(holders) >= 2:
        global_issues.append({
            "kind": "deadlock_risk", "severity": "warning", "time_ns": time_max,
            "obj_key": None, "ptr": "", "kind_label": "mutex",
            "detail": (f"{len(end_mutex_holds)} mutex(es) still held by "
                       f"{len(holders)} tasks at trace end"),
            "objects": [h[0]["key"] for h in end_mutex_holds],
        })

    sync_issues: List[dict] = []
    for obj in objects.values():
        for iss in obj["issues"]:
            sync_issues.append({**iss, "obj_key": obj["key"], "ptr": obj["ptr"],
                                "kind_label": obj["kind"]})
    sync_issues.extend(global_issues)
    sync_issues.sort(key=lambda i: (i["time_ns"], i.get("obj_key") or ""))
    return objects, sync_issues, True

def _sync_in_scope(time_ns: int, lo: Optional[int], hi: Optional[int]) -> bool:
    if lo is None or hi is None:
        return True
    return lo <= time_ns <= hi

def _sync_object_status(obj: dict, lo: Optional[int], hi: Optional[int]) -> str:
    issues = [i for i in obj.get("issues", []) if _sync_in_scope(i["time_ns"], lo, hi)]
    if not issues:
        return "ok"
    if any(i.get("severity") == "error" for i in issues):
        return "error"
    return "warning"

def _sync_object_stats_rows(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
    kind_filter: Optional[str] = None,
) -> List[tuple]:
    if not trace.has_sync_object_instrumentation:
        return []
    scale = trace.time_scale
    rows = []
    for obj in trace.sync_objects.values():
        if kind_filter is not None and obj["kind"] != kind_filter:
            continue
        holds = [h for h in obj.get("holds", [])
                 if lo is None or hi is None or (h["stop_ns"] > lo and h["start_ns"] < hi)]
        issues = [i for i in obj.get("issues", []) if _sync_in_scope(i["time_ns"], lo, hi)]
        if lo is not None and hi is not None and not holds and not issues:
            if obj.get("create_ns") is None or not _sync_in_scope(obj["create_ns"], lo, hi):
                continue
        status = _sync_object_status(obj, lo, hi)
        status_label = {"ok": "OK", "error": "Error", "warning": "Warning"}[status]
        avg_ns = (sum(h["duration_ns"] for h in holds) // len(holds)) if holds else 0
        bounces = sum(
            1 for h in holds
            if h.get("take_core") and h.get("give_core")
            and h["take_core"] != h["give_core"]
        )
        rows.append((
            obj["key"],
            obj["kind"],
            obj["ptr"],
            f"{obj['kind']} {obj['ptr']}",
            len(holds),
            len(issues),
            _format_time(avg_ns, scale) if holds else "—",
            status_label,
            status,
            avg_ns,
            bounces,
        ))
    rows.sort(key=lambda r: (
        0 if r[8] == "error" else 1 if r[8] == "warning" else 2,
        -r[5], r[3]))
    return rows

def _sync_object_hold_detail_rows(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
    limit: int = 150,
) -> List[dict]:
    if not trace.has_sync_object_instrumentation:
        return []
    scale = trace.time_scale
    rows: List[dict] = []
    for obj in trace.sync_objects.values():
        for h in obj.get("holds", []):
            if lo is not None and hi is not None:
                if not (h["stop_ns"] > lo and h["start_ns"] < hi):
                    continue
            rows.append({
                "object": f"{obj['kind']} {obj['ptr']}",
                "holder": h.get("holder_label") or "—",
                "start": _format_time(h["start_ns"], scale),
                "start_ns": h["start_ns"],
                "stop": _format_time(h["stop_ns"], scale),
                "duration": _format_time(h["duration_ns"], scale),
                "duration_ns": h["duration_ns"],
                "take_core": h.get("take_core") or "",
                "give_core": h.get("give_core") or "",
            })
    # Tie-break by the raw start timestamp (not the formatted label) so equal
    # durations sort chronologically rather than lexicographically.
    rows.sort(key=lambda r: (-r["duration_ns"], r.get("start_ns", 0)))
    return rows[:limit] if limit > 0 else rows

def _priority_episode_detail_rows(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
    limit: int = 200,
) -> List[dict]:
    if not trace.has_priority_instrumentation:
        return []
    scale = trace.time_scale
    rows: List[dict] = []
    for ep in trace.priority_episodes:
        if lo is not None and hi is not None:
            if not (ep.stop_ns > lo and ep.start_ns < hi):
                continue
        rows.append({
            "task": ep.task_label,
            "pri": f"{ep.base_pri}→{ep.peak_pri}",
            "start": _format_time(ep.start_ns, scale),
            "stop": _format_time(ep.stop_ns, scale),
            "duration": _format_time(ep.stop_ns - ep.start_ns, scale),
            "start_ns": ep.start_ns,
            "pattern": ep.pattern or "—",
        })
    rows.sort(key=lambda r: (r["start_ns"], r.get("stop", "")))
    return rows[:limit] if limit > 0 else rows

def _interval_instance_detail_rows(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
    limit: int = 200,
) -> List[dict]:
    scale = trace.time_scale
    rows: List[dict] = []
    for iid in trace.interval_ids:
        for inst in trace.interval_instances_by_id.get(iid, []):
            if not _interval_overlaps_range(inst, lo, hi):
                continue
            rows.append({
                "id": iid,
                "task_id": inst.task_id or "—",
                "start": _format_time(inst.start_ns, scale),
                "start_ns": inst.start_ns,
                "stop": _format_time(inst.stop_ns, scale),
                "duration": _format_time(inst.stop_ns - inst.start_ns, scale),
                "duration_ns": inst.stop_ns - inst.start_ns,
                "start_core": inst.start_core or "",
                "stop_core": inst.stop_core or "",
            })
    # Tie-break by the raw start timestamp (not the formatted label) so equal
    # durations sort chronologically rather than lexicographically.
    rows.sort(key=lambda r: (-r["duration_ns"], r.get("start_ns", 0)))
    return rows[:limit] if limit > 0 else rows

def _task_priority_label_suffix(trace: "BtfTrace", mk: str) -> str:
    pri = trace.task_base_priority.get(mk)
    return f" · pri {pri}" if pri is not None else ""

def _plot_point_mark_ns(payload, x_ns: int) -> int:
    """Timeline position for an annotation created from a metrics plot point."""
    if isinstance(payload, IntervalInstance):
        return payload.stop_ns
    if isinstance(payload, TagSample):
        return payload.time_ns
    if isinstance(payload, PriorityEpisode):
        return payload.stop_ns
    if isinstance(payload, SyncIssueRef):
        return payload.time_ns
    if isinstance(payload, MigrationEvent):
        return payload.ns
    if isinstance(payload, TaskSegment):
        return payload.start
    return x_ns

def _format_plot_point_note(
    trace: "BtfTrace",
    kind: str,
    mk: Optional[str],
    preemptor: Optional[str],
    x_ns: int,
    y_ns: int,
    payload,
) -> str:
    """Human-readable note for a statistics distribution plot point."""
    scale = trace.time_scale
    fmt = lambda v: _format_time(v, scale)
    if isinstance(payload, IntervalInstance):
        return (f"Interval {payload.id}: {fmt(y_ns)} "
                f"[{fmt(payload.start_ns)} – {fmt(payload.stop_ns)}]")
    if isinstance(payload, TagSample):
        return (f"{_tag_channel_label(payload.channel)}: "
                f"{_format_tag_value(y_ns)} at {fmt(x_ns)}")
    if isinstance(payload, PriorityEpisode):
        tag = " · L/M/H" if payload.inversion_suspect else ""
        return (f"{payload.task_label}: pri {payload.base_pri}→{payload.peak_pri} "
                f"— {fmt(y_ns)} [{fmt(payload.start_ns)} – {fmt(payload.stop_ns)}]{tag}")
    if isinstance(payload, TaskSegment):
        raw = trace.task_repr.get(mk, mk) if mk else payload.task
        name = _task_display_name(raw)
        if kind == "exec":
            return f"{name}: {fmt(y_ns)} at {fmt(x_ns)}"
        if kind == "block":
            return f"{name}: {fmt(y_ns)} blocked before {fmt(x_ns)}"
        if kind == "inter":
            return f"{name}: {fmt(y_ns)} inter-arrival at {fmt(x_ns)}"
        if kind == "preempt":
            pre = preemptor or "?"
            return f"{name} ← {pre}: {fmt(y_ns)} at {fmt(x_ns)}"
        if kind == "mig_dwell":
            return f"{name}: {fmt(y_ns)} dwell on {payload.core} at {fmt(x_ns)}"
    if isinstance(payload, MigrationEvent):
        raw = trace.task_repr.get(mk, mk) if mk else payload.merge_key
        name = _task_display_name(raw)
        if kind == "mig_rate":
            return f"{name}: {fmt(y_ns)} since previous migration at {fmt(x_ns)}"
        if kind == "mig_gap":
            return (f"{name}: {fmt(y_ns)} blocked after {payload.from_core}→"
                    f"{payload.to_core} at {fmt(x_ns)}")
    if kind == "tick":
        return f"Tick interval {fmt(y_ns)} at {fmt(x_ns)}"
    return f"{fmt(y_ns)} at {fmt(x_ns)}"

def _gap_before_segment(segs: list, seg: "TaskSegment", kind: str) -> Optional[int]:
    ordered = sorted(segs, key=lambda s: s.start)
    idx = next(
        (i for i, s in enumerate(ordered)
         if s is seg or (s.start == seg.start and s.end == seg.end and s.task == seg.task)),
        -1,
    )
    if idx <= 0:
        return None
    prev, nxt = ordered[idx - 1], ordered[idx]
    if kind == "inter":
        return nxt.start - prev.start
    return nxt.start - prev.end

def _format_extreme_segment_note(
    trace: "BtfTrace",
    mk: str,
    kind: str,
    seg: "TaskSegment",
    find_max: bool,
) -> str:
    """Annotation note for Min/Max links in statistics tables."""
    raw = trace.task_repr.get(mk, mk)
    name = _task_display_name(raw)
    scale = trace.time_scale
    fmt = lambda v: _format_time(v, scale)
    label = "max" if find_max else "min"
    if kind == "exec":
        dur = seg.end - seg.start
        extreme = "WCET" if find_max else "BCET"
        return f"{name} {extreme}: {fmt(dur)} at {fmt(seg.start)}"
    segs = trace.seg_map_by_merge_key.get(mk, [])
    gap = _gap_before_segment(segs, seg, kind)
    gap_s = fmt(gap) if gap is not None else "?"
    if kind == "block":
        return f"{name} {label} blocking: {gap_s} before {fmt(seg.start)}"
    if kind == "inter":
        return f"{name} {label} inter-arrival: {gap_s} at {fmt(seg.start)}"
    return f"{name} at {fmt(seg.start)}"

@dataclass
class TraceBookmark:
    """User bookmark pinned to a timeline timestamp."""
    id: int
    ns: int
    label: str

@dataclass
class TraceAnnotation:
    """User annotation pinned to a timeline timestamp."""
    id: int
    ns: int
    note: str

@dataclass
class SegLodData:
    """Per-row/column segment LOD data bundle for _visible_segs() clipping."""
    segs: list
    starts: list
    lod_segs: list
    lod_starts: list
    lod_ultra_segs: list = field(default_factory=list)
    lod_ultra_starts: list = field(default_factory=list)

@dataclass
class ViewClipParams:
    """Shared viewport/zoom parameters for _visible_segs() calls within one builder."""
    ns_lo: int
    ns_hi: int
    time_min: int
    px_per_ns: float
    offset: float
    cur_timescale_per_px: float
    lod_timescale_per_px: float
    lod_ultra_timescale_per_px: float = float("inf")

@dataclass
class BtfTrace:
    """Parsed result of a .btf file."""
    time_scale: str                     # "ns", "us", "ms" ...
    tasks: List[str]                    # ordered task name list
    segments: List[TaskSegment]
    sti_events: List[StiEvent]
    sti_channels: List[str]             # ordered list of distinct STI channel names
    sti_events_by_target: Dict[str, List[StiEvent]]   # fast lookup for builders
    time_min: int
    time_max: int
    meta: Dict[str, str] = field(default_factory=dict)
    # Pre-built, start-time-sorted segment map keyed by _task_merge_key.
    # Avoids O(n_segments) iteration on every scene rebuild.
    seg_map_by_merge_key: Dict[str, List[TaskSegment]] = field(default_factory=dict)
    # Pre-built core-view data - cached once at parse time so core-view
    # rebuild() never iterates trace.segments again (O(1) access).
    core_names:      List[str]                                        = field(default_factory=list)
    core_segs:       Dict[str, List[TaskSegment]]                     = field(default_factory=dict)
    core_task_order: Dict[str, List[str]]                             = field(default_factory=dict)
    core_task_segs:  Dict[str, Dict[str, List[TaskSegment]]]          = field(default_factory=dict)
    # Maps each merge-key to its representative raw task name string.
    # Used by task-view builders to look up display names and colours from
    # merge keys (trace.tasks stores merge keys, not raw names).
    task_repr: Dict[str, str]                                         = field(default_factory=dict)

    # ---- Fast viewport-clip support (1M-event performance) ----------------
    # Pre-sorted start-time lists (ints) for each key - enable O(log n) bisect
    # clipping so builders only iterate segments visible in the current viewport.
    seg_start_by_merge_key:  Dict[str, List[int]]             = field(default_factory=dict)
    core_seg_starts:         Dict[str, List[int]]             = field(default_factory=dict)
    core_task_seg_starts:    Dict[str, Dict[str, List[int]]]  = field(default_factory=dict)
    sti_starts_by_target:    Dict[str, List[int]]             = field(default_factory=dict)

    # Pre-built coarse LOD summaries (_LOD_SUMMARY_BINS bins over the full time
    # span).  When timescale_per_px >= seg_lod_timescale_per_px (i.e., zoomed out past the
    # summary resolution), builders use these instead of iterating raw segments,
    # bounding rebuild cost to O(_LOD_SUMMARY_BINS) regardless of trace size.
    seg_lod_timescale_per_px:              float                                   = 1.0
    seg_lod_by_merge_key:           Dict[str, List[TaskSegment]]            = field(default_factory=dict)
    seg_lod_starts_by_merge_key:    Dict[str, List[int]]                    = field(default_factory=dict)
    seg_lod_ultra_timescale_per_px:        float                                   = 1.0
    seg_lod_ultra_by_merge_key:     Dict[str, List[TaskSegment]]            = field(default_factory=dict)
    seg_lod_ultra_starts_by_merge_key: Dict[str, List[int]]                 = field(default_factory=dict)
    core_seg_lod:                   Dict[str, List[TaskSegment]]            = field(default_factory=dict)
    core_seg_lod_starts:            Dict[str, List[int]]                    = field(default_factory=dict)
    core_seg_lod_ultra:             Dict[str, List[TaskSegment]]            = field(default_factory=dict)
    core_seg_lod_ultra_starts:      Dict[str, List[int]]                    = field(default_factory=dict)
    core_task_seg_lod:              Dict[str, Dict[str, List[TaskSegment]]] = field(default_factory=dict)
    core_task_seg_lod_starts:       Dict[str, Dict[str, List[int]]]         = field(default_factory=dict)
    core_task_seg_lod_ultra:        Dict[str, Dict[str, List[TaskSegment]]] = field(default_factory=dict)
    core_task_seg_lod_ultra_starts: Dict[str, Dict[str, List[int]]]         = field(default_factory=dict)
    # Map from merge-key -> timestamp of the task_create event (first occurrence).
    task_create_times: Dict[str, int]                                       = field(default_factory=dict)
    # Map from merge-key -> raw task representation seen at creation time. Used as a
    # fallback label source for tasks that are created but never scheduled (so they
    # never appear in `task_repr`, which is only populated from context-switch segments).
    task_create_repr: Dict[str, str]                                        = field(default_factory=dict)
    # Sorted timestamps from STI TICK events - rendered as ruler marks.
    tick_sti_times: List[int]                                               = field(default_factory=list)
    # All STI event times sorted once at parse — used by migration stats.
    sti_event_times: List[int]                                              = field(default_factory=list)
    # Core migrations: consecutive slices of the same merge-key on different cores.
    migrations: List[MigrationEvent]                                        = field(default_factory=list)
    migrations_by_mk: Dict[str, List[MigrationEvent]]                       = field(default_factory=dict)
    interval_instances: List["IntervalInstance"]                            = field(default_factory=list)
    interval_ids: List[str]                                                 = field(default_factory=list)
    interval_instances_by_id: Dict[str, List["IntervalInstance"]]            = field(default_factory=dict)
    # Nested intervals culled once at parse time so rebuild() only bisect-clips
    # the viewport slice (O(log n + visible)) instead of O(n²) nested culling.
    interval_instances_culled_by_id: Dict[str, List["IntervalInstance"]]     = field(default_factory=dict)
    core_util_pct: Dict[str, float]                                         = field(default_factory=dict)
    interval_marker_by_id: Dict[str, dict]                                  = field(default_factory=dict)
    interval_unmatched_starts: int                                          = 0
    tag_channels: List[str]                                                 = field(default_factory=list)
    tag_samples_by_channel: Dict[str, List["TagSample"]]                    = field(default_factory=dict)
    task_base_priority: Dict[str, int]                                     = field(default_factory=dict)
    priority_episodes: List[PriorityEpisode]                                = field(default_factory=list)
    priority_episodes_by_mk: Dict[str, List[PriorityEpisode]]                 = field(default_factory=dict)
    has_priority_instrumentation: bool                                      = False
    sync_objects: Dict[str, dict]                                           = field(default_factory=dict)
    sync_issues: List[dict]                                                 = field(default_factory=list)
    has_sync_object_instrumentation: bool                                   = False
    # Timestamps (ns) of migrations that occurred while a mutex was held across cores.
    lock_bounce_migration_ns: frozenset                                     = field(default_factory=frozenset)
    # Core affinity masks parsed from affinity_set STI events (merge_key → bitmask).
    task_affinity_mask: Dict[str, int]                                      = field(default_factory=dict)

# ---------------------------------------------------------------------------
# Task-name helpers
# ---------------------------------------------------------------------------

_TASK_BRACKET_RE = re.compile(
    r"^\[((?:0[xX][0-9a-fA-F]+|\d+))/((?:0[xX][0-9a-fA-F]+|\d+))\](.+)$")
_TASK_SUFFIX_BRACKET_RE = re.compile(
    r"^(.+?)\[((?:0[xX][0-9a-fA-F]+|\d+))\]$")
_TASK_SUFFIX_PAREN_RE = re.compile(
    r"^(.+?)\(((?:0[xX][0-9a-fA-F]+|\d+))\)$")
# Back-compat alias
_TASK_RE = _TASK_BRACKET_RE
# Matches: idle, idle0, idle 0, idle(0x...), idle 0(0x...), idle0(0x...)
_IDLE_RE = re.compile(
    r"^idle(?:\s*(\d+))?\s*(?:\((?:0[xX][0-9a-fA-F]+|\d+)\))?$",
    re.IGNORECASE,
)

_MAX_SAFE_INT_DIGITS = 18  # generous headroom over any realistic task/core id, priority, or tag index

def _safe_int(s: str, base: int = 10, default: int = 0) -> int:
    """Parse an int token defensively.

    Returns `default` for invalid input or an absurdly long digit string from an
    adversarial trace file, instead of raising (Python's int-string-conversion
    limit) or succeeding with an astronomically large value that later blows up
    a bit-shift/format operation.
    """
    if not s or len(s) > _MAX_SAFE_INT_DIGITS:
        return default
    try:
        return int(s, base)
    except ValueError:
        return default

def _parse_int_token(s: str) -> int:
    """Parse an integer token that may be hex (0x...) or decimal (with optional leading zeros)."""
    if s.startswith(("0x", "0X")):
        return _safe_int(s, 16)
    return _safe_int(s, 10)

def _format_int_token_display(token: str, value: int) -> str:
    """Format a parsed task-id token for Name[id] labels."""
    if token.startswith(("0x", "0X")):
        return f"0x{value:X}"
    return str(value)

def _task_id_display_string(raw: str, task_id: int) -> str:
    """Recover display form of task id from the raw BTF task name."""
    for pat in (_TASK_BRACKET_RE, _TASK_SUFFIX_BRACKET_RE, _TASK_SUFFIX_PAREN_RE):
        m = pat.match(raw)
        if m:
            return _format_int_token_display(m.group(2), task_id)
    return str(task_id)

@functools.lru_cache(maxsize=16384)
def _parse_task_name(raw: str) -> Tuple[Optional[int], Optional[int], str]:
    """Return (core_id, task_id, display_name) from a raw BTF task name.

    Supported forms:
      [core/task]name   e.g. [0/0001]MainCtrl, [2/0x9]Worker
      name[task]        e.g. MainCtrl[1], Worker[0x8]
      name(task)        e.g. Worker_0(0x6000d200), trace_test(42)
    IDLE variants are left unparsed (merge key = raw string).
    """
    if _IDLE_RE.match(raw):
        return None, None, raw
    m = _TASK_BRACKET_RE.match(raw)
    if m:
        return (_parse_int_token(m.group(1)), _parse_int_token(m.group(2)),
                m.group(3).strip())
    m = _TASK_SUFFIX_BRACKET_RE.match(raw)
    if m:
        return None, _parse_int_token(m.group(2)), m.group(1).strip()
    m = _TASK_SUFFIX_PAREN_RE.match(raw)
    if m:
        return None, _parse_int_token(m.group(2)), m.group(1).strip()
    return None, None, raw

@functools.lru_cache(maxsize=16384)
def _is_idle_task_name(name: str) -> bool:
    return _IDLE_RE.match(name) is not None

@functools.lru_cache(maxsize=16384)
def _idle_task_index(name: str) -> int:
    m = _IDLE_RE.match(name)
    if m and m.group(1):
        try:
            return int(m.group(1))
        except ValueError:
            return 0
    return 0

@functools.lru_cache(maxsize=16384)
def _normalize_idle_name(name: str) -> str:
    """Normalize any idle variant (e.g. 'idle 0(0x1)') to 'idle' or 'idle<N>'."""
    m = _IDLE_RE.match(name)
    if m:
        idx = m.group(1)
        return f"idle{idx}" if idx else "idle"
    return name

@functools.lru_cache(maxsize=16384)
def _task_display_name(raw: str) -> str:
    """Short display name: 'Name[id]' for regular tasks; bare name for IDLE/TICK."""
    if raw.startswith("\x00"):
        # `raw` is itself an internal merge-key string (e.g. '\x00271\x00SR'),
        # not an actual raw trace repr — this happens when no trace repr was
        # ever recorded for the task (see `_task_merge_key`). Decode it directly
        # instead of falling through to the raw-name parsers below, which
        # would otherwise return it unparsed and produce a garbled label like
        # "289SF" (task_id and name glued together with invisible NUL bytes).
        sep = raw.find("\x00", 1)
        if sep > 0:
            task_id_str, name = raw[1:sep], raw[sep + 1:]
            if name == "TICK":
                return name
            if _is_idle_task_name(name):
                return _normalize_idle_name(name)
            return f"{name}[{task_id_str}]"
    if _IDLE_RE.match(raw):
        return _normalize_idle_name(raw)
    _, task_id, name = _parse_task_name(raw)
    if _is_idle_task_name(name):
        return _normalize_idle_name(name)
    if task_id is not None and name != "TICK":
        return f"{name}[{_task_id_display_string(raw, task_id)}]"
    return name

@functools.lru_cache(maxsize=16384)
def _task_sort_key(raw: str) -> Tuple[int, int, str]:
    """Sorting key: user tasks first, then IDLE, then TICK."""
    core_id, task_id, name = _parse_task_name(raw)
    if _is_idle_task_name(name):
        group = 2
    elif name == "TICK":
        group = 3
    else:
        group = 1
    return (group, task_id if task_id is not None else 0, name)

@functools.lru_cache(maxsize=16384)
def _task_merge_key(raw: str) -> str:
    """Stable key that ignores core_id, used to merge cross-core task rows in task view.

    Two raw names like '[0/1]MyTask' and '[1/1]MyTask' share the same merge key
    so they collapse into a single row in the task view, while the core view still
    shows them separately.
    """
    _, task_id, name = _parse_task_name(raw)
    if task_id is not None:
        return f"\x00{task_id}\x00{name}"
    return raw  # no [core/id] prefix -> use as-is

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=4096)
def _is_core_entity(name: str) -> bool:
    return name.startswith("Core_")

def _seg_overlap_ns(seg: TaskSegment, lo: int, hi: int) -> int:
    """Nanoseconds of *seg* that fall inside the half-open interval [lo, hi)."""
    if seg.end <= lo or seg.start >= hi:
        return 0
    return min(seg.end, hi) - max(seg.start, lo)

def _seg_fully_in_range(seg: TaskSegment, lo: int, hi: int) -> bool:
    """True when the segment starts and ends inside [lo, hi] (inclusive)."""
    return seg.start >= lo and seg.end <= hi

def _seg_overlaps_range(seg: TaskSegment, lo: int, hi: int) -> bool:
    return seg.end > lo and seg.start < hi

def _safe_scene_remove_items(scene: "QGraphicsScene", items: list) -> None:
    """Remove graphics items without crashing if clear() already destroyed them."""
    for item in items:
        try:
            if item.scene() is scene:
                scene.removeItem(item)
        except RuntimeError:
            pass

def _seg_core_neighbors(trace: "BtfTrace", seg: TaskSegment
                        ) -> Tuple[Optional[TaskSegment], Optional[TaskSegment], int, int]:
    """Return (prev_on_core, next_on_core, 1-based_index, total_on_core) for *seg*."""
    segs = trace.core_segs.get(seg.core, [])
    n = len(segs)
    if not n:
        return None, None, 0, 0
    starts = trace.core_seg_starts.get(seg.core)
    idx = -1
    if starts and len(starts) == n:
        i0 = bisect_left(starts, seg.start)
        for i in (i0 - 1, i0, i0 + 1):
            if 0 <= i < n:
                s = segs[i]
                if s.start == seg.start and s.end == seg.end and s.task == seg.task:
                    idx = i
                    break
    if idx < 0:
        for i, s in enumerate(segs):
            if s.start == seg.start and s.end == seg.end and s.task == seg.task:
                idx = i
                break
    if idx < 0:
        return None, None, 0, n
    prev = segs[idx - 1] if idx > 0 else None
    nxt = segs[idx + 1] if idx + 1 < n else None
    return prev, nxt, idx + 1, n

def _blocking_time_samples(segs: list,
                           lo: Optional[int] = None, hi: Optional[int] = None) -> List[int]:
    """Off-CPU gaps between consecutive slices of the same task."""
    if len(segs) < 2:
        return []
    ordered = sorted(segs, key=lambda s: s.start)
    samples: List[int] = []
    for i in range(1, len(ordered)):
        prev, nxt = ordered[i - 1], ordered[i]
        if lo is not None and hi is not None:
            if not (_seg_fully_in_range(prev, lo, hi) and _seg_fully_in_range(nxt, lo, hi)):
                continue
        gap = nxt.start - prev.end
        if gap > 0:
            samples.append(gap)
    return samples

def _scheduling_stats(trace: "BtfTrace",
                      lo: Optional[int] = None, hi: Optional[int] = None
                      ) -> Tuple[int, List[int]]:
    """Context-switch count and inter-slice core gaps (ns) within optional scope."""
    ctx_switches = 0
    gaps: List[int] = []
    for core in trace.core_names:
        segs = trace.core_segs.get(core, [])
        for i in range(1, len(segs)):
            prev, curr = segs[i - 1], segs[i]
            if lo is not None and hi is not None:
                if not (lo <= curr.start <= hi):
                    continue
            ctx_switches += 1
            gap = curr.start - prev.end
            gaps.append(gap if gap > 0 else 0)
    return ctx_switches, gaps

def _task_cores_used(trace: "BtfTrace", merge_key: str) -> set:
    return {s.core for s in trace.seg_map_by_merge_key.get(merge_key, ())}

def _is_migrated_task(trace: "BtfTrace", merge_key: str) -> bool:
    return len(_task_cores_used(trace, merge_key)) >= 2

def _build_migration_index(
    segs_by_mk: Dict[str, list],
) -> Tuple[List[MigrationEvent], Dict[str, List[MigrationEvent]]]:
    """Detect core changes between consecutive slices per merge-key."""
    migrations: List[MigrationEvent] = []
    by_mk: Dict[str, List[MigrationEvent]] = {}
    for mk, segs in segs_by_mk.items():
        if len(segs) < 2:
            continue
        raw = segs[0].task
        _cid, _tid, tname = _parse_task_name(raw)
        if _is_idle_task_name(tname) or tname == "TICK":
            continue
        for i in range(1, len(segs)):
            prev, nxt = segs[i - 1], segs[i]
            if prev.core == nxt.core:
                continue
            gap = max(0, nxt.start - prev.end)
            ev = MigrationEvent(
                ns=prev.end,
                merge_key=mk,
                from_core=prev.core,
                to_core=nxt.core,
                gap_ns=gap,
            )
            migrations.append(ev)
            by_mk.setdefault(mk, []).append(ev)
    migrations.sort(key=lambda m: m.ns)
    return migrations, by_mk

def _count_ping_pong(migs: List[MigrationEvent],
                     window: int = _MIGRATION_PING_PONG_WINDOW) -> int:
    """Count A→B→A core hops within *window* trace time units."""
    if len(migs) < 3:
        return 0
    count = 0
    for i in range(2, len(migs)):
        a, b, c = migs[i - 2], migs[i - 1], migs[i]
        if (b.ns - a.ns > window) or (c.ns - b.ns > window):
            continue
        if a.to_core == b.from_core and b.to_core == c.from_core and a.from_core == c.to_core:
            count += 1
    return count

def _migration_sti_near_count(sti_times: List[int], migs: List[MigrationEvent],
                              window: int = _MIGRATION_STI_WINDOW) -> int:
    if not migs or not sti_times:
        return 0
    count = 0
    for m in migs:
        lo = m.ns - window
        hi = m.ns + window
        i0 = bisect_left(sti_times, lo)
        i1 = bisect_right(sti_times, hi)
        if i1 > i0:
            count += 1
    return count

def _cores_in_scope(
    segs: List["TaskSegment"],
    migs: List[MigrationEvent],
    lo: Optional[int] = None, hi: Optional[int] = None,
) -> set:
    """Distinct cores with on-CPU slices or migrations in scope."""
    cores: set = set()
    for s in segs:
        if lo is not None and hi is not None:
            if not _seg_overlaps_range(s, lo, hi):
                continue
        cores.add(s.core)
    if not cores and migs:
        for m in migs:
            cores.add(m.from_core)
            cores.add(m.to_core)
    return cores

def _clip_segments_for_scope(
    segs: List["TaskSegment"],
    lo: Optional[int] = None, hi: Optional[int] = None,
) -> List[Tuple[int, int]]:
    """Segment [start, end] intervals clipped to scope, sorted by start."""
    clipped: List[Tuple[int, int]] = []
    for s in segs:
        if lo is not None and hi is not None:
            if not _seg_overlaps_range(s, lo, hi):
                continue
            seg_lo = max(s.start, lo)
            seg_hi = min(s.end, hi)
        else:
            seg_lo, seg_hi = s.start, s.end
        if seg_lo <= seg_hi:
            clipped.append((seg_lo, seg_hi))
    clipped.sort(key=lambda x: x[0])
    return clipped

def _tick_count_for_task(
    segs: List["TaskSegment"],
    tick_times: List[int],
    lo: Optional[int] = None, hi: Optional[int] = None,
) -> int:
    """TICK events in scope while this task was on-CPU."""
    clipped = _clip_segments_for_scope(segs, lo, hi)
    if not clipped or not tick_times:
        return 0
    count = 0
    i = 0
    n = len(clipped)
    for t in tick_times:
        if lo is not None and hi is not None and not (lo <= t <= hi):
            continue
        while i + 1 < n and clipped[i + 1][0] <= t:
            i += 1
        seg_lo, seg_hi = clipped[i]
        if seg_lo <= t <= seg_hi:
            count += 1
    return count

def _core_dwell_samples(
    segs: List["TaskSegment"],
    lo: Optional[int] = None, hi: Optional[int] = None,
) -> List[int]:
    """Per on-core run duration: each slice until block, yield, or migration."""
    samples: List[int] = []
    for s in segs:
        if lo is not None and hi is not None:
            if not _seg_overlaps_range(s, lo, hi):
                continue
            ov_lo = max(s.start, lo)
            ov_hi = min(s.end, hi)
        else:
            ov_lo, ov_hi = s.start, s.end
        dur = max(0, ov_hi - ov_lo)
        if dur > 0:
            samples.append(dur)
    return samples

def _format_migration_rate(n_mig: int, task_active: int, tick_count: int,
                           time_scale: str) -> Tuple[str, float]:
    """Return (display label, migrations per second of task active time) for sorting."""
    if n_mig <= 0:
        return "-", -1.0
    per_s = -1.0
    per_s_label: Optional[str] = None
    if task_active > 0:
        active_s = _to_ns(task_active, time_scale) / 1_000_000_000.0
        if active_s > 0:
            per_s = n_mig / active_s
            per_s_label = f"{per_s:.2f}/s"
    if tick_count > 0:
        per_tick = n_mig / tick_count
        tick_label = f"{per_tick:.3f}/tick"
        if per_s_label:
            return f"{per_s_label} · {tick_label}", per_s
        return tick_label, per_s
    if per_s_label:
        return per_s_label, per_s
    return "-", -1.0

def _migration_row_html(r: tuple) -> str:
    """One Core Migrations table row for statistics HTML export."""
    (_mk, name, n_mig, n_cores, _cores, primary, primary_pct,
     ping, sti, g_after, g_other, migr_rate, _rps, avg_dwell, _dwell_tu) = r
    esc = html.escape
    return (
        f"<tr><td>{esc(str(name))}</td><td>{n_mig}</td>"
        f"<td>{esc(str(migr_rate))}</td><td>{esc(str(avg_dwell))}</td><td>{n_cores}</td>"
        f"<td>{esc(str(primary))} ({primary_pct:.0f}%)</td><td>{ping}</td><td>{sti}</td>"
        f"<td>{esc(str(g_after))}</td><td>{esc(str(g_other))}</td></tr>"
    )

def _migration_rows(trace: "BtfTrace",
                    lo: Optional[int] = None, hi: Optional[int] = None
                    ) -> List[tuple]:
    """Rows for the Core Migrations stats table."""
    scale = trace.time_scale
    tick_times = trace.tick_sti_times
    rows: List[tuple] = []
    for mk in trace.tasks:
        if not _is_migrated_task(trace, mk):
            continue
        segs = trace.seg_map_by_merge_key.get(mk, [])
        migs = list(trace.migrations_by_mk.get(mk, ()))
        if lo is not None and hi is not None:
            migs = [m for m in migs if lo <= m.ns <= hi]
            if not migs and not any(_seg_overlaps_range(s, lo, hi) for s in segs):
                continue
        cores = _task_cores_used(trace, mk)
        cores_in_scope = _cores_in_scope(segs, migs, lo, hi)
        n_cores = len(cores_in_scope) if cores_in_scope else len(cores)
        core_time: Dict[str, int] = defaultdict(int)
        for s in segs:
            if lo is not None and hi is not None:
                if not _seg_overlaps_range(s, lo, hi):
                    continue
                ov_lo = max(s.start, lo)
                ov_hi = min(s.end, hi)
            else:
                ov_lo, ov_hi = s.start, s.end
            core_time[s.core] += max(0, ov_hi - ov_lo)
        total = sum(core_time.values())
        if total <= 0 and not migs:
            continue
        if total > 0:
            primary = max(core_time, key=core_time.get)
            primary_pct = 100.0 * core_time[primary] / total
        else:
            primary = sorted(cores, key=_core_sort_key_tuple)[0] if cores else "-"
            primary_pct = 0.0
        tick_count = _tick_count_for_task(segs, tick_times, lo, hi)
        ping = _count_ping_pong(migs)
        sti_near = _migration_sti_near_count(trace.sti_event_times, migs)
        gaps_after = [m.gap_ns for m in migs if m.gap_ns > 0]
        all_gaps = _blocking_time_samples(segs, lo, hi)
        avg_after = (sum(gaps_after) / len(gaps_after)) if gaps_after else 0
        avg_other = (sum(all_gaps) / len(all_gaps)) if all_gaps else 0
        dwell_samples = _core_dwell_samples(segs, lo, hi)
        avg_dwell_tu = int(round(sum(dwell_samples) / len(dwell_samples))) if dwell_samples else 0
        migr_rate, rate_per_s = _format_migration_rate(len(migs), total, tick_count, scale)
        avg_dwell = _format_time(avg_dwell_tu, scale) if avg_dwell_tu else "-"
        raw = trace.task_repr.get(mk, mk)
        disp = _task_display_name(raw)
        cores_str = ", ".join(sorted(cores_in_scope or cores, key=_core_sort_key_tuple))
        rows.append((
            mk, disp, len(migs), n_cores, cores_str, primary, primary_pct,
            ping, sti_near,
            _format_time(int(avg_after), scale) if avg_after else "-",
            _format_time(int(avg_other), scale) if avg_other else "-",
            migr_rate, rate_per_s, avg_dwell, avg_dwell_tu,
        ))
    rows.sort(key=lambda r: (-r[2], r[1].lower()))
    return rows

def _migration_dwell_plot_points(
    trace: "BtfTrace", mk: str,
    lo: Optional[int] = None, hi: Optional[int] = None,
) -> List[Tuple[int, int, "TaskSegment"]]:
    """One point per on-core run (clipped to scope): x = run start, y = duration."""
    segs = trace.seg_map_by_merge_key.get(mk, [])
    pts: List[Tuple[int, int, TaskSegment]] = []
    for s in segs:
        if lo is not None and hi is not None:
            if not _seg_overlaps_range(s, lo, hi):
                continue
            ov_lo, ov_hi = max(s.start, lo), min(s.end, hi)
        else:
            ov_lo, ov_hi = s.start, s.end
        dur = max(0, ov_hi - ov_lo)
        if dur > 0:
            pts.append((ov_lo, dur, s))
    return pts

def _migration_rate_plot_points(
    trace: "BtfTrace", mk: str,
    lo: Optional[int] = None, hi: Optional[int] = None,
) -> List[Tuple[int, int, "MigrationEvent"]]:
    """One point per consecutive migration-event pair: x = event time, y = gap since the previous migration."""
    migs = sorted(trace.migrations_by_mk.get(mk, ()), key=lambda m: m.ns)
    pts: List[Tuple[int, int, MigrationEvent]] = []
    for i in range(1, len(migs)):
        cur = migs[i]
        if lo is not None and hi is not None and (cur.ns < lo or cur.ns > hi):
            continue
        gap = cur.ns - migs[i - 1].ns
        if gap > 0:
            pts.append((cur.ns, gap, cur))
    return pts

def _migration_gap_plot_points(
    trace: "BtfTrace", mk: str,
    lo: Optional[int] = None, hi: Optional[int] = None,
) -> List[Tuple[int, int, "MigrationEvent"]]:
    """One point per migration event with a positive post-migration blocking gap."""
    migs = trace.migrations_by_mk.get(mk, ())
    pts: List[Tuple[int, int, MigrationEvent]] = []
    for m in migs:
        if lo is not None and hi is not None and (m.ns < lo or m.ns > hi):
            continue
        if m.gap_ns > 0:
            pts.append((m.ns, m.gap_ns, m))
    return pts

_TICK_HEALTH_PERIOD = 1000   # expected tick period in trace units (1 ms @ us scale)
_TICK_HEALTH_GAP_FACTOR = 2.0
# Coefficient-of-variation threshold for tickless-mode detection.
# In tick mode CV is near 0; tickless idle suppresses ticks during sleep
# so the interval distribution widens (CV grows above this threshold).
_TICK_HEALTH_TICKLESS_CV = 0.05
PREEMPTION_CHAIN_MAX_ROWS = 2000

def _collect_preemption_events(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[Tuple[str, str, int, int, "TaskSegment"]]:
    """Raw preemption events: (victim_mk, preemptor_disp, time_ns, duration_ns, preemptor_seg)."""
    core_segs: Dict[str, List["TaskSegment"]] = trace.core_segs
    core_starts: Dict[str, List[int]] = {
        c: [s.start for s in segs] for c, segs in core_segs.items()
    }
    events: List[Tuple[str, str, int, int, "TaskSegment"]] = []

    for mk, segs in trace.seg_map_by_merge_key.items():
        if len(segs) < 2:
            continue
        raw = trace.task_repr.get(mk, mk)
        _, _, tname = _parse_task_name(raw)
        if _is_idle_task_name(tname) or tname == "TICK":
            continue

        ordered = sorted(segs, key=lambda s: s.start)
        for i in range(1, len(ordered)):
            prev, nxt = ordered[i - 1], ordered[i]
            gap_start = prev.end
            gap_end = nxt.start
            if gap_end <= gap_start:
                continue
            if lo is not None and hi is not None:
                if not (_seg_fully_in_range(prev, lo, hi) and _seg_fully_in_range(nxt, lo, hi)):
                    continue

            # Preemptors ran on the same core the victim was on when descheduled.
            core = prev.core
            core_seg_list = core_segs.get(core)
            if not core_seg_list:
                continue
            starts = core_starts[core]
            i0 = bisect_right(starts, gap_end - 1)
            i_start = max(0, i0 - 1)
            for j in range(i_start, len(core_seg_list)):
                cs = core_seg_list[j]
                if cs.start >= gap_end:
                    break
                if cs.end <= gap_start:
                    continue
                preemptor_mk = _task_merge_key(cs.task)
                if preemptor_mk == mk:
                    continue
                pre_raw = trace.task_repr.get(preemptor_mk, cs.task)
                _, _, pre_tname = _parse_task_name(pre_raw)
                if _is_idle_task_name(pre_tname):
                    continue
                ov_lo = max(cs.start, gap_start)
                ov_hi = min(cs.end, gap_end)
                overlap = ov_hi - ov_lo
                if overlap <= 0:
                    continue
                pre_disp = _task_display_name(pre_raw)
                events.append((mk, pre_disp, ov_lo, overlap, cs))

    return events

def _preemption_chain_rows(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> Tuple[List[tuple], bool]:
    """For each task, find which tasks preempted it and how often/long.

    Returns (rows, truncated) where rows is a list of tuples:
        (victim_mk, victim_name, preemptor_name, count, total_str, avg_str, max_str)
    sorted by total preemption time descending.
    """
    scale = trace.time_scale
    data: Dict[str, Dict[str, List[int]]] = {}
    for mk, pre_disp, _t, duration, _seg in _collect_preemption_events(trace, lo, hi):
        data.setdefault(mk, {}).setdefault(pre_disp, []).append(duration)

    rows_raw = []
    for mk, preemptors in data.items():
        raw = trace.task_repr.get(mk, mk)
        victim_disp = _task_display_name(raw)
        for pre_disp, durations in preemptors.items():
            total = sum(durations)
            avg = int(round(total / len(durations)))
            mx = max(durations)
            rows_raw.append((mk, victim_disp, pre_disp, len(durations), total, avg, mx))

    # Sort by the exact raw total (not a formatted/rounded label) so rows whose
    # labels happen to display the same text still order by true magnitude.
    rows_raw.sort(key=lambda r: (-r[4], r[1].lower(), r[2].lower()))
    rows = [
        (
            mk, victim_disp, pre_disp, cnt,
            _format_time(total, scale), _format_time(avg, scale), _format_time(mx, scale),
        )
        for mk, victim_disp, pre_disp, cnt, total, avg, mx in rows_raw
    ]
    truncated = len(rows) > PREEMPTION_CHAIN_MAX_ROWS
    if truncated:
        rows = rows[:PREEMPTION_CHAIN_MAX_ROWS]
    return rows, truncated

def _preemption_chain_plot_points(
    trace: "BtfTrace",
    victim_mk: str,
    preemptor_disp: str,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[Tuple[int, int, "TaskSegment"]]:
    """Scatter points for one victim/preemptor pair: (time_ns, duration_ns, preemptor_seg)."""
    return [
        (t, d, seg)
        for mk, pre_disp, t, d, seg in _collect_preemption_events(trace, lo, hi)
        if mk == victim_mk and pre_disp == preemptor_disp
    ]

def _tick_health_report(trace: "BtfTrace",
                        lo: Optional[int] = None, hi: Optional[int] = None) -> dict:
    """Summarise STI TICK timestamps: gaps, missed-tick estimate, health status.

    Also detects tick vs tickless mode via coefficient of variation (CV) of
    tick intervals.  In tick mode all intervals are nearly constant (low CV);
    in tickless mode idle periods suppress ticks so the interval distribution
    widens (high CV).
    """
    times = trace.tick_sti_times
    if lo is not None and hi is not None:
        times = [t for t in times if lo <= t <= hi]
    if not times:
        return {"tick_count": 0, "health": "unknown", "large_gaps": [],
                "avg_period": 0, "max_gap": 0, "missed_estimate": 0,
                "is_tickless": False, "tick_deltas": [], "tick_cv": 0.0}

    threshold = _TICK_HEALTH_PERIOD * _TICK_HEALTH_GAP_FACTOR
    large_gaps = []
    tick_deltas = []
    sum_delta = 0
    max_gap = 0
    missed_total = 0
    for i in range(1, len(times)):
        delta = times[i] - times[i - 1]
        tick_deltas.append(delta)
        sum_delta += delta
        if delta > max_gap:
            max_gap = delta
        if delta > threshold:
            missed = max(0, round(delta / _TICK_HEALTH_PERIOD) - 1)
            missed_total += missed
            large_gaps.append((times[i - 1], times[i], delta, missed))

    n = len(tick_deltas)
    avg_period = sum_delta / n if n > 0 else _TICK_HEALTH_PERIOD

    # Tickless-mode detection via CV = stddev / mean
    tick_cv = 0.0
    if n > 1 and avg_period > 0:
        variance = sum((d - avg_period) ** 2 for d in tick_deltas) / n
        tick_cv = variance ** 0.5 / avg_period
    is_tickless = tick_cv > _TICK_HEALTH_TICKLESS_CV

    health = "good"
    if large_gaps:
        health = "critical" if max_gap / _TICK_HEALTH_PERIOD > 10 else "warning"
    return {
        "tick_count": len(times),
        "avg_period": int(round(avg_period)),
        "max_gap": max_gap,
        "large_gaps": large_gaps,
        "missed_estimate": missed_total,
        "health": health,
        "is_tickless": is_tickless,
        "tick_deltas": tick_deltas,
        "tick_cv": tick_cv,
    }

def _build_lock_bounce_migration_set(
    migrations_by_mk: Dict[str, list], sync_objects: Dict[str, dict]
) -> frozenset:
    """Return frozenset of migration timestamps (ns) that occurred while a mutex
    was held across two different cores (cache-line bounce migrations)."""
    bounce_ns: set = set()
    for obj in sync_objects.values():
        if obj["kind"] != "mutex":
            continue
        for hold in obj.get("holds", []):
            if not (hold.get("take_core") and hold.get("give_core")
                    and hold["take_core"] != hold["give_core"]):
                continue
            holder_mk = hold.get("holder_mk")
            if not holder_mk:
                continue
            t0, t1 = hold["start_ns"], hold["stop_ns"]
            for mig in migrations_by_mk.get(holder_mk, []):
                if t0 <= mig.ns <= t1:
                    bounce_ns.add(mig.ns)
    return frozenset(bounce_ns)


def _migration_heatmap_data(trace: "BtfTrace",
                            lo: Optional[int] = None, hi: Optional[int] = None,
                            time_bins: int = 32,
                            bounce_only: bool = False) -> Tuple[list, list, int]:
    """Core-pair rows × time bins grid for migration heatmap."""
    cores = trace.core_names
    pairs = []
    pair_idx: Dict[Tuple[str, str], int] = {}
    for fc in cores:
        for tc in cores:
            if fc != tc:
                pair_idx[(fc, tc)] = len(pairs)
                pairs.append((fc, tc,
                              f"{_core_short_name(fc)}→{_core_short_name(tc)}"))
    t_min = lo if lo is not None else trace.time_min
    t_hi = hi if hi is not None else trace.time_max
    span = max(t_hi - t_min, 1)
    bin_w = span / time_bins
    grid = [[0] * time_bins for _ in pairs]
    for m in trace.migrations:
        if bounce_only and m.ns not in trace.lock_bounce_migration_ns:
            continue
        if lo is not None and m.ns < lo:
            continue
        if hi is not None and m.ns > hi:
            continue
        pi = pair_idx.get((m.from_core, m.to_core))
        if pi is None:
            continue
        bi = _heatmap_bin_index_for_ns(
            t_min, bin_w, time_bins, t_hi, m.ns)
        grid[pi][bi] += 1
    return pairs, grid, time_bins

_MIGRATION_HEATMAP_MATRIX_CORE_THRESHOLD = 16

def _migration_heatmap_uses_matrix(trace: "BtfTrace") -> bool:
    return len(trace.core_names) > _MIGRATION_HEATMAP_MATRIX_CORE_THRESHOLD

def _migration_heatmap_matrix(trace: "BtfTrace",
                              lo: Optional[int] = None, hi: Optional[int] = None,
                              bounce_only: bool = False) -> Tuple[list, list]:
    """Source × destination core counts (one row per source core)."""
    cores = trace.core_names
    n = len(cores)
    core_idx = {c: i for i, c in enumerate(cores)}
    grid = [[0] * n for _ in range(n)]
    for m in trace.migrations:
        if bounce_only and m.ns not in trace.lock_bounce_migration_ns:
            continue
        if lo is not None and m.ns < lo:
            continue
        if hi is not None and m.ns > hi:
            continue
        fi = core_idx.get(m.from_core)
        ti = core_idx.get(m.to_core)
        if fi is None or ti is None or fi == ti:
            continue
        grid[fi][ti] += 1
    return cores, grid

# Gap between adjacent core arcs and floor arc size in the chord diagram, in radians.
_CHORD_GAP_RAD = 0.03
_CHORD_MIN_ARC_RAD = 0.05

@dataclass
class ChordArc:
    """One core's arc segment in the migration chord diagram."""
    core: str
    index: int
    start_angle: float
    end_angle: float
    total: float

@dataclass
class ChordLayout:
    """Circular layout for the migration chord diagram (see _build_chord_layout)."""
    arcs: List[ChordArc]
    # tick_angles[i][j] = angle (radians) on core i's arc pointing toward core j.
    tick_angles: List[Dict[int, float]]

    def tick_angle(self, i: int, j: int) -> float:
        if 0 <= i < len(self.tick_angles) and j in self.tick_angles[i]:
            return self.tick_angles[i][j]
        if 0 <= i < len(self.arcs):
            arc = self.arcs[i]
            return (arc.start_angle + arc.end_angle) / 2
        return 0.0

def _build_chord_layout(cores: List[str], grid: List[List[float]]) -> ChordLayout:
    """Pure circular layout for the migration chord diagram — parity with the
    web app's buildChordLayout() in migrationAnalysis.js. Each core gets an arc
    sized proportionally to its total in+out migration volume (with a minimum
    sliver so zero-flow cores still appear as nodes), separated by a fixed gap.
    Each connected core-pair also gets a tick position within its two arcs,
    used as chord endpoints so parallel migrations fan out rather than
    overlapping."""
    n = len(cores)
    totals = [0.0] * n
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            gij = grid[i][j] if i < len(grid) and j < len(grid[i]) else 0
            gji = grid[j][i] if j < len(grid) and i < len(grid[j]) else 0
            totals[i] += gij + gji
    grand_total = sum(totals)
    gap = min(_CHORD_GAP_RAD, (math.pi * 1.5) / n) if n > 0 else 0.0
    available = max(0.0, 2 * math.pi - gap * n)
    min_arc = min(_CHORD_MIN_ARC_RAD, available / n) if n > 0 else 0.0

    floor_total = min_arc * n
    remaining = max(0.0, available - floor_total)
    if grand_total > 0:
        arc_sizes = [min_arc + remaining * (t / grand_total) for t in totals]
    else:
        arc_sizes = [min_arc + remaining / n for _ in totals] if n > 0 else []

    arcs: List[ChordArc] = []
    angle = -math.pi / 2
    for i in range(n):
        start_angle = angle
        end_angle = start_angle + arc_sizes[i]
        arcs.append(ChordArc(cores[i], i, start_angle, end_angle, totals[i]))
        angle = end_angle + gap

    tick_angles: List[Dict[int, float]] = [dict() for _ in range(n)]
    for i in range(n):
        arc = arcs[i]
        links = []
        for j in range(n):
            if j == i:
                continue
            gij = grid[i][j] if i < len(grid) and j < len(grid[i]) else 0
            gji = grid[j][i] if j < len(grid) and i < len(grid[j]) else 0
            mag = gij + gji
            if mag > 0:
                links.append((j, mag))
        link_total = sum(m for _, m in links)
        span = arc.end_angle - arc.start_angle
        cursor = arc.start_angle
        for j, mag in links:
            sl = span * (mag / link_total) if link_total > 0 else span / len(links)
            tick_angles[i][j] = cursor + sl / 2
            cursor += sl

    return ChordLayout(arcs=arcs, tick_angles=tick_angles)

def _migration_core_outgoing_heatmap(trace: "BtfTrace", from_core: str,
                                     lo: Optional[int] = None, hi: Optional[int] = None,
                                     time_bins: int = 32) -> Tuple[list, list, int, int, int, float]:
    """Time bins for all outgoing pairs from one source core (matrix row drill-down)."""
    cores = trace.core_names
    pairs = []
    pair_idx: Dict[str, int] = {}
    for tc in cores:
        if tc == from_core:
            continue
        pair_idx[tc] = len(pairs)
        pairs.append((from_core, tc,
                      f"{_core_short_name(from_core)}→{_core_short_name(tc)}"))
    t_min = lo if lo is not None else trace.time_min
    t_hi = hi if hi is not None else trace.time_max
    span = max(t_hi - t_min, 1)
    bin_w = span / time_bins
    grid = [[0] * time_bins for _ in pairs]
    for m in trace.migrations:
        if m.from_core != from_core:
            continue
        if lo is not None and m.ns < lo:
            continue
        if hi is not None and m.ns > hi:
            continue
        pi = pair_idx.get(m.to_core)
        if pi is None:
            continue
        bi = _heatmap_bin_index_for_ns(t_min, bin_w, time_bins, t_hi, m.ns)
        grid[pi][bi] += 1
    return pairs, grid, time_bins, t_min, t_hi, bin_w

def _migration_pair_time_bins(trace: "BtfTrace", from_core: str, to_core: str,
                              lo: Optional[int] = None, hi: Optional[int] = None,
                              time_bins: int = 32) -> Tuple[list, list, int, int, int, float]:
    """Time bins for one directed core pair (matrix drill-down)."""
    t_min = lo if lo is not None else trace.time_min
    t_hi = hi if hi is not None else trace.time_max
    span = max(t_hi - t_min, 1)
    bin_w = span / time_bins
    bins = [0] * time_bins
    for m in trace.migrations:
        if m.from_core != from_core or m.to_core != to_core:
            continue
        if lo is not None and m.ns < lo:
            continue
        if hi is not None and m.ns > hi:
            continue
        bi = _heatmap_bin_index_for_ns(t_min, bin_w, time_bins, t_hi, m.ns)
        bins[bi] += 1
    label = f"{_core_short_name(from_core)}→{_core_short_name(to_core)}"
    pairs = [(from_core, to_core, label)]
    return pairs, [bins], time_bins, t_min, t_hi, bin_w

def _heatmap_bin_range(t_min: int, bin_w: float, time_bins: int, t_max: int,
                       bin_index: int) -> Tuple[int, int]:
    bin_lo = int(t_min + bin_index * bin_w)
    bin_hi = t_max if bin_index >= time_bins - 1 else int(t_min + (bin_index + 1) * bin_w)
    return bin_lo, bin_hi

def _migration_ns_in_bin(ns: int, bin_lo: int, bin_hi: int, *,
                         bin_index: int, time_bins: int) -> bool:
    """Half-open [bin_lo, bin_hi) except the last bin includes bin_hi."""
    if ns < bin_lo:
        return False
    if bin_index >= time_bins - 1:
        return ns <= bin_hi
    return ns < bin_hi

def _heatmap_bin_index_for_ns(t_min: int, bin_w: float, time_bins: int, t_max: int,
                              ns: int) -> int:
    """Bin index for ns; retries bi+1 when int division lands on an upper boundary."""
    bi = min(time_bins - 1, max(0, int((ns - t_min) / bin_w)))
    for b in (bi, bi + 1):
        if b >= time_bins:
            continue
        blo, bhi = _heatmap_bin_range(t_min, bin_w, time_bins, t_max, b)
        if _migration_ns_in_bin(ns, blo, bhi, bin_index=b, time_bins=time_bins):
            return b
    return bi

def _range_stats_over_segments(trace: "BtfTrace", lo: int, hi: int
                               ) -> Tuple[int, Dict[str, int], list]:
    """Segments overlapping [lo, hi]: count, per-task overlap ns, slice durations."""
    switches = 0
    task_acc: Dict[str, int] = {}
    durations: list = []
    for mk, segs in trace.seg_map_by_merge_key.items():
        starts = trace.seg_start_by_merge_key.get(mk)
        if not starts:
            continue
        i0 = max(0, bisect_left(starts, lo) - 1)
        for j in range(i0, len(segs)):
            seg = segs[j]
            if seg.start >= hi:
                break
            if seg.end <= lo:
                continue
            ov = min(seg.end, hi) - max(seg.start, lo)
            if ov <= 0:
                continue
            switches += 1
            durations.append(seg.end - seg.start)
            raw = trace.task_repr.get(mk, mk)
            disp = _task_display_name(raw)
            task_acc[disp] = task_acc.get(disp, 0) + ov
    return switches, task_acc, durations

def _merge_keys_for_heatmap_cell(trace: "BtfTrace", from_core: str, to_core: str,
                                 bin_lo: int, bin_hi: int,
                                 bin_index: int, time_bins: int) -> set:
    keys: set = set()
    for m in trace.migrations:
        if m.from_core != from_core or m.to_core != to_core:
            continue
        if not _migration_ns_in_bin(m.ns, bin_lo, bin_hi,
                                    bin_index=bin_index, time_bins=time_bins):
            continue
        keys.add(m.merge_key)
    return keys

def _migration_task_heatmap_data(trace: "BtfTrace", from_core: str, to_core: str,
                                 bin_lo: int, bin_hi: int,
                                 time_bins: int = 32,
                                 parent_bin_index: int = 0,
                                 parent_time_bins: int = 32) -> Tuple[list, list, int, int, int, float]:
    """Task rows × sub-bins for one core-pair / time-bin drill-down."""
    t_min, t_hi = bin_lo, bin_hi
    span = max(t_hi - t_min, 1)
    bin_w = span / time_bins
    task_bins: Dict[str, List[int]] = {}
    for m in trace.migrations:
        if m.from_core != from_core or m.to_core != to_core:
            continue
        if not _migration_ns_in_bin(m.ns, bin_lo, bin_hi,
                                    bin_index=parent_bin_index,
                                    time_bins=parent_time_bins):
            continue
        mk = m.merge_key
        if mk not in task_bins:
            task_bins[mk] = [0] * time_bins
        bi = _heatmap_bin_index_for_ns(t_min, bin_w, time_bins, t_hi, m.ns)
        task_bins[mk][bi] += 1
    items = sorted(task_bins.items(),
                   key=lambda x: (-sum(x[1]), x[0]))
    rows: list = []
    grid: list = []
    for mk, counts in items:
        raw = trace.task_repr.get(mk, mk)
        rows.append((mk, _task_display_name(raw)))
        grid.append(counts)
    return rows, grid, time_bins, t_min, t_hi, bin_w

def _trace_summary_snapshot(trace: "BtfTrace",
                            lo: Optional[int] = None, hi: Optional[int] = None) -> dict:
    """Summary metrics for trace compare (optional cursor scope)."""
    full_span = trace.time_max - trace.time_min
    span = max(0, hi - lo) if lo is not None and hi is not None else full_span
    sti = sum(
        1 for ev in trace.sti_events
        if not _is_tag_sti_channel(ev.target)
        and (lo is None or hi is None or (lo <= ev.time <= hi))
    )
    ctx, gaps = _scheduling_stats(trace, lo, hi)
    gap_avg = int(round(sum(gaps) / len(gaps))) if gaps else 0
    gap_max = max(gaps) if gaps else 0
    if lo is not None and hi is not None:
        migrations = sum(1 for m in trace.migrations if lo <= m.ns <= hi)
        mig_tasks = len(_migration_rows(trace, lo, hi))
        segments = sum(
            1 for s in trace.segments if s.end > lo and s.start < hi)
    else:
        migrations = len(trace.migrations)
        mig_tasks = sum(1 for mk in trace.tasks if _is_migrated_task(trace, mk))
        segments = len(trace.segments)
    return {
        "span_ns": span,
        "tasks": len(trace.tasks),
        "segments": segments,
        "sti_events": sti,
        "context_switches": ctx,
        "gap_avg_ns": gap_avg,
        "gap_max_ns": gap_max,
        "migrations": migrations,
        "migrated_tasks": mig_tasks,
        "time_scale": trace.time_scale,
    }

def _top_tasks_cpu_by_name(trace: "BtfTrace", limit: int = 10,
                           lo: Optional[int] = None, hi: Optional[int] = None) -> Dict[str, float]:
    """Top tasks by CPU%, keyed by display name."""
    if lo is not None and hi is not None:
        total_ns = max(1, hi - lo)
    else:
        total_ns = trace.time_max - trace.time_min
    if total_ns <= 0:
        return {}
    task_times: Dict[str, int] = {}
    for mk, segs in trace.seg_map_by_merge_key.items():
        raw = trace.task_repr.get(mk, mk)
        _, _, tname = _parse_task_name(raw)
        if _is_idle_task_name(tname) or tname == "TICK":
            continue
        t_ns = 0
        for s in segs:
            if lo is not None and hi is not None:
                if s.end <= lo or s.start >= hi:
                    continue
                t_ns += min(s.end, hi) - max(s.start, lo)
            else:
                t_ns += s.end - s.start
        if t_ns > 0:
            task_times[mk] = t_ns
    result: Dict[str, float] = {}
    for mk, t_ns in sorted(task_times.items(), key=lambda kv: kv[1], reverse=True)[:limit]:
        raw = trace.task_repr.get(mk, mk)
        result[_task_display_name(raw)] = 100.0 * t_ns / total_ns
    return result

def _blocking_compare_by_name(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> Dict[str, dict]:
    """Blocking-time summary keyed by task display name."""
    scale = trace.time_scale
    out: Dict[str, dict] = {}
    for mk, segs in trace.seg_map_by_merge_key.items():
        samples = _blocking_time_samples(segs, lo, hi)
        if not samples:
            continue
        raw = trace.task_repr.get(mk, mk)
        _, _, tname = _parse_task_name(raw)
        if _is_idle_task_name(tname) or tname == "TICK":
            continue
        avg_ns = int(round(sum(samples) / len(samples)))
        out[_task_display_name(raw)] = {
            "gaps": len(samples),
            "avg_ns": avg_ns,
            "avg": _format_time(avg_ns, scale),
        }
    return out

def _preemption_totals_by_victim(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> Dict[str, dict]:
    """Aggregate preemption events by victim task display name."""
    totals: Dict[str, dict] = {}
    for mk, _pre_disp, _t, duration, _seg in _collect_preemption_events(trace, lo, hi):
        raw = trace.task_repr.get(mk, mk)
        victim = _task_display_name(raw)
        cur = totals.setdefault(victim, {"count": 0, "total_ns": 0})
        cur["count"] += 1
        cur["total_ns"] += duration
    return totals

def _sync_compare_summary(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> dict:
    if not trace.has_sync_object_instrumentation:
        return {"objects": 0, "holds": 0, "issues": 0, "queue": 0, "mutex": 0, "sem": 0}
    rows = _sync_object_stats_rows(trace, lo, hi)
    out = {"objects": len(rows), "holds": 0, "issues": 0, "queue": 0, "mutex": 0, "sem": 0}
    for row in rows:
        out["holds"] += row[4]
        out["issues"] += row[5]
        kind = row[1]
        if kind == "queue":
            out["queue"] += 1
        elif kind == "mutex":
            out["mutex"] += 1
        elif kind == "sem":
            out["sem"] += 1
    return out

def _cursor_range_for_tab(win: "MainWindow", tab_idx: int) -> Tuple[Optional[int], Optional[int]]:
    """Return (lo, hi) from a tab's placed cursors, or (None, None) if fewer than 2."""
    if tab_idx < 0 or tab_idx >= len(win._tabs):
        return None, None
    times = win._tabs[tab_idx].view._scene.cursor_times()
    if len(times) < 2:
        return None, None
    sorted_t = sorted(times)
    return sorted_t[0], sorted_t[-1]

def _fmt_signed_time_delta(delta_ns: int, scale: str) -> str:
    if delta_ns == 0:
        return "0"
    sign = "+" if delta_ns >= 0 else "−"
    return f"{sign}{_format_time(abs(delta_ns), scale)}"

def _fmt_signed_int_delta(delta: int) -> str:
    if delta == 0:
        return "0"
    return f"+{delta}" if delta > 0 else str(delta)

def _fmt_signed_pct_delta(delta: float) -> str:
    if abs(delta) < 0.05:
        return "0.0"
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.1f}"

def _fmt_signed_rate_delta(rate_a: float, rate_b: float) -> str:
    if rate_a < 0 or rate_b < 0:
        return "—"
    delta = rate_a - rate_b
    if abs(delta) < 0.005:
        return "0"
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.2f}/s"

def _fmt_signed_dwell_delta(dwell_a: int, dwell_b: int, scale: str) -> str:
    if dwell_a < 0 or dwell_b < 0:
        return "—"
    delta = dwell_a - dwell_b
    if delta == 0:
        return "0"
    sign = "+" if delta > 0 else "−"
    return f"{sign}{_format_time(abs(delta), scale)}"

def _build_trace_compare_rows(
    trace_a: "BtfTrace",
    trace_b: "BtfTrace",
    lo_a: Optional[int] = None,
    hi_a: Optional[int] = None,
    lo_b: Optional[int] = None,
    hi_b: Optional[int] = None,
) -> Tuple[List[List], List[List], List[List], List[List], List[List], List[List]]:
    """Summary, top-task, migration, blocking, preemption, and sync compare tables."""
    a = _trace_summary_snapshot(trace_a, lo_a, hi_a)
    b = _trace_summary_snapshot(trace_b, lo_b, hi_b)
    scale = a["time_scale"]
    summary_rows = [
        ["Span",
         _format_time(a["span_ns"], scale),
         _format_time(b["span_ns"], scale),
         _fmt_signed_time_delta(a["span_ns"] - b["span_ns"], scale)],
        ["Tasks", a["tasks"], b["tasks"], _fmt_signed_int_delta(a["tasks"] - b["tasks"])],
        ["Segments", a["segments"], b["segments"],
         _fmt_signed_int_delta(a["segments"] - b["segments"])],
        ["STI events", a["sti_events"], b["sti_events"],
         _fmt_signed_int_delta(a["sti_events"] - b["sti_events"])],
        ["Context switches", a["context_switches"], b["context_switches"],
         _fmt_signed_int_delta(a["context_switches"] - b["context_switches"])],
        ["Core gap avg",
         _format_time(a["gap_avg_ns"], scale),
         _format_time(b["gap_avg_ns"], scale),
         _fmt_signed_time_delta(a["gap_avg_ns"] - b["gap_avg_ns"], scale)],
        ["Core gap max",
         _format_time(a["gap_max_ns"], scale),
         _format_time(b["gap_max_ns"], scale),
         _fmt_signed_time_delta(a["gap_max_ns"] - b["gap_max_ns"], scale)],
        ["Migrations (total)", a["migrations"], b["migrations"],
         _fmt_signed_int_delta(a["migrations"] - b["migrations"])],
        ["Migrated tasks", a["migrated_tasks"], b["migrated_tasks"],
         _fmt_signed_int_delta(a["migrated_tasks"] - b["migrated_tasks"])],
    ]

    map_a = _top_tasks_cpu_by_name(trace_a, lo=lo_a, hi=hi_a)
    map_b = _top_tasks_cpu_by_name(trace_b, lo=lo_b, hi=hi_b)
    names = sorted(set(map_a) | set(map_b),
                   key=lambda n: (-max(map_a.get(n, 0.0), map_b.get(n, 0.0)), n.lower()))
    top_rows: List[List] = []
    for name in names:
        pa = map_a.get(name)
        pb = map_b.get(name)
        a_val = pa if pa is not None else 0.0
        b_val = pb if pb is not None else 0.0
        top_rows.append([
            name,
            f"{pa:.1f}" if pa is not None else "—",
            f"{pb:.1f}" if pb is not None else "—",
            _fmt_signed_pct_delta(a_val - b_val),
        ])

    rows_a = {r[0]: r for r in _migration_rows(trace_a, lo_a, hi_a)}
    rows_b = {r[0]: r for r in _migration_rows(trace_b, lo_b, hi_b)}
    keys = sorted(set(rows_a) | set(rows_b),
                  key=lambda k: rows_a.get(k, rows_b.get(k))[1].lower())
    mig_rows: List[List] = []
    for mk in keys:
        ra = rows_a.get(mk)
        rb = rows_b.get(mk)
        name = (ra or rb)[1]
        ma = ra[2] if ra else 0
        mb = rb[2] if rb else 0
        ra_rate = ra[11] if ra else "—"
        rb_rate = rb[11] if rb else "—"
        ra_dwell = ra[13] if ra else "—"
        rb_dwell = rb[13] if rb else "—"
        ra_rps = ra[12] if ra else -1.0
        rb_rps = rb[12] if rb else -1.0
        ra_dtu = ra[14] if ra else -1
        rb_dtu = rb[14] if rb else -1
        pa = ra[7] if ra else 0
        pb = rb[7] if rb else 0
        mig_rows.append([
            name, ma, mb, ma - mb, ra_rate, rb_rate,
            _fmt_signed_rate_delta(ra_rps, rb_rps),
            ra_dwell, rb_dwell, _fmt_signed_dwell_delta(ra_dtu, rb_dtu, scale),
            pa, pb,
        ])

    block_a = _blocking_compare_by_name(trace_a, lo_a, hi_a)
    block_b = _blocking_compare_by_name(trace_b, lo_b, hi_b)
    block_names = sorted(
        set(block_a) | set(block_b),
        key=lambda n: (-max(block_a.get(n, {}).get("gaps", 0),
                            block_b.get(n, {}).get("gaps", 0)), n.lower()),
    )[:15]
    block_rows: List[List] = []
    for name in block_names:
        ba = block_a.get(name)
        bb = block_b.get(name)
        avg_a = ba["avg_ns"] if ba else 0
        avg_b = bb["avg_ns"] if bb else 0
        block_rows.append([
            name,
            ba["gaps"] if ba else 0,
            bb["gaps"] if bb else 0,
            ba["avg"] if ba else "—",
            bb["avg"] if bb else "—",
            _fmt_signed_time_delta(avg_a - avg_b, scale),
        ])

    pre_a = _preemption_totals_by_victim(trace_a, lo_a, hi_a)
    pre_b = _preemption_totals_by_victim(trace_b, lo_b, hi_b)
    pre_names = sorted(
        set(pre_a) | set(pre_b),
        key=lambda n: (-max(pre_a.get(n, {}).get("count", 0),
                            pre_b.get(n, {}).get("count", 0)), n.lower()),
    )[:15]
    pre_rows: List[List] = []
    for name in pre_names:
        pa = pre_a.get(name)
        pb = pre_b.get(name)
        ca = pa["count"] if pa else 0
        cb = pb["count"] if pb else 0
        pre_rows.append([
            name,
            ca,
            cb,
            _fmt_signed_int_delta(ca - cb),
            _format_time(pa["total_ns"], scale) if pa else "—",
            _format_time(pb["total_ns"], scale) if pb else "—",
        ])

    sa = _sync_compare_summary(trace_a, lo_a, hi_a)
    sb = _sync_compare_summary(trace_b, lo_b, hi_b)
    sync_rows = [
        ["Sync objects", sa["objects"], sb["objects"],
         _fmt_signed_int_delta(sa["objects"] - sb["objects"])],
        ["Holds (paired)", sa["holds"], sb["holds"],
         _fmt_signed_int_delta(sa["holds"] - sb["holds"])],
        ["Issues", sa["issues"], sb["issues"],
         _fmt_signed_int_delta(sa["issues"] - sb["issues"])],
        ["Mutex objects", sa["mutex"], sb["mutex"],
         _fmt_signed_int_delta(sa["mutex"] - sb["mutex"])],
        ["Semaphore objects", sa["sem"], sb["sem"],
         _fmt_signed_int_delta(sa["sem"] - sb["sem"])],
        ["Queue objects", sa["queue"], sb["queue"],
         _fmt_signed_int_delta(sa["queue"] - sb["queue"])],
    ]

    return summary_rows, top_rows, mig_rows, block_rows, pre_rows, sync_rows

_CSV_FORMULA_LEAD_CHARS = ("=", "+", "-", "@", "\t", "\r")

def _csv_sanitize_cell(v: object) -> object:
    """Neutralize CSV/spreadsheet formula injection (CWE-1236).

    Trace-derived strings (task/object names, labels) are attacker-controllable;
    if a value begins with =, +, -, @ (or a tab/CR) and the exported CSV is later
    opened in Excel/Sheets, it can be interpreted as a formula. Prefix with a
    leading apostrophe to force text interpretation; non-strings pass through.
    """
    if isinstance(v, str) and v.startswith(_CSV_FORMULA_LEAD_CHARS):
        return "'" + v
    return v


class _SafeCsvWriter:
    """csv.writer wrapper that sanitizes every cell against formula injection (CWE-1236)."""
    def __init__(self, fh, **kwargs):
        self._writer = csv.writer(fh, **kwargs)

    def writerow(self, row):
        self._writer.writerow(_csv_sanitize_cell(c) for c in row)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


def _compare_csv_cell(v: object) -> str:
    s = str(_csv_sanitize_cell(v))
    if any(c in s for c in '",\n\r'):
        return '"' + s.replace('"', '""') + '"'
    return s

def _table_widget_rows(table: "QTableWidget") -> List[List[str]]:
    rows: List[List[str]] = []
    for ri in range(table.rowCount()):
        row: List[str] = []
        for ci in range(table.columnCount()):
            item = table.item(ri, ci)
            row.append(item.text() if item else "")
        rows.append(row)
    return rows

def _build_compare_csv(name_a: str, name_b: str, scope_enabled: bool,
                         summary: List[List], top: List[List],
                         mig: List[List],
                         blocking: Optional[List[List]] = None,
                         preemption: Optional[List[List]] = None,
                         sync: Optional[List[List]] = None) -> str:
    lines: List[str] = []
    lines.append(f"Trace A,{_compare_csv_cell(name_a)}")
    lines.append(f"Trace B,{_compare_csv_cell(name_b)}")
    lines.append(f"Cursor scope per tab,{'yes' if scope_enabled else 'no'}")
    lines.append("")

    lines.append("Summary")
    lines.append("Metric,Trace A,Trace B,Δ")
    for row in summary:
        if len(row) >= 4:
            lines.append(",".join(_compare_csv_cell(c) for c in row[:4]))

    lines.append("")
    lines.append("Top Tasks")
    lines.append("Task,CPU% A,CPU% B,Δ")
    for row in top:
        if len(row) >= 4:
            lines.append(",".join(_compare_csv_cell(c) for c in row[:4]))

    lines.append("")
    lines.append("Core Migrations")
    lines.append("Task,Migrations A,Migrations B,Δ,Rate A,Rate B,Rate Δ,Dwell A,Dwell B,Dwell Δ,Ping-pong A,Ping-pong B")
    for row in mig:
        if len(row) >= 12:
            lines.append(",".join(_compare_csv_cell(c) for c in row[:12]))

    if blocking:
        lines.append("")
        lines.append("Blocking Time")
        lines.append("Task,Gaps A,Gaps B,Avg A,Avg B,Δ avg")
        for row in blocking:
            if len(row) >= 6:
                lines.append(",".join(_compare_csv_cell(c) for c in row[:6]))

    if preemption:
        lines.append("")
        lines.append("Preemption Chains")
        lines.append("Victim,Count A,Count B,Δ,Total A,Total B")
        for row in preemption:
            if len(row) >= 6:
                lines.append(",".join(_compare_csv_cell(c) for c in row[:6]))

    if sync:
        lines.append("")
        lines.append("Sync Objects")
        lines.append("Metric,Trace A,Trace B,Δ")
        for row in sync:
            if len(row) >= 4:
                lines.append(",".join(_compare_csv_cell(c) for c in row[:4]))

    return "\n".join(lines)

_COMPARE_HTML_STYLE = """
  :root { --bg:#e9edf3; --paper:#fff; --ink:#182230; --muted:#5f6f82; --line:#d9e0ea; --header:#16324f; }
  * { box-sizing:border-box; }
  body { margin:0; padding:28px; font-family:"Segoe UI",Arial,sans-serif; color:var(--ink); background:var(--bg); }
  .report { max-width:960px; margin:0 auto; }
  .report-head { background:linear-gradient(135deg,var(--header),#21496f); color:#f3f7fd; border-radius:14px; padding:20px 24px; margin-bottom:18px; }
  h1 { margin:0; font-size:26px; }
  .sub { margin-top:6px; color:#cfe1f7; font-size:13px; }
  .report-card { margin:14px 0; background:var(--paper); border:1px solid var(--line); border-radius:12px; padding:12px 14px; }
  h2 { margin:0 0 10px; color:#123355; font-size:17px; }
  table { border-collapse:collapse; width:100%; }
  th,td { border-bottom:1px solid var(--line); padding:8px 10px; font-size:13px; text-align:right; }
  th:first-child,td:first-child { text-align:left; }
  thead th { background:#f1f5fb; font-weight:600; }
  tbody tr:nth-child(even) td { background:#f7f9fc; }
  .empty { text-align:center; color:var(--muted); }
"""

def _build_compare_html(name_a: str, name_b: str, scope_enabled: bool,
                        summary: List[List], top: List[List],
                        mig: List[List],
                        blocking: Optional[List[List]] = None,
                        preemption: Optional[List[List]] = None,
                        sync: Optional[List[List]] = None) -> str:
    scope_note = (
        "Each side uses its own tab cursor range (C1–Cn) when 2+ cursors are placed."
        if scope_enabled else "Full trace span on each side.")

    def _esc(v: object) -> str:
        return html.escape(str(v), quote=True)

    def _rows_html(rows: List[List], cols: int, empty: str) -> str:
        if not rows:
            return f'<tr><td colspan="{cols}" class="empty">{_esc(empty)}</td></tr>'
        parts = []
        for row in rows:
            cells = "".join(f"<td>{_esc(c)}</td>" for c in row[:cols])
            parts.append(f"<tr>{cells}</tr>")
        return "".join(parts)

    summary_body = _rows_html(summary, 4, "No data")
    top_body = _rows_html(top, 4, "No user tasks in either trace")
    mig_body = _rows_html(mig, 12, "No migrated tasks in either trace")
    block_body = _rows_html(blocking or [], 6, "No blocking samples in either trace")
    pre_body = _rows_html(preemption or [], 6, "No preemption chains in either trace")
    sync_body = _rows_html(sync or [], 4, "No sync instrumentation in either trace")

    return f"""<!doctype html>
<html><head><meta charset="utf-8"/><title>BTF Trace Compare</title>
<style>{_COMPARE_HTML_STYLE}</style></head>
<body><div class="report">
  <header class="report-head">
    <h1>Trace Compare</h1>
    <div class="sub">{_esc(name_a)} vs {_esc(name_b)} · {_esc(scope_note)}</div>
  </header>
  <section class="report-card"><h2>Summary</h2>
    <table><thead><tr><th>Metric</th><th>Trace A</th><th>Trace B</th><th>Δ</th></tr></thead>
    <tbody>{summary_body}</tbody></table>
  </section>
  <section class="report-card"><h2>Top Tasks</h2>
    <table><thead><tr><th>Task</th><th>CPU% A</th><th>CPU% B</th><th>Δ</th></tr></thead>
    <tbody>{top_body}</tbody></table>
  </section>
  <section class="report-card"><h2>Core Migrations</h2>
    <table><thead><tr><th>Task</th><th>Migr A</th><th>Migr B</th><th>Δ</th><th>Rate A</th><th>Rate B</th><th>Rate Δ</th><th>Dwell A</th><th>Dwell B</th><th>Dwell Δ</th><th>Ping A</th><th>Ping B</th></tr></thead>
    <tbody>{mig_body}</tbody></table>
  </section>
  <section class="report-card"><h2>Blocking Time</h2>
    <table><thead><tr><th>Task</th><th>Gaps A</th><th>Gaps B</th><th>Avg A</th><th>Avg B</th><th>Δ avg</th></tr></thead>
    <tbody>{block_body}</tbody></table>
  </section>
  <section class="report-card"><h2>Preemption Chains</h2>
    <table><thead><tr><th>Victim</th><th>Count A</th><th>Count B</th><th>Δ</th><th>Total A</th><th>Total B</th></tr></thead>
    <tbody>{pre_body}</tbody></table>
  </section>
  <section class="report-card"><h2>Sync Objects</h2>
    <table><thead><tr><th>Metric</th><th>Trace A</th><th>Trace B</th><th>Δ</th></tr></thead>
    <tbody>{sync_body}</tbody></table>
  </section>
</div></body></html>"""

def _core_sort_key_tuple(c: str) -> tuple:
    if c.startswith("Core_"):
        tail = c[5:]
        return (0, int(tail) if tail.isdigit() else sys.maxsize, c)
    return (1, sys.maxsize, c)

def _core_short_name(core: str) -> str:
    """Short core label for heatmap rows, e.g. Core_0 -> c0."""
    if core.startswith("Core_"):
        tail = core[5:]
        if tail.isdigit():
            return f"c{tail}"
    return core

def _trace_is_multi_core(trace: "BtfTrace") -> bool:
    return len(trace.core_names) >= 2

def _find_wcet_segment(segs: list,
                       lo: Optional[int] = None, hi: Optional[int] = None
                       ) -> Optional[TaskSegment]:
    """Return the longest-duration slice in *segs* (respecting cursor scope)."""
    best: Optional[TaskSegment] = None
    best_d = 0
    for s in segs:
        d = s.end - s.start
        if d <= 0:
            continue
        if lo is not None and hi is not None and not _seg_fully_in_range(s, lo, hi):
            continue
        if d > best_d:
            best_d = d
            best = s
    return best

def _find_bcet_segment(segs: list,
                       lo: Optional[int] = None, hi: Optional[int] = None
                       ) -> Optional[TaskSegment]:
    """Return the shortest-duration slice in *segs* (respecting cursor scope)."""
    best: Optional[TaskSegment] = None
    best_d: Optional[int] = None
    for s in segs:
        d = s.end - s.start
        if d <= 0:
            continue
        if lo is not None and hi is not None and not _seg_fully_in_range(s, lo, hi):
            continue
        if best_d is None or d < best_d:
            best_d = d
            best = s
    return best

def _find_extreme_blocking_segment(segs: list,
                                   lo: Optional[int] = None, hi: Optional[int] = None,
                                   find_max: bool = True) -> Optional[TaskSegment]:
    """Return the resume slice for the min/max off-CPU gap between activations."""
    if len(segs) < 2:
        return None
    ordered = sorted(segs, key=lambda s: s.start)
    best_seg: Optional[TaskSegment] = None
    best_gap: Optional[int] = None
    for i in range(1, len(ordered)):
        prev, nxt = ordered[i - 1], ordered[i]
        if lo is not None and hi is not None:
            if not (_seg_fully_in_range(prev, lo, hi) and _seg_fully_in_range(nxt, lo, hi)):
                continue
        gap = nxt.start - prev.end
        if gap <= 0:
            continue
        if best_gap is None or (gap > best_gap if find_max else gap < best_gap):
            best_gap = gap
            best_seg = nxt
    return best_seg

def _find_extreme_inter_arrival_segment(segs: list,
                                        lo: Optional[int] = None, hi: Optional[int] = None,
                                        find_max: bool = True) -> Optional[TaskSegment]:
    """Return the activation slice for the min/max inter-arrival gap."""
    if len(segs) < 2:
        return None
    ordered = sorted(segs, key=lambda s: s.start)
    best_seg: Optional[TaskSegment] = None
    best_gap: Optional[int] = None
    for i in range(1, len(ordered)):
        prev, nxt = ordered[i - 1], ordered[i]
        gap = nxt.start - prev.start
        if gap <= 0:
            continue
        if lo is not None and hi is not None and (nxt.start < lo or nxt.start > hi):
            continue
        if best_gap is None or (gap > best_gap if find_max else gap < best_gap):
            best_gap = gap
            best_seg = nxt
    return best_seg

class _ParseCancelledError(Exception):
    """Internal control-flow exception used to abort _parse_btf cleanly."""

def _parse_btf(filepath: str,
              progress_callback=None,
              cancel_check=None) -> BtfTrace:
    """Parse a .btf file and return a BtfTrace.

    *progress_callback*, if given, is called as
    ``progress_callback(pct, message)``
    where *pct* is an integer 0-100 and *message* is a short status string.
    """
    try:
        file_size = os.path.getsize(filepath)
    except OSError:
        file_size = 0
    if file_size > _MAX_TRACE_FILE_BYTES:
        raise ValueError(
            f"Trace file is too large ({file_size / (1024 * 1024):.0f} MB, "
            f"max {_MAX_TRACE_FILE_BYTES // (1024 * 1024)} MB)"
        )

    meta: Dict[str, str] = {}
    time_scale = "ns"

    # T-events grouped by timestamp for O(1) same-tick access
    t_events_by_time: Dict[int, List[Tuple]] = defaultdict(list)
    sti_events: List[StiEvent] = []
    tick_sti_times: List[int] = []  # timestamps from STI TICK events -> rendered on ruler
    time_min = 0
    time_max = 0
    first_event = True
    _skipped_lines: int = 0  # lines with unparseable timestamps (reported in meta)
    # raw_name -> first task_create timestamp
    _task_create_raw: Dict[str, int] = {}
    _task_create_pri_raw: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Phase 1 : file reading
    # Scan every line in one pass; collect T-events into a dict keyed by
    # timestamp so that all same-tick events can be processed together in
    # Phase 2.  STI events are stored as-is.  Comment/meta lines (#) fill
    # the meta dict and set time_scale.
    # ------------------------------------------------------------------
    if progress_callback:
        progress_callback(2, "Reading file…")
    _int = int
    _meta_re_match = _META_KEY_RE.match
    with open(filepath, encoding="utf-8", errors="replace") as fh:
        for line_index, line in enumerate(fh, start=1):
            if cancel_check and line_index % 2048 == 0 and cancel_check():
                raise _ParseCancelledError()
            line = line.strip()
            if not line:
                continue
            if line[0] == "#":
                stripped = line[1:].lstrip()
                if " " in stripped:
                    key, _, value = stripped.partition(" ")
                    if _meta_re_match(key):
                        value = value.strip()
                        meta[key] = value
                        if key == "timeScale":
                            time_scale = value
                continue

            parts = line.split(",", 8)
            if len(parts) < 7:
                continue

            try:
                t = _int(parts[0])
            except ValueError:
                _skipped_lines += 1
                continue

            ev_type = parts[3]
            if ev_type and (ev_type[0] == " " or ev_type[-1] == " "):
                ev_type = ev_type.strip()
            # Update time bounds only for non-C (non-set_frequency) events so
            # that the trace start is anchored to the first scheduling event.
            if ev_type != "C":
                if first_event:
                    time_min = time_max = t
                    first_event = False
                else:
                    if t < time_min:
                        time_min = t
                    if t > time_max:
                        time_max = t
            if ev_type == "T":
                _note = parts[7].strip() if len(parts) > 7 else ""
                _tgt_raw = parts[4].strip()
                if _note == "task_create":
                    if _tgt_raw not in _task_create_raw:
                        _task_create_raw[_tgt_raw] = t
                _create_pri = _parse_create_priority(_note)
                if _create_pri is not None:
                    if _tgt_raw not in _task_create_raw:
                        _task_create_raw[_tgt_raw] = t
                    if _tgt_raw not in _task_create_pri_raw:
                        _task_create_pri_raw[_tgt_raw] = _create_pri
                t_events_by_time[t].append((
                    t,
                    parts[1].strip(),   # source
                    parts[6].strip(),   # event
                    _tgt_raw,           # target
                    _note,              # note
                ))
            elif ev_type == "STI":
                _sti_target = parts[4].strip()
                if _sti_target == "TICK":
                    # STI TICK events are rendered as ruler marks, not STI channel rows.
                    tick_sti_times.append(t)
                else:
                    sti_events.append(StiEvent(
                        time=t,
                        core=parts[1].strip(),
                        target=_sti_target,
                        event=parts[6].strip(),
                        note=parts[7].strip() if len(parts) > 7 else "",
                    ))

    open_seg: Dict[str, Tuple[int, str]] = {}
    last_core: Dict[str, str] = {}
    segments: List[TaskSegment] = []

    if progress_callback:
        progress_callback(25, "Reconstructing segments…")

    # ------------------------------------------------------------------
    # Phase 2 : state-machine segment reconstruction
    # Replay events in chronological order.  The state machine tracks one
    # open (start, core) interval per task in *open_seg*.
    # _open_seg  -> record the start of a new execution interval.
    # _close_seg -> seal the current open interval into a TaskSegment.
    #
    # At each timestamp we process events in two passes:
    #   Pass A  - resume events: close the pre-empted task, open the
    #             newly resumed task on the correct core.
    #   Pass B  - preempt events that have NO matching resume at the same
    #             tick: these are naked pre-emptions (e.g. task termination
    #             or OS reclaim) so we just close the segment.
    # ------------------------------------------------------------------
    def _close_seg(task: str, end_time: int) -> None:
        if task in open_seg:
            start, core = open_seg.pop(task)
            if end_time > start:
                segments.append(TaskSegment(task=task, start=start,
                                            end=end_time, core=core))

    def _open_seg(task: str, start_time: int, core: str) -> None:
        _close_seg(task, start_time)
        open_seg[task] = (start_time, core)
        last_core[task] = core

    def _core_from_task_entity(entity: str) -> Optional[str]:
        core_id, _, _ = _parse_task_name(entity)
        if core_id is None:
            return None
        return f"Core_{core_id}"

    for timestamp_index, ts in enumerate(sorted(t_events_by_time), start=1):
        if cancel_check and timestamp_index % 512 == 0 and cancel_check():
            raise _ParseCancelledError()
        events = t_events_by_time[ts]
        # (time, source, event, target, note)

        core_preempts: Dict[str, str] = {}
        for (_, src, ev, tgt, _note) in events:
            if ev == "preempt":
                if _is_core_entity(src):
                    core_preempts[tgt] = src
                else:
                    src_core = _core_from_task_entity(src)
                    if src_core is not None:
                        core_preempts[tgt] = src_core

        # Build set of sources that issued a resume (used to detect naked preempts).
        resumed_srcs = {src for (_, src, ev, tgt, _n) in events if ev == "resume"}

        for (_, src, ev, tgt, _note) in events:
            if ev != "resume":
                continue

            if src in core_preempts:
                core = core_preempts[src]
            elif _is_core_entity(src):
                core = src
            elif src in last_core:
                core = last_core[src]
            else:
                core = (_core_from_task_entity(src)
                        or _core_from_task_entity(tgt)
                        or "Core_0")

            _close_seg(src, ts)
            _open_seg(tgt, ts, core)

        for (_, src, ev, tgt, _note) in events:
            if ev == "preempt":
                if tgt not in resumed_srcs:
                    core = (core_preempts.get(tgt)
                            or last_core.get(tgt)
                            or _core_from_task_entity(tgt)
                            or "Core_0")
                    _close_seg(tgt, ts)
                    if _is_core_entity(src):
                        last_core[tgt] = src
                    else:
                        src_core = _core_from_task_entity(src)
                        if src_core is not None:
                            last_core[tgt] = src_core

    for task in list(open_seg.keys()):
        _close_seg(task, time_max)

    # Free the raw event dict - no longer needed after segment reconstruction.
    t_events_by_time.clear()

    if _skipped_lines:
        meta["_skipped_lines"] = str(_skipped_lines)

    _ver = meta.get("version")
    if _ver:
        try:
            if int(str(_ver).split(".")[0]) != 2:
                meta["_version_warning"] = (
                    f"Unsupported BTF format version: {_ver} (expected 2.x)")
        except ValueError:
            meta["_version_warning"] = f"Unrecognized BTF version: {_ver}"

    if progress_callback:
        progress_callback(55, "Building lookup tables…")

    # ------------------------------------------------------------------
    # Phase 3 : post-processing - build sorted task list + lookup tables
    # All collections created here are stored in BtfTrace so that scene
    # rebuild() calls never have to iterate raw segments again.
    # ------------------------------------------------------------------
    # Task-view rows should reflect actual execution timelines.
    # Including created-but-never-run tasks produces label-only blank rows.
    # Build merge-key map in a single pass (avoids second full segment scan).
    _mk_cache: Dict[str, str] = {}
    segs_by_mk_build: Dict[str, list] = defaultdict(list)
    _core_segs_build: Dict[str, list] = defaultdict(list)
    _cn_set: set = set()
    if cancel_check and cancel_check():
        raise _ParseCancelledError()
    for seg in segments:
        if _is_core_entity(seg.task) or not seg.task:
            continue
        mk = _mk_cache.get(seg.task)
        if mk is None:
            mk = _task_merge_key(seg.task)
            _mk_cache[seg.task] = mk
        segs_by_mk_build[mk].append(seg)
        # TICK is rendered on the ruler, not as per-core timeline bars.
        # Exclude all TICK segments from core rows to avoid LOD artifacts.
        _tname = _parse_task_name(seg.task)[2]
        if _tname != "TICK":
            _core_segs_build[seg.core].append(seg)
            _cn_set.add(seg.core)

    task_set: set = set(_mk_cache.values())
    # Sort by the first representative raw task name for each key.
    _mk_repr: Dict[str, str] = {}
    for raw, mk in _mk_cache.items():
        if mk not in _mk_repr:
            _mk_repr[mk] = raw
    # TICK is rendered on the time-scale ruler, not as a task row.
    _tick_mk_excl = _task_merge_key("TICK")
    tasks = sorted(
        (mk for mk in task_set if mk != _tick_mk_excl),
        key=lambda mk: _task_sort_key(_mk_repr[mk]))

    sti_channels, sti_by_target, _interval_instances, _interval_ids, \
        _interval_by_id, _interval_unmatched, _interval_marker_by_id, \
        _tag_channels, _tag_by_ch = _build_sti_derived(sti_events)

    _seg_start_key = _attrgetter('start')
    segs_by_mk: Dict[str, list] = dict(segs_by_mk_build)
    for _lst in segs_by_mk.values():
        _lst.sort(key=_seg_start_key)
    _migrations, _migrations_by_mk = _build_migration_index(segs_by_mk)
    def _core_sort_key(c: str):
        if c.startswith("Core_"):
            tail = c[5:]
            return (0, int(tail) if tail.isdigit() else sys.maxsize, c)
        return (1, sys.maxsize, c)
    _core_names = sorted(_cn_set, key=_core_sort_key)
    _core_segs: Dict[str, list] = {}
    _core_task_order: Dict[str, list] = {}
    _core_task_segs:  Dict[str, dict] = {}
    _core_seg_starts: Dict[str, list] = {}

    if progress_callback:
        progress_callback(62, "Sorting core segments…")
    if cancel_check and cancel_check():
        raise _ParseCancelledError()

    for i, c in enumerate(_core_names):
        if cancel_check and i % 4 == 0 and cancel_check():
            raise _ParseCancelledError()
        segs = _core_segs_build.get(c, [])
        segs.sort(key=_seg_start_key)
        _core_segs[c] = segs
        _core_seg_starts[c] = [s.start for s in segs]

        tsm: Dict[str, list] = defaultdict(list)
        for seg in segs:
            tsm[seg.task].append(seg)
        _core_task_segs[c] = dict(tsm)
        _core_task_order[c] = sorted(tsm.keys(), key=_task_sort_key)

    # Map raw task_create names to merge keys.
    _task_create_times: Dict[str, int] = {}
    _task_create_repr: Dict[str, str] = {}
    for _raw_ct, _ct_time in _task_create_raw.items():
        _mk_ct = _mk_cache.get(_raw_ct) or _task_merge_key(_raw_ct)
        if _mk_ct not in _task_create_times or _ct_time < _task_create_times[_mk_ct]:
            _task_create_times[_mk_ct] = _ct_time
        if _mk_ct not in _task_create_repr:
            _task_create_repr[_mk_ct] = _raw_ct

    _task_base_pri, _priority_episodes, _priority_by_mk, _has_priority = (
        _build_priority_data(
            sti_events, _task_create_pri_raw, time_max, _mk_cache, _mk_repr)
    )
    _sync_objects, _sync_issues, _has_sync = _build_sync_object_data(
        sti_events, _core_segs, _mk_repr, time_max, _core_seg_starts,
        mk_cache=_mk_cache)

    # ------------------------------------------------------------------
    # Phase 4 : 1M-event performance pre-processing
    # Pre-build start-time arrays (for O(log n) bisect viewport clipping)
    # and a coarse LOD summary (_LOD_SUMMARY_BINS bins over the full time
    # span) so that scene rebuilds never iterate more than _LOD_SUMMARY_BINS
    # segments per row at fit-to-view zoom.
    # ------------------------------------------------------------------
    _time_span = max(time_max - time_min, 1)
    _lod_timescale_per_px = _time_span / _LOD_SUMMARY_BINS  # ns per summary bin
    _lod_ultra_timescale_per_px = _time_span / _LOD_SUMMARY_BINS_ULTRA

    if progress_callback:
        progress_callback(70, "Building task LOD summaries…")
    if cancel_check and cancel_check():
        raise _ParseCancelledError()

    def _make_lod_summary(segs_sorted: list, bins: int, bin_span: float) -> list:
        """Down-sample *segs_sorted* to at most *bins* entries.

        Returns a ``(summary, starts)`` tuple so callers avoid a second
        iteration to extract the start-time list.
        """
        if len(segs_sorted) <= bins:
            result = list(segs_sorted)   # copy to prevent aliasing
            return result, list(map(_attrgetter('start'), result))
        safe_span = max(bin_span, 1e-9)  # guard against zero-span edge case
        result: list = []
        starts: list = []
        prev_bin = -2
        for s in segs_sorted:
            b = (s.start - time_min) // safe_span  # floor-div avoids int() overhead
            if b != prev_bin:
                result.append(s)
                starts.append(s.start)
                prev_bin = b
        return result, starts

    # Task-view: start-time arrays + LOD summaries keyed by merge-key
    _seg_starts_mk:     Dict[str, list] = {}
    _seg_lod_mk:        Dict[str, list] = {}
    _seg_lod_starts_mk: Dict[str, list] = {}
    _seg_lod_ultra_mk:        Dict[str, list] = {}
    _seg_lod_ultra_starts_mk: Dict[str, list] = {}
    for _mk, _lst in segs_by_mk.items():
        _seg_starts_mk[_mk] = list(map(_attrgetter('start'), _lst))
        _lod, _lod_starts = _make_lod_summary(_lst, _LOD_SUMMARY_BINS, _lod_timescale_per_px)
        _seg_lod_mk[_mk]        = _lod
        _seg_lod_starts_mk[_mk] = _lod_starts
        _lod_ultra, _lod_ultra_starts = _make_lod_summary(_lod, _LOD_SUMMARY_BINS_ULTRA, _lod_ultra_timescale_per_px)
        _seg_lod_ultra_mk[_mk]        = _lod_ultra
        _seg_lod_ultra_starts_mk[_mk] = _lod_ultra_starts

    if progress_callback:
        progress_callback(80, "Building core LOD summaries…")
    if cancel_check and cancel_check():
        raise _ParseCancelledError()

    # Core-view: start-time arrays + LOD summaries for core summary rows
    _core_seg_lod:        Dict[str, list] = {}
    _core_seg_lod_starts: Dict[str, list] = {}
    _core_seg_lod_ultra:        Dict[str, list] = {}
    _core_seg_lod_ultra_starts: Dict[str, list] = {}
    for _c in _core_names:
        _lod, _lod_starts = _make_lod_summary(_core_segs[_c], _LOD_SUMMARY_BINS, _lod_timescale_per_px)
        _core_seg_lod[_c]        = _lod
        _core_seg_lod_starts[_c] = _lod_starts
        _lod_ultra, _lod_ultra_starts = _make_lod_summary(_lod, _LOD_SUMMARY_BINS_ULTRA, _lod_ultra_timescale_per_px)
        _core_seg_lod_ultra[_c]        = _lod_ultra
        _core_seg_lod_ultra_starts[_c] = _lod_ultra_starts

    if progress_callback:
        progress_callback(88, "Building per-task core LOD summaries…")
    if cancel_check and cancel_check():
        raise _ParseCancelledError()

    # Core-view: start-time arrays + LOD summaries for per-task sub-rows
    _core_task_starts:     Dict[str, dict] = {}
    _core_task_lod:        Dict[str, dict] = {}
    _core_task_lod_starts: Dict[str, dict] = {}
    _core_task_lod_ultra:        Dict[str, dict] = {}
    _core_task_lod_ultra_starts: Dict[str, dict] = {}
    for _c in _core_names:
        _core_task_starts[_c]     = {}
        _core_task_lod[_c]        = {}
        _core_task_lod_starts[_c] = {}
        _core_task_lod_ultra[_c]        = {}
        _core_task_lod_ultra_starts[_c] = {}
        for _tn, _tsegs in _core_task_segs[_c].items():
            _core_task_starts[_c][_tn] = list(map(_attrgetter('start'), _tsegs))
            _lod, _lod_starts = _make_lod_summary(_tsegs, _LOD_SUMMARY_BINS, _lod_timescale_per_px)
            _core_task_lod[_c][_tn]        = _lod
            _core_task_lod_starts[_c][_tn] = _lod_starts
            _lod_ultra, _lod_ultra_starts = _make_lod_summary(_lod, _LOD_SUMMARY_BINS_ULTRA, _lod_ultra_timescale_per_px)
            _core_task_lod_ultra[_c][_tn]        = _lod_ultra
            _core_task_lod_ultra_starts[_c][_tn] = _lod_ultra_starts

    # STI: start-time arrays for bisect clipping in builders
    _sti_starts_by_target: Dict[str, list] = {
        _ch: [e.time for e in _evs]
        for _ch, _evs in sti_by_target.items()
    }

    if progress_callback:
        progress_callback(95, "Finalising…")

    _total_ns = max(time_max - time_min, 1)
    _core_util_pct: Dict[str, float] = {}
    for _c in _core_names:
        _active_ns = sum(
            s.end - s.start for s in _core_segs[_c]
            if (_tn := _parse_task_name(s.task)[2]) != "TICK"
            and not _is_idle_task_name(_tn))
        _core_util_pct[_c] = 100.0 * _active_ns / _total_ns

    if progress_callback:
        progress_callback(97, "Culling interval instances…")
    if cancel_check and cancel_check():
        raise _ParseCancelledError()

    _interval_culled_by_id: Dict[str, list] = {
        _iid: _interval_instances_cull_nested(_insts)
        for _iid, _insts in _interval_by_id.items()
    }

    return BtfTrace(
        time_scale=time_scale,
        tasks=tasks,
        segments=segments,
        sti_events=sti_events,
        sti_channels=sti_channels,
        sti_events_by_target=sti_by_target,
        time_min=time_min,
        time_max=time_max,
        meta=meta,
        seg_map_by_merge_key=dict(segs_by_mk),
        core_names=_core_names,
        core_segs=dict(_core_segs),
        core_task_order=_core_task_order,
        core_task_segs=_core_task_segs,
        task_repr=_mk_repr,
        # Phase 4 - 1M-event performance fields
        seg_start_by_merge_key=_seg_starts_mk,
        core_seg_starts=_core_seg_starts,
        core_task_seg_starts=dict(_core_task_starts),
        sti_starts_by_target=_sti_starts_by_target,
        seg_lod_timescale_per_px=_lod_timescale_per_px,
        seg_lod_by_merge_key=_seg_lod_mk,
        seg_lod_starts_by_merge_key=_seg_lod_starts_mk,
        seg_lod_ultra_timescale_per_px=_lod_ultra_timescale_per_px,
        seg_lod_ultra_by_merge_key=_seg_lod_ultra_mk,
        seg_lod_ultra_starts_by_merge_key=_seg_lod_ultra_starts_mk,
        core_seg_lod=_core_seg_lod,
        core_seg_lod_starts=_core_seg_lod_starts,
        core_seg_lod_ultra=_core_seg_lod_ultra,
        core_seg_lod_ultra_starts=_core_seg_lod_ultra_starts,
        core_task_seg_lod=dict(_core_task_lod),
        core_task_seg_lod_starts=dict(_core_task_lod_starts),
        core_task_seg_lod_ultra=dict(_core_task_lod_ultra),
        core_task_seg_lod_ultra_starts=dict(_core_task_lod_ultra_starts),
        task_create_times=_task_create_times,
        task_create_repr=_task_create_repr,
        tick_sti_times=sorted(tick_sti_times),
        sti_event_times=sorted(e.time for e in sti_events),
        migrations=_migrations,
        migrations_by_mk=dict(_migrations_by_mk),
        interval_instances=_interval_instances,
        interval_ids=_interval_ids,
        interval_instances_by_id=_interval_by_id,
        interval_instances_culled_by_id=_interval_culled_by_id,
        core_util_pct=_core_util_pct,
        interval_marker_by_id=_interval_marker_by_id,
        interval_unmatched_starts=_interval_unmatched,
        tag_channels=_tag_channels,
        tag_samples_by_channel=_tag_by_ch,
        task_base_priority=_task_base_pri,
        priority_episodes=_priority_episodes,
        priority_episodes_by_mk=_priority_by_mk,
        has_priority_instrumentation=_has_priority,
        sync_objects=_sync_objects,
        sync_issues=_sync_issues,
        has_sync_object_instrumentation=_has_sync,
        lock_bounce_migration_ns=_build_lock_bounce_migration_set(
            dict(_migrations_by_mk), _sync_objects),
    )

