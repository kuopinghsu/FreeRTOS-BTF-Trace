"""
btf_viewer.py – Single-file BTF Trace Viewer (PyQt5).

Usage:
    python btf_viewer.py [trace.btf]

Parses RTOS .btf context-switch traces and renders an interactive
Gantt-style timeline with multi-cursor, drag-to-move, zoom/pan, and
expandable core-view rows.

Architecture overview
---------------------
  1. BTF Parser  (parse_btf)
     Reads the .btf text file line-by-line and reconstructs task
     execution segments from the sparse event stream (resume / preempt
     pairs).  All derived lookup tables (seg_map_by_merge_key, core_segs,
     core_task_segs, …) are pre-built here once so that scene rebuilds
     never iterate over raw segments again.

  2. Data model  (dataclasses: RawEvent, TaskSegment, StiEvent, BtfTrace)
     Plain dataclasses; no Qt dependency.  BtfTrace is the single source
     of truth passed from the parser to the scene.

  3. Timeline scene  (TimelineScene : QGraphicsScene)
     Converts BtfTrace data into QGraphicsItems at a given zoom level
     (ns_per_px).  Four builder methods cover the two view modes
     (task / core) × two orientations (horizontal / vertical).  The scene
     is fully torn down and rebuilt on every zoom/scroll action.

  4. Graphics items  (_RulerItem, _BatchRowItem, _BatchStiItem, …)
     Custom QGraphicsItem subclasses.  _BatchRowItem and _BatchStiItem
     each represent an entire row with a single Qt item and use a
     3-tier Level-of-Detail (LOD) paint strategy to keep frame times
     low across the full zoom range (see _BatchRowItem docstring).

  5. Timeline view  (TimelineView : QGraphicsView)
     Wraps the scene; handles mouse events (click → cursor, drag → pan,
     Ctrl+wheel / pinch → zoom, middle-drag → range-zoom), label-column
     resize, and frozen-label repositioning on scroll.

  6. Main window  (MainWindow : QMainWindow)
     Top-level application window.  Owns the toolbar, menus, status bar,
     legend dock, and drag-and-drop file opening.

Section index
-------------
  USER CONFIGURATION  – fonts, layout, colours, cursors, LOD thresholds
                        (edit here to customise the viewer appearance)
  BTF Parser          – dataclasses + task-name helpers + parse_btf()
  Timeline Widget     – internal colour helpers, _format_time, _monospace_font,
                        _lod_reduce, _nice_grid_step
  Scene               – TimelineScene and its four builder methods
  Graphics Items      – _RulerItem, _BatchRowItem, _BatchStiItem,
                        _TaskLabelItem, _CoreHeaderItem,
                        _SegmentItem (legacy), _StiMarkerItem (legacy)
  View                – TimelineView (pan / zoom / cursor mouse handling)
  Main Window         – _CursorButton, CursorBarWidget, LegendWidget,
                        _WheelSpinBox, MainWindow
  Entry point         – main()
"""

from __future__ import annotations

import configparser
import functools
import os
import re
import shutil
import subprocess
import sys
import threading
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import (
    QBuffer, QByteArray, QEvent, QIODevice, QLineF, QMimeData,
    QPoint, QPointF, QRectF, QSize, Qt, QThread, QTimer,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QBrush, QColor, QFont, QFontDatabase, QFontMetrics, QIcon, QKeySequence, QPainter,
    QPalette, QPen, QPixmap, QPolygonF, QWheelEvent,
)
from PyQt5.QtWidgets import (
    QAction, QApplication, QCheckBox, QDockWidget, QFileDialog,
    QFrame, QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem,
    QGraphicsRectItem, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QProgressBar,
    QProgressDialog,
    QPushButton, QScrollArea, QSpinBox, QStackedWidget,
    QStatusBar, QStyleFactory, QStyleOptionGraphicsItem,
    QToolBar, QToolButton, QVBoxLayout, QWidget,
)
from PyQt5.QtSvg import QSvgGenerator  # noqa: F401 – kept for optional future SVG use

# ===========================================================================
# USER CONFIGURATION
# Edit the values in this section to customise the viewer.
# Everything else in the file is internal implementation detail.
# ===========================================================================

# ---- Fonts ----------------------------------------------------------------
_FONT_SIZE    = 10   # Timeline label font size (pt).  Adjustable at runtime
                     # via the Font spinbox in the toolbar.
_UI_FONT_SIZE = 10   # Application UI font: menus, toolbar, status bar (pt).

# ---- Layout ---------------------------------------------------------------
LABEL_WIDTH   = 160  # Width of the frozen task-label column (px).
RULER_HEIGHT  =  40  # Height of the time ruler row (px) — horizontal mode.
RULER_WIDTH   =  80  # Width of the time ruler column (px) — vertical mode.
ROW_HEIGHT    =  22  # Height of each task / core row (px).
ROW_GAP       =   4  # Vertical gap between rows (px).
STI_ROW_H     =  18  # Height of an STI (software-trace) row (px).
STI_MARKER_H  =   6  # Height of an STI marker triangle (px).
MIN_SEG_WIDTH = 1.0  # Minimum painted width of a task segment (px).

# ---- Cursors --------------------------------------------------------------
MAX_CURSORS    = 4
_CURSOR_COLORS = ["#FF4444", "#44FF88", "#4499FF", "#FFAA22"]

# ---- Task colour palette --------------------------------------------------
# 16-colour cycle used to distinguish tasks (hex RGB strings).
_PALETTE = [
    "#4E9AF1", "#F1884E", "#4EF188", "#F14E9A",
    "#9A4EF1", "#F1D94E", "#4EF1D9", "#F14E4E",
    "#88C057", "#C057C0", "#57C0C0", "#C09057",
    "#7B68EE", "#EE687B", "#68EE7B", "#EEB468",
]

# Colour map for core header dots.
# Core dot / header colors – 16 hand-picked distinct hues that cycle for
# more than 16 cores.  Index by numeric core ID extracted from "Core_N".
_CORE_PALETTE = [
    "#FF9933",  # 0  orange
    "#33BBFF",  # 1  sky blue
    "#66FF88",  # 2  lime green
    "#FF66AA",  # 3  pink
    "#FFEE44",  # 4  yellow
    "#BB77FF",  # 5  purple
    "#44FFEE",  # 6  cyan
    "#FF5555",  # 7  red
    "#AADDFF",  # 8  light blue
    "#FFBB55",  # 9  amber
    "#88FF44",  # 10 yellow-green
    "#FF88DD",  # 11 lavender-pink
    "#55DDBB",  # 12 teal
    "#FFAA77",  # 13 peach
    "#99BBFF",  # 14 periwinkle
    "#DDFF77",  # 15 chartreuse
]

# ---------------------------------------------------------------------------
# SVG icon helpers
# ---------------------------------------------------------------------------

def _svg_icon(path_data: str, color: str = "#9E9E9E", size: int = 16) -> "QIcon":
    """Build a QIcon from an SVG path string (16×16 viewBox by default)."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 16 16"><path fill="{color}" d="{path_data}"/></svg>'
    )
    ba = QByteArray(svg.encode())
    pm = QPixmap()
    pm.loadFromData(ba, "SVG")
    return QIcon(pm)

# Icon path data (16×16 viewBox, single-path SVG outlines)
_IC_OPEN   = "M2 4a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1H7L5.5 4H2z"
_IC_SAVE   = "M2 1a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V4.5L11.5 1H2zm2 1h5v3H4V2zm4 8a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3zM3 10h10v4H3v-4z"
_IC_COPY   = "M4 1.5H3a2 2 0 0 0-2 2V14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V3.5a2 2 0 0 0-2-2h-1v1h1a1 1 0 0 1 1 1V14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1h1v-1zM5 0h6a1 1 0 0 1 1 1v3H4V1a1 1 0 0 1 1-1z"
_IC_HORIZ  = "M1 4h14v2H1zm0 4h14v2H1zm0 4h14v2H1z"
_IC_VERT   = "M3 1h2v14H3zm4 0h2v14H7zm4 0h2v14h-2z"
_IC_ZIN    = "M6.5 1a5.5 5.5 0 1 0 3.89 9.4l3.4 3.4.7-.7-3.4-3.4A5.5 5.5 0 0 0 6.5 1zm0 1a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9zM6 5v1.5H4.5v1H6V9h1V7.5h1.5v-1H7V5H6z"
_IC_ZOUT   = "M6.5 1a5.5 5.5 0 1 0 3.89 9.4l3.4 3.4.7-.7-3.4-3.4A5.5 5.5 0 0 0 6.5 1zm0 1a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9zM4 6h5v1H4V6z"
_IC_FIT    = "M1.5 1h5v1h-4v4h-1V1.5a.5.5 0 0 1 .5-.5zm13 0a.5.5 0 0 1 .5.5V6h-1V2h-4V1h4.5zM1 10h1v4h4v1H1.5a.5.5 0 0 1-.5-.5V10zm14 0v4.5a.5.5 0 0 1-.5.5H10v-1h4v-4h1z"
_IC_CURSOR = "M1 1l5 12 2-4 4 4 1-1-4-4 4-2L1 1z"
_IC_CLEAR  = "M2 2.5l.5-.5 5.5 5.5 5.5-5.5.5.5L8.5 8 14 13.5l-.5.5L8 8.5 2.5 14l-.5-.5L7.5 8 2 2.5z"
_IC_LEGEND = "M1 2a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V2zm5-1h8v1H6V1zm0 3h8v1H6V4zm-5 3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V7zm5-1h8v1H6V6zm0 3h8v1H6V9zm-5 3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1v-2zm5-1h8v1H6v-1zm0 3h8v1H6v-1z"
_IC_TASK   = "M1 2.5A1.5 1.5 0 0 1 2.5 1h11A1.5 1.5 0 0 1 15 2.5v11a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 13.5v-11zM4 5.5h8v1H4v-1zm0 3h8v1H4v-1zm0 3h5v1H4v-1z"
_IC_CORE   = "M5 1v2H3a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2v2h1v-2h4v2h1v-2h2a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2h-2V1h-1v2H6V1H5zm-2 4h10v6H3V5zm2 1v4h6V6H5z"
_IC_EXPAND = "M1.5 1h5v1h-4v4h-1V1.5a.5.5 0 0 1 .5-.5zm13 0a.5.5 0 0 1 .5.5V6h-1V2h-4V1h4.5zM1 10h1v4h4v1H1.5a.5.5 0 0 1-.5-.5V10zm14 0v4.5a.5.5 0 0 1-.5.5H10v-1h4v-4h1z"

def _core_color(core_name: str) -> str:
    """Return a distinct color hex string for a core name like 'Core_N'."""
    if core_name.startswith("Core_"):
        tail = core_name[5:]
        if tail.isdigit():
            return _CORE_PALETTE[int(tail) % len(_CORE_PALETTE)]
    return "#AAAAAA"

# Alpha-tint overlaid on task colours to indicate which core a segment ran on.
_CORE_TINTS = {
    "Core_0": QColor(255, 255, 255, 0),   # no tint
    "Core_1": QColor(0,   0,   40,  40),  # subtle blue
    "Core_2": QColor(0,   40,  0,   40),  # subtle green
    "Core_3": QColor(40,  0,   0,   40),  # subtle red
    "Core_?": QColor(60,  60,  60,  60),  # grey for unknown cores
}

# Colour overrides for specific well-known task names.
_SPECIAL_COLORS: Dict[str, QColor] = {
    "TICK": QColor("#E8C84A"),
}

# ---- STI event colours ----------------------------------------------------
# Fixed colours for well-known STI notes; unknown notes get auto-assigned
# colours from the internal _STI_PALETTE (defined in Timeline Widget below).
_STI_COLORS: Dict[str, QColor] = {
    "take_mutex":   QColor("#E05050"),
    "give_mutex":   QColor("#50C050"),
    "create_mutex": QColor("#5080E0"),
    "trigger":      QColor("#C08030"),
    # Unknown notes are assigned dynamically by _sti_color().
}

# ---- Performance / Level-of-Detail ----------------------------------------
NS_PER_PX_DEFAULT = 5.0    # Initial zoom level (nanoseconds per screen pixel).
# _BatchRowItem.paint() LOD thresholds (Qt levelOfDetail: 1.0 = 100% zoom).
_PAINT_LOD_COARSE = 0.45   # Below: merge nearby segments, skip pen outlines.
_PAINT_LOD_MICRO  = 0.12   # Below: draw one tinted activity bar per row.
# Number of bins used when pre-computing a coarse LOD summary at parse time.
# The summary is stored in BtfTrace and replaces O(N_segs) _lod_reduce calls
# with an O(4096) worst-case iteration during fit-to-view rebuilds.
_LOD_SUMMARY_BINS = 4096

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
    event:      str   # event verb: 'resume', 'preempt', 'trigger', …
    note:       str   # optional annotation (e.g. 'task_create', mutex name)

@dataclass
class TaskSegment:
    """One contiguous execution slice of a task on a core."""
    task: str
    start: int          # ns
    end: int            # ns
    core: str           # e.g. "Core_0"

@dataclass
class StiEvent:
    """An RTOS software trace item (mutex/semaphore/queue event, etc.)."""
    time: int
    core: str           # source core (e.g. "Core_0")
    target: str         # STI target name (e.g. "mutex_event")
    event: str          # event name (e.g. "trigger")
    note: str           # detail (e.g. "take_mutex")

@dataclass
class BtfTrace:
    """Parsed result of a .btf file."""
    time_scale: str                     # "ns", "us", "ms" …
    tasks: List[str]                    # ordered task name list
    segments: List[TaskSegment]
    sti_events: List[StiEvent]
    sti_channels: List[str]             # ordered list of distinct STI channel names
    sti_events_by_target: Dict[str, List[StiEvent]]   # fast lookup for builders
    time_min: int
    time_max: int
    meta: Dict[str, str] = field(default_factory=dict)
    # Pre-built, start-time-sorted segment map keyed by task_merge_key.
    # Avoids O(n_segments) iteration on every scene rebuild.
    seg_map_by_merge_key: Dict[str, List[TaskSegment]] = field(default_factory=dict)
    # Pre-built core-view data – cached once at parse time so core-view
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
    # Pre-sorted start-time lists (ints) for each key – enable O(log n) bisect
    # clipping so builders only iterate segments visible in the current viewport.
    seg_start_by_merge_key:  Dict[str, List[int]]             = field(default_factory=dict)
    core_seg_starts:         Dict[str, List[int]]             = field(default_factory=dict)
    core_task_seg_starts:    Dict[str, Dict[str, List[int]]]  = field(default_factory=dict)
    sti_starts_by_target:    Dict[str, List[int]]             = field(default_factory=dict)

    # Pre-built coarse LOD summaries (_LOD_SUMMARY_BINS bins over the full time
    # span).  When ns_per_px >= seg_lod_ns_per_px (i.e., zoomed out past the
    # summary resolution), builders use these instead of iterating raw segments,
    # bounding rebuild cost to O(_LOD_SUMMARY_BINS) regardless of trace size.
    seg_lod_ns_per_px:              float                                   = 1.0
    seg_lod_by_merge_key:           Dict[str, List[TaskSegment]]            = field(default_factory=dict)
    seg_lod_starts_by_merge_key:    Dict[str, List[int]]                    = field(default_factory=dict)
    core_seg_lod:                   Dict[str, List[TaskSegment]]            = field(default_factory=dict)
    core_seg_lod_starts:            Dict[str, List[int]]                    = field(default_factory=dict)
    core_task_seg_lod:              Dict[str, Dict[str, List[TaskSegment]]] = field(default_factory=dict)
    core_task_seg_lod_starts:       Dict[str, Dict[str, List[int]]]         = field(default_factory=dict)
    # Map from merge-key → timestamp of the task_create event (first occurrence).
    task_create_times: Dict[str, int]                                       = field(default_factory=dict)

# ---------------------------------------------------------------------------
# Task-name helpers
# ---------------------------------------------------------------------------

_TASK_RE = re.compile(r"^\[(\d+)/(\d+)\](.+)$")

@functools.lru_cache(maxsize=16384)
def parse_task_name(raw: str) -> Tuple[Optional[int], Optional[int], str]:
    """Return (core_id, task_id, display_name) from a raw BTF task name."""
    m = _TASK_RE.match(raw)
    if m:
        return int(m.group(1)), int(m.group(2)), m.group(3).strip()
    return None, None, raw

@functools.lru_cache(maxsize=16384)
def task_display_name(raw: str) -> str:
    """Short display name: 'Name[id]' for regular tasks; bare name for IDLE/TICK."""
    _, task_id, name = parse_task_name(raw)
    if task_id is not None and not (name.startswith("IDLE") or name == "TICK"):
        return f"{name}[{task_id}]"
    return name

@functools.lru_cache(maxsize=16384)
def task_sort_key(raw: str) -> Tuple[int, int, str]:
    """Sorting key: user tasks first, then IDLE, then TICK."""
    core_id, task_id, name = parse_task_name(raw)
    if name.startswith("IDLE"):
        group = 2
    elif name == "TICK":
        group = 3
    else:
        group = 1
    return (group, task_id if task_id is not None else 0, name)

@functools.lru_cache(maxsize=16384)
def task_merge_key(raw: str) -> str:
    """Stable key that ignores core_id, used to merge cross-core task rows in task view.

    Two raw names like '[0/1]MyTask' and '[1/1]MyTask' share the same merge key
    so they collapse into a single row in the task view, while the core view still
    shows them separately.
    """
    _, task_id, name = parse_task_name(raw)
    if task_id is not None:
        return f"\x00{task_id}\x00{name}"
    return raw  # no [core/id] prefix → use as-is

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=4096)
def _is_core_entity(name: str) -> bool:
    return name.startswith("Core_")

class _ParseCancelledError(Exception):
    """Internal control-flow exception used to abort parse_btf cleanly."""

def parse_btf(filepath: str,
              progress_callback=None,
              cancel_check=None) -> BtfTrace:
    """Parse a .btf file and return a BtfTrace.

    *progress_callback*, if given, is called as
    ``progress_callback(pct, message)``
    where *pct* is an integer 0–100 and *message* is a short status string.
    """

    meta: Dict[str, str] = {}
    time_scale = "ns"

    # T-events grouped by timestamp for O(1) same-tick access
    t_events_by_time: Dict[int, List[Tuple]] = defaultdict(list)
    sti_events: List[StiEvent] = []
    time_min = 0
    time_max = 0
    first_event = True
    # raw_name → first task_create timestamp
    _task_create_raw: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Phase 1 : file reading
    # Scan every line in one pass; collect T-events into a dict keyed by
    # timestamp so that all same-tick events can be processed together in
    # Phase 2.  STI events are stored as-is.  Comment/meta lines (#) fill
    # the meta dict and set time_scale.
    # ------------------------------------------------------------------
    if progress_callback:
        progress_callback(2, "Reading file…")
    with open(filepath, encoding="utf-8", errors="replace") as fh:
        for line_index, line in enumerate(fh, start=1):
            if cancel_check and line_index % 2048 == 0 and cancel_check():
                raise _ParseCancelledError()
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                stripped = line[1:].strip()
                if " " in stripped:
                    key, _, value = stripped.partition(" ")
                    meta[key] = value.strip()
                    if key == "timeScale":
                        time_scale = value.strip()
                continue

            parts = line.split(",")
            if len(parts) < 7:
                continue

            try:
                t = int(parts[0])
            except ValueError:
                continue

            ev_type = parts[3].strip()
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
                if _note == "task_create":
                    _tgt_raw = parts[4].strip()
                    if _tgt_raw not in _task_create_raw:
                        _task_create_raw[_tgt_raw] = t
                t_events_by_time[t].append((
                    t,
                    parts[1].strip(),   # source
                    parts[6].strip(),   # event
                    parts[4].strip(),   # target
                    _note,              # note
                ))
            elif ev_type == "STI":
                sti_events.append(StiEvent(
                    time=t,
                    core=parts[1].strip(),
                    target=parts[4].strip(),
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
    # _open_seg  → record the start of a new execution interval.
    # _close_seg → seal the current open interval into a TaskSegment.
    #
    # At each timestamp we process events in two passes:
    #   Pass A  – resume events: close the pre-empted task, open the
    #             newly resumed task on the correct core.
    #   Pass B  – preempt events that have NO matching resume at the same
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

    for timestamp_index, ts in enumerate(sorted(t_events_by_time), start=1):
        if cancel_check and timestamp_index % 512 == 0 and cancel_check():
            raise _ParseCancelledError()
        events = t_events_by_time[ts]
        # (time, source, event, target, note)

        core_preempts: Dict[str, str] = {}
        for (_, src, ev, tgt, _note) in events:
            if ev == "preempt" and _is_core_entity(src):
                core_preempts[tgt] = src

        # Build resume-source set once (avoids O(n²) generator inside loop)
        resume_sources = {src for (_, src, ev, tgt, _n) in events if ev == "resume"}

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
                core = "Core_?"

            _close_seg(src, ts)
            _open_seg(tgt, ts, core)

        for (_, src, ev, tgt, _note) in events:
            if ev == "preempt":
                if tgt not in resume_sources:
                    core = core_preempts.get(tgt, last_core.get(tgt, "Core_?"))
                    _close_seg(tgt, ts)
                    if _is_core_entity(src):
                        last_core[tgt] = src

    for task in list(open_seg.keys()):
        _close_seg(task, time_max)

    if progress_callback:
        progress_callback(55, "Building lookup tables…")

    # ------------------------------------------------------------------
    # Phase 3 : post-processing – build sorted task list + lookup tables
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
            mk = task_merge_key(seg.task)
            _mk_cache[seg.task] = mk
        segs_by_mk_build[mk].append(seg)
        # TICK is a global event not associated with any real core; suppress it
        # from Core_? so it doesn't pollute the unknown-core row in core view.
        _tname = parse_task_name(seg.task)[2]
        if not (_tname == "TICK" and seg.core == "Core_?"):
            _core_segs_build[seg.core].append(seg)
            _cn_set.add(seg.core)

    task_set: set = set(_mk_cache.values())
    # Sort by the first representative raw task name for each key.
    _mk_repr: Dict[str, str] = {}
    for raw, mk in _mk_cache.items():
        if mk not in _mk_repr:
            _mk_repr[mk] = raw
    # TICK is rendered on the time-scale ruler, not as a task row.
    _tick_mk_excl = task_merge_key("TICK")
    tasks = sorted(
        (mk for mk in task_set if mk != _tick_mk_excl),
        key=lambda mk: task_sort_key(_mk_repr[mk]))

    sti_channels = sorted({e.target for e in sti_events})
    sti_by_target: Dict[str, List[StiEvent]] = defaultdict(list)
    for _ev in sti_events:
        sti_by_target[_ev.target].append(_ev)

    segs_by_mk: Dict[str, list] = dict(segs_by_mk_build)
    for _lst in segs_by_mk.values():
        _lst.sort(key=lambda s: s.start)
    def _core_sort_key(c: str):
        if c.startswith("Core_"):
            tail = c[5:]
            return (0, int(tail) if tail.isdigit() else float("inf"), c)
        return (1, float("inf"), c)
    _core_names = sorted(_cn_set, key=_core_sort_key)
    _core_segs: Dict[str, list] = {c: list(_core_segs_build.get(c, [])) for c in _core_names}

    if progress_callback:
        progress_callback(62, "Sorting core segments…")
    if cancel_check and cancel_check():
        raise _ParseCancelledError()

    _core_task_order: Dict[str, list] = {}
    _core_task_segs:  Dict[str, dict] = {}
    for c in _core_names:
        _tsm: Dict[str, list] = {}
        for seg in _core_segs[c]:
            if seg.task in _tsm:
                _tsm[seg.task].append(seg)
            else:
                _tsm[seg.task] = [seg]
        for _lst in _tsm.values():
            _lst.sort(key=lambda s: s.start)
        _core_segs[c].sort(key=lambda s: s.start)
        _core_task_order[c] = sorted(_tsm.keys(), key=task_sort_key)
        _core_task_segs[c]  = _tsm

    # Map raw task_create names to merge keys.
    _task_create_times: Dict[str, int] = {}
    for _raw_ct, _ct_time in _task_create_raw.items():
        _mk_ct = _mk_cache.get(_raw_ct) or task_merge_key(_raw_ct)
        if _mk_ct not in _task_create_times or _ct_time < _task_create_times[_mk_ct]:
            _task_create_times[_mk_ct] = _ct_time

    # ------------------------------------------------------------------
    # Phase 4 : 1M-event performance pre-processing
    # Pre-build start-time arrays (for O(log n) bisect viewport clipping)
    # and a coarse LOD summary (_LOD_SUMMARY_BINS bins over the full time
    # span) so that scene rebuilds never iterate more than _LOD_SUMMARY_BINS
    # segments per row at fit-to-view zoom.
    # ------------------------------------------------------------------
    _time_span = max(time_max - time_min, 1)
    _lod_ns_per_px = _time_span / _LOD_SUMMARY_BINS  # ns per summary bin

    if progress_callback:
        progress_callback(70, "Building task LOD summaries…")
    if cancel_check and cancel_check():
        raise _ParseCancelledError()

    def _make_lod_summary(segs_sorted: list) -> list:
        """Down-sample a sorted segment list to at most _LOD_SUMMARY_BINS entries."""
        if len(segs_sorted) <= _LOD_SUMMARY_BINS:
            return segs_sorted   # already fine, skip work
        result: list = []
        prev_bin = -2
        for s in segs_sorted:
            b = int((s.start - time_min) / _lod_ns_per_px)
            if b != prev_bin:
                result.append(s)
                prev_bin = b
        return result

    # Task-view: start-time arrays + LOD summaries keyed by merge-key
    _seg_starts_mk:     Dict[str, list] = {}
    _seg_lod_mk:        Dict[str, list] = {}
    _seg_lod_starts_mk: Dict[str, list] = {}
    for _mk, _lst in segs_by_mk.items():
        _seg_starts_mk[_mk] = [s.start for s in _lst]
        _lod = _make_lod_summary(_lst)
        _seg_lod_mk[_mk]        = _lod
        _seg_lod_starts_mk[_mk] = [s.start for s in _lod]

    if progress_callback:
        progress_callback(80, "Building core LOD summaries…")
    if cancel_check and cancel_check():
        raise _ParseCancelledError()

    # Core-view: start-time arrays + LOD summaries for core summary rows
    _core_seg_starts:     Dict[str, list] = {}
    _core_seg_lod:        Dict[str, list] = {}
    _core_seg_lod_starts: Dict[str, list] = {}
    for _c in _core_names:
        _core_seg_starts[_c] = [s.start for s in _core_segs[_c]]
        _lod = _make_lod_summary(_core_segs[_c])
        _core_seg_lod[_c]        = _lod
        _core_seg_lod_starts[_c] = [s.start for s in _lod]

    if progress_callback:
        progress_callback(88, "Building per-task core LOD summaries…")
    if cancel_check and cancel_check():
        raise _ParseCancelledError()

    # Core-view: start-time arrays + LOD summaries for per-task sub-rows
    _core_task_starts:     Dict[str, dict] = {}
    _core_task_lod:        Dict[str, dict] = {}
    _core_task_lod_starts: Dict[str, dict] = {}
    for _c in _core_names:
        _core_task_starts[_c]     = {}
        _core_task_lod[_c]        = {}
        _core_task_lod_starts[_c] = {}
        for _tn, _tsegs in _core_task_segs[_c].items():
            _core_task_starts[_c][_tn] = [s.start for s in _tsegs]
            _lod = _make_lod_summary(_tsegs)
            _core_task_lod[_c][_tn]        = _lod
            _core_task_lod_starts[_c][_tn] = [s.start for s in _lod]

    # STI: start-time arrays for bisect clipping in builders
    _sti_starts_by_target: Dict[str, list] = {
        _ch: [e.time for e in _evs]
        for _ch, _evs in sti_by_target.items()
    }

    if progress_callback:
        progress_callback(95, "Finalising…")

    return BtfTrace(
        time_scale=time_scale,
        tasks=tasks,
        segments=segments,
        sti_events=sti_events,
        sti_channels=sti_channels,
        sti_events_by_target=dict(sti_by_target),
        time_min=time_min,
        time_max=time_max,
        meta=meta,
        seg_map_by_merge_key=dict(segs_by_mk),
        core_names=_core_names,
        core_segs=dict(_core_segs),
        core_task_order=_core_task_order,
        core_task_segs=_core_task_segs,
        task_repr=_mk_repr,
        # Phase 4 – 1M-event performance fields
        seg_start_by_merge_key=_seg_starts_mk,
        core_seg_starts=_core_seg_starts,
        core_task_seg_starts=dict(_core_task_starts),
        sti_starts_by_target=_sti_starts_by_target,
        seg_lod_ns_per_px=_lod_ns_per_px,
        seg_lod_by_merge_key=_seg_lod_mk,
        seg_lod_starts_by_merge_key=_seg_lod_starts_mk,
        core_seg_lod=_core_seg_lod,
        core_seg_lod_starts=_core_seg_lod_starts,
        core_task_seg_lod=dict(_core_task_lod),
        core_task_seg_lod_starts=dict(_core_task_lod_starts),
        task_create_times=_task_create_times,
    )

# ===========================================================================
# Timeline Widget
# ===========================================================================

# ---------------------------------------------------------------------------
# Internal widget constants
# All user-configurable values (fonts, layout, colours, cursors, LOD) are
# in the USER CONFIGURATION block at the top of this file.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Persistent hover-info popup  (replaces QToolTip which auto-hides on scroll)
# ---------------------------------------------------------------------------

class _InfoPopup(QLabel):
    """Frameless persistent info popup – shown on hover-enter, hidden on hover-leave."""

    _stylesheet_applied: bool = False

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setTextFormat(Qt.RichText)
        self.setMargin(7)
        # Stylesheet is deferred to first show() so that _get_fixed_font_family()
        # can resolve the actual system fixed font (requires a live QApplication
        # with fonts loaded).  Using only the resolved name avoids the ~100 ms
        # "Populating font family aliases" warning that Qt emits when a font
        # name in the CSS list doesn't exist on the current platform.

    def _ensure_stylesheet(self) -> None:
        if _InfoPopup._stylesheet_applied:
            return
        _InfoPopup._stylesheet_applied = True
        fam = _get_fixed_font_family()
        self.setStyleSheet(
            f"QLabel {{ background:#252526; color:#E0E0E0; "
            f"border:1px solid #666; border-radius:4px; "
            f"font-size:9pt; font-family:'{fam}',monospace; }}"
        )

    def show_at(self, screen_pos: QPoint, html: str) -> None:
        self._ensure_stylesheet()
        self.setText(html)
        self.adjustSize()
        # offset so the cursor does not cover the box
        self.move(screen_pos.x() + 16, screen_pos.y() + 8)
        self.show()
        self.raise_()

_info_popup: Optional[_InfoPopup] = None

def _get_popup() -> _InfoPopup:
    global _info_popup
    if _info_popup is None:
        _info_popup = _InfoPopup()
    return _info_popup

_GRID_STEPS = [
    1, 2, 5, 10, 20, 50, 100, 200, 500,
    1_000, 2_000, 5_000, 10_000, 20_000, 50_000,
    100_000, 200_000, 500_000,
    1_000_000, 5_000_000, 10_000_000,
]

# ---------------------------------------------------------------------------
# Color helpers
# (_PALETTE, _CORE_TINTS, _SPECIAL_COLORS and _STI_COLORS are defined in
#  the USER CONFIGURATION block near the top of this file.)
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=None)
def _task_color(task_raw: str) -> QColor:
    """Return a stable QColor for a task name.

    Color is keyed on the full raw name (including [core/id] prefix) so that
    two tasks with the same display name but different IDs get different colors.
    IDLE tasks always use grey shades, differentiated by their task_id.
    """
    core_id, tid, name = parse_task_name(task_raw)
    if re.match(r"^IDLE\d*$", name):
        # Use task_id to differentiate IDLE tasks across cores; fall back to
        # the number suffix in the name, then 0.
        if tid is not None:
            idx = tid
        else:
            try:
                idx = int(name[4:]) if name[4:] else 0
            except ValueError:
                idx = 0
        greys = [180, 160, 140, 120, 100, 80]
        v = greys[idx % len(greys)]
        return QColor(v, v, v)
    if name in _SPECIAL_COLORS:
        return _SPECIAL_COLORS[name]
    # Hash on merge key (task_id + name, ignoring core_id) so the same logical
    # task always gets the same colour regardless of which core it ran on.
    idx = hash(task_merge_key(task_raw)) % len(_PALETTE)
    return QColor(_PALETTE[idx])

def _blend_core_tint(base: QColor, core: str) -> QColor:
    tint = _CORE_TINTS.get(core, _CORE_TINTS["Core_?"])
    r = int(base.red()   * (1 - tint.alphaF()) + tint.red()   * tint.alphaF())
    g = int(base.green() * (1 - tint.alphaF()) + tint.green() * tint.alphaF())
    b = int(base.blue()  * (1 - tint.alphaF()) + tint.blue()  * tint.alphaF())
    return QColor(r, g, b)

@functools.lru_cache(maxsize=None)
def _blended_color(task_raw: str, core: str) -> QColor:
    """Cached blend of a task's base color with a core tint."""
    return _blend_core_tint(_task_color(task_raw), core)

