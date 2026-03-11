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
     (timescale_per_px).  Four builder methods cover the two view modes
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
  Main Window         – _CursorButton, _CursorBarWidget, _LegendWidget,
                        _StatsPanel, _RcSettings, _WheelSpinBox, MainWindow
  Entry point         – main()
"""

from __future__ import annotations

import configparser
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import zlib
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
    QAction, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDockWidget, QFileDialog, QFormLayout, QFrame, QGridLayout, QInputDialog,
    QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem,
    QGraphicsRectItem, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QProgressBar,
    QProgressDialog,
    QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QDoubleSpinBox, QSpinBox, QStackedWidget,
    QStatusBar, QStyleFactory, QStyleOptionGraphicsItem, QTabWidget,
    QToolBar, QToolButton, QVBoxLayout, QWidget,
)

# ===========================================================================
# USER CONFIGURATION
# Edit the values in this section to customise the viewer.
# Everything else in the file is internal implementation detail.
# ===========================================================================

# ---- Fonts ----------------------------------------------------------------
FONT_SIZE     = 10   # Timeline label font size (pt).  Adjustable at runtime
                     # via the Font spinbox in the toolbar.
UI_FONT_SIZE  = 10   # Application UI font: menus, toolbar, status bar (pt).

# ---- Layout ---------------------------------------------------------------
LABEL_WIDTH   = 160  # Width of the frozen task-label column (px).
RULER_HEIGHT  =  40  # Height of the time ruler row (px) — horizontal mode.
RULER_WIDTH   = 120  # Width of the time ruler column (px) — vertical mode.
ROW_HEIGHT    =  22  # Height of each task / core row (px).
ROW_GAP       =   4  # Vertical gap between rows (px).
STI_ROW_H     =  18  # Height of an STI (software-trace) row (px).
STI_MARKER_H  =   6  # Height of an STI marker triangle (px).
MIN_SEG_WIDTH = 1.0  # Minimum painted width of a task segment (px).

# ---- Performance / Level-of-Detail ----------------------------------------
_TIMESCALE_PER_PX_DEFAULT       = 2.0    # Initial zoom level (nanoseconds per screen pixel).
_HOVER_HIGHLIGHT_ENABLED = False  # Highlight task bars when hovering the label (default off).
# _BatchRowItem.paint() LOD thresholds (Qt levelOfDetail: 1.0 = 100% zoom).
_PAINT_LOD_COARSE        = 0.45   # Below: merge nearby segments, skip pen outlines.
_PAINT_LOD_MICRO         = 0.12   # Below: draw one tinted activity bar per row.
_LOD_MERGE_PX            = 6.0    # Coarse LOD: merge segments closer than this many scene-px.
_ACTIVITY_ALPHA          = 160    # Alpha for the micro-LOD activity-presence bar.
_HOVER_BISECT_MARGIN     = 3      # Neighbour scan window used in hoverMoveEvent bisect lookup.
# Inline segment text is only rendered near 1:1 zoom; zoomed-out views keep
# bars only for performance, especially at far-right large coordinates.
# Number of bins used when pre-computing a coarse LOD summary at parse time.
# The summary is stored in BtfTrace and replaces O(N_segs) _lod_reduce calls
# with an O(4096) worst-case iteration during fit-to-view rebuilds.
_LOD_SUMMARY_BINS        = 4096
# Second-level coarse summary used for deep zoom-out rebuilds.
_LOD_SUMMARY_BINS_ULTRA  = 1024

# ---- Cursors --------------------------------------------------------------
_MAX_CURSORS         = 8  # Hard upper bound – must equal len(_CURSOR_COLORS).
_DEFAULT_MAX_CURSORS = 4  # Default number of simultaneously visible cursors.
_CURSOR_COLORS = [
    "#FF4444",  # 1 red
    "#44FF88",  # 2 green
    "#4499FF",  # 3 blue
    "#FFAA22",  # 4 amber
    "#FF44FF",  # 5 magenta
    "#44FFFF",  # 6 cyan
    "#FFFF44",  # 7 yellow
    "#CC44FF",  # 8 purple
]

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
        f'viewBox="0 0 16 16"><path fill="{color}" fill-rule="evenodd" d="{path_data}"/></svg>'
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
_IC_EXPAND     = "M3 1h1v14H3zM12 1h1v14h-1zM4 5l3 3-3 3zM12 5l-3 3 3 3z"
_IC_EXPAND_ALL = "M8 1l2.5 3h-2v3h-1V4H5.5zM8 15l-2.5-3h2v-3h1V12h2.5zM2 7.5h12v1H2z"
_IC_1TO1     = "M6.5 1a5.5 5.5 0 1 0 3.89 9.4l3.4 3.4.7-.7-3.4-3.4A5.5 5.5 0 0 0 6.5 1zm0 1a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9zM6.5 4L5.5 5h1v4h1V4z"
_IC_SETTINGS = ("M9.405 1.05c-.413-1.4-2.397-1.4-2.81 0l-.1.34a1.464 1.464 0 0 1-2.105.872l-.31-.17"
                "c-1.283-.698-2.686.705-1.987 1.987l.169.311c.446.82.023 1.841-.872 2.105l-.34.1"
                "c-1.4.413-1.4 2.397 0 2.81l.34.1a1.464 1.464 0 0 1 .872 2.105l-.17.31"
                "c-.698 1.283.705 2.686 1.987 1.987l.311-.169a1.464 1.464 0 0 1 2.105.872l.1.34"
                "c.413 1.4 2.397 1.4 2.81 0l.1-.34a1.464 1.464 0 0 1 2.105-.872l.31.17"
                "c1.283.698 2.686-.705 1.987-1.987l-.169-.311a1.464 1.464 0 0 1 .872-2.105l.34-.1"
                "c1.4-.413 1.4-2.397 0-2.81l-.34-.1a1.464 1.464 0 0 1-.872-2.105l.17-.31"
                "c.698-1.283-.705-2.686-1.987-1.987l-.311.169a1.464 1.464 0 0 1-2.105-.872l-.1-.34z"
                "M8 10.93a2.929 2.929 0 1 1 0-5.86 2.929 2.929 0 0 1 0 5.858z")

# App icon — multi-colour 72×72 SVG rendered in the About dialog header.
_APP_VERSION = "1.0.0"
_APP_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="72" height="72" viewBox="0 0 72 72">'
    '<rect x="3" y="3" width="66" height="66" rx="14" fill="#1C3A6E"/>'
    '<rect x="10" y="17" width="29" height="7" rx="3.5" fill="#5B9BD5"/>'
    '<rect x="16" y="28" width="22" height="7" rx="3.5" fill="#7EC8E3"/>'
    '<rect x="10" y="39" width="36" height="7" rx="3.5" fill="#5B9BD5"/>'
    '<rect x="20" y="50" width="18" height="7" rx="3.5" fill="#7EC8E3"/>'
    '<rect x="46" y="13" width="2" height="46" fill="#FFC107"/>'
    '<polygon points="42,13 50,13 46,20" fill="#FFC107"/>'
    '</svg>'
)

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

            parts = line.split(",", 8)
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
    _lod_timescale_per_px = _time_span / _LOD_SUMMARY_BINS  # ns per summary bin
    _lod_ultra_timescale_per_px = _time_span / _LOD_SUMMARY_BINS_ULTRA

    if progress_callback:
        progress_callback(70, "Building task LOD summaries…")
    if cancel_check and cancel_check():
        raise _ParseCancelledError()

    def _make_lod_summary(segs_sorted: list, bins: int, bin_span: float) -> list:
        """Down-sample a sorted segment list to at most *bins* entries."""
        if len(segs_sorted) <= bins:
            return segs_sorted   # already fine, skip work
        result: list = []
        prev_bin = -2
        for s in segs_sorted:
            b = int((s.start - time_min) / bin_span)
            if b != prev_bin:
                result.append(s)
                prev_bin = b
        return result

    # Task-view: start-time arrays + LOD summaries keyed by merge-key
    _seg_starts_mk:     Dict[str, list] = {}
    _seg_lod_mk:        Dict[str, list] = {}
    _seg_lod_starts_mk: Dict[str, list] = {}
    _seg_lod_ultra_mk:        Dict[str, list] = {}
    _seg_lod_ultra_starts_mk: Dict[str, list] = {}
    for _mk, _lst in segs_by_mk.items():
        _seg_starts_mk[_mk] = [s.start for s in _lst]
        _lod = _make_lod_summary(_lst, _LOD_SUMMARY_BINS, _lod_timescale_per_px)
        _seg_lod_mk[_mk]        = _lod
        _seg_lod_starts_mk[_mk] = [s.start for s in _lod]
        _lod_ultra = _make_lod_summary(_lod, _LOD_SUMMARY_BINS_ULTRA, _lod_ultra_timescale_per_px)
        _seg_lod_ultra_mk[_mk]        = _lod_ultra
        _seg_lod_ultra_starts_mk[_mk] = [s.start for s in _lod_ultra]

    if progress_callback:
        progress_callback(80, "Building core LOD summaries…")
    if cancel_check and cancel_check():
        raise _ParseCancelledError()

    # Core-view: start-time arrays + LOD summaries for core summary rows
    _core_seg_starts:     Dict[str, list] = {}
    _core_seg_lod:        Dict[str, list] = {}
    _core_seg_lod_starts: Dict[str, list] = {}
    _core_seg_lod_ultra:        Dict[str, list] = {}
    _core_seg_lod_ultra_starts: Dict[str, list] = {}
    for _c in _core_names:
        _core_seg_starts[_c] = [s.start for s in _core_segs[_c]]
        _lod = _make_lod_summary(_core_segs[_c], _LOD_SUMMARY_BINS, _lod_timescale_per_px)
        _core_seg_lod[_c]        = _lod
        _core_seg_lod_starts[_c] = [s.start for s in _lod]
        _lod_ultra = _make_lod_summary(_lod, _LOD_SUMMARY_BINS_ULTRA, _lod_ultra_timescale_per_px)
        _core_seg_lod_ultra[_c]        = _lod_ultra
        _core_seg_lod_ultra_starts[_c] = [s.start for s in _lod_ultra]

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
            _core_task_starts[_c][_tn] = [s.start for s in _tsegs]
            _lod = _make_lod_summary(_tsegs, _LOD_SUMMARY_BINS, _lod_timescale_per_px)
            _core_task_lod[_c][_tn]        = _lod
            _core_task_lod_starts[_c][_tn] = [s.start for s in _lod]
            _lod_ultra = _make_lod_summary(_lod, _LOD_SUMMARY_BINS_ULTRA, _lod_ultra_timescale_per_px)
            _core_task_lod_ultra[_c][_tn]        = _lod_ultra
            _core_task_lod_ultra_starts[_c][_tn] = [s.start for s in _lod_ultra]

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

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setTextFormat(Qt.RichText)
        self.setMargin(7)
        self._ss_applied_dark: Optional[bool] = None   # None = never applied

    def _apply_stylesheet(self, is_dark: bool) -> None:
        if self._ss_applied_dark == is_dark:
            return
        self._ss_applied_dark = is_dark
        fam = _get_fixed_font_family()
        if is_dark:
            self.setStyleSheet(
                f"QLabel {{ background:#252526; color:#E0E0E0; "
                f"border:1px solid #666; border-radius:4px; "
                f"font-size:7pt; font-family:'{fam}'; }}"
            )
        else:
            self.setStyleSheet(
                f"QLabel {{ background:#FFFFCC; color:#1E1E1E; "
                f"border:1px solid #AAAAAA; border-radius:4px; "
                f"font-size:7pt; font-family:'{fam}'; }}"
            )

    def show_at(self, screen_pos: QPoint, html: str, is_dark: bool = True) -> None:
        self._apply_stylesheet(is_dark)
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
    # Use a deterministic hash so palette selection is stable across runs.
    _key = task_merge_key(task_raw).encode("utf-8", errors="replace")
    idx = zlib.crc32(_key) % len(_PALETTE)
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
    return QPen(_task_color(task_raw).darker(130), 0.7)

@functools.lru_cache(maxsize=None)
def _blended_brush(task_raw: str, core: str) -> QBrush:
    """Cached QBrush for a task blended with a core tint."""
    return QBrush(_blended_color(task_raw, core))

@functools.lru_cache(maxsize=None)
def _blended_pen_dark(task_raw: str, core: str) -> QPen:
    """Cached dark-border QPen for a task blended with a core tint."""
    return QPen(_blended_color(task_raw, core).darker(130), 0.7)

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
        _key = (note or "").encode("utf-8", errors="replace")
        idx = zlib.crc32(_key) % len(_STI_PALETTE)
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

    At coarse zoom levels (timescale_per_px >> 1) thousands of segments are
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

def _visible_segs(lod: SegLodData, vp: ViewClipParams) -> list:
    """Return LOD-reduced, viewport-clipped segments for one timeline row/column.

    Two-path strategy for 1M-event performance:

    *Coarse path* (vp.cur_timescale_per_px >= vp.lod_timescale_per_px, i.e. zoomed out
    past the pre-built LOD summary resolution):
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
    if not lod.segs:
        return lod.segs

    if (vp.cur_timescale_per_px >= vp.lod_ultra_timescale_per_px
            and lod.lod_ultra_segs):
        if lod.lod_ultra_starts:
            lo = max(0, bisect_left(lod.lod_ultra_starts, vp.ns_lo) - 1)
            hi = min(len(lod.lod_ultra_segs), bisect_right(lod.lod_ultra_starts, vp.ns_hi) + 1)
            clipped = lod.lod_ultra_segs[lo:hi]
        else:
            clipped = lod.lod_ultra_segs
    elif vp.cur_timescale_per_px >= vp.lod_timescale_per_px and lod.lod_segs:
        # Coarse path: use pre-built LOD summary
        if lod.lod_starts:
            lo = max(0, bisect_left(lod.lod_starts, vp.ns_lo) - 1)
            hi = min(len(lod.lod_segs), bisect_right(lod.lod_starts, vp.ns_hi) + 1)
            clipped = lod.lod_segs[lo:hi]
        else:
            clipped = lod.lod_segs
    else:
        # Fine path: clip raw segment list to viewport time range
        if lod.starts:
            lo = max(0, bisect_left(lod.starts, vp.ns_lo) - 1)
            hi = min(len(lod.segs), bisect_right(lod.starts, vp.ns_hi) + 1)
            clipped = lod.segs[lo:hi]
        else:
            clipped = lod.segs

    result = _lod_reduce(clipped, vp.time_min, vp.px_per_ns, vp.offset)
    return result

