"""BTF Viewer — parser module (source). Do not edit btf_viewer.py; run make bundle."""
from __future__ import annotations

from ._imports import *  # noqa: F403,F401
from .config import *  # noqa: F403,F401
# Star-import skips leading-underscore names; STI helpers are used by name below.
from .config import _is_tag_sti_channel, _sti_channel_sort_key  # noqa: F401
from .html_report import (
    HTML_REPORT_INTERACTIVE_SCRIPT,
    HTML_REPORT_TOC_CSS,
    HTML_REPORT_TOC_SCRIPT,
    btf_html_report_document,
    html_apply_collapsible_toc,
)

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

# Open dialog / drag-drop accept list (plain + compressed BTF + demo packs).
# Put *.xtf in the *first* filter: macOS/Qt remember the last selected filter, so
# a BTF-only default leaves .xtf grayed until the user switches once.
_BTF_OPEN_FILTER = (
    "BTF traces and demo packs "
    "(*.btf *.btf.gz *.btf.bz2 *.btf.zip *.xtf *.xml *.gz *.bz2 *.zip);;"
    "Demo packs (*.xtf *.xml);;"
    "All files (*)"
)
_BTF_NAME_EXTS = (".btf", ".btf.gz", ".btf.bz2", ".btf.zip", ".gz", ".bz2", ".zip")

# Virtual path for a BTF member inside a zip: ``/path/archive.zip::subdir/a.btf``
_ZIP_MEMBER_SEP = "::"


def is_xtf_open_path(path: str) -> bool:
    """True if *path* is a shareable demo tour pack (``.xtf`` zip)."""
    return (path or "").lower().endswith(".xtf")


def extract_xtf_pack(path: str, dest_dir: Optional[str] = None) -> Tuple[str, str]:
    """Extract a ``.xtf`` zip. Returns ``(xml_path, btf_path)`` under *dest_dir*."""
    import tempfile

    src = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(src):
        raise FileNotFoundError(src)
    if not zipfile.is_zipfile(src):
        raise ValueError(f"not a zip/.xtf archive: {src}")
    out = dest_dir or tempfile.mkdtemp(prefix="btf_xtf_")
    os.makedirs(out, exist_ok=True)
    with zipfile.ZipFile(src, "r") as zf:
        zf.extractall(out)

    xml_path = ""
    xmls = []
    btfs = []
    for root, _dirs, files in os.walk(out):
        for name in files:
            full = os.path.join(root, name)
            lower = name.lower()
            if lower.endswith(".xml"):
                xmls.append(full)
            elif is_btf_open_path(full) and not lower.endswith(".xtf"):
                # Prefer real BTF containers over treating nested zips oddly.
                btfs.append(full)
    if not xmls:
        raise ValueError(f"no .xml demo script inside {src}")
    demoish = [p for p in xmls if "demo" in os.path.basename(p).lower()]
    xml_path = sorted(demoish or xmls)[0]
    if not btfs:
        raise ValueError(f"no .btf / .btf.gz inside {src}")
    # Prefer the BTF next to the XML when several exist.
    xml_dir = os.path.dirname(xml_path)
    same = [p for p in btfs if os.path.dirname(p) == xml_dir]
    btf_path = sorted(same or btfs)[0]
    return xml_path, btf_path


def is_btf_open_path(path: str) -> bool:
    """True if *path* looks like a BTF trace or a gz/bz2/zip container of one."""
    lower = (path or "").lower()
    # Strip zip-member suffix before extension checks.
    if _ZIP_MEMBER_SEP in lower:
        lower = lower.split(_ZIP_MEMBER_SEP, 1)[0]
    return any(lower.endswith(ext) for ext in _BTF_NAME_EXTS)


def _split_zip_member_path(filepath: str) -> Tuple[str, Optional[str]]:
    """Split ``archive.zip::member.btf`` into ``(archive.zip, member.btf)``.

    Plain paths return ``(filepath, None)``.
    """
    idx = (filepath or "").find(_ZIP_MEMBER_SEP)
    if idx <= 0:
        return filepath, None
    return filepath[:idx], filepath[idx + len(_ZIP_MEMBER_SEP):]


def _normalize_open_path(path: str) -> str:
    """Absolute-normalize a load path, preserving an optional ``::member`` suffix."""
    zip_path, member = _split_zip_member_path(path)
    norm = os.path.abspath(os.path.expanduser(zip_path))
    if member:
        return f"{norm}{_ZIP_MEMBER_SEP}{member}"
    return norm


def _open_path_exists(filepath: str) -> bool:
    """True if *filepath* (or its zip archive / named member) is still on disk."""
    path, member = _split_zip_member_path(filepath or "")
    if not path:
        return False
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(path):
        return False
    if not member:
        return True
    try:
        with zipfile.ZipFile(path, "r") as zf:
            return member in zf.namelist()
    except zipfile.BadZipFile:
        return False


def _filter_existing_open_paths(paths) -> List[str]:
    """Dedupe and keep only loadable BTF / ``zip::member`` paths (session restore)."""
    seen: set = set()
    unique: List[str] = []
    for raw in paths or []:
        text = str(raw).strip()
        if not text:
            continue
        norm = _normalize_open_path(text)
        if norm in seen or not _open_path_exists(norm):
            continue
        seen.add(norm)
        unique.append(norm)
    return unique


def _trace_display_name(path: str) -> str:
    """Tab / status label for a load path (zip member → bare ``.btf`` name)."""
    _zip_path, member = _split_zip_member_path(path)
    if member:
        return os.path.basename(member.replace("\\", "/")) or member
    return os.path.basename(path)


def _sniff_compression(filepath: str) -> str:
    """Return 'gzip', 'bz2', 'zip', or '' from magic bytes (fallback: extension)."""
    zip_path, _member = _split_zip_member_path(filepath)
    try:
        with open(zip_path, "rb") as fh:
            magic = fh.read(4)
    except OSError:
        magic = b""
    if magic.startswith(b"\x1f\x8b"):
        return "gzip"
    if magic.startswith(b"BZh"):
        return "bz2"
    if magic.startswith(b"PK"):
        return "zip"
    lower = zip_path.lower()
    if lower.endswith((".gz", ".btf.gz")):
        return "gzip"
    if lower.endswith((".bz2", ".btf.bz2")):
        return "bz2"
    if lower.endswith((".zip", ".btf.zip")):
        return "zip"
    return ""


def _zip_file_entries(names: List[str]) -> List[str]:
    """Non-directory entry names from a zip namelist."""
    return [n for n in names if n and not n.endswith("/") and not n.endswith("\\")]


def _list_zip_btf_members(names: List[str]) -> List[str]:
    """Return ``.btf`` members (plain, not ``.btf.gz`` / ``.btf.bz2``), sorted.

    Top-level members sort before nested paths; otherwise lexicographic.
    """
    btf_members = [
        n for n in _zip_file_entries(names)
        if n.lower().endswith(".btf") and not n.lower().endswith((".btf.gz", ".btf.bz2"))
    ]

    def sort_key(n: str) -> Tuple[int, str]:
        depth = n.count("/") + n.count("\\")
        return (depth, n.lower())

    return sorted(btf_members, key=sort_key)


def _zip_no_btf_message(names: List[str]) -> str:
    files = _zip_file_entries(names)
    if not files:
        return "ZIP archive contains no files"
    sample = ", ".join(sorted(files)[:8])
    more = "…" if len(files) > 8 else ""
    return f"ZIP archive has no .btf member (found: {sample}{more})"


def _pick_zip_btf_member(names: List[str]) -> str:
    """Choose a single BTF member inside a zip archive (legacy single-open)."""
    btf_members = _list_zip_btf_members(names)
    if len(btf_members) == 1:
        return btf_members[0]
    if len(btf_members) > 1:
        top = [n for n in btf_members if "/" not in n and "\\" not in n]
        return sorted(top or btf_members)[0]
    raise ValueError(_zip_no_btf_message(names))


def _expand_open_paths(filepath: str) -> List[str]:
    """Expand a user path into one or more loadable paths.

    A zip with multiple ``.btf`` members becomes one ``archive.zip::member``
    path per member. A zip with none raises ``ValueError`` with a clear message.
    """
    path, member = _split_zip_member_path(filepath)
    if member:
        return [_normalize_open_path(filepath)]
    path = os.path.abspath(os.path.expanduser(path))
    if _sniff_compression(path) != "zip":
        return [path]
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
    members = _list_zip_btf_members(names)
    if not members:
        raise ValueError(_zip_no_btf_message(names))
    if len(members) == 1:
        return [path]
    return [f"{path}{_ZIP_MEMBER_SEP}{m}" for m in members]


@contextmanager
def _open_btf_text(filepath: str):
    """Yield a text stream for a plain or compressed BTF file."""
    zip_path, member = _split_zip_member_path(filepath)
    if member:
        with zipfile.ZipFile(zip_path, "r") as zf:
            with zf.open(member, "r") as raw:
                with io.TextIOWrapper(raw, encoding="utf-8", errors="replace") as fh:
                    yield fh
        return
    kind = _sniff_compression(zip_path)
    if kind == "gzip":
        with gzip.open(zip_path, "rt", encoding="utf-8", errors="replace") as fh:
            yield fh
        return
    if kind == "bz2":
        with bz2.open(zip_path, "rt", encoding="utf-8", errors="replace") as fh:
            yield fh
        return
    if kind == "zip":
        with zipfile.ZipFile(zip_path, "r") as zf:
            picked = _pick_zip_btf_member(zf.namelist())
            with zf.open(picked, "r") as raw:
                with io.TextIOWrapper(raw, encoding="utf-8", errors="replace") as fh:
                    yield fh
        return
    with open(zip_path, encoding="utf-8", errors="replace") as fh:
        yield fh


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


def _nearest_rank_index(n: int, p: float) -> int:
    """Nearest-rank percentile index (matches the Statistics-panel convention)."""
    return min(n - 1, max(0, int(math.ceil(p * n)) - 1))


def _sample_variability(sorted_samples: "List") -> "Tuple[float, float, float, float]":
    """``(jitter, sigma, p50, p99)`` for an already-sorted numeric sample list.

    ``jitter`` is ``max - min``; ``sigma`` is the population standard deviation
    (dividing by ``n``), matching the exec/blocking Statistics tables.  Used to
    give the Interval and Tag tables the same summary column set (review item
    B10).  Returns zeros for an empty list.
    """
    n = len(sorted_samples)
    if n == 0:
        return 0.0, 0.0, 0.0, 0.0
    avg = sum(sorted_samples) / n
    sigma = math.sqrt(sum((v - avg) ** 2 for v in sorted_samples) / n)
    jitter = sorted_samples[-1] - sorted_samples[0]
    p50 = sorted_samples[_nearest_rank_index(n, 0.50)]
    p99 = sorted_samples[_nearest_rank_index(n, 0.99)]
    return jitter, sigma, p50, p99


def _nominal_resolution(trace: "BtfTrace") -> int:
    """Effective timestamp grid of the trace, in the trace's native time unit
    (review item B11).

    The greatest common divisor of a sample of segment boundaries — if every
    recorded timestamp is a multiple of *g*, the capture clock (or its export)
    quantises to *g*, so any duration distribution whose tail sits near *g* is
    dominated by that grid rather than by task behavior.  Floored at 1.
    """
    g = 0
    n = 0
    for segs in getattr(trace, "seg_map_by_merge_key", {}).values():
        for s in segs:
            for v in (int(s.start), int(s.end)):
                if v:
                    g = math.gcd(g, v)
            n += 1
            if n >= 4000 or g == 1:
                break
        if n >= 4000 or g == 1:
            break
    return max(1, g)


def _resolution_limited_pct(samples: "List[int]", res: int) -> float:
    """Percent of ``samples`` at or below ``res`` (0.0 when no samples)."""
    if not samples or res <= 0:
        return 0.0
    n_low = sum(1 for s in samples if s <= res)
    return 100.0 * n_low / len(samples)


def _all_timing_samples(trace: "BtfTrace", kind: str,
                        lo: Optional[int] = None,
                        hi: Optional[int] = None) -> "List[int]":
    """Flat list of every sample feeding a timing table (``kind`` = ``exec`` for
    on-CPU slice durations, ``block`` for off-CPU gaps), tasks pooled, IDLE/TICK
    excluded.  Used for the resolution caveat (review item B11)."""
    out: List[int] = []
    for mk, segs in getattr(trace, "seg_map_by_merge_key", {}).items():
        raw = trace.task_repr.get(mk, mk)
        _c, _tid, name = _parse_task_name(str(raw))
        if _is_idle_task_name(name) or name == "TICK":
            continue
        if kind == "block":
            out.extend(_blocking_time_samples(list(segs), lo, hi))
        else:
            out.extend(_exec_slice_samples(list(segs), lo, hi))
    return out


def _resolution_note(trace: "BtfTrace", samples: "List[int]",
                     lo: Optional[int] = None, hi: Optional[int] = None) -> str:
    """One-line caveat for a timing table, or '' when quantisation is not a
    concern (fewer than ~15% of samples at or below the effective grid).

    ``lo``/``hi`` are accepted for call-site symmetry; the grid is trace-wide.
    """
    if not samples:
        return ""
    res = _nominal_resolution(trace)
    if res <= 1:
        return ""
    pct = _resolution_limited_pct(samples, res)
    if pct < 15.0:
        return ""
    return (f"{pct:.0f}% of samples are at or below the ~"
            f"{_format_time(res, trace.time_scale)} timestamp grid; "
            f"tail percentiles near that value may be quantisation artefacts.")