@functools.lru_cache(maxsize=None)
def _task_brush(task_raw: str) -> QBrush:
    """Cached QBrush for a task's base color."""
    return QBrush(_task_color(task_raw))

@functools.lru_cache(maxsize=None)
def _task_pen_dark(task_raw: str) -> QPen:
    """Cached dark-border QPen for a task's base color."""
    return QPen(_task_color(task_raw).darker(130), 0.4)

@functools.lru_cache(maxsize=None)
def _blended_brush(task_raw: str, core: str) -> QBrush:
    """Cached QBrush for a task blended with a core tint."""
    return QBrush(_blended_color(task_raw, core))

@functools.lru_cache(maxsize=None)
def _blended_pen_dark(task_raw: str, core: str) -> QPen:
    """Cached dark-border QPen for a task blended with a core tint."""
    return QPen(_blended_color(task_raw, core).darker(130), 0.4)

# Palette dedicated to dynamically-assigned STI note colours (distinct from
# the task palette so task and STI markers never share the same hue).
# (_STI_COLORS base entries are in the USER CONFIGURATION block at the top.)
_STI_PALETTE = [
    "#FF6B6B", "#6BCB77", "#4D96FF", "#FFD93D",
    "#C77DFF", "#FF9A3C", "#00C9A7", "#F72585",
    "#48CAE4", "#E9C46A", "#A8DADC", "#E76F51",
    "#B7E4C7", "#CDB4DB", "#FFAFCC", "#BDE0FE",
]

# Dynamic STI color assignments (kept separate from the user-config _STI_COLORS).
_STI_DYNAMIC_COLORS: Dict[str, QColor] = {}

def _sti_color(note: str) -> QColor:
    """Return a stable color for a STI note, auto-assigning if unknown."""
    if note in _STI_COLORS:
        return _STI_COLORS[note]
    if note not in _STI_DYNAMIC_COLORS:
        idx = hash(note) % len(_STI_PALETTE)
        _STI_DYNAMIC_COLORS[note] = QColor(_STI_PALETTE[idx])
    return _STI_DYNAMIC_COLORS[note]

# ---------------------------------------------------------------------------
# Time-formatting helper
# ---------------------------------------------------------------------------

def _format_time(ns: int, time_scale: str = "ns") -> str:
    """Format a timestamp into a human-readable string."""
    if time_scale == "us":
        ns *= 1_000
    elif time_scale == "ms":
        ns *= 1_000_000
    if ns >= 1_000_000:
        return f"{ns / 1_000_000:.3f} ms"
    if ns >= 1_000:
        return f"{ns / 1_000:.3f} µs"
    return f"{ns} ns"

_monospace_font_cache: dict = {}

def _monospace_font(size: int, weight: int = QFont.Normal) -> QFont:
    """Return a cached monospace QFont using the system fixed font.

    Cached so the expensive QFontDatabase.systemFont() Qt bridge call is made
    only once per (size, weight) pair regardless of how many rebuilds happen.
    """
    key = (size, weight)
    f = _monospace_font_cache.get(key)
    if f is None:
        f = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        f.setPointSize(size)
        f.setWeight(weight)
        _monospace_font_cache[key] = f
    return f

# Resolved family name of the system fixed-pitch font, used in Qt stylesheets.
# Lazily initialised on first use so that import does not require a live
# QApplication (avoids crash when the module is imported in test harnesses).
_FIXED_FONT_FAMILY: Optional[str] = None

def _get_fixed_font_family() -> str:
    """Return the system fixed-pitch font family name, initialising lazily."""
    global _FIXED_FONT_FAMILY
    if _FIXED_FONT_FAMILY is None:
        _FIXED_FONT_FAMILY = QFontDatabase.systemFont(QFontDatabase.FixedFont).family()
    return _FIXED_FONT_FAMILY

def _lod_reduce(segs: list, time_min: int, px_per_ns: float,
                offset: float) -> list:
    """Drop segments that would render to the same pixel column as the previous.

    At coarse zoom levels (ns_per_px >> 1) thousands of segments are
    sub-pixel wide and stacked on top of each other.  Keeping only the first
    segment per pixel column reduces the rendered count by up to 30× at the
    default fit-to-width zoom with no visible quality loss.  Callers are
    responsible for passing segments pre-sorted by start time.
    """
    if len(segs) <= 1:
        return segs
    result: list = []
    prev_bin = -2
    for seg in segs:
        b = int(offset + (seg.start - time_min) * px_per_ns)
        if b != prev_bin:
            result.append(seg)
            prev_bin = b
    return result

def _visible_segs(segs: list, starts: list,
                  lod_segs: list, lod_starts: list,
                  lod_ns_per_px: float, cur_ns_per_px: float,
                  ns_lo: int, ns_hi: int,
                  time_min: int, px_per_ns: float, offset: float) -> list:
    """Return LOD-reduced, viewport-clipped segments for one timeline row/column.

    Two-path strategy for 1M-event performance:

    *Coarse path* (cur_ns_per_px >= lod_ns_per_px, i.e. zoomed out past the
    pre-built LOD summary resolution):
        Bisect-clip the pre-built LOD summary (at most _LOD_SUMMARY_BINS
        entries total) to the visible ns range, then run _lod_reduce on the
        small result.  Cost: O(log(_LOD_SUMMARY_BINS) + visible_summary).

    *Fine path* (more zoomed in than the LOD summary):
        Bisect-clip the raw sorted segment list to [ns_lo, ns_hi] first, then
        run _lod_reduce only on the viewport-visible subset.  Cost is
        O(log(N) + visible_segs) regardless of total segment count.

    Both paths eliminate the O(N_total_segs) worst-case that occurs when
    _lod_reduce is called on the un-clipped full segment list.
    """
    if not segs:
        return segs

    if cur_ns_per_px >= lod_ns_per_px and lod_segs:
        # Coarse path: use pre-built LOD summary
        if lod_starts:
            lo = max(0, bisect_left(lod_starts, ns_lo) - 1)
            hi = min(len(lod_segs), bisect_right(lod_starts, ns_hi) + 1)
            clipped = lod_segs[lo:hi]
        else:
            clipped = lod_segs
    else:
        # Fine path: clip raw segment list to viewport time range
        if starts:
            lo = max(0, bisect_left(starts, ns_lo) - 1)
            hi = min(len(segs), bisect_right(starts, ns_hi) + 1)
            clipped = segs[lo:hi]
        else:
            clipped = segs

    return _lod_reduce(clipped, time_min, px_per_ns, offset)

def _nice_grid_step(ns_per_px: float, target_px: float = 100.0) -> int:
    """Return a 'nice' grid step (in ns) so that one step ≈ target_px pixels."""
    ideal_ns = ns_per_px * target_px
    best = _GRID_STEPS[0]
    for step in _GRID_STEPS:
        if step >= ideal_ns:
            best = step
            break
        best = step
    return best

# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------