def _nice_grid_step(timescale_per_px: float, target_px: float = 100.0) -> int:
    """Return a 'nice' grid step (in ns) so that one step ≈ target_px pixels."""
    ideal_ns = timescale_per_px * target_px
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
        self._timescale_per_px_default: float = _TIMESCALE_PER_PX_DEFAULT  # max zoom-in limit (ns/px)
        self._timescale_per_px     = self._timescale_per_px_default
        self._timescale_per_px_fit = float('inf')   # zoom-out limit: ns/px at fit-to-view
        # -- View state --------------------------------------------------
        self._show_sti    = True
        self._show_grid   = True
        self._view_mode   = "task"       # "task" or "core"
        self._core_expanded: Dict[str, bool] = {}   # True = expanded (default)
        self._font_size: int = FONT_SIZE            # label font size (pt)
        self._max_cursors: int = _DEFAULT_MAX_CURSORS  # max simultaneous cursors
        self._label_width: int = LABEL_WIDTH            # resizable label-column width (px)
        self._row_height: int = ROW_HEIGHT              # row height (px)
        self._row_gap:    int = ROW_GAP                 # gap between rows (px)
        self._hover_highlight: bool = _HOVER_HIGHLIGHT_ENABLED
        self._task_filter_q: str = ""
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
        # Counter of cursor-label entries appended to _frozen_top_items by
        # the most recent _draw_cursors() call.  Used to purge stale entries
        # on a direct (non-rebuild) _draw_cursors() call (e.g. cursor drag).
        self._cursor_frozen_top_count: int = 0
        # Counter of cursor-label entries appended to _frozen_items by
        # vertical-mode _draw_cursors() calls (left-edge frozen labels).
        self._cursor_frozen_left_count: int = 0
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
        self._timescale_per_px = time_span / avail
        self._timescale_per_px_fit = self._timescale_per_px   # record fit-to-view limit
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
    def timescale_per_px(self) -> float:
        return self._timescale_per_px

    @timescale_per_px.setter
    def timescale_per_px(self, v: float) -> None:
        self._timescale_per_px = max(v, self._timescale_per_px_default)
        self.rebuild()

    def set_font_size(self, size: int) -> None:
        """Change label font size (pt) and rebuild."""
        self._font_size = max(6, min(size, 24))
        self.rebuild()

    def set_max_cursors(self, n: int) -> None:
        """Set the maximum number of simultaneous cursors (4–8)."""
        self._max_cursors = max(4, min(n, _MAX_CURSORS))
        # Evict oldest cursors if the current count now exceeds the new limit.
        while len(self._cursor_times) > self._max_cursors:
            self._cursor_times.pop(0)
        self._draw_cursors()

    def set_hover_highlight(self, enabled: bool) -> None:
        """Enable or disable hover-over-label task highlighting."""
        self._hover_highlight = enabled
        if not enabled:
            self.clear_hover()

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def set_task_filter(self, text: str) -> None:
        """Filter visible task rows/columns by merge-key/raw/display name."""
        q = (text or "").strip().lower()
        if q == self._task_filter_q:
            return
        self._task_filter_q = q
        self.rebuild()

    def set_timescale_per_px_default(self, v: float) -> None:
        """Change the maximum zoom-in limit (ns/px) and rebuild if needed."""
        self._timescale_per_px_default = max(0.5, min(v, 200.0))
        if self._timescale_per_px < self._timescale_per_px_default:
            self._timescale_per_px = self._timescale_per_px_default
            self.rebuild()

    def set_label_width(self, width: int) -> None:
        """Change the Task / TaskID column width (px) and rebuild."""
        self._label_width = max(60, min(width, 600))
        self.rebuild()

    def set_row_height(self, h: int) -> None:
        """Change the row height (px) and rebuild."""
        self._row_height = max(12, min(h, 60))
        self.rebuild()

    def set_row_gap(self, g: int) -> None:
        """Change the gap between rows (px) and rebuild."""
        self._row_gap = max(0, min(g, 20))
        self.rebuild()

    def zoom(self, factor: float, center_ns: Optional[int] = None) -> None:
        new_val = self._timescale_per_px / factor
        # Clamp: don't zoom in past _TIMESCALE_PER_PX_DEFAULT or
        # zoom out past fit-to-view level.
        new_val = max(self._timescale_per_px_default, min(new_val, self._timescale_per_px_fit))
        if new_val == self._timescale_per_px:
            return  # already at limit – skip expensive rebuild
        self._timescale_per_px = new_val
        self.rebuild()

    def fit_to_width(self, viewport_width: int) -> None:
        if self._trace is None:
            return
        time_span = max(self._trace.time_max - self._trace.time_min, 1)
        avail = max(viewport_width - self._label_width, 100)
        self._timescale_per_px = time_span / avail
        self._timescale_per_px_fit = self._timescale_per_px   # update fit-to-view limit
        self.rebuild()

    # ------------------------------------------------------------------
    # Cursor API
    # ------------------------------------------------------------------

    def scene_to_ns(self, coord: float) -> int:
        """Convert a scene X (horizontal) or Y (vertical) coord to ns."""
        if self._trace is None:
            return 0
        ns = int((coord - self._label_width) * self._timescale_per_px) + self._trace.time_min
        return max(self._trace.time_min, min(self._trace.time_max, ns))

    def ns_to_scene_coord(self, ns: int) -> float:
        """Convert a timestamp to the scene X (horizontal) or Y (vertical) coordinate."""
        return self._label_width + self._ns_to_px(ns)

    def add_cursor(self, ns: int) -> None:
        """Add a cursor at timestamp *ns*. Oldest is evicted when > self._max_cursors."""
        self._cursor_times.append(ns)
        if len(self._cursor_times) > self._max_cursors:
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
        self._timescale_per_px = max(span / avail, self._timescale_per_px_default)
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

        # Purge any cursor-label entries that were appended to _frozen_top_items
        # by the previous _draw_cursors() call.  This is only needed on direct
        # calls (e.g. cursor drag); rebuild() already resets _frozen_top_items.
        if self._cursor_frozen_top_count > 0:
            if len(self._frozen_top_items) >= self._cursor_frozen_top_count:
                del self._frozen_top_items[-self._cursor_frozen_top_count:]
            self._cursor_frozen_top_count = 0
        if self._cursor_frozen_left_count > 0:
            if len(self._frozen_items) >= self._cursor_frozen_left_count:
                del self._frozen_items[-self._cursor_frozen_left_count:]
            self._cursor_frozen_left_count = 0

        if self._trace is None or not self._cursor_times:
            return

        scene_r  = self.sceneRect()
        font     = _monospace_font(self._font_size)
        font_big = _monospace_font(self._font_size + 1, QFont.Bold)
        fm_bold  = QFontMetrics(font_big)

        # Get the current scene-top so cursor labels can be registered as
        # y-frozen items (always visible in the ruler area even when the user
        # has scrolled the task rows down).
        _views = self.views()
        _scene_top = _views[0].mapToScene(QPoint(0, 0)).y() if _views else 0.0
        _scene_left = _views[0].mapToScene(QPoint(0, 0)).x() if _views else 0.0

        sorted_cursors = sorted(enumerate(self._cursor_times), key=lambda x: x[1])

        for order, (orig_idx, ns) in enumerate(sorted_cursors):
            color = QColor(_CURSOR_COLORS[orig_idx % len(_CURSOR_COLORS)])
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
                _orig_y = 2 + (orig_idx + 1) * (th + 2)
                lbl_y   = _scene_top + _orig_y
                bg = self.addRect(
                    QRectF(0, 0, tw + 4, th + 2),
                    QPen(Qt.NoPen),
                    QBrush(QColor(0, 0, 0, 180)),
                )
                bg.setZValue(31)
                bg.setPos(lbl_x - 2, lbl_y - 1)
                lbl.setPos(lbl_x, lbl_y)
                self._cursor_items.extend([bg, lbl])
                # Register label + background as y-frozen so _reposition_frozen_top
                # keeps them in the ruler area regardless of vertical scroll.
                self._frozen_top_items.append((bg, _orig_y - 1))
                self._frozen_top_items.append((lbl, _orig_y))
                self._cursor_frozen_top_count += 2

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
                # Keep vertical labels outside the frozen ruler column
                # (ruler z=35/36 would otherwise overdraw label z=31/32).
                _left_pad = RULER_WIDTH + 4
                lbl_x = _scene_left + _left_pad
                lbl_y = y + 2
                bg = self.addRect(
                    QRectF(0, 0, tw + 4, th + 2),
                    QPen(Qt.NoPen),
                    QBrush(QColor(0, 0, 0, 180)),
                )
                bg.setZValue(31)
                bg.setPos(lbl_x - 2, lbl_y - 1)
                lbl.setPos(lbl_x, lbl_y)
                self._cursor_items.extend([bg, lbl])
                # Keep vertical-mode cursor labels frozen at viewport-left.
                self._frozen_items.append((bg, _left_pad - 2))
                self._frozen_items.append((lbl, _left_pad))
                self._cursor_frozen_left_count += 2

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
        ns_lo = t_min + int((lo_coord - lw) * self._timescale_per_px)
        ns_hi = t_min + int((hi_coord - lw) * self._timescale_per_px)

        # Guard: clamp raw viewport-derived ns values to the trace bounds.
        # During zoom transitions the scroll position may not yet match the
        # new timescale_per_px (e.g. zoom_fit is called while the viewport is still
        # at the 1:1 scroll position), producing astronomically large ns_lo/hi
        # that would push _vp_ns_lo beyond t_max and leave only the very last
        # segment loaded.  If both endpoints fall outside the trace in the
        # same direction, fall back to the full trace range so the rebuild
        # always returns a useful result.
        ns_lo = max(t_min, min(t_max, ns_lo))
        ns_hi = max(t_min, min(t_max, ns_hi))
        if ns_lo >= ns_hi:
            ns_lo, ns_hi = t_min, t_max

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
            _ORTH_BUF = (self._row_height + self._row_gap) * 20
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
        self._cursor_frozen_top_count = 0
        self._cursor_frozen_left_count = 0
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

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def _ns_to_px(self, ns: int) -> float:
        return (ns - self._trace.time_min) / self._timescale_per_px

    # ------------------------------------------------------------------
    # Filtering helpers
    # ------------------------------------------------------------------

    def _task_merge_key_matches_filter(self, merge_key: str) -> bool:
        if not self._task_filter_q:
            return True
        tr = self._trace
        if tr is None:
            return True
        raw = tr.task_repr.get(merge_key, merge_key)
        disp = task_display_name(raw)
        q = self._task_filter_q
        return (q in merge_key.lower()) or (q in raw.lower()) or (q in disp.lower())

    def _task_raw_name_matches_filter(self, raw_name: str) -> bool:
        if not self._task_filter_q:
            return True
        mk = task_merge_key(raw_name)
        disp = task_display_name(raw_name)
        q = self._task_filter_q
        return (q in mk.lower()) or (q in raw_name.lower()) or (q in disp.lower())

    def _sti_channel_matches_filter(self, channel: str) -> bool:
        """Return True when *channel* or its STI notes match the active filter."""
        q = self._task_filter_q
        if not q:
            return True
        if q in channel.lower():
            return True
        tr = self._trace
        if tr is None:
            return False
        for ev in tr.sti_events_by_target.get(channel, []):
            if q in (ev.note or "").lower():
                return True
        return False

    # ------------------------------------------------------------------
    # LOD / viewport helpers (used by all four builder methods)
    # ------------------------------------------------------------------

    def _view_clip_params(self) -> ViewClipParams:
        """Build a ViewClipParams snapshot from the current scene state."""
        tr = self._trace
        return ViewClipParams(
            ns_lo=self._vp_ns_lo,
            ns_hi=self._vp_ns_hi,
            time_min=tr.time_min,
            px_per_ns=1.0 / self._timescale_per_px,
            offset=self._label_width,
            cur_timescale_per_px=self._timescale_per_px,
            lod_timescale_per_px=tr.seg_lod_timescale_per_px,
            lod_ultra_timescale_per_px=tr.seg_lod_ultra_timescale_per_px,
        )

    def _seg_lod_for_task(self, task: str) -> SegLodData:
        """Build SegLodData for a task-view merge-key."""
        tr = self._trace
        return SegLodData(
            segs=tr.seg_map_by_merge_key.get(task, []),
            starts=tr.seg_start_by_merge_key.get(task, []),
            lod_segs=tr.seg_lod_by_merge_key.get(task, []),
            lod_starts=tr.seg_lod_starts_by_merge_key.get(task, []),
            lod_ultra_segs=tr.seg_lod_ultra_by_merge_key.get(task, []),
            lod_ultra_starts=tr.seg_lod_ultra_starts_by_merge_key.get(task, []),
        )

    def _seg_lod_for_tick(self) -> SegLodData:
        """Build SegLodData for the global TICK task."""
        return self._seg_lod_for_task(task_merge_key("TICK"))

    def _seg_lod_for_core(self, core: str) -> SegLodData:
        """Build SegLodData for a core-summary row/column."""
        tr = self._trace
        return SegLodData(
            segs=tr.core_segs.get(core, []),
            starts=tr.core_seg_starts.get(core, []),
            lod_segs=tr.core_seg_lod.get(core, []),
            lod_starts=tr.core_seg_lod_starts.get(core, []),
            lod_ultra_segs=tr.core_seg_lod_ultra.get(core, []),
            lod_ultra_starts=tr.core_seg_lod_ultra_starts.get(core, []),
        )

    def _seg_lod_for_core_task(self, core: str, task_name: str) -> SegLodData:
        """Build SegLodData for a per-task sub-row/column within a core."""
        tr = self._trace
        return SegLodData(
            segs=tr.core_task_segs.get(core, {}).get(task_name, []),
            starts=tr.core_task_seg_starts.get(core, {}).get(task_name, []),
            lod_segs=tr.core_task_seg_lod.get(core, {}).get(task_name, []),
            lod_starts=tr.core_task_seg_lod_starts.get(core, {}).get(task_name, []),
            lod_ultra_segs=tr.core_task_seg_lod_ultra.get(core, {}).get(task_name, []),
            lod_ultra_starts=tr.core_task_seg_lod_ultra_starts.get(core, {}).get(task_name, []),
        )

    @staticmethod
    def _clip_sti_events(events: list, starts: list, ns_lo: int, ns_hi: int) -> list:
        """Return the viewport-visible subset of *events*.

        One extra entry is kept on each side so that events whose start
        time is just outside the viewport are still drawn (they can
        overlap into the visible area).
        """
        if not starts:
            return events
        lo = max(0, bisect_left(starts, ns_lo) - 1)
        hi = min(len(events), bisect_right(starts, ns_hi) + 1)
        return events[lo:hi]

    def _build_horizontal(self) -> None:
        trace = self._trace
        font = _monospace_font(self._font_size)
        # Use a slightly smaller font for inline segment labels so dense
        # regions remain readable across platforms with different font metrics.
        font_inline = _monospace_font(max(6, self._font_size - 1))
        fm   = QFontMetrics(font)
        fm_inline = QFontMetrics(font_inline)

        # trace.tasks is a sorted list of merge-keys.  task_repr maps
        # each merge-key to its representative raw name, which is needed
        # to resolve display names and colours.
        task_rows = [t for t in trace.tasks if self._task_merge_key_matches_filter(t)]
        sti_rows  = trace.sti_channels if self._show_sti else []
        if self._task_filter_q:
            sti_rows = [c for c in sti_rows if self._sti_channel_matches_filter(c)]
        n_task = len(task_rows)
        n_sti  = len(sti_rows)
        total_rows = n_task + n_sti
        if total_rows == 0:
            return

        time_span  = trace.time_max - trace.time_min
        timeline_w = time_span / self._timescale_per_px
        total_h = RULER_HEIGHT + total_rows * (self._row_height + self._row_gap)
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
        _ruler_grid = _RulerItem(trace, self._timescale_per_px, total_w, total_h,
                                   font, trace.time_scale, self._show_grid,
                                   horiz=True, axis_offset=self._label_width,
                                   draw_header=False)
        _ruler_grid.setZValue(0.5)
        self.addItem(_ruler_grid)
        # Header-only ruler: tick marks + labels, frozen to the top edge.
        _ruler_hdr = _RulerItem(trace, self._timescale_per_px, total_w, total_h,
                                 font, trace.time_scale, show_grid=False,
                                 horiz=True, axis_offset=self._label_width,
                                 draw_grid=False)
        _ruler_hdr.setZValue(11)
        self.addItem(_ruler_hdr)
        self._frozen_top_items.append((_ruler_hdr, 0))
        vp = self._view_clip_params()

        # --- TICK band on ruler (bottom strip) ---------------------------
        _tick_mk   = task_merge_key("TICK")
        _tick_segs = trace.seg_map_by_merge_key.get(_tick_mk, [])
        if _tick_segs:
            _ht_y        = RULER_HEIGHT - 10
            _ht_h        = 8
            _ht_data: list = []
            _ht_xs:   list = []
            for _i, _seg in enumerate(_visible_segs(self._seg_lod_for_tick(), vp)):
                _x1 = vp.offset + (_seg.start - vp.time_min) * vp.px_per_ns
                _x2 = vp.offset + (_seg.end   - vp.time_min) * vp.px_per_ns
                _w  = _x2 - _x1 if _x2 - _x1 >= MIN_SEG_WIDTH else MIN_SEG_WIDTH
                _ht_data.append((
                    QRectF(_x1, _ht_y + 1, _w, _ht_h - 2),
                    _task_brush(_seg.task), _task_pen_dark(_seg.task), _seg,
                ))
                _ht_xs.append((_x1, _x1 + _w, _i))
            _ht_batch = _BatchRowItem(
                QRectF(vp.offset, _ht_y, timeline_w, _ht_h),
                _ht_data, trace.time_scale, xs=_ht_xs,
                time_min=trace.time_min)
            _ht_batch.setZValue(12)   # above frozen ruler_bg+header
            self.addItem(_ht_batch)
            self._frozen_top_items.append((_ht_batch, 0))

        # Shared colors/pens/brushes hoisted out of loops
        _bg_even     = QBrush(QColor("#252526"))
        _bg_odd      = QBrush(QColor("#2D2D2D"))
        _sep_pen     = QPen(QColor("#333333"), 0.5)
        _lbl_color   = QColor("#D4D4D4")
        _seg_white   = QBrush(QColor("#FFFFFF"))
        _pen_hl      = QPen(QColor("#FFFFFF"), 1.5)
        _stripe_rows: list = []   # accumulated by task + STI loops → one _RowStripesItem

        # --- Task rows ---------------------------------------------------
        # Compute first/last visible row indices from the cached orth bounds.
        # This avoids iterating all n_task rows just to skip ~95 % of them.
        _row_stride   = self._row_height + self._row_gap
        _first_vis    = max(0, int((self._vp_scene_orth_lo - RULER_HEIGHT) // _row_stride))
        _last_vis     = min(n_task - 1, int((self._vp_scene_orth_hi - RULER_HEIGHT) // _row_stride) + 1)
        _time_min     = vp.time_min
        _px_per_ns    = vp.px_per_ns
        lw            = self._label_width
        _vp_ns_lo     = vp.ns_lo
        _vp_ns_hi     = vp.ns_hi
        for row_idx in range(_first_vis, _last_vis + 1):
            task  = task_rows[row_idx]
            raw   = trace.task_repr.get(task, task)
            y_top = RULER_HEIGHT + row_idx * _row_stride
            y_ctr = y_top + self._row_height / 2
            is_hl = (task == self._locked_task)
            disp      = task_display_name(raw)
            row_color = _task_color(raw)
            self._task_row_rects[task] = [(QRectF(lw, y_top, timeline_w, self._row_height), row_color)]

            _stripe_rows.append((y_top, self._row_height, self._row_gap,
                                 _bg_even if row_idx % 2 == 0 else _bg_odd, _sep_pen))
            if is_hl:
                hl_bg = QColor(row_color.red(), row_color.green(), row_color.blue(), 35)
                hl_border = QPen(row_color.lighter(160), 1.0)
                self.addRect(QRectF(lw, y_top, timeline_w, self._row_height),
                             hl_border, QBrush(hl_bg)).setZValue(0.9)

            # Clickable label background
            lbl_bg = _TaskLabelItem(QRectF(0, y_top, lw, self._row_height), task, self,
                                    tooltip_text=disp)
            lbl_bg.setZValue(36)
            self.addItem(lbl_bg)
            self._frozen_items.append((lbl_bg, 0))

            lbl_color    = QColor("#FFD700") if is_hl else _lbl_color
            lbl_font     = _monospace_font(self._font_size, QFont.Bold) if is_hl else font
            _lbl_avail_w = max(0, lw - 4 - 4)   # left=4, right margin=4
            _lbl_fm      = QFontMetrics(lbl_font) if is_hl else fm
            _lbl_elided  = _lbl_fm.elidedText(disp, Qt.ElideRight, _lbl_avail_w)
            lbl = self.addSimpleText(_lbl_elided, lbl_font)
            lbl.setBrush(QBrush(lbl_color))
            lbl.setPos(4, y_ctr - fm.height() / 2)
            lbl.setZValue(37)
            self._frozen_items.append((lbl, 4))

            pen_hl     = _pen_hl
            seg_data: list = []
            xs:      list = []
            for i_s, seg in enumerate(_visible_segs(self._seg_lod_for_task(task), vp)):
                x1 = lw + (seg.start - _time_min) * _px_per_ns
                x2 = lw + (seg.end   - _time_min) * _px_per_ns
                w  = x2 - x1 if x2 - x1 >= MIN_SEG_WIDTH else MIN_SEG_WIDTH
                seg_data.append((
                    QRectF(x1, y_top + 1, w, self._row_height - 2),
                    _blended_brush(seg.task, seg.core),
                    pen_hl if is_hl else _blended_pen_dark(seg.task, seg.core),
                    seg,
                ))
                xs.append((x1, x1 + w, i_s))
            batch = _BatchRowItem(
                QRectF(lw, y_top, timeline_w, self._row_height),
                seg_data, trace.time_scale,
                label_font=font_inline, label_fm=fm_inline, label_text=disp,
                xs=xs, time_min=trace.time_min, timescale_per_px=self._timescale_per_px)
            batch.setZValue(1)
            self.addItem(batch)

            # Task-create marker: 1px vertical line at the creation timestamp
            _ct_h = trace.task_create_times.get(task)
            if _ct_h is not None:
                _cx = lw + (_ct_h - _time_min) * _px_per_ns
                _cl = self.addLine(_cx, y_top, _cx, y_top + self._row_height,
                                   QPen(row_color, 1))
                _cl.setZValue(2.5)
        # One row per STI channel containing one _BatchStiItem with all
        # events for that channel, sorted by time (ascending scene_x).
        _sti_bg = QBrush(QColor("#1A1A2E"))
        for sti_idx, channel in enumerate(sti_rows):
            row_idx = n_task + sti_idx
            y_top   = RULER_HEIGHT + row_idx * (self._row_height + self._row_gap)
            y_ctr   = y_top + self._row_height / 2
            _stripe_rows.append((y_top, self._row_height, self._row_gap, _sti_bg, None))
            lbl = self.addSimpleText(
                fm.elidedText(channel, Qt.ElideRight, max(0, lw - 4 - 4)), font)
            lbl.setBrush(QBrush(QColor("#88AABB")))
            lbl.setPos(4, y_ctr - fm.height() / 2)
            lbl.setZValue(37)
            self._frozen_items.append((lbl, 4))
            _sti_evs_h  = trace.sti_events_by_target.get(channel, [])
            _sti_stts_h = trace.sti_starts_by_target.get(channel, [])
            _sti_evs_h  = self._clip_sti_events(_sti_evs_h, _sti_stts_h, _vp_ns_lo, _vp_ns_hi)
            _sti_markers = [
                (lw + (ev.time - _time_min) * _px_per_ns, _sti_color(ev.note), ev)
                for ev in _sti_evs_h
            ]
            _sti_item = _BatchStiItem(
                QRectF(lw, y_top, timeline_w, self._row_height),
                _sti_markers, trace.time_scale, horizontal=True, axis=y_ctr,
                time_min=trace.time_min)
            _sti_item.setZValue(2)
            self.addItem(_sti_item)

        if _stripe_rows:
            _stripes = _RowStripesItem(
                QRectF(0, RULER_HEIGHT, total_w, total_h - RULER_HEIGHT),
                _stripe_rows, lw, total_w)
            _stripes.setZValue(0)
            self.addItem(_stripes)

        # --- Frozen label column header ----------------------------------
        # Drawn last so it sits on top of all other frozen items (z=38-39).
        _has_tick_h = bool(trace.seg_map_by_merge_key.get(_tick_mk, []))
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
        # Keep inline labels one size smaller for better visibility on
        # high-DPI and wider-metric monospace fonts.
        font_inline = _monospace_font(max(6, self._font_size - 1))
        fm   = QFontMetrics(font)
        fm_inline = QFontMetrics(font_inline)

        # trace.tasks is a sorted list of merge-keys.  task_repr maps
        # each merge-key to its representative raw name.
        task_cols = [t for t in trace.tasks if self._task_merge_key_matches_filter(t)]
        sti_cols  = trace.sti_channels if self._show_sti else []
        if self._task_filter_q:
            sti_cols = [c for c in sti_cols if self._sti_channel_matches_filter(c)]
        n_task = len(task_cols)
        n_sti  = len(sti_cols)
        total_cols = n_task + n_sti
        if total_cols == 0:
            return

        col_w       = max(self._row_height + self._row_gap, 26)
        label_row_h = self._label_width
        time_span   = trace.time_max - trace.time_min
        timeline_h  = time_span / self._timescale_per_px
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
        _label_row_bg.setZValue(35)  # above cursor lines (z=30-32), same as ruler column
        self._frozen_top_items.append((_label_row_bg, 0))

        # Grid-only ruler: horizontal lines at absolute Y positions (not frozen).
        _ruler_grid = _RulerItem(trace, self._timescale_per_px, total_w, total_h,
                                   font, trace.time_scale, self._show_grid,
                                   horiz=False, axis_offset=label_row_h,
                                   draw_header=False)
        _ruler_grid.setZValue(0.5)
        self.addItem(_ruler_grid)
        # Header-only ruler: tick marks + labels, frozen to left edge.
        _ruler_hdr = _RulerItem(trace, self._timescale_per_px, total_w, total_h,
                                  font, trace.time_scale, show_grid=False,
                                  horiz=False, axis_offset=label_row_h,
                                  draw_grid=False)
        _ruler_hdr.setZValue(36)
        self.addItem(_ruler_hdr)
        self._frozen_items.append((_ruler_hdr, 0))
        vp = self._view_clip_params()

        # --- TICK band on ruler (right strip of ruler column) ------------
        _tick_mk   = task_merge_key("TICK")
        _tick_segs = trace.seg_map_by_merge_key.get(_tick_mk, [])
        _has_tick_v = bool(_tick_segs)
        if _has_tick_v:
            _vt_x        = RULER_WIDTH - 18
            _vt_w        = 14
            _vt_data: list = []
            _vt_xs:   list = []
            for _i, _seg in enumerate(_visible_segs(self._seg_lod_for_tick(), vp)):
                _y1 = label_row_h + (_seg.start - vp.time_min) * vp.px_per_ns
                _y2 = label_row_h + (_seg.end   - vp.time_min) * vp.px_per_ns
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

        # --- Task columns ------------------------------------------------
        _bg_even   = QBrush(QColor("#252526"))
        _bg_odd    = QBrush(QColor("#2D2D2D"))
        _lbl_color = QColor("#D4D4D4")
        _pen_hl_v  = QPen(QColor("#FFFFFF"), 1.5)
        _time_min  = vp.time_min
        _px_per_ns = vp.px_per_ns
        _vp_ns_lo  = vp.ns_lo
        _vp_ns_hi  = vp.ns_hi

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

            lbl_color    = QColor("#FFD700") if is_hl else _lbl_color
            lbl_font     = _monospace_font(self._font_size, QFont.Bold) if is_hl else font
            _lbl_avail_v = max(0, label_row_h - 14)
            _lbl_fm_v    = QFontMetrics(lbl_font) if is_hl else fm
            _lbl_disp_v  = _lbl_fm_v.elidedText(disp, Qt.ElideRight, _lbl_avail_v)
            lbl = self.addSimpleText(_lbl_disp_v, lbl_font)
            lbl.setBrush(QBrush(lbl_color))
            lbl.setRotation(-90)
            lbl.setPos(x_left + col_w / 2 - fm.height() / 2, label_row_h - 10)
            lbl.setZValue(37)
            self._frozen_top_items.append((lbl, lbl.pos().y()))

            pen_hl      = _pen_hl_v
            seg_data: list = []
            xs:      list = []
            for i_s, seg in enumerate(_visible_segs(self._seg_lod_for_task(task), vp)):
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
                label_font=font_inline, label_fm=fm_inline, label_text=disp,
                xs=xs, time_min=trace.time_min, timescale_per_px=self._timescale_per_px)
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
            lbl.setPos(x_left + col_w / 2 - fm.height() / 2, label_row_h - 10)
            lbl.setZValue(37)
            self._frozen_top_items.append((lbl, lbl.pos().y()))
            _sti_evs_v  = trace.sti_events_by_target.get(channel, [])
            _sti_stts_v = trace.sti_starts_by_target.get(channel, [])
            _sti_evs_v  = self._clip_sti_events(_sti_evs_v, _sti_stts_v, _vp_ns_lo, _vp_ns_hi)
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
        _vt_corner_rect = self.addRect(QRectF(0, 0, RULER_WIDTH, label_row_h),
                                       QPen(Qt.NoPen), QBrush(QColor("#1A1A1A")))
        _vt_corner_rect.setZValue(40)   # above ruler (35-37) and label row (10-37)
        self._frozen_items.append((_vt_corner_rect, 0))
        self._frozen_top_items.append((_vt_corner_rect, 0))
        if _has_tick_v:
            _tick_vlbl = self.addSimpleText("TICK", font)
            _tick_vlbl.setBrush(QBrush(QColor("#E8C84A")))
            _tick_vlbl.setRotation(-90)
            _vband_cx  = (RULER_WIDTH - 18) + 14 / 2
            _tick_vlbl.setPos(_vband_cx - fm.height() / 2, label_row_h - 10)
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
        fm_sm   = QFontMetrics(font_sm)

        # Use pre-built core data cached at parse time (O(1), no segment iteration)
        core_names           = trace.core_names
        core_segs            = trace.core_segs
        core_tasks           = trace.core_task_order
        sti_rows             = trace.sti_channels if self._show_sti else []
        if self._task_filter_q:
            sti_rows = [c for c in sti_rows if self._sti_channel_matches_filter(c)]

        if self._task_filter_q:
            _filtered_core_names = []
            _filtered_core_tasks = {}
            for _core in core_names:
                _tasks = [t for t in core_tasks[_core] if self._task_raw_name_matches_filter(t)]
                if _tasks:
                    _filtered_core_names.append(_core)
                    _filtered_core_tasks[_core] = _tasks
            core_names = _filtered_core_names
            core_tasks = _filtered_core_tasks

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
        timeline_w = time_span / self._timescale_per_px
        total_h    = RULER_HEIGHT + total_rows * (self._row_height + self._row_gap)
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
        _ruler_grid = _RulerItem(trace, self._timescale_per_px, total_w, total_h,
                                   font, trace.time_scale, self._show_grid,
                                   horiz=True, axis_offset=self._label_width,
                                   draw_header=False)
        _ruler_grid.setZValue(0.5)
        self.addItem(_ruler_grid)
        # Header-only ruler (frozen by Y — always visible at viewport top).
        _ruler_hdr = _RulerItem(trace, self._timescale_per_px, total_w, total_h,
                                 font, trace.time_scale, show_grid=False,
                                 horiz=True, axis_offset=self._label_width,
                                 draw_grid=False)
        _ruler_hdr.setZValue(11)
        self.addItem(_ruler_hdr)
        self._frozen_top_items.append((_ruler_hdr, 0))

        _time_min  = trace.time_min
        _px_per_ns = 1.0 / self._timescale_per_px
        lw         = self._label_width
        _vp_ns_lo  = self._vp_ns_lo
        _vp_ns_hi  = self._vp_ns_hi
        vp = self._view_clip_params()
        # --- TICK band: TICK segments overlaid on the bottom strip of the ruler ---
        if _has_tick:
            _tb_y = RULER_HEIGHT - 10   # y of TICK band within ruler (bottom 10 px)
            _tb_h = 8                   # height of TICK band
            _tick_seg_data: list = []
            _tick_xs:       list = []
            for i_s, seg in enumerate(_visible_segs(self._seg_lod_for_tick(), vp)):
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

            y_top = RULER_HEIGHT + row_idx * (self._row_height + self._row_gap)
            y_ctr = y_top + self._row_height / 2
            row_idx += 1   # advance immediately, independent of viewport cull

            _core_in_vp = not (y_top + self._row_height < self._vp_scene_orth_lo
                               or y_top > self._vp_scene_orth_hi)
            if _core_in_vp:
                self.addRect(QRectF(lw, y_top, timeline_w, self._row_height),
                             QPen(Qt.NoPen), QBrush(QColor("#2A2A3E"))).setZValue(0)
                self.addLine(0, y_top + self._row_height + self._row_gap - 1,
                             total_w, y_top + self._row_height + self._row_gap - 1,
                             QPen(QColor("#444466"), 0.8)).setZValue(0.5)

                hdr_item = _CoreHeaderItem(
                    QRectF(0, y_top, lw, self._row_height), core, self)
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
                                 if (_tn := parse_task_name(s.task)[2]) != "TICK"
                                 and not _tn.startswith("IDLE"))
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
                for i_s, seg in enumerate(_visible_segs(self._seg_lod_for_core(core), vp)):
                    x1 = lw + (seg.start - _time_min) * _px_per_ns
                    x2 = lw + (seg.end   - _time_min) * _px_per_ns
                    w  = x2 - x1 if x2 - x1 >= MIN_SEG_WIDTH else MIN_SEG_WIDTH
                    seg_data.append((
                        QRectF(x1, y_top + 2, w, self._row_height - 4),
                        _task_brush(seg.task), _task_pen_dark(seg.task), seg,
                    ))
                    xs.append((x1, x1 + w, i_s))
                batch = _BatchRowItem(
                    QRectF(lw, y_top, timeline_w, self._row_height),
                    seg_data, trace.time_scale,
                    xs=xs, time_min=trace.time_min)
                batch.setZValue(1)
                self.addItem(batch)

            if not expanded:
                continue

            # -- Per-task sub-rows (only when this core is expanded) -------

            # Bulk-skip: if the entire sub-row block for this core lies
            # completely outside the viewport, advance row_idx in one step
            # and skip the O(n_tasks) inner loop entirely.
            n_tasks = len(tasks)
            if n_tasks:
                _first_y2 = RULER_HEIGHT + row_idx * (self._row_height + self._row_gap)
                _last_y2  = _first_y2 + (n_tasks - 1) * (self._row_height + self._row_gap)
                if (_last_y2 + self._row_height < self._vp_scene_orth_lo
                        or _first_y2 > self._vp_scene_orth_hi):
                    row_idx += n_tasks
                    continue

            for sub_idx, task_name in enumerate(tasks):
                y_top2 = RULER_HEIGHT + row_idx * (self._row_height + self._row_gap)
                row_idx += 1   # always advance before any early continue

                # Orth-cull: skip ALL item creation for off-screen sub-rows.
                if y_top2 + self._row_height < self._vp_scene_orth_lo or y_top2 > self._vp_scene_orth_hi:
                    continue

                y_ctr2 = y_top2 + self._row_height / 2
                _tmk   = task_merge_key(task_name)
                is_hl  = (_tmk == self._locked_task)

                sub_bg = QColor("#1E1E2C") if sub_idx % 2 == 0 else QColor("#232330")
                self.addRect(QRectF(lw, y_top2, timeline_w, self._row_height),
                             QPen(Qt.NoPen), QBrush(sub_bg)).setZValue(0)
                _row_color = _task_color(task_name)
                self._task_row_rects.setdefault(_tmk, []).append(
                    (QRectF(lw, y_top2, timeline_w, self._row_height), _row_color))
                if is_hl:
                    hl_bg = QColor(_row_color.red(), _row_color.green(), _row_color.blue(), 35)
                    self.addRect(QRectF(lw, y_top2, timeline_w, self._row_height),
                                 QPen(_row_color.lighter(160), 1.0), QBrush(hl_bg)).setZValue(0.9)
                self.addLine(0, y_top2 + self._row_height + self._row_gap - 1,
                             total_w, y_top2 + self._row_height + self._row_gap - 1,
                             QPen(QColor("#2E2E3A"), 0.5)).setZValue(0.5)

                stripe = self.addRect(QRectF(26, y_top2 + 3, 3, self._row_height - 6),
                                      QPen(Qt.NoPen), QBrush(_row_color))
                stripe.setZValue(36)
                self._frozen_items.append((stripe, 0))

                # Clickable label background for sub-task row
                disp      = task_display_name(task_name)
                sub_lbl_bg = _TaskLabelItem(
                    QRectF(0, y_top2, lw, self._row_height), _tmk, self,
                    tooltip_text=disp)
                sub_lbl_bg.setZValue(36)
                self.addItem(sub_lbl_bg)
                self._frozen_items.append((sub_lbl_bg, 0))
                lbl_color = QColor("#FFD700") if is_hl else QColor("#B0B0C0")
                lbl_fnt   = _monospace_font(self._font_size,
                                            QFont.Bold) if is_hl else font
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
                        self._seg_lod_for_core_task(core, task_name), vp)):
                    x1 = lw + (seg.start - _time_min) * _px_per_ns
                    x2 = lw + (seg.end   - _time_min) * _px_per_ns
                    w  = x2 - x1 if x2 - x1 >= MIN_SEG_WIDTH else MIN_SEG_WIDTH
                    seg_data.append((
                        QRectF(x1, y_top2 + 1, w, self._row_height - 2),
                        _task_br_cs,
                        pen_hl if is_hl else _task_pen_cs,
                        seg,
                    ))
                    xs.append((x1, x1 + w, i_s))
                batch = _BatchRowItem(
                    QRectF(lw, y_top2, timeline_w, self._row_height),
                    seg_data, trace.time_scale,
                    label_font=font_sm, label_fm=fm_sm, label_text=disp,
                    xs=xs, time_min=trace.time_min, timescale_per_px=self._timescale_per_px)
                batch.setZValue(1)
                self.addItem(batch)

        # --- STI rows ---------------------------------------------------
        for channel in sti_rows:
            y_top = RULER_HEIGHT + row_idx * (self._row_height + self._row_gap)
            y_ctr = y_top + self._row_height / 2
            self.addRect(QRectF(lw, y_top, timeline_w, self._row_height),
                         QPen(Qt.NoPen), QBrush(QColor("#1A1A2E"))).setZValue(0)
            lbl = self.addSimpleText(
                fm.elidedText(channel, Qt.ElideRight, max(0, lw - 4 - 4)), font)
            lbl.setBrush(QBrush(QColor("#88AABB")))
            lbl.setPos(4, y_ctr - fm.height() / 2)
            lbl.setZValue(37)
            self._frozen_items.append((lbl, 4))
            _sti_evs_ch  = trace.sti_events_by_target.get(channel, [])
            _sti_stts_ch = trace.sti_starts_by_target.get(channel, [])
            _sti_evs_ch  = self._clip_sti_events(_sti_evs_ch, _sti_stts_ch, _vp_ns_lo, _vp_ns_hi)
            _sti_markers_ch = [
                (lw + (ev.time - _time_min) * _px_per_ns, _sti_color(ev.note), ev)
                for ev in _sti_evs_ch
            ]
            _sti_item_ch = _BatchStiItem(
                QRectF(lw, y_top, timeline_w, self._row_height),
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
        fm_sm   = QFontMetrics(font_sm)

        # Use pre-built core data cached at parse time (O(1), no segment iteration)
        core_names           = trace.core_names
        core_segs            = trace.core_segs
        core_tasks           = trace.core_task_order
        sti_cols             = trace.sti_channels if self._show_sti else []
        if self._task_filter_q:
            sti_cols = [c for c in sti_cols if self._sti_channel_matches_filter(c)]

        if self._task_filter_q:
            _filtered_core_names = []
            _filtered_core_tasks = {}
            for _core in core_names:
                _tasks = [t for t in core_tasks[_core] if self._task_raw_name_matches_filter(t)]
                if _tasks:
                    _filtered_core_names.append(_core)
                    _filtered_core_tasks[_core] = _tasks
            core_names = _filtered_core_names
            core_tasks = _filtered_core_tasks

        # TICK is a global event — shown as a band in the ruler column.
        _tick_mk   = task_merge_key("TICK")
        _tick_segs = trace.seg_map_by_merge_key.get(_tick_mk, [])
        _has_tick  = bool(_tick_segs)

        def _col_count(c: str) -> int:
            return 1 + (len(core_tasks[c]) if self._core_expanded.get(c, True) else 0)

        total_cols = sum(_col_count(c) for c in core_names) + len(sti_cols)
        if total_cols == 0:
            return

        col_w       = max(self._row_height + self._row_gap, 26)
        label_row_h = self._label_width
        time_span   = trace.time_max - trace.time_min
        timeline_h  = time_span / self._timescale_per_px
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
        _ruler_grid_c = _RulerItem(trace, self._timescale_per_px, total_w, total_h,
                                     font, trace.time_scale, self._show_grid,
                                     horiz=False, axis_offset=label_row_h,
                                     draw_header=False)
        _ruler_grid_c.setZValue(0.5)
        self.addItem(_ruler_grid_c)
        # Header-only ruler: tick marks + labels, frozen to left edge.
        _ruler_hdr_c = _RulerItem(trace, self._timescale_per_px, total_w, total_h,
                                    font, trace.time_scale, show_grid=False,
                                    horiz=False, axis_offset=label_row_h,
                                    draw_grid=False)
        _ruler_hdr_c.setZValue(36)
        self.addItem(_ruler_hdr_c)
        self._frozen_items.append((_ruler_hdr_c, 0))

        _time_min  = trace.time_min
        _px_per_ns = 1.0 / self._timescale_per_px
        _vp_ns_lo  = self._vp_ns_lo
        _vp_ns_hi  = self._vp_ns_hi
        vp = self._view_clip_params()

        # --- TICK band: TICK segments overlaid on the right strip of the ruler column ---
        if _has_tick:
            _vtb_x = RULER_WIDTH - 18   # x of TICK band within ruler (right edge strip)
            _vtb_w = 14                 # width of TICK band
            _tick_seg_data_v: list = []
            _tick_xs_v:       list = []
            for i_s, seg in enumerate(_visible_segs(self._seg_lod_for_tick(), vp)):
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
                _lbl_avail_c = max(0, label_row_h - 14)
                arr_label = QFontMetrics(font).elidedText(arr_label, Qt.ElideRight, _lbl_avail_c)
                arr_txt = self.addSimpleText(arr_label, font)
                arr_txt.setBrush(QBrush(QColor("#9999CC")))
                arr_txt.setRotation(-90)
                arr_txt.setPos(x_left + col_w / 2 - fm.height() / 2, label_row_h - 10)
                arr_txt.setZValue(37)
                arr_txt.setAcceptedMouseButtons(Qt.NoButton)
                arr_txt.setAcceptHoverEvents(False)
                self._frozen_top_items.append((arr_txt, arr_txt.pos().y()))

                seg_data: list = []
                xs:       list = []
                for i_s, seg in enumerate(_visible_segs(self._seg_lod_for_core(core), vp)):
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
                lbl_fnt   = _monospace_font(self._font_size,
                                            QFont.Bold) if is_hl else font
                t_lbl = self.addSimpleText(disp, lbl_fnt)
                t_lbl.setBrush(QBrush(lbl_color))
                t_lbl.setRotation(-90)
                t_lbl.setPos(x_left2 + col_w / 2 - fm.height() / 2, label_row_h - 10)
                t_lbl.setZValue(37)
                self._frozen_top_items.append((t_lbl, t_lbl.pos().y()))

                pen_hl       = QPen(QColor("#FFFFFF"), 1.5)
                _task_pen_cs = _task_pen_dark(task_name)
                _task_br_cs  = _task_brush(task_name)
                seg_data: list = []
                xs:       list = []
                for i_s, seg in enumerate(_visible_segs(
                        self._seg_lod_for_core_task(core, task_name), vp)):
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
                    label_font=font_sm, label_fm=fm_sm, label_text=disp,
                    xs=xs, time_min=trace.time_min, timescale_per_px=self._timescale_per_px)
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
            lbl.setPos(x_left + col_w / 2 - fm.height() / 2, label_row_h - 10)
            lbl.setZValue(37)
            self._frozen_top_items.append((lbl, lbl.pos().y()))
            _x_ctr_vc    = x_left + col_w / 2
            _sti_evs_vc  = trace.sti_events_by_target.get(channel, [])
            _sti_stts_vc = trace.sti_starts_by_target.get(channel, [])
            _sti_evs_vc  = self._clip_sti_events(_sti_evs_vc, _sti_stts_vc, _vp_ns_lo, _vp_ns_hi)
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

    def __init__(self, trace, timescale_per_px: float,
                 total_w: float, total_h: float,
                 font: QFont, time_scale,
                 show_grid: bool, horiz: bool,
                 axis_offset: float,
                 draw_header: bool = True, draw_grid: bool = True):
        super().__init__()
        self._trace       = trace
        self._npp         = timescale_per_px
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