def _interval_stats_rows(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    """Per-interval-id stats, variability shape (review item B10):
    ``(id, label, count, min, avg, max, jitter, sigma, p50, p95, p99)`` as
    formatted strings.

    ``label`` is ``Interval <id>``, suffixed with the owning task
    (``Interval 5 · PS[228]``) when every instance in scope names the same one.
    """
    scale = trace.time_scale
    _tid_to_name: Dict[str, str] = {}
    for _raw in getattr(trace, "task_repr", {}).values():
        _c, _tid, _name = _parse_task_name(str(_raw))
        if _tid is not None:
            _tid_to_name.setdefault(str(_tid), _name)
    rows = []
    for iid in trace.interval_ids:
        _insts = [
            inst for inst in trace.interval_instances_by_id.get(iid, [])
            if _interval_overlaps_range(inst, lo, hi)
        ]
        samples = [inst.stop_ns - inst.start_ns for inst in _insts]
        if not samples:
            continue
        _tids = {str(inst.task_id) for inst in _insts if inst.task_id is not None}
        if len(_tids) == 1:
            _t = next(iter(_tids))
            _owner = _tid_to_name.get(_t) or f"task {_t}"
        elif len(_tids) > 1:
            _owner = "(mixed)"
        else:
            _owner = ""
        _label = f"Interval {iid}" + (f" · {_owner}" if _owner else "")
        samples.sort()
        total = sum(samples)
        count = len(samples)
        mn = samples[0]
        mx = samples[-1]
        avg = int(round(total / count))
        p95 = samples[_nearest_rank_index(count, 0.95)]
        jitter, sigma_f, p50, p99 = _sample_variability(samples)
        sigma = int(round(sigma_f))
        rows.append((
            iid,
            _label,
            count,
            _format_time(mn, scale),
            _format_time(avg, scale),
            _format_time(mx, scale),
            _format_time(jitter, scale),
            _format_time(sigma, scale),
            _format_time(p50, scale),
            _format_time(p95, scale),
            _format_time(p99, scale),
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
    """Per-tag-channel stats, variability shape (review item B10):
    ``(channel, label, count, min, avg, max, jitter, sigma, p50, p95, p99)`` as
    formatted values.
    """
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
        p95 = samples[_nearest_rank_index(count, 0.95)]
        jitter, sigma, p50, p99 = _sample_variability(samples)
        rows.append((
            ch,
            _tag_channel_label(ch),
            count,
            _format_tag_value(mn),
            _format_tag_value(avg),
            _format_tag_value(mx),
            _format_tag_value(jitter),
            _format_tag_value(sigma),
            _format_tag_value(p50),
            _format_tag_value(p95),
            _format_tag_value(p99),
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
    for m in _migrations_in_range(trace, lo, hi):
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


def _migration_summary(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> dict:
    """Compact Migration Summary for progressive drill-down (Step 2).

    Returns totals, rate, top task/pair, median dwell, and a thrash hint.
    Does not change Scope or Filters — callers link into existing sections.
    """
    from .timeline_util import _format_time, _to_ns

    migs = list(_migrations_in_range(trace, lo, hi))
    total = len(migs)
    rows = _migration_rows(trace, lo, hi)
    pairs = _core_pair_rows(trace, lo, hi)
    if lo is not None and hi is not None:
        span = max(0, int(hi) - int(lo))
    else:
        span = max(0, int(trace.time_max) - int(trace.time_min))
    span_s = (_to_ns(span, trace.time_scale) / 1_000_000_000.0) if span > 0 else 0.0
    rate = (total / span_s) if span_s > 0 else 0.0
    rate_label = f"{rate:.2f}/s" if span_s > 0 and total else "—"

    top_task = None
    if rows:
        mk, name, n_mig = rows[0][0], rows[0][1], rows[0][2]
        top_task = {"mk": mk, "name": name, "count": int(n_mig)}

    top_pair = None
    if pairs:
        fc, tc, cnt, bnc, _gap = pairs[0]
        top_pair = {
            "from": fc, "to": tc, "count": int(cnt), "bounces": int(bnc),
        }

    dwell: List[int] = []
    for row in rows:
        mk = row[0]
        segs = (
            _task_segs_in_range(trace, mk, lo, hi)
            if lo is not None and hi is not None
            else trace.seg_map_by_merge_key.get(mk, [])
        )
        dwell.extend(_core_dwell_samples(segs, lo, hi))
    median_dwell_ns = 0
    if dwell:
        ordered = sorted(dwell)
        median_dwell_ns = ordered[len(ordered) // 2]
    median_dwell = (
        _format_time(median_dwell_ns, trace.time_scale) if median_dwell_ns else "—"
    )

    ping_total = sum(int(r[7] or 0) for r in rows)
    thrash_hint = ""
    if ping_total > 0:
        thrash_hint = f"{ping_total} ping-pong migration(s) in scope"
    elif top_pair and top_pair["count"] > 0:
        bounce_pct = 100.0 * top_pair["bounces"] / top_pair["count"]
        if bounce_pct >= 30.0:
            thrash_hint = (
                f"Hot pair {top_pair['from']}→{top_pair['to']} "
                f"bounce {bounce_pct:.0f}%"
            )

    return {
        "total": total,
        "rate": rate,
        "rate_label": rate_label,
        "top_task": top_task,
        "top_pair": top_pair,
        "median_dwell_ns": median_dwell_ns,
        "median_dwell": median_dwell,
        "thrash_hint": thrash_hint,
        "has_data": total > 0 or bool(rows),
    }


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
    *,
    include_merge_key: bool = False,
) -> List[tuple]:
    """Per-task core affinity summary.

    Returns ``[(label, mask_hex, observed_cores_str, violation_cores_str), ...]``.
    With ``include_merge_key=True``, prepends the task merge key to each row
    for interactive UI consumers.

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
        row = (label, mask_hex, obs_str, viol_str)
        rows.append((mk, *row) if include_merge_key else row)
    return rows


def _deadline_violations(
    trace: "BtfTrace",
    cpu_budget_pct: float,
    task_deadlines_ns: Dict[str, int],
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> Dict[str, list]:
    """Compute per-slice and CPU-budget violations (mirrors web deadlineAnalysis.js).

    slice_violations entries:
      (label, duration, limit, over_by, mk, start_ns, seg, dur_tu, limit_tu)
    cpu_violations entries:
      (label, cpu_pct, budget, mk, pct_raw, budget_pct)
    """
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
            # Settings store true nanoseconds; segment times are trace-native.
            limit_tu = _from_ns(limit_ns, scale)
            for seg in segs:
                if lo is not None and hi is not None and (seg.end <= lo or seg.start >= hi):
                    continue
                dur = seg.end - seg.start
                if dur > limit_tu:
                    slice_violations.append((
                        disp,
                        _format_time(dur, scale),
                        _format_time(limit_tu, scale),
                        _format_time(dur - limit_tu, scale),
                        dur,  # sort key (trace units)
                        mk,
                        seg.start,
                        seg,
                        limit_tu,
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
                cpu_violations.append((
                    disp, f"{pct:.1f}%", f"{cpu_budget_pct:.1f}%",
                    pct, mk, float(cpu_budget_pct),
                ))
    slice_violations.sort(key=lambda r: -r[4])
    cpu_violations.sort(key=lambda r: -r[3])
    return {
        # label, duration, limit, over_by, mk, start_ns, seg, dur_tu, limit_tu
        "slice_violations": [
            (r[0], r[1], r[2], r[3], r[5], r[6], r[7], r[4], r[8])
            for r in slice_violations
        ],
        # label, cpu_pct, budget, mk, pct_raw, budget_pct
        "cpu_violations": [
            (r[0], r[1], r[2], r[4], r[3], r[5]) for r in cpu_violations
        ],
    }


def _format_deadline_slice_note(
    trace: "BtfTrace",
    mk: str,
    seg: "TaskSegment",
    limit_label: str,
) -> str:
    """Annotation note for a Slice-over-deadline stats row click."""
    raw = trace.task_repr.get(mk, mk)
    name = _task_display_name(raw)
    scale = trace.time_scale
    dur = seg.end - seg.start
    return (
        f"{name} over deadline: {_format_time(dur, scale)} > {limit_label} "
        f"at {_format_time(seg.start, scale)}"
    )


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

def _tag_interval_plot_points(
    trace: "BtfTrace",
    channel: str,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[Tuple[int, int, TagSample]]:
    """Elapsed time between consecutive samples on one tag channel.

    Unlike interval_start/stop (paired per task id), tag samples carry no
    task pairing — consecutive samples on the same channel measure elapsed
    time regardless of which task/core emitted them, which makes tags the
    recommended way to measure an interval that spans two different tasks.
    """
    samples = [
        s for s in trace.tag_samples_by_channel.get(channel, [])
        if _tag_overlaps_range(s, lo, hi)
    ]
    pts: List[Tuple[int, int, TagSample]] = []
    for i in range(1, len(samples)):
        gap = samples[i].time_ns - samples[i - 1].time_ns
        if gap > 0:
            pts.append((samples[i].time_ns, gap, samples[i]))
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

def _merge_intervals(intervals: "List[Tuple[int, int]]") -> "List[Tuple[int, int]]":
    """Sort + coalesce overlapping/touching ``(a, b)`` intervals (``a < b``)."""
    if not intervals:
        return []
    ordered = sorted(intervals)
    out = [list(ordered[0])]
    for a, b in ordered[1:]:
        if a <= out[-1][1]:
            if b > out[-1][1]:
                out[-1][1] = b
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _intervals_overlap_measure(
    a: "List[Tuple[int, int]]", b: "List[Tuple[int, int]]",
) -> int:
    """Total length of the intersection of two coalesced interval lists."""
    i = j = total = 0
    while i < len(a) and j < len(b):
        lo = max(a[i][0], b[j][0])
        hi = min(a[i][1], b[j][1])
        if hi > lo:
            total += hi - lo
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return total


def _priority_inversion_time(
    trace: "BtfTrace", ep: "PriorityEpisode", med_mks: "set",
    mk_cache: "Dict[str, str]",
) -> int:
    """Wall-clock time in ``ep`` where a medium-priority task actually runs while
    the boosted holder does not — the measured priority-inversion duration
    (review item A6).  0 when the episode has no medium candidates."""
    lo, hi = ep.start_ns, ep.stop_ns
    if not med_mks or hi <= lo:
        return 0
    med_iv: List[Tuple[int, int]] = []
    for segs in trace.core_segs.values():
        starts = [s.start for s in segs]
        k = max(0, bisect_left(starts, lo) - 1)
        for idx in range(k, len(segs)):
            s = segs[idx]
            if s.start >= hi:
                break
            if s.end <= lo:
                continue
            raw = s.task
            smk = mk_cache.get(raw)
            if smk is None:
                smk = _task_merge_key(raw)
                mk_cache[raw] = smk
            if smk in med_mks:
                med_iv.append((max(int(s.start), lo), min(int(s.end), hi)))
    if not med_iv:
        return 0
    med_union = _merge_intervals(med_iv)
    hold_union = _merge_intervals([
        (max(int(s.start), lo), min(int(s.end), hi))
        for s in trace.seg_map_by_merge_key.get(ep.mk, ())
        if min(int(s.end), hi) > max(int(s.start), lo)
    ])
    med_total = sum(b - a for a, b in med_union)
    return med_total - _intervals_overlap_measure(med_union, hold_union)


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
    base_by_name = {
        _task_display_name(trace.task_repr.get(m, m)): m
        for m in trace.task_base_priority
    }
    mk_cache: Dict[str, str] = {}
    rows = []
    for mk, eps in by_mk.items():
        base_pri = trace.task_base_priority.get(mk, eps[0].base_pri)
        peak_pri = max(ep.peak_pri for ep in eps)
        total_ns = 0
        inv_worst_ns = 0
        inv_total_ns = 0
        inv_count = 0
        inherit_count = 0
        lmh_count = 0
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
            # Inherit episodes with medium-priority interveners still carry
            # L/M/H geometry (episode.pattern contains "L/M/H"); do not hide
            # that behind a plain "Mutex inherit" aggregate label.
            if ep.medium_tasks or "L/M/H" in (ep.pattern or ""):
                lmh_count += 1
            med_mks = {
                base_by_name[n] for n in ep.medium_tasks if n in base_by_name
            }
            ep_inv = _priority_inversion_time(trace, ep, med_mks, mk_cache)
            if ep_inv > 0:
                inv_total_ns += ep_inv
                inv_worst_ns = max(inv_worst_ns, ep_inv)
        if inherit_count:
            pattern = "Mutex inherit + L/M/H" if lmh_count else "Mutex inherit"
        elif lmh_count or inv_count:
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
            _format_time(inv_worst_ns, scale) if inv_worst_ns else "—",
            _format_time(inv_total_ns, scale) if inv_total_ns else "—",
            pattern,
            total_ns,
            inv_worst_ns,
            inv_total_ns,
        ))
    rows.sort(key=lambda r: (-r[11], -r[9], r[1]))
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
            # Review item A7: distinct tasks that took/recv'd while the object
            # was already held, and the deepest simultaneously-open take count.
            "waiters": set(),
            "max_nest": 0,
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
                    # Contended acquire: something is already held, and it is a
                    # different task → the taker had to wait (review item A7).
                    if (obj["open_takes"] and task_mk
                            and task_mk != obj["open_takes"][-1].get("task_mk")):
                        obj["waiters"].add(task_mk)
                    obj["open_takes"].append(rec)
                    if len(obj["open_takes"]) > obj["max_nest"]:
                        obj["max_nest"] = len(obj["open_takes"])
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

# A cross-core hold ratio this high on a meaningful sample is a warning even
# with no explicit issue record (e.g. a queue whose holds almost always move
# across cores). Below the sample floor, one stray issue on 3 holds is noise —
# do not grade it as more than the issue itself already says.
_SYNC_MIN_SAMPLE = 20
_SYNC_HIGH_BOUNCE_PCT = 25.0


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
        n_holds = len(holds)
        avg_ns = (sum(h["duration_ns"] for h in holds) // n_holds) if holds else 0
        bounces = sum(
            1 for h in holds
            if h.get("take_core") and h.get("give_core")
            and h["take_core"] != h["give_core"]
        )
        bounce_pct = round(100.0 * bounces / n_holds, 1) if n_holds else 0.0
        if (status == "ok" and n_holds >= _SYNC_MIN_SAMPLE
                and bounce_pct >= _SYNC_HIGH_BOUNCE_PCT):
            status = "warning"
        status_label = {"ok": "OK", "error": "Error", "warning": "Warning"}[status]
        # Review item A7: hold-time tail, waiter fan-in, deepest nesting.
        _hd = sorted(h["duration_ns"] for h in holds)
        if _hd:
            p95_hold_ns = _hd[_nearest_rank_index(len(_hd), 0.95)]
            p99_hold_ns = _hd[_nearest_rank_index(len(_hd), 0.99)]
        else:
            p95_hold_ns = p99_hold_ns = 0
        waiters = len(obj.get("waiters") or ())
        max_nest = int(obj.get("max_nest") or 0)
        rows.append((
            obj["key"],
            obj["kind"],
            obj["ptr"],
            f"{obj['kind']} {obj['ptr']}",
            n_holds,
            len(issues),
            _format_time(avg_ns, scale) if holds else "—",
            status_label,
            status,
            avg_ns,
            bounces,
            bounce_pct,
            _format_time(p95_hold_ns, scale) if _hd else "—",
            _format_time(p99_hold_ns, scale) if _hd else "—",
            waiters,
            max_nest,
            p95_hold_ns,
            p99_hold_ns,
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
        if kind == "tag_interval":
            return (f"{_tag_channel_label(payload.channel)}: {fmt(y_ns)} "
                    f"since previous sample at {fmt(x_ns)}")
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
        if kind == "dispatch":
            return f"{name}: {fmt(y_ns)} dispatch latency at {fmt(x_ns)}"
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
        if kind == "pair_rate":
            return (f"{payload.from_core}→{payload.to_core}: {fmt(y_ns)} since "
                    f"previous pair migration at {fmt(x_ns)}")
        if kind == "pair_gap":
            bounce = " · bounce" if payload.ns in trace.lock_bounce_migration_ns else ""
            return (f"{payload.from_core}→{payload.to_core}: {fmt(y_ns)} blocked "
                    f"after migration at {fmt(x_ns)}{bounce}")
    if kind == "tick":
        return f"Tick interval {fmt(y_ns)} at {fmt(x_ns)}"
    if kind == "switch_overhead":
        core = mk or "core"
        return f"{core}: switch overhead {fmt(y_ns)} at {fmt(x_ns)}"
    if kind == "concurrency":
        n = mk if mk is not None else "?"
        return f"{n} active cores: dwell {fmt(y_ns)} starting {fmt(x_ns)}"
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


def _format_priority_episode_note(trace: "BtfTrace", ep: "PriorityEpisode") -> str:
    """Annotation note for a Priority Inheritance table row jump."""
    fmt = lambda v: _format_time(v, trace.time_scale)
    kind = "inversion" if ep.inversion_suspect else ("inheritance" if ep.inherited else "boost")
    return (f"{ep.task_label} priority {kind}: pri {ep.base_pri}→{ep.peak_pri} "
            f"at {fmt(ep.start_ns)}")

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
    # Parallel to migrations (same order) for O(log n) time-window slices.
    migration_times: List[int]                                              = field(default_factory=list)
    migrated_mks: frozenset                                                 = field(default_factory=frozenset)
    # Full-trace stats snapshots filled at parse (Statistics / heatmap open path).
    task_cpu_ns: Optional[Dict[str, int]]                                   = None
    sched_ctx_switches: Optional[int]                                       = None
    sched_core_gaps: Optional[List[int]]                                    = None
    migration_rows_full: Optional[List[dict]]                               = None
    # Full-trace Statistics harvest filled at parse (exec / block / inter / mig).
    ux_events_full: Optional[List[dict]]                                    = None
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
    if (lo is None and hi is None
            and trace.sched_ctx_switches is not None
            and trace.sched_core_gaps is not None):
        return trace.sched_ctx_switches, trace.sched_core_gaps
    ctx_switches = 0
    gaps: List[int] = []
    for core in trace.core_names:
        segs = _core_segs_in_range(trace, core, lo, hi)
        for i in range(1, len(segs)):
            prev, curr = segs[i - 1], segs[i]
            if lo is not None and hi is not None:
                if not (lo <= curr.start <= hi):
                    continue
            ctx_switches += 1
            gap = curr.start - prev.end
            gaps.append(gap if gap > 0 else 0)
    return ctx_switches, gaps


def _dispatch_latency_by_mk(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> Dict[str, dict]:
    """Map merge-key → {samples, min_seg, max_seg} for dispatch latency.

    ``t_ready`` comes from STI ``resume Name[id]`` (vTaskResume) or task create
    time; ``t_resume`` is the next switch-in (segment start) for that task.
    ISR resumes without a task name are skipped. Sync-object wakes are not
    attributed (BTF notes carry the object pointer, not the woken task).
    """
    by_mk: Dict[str, dict] = {}

    def _ensure(mk: str) -> dict:
        if mk not in by_mk:
            by_mk[mk] = {
                "samples": [],
                "points": [],  # (dispatch_ns, latency_ns, seg)
                "min_seg": None,
                "max_seg": None,
                "min_ns": None,
                "max_ns": None,
            }
        return by_mk[mk]

    def _add(mk: str, ready_ns: int) -> None:
        segs = trace.seg_map_by_merge_key.get(mk, ())
        if not segs:
            return
        if lo is not None and hi is not None and not (lo <= ready_ns <= hi):
            return
        best = None
        for s in segs:
            if s.start < ready_ns:
                continue
            if lo is not None and hi is not None and not (lo <= s.start <= hi):
                continue
            if best is None or s.start < best.start:
                best = s
        if best is None:
            return
        lat = best.start - ready_ns
        if lat < 0:
            return
        e = _ensure(mk)
        e["samples"].append(lat)
        e["points"].append((best.start, lat, best))
        if e["min_ns"] is None or lat < e["min_ns"]:
            e["min_ns"] = lat
            e["min_seg"] = best
        if e["max_ns"] is None or lat > e["max_ns"]:
            e["max_ns"] = lat
            e["max_seg"] = best

    for mk, create_ns in getattr(trace, "task_create_times", {}).items():
        _add(mk, create_ns)

    for ev in trace.sti_events:
        if ev.target != "task":
            continue
        note = (ev.note or "").strip()
        m = _LIFECYCLE_NOTE_RE.match(note)
        if not m or m.group(1).lower() != "resume":
            continue
        task_label = note[m.end():].strip()
        if not task_label:
            continue
        _add(_task_merge_key(task_label), ev.time)
    return by_mk


def _switch_overhead_rows(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    """Per-core kernel switch overhead rows.

    Returns list of
    ``(core, switches, min_ns, avg_ns, max_ns, total_ns, pct_of_span)``.
    """
    if lo is not None and hi is not None:
        span_ns = max(1, hi - lo)
    else:
        span_ns = max(1, trace.time_max - trace.time_min)
    rows: List[tuple] = []
    for core in trace.core_names:
        segs = trace.core_segs.get(core, [])
        samples: List[int] = []
        for i in range(1, len(segs)):
            prev, curr = segs[i - 1], segs[i]
            if lo is not None and hi is not None and not (lo <= curr.start <= hi):
                continue
            gap = curr.start - prev.end
            samples.append(gap if gap > 0 else 0)
        if not samples:
            continue
        total = sum(samples)
        avg = int(round(total / len(samples)))
        rows.append((
            core,
            len(samples),
            min(samples),
            avg,
            max(samples),
            total,
            100.0 * total / span_ns,
        ))
    return rows


def _concurrent_core_active_rows(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    """Time spent with N cores concurrently active (non-IDLE, non-TICK).

    Returns ``(active_cores, duration_ns, pct_of_span)`` rows for N with
    non-zero duration.
    """
    t0 = lo if lo is not None else trace.time_min
    t1 = hi if hi is not None else trace.time_max
    span_ns = max(1, t1 - t0)
    n_cores = len(trace.core_names)
    if n_cores <= 0 or t1 <= t0:
        return []

    events: List[Tuple[int, int]] = []
    for core in trace.core_names:
        for s in trace.core_segs.get(core, ()):
            _cid, _tid, tname = _parse_task_name(s.task)
            if _is_idle_task_name(tname) or tname == "TICK":
                continue
            a, b = s.start, s.end
            if b <= t0 or a >= t1:
                continue
            if a < t0:
                a = t0
            if b > t1:
                b = t1
            if b <= a:
                continue
            events.append((a, 1))
            events.append((b, -1))
    events.sort(key=lambda e: (e[0], e[1]))

    dur = [0] * (n_cores + 1)
    active = 0
    prev_t = t0
    for t, delta in events:
        if t > prev_t:
            level = max(0, min(n_cores, active))
            dur[level] += t - prev_t
            prev_t = t
        active += delta
    if t1 > prev_t:
        level = max(0, min(n_cores, active))
        dur[level] += t1 - prev_t

    rows: List[tuple] = []
    for n, d in enumerate(dur):
        if d <= 0:
            continue
        rows.append((n, d, 100.0 * d / span_ns))
    return rows


def _dispatch_latency_plot_points(
    trace: "BtfTrace",
    merge_key: str,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    """``(dispatch_ns, latency_ns, seg)`` for one task's dispatch samples."""
    data = _dispatch_latency_by_mk(trace, lo, hi).get(merge_key)
    if not data:
        return []
    return list(data.get("points") or ())


def _switch_overhead_plot_points(
    trace: "BtfTrace",
    core: str,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    """``(switch_ns, gap_ns, None)`` per consecutive core_segs gap on *core*."""
    segs = list(trace.core_segs.get(core, ()))
    if len(segs) < 2:
        return []
    points: List[tuple] = []
    for i in range(1, len(segs)):
        prev, curr = segs[i - 1], segs[i]
        if lo is not None and hi is not None and not (lo <= curr.start <= hi):
            continue
        gap = curr.start - prev.end
        points.append((curr.start, gap if gap > 0 else 0, None))
    return points


def _concurrency_level_plot_points(
    trace: "BtfTrace",
    active_cores: int,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    """``(interval_start_ns, duration_ns, None)`` while N cores are active."""
    t0 = lo if lo is not None else trace.time_min
    t1 = hi if hi is not None else trace.time_max
    n_cores = len(trace.core_names)
    if n_cores <= 0 or t1 <= t0:
        return []
    target = max(0, min(n_cores, int(active_cores)))

    events: List[Tuple[int, int]] = []
    for core in trace.core_names:
        for s in trace.core_segs.get(core, ()):
            _cid, _tid, tname = _parse_task_name(s.task)
            if _is_idle_task_name(tname) or tname == "TICK":
                continue
            a, b = s.start, s.end
            if b <= t0 or a >= t1:
                continue
            if a < t0:
                a = t0
            if b > t1:
                b = t1
            if b <= a:
                continue
            events.append((a, 1))
            events.append((b, -1))
    events.sort(key=lambda e: (e[0], e[1]))

    points: List[tuple] = []
    active = 0
    prev_t = t0
    for t, delta in events:
        if t > prev_t:
            level = max(0, min(n_cores, active))
            if level == target:
                points.append((prev_t, t - prev_t, None))
            prev_t = t
        active += delta
    if t1 > prev_t:
        level = max(0, min(n_cores, active))
        if level == target:
            points.append((prev_t, t1 - prev_t, None))
    return points


def _task_cores_used(trace: "BtfTrace", merge_key: str) -> set:
    return {s.core for s in trace.seg_map_by_merge_key.get(merge_key, ())}


def _task_core_sets(trace: "BtfTrace") -> dict:
    """merge_key -> set of core names its segments run on (memoised on *trace*).

    Parity with web ``taskCoreSets`` — the Core Filter uses this to scope the
    Task view / legend list to tasks that actually run on a selected core.
    """
    cache = getattr(trace, "_task_core_sets_cache", None)
    if cache is not None:
        return cache
    out: dict = {}
    for mk, segs in (getattr(trace, "seg_map_by_merge_key", None) or {}).items():
        out[mk] = {s.core for s in segs}
    try:
        trace._task_core_sets_cache = out
    except Exception:
        pass
    return out


def _task_runs_on_selected_core(trace: "BtfTrace", merge_key: str,
                                core_keys) -> bool:
    """True unless the Core Filter is active and *merge_key* never runs on a
    selected core.  Parity with web ``taskRunsOnSelectedCore``.
    """
    if not core_keys:
        return True
    total = len(getattr(trace, "core_names", None) or ())
    if total and len(core_keys) >= total:
        return True
    cset = core_keys if isinstance(core_keys, (set, frozenset)) else set(core_keys)
    task_cores = _task_core_sets(trace).get(merge_key)
    if not task_cores:
        return True  # unknown -> don't hide
    return not cset.isdisjoint(task_cores)

def _is_migrated_task(trace: "BtfTrace", merge_key: str) -> bool:
    mks = trace.migrated_mks or trace.migrations_by_mk
    if mks:
        return merge_key in mks
    return len(_task_cores_used(trace, merge_key)) >= 2

def _migrations_in_range(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> Sequence["MigrationEvent"]:
    """Migrations with ns in [lo, hi] (inclusive). Uses migration_times bisect."""
    migs = trace.migrations
    if not migs:
        return migs
    if lo is None and hi is None:
        return migs
    times = trace.migration_times
    if not times or len(times) != len(migs):
        return [
            m for m in migs
            if (lo is None or m.ns >= lo) and (hi is None or m.ns <= hi)
        ]
    i0 = 0 if lo is None else bisect_left(times, lo)
    i1 = len(migs) if hi is None else bisect_right(times, hi)
    return migs[i0:i1]

def _core_segs_in_range(
    trace: "BtfTrace",
    core: str,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> Sequence["TaskSegment"]:
    segs = trace.core_segs.get(core, [])
    if not segs or lo is None or hi is None:
        return segs
    starts = trace.core_seg_starts.get(core)
    if not starts or len(starts) != len(segs):
        starts = [s.start for s in segs]
    i0 = max(0, bisect_left(starts, lo) - 1)
    i1 = bisect_right(starts, hi)
    return segs[i0:i1]

def _task_segs_in_range(
    trace: "BtfTrace",
    mk: str,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> Sequence["TaskSegment"]:
    segs = trace.seg_map_by_merge_key.get(mk, [])
    if not segs or lo is None or hi is None:
        return segs
    starts = trace.seg_start_by_merge_key.get(mk)
    if not starts or len(starts) != len(segs):
        starts = [s.start for s in segs]
    i0 = max(0, bisect_left(starts, lo) - 1)
    i1 = bisect_right(starts, hi)
    return segs[i0:i1]

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
    if lo is None and hi is None and trace.migration_rows_full is not None:
        return list(trace.migration_rows_full)
    scale = trace.time_scale
    tick_times = trace.tick_sti_times
    rows: List[tuple] = []
    for mk in trace.tasks:
        if not _is_migrated_task(trace, mk):
            continue
        segs = (_task_segs_in_range(trace, mk, lo, hi)
                if lo is not None and hi is not None
                else trace.seg_map_by_merge_key.get(mk, []))
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
        # Dwell / gap columns: trim trailing zeros to match the web Core
        # Migrations table + Analysis finding (web uses formatTime/formatMigrationGapTime).
        avg_dwell = _format_time_web(avg_dwell_tu, scale) if avg_dwell_tu else "-"
        raw = trace.task_repr.get(mk, mk)
        disp = _task_display_name(raw)
        cores_str = ", ".join(sorted(cores_in_scope or cores, key=_core_sort_key_tuple))
        rows.append((
            mk, disp, len(migs), n_cores, cores_str, primary, primary_pct,
            ping, sti_near,
            _format_time_web(int(avg_after), scale) if avg_after else "-",
            _format_time_web(int(avg_other), scale) if avg_other else "-",
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

# Encode/decode directed core-pair keys for Core-Pair Gap/Rate plot sessions.
_PAIR_PLOT_KEY_SEP = "\x00"
# Accent for lock-bounce migration samples on pair charts (matches Bounce %).
_PAIR_BOUNCE_POINT_COLOR = "#FF9800"

def _pair_plot_key(from_core: str, to_core: str) -> str:
    return f"{from_core}{_PAIR_PLOT_KEY_SEP}{to_core}"

def _parse_pair_plot_key(key: str) -> Optional[Tuple[str, str]]:
    if not key or _PAIR_PLOT_KEY_SEP not in key:
        return None
    fc, tc = key.split(_PAIR_PLOT_KEY_SEP, 1)
    if not fc or not tc:
        return None
    return fc, tc

def _pair_migrations(
    trace: "BtfTrace", from_core: str, to_core: str,
    lo: Optional[int] = None, hi: Optional[int] = None,
) -> List["MigrationEvent"]:
    """Directed From→To migrations in scope, time-sorted."""
    out: List[MigrationEvent] = [
        m for m in _migrations_in_range(trace, lo, hi)
        if m.from_core == from_core and m.to_core == to_core
    ]
    out.sort(key=lambda m: m.ns)
    return out

def _pair_gap_plot_points(
    trace: "BtfTrace", from_core: str, to_core: str,
    lo: Optional[int] = None, hi: Optional[int] = None,
) -> List[Tuple]:
    """One point per pair migration with positive gap; bounce events carry accent color."""
    bounce_ns = trace.lock_bounce_migration_ns
    pts: List[Tuple] = []
    for m in _pair_migrations(trace, from_core, to_core, lo, hi):
        if m.gap_ns <= 0:
            continue
        if m.ns in bounce_ns:
            pts.append((m.ns, m.gap_ns, m, _PAIR_BOUNCE_POINT_COLOR))
        else:
            pts.append((m.ns, m.gap_ns, m))
    return pts

def _pair_rate_plot_points(
    trace: "BtfTrace", from_core: str, to_core: str,
    lo: Optional[int] = None, hi: Optional[int] = None,
) -> List[Tuple]:
    """One point per consecutive pair-migration: y = time since previous on this corridor."""
    migs = _pair_migrations(trace, from_core, to_core, lo=None, hi=None)
    bounce_ns = trace.lock_bounce_migration_ns
    pts: List[Tuple] = []
    for i in range(1, len(migs)):
        cur = migs[i]
        if lo is not None and hi is not None and (cur.ns < lo or cur.ns > hi):
            continue
        gap = cur.ns - migs[i - 1].ns
        if gap <= 0:
            continue
        if cur.ns in bounce_ns:
            pts.append((cur.ns, gap, cur, _PAIR_BOUNCE_POINT_COLOR))
        else:
            pts.append((cur.ns, gap, cur))
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

# STI take/give/suspend within this many native time units of a slice end is
# treated as the cause of the following off-CPU gap (review items A1 / A4).
_OFFCPU_STI_WINDOW = 50

_OFFCPU_GAP_KINDS = ("preempted", "blocked", "suspended", "period_wait", "unknown")


def _classify_offcpu_gaps(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> "Dict[str, List[Tuple[int, str, int]]]":
    """Per task (merge key) → list of ``(gap_ns, kind, at_ns)`` for every off-CPU
    gap between consecutive slices.  ``at_ns`` is the resume time (next slice
    start).  ``kind`` is one of ``_OFFCPU_GAP_KINDS``:

    - ``preempted``  — a higher-or-equal task actually ran on the victim's core
      during the gap (involuntary),
    - ``blocked``    — an STI ``take``/``recv`` on that core ends the slice
      (waiting on a sync object),
    - ``suspended``  — an STI ``suspend`` for this task ends the slice
      (voluntary self-suspend),
    - ``period_wait``— nothing but IDLE ran on the core for the whole gap
      (the task is sleeping between activations),
    - ``unknown``    — none of the above (partial coverage, capture gap, …).

    Foundation for the Switch Reason Breakdown (A1) and Ready-Gap (A4) sections.
    """
    core_segs: Dict[str, List["TaskSegment"]] = trace.core_segs
    core_starts: Dict[str, List[int]] = {
        c: [s.start for s in segs] for c, segs in core_segs.items()
    }
    # STI cause windows, indexed by source core and time.
    sync_ev: List[Tuple[int, str]] = []
    for tgt in ("mutex", "sem", "queue"):
        for ev in trace.sti_events_by_target.get(tgt, ()):  # noqa: E501
            note = ev.note or ""
            if note.startswith("take") or note.startswith("recv"):
                sync_ev.append((ev.time, ev.core))
    sync_ev.sort()
    sync_times = [t for t, _ in sync_ev]
    suspend_by_mk: Dict[str, List[int]] = {}
    for ev in trace.sti_events_by_target.get("task", ()):
        note = ev.note or ""
        if not note.startswith("suspend"):
            continue
        m = re.match(r"^suspend\s+(.+)$", note)
        if not m:
            continue
        smk = _task_merge_key(m.group(1).strip())
        suspend_by_mk.setdefault(smk, []).append(ev.time)
    for lst in suspend_by_mk.values():
        lst.sort()

    out: Dict[str, List[Tuple[int, str, int]]] = {}
    for mk, segs in trace.seg_map_by_merge_key.items():
        if len(segs) < 2:
            continue
        raw = trace.task_repr.get(mk, mk)
        _, _, tname = _parse_task_name(raw)
        if _is_idle_task_name(tname) or tname == "TICK":
            continue
        ordered = sorted(segs, key=lambda s: s.start)
        gaps: List[Tuple[int, str, int]] = []
        susp = suspend_by_mk.get(mk, [])
        for i in range(1, len(ordered)):
            prev, nxt = ordered[i - 1], ordered[i]
            g0, g1 = prev.end, nxt.start
            if g1 <= g0:
                continue
            if lo is not None and hi is not None and not (
                _seg_fully_in_range(prev, lo, hi)
                and _seg_fully_in_range(nxt, lo, hi)
            ):
                continue
            gap = g1 - g0
            core = prev.core
            cslist = core_segs.get(core) or []
            cstarts = core_starts.get(core) or []

            non_idle_overlap = 0
            idle_overlap = 0
            j = max(0, bisect_right(cstarts, g1 - 1) - 1)
            while j < len(cslist):
                cs = cslist[j]
                j += 1
                if cs.start >= g1:
                    break
                if cs.end <= g0:
                    continue
                ov = min(cs.end, g1) - max(cs.start, g0)
                if ov <= 0:
                    continue
                cmk = _task_merge_key(cs.task)
                if cmk == mk:
                    continue
                cn = _parse_task_name(trace.task_repr.get(cmk, cs.task))[2]
                if _is_idle_task_name(cn):
                    idle_overlap += ov
                elif cn != "TICK":
                    non_idle_overlap += ov

            if non_idle_overlap > 0:
                kind = "preempted"
            elif susp and _has_time_near(susp, g0, _OFFCPU_STI_WINDOW):
                kind = "suspended"
            elif _has_sync_cause(sync_times, sync_ev, g0, core, _OFFCPU_STI_WINDOW):
                kind = "blocked"
            elif idle_overlap >= 0.8 * gap:
                kind = "period_wait"
            else:
                kind = "unknown"
            gaps.append((gap, kind, g1))
        if gaps:
            out[mk] = gaps
    return out


def _has_time_near(sorted_times: "List[int]", t: int, window: int) -> bool:
    i = bisect_left(sorted_times, t - window)
    return i < len(sorted_times) and sorted_times[i] <= t + window


def _has_sync_cause(sorted_times: "List[int]", ev_pairs: "List[Tuple[int, str]]",
                    t: int, core: str, window: int) -> bool:
    i = bisect_left(sorted_times, t - window)
    while i < len(sorted_times) and sorted_times[i] <= t + window:
        if ev_pairs[i][1] == core:
            return True
        i += 1
    return False


def _switch_reason_rows(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    """Per-task off-CPU switch-reason counts (review item A1).

    Row: ``(mk, name, preempted, blocked, suspended, period_wait, unknown,
    total, preempt_rate_per_s)``.  ``preempt_rate_per_s`` is the involuntary
    (preempted) switch rate — the number most worth ranking on.
    """
    from .timeline_util import _to_ns
    if lo is not None and hi is not None:
        span = max(1, hi - lo)
    else:
        span = max(1, trace.time_max - trace.time_min)
    span_s = _to_ns(span, trace.time_scale) / 1_000_000_000.0
    by_mk = _classify_offcpu_gaps(trace, lo, hi)
    rows: List[tuple] = []
    for mk, gaps in by_mk.items():
        counts = {k: 0 for k in _OFFCPU_GAP_KINDS}
        for _g, kind, _at in gaps:
            counts[kind] += 1
        total = len(gaps)
        name = _task_display_name(trace.task_repr.get(mk, mk))
        rate = counts["preempted"] / span_s if span_s > 0 else 0.0
        rows.append((
            mk, name,
            counts["preempted"], counts["blocked"], counts["suspended"],
            counts["period_wait"], counts["unknown"], total, rate,
        ))
    rows.sort(key=lambda r: (-r[2], -r[7], r[1].lower()))
    return rows


def _sched_load_over_time_rows(
    trace: "BtfTrace",
    events: "Sequence[dict]",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[dict]:
    """Per-time-bin scheduling load (review items A2 + A9).

    Each dict: ``{start, stop, jump_ns, ctx, ctx_per_s, sigma_pct, lb_score,
    busiest_core, peak_pct}``.  ``sigma_pct`` / ``lb_score`` are the per-bin
    core-utilisation standard deviation and load-balance score, so an imbalance
    can be placed in time rather than only detected overall.
    """
    from .timeline_util import _to_ns
    grid_fn = globals().get("core_util_over_time")
    if grid_fn is None:
        from .ux_explore import core_util_over_time as grid_fn
    grid = grid_fn(events, list(trace.core_names or []), lo, hi)
    bins = grid.get("bins") or []
    cores = grid.get("cores") or list(trace.core_names or [])
    if not bins:
        return []
    core_seg_starts = {
        c: sorted(s.start for s in trace.core_segs.get(c, ())) for c in cores
    }
    out: List[dict] = []
    for b in bins:
        b0 = int(b.get("start") or 0)
        b1 = int(b.get("stop") or b0 + 1)
        ctx = 0
        for c in cores:
            starts = core_seg_starts.get(c) or []
            ctx += bisect_left(starts, b1) - bisect_left(starts, b0)
        cells = b.get("cells") or {}
        pcts = [float((cells.get(c) or {}).get("pct") or 0.0) for c in cores]
        sigma = _core_util_stddev(pcts) if len(pcts) >= 2 else 0.0
        lb_score = None
        if len(pcts) >= 2 and sum(pcts) > 0.0:
            lb_score = max(0.0, 100.0 * (1.0 - _gini_coefficient(pcts)))
        span_s = _to_ns(max(1, b1 - b0), trace.time_scale) / 1_000_000_000.0
        out.append({
            "start": b0, "stop": b1, "jump_ns": b0,
            "ctx": ctx,
            "ctx_per_s": (ctx / span_s) if span_s > 0 else 0.0,
            "sigma_pct": sigma,
            "lb_score": lb_score,
            "busiest_core": b.get("peak_core") or "",
            "peak_pct": float(b.get("peak_pct") or 0.0),
        })
    return out


def _activation_latency_rows(
    trace: "BtfTrace",
    events: "Sequence[dict]",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    """Per periodic task, how far each activation lands from a fitted ideal
    periodic grid ``phi + k*T`` (review item A3).

    ``T`` is the p50 inter-arrival gap (from :func:`analyze_task_periods`); the
    grid is anchored at the first activation in scope and the error for an
    activation ``t`` is ``min_k |t - (anchor + k*T)|``.  Row (variability shape,
    matching the exec / inter tables):
    ``(mk, name, count, min, avg, max, jitter, sigma, p50, p95, p99)`` as
    formatted strings, largest max first.  Needs >= 3 activations per task.
    """
    period_fn = globals().get("analyze_task_periods")
    if period_fn is None:
        from .ux_explore import analyze_task_periods as period_fn
    scale = trace.time_scale
    period_by_mk: Dict[str, int] = {}
    for prow in period_fn(events, 3):
        mk = str(prow.get("mk") or "")
        t_ns = int(prow.get("expected_ns") or 0)
        if mk and t_ns > 0:
            period_by_mk[mk] = t_ns
    starts_by_mk: Dict[str, List[int]] = {}
    for ev in events or []:
        if not isinstance(ev, dict) or ev.get("kind") != "inter":
            continue
        mk = str(ev.get("mk") or ev.get("task") or "")
        if mk not in period_by_mk:
            continue
        s = int(ev.get("start") or 0)
        if lo is not None and hi is not None and not (lo <= s <= hi):
            continue
        starts_by_mk.setdefault(mk, []).append(s)
    raw: List[tuple] = []
    for mk, starts in starts_by_mk.items():
        if len(starts) < 3:
            continue
        starts.sort()
        period = period_by_mk[mk]
        anchor = starts[0]
        errs = sorted(
            abs(t - (anchor + round((t - anchor) / period) * period))
            for t in starts
        )
        n = len(errs)
        mn, mx = errs[0], errs[-1]
        avg = int(round(sum(errs) / n))
        p95 = errs[_nearest_rank_index(n, 0.95)]
        jitter, sigma_f, p50, p99 = _sample_variability(errs)
        name = _task_display_name(trace.task_repr.get(mk, mk))
        raw.append((mk, name, n, mn, avg, mx, int(jitter),
                    int(round(sigma_f)), int(p50), p95, int(p99)))
    raw.sort(key=lambda r: (-r[5], -r[4], r[1].lower()))
    return [
        (mk, name, n,
         _format_time(mn, scale), _format_time(avg, scale),
         _format_time(mx, scale), _format_time(jitter, scale),
         _format_time(sigma, scale), _format_time(p50, scale),
         _format_time(p95, scale), _format_time(p99, scale))
        for mk, name, n, mn, avg, mx, jitter, sigma, p50, p95, p99 in raw
    ]


_READY_GAP_KINDS = ("preempted", "blocked", "unknown")


def _ready_gap_rows(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    """Per task, off-CPU time it spent arguably able to run — the ready-gap /
    starvation view (review item A4).

    From :func:`_classify_offcpu_gaps`, keeps the ``preempted`` / ``blocked`` /
    ``unknown`` gaps and drops ``suspended`` / ``period_wait`` (the task
    voluntarily off-CPU).  Row (raw ns, formatted by the caller):
    ``(mk, name, count, longest_ns, total_ns, avg_ns, p95_ns, preempt_pct)``,
    longest gap first.
    """
    by_mk = _classify_offcpu_gaps(trace, lo, hi)
    rows: List[tuple] = []
    for mk, gaps in by_mk.items():
        ready = sorted(g for g, k, _at in gaps if k in _READY_GAP_KINDS)
        if not ready:
            continue
        preempt_sum = sum(g for g, k, _at in gaps if k == "preempted")
        n = len(ready)
        total = sum(ready)
        avg = int(round(total / n))
        p95 = ready[_nearest_rank_index(n, 0.95)]
        preempt_pct = (100.0 * preempt_sum / total) if total > 0 else 0.0
        name = _task_display_name(trace.task_repr.get(mk, mk))
        rows.append((mk, name, n, ready[-1], total, avg, p95, preempt_pct))
    rows.sort(key=lambda r: (-r[3], -r[4], r[1].lower()))
    return rows


def _idle_analysis_rows(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> "Tuple[List[tuple], int, int]":
    """Per-core idle analysis plus the longest all-cores-idle window (A5).

    Returns ``(rows, all_idle_span_ns, all_idle_start_ns)``; each row is
    ``(core, total_ns, longest_ns, longest_start_ns, fragments, p95_ns)``,
    most-idle core first.  ``all_idle_span_ns`` is the longest stretch where
    every core was IDLE at once (0 when it never happened).
    """
    eff_lo = lo if lo is not None else trace.time_min
    eff_hi = hi if hi is not None else trace.time_max
    idle_by_core: Dict[str, List[Tuple[int, int]]] = {}
    rows: List[tuple] = []
    for core in trace.core_names:
        spans: List[Tuple[int, int]] = []
        for seg in trace.core_segs.get(core, ()):  # segments are start-sorted
            slo = max(int(seg.start), eff_lo)
            shi = min(int(seg.end), eff_hi)
            if slo >= shi:
                continue
            if _is_idle_task_name(_parse_task_name(seg.task)[2]):
                spans.append((slo, shi))
        idle_by_core[core] = spans
        if not spans:
            continue
        durs = sorted(b - a for a, b in spans)
        longest = max(spans, key=lambda p: p[1] - p[0])
        p95 = durs[_nearest_rank_index(len(durs), 0.95)]
        rows.append((core, sum(durs), longest[1] - longest[0], longest[0],
                     len(spans), p95))
    rows.sort(key=lambda r: (-r[1], r[0]))

    all_span, all_start = 0, eff_lo
    cores = list(trace.core_names)
    if cores and all(idle_by_core.get(c) for c in cores):
        evts: List[Tuple[int, int]] = []
        for c in cores:
            for a, b in idle_by_core[c]:
                evts.append((a, 1))
                evts.append((b, -1))
        evts.sort()
        active, seg_start, n = 0, None, len(cores)
        for t, delta in evts:
            if seg_start is not None and active == n and t > seg_start:
                if t - seg_start > all_span:
                    all_span, all_start = t - seg_start, seg_start
            active += delta
            seg_start = t if active == n else None
    return rows, all_span, all_start


def _activation_latency_plot_points(
    trace: "BtfTrace",
    mk: str,
    events: "Sequence[dict]",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    """``(activation_ns, abs_error_ns, None)`` vs ideal ``phi + k*T`` grid."""
    period_fn = globals().get("analyze_task_periods")
    if period_fn is None:
        from .ux_explore import analyze_task_periods as period_fn
    period = 0
    for prow in period_fn(events, 3):
        if str(prow.get("mk") or "") == mk:
            period = int(prow.get("expected_ns") or 0)
            break
    if period <= 0:
        return []
    starts: List[int] = []
    for ev in events or []:
        if not isinstance(ev, dict) or ev.get("kind") != "inter":
            continue
        if str(ev.get("mk") or ev.get("task") or "") != mk:
            continue
        s = int(ev.get("start") or 0)
        if lo is not None and hi is not None and not (lo <= s <= hi):
            continue
        starts.append(s)
    if len(starts) < 3:
        return []
    starts.sort()
    anchor = starts[0]
    return [
        (t, abs(t - (anchor + round((t - anchor) / period) * period)), None)
        for t in starts
    ]


def _ready_gap_plot_points(
    trace: "BtfTrace",
    mk: str,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    """``(resume_ns, gap_ns, None)`` for ready-gap kinds (preempted/blocked/unknown)."""
    gaps = (_classify_offcpu_gaps(trace, lo, hi).get(mk) or [])
    return [
        (int(at), int(gap), None)
        for gap, kind, at in gaps
        if kind in _READY_GAP_KINDS and int(gap) > 0
    ]


def _idle_fragment_plot_points(
    trace: "BtfTrace",
    core: str,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    """``(idle_start_ns, duration_ns, None)`` per IDLE fragment on *core*."""
    eff_lo = lo if lo is not None else trace.time_min
    eff_hi = hi if hi is not None else trace.time_max
    pts: List[tuple] = []
    for seg in trace.core_segs.get(core, ()):
        slo = max(int(seg.start), eff_lo)
        shi = min(int(seg.end), eff_hi)
        if slo >= shi:
            continue
        if not _is_idle_task_name(_parse_task_name(seg.task)[2]):
            continue
        pts.append((slo, shi - slo, None))
    return pts


def _sync_hold_plot_points(
    trace: "BtfTrace",
    obj_key: str,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    """``(hold_start_ns, duration_ns, hold_dict)`` for one sync object."""
    if not getattr(trace, "has_sync_object_instrumentation", False):
        return []
    obj = (trace.sync_objects or {}).get(obj_key)
    if not isinstance(obj, dict):
        return []
    pts: List[tuple] = []
    for h in obj.get("holds") or []:
        if not isinstance(h, dict):
            continue
        start = int(h.get("start_ns") or 0)
        stop = int(h.get("stop_ns") or 0)
        if stop <= start:
            continue
        if lo is not None and hi is not None and not (stop > lo and start < hi):
            continue
        pts.append((start, stop - start, h))
    return pts


def _mutex_wait_plot_points(
    waits: "Sequence[dict]",
    waiter_mk: str,
    obj_key: str,
) -> List[tuple]:
    """``(wait_start_ns, duration_ns, wait_dict)`` for one waiter×object pair."""
    wk = str(waiter_mk or "")
    obj = str(obj_key or "")
    if not wk or not obj:
        return []
    pts: List[tuple] = []
    for w in waits or []:
        if not isinstance(w, dict):
            continue
        if str(w.get("waiter_mk") or "") != wk:
            continue
        if str(w.get("object") or "") != obj:
            continue
        dur = int(w.get("duration") or 0)
        if dur <= 0:
            continue
        pts.append((int(w.get("start") or 0), dur, w))
    return pts


def _sync_level_rows(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[tuple]:
    """Running fill level of every queue / semaphore over the scope (A8).

    ``+1`` on give/send, ``-1`` on take/recv, floored at 0; ``create`` resets to
    0.  Row: ``(key, kind, ptr, label, max_level, time_at_max_ns, end_level,
    starved, peak_start_ns, first_starve_ns)`` where ``starved`` counts
    take/recv issued while the level was 0, ``peak_start_ns`` is the first
    time the level reached ``max_level`` (or ``None``), and ``first_starve_ns``
    is the first starved take/recv (or ``None``). Highest peak first; empty
    without queue/semaphore instrumentation.
    """
    seq: Dict[str, List[Tuple[int, int]]] = {}
    meta: Dict[str, Tuple[str, str]] = {}
    for tgt in ("queue", "sem"):
        for ev in trace.sti_events_by_target.get(tgt, ()):
            if lo is not None and hi is not None and not (lo <= ev.time <= hi):
                continue
            parsed = _parse_sync_object_note(ev.note)
            if not parsed:
                continue
            action, ptr = parsed
            if action == "delete":
                continue
            key = _sync_object_key(tgt, ptr)
            meta.setdefault(key, (tgt, ptr))
            delta = (1 if action in ("give", "send")
                     else -1 if action in ("take", "recv") else 0)
            seq.setdefault(key, []).append((ev.time, delta))
    eff_hi = hi if hi is not None else trace.time_max
    rows: List[tuple] = []
    for key, evts in seq.items():
        evts.sort()
        lvl = max_level = starved = 0
        first_starve: Optional[int] = None
        for t, d in evts:
            if d == 0:
                lvl = 0
            elif d < 0 and lvl == 0:
                starved += 1
                if first_starve is None:
                    first_starve = int(t)
            else:
                lvl = max(0, lvl + d)
                max_level = max(max_level, lvl)
        lvl, time_at_max, last_t = 0, 0, evts[0][0]
        peak_start: Optional[int] = None
        for t, d in evts:
            if t > last_t and lvl == max_level and max_level > 0:
                time_at_max += t - last_t
            last_t = t
            if d == 0:
                lvl = 0
            elif d < 0 and lvl == 0:
                pass
            else:
                lvl = max(0, lvl + d)
                if max_level > 0 and lvl == max_level and peak_start is None:
                    peak_start = int(t)
        if eff_hi > last_t and lvl == max_level and max_level > 0:
            time_at_max += eff_hi - last_t
        tgt, ptr = meta[key]
        rows.append((key, tgt, ptr, f"{tgt} {ptr}", max_level, time_at_max,
                     lvl, starved, peak_start, first_starve))
    rows.sort(key=lambda r: (-r[4], -r[7], r[3]))
    return rows


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
    for m in _migrations_in_range(trace, lo, hi):
        if bounce_only and m.ns not in trace.lock_bounce_migration_ns:
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
    for m in _migrations_in_range(trace, lo, hi):
        if bounce_only and m.ns not in trace.lock_bounce_migration_ns:
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
_CHORD_TAPER_DEST_RATIO = 0.4
_CHORD_GRAD_SOURCE_STOP = 0.7
_CHORD_RIBBON_MAX_HALF = 7.0
# Split core rings (TODO2): outer = egress/departures, inner = ingress/arrivals.
_CHORD_ARC_OUTER = 12.0
_CHORD_ARC_INNER = 8.0


def _chord_ring_geometry(radius: float) -> Tuple[float, float, float]:
    """Return ``(r_egress, r_ingress, r_ribbon)`` for a chord diagram of radius *radius*."""
    r_egress = float(radius)
    r_ingress = r_egress - _CHORD_ARC_OUTER - 2.0
    r_ribbon = r_ingress - _CHORD_ARC_INNER / 2.0 - 2.0
    return r_egress, r_ingress, r_ribbon


def _chord_hit_ring(dist: float, radius: float) -> Optional[str]:
    """Which split ring *dist* from the centre hits: ``'egress'``, ``'ingress'``, or None."""
    r_egress, r_ingress, _ = _chord_ring_geometry(radius)
    if abs(dist - r_egress) <= _CHORD_ARC_OUTER / 2.0 + 3.0:
        return "egress"
    if abs(dist - r_ingress) <= _CHORD_ARC_INNER / 2.0 + 3.0:
        return "ingress"
    return None

@dataclass
class ChordArc:
    """One core's arc segment in the migration chord diagram."""
    core: str
    index: int
    start_angle: float
    end_angle: float
    total: float
    out_total: float = 0.0
    in_total: float = 0.0

@dataclass
class ChordLayout:
    """Circular layout for the migration chord diagram (see _build_chord_layout)."""
    arcs: List[ChordArc]
    # tick_angles[i][j] = angle (radians) on core i's arc pointing toward core j.
    tick_angles: List[Dict[int, float]]
    egress_ticks: List[Dict[int, float]] = field(default_factory=list)
    ingress_ticks: List[Dict[int, float]] = field(default_factory=list)
    grid: Optional[List[List[float]]] = None

    def tick_angle(self, i: int, j: int) -> float:
        if 0 <= i < len(self.tick_angles) and j in self.tick_angles[i]:
            return self.tick_angles[i][j]
        if 0 <= i < len(self.arcs):
            arc = self.arcs[i]
            return (arc.start_angle + arc.end_angle) / 2
        return 0.0

    def egress_tick_angle(self, i: int, j: int) -> float:
        if 0 <= i < len(self.egress_ticks) and j in self.egress_ticks[i]:
            return self.egress_ticks[i][j]
        return self.tick_angle(i, j)

    def ingress_tick_angle(self, i: int, j: int) -> float:
        if 0 <= i < len(self.ingress_ticks) and j in self.ingress_ticks[i]:
            return self.ingress_ticks[i][j]
        return self.tick_angle(i, j)

    def ribbon_half_widths(self, i: int, j: int,
                           max_count: float = 1.0) -> Tuple[float, float]:
        g = self.grid or []
        count = g[i][j] if i < len(g) and j < len(g[i]) else 0
        if not count:
            return 0.0, 0.0
        m = max_count or 1.0
        src = max(0.75, min(_CHORD_RIBBON_MAX_HALF,
                            _CHORD_RIBBON_MAX_HALF * (count / m)))
        dst = max(0.5, src * _CHORD_TAPER_DEST_RATIO)
        return src, dst

def _trace_has_core_bounce_holds(trace: "BtfTrace") -> bool:
    """True if any sync-object hold crossed cores (cache-line lock bounce)."""
    if not getattr(trace, "has_sync_object_instrumentation", False):
        return False
    for obj in (getattr(trace, "sync_objects", None) or {}).values():
        for hold in obj.get("holds") or []:
            take_c = hold.get("take_core")
            give_c = hold.get("give_core")
            if take_c and give_c and take_c != give_c:
                return True
    return False


def _default_corridor_top_pct(core_count: int) -> int:
    if (core_count or 0) > 8:
        return 25
    return 100


_CORRIDOR_SHORT_DWELL_MS = 1
_CORRIDOR_HANDOFF_HATCH_PCT = 15
_CORRIDOR_TOP_N_OPTIONS = (5, 10, 25, 0)
_CORRIDOR_SORT_KEYS = (
    "rate", "pingpong", "dwell", "handoff", "share",
    "count", "net", "label",
)
# Path table: Core path first, then Sort by metrics (compact headers).
_CORRIDOR_TREE_COLS = (
    ("label", "Core path"),
    ("rate", "Rate"),
    ("count", "Count"),
    ("pingpong", "Ping"),
    ("dwell", "Dwell"),
    ("handoff", "Handoff"),
    ("net", "Net"),
    ("share", "Share"),
)
_CORRIDOR_TREE_TIPS = {
    "label": "Sort by Core path",
    "rate": "Sort by Migration rate",
    "count": "Sort by Migrations",
    "pingpong": "Sort by Ping-pong",
    "dwell": "Sort by Short dwell",
    "handoff": "Sort by Handoff",
    "net": "Sort by Net flow",
    "share": "Sort by Task share",
}
# Inspector workspace panes: Core path | heatmap | Topology (1:2:1).
_CI_SPLIT_RATIO = (1, 2, 1)
_CI_SPLIT_PANE_MIN = 160
_CI_TREE_COL_MIN = 40
_CI_TREE_NAME_W = 140
_CI_TREE_NUM_W = 56


def _corridor_tree_col_defaults() -> tuple:
    return tuple(
        _CI_TREE_NAME_W if key == "label" else _CI_TREE_NUM_W
        for key, _lab in _CORRIDOR_TREE_COLS
    )


def _parse_int_csv(text, n: int, fallback, lo: int = 1, hi: int = 8000):
    """Parse ``n`` comma-separated ints; return *fallback* on mismatch."""
    fb = tuple(fallback)
    if text is None or str(text).strip() == "":
        return fb
    parts = [p.strip() for p in str(text).split(",") if p.strip()]
    if len(parts) != int(n):
        return fb
    try:
        vals = [max(int(lo), min(int(hi), int(p))) for p in parts]
    except (TypeError, ValueError):
        return fb
    return tuple(vals)


def _format_int_csv(vals) -> str:
    return ",".join(str(int(v)) for v in vals)


def _scale_split_sizes(sizes, total: int, mins=None):
    """Scale three pane sizes to *total* px, keeping their ratio."""
    n = 3
    if mins is None:
        mins = (_CI_SPLIT_PANE_MIN,) * n
    mins = tuple(int(m) for m in mins)[:n]
    raw = list(sizes) if sizes is not None and len(list(sizes)) == n else list(_CI_SPLIT_RATIO)
    raw = [max(1, int(v)) for v in raw]
    total = max(int(total), sum(mins))
    ssum = sum(raw) or 1
    out = [max(mins[i], int(total * raw[i] / ssum)) for i in range(n)]
    extra = total - sum(out)
    heat = 1 if n > 1 else 0
    out[heat] = max(mins[heat], out[heat] + extra)
    return tuple(out)


def _corridor_tree_cell(row: dict, key: str, kind: str = "corridor") -> str:
    """Format one Inspector path-table cell. *kind* is corridor, task, or group."""
    if key == "label":
        return str(row.get("label") or "")
    if kind == "group":
        if key == "count":
            return str(int(row.get("count") or 0))
        return "—"
    if kind == "task":
        if key == "count":
            return str(int(row.get("count") or 0))
        if key == "handoff":
            pct = row.get("handoff_pct", row.get("bounce_pct", 0))
            return f"{float(pct or 0):.0f}%"
        if key == "share":
            return f"{float(row.get('share_pct') or 0):.0f}%"
        return "—"
    if key == "rate":
        return f"{float(row.get('rate_per_s') or 0):.1f}/s"
    if key == "count":
        return str(int(row.get("count") or 0))
    if key == "pingpong":
        return f"{float(row.get('ping_pong_pct') or 0):.0f}%"
    if key == "dwell":
        return f"{float(row.get('short_dwell_share') or 0):.0f}%"
    if key == "handoff":
        pct = row.get("handoff_pct", row.get("bounce_pct", 0))
        return f"{float(pct or 0):.0f}%"
    if key == "net":
        net = int(row.get("net") or 0)
        if net > 0:
            return f"+{net} ▲"
        if net < 0:
            return f"{net} ▼"
        return "0"
    if key == "share":
        task = row.get("primary_task") or {}
        if not task:
            return "—"
        return f"{float(task.get('share_pct') or 0):.0f}%"
    return "—"


def _corridor_short_dwell_threshold(time_scale: str) -> int:
    ns_per = {"ns": 1e9, "us": 1e6, "ms": 1e3, "s": 1.0}.get(time_scale or "ns", 1e9)
    return max(1, int(round((ns_per / 1000.0) * _CORRIDOR_SHORT_DWELL_MS)))


def _default_corridor_top_n(core_count: int) -> int:
    if (core_count or 0) > 8:
        return 10
    return 0


def _filter_corridors_by_top_n(corridors: list, n: int = 0) -> list:
    rows = list(corridors or [])
    try:
        limit = int(n)
    except (TypeError, ValueError):
        return rows
    if not rows or limit <= 0 or limit >= len(rows):
        return rows
    return sorted(
        rows,
        key=lambda c: (-int(c.get("count") or 0), str(c.get("label") or "")),
    )[:limit]


def _sort_corridors(corridors: list, sort_by: str = "rate",
                    descending: Optional[bool] = None) -> list:
    key = sort_by if sort_by in _CORRIDOR_SORT_KEYS else "rate"
    desc = (key != "label") if descending is None else bool(descending)

    def metric(c):
        if key == "pingpong":
            return float(c.get("ping_pong_pct") or 0)
        if key == "dwell":
            return float(c.get("short_dwell_share") or 0)
        if key == "handoff":
            return float(c.get("handoff_pct") or c.get("bounce_pct") or 0)
        if key == "share":
            task = c.get("primary_task") or {}
            return float(task.get("share_pct") or 0)
        if key == "count":
            return float(c.get("count") or 0)
        if key == "net":
            return float(c.get("net") or 0)
        return float(c.get("rate_per_s") or 0)

    rows = list(corridors or [])
    if key == "label":
        rows.sort(key=lambda c: -int(c.get("count") or 0))
        rows.sort(
            key=lambda c: str(c.get("label") or "").lower(), reverse=desc)
        return rows
    rows.sort(key=lambda c: (
        -metric(c) if desc else metric(c),
        -int(c.get("count") or 0),
        str(c.get("label") or ""),
    ))
    return rows

def _filter_corridors_by_top_pct(corridors: list, top_pct: int = 100) -> list:
    if not corridors or top_pct >= 100:
        return list(corridors or [])
    pct = max(1, min(100, int(top_pct)))
    sorted_rows = sorted(corridors, key=lambda c: c.get("count", 0), reverse=True)
    keep = max(1, math.ceil(len(sorted_rows) * (pct / 100.0)))
    threshold = sorted_rows[keep - 1].get("count", 0)
    return [c for c in corridors if c.get("count", 0) >= threshold]


def _filter_corridors_by_direction(corridors: list, mode: str,
                                   selected: Optional[dict] = None) -> list:
    """Keep corridors sharing the selected pair's source (egress) or dest (ingress)."""
    if not corridors or mode in (None, "", "all") or not selected:
        return list(corridors or [])
    if mode == "egress":
        want = selected.get("from_core")
        return [c for c in corridors if c.get("from_core") == want]
    if mode == "ingress":
        want = selected.get("to_core")
        return [c for c in corridors if c.get("to_core") == want]
    return list(corridors or [])


def _canon_numeric_id(token: str) -> Optional[str]:
    """Decimal digit string for a task-id token (`0011`/`0xB` → `11`)."""
    t = (token or "").strip().lower()
    if not t:
        return None
    try:
        if t.startswith("0x"):
            return str(int(t, 16))
        if t.isdigit():
            return str(int(t, 10))
    except ValueError:
        return None
    return None


def _corridor_task_ids_and_name(task: dict) -> Tuple[list, str]:
    """Task ids (canonical decimal) and bare name from a corridor task row."""
    ids: list = []
    name = ""

    def add_id(token) -> None:
        cid = _canon_numeric_id(str(token) if token is not None else "")
        if cid is not None and cid not in ids:
            ids.append(cid)

    def consider(raw) -> None:
        nonlocal name
        if raw is None or raw == "":
            return
        s = str(raw)
        norm = s.replace("\ufffd", "\x00")
        if norm[:1] == "\x00":
            sep = norm.find("\x00", 1)
            if sep > 0:
                add_id(norm[1:sep])
                if not name:
                    name = norm[sep + 1:]
        _core, task_id, nm = _parse_task_name(s)
        if task_id is not None:
            add_id(task_id)
            if not name:
                name = nm
        collapsed = norm.replace("\x00", "")
        m = re.match(r"^(\d+)(\D.*)$", collapsed)
        if m:
            add_id(m.group(1))
            if not name:
                name = m.group(2)

    if task.get("task_id") is not None:
        add_id(task.get("task_id"))
    consider(task.get("mk"))
    consider(task.get("label"))
    if not name:
        name = str(task.get("label") or "")
    return ids, name


def _corridor_task_query_hit(task: dict, q: str) -> bool:
    """True when *q* matches this task.

    A pure decimal query (`28`, `0028`) is an exact task id — it must not
    hit `CS[128]` / `[0/0128]CS` via substring. Name queries stay substring.
    """
    ids, name = _corridor_task_ids_and_name(task)
    q_id = _canon_numeric_id(q)
    if q_id is not None and q.isdigit():
        return q_id in ids
    ql = q.lower()
    label = (task.get("label") or "").lower()
    if ql in label:
        return True
    if ql in name.lower():
        return True
    mk = str(task.get("mk") or "")
    if mk.startswith("\x00"):
        return False
    return ql in mk.lower()


def _corridor_restricted_to_tasks(c: dict, tasks: list) -> dict:
    """Copy *c* so heatmap/tree counts include only *tasks* (no model mutation)."""
    n = len(c.get("bins") or [])
    bins = [0] * n
    bounce_bins = [0] * n
    count = 0
    bounces = 0
    has_task_bounce = False
    for t in tasks:
        count += int(t.get("count") or 0)
        bounces += int(t.get("bounces") or 0)
        tb = t.get("bins") or []
        bb = t.get("bounce_bins") or []
        if bb:
            has_task_bounce = True
        for i in range(n):
            bins[i] += tb[i] if i < len(tb) else 0
            bounce_bins[i] += bb[i] if i < len(bb) else 0
    if not has_task_bounce:
        if not bounces:
            bounce_bins = [0] * n
        elif count and bounces == count:
            bounce_bins = list(bins)
        else:
            old = c.get("bounce_bins") or []
            bounce_bins = [
                min(old[i] if i < len(old) else 0, bins[i]) for i in range(n)]
    new_tasks = []
    for t in tasks:
        nt = dict(t)
        nt["share_pct"] = (100.0 * int(t.get("count") or 0) / count) if count else 0.0
        new_tasks.append(nt)
    peak_bin = max(range(n), key=lambda b: bins[b]) if n else 0
    old_count = int(c.get("count") or 0)
    out = dict(c)
    out.update({
        "count": count,
        "bounces": bounces,
        "bounce_pct": (100.0 * bounces / count) if count else 0.0,
        "rate_per_s": ((c.get("rate_per_s") or 0.0) * count / old_count)
        if old_count else 0.0,
        "bins": bins,
        "bounce_bins": bounce_bins,
        "tasks": new_tasks,
        "primary_task": new_tasks[0] if new_tasks else None,
        "peak_bin": peak_bin,
        "peak_count": bins[peak_bin] if n else 0,
    })
    return out


def _recompute_corridor_nets(corridors: list) -> list:
    """Refresh net/rev from the (possibly narrowed) corridor set."""
    by_pair = {}
    for c in corridors:
        by_pair[(c.get("from_core"), c.get("to_core"))] = c
    out = []
    for c in corridors:
        rev = by_pair.get((c.get("to_core"), c.get("from_core")))
        rev_count = int(rev["count"]) if rev else 0
        net = _net_migration_balance(rev_count, int(c.get("count") or 0))
        if rev_count == c.get("rev_count") and net == c.get("net"):
            out.append(c)
            continue
        nc = dict(c)
        nc["rev_count"] = rev_count
        nc["net"] = net
        out.append(nc)
    return out


def _filter_corridors_by_task_query(corridors: list, query: str) -> list:
    """Keep corridors that have a matching task; drop sibling tasks from hits."""
    q = (query or "").strip().lower()
    if not q:
        return list(corridors or [])
    out = []
    for c in corridors or []:
        tasks = c.get("tasks") or []
        matched = [t for t in tasks if _corridor_task_query_hit(t, q)]
        if not matched:
            continue
        if len(matched) == len(tasks):
            out.append(c)
        else:
            out.append(_corridor_restricted_to_tasks(c, matched))
    return _recompute_corridor_nets(out)


def _corridor_groups_by_source(corridors: list) -> list:
    """Group directed corridors under their source core (large-core tree)."""
    gmap: Dict[str, dict] = {}
    for c in corridors or []:
        src = c.get("from_core")
        if not src:
            continue
        g = gmap.get(src)
        if g is None:
            g = {
                "source": src,
                "label": f"{_core_short_name(src)} → Destinations",
                "count": 0,
                "corridors": [],
            }
            gmap[src] = g
        g["count"] += int(c.get("count") or 0)
        g["corridors"].append(c)
    return sorted(gmap.values(), key=lambda g: -g["count"])


def _net_migration_balance(incoming: int, outgoing: int) -> int:
    return int(incoming or 0) - int(outgoing or 0)


def _chord_label_nice_step(raw: int) -> int:
    """Round a label stride up to 1/2/5×10^k so ticks stay readable (0, 5, 10…)."""
    n = max(1, int(raw))
    if n <= 1:
        return 1
    mag = 10 ** int(math.floor(math.log10(n)))
    for mult in (1, 2, 5, 10):
        nice = mult * mag
        if nice >= n:
            return int(nice)
    return n


def _chord_label_step(
    n_cores: int,
    *,
    min_px: float = 0.0,
    span_px: float = 0.0,
) -> int:
    """How many cores to skip between chord/matrix tick labels.

    Small core counts keep every name. Larger rings/matrices use a stride
    such as 5 → c0, c5, c10. *min_px*/*span_px* raise the stride when
    glyphs would still collide (circle circumference or matrix cell pitch).
    """
    n = int(n_cores or 0)
    if n <= 16:
        step = 1
    elif n <= 32:
        step = 2
    elif n <= 64:
        step = 5
    elif n <= 128:
        step = 8
    else:
        step = 10
    if min_px > 0 and span_px > 0 and n > 0:
        per = span_px / n
        if per < min_px:
            need = int(math.ceil(min_px / max(per, 1e-9)))
            step = max(step, _chord_label_nice_step(need))
    return max(1, step)


def _chord_label_visible(
    index: int,
    step: int,
    extra: Optional[set] = None,
) -> bool:
    """True when core *index* should draw a name (stride tick or hover/focus)."""
    if extra and int(index) in extra:
        return True
    if step <= 1:
        return True
    return int(index) % step == 0

def _build_chord_layout(cores: List[str], grid: List[List[float]]) -> ChordLayout:
    """Pure circular layout for the migration chord diagram — parity with the
    web app's buildChordLayout() in migrationAnalysis.js. Each core gets an arc
    sized proportionally to its total in+out migration volume (with a minimum
    sliver so zero-flow cores still appear as nodes), separated by a fixed gap.
    Each connected core-pair also gets a tick position within its two arcs,
    used as chord endpoints so parallel migrations fan out rather than
    overlapping. Also exposes egress/ingress ticks and tapered ribbon widths."""
    n = len(cores)
    totals = [0.0] * n
    out_totals = [0.0] * n
    in_totals = [0.0] * n
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            gij = grid[i][j] if i < len(grid) and j < len(grid[i]) else 0
            gji = grid[j][i] if j < len(grid) and i < len(grid[j]) else 0
            out_totals[i] += gij
            in_totals[i] += gji
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
        arcs.append(ChordArc(
            cores[i], i, start_angle, end_angle, totals[i],
            out_totals[i], in_totals[i]))
        angle = end_angle + gap

    tick_angles: List[Dict[int, float]] = [dict() for _ in range(n)]
    egress_ticks: List[Dict[int, float]] = [dict() for _ in range(n)]
    ingress_ticks: List[Dict[int, float]] = [dict() for _ in range(n)]

    def _place(links, dest_map, arc):
        link_total = sum(m for _, m in links)
        span = arc.end_angle - arc.start_angle
        cursor = arc.start_angle
        for j, mag in links:
            sl = (span * (mag / link_total) if link_total > 0
                  else (span / len(links) if links else 0.0))
            dest_map[j] = cursor + sl / 2
            cursor += sl

    for i in range(n):
        arc = arcs[i]
        combined, egress, ingress = [], [], []
        for j in range(n):
            if j == i:
                continue
            gij = grid[i][j] if i < len(grid) and j < len(grid[i]) else 0
            gji = grid[j][i] if j < len(grid) and i < len(grid[j]) else 0
            if gij + gji > 0:
                combined.append((j, gij + gji))
            if gij > 0:
                egress.append((j, gij))
            if gji > 0:
                ingress.append((j, gji))
        _place(combined, tick_angles[i], arc)
        _place(egress, egress_ticks[i], arc)
        _place(ingress, ingress_ticks[i], arc)

    return ChordLayout(
        arcs=arcs, tick_angles=tick_angles,
        egress_ticks=egress_ticks, ingress_ticks=ingress_ticks, grid=grid)


def _attach_corridor_path_metrics(by_key: dict, migrations: list, time_scale: str) -> None:
    window = _MIGRATION_PING_PONG_WINDOW
    short_th = _corridor_short_dwell_threshold(time_scale)
    by_mk: Dict[str, list] = {}
    for m in migrations or []:
        mk = getattr(m, "merge_key", None)
        if not mk:
            continue
        by_mk.setdefault(mk, []).append(m)
    ping: Dict[Tuple[str, str], int] = {}
    dwells: Dict[Tuple[str, str], list] = {}
    for lst in by_mk.values():
        ordered = sorted(lst, key=lambda x: x.ns)
        for i, m in enumerate(ordered):
            key = (m.from_core, m.to_core)
            if i + 1 < len(ordered):
                dwells.setdefault(key, []).append(max(0, ordered[i + 1].ns - m.ns))
        for i in range(1, len(ordered)):
            a, b = ordered[i - 1], ordered[i]
            if b.ns - a.ns > window:
                continue
            if a.to_core == b.from_core and a.from_core == b.to_core:
                key = (a.from_core, a.to_core)
                ping[key] = ping.get(key, 0) + 1
    for key, row in by_key.items():
        p = ping.get(key, 0)
        samples = dwells.get(key) or []
        row["ping_pong"] = p
        row["ping_pong_pct"] = (100.0 * p / row["count"]) if row.get("count") else 0.0
        ordered = sorted(samples)
        row["median_dwell_ns"] = ordered[len(ordered) // 2] if ordered else 0
        row["short_dwell_share"] = (
            100.0 * sum(1 for d in samples if d < short_th) / len(samples)
            if samples else 0.0
        )


_INSPECTOR_FULL_VIEW_RATIO = 0.92


def _inspector_viewport_is_full(lo, hi, t_min, t_max, fit_mode: bool = False) -> bool:
    if fit_mode or lo is None or hi is None:
        return True
    span = max(int(t_max) - int(t_min), 1)
    return (int(hi) - int(lo)) / span >= _INSPECTOR_FULL_VIEW_RATIO


def _inspector_viewport_tuple(viewport):
    if isinstance(viewport, dict):
        try:
            return int(viewport.get("timeStart")), int(viewport.get("timeEnd"))
        except (TypeError, ValueError):
            return None, None
    if isinstance(viewport, (tuple, list)) and len(viewport) >= 2:
        try:
            return int(viewport[0]), int(viewport[1])
        except (TypeError, ValueError):
            return None, None
    return None, None


def _inspector_analysis_scope(mode: str, cursors, time_min, time_max, time_scale: str,
                              viewport=None, fit_mode: bool = False):
    """Inspector Analysis Scope: Follow zoom, Full Trace, Viewport, or Cursor.

    *viewport* is ``(lo, hi)`` or ``{timeStart, timeEnd}``. Default *mode*
    ``auto`` follows Fit vs zoom (Full Trace vs Viewport).
    """
    placed = [int(c) for c in (cursors or []) if c is not None]
    can_cursor = len(placed) >= 2
    tlo = int(time_min or 0)
    thi = int(time_max or 0)
    lo = hi = None
    resolved = "full"
    want = mode or "auto"
    if isinstance(viewport, dict) and viewport.get("fitMode"):
        fit_mode = True
    if want == "cursor" and can_cursor:
        ordered = sorted(placed)
        lo, hi = ordered[0], ordered[-1]
        if hi > lo:
            resolved = "cursor"
        else:
            lo = hi = None
    elif want == "viewport":
        vlo, vhi = _inspector_viewport_tuple(viewport)
        if vlo is not None and vhi is not None and vhi > vlo:
            lo, hi = vlo, vhi
        else:
            lo, hi = tlo, thi
        resolved = "viewport"
    elif want == "full":
        resolved = "full"
    else:
        vlo, vhi = _inspector_viewport_tuple(viewport)
        if vlo is None or vhi is None or not (vhi > vlo):
            vlo, vhi = tlo, thi
        if _inspector_viewport_is_full(vlo, vhi, tlo, thi, fit_mode):
            resolved = "full"
        else:
            lo, hi = vlo, vhi
            resolved = "viewport"
    scoped = resolved != "full"
    a = lo if lo is not None else tlo
    b = hi if hi is not None else thi
    n = len(placed) if resolved == "cursor" else 0
    if resolved == "cursor":
        label = f"Cursor C1–C{n}"
    elif resolved == "viewport":
        label = "Viewport"
    else:
        label = "Full Trace"
    unit = time_scale or "ns"
    detail = (
        f"{_format_time(a, unit)} … {_format_time(b, unit)} "
        f"({_format_time(max(0, b - a), unit)}) · trace unit: {unit}"
    )
    return {
        "mode": resolved,
        "lo": lo if scoped else None,
        "hi": hi if scoped else None,
        "n_cursors": n,
        "can_cursor": can_cursor,
        "cursor_disabled_reason": "" if can_cursor else "Place at least two cursors.",
        "label": label,
        "detail": detail,
        "unit": unit,
        "scoped": scoped,
    }


def _classify_corridor_concern(corridor: Optional[dict]) -> dict:
    if not corridor:
        return {"id": "none", "label": "None", "detail": ""}
    ping = float(corridor.get("ping_pong_pct") or 0)
    short = float(corridor.get("short_dwell_share") or 0)
    handoff = float(corridor.get("handoff_pct") or corridor.get("bounce_pct") or 0)
    count = int(corridor.get("count") or 0)
    burst = (100.0 * int(corridor.get("peak_count") or 0) / count) if count else 0.0
    candidates = [
        ("pingpong", "Ping-pong", ping, 40, corridor.get("ping_pong") is not None),
        ("dwell", "Short dwell", short, 50, corridor.get("short_dwell_share") is not None),
        ("burst", "Burst", burst, 40, corridor.get("peak_count") is not None),
        ("handoff", "Handoff suspect", handoff, _CORRIDOR_HANDOFF_HATCH_PCT,
         corridor.get("bounces") is not None),
    ]
    candidates = [c for c in candidates if c[4]]
    candidates.sort(key=lambda c: -c[2])
    best = next((c for c in candidates if c[2] >= c[3]), None)
    if not best:
        return {"id": "none", "label": "None", "detail": ""}
    task = corridor.get("primary_task") or {}
    cid, label = best[0], best[1]
    if cid == "pingpong" and task.get("label"):
        detail = (
            f"{task['label']} repeatedly moves between "
            f"{corridor.get('from_core')} and {corridor.get('to_core')}"
        )
    elif cid == "burst":
        detail = f"{corridor.get('label')} concentrates migrations in a short window"
    elif cid == "dwell" and task.get("label"):
        detail = f"{task['label']} leaves {corridor.get('to_core')} after a short dwell"
    elif cid == "handoff":
        detail = (
            "Repeated synchronization ownership changes associated with "
            f"{corridor.get('label')}"
        )
    else:
        detail = (
            f"{task.get('label')} on {corridor.get('label')}"
            if task.get("label") else corridor.get("label") or ""
        )
    return {"id": cid, "label": label, "detail": detail}


def _corridor_load_balance_status(trace, lo, hi) -> dict:
    rows = _core_util_pct_rows(trace, lo, hi) if trace is not None else []
    pcts = [p for _c, p in rows]
    if len(pcts) < 2 or sum(pcts) <= 0:
        return {"label": "Not evaluated", "zone": None, "score": None}
    gini = _gini_coefficient(pcts)
    sigma = _core_util_stddev(pcts)
    score = max(0.0, 100.0 * (1.0 - gini))
    zone = "red" if score < 70.0 else ("amber" if sigma > 30.0 else "ok")
    return {
        "label": "Balanced" if zone == "ok" else "Imbalanced",
        "zone": zone,
        "score": score,
    }


def _build_corridor_overview(trace, model: dict, scope: Optional[dict] = None) -> dict:
    scope = scope or {}
    corridors = model.get("all_corridors") or model.get("corridors") or []
    total = sum(int(c.get("count") or 0) for c in corridors)
    rate = sum(float(c.get("rate_per_s") or 0) for c in corridors)
    lb = _corridor_load_balance_status(trace, scope.get("lo"), scope.get("hi"))
    hottest = sorted(corridors, key=lambda c: -int(c.get("count") or 0))
    hottest = hottest[0] if hottest else None
    task_totals: Dict[str, dict] = {}
    for c in corridors:
        for t in c.get("tasks") or []:
            mk = t.get("mk")
            if not mk:
                continue
            cur = task_totals.setdefault(
                mk, {"mk": mk, "label": t.get("label"), "count": 0})
            cur["count"] += int(t.get("count") or 0)
    top_task = sorted(task_totals.values(), key=lambda t: -t["count"])
    top_task = top_task[0] if top_task else None
    share = (100.0 * top_task["count"] / total) if top_task and total else 0.0
    concern = _classify_corridor_concern(hottest)
    hottest_label = (
        f"{hottest.get('from_core')} → {hottest.get('to_core')}" if hottest else "—"
    )
    scope_label = scope.get("label") or "Full Trace"
    return {
        "scope_label": scope_label,
        "load_balance": lb["label"],
        "migrations": total,
        "migration_rate_label": f"{rate:.1f}/s" if total else "—",
        "most_affected_task": top_task,
        "most_affected_share": share,
        "hottest_path": hottest_label,
        "main_concern": concern["label"],
        "main_concern_detail": concern["detail"],
        "headline": (
            f"Scope: {scope_label} · Load balance: {lb['label']} · "
            f"{total:,} migrations"
        ),
        "evaluated": lb["label"] != "Not evaluated",
    }


def _build_corridor_evidence(corridor, opts=None) -> Optional[dict]:
    """Selected-path evidence card (Web ``buildCorridorEvidence`` lockstep)."""
    if not corridor:
        return None
    opts = opts or {}
    scale = opts.get("time_scale") or "ns"
    task = opts.get("selected_task") or corridor.get("primary_task")
    concern = _classify_corridor_concern(corridor)
    median_ns = corridor.get("median_dwell_ns")
    median = _format_time(int(median_ns), scale) if median_ns else "—"
    bin_lo, bin_hi = opts.get("bin_lo"), opts.get("bin_hi")
    if bin_lo is not None and bin_hi is not None:
        window = f"range:{bin_lo}/{bin_hi}"
    else:
        window = opts.get("scope_label") or "full trace"
    ping = corridor.get("ping_pong_pct")
    short = corridor.get("short_dwell_share")
    handoff = corridor.get("handoff_pct")
    if handoff is None:
        handoff = corridor.get("bounce_pct")
    bounces = corridor.get("bounces")
    lines = [
        ("Migration volume", str(corridor.get("count") or 0)),
        ("Rate", f"{float(corridor.get('rate_per_s') or 0):.1f}/s"),
        ("Ping-pong", f"{float(ping):.0f}%" if ping is not None else "—"),
        ("Median dwell", median),
        ("Short-dwell share",
         f"{float(short):.0f}%" if short is not None else "—"),
        ("Handoff suspects",
         f"{bounces} ({float(handoff or 0):.0f}%)" if bounces is not None else "—"),
        ("Top migrating task",
         f"{task.get('label')} · {float(task.get('share_pct') or 0):.0f}%"
         if task else "—"),
        ("Evidence window", window),
    ]
    return {
        "title": f"{corridor.get('from_core')} → {corridor.get('to_core')}",
        "lines": lines,
        "assessment": concern.get("detail")
        or "No dominant migration condition on this path.",
        "evidence_quality": {
            "direct": "migration events",
            "correlated": "synchronization handoffs",
            "limitation": (
                "Handoff association is a heuristic, not a measured "
                "cache-line transfer."),
        },
        "task": task,
        "concern": concern,
    }


def _build_corridor_ai_context(
        scope=None, corridor=None, task=None, bin_label=None,
        overview=None, inspector_filters=None, time_scale=None) -> str:
    scale = time_scale or (scope or {}).get("unit") or "ns"
    lines = [
        f"Analysis scope: {(scope or {}).get('label') or 'Full Trace'}",
        f"Trace unit: {scale}",
    ]
    if scope and scope.get("detail"):
        lines.append(f"Scope range: {scope['detail']}")
    if corridor:
        lines.append(
            f"Selected core path: {corridor.get('from_core')} → {corridor.get('to_core')}")
    else:
        lines.append("Selected core path: none")
    lines.append(
        f"Selected task: {task.get('label')}" if task else "Selected task: none")
    lines.append(
        f"Selected time bin: {bin_label}" if bin_label else "Selected time bin: none")
    if corridor:
        lines.append(
            f"Migrations: {corridor.get('count', 0)} "
            f"({float(corridor.get('rate_per_s') or 0):.1f}/s)")
        if corridor.get("ping_pong_pct") is not None:
            lines.append(f"Ping-pong: {float(corridor.get('ping_pong_pct') or 0):.0f}%")
        if corridor.get("median_dwell_ns"):
            lines.append(
                f"Median dwell: {_format_time(int(corridor['median_dwell_ns']), scale)}")
        lines.append(
            f"Handoff suspects: {corridor.get('bounces') or 0} "
            f"({float(corridor.get('handoff_pct') or corridor.get('bounce_pct') or 0):.0f}%). "
            "Heuristic synchronization association, not a measured cache-line transfer.")
    if overview:
        lines.append(f"Load balance: {overview.get('load_balance')}")
    lines.append(f"Inspector filters: {inspector_filters or 'none'}")
    lines.append(
        "Do not automatically filter the timeline or change cursors unless the "
        "user explicitly selects a viewer action.")
    return "\n".join(lines)


def _build_corridor_inspector_model(
        trace: "BtfTrace",
        lo: Optional[int] = None,
        hi: Optional[int] = None,
        *,
        bounce_only: bool = False,
        top_pct: Optional[int] = None,
        time_bins: int = 32) -> dict:
    """Unified corridor inspector model — parity with web buildCorridorInspectorModel."""
    cores = list(trace.core_names)
    if top_pct is None:
        top_pct = _default_corridor_top_pct(len(cores))
    bounce_ns = trace.lock_bounce_migration_ns
    t_min = lo if lo is not None else trace.time_min
    t_hi = hi if hi is not None else trace.time_max
    span = max(t_hi - t_min, 1)
    bin_w = span / time_bins
    ns_per = {"ns": 1e9, "us": 1e6, "ms": 1e3, "s": 1.0}.get(trace.time_scale, 1e9)
    scope_sec = span / ns_per

    by_key: Dict[Tuple[str, str], dict] = {}
    n_cores_m = len(cores)
    core_idx = {c: i for i, c in enumerate(cores)}
    full_grid = [[0] * n_cores_m for _ in range(n_cores_m)]
    scoped_migs = []
    for m in _migrations_in_range(trace, lo, hi):
        if bounce_only and m.ns not in bounce_ns:
            continue
        if m.from_core == m.to_core:
            continue
        scoped_migs.append(m)
        fi = core_idx.get(m.from_core)
        ti = core_idx.get(m.to_core)
        if fi is not None and ti is not None:
            full_grid[fi][ti] += 1
        key = (m.from_core, m.to_core)
        row = by_key.get(key)
        if row is None:
            row = {
                "from_core": m.from_core,
                "to_core": m.to_core,
                "label": f"{_core_short_name(m.from_core)}→{_core_short_name(m.to_core)}",
                "count": 0,
                "bounces": 0,
                "gap_sum": 0,
                "bins": [0] * time_bins,
                "bounce_bins": [0] * time_bins,
                "tasks": {},
            }
            by_key[key] = row
        row["count"] += 1
        is_bounce = m.ns in bounce_ns
        if is_bounce:
            row["bounces"] += 1
        row["gap_sum"] += m.gap_ns
        bi = _heatmap_bin_index_for_ns(t_min, bin_w, time_bins, t_hi, m.ns)
        row["bins"][bi] += 1
        if is_bounce:
            row["bounce_bins"][bi] += 1
        mk = m.merge_key
        if mk:
            t = row["tasks"].get(mk)
            if t is None:
                t = {
                    "mk": mk, "count": 0, "bounces": 0,
                    "bins": [0] * time_bins,
                    "bounce_bins": [0] * time_bins,
                }
                row["tasks"][mk] = t
            t["count"] += 1
            if is_bounce:
                t["bounces"] += 1
                t["bounce_bins"][bi] += 1
            t["bins"][bi] += 1

    _attach_corridor_path_metrics(by_key, scoped_migs, trace.time_scale)

    all_corridors = []
    for row in by_key.values():
        rev = by_key.get((row["to_core"], row["from_core"]))
        rev_count = rev["count"] if rev else 0
        tasks = sorted(row["tasks"].values(),
                       key=lambda t: (-t["count"], t["mk"]))
        task_rows = []
        for t in tasks:
            raw = trace.task_repr.get(t["mk"], t["mk"])
            label = _task_display_name(raw)
            id_list, _nm = _corridor_task_ids_and_name(
                {"mk": t["mk"], "label": label})
            task_rows.append({
                "mk": t["mk"],
                "label": label,
                "task_id": int(id_list[0]) if id_list else None,
                "count": t["count"],
                "bounces": t["bounces"],
                "bounce_pct": (100.0 * t["bounces"] / t["count"]) if t["count"] else 0.0,
                "share_pct": (100.0 * t["count"] / row["count"]) if row["count"] else 0.0,
                "bins": t["bins"],
                "bounce_bins": t["bounce_bins"],
            })
        peak_bin = max(range(time_bins), key=lambda b: row["bins"][b]) if time_bins else 0
        peak_val = row["bins"][peak_bin] if time_bins else 0
        bounce_pct = (100.0 * row["bounces"] / row["count"]) if row["count"] else 0.0
        all_corridors.append({
            "from_core": row["from_core"],
            "to_core": row["to_core"],
            "label": row["label"],
            "count": row["count"],
            "bounces": row["bounces"],
            "bounce_pct": bounce_pct,
            "handoff_count": row["bounces"],
            "handoff_pct": bounce_pct,
            "ping_pong": int(row.get("ping_pong") or 0),
            "ping_pong_pct": float(row.get("ping_pong_pct") or 0),
            "median_dwell_ns": int(row.get("median_dwell_ns") or 0),
            "short_dwell_share": float(row.get("short_dwell_share") or 0),
            "avg_gap_ns": (row["gap_sum"] // row["count"]) if row["count"] else 0,
            "rate_per_s": (row["count"] / scope_sec) if scope_sec > 0 else 0.0,
            "net": _net_migration_balance(rev_count, row["count"]),
            "rev_count": rev_count,
            "bins": row["bins"],
            "bounce_bins": row["bounce_bins"],
            "tasks": task_rows,
            "primary_task": task_rows[0] if task_rows else None,
            "peak_bin": peak_bin,
            "peak_count": peak_val,
        })
    all_corridors.sort(key=lambda c: (-c["count"], c["label"]))
    corridors = _filter_corridors_by_top_pct(all_corridors, top_pct)

    group_by_source = len(cores) > 16
    groups = _corridor_groups_by_source(corridors) if group_by_source else []

    matrix_cores = cores
    filtered_grid = []
    corridor_set = {(c["from_core"], c["to_core"]) for c in corridors}
    for i, fc in enumerate(matrix_cores):
        row = []
        for j, tc in enumerate(matrix_cores):
            if i == j:
                row.append(0)
            elif (fc, tc) in corridor_set:
                row.append(full_grid[i][j])
            else:
                row.append(0)
        filtered_grid.append(row)

    task_agg: Dict[str, Dict[str, int]] = {}
    for c in all_corridors:
        for core in (c["from_core"], c["to_core"]):
            agg = task_agg.setdefault(core, {})
            for t in c.get("tasks") or []:
                mk = t.get("mk")
                if not mk:
                    continue
                agg[mk] = agg.get(mk, 0) + int(t.get("count") or 0)
    core_stats = []
    n_mat = len(matrix_cores)
    for i, core in enumerate(matrix_cores):
        out_v = inn_v = 0
        for j in range(n_mat):
            if i == j:
                continue
            if i < len(full_grid) and j < len(full_grid[i]):
                out_v += full_grid[i][j]
            if j < len(full_grid) and i < len(full_grid[j]):
                inn_v += full_grid[j][i]
        top3 = sorted(task_agg.get(core, {}).items(), key=lambda kv: -kv[1])[:3]
        core_stats.append({
            "core": core,
            "out": out_v,
            "in": inn_v,
            "net": _net_migration_balance(inn_v, out_v),
            "top_tasks": [
                {
                    "mk": mk,
                    "label": _task_display_name(trace.task_repr.get(mk, mk)),
                    "count": n,
                }
                for mk, n in top3
            ],
        })

    hotspot = None
    for c in all_corridors:
        score = c["count"] + c["bounces"] * 2
        if hotspot is None or score > hotspot["score"]:
            offender = c["primary_task"]
            hotspot = {
                "score": score,
                "from_core": c["from_core"],
                "to_core": c["to_core"],
                "label": c["label"],
                "count": c["count"],
                "bounces": c["bounces"],
                "bounce_pct": c["bounce_pct"],
                "peak_bin": c["peak_bin"],
                "task": offender,
                "summary": (
                    f"Hotspot: {offender['label']} on {c['label']} "
                    f"({c['count']} mig, {c.get('ping_pong_pct', 0):.0f}% ping-pong)"
                    if offender else
                    f"Hotspot: {c['label']} ({c['count']} migrations)"
                ),
            }

    max_bin = 0
    for c in corridors:
        for v in c["bins"]:
            if v > max_bin:
                max_bin = v

    return {
        "cores": matrix_cores,
        "corridors": corridors,
        "all_corridors": all_corridors,
        "groups": groups,
        "group_by_source": group_by_source,
        "top_pct": top_pct,
        "time_bins": time_bins,
        "t_min": t_min,
        "t_max": t_hi,
        "bin_w": bin_w,
        "max_bin": max_bin,
        "matrix": {"cores": matrix_cores, "grid": full_grid},
        "filtered_matrix": {"cores": matrix_cores, "grid": filtered_grid},
        "core_stats": core_stats,
        "hotspot": hotspot,
        "has_data": any(c["count"] > 0 for c in corridors),
    }

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

def _gini_coefficient(values: List[float]) -> float:
    """Gini coefficient of non-negative values (0 = equality, 1 = max inequality)."""
    n = len(values)
    if n < 2:
        return 0.0
    total = sum(values)
    if total == 0.0:
        return 0.0
    sorted_v = sorted(values)
    cumsum = 0.0
    gini_num = 0.0
    for i, v in enumerate(sorted_v):
        cumsum += v
        gini_num += cumsum
    gini = (n + 1.0) / n - (2.0 * gini_num) / (n * total)
    return max(0.0, min(1.0, gini))


def _core_util_stddev(values: List[float]) -> float:
    """Population standard deviation of core utilisation percentages."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / n)


def _core_util_pct_rows(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[Tuple[str, float]]:
    """Per-core util % excluding IDLE/TICK (same logic as StatsPanel._core_util_rows)."""
    if lo is None and hi is None and trace.core_util_pct:
        return [(c, float(trace.core_util_pct.get(c, 0.0))) for c in trace.core_names]
    if lo is not None and hi is not None:
        total_ns = hi - lo
    else:
        total_ns = trace.time_max - trace.time_min
    if total_ns <= 0:
        return []
    rows: List[Tuple[str, float]] = []
    for core in trace.core_names:
        segs = _core_segs_in_range(trace, core, lo, hi)
        if lo is not None and hi is not None:
            active_ns = sum(
                _seg_overlap_ns(s, lo, hi) for s in segs
                if (_tn := _parse_task_name(s.task)[2]) != "TICK"
                and not _is_idle_task_name(_tn)
            )
        else:
            active_ns = sum(
                s.end - s.start for s in segs
                if (_tn := _parse_task_name(s.task)[2]) != "TICK"
                and not _is_idle_task_name(_tn)
            )
        rows.append((core, 100.0 * active_ns / total_ns))
    return rows


def _exec_slice_samples(
    segs: list,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[int]:
    if lo is not None and hi is not None:
        return [s.end - s.start for s in segs
                if (s.end - s.start) > 0 and _seg_fully_in_range(s, lo, hi)]
    return [s.end - s.start for s in segs if (s.end - s.start) > 0]


def _inter_arrival_samples(
    segs: list,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> List[int]:
    starts = sorted(s.start for s in segs)
    samples: List[int] = []
    for i in range(1, len(starts)):
        gap = starts[i] - starts[i - 1]
        if gap <= 0:
            continue
        if lo is not None and hi is not None and (starts[i] < lo or starts[i] > hi):
            continue
        samples.append(gap)
    return samples


def _summarize_time_samples(samples: List[int], scale: str) -> Optional[dict]:
    if not samples:
        return None
    vals = sorted(samples)
    n = len(vals)
    p95_idx = min(n - 1, math.ceil(n * 0.95) - 1)
    avg_ns = int(round(sum(vals) / n))
    min_ns = vals[0]
    max_ns = vals[-1]
    p95_ns = vals[p95_idx]
    return {
        "count": n,
        "min_ns": min_ns,
        "avg_ns": avg_ns,
        "max_ns": max_ns,
        "p95_ns": p95_ns,
        "min": _format_time(min_ns, scale),
        "avg": _format_time(avg_ns, scale),
        "max": _format_time(max_ns, scale),
        "p95": _format_time(p95_ns, scale),
    }


def _task_metric_compare_by_name(
    trace: "BtfTrace",
    sample_fn,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
    *,
    include_cpu: bool = False,
) -> Dict[str, dict]:
    """Per-task time-sample summary keyed by display name (excludes IDLE/TICK)."""
    scale = trace.time_scale
    if lo is not None and hi is not None:
        span_ns = max(1, hi - lo)
    else:
        span_ns = max(1, trace.time_max - trace.time_min)
    out: Dict[str, dict] = {}
    for mk, segs in trace.seg_map_by_merge_key.items():
        raw = trace.task_repr.get(mk, mk)
        _, _, tname = _parse_task_name(raw)
        if _is_idle_task_name(tname) or tname == "TICK":
            continue
        samples = sample_fn(segs, lo, hi)
        summary = _summarize_time_samples(samples, scale)
        if summary is None:
            continue
        entry = dict(summary)
        if include_cpu:
            entry["cpu"] = 100.0 * sum(samples) / span_ns
        out[_task_display_name(raw)] = entry
    return out


def _task_samples_by_name(trace: "BtfTrace", sample_fn,
                          lo: Optional[int] = None,
                          hi: Optional[int] = None) -> "Dict[str, List[int]]":
    """Raw per-task samples keyed by display name (IDLE/TICK excluded) — the raw
    counterpart of ``_task_metric_compare_by_name``, used for the Trace Compare
    distribution-shape (KS) column (review item B12)."""
    out: Dict[str, List[int]] = {}
    for mk, segs in trace.seg_map_by_merge_key.items():
        raw = trace.task_repr.get(mk, mk)
        _, _, tname = _parse_task_name(raw)
        if _is_idle_task_name(tname) or tname == "TICK":
            continue
        out[_task_display_name(raw)] = sample_fn(segs, lo, hi)
    return out


def _ks_statistic(a: "List[int]", b: "List[int]") -> float:
    """Two-sample Kolmogorov–Smirnov D — the largest gap between the two
    empirical CDFs (0.0 = identical shape, 1.0 = disjoint).  0.0 when either
    list is empty.  Scale-free, so it catches a tail that widened without the
    mean or p99 moving much (review item B12)."""
    if not a or not b:
        return 0.0
    sa, sb = sorted(a), sorted(b)
    na, nb = len(sa), len(sb)
    ia = ib = 0
    d = 0.0
    while ia < na and ib < nb:
        va, vb = sa[ia], sb[ib]
        if va <= vb:
            ia += 1
        if vb <= va:
            ib += 1
        d = max(d, abs(ia / na - ib / nb))
    return d


def _fmt_ks(a: "Optional[List[int]]", b: "Optional[List[int]]") -> str:
    """KS D for a compare row, or ``—`` when either side is too small to shape."""
    if not a or not b or len(a) < 3 or len(b) < 3:
        return "—"
    return f"{_ks_statistic(a, b):.2f}"


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
        migrations = len(_migrations_in_range(trace, lo, hi))
        mig_tasks = len(_migration_rows(trace, lo, hi))
        segments = sum(
            1 for s in trace.segments if s.end > lo and s.start < hi)
    else:
        migrations = len(trace.migrations)
        mig_tasks = sum(1 for mk in trace.tasks if _is_migrated_task(trace, mk))
        segments = len(trace.segments)

    util_rows = _core_util_pct_rows(trace, lo, hi)
    pcts = [pct for _, pct in util_rows]
    load_balance_score = None
    load_balance_sigma = None
    if len(pcts) >= 2 and sum(pcts) > 0.0:
        gini = _gini_coefficient(pcts)
        load_balance_score = max(0.0, 100.0 * (1.0 - gini))
        load_balance_sigma = _core_util_stddev(pcts)

    tick = _tick_health_report(trace, lo, hi)
    tick_count = tick.get("tick_count", 0)
    if tick_count:
        tick_mode = "TICKLESS" if tick.get("is_tickless") else "TICK"
    else:
        tick_mode = "—"

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
        "load_balance_score": load_balance_score,
        "load_balance_sigma": load_balance_sigma,
        "tick_health": tick.get("health", "unknown"),
        "tick_mode": tick_mode,
        "tick_count": tick_count,
        "missed_ticks": tick.get("missed_estimate", 0),
    }


def cross_trace_trends(rows: Optional[Sequence[dict]] = None) -> List[dict]:
    """Per-open-tab summary rows for Compare when 3+ traces are loaded."""
    out: List[dict] = []
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        snap = raw.get("snap") if isinstance(raw.get("snap"), dict) else raw
        name = str(raw.get("name") or snap.get("name") or "").strip()
        out.append({
            "name": name,
            "span_ns": snap.get("span_ns", snap.get("spanNs")),
            "migrations": snap.get("migrations"),
            "load_balance": snap.get(
                "load_balance_score", snap.get("loadBalanceScore")),
            "tick_health": snap.get("tick_health", snap.get("tickHealth")),
            "tasks": snap.get("tasks"),
        })
    return out


def _take_compare_limit(items, limit) -> list:
    """Keep *limit* rows; ``None`` or ``<= 0`` keeps every row."""
    seq = list(items)
    if limit is None:
        return seq
    try:
        n = int(limit)
    except (TypeError, ValueError):
        return seq
    if n <= 0:
        return seq
    return seq[:n]


def _compare_trend_table_rows(trend_dicts: Optional[Sequence[dict]] = None) -> List[List]:
    """Format ``cross_trace_trends`` dicts as Compare Trends table rows."""
    filled: List[List] = []
    for row in trend_dicts or []:
        if not isinstance(row, dict):
            continue
        lb = row.get("load_balance")
        lb_s = "—" if lb is None else f"{round(float(lb))}%"
        filled.append([
            row.get("name") or "",
            row.get("tasks") if row.get("tasks") is not None else "—",
            row.get("migrations") if row.get("migrations") is not None else "—",
            lb_s,
            row.get("tick_health") or "—",
            row.get("span_ns") if row.get("span_ns") is not None else "—",
        ])
    return filled


def _shared_pattern_table_row(row) -> List:
    """Normalize a shared-pattern dict or list into CSV/HTML cells."""
    if isinstance(row, dict):
        return [
            row.get("task") or row.get("name") or "",
            row.get("kind") or "",
            row.get("count_a", row.get("countA", "")),
            row.get("count_b", row.get("countB", "")),
            row.get("reason") or "",
        ]
    return list(row)[:5]


def _top_tasks_cpu_by_name(trace: "BtfTrace", limit: Optional[int] = 10,
                           lo: Optional[int] = None, hi: Optional[int] = None) -> Dict[str, float]:
    """Top tasks by CPU%, keyed by display name.

    *limit* ``None`` or ``<= 0`` returns every user task (HTML/CSV export).
    """
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
    ranked = sorted(task_times.items(), key=lambda kv: kv[1], reverse=True)
    for mk, t_ns in _take_compare_limit(ranked, limit):
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
        summary = _summarize_time_samples(samples, scale)
        if summary is None:
            continue
        raw = trace.task_repr.get(mk, mk)
        _, _, tname = _parse_task_name(raw)
        if _is_idle_task_name(tname) or tname == "TICK":
            continue
        out[_task_display_name(raw)] = {
            "gaps": summary["count"],
            "avg_ns": summary["avg_ns"],
            "avg": summary["avg"],
            "min_ns": summary["min_ns"],
            "min": summary["min"],
            "max_ns": summary["max_ns"],
            "max": summary["max"],
            "p95_ns": summary["p95_ns"],
            "p95": summary["p95"],
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
        return {
            "objects": 0, "holds": 0, "issues": 0, "queue": 0, "mutex": 0, "sem": 0,
            "bounces": 0, "lock_bounce_migrations": 0,
        }
    rows = _sync_object_stats_rows(trace, lo, hi)
    out = {
        "objects": len(rows), "holds": 0, "issues": 0, "queue": 0, "mutex": 0, "sem": 0,
        "bounces": 0, "lock_bounce_migrations": 0,
    }
    for row in rows:
        out["holds"] += row[4]
        out["issues"] += row[5]
        out["bounces"] += row[10]
        kind = row[1]
        if kind == "queue":
            out["queue"] += 1
        elif kind == "mutex":
            out["mutex"] += 1
        elif kind == "sem":
            out["sem"] += 1
    bounce_ns = trace.lock_bounce_migration_ns
    if lo is not None and hi is not None:
        out["lock_bounce_migrations"] = sum(1 for ns in bounce_ns if lo <= ns <= hi)
    else:
        out["lock_bounce_migrations"] = len(bounce_ns)
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
    return f"{sign}{_format_time_trim(abs(delta_ns), scale)}"

def _fmt_signed_int_delta(delta: int) -> str:
    if delta == 0:
        return "0"
    return f"+{delta}" if delta > 0 else f"−{abs(delta)}"

def _fmt_signed_pct_delta(delta: float) -> str:
    """Percentage-point delta (Load Balance Score / σ)."""
    if abs(delta) < 0.05:
        return "0.0 pp"
    sign = "+" if delta >= 0 else "−"
    return f"{sign}{abs(delta):.1f} pp"

def _fmt_signed_rate_delta(rate_a: float, rate_b: float) -> str:
    if rate_a < 0 or rate_b < 0:
        return "—"
    delta = rate_a - rate_b
    if abs(delta) < 0.005:
        return "0"
    sign = "+" if delta >= 0 else "−"
    return f"{sign}{abs(delta):.2f}/s"

def _fmt_signed_dwell_delta(dwell_a: int, dwell_b: int, scale: str) -> str:
    if dwell_a < 0 or dwell_b < 0:
        return "—"
    delta = dwell_a - dwell_b
    if delta == 0:
        return "0"
    sign = "+" if delta > 0 else "−"
    return f"{sign}{_format_time_trim(abs(delta), scale)}"


def _fmt_p99_with_task(ns: int, task: str, scale: str) -> str:
    text = _format_time_trim(int(ns or 0), scale)
    name = str(task or "").strip()
    return f"{text} ({name})" if name else text


def _per_second(count: float, span_ns: int) -> Optional[float]:
    """Count / span as per-second rate; None when span is empty."""
    if span_ns is None or int(span_ns) <= 0:
        return None
    return float(count) / (float(span_ns) / 1_000_000_000.0)


def _fmt_rate_per_s(rate: Optional[float]) -> str:
    if rate is None:
        return "—"
    if abs(rate) < 0.005:
        return "0/s"
    return f"{rate:.2f}/s"


def _blocking_total_ns(
    trace: "BtfTrace",
    lo: Optional[int] = None,
    hi: Optional[int] = None,
) -> int:
    """Sum of off-CPU blocking gaps for user tasks in scope."""
    total = 0
    for mk, segs in (getattr(trace, "seg_map_by_merge_key", None) or {}).items():
        raw = (getattr(trace, "task_repr", None) or {}).get(mk, mk)
        _, _, tname = _parse_task_name(raw)
        if _is_idle_task_name(tname) or tname == "TICK":
            continue
        for gap in _blocking_time_samples(segs, lo, hi):
            total += int(gap)
    return total

def _build_trace_compare_rows(
    trace_a: "BtfTrace",
    trace_b: "BtfTrace",
    lo_a: Optional[int] = None,
    hi_a: Optional[int] = None,
    lo_b: Optional[int] = None,
    hi_b: Optional[int] = None,
    deadlines: Optional[dict] = None,
    row_limit: Optional[int] = 15,
    top_limit: Optional[int] = 10,
) -> Dict[str, List[List]]:
    """Build all Trace Compare tables as a dict of row lists.

    Dialog views pass the default caps. HTML/CSV export pass
    ``row_limit=None`` / ``top_limit=None`` for every row.
    """
    a = _trace_summary_snapshot(trace_a, lo_a, hi_a)
    b = _trace_summary_snapshot(trace_b, lo_b, hi_b)
    scale = a["time_scale"]

    def _lb_score(v) -> str:
        return f"{v:.1f}%" if v is not None else "—"

    def _lb_sigma(v) -> str:
        return f"{v:.1f}%" if v is not None else "—"

    def _tick_health_label(v: str) -> str:
        return (v or "unknown").upper() if v != "unknown" else "unknown"

    cs_rate_a = _per_second(a["context_switches"], a["span_ns"])
    cs_rate_b = _per_second(b["context_switches"], b["span_ns"])
    mig_rate_a = _per_second(a["migrations"], a["span_ns"])
    mig_rate_b = _per_second(b["migrations"], b["span_ns"])
    block_ns_a = _blocking_total_ns(trace_a, lo_a, hi_a)
    block_ns_b = _blocking_total_ns(trace_b, lo_b, hi_b)

    def _fmt_blocking_per_s(block_ns: int, span_ns: int) -> str:
        if span_ns <= 0:
            return "—"
        per_s = int(round(block_ns / (span_ns / 1_000_000_000.0)))
        return f"{_format_time_trim(per_s, scale)}/s"

    def _fmt_blocking_per_s_delta(ba: int, bb: int, sa: int, sb: int) -> str:
        if sa <= 0 or sb <= 0:
            return "—"
        ra = int(round(ba / (sa / 1_000_000_000.0)))
        rb = int(round(bb / (sb / 1_000_000_000.0)))
        return _fmt_signed_time_delta(ra - rb, scale) + "/s" if (ra - rb) != 0 else "0"

    summary_rows = [
        ["Span",
         _format_time_trim(a["span_ns"], scale),
         _format_time_trim(b["span_ns"], scale),
         _fmt_signed_time_delta(a["span_ns"] - b["span_ns"], scale)],
        ["Tasks", a["tasks"], b["tasks"], _fmt_signed_int_delta(a["tasks"] - b["tasks"])],
        ["Segments", a["segments"], b["segments"],
         _fmt_signed_int_delta(a["segments"] - b["segments"])],
        ["STI events", a["sti_events"], b["sti_events"],
         _fmt_signed_int_delta(a["sti_events"] - b["sti_events"])],
        ["Context switches", a["context_switches"], b["context_switches"],
         _fmt_signed_int_delta(a["context_switches"] - b["context_switches"])],
        ["Context switches /s",
         _fmt_rate_per_s(cs_rate_a), _fmt_rate_per_s(cs_rate_b),
         _fmt_signed_rate_delta(cs_rate_a if cs_rate_a is not None else -1.0,
                                cs_rate_b if cs_rate_b is not None else -1.0)],
        ["Core gap avg",
         _format_time_trim(a["gap_avg_ns"], scale),
         _format_time_trim(b["gap_avg_ns"], scale),
         _fmt_signed_time_delta(a["gap_avg_ns"] - b["gap_avg_ns"], scale)],
        ["Core gap max",
         _format_time_trim(a["gap_max_ns"], scale),
         _format_time_trim(b["gap_max_ns"], scale),
         _fmt_signed_time_delta(a["gap_max_ns"] - b["gap_max_ns"], scale)],
        ["Migrations (total)", a["migrations"], b["migrations"],
         _fmt_signed_int_delta(a["migrations"] - b["migrations"])],
        ["Migrations /s",
         _fmt_rate_per_s(mig_rate_a), _fmt_rate_per_s(mig_rate_b),
         _fmt_signed_rate_delta(mig_rate_a if mig_rate_a is not None else -1.0,
                                mig_rate_b if mig_rate_b is not None else -1.0)],
        ["Migrated tasks", a["migrated_tasks"], b["migrated_tasks"],
         _fmt_signed_int_delta(a["migrated_tasks"] - b["migrated_tasks"])],
        ["Blocking time /s",
         _fmt_blocking_per_s(block_ns_a, a["span_ns"]),
         _fmt_blocking_per_s(block_ns_b, b["span_ns"]),
         _fmt_blocking_per_s_delta(block_ns_a, block_ns_b, a["span_ns"], b["span_ns"])],
        ["Load Balance Score",
         _lb_score(a["load_balance_score"]),
         _lb_score(b["load_balance_score"]),
         _fmt_signed_pct_delta(
             (a["load_balance_score"] or 0.0) - (b["load_balance_score"] or 0.0))
         if a["load_balance_score"] is not None and b["load_balance_score"] is not None
         else "—"],
        ["Load Balance σ",
         _lb_sigma(a["load_balance_sigma"]),
         _lb_sigma(b["load_balance_sigma"]),
         _fmt_signed_pct_delta(
             (a["load_balance_sigma"] or 0.0) - (b["load_balance_sigma"] or 0.0))
         if a["load_balance_sigma"] is not None and b["load_balance_sigma"] is not None
         else "—"],
        ["Tick health",
         _tick_health_label(a["tick_health"]),
         _tick_health_label(b["tick_health"]),
         "—"],
        ["Tick mode", a["tick_mode"], b["tick_mode"], "—"],
        ["Tick count", a["tick_count"], b["tick_count"],
         _fmt_signed_int_delta(a["tick_count"] - b["tick_count"])],
        ["Missed ticks (est.)", a["missed_ticks"], b["missed_ticks"],
         _fmt_signed_int_delta(a["missed_ticks"] - b["missed_ticks"])],
    ]

    map_rank_a = _top_tasks_cpu_by_name(trace_a, limit=top_limit, lo=lo_a, hi=hi_a)
    map_rank_b = _top_tasks_cpu_by_name(trace_b, limit=top_limit, lo=lo_b, hi=hi_b)
    if top_limit is None or (isinstance(top_limit, int) and top_limit <= 0):
        map_a, map_b = map_rank_a, map_rank_b
    else:
        map_a = _top_tasks_cpu_by_name(trace_a, limit=None, lo=lo_a, hi=hi_a)
        map_b = _top_tasks_cpu_by_name(trace_b, limit=None, lo=lo_b, hi=hi_b)
    names = sorted(set(map_rank_a) | set(map_rank_b),
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

    util_a = {c: p for c, p in _core_util_pct_rows(trace_a, lo_a, hi_a)}
    util_b = {c: p for c, p in _core_util_pct_rows(trace_b, lo_b, hi_b)}
    core_names = sorted(set(util_a) | set(util_b), key=_core_sort_key_tuple)
    core_util_rows: List[List] = []
    for core in core_names:
        pa = util_a.get(core)
        pb = util_b.get(core)
        a_val = pa if pa is not None else 0.0
        b_val = pb if pb is not None else 0.0
        core_util_rows.append([
            core,
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
        cores_a = ra[3] if ra else "—"
        cores_b = rb[3] if rb else "—"
        primary_a = (f"{ra[5]} {ra[6]:.0f}%" if ra else "—")
        primary_b = (f"{rb[5]} {rb[6]:.0f}%" if rb else "—")
        mig_rows.append([
            name, ma, mb, ma - mb, ra_rate, rb_rate,
            _fmt_signed_rate_delta(ra_rps, rb_rps),
            ra_dwell, rb_dwell, _fmt_signed_dwell_delta(ra_dtu, rb_dtu, scale),
            pa, pb, cores_a, cores_b, primary_a, primary_b,
        ])

    exec_a = _task_metric_compare_by_name(
        trace_a, _exec_slice_samples, lo_a, hi_a, include_cpu=True)
    exec_b = _task_metric_compare_by_name(
        trace_b, _exec_slice_samples, lo_b, hi_b, include_cpu=True)
    exec_names = _take_compare_limit(sorted(
        set(exec_a) | set(exec_b),
        key=lambda n: (-max(exec_a.get(n, {}).get("count", 0),
                            exec_b.get(n, {}).get("count", 0)), n.lower()),
    ), row_limit)
    exec_samp_a = _task_samples_by_name(trace_a, _exec_slice_samples, lo_a, hi_a)
    exec_samp_b = _task_samples_by_name(trace_b, _exec_slice_samples, lo_b, hi_b)
    exec_rows: List[List] = []
    for name in exec_names:
        ea = exec_a.get(name)
        eb = exec_b.get(name)
        max_a = ea["max_ns"] if ea else 0
        max_b = eb["max_ns"] if eb else 0
        exec_rows.append([
            name,
            ea["count"] if ea else 0,
            eb["count"] if eb else 0,
            ea["avg"] if ea else "—",
            eb["avg"] if eb else "—",
            ea["max"] if ea else "—",
            eb["max"] if eb else "—",
            _fmt_signed_time_delta(max_a - max_b, scale),
            _fmt_ks(exec_samp_a.get(name), exec_samp_b.get(name)),
        ])

    block_a = _blocking_compare_by_name(trace_a, lo_a, hi_a)
    block_b = _blocking_compare_by_name(trace_b, lo_b, hi_b)
    block_names = _take_compare_limit(sorted(
        set(block_a) | set(block_b),
        key=lambda n: (-max(block_a.get(n, {}).get("gaps", 0),
                            block_b.get(n, {}).get("gaps", 0)), n.lower()),
    ), row_limit)
    block_samp_a = _task_samples_by_name(trace_a, _blocking_time_samples, lo_a, hi_a)
    block_samp_b = _task_samples_by_name(trace_b, _blocking_time_samples, lo_b, hi_b)
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
            ba["max"] if ba else "—",
            bb["max"] if bb else "—",
            _fmt_signed_time_delta(avg_a - avg_b, scale),
            _fmt_ks(block_samp_a.get(name), block_samp_b.get(name)),
        ])

    ia_a = _task_metric_compare_by_name(
        trace_a, _inter_arrival_samples, lo_a, hi_a)
    ia_b = _task_metric_compare_by_name(
        trace_b, _inter_arrival_samples, lo_b, hi_b)
    ia_names = _take_compare_limit(sorted(
        set(ia_a) | set(ia_b),
        key=lambda n: (-max(ia_a.get(n, {}).get("count", 0),
                            ia_b.get(n, {}).get("count", 0)), n.lower()),
    ), row_limit)
    ia_samp_a = _task_samples_by_name(trace_a, _inter_arrival_samples, lo_a, hi_a)
    ia_samp_b = _task_samples_by_name(trace_b, _inter_arrival_samples, lo_b, hi_b)
    inter_rows: List[List] = []
    for name in ia_names:
        xa = ia_a.get(name)
        xb = ia_b.get(name)
        avg_a = xa["avg_ns"] if xa else 0
        avg_b = xb["avg_ns"] if xb else 0
        inter_rows.append([
            name,
            xa["count"] if xa else 0,
            xb["count"] if xb else 0,
            xa["avg"] if xa else "—",
            xb["avg"] if xb else "—",
            xa["max"] if xa else "—",
            xb["max"] if xb else "—",
            _fmt_signed_time_delta(avg_a - avg_b, scale),
            _fmt_ks(ia_samp_a.get(name), ia_samp_b.get(name)),
        ])

    pre_a = _preemption_totals_by_victim(trace_a, lo_a, hi_a)
    pre_b = _preemption_totals_by_victim(trace_b, lo_b, hi_b)
    pre_names = _take_compare_limit(sorted(
        set(pre_a) | set(pre_b),
        key=lambda n: (-max(pre_a.get(n, {}).get("count", 0),
                            pre_b.get(n, {}).get("count", 0)), n.lower()),
    ), row_limit)
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
        ["Lock-bounce migrations", sa["lock_bounce_migrations"], sb["lock_bounce_migrations"],
         _fmt_signed_int_delta(sa["lock_bounce_migrations"] - sb["lock_bounce_migrations"])],
        ["Core Affinity Violations (bounce)", sa["bounces"], sb["bounces"],
         _fmt_signed_int_delta(sa["bounces"] - sb["bounces"])],
        ["Mutex objects", sa["mutex"], sb["mutex"],
         _fmt_signed_int_delta(sa["mutex"] - sb["mutex"])],
        ["Semaphore objects", sa["sem"], sb["sem"],
         _fmt_signed_int_delta(sa["sem"] - sb["sem"])],
        ["Queue objects", sa["queue"], sb["queue"],
         _fmt_signed_int_delta(sa["queue"] - sb["queue"])],
    ]

    extras_fn = globals().get("compare_analysis_tables")
    if extras_fn is None:
        from .ux_explore import compare_analysis_tables as extras_fn
    extras = extras_fn(
        trace_a, trace_b, lo_a, hi_a, lo_b, hi_b, deadlines, row_limit)
    metrics = extras.get("metrics") or {}
    mutex_a = int(metrics.get("mutex_ns_a") or 0)
    mutex_b = int(metrics.get("mutex_ns_b") or 0)
    summary_rows.extend([
        ["Response P99 (worst task)",
         _fmt_p99_with_task(
             int(metrics.get("response_p99_a") or 0),
             str(metrics.get("response_p99_task_a") or ""), scale),
         _fmt_p99_with_task(
             int(metrics.get("response_p99_b") or 0),
             str(metrics.get("response_p99_task_b") or ""), scale),
         _fmt_signed_time_delta(
             int(metrics.get("response_p99_a") or 0)
             - int(metrics.get("response_p99_b") or 0), scale)],
        ["Mutex blocking (total)",
         _format_time_trim(mutex_a, scale),
         _format_time_trim(mutex_b, scale),
         _fmt_signed_time_delta(mutex_a - mutex_b, scale)],
        ["Mutex blocking /s",
         _fmt_blocking_per_s(mutex_a, a["span_ns"]),
         _fmt_blocking_per_s(mutex_b, b["span_ns"]),
         _fmt_blocking_per_s_delta(mutex_a, mutex_b, a["span_ns"], b["span_ns"])],
        ["Deadline misses",
         int(metrics.get("deadline_misses_a") or 0),
         int(metrics.get("deadline_misses_b") or 0),
         _fmt_signed_int_delta(
             int(metrics.get("deadline_misses_a") or 0)
             - int(metrics.get("deadline_misses_b") or 0))],
    ])
    response_rows = [
        [r.get("name"),
         _format_time(int(r.get("p99_a") or 0), scale),
         _format_time(int(r.get("p99_b") or 0), scale),
         _fmt_signed_time_delta(int(r.get("delta_ns") or 0), scale)]
        for r in extras.get("response") or []
    ]
    mutex_rows = [
        [r.get("name"),
         _format_time(int(r.get("total_a") or 0), scale),
         _format_time(int(r.get("total_b") or 0), scale),
         _fmt_signed_time_delta(int(r.get("delta_ns") or 0), scale)]
        for r in extras.get("mutex_block") or []
    ]
    trend_rows = _compare_trend_table_rows(cross_trace_trends([
        {"name": "Trace A", "snap": a},
        {"name": "Trace B", "snap": b},
    ]))

    return {
        "summary": summary_rows,
        "top": top_rows,
        "core_util": core_util_rows,
        "migrations": mig_rows,
        "execution": exec_rows,
        "blocking": block_rows,
        "inter_arrival": inter_rows,
        "preemption": pre_rows,
        "sync": sync_rows,
        "response": response_rows,
        "mutex_block": mutex_rows,
        "shared_patterns": extras.get("shared_patterns") or [],
        "trends": trend_rows,
        "shape": {
            "cores_a": len(trace_a.core_names or []),
            "cores_b": len(trace_b.core_names or []),
            "task_names_a": sorted({_task_display_name(trace_a.task_repr.get(mk, mk))
                                    for mk in trace_a.tasks}),
            "task_names_b": sorted({_task_display_name(trace_b.task_repr.get(mk, mk))
                                    for mk in trace_b.tasks}),
            "span_a_ns": a["span_ns"],
            "span_b_ns": b["span_ns"],
        },
    }

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
    """csv.writer wrapper that sanitizes every cell against formula injection (CWE-1236).

    ``cell_transform`` (optional) is applied to every cell before sanitising —
    used by ``report --anonymize`` to alias task names.
    """
    def __init__(self, fh, *, cell_transform=None, **kwargs):
        self._writer = csv.writer(fh, **kwargs)
        self._xf = cell_transform or (lambda v: v)

    def writerow(self, row):
        self._writer.writerow(_csv_sanitize_cell(self._xf(c)) for c in row)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


_TIME_PAD_RE = re.compile(r"(-?\d+)\.(\d+)( (?:ns|us|µs|μs|ms|s))")


def _trim_time_pad(v: object) -> str:
    """Drop fixed-decimal padding from an already-formatted time string.

    ``945.000 µs`` -> ``945 µs``; ``3.292 ms`` and any non ``<number> <unit>``
    string are returned unchanged. Safe to run on every report/table cell.
    """
    s = str(v)
    m = _TIME_PAD_RE.fullmatch(s)
    if not m:
        return s
    frac = m.group(2).rstrip("0")
    return f"{m.group(1)}.{frac}{m.group(3)}" if frac else f"{m.group(1)}{m.group(3)}"


def _compare_csv_cell(v: object) -> str:
    s = _trim_time_pad(_csv_sanitize_cell(v))
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
                       tables: Dict[str, List[List]]) -> str:
    lines: List[str] = []
    notable_fn = globals().get("compare_notable_changes")
    formula = globals().get("COMPARE_DELTA_FORMULA")
    glossary = globals().get("COMPARE_METRIC_GLOSSARY")
    if notable_fn is None or formula is None:
        from .ux_explore import COMPARE_DELTA_FORMULA as formula
        from .ux_explore import compare_notable_changes as notable_fn
    if glossary is None:
        from .ux_explore import COMPARE_METRIC_GLOSSARY as glossary
    notable = notable_fn(tables or {}, 8, name_a, name_b) or {}
    ident = notable.get("identity") or {}
    ident_a = ident.get("a") or {}
    ident_b = ident.get("b") or {}
    lines.append(f"Baseline A (Trace A),{_compare_csv_cell(ident_a.get('file') or name_a)}")
    lines.append(f"Candidate B (Trace B),{_compare_csv_cell(ident_b.get('file') or name_b)}")
    lines.append(f"Delta formula,{_compare_csv_cell(formula)}")
    lines.append(f"Metric glossary,{_compare_csv_cell(glossary)}")
    lines.append(f"Cursor scope per tab,{'yes' if scope_enabled else 'no'}")
    lines.append("")
    lines.append("Overview")
    lines.append(f"Verdict,{_compare_csv_cell(notable.get('verdict_label') or 'SIMILAR')}")
    for _b in notable.get("verdict_bullets") or []:
        lines.append(
            "Verdict change,"
            f"{_compare_csv_cell(_b.get('status'))},"
            f"{_compare_csv_cell(_b.get('label'))},"
            f"{_compare_csv_cell(_b.get('change'))}"
        )
    _comp = notable.get("comparability") or {}
    lines.append(
        f"Comparability,{'ok' if _comp.get('comparable', True) else 'WARNING'}"
    )
    for _cw in _comp.get("warnings") or []:
        lines.append(f"Comparability warning,{_compare_csv_cell(_cw)}")
    nxt = str(notable.get("next_investigation") or "").strip()
    if nxt:
        lines.append(f"Next investigation,{_compare_csv_cell(nxt)}")
    omitted = int(notable.get("small_omitted_count") or 0)
    if omitted or int((notable.get("cards") or {}).get("significant") or 0):
        lines.append(
            "Significance note,"
            "Showing engineering-significant deltas only (small changes omitted)"
        )
    cards = notable.get("cards") or {}
    lines.append(
        "Status cards,"
        f"regressions {int(cards.get('regressions') or 0)},"
        f"improvements {int(cards.get('improvements') or 0)},"
        f"significant {int(cards.get('significant') or 0)},"
        f"warnings {int(cards.get('warnings') or 0)}"
    )
    for warn in notable.get("warnings") or []:
        lines.append(f"Warning,{_compare_csv_cell(warn)}")
    lines.append("Status,Metric,Baseline A,Candidate B,Change")
    for row in notable.get("rows") or []:
        lines.append(",".join(_compare_csv_cell(c) for c in (
            row.get("status"), row.get("label"), row.get("a"),
            row.get("b"), row.get("change"),
        )))
    # Minimal Evidence refs when shared-pattern reasons carry time tokens.
    ev_refs = []
    for row in (tables.get("shared_patterns") or []):
        if isinstance(row, dict):
            reason = str(row.get("reason") or "")
            task = str(row.get("task") or row.get("name") or "pattern")
        elif isinstance(row, (list, tuple)) and len(row) >= 5:
            task, reason = str(row[0] or "pattern"), str(row[4] or "")
        else:
            continue
        if any(u in reason.lower() for u in (" ms", " µs", " us", " ns", "jump:")):
            ev_refs.append((task, reason[:120]))
        if len(ev_refs) >= 4:
            break
    if ev_refs:
        lines.append("")
        lines.append("Evidence refs")
        lines.append("Finding,Evidence / Time")
        for lab, ttxt in ev_refs:
            lines.append(
                f"{_compare_csv_cell(lab)},{_compare_csv_cell(ttxt)}"
            )
    lines.append("")

    def _section(title: str, header: str, rows: List[List], ncols: int) -> None:
        lines.append(title)
        lines.append(header)
        for row in rows or []:
            if len(row) >= ncols:
                lines.append(",".join(_compare_csv_cell(c) for c in row[:ncols]))
        lines.append("")

    _section("Summary", "Metric,Baseline A,Candidate B,Δ", tables.get("summary", []), 4)
    _section("Top Tasks", "Task,CPU A (%),CPU B (%),Δ (pp)", tables.get("top", []), 4)
    _section("Core Utilisation", "Core,Util A (%),Util B (%),Δ (pp)", tables.get("core_util", []), 4)
    _section(
        "Core Migrations",
        "Task,Migrations A,Migrations B,Δ,Rate A,Rate B,Rate Δ,"
        "Dwell A,Dwell B,Dwell Δ,Ping-pong A,Ping-pong B,Cores A,Cores B,Primary A,Primary B",
        tables.get("migrations", []), 16)
    _section(
        "Execution Time",
        "Task,Runs A,Runs B,Avg A,Avg B,Max A,Max B,Δ max,Shape Δ",
        tables.get("execution", []), 9)
    _section(
        "Blocking Time",
        "Task,Gaps A,Gaps B,Avg A,Avg B,Max A,Max B,Δ avg,Shape Δ",
        tables.get("blocking", []), 9)
    _section(
        "Inter-Arrival Time",
        "Task,Runs A,Runs B,Avg A,Avg B,Max A,Max B,Δ avg,Shape Δ",
        tables.get("inter_arrival", []), 9)
    _section(
        "Preemption Chains",
        "Victim,Count A,Count B,Δ,Total A,Total B",
        tables.get("preemption", []), 6)
    _section("Sync Objects", "Metric,Baseline A,Candidate B,Δ", tables.get("sync", []), 4)
    _section(
        "Response P99",
        "Task,P99 A,P99 B,Δ",
        tables.get("response", []), 4)
    _section(
        "Mutex Blocking",
        "Task,Total A,Total B,Δ",
        tables.get("mutex_block", []), 4)
    shared_rows = [
        _shared_pattern_table_row(r) for r in (tables.get("shared_patterns") or [])
    ]
    _section(
        "Shared Patterns",
        "Task,Kind,Count A,Count B,Description",
        shared_rows, 5)
    _section(
        "Trends",
        "Trace,Tasks,Migrations,Load balance,Tick health,Span",
        tables.get("trends") or tables.get("trend", []), 6)

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)

_COMPARE_HTML_EXTRA_CSS = f"""
.report.report-compare {{ max-width: min(1280px, 100%); }}
.report-card {{ overflow: hidden; }}
.table-scroll {{ overflow-x: auto; -webkit-overflow-scrolling: touch; max-width: 100%; }}
table {{ border-collapse: collapse; width: max-content; min-width: 100%; }}
th, td {{
  border-bottom: 1px solid var(--line);
  padding: 6px 8px;
  font-size: 12px;
  text-align: right;
  white-space: nowrap;
}}
th:first-child, td:first-child {{ text-align: left; }}
thead th {{ background: #f1f5fb; font-weight: 600; }}
thead th:first-child, tbody td:first-child {{ position: sticky; left: 0; z-index: 1; }}
thead th:first-child {{ background: #f1f5fb; }}
tbody td:first-child {{ background: #fff; }}
tbody tr:nth-child(even) td {{ background: #f7f9fc; }}
tbody tr:nth-child(even) td:first-child {{ background: #f7f9fc; }}
.empty {{ text-align: center; color: var(--muted); white-space: normal; }}
.detail-note {{ margin: 6px 0 10px; font-size: 12px; color: var(--muted); line-height: 1.45; }}
.overview-why {{ color: var(--muted); margin: 0 0 10px; }}
.overview-sub {{ margin: 12px 0 6px; font-size: 13px; color: #123355; }}
.overview-formula {{ color: var(--muted); font-size: 12px; margin: 0 0 10px; }}
.col-baseline {{ color: #2a6fb2; }}
.col-candidate {{ color: #6b4ea8; }}
.status-cards {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0 12px; }}
.status-card {{
  flex: 1 1 120px; border: 1px solid var(--line); border-radius: 8px;
  padding: 8px 10px; background: #fff;
}}
.status-card .n {{ font-size: 20px; font-weight: 700; line-height: 1.1; }}
.status-regressed {{ border-left: 4px solid #c0392b; }}
.status-improved {{ border-left: 4px solid #1f6b45; }}
.status-changed {{ border-left: 4px solid #2a6fb2; }}
.status-warn {{ border-left: 4px solid #c87a12; }}
.badge-regressed {{ background: #fde8e6; color: #9b2c2c; }}
.badge-changed {{ background: #e8eef7; color: #123355; }}
.compare-decision {{
  margin: 0 0 12px; padding: 8px 10px; border-radius: 6px;
  background: rgba(52, 152, 219, 0.10); font-size: 12px; line-height: 1.45; color: #3d4f63;
}}
.compare-decision-identity {{ font-size: 11px; color: #5f6f82; }}
.compare-decision-counts {{ margin-top: 4px; font-weight: 600; color: #123355; }}
.compare-decision-largest {{ margin-top: 4px; color: #182230; }}
.compare-decision-why, .compare-decision-next {{ margin-top: 2px; font-size: 11px; color: #5f6f82; }}
.compare-decision-sig {{ margin-top: 2px; font-size: 10px; color: #7a8690; }}
.compare-verdict {{ margin-top: 6px; }}
.compare-verdict-chip {{
  display: inline-block; padding: 2px 10px; border-radius: 999px;
  font-weight: 700; font-size: 12px; letter-spacing: 0.04em; color: #fff;
}}
.compare-verdict-chip.tone-regressed {{ background: #c0392b; }}
.compare-verdict-chip.tone-improved {{ background: #1f6b45; }}
.compare-verdict-chip.tone-mixed {{ background: #c87a12; }}
.compare-verdict-chip.tone-neutral {{ background: #6b7a8d; }}
.compare-verdict-bullets {{ margin: 6px 0 0; padding-left: 18px; }}
.compare-verdict-bullets li {{ margin: 1px 0; color: #182230; }}
.compare-verdict-bullets li.reg {{ color: #9b2c2c; }}
.compare-verdict-bullets li.imp {{ color: #1f6b45; }}
.compare-verdict-none {{ margin-top: 6px; color: #5f6f82; font-size: 11px; }}
.compare-verdict-banner {{
  display: flex; gap: 10px; align-items: flex-start;
  margin: 6px 0 10px; padding: 10px 12px; border-radius: 8px; border: 1px solid #d9e0ea;
}}
.compare-verdict-glyph {{ font-size: 15px; line-height: 1.3; }}
.compare-verdict-main {{ display: flex; flex-direction: column; gap: 2px; }}
.compare-verdict-label {{ font-weight: 700; font-size: 13px; letter-spacing: 0.04em; }}
.compare-verdict-sentence {{ font-size: 12px; color: #3d4f63; }}
.compare-verdict-banner.tone-regressed {{ background: #fdecea; border-color: #e6b3ac; }}
.compare-verdict-banner.tone-regressed .compare-verdict-label,
.compare-verdict-banner.tone-regressed .compare-verdict-glyph {{ color: #b23125; }}
.compare-verdict-banner.tone-improved {{ background: #e9f5ee; border-color: #a9d3ba; }}
.compare-verdict-banner.tone-improved .compare-verdict-label,
.compare-verdict-banner.tone-improved .compare-verdict-glyph {{ color: #1f6b45; }}
.compare-verdict-banner.tone-mixed {{ background: #fdf3e2; border-color: #e2c48a; }}
.compare-verdict-banner.tone-mixed .compare-verdict-label,
.compare-verdict-banner.tone-mixed .compare-verdict-glyph {{ color: #b4670e; }}
.compare-verdict-banner.tone-neutral {{ background: #eef1f5; border-color: #d1d8e0; }}
.compare-cards {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0 10px; }}
.compare-card {{
  flex: 1 1 120px; border: 1px solid var(--line); border-radius: 8px;
  padding: 8px 10px; background: #fff; display: flex; flex-direction: column; gap: 3px;
}}
.compare-card-k {{ font-size: 10px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }}
.compare-card-v {{ font-size: 18px; font-weight: 700; line-height: 1.1; }}
.compare-card.tone-regressed {{ border-left: 4px solid #c0392b; }}
.compare-card.tone-regressed .compare-card-v {{ color: #b23125; }}
.compare-card.tone-improved {{ border-left: 4px solid #1f6b45; }}
.compare-card.tone-improved .compare-card-v {{ color: #1f6b45; }}
.compare-card.tone-warn {{ border-left: 4px solid #c87a12; }}
.compare-card.tone-warn .compare-card-v {{ color: #b4670e; }}
.compare-card-mover {{ flex: 2 1 200px; }}
.compare-card-mover .compare-card-v {{ font-size: 13px; font-weight: 600; }}
.compare-next {{ margin: 6px 0 4px; font-size: 12px; font-weight: 600; color: #123355; }}
.compare-comparability-warn {{
  margin: 0 0 8px; padding: 8px 10px; border-radius: 6px;
  background: #fdf0e2; border-left: 4px solid #c87a12; color: #6b4a12;
}}
.compare-comparability-head {{ font-weight: 700; }}
.compare-comparability-warn ul {{ margin: 4px 0 0; padding-left: 18px; }}
.compare-comparability-warn li {{ margin: 1px 0; }}
.compare-chart {{ margin: 0 0 12px; overflow-x: auto; }}
.compare-chart svg {{ max-width: 100%; height: auto; display: block; }}
.table-tools {{ margin: 8px 0 12px; }}
.table-toolbar {{
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 6px;
}}
.table-search {{
  font: inherit; font-size: 12px; padding: 4px 8px; border: 1px solid var(--line);
  border-radius: 6px; min-width: 160px;
}}
.table-check {{ font-size: 12px; color: var(--muted); display: inline-flex; gap: 4px; align-items: center; }}
.table-count {{ font-size: 12px; color: var(--muted); margin-left: auto; }}
.table-scroll table {{ min-width: 100%; }}
.sortable {{ cursor: pointer; }}
.sortable:hover {{ color: var(--accent); }}
@media (prefers-color-scheme: dark) {{
  .compare-card {{ background: var(--paper); }}
  .compare-card.tone-regressed .compare-card-v {{ color: #e5776a; }}
  .compare-card.tone-improved .compare-card-v {{ color: #57c191; }}
  .compare-card.tone-warn .compare-card-v {{ color: #e0a44a; }}
  .compare-next {{ color: #cfe1f7; }}
  .compare-comparability-warn {{
    background: #2a2114; border-left-color: #c87a12; color: #e6cfa6;
  }}
  .table-search {{ background: var(--paper); color: var(--ink); }}
}}
{HTML_REPORT_TOC_CSS}
""".strip()

# Same grouping as the Trace Compare dialog's nav rail (pageTabs `group`).
COMPARE_TOC_GROUPS = (
    ("Overview", (
        "Overview", "Summary",
    )),
    ("CPU & Cores", (
        "Top Tasks", "Core Utilisation", "Core Migrations",
    )),
    ("Timing", (
        "Execution Time", "Blocking Time", "Inter-Arrival Time", "Response P99",
    )),
    ("Contention", (
        "Preemption Chains", "Sync Objects", "Mutex Blocking",
    )),
    ("Cross-trace", (
        "Shared Patterns", "Trends",
    )),
)

def _build_compare_html(name_a: str, name_b: str, scope_enabled: bool,
                        tables: Dict[str, List[List]]) -> str:
    scope_note = (
        "Each side uses its own tab cursor range (C1–Cn) when 2+ cursors are placed."
        if scope_enabled else "Full trace span on each side.")

    _g = globals()
    _note_sigma = _g.get("COMPARE_NOTE_SIGMA")
    _note_mig = _g.get("COMPARE_NOTE_MIGRATION")
    _note_sti = _g.get("COMPARE_NOTE_STI")
    _note_p99 = _g.get("COMPARE_NOTE_P99")
    if None in (_note_sigma, _note_mig, _note_sti, _note_p99):
        from .ux_explore import (
            COMPARE_NOTE_SIGMA as _note_sigma,
            COMPARE_NOTE_MIGRATION as _note_mig,
            COMPARE_NOTE_STI as _note_sti,
            COMPARE_NOTE_P99 as _note_p99,
        )

    def _esc(v: object) -> str:
        return html.escape(_trim_time_pad(v), quote=True)

    def _rows_html(rows: List[List], cols: int, empty: str) -> str:
        if not rows:
            return f'<tr><td colspan="{cols}" class="empty">{_esc(empty)}</td></tr>'
        parts = []
        for row in rows:
            cells = "".join(f"<td>{_esc(c)}</td>" for c in row[:cols])
            parts.append(f"<tr>{cells}</tr>")
        return "".join(parts)

    def _card(title: str, headers: List[str], rows: List[List], empty: str,
              lead_html: str = "", note: str = "") -> str:
        cols = len(headers)
        th = "".join(f"<th>{_esc(h)}</th>" for h in headers)
        note_html = (
            f'<p class="detail-note">{_esc(note)}</p>' if note else ""
        )
        return (
            f'<section class="report-card"><h2>{_esc(title)}</h2>'
            f"{note_html}{lead_html}"
            f'<table><thead><tr>{th}</tr></thead>'
            f'<tbody>{_rows_html(rows, cols, empty)}</tbody></table>'
            f"</section>"
        )

    def _overview_card() -> str:
        notable_fn = globals().get("compare_notable_changes")
        formula = globals().get("COMPARE_DELTA_FORMULA")
        if notable_fn is None or formula is None:
            from .ux_explore import COMPARE_DELTA_FORMULA as formula
            from .ux_explore import compare_notable_changes as notable_fn
        notable = notable_fn(tables or {}, 8, name_a, name_b) or {}
        ident = notable.get("identity") or {}
        ident_a = ident.get("a") or {}
        ident_b = ident.get("b") or {}
        ident_rows = [
            ["File", ident_a.get("file") or name_a, ident_b.get("file") or name_b],
            ["Range", ident_a.get("span") or "—", ident_b.get("span") or "—"],
            ["Tick mode", ident_a.get("tick_mode") or "—", ident_b.get("tick_mode") or "—"],
        ]
        verdict_label = str(notable.get("verdict_label") or "SIMILAR")
        verdict_tone = str(notable.get("verdict_tone") or "neutral")
        import re as _re
        verdict_sentence = _re.sub(
            r"^Overall:\s*", "", str(notable.get("verdict") or "")).strip()
        verdict_glyph = {"regressed": "▲", "improved": "▼", "mixed": "◆"}.get(
            verdict_tone, "●")
        comparability = notable.get("comparability") or {}
        comp_warnings = list(comparability.get("warnings") or [])
        cards = notable.get("cards") or {}
        notable_rows = [
            [r.get("status"), r.get("label"), r.get("a"), r.get("b"), r.get("change")]
            for r in (notable.get("rows") or [])
            if isinstance(r, dict)
        ]
        warn_html = "".join(
            f'<p class="warn-banner">{_esc(w)}</p>'
            for w in (notable.get("warnings") or [])
        )
        badge = {
            "Regressed": "badge-regressed",
            "Improved": "badge-ok",
            "Changed": "badge-changed",
        }

        def _notable_rows_html() -> str:
            if not notable_rows:
                return (
                    '<tr><td colspan="5" class="empty">'
                    "No significant improvements or regressions above threshold"
                    "</td></tr>"
                )
            parts = []
            for status, label, a_val, b_val, change in notable_rows:
                cls = badge.get(str(status), "badge-changed")
                parts.append(
                    "<tr>"
                    f'<td><span class="badge {cls}">{_esc(status)}</span></td>'
                    f"<td>{_esc(label)}</td>"
                    f"<td>{_esc(a_val)}</td>"
                    f"<td>{_esc(b_val)}</td>"
                    f"<td>{_esc(change)}</td>"
                    "</tr>"
                )
            return "".join(parts)

        parts = ['<section class="report-card"><h2>Overview</h2>'
                 '<p class="detail-note">Verdict, identity, and engineering-significant '
                 "deltas between Baseline A and Candidate B.</p>"]
        if comp_warnings:
            parts.append(
                '<div class="compare-comparability-warn">'
                '<div class="compare-comparability-head">⚠ Traces may not be '
                'directly comparable</div><ul>'
                + "".join(f"<li>{_esc(w)}</li>" for w in comp_warnings)
                + "</ul></div>"
            )
        parts.append(
            f'<div class="compare-verdict-banner tone-{_esc(verdict_tone)}">'
            f'<span class="compare-verdict-glyph">{verdict_glyph}</span>'
            '<span class="compare-verdict-main">'
            f'<span class="compare-verdict-label">{_esc(verdict_label)}</span>'
            + (f'<span class="compare-verdict-sentence">{_esc(verdict_sentence)}</span>'
               if verdict_sentence else "")
            + "</span></div>"
        )
        nxt = str(notable.get("next_investigation") or "").strip()
        if nxt:
            parts.append(f'<p class="compare-next">{_esc(nxt)}</p>')
        omitted = int(notable.get("small_omitted_count") or 0)
        if omitted or int(cards.get("significant") or 0):
            parts.append(
                '<p class="overview-formula">'
                "Showing engineering-significant deltas only "
                "(small changes omitted)</p>"
            )
        parts.append(f'<p class="overview-formula">{_esc(formula)}</p>')
        _mover = None
        for _r in notable_rows:
            if str(_r[0]) == "Regressed":
                _mover = _r
                break
        if _mover is None:
            for _r in notable_rows:
                if str(_r[0]) == "Improved":
                    _mover = _r
                    break
        _mover_text = f"{_mover[1]}: {_mover[4]}" if _mover else "—"
        parts.append(
            '<div class="compare-cards">'
            f'<div class="compare-card tone-regressed"><span class="compare-card-k">'
            f'Regressions</span><span class="compare-card-v">'
            f'{int(cards.get("regressions") or 0)}</span></div>'
            f'<div class="compare-card tone-improved"><span class="compare-card-k">'
            f'Improvements</span><span class="compare-card-v">'
            f'{int(cards.get("improvements") or 0)}</span></div>'
            f'<div class="compare-card tone-warn"><span class="compare-card-k">'
            f'Warnings</span><span class="compare-card-v">'
            f'{int(cards.get("warnings") or 0)}</span></div>'
            f'<div class="compare-card compare-card-mover"><span class="compare-card-k">'
            f'Biggest mover</span><span class="compare-card-v">'
            f'{_esc(_mover_text)}</span></div>'
            "</div>"
        )
        if warn_html:
            parts.append(warn_html)
        parts.append('<h3 class="overview-sub">Comparison identity</h3>')
        parts.append(
            '<div class="table-scroll"><table><thead><tr>'
            '<th></th><th class="col-baseline">Baseline A</th>'
            '<th class="col-candidate">Candidate B</th></tr></thead><tbody>'
            f'{_rows_html(ident_rows, 3, "No identity")}'
            "</tbody></table></div>"
        )
        # Minimal Evidence refs when shared-pattern reasons carry time tokens.
        ev_rows = []
        for row in (tables.get("shared_patterns") or []):
            if isinstance(row, dict):
                reason = str(row.get("reason") or "")
                task = str(row.get("task") or row.get("name") or "pattern")
            elif isinstance(row, (list, tuple)) and len(row) >= 5:
                task, reason = str(row[0] or "pattern"), str(row[4] or "")
            else:
                continue
            low = reason.lower()
            if any(u in low for u in (" ms", " µs", " us", " ns", "jump:")):
                ev_rows.append([task, reason[:120]])
            if len(ev_rows) >= 4:
                break
        if ev_rows:
            parts.append('<h3 class="overview-sub">Evidence refs</h3>')
            parts.append(
                '<div class="table-scroll"><table><thead><tr>'
                "<th>Finding</th><th>Evidence / Time</th></tr></thead><tbody>"
                f'{_rows_html(ev_rows, 2, "No evidence refs")}'
                "</tbody></table></div>"
            )
        parts.append('<h3 class="overview-sub">Notable Changes</h3>')
        parts.append(
            '<div class="table-scroll"><table><thead><tr>'
            "<th>Status</th><th>Metric</th>"
            '<th class="col-baseline">Baseline A</th>'
            '<th class="col-candidate">Candidate B</th>'
            "<th>Change</th></tr></thead><tbody>"
            f"{_notable_rows_html()}"
            "</tbody></table></div></section>"
        )
        return "".join(parts)

    shared_rows = [
        _shared_pattern_table_row(r) for r in (tables.get("shared_patterns") or [])
    ]
    trend_rows = list(tables.get("trends") or tables.get("trend") or [])

    util_svg_fn = globals().get("compare_core_util_chart_svg")
    util_rows_fn = globals().get("compare_core_util_chart_rows")
    p99_svg_fn = globals().get("compare_p99_delta_chart_svg")
    p99_rows_fn = globals().get("compare_p99_delta_chart_rows")
    sum_svg_fn = globals().get("compare_summary_change_bars_svg")
    sum_rows_fn = globals().get("compare_summary_change_bar_rows")
    heat_svg_fn = globals().get("compare_migration_heatmap_svg")
    heat_rows_fn = globals().get("compare_migration_heatmap_rows")
    mig_filt_fn = globals().get("filter_compare_migration_rows")
    decision_fn = globals().get("compare_summary_decision_html")
    if any(fn is None for fn in (
        util_svg_fn, util_rows_fn, p99_svg_fn, p99_rows_fn,
        sum_svg_fn, sum_rows_fn, heat_svg_fn, heat_rows_fn, mig_filt_fn,
    )):
        from .ux_explore import (
            compare_core_util_chart_rows as util_rows_fn,
            compare_core_util_chart_svg as util_svg_fn,
            compare_p99_delta_chart_rows as p99_rows_fn,
            compare_p99_delta_chart_svg as p99_svg_fn,
            compare_summary_change_bar_rows as sum_rows_fn,
            compare_summary_change_bars_svg as sum_svg_fn,
            compare_migration_heatmap_rows as heat_rows_fn,
            compare_migration_heatmap_svg as heat_svg_fn,
            filter_compare_migration_rows as mig_filt_fn,
            compare_summary_decision_html as decision_fn,
        )
    elif decision_fn is None:
        from .ux_explore import compare_summary_decision_html as decision_fn
    util_svg = util_svg_fn(util_rows_fn(tables or {}))
    p99_svg = p99_svg_fn(p99_rows_fn(tables or {}, 12))
    sum_svg = sum_svg_fn(sum_rows_fn(tables or {}, 8)) if sum_svg_fn and sum_rows_fn else ""
    heat_svg = heat_svg_fn(heat_rows_fn(tables.get("migrations") or [], 12)) if heat_svg_fn and heat_rows_fn else ""
    decision_html = decision_fn(tables or {}, name_a, name_b) if decision_fn else ""
    util_lead = f'<div class="compare-chart">{util_svg}</div>' if util_svg else ""
    p99_lead = f'<div class="compare-chart">{p99_svg}</div>' if p99_svg else ""
    sum_lead = (decision_html or "") + (f'<div class="compare-chart">{sum_svg}</div>' if sum_svg else "")
    heat_lead = f'<div class="compare-chart">{heat_svg}</div>' if heat_svg else ""
    mig_top = mig_filt_fn(tables.get("migrations") or [], "count", "top", "", 10)
    mig_lead = heat_lead
    if mig_top.get("rows"):
        mig_th = "".join(f"<th>{_esc(h)}</th>" for h in (mig_top.get("headers") or []))
        mig_body = _rows_html(
            mig_top.get("rows") or [],
            len(mig_top.get("headers") or []),
            "No migration count changes",
        )
        shown = int(mig_top.get("shown") or 0)
        total = int(mig_top.get("total") or 0)
        mig_lead += (
            f'<h3 class="overview-sub">Largest changes (count &amp; rate)</h3>'
            f'<p class="overview-formula">{shown} of {total} migrated tasks</p>'
            f'<div class="table-scroll"><table><thead><tr>{mig_th}</tr></thead>'
            f'<tbody>{mig_body}</tbody></table></div>'
            '<h3 class="overview-sub">All columns</h3>'
        )

    sections = [
        _overview_card(),
        _card("Summary",
              ["Metric", "Baseline A", "Candidate B", "Δ"],
              tables.get("summary", []), "No data",
              lead_html=sum_lead,
              note="KPI-style totals and rates. Δ = Baseline A − Candidate B "
                   "(positive means A is numerically larger). " + _note_sigma),
        _card("Top Tasks",
              ["Task", "CPU A (%)", "CPU B (%)", "Δ (pp)"],
              tables.get("top", []), "No user tasks in either trace",
              note="Highest CPU consumers excluding IDLE/TICK. "
                   "Δ is percentage points (pp)."),
        _card("Core Utilisation",
              ["Core", "Util A (%)", "Util B (%)", "Δ (pp)"],
              tables.get("core_util", []), "No core util data",
              lead_html=util_lead,
              note="Per-core active util % excluding IDLE/TICK over each side's "
                   "scoped wall-clock span."),
        _card("Core Migrations",
              ["Task", "Migr A", "Migr B", "Δ", "Rate A", "Rate B", "Rate Δ",
               "Dwell A", "Dwell B", "Dwell Δ", "Ping A", "Ping B",
               "Cores A", "Cores B", "Primary A", "Primary B"],
              tables.get("migrations", []), "No migrated tasks in either trace",
              lead_html=mig_lead,
              note="Migration count, rate, dwell, ping-pong, and primary-core "
                   "affinity for tasks that ran on more than one core. " + _note_mig),
        _card("Execution Time",
              ["Task", "Runs A", "Runs B", "Avg A", "Avg B", "Max A", "Max B",
               "Δ max", "Shape Δ"],
              tables.get("execution", []), "No execution samples in either trace",
              note="Per-slice run durations between consecutive context switches. "
                   "Shape Δ is the two-sample KS statistic (0 = same distribution)."),
        _card("Blocking Time",
              ["Task", "Gaps A", "Gaps B", "Avg A", "Avg B", "Max A", "Max B",
               "Δ avg", "Shape Δ"],
              tables.get("blocking", []), "No blocking samples in either trace",
              note="Off-CPU gaps between consecutive slices of the same task "
                   "(preemption, wait, or scheduling delay). "
                   "Shape Δ is the two-sample KS statistic (0 = same distribution)."),
        _card("Inter-Arrival Time",
              ["Task", "Runs A", "Runs B", "Avg A", "Avg B", "Max A", "Max B",
               "Δ avg", "Shape Δ"],
              tables.get("inter_arrival", []), "No inter-arrival samples in either trace",
              note="Time between consecutive activations of the same task "
                   "(slice start to next slice start). "
                   "Shape Δ is the two-sample KS statistic (0 = same distribution)."),
        _card("Preemption Chains",
              ["Victim", "Count A", "Count B", "Δ", "Total A", "Total B"],
              tables.get("preemption", []), "No preemption chains in either trace",
              note="Victim/preemptor pairs for off-CPU gaps on the same core."),
        _card("Sync Objects",
              ["Metric", "Baseline A", "Candidate B", "Δ"],
              tables.get("sync", []), "No sync instrumentation in either trace",
              note="Mutex, semaphore, and queue STI instrumentation totals. "
                   + _note_sti),
        _card("Response P99",
              ["Task", "P99 A", "P99 B", "Δ"],
              tables.get("response", []), "No response samples in either trace",
              lead_html=p99_lead,
              note="Heuristic ready→completion P99 from adjacent slices "
                   "(not an explicit BTF release/completion pair). " + _note_p99),
        _card("Mutex Blocking",
              ["Task", "Total A", "Total B", "Δ"],
              tables.get("mutex_block", []), "No mutex blocking in either trace",
              note="Total mutex-attributed blocking time per task."),
        _card("Shared Patterns",
              ["Task", "Kind", "Count A", "Count B", "Description"],
              shared_rows, "No shared anomaly patterns",
              note="Anomaly kinds present on both sides with counts and a short reason."),
        _card("Trends",
              ["Trace", "Tasks", "Migrations", "Load balance", "Tick health", "Span"],
              trend_rows, "Open 2+ traces to trend summaries",
              note="Multi-trace summary when two or more traces are open."),
    ]

    report = btf_html_report_document(
        "Trace Compare",
        "<!--TOC-->\n" + "\n".join(sections) + "\n"
        + HTML_REPORT_TOC_SCRIPT + "\n" + HTML_REPORT_INTERACTIVE_SCRIPT,
        subtitle=f"Baseline A: {name_a} vs Candidate B: {name_b} · {scope_note}",
        extra_css=_COMPARE_HTML_EXTRA_CSS,
        doc_title="BTFViewer — Trace Compare",
        report_class="report-compare",
    )
    return html_apply_collapsible_toc(
        report,
        default_expanded=("Overview", "Summary"),
        toc_groups=COMPARE_TOC_GROUPS,
    )

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

def _percentile_sample_index(n: int, p: float) -> int:
    """Index of the p-quantile in a sorted n-sample list (stats-table formula)."""
    if n <= 0:
        return 0
    return min(n - 1, max(0, math.ceil(n * float(p)) - 1))

def _find_percentile_exec_segment(segs: list, p: float,
                                  lo: Optional[int] = None,
                                  hi: Optional[int] = None
                                  ) -> Optional[TaskSegment]:
    """Return the slice at percentile *p* of duration."""
    samples: List[Tuple[int, TaskSegment]] = []
    for s in segs or []:
        d = s.end - s.start
        if d <= 0:
            continue
        if lo is not None and hi is not None and not _seg_fully_in_range(s, lo, hi):
            continue
        samples.append((d, s))
    if not samples:
        return None
    samples.sort(key=lambda kv: kv[0])
    return samples[_percentile_sample_index(len(samples), p)][1]

def _find_percentile_blocking_segment(segs: list, p: float,
                                      lo: Optional[int] = None,
                                      hi: Optional[int] = None
                                      ) -> Optional[TaskSegment]:
    """Return the resume slice at percentile *p* of off-CPU gap."""
    if not segs or len(segs) < 2:
        return None
    ordered = sorted(segs, key=lambda s: s.start)
    samples: List[Tuple[int, TaskSegment]] = []
    for i in range(1, len(ordered)):
        prev, nxt = ordered[i - 1], ordered[i]
        if lo is not None and hi is not None:
            if not (_seg_fully_in_range(prev, lo, hi) and _seg_fully_in_range(nxt, lo, hi)):
                continue
        gap = nxt.start - prev.end
        if gap > 0:
            samples.append((gap, nxt))
    if not samples:
        return None
    samples.sort(key=lambda kv: kv[0])
    return samples[_percentile_sample_index(len(samples), p)][1]

def _find_percentile_inter_arrival_segment(segs: list, p: float,
                                           lo: Optional[int] = None,
                                           hi: Optional[int] = None
                                           ) -> Optional[TaskSegment]:
    """Return the activation slice at percentile *p* of inter-arrival gap."""
    if not segs or len(segs) < 2:
        return None
    ordered = sorted(segs, key=lambda s: s.start)
    samples: List[Tuple[int, TaskSegment]] = []
    for i in range(1, len(ordered)):
        prev, nxt = ordered[i - 1], ordered[i]
        gap = nxt.start - prev.start
        if gap <= 0:
            continue
        if lo is not None and hi is not None and (nxt.start < lo or nxt.start > hi):
            continue
        samples.append((gap, nxt))
    if not samples:
        return None
    samples.sort(key=lambda kv: kv[0])
    return samples[_percentile_sample_index(len(samples), p)][1]

class _ParseCancelledError(Exception):
    """Internal control-flow exception used to abort _parse_btf cleanly."""


def _drawable_time_range(
    segments: List[TaskSegment],
    sti_events: List[StiEvent],
    tick_sti_times: List[int],
) -> Optional[Tuple[int, int]]:
    """Span covering painted activity (run segments, STI, tick marks).

    Boot-time ``task_create`` / ``set_frequency`` events are excluded so
    fit-to-window does not leave a blank left margin.
    """
    lo: Optional[int] = None
    hi: Optional[int] = None
    for seg in segments:
        if lo is None or seg.start < lo:
            lo = seg.start
        if hi is None or seg.end > hi:
            hi = seg.end
    for ev in sti_events:
        t = ev.time
        if lo is None or t < lo:
            lo = t
        if hi is None or t > hi:
            hi = t
    for t in tick_sti_times:
        if lo is None or t < lo:
            lo = t
        if hi is None or t > hi:
            hi = t
    if lo is None or hi is None or hi <= lo:
        return None
    return lo, hi


def _parse_btf(filepath: str,
              progress_callback=None,
              cancel_check=None) -> BtfTrace:
    """Parse a .btf file and return a BtfTrace.

    *progress_callback*, if given, is called as
    ``progress_callback(pct, message)``
    where *pct* is an integer 0-100 and *message* is a short status string.
    """
    try:
        size_path, _member = _split_zip_member_path(filepath)
        file_size = os.path.getsize(size_path)
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
    with _open_btf_text(filepath) as fh:
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
                        # Spec Table uses #timescale; Vector examples and
                        # FreeRTOS emitters use #timeScale — accept any case.
                        if key.lower() == "timescale":
                            meta["timeScale"] = value
                            time_scale = value
                        else:
                            meta[key] = value
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
            # Update time bounds only for non-C (non-set_frequency) events.
            # After segment reconstruction these are tightened to drawable
            # activity so a task_create storm does not pad the left margin.
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
    if progress_callback:
        progress_callback(61, "Indexing migrations…")
    _migration_times = [m.ns for m in _migrations]
    _migrated_mks = frozenset(_migrations_by_mk.keys())
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
    _drawn = _drawable_time_range(segments, sti_events, tick_sti_times)
    if _drawn is not None:
        time_min, time_max = _drawn
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

    _task_cpu_ns: Dict[str, int] = {}
    for mk, segs in segs_by_mk.items():
        raw = _mk_repr.get(mk, mk)
        tname = _parse_task_name(raw)[2]
        if _is_idle_task_name(tname) or tname == "TICK":
            continue
        t_ns = sum(s.end - s.start for s in segs)
        if t_ns > 0:
            _task_cpu_ns[mk] = t_ns

    trace = BtfTrace(
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
        migration_times=_migration_times,
        migrated_mks=_migrated_mks,
        task_cpu_ns=_task_cpu_ns,
    )
    if progress_callback:
        progress_callback(99, "Preparing statistics…")
    _ctx, _gaps = _scheduling_stats(trace)
    trace.sched_ctx_switches = _ctx
    trace.sched_core_gaps = _gaps
    trace.migration_rows_full = _migration_rows(trace)
    # Bundle concatenates modules into one file, so a relative import fails there.
    prepare = globals().get("prepare_ux_events")
    if prepare is None:
        from .ux_explore import prepare_ux_events as prepare
    prepare(trace)
    return trace