class TimelineScene(QGraphicsScene):
    """Manages the full timeline and renders it as QGraphicsItems.

    The scene is stateless between rebuilds: every zoom or orientation change
    calls rebuild() which calls one of four builder methods:

        _build_horizontal       – task view, horizontal (time on X axis)
        _build_vertical         – task view, vertical   (time on Y axis)
        _build_horizontal_core  – core view, horizontal
        _build_vertical_core    – core view, vertical

    Because there is no incremental update, the scene can handle 1M+ events
    without housekeeping overhead; the cost is paid only when zooming.
    Paint performance is recovered via the 3-tier LOD system in _BatchRowItem.
    """

    scene_rebuilt    = pyqtSignal()          # emitted after every rebuild()
    highlight_changed = pyqtSignal(object, bool) # (task_name_or_None, locked)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Disable Qt's BSP spatial index.  The default BSP index updates on
        # every addItem() / removeItem() / clear() call which dominates rebuild
        # time when the scene is torn down and re-created on each scroll/zoom.
        # Hit-testing is O(n_items) with NoIndex; that is fine because a
        # culled rebuild only materialises ~30–70 items at a time.
        self.setItemIndexMethod(QGraphicsScene.NoIndex)
        # -- Trace data --------------------------------------------------
        self._trace: Optional[BtfTrace] = None
        # -- Zoom / orientation ------------------------------------------
        self._horizontal = True
        self._ns_per_px     = NS_PER_PX_DEFAULT
        self._ns_per_px_fit = float('inf')   # zoom-out limit: ns/px at fit-to-view
        # -- View state --------------------------------------------------
        self._show_sti    = True
        self._show_grid   = True
        self._view_mode   = "task"       # "task" or "core"
        self._core_expanded: Dict[str, bool] = {}   # True = expanded (default)
        self._font_size: int = _FONT_SIZE            # label font size (pt)
        self._label_width: int = LABEL_WIDTH            # resizable label-column width (px)
        # -- Viewport time bounds (updated at each rebuild for segment clipping) --
        # Set to None initially; _update_viewport_bounds() fills them from the
        # attached QGraphicsView, or falls back to the full trace time range.
        self._vp_ns_lo: int = 0
        self._vp_ns_hi: int = 0
        # When zoom_to_range() calls rebuild(), the view hasn't scrolled to
        # the new position yet, so the viewport-based ns computation would
        # cover the wrong part of the trace.  zoom_to_range() sets this hint
        # to the selected [ns_lo, ns_hi] so _update_viewport_bounds() uses
        # it instead of deriving the range from the stale scroll position.
        self._ns_range_hint: Optional[tuple] = None
        # When a rebuild is triggered by an operation that will reposition the
        # view (fit, load, orientation switch, …), the scroll position at the
        # time _update_viewport_bounds() runs is stale.  Setting this flag
        # makes _update_viewport_bounds() skip orth culling for that one
        # rebuild, ensuring all rows/columns are built.
        self._skip_orth_culling: bool = False
        # Viewport orthogonal bounds (row Y for horizontal view, column X for
        # vertical view).  Initialised to ±∞ so all rows are built on the
        # first rebuild before a live view is attached.
        self._vp_scene_orth_lo: float = -1e18
        self._vp_scene_orth_hi: float = +1e18
        # -- Frozen label-column items -----------------------------------
        # List of (item, orig_x_offset); repositioned on every scroll so
        # the label column stays pinned to the left edge of the viewport.
        self._frozen_items: List[tuple] = []
        # -- Frozen top-row (ruler + TICK band) items --------------------
        # List of (item, orig_y_offset); repositioned on vertical scroll so
        # the time-scale ruler stays pinned to the top edge of the viewport.
        self._frozen_top_items: List[tuple] = []
        # -- Cursor overlay ----------------------------------------------
        # Stored as ns timestamps; drawn as colored dash-lines above everything.
        self._cursor_times: List[int] = []
        self._cursor_items: list = []    # live QGraphicsItems for cursors
        # -- Task highlight state ----------------------------------------
        self._locked_task:  Optional[str] = None   # click-locked task (persistent)
        self._hovered_task: Optional[str] = None   # hover task (transient)
        # task_key → [(QRectF, QColor)] – populated by builders, used for hover overlays
        self._task_row_rects: Dict[str, list] = {}
        self._hover_overlay_items: list = []   # lightweight overlay items (no rebuild)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_trace(self, trace: BtfTrace, viewport_width: int = 1200) -> None:
        self._trace = trace
        time_span = max(trace.time_max - trace.time_min, 1)
        avail = max(viewport_width - self._label_width, 100)
        self._ns_per_px = time_span / avail
        self._ns_per_px_fit = self._ns_per_px   # record fit-to-view limit
        # Do NOT set _skip_orth_culling here: the viewport bounds are valid
        # (window is visible) and orth culling keeps the initial build to
        # O(visible_rows) instead of O(all_rows), preventing a UI freeze
        # when loading large traces (e.g. 128 cores × 1000 tasks).
        self.rebuild()

    def set_horizontal(self, horizontal: bool) -> None:
        self._horizontal = horizontal
        self._skip_orth_culling = True
        self.rebuild()

    def set_show_sti(self, show: bool) -> None:
        self._show_sti = show
        self.rebuild()

    def set_show_grid(self, show: bool) -> None:
        self._show_grid = show
        self.rebuild()

    def set_view_mode(self, mode: str) -> None:
        """Switch between 'task' (one row per task) and 'core' (one row per CPU core)."""
        self._view_mode = mode
        # Do NOT set _skip_orth_culling here: both task and core views use the
        # same Y-axis row layout, so the existing viewport orth bounds are valid.
        self.rebuild()

    def toggle_core(self, core_name: str) -> None:
        """Expand or collapse a core's task sub-rows in the core view."""
        self._core_expanded[core_name] = not self._core_expanded.get(core_name, True)
        self.rebuild()

    def set_all_cores_expanded(self, expanded: bool) -> None:
        """Expand or collapse every core at once in the core view."""
        if self._trace is None:
            return
        for c in self._trace.core_names:
            self._core_expanded[c] = expanded
        self.rebuild()

    @property
    def ns_per_px(self) -> float:
        return self._ns_per_px

    @ns_per_px.setter
    def ns_per_px(self, v: float) -> None:
        self._ns_per_px = max(v, NS_PER_PX_DEFAULT)
        self.rebuild()

    def set_font_size(self, size: int) -> None:
        """Change label font size (pt) and rebuild."""
        self._font_size = max(6, min(size, 24))
        self.rebuild()

    def set_label_width(self, width: int) -> None:
        """Change the Task / TaskID column width (px) and rebuild."""
        self._label_width = max(60, min(width, 600))
        self.rebuild()

    def zoom(self, factor: float, center_ns: Optional[int] = None) -> None:
        new_val = self._ns_per_px / factor
        # Clamp: don't zoom in past NS_PER_PX_DEFAULT or
        # zoom out past fit-to-view level.
        new_val = max(NS_PER_PX_DEFAULT, min(new_val, self._ns_per_px_fit))
        if new_val == self._ns_per_px:
            return  # already at limit – skip expensive rebuild
        self._ns_per_px = new_val
        self.rebuild()

    def fit_to_width(self, viewport_width: int) -> None:
        if self._trace is None:
            return
        time_span = max(self._trace.time_max - self._trace.time_min, 1)
        avail = max(viewport_width - self._label_width, 100)
        self._ns_per_px = time_span / avail
        self._ns_per_px_fit = self._ns_per_px   # update fit-to-view limit
        self.rebuild()

    # ------------------------------------------------------------------
    # Cursor API
    # ------------------------------------------------------------------

    def scene_to_ns(self, coord: float) -> int:
        """Convert a scene X (horizontal) or Y (vertical) coord to ns."""
        if self._trace is None:
            return 0
        ns = int((coord - self._label_width) * self._ns_per_px) + self._trace.time_min
        return max(self._trace.time_min, min(self._trace.time_max, ns))

    def ns_to_scene_coord(self, ns: int) -> float:
        """Convert a timestamp to the scene X (horizontal) or Y (vertical) coordinate."""
        return self._label_width + self._ns_to_px(ns)

    def add_cursor(self, ns: int) -> None:
        """Add a cursor at timestamp *ns*. Oldest is evicted when > MAX_CURSORS."""
        self._cursor_times.append(ns)
        if len(self._cursor_times) > MAX_CURSORS:
            self._cursor_times.pop(0)
        self._draw_cursors()

    def remove_nearest_cursor(self, ns: int) -> None:
        """Remove the cursor closest to *ns*."""
        if not self._cursor_times:
            return
        nearest = min(self._cursor_times, key=lambda t: abs(t - ns))
        self._cursor_times.remove(nearest)
        self._draw_cursors()

    def clear_cursors(self) -> None:
        self._cursor_times.clear()
        self._draw_cursors()

    def zoom_to_range(self, ns_a: int, ns_b: int, viewport_px: int) -> None:
        """Zoom so that the range [ns_a, ns_b] fills the available timeline width."""
        span = abs(ns_b - ns_a)
        if span < 1:
            return
        avail = max(viewport_px - self._label_width, 100)
        self._ns_per_px = max(span / avail, NS_PER_PX_DEFAULT)
        # Supply an explicit ns range so _update_viewport_bounds() inside
        # rebuild() clips to the target region rather than deriving a wrong
        # range from the not-yet-scrolled viewport position.
        self._ns_range_hint = (min(ns_a, ns_b), max(ns_a, ns_b))
        self.rebuild()

    def _apply_hover_overlay(self, task_name: str) -> None:
        """Add translucent highlight rects for *task_name* without rebuilding the scene."""
        for rect, tc in self._task_row_rects.get(task_name, []):
            hl_bg = QColor(tc.red(), tc.green(), tc.blue(), 35)
            item = self.addRect(rect, QPen(tc.lighter(160), 1.0), QBrush(hl_bg))
            item.setZValue(0.9)
            self._hover_overlay_items.append(item)

    def _remove_hover_overlay(self) -> None:
        """Remove all current hover overlay items from the scene."""
        for item in self._hover_overlay_items:
            self.removeItem(item)
        self._hover_overlay_items = []

    def set_highlighted_task(self, task_name: Optional[str],
                             locked: bool = False) -> None:
        """Set or clear the highlighted task on the timeline.

        - ``task_name=None`` always clears the highlight and the lock.
        - ``locked=True``  pins the highlight (triggered by a click); full rebuild.
        - ``locked=False`` is a transient hover highlight; uses a lightweight
          overlay rect so the scene is NOT rebuilt (fast path).
        """
        if task_name is None:
            if self._locked_task is None and self._hovered_task is None:
                return
            self._remove_hover_overlay()
            self._locked_task  = None
            self._hovered_task = None
            self.highlight_changed.emit(None, False)
            self.rebuild()
        elif locked:
            self._remove_hover_overlay()
            self._locked_task  = task_name
            self._hovered_task = None
            self.highlight_changed.emit(task_name, True)
            self.rebuild()
        else:
            # Hover: update overlay only – no rebuild
            self._remove_hover_overlay()
            self._hovered_task = task_name
            self._apply_hover_overlay(task_name)
            self.highlight_changed.emit(self._locked_task,
                                        self._locked_task is not None)

    def clear_hover(self) -> None:
        """Clear the transient hover highlight without rebuilding the scene."""
        if self._hovered_task is None:
            return
        self._hovered_task = None
        self._remove_hover_overlay()
        self.highlight_changed.emit(self._locked_task,
                                    self._locked_task is not None)

    def cursor_times(self) -> List[int]:
        return list(self._cursor_times)

    # ------------------------------------------------------------------
    # Draw cursor overlay
    # ------------------------------------------------------------------

    def _draw_cursors(self) -> None:
        for item in self._cursor_items:
            self.removeItem(item)
        self._cursor_items.clear()

        if self._trace is None or not self._cursor_times:
            return

        scene_r = self.sceneRect()
        font     = _monospace_font(self._font_size)
        font_big = _monospace_font(self._font_size + 1, QFont.Bold)
        fm_bold  = QFontMetrics(font_big)

        sorted_cursors = sorted(enumerate(self._cursor_times), key=lambda x: x[1])

        for order, (orig_idx, ns) in enumerate(sorted_cursors):
            color = QColor(_CURSOR_COLORS[orig_idx % MAX_CURSORS])
            pen   = QPen(color, 1.2, Qt.DashLine)

            if self._horizontal:
                x = self._label_width + self._ns_to_px(ns)
                line = QGraphicsLineItem(x, 0, x, scene_r.height())
                line.setPen(pen)
                line.setZValue(30)
                self.addItem(line)
                self._cursor_items.append(line)

                t_str = _format_time(ns, self._trace.time_scale)
                lbl = self.addSimpleText(f"C{orig_idx+1}: {t_str}", font_big)
                lbl.setBrush(QBrush(color))
                lbl.setZValue(32)
                tw = fm_bold.horizontalAdvance(lbl.text())
                th = fm_bold.height()
                lbl_x = min(x + 3, scene_r.width() - tw - 4)
                lbl_y = 2 + (orig_idx + 1) * (th + 2)
                bg = self.addRect(
                    QRectF(lbl_x - 2, lbl_y - 1, tw + 4, th + 2),
                    QPen(Qt.NoPen),
                    QBrush(QColor(0, 0, 0, 180)),
                )
                bg.setZValue(31)
                lbl.setPos(lbl_x, lbl_y)
                self._cursor_items.extend([bg, lbl])

                if order > 0:
                    prev_ns = sorted_cursors[order - 1][1]
                    delta   = abs(ns - prev_ns)
                    d_str   = f"Δ {_format_time(delta, self._trace.time_scale)}"
                    mid_x   = self._label_width + self._ns_to_px((ns + prev_ns) // 2)
                    d_lbl   = self.addSimpleText(d_str, font)
                    d_w     = QFontMetrics(font).horizontalAdvance(d_str)
                    d_lbl.setBrush(QBrush(QColor("#FFFFFF")))
                    d_lbl.setZValue(32)
                    bg_rect = self.addRect(
                        QRectF(mid_x - d_w / 2 - 3, RULER_HEIGHT + 4,
                               d_w + 6, QFontMetrics(font).height() + 4),
                        QPen(Qt.NoPen),
                        QBrush(QColor(0, 0, 0, 160)),
                    )
                    bg_rect.setZValue(31)
                    d_lbl.setPos(mid_x - d_w / 2, RULER_HEIGHT + 6)
                    self._cursor_items.extend([bg_rect, d_lbl])

            else:  # vertical mode
                label_row_h = self._label_width
                y = label_row_h + self._ns_to_px(ns)
                line = QGraphicsLineItem(0, y, scene_r.width(), y)
                line.setPen(pen)
                line.setZValue(30)
                self.addItem(line)
                self._cursor_items.append(line)

                t_str = _format_time(ns, self._trace.time_scale)
                lbl = self.addSimpleText(f"C{orig_idx+1}: {t_str}", font_big)
                lbl.setBrush(QBrush(color))
                lbl.setZValue(32)
                tw = fm_bold.horizontalAdvance(lbl.text())
                th = fm_bold.height()
                lbl_x = 2
                lbl_y = y + 2 + (orig_idx + 1) * (th + 2)
                bg = self.addRect(
                    QRectF(lbl_x - 2, lbl_y - 1, tw + 4, th + 2),
                    QPen(Qt.NoPen),
                    QBrush(QColor(0, 0, 0, 180)),
                )
                bg.setZValue(31)
                lbl.setPos(lbl_x, lbl_y)
                self._cursor_items.extend([bg, lbl])

                if order > 0:
                    prev_ns = sorted_cursors[order - 1][1]
                    delta   = abs(ns - prev_ns)
                    d_str   = f"Δ {_format_time(delta, self._trace.time_scale)}"
                    mid_y   = label_row_h + self._ns_to_px((ns + prev_ns) // 2)
                    d_lbl   = self.addSimpleText(d_str, font)
                    dh      = QFontMetrics(font).height()
                    d_lbl.setBrush(QBrush(QColor("#FFFFFF")))
                    d_lbl.setZValue(32)
                    bg_rect = self.addRect(
                        QRectF(RULER_WIDTH + 4, mid_y - dh / 2 - 2,
                               QFontMetrics(font).horizontalAdvance(d_str) + 6, dh + 4),
                        QPen(Qt.NoPen), QBrush(QColor(0, 0, 0, 160))
                    )
                    bg_rect.setZValue(31)
                    d_lbl.setPos(RULER_WIDTH + 7, mid_y - dh / 2)
                    self._cursor_items.extend([bg_rect, d_lbl])

    # ------------------------------------------------------------------
    # Build / rebuild
    # ------------------------------------------------------------------

    def _update_viewport_bounds(self) -> None:
        """Compute the visible time range and store it in _vp_ns_lo / _vp_ns_hi.

        Called at the start of every rebuild() so the four builder methods can
        clip segment lists to roughly the visible ns range using bisect, reducing
        the number of segments processed from O(N_total) to O(N_visible).

        A 10 % margin is added to each side so fast scrolling never reveals
        blank edges before the next debounced rebuild fires.
        """
        if self._trace is None:
            self._skip_orth_culling = False   # don't let a pre-load mode switch poison the first rebuild
            self._vp_ns_lo = 0
            self._vp_ns_hi = 0
            self._vp_scene_orth_lo = -1e18
            self._vp_scene_orth_hi = +1e18
            return

        t_min = self._trace.time_min
        t_max = self._trace.time_max

        views = self.views()
        if not views:
            # No attached view yet (e.g. during unit tests) – use full range.
            self._vp_ns_lo = t_min
            self._vp_ns_hi = t_max
            self._vp_scene_orth_lo = -1e18
            self._vp_scene_orth_hi = +1e18
            return

        view = views[0]
        vp_rect = view.viewport().rect()

        if self._horizontal:
            lo_coord = view.mapToScene(vp_rect.topLeft()).x()
            hi_coord = view.mapToScene(vp_rect.topRight()).x()
        else:
            lo_coord = view.mapToScene(vp_rect.topLeft()).y()
            hi_coord = view.mapToScene(vp_rect.bottomLeft()).y()

        lw = self._label_width
        ns_lo = t_min + int((lo_coord - lw) * self._ns_per_px)
        ns_hi = t_min + int((hi_coord - lw) * self._ns_per_px)

        # If zoom_to_range() supplied an explicit hint, use it so the rebuild
        # clips to the correct (target) region even though the viewport scroll
        # position hasn't been updated yet.  Consume the hint immediately.
        if self._ns_range_hint is not None:
            ns_lo, ns_hi = self._ns_range_hint
            self._ns_range_hint = None

        # 150 % margin on each side so the user can scroll ~1.5 viewport
        # widths before hitting blank content.  bisect keeps the cost
        # proportional to the number of visible segments, not the total.
        margin = max(1, int((ns_hi - ns_lo) * 1.5))
        self._vp_ns_lo = max(t_min, ns_lo - margin)
        self._vp_ns_hi = min(t_max, ns_hi + margin)

        # Orthogonal axis bounds for row/column culling during rebuild.
        # Guard: if the viewport rect has no size yet (widget not shown),
        # keep ±∞ so the first rebuild always builds all rows.
        if self._skip_orth_culling or vp_rect.width() <= 1 or vp_rect.height() <= 1:
            self._skip_orth_culling = False
            self._vp_scene_orth_lo = -1e18
            self._vp_scene_orth_hi = +1e18
        else:
            # Buffer of 20 rows/cols: wide enough that typical fast scrolling
            # doesn't exhaust the pre-built region before the next rebuild fires.
            _ORTH_BUF = (ROW_HEIGHT + ROW_GAP) * 20
            if self._horizontal:
                vy_lo = view.mapToScene(vp_rect.topLeft()).y()
                vy_hi = view.mapToScene(vp_rect.bottomLeft()).y()
            else:
                vy_lo = view.mapToScene(vp_rect.topLeft()).x()
                vy_hi = view.mapToScene(vp_rect.topRight()).x()
            self._vp_scene_orth_lo = vy_lo - _ORTH_BUF
            self._vp_scene_orth_hi = vy_hi + _ORTH_BUF

    def rebuild(self) -> None:
        self._update_viewport_bounds()
        self.clear()
        self._cursor_items = []
        self._frozen_items = []
        self._frozen_top_items = []
        self._task_row_rects = {}
        self._hover_overlay_items = []   # clear() removed them from the scene
        if self._trace is None:
            return
        if self._view_mode == "core":
            if self._horizontal:
                self._build_horizontal_core()
            else:
                self._build_vertical_core()
        else:
            if self._horizontal:
                self._build_horizontal()
            else:
                self._build_vertical()
        # Re-add hover overlay after rebuild (e.g. zoom while hovering)
        if self._hovered_task is not None:
            self._apply_hover_overlay(self._hovered_task)
        self._draw_cursors()
        self.scene_rebuilt.emit()

    def _ns_to_px(self, ns: int) -> float:
        return (ns - self._trace.time_min) / self._ns_per_px

    def _build_horizontal(self) -> None:
        trace = self._trace
        font = _monospace_font(self._font_size)
        fm   = QFontMetrics(font)

        # trace.tasks is a sorted list of merge-keys.  task_repr maps
        # each merge-key to its representative raw name, which is needed
        # to resolve display names and colours.
        task_rows = trace.tasks
        sti_rows  = trace.sti_channels if self._show_sti else []
        n_task = len(task_rows)
        n_sti  = len(sti_rows)
        total_rows = n_task + n_sti
        if total_rows == 0:
            return

        time_span  = trace.time_max - trace.time_min
        timeline_w = time_span / self._ns_per_px
        total_h = RULER_HEIGHT + total_rows * (ROW_HEIGHT + ROW_GAP)
        total_w = self._label_width + timeline_w
        self.setSceneRect(0, 0, total_w, total_h)

        # --- Background & ruler ------------------------------------------
        _ruler_bg = self.addRect(QRectF(0, 0, total_w, RULER_HEIGHT),
                                 QPen(Qt.NoPen), QBrush(QColor("#2B2B2B")))
        _ruler_bg.setZValue(10)   # above task rows (z=0-2) when frozen at top
        self._frozen_top_items.append((_ruler_bg, 0))
        _lbg = self.addRect(QRectF(0, 0, self._label_width, total_h),
                            QPen(Qt.NoPen), QBrush(QColor("#1E1E1E")))
        _lbg.setZValue(35)   # must be above cursor lines (z=30-32)
        self._frozen_items.append((_lbg, 0))

        # Grid-only ruler: grid lines stay at absolute scene positions (not frozen).
        _ruler_grid = _RulerItem(trace, self._ns_per_px, total_w, total_h,
                                   font, trace.time_scale, self._show_grid,
                                   horiz=True, axis_offset=self._label_width,
                                   draw_header=False)
        _ruler_grid.setZValue(0.5)
        self.addItem(_ruler_grid)
        # Header-only ruler: tick marks + labels, frozen to the top edge.
        _ruler_hdr = _RulerItem(trace, self._ns_per_px, total_w, total_h,
                                 font, trace.time_scale, show_grid=False,
                                 horiz=True, axis_offset=self._label_width,
                                 draw_grid=False)
        _ruler_hdr.setZValue(11)
        self.addItem(_ruler_hdr)
        self._frozen_top_items.append((_ruler_hdr, 0))

        # --- TICK band on ruler (bottom strip) ---------------------------
        _htmk   = task_merge_key("TICK")
        _htsegs = trace.seg_map_by_merge_key.get(_htmk, [])
        if _htsegs:
            _ht_lod_ns   = trace.seg_lod_ns_per_px
            _ht_npp      = self._ns_per_px
            _ht_vlo      = self._vp_ns_lo
            _ht_vhi      = self._vp_ns_hi
            _ht_tmin     = trace.time_min
            _ht_ppns     = 1.0 / _ht_npp
            _ht_lw       = self._label_width
            _ht_y        = RULER_HEIGHT - 10
            _ht_h        = 8
            _ht_data: list = []
            _ht_xs:   list = []
            for _i, _seg in enumerate(_visible_segs(
                    _htsegs,
                    trace.seg_start_by_merge_key.get(_htmk, []),
                    trace.seg_lod_by_merge_key.get(_htmk, []),
                    trace.seg_lod_starts_by_merge_key.get(_htmk, []),
                    _ht_lod_ns, _ht_npp, _ht_vlo, _ht_vhi,
                    _ht_tmin, _ht_ppns, _ht_lw)):
                _x1 = _ht_lw + (_seg.start - _ht_tmin) * _ht_ppns
                _x2 = _ht_lw + (_seg.end   - _ht_tmin) * _ht_ppns
                _w  = _x2 - _x1 if _x2 - _x1 >= MIN_SEG_WIDTH else MIN_SEG_WIDTH
                _ht_data.append((
                    QRectF(_x1, _ht_y + 1, _w, _ht_h - 2),
                    _task_brush(_seg.task), _task_pen_dark(_seg.task), _seg,
                ))
                _ht_xs.append((_x1, _x1 + _w, _i))
            _ht_batch = _BatchRowItem(
                QRectF(_ht_lw, _ht_y, timeline_w, _ht_h),
                _ht_data, trace.time_scale, xs=_ht_xs,
                time_min=trace.time_min)
            _ht_batch.setZValue(12)   # above frozen ruler_bg+header
            self.addItem(_ht_batch)
            self._frozen_top_items.append((_ht_batch, 0))

        # Shared colors/pens/brushes hoisted out of loops
        _bg_even   = QBrush(QColor("#252526"))
        _bg_odd    = QBrush(QColor("#2D2D2D"))
        _sep_pen   = QPen(QColor("#333333"), 0.5)
        _lbl_color = QColor("#D4D4D4")
        _seg_white = QBrush(QColor("#FFFFFF"))
        _pen_hl    = QPen(QColor("#FFFFFF"), 1.5)

        # Use pre-built sorted segment map from the trace (avoids O(n_seg) rebuild work)
        seg_map = trace.seg_map_by_merge_key

        # --- Task rows ---------------------------------------------------
        # Compute first/last visible row indices from the cached orth bounds.
        # This avoids iterating all n_task rows just to skip ~95 % of them.
        _row_stride   = ROW_HEIGHT + ROW_GAP
        _first_vis    = max(0, int((self._vp_scene_orth_lo - RULER_HEIGHT) // _row_stride))
        _last_vis     = min(n_task - 1, int((self._vp_scene_orth_hi - RULER_HEIGHT) // _row_stride) + 1)
        _time_min     = trace.time_min
        _px_per_ns    = 1.0 / self._ns_per_px
        lw            = self._label_width
        _vp_ns_lo     = self._vp_ns_lo
        _vp_ns_hi     = self._vp_ns_hi
        lod_ns_per_px = trace.seg_lod_ns_per_px
        _ns_per_px    = self._ns_per_px
        for row_idx in range(_first_vis, _last_vis + 1):
            task  = task_rows[row_idx]
            raw   = trace.task_repr.get(task, task)
            y_top = RULER_HEIGHT + row_idx * _row_stride
            y_ctr = y_top + ROW_HEIGHT / 2
            is_hl = (task == self._locked_task)
            disp      = task_display_name(raw)
            row_color = _task_color(raw)
            self._task_row_rects[task] = [(QRectF(lw, y_top, timeline_w, ROW_HEIGHT), row_color)]

            self.addRect(QRectF(lw, y_top, timeline_w, ROW_HEIGHT),
                         QPen(Qt.NoPen),
                         _bg_even if row_idx % 2 == 0 else _bg_odd).setZValue(0)
            if is_hl:
                hl_bg = QColor(row_color.red(), row_color.green(), row_color.blue(), 35)
                hl_border = QPen(row_color.lighter(160), 1.0)
                self.addRect(QRectF(lw, y_top, timeline_w, ROW_HEIGHT),
                             hl_border, QBrush(hl_bg)).setZValue(0.9)
            self.addLine(0, y_top + ROW_HEIGHT + ROW_GAP - 1,
                         total_w, y_top + ROW_HEIGHT + ROW_GAP - 1,
                         _sep_pen).setZValue(0.5)

            # Clickable label background
            lbl_bg = _TaskLabelItem(QRectF(0, y_top, lw, ROW_HEIGHT), task, self,
                                    tooltip_text=disp)
            lbl_bg.setZValue(36)
            self.addItem(lbl_bg)
            self._frozen_items.append((lbl_bg, 0))

            lbl_color = QColor("#FFD700") if is_hl else _lbl_color
            lbl_font  = _monospace_font(self._font_size, QFont.Bold) if is_hl else font
            _lbl_avail_w = max(0, lw - 4 - 4)   # left=4, right margin=4
            _lbl_elided  = QFontMetrics(lbl_font).elidedText(
                disp, Qt.ElideRight, _lbl_avail_w)
            lbl = self.addSimpleText(_lbl_elided, lbl_font)
            lbl.setBrush(QBrush(lbl_color))
            lbl.setPos(4, y_ctr - fm.height() / 2)
            lbl.setZValue(37)
            self._frozen_items.append((lbl, 4))

            pen_hl     = _pen_hl
            seg_data: list = []
            xs:      list = []
            for i_s, seg in enumerate(_visible_segs(
                    seg_map.get(task, []),
                    trace.seg_start_by_merge_key.get(task, []),
                    trace.seg_lod_by_merge_key.get(task, []),
                    trace.seg_lod_starts_by_merge_key.get(task, []),
                    lod_ns_per_px, _ns_per_px, _vp_ns_lo, _vp_ns_hi,
                    _time_min, _px_per_ns, lw)):
                x1 = lw + (seg.start - _time_min) * _px_per_ns
                x2 = lw + (seg.end   - _time_min) * _px_per_ns
                w  = x2 - x1 if x2 - x1 >= MIN_SEG_WIDTH else MIN_SEG_WIDTH
                seg_data.append((
                    QRectF(x1, y_top + 1, w, ROW_HEIGHT - 2),
                    _blended_brush(seg.task, seg.core),
                    pen_hl if is_hl else _blended_pen_dark(seg.task, seg.core),
                    seg,
                ))
                xs.append((x1, x1 + w, i_s))
            batch = _BatchRowItem(
                QRectF(lw, y_top, timeline_w, ROW_HEIGHT),
                seg_data, trace.time_scale,
                label_font=font, label_fm=fm, label_text=disp,
                xs=xs, time_min=trace.time_min)
            batch.setZValue(1)
            self.addItem(batch)

            # Task-create marker: 1px vertical line at the creation timestamp
            _ct_h = trace.task_create_times.get(task)
            if _ct_h is not None:
                _cx = lw + (_ct_h - _time_min) * _px_per_ns
                _cl = self.addLine(_cx, y_top, _cx, y_top + ROW_HEIGHT,
                                   QPen(row_color, 1))
                _cl.setZValue(2.5)
        # One row per STI channel containing one _BatchStiItem with all
        # events for that channel, sorted by time (ascending scene_x).
        for sti_idx, channel in enumerate(sti_rows):
            row_idx = n_task + sti_idx
            y_top   = RULER_HEIGHT + row_idx * (ROW_HEIGHT + ROW_GAP)
            y_ctr   = y_top + ROW_HEIGHT / 2
            self.addRect(QRectF(lw, y_top, timeline_w, ROW_HEIGHT),
                         QPen(Qt.NoPen), QBrush(QColor("#1A1A2E"))).setZValue(0)
            lbl = self.addSimpleText(
                fm.elidedText(channel, Qt.ElideRight, max(0, lw - 4 - 4)), font)
            lbl.setBrush(QBrush(QColor("#88AABB")))
            lbl.setPos(4, y_ctr - fm.height() / 2)
            lbl.setZValue(37)
            self._frozen_items.append((lbl, 4))
            _sti_evs_h  = trace.sti_events_by_target.get(channel, [])
            _sti_stts_h = trace.sti_starts_by_target.get(channel, [])
            if _sti_stts_h:
                _slo = max(0, bisect_left(_sti_stts_h, _vp_ns_lo) - 1)
                _shi = min(len(_sti_evs_h), bisect_right(_sti_stts_h, _vp_ns_hi) + 1)
                _sti_evs_h = _sti_evs_h[_slo:_shi]
            _sti_markers = [
                (lw + (ev.time - _time_min) * _px_per_ns, _sti_color(ev.note), ev)
                for ev in _sti_evs_h
            ]
            _sti_item = _BatchStiItem(
                QRectF(lw, y_top, timeline_w, ROW_HEIGHT),
                _sti_markers, trace.time_scale, horizontal=True, axis=y_ctr,
                time_min=trace.time_min)
            _sti_item.setZValue(2)
            self.addItem(_sti_item)

        # --- Frozen label column header ----------------------------------
        # Drawn last so it sits on top of all other frozen items (z=38-39).
        _htmk_c = task_merge_key("TICK")
        _has_tick_h = bool(trace.seg_map_by_merge_key.get(_htmk_c, []))
        corner = self.addRect(QRectF(0, 0, lw, RULER_HEIGHT),
                              QPen(Qt.NoPen), QBrush(QColor("#1A1A1A")))
        corner.setZValue(38)
        _hdr_band_h = RULER_HEIGHT - (10 if _has_tick_h else 0)
        hdr = self.addSimpleText("Task / TaskID", font)
        hdr.setBrush(QBrush(QColor("#888888")))
        hdr.setPos(4, _hdr_band_h / 2 - fm.height() / 2)
        hdr.setZValue(39)
        self._frozen_items.append((corner, 0))
        self._frozen_items.append((hdr, 4))
        self._frozen_top_items.append((corner, 0))
        self._frozen_top_items.append((hdr, hdr.pos().y()))
        if _has_tick_h:
            _tick_hdr = self.addSimpleText("TICK", font)
            _tick_hdr.setBrush(QBrush(QColor("#E8C84A")))
            _tick_hdr.setPos(4, RULER_HEIGHT - 10 + (10 - fm.height()) / 2)
            _tick_hdr.setZValue(39)
            self._frozen_items.append((_tick_hdr, 4))
            self._frozen_top_items.append((_tick_hdr, _tick_hdr.pos().y()))

    def _build_vertical(self) -> None:
        trace = self._trace
        font = _monospace_font(self._font_size)
        fm   = QFontMetrics(font)

        # trace.tasks is a sorted list of merge-keys.  task_repr maps
        # each merge-key to its representative raw name.
        task_cols = trace.tasks
        sti_cols  = trace.sti_channels if self._show_sti else []
        n_task = len(task_cols)
        n_sti  = len(sti_cols)
        total_cols = n_task + n_sti
        if total_cols == 0:
            return

        col_w       = max(ROW_HEIGHT + ROW_GAP, 26)
        label_row_h = self._label_width
        time_span   = trace.time_max - trace.time_min
        timeline_h  = time_span / self._ns_per_px
        total_w     = col_w * total_cols + RULER_WIDTH
        total_h     = label_row_h + timeline_h
        self.setSceneRect(0, 0, total_w, total_h)

        # --- Ruler column (left side): frozen to left edge on X scroll ------
        _ruler_col_bg = self.addRect(QRectF(0, 0, RULER_WIDTH, total_h),
                                     QPen(Qt.NoPen), QBrush(QColor("#2B2B2B")))
        _ruler_col_bg.setZValue(35)  # above cursor lines (z=30-32)
        self._frozen_items.append((_ruler_col_bg, 0))

        # --- Label row (top): frozen to top edge on Y scroll ---------------
        _label_row_bg = self.addRect(QRectF(0, 0, total_w, label_row_h),
                                     QPen(Qt.NoPen), QBrush(QColor("#1E1E1E")))
        _label_row_bg.setZValue(10)
        self._frozen_top_items.append((_label_row_bg, 0))

        # Grid-only ruler: horizontal lines at absolute Y positions (not frozen).
        _ruler_grid = _RulerItem(trace, self._ns_per_px, total_w, total_h,
                                   font, trace.time_scale, self._show_grid,
                                   horiz=False, axis_offset=label_row_h,
                                   draw_header=False)
        _ruler_grid.setZValue(0.5)
        self.addItem(_ruler_grid)
        # Header-only ruler: tick marks + labels, frozen to left edge.
        _ruler_hdr = _RulerItem(trace, self._ns_per_px, total_w, total_h,
                                  font, trace.time_scale, show_grid=False,
                                  horiz=False, axis_offset=label_row_h,
                                  draw_grid=False)
        _ruler_hdr.setZValue(36)
        self.addItem(_ruler_hdr)
        self._frozen_items.append((_ruler_hdr, 0))

        # --- TICK band on ruler (right strip of ruler column) ------------
        _vtmk   = task_merge_key("TICK")
        _vtsegs = trace.seg_map_by_merge_key.get(_vtmk, [])
        _has_tick_v = bool(_vtsegs)
        if _has_tick_v:
            _vt_lod_ns   = trace.seg_lod_ns_per_px
            _vt_npp      = self._ns_per_px
            _vt_vlo      = self._vp_ns_lo
            _vt_vhi      = self._vp_ns_hi
            _vt_tmin     = trace.time_min
            _vt_ppns     = 1.0 / _vt_npp
            _vt_x        = RULER_WIDTH - 18
            _vt_w        = 14
            _vt_data: list = []
            _vt_xs:   list = []
            for _i, _seg in enumerate(_visible_segs(
                    _vtsegs,
                    trace.seg_start_by_merge_key.get(_vtmk, []),
                    trace.seg_lod_by_merge_key.get(_vtmk, []),
                    trace.seg_lod_starts_by_merge_key.get(_vtmk, []),
                    _vt_lod_ns, _vt_npp, _vt_vlo, _vt_vhi,
                    _vt_tmin, _vt_ppns, label_row_h)):
                _y1 = label_row_h + (_seg.start - _vt_tmin) * _vt_ppns
                _y2 = label_row_h + (_seg.end   - _vt_tmin) * _vt_ppns
                _h  = _y2 - _y1 if _y2 - _y1 >= MIN_SEG_WIDTH else MIN_SEG_WIDTH
                _vt_data.append((
                    QRectF(_vt_x + 1, _y1, _vt_w - 2, _h),
                    _task_brush(_seg.task), _task_pen_dark(_seg.task), _seg,
                ))
                _vt_xs.append((_y1, _y1 + _h, _i))
            _vt_batch = _BatchRowItem(
                QRectF(_vt_x, label_row_h, _vt_w, timeline_h),
                _vt_data, trace.time_scale, xs=_vt_xs,
                time_min=trace.time_min)
            _vt_batch.setZValue(37)   # above ruler header (z=36)
            self.addItem(_vt_batch)
            self._frozen_items.append((_vt_batch, 0))

        # Use pre-built sorted segment map from the trace (avoids O(n_seg) rebuild work)
        seg_map = trace.seg_map_by_merge_key

        # --- Task columns ------------------------------------------------
        _bg_even   = QBrush(QColor("#252526"))
        _bg_odd    = QBrush(QColor("#2D2D2D"))
        _lbl_color = QColor("#D4D4D4")
        _pen_hl_v  = QPen(QColor("#FFFFFF"), 1.5)
        _time_min  = trace.time_min
        _px_per_ns = 1.0 / self._ns_per_px
        _vp_ns_lo  = self._vp_ns_lo
        _vp_ns_hi  = self._vp_ns_hi
        lod_ns_per_px = trace.seg_lod_ns_per_px
        _ns_per_px = self._ns_per_px

        # Compute first/last visible col indices from the cached orth bounds.
        _first_vis_c = max(0, int((self._vp_scene_orth_lo - RULER_WIDTH) // col_w))
        _last_vis_c  = min(n_task - 1, int((self._vp_scene_orth_hi - RULER_WIDTH) // col_w) + 1)
        for col_idx in range(_first_vis_c, _last_vis_c + 1):
            task   = task_cols[col_idx]
            raw    = trace.task_repr.get(task, task)
            x_left = RULER_WIDTH + col_idx * col_w
            is_hl  = (task == self._locked_task)
            disp      = task_display_name(raw)
            col_color = _task_color(raw)
            self._task_row_rects[task] = [(QRectF(x_left, label_row_h, col_w, timeline_h), col_color)]

            self.addRect(QRectF(x_left, label_row_h, col_w, timeline_h),
                         QPen(Qt.NoPen),
                         _bg_even if col_idx % 2 == 0 else _bg_odd).setZValue(0)
            if is_hl:
                hl_bg = QColor(col_color.red(), col_color.green(), col_color.blue(), 35)
                self.addRect(QRectF(x_left, label_row_h, col_w, timeline_h),
                             QPen(col_color.lighter(160), 1.0), QBrush(hl_bg)).setZValue(0.9)

            # Clickable label area at the top of each column
            lbl_bg = _TaskLabelItem(QRectF(x_left, 0, col_w, label_row_h), task, self,
                                    tooltip_text=disp)
            lbl_bg.setZValue(36)
            self.addItem(lbl_bg)
            self._frozen_top_items.append((lbl_bg, 0))

            lbl_color = QColor("#FFD700") if is_hl else _lbl_color
            lbl_font  = _monospace_font(self._font_size, QFont.Bold) if is_hl else font
            _lbl_avail_v = max(0, label_row_h - 8)
            _lbl_disp_v  = QFontMetrics(lbl_font).elidedText(
                disp, Qt.ElideRight, _lbl_avail_v)
            lbl = self.addSimpleText(_lbl_disp_v, lbl_font)
            lbl.setBrush(QBrush(lbl_color))
            lbl.setRotation(-90)
            lbl.setPos(x_left + col_w / 2 - fm.height() / 2, label_row_h - 4)
            lbl.setZValue(37)
            self._frozen_top_items.append((lbl, lbl.pos().y()))

            pen_hl      = _pen_hl_v
            seg_data: list = []
            xs:      list = []
            for i_s, seg in enumerate(_visible_segs(
                    seg_map.get(task, []),
                    trace.seg_start_by_merge_key.get(task, []),
                    trace.seg_lod_by_merge_key.get(task, []),
                    trace.seg_lod_starts_by_merge_key.get(task, []),
                    lod_ns_per_px, _ns_per_px, _vp_ns_lo, _vp_ns_hi,
                    _time_min, _px_per_ns, label_row_h)):
                y1 = label_row_h + (seg.start - _time_min) * _px_per_ns
                y2 = label_row_h + (seg.end   - _time_min) * _px_per_ns
                h  = y2 - y1 if y2 - y1 >= MIN_SEG_WIDTH else MIN_SEG_WIDTH
                seg_data.append((
                    QRectF(x_left + 1, y1, col_w - 2, h),
                    _blended_brush(seg.task, seg.core),
                    pen_hl if is_hl else _blended_pen_dark(seg.task, seg.core),
                    seg,
                ))
                xs.append((y1, y1 + h, i_s))
            batch = _BatchRowItem(
                QRectF(x_left, label_row_h, col_w, timeline_h),
                seg_data, trace.time_scale,
                xs=xs, time_min=trace.time_min)
            batch.setZValue(1)
            self.addItem(batch)

            # Task-create marker: 1px horizontal line at the creation timestamp
            _ct_v = trace.task_create_times.get(task)
            if _ct_v is not None:
                _cy = label_row_h + (_ct_v - _time_min) * _px_per_ns
                _cl_v = self.addLine(x_left, _cy, x_left + col_w, _cy,
                                     QPen(col_color, 1))
                _cl_v.setZValue(2.5)

        # --- STI columns ------------------------------------------------
        for sti_idx, channel in enumerate(sti_cols):
            col_idx = n_task + sti_idx
            x_left  = RULER_WIDTH + col_idx * col_w
            x_ctr   = x_left + col_w / 2
            self.addRect(QRectF(x_left, label_row_h, col_w, timeline_h),
                         QPen(Qt.NoPen), QBrush(QColor("#1A1A2E"))).setZValue(0)
            lbl = self.addSimpleText(channel, font)
            lbl.setBrush(QBrush(QColor("#88AABB")))
            lbl.setRotation(-90)
            lbl.setPos(x_left + col_w / 2 - fm.height() / 2, label_row_h - 4)
            lbl.setZValue(37)
            self._frozen_top_items.append((lbl, lbl.pos().y()))
            _sti_evs_v  = trace.sti_events_by_target.get(channel, [])
            _sti_stts_v = trace.sti_starts_by_target.get(channel, [])
            if _sti_stts_v:
                _slo = max(0, bisect_left(_sti_stts_v, _vp_ns_lo) - 1)
                _shi = min(len(_sti_evs_v), bisect_right(_sti_stts_v, _vp_ns_hi) + 1)
                _sti_evs_v = _sti_evs_v[_slo:_shi]
            _sti_markers_v = [
                (label_row_h + (ev.time - _time_min) * _px_per_ns, _sti_color(ev.note), ev)
                for ev in _sti_evs_v
            ]
            _sti_item_v = _BatchStiItem(
                QRectF(x_left, label_row_h, col_w, timeline_h),
                _sti_markers_v, trace.time_scale, horizontal=False, axis=x_ctr,
                time_min=trace.time_min)
            _sti_item_v.setZValue(2)
            self.addItem(_sti_item_v)

        # --- Corner: ruler-column × label-row intersection ---------------
        _vtmk_c = task_merge_key("TICK")
        _has_tick_vc = bool(trace.seg_map_by_merge_key.get(_vtmk_c, []))
        _vt_corner_rect = self.addRect(QRectF(0, 0, RULER_WIDTH, label_row_h),
                                       QPen(Qt.NoPen), QBrush(QColor("#1A1A1A")))
        _vt_corner_rect.setZValue(40)   # above ruler (35-37) and label row (10-37)
        self._frozen_items.append((_vt_corner_rect, 0))
        self._frozen_top_items.append((_vt_corner_rect, 0))
        if _has_tick_vc:
            _tick_vlbl = self.addSimpleText("TICK", font)
            _tick_vlbl.setBrush(QBrush(QColor("#E8C84A")))
            _tick_vlbl.setRotation(-90)
            _vband_cx  = (RULER_WIDTH - 18) + 14 / 2
            _tick_vlbl.setPos(_vband_cx - fm.height() / 2, label_row_h - 4)
            _tick_vlbl.setZValue(41)
            self._frozen_items.append((_tick_vlbl, _tick_vlbl.pos().x()))
            self._frozen_top_items.append((_tick_vlbl, _tick_vlbl.pos().y()))

    # ------------------------------------------------------------------
    # Core view builders
    # ------------------------------------------------------------------

    def _build_horizontal_core(self) -> None:
        """Horizontal core view: expandable cores → per-task sub-rows."""
        trace   = self._trace
        font    = _monospace_font(self._font_size)
        font_sm = _monospace_font(max(6, self._font_size - 1))
        fm      = QFontMetrics(font)

        # Use pre-built core data cached at parse time (O(1), no segment iteration)
        core_names           = trace.core_names
        core_segs            = trace.core_segs
        core_tasks           = trace.core_task_order
        task_seg_map_by_core = trace.core_task_segs
        sti_rows             = trace.sti_channels if self._show_sti else []

        # TICK is a global event — shown as a sticky first row above all cores.
        _tick_mk   = task_merge_key("TICK")
        _tick_segs = trace.seg_map_by_merge_key.get(_tick_mk, [])
        _has_tick  = bool(_tick_segs)

        def _row_count(c: str) -> int:
            return 1 + (len(core_tasks[c]) if self._core_expanded.get(c, True) else 0)

        total_rows = sum(_row_count(c) for c in core_names) + len(sti_rows)
        if total_rows == 0:
            return

        time_span  = trace.time_max - trace.time_min
        timeline_w = time_span / self._ns_per_px
        total_h    = RULER_HEIGHT + total_rows * (ROW_HEIGHT + ROW_GAP)
        total_w    = self._label_width + timeline_w
        self.setSceneRect(0, 0, total_w, total_h)

        # --- Background & ruler ------------------------------------------
        _ruler_bg = self.addRect(QRectF(0, 0, total_w, RULER_HEIGHT),
                                 QPen(Qt.NoPen), QBrush(QColor("#2B2B2B")))
        _ruler_bg.setZValue(10)
        self._frozen_top_items.append((_ruler_bg, 0))
        _lbg = self.addRect(QRectF(0, 0, self._label_width, total_h),
                            QPen(Qt.NoPen), QBrush(QColor("#1E1E1E")))
        _lbg.setZValue(35)   # must be above cursor lines (z=30-32)
        self._frozen_items.append((_lbg, 0))

        # Grid-only ruler (not frozen — grid lines stay at their scene positions).
        _ruler_grid = _RulerItem(trace, self._ns_per_px, total_w, total_h,
                                   font, trace.time_scale, self._show_grid,
                                   horiz=True, axis_offset=self._label_width,
                                   draw_header=False)
        _ruler_grid.setZValue(0.5)
        self.addItem(_ruler_grid)
        # Header-only ruler (frozen by Y — always visible at viewport top).
        _ruler_hdr = _RulerItem(trace, self._ns_per_px, total_w, total_h,
                                 font, trace.time_scale, show_grid=False,
                                 horiz=True, axis_offset=self._label_width,
                                 draw_grid=False)
        _ruler_hdr.setZValue(11)
        self.addItem(_ruler_hdr)
        self._frozen_top_items.append((_ruler_hdr, 0))

        _time_min  = trace.time_min
        _px_per_ns = 1.0 / self._ns_per_px
        lw         = self._label_width
        _vp_ns_lo  = self._vp_ns_lo
        _vp_ns_hi  = self._vp_ns_hi
        lod_ns_per_px = trace.seg_lod_ns_per_px
        _ns_per_px = self._ns_per_px
        # Pre-built LOD/start-time references for core view clipping
        c_seg_starts  = trace.core_seg_starts
        _c_seg_lod    = trace.core_seg_lod
        c_seg_lod_starts = trace.core_seg_lod_starts
        ct_seg_starts = trace.core_task_seg_starts
        _ct_lod       = trace.core_task_seg_lod
        ct_lod_starts = trace.core_task_seg_lod_starts
        # --- TICK band: TICK segments overlaid on the bottom strip of the ruler ---
        if _has_tick:
            _tb_y = RULER_HEIGHT - 10   # y of TICK band within ruler (bottom 10 px)
            _tb_h = 8                   # height of TICK band
            _tick_seg_data: list = []
            _tick_xs:       list = []
            for i_s, seg in enumerate(_visible_segs(
                    _tick_segs,
                    trace.seg_start_by_merge_key.get(_tick_mk, []),
                    trace.seg_lod_by_merge_key.get(_tick_mk, []),
                    trace.seg_lod_starts_by_merge_key.get(_tick_mk, []),
                    lod_ns_per_px, _ns_per_px, _vp_ns_lo, _vp_ns_hi,
                    _time_min, _px_per_ns, lw)):
                x1 = lw + (seg.start - _time_min) * _px_per_ns
                x2 = lw + (seg.end   - _time_min) * _px_per_ns
                w  = x2 - x1 if x2 - x1 >= MIN_SEG_WIDTH else MIN_SEG_WIDTH
                _tick_seg_data.append((
                    QRectF(x1, _tb_y + 1, w, _tb_h - 2),
                    _task_brush(seg.task), _task_pen_dark(seg.task), seg,
                ))
                _tick_xs.append((x1, x1 + w, i_s))
            tick_batch = _BatchRowItem(
                QRectF(lw, _tb_y, timeline_w, _tb_h),
                _tick_seg_data, trace.time_scale,
                xs=_tick_xs, time_min=trace.time_min)
            tick_batch.setZValue(12)   # above frozen ruler_bg+header
            self.addItem(tick_batch)
            self._frozen_top_items.append((tick_batch, 0))

        row_idx = 0

        # --- Core rows ---------------------------------------------------
        # Each core gets one summary row (always visible) plus optional
        # per-task sub-rows that appear when the core is expanded.
        for core in core_names:
            expanded = self._core_expanded.get(core, True)
            tasks    = core_tasks[core]
            segs     = core_segs[core]
            dot_c    = QColor(_core_color(core))

            y_top = RULER_HEIGHT + row_idx * (ROW_HEIGHT + ROW_GAP)
            y_ctr = y_top + ROW_HEIGHT / 2
            row_idx += 1   # advance immediately, independent of viewport cull

            _core_in_vp = not (y_top + ROW_HEIGHT < self._vp_scene_orth_lo
                               or y_top > self._vp_scene_orth_hi)
            if _core_in_vp:
                self.addRect(QRectF(lw, y_top, timeline_w, ROW_HEIGHT),
                             QPen(Qt.NoPen), QBrush(QColor("#2A2A3E"))).setZValue(0)
                self.addLine(0, y_top + ROW_HEIGHT + ROW_GAP - 1,
                             total_w, y_top + ROW_HEIGHT + ROW_GAP - 1,
                             QPen(QColor("#444466"), 0.8)).setZValue(0.5)

                hdr_item = _CoreHeaderItem(
                    QRectF(0, y_top, lw, ROW_HEIGHT), core, self)
                hdr_item.setBrush(QBrush(QColor("#2B2B45")))
                hdr_item.setPen(QPen(Qt.NoPen))
                hdr_item.setZValue(36)
                self.addItem(hdr_item)
                self._frozen_items.append((hdr_item, 0))

                arrow   = "▼" if expanded else "▶"
                arrow_w = fm.horizontalAdvance("▼")
                arr_txt = self.addSimpleText(arrow, font)
                arr_txt.setBrush(QBrush(QColor("#9999CC")))
                arr_txt.setPos(3, y_ctr - fm.height() / 2)
                arr_txt.setZValue(37)
                arr_txt.setAcceptedMouseButtons(Qt.NoButton)
                arr_txt.setAcceptHoverEvents(False)
                self._frozen_items.append((arr_txt, 3))

                dot_item = QGraphicsEllipseItem(0, -5, 10, 10)
                dot_item.setPen(QPen(Qt.NoPen))
                dot_item.setBrush(QBrush(dot_c))
                dot_item.setPos(arrow_w + 6, y_ctr)
                dot_item.setZValue(37)
                dot_item.setAcceptedMouseButtons(Qt.NoButton)
                dot_item.setAcceptHoverEvents(False)
                self.addItem(dot_item)
                self._frozen_items.append((dot_item, arrow_w + 6))

                _util_w         = fm.horizontalAdvance("100%") + 8
                _core_lbl_avail = max(0, lw - (arrow_w + 20) - 4 - _util_w)
                lbl_item = self.addSimpleText(
                    fm.elidedText(core, Qt.ElideRight, _core_lbl_avail), font)
                lbl_item.setBrush(QBrush(QColor("#E0E0E0")))
                lbl_item.setPos(arrow_w + 20, y_ctr - fm.height() / 2)
                lbl_item.setZValue(37)
                lbl_item.setAcceptedMouseButtons(Qt.NoButton)
                lbl_item.setAcceptHoverEvents(False)
                self._frozen_items.append((lbl_item, arrow_w + 20))

                # --- Core utilisation % (IDLE excluded) ---
                _total_ns  = trace.time_max - trace.time_min
                _active_ns = sum(s.end - s.start for s in segs
                                 if parse_task_name(s.task)[2] not in ("TICK",)
                                 and not parse_task_name(s.task)[2].startswith("IDLE"))
                _util_pct  = 100.0 * _active_ns / _total_ns if _total_ns > 0 else 0.0
                _util_item = self.addSimpleText(f"{_util_pct:.0f}%", font_sm)
                _util_item.setBrush(QBrush(QColor("#77BB77")))
                _util_item.setPos(lw - _util_w + 4, y_ctr - fm.height() / 2)
                _util_item.setZValue(37)
                _util_item.setAcceptedMouseButtons(Qt.NoButton)
                _util_item.setAcceptHoverEvents(False)
                self._frozen_items.append((_util_item, lw - _util_w + 4))

                seg_data: list = []
                xs:       list = []
                for i_s, seg in enumerate(_visible_segs(
                        segs,
                        c_seg_starts.get(core, []),
                        _c_seg_lod.get(core, []),
                        c_seg_lod_starts.get(core, []),
                        lod_ns_per_px, _ns_per_px, _vp_ns_lo, _vp_ns_hi,
                        _time_min, _px_per_ns, lw)):
                    x1 = lw + (seg.start - _time_min) * _px_per_ns
                    x2 = lw + (seg.end   - _time_min) * _px_per_ns
                    w  = x2 - x1 if x2 - x1 >= MIN_SEG_WIDTH else MIN_SEG_WIDTH
                    seg_data.append((
                        QRectF(x1, y_top + 2, w, ROW_HEIGHT - 4),
                        _task_brush(seg.task), _task_pen_dark(seg.task), seg,
                    ))
                    xs.append((x1, x1 + w, i_s))
                batch = _BatchRowItem(
                    QRectF(lw, y_top, timeline_w, ROW_HEIGHT),
                    seg_data, trace.time_scale,
                    xs=xs, time_min=trace.time_min)
                batch.setZValue(1)
                self.addItem(batch)

            if not expanded:
                continue

            # -- Per-task sub-rows (only when this core is expanded) -------
            task_seg_map = task_seg_map_by_core[core]

            # Bulk-skip: if the entire sub-row block for this core lies
            # completely outside the viewport, advance row_idx in one step
            # and skip the O(n_tasks) inner loop entirely.
            n_tasks = len(tasks)
            if n_tasks:
                _first_y2 = RULER_HEIGHT + row_idx * (ROW_HEIGHT + ROW_GAP)
                _last_y2  = _first_y2 + (n_tasks - 1) * (ROW_HEIGHT + ROW_GAP)
                if (_last_y2 + ROW_HEIGHT < self._vp_scene_orth_lo
                        or _first_y2 > self._vp_scene_orth_hi):
                    row_idx += n_tasks
                    continue

            for sub_idx, task_name in enumerate(tasks):
                y_top2 = RULER_HEIGHT + row_idx * (ROW_HEIGHT + ROW_GAP)
                row_idx += 1   # always advance before any early continue

                # Orth-cull: skip ALL item creation for off-screen sub-rows.
                if y_top2 + ROW_HEIGHT < self._vp_scene_orth_lo or y_top2 > self._vp_scene_orth_hi:
                    continue

                y_ctr2 = y_top2 + ROW_HEIGHT / 2
                _tmk   = task_merge_key(task_name)
                is_hl  = (_tmk == self._locked_task)

                sub_bg = QColor("#1E1E2C") if sub_idx % 2 == 0 else QColor("#232330")
                self.addRect(QRectF(lw, y_top2, timeline_w, ROW_HEIGHT),
                             QPen(Qt.NoPen), QBrush(sub_bg)).setZValue(0)
                _row_color = _task_color(task_name)
                self._task_row_rects.setdefault(_tmk, []).append(
                    (QRectF(lw, y_top2, timeline_w, ROW_HEIGHT), _row_color))
                if is_hl:
                    hl_bg = QColor(_row_color.red(), _row_color.green(), _row_color.blue(), 35)
                    self.addRect(QRectF(lw, y_top2, timeline_w, ROW_HEIGHT),
                                 QPen(_row_color.lighter(160), 1.0), QBrush(hl_bg)).setZValue(0.9)
                self.addLine(0, y_top2 + ROW_HEIGHT + ROW_GAP - 1,
                             total_w, y_top2 + ROW_HEIGHT + ROW_GAP - 1,
                             QPen(QColor("#2E2E3A"), 0.5)).setZValue(0.5)

                stripe = self.addRect(QRectF(26, y_top2 + 3, 3, ROW_HEIGHT - 6),
                                      QPen(Qt.NoPen), QBrush(_row_color))
                stripe.setZValue(36)
                self._frozen_items.append((stripe, 0))

                # Clickable label background for sub-task row
                disp      = task_display_name(task_name)
                sub_lbl_bg = _TaskLabelItem(
                    QRectF(0, y_top2, lw, ROW_HEIGHT), _tmk, self,
                    tooltip_text=disp)
                sub_lbl_bg.setZValue(36)
                self.addItem(sub_lbl_bg)
                self._frozen_items.append((sub_lbl_bg, 0))
                lbl_color = QColor("#FFD700") if is_hl else QColor("#B0B0C0")
                lbl_fnt   = _monospace_font(max(6, self._font_size - 1),
                                            QFont.Bold) if is_hl else font_sm
                _sub_avail  = max(0, lw - 33 - 4)   # left=33, right margin=4
                _sub_elided = QFontMetrics(lbl_fnt).elidedText(
                    disp, Qt.ElideRight, _sub_avail)
                t_lbl = self.addSimpleText(_sub_elided, lbl_fnt)
                t_lbl.setBrush(QBrush(lbl_color))
                t_lbl.setPos(33, y_ctr2 - fm.height() / 2)
                t_lbl.setZValue(37)
                self._frozen_items.append((t_lbl, 33))

                pen_hl       = QPen(QColor("#FFFFFF"), 1.5)
                _task_pen_cs = _task_pen_dark(task_name)
                _task_br_cs  = _task_brush(task_name)
                seg_data: list = []
                xs:       list = []
                for i_s, seg in enumerate(_visible_segs(
                        task_seg_map[task_name],
                        ct_seg_starts.get(core, {}).get(task_name, []),
                        _ct_lod.get(core, {}).get(task_name, []),
                        ct_lod_starts.get(core, {}).get(task_name, []),
                        lod_ns_per_px, _ns_per_px, _vp_ns_lo, _vp_ns_hi,
                        _time_min, _px_per_ns, lw)):
                    x1 = lw + (seg.start - _time_min) * _px_per_ns
                    x2 = lw + (seg.end   - _time_min) * _px_per_ns
                    w  = x2 - x1 if x2 - x1 >= MIN_SEG_WIDTH else MIN_SEG_WIDTH
                    seg_data.append((
                        QRectF(x1, y_top2 + 1, w, ROW_HEIGHT - 2),
                        _task_br_cs,
                        pen_hl if is_hl else _task_pen_cs,
                        seg,
                    ))
                    xs.append((x1, x1 + w, i_s))
                batch = _BatchRowItem(
                    QRectF(lw, y_top2, timeline_w, ROW_HEIGHT),
                    seg_data, trace.time_scale,
                    label_font=font_sm, label_fm=fm, label_text=disp,
                    xs=xs, time_min=trace.time_min)
                batch.setZValue(1)
                self.addItem(batch)

        # --- STI rows ---------------------------------------------------
        for channel in sti_rows:
            y_top = RULER_HEIGHT + row_idx * (ROW_HEIGHT + ROW_GAP)
            y_ctr = y_top + ROW_HEIGHT / 2
            self.addRect(QRectF(lw, y_top, timeline_w, ROW_HEIGHT),
                         QPen(Qt.NoPen), QBrush(QColor("#1A1A2E"))).setZValue(0)
            lbl = self.addSimpleText(
                fm.elidedText(channel, Qt.ElideRight, max(0, lw - 4 - 4)), font)
            lbl.setBrush(QBrush(QColor("#88AABB")))
            lbl.setPos(4, y_ctr - fm.height() / 2)
            lbl.setZValue(37)
            self._frozen_items.append((lbl, 4))
            _sti_evs_ch  = trace.sti_events_by_target.get(channel, [])
            _sti_stts_ch = trace.sti_starts_by_target.get(channel, [])
            if _sti_stts_ch:
                _slo = max(0, bisect_left(_sti_stts_ch, _vp_ns_lo) - 1)
                _shi = min(len(_sti_evs_ch), bisect_right(_sti_stts_ch, _vp_ns_hi) + 1)
                _sti_evs_ch = _sti_evs_ch[_slo:_shi]
            _sti_markers_ch = [
                (lw + (ev.time - _time_min) * _px_per_ns, _sti_color(ev.note), ev)
                for ev in _sti_evs_ch
            ]
            _sti_item_ch = _BatchStiItem(
                QRectF(lw, y_top, timeline_w, ROW_HEIGHT),
                _sti_markers_ch, trace.time_scale, horizontal=True, axis=y_ctr,
                time_min=trace.time_min)
            _sti_item_ch.setZValue(2)
            self.addItem(_sti_item_ch)
            row_idx += 1

        corner = self.addRect(QRectF(0, 0, lw, RULER_HEIGHT),
                              QPen(Qt.NoPen), QBrush(QColor("#1A1A1A")))
        corner.setZValue(38)
        _upper_h = RULER_HEIGHT - (10 if _has_tick else 0)
        hdr_lbl = self.addSimpleText("Core / Task", font)
        hdr_lbl.setBrush(QBrush(QColor("#888888")))
        hdr_lbl.setPos(4, _upper_h / 2 - fm.height() / 2)
        hdr_lbl.setZValue(39)
        self._frozen_items.append((corner, 0))
        self._frozen_items.append((hdr_lbl, 4))
        self._frozen_top_items.append((corner, 0))
        self._frozen_top_items.append((hdr_lbl, hdr_lbl.pos().y()))
        if _has_tick:
            _tick_corner = self.addSimpleText("TICK", font)
            _tick_corner.setBrush(QBrush(QColor("#E8C84A")))
            _tick_corner.setPos(4, RULER_HEIGHT - 10 + (10 - fm.height()) / 2)
            _tick_corner.setZValue(39)
            self._frozen_items.append((_tick_corner, 4))
            self._frozen_top_items.append((_tick_corner, _tick_corner.pos().y()))

    def _build_vertical_core(self) -> None:
        """Vertical core view: expandable core columns → per-task sub-columns."""
        trace   = self._trace
        font    = _monospace_font(self._font_size)
        font_sm = _monospace_font(max(6, self._font_size - 1))
        fm      = QFontMetrics(font)

        # Use pre-built core data cached at parse time (O(1), no segment iteration)
        core_names           = trace.core_names
        core_segs            = trace.core_segs
        core_tasks           = trace.core_task_order
        task_seg_map_by_core = trace.core_task_segs
        sti_cols             = trace.sti_channels if self._show_sti else []

        # TICK is a global event — shown as a band in the ruler column.
        _tick_mk   = task_merge_key("TICK")
        _tick_segs = trace.seg_map_by_merge_key.get(_tick_mk, [])
        _has_tick  = bool(_tick_segs)

        def _col_count(c: str) -> int:
            return 1 + (len(core_tasks[c]) if self._core_expanded.get(c, True) else 0)

        total_cols = sum(_col_count(c) for c in core_names) + len(sti_cols)
        if total_cols == 0:
            return

        col_w       = max(ROW_HEIGHT + ROW_GAP, 26)
        label_row_h = self._label_width
        time_span   = trace.time_max - trace.time_min
        timeline_h  = time_span / self._ns_per_px
        total_w     = col_w * total_cols + RULER_WIDTH
        total_h     = label_row_h + timeline_h
        self.setSceneRect(0, 0, total_w, total_h)

        # --- Ruler column (left side): frozen to left edge on X scroll ------
        _ruler_col_bg_c = self.addRect(QRectF(0, 0, RULER_WIDTH, total_h),
                                       QPen(Qt.NoPen), QBrush(QColor("#2B2B2B")))
        _ruler_col_bg_c.setZValue(35)
        self._frozen_items.append((_ruler_col_bg_c, 0))

        # --- Label row (top): frozen to top edge on Y scroll ---------------
        _label_row_bg_c = self.addRect(QRectF(0, 0, total_w, label_row_h),
                                       QPen(Qt.NoPen), QBrush(QColor("#1E1E1E")))
        _label_row_bg_c.setZValue(10)
        self._frozen_top_items.append((_label_row_bg_c, 0))

        # Grid-only ruler: horizontal grid lines at absolute Y positions.
        _ruler_grid_c = _RulerItem(trace, self._ns_per_px, total_w, total_h,
                                     font, trace.time_scale, self._show_grid,
                                     horiz=False, axis_offset=label_row_h,
                                     draw_header=False)
        _ruler_grid_c.setZValue(0.5)
        self.addItem(_ruler_grid_c)
        # Header-only ruler: tick marks + labels, frozen to left edge.
        _ruler_hdr_c = _RulerItem(trace, self._ns_per_px, total_w, total_h,
                                    font, trace.time_scale, show_grid=False,
                                    horiz=False, axis_offset=label_row_h,
                                    draw_grid=False)
        _ruler_hdr_c.setZValue(36)
        self.addItem(_ruler_hdr_c)
        self._frozen_items.append((_ruler_hdr_c, 0))

        _time_min  = trace.time_min
        _px_per_ns = 1.0 / self._ns_per_px
        _vp_ns_lo  = self._vp_ns_lo
        _vp_ns_hi  = self._vp_ns_hi
        lod_ns_per_px = trace.seg_lod_ns_per_px
        _ns_per_px = self._ns_per_px
        # Pre-built LOD/start-time references for core view clipping
        c_seg_starts  = trace.core_seg_starts
        _c_seg_lod    = trace.core_seg_lod
        c_seg_lod_starts = trace.core_seg_lod_starts
        ct_seg_starts = trace.core_task_seg_starts
        _ct_lod       = trace.core_task_seg_lod
        ct_lod_starts = trace.core_task_seg_lod_starts

        # --- TICK band: TICK segments overlaid on the right strip of the ruler column ---
        if _has_tick:
            _vtb_x = RULER_WIDTH - 18   # x of TICK band within ruler (right edge strip)
            _vtb_w = 14                 # width of TICK band
            _tick_seg_data_v: list = []
            _tick_xs_v:       list = []
            for i_s, seg in enumerate(_visible_segs(
                    _tick_segs,
                    trace.seg_start_by_merge_key.get(_tick_mk, []),
                    trace.seg_lod_by_merge_key.get(_tick_mk, []),
                    trace.seg_lod_starts_by_merge_key.get(_tick_mk, []),
                    lod_ns_per_px, _ns_per_px, _vp_ns_lo, _vp_ns_hi,
                    _time_min, _px_per_ns, label_row_h)):
                y1 = label_row_h + (seg.start - _time_min) * _px_per_ns
                y2 = label_row_h + (seg.end   - _time_min) * _px_per_ns
                h  = y2 - y1 if y2 - y1 >= MIN_SEG_WIDTH else MIN_SEG_WIDTH
                _tick_seg_data_v.append((
                    QRectF(_vtb_x + 1, y1, _vtb_w - 2, h),
                    _task_brush(seg.task), _task_pen_dark(seg.task), seg,
                ))
                _tick_xs_v.append((y1, y1 + h, i_s))
            tick_batch_v = _BatchRowItem(
                QRectF(_vtb_x, label_row_h, _vtb_w, timeline_h),
                _tick_seg_data_v, trace.time_scale,
                xs=_tick_xs_v, time_min=trace.time_min)
            tick_batch_v.setZValue(37)   # above ruler header (z=36)
            self.addItem(tick_batch_v)
            self._frozen_items.append((tick_batch_v, 0))

        col_idx = 0

        # --- Core columns ------------------------------------------------
        # Each core gets one summary column (always visible) plus optional
        # per-task sub-columns that appear when the core is expanded.
        for core in core_names:
            expanded = self._core_expanded.get(core, True)
            tasks    = core_tasks[core]
            segs     = core_segs[core]
            dot_c    = QColor(_core_color(core))

            x_left = RULER_WIDTH + col_idx * col_w
            col_idx += 1   # advance immediately, independent of viewport cull

            _core_in_vp = not (x_left + col_w < self._vp_scene_orth_lo
                               or x_left > self._vp_scene_orth_hi)
            if _core_in_vp:
                self.addRect(QRectF(x_left, label_row_h, col_w, timeline_h),
                             QPen(Qt.NoPen), QBrush(QColor("#2A2A3E"))).setZValue(0)

                # Clickable core column header (▼/▶ expand toggle)
                hdr_item = _CoreHeaderItem(
                    QRectF(x_left, 0, col_w, label_row_h), core, self)
                hdr_item.setBrush(QBrush(QColor("#2B2B45")))
                hdr_item.setPen(QPen(Qt.NoPen))
                hdr_item.setZValue(36)
                self.addItem(hdr_item)
                self._frozen_top_items.append((hdr_item, 0))

                # Arrow + core name (rotated -90 like task view labels)
                arrow     = "▼" if expanded else "▶"
                arr_label = arrow + " " + core
                _lbl_avail_c = max(0, label_row_h - 8)
                arr_label = QFontMetrics(font).elidedText(arr_label, Qt.ElideRight, _lbl_avail_c)
                arr_txt = self.addSimpleText(arr_label, font)
                arr_txt.setBrush(QBrush(QColor("#9999CC")))
                arr_txt.setRotation(-90)
                arr_txt.setPos(x_left + col_w / 2 - fm.height() / 2, label_row_h - 4)
                arr_txt.setZValue(37)
                arr_txt.setAcceptedMouseButtons(Qt.NoButton)
                arr_txt.setAcceptHoverEvents(False)
                self._frozen_top_items.append((arr_txt, arr_txt.pos().y()))

                seg_data: list = []
                xs:       list = []
                for i_s, seg in enumerate(_visible_segs(
                        segs,
                        c_seg_starts.get(core, []),
                        _c_seg_lod.get(core, []),
                        c_seg_lod_starts.get(core, []),
                        lod_ns_per_px, _ns_per_px, _vp_ns_lo, _vp_ns_hi,
                        _time_min, _px_per_ns, label_row_h)):
                    y1 = label_row_h + (seg.start - _time_min) * _px_per_ns
                    y2 = label_row_h + (seg.end   - _time_min) * _px_per_ns
                    h  = y2 - y1 if y2 - y1 >= MIN_SEG_WIDTH else MIN_SEG_WIDTH
                    seg_data.append((
                        QRectF(x_left + 1, y1, col_w - 2, h),
                        _task_brush(seg.task), _task_pen_dark(seg.task), seg,
                    ))
                    xs.append((y1, y1 + h, i_s))
                batch = _BatchRowItem(
                    QRectF(x_left, label_row_h, col_w, timeline_h),
                    seg_data, trace.time_scale,
                    xs=xs, time_min=trace.time_min)
                batch.setZValue(1)
                self.addItem(batch)

            if not expanded:
                continue

            task_seg_map = task_seg_map_by_core[core]

            # Bulk-skip: if the entire sub-column block for this core lies
            # completely outside the viewport, advance col_idx in one step.
            n_tasks = len(tasks)
            if n_tasks:
                _first_x2 = RULER_WIDTH + col_idx * col_w
                _last_x2  = _first_x2 + (n_tasks - 1) * col_w
                if (_last_x2 + col_w < self._vp_scene_orth_lo
                        or _first_x2 > self._vp_scene_orth_hi):
                    col_idx += n_tasks
                    continue

            for sub_idx, task_name in enumerate(tasks):
                x_left2 = RULER_WIDTH + col_idx * col_w
                col_idx += 1   # always advance before any early continue

                # Orth-cull: skip ALL item creation for off-screen sub-cols.
                if x_left2 + col_w < self._vp_scene_orth_lo or x_left2 > self._vp_scene_orth_hi:
                    continue

                sub_bg  = QColor("#1E1E2C") if sub_idx % 2 == 0 else QColor("#232330")
                self.addRect(QRectF(x_left2, label_row_h, col_w, timeline_h),
                             QPen(Qt.NoPen), QBrush(sub_bg)).setZValue(0)

                _tmk       = task_merge_key(task_name)
                is_hl      = (_tmk == self._locked_task)
                _row_color = _task_color(task_name)
                self._task_row_rects.setdefault(_tmk, []).append(
                    (QRectF(x_left2, label_row_h, col_w, timeline_h), _row_color))
                if is_hl:
                    hl_bg = QColor(_row_color.red(), _row_color.green(), _row_color.blue(), 35)
                    self.addRect(QRectF(x_left2, label_row_h, col_w, timeline_h),
                                 QPen(_row_color.lighter(160), 1.0), QBrush(hl_bg)).setZValue(0.9)

                # Horizontal colour stripe at the bottom edge of the label header
                # (mirrors the vertical stripe at the left edge in horizontal mode)
                stripe = self.addRect(
                    QRectF(x_left2 + 3, label_row_h - 4, col_w - 6, 3),
                    QPen(Qt.NoPen), QBrush(_row_color))
                stripe.setZValue(38)   # above label background (z=36) and text (z=37)
                self._frozen_top_items.append((stripe, stripe.pos().y()))

                # Clickable sub-task column label
                disp      = task_display_name(task_name)
                sub_lbl_bg = _TaskLabelItem(
                    QRectF(x_left2, 0, col_w, label_row_h), _tmk, self,
                    tooltip_text=disp)
                sub_lbl_bg.setZValue(36)
                self.addItem(sub_lbl_bg)
                self._frozen_top_items.append((sub_lbl_bg, 0))
                lbl_color = QColor("#FFD700") if is_hl else QColor("#B0B0C0")
                lbl_fnt   = _monospace_font(max(6, self._font_size - 1),
                                            QFont.Bold) if is_hl else font_sm
                t_lbl = self.addSimpleText(disp, lbl_fnt)
                t_lbl.setBrush(QBrush(lbl_color))
                t_lbl.setRotation(-90)
                t_lbl.setPos(x_left2 + col_w / 2 - fm.height() / 2, label_row_h - 4)
                t_lbl.setZValue(37)
                self._frozen_top_items.append((t_lbl, t_lbl.pos().y()))

                pen_hl       = QPen(QColor("#FFFFFF"), 1.5)
                _task_pen_cs = _task_pen_dark(task_name)
                _task_br_cs  = _task_brush(task_name)
                seg_data: list = []
                xs:       list = []
                for i_s, seg in enumerate(_visible_segs(
                        task_seg_map[task_name],
                        ct_seg_starts.get(core, {}).get(task_name, []),
                        _ct_lod.get(core, {}).get(task_name, []),
                        ct_lod_starts.get(core, {}).get(task_name, []),
                        lod_ns_per_px, _ns_per_px, _vp_ns_lo, _vp_ns_hi,
                        _time_min, _px_per_ns, label_row_h)):
                    y1 = label_row_h + (seg.start - _time_min) * _px_per_ns
                    y2 = label_row_h + (seg.end   - _time_min) * _px_per_ns
                    h  = y2 - y1 if y2 - y1 >= MIN_SEG_WIDTH else MIN_SEG_WIDTH
                    seg_data.append((
                        QRectF(x_left2 + 1, y1, col_w - 2, h),
                        _task_br_cs,
                        pen_hl if is_hl else _task_pen_cs,
                        seg,
                    ))
                    xs.append((y1, y1 + h, i_s))
                batch = _BatchRowItem(
                    QRectF(x_left2, label_row_h, col_w, timeline_h),
                    seg_data, trace.time_scale,
                    xs=xs, time_min=trace.time_min)
                batch.setZValue(1)
                self.addItem(batch)

        # --- STI columns ------------------------------------------------
        for channel in sti_cols:
            x_left = RULER_WIDTH + col_idx * col_w
            self.addRect(QRectF(x_left, label_row_h, col_w, timeline_h),
                         QPen(Qt.NoPen), QBrush(QColor("#1A1A2E"))).setZValue(0)
            lbl = self.addSimpleText(channel, font)
            lbl.setBrush(QBrush(QColor("#88AABB")))
            lbl.setRotation(-90)
            lbl.setPos(x_left + col_w / 2 - fm.height() / 2, label_row_h - 4)
            lbl.setZValue(37)
            self._frozen_top_items.append((lbl, lbl.pos().y()))
            _x_ctr_vc    = x_left + col_w / 2
            _sti_evs_vc  = trace.sti_events_by_target.get(channel, [])
            _sti_stts_vc = trace.sti_starts_by_target.get(channel, [])
            if _sti_stts_vc:
                _slo = max(0, bisect_left(_sti_stts_vc, _vp_ns_lo) - 1)
                _shi = min(len(_sti_evs_vc), bisect_right(_sti_stts_vc, _vp_ns_hi) + 1)
                _sti_evs_vc = _sti_evs_vc[_slo:_shi]
            _sti_mrk_vc = [
                (label_row_h + (ev.time - _time_min) * _px_per_ns, _sti_color(ev.note), ev)
                for ev in _sti_evs_vc
            ]
            _sti_itm_vc = _BatchStiItem(
                QRectF(x_left, label_row_h, col_w, timeline_h),
                _sti_mrk_vc, trace.time_scale, horizontal=False, axis=_x_ctr_vc,
                time_min=trace.time_min)
            _sti_itm_vc.setZValue(2)
            self.addItem(_sti_itm_vc)
            col_idx += 1

        # --- Corner: ruler-column × label-row intersection ---------------
        _vc_corner = self.addRect(QRectF(0, 0, RULER_WIDTH, label_row_h),
                                  QPen(Qt.NoPen), QBrush(QColor("#1A1A1A")))
        _vc_corner.setZValue(40)
        self._frozen_items.append((_vc_corner, 0))
        self._frozen_top_items.append((_vc_corner, 0))

# ---------------------------------------------------------------------------
# Custom graphics items
# ---------------------------------------------------------------------------

class _RulerItem(QGraphicsItem):
    """Lazy ruler + optional grid-line painter.

    Instead of pre-creating one QGraphicsItem per tick (which freezes the UI
    at high zoom levels where step_ns is tiny), this single item computes and
    draws only the ticks that fall inside option.exposedRect at paint time.
    For a 1920 px viewport at 100 px/tick that is ~20 draw calls regardless
    of trace length or zoom level.

    Parameters
    ----------
    horiz : True  → time on X axis (horizontal layout)
             False → time on Y axis (vertical layout)
    axis_offset : pixels from scene origin to the time=0 coordinate
                  (LABEL_WIDTH for horizontal, label_row_h for vertical)
    """

    def __init__(self, trace, ns_per_px: float,
                 total_w: float, total_h: float,
                 font: QFont, time_scale,
                 show_grid: bool, horiz: bool,
                 axis_offset: float,
                 draw_header: bool = True, draw_grid: bool = True):
        super().__init__()
        self._trace       = trace
        self._npp         = ns_per_px
        self._total_w     = total_w
        self._total_h     = total_h
        self._font        = font
        self._time_scale  = time_scale
        self._show_grid   = show_grid
        self._horiz       = horiz
        self._axis_offset = axis_offset
        self._draw_header = draw_header
        self._draw_grid   = draw_grid
        fm = QFontMetrics(font)
        self._text_ascent = fm.ascent()
        # Tell Qt to supply the real exposed rect, not the full bounding rect
        self.setFlag(QGraphicsItem.ItemUsesExtendedStyleOption, True)
        self.setCacheMode(QGraphicsItem.NoCache)

    def boundingRect(self) -> QRectF:
        if not self._draw_grid:
            # Header-only variant: tight rect = just the ruler strip/column.
            if self._horiz:
                return QRectF(0, 0, self._total_w, RULER_HEIGHT)
            else:
                return QRectF(0, 0, RULER_WIDTH, self._total_h)
        return QRectF(0, 0, self._total_w, self._total_h)

    def paint(self, painter, option, widget=None) -> None:
        trace    = self._trace
        npp      = self._npp
        t_min    = trace.time_min
        t_max    = trace.time_max
        exposed  = option.exposedRect
        step_ns  = _nice_grid_step(npp, 100)
        off      = self._axis_offset

        if self._horiz:
            # Compute ns range that is currently exposed
            px_lo    = max(off, exposed.left()) - off
            px_hi    = min(self._total_w, exposed.right()) - off
            ns_lo    = t_min + int(px_lo * npp) - step_ns
            ns_hi    = t_min + int(px_hi * npp) + step_ns
            ns_lo    = max(t_min, ns_lo)
            ns_hi    = min(t_max + step_ns, ns_hi)
            # Grid anchored to t_min so the first tick is always at t_min ("0").
            first    = t_min + ((ns_lo - t_min) // step_ns) * step_ns
            t = first
            while t <= ns_hi:
                if t >= t_min:
                    x = off + (t - t_min) / npp
                    if self._draw_grid and self._show_grid:
                        painter.setPen(QPen(QColor("#555555"), 0.8))
                        painter.drawLine(QLineF(x, RULER_HEIGHT, x, self._total_h))
                    if self._draw_header:
                        painter.setPen(QPen(QColor("#888888"), 1))
                        painter.drawLine(QLineF(x, RULER_HEIGHT - 6, x, RULER_HEIGHT))
                        painter.setPen(QPen(QColor("#AAAAAA")))
                        painter.setFont(self._font)
                        painter.drawText(QPointF(x + 2, 2 + self._text_ascent),
                                         _format_time(t, self._time_scale))
                t += step_ns
        else:
            # Vertical layout: time on Y axis
            py_lo    = max(off, exposed.top()) - off
            py_hi    = min(self._total_h, exposed.bottom()) - off
            ns_lo    = t_min + int(py_lo * npp) - step_ns
            ns_hi    = t_min + int(py_hi * npp) + step_ns
            ns_lo    = max(t_min, ns_lo)
            ns_hi    = min(t_max + step_ns, ns_hi)
            # Grid anchored to t_min so the first tick is always at t_min ("0").
            first    = t_min + ((ns_lo - t_min) // step_ns) * step_ns
            t = first
            while t <= ns_hi:
                if t >= t_min:
                    y = off + (t - t_min) / npp
                    if self._draw_grid and self._show_grid:
                        painter.setPen(QPen(QColor("#3A3A3A"), 0.5))
                        painter.drawLine(QLineF(RULER_WIDTH, y, self._total_w, y))
                    if self._draw_header:
                        painter.setPen(QPen(QColor("#888888"), 1))
                        painter.drawLine(QLineF(RULER_WIDTH - 6, y, RULER_WIDTH, y))
                        painter.setPen(QPen(QColor("#AAAAAA")))
                        painter.setFont(self._font)
                        painter.drawText(QPointF(2, y - 2 + self._text_ascent),
                                         _format_time(t, self._time_scale))
                t += step_ns

class _BatchRowItem(QGraphicsItem):
    """Renders all segments for one timeline row/column in a single paint() pass.

    Replacing O(n_segments) individual QGraphicsItems with one item per row
    reduces scene item count from tens-of-thousands to a handful, eliminating
    the multi-second freeze when switching to the core view on large traces.

    3-Tier Level-of-Detail (LOD) paint strategy
    -------------------------------------------
    Paint cost is bounded to O(visible_segments) at all zoom levels by
    combining pre-merged coarse data with binary-search viewport clipping:

    Tier 1 – micro  (lod < _PAINT_LOD_MICRO = 0.12)
        Single tinted rectangle per row.  Used at far-out zoom where all
        segments are sub-pixel.  O(1) draw calls.

    Tier 2 – coarse (lod < _PAINT_LOD_COARSE = 0.45)
        Uses _coarse_data (segments merged within 6 px) via binary search
        on _coarse_xs to skip off-screen entries.  No pen outlines drawn.
        O(visible_merged) draw calls.

    Tier 3 – full detail
        Full segment rectangles with pen outlines and optional inline text
        labels.  Binary search on _xs limits paint to visible viewport
        slice.  O(visible) draw calls.

    Parameters
    ----------
    bounding_rect : QRectF
        Full bounding box of the row/column in scene coordinates.
    seg_data : list of (QRectF, QBrush, QPen, segment_or_None)
        Pre-computed rectangle + style per segment.  Pass the segment object
        for tooltip support; None suppresses tooltips for that entry.
    time_scale : str
        Forwarded to _format_time() for tooltip text.
    label_font, label_fm, label_text
        When provided, inline text labels are drawn inside wide-enough segments.
    xs : list of (x1, x2, index) or None
        Pre-computed coordinate pairs (start, end) and index into seg_data for
        O(log n) binary-search hit-testing and viewport clipping.  If not
        supplied, xs is derived from seg_data.x() at construction time.
    """

    def __init__(self, bounding_rect: QRectF, seg_data: list, time_scale: str,
                 label_font=None, label_fm=None, label_text: str = "",
                 presorted: bool = False, xs: Optional[list] = None,
                 time_min: int = 0):
        super().__init__()
        self._bounding_rect = bounding_rect
        self._seg_data      = seg_data      # [(QRectF, QBrush, QPen, seg|None)]
        self._time_scale    = time_scale
        self._time_min      = time_min
        self._label_font    = label_font
        self._label_fm      = label_fm
        self._label_text    = label_text
        self._label_adv     = (label_fm.horizontalAdvance(label_text) + 4
                               if label_fm and label_text else 0)
        # (x1, x2, index) list for O(log n) hover hit-testing.
        # Callers that already know x1/x2 should pass xs= to avoid redundant
        # r.x() / r.width() Qt bridge calls for every segment.
        if xs is not None:
            self._xs = xs        # already in start-time order from the builder
        else:
            _xs: list = []
            for i, (r, _, _, s) in enumerate(seg_data):
                if s is not None:
                    rx = r.x()
                    _xs.append((rx, rx + r.width(), i))
            self._xs = _xs if presorted else sorted(_xs, key=lambda t: t[0])
        self.setAcceptHoverEvents(bool(seg_data))
        # Expose the actual clip rect to paint() so we can skip off-screen segments
        self.setFlag(QGraphicsItem.ItemUsesExtendedStyleOption, True)
        # Orientation: horizontal rows have wide bounding rect, vertical columns are tall
        self._horiz = bounding_rect.width() >= bounding_rect.height()
        # Pre-compute coarse LOD segment list (merge segments within 6 scene-px)
        self._coarse_data = self._make_coarse_data()
        # Pre-compute (start, end) coordinate pairs for coarse LOD binary-search clipping
        horiz = self._horiz
        self._coarse_xs: list = [
            (r.x(), r.x() + r.width()) if horiz else (r.y(), r.y() + r.height())
            for r, _, _, _ in self._coarse_data
        ]

    def _make_coarse_data(self) -> list:
        """Pre-merge segments within 6 scene-px of each other for coarse LOD paint.

        Returns a shorter list used when LOD < _PAINT_LOD_COARSE.  Each merged
        run keeps the colour of its first segment; merged rects span from the
        first start to the last end of the run.
        """
        data = self._seg_data
        if len(data) <= 10:
            return data   # not worth merging tiny lists
        MERGE_PX = 6.0
        horiz    = self._horiz
        result   = []
        r0, br0, pen0, seg0 = data[0]
        s0 = r0.x()       if horiz else r0.y()
        e0 = s0 + (r0.width() if horiz else r0.height())
        for r, br, pen, seg in data[1:]:
            s = r.x()     if horiz else r.y()
            e = s + (r.width() if horiz else r.height())
            if s <= e0 + MERGE_PX:
                if e > e0:
                    e0 = e
            else:
                result.append((
                    QRectF(s0, r0.y(), e0 - s0, r0.height()) if horiz else
                    QRectF(r0.x(), s0, r0.width(), e0 - s0),
                    br0, pen0, seg0,
                ))
                r0, br0, pen0, seg0 = r, br, pen, seg
                s0, e0 = s, e
        result.append((
            QRectF(s0, r0.y(), e0 - s0, r0.height()) if horiz else
            QRectF(r0.x(), s0, r0.width(), e0 - s0),
            br0, pen0, seg0,
        ))
        return result

    def boundingRect(self) -> QRectF:
        return self._bounding_rect

    def paint(self, painter: QPainter, option, widget=None) -> None:
        lod = QStyleOptionGraphicsItem.levelOfDetailFromTransform(
                  painter.worldTransform())
        painter.save()

        if lod < _PAINT_LOD_MICRO:
            # ---- Tier 1: micro LOD -----------------------------------------------
            # Row is so compressed that individual segments are meaningless.
            # Draw a single tinted activity bar to indicate presence.
            if self._seg_data:
                br   = self._bounding_rect
                col  = QColor(self._seg_data[0][1].color())
                col.setAlpha(160)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(col))
                if self._horiz:
                    h = br.height()
                    painter.drawRect(QRectF(br.x(), br.y() + h * 0.25,
                                           br.width(), h * 0.50))
                else:
                    w = br.width()
                    painter.drawRect(QRectF(br.x() + w * 0.25, br.y(),
                                           w * 0.50, br.height()))
            painter.restore()
            return

        exposed = option.exposedRect

        if lod < _PAINT_LOD_COARSE:
            # ---- Tier 2: coarse LOD ----------------------------------------------
            # Use pre-merged coarse_data with binary-search viewport clipping.
            cxs    = self._coarse_xs
            coarse = self._coarse_data
            if cxs:
                clip_lo = exposed.left() if self._horiz else exposed.top()
                clip_hi = exposed.right() if self._horiz else exposed.bottom()
                lo_lo, lo_hi = 0, len(cxs)
                while lo_lo < lo_hi:
                    mid = (lo_lo + lo_hi) >> 1
                    if cxs[mid][1] < clip_lo:
                        lo_lo = mid + 1
                    else:
                        lo_hi = mid
                lo_idx = lo_lo
                h_lo, h_hi = lo_idx, len(cxs)
                while h_lo < h_hi:
                    mid = (h_lo + h_hi) >> 1
                    if cxs[mid][0] <= clip_hi:
                        h_lo = mid + 1
                    else:
                        h_hi = mid
                coarse = coarse[lo_idx:h_lo]
            painter.setPen(Qt.NoPen)
            last_brush = None
            for rect, brush, _, _seg in coarse:
                if brush is not last_brush:
                    painter.setBrush(brush)
                    last_brush = brush
                painter.drawRect(rect)
            painter.restore()
            return

        # ---- Tier 3: full detail ------------------------------------------------
        # Binary-search _xs to only paint segments that intersect exposedRect.
        xs = self._xs
        seg_slice: list
        if xs:
            clip_lo = exposed.left() if self._horiz else exposed.top()
            clip_hi = exposed.right() if self._horiz else exposed.bottom()
            # lo_idx: first segment whose right edge >= clip_lo (not fully off left)
            lo_lo, lo_hi = 0, len(xs)
            while lo_lo < lo_hi:
                mid = (lo_lo + lo_hi) >> 1
                if xs[mid][1] < clip_lo:
                    lo_lo = mid + 1
                else:
                    lo_hi = mid
            lo_idx = lo_lo
            # hi_idx: first segment whose left edge > clip_hi (fully off right)
            h_lo, h_hi = lo_idx, len(xs)
            while h_lo < h_hi:
                mid = (h_lo + h_hi) >> 1
                if xs[mid][0] <= clip_hi:
                    h_lo = mid + 1
                else:
                    h_hi = mid
            seg_slice = self._seg_data[lo_idx:h_lo]
        else:
            seg_slice = self._seg_data
        last_brush   = None
        last_pen_key = None
        for rect, brush, pen, _seg in seg_slice:
            if brush is not last_brush:
                painter.setBrush(brush)
                last_brush = brush
            pen_key = (pen.color().rgba(), pen.widthF(), int(pen.style()))
            if pen_key != last_pen_key:
                painter.setPen(pen)
                last_pen_key = pen_key
            painter.drawRect(rect)
        # Inline text labels – second pass to minimise font/pen switches
        if self._label_font and self._label_text and self._label_adv:
            painter.setPen(QPen(QColor("#FFFFFF")))
            painter.setFont(self._label_font)
            txt = self._label_text
            adv = self._label_adv
            for rect, _, _, _seg in seg_slice:
                if rect.width() > adv:
                    painter.drawText(
                        QRectF(rect.x() + 2, rect.y(),
                               rect.width() - 4, rect.height()),
                        Qt.AlignVCenter | Qt.AlignLeft,
                        txt,
                    )
        painter.restore()

    def hoverMoveEvent(self, event) -> None:
        if not self._xs:
            super().hoverMoveEvent(event)
            return
        x  = event.pos().x() if self._horiz else event.pos().y()
        xs = self._xs
        # Binary search: rightmost entry with x1 <= x
        lo, hi = 0, len(xs)
        while lo < hi:
            mid = (lo + hi) >> 1
            if xs[mid][0] <= x:
                lo = mid + 1
            else:
                hi = mid
        for k in range(max(0, lo - 3), min(len(xs), lo + 2)):
            x1, x2, idx = xs[k]
            if x1 <= x <= x2:
                seg = self._seg_data[idx][3]
                if seg is not None:
                    dur = seg.end - seg.start
                    tip = (f"<b>{seg.task}</b><br>"
                           f"Core: {seg.core}<br>"
                           f"Start: {_format_time(seg.start, self._time_scale)}<br>"
                           f"End:   {_format_time(seg.end,   self._time_scale)}<br>"
                           f"Duration: {_format_time(dur,                     self._time_scale)}")
                    _get_popup().show_at(event.screenPos(), tip)
                    super().hoverMoveEvent(event)
                    return
        _get_popup().hide()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        _get_popup().hide()
        super().hoverLeaveEvent(event)

class _BatchStiItem(QGraphicsItem):
    """Renders all STI markers for one channel in a single paint() pass.

    Replaces O(n_sti_events) individual _StiMarkerItem objects with one item
    per channel row, reducing scene item count dramatically on large traces.
    Binary search on pre-sorted marker positions limits paint work to the
    visible viewport slice at any zoom level.
    """

    def __init__(self, bounding_rect: QRectF, markers: list, time_scale: str,
                 horizontal: bool, axis: float, time_min: int = 0):
        """
        markers  : list of (scene_coord, QColor, StiEvent) sorted by scene_coord.
                   scene_coord = scene_x (horizontal) or scene_y (vertical).
        axis     : fixed scene_y for horizontal rows; fixed scene_x for vertical.
        """
        super().__init__()
        self._bounding_rect = bounding_rect
        self._markers       = markers   # sorted by coord
        self._time_scale    = time_scale
        self._time_min      = time_min
        self._horizontal    = horizontal
        self._axis          = axis
        self.setAcceptHoverEvents(bool(markers))
        self.setFlag(QGraphicsItem.ItemUsesExtendedStyleOption, True)
        self.setCacheMode(QGraphicsItem.NoCache)

    def boundingRect(self) -> QRectF:
        return self._bounding_rect

    def paint(self, painter: QPainter, option, widget=None) -> None:
        if not self._markers:
            return
        exposed  = option.exposedRect
        h        = STI_MARKER_H
        w        = 2
        markers  = self._markers
        horiz    = self._horizontal

        # Compute clip bounds with a small margin for the marker size
        lo_bound = (exposed.left()  if horiz else exposed.top())    - h * 3
        hi_bound = (exposed.right() if horiz else exposed.bottom()) + h * 3

        # Binary search: first marker with coord >= lo_bound
        lo_lo, lo_hi = 0, len(markers)
        while lo_lo < lo_hi:
            mid = (lo_lo + lo_hi) >> 1
            if markers[mid][0] < lo_bound:
                lo_lo = mid + 1
            else:
                lo_hi = mid
        lo_idx = lo_lo

        # Binary search: first marker with coord > hi_bound
        h_lo, h_hi = lo_idx, len(markers)
        while h_lo < h_hi:
            mid = (h_lo + h_hi) >> 1
            if markers[mid][0] <= hi_bound:
                h_lo = mid + 1
            else:
                h_hi = mid

        visible = markers[lo_idx:h_lo]
        if not visible:
            return

        lod = QStyleOptionGraphicsItem.levelOfDetailFromTransform(
                  painter.worldTransform())
        axis = self._axis

        painter.save()
        if horiz:
            if lod < _PAINT_LOD_COARSE:
                # Coarse: thin vertical ticks instead of triangles
                for x, color, _ev in visible:
                    painter.setPen(QPen(color, 1.0))
                    painter.drawLine(QLineF(x, axis - h, x, axis + h))
            else:
                last_color = None
                for x, color, _ev in visible:
                    if color is not last_color:
                        painter.setBrush(QBrush(color))
                        painter.setPen(QPen(color.darker(150), 0.5))
                        last_color = color
                    painter.drawPolygon(QPolygonF([
                        QPointF(x,     axis - h),
                        QPointF(x + w, axis + h),
                        QPointF(x - w, axis + h),
                    ]))
        else:
            if lod < _PAINT_LOD_COARSE:
                for y, color, _ev in visible:
                    painter.setPen(QPen(color, 1.0))
                    painter.drawLine(QLineF(axis - h, y, axis + h, y))
            else:
                last_color = None
                for y, color, _ev in visible:
                    if color is not last_color:
                        painter.setBrush(QBrush(color))
                        painter.setPen(QPen(color.darker(150), 0.5))
                        last_color = color
                    painter.drawPolygon(QPolygonF([
                        QPointF(axis - h, y),
                        QPointF(axis + h, y - w),
                        QPointF(axis + h, y + w),
                    ]))
        painter.restore()

    def hoverMoveEvent(self, event) -> None:
        if not self._markers:
            super().hoverMoveEvent(event)
            return
        pos     = event.pos().x() if self._horizontal else event.pos().y()
        markers = self._markers
        HIT     = 8   # px hit-zone half-width
        # Binary search for the nearest candidate
        lo_lo, lo_hi = 0, len(markers)
        while lo_lo < lo_hi:
            mid = (lo_lo + lo_hi) >> 1
            if markers[mid][0] < pos - HIT:
                lo_lo = mid + 1
            else:
                lo_hi = mid
        for k in range(max(0, lo_lo - 1), min(len(markers), lo_lo + 3)):
            c, color, ev = markers[k]
            if abs(c - pos) <= HIT:
                tip = (f"<b>STI: {ev.note}</b><br>"
                       f"Time: {_format_time(ev.time, self._time_scale)}<br>"
                       f"Core: {ev.core}<br>"
                       f"Target: {ev.target}<br>"
                       f"Event: {ev.event}")
                _get_popup().show_at(event.screenPos(), tip)
                super().hoverMoveEvent(event)
                return
        _get_popup().hide()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        _get_popup().hide()
        super().hoverLeaveEvent(event)

class _TaskLabelItem(QGraphicsRectItem):
    """Clickable task-name label area in the timeline label column.

    Clicking toggles the highlight for that task's segments on the timeline.
    """

    _HOVER_BRUSH     = QBrush(QColor(255, 255, 255, 18))
    _HIGHLIGHT_BRUSH = QBrush(QColor(255, 215, 0, 45))

    def __init__(self, rect: QRectF, task_name: str, tl_scene,
                 tooltip_text: str = ""):
        super().__init__(rect)
        self._task_name   = task_name
        self._tl_scene    = tl_scene
        self._tooltip_text = tooltip_text
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setPen(QPen(Qt.NoPen))
        self._update_brush()

    def _update_brush(self) -> None:
        if self._tl_scene._locked_task == self._task_name:
            self.setBrush(self._HIGHLIGHT_BRUSH)
        else:
            self.setBrush(QBrush(Qt.transparent))

    def mousePressEvent(self, event):
        if self._tl_scene._locked_task == self._task_name:
            self._tl_scene.set_highlighted_task(None)   # second click → cancel lock
        else:
            self._tl_scene.set_highlighted_task(self._task_name, locked=True)
        event.accept()

    def hoverEnterEvent(self, event):
        if self._tl_scene._locked_task != self._task_name:
            self.setBrush(self._HOVER_BRUSH)
        if self._tooltip_text:
            _get_popup().show_at(event.screenPos(), self._tooltip_text)
        super().hoverEnterEvent(event)
        # Defer rebuild so it never runs while this item's event handler is active
        task = self._task_name
        scene = self._tl_scene
        QTimer.singleShot(0, lambda: scene.set_highlighted_task(task, locked=False))

    def hoverMoveEvent(self, event):
        if self._tooltip_text:
            _get_popup().show_at(event.screenPos(), self._tooltip_text)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self._update_brush()
        _get_popup().hide()
        super().hoverLeaveEvent(event)
        scene = self._tl_scene
        QTimer.singleShot(0, scene.clear_hover)

class _CoreHeaderItem(QGraphicsRectItem):
    """Clickable label area for a core row — toggles expand/collapse."""

    _NORMAL_BRUSH = QBrush(QColor("#2B2B45"))
    _HOVER_BRUSH  = QBrush(QColor(100, 100, 220, 55))

    def __init__(self, rect: QRectF, core_name: str, tl_scene):
        super().__init__(rect)
        self._core_name = core_name
        self._tl_scene  = tl_scene
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        self._tl_scene.toggle_core(self._core_name)
        event.accept()

    def hoverEnterEvent(self, event):
        self.setBrush(self._HOVER_BRUSH)
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(self._NORMAL_BRUSH)
        self.update()
        super().hoverLeaveEvent(event)

# ---------------------------------------------------------------------------
# LEGACY item classes – superseded by _BatchRowItem / _BatchStiItem
# These classes are no longer instantiated by any builder.  They are retained
# here for reference and as a fallback if individual-item rendering is ever
# needed again (e.g. for a future SVG export path).
# ---------------------------------------------------------------------------

# ===========================================================================
# View
# ===========================================================================

class TimelineView(QGraphicsView):
    """Pan + zoom QGraphicsView wrapping a TimelineScene."""

    zoom_changed    = pyqtSignal(float)
    cursors_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = TimelineScene(self)
        self.setScene(self._scene)

        # -- Qt render settings ------------------------------------------
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.TextAntialiasing, True)
        self.setOptimizationFlags(
            QGraphicsView.DontAdjustForAntialiasing |
            QGraphicsView.DontSavePainterState
        )
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setBackgroundBrush(QBrush(QColor("#1E1E1E")))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)

        # -- Mouse interaction state -------------------------------------
        # Tracks the press position to distinguish click vs drag; button to
        # distinguish left / middle / right action paths in mouseReleaseEvent.
        self._press_pos: Optional[QPoint] = None
        self._press_btn: Qt.MouseButton = Qt.NoButton
        self._drag_threshold    = 6    # px – min movement to enter pan mode
        self._dragging_cursor_idx = -1  # index of cursor being dragged, or -1
        self._cursor_drag_threshold = 8 # px – click-zone around a cursor line

        # Label-column resize drag state
        self._LABEL_RESIZE_ZONE   = 6   # px hit zone around the right border
        self._label_resize_dragging = False
        self._label_resize_start_x  = 0
        self._label_resize_start_w  = 0

        # Middle-button time-range selection (drag to select, release to zoom)
        self._mid_press_ns: Optional[int]   = None   # ns at middle-press
        self._mid_band_item = None                   # gray overlay QGraphicsRectItem

        # -- Zoom debounce -----------------------------------------------
        # Wheel events fire very rapidly; we accumulate the zoom factor and
        # fire one rebuild on a short (60 ms) timer. This prevents janky
        # intermediate renders during fast scrolling.
        self._pinch_accum = 1.0
        # macOS native pinch zoom — intercept events on the viewport widget
        self.viewport().installEventFilter(self)
        # Reposition frozen label-column items whenever the scene is rebuilt
        self._scene.scene_rebuilt.connect(self._reposition_frozen)
        self._scene.scene_rebuilt.connect(self._reposition_frozen_top)

        # Debounce zoom: accumulate factor across rapid wheel events and
        # fire a single rebuild once the user stops scrolling.
        self._zoom_accum: float = 1.0
        self._zoom_anchor_pos: Optional[QPoint] = None
        self._zoom_timer = QTimer(self)
        self._zoom_timer.setSingleShot(True)
        self._zoom_timer.setInterval(60)   # ms – coalesce wheel events
        self._zoom_timer.timeout.connect(self._flush_zoom)

        # Two-timer scroll-rebuild strategy:
        #   _pan_heartbeat: repeating, fires every 50ms WHILE the user is
        #     scrolling.  Keeps the scene fresh during trackpad momentum by
        #     doing a rebuild whenever the viewport has left the cached region.
        #   _pan_timer (settle): single-shot, fires 120ms AFTER the last
        #     scroll event for a final cleanup rebuild.
        # Without the heartbeat, the settle timer is restarted on every
        # scroll event and never fires during continuous scrolling, leaving
        # blank rows once the orth-buffer is exhausted.
        self._pan_timer = QTimer(self)
        self._pan_timer.setSingleShot(True)
        self._pan_timer.setInterval(120)   # ms – settle after scroll stops
        self._pan_timer.timeout.connect(self._on_pan_timeout)
        self._pan_heartbeat = QTimer(self)
        self._pan_heartbeat.setSingleShot(False)
        self._pan_heartbeat.setInterval(50) # ms – in-flight rebuild (≈20 fps)
        self._pan_heartbeat.timeout.connect(self._on_pan_heartbeat)

        # -- Fit / resize mode -------------------------------------------
        # Fit-to-window mode: when True, every resize re-runs fit_to_width().
        self._fit_mode: bool = False
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(80)   # ms – debounce rapid resize events
        self._resize_timer.timeout.connect(self._on_resize_timeout)

        # Cache of the last scene-left used for frozen label positioning.
        # Avoids O(n_frozen_items) updates when only vertical scrolling occurs.
        self._frozen_last_scene_left: Optional[float] = None
        # Cache of the last scene-top used for frozen ruler positioning.
        self._frozen_last_scene_top: Optional[float] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _fit_viewport_size(self) -> int:
        """Return the viewport dimension relevant to the time axis for fit calculations."""
        if self._scene._horizontal:
            return max(self.viewport().width(), 800)
        else:
            return max(self.viewport().height(), 600)

    def load_trace(self, trace: BtfTrace) -> None:
        self._fit_mode = True   # new trace always starts in fit mode
        self._scene.set_trace(trace, self._fit_viewport_size())
        self.zoom_changed.emit(self._scene.ns_per_px)

    def add_cursor_at_view_center(self) -> None:
        vp = self.viewport().rect()
        scene_pt = self.mapToScene(vp.center())
        coord = scene_pt.x() if self._scene._horizontal else scene_pt.y()
        ns = self._scene.scene_to_ns(coord)
        self._scene.add_cursor(ns)
        self.cursors_changed.emit(self._scene.cursor_times())

    def clear_cursors(self) -> None:
        self._scene.clear_cursors()
        self.cursors_changed.emit([])

    def set_view_mode(self, mode: str) -> None:
        self._scene.set_view_mode(mode)

    def set_all_cores_expanded(self, expanded: bool) -> None:
        self._scene.set_all_cores_expanded(expanded)

    def scroll_to_ns(self, ns: int) -> None:
        if self._scene._trace is None:
            return
        coord = self._scene.ns_to_scene_coord(ns)
        cur_scene = self.mapToScene(self.viewport().rect().center())
        if self._scene._horizontal:
            self.centerOn(coord, cur_scene.y())
        else:
            self.centerOn(cur_scene.x(), coord)

    def set_horizontal(self, h: bool) -> None:
        self._scene.set_horizontal(h)

    def set_show_sti(self, show: bool) -> None:
        self._scene.set_show_sti(show)

    def set_show_grid(self, show: bool) -> None:
        self._scene.set_show_grid(show)

    def set_font_size(self, size: int) -> None:
        self._scene.set_font_size(size)
        self.zoom_changed.emit(self._scene.ns_per_px)

    def zoom_in(self) -> None:
        self._fit_mode = False
        self._zoom_accum *= 2.0
        if self._zoom_anchor_pos is None:
            self._zoom_anchor_pos = self.viewport().rect().center()
        self._zoom_timer.start()

    def zoom_out(self) -> None:
        self._fit_mode = False
        self._zoom_accum *= 0.5
        if self._zoom_anchor_pos is None:
            self._zoom_anchor_pos = self.viewport().rect().center()
        self._zoom_timer.start()

    def zoom_fit(self) -> None:
        self._fit_mode = True
        self._scene.fit_to_width(self._fit_viewport_size())
        # Ensure the view transform is identity: all zoom is handled at the
        # scene level (ns_per_px) so there must be no view-level scale active.
        # fitInView() would set a persistent QTransform that is not needed here.
        self.resetTransform()
        self.zoom_changed.emit(self._scene.ns_per_px)

    def zoom_1to1(self) -> None:
        """Set zoom to exactly NS_PER_PX_DEFAULT (5 ns/px), keeping the current viewport centre."""
        if self._scene._trace is None:
            return
        self._fit_mode = False
        if self._scene._ns_per_px == NS_PER_PX_DEFAULT:
            return
        # Remember the ns coordinate at the viewport centre so we can restore it.
        vp_center = self.viewport().rect().center()
        scene_pt  = self.mapToScene(vp_center)
        if self._scene._horizontal:
            center_ns = self._scene.scene_to_ns(scene_pt.x())
        else:
            center_ns = self._scene.scene_to_ns(scene_pt.y())
        self._scene._ns_per_px = NS_PER_PX_DEFAULT
        self._scene.rebuild()
        self.resetTransform()
        self.zoom_changed.emit(self._scene.ns_per_px)
        # Scroll so the same ns coordinate stays at the viewport centre.
        # Use scene_pt (captured before rebuild) for the non-time axis so the
        # row/column scroll position is preserved correctly.
        new_coord = self._scene.ns_to_scene_coord(center_ns)
        if self._scene._horizontal:
            self.centerOn(new_coord, scene_pt.y())
        else:
            self.centerOn(scene_pt.x(), new_coord)

    def save_image(self, filepath: str) -> None:
        """Capture the current visible scene content as a PNG image.

        QWidget.grab() renders exactly what is on screen.  When the scene is
        smaller than the viewport, QGraphicsView centres it and leaves blank
        margins; we crop those away by computing the scene rect in viewport
        coordinates so the output contains only real content.
        """
        vp = self.viewport()
        vp_rect = vp.rect()

        # Map the scene bounding rect into viewport pixel coordinates.
        scene_in_vp = self.mapFromScene(self._scene.sceneRect()).boundingRect()

        # Intersect with the viewport rect to get the visible content area.
        content_rect = vp_rect.intersected(scene_in_vp)

        # Fall back to the full viewport if the intersection is empty.
        capture_rect = content_rect if not content_rect.isEmpty() else vp_rect

        pixmap = vp.grab(capture_rect)
        if not pixmap.save(filepath, "PNG"):
            raise OSError(f"QPixmap.save() failed for path: {filepath}")

    def copy_image_to_clipboard(self) -> Optional[str]:
        """Copy the current visible scene content as a PNG image to the clipboard.
        Returns the tool name used ('xclip', 'xsel', 'wl-copy') or None for Qt fallback."""
        vp = self.viewport()
        vp_rect = vp.rect()
        scene_in_vp = self.mapFromScene(self._scene.sceneRect()).boundingRect()
        content_rect = vp_rect.intersected(scene_in_vp)
        capture_rect = content_rect if not content_rect.isEmpty() else vp_rect
        pixmap = vp.grab(capture_rect)

        # Encode to PNG bytes once
        buf = QByteArray()
        buf_dev = QBuffer(buf)
        buf_dev.open(QIODevice.WriteOnly)
        pixmap.save(buf_dev, 'PNG')
        buf_dev.close()
        png_bytes = bytes(buf)

        # On Linux prefer xclip / xsel / wl-copy — Qt clipboard is unreliable for images on X11/Wayland
        for tool, args in [
            ('xclip',   ['xclip',   '-selection', 'clipboard', '-t', 'image/png']),
            ('xsel',    ['xsel',    '--clipboard', '--input']),
            ('wl-copy', ['wl-copy', '--type', 'image/png']),
        ]:
            if shutil.which(tool):
                proc = subprocess.Popen(args, stdin=subprocess.PIPE)
                proc.communicate(png_bytes)
                if proc.returncode == 0:
                    return tool
                # tool failed — try the next one

        # Fallback: Qt clipboard (works on Windows/macOS, variable on Linux)
        # Set both a pixmap (X11 PIXMAP atom, understood by xclipboard) and
        # MIME image/png so modern apps can also paste.
        clipboard = QApplication.clipboard()
        mime = QMimeData()
        mime.setData('image/png', buf)
        mime.setImageData(pixmap.toImage())
        clipboard.setMimeData(mime)
        # Also set as pixmap directly for legacy X11 clipboard managers
        clipboard.setPixmap(pixmap)
        return None

    # ------------------------------------------------------------------
    # Mouse: click → place cursor, drag → pan
    # ------------------------------------------------------------------
    # mousePressEvent priority (in order of evaluation):
    #   1. MiddleButton  → start time-range selection band
    #   2. LeftButton near label-column border → start resize drag
    #   3. LeftButton near a cursor line → start cursor drag
    #   4. LeftButton inside label column → let _TaskLabelItem handle it
    #   5. Anything else → default ScrollHandDrag (pan)
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        self._press_pos = event.pos()
        self._press_btn = event.button()

        if event.button() == Qt.MiddleButton:
            if self._scene._trace is not None:
                scene_pt = self.mapToScene(event.pos())
                coord = scene_pt.x() if self._scene._horizontal else scene_pt.y()
                self._mid_press_ns = self._scene.scene_to_ns(coord)
                # Remove any stale band
                if self._mid_band_item is not None:
                    self._scene.removeItem(self._mid_band_item)
                    self._mid_band_item = None
                self.setDragMode(QGraphicsView.NoDrag)
                event.accept()
                return

        if event.button() == Qt.LeftButton:
            # --- Check if we're starting a label-column/row resize drag ---
            if self._scene._horizontal:
                lw = self._scene._label_width
                if abs(event.pos().x() - lw) <= self._LABEL_RESIZE_ZONE:
                    self._label_resize_dragging = True
                    self._label_resize_start_x  = event.pos().x()
                    self._label_resize_start_w  = lw
                    self.setDragMode(QGraphicsView.NoDrag)
                    self.viewport().setCursor(Qt.SizeHorCursor)
                    event.accept()
                    return
            else:
                lw = self._scene._label_width
                if abs(event.pos().y() - lw) <= self._LABEL_RESIZE_ZONE:
                    self._label_resize_dragging = True
                    self._label_resize_start_x  = event.pos().y()   # reused as start coord
                    self._label_resize_start_w  = lw
                    self.setDragMode(QGraphicsView.NoDrag)
                    self.viewport().setCursor(Qt.SizeVerCursor)
                    event.accept()
                    return

            # --- Check if we're starting a cursor drag ---
            scene_pt = self.mapToScene(event.pos())
            th = self._cursor_drag_threshold
            for idx, cursor_ns in enumerate(self._scene._cursor_times):
                cursor_coord = self._scene.ns_to_scene_coord(cursor_ns)
                press_coord  = scene_pt.x() if self._scene._horizontal else scene_pt.y()
                if abs(press_coord - cursor_coord) <= th:
                    self._dragging_cursor_idx = idx
                    self.setDragMode(QGraphicsView.NoDrag)
                    self.viewport().setCursor(Qt.SizeHorCursor
                                              if self._scene._horizontal
                                              else Qt.SizeVerCursor)
                    event.accept()
                    return

            # --- Clicking inside the label column: disable ScrollHandDrag so
            #     _TaskLabelItem (and _CoreHeaderItem) can receive the click.
            #     If the click does NOT land on any _TaskLabelItem, cancel the
            #     current highlight (click on empty label-column area). ---
            lw = self._scene._label_width
            in_vp_label = (event.pos().x() < lw if self._scene._horizontal
                           else event.pos().y() < lw)
            if in_vp_label:
                self.setDragMode(QGraphicsView.NoDrag)
                scene_pt2 = self.mapToScene(event.pos())
                hits = [it for it in self._scene.items(scene_pt2)
                        if isinstance(it, _TaskLabelItem)]
                if not hits and self._scene._locked_task is not None:
                    self._scene.set_highlighted_task(None)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        # Dispatch in order of drag states (mutually exclusive):
        #   1. Label-column resize drag  (_label_resize_dragging)
        #   2. Hover cursor near label border  (show resize cursor hint)
        #   3. Middle-button range selection  (_mid_press_ns)
        #   4. Cursor drag  (_dragging_cursor_idx >= 0)
        #   5. Default pan  (super().mouseMoveEvent)
        #      + fallback: clear stale hover if mouse leaves label column

        # Label-column/row resize drag
        if self._label_resize_dragging:
            if self._scene._horizontal:
                delta = event.pos().x() - self._label_resize_start_x
            else:
                delta = event.pos().y() - self._label_resize_start_x
            new_w   = self._label_resize_start_w + delta
            self._scene.set_label_width(new_w)
            if self._scene._horizontal:
                self._reposition_frozen()
                if self._fit_mode and self._scene._trace is not None:
                    self._scene.fit_to_width(self._fit_viewport_size())
                    self.zoom_changed.emit(self._scene.ns_per_px)
            else:
                self._reposition_frozen_top()
            event.accept()
            return

        # Show resize cursor when hovering near the label border
        if (self._scene._trace is not None and
                not self._label_resize_dragging and
                self._mid_press_ns is None and
                self._dragging_cursor_idx < 0):
            lw = self._scene._label_width
            if self._scene._horizontal:
                if abs(event.pos().x() - lw) <= self._LABEL_RESIZE_ZONE:
                    self.viewport().setCursor(Qt.SizeHorCursor)
                else:
                    self.viewport().unsetCursor()
            else:
                if abs(event.pos().y() - lw) <= self._LABEL_RESIZE_ZONE:
                    self.viewport().setCursor(Qt.SizeVerCursor)
                else:
                    self.viewport().unsetCursor()

        # Middle-button drag: update gray selection band
        if self._mid_press_ns is not None:
            scene_pt = self.mapToScene(event.pos())
            coord    = scene_pt.x() if self._scene._horizontal else scene_pt.y()
            cur_ns   = self._scene.scene_to_ns(coord)
            a_coord  = self._scene.ns_to_scene_coord(self._mid_press_ns)
            b_coord  = self._scene.ns_to_scene_coord(cur_ns)
            if a_coord > b_coord:
                a_coord, b_coord = b_coord, a_coord
            sr   = self._scene.sceneRect()
            # Remove old band before drawing new one
            if self._mid_band_item is not None:
                self._scene.removeItem(self._mid_band_item)
                self._mid_band_item = None
            band_brush = QBrush(QColor(180, 180, 180, 55))
            band_pen   = QPen(QColor(220, 220, 220, 120), 1.0)
            if self._scene._horizontal:
                rect = QRectF(a_coord, sr.y(), b_coord - a_coord, sr.height())
            else:
                rect = QRectF(sr.x(), a_coord, sr.width(), b_coord - a_coord)
            self._mid_band_item = self._scene.addRect(rect, band_pen, band_brush)
            self._mid_band_item.setZValue(50)
            event.accept()
            return

        if self._dragging_cursor_idx >= 0:
            scene_pt = self.mapToScene(event.pos())
            coord    = scene_pt.x() if self._scene._horizontal else scene_pt.y()
            ns       = self._scene.scene_to_ns(coord)
            self._scene._cursor_times[self._dragging_cursor_idx] = ns
            self._scene._draw_cursors()
            self.cursors_changed.emit(self._scene.cursor_times())
            event.accept()
            return
        super().mouseMoveEvent(event)
        # After rebuild(), newly-created _TaskLabelItems never receive hoverEnterEvent
        # so their hoverLeaveEvent never fires.  Use position tracking as a fallback:
        # if _hovered_task is set but the mouse is no longer over the label column,
        # clear the hover immediately.
        if self._scene._hovered_task is not None:
            lw = self._scene._label_width
            in_label = (event.pos().x() < lw if self._scene._horizontal
                        else event.pos().y() < lw)
            if not in_label:
                self._scene.clear_hover()

    def mouseReleaseEvent(self, event) -> None:
        # Dispatch in order (first match returns early):
        #   1. Middle-button release  → zoom to dragged range
        #   2. Label-column resize end
        #   3. Cursor drag end
        #   4. Left-click (delta ≤ threshold) inside timeline  → place cursor
        #   5. Right-click inside timeline → remove cursor / clear all

        # Middle-button release: zoom to selected range
        if event.button() == Qt.MiddleButton and self._mid_press_ns is not None:
            # Remove band overlay
            if self._mid_band_item is not None:
                self._scene.removeItem(self._mid_band_item)
                self._mid_band_item = None
            scene_pt  = self.mapToScene(event.pos())
            coord     = scene_pt.x() if self._scene._horizontal else scene_pt.y()
            end_ns    = self._scene.scene_to_ns(coord)
            start_ns  = self._mid_press_ns
            self._mid_press_ns = None
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            if abs(end_ns - start_ns) > 0:
                ns_lo, ns_hi = min(start_ns, end_ns), max(start_ns, end_ns)
                vw = max(self.viewport().width(), 100)
                self._fit_mode = False
                self._scene.zoom_to_range(ns_lo, ns_hi, vw)
                self.zoom_changed.emit(self._scene.ns_per_px)
                # Scroll so the selected range is centred
                center_ns   = (ns_lo + ns_hi) // 2
                new_coord   = self._scene.ns_to_scene_coord(center_ns)
                vp_center   = self.viewport().rect().center()
                cur_scene   = self.mapToScene(vp_center)
                if self._scene._horizontal:
                    self.centerOn(new_coord, cur_scene.y())
                else:
                    self.centerOn(cur_scene.x(), new_coord)
            event.accept()
            return

        if self._label_resize_dragging:
            self._label_resize_dragging = False
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.viewport().unsetCursor()
            event.accept()
            return

        if self._dragging_cursor_idx >= 0:
            self._dragging_cursor_idx = -1
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.viewport().unsetCursor()
            self.cursors_changed.emit(self._scene.cursor_times())
            event.accept()
            return

        # Restore drag mode if it was temporarily disabled for a label click
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        super().mouseReleaseEvent(event)
        if self._press_pos is None:
            return
        delta = (event.pos() - self._press_pos).manhattanLength()
        if delta <= self._drag_threshold:
            # Use viewport coordinates — label column is always the leftmost
            # _label_width pixels on screen regardless of horizontal scroll.
            lw = self._scene._label_width
            in_vp_label = (event.pos().x() < lw if self._scene._horizontal
                           else event.pos().y() < lw)
            if in_vp_label:
                self._press_pos = None
                return
            scene_pt = self.mapToScene(event.pos())
            coord = scene_pt.x() if self._scene._horizontal else scene_pt.y()
            ns = self._scene.scene_to_ns(coord)
            if event.button() == Qt.LeftButton:
                self._scene.add_cursor(ns)
                self.cursors_changed.emit(self._scene.cursor_times())
            elif event.button() == Qt.RightButton:
                if event.modifiers() & Qt.ShiftModifier:
                    self._scene.clear_cursors()
                else:
                    self._scene.remove_nearest_cursor(ns)
                self.cursors_changed.emit(self._scene.cursor_times())
        self._press_pos = None

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        scene_pt = self.mapToScene(event.pos())
        coord = scene_pt.x() if self._scene._horizontal else scene_pt.y()
        ns = self._scene.scene_to_ns(coord)

        menu.addAction(
            f"Place cursor here  ({_format_time(ns, self._scene._trace.time_scale) if self._scene._trace else ''})",
            lambda: (self._scene.add_cursor(ns),
                     self.cursors_changed.emit(self._scene.cursor_times()))
        )
        if self._scene.cursor_times():
            menu.addAction(
                "Remove nearest cursor",
                lambda: (self._scene.remove_nearest_cursor(ns),
                         self.cursors_changed.emit(self._scene.cursor_times()))
            )
            menu.addAction(
                "Clear all cursors",
                lambda: (self._scene.clear_cursors(),
                         self.cursors_changed.emit([]))
            )
        menu.exec_(event.globalPos())

    # ------------------------------------------------------------------
    # Wheel + touch events
    # ------------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.ControlModifier:
            angle  = event.angleDelta().y()
            factor = 1.15 if angle > 0 else 1 / 1.15
            # Accumulate factor; record anchor from the *first* event in the
            # batch so the zoom stays anchored at the initial cursor position.
            self._zoom_accum *= factor
            if self._zoom_anchor_pos is None:
                self._zoom_anchor_pos = QPoint(event.pos())
            # Exit fit mode immediately so a resize event that fires inside
            # the 60 ms debounce window does not snap back to fit-to-width.
            self._fit_mode = False
            self._zoom_timer.start()   # restart the debounce window
            event.accept()
        else:
            dy  = event.angleDelta().y()
            dx  = event.angleDelta().x()
            hsb = self.horizontalScrollBar()
            vsb = self.verticalScrollBar()
            # Shift+scroll → pan horizontally; plain scroll → natural direction
            if event.modifiers() & Qt.ShiftModifier:
                if dy != 0:
                    hsb.setValue(hsb.value() - dy)
            else:
                if dx != 0:
                    hsb.setValue(hsb.value() - dx)
                if dy != 0:
                    vsb.setValue(vsb.value() - dy)

    def _flush_zoom(self) -> None:
        """Called by the debounce timer: apply all accumulated wheel-zoom at once."""
        factor = self._zoom_accum
        anchor = self._zoom_anchor_pos
        self._zoom_accum       = 1.0
        self._zoom_anchor_pos  = None
        if factor != 1.0:
            self._do_zoom(factor, anchor)

    def eventFilter(self, obj, e) -> bool:
        """Intercept native pinch-zoom gestures delivered to the viewport."""
        if obj is self.viewport():
            if e.type() == QEvent.Leave:
                # Mouse left the viewport — ensure any hover highlight is cleared
                self._scene.clear_hover()
                return False
            if e.type() == QEvent.NativeGesture:
                # Qt.ZoomNativeGesture == 3 (macOS two-finger pinch)
                _ZOOM_GESTURE = getattr(Qt, 'ZoomNativeGesture', 3)
                try:
                    if int(e.gestureType()) == int(_ZOOM_GESTURE):
                        factor = 1.0 + e.value()
                        if factor > 0.1:
                            self._do_zoom(factor, e.pos())
                        return True
                except AttributeError:
                    pass
        return super().eventFilter(obj, e)

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        """Called by Qt on every scroll — reposition frozen label-column items."""
        super().scrollContentsBy(dx, dy)
        # Frozen label column only depends on scene X, so skip work on pure
        # vertical scroll (common hot path when browsing many task rows).
        if dx != 0:
            self._reposition_frozen()
        # Frozen ruler row only depends on scene Y, so skip work on pure
        # horizontal (time-axis) scroll.
        if dy != 0:
            self._reposition_frozen_top()
        # Trigger a debounced rebuild on any scroll so that:
        #   • Time-axis scroll (dx in horizontal view / dy in vertical view)
        #     refreshes _vp_ns_lo/hi and repopulates segments that were outside
        #     the 10 % margin used during the last rebuild.
        #   • Orthogonal scroll (row/column direction) populates rows/columns
        #     that row-culling skipped during the last rebuild.
        if dx != 0 or dy != 0:
            self._pan_timer.start()            # restart settle countdown
            if not self._pan_heartbeat.isActive():
                self._pan_heartbeat.start()    # begin continuous rebuild pump

    def _reposition_frozen(self) -> None:
        """Move all frozen label-column scene items so they stay at the left edge."""
        if not self._scene._frozen_items:
            return
        scene_left = self.mapToScene(QPoint(0, 0)).x()
        if self._frozen_last_scene_left is not None and abs(scene_left - self._frozen_last_scene_left) < 1e-6:
            # If new frozen items were created by rebuild(), their x may still
            # be unfrozen even though scene_left is unchanged.
            first_item, first_orig_x = self._scene._frozen_items[0]
            expected_x = scene_left + first_orig_x
            if abs(first_item.x() - expected_x) < 1e-6:
                return
        self._frozen_last_scene_left = scene_left
        for item, orig_x in self._scene._frozen_items:
            item.setX(scene_left + orig_x)

    def _reposition_frozen_top(self) -> None:
        """Move all frozen top-row scene items so they stay at the top edge."""
        if not self._scene._frozen_top_items:
            return
        scene_top = self.mapToScene(QPoint(0, 0)).y()
        if self._frozen_last_scene_top is not None and abs(scene_top - self._frozen_last_scene_top) < 1e-6:
            first_item, first_orig_y = self._scene._frozen_top_items[0]
            if abs(first_item.y() - (scene_top + first_orig_y)) < 1e-6:
                return
        self._frozen_last_scene_top = scene_top
        for item, orig_y in self._scene._frozen_top_items:
            item.setY(scene_top + orig_y)

    def resizeEvent(self, event) -> None:
        """Reflow the timeline on every resize to preserve the current zoom ratio."""
        super().resizeEvent(event)
        if self._scene._trace is not None:
            self._resize_timer.start()

    def _on_resize_timeout(self) -> None:
        """Debounced resize handler.

        Fit mode  → rebuild at the new fit zoom so the trace always fills
                    the viewport (no blank space, no scrollbar).
        Zoom mode → ns_per_px is NEVER touched.  Only update _ns_per_px_fit
                    so the zoom-out clamp reflects the new viewport size, and
                    reposition the frozen label column items.
        """
        if self._scene._trace is None:
            return
        vsize = self._fit_viewport_size()
        time_span = max(
            self._scene._trace.time_max - self._scene._trace.time_min, 1)
        avail   = max(vsize - self._scene._label_width, 100)
        new_fit = time_span / avail

        if self._fit_mode:
            self._scene._ns_per_px_fit = new_fit
            self._scene._ns_per_px     = new_fit
            self._scene.rebuild()
            self.resetTransform()
            self.zoom_changed.emit(self._scene.ns_per_px)
        else:
            # Zoom mode: preserve zoom level exactly.
            self._scene._ns_per_px_fit = new_fit
            self._reposition_frozen()
            self._reposition_frozen_top()

    def _on_pan_heartbeat(self) -> None:
        """During active scrolling: rebuild if viewport exceeds cached bounds."""
        if not self._pan_timer.isActive():
            # Settle timer already expired; stop heartbeat (no-op if also expired).
            self._pan_heartbeat.stop()
            return
        if self._scene._trace is None or self._zoom_timer.isActive():
            return
        if self._needs_rebuild_for_scroll():
            self._scene.rebuild()

    def _on_pan_timeout(self) -> None:
        """Final rebuild ~120 ms after scrolling stops."""
        self._pan_heartbeat.stop()
        if self._scene._trace is None or self._zoom_timer.isActive():
            return
        if self._needs_rebuild_for_scroll():
            self._scene.rebuild()

    def _needs_rebuild_for_scroll(self) -> bool:
        """Return True when current viewport exceeds the last rebuild coverage.

        The scene stores expanded time/orthogonal ranges (_vp_ns_* and
        _vp_scene_orth_*) computed at the last rebuild. During scrolling we can
        skip expensive rebuilds while the viewport remains inside those ranges.
        """
        trace = self._scene._trace
        if trace is None:
            return False

        vp_rect = self.viewport().rect()
        if vp_rect.width() <= 1 or vp_rect.height() <= 1:
            return False

        t_min = trace.time_min
        t_max = trace.time_max
        lw = self._scene._label_width
        ns_per_px = self._scene._ns_per_px

        if self._scene._horizontal:
            lo_coord = self.mapToScene(vp_rect.topLeft()).x()
            hi_coord = self.mapToScene(vp_rect.topRight()).x()
            orth_lo = self.mapToScene(vp_rect.topLeft()).y()
            orth_hi = self.mapToScene(vp_rect.bottomLeft()).y()
        else:
            lo_coord = self.mapToScene(vp_rect.topLeft()).y()
            hi_coord = self.mapToScene(vp_rect.bottomLeft()).y()
            orth_lo = self.mapToScene(vp_rect.topLeft()).x()
            orth_hi = self.mapToScene(vp_rect.topRight()).x()

        ns_lo = max(t_min, min(t_max, t_min + int((lo_coord - lw) * ns_per_px)))
        ns_hi = max(t_min, min(t_max, t_min + int((hi_coord - lw) * ns_per_px)))

        # Time-axis coverage exceeded → need rebuild to repopulate segments.
        if ns_lo < self._scene._vp_ns_lo or ns_hi > self._scene._vp_ns_hi:
            return True

        # Orthogonal coverage exceeded → need rebuild to populate culled rows/cols.
        if orth_lo < self._scene._vp_scene_orth_lo or orth_hi > self._scene._vp_scene_orth_hi:
            return True

        return False

    def _do_zoom(self, factor: float, vp_pos=None) -> None:
        """Zoom by factor, keeping vp_pos (viewport coords) fixed on screen."""
        self._fit_mode = False   # any manual zoom leaves fit mode
        if vp_pos is None:
            vp_pos = self.viewport().rect().center()
        # Convert anchor viewport position to ns coordinate
        scene_pt = self.mapToScene(vp_pos)
        center_ns = self._scene.scene_to_ns(scene_pt.x())
        # Compute the viewport-center offset from the anchor
        vp_center = self.viewport().rect().center()
        offset_x = vp_center.x() - vp_pos.x()

        prev_ns_per_px = self._scene.ns_per_px
        self._scene.zoom(factor)
        if self._scene.ns_per_px == prev_ns_per_px:
            return  # already at zoom limit – nothing changed, skip scroll/emit
        self.zoom_changed.emit(self._scene.ns_per_px)

        # After rebuild, scroll so center_ns reappears at the same viewport x
        new_scene_x = self._scene.ns_to_scene_coord(center_ns)
        cur_scene_y = self.mapToScene(vp_center).y()
        self.centerOn(new_scene_x + offset_x, cur_scene_y)

# ===========================================================================
# Main Window
# ===========================================================================

# ---------------------------------------------------------------------------
# Custom progress dialog (more reliable than QProgressDialog on macOS)
# ---------------------------------------------------------------------------

class _LoadProgressDialog(QWidget):
    """Borderless progress dialog that paints reliably on macOS.

    QProgressDialog on macOS respects setMinimumDuration(0) but still defers
    its first paint until after the event loop has had at least one idle
    cycle.  When files are opened at startup the window manager hasn't
    settled yet, so the dialog can appear blank or not at all.

    This replacement widget uses a plain QWidget with Qt.Tool window flag,
    which bypasses the macOS sheet mechanism entirely and paints immediately.
    """

    def __init__(self, title: str, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        self._title_lbl = QLabel(title, self)
        self._title_lbl.setWordWrap(True)
        layout.addWidget(self._title_lbl)

        self._bar = QProgressBar(self)
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        layout.addWidget(self._bar)

        self._msg_lbl = QLabel("", self)
        layout.addWidget(self._msg_lbl)

        # Draw a subtle border via the stylesheet.
        # Use the object name so the QWidget selector matches only this dialog.
        self.setObjectName("loadprog")
        self.setStyleSheet("""
            QWidget#loadprog {
                background: #2B2B2B;
                border: 1px solid #555;
                border-radius: 6px;
            }
            QLabel { color: #D4D4D4; font-size: 12px; }
            QProgressBar {
                border: 1px solid #555; border-radius: 3px;
                background: #1E1E1E; height: 18px; text-align: center;
                color: #D4D4D4;
            }
            QProgressBar::chunk { background: #0E70C0; border-radius: 2px; }
        """)
        self.adjustSize()

    def setValue(self, pct: int) -> None:
        self._bar.setValue(pct)

    def setLabelText(self, msg: str) -> None:
        self._msg_lbl.setText(msg)

    def update_progress(self, pct: int, msg: str) -> None:
        self._bar.setValue(pct)
        self._msg_lbl.setText(msg)
        QApplication.processEvents()

    def _centre_on_parent(self) -> None:
        """Reposition this dialog centred over its parent window."""
        p = self.parent()
        if p is None:
            return
        pg = p.geometry()
        self.move(pg.center().x() - self.width() // 2,
                  pg.center().y() - self.height() // 2)

    def eventFilter(self, obj, event) -> bool:
        """Track parent-window moves and reposition the dialog to follow."""
        if obj is self.parent() and event.type() == QEvent.Move:
            self._centre_on_parent()
        return super().eventFilter(obj, event)

    def closeEvent(self, event) -> None:
        """Uninstall the parent event filter when the dialog closes."""
        p = self.parent()
        if p is not None:
            p.removeEventFilter(self)
        super().closeEvent(event)

    def show_centered(self, parent_geom) -> None:
        self.adjustSize()
        # Track parent-window moves so the dialog follows.
        p = self.parent()
        if p is not None:
            p.installEventFilter(self)
        self.show()
        self.raise_()
        self.activateWindow()
        # Force an immediate paint so the bar is visible before the thread starts.
        self.repaint()
        QApplication.processEvents()
        # Centre over the parent window.
        _c = parent_geom.center()
        self.move(_c.x() - self.width() // 2,
                  _c.y() - self.height() // 2)
        self.repaint()
        QApplication.processEvents()

# ---------------------------------------------------------------------------
# Background parse thread
# ---------------------------------------------------------------------------

class _ParseThread(QThread):
    """Parses a BTF file in a background thread, emitting progress updates."""
    done     = pyqtSignal(object)   # BtfTrace
    errored  = pyqtSignal(str)
    progress = pyqtSignal(int, str) # pct, message

    def __init__(self, path: str):
        super().__init__()
        self._path = path

    def run(self):
        try:
            self.done.emit(parse_btf(
                self._path,
                progress_callback=self.progress.emit,
                cancel_check=self.isInterruptionRequested,
            ))
        except _ParseCancelledError:
            return
        except Exception as exc:
            self.errored.emit(str(exc))

# ---------------------------------------------------------------------------
# Cursor status-bar widget
# ---------------------------------------------------------------------------

class _CursorButton(QPushButton):
    """Status-bar cursor badge.

    • Click (no drag) → emits ``clicked`` as normal (jump to cursor).
    • Drag out of the status bar → emits ``delete_requested`` so the caller
      can remove the corresponding cursor.
    """

    delete_requested = pyqtSignal()
    _DRAG_THRESHOLD  = 10

    def __init__(self, text: str, color: str, parent: QWidget = None):
        super().__init__(text, parent)
        self._color     = color
        self._press_pos: Optional[QPoint] = None
        self._dragging  = False
        self._normal_ss = self._make_style(color, delete=False)
        self._delete_ss = self._make_style(color, delete=True)
        self.setStyleSheet(self._normal_ss)
        self.setCursor(Qt.PointingHandCursor)

    @staticmethod
    def _make_style(c: str, delete: bool = False) -> str:
        bg  = "#5A1A1A" if delete else "#2A2A2A"
        hbg = "#6A2A2A" if delete else "#3A3A3A"
        bc  = "#FF4444" if delete else c
        return (
            f"QPushButton {{ color: {c}; background: {bg}; "
            f"border: 1px solid {bc}; border-radius: 3px; "
            f"padding: 1px 7px; font-size: {_UI_FONT_SIZE}pt; "
            f"font-family: \"{_get_fixed_font_family()}\"; }}"
            f"QPushButton:hover   {{ background: {hbg}; }}"
            f"QPushButton:pressed {{ background: #4A4A4A; }}"
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._press_pos = event.pos()
            self._dragging  = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._press_pos is not None and (event.buttons() & Qt.LeftButton):
            if (event.pos() - self._press_pos).manhattanLength() > self._DRAG_THRESHOLD:
                self._dragging = True
                outside = self._outside_statusbar(event.globalPos())
                self.setStyleSheet(self._delete_ss if outside else self._normal_ss)
                self.setCursor(Qt.ForbiddenCursor if outside else Qt.ClosedHandCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._dragging:
            outside = self._outside_statusbar(event.globalPos())
            self.setStyleSheet(self._normal_ss)
            self.setCursor(Qt.PointingHandCursor)
            self._press_pos = None
            self._dragging  = False
            if outside:
                self.delete_requested.emit()
            event.accept()
            return
        self._press_pos = None
        self._dragging  = False
        super().mouseReleaseEvent(event)

    def _outside_statusbar(self, global_pos: QPoint) -> bool:
        """True when *global_pos* lies outside the enclosing QStatusBar."""
        w = self.parentWidget()
        while w is not None:
            if isinstance(w, QStatusBar):
                return not w.rect().contains(w.mapFromGlobal(global_pos))
            w = w.parentWidget()
        # Fallback: check own rect
        own_parent = self.parentWidget()
        if own_parent:
            return not own_parent.rect().contains(own_parent.mapFromGlobal(global_pos))
        return True

class CursorBarWidget(QWidget):
    """A row of per-cursor _CursorButtons in the status bar."""
    jump_requested          = pyqtSignal(int)   # ns – scroll timeline
    cursor_delete_requested = pyqtSignal(int)   # ns – remove this cursor

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(2, 0, 2, 0)
        self._layout.setSpacing(4)
        self._buttons: list = []
        self._delta_label: Optional[QLabel] = None

    def rebuild(self, times: list, trace) -> None:
        if not times or trace is None:
            # Clear everything only when there are no cursors.
            if self._buttons or self._delta_label is not None:
                while self._layout.count():
                    item = self._layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()
                self._buttons.clear()
                self._delta_label = None
            return

        ts     = trace.time_scale
        t_min  = trace.time_min
        colors = ["#FF6666", "#66FF99", "#6699FF", "#FFBB44"]
        sorted_pairs = sorted(enumerate(times), key=lambda x: x[1])

        if len(sorted_pairs) != len(self._buttons):
            # Cursor count changed — full rebuild needed.
            while self._layout.count():
                item = self._layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._buttons.clear()
            self._delta_label = None

            for order, (orig_idx, t) in enumerate(sorted_pairs):
                c          = colors[orig_idx % len(colors)]
                label_text = f"C{orig_idx + 1}: {_format_time(t, ts)}"
                ns_capture = t
                btn = _CursorButton(label_text, c)
                btn.clicked.connect(
                    lambda checked=False, ns=ns_capture: self.jump_requested.emit(ns)
                )
                btn.delete_requested.connect(
                    lambda ns=ns_capture: self.cursor_delete_requested.emit(ns)
                )
                btn.setToolTip(
                    f"C{orig_idx + 1}: click to jump  |  drag out of status bar to delete"
                )
                self._layout.addWidget(btn)
                self._buttons.append(btn)

            if len(sorted_pairs) >= 2:
                delta_parts = []
                for i in range(1, len(sorted_pairs)):
                    d = sorted_pairs[i][1] - sorted_pairs[i - 1][1]
                    delta_parts.append(f"Δ{i}={_format_time(d, ts)}")
                dlbl = QLabel("  " + "  ".join(delta_parts))
                dlbl.setStyleSheet(
                    f"color:#FFFFFF; font-size:{_UI_FONT_SIZE}pt;"
                    f" font-family:\"{_get_fixed_font_family()}\"; padding:0 4px;"
                )
                self._layout.addWidget(dlbl)
                self._delta_label = dlbl
        else:
            # Same number of cursors — update text in-place, no widget
            # creation/deletion, no visual flash.
            for order, (orig_idx, t) in enumerate(sorted_pairs):
                btn = self._buttons[order]
                btn.setText(f"C{orig_idx + 1}: {_format_time(t, ts)}")
                # Reconnect jump target to the new timestamp.
                try:
                    btn.clicked.disconnect()
                    btn.delete_requested.disconnect()
                except RuntimeError:
                    pass
                ns_capture = t
                btn.clicked.connect(
                    lambda checked=False, ns=ns_capture: self.jump_requested.emit(ns)
                )
                btn.delete_requested.connect(
                    lambda ns=ns_capture: self.cursor_delete_requested.emit(ns)
                )

            if self._delta_label is not None and len(sorted_pairs) >= 2:
                delta_parts = []
                for i in range(1, len(sorted_pairs)):
                    d = sorted_pairs[i][1] - sorted_pairs[i - 1][1]
                    delta_parts.append(f"Δ{i}={_format_time(d, ts)}")
                self._delta_label.setText("  " + "  ".join(delta_parts))

# ---------------------------------------------------------------------------
# Legend widget
# ---------------------------------------------------------------------------

class _LegendTaskRow(QWidget):
    """A single task row in the legend that emits a click signal."""

    clicked   = pyqtSignal(str)   # task merge key

    _BG_NORMAL  = "background: transparent;"
    _BG_HOVER   = "background: rgba(255,255,255,18); border-radius:3px;"
    _BG_LOCKED  = "background: rgba(255,215,0,45);  border-radius:3px;"

    def __init__(self, task_name: str, display_name: str,
                 color: QColor, tooltip: str = "", parent=None):
        super().__init__(parent)
        self._task_name = task_name
        self._locked    = False

        hl = QHBoxLayout(self)
        hl.setContentsMargins(2, 1, 2, 1)
        hl.setSpacing(6)

        swatch = QLabel()
        swatch.setFixedSize(14, 14)
        swatch.setStyleSheet(
            f"background:{color.name()}; border-radius:2px; border:1px solid #555;"
        )
        hl.addWidget(swatch)

        self._lbl = QLabel(display_name)
        self._lbl.setStyleSheet("color:#D4D4D4;")
        self._lbl.setToolTip(tooltip or display_name)
        hl.addWidget(self._lbl)
        hl.addStretch()

        self.setCursor(Qt.PointingHandCursor)
        self.setAutoFillBackground(False)
        self._set_bg(self._BG_NORMAL)

    def _set_bg(self, css: str) -> None:
        self.setStyleSheet(css)

    def set_locked(self, locked: bool) -> None:
        """Update the visual appearance to reflect click-lock state."""
        self._locked = locked
        self._set_bg(self._BG_LOCKED if locked else self._BG_NORMAL)

    def enterEvent(self, event):
        if not self._locked:
            self._set_bg(self._BG_HOVER)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._locked:
            self._set_bg(self._BG_NORMAL)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._task_name)
        event.accept()   # prevent bubbling up to LegendWidget.mousePressEvent

class LegendWidget(QWidget):
    """Compact scrollable colour legend with click → timeline highlight."""

    task_clicked     = pyqtSignal(str)   # click: task merge key
    cancel_highlight = pyqtSignal()      # click on background → cancel highlight

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(2)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("#1E1E1E"))
        self.setPalette(palette)
        self._task_rows: Dict[str, _LegendTaskRow] = {}   # raw name → row widget
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter tasks…")
        self._search.setStyleSheet(
            "QLineEdit { background:#2D2D2D; color:#D4D4D4; border:1px solid #555; "
            "border-radius:3px; padding:2px 4px; }"
        )
        self._search.textChanged.connect(self._filter_tasks)
        self._layout.addWidget(self._search)

    def set_locked_task(self, task_name: Optional[str]) -> None:
        """Visually mark *task_name* as click-locked (or clear all locks)."""
        for raw, row in self._task_rows.items():
            row.set_locked(raw == task_name)

    def mousePressEvent(self, event) -> None:
        """Click on the legend background (outside a task row) cancels highlight."""
        self.cancel_highlight.emit()
        super().mousePressEvent(event)

    def rebuild(self, trace: BtfTrace) -> None:
        self._task_rows.clear()

        # O(1) teardown: re-parent the old layout (and all its items) onto a
        # temporary QWidget that is immediately scheduled for deletion.  This
        # avoids the O(n²) takeAt(0)-in-a-loop pattern where every removal
        # shifts all remaining items.
        _old = QWidget()
        _old.setLayout(self._layout)
        _old.deleteLater()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(2)

        # Suppress per-addWidget layout recalculations for the whole batch.
        self.setUpdatesEnabled(False)
        try:
            header = QLabel("<b style='color:#AAAAAA'>Tasks</b>")
            header.setTextFormat(Qt.RichText)
            self._layout.addWidget(header)

            # trace.tasks contains merge keys; task_repr maps each to its raw name.
            for _mk in trace.tasks:
                _rep_raw = trace.task_repr.get(_mk, _mk)
                color = _task_color(_rep_raw)
                display = task_display_name(_rep_raw)
                row = _LegendTaskRow(_mk, display, color, tooltip=_rep_raw)
                row.clicked.connect(self.task_clicked)
                self._task_rows[_mk] = row
                self._layout.addWidget(row)

            if trace.sti_channels:
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                sep.setStyleSheet("color:#444;")
                self._layout.addWidget(sep)

                hdr2 = QLabel("<b style='color:#88AABB'>STI Events</b>")
                hdr2.setTextFormat(Qt.RichText)
                self._layout.addWidget(hdr2)

                seen_notes = sorted({ev.note for ev in trace.sti_events if ev.note})
                for note in seen_notes:
                    color = _sti_color(note)
                    row_w = QWidget()
                    hl    = QHBoxLayout(row_w)
                    hl.setContentsMargins(0, 0, 0, 0)
                    hl.setSpacing(6)
                    swatch = QLabel("▼")
                    swatch.setStyleSheet(f"color:{color.name()};")
                    swatch.setFixedWidth(14)
                    hl.addWidget(swatch)
                    lbl = QLabel(note)
                    lbl.setStyleSheet("color:#D4D4D4;")
                    hl.addWidget(lbl)
                    hl.addStretch()
                    self._layout.addWidget(row_w)

            self._layout.addStretch()
        finally:
            self.setUpdatesEnabled(True)

    def _filter_tasks(self, text: str) -> None:
        """Show / hide task rows in the legend based on the search filter."""
        q = text.strip().lower()
        for mk, row in self._task_rows.items():
            row.setVisible(not q or q in mk.lower() or q in row._lbl.text().lower())

# ---------------------------------------------------------------------------
# Statistics dock panel
# ---------------------------------------------------------------------------

class StatsPanel(QWidget):
    """Dock panel showing trace statistics (span, core utilisation, top tasks)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self._inner = QWidget()
        self._ilay = QVBoxLayout(self._inner)
        self._ilay.setContentsMargins(8, 6, 8, 6)
        self._ilay.setSpacing(2)
        self._ilay.addStretch()
        scroll.setWidget(self._inner)
        outer.addWidget(scroll)

    def _clear(self) -> None:
        while self._ilay.count():
            item = self._ilay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _lbl(self, text: str, color: str = "#D4D4D4", bold: bool = False) -> QLabel:
        w = QLabel(text)
        style = f"color:{color}; background:transparent;"
        if bold:
            style += " font-weight:bold;"
        w.setStyleSheet(style)
        return w

    def _sep(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        f.setStyleSheet("color:#444;")
        return f

    def update_trace(self, trace: "BtfTrace") -> None:
        self._clear()
        total_ns = trace.time_max - trace.time_min
        span_str = _format_time(total_ns, trace.time_scale)

        # -- Summary row ---------------------------------------------------
        self._ilay.addWidget(self._lbl(
            f"Span: {span_str}  |  Tasks: {len(trace.tasks)}  |  "
            f"Segments: {len(trace.segments)}  |  STI events: {len(trace.sti_events)}",
            color="#AAAAAA",
        ))

        # -- Core utilisation (excl. IDLE) ---------------------------------
        if trace.core_names:
            self._ilay.addWidget(self._sep())
            self._ilay.addWidget(self._lbl("Core Utilisation (excl. IDLE/TICK):", bold=True))
            for core in trace.core_names:
                segs = trace.core_segs.get(core, [])
                act  = sum(s.end - s.start for s in segs
                           if not parse_task_name(s.task)[2].startswith("IDLE")
                           and parse_task_name(s.task)[2] != "TICK")
                pct  = 100.0 * act / total_ns if total_ns > 0 else 0.0
                n    = max(0, min(10, round(pct / 10)))
                bar  = "█" * n + "░" * (10 - n)
                self._ilay.addWidget(
                    self._lbl(f"  {core}:  {bar}  {pct:.1f}%", color="#77BB77"))

        # -- Top tasks by CPU time (excl. IDLE, top 10) -------------------
        self._ilay.addWidget(self._sep())
        self._ilay.addWidget(self._lbl("Top Tasks by CPU (excl. IDLE/TICK):", bold=True))
        task_times: Dict[str, int] = {}
        for mk, segs in trace.seg_map_by_merge_key.items():
            raw = trace.task_repr.get(mk, mk)
            _, _, tname = parse_task_name(raw)
            if tname.startswith("IDLE") or tname == "TICK":
                continue
            task_times[mk] = sum(s.end - s.start for s in segs)
        for mk, t_ns in sorted(task_times.items(), key=lambda kv: kv[1], reverse=True)[:10]:
            raw  = trace.task_repr.get(mk, mk)
            disp = task_display_name(raw)
            pct  = 100.0 * t_ns / total_ns if total_ns > 0 else 0.0
            self._ilay.addWidget(self._lbl(f"  {disp}:  {pct:.1f}%"))
        self._ilay.addStretch()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _WheelSpinBox(QSpinBox):
    """SpinBox that responds to scroll wheel without requiring keyboard focus."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, event) -> None:
        # Always handle the wheel regardless of focus state
        delta = event.angleDelta().y()
        if delta > 0:
            self.setValue(self.value() + 1)
        elif delta < 0:
            self.setValue(self.value() - 1)
        event.accept()

# ---------------------------------------------------------------------------
# Persistent settings  (btf_viewer.rc)
# ---------------------------------------------------------------------------

class RcSettings:
    """INI-style persistent settings store backed by *btf_viewer.rc*.

    The file is written next to the script.  If it does not yet exist it is
    created automatically with sensible default values on first run.

    Sections and keys
    -----------------
    [window]   width, height, x, y, maximized
    [view]     font_size, theme, horizontal, view_mode, show_sti, show_grid
    [zoom]     ns_per_px  (-1 = use fit-to-width on next open)
    [files]    last_file, last_dir
    """

    RC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btf_viewer.rc")

    _DEFAULTS: Dict[str, Dict[str, str]] = {
        "window": {
            "width":     "1280",
            "height":    "720",
            "x":         "-1",
            "y":         "-1",
            "maximized": "false",
        },
        "view": {
            "font_size":  str(_FONT_SIZE),
            "theme":      "dark",
            "horizontal": "true",
            "view_mode":  "task",
            "show_sti":   "true",
            "show_grid":  "true",
        },
        "zoom": {
            "ns_per_px": "-1",
        },
        "files": {
            "last_file": "",
            "last_dir":  os.path.expanduser("~"),
        },
    }

    def __init__(self) -> None:
        self._cfg = configparser.ConfigParser()
        # Seed every section/key with the compiled defaults so callers always
        # get a valid value even when the rc file is absent or incomplete.
        for section, keys in self._DEFAULTS.items():
            self._cfg[section] = dict(keys)
        # Overlay with the user's saved file (absent keys keep their defaults).
        self._cfg.read(self.RC_PATH, encoding="utf-8")
        # Write the default file on first run so the user can inspect/edit it.
        if not os.path.isfile(self.RC_PATH):
            self._flush()

    # ------------------------------------------------------------------ I/O
    def _flush(self) -> None:
        """Write current state to disk immediately."""
        try:
            with open(self.RC_PATH, "w", encoding="utf-8") as fh:
                fh.write("# btf_viewer.rc – BTF Trace Viewer settings\n")
                fh.write("# This file is managed automatically; you may edit it by hand.\n\n")
                self._cfg.write(fh)
        except OSError:
            pass   # silently ignore write failures (read-only fs, etc.)

    # ---------------------------------------------------------------- getters
    def get(self, section: str, key: str, fallback: str = "") -> str:
        return self._cfg.get(section, key, fallback=fallback)

    def get_int(self, section: str, key: str, fallback: int = 0) -> int:
        try:
            return self._cfg.getint(section, key, fallback=fallback)
        except (ValueError, configparser.Error):
            return fallback

    def get_float(self, section: str, key: str, fallback: float = 0.0) -> float:
        try:
            return self._cfg.getfloat(section, key, fallback=fallback)
        except (ValueError, configparser.Error):
            return fallback

    def get_bool(self, section: str, key: str, fallback: bool = False) -> bool:
        try:
            return self._cfg.getboolean(section, key, fallback=fallback)
        except (ValueError, configparser.Error):
            return fallback

    # ---------------------------------------------------------------- setters
    def set(self, section: str, key: str, value) -> None:
        """Set *key* in *section* and immediately flush to disk."""
        if not self._cfg.has_section(section):
            self._cfg.add_section(section)
        self._cfg.set(section, key, str(value))
        self._flush()

    def set_many(self, section: str, pairs: Dict[str, str]) -> None:
        """Set multiple keys at once with a single disk flush."""
        if not self._cfg.has_section(section):
            self._cfg.add_section(section)
        for key, value in pairs.items():
            self._cfg.set(section, key, str(value))
        self._flush()

# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self._trace: Optional[BtfTrace] = None
        self._current_file: str = ""
        self._parse_thread = None
        self._progress_dialog: Optional[QProgressDialog] = None
        self._settings = RcSettings()

        self.setWindowTitle("BTF Trace Viewer")
        self.resize(1280, 720)

        # Apply saved theme BEFORE building the UI (affects the Qt stylesheet).
        self._is_dark = (self._settings.get("view", "theme", "dark") == "dark")
        if self._is_dark:
            self._apply_dark_theme()
        else:
            self._apply_light_theme()

        self._build_ui()
        self._build_menus()
        self._build_toolbar()
        self._build_status_bar()
        self._view_mode = "task"

        # Restore all persisted settings (geometry, zoom, orientation, …).
        self._restore_settings()

    # ------------------------------------------------------------------
    # Settings: restore on startup, save on close
    # ------------------------------------------------------------------

    def _restore_settings(self) -> None:
        """Apply all values from btf_viewer.rc after the UI has been built."""
        s = self._settings

        # Window geometry
        w = s.get_int("window", "width",  1280)
        h = s.get_int("window", "height", 720)
        self.resize(max(400, w), max(300, h))
        x = s.get_int("window", "x", -1)
        y = s.get_int("window", "y", -1)
        if x >= 0 and y >= 0:
            self.move(x, y)
        if s.get_bool("window", "maximized", False):
            self.showMaximized()

        # Font size
        saved_fs = s.get_int("view", "font_size", _FONT_SIZE)
        self._font_spin.setValue(saved_fs)
        if saved_fs != _FONT_SIZE:
            self._view.set_font_size(saved_fs)

        # Orientation (horizontal is the default)
        if not s.get_bool("view", "horizontal", True):
            self._set_orientation(False)

        # View mode
        if s.get("view", "view_mode", "task") == "core":
            self._set_view_mode("core")

        # STI / grid visibility
        if not s.get_bool("view", "show_sti", True):
            self._act_show_sti.setChecked(False)
            self._sti_cb.setChecked(False)
            self._view.set_show_sti(False)
        if not s.get_bool("view", "show_grid", True):
            self._act_show_grid.setChecked(False)
            self._grid_cb.setChecked(False)
            self._view.set_show_grid(False)

        # Keep the Light-theme menu label in sync when we restored a light theme.
        if not self._is_dark:
            self._act_theme.setText("Switch to &Dark Theme")

    def closeEvent(self, event) -> None:
        """Persist all runtime state to btf_viewer.rc on exit."""
        s = self._settings

        # Window geometry – only save non-maximised size/position so we can
        # restore the proper normal-state geometry if the user un-maximises.
        if self.isMaximized():
            s.set("window", "maximized", "true")
        else:
            s.set_many("window", {
                "maximized": "false",
                "width":     str(self.width()),
                "height":    str(self.height()),
                "x":         str(self.x()),
                "y":         str(self.y()),
            })

        # View settings
        s.set_many("view", {
            "theme":      "dark" if self._is_dark else "light",
            "horizontal": str(self._view._scene._horizontal).lower(),
            "view_mode":  self._view_mode,
            "show_sti":   str(self._act_show_sti.isChecked()).lower(),
            "show_grid":  str(self._act_show_grid.isChecked()).lower(),
            "font_size":  str(self._font_spin.value()),
        })

        # Zoom – save current ns/px so we can re-apply it the next time the
        # same file is opened.  -1 means "use fit-to-width" (no saved zoom).
        if self._view._scene._trace is not None:
            s.set("zoom", "ns_per_px", str(self._view._scene.ns_per_px))
        else:
            s.set("zoom", "ns_per_px", "-1")

        # Drop the trace reference immediately so Python's GC can reclaim
        # the millions of TaskSegment objects on a background thread instead
        # of blocking the main thread (which would freeze the close animation).
        _trace_to_free = self._trace
        self._trace = None
        self._view._scene._trace = None
        if _trace_to_free is not None:
            threading.Thread(
                target=lambda t=_trace_to_free: t,
                daemon=True,
            ).start()
            del _trace_to_free

        super().closeEvent(event)

    def _apply_dark_theme(self) -> None:
        app     = QApplication.instance()

        # Set the application-wide UI font to 12 pt (menus, toolbar, status bar).
        # Timeline task labels use _FONT_SIZE (12 pt) independently.
        base_font = app.font()
        base_font.setPointSize(_UI_FONT_SIZE)
        app.setFont(base_font)
        _ui_fs = f"{_UI_FONT_SIZE}pt"   # reused in stylesheet below

        palette = QPalette()
        dark    = QColor("#1E1E1E")
        darker  = QColor("#121212")
        mid     = QColor("#2D2D2D")
        light   = QColor("#D4D4D4")
        accent  = QColor("#007ACC")
        palette.setColor(QPalette.Window,          dark)
        palette.setColor(QPalette.WindowText,      light)
        palette.setColor(QPalette.Base,            darker)
        palette.setColor(QPalette.AlternateBase,   mid)
        palette.setColor(QPalette.Text,            light)
        palette.setColor(QPalette.Button,          mid)
        palette.setColor(QPalette.ButtonText,      light)
        palette.setColor(QPalette.Highlight,       accent)
        palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
        palette.setColor(QPalette.Link,            accent)
        palette.setColor(QPalette.ToolTipBase,     QColor("#252526"))
        palette.setColor(QPalette.ToolTipText,     light)
        app.setPalette(palette)
        app.setStyleSheet(f"""
            QToolTip  {{ background:#252526; color:#D4D4D4; border:1px solid #555;
                         padding:4px; font-size:{_ui_fs}; }}
            QMenuBar  {{ background:#2D2D2D; color:#D4D4D4; font-size:{_ui_fs}; }}
            QMenuBar::item:selected {{ background:#007ACC; }}
            QMenu     {{ background:#252526; color:#D4D4D4; font-size:{_ui_fs}; }}
            QMenu::item:selected {{ background:#007ACC; }}
            QToolBar  {{ background:#2D2D2D; border:none; spacing:4px;
                         font-size:{_ui_fs}; }}
            QToolBar::separator {{ width:1px; background:#444444; margin:3px 2px; }}
            QToolButton {{ font-size:{_ui_fs}; }}
            QToolButton:hover    {{ background:#3C3C3C; border-radius:3px; }}
            QToolButton:pressed  {{ background:#1C5A9E; border-radius:3px; }}
            QToolButton:checked  {{ background:#0E4D80; border-radius:3px; color:#FFFFFF; }}
            QToolButton:disabled {{ color:#555555; }}
            QStatusBar  {{ background:#1E1E1E; color:#AAAAAA; font-size:{_ui_fs}; }}
            QLabel      {{ font-size:{_ui_fs}; }}
            QCheckBox   {{ font-size:{_ui_fs}; }}
            QSpinBox    {{ font-size:{_ui_fs}; }}
            QDockWidget::title {{ background:#2D2D2D; color:#AAAAAA;
                                  padding:4px; font-size:{_ui_fs}; }}
            QScrollArea {{ background:#1E1E1E; border:none; }}
        """)

    def _apply_light_theme(self) -> None:
        app = QApplication.instance()
        _ui_fs = f"{_UI_FONT_SIZE}pt"

        palette = QPalette()
        bg      = QColor("#F5F5F5")
        bg_base = QColor("#FFFFFF")
        mid     = QColor("#E0E0E0")
        text    = QColor("#1E1E1E")
        accent  = QColor("#007ACC")
        palette.setColor(QPalette.Window,          bg)
        palette.setColor(QPalette.WindowText,      text)
        palette.setColor(QPalette.Base,            bg_base)
        palette.setColor(QPalette.AlternateBase,   mid)
        palette.setColor(QPalette.Text,            text)
        palette.setColor(QPalette.Button,          mid)
        palette.setColor(QPalette.ButtonText,      text)
        palette.setColor(QPalette.Highlight,       accent)
        palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
        palette.setColor(QPalette.Link,            accent)
        palette.setColor(QPalette.ToolTipBase,     QColor("#FFFFCC"))
        palette.setColor(QPalette.ToolTipText,     text)
        app.setPalette(palette)
        app.setStyleSheet(f"""
            QToolTip  {{ background:#FFFFCC; color:#1E1E1E; border:1px solid #AAA;
                         padding:4px; font-size:{_ui_fs}; }}
            QMenuBar  {{ background:#E0E0E0; color:#1E1E1E; font-size:{_ui_fs}; }}
            QMenuBar::item:selected {{ background:#007ACC; color:#FFFFFF; }}
            QMenu     {{ background:#F5F5F5; color:#1E1E1E; font-size:{_ui_fs}; }}
            QMenu::item:selected {{ background:#007ACC; color:#FFFFFF; }}
            QToolBar  {{ background:#E0E0E0; border:none; spacing:4px;
                         font-size:{_ui_fs}; }}
            QToolBar::separator {{ width:1px; background:#C0C0C0; margin:3px 2px; }}
            QToolButton {{ font-size:{_ui_fs}; }}
            QToolButton:hover    {{ background:#D0D0D0; border-radius:3px; }}
            QToolButton:pressed  {{ background:#AACCEE; border-radius:3px; }}
            QToolButton:checked  {{ background:#B3D1EE; border-radius:3px; color:#005A9E; }}
            QToolButton:disabled {{ color:#BBBBBB; }}
            QStatusBar  {{ background:#F5F5F5; color:#555555; font-size:{_ui_fs}; }}
            QLabel      {{ font-size:{_ui_fs}; }}
            QCheckBox   {{ font-size:{_ui_fs}; }}
            QSpinBox    {{ font-size:{_ui_fs}; }}
            QDockWidget::title {{ background:#E0E0E0; color:#555555;
                                  padding:4px; font-size:{_ui_fs}; }}
            QScrollArea {{ background:#F5F5F5; border:none; }}
        """)

    def _toggle_theme(self) -> None:
        self._is_dark = not self._is_dark
        if self._is_dark:
            self._apply_dark_theme()
            self._act_theme.setText("Switch to &Light Theme")
        else:
            self._apply_light_theme()
            self._act_theme.setText("Switch to &Dark Theme")

    def _build_ui(self) -> None:
        # --- Central widget: QStackedWidget (page 0=welcome, page 1=timeline) ---
        self._view = TimelineView(self)
        self._view.zoom_changed.connect(self._on_zoom_changed)
        self._view.cursors_changed.connect(
            lambda times: self._cursor_bar.rebuild(times, self._trace)
        )

        self._welcome_page = QWidget()
        _wl = QVBoxLayout(self._welcome_page)
        _wl.setAlignment(Qt.AlignCenter)
        _wlbl = QLabel(
            "<h2 style='color:#888;'>BTF Trace Viewer</h2>"
            "<p style='color:#666; font-size:11pt;'>"
            "Drop a <b>.btf</b> file here<br>"
            "or press <b>Ctrl+O</b> to open one</p>"
        )
        _wlbl.setTextFormat(Qt.RichText)
        _wlbl.setAlignment(Qt.AlignCenter)
        _wl.addWidget(_wlbl)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._welcome_page)   # index 0
        self._stack.addWidget(self._view)            # index 1
        self._stack.setCurrentIndex(0)
        self.setCentralWidget(self._stack)

        # --- Legend dock (right panel) ---
        self._legend = LegendWidget()
        scroll = QScrollArea()
        scroll.setWidget(self._legend)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(180)
        scroll.setMaximumWidth(260)
        dock = QDockWidget("Legend", self)
        dock.setWidget(scroll)
        dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self._legend_dock = dock

        # --- Statistics dock (bottom panel) ---
        self._stats_panel = StatsPanel()
        stats_dock = QDockWidget("Statistics", self)
        stats_dock.setWidget(self._stats_panel)
        stats_dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.BottomDockWidgetArea, stats_dock)
        self._stats_dock = stats_dock
        stats_dock.hide()

        # --- Signal wiring: legend ↔ scene highlight sync ---
        # Legend click → toggle locked highlight
        sc = self._view._scene
        self._legend.task_clicked.connect(self._on_legend_task_clicked)
        self._legend.cancel_highlight.connect(
            lambda: sc.set_highlighted_task(None)
        )
        # Keep legend lock-highlight in sync whenever the scene highlight changes
        sc.highlight_changed.connect(
            lambda t, lk: self._legend.set_locked_task(t if lk else None)
        )

        self.setAcceptDrops(True)

    def _build_menus(self) -> None:
        mb = self.menuBar()

        # --- File menu ---
        fm = mb.addMenu("&File")
        self._act_open = fm.addAction("&Open…", self._on_open, QKeySequence.Open)
        fm.addSeparator()
        self._act_save_img = fm.addAction("Save as &Image (PNG)…", self._on_save_image, "Ctrl+S")
        self._act_save_img.setEnabled(False)
        self._act_copy_img = fm.addAction("&Copy Image to Clipboard", self._on_copy_image, "Ctrl+Shift+C")
        self._act_copy_img.setEnabled(False)
        fm.addSeparator()
        fm.addAction("E&xit", self.close, QKeySequence.Quit)

        # --- View menu (layout, visibility, zoom, mode, theme) ---
        vm = mb.addMenu("&View")
        self._act_horiz = vm.addAction("&Horizontal layout", lambda: self._set_orientation(True))
        self._act_vert  = vm.addAction("&Vertical layout",   lambda: self._set_orientation(False))
        self._act_horiz.setCheckable(True)
        self._act_vert.setCheckable(True)
        self._act_horiz.setChecked(True)
        vm.addSeparator()
        self._act_show_sti  = vm.addAction("Show &STI events", lambda: self._toggle_sti())
        self._act_show_grid = vm.addAction("Show &grid lines", lambda: self._toggle_grid())
        self._act_show_sti.setCheckable(True)
        self._act_show_sti.setChecked(True)
        self._act_show_grid.setCheckable(True)
        self._act_show_grid.setChecked(True)
        vm.addSeparator()
        vm.addAction("&Zoom In",        self._view.zoom_in,   QKeySequence.ZoomIn)
        vm.addAction("Zoom &Out",       self._view.zoom_out,  QKeySequence.ZoomOut)
        vm.addAction("&Fit to window",  self._view.zoom_fit,  "Ctrl+0")
        vm.addSeparator()
        self._act_legend = vm.addAction("Show &Legend")
        self._act_legend.setShortcut("Ctrl+L")
        self._act_legend.setCheckable(True)
        self._act_legend.setChecked(True)
        self._act_legend.toggled.connect(self._legend_dock.setVisible)
        self._legend_dock.visibilityChanged.connect(self._act_legend.setChecked)
        self._act_stats = vm.addAction("Show S&tatistics")
        self._act_stats.setShortcut("Ctrl+T")
        self._act_stats.setCheckable(True)
        self._act_stats.setChecked(False)
        self._act_stats.toggled.connect(self._stats_dock.setVisible)
        self._stats_dock.visibilityChanged.connect(self._act_stats.setChecked)
        vm.addSeparator()
        self._act_task_view = vm.addAction("Task &View", lambda: self._set_view_mode("task"))
        self._act_core_view = vm.addAction("&Core View", lambda: self._set_view_mode("core"))
        self._act_task_view.setCheckable(True)
        self._act_core_view.setCheckable(True)
        self._act_task_view.setChecked(True)
        vm.addSeparator()
        self._act_theme = vm.addAction("Switch to &Light Theme", self._toggle_theme)

        # --- Cursors menu ---
        cm = mb.addMenu("&Cursors")
        cm.addAction("Place cursor at centre\tC",
                     self._view.add_cursor_at_view_center, "C")
        cm.addAction("Clear all cursors\tShift+C",
                     self._view.clear_cursors, "Shift+C")
        cm.addSeparator()
        cm.addAction(
            "Tip: Left-click on timeline to place cursor\n"
            "Right-click on timeline to remove nearest cursor"
        ).setEnabled(False)

        # --- Help menu ---
        hm = mb.addMenu("&Help")
        hm.addAction("&About", self._on_about)

    def _build_toolbar(self) -> None:
        tb = self.addToolBar("Main")
        self._tb = tb
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        # --- File actions ---
        tb.addAction("📂 Open",    self._on_open)
        tb.addAction("💾 Save PNG", self._on_save_image)
        tb.addAction("📋 Copy",     self._on_copy_image)
        tb.addSeparator()

        # --- Layout and zoom ---
        self._tb_horiz_btn = tb.addAction("↔ Horizontal", lambda: self._set_orientation(True))
        self._tb_vert_btn  = tb.addAction("↕ Vertical",   lambda: self._set_orientation(False))
        self._tb_horiz_btn.setCheckable(True)
        self._tb_vert_btn.setCheckable(True)
        self._tb_horiz_btn.setChecked(True)   # default: horizontal
        tb.addSeparator()
        tb.addAction("🔍+",     self._view.zoom_in)
        tb.addAction("🔍-",     self._view.zoom_out)
        self._act_zoom_1to1 = tb.addAction("1:1", self._view.zoom_1to1)
        self._act_zoom_1to1.setToolTip("Zoom to 5 ns/pixel")
        tb.addAction("⊡ Fit",   self._view.zoom_fit)
        tb.addSeparator()

        # --- View mode toggle (Task / Core) ---
        self._tb_task_btn = tb.addAction("Task View", lambda: self._set_view_mode("task"))
        self._tb_core_btn = tb.addAction("Core View", lambda: self._set_view_mode("core"))
        self._tb_task_btn.setCheckable(True)
        self._tb_core_btn.setCheckable(True)
        self._tb_task_btn.setChecked(True)
        # Use addAction so Qt creates and fully owns the internal QToolButton.
        # This avoids the QWidgetAction::releaseWidget SIGSEGV on app exit that
        # occurs when a Python-owned QToolButton is added via addWidget().
        self._tb_expand_all_btn = tb.addAction("⊞ Expand All. ", self._toggle_expand_all_cores)
        self._tb_expand_all_btn.setCheckable(True)
        self._tb_expand_all_btn.setChecked(True)   # default: all expanded
        self._tb_expand_all_btn.setEnabled(False)   # only active in core view
        self._tb_expand_all_btn.setToolTip("Expand / collapse all cores  (only in Core View)")
        # widgetForAction() returns the Qt-owned internal QToolButton — safe to style.
        _ea_widget = tb.widgetForAction(self._tb_expand_all_btn)
        if _ea_widget is not None:
            # Store as instance attribute: QWidget::setStyle does NOT transfer ownership,
            # so the caller must keep the QStyle alive or Qt will use a freed pointer.
            self._ea_fusion_style = QStyleFactory.create("Fusion")
            if self._ea_fusion_style:
                _ea_widget.setStyle(self._ea_fusion_style)
            _ea_widget.setStyleSheet(
                "QToolButton { color: #D4D4D4; background: transparent; border: none; padding: 2px 4px; }"
                "QToolButton:disabled { color: #555555; }"
            )
            # Fix width to the wider of the two label strings so the toolbar never shifts
            _ea_fm = _ea_widget.fontMetrics()
            _ea_w  = max(_ea_fm.horizontalAdvance("⊞ Expand All. "),
                         _ea_fm.horizontalAdvance("⊟ Collapse All")) + 24
            _ea_widget.setFixedWidth(_ea_w)
        tb.addSeparator()

        # --- Cursor controls ---
        tb.addAction("│C Place cursor", self._view.add_cursor_at_view_center)
        tb.addAction("✕ Clear cursors", self._view.clear_cursors)
        tb.addSeparator()
        self._tb_legend_btn = tb.addAction("📋 Legend", lambda: self._act_legend.toggle())
        self._tb_legend_btn.setCheckable(True)
        self._tb_legend_btn.setChecked(True)
        self._tb_legend_btn.setToolTip("Show / hide the Legend panel  (Ctrl+L)")
        self._legend_dock.visibilityChanged.connect(self._tb_legend_btn.setChecked)
        tb.addSeparator()

        # --- Toolbar widgets: STI/grid checkboxes, font spinbox ---
        self._sti_cb = QCheckBox("STI events")
        self._sti_cb.setChecked(True)
        self._sti_cb.stateChanged.connect(lambda s: self._view.set_show_sti(bool(s)))
        self._sti_cb.setStyleSheet("color:#D4D4D4;")
        tb.addWidget(self._sti_cb)

        self._grid_cb = QCheckBox("Grid")
        self._grid_cb.setChecked(True)
        self._grid_cb.stateChanged.connect(lambda s: self._view.set_show_grid(bool(s)))
        self._grid_cb.setStyleSheet("color:#D4D4D4;")
        tb.addWidget(self._grid_cb)
        tb.addSeparator()

        font_lbl = QLabel(" Font:")
        font_lbl.setStyleSheet("color:#AAAAAA;")
        tb.addWidget(font_lbl)
        self._font_spin = _WheelSpinBox()
        self._font_spin.setRange(6, 24)
        self._font_spin.setValue(_FONT_SIZE)   # overwritten by _restore_settings()
        self._font_spin.setFixedWidth(52)
        self._font_spin.setToolTip("Label font size (pt): scroll wheel to adjust")
        self._font_spin.setStyleSheet(
            "QSpinBox { background:#2D2D2D; color:#D4D4D4; border:1px solid #555; "
            "padding:1px 2px; } "
            "QSpinBox::up-button, QSpinBox::down-button { width:14px; }"
        )
        self._font_spin.valueChanged.connect(self._on_font_size_changed)
        tb.addWidget(self._font_spin)


    def _build_status_bar(self) -> None:
        sb = self.statusBar()

        # --- Status labels (file path, event stats) ---
        self._status_file  = QLabel("No file loaded")
        self._status_stats = QLabel("")

        # --- Cursor badge bar ---
        self._cursor_bar   = CursorBarWidget()
        self._cursor_bar.jump_requested.connect(self._view.scroll_to_ns)
        self._cursor_bar.cursor_delete_requested.connect(self._on_cursor_delete)

        # --- Hint text (interaction guide) ---
        self._status_hint  = QLabel(
            "Left-click: cursor  |  Ctrl+Wheel: zoom  |  Scroll: pan"
        )
        self._status_hint.setStyleSheet("color:#666;")

        self._zoom_label = QLabel("Zoom: —")
        self._zoom_label.setStyleSheet("color:#AAAAAA; padding: 0 8px;")

        sb.addWidget(self._status_file)
        sb.addPermanentWidget(self._cursor_bar)
        sb.addPermanentWidget(self._status_stats)
        sb.addPermanentWidget(self._zoom_label)
        sb.addPermanentWidget(self._status_hint)

    # ------------------------------------------------------------------
    # Slots / callbacks
    # ------------------------------------------------------------------

    def _on_open(self) -> None:
        last_dir = self._settings.get("files", "last_dir", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(
            self, "Open BTF trace", last_dir,
            "BTF files (*.btf);;All files (*)"
        )
        if path:
            self._open_file(path)

    def _open_file(self, path: str) -> None:
        if self._progress_dialog is not None:
            self._progress_dialog.close()
            self._progress_dialog = None

        # Abort any in-progress load before starting a new one.
        if self._parse_thread is not None and self._parse_thread.isRunning():
            try:
                self._parse_thread.done.disconnect()
            except (TypeError, RuntimeError):
                pass
            try:
                self._parse_thread.errored.disconnect()
            except (TypeError, RuntimeError):
                pass
            try:
                self._parse_thread.progress.disconnect()
            except (TypeError, RuntimeError):
                pass
            self._parse_thread.requestInterruption()
            self._parse_thread.wait(2000)
            if self._parse_thread.isRunning():
                self._status_file.setText("  Previous load is still stopping…")
                return
            self._parse_thread = None

        # Show a wait cursor and status message while parsing
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self._status_file.setText(f"  Loading {os.path.basename(path)}…")
        QApplication.processEvents()

        # Progress dialog – created before closures so progress_dialog is defined.
        progress_dialog = _LoadProgressDialog(
            f"Loading {os.path.basename(path)}…", self)
        progress_dialog.show_centered(self.geometry())
        self._progress_dialog = progress_dialog

        def _on_done(trace):
            progress_dialog.update_progress(100, "Building scene…")
            QApplication.processEvents()   # let the dialog repaint before heavy build
            self._parse_thread = None
            try:
                self._trace = trace
                self._current_file = path
                # Check whether to restore the saved zoom BEFORE updating last_file.
                _prev_file  = self._settings.get("files", "last_file", "")
                _saved_zoom = self._settings.get_float("zoom", "ns_per_px", -1.0)
                self._settings.set_many("files", {
                    "last_file": path,
                    "last_dir":  os.path.dirname(path),
                })
                self._view.load_trace(trace)
                self._stack.setCurrentIndex(1)
                # Re-apply the saved zoom only when re-opening the exact same file
                # so that new files always start at fit-to-width.
                if _prev_file == path and _saved_zoom > 0:
                    self._view._scene._ns_per_px = max(NS_PER_PX_DEFAULT, _saved_zoom)
                    self._view._scene.rebuild()
                    self._view._fit_mode = False
                    self._view.zoom_changed.emit(self._view._scene.ns_per_px)
                progress_dialog.update_progress(100, "Building legend…")
                QApplication.processEvents()
                self._legend.rebuild(trace)
                self._stats_panel.update_trace(trace)
                self._stats_dock.show()
                self._act_save_img.setEnabled(True)
                self._act_copy_img.setEnabled(True)
                fname = os.path.basename(path)
                ts    = _format_time(trace.time_max - trace.time_min, trace.time_scale)
                n_seg = len(trace.segments)
                n_sti = len(trace.sti_events)
                self.setWindowTitle(f"BTF Trace Viewer – {fname}")
                self._status_file.setText(f"  {fname}  |  span: {ts}")
                self._status_stats.setText(
                    f"tasks: {len(trace.tasks)}  "
                    f"segments: {n_seg}  "
                    f"STI events: {n_sti}  |  "
                )
            except Exception as exc:
                self._status_file.setText("  No file loaded")
                QMessageBox.critical(self, "Render Error",
                                     f"Failed to display:\n{path}\n\n{exc}")
            finally:
                progress_dialog.close()   # close after all heavy work is done
                if self._progress_dialog is progress_dialog:
                    self._progress_dialog = None
                QApplication.restoreOverrideCursor()

        def _on_error(msg):
            progress_dialog.close()
            if self._progress_dialog is progress_dialog:
                self._progress_dialog = None
            QApplication.restoreOverrideCursor()
            self._parse_thread = None
            self._status_file.setText("  No file loaded")
            QMessageBox.critical(self, "Parse Error",
                                 f"Failed to parse:\n{path}\n\n{msg}")

        thread = _ParseThread(path)
        thread.done.connect(_on_done)
        thread.errored.connect(_on_error)
        thread.progress.connect(progress_dialog.update_progress)
        # Keep a reference so the thread is not garbage-collected
        self._parse_thread = thread
        thread.start()

    def _on_save_image(self) -> None:
        if self._trace is None:
            return
        base = os.path.splitext(self._current_file)[0] if self._current_file else "trace"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Image", base + ".png",
            "PNG images (*.png);;All files (*)"
        )
        if path:
            try:
                self._view.save_image(path)
                self.statusBar().showMessage(f"Saved: {path}", 4000)
            except Exception as exc:
                QMessageBox.critical(self, "Save Error", f"Could not save image:\n{exc}")

    def _on_copy_image(self) -> None:
        if self._trace is None:
            return
        used_tool = self._view.copy_image_to_clipboard()
        if used_tool:
            self.statusBar().showMessage(f"Image copied to clipboard (via {used_tool})", 3000)
        elif sys.platform.startswith('linux'):
            # No external tool found — Qt clipboard used (may not work on all setups)
            missing = [t for t in ('xclip', 'xsel', 'wl-copy') if not shutil.which(t)]
            if missing:
                self.statusBar().showMessage(
                    "Image copied (Qt). If paste fails, install xclip:  sudo apt install xclip", 6000)
            else:
                self.statusBar().showMessage("Image copied to clipboard", 3000)
        else:
            self.statusBar().showMessage("Image copied to clipboard", 3000)

    def _set_orientation(self, horizontal: bool) -> None:
        self._act_horiz.setChecked(horizontal)
        self._act_vert.setChecked(not horizontal)
        self._tb_horiz_btn.setChecked(horizontal)
        self._tb_vert_btn.setChecked(not horizontal)
        self._view.set_horizontal(horizontal)

    def _set_view_mode(self, mode: str) -> None:
        self._view_mode = mode
        is_task = (mode == "task")
        self._act_task_view.setChecked(is_task)
        self._act_core_view.setChecked(not is_task)
        self._tb_task_btn.setChecked(is_task)
        self._tb_core_btn.setChecked(not is_task)
        self._tb_expand_all_btn.setEnabled(not is_task)
        if not is_task:
            # Sync button text/state with actual core expanded state
            scene = self._view._scene
            trace = scene._trace
            if trace and trace.core_names:
                all_expanded = all(
                    scene._core_expanded.get(c, True) for c in trace.core_names)
                self._tb_expand_all_btn.setChecked(all_expanded)
                self._tb_expand_all_btn.setText(
                    "⊞ Expand All. " if all_expanded else "⊟ Collapse All")
        self._view.set_view_mode(mode)

    def _toggle_expand_all_cores(self) -> None:
        """Expand or collapse all cores based on the button's checked state."""
        expanded = self._tb_expand_all_btn.isChecked()
        self._tb_expand_all_btn.setText("⊞ Expand All. " if expanded else "⊟ Collapse All")
        self._view.set_all_cores_expanded(expanded)

    def _toggle_sti(self) -> None:
        state = self._act_show_sti.isChecked()
        self._sti_cb.setChecked(state)
        self._view.set_show_sti(state)

    def _toggle_grid(self) -> None:
        state = self._act_show_grid.isChecked()
        self._grid_cb.setChecked(state)
        self._view.set_show_grid(state)

    def _on_font_size_changed(self, size: int) -> None:
        self._view.set_font_size(size)
        self._settings.set("view", "font_size", str(size))

    def _on_zoom_changed(self, ns_per_px: float) -> None:
        if ns_per_px >= 1_000_000:
            z = f"{ns_per_px/1_000_000:.1f} ms/px"
        elif ns_per_px >= 1_000:
            z = f"{ns_per_px/1_000:.1f} µs/px"
        else:
            z = f"{ns_per_px:.1f} ns/px"
        self._zoom_label.setText(f"Zoom: {z}")

    def _on_cursor_delete(self, ns: int) -> None:
        """Remove the cursor whose timestamp matches *ns* (from a badge drag-out)."""
        self._view._scene.remove_nearest_cursor(ns)
        self._view.cursors_changed.emit(self._view._scene.cursor_times())

    def _on_legend_task_clicked(self, task: str) -> None:
        """Toggle click-locked highlight for *task* from the Legend panel."""
        sc = self._view._scene
        if sc._locked_task == task:
            sc.set_highlighted_task(None)          # second click on same → cancel
        else:
            sc.set_highlighted_task(task, locked=True)

    def _on_about(self) -> None:
        if self._is_dark:
            c_title = "#7EC8E3"
            c_head  = "#FFD700"
            c_key   = "#7EC8E3"
            c_body  = "#D4D4D4"
        else:
            c_title = "#005A8E"
            c_head  = "#B8860B"
            c_key   = "#005A8E"
            c_body  = "#333333"
        QMessageBox.about(
            self, "About BTF Trace Viewer",
            f"<h3 style='color:{c_title};'>BTF Trace Viewer</h3>"
            f"<p style='color:{c_body};'>RTOS context-switch visualiser for .btf files.</p>"
            f"<p style='color:{c_body};'><b style='color:{c_head};'>View modes:</b><br>"
            f"• <b style='color:{c_key};'>Task View</b> – one row per task<br>"
            f"• <b style='color:{c_key};'>Core View</b> – one expandable row per CPU core</p>"
            f"<p style='color:{c_body};'><b style='color:{c_head};'>Controls:</b><br>"
            f"• <b style='color:{c_key};'>Left-click</b> – place cursor  |  <b style='color:{c_key};'>Drag</b> cursor line – move it<br>"
            f"• <b style='color:{c_key};'>Right-click</b> – remove cursor  |  <b style='color:{c_key};'>Status badge</b> – jump to cursor<br>"
            f"• <b style='color:{c_key};'>Ctrl+Wheel</b> / pinch – zoom  |  <b style='color:{c_key};'>Scroll</b> – pan<br>"
            f"• <b style='color:{c_key};'>Ctrl+0</b> – fit to window</p>"
        )

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            if any(u.toLocalFile().endswith(".btf") for u in event.mimeData().urls()):
                event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.endswith(".btf"):
                self._open_file(path)
                break

# ===========================================================================
# Entry point
# ===========================================================================

def main() -> None:
    # On Windows with display scaling > 100 %, AA_EnableHighDpiScaling causes
    # Qt to magnify everything (window size AND font pt values) by the scale
    # factor.  Pinning QT_FONT_DPI to 96 keeps font sizes at their intended
    # 96-DPI metrics while still letting widget geometry scale correctly.
    os.environ.setdefault("QT_FONT_DPI", "96")

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps,   True)

    app = QApplication(sys.argv)
    app.setApplicationName("BTF Trace Viewer")
    app.setOrganizationName("btf_viewer")

    win = MainWindow()
    win.show()
    QApplication.processEvents()  # ensure the window is painted before any file open

    if len(sys.argv) > 1:
        path = sys.argv[1]
        if os.path.isfile(path):
            QTimer.singleShot(100, lambda: win._open_file(path))
    else:
        last = win._settings.get("files", "last_file", "")
        if last and os.path.isfile(last):
            QTimer.singleShot(100, lambda: win._open_file(last))

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