class _RowStripesItem(QGraphicsItem):
    """Draws N row background rectangles and optional separator lines in one pass.

    Replaces 2×N individual QGraphicsRectItem/QGraphicsLineItem scene items with
    a single item, eliminating PyQt bridge-call overhead that accumulates during
    rebuild when many rows are visible simultaneously.

    rows: sequence of (y_top, row_h, gap, brush, sep_pen_or_None)
        sep_pen_or_None — QPen for a horizontal line at y = y_top+row_h+gap-1,
                          or None to omit the separator for that row.
    """

    def __init__(self, bounding_rect: QRectF, rows: list,
                 timeline_x: float, total_w: float) -> None:
        super().__init__()
        self._bounding_rect = bounding_rect
        self._rows       = rows          # [(y_top, row_h, gap, brush, sep_pen|None)]
        self._timeline_x = timeline_x   # x where background rect starts (= label_width)
        self._total_w    = total_w       # full scene width (for separator lines)
        self.setFlag(QGraphicsItem.ItemUsesExtendedStyleOption, True)

    def boundingRect(self) -> QRectF:
        return self._bounding_rect

    def paint(self, painter, option, widget=None) -> None:
        rows = self._rows
        if not rows:
            return
        exposed = option.exposedRect
        exp_top = exposed.top()
        exp_bot = exposed.bottom()
        tx      = self._timeline_x
        tw      = self._total_w - tx
        # Binary-search to first row that may intersect the exposed rect.
        lo, hi = 0, len(rows)
        while lo < hi:
            mid = (lo + hi) >> 1
            y_top, row_h, gap, _, _ = rows[mid]
            if y_top + row_h + gap <= exp_top:
                lo = mid + 1
            else:
                hi = mid
        # --- Background rectangles (no pen) ---
        painter.setPen(Qt.NoPen)
        last_brush = None
        sep_rows: list = []
        for i in range(lo, len(rows)):
            y_top, row_h, gap, brush, sep_pen = rows[i]
            if y_top > exp_bot:
                break
            if brush is not last_brush:
                painter.setBrush(brush)
                last_brush = brush
            painter.drawRect(QRectF(tx, y_top, tw, row_h))
            if sep_pen is not None:
                sep_rows.append((y_top + row_h + gap - 1, sep_pen))
        # --- Separator lines ---
        total_w  = self._total_w
        last_pen = None
        for sep_y, sep_pen in sep_rows:
            if sep_pen is not last_pen:
                painter.setPen(sep_pen)
                painter.setBrush(Qt.NoBrush)
                last_pen = sep_pen
            painter.drawLine(QLineF(0, sep_y, total_w, sep_y))

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
                 time_min: int = 0, timescale_per_px: float = 0.0):
        super().__init__()
        self._bounding_rect = bounding_rect
        self._seg_data      = seg_data      # [(QRectF, QBrush, QPen, seg|None)]
        self._time_scale    = time_scale
        self._time_min      = time_min
        self._timescale_per_px     = timescale_per_px
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
        horiz  = self._horiz
        result = []
        r0, br0, pen0, seg0 = data[0]
        s0 = r0.x()       if horiz else r0.y()
        e0 = s0 + (r0.width() if horiz else r0.height())
        for r, br, pen, seg in data[1:]:
            s = r.x()     if horiz else r.y()
            e = s + (r.width() if horiz else r.height())
            if s <= e0 + _LOD_MERGE_PX:
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
        _wt0 = painter.worldTransform()
        _m11_0 = _wt0.m11()
        _scene_left = (-_wt0.dx() / _m11_0) if _m11_0 != 0.0 else -_wt0.dx()
        painter.save()

        if lod < _PAINT_LOD_MICRO:
            # ---- Tier 1: micro LOD -----------------------------------------------
            # Row is so compressed that individual segments are meaningless.
            # Draw a single tinted activity bar to indicate presence.
            if self._seg_data:
                br   = self._bounding_rect
                col  = QColor(self._seg_data[0][1].color())
                col.setAlpha(_ACTIVITY_ALPHA)
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

        if lod < _PAINT_LOD_COARSE:
            # ---- Tier 2: coarse LOD ----------------------------------------------
            # Use pre-merged coarse_data.  rebuild() already clips to ±1.5×
            # the viewport so painting all coarse entries is safe.
            painter.setPen(Qt.NoPen)
            _rebase = (abs(option.exposedRect.left()) > 2_000_000.0) if self._horiz else (abs(option.exposedRect.top()) > 2_000_000.0)
            if _rebase:
                painter.save()
                if self._horiz:
                    painter.translate(-option.exposedRect.left(), 0.0)
                else:
                    painter.translate(0.0, -option.exposedRect.top())
            last_brush = None
            for rect, brush, _, _seg in self._coarse_data:
                if brush is not last_brush:
                    painter.setBrush(brush)
                    last_brush = brush
                painter.drawRect(rect)
            if _rebase:
                painter.restore()
            painter.restore()
            return

        # ---- Tier 3: full detail ------------------------------------------------
        # rebuild() already pre-clips segments to ±1.5× the viewport, so
        # painting all of _seg_data is safe and correct.
        seg_slice = self._seg_data
        _rebase = (abs(option.exposedRect.left()) > 2_000_000.0) if self._horiz else (abs(option.exposedRect.top()) > 2_000_000.0)
        if _rebase:
            painter.save()
            if self._horiz:
                painter.translate(-option.exposedRect.left(), 0.0)
            else:
                painter.translate(0.0, -option.exposedRect.top())
        last_brush = None
        last_pen   = None
        for rect, brush, pen, _seg in seg_slice:
            if brush is not last_brush:
                painter.setBrush(brush)
                last_brush = brush
            if pen is not last_pen:
                painter.setPen(pen)
                last_pen = pen
            painter.drawRect(rect)
        if _rebase:
            painter.restore()
        # Inline text labels – second pass to minimise font/pen switches.
        if self._label_font and self._label_text and self._label_fm:
            painter.setPen(QPen(QColor("#FFFFFF")))
            painter.setFont(self._label_font)
            txt = self._label_text
            adv = self._label_adv
            fm  = self._label_fm
            # Compute the minimum scene coordinate at which text is visible.
            # When a long segment starts to the left (or above) the frozen
            # label column the text_origin would be off-screen; clamping it to
            # the label-column boundary keeps the label visible whenever the
            # segment intersects the current viewport.
            _wt    = painter.worldTransform()
            _m11   = _wt.m11()
            _m22   = _wt.m22()
            _vp_left = (-_wt.dx() / _m11) if _m11 != 0.0 else -_wt.dx()
            _vp_top  = (-_wt.dy() / _m22) if _m22 != 0.0 else -_wt.dy()
            # Clip text to the visible timeline content area in scene coords.
            # Adding viewport origin to row origin over-shifts the clamp and
            # makes labels disappear after horizontal/vertical scrolling.
            _content_left = max(_vp_left, self._bounding_rect.x())
            _content_top  = max(_vp_top,  self._bounding_rect.y())
            if self._horiz:
                # Fast path: draw in scene coordinates.
                # Precision path: when scene X is very large, switch to device
                # coordinates to avoid float precision loss in Qt text layout.
                _wt = painter.worldTransform()
                _use_device_text = abs(_content_left) > 2_000_000.0
                if _use_device_text:
                    painter.save()
                    painter.resetTransform()

                def _draw_text(scene_rect: QRectF, draw_txt: str) -> None:
                    if _use_device_text:
                        painter.drawText(_wt.mapRect(scene_rect),
                                         Qt.AlignVCenter | Qt.AlignLeft,
                                         draw_txt)
                    else:
                        painter.drawText(scene_rect,
                                         Qt.AlignVCenter | Qt.AlignLeft,
                                         draw_txt)

                any_label_drawn = False
                best_slot = None  # (text_w, text_x, rect)
                for rect, _, _, _seg in seg_slice:
                    vis_rect = rect.intersected(option.exposedRect)
                    if vis_rect.isEmpty():
                        continue
                    # Clamp text start to visible content area.
                    text_x = max(vis_rect.x() + 2.0, _content_left)
                    text_w = vis_rect.right() - 2.0 - text_x
                    if text_w <= 4.0:
                        continue
                    if best_slot is None or text_w > best_slot[0]:
                        best_slot = (text_w, text_x, vis_rect)
                    if text_w >= adv:
                        draw_txt = txt
                    else:
                        draw_txt = fm.elidedText(txt, Qt.ElideRight, int(text_w) - 4)
                        if draw_txt == "\u2026":
                            continue
                    _draw_text(QRectF(text_x, vis_rect.y(), text_w, vis_rect.height()), draw_txt)
                    any_label_drawn = True
                if not any_label_drawn and best_slot is not None:
                    # Cross-platform fallback: when elision collapses to only an
                    # ellipsis (common with dense traces), draw a short prefix.
                    text_w, text_x, vis_rect = best_slot
                    if text_w >= 8.0:
                        avg_ch = max(1, fm.horizontalAdvance("M"))
                        n_ch = max(1, int((text_w - 2.0) // avg_ch))
                        draw_txt = txt[:n_ch]
                        _draw_text(QRectF(text_x, vis_rect.y(), text_w, vis_rect.height()), draw_txt)
                if _use_device_text:
                    painter.restore()
            else:
                # Keep text coordinates near zero to avoid precision loss when
                # scene Y becomes very large on long traces.
                _base_y = option.exposedRect.top()
                painter.save()
                painter.translate(0.0, _base_y)
                any_label_drawn = False
                for rect, _, _, _seg in seg_slice:
                    vis_rect = rect.intersected(option.exposedRect)
                    if vis_rect.isEmpty():
                        continue
                    # Clamp text start to visible content area.
                    text_y = max(vis_rect.y() + 2.0, _content_top)
                    text_h = vis_rect.bottom() - 2.0 - text_y
                    if text_h <= 0.0:
                        continue
                    if text_h >= adv:
                        draw_txt = txt
                    else:
                        draw_txt = fm.elidedText(txt, Qt.ElideRight, int(text_h) - 4)
                        if draw_txt == "\u2026":
                            continue
                    painter.save()
                    painter.translate(vis_rect.x() + vis_rect.width() / 2,
                                      text_y - _base_y + text_h / 2)
                    painter.rotate(90)
                    painter.drawText(
                        QRectF(-text_h / 2, -vis_rect.width() / 2, text_h, vis_rect.width()),
                        Qt.AlignVCenter | Qt.AlignLeft,
                        draw_txt,
                    )
                    painter.restore()
                    any_label_drawn = True
                painter.restore()
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
        for k in range(max(0, lo - _HOVER_BISECT_MARGIN),
                       min(len(xs), lo + _HOVER_BISECT_MARGIN)):
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
        self.setCacheMode(QGraphicsItem.NoCache)

    def boundingRect(self) -> QRectF:
        return self._bounding_rect

    def paint(self, painter: QPainter, option, widget=None) -> None:
        if not self._markers:
            return
        h        = STI_MARKER_H
        w        = 2
        markers  = self._markers
        horiz    = self._horizontal

        lod = QStyleOptionGraphicsItem.levelOfDetailFromTransform(
                  painter.worldTransform())
        axis = self._axis

        painter.save()
        if horiz:
            if lod < _PAINT_LOD_COARSE:
                for x, color, _ev in markers:
                    painter.setPen(QPen(color, 1.0))
                    painter.drawLine(QLineF(x, axis - h, x, axis + h))
            else:
                last_color = None
                for x, color, _ev in markers:
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
                for y, color, _ev in markers:
                    painter.setPen(QPen(color, 1.0))
                    painter.drawLine(QLineF(axis - h, y, axis + h, y))
            else:
                last_color = None
                for y, color, _ev in markers:
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
        if self._tl_scene._hover_highlight:
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
        if self._tl_scene._hover_highlight:
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

# ===========================================================================
# View
# ===========================================================================

class TimelineView(QGraphicsView):
    """Pan + zoom QGraphicsView wrapping a TimelineScene."""

    zoom_changed         = pyqtSignal(float)
    cursors_changed      = pyqtSignal(list)
    bookmark_requested   = pyqtSignal(int)   # ns at right-click position
    annotation_requested = pyqtSignal(int)   # ns at right-click position

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = TimelineScene(self)
        self.setScene(self._scene)

        # -- Qt render settings ------------------------------------------
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.TextAntialiasing, True)
        self.setOptimizationFlags(
            QGraphicsView.DontAdjustForAntialiasing
        )
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
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
        # Remember the last viewport position for each orientation.
        # key=True  -> horizontal mode, key=False -> vertical mode
        # value=(center_ns, orth_center_coord)
        self._view_pos_by_orientation: Dict[bool, Tuple[int, float]] = {}

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
        self.zoom_changed.emit(self._scene.timescale_per_px)

    def add_cursor_at_view_center(self) -> None:
        vp = self.viewport().rect()
        scene_pt = self.mapToScene(vp.center())
        coord = scene_pt.x() if self._scene._horizontal else scene_pt.y()
        ns = self._scene.scene_to_ns(coord)
        self._scene.add_cursor(ns)
        self.cursors_changed.emit(self._scene.cursor_times())

    def view_center_ns(self) -> int:
        """Return the timestamp currently at the viewport centre."""
        vp = self.viewport().rect()
        scene_pt = self.mapToScene(vp.center())
        coord = scene_pt.x() if self._scene._horizontal else scene_pt.y()
        return self._scene.scene_to_ns(coord)

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
        trace = self._scene._trace
        _span = max(trace.time_max - trace.time_min, 1)
        _vp_half = int(self._fit_viewport_size() * 10 * self._scene._timescale_per_px)
        _half = max(_vp_half, _span // 100)
        self._scene._ns_range_hint = (
            max(trace.time_min, ns - _half),
            min(trace.time_max, ns + _half),
        )
        self._scene.rebuild()
        coord     = self._scene.ns_to_scene_coord(ns)
        is_horiz  = self._scene._horizontal
        cur_scene = self.mapToScene(self.viewport().rect().center())
        if is_horiz:
            self.centerOn(coord, cur_scene.y())
        else:
            self.centerOn(cur_scene.x(), coord)
        self.viewport().update()

    def set_horizontal(self, horizontal: bool) -> None:
        trace = self._scene._trace
        old_h = self._scene._horizontal
        if old_h == horizontal:
            return
        if trace is None:
            self._scene.set_horizontal(horizontal)
            return

        vp = self.viewport().rect()
        old_scene_pt = self.mapToScene(vp.center())
        old_time_coord = old_scene_pt.x() if old_h else old_scene_pt.y()
        old_ns = self._scene.scene_to_ns(old_time_coord)
        old_orth = old_scene_pt.y() if old_h else old_scene_pt.x()
        self._view_pos_by_orientation[old_h] = (old_ns, old_orth)

        target_ns, target_orth = self._view_pos_by_orientation.get(horizontal, (old_ns, old_orth))

        _span = max(trace.time_max - trace.time_min, 1)
        _vp_half = int(self._fit_viewport_size() * 10 * self._scene._timescale_per_px)
        _half = max(_vp_half, _span // 100)
        self._scene._ns_range_hint = (
            max(trace.time_min, target_ns - _half),
            min(trace.time_max, target_ns + _half),
        )

        self._scene.set_horizontal(horizontal)
        new_time_coord = self._scene.ns_to_scene_coord(target_ns)
        if horizontal:
            self.centerOn(new_time_coord, target_orth)
        else:
            self.centerOn(target_orth, new_time_coord)
        self.viewport().update()

    def set_show_sti(self, show: bool) -> None:
        self._scene.set_show_sti(show)

    def set_show_grid(self, show: bool) -> None:
        self._scene.set_show_grid(show)

    def set_font_size(self, size: int) -> None:
        self._scene.set_font_size(size)
        self.zoom_changed.emit(self._scene.timescale_per_px)

    def set_max_cursors(self, n: int) -> None:
        self._scene.set_max_cursors(n)

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
        # scene level (timescale_per_px) so there must be no view-level scale active.
        # fitInView() would set a persistent QTransform that is not needed here.
        self.resetTransform()
        self.zoom_changed.emit(self._scene.timescale_per_px)

    def zoom_1to1(self) -> None:
        """Set zoom to exactly _TIMESCALE_PER_PX_DEFAULT ns/px, scrolling to trace start when in fit mode."""
        if self._scene._trace is None:
            return
        was_fit_mode = self._fit_mode
        self._fit_mode = False
        if self._scene._timescale_per_px == self._scene._timescale_per_px_default:
            return
        trace = self._scene._trace
        # When transitioning from fit mode the viewport centre is the middle of
        # the entire trace.  At 1:1 zoom the viewport window is very narrow
        # (viewport_width × timescale_per_px ≈ 1280 ns for a typical 640 px window),
        # so centering on the trace midpoint almost never lands on a segment.
        # Instead, scroll to time_min so the first segments are immediately
        # visible — which is the same position the viewer starts at on launch.
        vp_center = self.viewport().rect().center()
        scene_pt  = self.mapToScene(vp_center)
        if was_fit_mode:
            center_ns = trace.time_min
        else:
            if self._scene._horizontal:
                center_ns = self._scene.scene_to_ns(scene_pt.x())
            else:
                center_ns = self._scene.scene_to_ns(scene_pt.y())
        self._scene._timescale_per_px = self._scene._timescale_per_px_default
        # Supply an explicit ns range hint centred on center_ns so that
        # _update_viewport_bounds() loads the correct segment region.
        #
        # Using the viewport pixel size alone (±640 px * 2 ns/px = ±1280 ns)
        # is too narrow: tasks with long periods may have NO segment in that
        # window.  Instead use ±(1% of trace span) or ±10 viewports, whichever
        # is larger.  The 150 % margin inside _update_viewport_bounds adds
        # another 3× on top so the first scroll after 1:1 is also covered.
        _span = max(trace.time_max - trace.time_min, 1)
        _vp_half = int(self._fit_viewport_size() * 10 * self._scene._timescale_per_px_default)
        _half = max(_vp_half, _span // 100)
        self._scene._ns_range_hint = (
            max(trace.time_min, center_ns - _half),
            min(trace.time_max, center_ns + _half),
        )
        self._scene.rebuild()
        self.resetTransform()
        self.zoom_changed.emit(self._scene.timescale_per_px)
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
    # Mouse interaction
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
                    self.zoom_changed.emit(self._scene.timescale_per_px)
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
            self._reposition_frozen_top()   # keep cursor labels in the ruler area
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
                self.zoom_changed.emit(self._scene.timescale_per_px)
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
            in_vp_label  = (event.pos().x()       < lw if self._scene._horizontal
                            else event.pos().y()       < lw)
            # Also block when the press originated inside the label column:
            # a tiny drag (≤ drag_threshold) from the label into the timeline
            # must not place a cursor.
            press_in_label = (self._press_pos.x() < lw if self._scene._horizontal
                              else self._press_pos.y() < lw)
            if in_vp_label or press_in_label:
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
        # Suppress the context menu when the click lands inside the label column.
        lw = self._scene._label_width
        in_label = (event.pos().x() < lw if self._scene._horizontal
                    else event.pos().y() < lw)
        if in_label:
            event.accept()
            return

        menu = QMenu(self)
        scene_pt = self.mapToScene(event.pos())
        coord = scene_pt.x() if self._scene._horizontal else scene_pt.y()
        ns = self._scene.scene_to_ns(coord)

        # Shared icon color — timeline always uses a dark background
        _icon_color = "#D4D4D4"

        # Place cursor
        act = menu.addAction(
            _svg_icon(_IC_CURSOR, _icon_color),
            f"Place cursor here  ({_format_time(ns, self._scene._trace.time_scale) if self._scene._trace else ''})",
            lambda: (self._scene.add_cursor(ns),
                     self.cursors_changed.emit(self._scene.cursor_times()))
        )
        if self._scene.cursor_times():
            # Remove nearest cursor — use an eraser/minus-cursor icon
            menu.addAction(
                _svg_icon("M2 2.5A.5.5 0 0 1 2.5 2h4a.5.5 0 0 1 0 1H3v9h9v-3.5a.5.5 0 0 1 1 0V12.5a.5.5 0 0 1-.5.5h-10a.5.5 0 0 1-.5-.5v-10zM14.854 2.854a.5.5 0 0 0-.708-.708L8 8.293 5.854 6.146a.5.5 0 1 0-.708.708l2.5 2.5a.5.5 0 0 0 .708 0l6.5-6.5z", _icon_color),
                "Remove nearest cursor",
                lambda: (self._scene.remove_nearest_cursor(ns),
                         self.cursors_changed.emit(self._scene.cursor_times()))
            )
            menu.addAction(
                _svg_icon(_IC_CLEAR, _icon_color),
                "Clear all cursors",
                lambda: (self._scene.clear_cursors(),
                         self.cursors_changed.emit([]))
            )
        if self._scene._trace is not None:
            menu.addSeparator()
            # Bookmark icon — flag/ribbon shape
            menu.addAction(
                _svg_icon("M2 2a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v13.5a.5.5 0 0 1-.74.439L8 13.069l-5.26 2.87A.5.5 0 0 1 2 15.5V2zm2-1a1 1 0 0 0-1 1v12.566l4.74-2.586a.5.5 0 0 1 .48 0L13 14.566V2a1 1 0 0 0-1-1H4z", _icon_color),
                f"Add Bookmark here  ({_format_time(ns, self._scene._trace.time_scale)})",
                lambda: self.bookmark_requested.emit(ns)
            )
            # Annotation icon — pencil/note shape
            menu.addAction(
                _svg_icon("M12.854 0.146a.5.5 0 0 0-.707 0L10.5 1.793 14.207 5.5l1.647-1.646a.5.5 0 0 0 0-.708l-3-3zm.646 6.061L9.793 2.5 3.293 9H3.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.207l6.5-6.5zm-7.468 7.468A.5.5 0 0 1 6 13.5V13h-.5a.5.5 0 0 1-.5-.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.5-.5V10h-.5a.499.499 0 0 1-.175-.032l-.179.178a.5.5 0 0 0-.11.168l-2 5a.5.5 0 0 0 .65.65l5-2a.5.5 0 0 0 .168-.11l.178-.178z", _icon_color),
                f"Add Annotation here  ({_format_time(ns, self._scene._trace.time_scale)})",
                lambda: self.annotation_requested.emit(ns)
            )
        menu.exec_(event.globalPos())

    # ------------------------------------------------------------------
    # Wheel and touch zoom
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

    # ------------------------------------------------------------------
    # Zoom internals
    # ------------------------------------------------------------------

    def _do_zoom(self, factor: float, vp_pos=None) -> None:
        """Zoom by factor, keeping vp_pos (viewport coords) fixed on screen."""
        self._fit_mode = False   # any manual zoom leaves fit mode
        if vp_pos is None:
            vp_pos = self.viewport().rect().center()
        is_horiz = self._scene._horizontal
        # Convert anchor viewport position to ns coordinate
        scene_pt = self.mapToScene(vp_pos)
        center_coord = scene_pt.x() if is_horiz else scene_pt.y()
        center_ns = self._scene.scene_to_ns(center_coord)
        # Compute the viewport-center offset from the anchor
        vp_center = self.viewport().rect().center()
        offset = (vp_center.x() - vp_pos.x()) if is_horiz else (vp_center.y() - vp_pos.y())

        prev_timescale_per_px = self._scene.timescale_per_px
        trace = self._scene._trace
        if trace is not None:
            axis_px = self.viewport().width() if is_horiz else self.viewport().height()
            axis_px = max(1, axis_px)
            target_timescale = prev_timescale_per_px / factor
            target_timescale = max(
                self._scene._timescale_per_px_default,
                min(target_timescale, self._scene._timescale_per_px_fit),
            )
            center_target_ns = center_ns + int(offset * target_timescale)
            half_span_ns = int((axis_px * target_timescale) / 2)
            hint_lo = max(trace.time_min, center_target_ns - half_span_ns)
            hint_hi = min(trace.time_max, center_target_ns + half_span_ns)
            if hint_hi > hint_lo:
                # Rebuild uses this range immediately before centerOn() updates
                # scrollbars, preventing far-right zoom-out from clipping to a
                # pathological full-trace range.
                self._scene._ns_range_hint = (hint_lo, hint_hi)
        self._scene.zoom(factor)
        if self._scene.timescale_per_px == prev_timescale_per_px:
            return  # already at zoom limit – nothing changed, skip scroll/emit
        self.zoom_changed.emit(self._scene.timescale_per_px)

        # After rebuild, keep the time-axis anchor fixed without drifting on
        # the orthogonal axis (prevents left/right drift in vertical mode).
        new_scene_coord = self._scene.ns_to_scene_coord(center_ns)
        cur_scene_center = self.mapToScene(vp_center)
        if is_horiz:
            self.centerOn(new_scene_coord + offset, cur_scene_center.y())
        else:
            self.centerOn(cur_scene_center.x(), new_scene_coord + offset)

    # ------------------------------------------------------------------
    # Scroll and viewport sync
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Resize handling
    # ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        """Reflow the timeline on every resize to preserve the current zoom ratio."""
        super().resizeEvent(event)
        if self._scene._trace is not None:
            self._resize_timer.start()

    def _on_resize_timeout(self) -> None:
        """Debounced resize handler.

        Fit mode  → rebuild at the new fit zoom so the trace always fills
                    the viewport (no blank space, no scrollbar).
        Zoom mode → timescale_per_px is NEVER touched.  Only update _timescale_per_px_fit
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
            self._scene._timescale_per_px_fit = new_fit
            self._scene._timescale_per_px     = new_fit
            self._scene.rebuild()
            self.resetTransform()
            self.zoom_changed.emit(self._scene.timescale_per_px)
        else:
            # Zoom mode: preserve zoom level exactly.
            self._scene._timescale_per_px_fit = new_fit
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
        timescale_per_px = self._scene._timescale_per_px

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

        ns_lo = max(t_min, min(t_max, t_min + int((lo_coord - lw) * timescale_per_px)))
        ns_hi = max(t_min, min(t_max, t_min + int((hi_coord - lw) * timescale_per_px)))

        # Time-axis coverage exceeded → need rebuild to repopulate segments.
        if ns_lo < self._scene._vp_ns_lo or ns_hi > self._scene._vp_ns_hi:
            return True

        # Orthogonal coverage exceeded → need rebuild to populate culled rows/cols.
        if orth_lo < self._scene._vp_scene_orth_lo or orth_hi > self._scene._vp_scene_orth_hi:
            return True

        return False

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
        # The frameless Qt.Tool variant is primarily needed on macOS to avoid
        # delayed first paint at startup. On Windows it may leave a tiny black
        # artifact near (0, 0), so use a regular dialog there.
        if sys.platform == "darwin":
            flags = Qt.Tool | Qt.FramelessWindowHint
        else:
            flags = Qt.Dialog | Qt.WindowTitleHint | Qt.CustomizeWindowHint
        super().__init__(parent, flags)
        self.setWindowModality(Qt.ApplicationModal)
        if sys.platform != "darwin":
            self.setWindowTitle("Loading")
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
        _is_dark = QApplication.instance().palette().color(QPalette.Window).lightness() < 128
        if _is_dark:
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
                QProgressBar::chunk { background: #0E4D80; border-radius: 2px; }
            """)
        else:
            self.setStyleSheet("""
                QWidget#loadprog {
                    background: #F5F5F5;
                    border: 1px solid #CCCCCC;
                    border-radius: 6px;
                }
                QLabel { color: #1E1E1E; font-size: 12px; }
                QProgressBar {
                    border: 1px solid #AAAAAA; border-radius: 3px;
                    background: #FFFFFF; height: 18px; text-align: center;
                    color: #1E1E1E;
                }
                QProgressBar::chunk { background: #005A9E; border-radius: 2px; }
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
        # Centre over the parent window.
        _c = parent_geom.center()
        self.move(_c.x() - self.width() // 2,
                  _c.y() - self.height() // 2)
        self.show()
        self.raise_()
        self.activateWindow()
        # Force an immediate paint so the bar is visible before the thread starts.
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

    def __init__(self, text: str, color: str, is_dark: bool = True,
                 parent: QWidget = None):
        super().__init__(text, parent)
        self._color     = color
        self._is_dark   = is_dark
        self._press_pos: Optional[QPoint] = None
        self._dragging  = False
        self._normal_ss = self._make_style(color, delete=False, is_dark=is_dark)
        self._delete_ss = self._make_style(color, delete=True,  is_dark=is_dark)
        self.setStyleSheet(self._normal_ss)
        self.setCursor(Qt.PointingHandCursor)

    @staticmethod
    def _make_style(c: str, delete: bool = False, is_dark: bool = True) -> str:
        if is_dark:
            bg      = "#5A1A1A" if delete else "#2A2A2A"
            hbg     = "#6A2A2A" if delete else "#3A3A3A"
            pressed = "#4A4A4A"
        else:
            bg      = "#FAEAEA" if delete else "#F0F0F0"
            hbg     = "#EACACA" if delete else "#E0E0E0"
            pressed = "#D0D0D0"
        bc  = "#FF4444" if delete else c
        return (
            f"QPushButton {{ color: {c}; background: {bg}; "
            f"border: 1px solid {bc}; border-radius: 3px; "
            f"padding: 1px 7px; font-size: {UI_FONT_SIZE}pt; "
            f"font-family: \"{_get_fixed_font_family()}\"; }}"
            f"QPushButton:hover   {{ background: {hbg}; }}"
            f"QPushButton:pressed {{ background: {pressed}; }}"
        )

    def update_style(self, is_dark: bool) -> None:
        """Regenerate button stylesheets for the given theme and re-apply."""
        self._is_dark   = is_dark
        self._normal_ss = self._make_style(self._color, delete=False, is_dark=is_dark)
        self._delete_ss = self._make_style(self._color, delete=True,  is_dark=is_dark)
        # Apply the appropriate state (delete style is only shown while dragging)
        self.setStyleSheet(self._normal_ss)

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

class _CursorBarWidget(QWidget):
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
        self._is_dark: bool = True

    def update_theme(self, is_dark: bool) -> None:
        """Update all existing cursor buttons to reflect the new theme."""
        self._is_dark = is_dark
        for btn in self._buttons:
            btn.update_style(is_dark)

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
                btn = _CursorButton(label_text, c, is_dark=self._is_dark)
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
                    f"font-size:{UI_FONT_SIZE}pt;"
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
    _BG_LOCKED  = "background: rgba(255,215,0,45);  border-radius:3px;"

    def __init__(self, task_name: str, display_name: str,
                 color: QColor, tooltip: str = "", is_dark: bool = True,
                 parent=None):
        super().__init__(parent)
        self._task_name = task_name
        self._locked    = False
        # Theme-variant hover BG and swatch border
        self._BG_HOVER  = ("background: rgba(255,255,255,18); border-radius:3px;"
                            if is_dark else
                            "background: rgba(0,0,0,20);       border-radius:3px;")
        swatch_border   = "#555555" if is_dark else "#AAAAAA"

        hl = QHBoxLayout(self)
        hl.setContentsMargins(2, 1, 2, 1)
        hl.setSpacing(6)

        swatch = QLabel()
        swatch.setFixedSize(14, 14)
        swatch.setStyleSheet(
            f"background:{color.name()}; border-radius:2px; border:1px solid {swatch_border};"
        )
        hl.addWidget(swatch)

        self._lbl = QLabel(display_name)
        self._lbl.setToolTip(tooltip or display_name)
        hl.addWidget(self._lbl)
        hl.addStretch()

        self.setCursor(Qt.PointingHandCursor)
        self.setAutoFillBackground(False)
        self._set_bg(self._BG_NORMAL)

    def _set_bg(self, css: str) -> None:
        self.setStyleSheet(css)

    def matches_filter(self, q: str) -> bool:
        """Case-insensitive filter match against merge-key or display name."""
        if not q:
            return True
        ql = q.lower()
        return (ql in self._task_name.lower()) or (ql in self._lbl.text().lower())

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
        event.accept()   # prevent bubbling up to _LegendWidget.mousePressEvent

class _LegendWidget(QWidget):
    """Compact scrollable colour legend with click → timeline highlight."""

    task_clicked     = pyqtSignal(str)   # click: task merge key
    cancel_highlight = pyqtSignal()      # click on background → cancel highlight
    filter_changed   = pyqtSignal(str)   # search text changed

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 0, 6)  # no right margin: lets scroll bar sit flush at edge
        outer.setSpacing(4)
        self.setAutoFillBackground(True)
        self._is_dark: bool = True
        self._trace_ref = None        # cached for update_theme() rebuild
        self._show_sti_flag: bool = True
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("#1E1E1E"))
        self.setPalette(palette)
        self._task_rows: Dict[str, _LegendTaskRow] = {}   # raw name → row widget
        self._sti_rows: List[tuple] = []  # [(channel_or_note_lc, row_widget)]
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter tasks…")
        self._search.setStyleSheet(
            "QLineEdit { background:#2D2D2D; color:#D4D4D4; border:1px solid #555; "
            "border-radius:3px; padding:2px 4px; }"
        )
        self._filter_emit_timer = QTimer(self)
        self._filter_emit_timer.setSingleShot(True)
        self._filter_emit_timer.setInterval(150)
        self._filter_emit_timer.timeout.connect(
            lambda: self.filter_changed.emit(self._search.text())
        )
        self._search.textChanged.connect(self._on_search_text_changed)
        outer.addWidget(self._search)

        # Sticky-search layout: only the legend rows scroll.
        self._list_host = QWidget()
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setWidget(self._list_host)
        outer.addWidget(self._scroll, 1)

    def update_theme(self, is_dark: bool) -> None:
        """Switch the legend palette and search-box styling to match the app theme."""
        self._is_dark = is_dark
        palette = self.palette()
        palette.setColor(QPalette.Window,
                         QColor("#1E1E1E") if is_dark else QColor("#F5F5F5"))
        self.setPalette(palette)
        if is_dark:
            self._search.setStyleSheet(
                "QLineEdit { background:#2D2D2D; color:#D4D4D4; border:1px solid #555; "
                "border-radius:3px; padding:2px 4px; }"
            )
        else:
            self._search.setStyleSheet(
                "QLineEdit { background:#FFFFFF; color:#1E1E1E; border:1px solid #AAAAAA; "
                "border-radius:3px; padding:2px 4px; }"
            )
        if self._trace_ref is not None:
            self.rebuild(self._trace_ref, show_sti=self._show_sti_flag)

    def set_locked_task(self, task_name: Optional[str]) -> None:
        """Visually mark *task_name* as click-locked (or clear all locks)."""
        for raw, row in self._task_rows.items():
            row.set_locked(raw == task_name)

    def mousePressEvent(self, event) -> None:
        """Click on the legend background (outside a task row) cancels highlight."""
        self.cancel_highlight.emit()
        super().mousePressEvent(event)

    def rebuild(self, trace: BtfTrace, *, show_sti: bool = True) -> None:
        self._trace_ref      = trace
        self._show_sti_flag  = show_sti
        self._task_rows.clear()
        self._sti_rows = []

        while self._list_layout.count():
            _item = self._list_layout.takeAt(0)
            _w = _item.widget()
            if _w is None:
                continue
            _w.deleteLater()

        # Suppress per-addWidget layout recalculations for the whole batch.
        is_dark       = self._is_dark
        hdr_color     = "#AAAAAA" if is_dark else "#555555"
        sep_color     = "#444444" if is_dark else "#CCCCCC"
        hdr2_color    = "#88AABB" if is_dark else "#005A9E"
        self.setUpdatesEnabled(False)
        try:
            header = QLabel(f"<b style='color:{hdr_color}'>Tasks</b>")
            header.setTextFormat(Qt.RichText)
            self._list_layout.addWidget(header)

            # trace.tasks contains merge keys; task_repr maps each to its raw name.
            for _mk in trace.tasks:
                _rep_raw = trace.task_repr.get(_mk, _mk)
                color = _task_color(_rep_raw)
                display = task_display_name(_rep_raw)
                row = _LegendTaskRow(_mk, display, color, tooltip=_rep_raw, is_dark=is_dark)
                row.clicked.connect(self.task_clicked)
                self._task_rows[_mk] = row
                self._list_layout.addWidget(row)

            if show_sti and trace.sti_channels:
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                sep.setStyleSheet(f"color:{sep_color};")
                self._list_layout.addWidget(sep)

                hdr2 = QLabel(f"<b style='color:{hdr2_color}'>STI Events</b>")
                hdr2.setTextFormat(Qt.RichText)
                self._list_layout.addWidget(hdr2)

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
                    hl.addWidget(lbl)
                    hl.addStretch()
                    self._list_layout.addWidget(row_w)
                    self._sti_rows.append((note.lower(), row_w))

            self._list_layout.addStretch()
            self._filter_tasks(self._search.text())
        finally:
            self.setUpdatesEnabled(True)

    def _on_search_text_changed(self, text: str) -> None:
        """Apply legend filter immediately, debounce expensive timeline rebuild."""
        self._filter_tasks(text)
        self._filter_emit_timer.start()

    def _filter_tasks(self, text: str) -> None:
        """Show / hide task and STI rows in the legend based on the search filter."""
        q = text.strip().lower()
        for mk, row in self._task_rows.items():
            row.setVisible(row.matches_filter(q))
        for key_lc, row_w in self._sti_rows:
            row_w.setVisible((not q) or (q in key_lc))

# ---------------------------------------------------------------------------
# Statistics dock panel
# ---------------------------------------------------------------------------

class _StatsPanel(QWidget):
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

    def _lbl(self, text: str, color: str = "", bold: bool = False) -> QLabel:
        w = QLabel(text)
        parts = ["background:transparent;"]
        if color:
            parts.insert(0, f"color:{color};")
        if bold:
            parts.append("font-weight:bold;")
        w.setStyleSheet(" ".join(parts))
        return w

    def _sep(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        return f

    def update_trace(self, trace: "BtfTrace") -> None:
        self._clear()
        total_ns = trace.time_max - trace.time_min
        span_str = _format_time(total_ns, trace.time_scale)

        # -- Summary row ---------------------------------------------------
        self._ilay.addWidget(self._lbl(
            f"Span: {span_str}  |  Tasks: {len(trace.tasks)}  |  "
            f"Segments: {len(trace.segments)}  |  STI events: {len(trace.sti_events)}",
            color="#888888",
        ))

        # -- Core utilisation (excl. IDLE) ---------------------------------
        if trace.core_names:
            self._ilay.addWidget(self._sep())
            self._ilay.addWidget(self._lbl("Core Utilisation (excl. IDLE/TICK):", bold=True))
            for core in trace.core_names:
                segs = trace.core_segs.get(core, [])
                act  = sum(s.end - s.start for s in segs
                           if (_tn := parse_task_name(s.task)[2]) != "TICK"
                           and not _tn.startswith("IDLE"))
                pct  = 100.0 * act / total_ns if total_ns > 0 else 0.0
                row = QWidget()
                hlay = QHBoxLayout(row)
                hlay.setContentsMargins(0, 0, 0, 0)
                hlay.setSpacing(8)

                core_lbl = self._lbl(f"  {core}:")
                core_lbl.setMinimumWidth(72)
                hlay.addWidget(core_lbl)

                pbar = QProgressBar()
                pbar.setRange(0, 1000)
                pbar.setValue(int(round(max(0.0, min(100.0, pct)) * 10.0)))
                pbar.setTextVisible(False)
                pbar.setFixedHeight(14)
                pbar.setStyleSheet("""
                    QProgressBar {
                        border: 1px solid #888888;
                        border-radius: 4px;
                        background: palette(alternateBase);
                    }
                    QProgressBar::chunk {
                        background-color: #5FCF6F;
                        border-radius: 3px;
                    }
                """)
                hlay.addWidget(pbar, 1)

                pct_lbl = self._lbl(f"{pct:.1f}%", color="#77BB77")
                pct_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                hlay.addWidget(pct_lbl)
                hlay.addStretch(1)

                self._ilay.addWidget(row)

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

class _RcSettings:
    """INI-style persistent settings store backed by *btf_viewer.rc*.

    The file is written next to the script.  If it does not yet exist it is
    created automatically with sensible default values on first run.

    Sections and keys
    -----------------
    [window]   width, height, x, y, maximized
    [view]     font_size, theme, horizontal, view_mode, show_sti, show_grid
    [zoom]     timescale_per_px  (-1 = use fit-to-width on next open)
    [cursors]  positions  (space-separated ns timestamps; "" = no saved cursors)
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
            "font_size":  str(FONT_SIZE),
            "theme":      "dark",
            "horizontal": "true",
            "view_mode":  "task",
            "show_sti":   "true",
            "show_grid":  "true",
            "show_marks": "true",
            "show_find": "false",
        },
        "zoom": {
            "timescale_per_px": "-1",
        },
        "cursors": {
            "positions": "",
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
# About Dialog
# ---------------------------------------------------------------------------

class _AboutDialog(QDialog):
    """Modern About dialog — app icon header, theme-aware, quick-reference table."""

    def __init__(self, parent, *, is_dark: bool):
        super().__init__(parent, Qt.Dialog)
        self.setWindowTitle("About BTF Trace Viewer")
        self.setModal(True)
        self.setFixedWidth(420)

        # Theme palette
        if is_dark:
            hdr_bg  = "#1E1E1E"; bg     = "#252526"; sep_c  = "#3A3A3A"
            title_c = "#FFFFFF";  sub_c  = "#9E9E9E"; sect_c = "#5B9BD5"
            key_c   = "#7EC8E3"; body_c = "#D4D4D4"
            btn_bg  = "#0E4D80"; btn_hov = "#1565C0"; btn_txt = "#FFFFFF"
        else:
            hdr_bg  = "#F0F0F0"; bg     = "#FAFAFA"; sep_c  = "#CCCCCC"
            title_c = "#1E1E1E"; sub_c  = "#666666"; sect_c = "#005A9E"
            key_c   = "#005A9E"; body_c = "#333333"
            btn_bg  = "#005A9E"; btn_hov = "#1472B5"; btn_txt = "#FFFFFF"

        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Header: icon + title + tagline ───────────────────────────────
        hdr = QWidget()
        hdr.setObjectName("about_hdr")
        hv = QVBoxLayout(hdr)
        hv.setAlignment(Qt.AlignHCenter)
        hv.setContentsMargins(24, 28, 24, 22)
        hv.setSpacing(8)

        icon_lbl = QLabel()
        icon_lbl.setAlignment(Qt.AlignHCenter)
        _pm = QPixmap()
        _pm.loadFromData(QByteArray(_APP_ICON_SVG.encode()), "SVG")
        icon_lbl.setPixmap(_pm)
        hv.addWidget(icon_lbl)

        name_lbl = QLabel("BTF Trace Viewer")
        name_lbl.setAlignment(Qt.AlignHCenter)
        name_lbl.setObjectName("about_title")
        hv.addWidget(name_lbl)

        sub_lbl = QLabel(f"RTOS context-switch timeline visualiser  ·  v{_APP_VERSION}")
        sub_lbl.setAlignment(Qt.AlignHCenter)
        sub_lbl.setObjectName("about_sub")
        hv.addWidget(sub_lbl)
        root.addWidget(hdr)

        def _hsep():
            f = QFrame()
            f.setFrameShape(QFrame.HLine)
            f.setFrameShadow(QFrame.Plain)
            f.setObjectName("about_sep")
            return f

        root.addWidget(_hsep())

        # ── Info body ─────────────────────────────────────────────────────
        info_w = QWidget()
        iv = QVBoxLayout(info_w)
        iv.setContentsMargins(24, 16, 24, 16)
        iv.setSpacing(10)

        def _sect(text: str) -> QLabel:
            lbl = QLabel(text.upper())
            lbl.setObjectName("about_sect")
            return lbl

        def _kv_table(rows) -> QWidget:
            w = QWidget()
            g = QGridLayout(w)
            g.setContentsMargins(8, 0, 0, 0)
            g.setHorizontalSpacing(16)
            g.setVerticalSpacing(3)
            g.setColumnStretch(1, 1)
            for r, (k, v) in enumerate(rows):
                kl = QLabel(k); kl.setObjectName("about_key")
                vl = QLabel(v); vl.setObjectName("about_body")
                g.addWidget(kl, r, 0, Qt.AlignTop)
                g.addWidget(vl, r, 1)
            return w

        iv.addWidget(_sect("View Modes"))
        iv.addWidget(_kv_table([
            ("Task View", "one row per task"),
            ("Core View", "expandable rows per CPU core"),
        ]))
        iv.addSpacing(4)
        iv.addWidget(_sect("Controls"))
        iv.addWidget(_kv_table([
            ("Left-click",  "place / drag cursor"),
            ("Ctrl+Wheel",  "zoom in / out  ·  Scroll \u2014 pan"),
            ("Ctrl+0",      "fit to window"),
            ("Ctrl+R",      "zoom to cursor range"),
            ("Help menu",   "full keyboard shortcut list"),
        ]))
        root.addWidget(info_w)

        root.addWidget(_hsep())

        # ── Footer ────────────────────────────────────────────────────────
        foot = QWidget()
        fh = QHBoxLayout(foot)
        fh.setContentsMargins(16, 10, 16, 14)
        fh.addStretch()
        btn = QPushButton("Close")
        btn.setObjectName("about_btn")
        btn.setFixedSize(88, 30)
        btn.setDefault(True)
        btn.clicked.connect(self.accept)
        fh.addWidget(btn)
        root.addWidget(foot)

        # ── Scoped stylesheet ─────────────────────────────────────────────
        self.setStyleSheet(f"""
            QDialog                     {{ background:{bg}; }}
            QWidget#about_hdr           {{ background:{hdr_bg}; }}
            QLabel#about_title          {{ color:{title_c}; font-size:17pt;
                                           font-weight:700; }}
            QLabel#about_sub            {{ color:{sub_c}; font-size:10pt; }}
            QLabel#about_sect           {{ color:{sect_c}; font-size:8pt;
                                           font-weight:700; letter-spacing:1px;
                                           margin-bottom:2px; }}
            QLabel#about_key            {{ color:{key_c}; font-size:10pt;
                                           font-weight:600; min-width:82px; }}
            QLabel#about_body           {{ color:{body_c}; font-size:10pt; }}
            QFrame#about_sep            {{ border:none; background:{sep_c};
                                           max-height:1px; }}
            QPushButton#about_btn       {{ background:{btn_bg}; color:{btn_txt};
                                           border:none; border-radius:5px;
                                           font-size:10pt; font-weight:600;
                                           padding:0px 22px; }}
            QPushButton#about_btn:hover {{ background:{btn_hov}; }}
        """)

        self.adjustSize()

# ---------------------------------------------------------------------------
# Settings Dialog
# ---------------------------------------------------------------------------

class _SettingsDialog(QDialog):
    """Modal settings dialog — sidebar navigation: Appearance | Display | Layout."""

    _INPUT_W = 110   # fixed pixel width for all spin / combo inputs

    # Emitted whenever any control value changes so _open_settings can
    # apply a live preview while the dialog is still open.
    live_preview = pyqtSignal()

    @staticmethod
    def _hline() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        f.setFrameShadow(QFrame.Plain)
        f.setObjectName("sep")
        return f

    @staticmethod
    def _section(text: str) -> QLabel:
        """Muted all-caps section header."""
        lbl = QLabel(text.upper())
        lbl.setObjectName("section_header")
        lbl.setContentsMargins(0, 6, 0, 2)
        return lbl

    @staticmethod
    def _indented(widget: QWidget, left: int = 16) -> QWidget:
        """Return widget wrapped in a container with a left-indent."""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(left, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(widget)
        return w

    @staticmethod
    def _dialog_ss(is_dark: bool, ui_fs: str) -> str:
        """Return a scoped stylesheet for the settings dialog."""
        if is_dark:
            return f"""
                QDialog                           {{ background:#252526; }}
                QListWidget                       {{ background:#1E1E1E; border:none;
                                                     padding:8px 0; }}
                QListWidget::item                 {{ color:#AAAAAA; padding:9px 16px;
                                                     font-size:{ui_fs}; }}
                QListWidget::item:selected        {{ background:#37373D; color:#FFFFFF;
                                                     border-left:3px solid #0E4D80;
                                                     padding-left:13px; }}
                QListWidget::item:hover:!selected {{ background:#2A2D2E; }}
                QFrame#vsep                       {{ border:none; background:#3A3A3A;
                                                     max-width:1px; }}
                QFrame#sep, QFrame#footer_sep     {{ border:none; background:#3A3A3A;
                                                     max-height:1px; }}
                QLabel#section_header             {{ color:#888888; font-weight:600;
                                                     font-size:{ui_fs}; }}
                QLabel                            {{ font-size:{ui_fs}; }}
                QCheckBox                         {{ font-size:{ui_fs}; }}
                QSpinBox, QDoubleSpinBox, QComboBox {{
                    background:#3C3C3C; color:#D4D4D4;
                    border:1.5px solid #555555; border-radius:4px;
                    padding:1px 6px; min-height:1.3em; font-size:{ui_fs}; }}
                QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus
                                                  {{ border-color:#0E4D80; }}
                QComboBox QAbstractItemView       {{ background:#3C3C3C; color:#D4D4D4;
                                                     selection-background-color:#0E4D80;
                                                     font-size:{ui_fs}; }}
                QCheckBox::indicator              {{ width:15px; height:15px;
                                                     border-radius:3px;
                                                     border:1.5px solid #555555;
                                                     background:#2D2D2D; }}
                QCheckBox::indicator:checked      {{ background:#0E4D80;
                                                     border-color:#0E4D80; }}
                QPushButton#btn_ok                {{ background:#0E4D80; color:#FFFFFF;
                                                     border:none; border-radius:5px;
                                                     padding:0px 22px;
                                                     font-weight:600;
                                                     font-size:{ui_fs}; }}
                QPushButton#btn_ok:hover          {{ background:#1565C0; }}
                QPushButton#btn_cancel            {{ background:transparent;
                                                     color:#AAAAAA;
                                                     border:1.5px solid #555555;
                                                     border-radius:5px;
                                                     padding:0px 22px;
                                                     font-size:{ui_fs}; }}
                QPushButton#btn_cancel:hover      {{ background:#2A2D2E;
                                                     border-color:#888888;
                                                     color:#CCCCCC; }}
            """
        else:
            return f"""
                QDialog                           {{ background:#FAFAFA; }}
                QListWidget                       {{ background:#F0F0F0; border:none;
                                                     padding:8px 0; }}
                QListWidget::item                 {{ color:#555555; padding:9px 16px;
                                                     font-size:{ui_fs}; }}
                QListWidget::item:selected        {{ background:#E8ECF0; color:#1E1E1E;
                                                     border-left:3px solid #005A9E;
                                                     padding-left:13px; }}
                QListWidget::item:hover:!selected {{ background:#EBEBEB; }}
                QFrame#vsep                       {{ border:none; background:#CCCCCC;
                                                     max-width:1px; }}
                QFrame#sep, QFrame#footer_sep     {{ border:none; background:#CCCCCC;
                                                     max-height:1px; }}
                QLabel#section_header             {{ color:#888888; font-weight:600;
                                                     font-size:{ui_fs}; }}
                QLabel                            {{ font-size:{ui_fs}; }}
                QCheckBox                         {{ font-size:{ui_fs}; }}
                QSpinBox, QDoubleSpinBox, QComboBox {{
                    background:#FFFFFF; color:#1E1E1E;
                    border:1.5px solid #AAAAAA; border-radius:4px;
                    padding:1px 6px; min-height:1.3em; font-size:{ui_fs}; }}
                QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus
                                                  {{ border-color:#005A9E; }}
                QComboBox QAbstractItemView       {{ background:#FFFFFF; color:#1E1E1E;
                                                     selection-background-color:#005A9E;
                                                     selection-color:#FFFFFF;
                                                     font-size:{ui_fs}; }}
                QCheckBox::indicator              {{ width:15px; height:15px;
                                                     border-radius:3px;
                                                     border:1.5px solid #AAAAAA;
                                                     background:#FFFFFF; }}
                QCheckBox::indicator:checked      {{ background:#005A9E;
                                                     border-color:#005A9E; }}
                QPushButton#btn_ok                {{ background:#005A9E; color:#FFFFFF;
                                                     border:none; border-radius:5px;
                                                     padding:0px 22px;
                                                     font-weight:600;
                                                     font-size:{ui_fs}; }}
                QPushButton#btn_ok:hover          {{ background:#1472B5; }}
                QPushButton#btn_cancel            {{ background:transparent;
                                                     color:#555555;
                                                     border:1.5px solid #AAAAAA;
                                                     border-radius:5px;
                                                     padding:0px 22px;
                                                     font-size:{ui_fs}; }}
                QPushButton#btn_cancel:hover      {{ background:#E5E5E5;
                                                     border-color:#888888;
                                                     color:#1E1E1E; }}
            """

    def __init__(self, parent, *,
                 font_size: int, ui_font_size: int,
                 max_cursors: int,
                 show_sti: bool, show_grid: bool,
                 show_legend: bool, show_stats: bool, show_marks: bool,
                 show_hover_highlight: bool,
                 zoom_unit: str,
                 label_width: int, row_height: int, row_gap: int,
                 timescale_per_px_default: float,
                 is_dark: bool):
        super().__init__(parent, Qt.Dialog)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumSize(580, 360)

        _ui_fs = f"{ui_font_size}pt"

        # Set an explicit font on the dialog so every child widget (including
        # QListWidget which uses native rendering on macOS and ignores CSS
        # font-size) inherits the correct point size consistently regardless
        # of which app-level theme was applied most recently.
        _dlg_font = QApplication.instance().font()
        _dlg_font.setPointSize(ui_font_size)
        self.setFont(_dlg_font)

        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # -- Body: sidebar + vertical separator + content stack ---------------
        body_w = QWidget()
        body = QHBoxLayout(body_w)
        body.setSpacing(0)
        body.setContentsMargins(0, 0, 0, 0)
        root.addWidget(body_w, 1)

        # Sidebar
        self._sidebar = QListWidget()
        self._sidebar.setFixedWidth(140)
        self._sidebar.setFont(_dlg_font)   # explicit – CSS font-size is ignored by macOS native item delegate
        self._sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._sidebar.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        _item_h = max(36, int(ui_font_size * 2.6))   # scale row height with font
        for _name in ("Appearance", "Display", "Layout"):
            _item = QListWidgetItem(_name)
            _item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            _item.setSizeHint(QSize(140, _item_h))
            self._sidebar.addItem(_item)
        self._sidebar.setCurrentRow(0)
        body.addWidget(self._sidebar)

        # Vertical separator
        _vsep = QFrame()
        _vsep.setFrameShape(QFrame.VLine)
        _vsep.setFrameShadow(QFrame.Plain)
        _vsep.setObjectName("vsep")
        _vsep.setFixedWidth(1)
        body.addWidget(_vsep)

        # Content stack (pages added below)
        self._content_stack = QStackedWidget()
        body.addWidget(self._content_stack, 1)

        def _inp(widget: QWidget) -> QWidget:
            widget.setFixedWidth(self._INPUT_W)
            return widget

        def _form(page: QWidget) -> QFormLayout:
            f = QFormLayout(page)
            f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
            f.setContentsMargins(20, 16, 20, 12)
            f.setHorizontalSpacing(16)
            f.setVerticalSpacing(10)
            f.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
            return f

        # -- Page 1: Appearance -----------------------------------------------
        p1 = QWidget()
        f1 = _form(p1)

        self._theme_combo = QComboBox()
        self._theme_combo.addItem("Dark")
        self._theme_combo.addItem("Light")
        self._theme_combo.setCurrentIndex(0 if is_dark else 1)
        self._theme_combo.setToolTip("Application colour theme")
        f1.addRow("Theme:", _inp(self._theme_combo))

        f1.addRow(self._hline())
        f1.addRow("", self._section("Font sizes"))

        self._font_spin = QSpinBox()
        self._font_spin.setRange(6, 24)
        self._font_spin.setSuffix(" pt")
        self._font_spin.setValue(font_size)
        self._font_spin.setToolTip("Font size for task / core labels drawn on the timeline")
        f1.addRow("Timeline labels:", _inp(self._font_spin))

        self._ui_font_spin = QSpinBox()
        self._ui_font_spin.setRange(8, 18)
        self._ui_font_spin.setSuffix(" pt")
        self._ui_font_spin.setValue(ui_font_size)
        self._ui_font_spin.setToolTip("Font size for menus, toolbar and status bar")
        f1.addRow("UI / menus:", _inp(self._ui_font_spin))

        self._content_stack.addWidget(p1)

        # -- Page 2: Display --------------------------------------------------
        p2 = QWidget()
        v2 = QVBoxLayout(p2)
        v2.setContentsMargins(20, 16, 20, 12)
        v2.setSpacing(7)

        v2.addWidget(self._section("Panels"))
        self._legend_cb = QCheckBox("Legend panel")
        self._legend_cb.setChecked(show_legend)
        self._stats_cb = QCheckBox("Statistics panel")
        self._stats_cb.setChecked(show_stats)
        self._marks_cb = QCheckBox("Marks panel")
        self._marks_cb.setChecked(show_marks)
        v2.addWidget(self._indented(self._legend_cb))
        v2.addWidget(self._indented(self._stats_cb))
        v2.addWidget(self._indented(self._marks_cb))

        v2.addSpacing(6)
        v2.addWidget(self._hline())
        v2.addSpacing(2)

        v2.addWidget(self._section("Timeline overlays"))
        self._sti_cb = QCheckBox("STI events")
        self._sti_cb.setChecked(show_sti)
        self._grid_cb = QCheckBox("Grid lines")
        self._grid_cb.setChecked(show_grid)
        self._hover_hl_cb = QCheckBox("Highlight segments on label hover")
        self._hover_hl_cb.setChecked(show_hover_highlight)
        self._hover_hl_cb.setToolTip(
            "Dim all other segments when hovering a task label.\n"
            "Disable for better performance with large traces.")
        v2.addWidget(self._indented(self._sti_cb))
        v2.addWidget(self._indented(self._grid_cb))
        v2.addWidget(self._indented(self._hover_hl_cb))
        v2.addStretch()

        self._content_stack.addWidget(p2)

        # -- Page 3: Layout ---------------------------------------------------
        p3 = QWidget()
        f3 = _form(p3)

        self._label_width_spin = QSpinBox()
        self._label_width_spin.setRange(60, 600)
        self._label_width_spin.setSuffix(" px")
        self._label_width_spin.setSingleStep(10)
        self._label_width_spin.setValue(label_width)
        self._label_width_spin.setToolTip("Width of the task / core label column (60\u2013600 px)")
        f3.addRow("Label column:", _inp(self._label_width_spin))

        self._row_height_spin = QSpinBox()
        self._row_height_spin.setRange(12, 60)
        self._row_height_spin.setSuffix(" px")
        self._row_height_spin.setValue(row_height)
        self._row_height_spin.setToolTip("Height of each task / core row (12\u201360 px)")
        f3.addRow("Row height:", _inp(self._row_height_spin))

        self._row_gap_spin = QSpinBox()
        self._row_gap_spin.setRange(0, 20)
        self._row_gap_spin.setSuffix(" px")
        self._row_gap_spin.setValue(row_gap)
        self._row_gap_spin.setToolTip("Vertical gap between rows (0\u201320 px)")
        f3.addRow("Row gap:", _inp(self._row_gap_spin))

        f3.addRow(self._hline())
        f3.addRow("", self._section("Zoom & cursors"))

        self._timescale_per_px_spin = QDoubleSpinBox()
        self._timescale_per_px_spin.setRange(0.5, 200.0)
        self._timescale_per_px_spin.setSingleStep(0.5)
        self._timescale_per_px_spin.setDecimals(1)
        self._timescale_per_px_spin.setSuffix(f" {zoom_unit}/px")
        self._timescale_per_px_spin.setValue(timescale_per_px_default)
        self._timescale_per_px_spin.setToolTip(
            f"Maximum zoom-in level (0.5\u2013200 {zoom_unit}/px).\n"
            "Also sets the target level of the 1:1 zoom button.")
        f3.addRow("1:1 zoom level:", _inp(self._timescale_per_px_spin))

        self._cursor_spin = QSpinBox()
        self._cursor_spin.setRange(4, _MAX_CURSORS)
        self._cursor_spin.setValue(max_cursors)
        self._cursor_spin.setToolTip(f"Maximum number of simultaneous cursors (4\u2013{_MAX_CURSORS})")
        f3.addRow("Max cursors:", _inp(self._cursor_spin))

        self._content_stack.addWidget(p3)

        # -- Sidebar ↔ stack sync ---------------------------------------------
        self._sidebar.currentRowChanged.connect(self._content_stack.setCurrentIndex)

        # -- Footer separator -------------------------------------------------
        footer_sep = QFrame()
        footer_sep.setFrameShape(QFrame.HLine)
        footer_sep.setFrameShadow(QFrame.Plain)
        footer_sep.setObjectName("footer_sep")
        footer_sep.setFixedHeight(1)
        root.addWidget(footer_sep)

        # -- Footer buttons ---------------------------------------------------
        footer_w = QWidget()
        footer = QHBoxLayout(footer_w)
        footer.setContentsMargins(16, 8, 16, 12)
        footer.setSpacing(14)
        footer.addStretch()

        _btn_w, _btn_h = 88, 30   # uniform size for both buttons

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("btn_cancel")
        btn_cancel.setFixedSize(_btn_w, _btn_h)
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("OK")
        btn_ok.setObjectName("btn_ok")
        btn_ok.setFixedSize(_btn_w, _btn_h)
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)

        footer.addWidget(btn_cancel)
        footer.addSpacing(8)
        footer.addWidget(btn_ok)
        root.addWidget(footer_w)

        # -- Scoped stylesheet ------------------------------------------------
        self.setStyleSheet(self._dialog_ss(is_dark, _ui_fs))

        # -- Live-preview wiring: broadcast any change to live_preview ---------
        # Each signal sends a typed argument (int/float); lambda absorbs it with
        # a default dummy parameter so all signals share a single emit adapter.
        for _sig in (
            self._theme_combo.currentIndexChanged,
            self._font_spin.valueChanged,
            self._ui_font_spin.valueChanged,
            self._cursor_spin.valueChanged,
            self._sti_cb.stateChanged,
            self._grid_cb.stateChanged,
            self._legend_cb.stateChanged,
            self._stats_cb.stateChanged,
            self._marks_cb.stateChanged,
            self._hover_hl_cb.stateChanged,
            self._label_width_spin.valueChanged,
            self._row_height_spin.valueChanged,
            self._row_gap_spin.valueChanged,
            self._timescale_per_px_spin.valueChanged,
        ):
            _sig.connect(lambda _=None: self.live_preview.emit())

        self.adjustSize()

    # -- result accessors (read after exec_() == Accepted) ------------------
    @property
    def font_size(self) -> int:           return self._font_spin.value()
    @property
    def ui_font_size(self) -> int:        return self._ui_font_spin.value()
    @property
    def max_cursors(self) -> int:         return self._cursor_spin.value()
    @property
    def show_sti(self) -> bool:           return self._sti_cb.isChecked()
    @property
    def show_grid(self) -> bool:          return self._grid_cb.isChecked()
    @property
    def show_legend(self) -> bool:        return self._legend_cb.isChecked()
    @property
    def show_stats(self) -> bool:         return self._stats_cb.isChecked()
    @property
    def label_width(self) -> int:         return self._label_width_spin.value()
    @property
    def row_height(self) -> int:          return self._row_height_spin.value()
    @property
    def row_gap(self) -> int:             return self._row_gap_spin.value()
    @property
    def timescale_per_px_default(self) -> float: return self._timescale_per_px_spin.value()
    @property
    def is_dark(self) -> bool:            return self._theme_combo.currentIndex() == 0
    @property
    def show_marks(self) -> bool:         return self._marks_cb.isChecked()
    @property
    def show_hover_highlight(self) -> bool: return self._hover_hl_cb.isChecked()
# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self):
        super().__init__()
        self._trace: Optional[BtfTrace] = None
        self._current_file: str = ""
        self._parse_thread = None
        self._progress_dialog: Optional[QProgressDialog] = None
        self._settings = _RcSettings()

        # -- Runtime state for settings managed via _SettingsDialog ----------
        self._show_sti:              bool  = True
        self._show_grid:             bool  = True
        self._show_legend:           bool  = True
        self._show_stats:            bool  = True
        self._show_marks:            bool  = True
        self._font_size_val:         int   = FONT_SIZE
        self._ui_font_size_val:      int   = UI_FONT_SIZE
        self._max_cursors_val:       int   = _DEFAULT_MAX_CURSORS
        self._label_width_val:       int   = LABEL_WIDTH
        self._row_height_val:        int   = ROW_HEIGHT
        self._row_gap_val:            int   = ROW_GAP
        self._timescale_per_px_default_val:  float = _TIMESCALE_PER_PX_DEFAULT
        self._hover_highlight_val:    bool  = _HOVER_HIGHLIGHT_ENABLED
        self._bookmarks: List[TraceBookmark] = []
        self._annotations: List[TraceAnnotation] = []
        self._mark_next_id: int = 1
        self._find_hits: List[int] = []
        self._find_hit_idx: int = -1
        self._find_marker_ns: Optional[int] = None
        self._find_marker_items: List[QGraphicsItem] = []
        self._tb_icon_actions: list = []   # (QAction, icon_path_data) for theme-aware icons

        self.setWindowTitle("BTF Trace Viewer")
        self.resize(1280, 720)

        # Apply saved theme BEFORE building the UI (affects the Qt stylesheet).
        self._is_dark = (self._settings.get("view", "theme", "dark") == "dark")
        self._apply_theme(self._is_dark)

        self._build_ui()
        self._build_menus()
        self._build_toolbar()
        self._build_status_bar()
        self._view_mode = "task"

        # Restore all persisted settings (geometry, zoom, orientation, …).
        self._restore_settings()

    # ------------------------------------------------------------------
    # Lifecycle persistence
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
        saved_fs = s.get_int("view", "font_size", FONT_SIZE)
        if saved_fs != FONT_SIZE:
            self._font_size_val = saved_fs
            self._view.set_font_size(saved_fs)

        # UI font size
        saved_ufs = s.get_int("view", "ui_font_size", UI_FONT_SIZE)
        if saved_ufs != UI_FONT_SIZE:
            self._ui_font_size_val = saved_ufs
            self._apply_theme(self._is_dark)

        # Max cursors
        saved_mc = s.get_int("view", "max_cursors", _DEFAULT_MAX_CURSORS)
        if saved_mc != _DEFAULT_MAX_CURSORS:
            self._max_cursors_val = saved_mc
            self._view.set_max_cursors(saved_mc)

        # Label column width
        saved_lw = s.get_int("view", "label_width", LABEL_WIDTH)
        if saved_lw != LABEL_WIDTH:
            self._label_width_val = saved_lw
            self._view._scene.set_label_width(saved_lw)

        # Row height
        saved_rh = s.get_int("view", "row_height", ROW_HEIGHT)
        if saved_rh != ROW_HEIGHT:
            self._row_height_val = saved_rh
            self._view._scene.set_row_height(saved_rh)

        # Row gap
        saved_rg = s.get_int("view", "row_gap", ROW_GAP)
        if saved_rg != ROW_GAP:
            self._row_gap_val = saved_rg
            self._view._scene.set_row_gap(saved_rg)

        # Max zoom-in level (timescale/px default)
        saved_nppd = s.get_float("view", "timescale_per_px_default", _TIMESCALE_PER_PX_DEFAULT)
        if saved_nppd != _TIMESCALE_PER_PX_DEFAULT:
            self._timescale_per_px_default_val = saved_nppd
            self._view._scene.set_timescale_per_px_default(saved_nppd)

        # Hover label highlight
        saved_hh = s.get_bool("view", "hover_highlight", _HOVER_HIGHLIGHT_ENABLED)
        if saved_hh != _HOVER_HIGHLIGHT_ENABLED:
            self._hover_highlight_val = saved_hh
            self._view._scene.set_hover_highlight(saved_hh)

        # Orientation (horizontal is the default)
        if not s.get_bool("view", "horizontal", True):
            self._set_orientation(False)

        # View mode
        if s.get("view", "view_mode", "task") == "core":
            self._set_view_mode("core")

        # STI / grid visibility
        if not s.get_bool("view", "show_sti", True):
            self._set_show_sti(False, persist=False)
        if not s.get_bool("view", "show_grid", True):
            self._set_show_grid(False, persist=False)

        # Legend / statistics panel visibility
        if not s.get_bool("view", "show_legend", True):
            self._show_legend = False
            self._legend_dock.setVisible(False)
        if not s.get_bool("view", "show_stats", True):
            self._show_stats = False
            self._stats_dock.setVisible(False)
        self._show_marks = s.get_bool("view", "show_marks", True)
        self._marks_dock.setVisible(self._show_marks)
        self._find_dock.setVisible(s.get_bool("view", "show_find", False))

        # Keep the Light-theme menu label in sync when we restored a light theme.
        if not self._is_dark:
            self._act_theme.setText("Switch to &Dark Theme")

        self._refresh_zoom_ui_unit()

    def closeEvent(self, event) -> None:
        """Persist all runtime state to btf_viewer.rc on exit."""
        s = self._settings

        # ---- 1. Stop all timers immediately -----------------------------------
        # Prevents any pending rebuild / zoom / resize callback from touching a
        # partially-destroyed widget tree after this point.
        self._view._zoom_timer.stop()
        self._view._pan_timer.stop()
        self._view._pan_heartbeat.stop()
        self._view._resize_timer.stop()

        # ---- 2. Abort any in-progress background parse ------------------------
        # IMPORTANT: stop the thread BEFORE disconnecting signals.
        # disconnect() destroys the PyQtSlotProxy C++ objects.  If the thread
        # is still running, PyQtSlotProxy::unislot() may execute concurrently
        # in the worker thread and call postEvent(this, ...) on the now-freed
        # proxy, causing an EXC_BAD_ACCESS / SIGBUS crash (data race).
        # After the thread is fully stopped no more unislot() calls can occur,
        # making it safe to destroy the proxies.  The proxy ~QObject() then
        # calls QObject::removePostedEvents(this, 0), purging any already-
        # queued events so they cannot be replayed during sendPostedEvents.
        if self._parse_thread is not None:
            if self._parse_thread.isRunning():
                self._parse_thread.requestInterruption()
                # Wait up to 3 s; parse threads check interruption frequently.
                self._parse_thread.wait(3000)
            # Thread is now stopped – safe to destroy PyQtSlotProxy objects.
            self._disconnect_parse_signals()
            self._parse_thread = None

        self._save_current_trace_state()
        self._persist_settings()

        # ---- 3. Hide the window immediately -----------------------------------
        # The window disappears right away so the user never sees a freeze while
        # we clean up the scene and free the trace below.
        self.hide()
        self._teardown_scene()

        super().closeEvent(event)

    def _persist_settings(self) -> None:
        """Write all runtime state to the config file (btf_viewer.rc)."""
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
            "theme":         "dark" if self._is_dark else "light",
            "horizontal":    str(self._view._scene._horizontal).lower(),
            "view_mode":     self._view_mode,
            "show_sti":      str(self._show_sti).lower(),
            "show_grid":     str(self._show_grid).lower(),
            "show_legend":   str(self._show_legend).lower(),
            "show_stats":    str(self._show_stats).lower(),
            "show_marks":    str(self._show_marks).lower(),
            "show_find":     str(self._find_dock.isVisible()).lower(),
            "font_size":     str(self._font_size_val),
            "ui_font_size":  str(self._ui_font_size_val),
            "max_cursors":   str(self._max_cursors_val),
            "label_width":       str(self._label_width_val),
            "row_height":        str(self._row_height_val),
            "row_gap":           str(self._row_gap_val),
            "timescale_per_px_default": str(self._timescale_per_px_default_val),
            "hover_highlight":   str(self._hover_highlight_val).lower(),
        })

        # Zoom – save current ns/px so we can re-apply it the next time the
        # same file is opened.  -1 means "use fit-to-width" (no saved zoom).
        if self._view._scene._trace is not None and not self._view._fit_mode:
            s.set("zoom", "timescale_per_px", str(self._view._scene.timescale_per_px))
        else:
            s.set("zoom", "timescale_per_px", "-1")

        # Cursor positions – saved as space-separated ns timestamps so they are
        # restored the next time the same file is opened.
        _cursor_times = self._view._scene.cursor_times()
        s.set("cursors", "positions",
              " ".join(str(t) for t in _cursor_times) if _cursor_times else "")

    def _teardown_scene(self) -> None:
        """Release all scene items and free trace data on a background thread.

        Called after the window is hidden so the visible freeze of freeing
        large traces is not perceptible to the user.
        """
        # ---- 4. Clear the scene explicitly ------------------------------------
        # Break all Python-side references held by scene items BEFORE calling
        # scene.clear().  Each _BatchRowItem stores _seg_data / _xs / _coarse_data
        # — lists that can contain thousands of (QRectF, QBrush, QPen, TaskSegment)
        # tuples for a large trace.  Keeping those alive until Qt's widget
        # destructor eventually frees the TimelineScene Python wrapper causes a
        # main-thread GC cascade of 100K-400K object deallocations, producing the
        # visible freeze.  Clearing them here (while the window is already hidden)
        # lets the ref-counts drop to zero immediately and allows step 5 to fully
        # offload the remaining trace teardown to the background thread.
        _scene = self._view._scene
        _scene._trace = None           # prevent any item from reading stale data
        for _item, _ in _scene._frozen_items:
            if hasattr(_item, '_seg_data'):
                _item._seg_data   = []
                _item._xs         = []
                _item._coarse_data = []
        _scene._frozen_items     = []
        _scene._frozen_top_items = []
        _scene._cursor_items     = []
        _scene._hover_overlay_items = []
        _scene._task_row_rects   = {}
        _scene.clear()
        del _scene

        # ---- 5. Free trace data on a background thread -----------------------
        # The trace can hold millions of TaskSegment objects; handing the last
        # reference to a non-daemon background thread lets Python's GC run
        # there instead of on the main thread.  Using daemon=False ensures the
        # thread is not killed prematurely at interpreter shutdown (a daemon
        # thread killed before it finishes would bounce the reference back to
        # the main-thread teardown, negating the benefit).
        _trace_to_free = self._trace
        self._trace = None
        if _trace_to_free is not None:
            def _drop(_t=_trace_to_free):
                del _t          # ref count → 0 here, GC runs on this thread
            threading.Thread(target=_drop, daemon=False).start()
            del _trace_to_free

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

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    @staticmethod
    def _theme_tokens(is_dark: bool) -> dict:
        """Return color tokens for the requested theme variant.

        All values are hex strings suitable for direct use in QSS or
        QPalette.  Edit only this method to change any theme color.
        """
        if is_dark:
            return dict(
                accent        = "#0E4D80",
                win_bg        = "#1E1E1E",
                win_base      = "#121212",
                mid           = "#2D2D2D",
                text          = "#D4D4D4",
                tooltip_bg    = "#252526",
                tooltip_border= "#555555",
                menu_bg       = "#252526",
                sep           = "#444444",
                tb_hover      = "#3C3C3C",
                tb_pressed    = "#1C5A9E",
                tb_checked_bg = "#0E4D80",
                tb_checked_fg = "#FFFFFF",
                tb_disabled   = "#555555",
                status_text   = "#AAAAAA",
                cb_border     = "#555555",
                cb_bg         = "#2D2D2D",
                input_bg      = "#2D2D2D",
                input_fg      = "#D4D4D4",
                input_border  = "#555555",
                combo_bg      = "#2D2D2D",
                combo_view_bg = "#2D2D2D",
                dock_title_bg = "#2D2D2D",
                dock_title_fg = "#AAAAAA",
                list_hover    = "#3A3A3A",
                tab_bg        = "#2D2D2D",
                tab_fg        = "#888888",
                tab_sel_bg    = "#1E1E1E",
                tab_sel_fg    = "#FFFFFF",
                tab_hover_bg  = "#3C3C3C",
                tab_hover_fg  = "#D4D4D4",
                scroll_bg     = "#1E1E1E",
                sb_bg         = "#2A2A2A",
                sb_handle     = "#555555",
                sb_handle_hov = "#777777",
                sub_text      = "#888888",
                muted_text    = "#999999",
                welcome_h2    = "#888888",
                welcome_p     = "#666666",
            )
        return dict(
            accent        = "#005A9E",
            win_bg        = "#F5F5F5",
            win_base      = "#FFFFFF",
            mid           = "#E0E0E0",
            text          = "#1E1E1E",
            tooltip_bg    = "#FFFFCC",
            tooltip_border= "#AAAAAA",
            menu_bg       = "#F5F5F5",
            sep           = "#C0C0C0",
            tb_hover      = "#D0D0D0",
            tb_pressed    = "#AACCEE",
            tb_checked_bg = "#B3D1EE",
            tb_checked_fg = "#005A9E",
            tb_disabled   = "#BBBBBB",
            status_text   = "#555555",
            cb_border     = "#AAAAAA",
            cb_bg         = "#FFFFFF",
            input_bg      = "#FFFFFF",
            input_fg      = "#1E1E1E",
            input_border  = "#AAAAAA",
            combo_bg      = "#F5F5F5",
            combo_view_bg = "#FFFFFF",
            dock_title_bg = "#E0E0E0",
            dock_title_fg = "#555555",
            list_hover    = "#E8E8E8",
            tab_bg        = "#E0E0E0",
            tab_fg        = "#666666",
            tab_sel_bg    = "#F5F5F5",
            tab_sel_fg    = "#1E1E1E",
            tab_hover_bg  = "#D0D0D0",
            tab_hover_fg  = "#1E1E1E",
            scroll_bg     = "#F5F5F5",
            sb_bg         = "#EBEBEB",
            sb_handle     = "#BBBBBB",
            sb_handle_hov = "#999999",
            sub_text      = "#555555",
            muted_text    = "#666666",
            welcome_h2    = "#555555",
            welcome_p     = "#444444",
        )

    def _apply_theme(self, is_dark: bool) -> None:
        """Apply the dark or light UI theme to the entire application.

        This is the single authoritative method for all theme changes.
        Color values are defined in ``_theme_tokens``; all QSS and widget
        overrides are driven from that table so there is only one place
        to edit when adjusting a color.
        """
        app = QApplication.instance()

        # Application-wide font (menus, toolbar, status bar).
        _ui_font_size = getattr(self, '_ui_font_size_val', UI_FONT_SIZE)
        _ui_fs = f"{_ui_font_size}pt"
        base_font = app.font()
        base_font.setPointSize(_ui_font_size)
        app.setFont(base_font)

        c = self._theme_tokens(is_dark)

        # --- Qt palette ---------------------------------------------------
        palette = QPalette()
        palette.setColor(QPalette.Window,          QColor(c['win_bg']))
        palette.setColor(QPalette.WindowText,      QColor(c['text']))
        palette.setColor(QPalette.Base,            QColor(c['win_base']))
        palette.setColor(QPalette.AlternateBase,   QColor(c['mid']))
        palette.setColor(QPalette.Text,            QColor(c['text']))
        palette.setColor(QPalette.Button,          QColor(c['mid']))
        palette.setColor(QPalette.ButtonText,      QColor(c['text']))
        palette.setColor(QPalette.Highlight,       QColor(c['accent']))
        palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
        palette.setColor(QPalette.Link,            QColor(c['accent']))
        palette.setColor(QPalette.ToolTipBase,     QColor(c['tooltip_bg']))
        palette.setColor(QPalette.ToolTipText,     QColor(c['text']))
        app.setPalette(palette)

        # --- App-wide QSS -------------------------------------------------
        app.setStyleSheet(f"""
            QToolTip  {{ background:{c['tooltip_bg']}; color:{c['text']}; border:1px solid {c['tooltip_border']};
                         padding:4px; font-size:{_ui_fs}; }}
            QMenuBar  {{ background:{c['mid']}; color:{c['text']}; font-size:{_ui_fs}; }}
            QMenuBar::item:selected {{ background:{c['accent']}; color:#FFFFFF; }}
            QMenu     {{ background:{c['menu_bg']}; color:{c['text']}; font-size:{_ui_fs}; }}
            QMenu::item:selected {{ background:{c['accent']}; color:#FFFFFF; }}
            QToolBar  {{ background:{c['mid']}; border:none; spacing:4px;
                         font-size:{_ui_fs}; }}
            QToolBar::separator {{ width:1px; background:{c['sep']}; margin:3px 2px; }}
            QToolButton {{ font-size:{_ui_fs}; }}
            QToolButton:hover    {{ background:{c['tb_hover']};      border-radius:3px; }}
            QToolButton:pressed  {{ background:{c['tb_pressed']};    border-radius:3px; }}
            QToolButton:checked  {{ background:{c['tb_checked_bg']}; border-radius:3px; color:{c['tb_checked_fg']}; }}
            QToolButton:disabled {{ color:{c['tb_disabled']}; }}
            QStatusBar  {{ background:{c['win_bg']}; color:{c['status_text']}; font-size:{_ui_fs};
                           border-top:1px solid {c['sep']}; }}
            QStatusBar QLabel {{ font-size:{_ui_fs}; color:{c['sub_text']}; }}
            QStatusBar QCheckBox {{ font-size:{_ui_fs}; color:{c['sub_text']}; padding: 0 4px; }}
            QLabel      {{ font-size:{_ui_fs}; }}
            QCheckBox   {{ font-size:{_ui_fs}; }}
            QCheckBox::indicator              {{ width:13px; height:13px; border-radius:2px;
                         border:1.5px solid {c['cb_border']}; background:{c['cb_bg']}; }}
            QCheckBox::indicator:checked     {{ background:{c['accent']}; border-color:{c['accent']}; }}
            QSpinBox, QDoubleSpinBox {{ background:{c['input_bg']}; color:{c['input_fg']};
                         border:1px solid {c['input_border']}; font-size:{_ui_fs};
                         padding:2px 6px; min-height:1.6em; }}
            QLineEdit   {{ background:{c['input_bg']}; color:{c['input_fg']};
                         border:1px solid {c['input_border']}; }}
            QComboBox   {{ background:{c['combo_bg']}; color:{c['text']};
                         border:1px solid {c['input_border']}; font-size:{_ui_fs};
                         padding:2px 6px; min-height:1.6em; }}
            QComboBox QAbstractItemView {{ background:{c['combo_view_bg']}; color:{c['text']};
                         selection-background-color:{c['accent']}; selection-color:#FFFFFF;
                         font-size:{_ui_fs}; }}
            QDockWidget::title {{ background:{c['dock_title_bg']}; color:{c['dock_title_fg']};
                                  padding:4px; font-size:{_ui_fs}; }}
            QPushButton {{ font-size:{_ui_fs}; }}
            QListWidget {{ font-size:{_ui_fs}; }}
            QListWidget::item {{ font-size:{_ui_fs}; }}
            QListWidget::item:selected {{ background:{c['accent']}; color:#FFFFFF; }}
            QListWidget::item:hover:!selected {{ background:{c['list_hover']}; }}
            QTabBar::tab               {{ background:{c['tab_bg']}; color:{c['tab_fg']};
                                           padding:4px 12px; border:none;
                                           border-bottom:2px solid transparent;
                                           font-size:{_ui_fs}; }}
            QTabBar::tab:selected      {{ background:{c['tab_sel_bg']}; color:{c['tab_sel_fg']};
                                           border-bottom:2px solid {c['accent']}; }}
            QTabBar::tab:hover:!selected {{ background:{c['tab_hover_bg']}; color:{c['tab_hover_fg']}; }}
            QScrollArea {{ background:{c['scroll_bg']}; border:none; }}
            QScrollBar:vertical   {{ background:{c['sb_bg']}; width:10px;
                                     border:none; margin:0; }}
            QScrollBar:horizontal {{ background:{c['sb_bg']}; height:10px;
                                     border:none; margin:0; }}
            QScrollBar::handle:vertical   {{ background:{c['sb_handle']};
                                             min-height:20px; border-radius:5px; margin:1px; }}
            QScrollBar::handle:horizontal {{ background:{c['sb_handle']};
                                             min-width:20px; border-radius:5px; margin:1px; }}
            QScrollBar::handle:vertical:hover,
            QScrollBar::handle:horizontal:hover {{ background:{c['sb_handle_hov']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical   {{ height:0; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical   {{ background:none; }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background:none; }}
        """)

        # --- Per-widget overrides not reachable via app-wide QSS ----------
        if hasattr(self, '_range_stats_label'):
            self._range_stats_label.setStyleSheet(f"color:{c['muted_text']};")
        if hasattr(self, '_find_status'):
            self._find_status.setStyleSheet(f"color:{c['muted_text']};")
        if hasattr(self, '_welcome_label'):
            self._welcome_label.setText(
                f"<h2 style='color:{c['welcome_h2']};'>BTF Trace Viewer</h2>"
                f"<p style='color:{c['welcome_p']}; font-size:11pt;'>"
                "Drop a <b>.btf</b> file here<br>"
                "or press <b>Ctrl+O</b> to open one</p>"
            )
        if hasattr(self, '_legend'):
            self._legend.update_theme(is_dark)
        if hasattr(self, '_cursor_bar'):
            self._cursor_bar.update_theme(is_dark)
        if getattr(self, '_tb_icon_actions', None):
            _ic_color = "#CCCCCC" if is_dark else "#555555"
            for _act, _ic_path in self._tb_icon_actions:
                _act.setIcon(_svg_icon(_ic_path, _ic_color))
        if hasattr(self, '_act_theme'):
            self._act_theme.setText(
                "Switch to &Light Theme" if is_dark else "Switch to &Dark Theme"
            )

    # Thin wrappers kept for any external callers.
    def _apply_dark_theme(self)  -> None: self._apply_theme(True)
    def _apply_light_theme(self) -> None: self._apply_theme(False)

    def _toggle_theme(self) -> None:
        self._is_dark = not self._is_dark
        self._apply_theme(self._is_dark)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # --- Central widget: QStackedWidget (page 0=welcome, page 1=timeline) ---
        self._view = TimelineView(self)
        self._view.zoom_changed.connect(self._on_zoom_changed)
        self._view.cursors_changed.connect(self._on_cursors_changed)
        self._view.bookmark_requested.connect(self._add_bookmark_at_ns)
        self._view.annotation_requested.connect(self._add_annotation_at_ns)

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
        self._welcome_label = _wlbl

        self._stack = QStackedWidget()
        self._stack.addWidget(self._welcome_page)   # index 0
        self._stack.addWidget(self._view)            # index 1
        self._stack.setCurrentIndex(0)
        self.setCentralWidget(self._stack)

        # --- Legend dock (right panel) ---
        self._legend = _LegendWidget()
        self._legend.setMinimumWidth(180)
        # No setMaximumWidth — the widget must fill the full dock column width so the
        # QScrollArea's scrollbar lands flush at the right edge.  The dock column width
        # is governed by resizeDocks() below; a fixed cap here would leave a blank gap
        # to the right of the legend whenever the Marks dock makes the column wider.
        dock = QDockWidget("Legend", self)
        dock.setWidget(self._legend)
        dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self._legend_dock = dock

        # --- Statistics dock (bottom panel) ---
        self._stats_panel = _StatsPanel()
        stats_dock = QDockWidget("Statistics", self)
        stats_dock.setWidget(self._stats_panel)
        stats_dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.RightDockWidgetArea, stats_dock)
        self._stats_dock = stats_dock

        # --- Marks dock (bookmarks + annotations) ---
        marks_host = QWidget()
        marks_v = QVBoxLayout(marks_host)
        marks_v.setContentsMargins(6, 6, 6, 6)
        marks_v.setSpacing(6)
        marks_tabs = QTabWidget()

        bm_page = QWidget()
        bm_v = QVBoxLayout(bm_page)
        bm_v.setContentsMargins(0, 0, 0, 0)
        bm_v.setSpacing(4)
        self._bookmark_list = QListWidget()
        self._bookmark_list.itemDoubleClicked.connect(lambda item: self._jump_to_ns(int(item.data(Qt.UserRole + 1))))
        self._bookmark_list.itemChanged.connect(self._on_bookmark_item_changed)
        bm_v.addWidget(self._bookmark_list)
        bm_btns = QHBoxLayout()
        bm_btns.setContentsMargins(0, 0, 0, 0)
        bm_add = QPushButton("Add")
        bm_add.clicked.connect(self._add_bookmark_at_center)
        bm_jump = QPushButton("Jump")
        bm_jump.clicked.connect(self._jump_selected_bookmark)
        bm_del = QPushButton("Delete")
        bm_del.clicked.connect(self._delete_selected_bookmark)
        bm_btns.addWidget(bm_add)
        bm_btns.addWidget(bm_jump)
        bm_btns.addWidget(bm_del)
        bm_v.addLayout(bm_btns)
        marks_tabs.addTab(bm_page, "Bookmarks")

        an_page = QWidget()
        an_v = QVBoxLayout(an_page)
        an_v.setContentsMargins(0, 0, 0, 0)
        an_v.setSpacing(4)
        self._annotation_list = QListWidget()
        self._annotation_list.itemDoubleClicked.connect(
            lambda item: self._edit_selected_annotation())
        an_v.addWidget(self._annotation_list)
        self._annotation_input = QLineEdit()
        self._annotation_input.setPlaceholderText("Annotation note...")
        self._annotation_input.returnPressed.connect(self._add_annotation_at_center)
        an_v.addWidget(self._annotation_input)
        an_btns = QHBoxLayout()
        an_btns.setContentsMargins(0, 0, 0, 0)
        an_add = QPushButton("Add")
        an_add.clicked.connect(self._add_annotation_at_center)
        an_jump = QPushButton("Jump")
        an_jump.clicked.connect(self._jump_selected_annotation)
        an_edit = QPushButton("Edit")
        an_edit.clicked.connect(self._edit_selected_annotation)
        an_del = QPushButton("Delete")
        an_del.clicked.connect(self._delete_selected_annotation)
        an_btns.addWidget(an_add)
        an_btns.addWidget(an_jump)
        an_btns.addWidget(an_edit)
        an_btns.addWidget(an_del)
        an_v.addLayout(an_btns)
        marks_tabs.addTab(an_page, "Annotations")
        marks_v.addWidget(marks_tabs)
        self._range_stats_label = QLabel("Range: place two cursors to measure")
        self._range_stats_label.setStyleSheet("color:#999;")
        self._range_stats_label.setWordWrap(True)
        marks_v.addWidget(self._range_stats_label)
        marks_io_row = QHBoxLayout()
        marks_import_btn = QPushButton("↓ Import Marks")
        marks_import_btn.setToolTip("Load bookmarks and annotations from a CSV file")
        marks_import_btn.clicked.connect(self._import_marks_csv)
        marks_io_row.addWidget(marks_import_btn)
        marks_export_btn = QPushButton("↑ Export Marks")
        marks_export_btn.setToolTip("Save all bookmarks and annotations to a CSV file")
        marks_export_btn.clicked.connect(self._export_marks_csv)
        marks_io_row.addWidget(marks_export_btn)
        marks_v.addLayout(marks_io_row)

        marks_dock = QDockWidget("Marks", self)
        marks_dock.setWidget(marks_host)
        marks_dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        marks_dock.setMinimumWidth(190)
        marks_dock.setMinimumHeight(120)
        self.addDockWidget(Qt.RightDockWidgetArea, marks_dock)
        self._marks_dock = marks_dock

        # --- Find dock ---
        find_host = QWidget()
        find_v = QVBoxLayout(find_host)
        find_v.setContentsMargins(6, 6, 6, 6)
        find_v.setSpacing(6)
        self._find_input = QLineEdit()
        self._find_input.setPlaceholderText("Find task or annotation text...")
        self._find_input.textChanged.connect(self._recompute_find_hits)
        find_v.addWidget(self._find_input)
        self._find_mode_combo = QComboBox()
        self._find_mode_combo.addItems(["Contains", "Exact", "Regex"])
        self._find_mode_combo.setCurrentIndex(0)
        self._find_mode_combo.currentIndexChanged.connect(self._recompute_find_hits)
        find_v.addWidget(self._find_mode_combo)
        find_btns = QHBoxLayout()
        find_btns.setContentsMargins(0, 0, 0, 0)
        find_prev = QPushButton("Previous")
        find_prev.clicked.connect(self._find_prev)
        find_next = QPushButton("Next")
        find_next.clicked.connect(self._find_next)
        find_btns.addWidget(find_prev)
        find_btns.addWidget(find_next)
        find_v.addLayout(find_btns)
        self._find_status = QLabel("0 matches")
        self._find_status.setStyleSheet("color:#999;")
        find_v.addWidget(self._find_status)
        find_dock = QDockWidget("Find & Jump", self)
        find_dock.setWidget(find_host)
        find_dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        find_dock.setMinimumWidth(190)
        find_dock.setMaximumWidth(260)
        find_dock.setMinimumHeight(120)
        self.addDockWidget(Qt.RightDockWidgetArea, find_dock)
        self.tabifyDockWidget(self._marks_dock, find_dock)
        self._find_dock = find_dock
        self.tabifyDockWidget(find_dock, self._stats_dock)

        # Put Marks below Legend and keep its startup height compact.
        self.splitDockWidget(self._legend_dock, self._marks_dock, Qt.Vertical)
        self.resizeDocks(
            [self._legend_dock, self._marks_dock],
            [420, 150],
            Qt.Vertical,
        )

        # Keep right-side width compact on startup.
        self.resizeDocks(
            [self._legend_dock, self._marks_dock],
            [220, 220],
            Qt.Horizontal,
        )

        # Keep runtime state in sync if the user closes a dock via its X button
        self._legend_dock.visibilityChanged.connect(
            lambda v: setattr(self, "_show_legend", v))
        self._stats_dock.visibilityChanged.connect(
            lambda v: setattr(self, "_show_stats", v))
        self._marks_dock.visibilityChanged.connect(
            lambda v: setattr(self, "_show_marks", v))
        self._find_dock.visibilityChanged.connect(self._on_find_dock_visibility_changed)
        self._view.horizontalScrollBar().valueChanged.connect(lambda _: self._on_view_scrolled())
        self._view.verticalScrollBar().valueChanged.connect(lambda _: self._on_view_scrolled())

        # --- Signal wiring: legend ↔ scene highlight sync ---
        # Legend click → toggle locked highlight
        sc = self._view._scene
        self._legend.task_clicked.connect(self._on_legend_task_clicked)
        self._legend.cancel_highlight.connect(
            lambda: sc.set_highlighted_task(None)
        )
        self._legend.filter_changed.connect(sc.set_task_filter)
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
        self._recent_menu = fm.addMenu("Open &Recent")
        self._rebuild_recent_menu()
        fm.addSeparator()
        self._act_save_img = fm.addAction("Save as &Image (PNG)…", self._on_save_image, "Ctrl+S")
        self._act_save_img.setEnabled(False)
        self._act_copy_img = fm.addAction("&Copy Image to Clipboard", self._on_copy_image, "Ctrl+Shift+C")
        self._act_copy_img.setEnabled(False)
        fm.addSeparator()
        _quit_act = fm.addAction("E&xit", self.close)
        # QKeySequence.Quit = Ctrl+Q on macOS/Linux; unmapped on Windows (Alt+F4 used there).
        # Provide Ctrl+Q explicitly so it works on all platforms.
        _quit_act.setShortcut(QKeySequence("Ctrl+Q"))

        # --- View menu (layout, visibility, zoom, mode, theme) ---
        vm = mb.addMenu("&View")
        self._act_horiz = vm.addAction("&Horizontal layout", lambda: self._set_orientation(True))
        self._act_vert  = vm.addAction("&Vertical layout",   lambda: self._set_orientation(False))
        self._act_horiz.setCheckable(True)
        self._act_vert.setCheckable(True)
        self._act_horiz.setChecked(True)
        vm.addSeparator()
        vm.addAction("&Zoom In",        self._view.zoom_in,   QKeySequence.ZoomIn)
        vm.addAction("Zoom &Out",       self._view.zoom_out,  QKeySequence.ZoomOut)
        vm.addAction("&Fit to window",  self._view.zoom_fit,  "Ctrl+0")
        vm.addSeparator()
        self._act_task_view = vm.addAction("Task &View", lambda: self._set_view_mode("task"))
        self._act_core_view = vm.addAction("&Core View", lambda: self._set_view_mode("core"))
        self._act_task_view.setCheckable(True)
        self._act_core_view.setCheckable(True)
        self._act_task_view.setChecked(True)
        vm.addSeparator()
        self._act_theme = vm.addAction("Switch to &Light Theme", self._toggle_theme)
        vm.addSeparator()
        vm.addAction("⚙ &Settings…", self._open_settings, "Ctrl+,")
        vm.addSeparator()
        self._act_show_marks = vm.addAction("Show &Marks Panel",
            lambda: self._marks_dock.setVisible(not self._marks_dock.isVisible()))
        self._act_show_marks.setCheckable(True)
        self._act_show_marks.setChecked(True)
        self._act_show_find = vm.addAction("Show &Find Panel",
            lambda: self._find_dock.setVisible(not self._find_dock.isVisible()))
        self._act_show_find.setCheckable(True)
        self._act_show_find.setChecked(False)

        # --- Cursors menu ---
        cm = mb.addMenu("&Cursors")
        cm.addAction("Place cursor at centre\tC",
                     self._view.add_cursor_at_view_center, "C")
        cm.addAction("Clear all cursors\tShift+C",
                     self._view.clear_cursors, "Shift+C")
        cm.addSeparator()
        cm.addAction("Tip: Left-click on timeline to place cursor").setEnabled(False)
        cm.addAction("Right-click on timeline to remove nearest cursor").setEnabled(False)

        # --- Navigate menu ---
        nm = mb.addMenu("&Navigate")
        nm.addAction("Add &Bookmark", self._add_bookmark_at_center, "Ctrl+B")
        nm.addAction("Add &Annotation…", self._prompt_annotation_at_center, "Ctrl+Shift+B")
        nm.addSeparator()
        self._act_zoom_range = nm.addAction(
            "Zoom to Cursor &Range", self._zoom_to_cursor_range, "Ctrl+R"
        )
        self._act_zoom_range.setEnabled(False)
        nm.addSeparator()
        nm.addAction("Jump to &Start", self._jump_to_trace_start, "Ctrl+Home")
        nm.addAction("Jump to En&d",   self._jump_to_trace_end,   "Ctrl+End")
        nm.addSeparator()
        nm.addAction("&Find", self._focus_find, QKeySequence.Find)
        nm.addAction("Find &Next", self._find_next, QKeySequence.FindNext)
        nm.addAction("Find &Previous", self._find_prev, QKeySequence.FindPrevious)

        # --- Help menu ---
        hm = mb.addMenu("&Help")
        hm.addAction("&Keyboard Shortcuts…", self._on_keyboard_shortcuts)
        hm.addSeparator()
        hm.addAction("&About", self._on_about)

        # Sync Show Marks / Show Find check state with dock X-button
        self._marks_dock.visibilityChanged.connect(self._act_show_marks.setChecked)
        self._find_dock.visibilityChanged.connect(self._act_show_find.setChecked)

    def _build_toolbar(self) -> None:
        tb = self.addToolBar("Main")
        self._tb = tb
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
        tb.setIconSize(QSize(18, 18))

        self._tb_icon_actions = []

        def _ia(text: str, handler, ic_path: str, tooltip: str = ""):
            act = tb.addAction(text, handler)
            act.setIcon(_svg_icon(ic_path))
            if tooltip:
                act.setToolTip(tooltip)
            self._tb_icon_actions.append((act, ic_path))
            return act

        # --- File actions ---
        _ia("Open",     self._on_open,         _IC_OPEN, "Open BTF trace file  (Ctrl+O)")
        _ia("Save PNG", self._on_save_image,   _IC_SAVE, "Save viewport as PNG  (Ctrl+S)")
        _ia("Copy",     self._on_copy_image,   _IC_COPY, "Copy viewport to clipboard  (Ctrl+Shift+C)")
        tb.addSeparator()

        # --- Layout and zoom ---
        self._tb_horiz_btn = _ia("Horizontal", lambda: self._set_orientation(True),  _IC_HORIZ)
        self._tb_vert_btn  = _ia("Vertical",   lambda: self._set_orientation(False), _IC_VERT)
        self._tb_horiz_btn.setCheckable(True)
        self._tb_vert_btn.setCheckable(True)
        self._tb_horiz_btn.setChecked(True)   # default: horizontal
        self._tb_horiz_btn.setToolTip("Horizontal layout — time runs left → right")
        self._tb_vert_btn.setToolTip("Vertical layout — time runs top → bottom")
        tb.addSeparator()
        _ia("Zoom In",  self._view.zoom_in,  _IC_ZIN,  "Zoom in  (Ctrl++)")
        _ia("Zoom Out", self._view.zoom_out, _IC_ZOUT, "Zoom out  (Ctrl+-)")
        self._act_zoom_1to1 = _ia("1:1", self._view.zoom_1to1, _IC_1TO1, "Zoom to 1:1 scale")
        _ia("Fit",   self._view.zoom_fit,          _IC_FIT,    "Fit entire trace to window  (Ctrl+0)")
        self._tb_zoom_range_btn = _ia("Range", self._zoom_to_cursor_range, _IC_EXPAND,
                                      "Zoom view to fit between cursor C1 and C2  (Ctrl+R)")
        self._tb_zoom_range_btn.setEnabled(False)
        tb.addSeparator()

        # --- View mode toggle (Task / Core) ---
        self._tb_task_btn = _ia("Task", lambda: self._set_view_mode("task"), _IC_TASK,
                                "Task View — one row per task, merges across cores")
        self._tb_core_btn = _ia("Core", lambda: self._set_view_mode("core"), _IC_CORE,
                                "Core View — one expandable row per CPU core")
        self._tb_task_btn.setCheckable(True)
        self._tb_core_btn.setCheckable(True)
        self._tb_task_btn.setChecked(True)
        # Task/Core are mode toggles — show short text beside icon so the active
        # state is readable at a glance without hovering.
        for _mode_act in (self._tb_task_btn, self._tb_core_btn):
            _mw = tb.widgetForAction(_mode_act)
            if _mw:
                _mw.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._tb_expand_all_btn = _ia("Expand All", self._toggle_expand_all_cores,
                                      _IC_EXPAND_ALL,
                                      "Expand / collapse all cores  (only in Core View)")
        self._tb_expand_all_btn.setCheckable(True)
        self._tb_expand_all_btn.setChecked(True)   # default: all expanded
        self._tb_expand_all_btn.setEnabled(False)   # only active in core view
        tb.addSeparator()

        # --- Cursor controls ---
        _ia("Place Cursor", self._view.add_cursor_at_view_center, _IC_CURSOR,
            "Place cursor at viewport centre  (C)")
        _ia("Clear Cursors", self._view.clear_cursors, _IC_CLEAR,
            "Clear all cursors  (Shift+C)")
        tb.addSeparator()

        # --- Settings button ---
        _ia("Settings", self._open_settings, _IC_SETTINGS, "Open Settings  (Ctrl+,)")

    def _build_status_bar(self) -> None:
        sb = self.statusBar()

        # --- LEFT: file info (stretches to fill available space) ---
        self._status_file  = QLabel("No file loaded")
        self._status_file.setContentsMargins(4, 0, 8, 0)

        # --- CENTER: cursor badge bar (permanent, but visually central) ---
        self._cursor_bar   = _CursorBarWidget()
        self._cursor_bar.jump_requested.connect(self._view.scroll_to_ns)
        self._cursor_bar.cursor_delete_requested.connect(self._on_cursor_delete)

        # --- Cursor range stats (compact; shown only when ≥2 cursors active) ---
        self._status_range = QLabel("")
        self._status_range.setContentsMargins(6, 0, 6, 0)
        self._status_range.setVisible(False)

        # --- RIGHT permanent zone ---

        # Quick view toggles — compact pill-style checkboxes
        self._sti_toggle_cb = QCheckBox("STI")
        self._sti_toggle_cb.setChecked(self._show_sti)
        self._sti_toggle_cb.setToolTip("Show or hide STI event markers")
        self._sti_toggle_cb.toggled.connect(self._set_show_sti)

        self._grid_toggle_cb = QCheckBox("Grid")
        self._grid_toggle_cb.setChecked(self._show_grid)
        self._grid_toggle_cb.setToolTip("Show or hide the time grid")
        self._grid_toggle_cb.toggled.connect(self._set_show_grid)

        # Zoom indicator — concise "10 ns/px" format, no label prefix
        self._zoom_label = QLabel("—")
        self._zoom_label.setContentsMargins(8, 0, 8, 0)
        self._zoom_label.setToolTip("Current zoom level (time per pixel)")

        sb.addWidget(self._status_file)
        sb.addPermanentWidget(self._cursor_bar)
        sb.addPermanentWidget(self._status_range)
        sb.addPermanentWidget(self._sti_toggle_cb)
        sb.addPermanentWidget(self._grid_toggle_cb)
        sb.addPermanentWidget(self._zoom_label)

        # Show interaction hint as a timed splash once the window is fully shown.
        # Delay avoids the overlap with _status_file that occurs when showMessage()
        # is called before Qt has finished laying out the status bar widgets.
        QTimer.singleShot(500, lambda: self.statusBar().showMessage(
            "Left-click: cursor  |  Ctrl+Wheel: zoom  |  Scroll: pan", 6000))

    # ------------------------------------------------------------------
    # Slots / callbacks
    # ------------------------------------------------------------------

    # -- View actions ---------------------------------------------------

    def _set_orientation(self, horizontal: bool) -> None:
        self._act_horiz.setChecked(horizontal)
        self._act_vert.setChecked(not horizontal)
        self._tb_horiz_btn.setChecked(horizontal)
        self._tb_vert_btn.setChecked(not horizontal)
        self._view.set_horizontal(horizontal)
        self._refresh_find_marker()

    def _set_show_sti(self, show: bool, persist: bool = True) -> None:
        """Apply STI visibility and keep all STI UI controls in sync."""
        self._show_sti = bool(show)
        self._view.set_show_sti(self._show_sti)
        if self._trace is not None:
            self._legend.rebuild(self._trace, show_sti=self._show_sti)
            self._legend.set_locked_task(self._view._scene._locked_task)
        if hasattr(self, "_sti_toggle_cb"):
            self._sti_toggle_cb.blockSignals(True)
            self._sti_toggle_cb.setChecked(self._show_sti)
            self._sti_toggle_cb.blockSignals(False)
        if persist:
            self._settings.set("view", "show_sti", str(self._show_sti).lower())

    def _set_show_grid(self, show: bool, persist: bool = True) -> None:
        """Apply grid visibility and keep all Grid UI controls in sync."""
        self._show_grid = bool(show)
        self._view.set_show_grid(self._show_grid)
        if hasattr(self, "_grid_toggle_cb"):
            self._grid_toggle_cb.blockSignals(True)
            self._grid_toggle_cb.setChecked(self._show_grid)
            self._grid_toggle_cb.blockSignals(False)
        if persist:
            self._settings.set("view", "show_grid", str(self._show_grid).lower())

    def _current_time_unit(self) -> str:
        if self._trace is not None and getattr(self._trace, "time_scale", ""):
            return self._trace.time_scale
        return "ns"

    def _refresh_zoom_ui_unit(self) -> None:
        unit = self._current_time_unit()
        self._act_zoom_1to1.setToolTip(
            f"Zoom to {self._timescale_per_px_default_val:.1f} {unit}/pixel"
        )
        if self._trace is None:
            self._zoom_label.setText("—")
            return
        self._on_zoom_changed(self._view._scene.timescale_per_px)

    def _set_view_mode(self, mode: str) -> None:
        self._view_mode = mode
        is_task = (mode == "task")
        self._act_task_view.setChecked(is_task)
        self._act_core_view.setChecked(not is_task)
        self._tb_task_btn.setChecked(is_task)
        self._tb_core_btn.setChecked(not is_task)
        self._tb_expand_all_btn.setEnabled(not is_task)
        if not is_task:
            # Sync button state with actual core expanded state
            scene = self._view._scene
            trace = scene._trace
            if trace and trace.core_names:
                all_expanded = all(
                    scene._core_expanded.get(c, True) for c in trace.core_names)
                self._tb_expand_all_btn.setChecked(all_expanded)
        self._view.set_view_mode(mode)
        self._refresh_find_marker()

    def _toggle_expand_all_cores(self) -> None:
        """Expand or collapse all cores based on the button's checked state."""
        expanded = self._tb_expand_all_btn.isChecked()
        self._view.set_all_cores_expanded(expanded)

    # -- File actions ---------------------------------------------------

    def _on_open(self) -> None:
        last_dir = self._settings.get("files", "last_dir", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(
            self, "Open BTF trace", last_dir,
            "BTF files (*.btf);;All files (*)"
        )
        if path:
            self._open_file(path)

    def _save_recent_files(self, path: str) -> None:
        norm = os.path.abspath(path)
        raw = self._settings.get("files", "recent", "")
        existing = [p for p in raw.split("|") if p.strip() and p != norm]
        recent = [norm] + existing
        self._settings.set("files", "recent", "|".join(recent[:5]))

    def _rebuild_recent_menu(self) -> None:
        self._recent_menu.clear()
        raw = self._settings.get("files", "recent", "")
        paths = [p for p in raw.split("|") if p.strip()]
        if not paths:
            act = self._recent_menu.addAction("No recent files")
            act.setEnabled(False)
            return
        for p in paths:
            parts = p.replace("\\", "/").split("/")
            label = "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
            self._recent_menu.addAction(label, lambda checked=False, _p=p: self._open_file(_p)) \
                .setToolTip(p)

    def _trace_state_key(self, path: str) -> str:
        norm = os.path.abspath(path)
        digest = zlib.crc32(norm.encode("utf-8")) & 0xFFFFFFFF
        return f"trace_{digest:08x}"

    def _save_current_trace_state(self) -> None:
        if not self._current_file:
            return
        key = self._trace_state_key(self._current_file)
        payload = {
            "next_id": self._mark_next_id,
            "bookmarks": [{"id": b.id, "ns": b.ns, "label": b.label} for b in self._bookmarks],
            "annotations": [{"id": a.id, "ns": a.ns, "note": a.note} for a in self._annotations],
        }
        self._settings.set("trace_state", key, json.dumps(payload, ensure_ascii=True))

    def _load_trace_state(self, path: str) -> None:
        self._bookmarks = []
        self._annotations = []
        self._mark_next_id = 1
        raw = self._settings.get("trace_state", self._trace_state_key(path), "")
        if raw.strip():
            try:
                payload = json.loads(raw)
                max_id = 0
                for entry in payload.get("bookmarks", []):
                    bid = int(entry.get("id", 0))
                    if bid <= 0:
                        bid = max_id + 1
                    b = TraceBookmark(bid, int(entry.get("ns", 0)), str(entry.get("label", "")).strip())
                    self._bookmarks.append(b)
                    max_id = max(max_id, b.id)
                for entry in payload.get("annotations", []):
                    note = str(entry.get("note", "")).strip()
                    aid = int(entry.get("id", 0))
                    if aid <= 0:
                        aid = max_id + 1
                    a = TraceAnnotation(aid, int(entry.get("ns", 0)), note)
                    self._annotations.append(a)
                    max_id = max(max_id, a.id)
                self._mark_next_id = max(int(payload.get("next_id", 0)), max_id + 1)
            except (ValueError, TypeError):
                pass
        if self._mark_next_id < 1:
            self._mark_next_id = 1
        self._rebuild_bookmark_list()
        self._rebuild_annotation_list()

    def _jump_to_ns(self, ns: int) -> None:
        if self._trace is None:
            return
        self._view.scroll_to_ns(ns)

    def _add_bookmark_at_center(self) -> None:
        if self._trace is None:
            return
        ns = self._view.view_center_ns()
        unit = self._current_time_unit()
        label = f"Bookmark @{_format_time(ns, unit)}"
        self._bookmarks.append(TraceBookmark(id=self._mark_next_id, ns=ns, label=label))
        self._mark_next_id += 1
        self._bookmarks.sort(key=lambda b: b.ns)
        self._rebuild_bookmark_list()
        self._save_current_trace_state()

    def _jump_selected_bookmark(self) -> None:
        item = self._bookmark_list.currentItem()
        if item is None:
            return
        self._jump_to_ns(int(item.data(Qt.UserRole + 1)))

    def _delete_selected_bookmark(self) -> None:
        item = self._bookmark_list.currentItem()
        if item is None:
            return
        bid = int(item.data(Qt.UserRole))
        for i, b in enumerate(self._bookmarks):
            if b.id == bid:
                self._bookmarks.pop(i)
                break
        self._rebuild_bookmark_list()
        self._save_current_trace_state()

    def _rebuild_bookmark_list(self) -> None:
        self._bookmark_list.blockSignals(True)
        self._bookmark_list.clear()
        if self._trace is None:
            self._bookmark_list.blockSignals(False)
            return
        unit = self._current_time_unit()
        for b in sorted(self._bookmarks, key=lambda x: x.ns):
            txt = b.label or f"Bookmark @{_format_time(b.ns, unit)}"
            item = QListWidgetItem(txt)
            item.setData(Qt.UserRole, int(b.id))
            item.setData(Qt.UserRole + 1, int(b.ns))
            item.setToolTip(f"{_format_time(b.ns, unit)}")
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self._bookmark_list.addItem(item)
        self._bookmark_list.blockSignals(False)

    def _on_bookmark_item_changed(self, item: QListWidgetItem) -> None:
        if item is None:
            return
        bid = int(item.data(Qt.UserRole))
        new_label = item.text().strip()
        for b in self._bookmarks:
            if b.id == bid:
                # Empty label → revert to the default timestamp label so the
                # bookmark keeps useful identity information.
                b.label = new_label or f"Bookmark @{_format_time(b.ns, self._current_time_unit())}"
                break
        self._save_current_trace_state()

    def _add_annotation_at_center(self) -> None:
        if self._trace is None:
            return
        note = self._annotation_input.text().strip()
        if not note:
            return
        ns = self._view.view_center_ns()
        self._annotations.append(TraceAnnotation(id=self._mark_next_id, ns=ns, note=note))
        self._mark_next_id += 1
        self._annotations.sort(key=lambda a: a.ns)
        self._annotation_input.clear()
        self._rebuild_annotation_list()
        self._save_current_trace_state()

    def _add_bookmark_at_ns(self, ns: int) -> None:
        """Add a bookmark at an explicit timestamp (e.g. from right-click)."""
        if self._trace is None:
            return
        unit = self._current_time_unit()
        label = f"Bookmark @{_format_time(ns, unit)}"
        self._bookmarks.append(TraceBookmark(id=self._mark_next_id, ns=ns, label=label))
        self._mark_next_id += 1
        self._bookmarks.sort(key=lambda b: b.ns)
        self._rebuild_bookmark_list()
        self._save_current_trace_state()
        self._marks_dock.setVisible(True)
        self._marks_dock.raise_()

    def _add_annotation_at_ns(self, ns: int) -> None:
        """Prompt for a note then add an annotation at an explicit timestamp."""
        if self._trace is None:
            return
        unit = self._current_time_unit()
        note, ok = QInputDialog.getText(
            self, "Add Annotation",
            f"Note for {_format_time(ns, unit)}:",
        )
        note = note.strip()
        if not ok or not note:
            return
        self._annotations.append(TraceAnnotation(id=self._mark_next_id, ns=ns, note=note))
        self._mark_next_id += 1
        self._annotations.sort(key=lambda a: a.ns)
        self._rebuild_annotation_list()
        self._save_current_trace_state()
        self._marks_dock.setVisible(True)
        self._marks_dock.raise_()

    def _jump_selected_annotation(self) -> None:
        item = self._annotation_list.currentItem()
        if item is None:
            return
        self._jump_to_ns(int(item.data(Qt.UserRole + 1)))

    def _delete_selected_annotation(self) -> None:
        item = self._annotation_list.currentItem()
        if item is None:
            return
        aid = int(item.data(Qt.UserRole))
        for i, a in enumerate(self._annotations):
            if a.id == aid:
                self._annotations.pop(i)
                break
        self._rebuild_annotation_list()
        self._save_current_trace_state()

    def _edit_selected_annotation(self) -> None:
        item = self._annotation_list.currentItem()
        if item is None:
            return
        aid = int(item.data(Qt.UserRole))
        for a in self._annotations:
            if a.id == aid:
                note, ok = QInputDialog.getText(
                    self, "Edit Annotation", "Note:", QLineEdit.Normal, a.note
                )
                if ok and note.strip():
                    a.note = note.strip()
                    self._rebuild_annotation_list()
                    self._recompute_find_hits()
                    self._save_current_trace_state()
                break

    def _rebuild_annotation_list(self) -> None:
        self._annotation_list.blockSignals(True)
        self._annotation_list.clear()
        if self._trace is None:
            self._annotation_list.blockSignals(False)
            return
        unit = self._current_time_unit()
        for a in sorted(self._annotations, key=lambda x: x.ns):
            txt = f"{_format_time(a.ns, unit)}  {a.note}"
            item = QListWidgetItem(txt)
            item.setData(Qt.UserRole, int(a.id))
            item.setData(Qt.UserRole + 1, int(a.ns))
            item.setToolTip(f"@ {_format_time(a.ns, unit)}\n{a.note}")
            self._annotation_list.addItem(item)
        self._annotation_list.blockSignals(False)

    def _focus_find(self) -> None:
        self._find_dock.setVisible(True)
        self._find_input.setFocus()
        self._find_input.selectAll()

    def _recompute_find_hits(self) -> None:
        self._find_hits = []
        self._find_hit_idx = -1
        self._set_find_marker_ns(None)
        if self._trace is None:
            self._find_status.setText("0 matches")
            return
        query = self._find_input.text().strip()
        # Clear highlights whenever the find dock is hidden or query is empty
        if not query or not self._find_dock.isVisible():
            self._find_status.setText("0 matches")
            return
        mode = self._find_mode_combo.currentText().lower()
        regex_obj = None
        if mode == "regex":
            try:
                regex_obj = re.compile(query, re.IGNORECASE)
            except re.error:
                self._find_status.setText("Regex error")
                self._set_find_marker_ns(None)
                return
        for mk, segs in self._trace.seg_map_by_merge_key.items():
            raw = self._trace.task_repr.get(mk, mk)
            disp = task_display_name(raw)
            hay = f"{mk} {raw} {disp}"
            if mode == "contains":
                matched = query.lower() in hay.lower()
            elif mode == "exact":
                matched = query.lower() == mk.lower() or query.lower() == raw.lower() or query.lower() == disp.lower()
            else:
                matched = bool(regex_obj.search(hay)) if regex_obj is not None else False
            if matched:
                self._find_hits.extend(s.start for s in segs)
        for ann in self._annotations:
            hay = ann.note
            if mode == "contains":
                matched = query.lower() in hay.lower()
            elif mode == "exact":
                matched = query.lower() == hay.lower()
            else:
                matched = bool(regex_obj.search(hay)) if regex_obj is not None else False
            if matched:
                self._find_hits.append(ann.ns)
        self._find_hits = sorted(set(self._find_hits))
        self._find_status.setText(f"{len(self._find_hits)} matches")
        if not self._find_hits:
            self._set_find_marker_ns(None)

    def _find_next(self) -> None:
        self._step_find_hit(forward=True)

    def _find_prev(self) -> None:
        self._step_find_hit(forward=False)

    def _step_find_hit(self, forward: bool) -> None:
        if not self._find_hits:
            return
        n = len(self._find_hits)
        if self._find_hit_idx < 0:
            # No previous jump — seed from viewport position.
            now = self._view.view_center_ns()
            if forward:
                idx = bisect_right(self._find_hits, now) % n
            else:
                idx = (bisect_left(self._find_hits, now) - 1) % n
        else:
            if forward:
                idx = (self._find_hit_idx + 1) % n
            else:
                idx = (self._find_hit_idx - 1) % n
        self._find_hit_idx = idx
        self._jump_to_ns(self._find_hits[idx])
        self._set_find_marker_ns(self._find_hits[idx])
        self._find_status.setText(f"{n} matches (at {idx + 1})")

    def _set_find_marker_ns(self, ns: Optional[int]) -> None:
        self._find_marker_ns = ns
        self._refresh_find_marker()

    def _clear_find_marker_items(self) -> None:
        sc = self._view._scene
        for item in self._find_marker_items:
            try:
                sc.removeItem(item)
            except RuntimeError:
                pass
        self._find_marker_items = []

    def _refresh_find_marker(self) -> None:
        self._clear_find_marker_items()
        if self._find_marker_ns is None or self._trace is None:
            return
        sc = self._view._scene
        coord = sc.ns_to_scene_coord(self._find_marker_ns)
        scene_r = sc.sceneRect()
        pen = QPen(QColor("#FFD54F"), 1.5, Qt.DotLine)
        if sc._horizontal:
            line = QGraphicsLineItem(coord, 0, coord, scene_r.height())
            line.setPen(pen)
            line.setZValue(33)
            sc.addItem(line)
            lbl = sc.addSimpleText("Find", _monospace_font(max(8, self._font_size_val - 1), QFont.Bold))
            lbl.setBrush(QBrush(QColor("#FFD54F")))
            lbl.setZValue(34)
            lbl.setPos(min(coord + 4, scene_r.width() - 36), 2)
            self._find_marker_items = [line, lbl]
        else:
            line = QGraphicsLineItem(0, coord, scene_r.width(), coord)
            line.setPen(pen)
            line.setZValue(33)
            sc.addItem(line)
            lbl = sc.addSimpleText("Find", _monospace_font(max(8, self._font_size_val - 1), QFont.Bold))
            lbl.setBrush(QBrush(QColor("#FFD54F")))
            lbl.setZValue(34)
            lbl.setPos(2, min(coord + 2, scene_r.height() - 14))
            self._find_marker_items = [line, lbl]

    def _on_view_scrolled(self) -> None:
        if self._find_marker_ns is not None:
            self._refresh_find_marker()

    def _disconnect_parse_signals(self) -> None:
        """Safely disconnect all signals on the current parse thread.

        Calling this before ``_parse_thread = None`` ensures that any
        PyQtSlotProxy objects are destroyed in a controlled order so that
        stale posted events are purged before the proxy QObjects are freed,
        preventing SIGBUS / EXC_BAD_ACCESS crashes on the next load.
        """
        if self._parse_thread is None:
            return
        for sig in (self._parse_thread.done,
                    self._parse_thread.errored,
                    self._parse_thread.progress):
            try:
                sig.disconnect()
            except (TypeError, RuntimeError):
                pass

    def _open_file(self, path: str) -> None:
        if self._trace is not None and self._current_file:
            self._save_current_trace_state()

        if self._progress_dialog is not None:
            self._progress_dialog.close()
            self._progress_dialog = None

        # Abort any in-progress load before starting a new one.
        # Always disconnect signals before dropping the reference – even a
        # IMPORTANT: stop the thread BEFORE disconnecting signals.
        # disconnect() destroys PyQtSlotProxy C++ objects; if the thread is
        # still running, PyQtSlotProxy::unislot() may execute concurrently and
        # call postEvent(this, ...) on the already-freed proxy → SIGBUS.
        # Stopping first guarantees no new unislot() calls are in-flight.
        # The proxy ~QObject() then calls removePostedEvents(this, 0) to purge
        # any already-queued events.
        if self._parse_thread is not None:
            if self._parse_thread.isRunning():
                self._parse_thread.requestInterruption()
                self._parse_thread.wait(2000)
                if self._parse_thread.isRunning():
                    self._status_file.setText("  Previous load is still stopping…")
                    return
            # Thread is fully stopped – safe to destroy PyQtSlotProxy objects.
            self._disconnect_parse_signals()
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
            # Disconnect all signals FIRST, before processEvents() or dropping the
            # thread reference.  This destroys the PyQtSlotProxy objects and their
            # QObject::removePostedEvents() call purges any still-queued progress/
            # errored events from the main-thread event queue.  Without this, a
            # queued progress event whose proxy was freed by _parse_thread=None
            # would be dispatched by sendPostedEvents → SIGBUS crash.
            self._disconnect_parse_signals()
            progress_dialog.update_progress(100, "Building scene…")
            QApplication.processEvents()   # let the dialog repaint before heavy build
            self._parse_thread = None
            try:
                self._trace = trace
                self._current_file = path
                # Check whether to restore the saved zoom BEFORE updating last_file.
                _prev_file  = self._settings.get("files", "last_file", "")
                _saved_zoom = self._settings.get_float("zoom", "timescale_per_px", -1.0)
                self._settings.set_many("files", {
                    "last_file": path,
                    "last_dir":  os.path.dirname(path),
                })
                # Show the trace view BEFORE load_trace() so that
                # viewport().width/height() already returns the real layout
                # size when _fit_viewport_size() is called inside load_trace().
                # (Hidden widgets report 0 px even though QStackedWidget has
                # already allocated the correct geometry to all pages.)
                self._stack.setCurrentIndex(1)
                QApplication.processEvents()   # force layout pass → viewport settles
                self._view.load_trace(trace)
                self._refresh_zoom_ui_unit()
                self._load_trace_state(path)
                self._recompute_find_hits()
                # Re-apply the saved zoom only when re-opening the exact same file
                # AND the user was in zoom mode (not fit mode) when they closed.
                # A saved zoom of -1 means "fit-to-width" – never restore it.
                if _prev_file == path and _saved_zoom > 0:
                    self._view._scene._timescale_per_px = max(_TIMESCALE_PER_PX_DEFAULT, _saved_zoom)
                    self._view._scene.rebuild()
                    self._view._fit_mode = False
                    self._view.zoom_changed.emit(self._view._scene.timescale_per_px)
                else:
                    # Clear any stale positive zoom so the next save writes -1.
                    self._settings.set("zoom", "timescale_per_px", "-1")
                    self._view.zoom_changed.emit(self._view._scene.timescale_per_px)

                # Restore saved cursor positions (same file only)
                _saved_cursors = self._settings.get("cursors", "positions", "")
                if _prev_file == path and _saved_cursors.strip():
                    try:
                        for _ns in [int(t) for t in _saved_cursors.split()]:
                            self._view._scene.add_cursor(_ns)
                        self._view.cursors_changed.emit(
                            self._view._scene.cursor_times())
                    except ValueError:
                        pass  # malformed rc entry – skip silently
                progress_dialog.update_progress(100, "Building legend…")
                QApplication.processEvents()
                self._legend.rebuild(trace, show_sti=self._show_sti)
                self._stats_panel.update_trace(trace)
                if self._show_stats:
                    self._stats_dock.show()
                self._act_save_img.setEnabled(True)
                self._act_copy_img.setEnabled(True)
                fname = os.path.basename(path)
                ts    = _format_time(trace.time_max - trace.time_min, trace.time_scale)
                n_seg = len(trace.segments)
                n_sti = len(trace.sti_events)
                self.setWindowTitle(f"BTF Trace Viewer – {fname}")
                self._status_file.setText(f"  {fname}  |  span: {ts}")
                self._status_file.setToolTip(
                    f"tasks: {len(trace.tasks)}  "
                    f"segments: {n_seg}  "
                    f"STI events: {n_sti}"
                )
                self._save_recent_files(path)
                self._rebuild_recent_menu()
            except (ValueError, RuntimeError, KeyError, OSError) as exc:
                self._status_file.setText("  No file loaded")
                QMessageBox.critical(self, "Render Error",
                                     f"Failed to display:\n{path}\n\n{exc}")
            finally:
                progress_dialog.close()   # close after all heavy work is done
                if self._progress_dialog is progress_dialog:
                    self._progress_dialog = None
                QApplication.restoreOverrideCursor()

        def _on_error(msg):
            # Same rationale as _on_done: disconnect first to purge any
            # stale queued events before the thread / proxies are freed.
            self._disconnect_parse_signals()
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
            except OSError as exc:
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

    # -- Settings actions -----------------------------------------------

    def _apply_settings_preview(self, vals: dict) -> None:
        """Apply *vals* dict to the live UI without writing to disk.

        Used for both live preview (called on every dialog change) and
        cancel-revert (called with the pre-dialog snapshot).
        """
        # Batch theme rebuilds: both is_dark and ui_font_size trigger
        # _apply_theme; accumulate and call once to avoid double-flicker.
        _need_theme = False
        if vals["is_dark"] != self._is_dark:
            self._is_dark = vals["is_dark"]
            _need_theme = True
        if vals["ui_font_size"] != self._ui_font_size_val:
            self._ui_font_size_val = vals["ui_font_size"]
            _need_theme = True
        if _need_theme:
            self._apply_theme(self._is_dark)
        if vals["font_size"] != self._font_size_val:
            self._font_size_val = vals["font_size"]
            self._view.set_font_size(self._font_size_val)
        if vals["max_cursors"] != self._max_cursors_val:
            self._max_cursors_val = vals["max_cursors"]
            self._view.set_max_cursors(self._max_cursors_val)
            self._view.cursors_changed.emit(self._view._scene.cursor_times())
        if vals["show_sti"] != self._show_sti:
            self._set_show_sti(vals["show_sti"], persist=False)
        if vals["show_grid"] != self._show_grid:
            self._set_show_grid(vals["show_grid"], persist=False)
        if vals["show_legend"] != self._show_legend:
            self._show_legend = vals["show_legend"]
            self._legend_dock.setVisible(self._show_legend)
        if vals["show_stats"] != self._show_stats:
            self._show_stats = vals["show_stats"]
            self._stats_dock.setVisible(self._show_stats)
        if vals["show_marks"] != self._show_marks:
            self._show_marks = vals["show_marks"]
            self._marks_dock.setVisible(self._show_marks)
        if vals["show_hover_highlight"] != self._hover_highlight_val:
            self._hover_highlight_val = vals["show_hover_highlight"]
            self._view._scene.set_hover_highlight(self._hover_highlight_val)
        if vals["label_width"] != self._label_width_val:
            self._label_width_val = vals["label_width"]
            self._view._scene.set_label_width(self._label_width_val)
        if vals["row_height"] != self._row_height_val:
            self._row_height_val = vals["row_height"]
            self._view._scene.set_row_height(self._row_height_val)
        if vals["row_gap"] != self._row_gap_val:
            self._row_gap_val = vals["row_gap"]
            self._view._scene.set_row_gap(self._row_gap_val)
        if vals["timescale_per_px_default"] != self._timescale_per_px_default_val:
            self._timescale_per_px_default_val = vals["timescale_per_px_default"]
            self._view._scene.set_timescale_per_px_default(self._timescale_per_px_default_val)
            self._refresh_zoom_ui_unit()

    def _persist_settings_after_dlg(self, snap: dict) -> None:
        """Write to disk any settings that differ from the pre-dialog snapshot."""
        if snap["is_dark"] != self._is_dark:
            self._settings.set("view", "theme", "dark" if self._is_dark else "light")
        if snap["font_size"] != self._font_size_val:
            self._settings.set("view", "font_size", str(self._font_size_val))
        if snap["ui_font_size"] != self._ui_font_size_val:
            self._settings.set("view", "ui_font_size", str(self._ui_font_size_val))
        if snap["max_cursors"] != self._max_cursors_val:
            self._settings.set("view", "max_cursors", str(self._max_cursors_val))
        if snap["show_sti"] != self._show_sti:
            self._settings.set("view", "show_sti", str(self._show_sti).lower())
        if snap["show_grid"] != self._show_grid:
            self._settings.set("view", "show_grid", str(self._show_grid).lower())
        if snap["show_legend"] != self._show_legend:
            self._settings.set("view", "show_legend", str(self._show_legend).lower())
        if snap["show_stats"] != self._show_stats:
            self._settings.set("view", "show_stats", str(self._show_stats).lower())
        if snap["show_marks"] != self._show_marks:
            self._settings.set("view", "show_marks", str(self._show_marks).lower())
        if snap["show_hover_highlight"] != self._hover_highlight_val:
            self._settings.set("view", "hover_highlight", str(self._hover_highlight_val).lower())
        if snap["label_width"] != self._label_width_val:
            self._settings.set("view", "label_width", str(self._label_width_val))
        if snap["row_height"] != self._row_height_val:
            self._settings.set("view", "row_height", str(self._row_height_val))
        if snap["row_gap"] != self._row_gap_val:
            self._settings.set("view", "row_gap", str(self._row_gap_val))
        if snap["timescale_per_px_default"] != self._timescale_per_px_default_val:
            self._settings.set("view", "timescale_per_px_default",
                               str(self._timescale_per_px_default_val))

    def _open_settings(self) -> None:
        """Open the Settings dialog with live preview; reverts on Cancel."""
        _snap = {
            "is_dark":                  self._is_dark,
            "font_size":                self._font_size_val,
            "ui_font_size":             self._ui_font_size_val,
            "max_cursors":              self._max_cursors_val,
            "show_sti":                 self._show_sti,
            "show_grid":                self._show_grid,
            "show_legend":              self._show_legend,
            "show_stats":               self._show_stats,
            "show_marks":               self._show_marks,
            "show_hover_highlight":     self._hover_highlight_val,
            "label_width":              self._label_width_val,
            "row_height":               self._row_height_val,
            "row_gap":                  self._row_gap_val,
            "timescale_per_px_default": self._timescale_per_px_default_val,
        }
        dlg = _SettingsDialog(
            self,
            font_size=self._font_size_val,
            ui_font_size=self._ui_font_size_val,
            max_cursors=self._max_cursors_val,
            show_sti=self._show_sti,
            show_grid=self._show_grid,
            show_legend=self._show_legend,
            show_stats=self._show_stats,
            show_marks=self._show_marks,
            label_width=self._label_width_val,
            row_height=self._row_height_val,
            row_gap=self._row_gap_val,
            timescale_per_px_default=self._timescale_per_px_default_val,
            is_dark=self._is_dark,
            show_hover_highlight=self._hover_highlight_val,
            zoom_unit=self._current_time_unit(),
        )
        dlg.live_preview.connect(lambda: self._apply_settings_preview({
            "is_dark":                  dlg.is_dark,
            "font_size":                dlg.font_size,
            "ui_font_size":             dlg.ui_font_size,
            "max_cursors":              dlg.max_cursors,
            "show_sti":                 dlg.show_sti,
            "show_grid":                dlg.show_grid,
            "show_legend":              dlg.show_legend,
            "show_stats":               dlg.show_stats,
            "show_marks":               dlg.show_marks,
            "show_hover_highlight":     dlg.show_hover_highlight,
            "label_width":              dlg.label_width,
            "row_height":               dlg.row_height,
            "row_gap":                  dlg.row_gap,
            "timescale_per_px_default": dlg.timescale_per_px_default,
        }))
        if dlg.exec_() == QDialog.Accepted:
            self._persist_settings_after_dlg(_snap)
        else:
            self._apply_settings_preview(_snap)

    # -- Status / legend callbacks -------------------------------------

    def _on_font_size_changed(self, size: int) -> None:
        self._font_size_val = size
        self._view.set_font_size(size)
        self._settings.set("view", "font_size", str(size))

    def _on_max_cursors_changed(self, n: int) -> None:
        self._max_cursors_val = n
        self._view.set_max_cursors(n)
        self._settings.set("view", "max_cursors", str(n))
        # If cursors were evicted, update the status-bar cursor badge strip.
        self._view.cursors_changed.emit(self._view._scene.cursor_times())

    def _on_zoom_changed(self, timescale_per_px: float) -> None:
        unit = self._current_time_unit()
        z = f"{timescale_per_px:.3g} {unit}/px"
        self._zoom_label.setText(z)
        self._refresh_find_marker()

    def _on_cursor_delete(self, ns: int) -> None:
        """Remove the cursor whose timestamp matches *ns* (from a badge drag-out)."""
        self._view._scene.remove_nearest_cursor(ns)
        self._view.cursors_changed.emit(self._view._scene.cursor_times())

    def _on_cursors_changed(self, times: list) -> None:
        self._cursor_bar.rebuild(times, self._trace)
        has_range = len(times) >= 2
        self._act_zoom_range.setEnabled(has_range)
        self._tb_zoom_range_btn.setEnabled(has_range)
        if self._trace is None or not has_range:
            self._range_stats_label.setText("Range: place two cursors to measure")
            self._status_range.setVisible(False)
            return
        t_sorted = sorted(times)
        lo = t_sorted[0]
        hi = t_sorted[-1]
        dt = max(0, hi - lo)
        unit = self._current_time_unit()
        switches = 0
        top_task = "-"
        top_ns = 0
        durations: list = []
        if self._trace is not None and dt > 0:
            task_acc: Dict[str, int] = {}
            for seg in self._trace.segments:
                if seg.end <= lo or seg.start >= hi:
                    continue
                ov = min(seg.end, hi) - max(seg.start, lo)
                if ov <= 0:
                    continue
                switches += 1
                dur = seg.end - seg.start
                durations.append(dur)
                raw = self._trace.task_repr.get(task_merge_key(seg.task), seg.task)
                disp = task_display_name(raw)
                task_acc[disp] = task_acc.get(disp, 0) + ov
            if task_acc:
                top_task, top_ns = max(task_acc.items(), key=lambda kv: kv[1])
        top_pct = (100.0 * top_ns / dt) if dt > 0 else 0.0
        self._range_stats_label.setText(
            f"Range C1-C{len(times)}: {_format_time(dt, unit)} | slices: {switches} | "
            f"top: {top_task} ({top_pct:.1f}%)"
        )
        # Compact status-bar version: span + segment min/max/avg
        if durations:
            d_min = _format_time(min(durations), unit)
            d_max = _format_time(max(durations), unit)
            d_avg = _format_time(int(sum(durations) / len(durations)), unit)
            range_text = (
                f"Range: {_format_time(dt, unit)}  "
                f"min {d_min}  max {d_max}  avg {d_avg}"
            )
        else:
            range_text = f"Range: {_format_time(dt, unit)}  (no segments)"
        self._status_range.setText(range_text)
        self._status_range.setVisible(True)

    def _on_legend_task_clicked(self, task: str) -> None:
        """Toggle click-locked highlight for *task* from the Legend panel."""
        sc = self._view._scene
        if sc._locked_task == task:
            sc.set_highlighted_task(None)          # second click on same → cancel
        else:
            sc.set_highlighted_task(task, locked=True)

    def _zoom_to_cursor_range(self) -> None:
        """Fit the view tightly between the first two cursor positions."""
        if self._trace is None:
            return
        times = sorted(self._view._scene.cursor_times())
        if len(times) < 2:
            self.statusBar().showMessage("Place at least 2 cursors to zoom to range", 3000)
            return
        ns_lo, ns_hi = times[0], times[-1]
        if ns_lo == ns_hi:
            return

        # Use the real viewport dimension (not the _fit_viewport_size() floor)
        # so that zoom_to_range and the centering formula are always consistent.
        vp = self._view.viewport().rect()
        is_horiz = self._view._scene._horizontal
        vp_px = max(vp.width() if is_horiz else vp.height(), 100)

        self._view._scene.zoom_to_range(ns_lo, ns_hi, vp_px)

        # Position so C1 aligns with the right edge of the frozen label column
        # and C2 aligns with the right edge of the viewport.
        #   avail = vp_px - label_w  →  ns_hi_scene - ns_lo_scene == avail
        #   centerOn(x) puts scene-x at viewport pixel-centre, so:
        #     center_scene = ns_lo_scene - label_w + vp_px / 2
        ns_lo_scene = self._view._scene.ns_to_scene_coord(ns_lo)
        label_w     = self._view._scene._label_width
        center_coord = ns_lo_scene - label_w + vp_px / 2
        cur_scene = self._view.mapToScene(vp.center())
        if is_horiz:
            self._view.centerOn(center_coord, cur_scene.y())
        else:
            self._view.centerOn(cur_scene.x(), center_coord)
        self._view.zoom_changed.emit(self._view._scene.timescale_per_px)
        self._refresh_find_marker()

    # -- Navigation helpers ---------------------------------------------

    def _jump_to_trace_start(self) -> None:
        """Scroll the viewport to the very beginning of the trace."""
        if self._trace is None:
            return
        self._view.scroll_to_ns(self._trace.time_min)

    def _jump_to_trace_end(self) -> None:
        """Scroll the viewport to the very end of the trace."""
        if self._trace is None:
            return
        self._view.scroll_to_ns(self._trace.time_max)

    def _prompt_annotation_at_center(self) -> None:
        """Prompt for a note then add annotation at the viewport centre (menu / keyboard)."""
        if self._trace is None:
            return
        self._add_annotation_at_ns(self._view.view_center_ns())

    # -- Marks export ---------------------------------------------------

    def _export_marks_csv(self) -> None:
        """Export all bookmarks and annotations to a CSV file."""
        if self._trace is None:
            return
        unit = self._current_time_unit()
        rows = []
        for b in self._bookmarks:
            rows.append(("bookmark",   _format_time(b.ns, unit), b.ns, b.label))
        for a in self._annotations:
            rows.append(("annotation", _format_time(a.ns, unit), a.ns, a.note))
        rows.sort(key=lambda r: r[2])
        if not rows:
            QMessageBox.information(self, "No Marks", "No bookmarks or annotations to export.")
            return
        base = os.path.splitext(os.path.basename(self._current_file or "trace"))[0]
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Marks",
            os.path.join(os.path.dirname(self._current_file or ""), f"{base}_marks.csv"),
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        try:
            import csv
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(["type", "timestamp", "raw_ns", "label_or_note"])
                writer.writerows(rows)
            self.statusBar().showMessage(f"Marks exported → {os.path.basename(path)}", 4000)
        except OSError as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    def _import_marks_csv(self) -> None:
        """Import bookmarks and annotations from a CSV file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Marks",
            os.path.dirname(self._current_file or ""),
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        try:
            import csv
            imported = 0
            with open(path, "r", newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    kind = row.get("type", "").strip().lower()
                    try:
                        ns = int(row.get("raw_ns", 0))
                    except (ValueError, TypeError):
                        continue
                    label = row.get("label_or_note", "")
                    if kind == "bookmark":
                        if not any(b.ns == ns for b in self._bookmarks):
                            self._bookmarks.append(TraceBookmark(id=self._mark_next_id, ns=ns, label=label))
                            self._mark_next_id += 1
                            imported += 1
                    elif kind == "annotation":
                        if not any(a.ns == ns for a in self._annotations):
                            self._annotations.append(TraceAnnotation(id=self._mark_next_id, ns=ns, note=label))
                            self._mark_next_id += 1
                            imported += 1
            self._rebuild_bookmark_list()
            self._rebuild_annotation_list()
            self.statusBar().showMessage(f"Imported {imported} mark(s) from {os.path.basename(path)}", 4000)
        except OSError as exc:
            QMessageBox.critical(self, "Import Error", str(exc))

    # -- Find dock ------------------------------------------------------

    def _on_find_dock_visibility_changed(self, visible: bool) -> None:
        """Clear highlight overlays when the Find dock is hidden."""
        if not visible:
            self._recompute_find_hits()

    # -- Help -----------------------------------------------------------

    def _on_keyboard_shortcuts(self) -> None:
        """Show a reference dialog listing all keyboard shortcuts."""
        if self._is_dark:
            c_head = "#FFD700"
            c_key  = "#7EC8E3"
            c_body = "#D4D4D4"
            c_bg   = "#2D2D2D"
        else:
            c_head = "#B8860B"
            c_key  = "#005A8E"
            c_body = "#333333"
            c_bg   = "#F5F5F5"
        sections = [
            ("File", [
                ("Ctrl+O",       "Open .btf trace file"),
                ("Ctrl+S",       "Save viewport as PNG"),
                ("Ctrl+Shift+C", "Copy viewport to clipboard"),
                ("Ctrl+Q",       "Quit  (Alt+F4 also works on Windows)"),
            ]),
            ("View / Zoom", [
                ("Ctrl++",    "Zoom in"),
                ("Ctrl+-",    "Zoom out"),
                ("Ctrl+0",    "Fit entire trace to window"),
                ("Ctrl+R",    "Zoom to cursor range"),
                ("Ctrl+,",    "Open Settings"),
            ]),
            ("Navigation", [
                ("Ctrl+Home", "Jump to trace start"),
                ("Ctrl+End",  "Jump to trace end"),
            ]),
            ("Cursors", [
                ("C",         "Place cursor at viewport centre"),
                ("Shift+C",   "Clear all cursors"),
            ]),
            ("Find", [
                ("Ctrl+F",    "Open Find bar"),
                ("F3",        "Find next match"),
                ("Shift+F3",  "Find previous match"),
            ]),
            ("Marks", [
                ("Ctrl+B",         "Add bookmark at viewport centre"),
                ("Ctrl+Shift+B",   "Add annotation at viewport centre"),
            ]),
        ]
        html = "<table style='border-collapse:collapse;' cellpadding='4'>"
        for section, items in sections:
            html += (
                f"<tr><td colspan='2' style='padding-top:8px;'>"
                f"<b style='color:{c_head};'>{section}</b></td></tr>"
            )
            for key, desc in items:
                html += (
                    f"<tr>"
                    f"<td style='color:{c_key}; font-family:monospace; white-space:nowrap;"
                    f" background:{c_bg}; padding:2px 6px; border-radius:3px;'>{key}</td>"
                    f"<td style='color:{c_body}; padding-left:10px;'>{desc}</td>"
                    f"</tr>"
                )
        html += "</table>"

        dlg = QDialog(self)
        dlg.setWindowTitle("Keyboard Shortcuts")
        dlg.setMinimumWidth(360)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 12, 16, 12)
        lbl = QLabel(html)
        lbl.setTextFormat(Qt.RichText)
        lbl.setWordWrap(False)
        layout.addWidget(lbl)
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok)
        btn_box.accepted.connect(dlg.accept)
        layout.addWidget(btn_box)
        dlg.exec_()

    def _on_about(self) -> None:
        _AboutDialog(self, is_dark=self._is_dark).exec_()

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
    app.setApplicationDisplayName("BTF Trace Viewer")
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
