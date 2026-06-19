"""
btf_viewer.py - Single-file RTOS BTF Viewer (PyQt5).

Usage:
    python btf_viewer.py [trace.btf]

Parses RTOS .btf context-switch traces and renders an interactive
Gantt-style timeline with multi-cursor, drag-to-move, zoom/pan, and
expandable core-view rows.

Architecture overview
---------------------
  1. BTF Parser  (_parse_btf)
     Reads the .btf text file line-by-line and reconstructs task
     execution segments from the sparse event stream (resume / preempt
     pairs).  All derived lookup tables (seg_map_by_merge_key, core_segs,
     core_task_segs, ...) are pre-built here once so that scene rebuilds
     never iterate over raw segments again.

  2. Data model  (dataclasses: RawEvent, TaskSegment, StiEvent, BtfTrace)
     Plain dataclasses; no Qt dependency.  BtfTrace is the single source
     of truth passed from the parser to the scene.

  3. Timeline scene  (TimelineScene : QGraphicsScene)
     Converts BtfTrace data into QGraphicsItems at a given zoom level
     (timescale_per_px).  Four builder methods cover the two view modes
     (task / core) x two orientations (horizontal / vertical).  The scene
     is fully torn down and rebuilt on every zoom/scroll action.

  4. Graphics items  (_RulerItem, _BatchRowItem, _BatchStiItem, ...)
     Custom QGraphicsItem subclasses.  _BatchRowItem and _BatchStiItem
     each represent an entire row with a single Qt item and use a
     3-tier Level-of-Detail (LOD) paint strategy to keep frame times
     low across the full zoom range (see _BatchRowItem docstring).

  5. Timeline view  (TimelineView : QGraphicsView)
     Wraps the scene; handles mouse events (click -> cursor, drag -> pan,
     Ctrl+wheel / pinch -> zoom, middle-drag -> range-zoom), label-column
     resize, and frozen-label repositioning on scroll.

  6. Main window  (MainWindow : QMainWindow)
     Top-level application window.  Owns the toolbar, menus, status bar,
     legend dock, and drag-and-drop file opening.

Section index
-------------
  USER CONFIGURATION  - fonts, layout, colours, cursors, LOD thresholds
                        (edit here to customise the viewer appearance)
  BTF Parser          - dataclasses + task-name helpers + _parse_btf()
  Timeline Widget     - internal colour helpers, _format_time, _monospace_font,
                        _lod_reduce, _nice_grid_step
  Scene               - TimelineScene and its four builder methods
  Graphics Items      - _RulerItem, _BatchRowItem, _BatchStiItem,
                        _TaskLabelItem, _CoreHeaderItem,
                        _SegmentItem (legacy), _StiMarkerItem (legacy)
  View                - TimelineView (pan / zoom / cursor mouse handling)
  Main Window         - _CursorButton, _CursorBarWidget, _LegendWidget,
                        _StatsPanel, _RcSettings, _WheelSpinBox, MainWindow
  Entry point         - main()
"""

from __future__ import annotations

import os
import sys
import threading

# ---------------------------------------------------------------------------
# macOS: suppress the harmless "TSM AdjustCapsLockLEDForKeyTransitionHandling"
# noise that macOS prints to fd 2 whenever a key is pressed in a Qt app.
# We redirect fd 2 into a pipe and relay everything EXCEPT that line.
# ---------------------------------------------------------------------------
if sys.platform == "darwin":
    def _install_macos_stderr_filter() -> None:
        _NOISE = b"TSM AdjustCapsLockLED"
        try:
            rfd, wfd = os.pipe()
        except OSError:
            return  # Can't create pipe; skip filter
        original_fd = os.dup(2)
        try:
            os.dup2(wfd, 2)
        except OSError:
            os.close(rfd)
            os.close(wfd)
            os.close(original_fd)
            return  # Restore fd 2 unchanged
        os.close(wfd)

        def _relay() -> None:
            leftover = b""
            try:
                with os.fdopen(rfd, "rb", buffering=0) as pipe:
                    while True:
                        chunk = pipe.read(256)
                        if not chunk:
                            break
                        leftover += chunk
                        while b"\n" in leftover:
                            line, leftover = leftover.split(b"\n", 1)
                            if _NOISE not in line:
                                try:
                                    os.write(original_fd, line + b"\n")
                                except OSError:
                                    pass
                if leftover and _NOISE not in leftover:
                    try:
                        os.write(original_fd, leftover)
                    except OSError:
                        pass
            finally:
                try:
                    os.close(original_fd)
                except OSError:
                    pass

        t = threading.Thread(target=_relay, daemon=True, name="stderr-filter")
        t.start()

    _install_macos_stderr_filter()
    del _install_macos_stderr_filter

import configparser
import csv
import datetime
import functools
import hashlib
import html
import itertools
import json
import math
import time
import re
import shutil
import subprocess
import tempfile
import traceback
import zlib
from bisect import bisect_left, bisect_right
from collections import defaultdict
from operator import attrgetter as _attrgetter
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import (
    QBuffer, QByteArray, QEasingCurve, QEvent, QEventLoop, QIODevice, QLineF, QMimeData,
    QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QThread, QTimer,
    QPropertyAnimation, pyqtSignal,
)
from PyQt5.QtGui import (
    QBrush, QColor, QFont, QFontDatabase, QFontMetrics, QFontMetricsF, QIcon, QKeySequence, QPainter,
    QPainterPath, QPalette, QPen, QPixmap, QPolygonF, QTransform, QWheelEvent,
)
from PyQt5.QtSvg import QSvgGenerator
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDockWidget, QFileDialog, QFormLayout, QFrame, QGridLayout, QInputDialog,
    QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem, QGraphicsOpacityEffect,
    QGraphicsPixmapItem,
    QGraphicsPolygonItem, QGraphicsRectItem, QGraphicsScene, QGraphicsTextItem, QGraphicsView,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListView, QMainWindow, QMenu, QMessageBox, QProgressBar,
    QProgressDialog,
    QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QShortcut, QDoubleSpinBox, QSpinBox, QStackedWidget,
    QStyle, QStyleFactory, QStyleOptionGraphicsItem, QAbstractItemView,
    QProxyStyle, QTabBar, QTabWidget, QTableWidget, QTableWidgetItem, QToolButton,
    QVBoxLayout, QWidget, QSizePolicy, QSplitter,
)

# ===========================================================================
# USER CONFIGURATION
# Edit the values in this section to customise the viewer.
# Everything else in the file is internal implementation detail.
# ===========================================================================

# ---- Fonts ----------------------------------------------------------------
FONT_SIZE                = 8    # Timeline label font size (pt).  Adjustable at runtime
                                # via the Font spinbox in the toolbar.
UI_FONT_SIZE             = 8    # Application UI font: menus, toolbar, status bar (pt).

# ---- Rendering -----------------------------------------------------------
# Vertical-mode label rendering: use a pre-rendered QPixmap rotated 90deg instead
# of a rotated QGraphicsTextItem.  On Windows, GDI cannot antialias rotated text,
# so the pixmap path (render text horizontally, then rotate the image) produces
# much crisper labels.  Enabled by default on Windows; other platforms use the
# original QGraphicsTextItem approach which works correctly with PreferAntialias.
_VERTICAL_LABEL_USE_PIXMAP_DEFAULT: bool = sys.platform == "win32"

# ---- Layout ---------------------------------------------------------------
LABEL_WIDTH              = 160  # Width of the frozen task-label column (px).
RULER_HEIGHT             =  40  # Height of the time ruler row (px) - horizontal mode.
RULER_WIDTH              = 120  # Width of the time ruler column (px) - vertical mode.
ROW_HEIGHT               =  22  # Height of each task / core row (px).
ROW_GAP                  =   4  # Vertical gap between rows (px).
STI_ROW_H                =  18  # Height of a collapsed STI row (px)
CPU_LOAD_ROW_H           =  30  # CPU load graph row height (px) - independent of timeline rows.
CPU_LOAD_ROW_GAP         =   2  # Gap between CPU load rows (px).
CPU_LOAD_COLLAPSED_H     =  20  # Height of a collapsed CPU load row (px - enough to show label).
CPU_LOAD_PANE_MAX_H      = 480  # Max CPU load pane height before inner vertical scroll (web parity).
STATS_UTIL_BAR_H         =   8  # Core/task CPU % bar height in Statistics panel (px).
STATS_UTIL_ROW_H         =  16  # Row height; matches stats-table row size (px).
STATS_UTIL_ROW_GAP       =   1  # Vertical gap between utilisation rows (px).
STATS_UTIL_LABEL_W       = 128  # Fixed label column so progress bars align (px).
STATS_UTIL_PCT_W         =  44  # Fixed CPU % column width (px).
STATS_TABLE_HEADER_H     =  18  # QTableWidget header row height (px).
STATS_TABLE_ROW_H        =  16  # QTableWidget body row height (px).
STATS_TABLE_HSCROLL_H    =  14  # Horizontal scrollbar strip inside wide tables (px).
STATS_MAX_VISIBLE_ROWS   =   8  # Default viewport shows this many rows before v-scroll.

def _stats_table_viewport_height(visible_rows: int = STATS_MAX_VISIBLE_ROWS,
                                 *, reserve_h_scroll: bool = False) -> int:
    """Pixel height for a stats table showing *visible_rows* body rows."""
    h = STATS_TABLE_HEADER_H + visible_rows * STATS_TABLE_ROW_H + 2
    if reserve_h_scroll:
        h += STATS_TABLE_HSCROLL_H
    return h

STATS_TABLE_DEFAULT_H    = _stats_table_viewport_height()
STATS_TABLE_MIG_DEFAULT_H = _stats_table_viewport_height(reserve_h_scroll=True)
STATS_UTIL_DEFAULT_H     = ( STATS_MAX_VISIBLE_ROWS * STATS_UTIL_ROW_H
                             + max(0, STATS_MAX_VISIBLE_ROWS - 1) * STATS_UTIL_ROW_GAP + 2 )
STI_WAVEFORM_H           =  80  # Height of an expanded STI waveform row (px).
STI_LINE_STYLE           = "linear"  # Default STI waveform draw style: "step" or "linear".

# First-run window geometry defaults (used when btf_viewer.rc is absent).
DEFAULT_WINDOW_WIDTH     = 1916
DEFAULT_WINDOW_HEIGHT    = 1088
DEFAULT_WINDOW_X         = 254
DEFAULT_WINDOW_Y         = 47
DEFAULT_DOCK_LAYOUT_VERSION = "7"
# Keep empty so first run uses code-driven dock sizing/tab defaults instead
# of a host-dependent serialized Qt dock_state blob.
DEFAULT_DOCK_STATE_B64 = ""

# Regex pattern: only tag_event and tag0_event...tag7_event channels can be expanded.
# Uses a capturing group so the digit (if any) can be extracted for sort ordering.
_STI_EXPANDABLE_RE = re.compile(r'^tag([0-7])?_event$', re.IGNORECASE)

def _is_tag_sti_channel(channel: str) -> bool:
    """Return True if *channel* is a tag_event / tag[0-7]_event channel (expandable)."""
    return bool(_STI_EXPANDABLE_RE.match(channel))

def _sti_channel_sort_key(channel: str) -> tuple:
    """Sort key placing tag channels first, then everything else alphabetically.

    Order:
      1. tag_event          (treated as digit -1 so it precedes tag0)
      2. tag0_event ... tag7_event  (numeric digit order)
      3. all other channels (alphabetical)
    """
    m = _STI_EXPANDABLE_RE.match(channel)
    if m:
        digit = m.group(1)
        return (0, int(digit) if digit else -1, channel.lower())
    return (1, 0, channel.lower())
STI_MARKER_H             =   3  # Height of an STI marker triangle (px).
MIN_SEG_WIDTH            = 1.0  # Minimum painted width of a task segment (px).
LABEL_BOTTOM_MARGIN      =  10  # Gap (px) between bottom edge of a vertical label and the timeline.

# ---- Performance / Level-of-Detail ----------------------------------------
_TIMESCALE_PER_PX_DEFAULT= 2.0    # Initial zoom level (nanoseconds per screen pixel).
_HOVER_HIGHLIGHT_ENABLED = False  # Highlight task bars when hovering the label (default off).
# _BatchRowItem.paint() LOD thresholds (Qt levelOfDetail: 1.0 = 100% zoom).
_PAINT_LOD_COARSE        = 0.45   # Below: merge nearby segments, skip pen outlines.
_PAINT_LOD_MICRO         = 0.12   # Below: draw one tinted activity bar per row.
_LOD_MERGE_PX            = 6.0    # Coarse LOD: merge segments closer than this many scene-px.
_ACTIVITY_ALPHA          = 160    # Alpha for the micro-LOD activity-presence bar.
_INTERVAL_MIN_PX         = 0.5    # Skip sub-pixel interval bars (avoids merge artefacts).
_HOVER_BISECT_MARGIN     = 3      # Neighbour scan window used in hoverMoveEvent bisect lookup.
# Inline segment text is only rendered near 1:1 zoom; zoomed-out views keep
# bars only for performance, especially at far-right large coordinates.
# Number of bins used when pre-computing a coarse LOD summary at parse time.
# The summary is stored in BtfTrace and replaces O(N_segs) _lod_reduce calls
# with an O(4096) worst-case iteration during fit-to-view rebuilds.
_LOD_SUMMARY_BINS        = 4096
# Second-level coarse summary used for deep zoom-out rebuilds.
_LOD_SUMMARY_BINS_ULTRA  = 1024
# Orthogonal scroll culling: keep at least this many rows/cols beyond the
# viewport so fast vertical scrolling does not trigger a full rebuild every
# few hundred pixels (critical for traces with hundreds of task rows).
_ORTH_BUF_MIN_ROWS        = 40
_ORTH_BUF_VIEWPORT_MULT   = 3.0
_ORTH_BUF_LARGE_TASKS     = 256   # reduce orth margin above this task count
_ORTH_BUF_HUGE_TASKS      = 768
_MAX_FINE_SEGS_PER_ROW    = 512   # fall back to LOD summary above this per row
_ZOOM_DEBOUNCE_MS         = 60
_ZOOM_DEBOUNCE_LARGE_MS   = 120
_ZOOM_DEBOUNCE_HUGE_MS    = 160
# Pan-rebuild timers: heartbeat polls while scrolling; min interval caps how
# often an in-flight scroll may trigger scene.clear()+rebuild.
_PAN_HEARTBEAT_MS         = 100
_PAN_HEARTBEAT_MIN_REBUILD_MS = 180
_PAN_ORTH_URGENT_REBUILD_MS   = 40   # faster rebuild when viewport outruns orth margin
_PAN_SETTLE_MS            = 120
_NAV_SCROLL_DEBOUNCE_MS   = 120
# Never draw grid lines closer than this (px); dense lines read as solid gray.
_MIN_GRID_SPACING_PX      = 12.0

# ---- Cursors --------------------------------------------------------------
_MAX_CURSORS         = 8  # Hard upper bound - must equal len(_CURSOR_COLORS).
_DEFAULT_MAX_CURSORS = 4  # Default number of simultaneously visible cursors.

# Portable session JSON (shared with BTFViewer/web sessionPortable.js)
SESSION_PORTABLE_VERSION = 1
_PORTABLE_FIND_MODES = ("contains", "exact", "regex", "migrations")
_META_KEY_RE = re.compile(r"^[\w.-]+$")
_MAX_FIND_REGEX_LEN = 200
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
# Darker, saturated variants for light backgrounds (timeline rows are white/light gray).
_CURSOR_COLORS_LIGHT = [
    "#C62828",  # 1 red
    "#2E7D32",  # 2 green
    "#1565C0",  # 3 blue
    "#E65100",  # 4 amber
    "#8E24AA",  # 5 magenta
    "#00838F",  # 6 cyan
    "#F9A825",  # 7 yellow
    "#6A1B9A",  # 8 purple
]

def _cursor_colors(is_dark: bool = True) -> list:
    return _CURSOR_COLORS if is_dark else _CURSOR_COLORS_LIGHT

# ---- Task colour palette --------------------------------------------------
# 16-colour cycle used to distinguish tasks (hex RGB strings).
_PALETTE = [
    "#4E9AF1", "#F1884E", "#4EF188", "#F14E9A",
    "#9A4EF1", "#F1D94E", "#4EF1D9", "#F14E4E",
    "#88C057", "#C057C0", "#57C0C0", "#C09057",
    "#7B68EE", "#EE687B", "#68EE7B", "#EEB468",
]

# Okabe-Ito 8-colour palette - distinguishable for deuteranopia / protanopia.
_PALETTE_COLORBLIND = [
    "#0072B2",  # blue
    "#E69F00",  # orange
    "#009E73",  # green
    "#CC79A7",  # pink
    "#56B4E9",  # sky blue
    "#D55E00",  # vermilion
    "#F0E442",  # yellow
    "#000000",  # black
]

@dataclass
class _RenderRuntimeState:
    """Process-local mutable render toggles and cache-affecting state."""

    colorblind_active: bool = False
    vertical_label_use_pixmap: bool = _VERTICAL_LABEL_USE_PIXMAP_DEFAULT

_RENDER_RUNTIME = _RenderRuntimeState()

# Colour map for core header dots.
# Core dot / header colors - 16 hand-picked distinct hues that cycle for
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
    """Build a QIcon from an SVG path string (16x16 viewBox by default)."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 16 16"><path fill="{color}" fill-rule="evenodd" d="{path_data}"/></svg>'
    )
    ba = QByteArray(svg.encode())
    pm = QPixmap()
    pm.loadFromData(ba, "SVG")
    return QIcon(pm)

def _svg_icon_markup(inner: str, size: int = 16) -> "QIcon":
    """Build a QIcon from raw SVG markup (supports stroke icons)."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 16 16">{inner}</svg>'
    )
    ba = QByteArray(svg.encode())
    pm = QPixmap()
    pm.loadFromData(ba, "SVG")
    return QIcon(pm)

def _stats_chevron_icon(collapsed: bool, is_dark: bool = True) -> QIcon:
    """Chevron for statistics section headers (matches web StatisticsPanel)."""
    color = "#9E9E9E" if is_dark else "#666666"
    if collapsed:
        inner = (
            f'<polyline points="5,3 11,8 5,13" fill="none" stroke="{color}" '
            f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    else:
        inner = (
            f'<polyline points="3,5 8,11 13,5" fill="none" stroke="{color}" '
            f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    return _svg_icon_markup(inner, size=10)

# Icon path data (16x16 viewBox, single-path SVG outlines)
_IC_OPEN   = ("M1 3.5A1.5 1.5 0 0 1 2.5 2h2.764c.958 0 1.76.56 2.311 1.184C7.985 3.648 8.48 4 9 4h4.5A1.5 1.5 0 0 1 15 5.5v.64c.57.265.94.876.856 1.546l-.64 5.124A2.5 2.5 0 0 1 12.733 15H3.267a2.5 2.5 0 0 1-2.483-2.19l-.64-5.124A1.5 1.5 0 0 1 1 6.14V3.5z"
              "M2 6h12v-.5a.5.5 0 0 0-.5-.5H9c-.964 0-1.71-.629-2.174-1.154C6.374 3.334 5.82 3 5.264 3H2.5a.5.5 0 0 0-.5.5V6z"
              "m-.367 1a.5.5 0 0 0-.496.562l.64 5.124A1.5 1.5 0 0 0 3.267 14h9.466a1.5 1.5 0 0 0 1.49-1.314l.64-5.124A.5.5 0 0 0 14.367 7H1.633z")
_IC_SAVE     = "M2 1a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V4.5L11.5 1H2zm2 1h5v3H4V2zm4 8a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3zM3 10h10v4H3v-4z"
_IC_SAVE_SVG = ("M7.5 1a.5.5 0 0 1 .5.5v8.793l2.146-2.147a.5.5 0 0 1 .708.708l-3 3"
                "a.5.5 0 0 1-.708 0l-3-3a.5.5 0 0 1 .708-.708L7 10.293V1.5a.5.5 0 0 1 .5-.5z"
                "M2.5 13a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5z")
_IC_COPY   = "M4 1.5H3a2 2 0 0 0-2 2V14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V3.5a2 2 0 0 0-2-2h-1v1h1a1 1 0 0 1 1 1V14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1h1v-1zM5 0h6a1 1 0 0 1 1 1v3H4V1a1 1 0 0 1 1-1z"
_IC_SHOT   = ("M3 3.5A1.5 1.5 0 0 1 4.5 2h7A1.5 1.5 0 0 1 13 3.5V5h1a1 1 0 0 1 1 1v6.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 12.5V6a1 1 0 0 1 1-1h1V3.5zm1 0V5h8V3.5a.5.5 0 0 0-.5-.5h-7a.5.5 0 0 0-.5.5z"
                "M8 7a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z")
_IC_HORIZ  = "M1 4h14v2H1zm0 4h14v2H1zm0 4h14v2H1z"
_IC_VERT   = "M3 1h2v14H3zm4 0h2v14H7zm4 0h2v14h-2z"
_IC_ZIN    = "M6.5 1a5.5 5.5 0 1 0 3.89 9.4l3.4 3.4.7-.7-3.4-3.4A5.5 5.5 0 0 0 6.5 1zm0 1a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9zM6 5v1.5H4.5v1H6V9h1V7.5h1.5v-1H7V5H6z"
_IC_ZOUT   = "M6.5 1a5.5 5.5 0 1 0 3.89 9.4l3.4 3.4.7-.7-3.4-3.4A5.5 5.5 0 0 0 6.5 1zm0 1a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9zM4 6h5v1H4V6z"
_IC_FIT    = "M1.5 1h5v1h-4v4h-1V1.5a.5.5 0 0 1 .5-.5zm13 0a.5.5 0 0 1 .5.5V6h-1V2h-4V1h4.5zM1 10h1v4h4v1H1.5a.5.5 0 0 1-.5-.5V10zm14 0v4.5a.5.5 0 0 1-.5.5H10v-1h4v-4h1z"
_IC_CURSOR = "M1 1l5 12 2-4 4 4 1-1-4-4 4-2L1 1z"
_IC_MARK   = "M3 2a1 1 0 0 1 1-1h8a1 1 0 0 1 1 1v12.5a.5.5 0 0 1-.777.416L8 12.101l-4.223 2.815A.5.5 0 0 1 3 14.5V2z"
_IC_CLEAR  = "M2 2.5l.5-.5 5.5 5.5 5.5-5.5.5.5L8.5 8 14 13.5l-.5.5L8 8.5 2.5 14l-.5-.5L7.5 8 2 2.5z"
_IC_LEGEND = "M1 2a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V2zm5-1h8v1H6V1zm0 3h8v1H6V4zm-5 3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V7zm5-1h8v1H6V6zm0 3h8v1H6V9zm-5 3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1v-2zm5-1h8v1H6v-1zm0 3h8v1H6v-1z"
_IC_TASK   = "M1 2.5A1.5 1.5 0 0 1 2.5 1h11A1.5 1.5 0 0 1 15 2.5v11a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 13.5v-11zM4 5.5h8v1H4v-1zm0 3h8v1H4v-1zm0 3h5v1H4v-1z"
_IC_CORE   = "M5 1v2H3a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2v2h1v-2h4v2h1v-2h2a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2h-2V1h-1v2H6V1H5zm-2 4h10v6H3V5zm2 1v4h6V6H5z"
_IC_EXPAND     = "M3 1h1v14H3zM12 1h1v14h-1zM4 5l3 3-3 3zM12 5l-3 3 3 3z"
_IC_EXPAND_ALL = "M8 1l2.5 3h-2v3h-1V4H5.5zM8 15l-2.5-3h2v-3h1V12h2.5zM2 7.5h12v1H2z"
_IC_SECTIONS_EXPAND = "M8 2v5H3v1h5v5h1V8h5V7H9V2H8z"
_IC_SECTIONS_COLLAPSE = "M2 7h12v2H2z"
_IC_1TO1     = ("M6.5 1a5.5 5.5 0 1 0 3.89 9.4l3.4 3.4.7-.7-3.4-3.4A5.5 5.5 0 0 0 6.5 1"
               "zm0 1a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9z"
               "M3.5 4h1.5v5h-1.5z"        # left  "1" bar
               "M5.8 4.8h1.4v1.2H5.8z"     # ":"   top dot
               "M5.8 6.9h1.4v1.2H5.8z"     # ":"   bottom dot
               "M7.8 4h1.5v5H7.8z"         # right "1" bar
               )
_IC_CPU_LOAD = ("M1 11a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1v-3z"
                "M5 7a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7z"
                "M9 3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1h-2a1 1 0 0 1-1-1V3z"
                "M13 1a1 1 0 0 1 1-1h1a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-1a1 1 0 0 1-1-1V1z")
_IC_HEATMAP = ("M1 1h4v4H1V1zm5 0h4v4H6V1zm5 0h4v4h-4V1z"
               "M1 6h4v4H1V6zm5 0h4v4H6V6zm5 0h4v4h-4V6z"
               "M1 11h4v4H1v-4zm5 0h4v4H6v-4zm5 0h4v4h-4v-4z")
_IC_EXPORT_CSV = ("M2 1h12a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1zm0 1v12h12V2H2zm2 2h8v1H4V4zm0 2h8v1H4V6zm0 2h5v1H4V8z")
_IC_THEME_DARK = ("M8 1.2a.5.5 0 0 1 .47.66A5.8 5.8 0 1 0 14.14 9a.5.5 0 0 1 .66.47"
                  "A6.8 6.8 0 1 1 8 1.2z")
_IC_THEME_LIGHT = ("M8 1.5a.5.5 0 0 1 .5.5V3a.5.5 0 0 1-1 0V2a.5.5 0 0 1 .5-.5z"
                   "M8 13a.5.5 0 0 1 .5.5V14a.5.5 0 0 1-1 0v-.5A.5.5 0 0 1 8 13z"
                   "M14.5 7.5a.5.5 0 0 1 0 1H14a.5.5 0 0 1 0-1h.5z"
                   "M2.5 7.5a.5.5 0 0 1 0 1H2a.5.5 0 0 1 0-1h.5z"
                   "M12.6 3.4a.5.5 0 0 1 .7 0l.35.35a.5.5 0 1 1-.7.7l-.35-.35a.5.5 0 0 1 0-.7z"
                   "M2.35 13.65a.5.5 0 0 1 .7 0l.35.35a.5.5 0 0 1-.7.7l-.35-.35a.5.5 0 0 1 0-.7z"
                   "M12.95 12.95a.5.5 0 0 1 .7 0l.35.35a.5.5 0 0 1-.7.7l-.35-.35a.5.5 0 0 1 0-.7z"
                   "M2.7 2.7a.5.5 0 0 1 .7 0l.35.35a.5.5 0 1 1-.7.7L2.7 3.4a.5.5 0 0 1 0-.7z"
                   "M8 4a4 4 0 1 1 0 8 4 4 0 0 1 0-8z")
_IC_SETTINGS = ("M9.405 1.05c-.413-1.4-2.397-1.4-2.81 0l-.1.34a1.464 1.464 0 0 1-2.105.872l-.31-.17"
                "c-1.283-.698-2.686.705-1.987 1.987l.169.311c.446.82.023 1.841-.872 2.105l-.34.1"
                "c-1.4.413-1.4 2.397 0 2.81l.34.1a1.464 1.464 0 0 1 .872 2.105l-.17.31"
                "c-.698 1.283.705 2.686 1.987 1.987l.311-.169a1.464 1.464 0 0 1 2.105.872l.1.34"
                "c.413 1.4 2.397 1.4 2.81 0l.1-.34a1.464 1.464 0 0 1 2.105-.872l.31.17"
                "c1.283.698 2.686-.705 1.987-1.987l-.169-.311a1.464 1.464 0 0 1 .872-2.105l.34-.1"
                "c1.4-.413 1.4-2.397 0-2.81l-.34-.1a1.464 1.464 0 0 1-.872-2.105l.17-.31"
                "c.698-1.283-.705-2.686-1.987-1.987l-.311.169a1.464 1.464 0 0 1-2.105-.872l-.1-.34z"
                "M8 10.93a2.929 2.929 0 1 1 0-5.86 2.929 2.929 0 0 1 0 5.858z")

# App icon - multi-colour 72x72 SVG rendered in the About dialog header.
_APP_VERSION = "1.3.1"
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
    event:      str   # event verb: 'resume', 'preempt', 'trigger', ...
    note:       str   # optional annotation (e.g. 'task_create', mutex name)

@dataclass
class TaskSegment:
    """One contiguous execution slice of a task on a core."""
    task: str
    start: int          # ns
    end: int            # ns
    core: str           # e.g. "Core_0"

@dataclass
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

@dataclass
class StiEvent:
    """An RTOS software trace item (mutex/semaphore/queue event, etc.)."""
    time: int
    core: str           # source core (e.g. "Core_0")
    target: str         # STI target name (e.g. "mutex_event")
    event: str          # event name (e.g. "trigger")
    note: str           # detail (e.g. "take_mutex")

@dataclass
class IntervalInstance:
    """Paired interval_start / interval_stop span."""
    id: str
    start_ns: int
    stop_ns: int
    start_core: str = ""
    stop_core: str = ""

_INTERVAL_START_CHANNELS = frozenset({"interval_start", "start_intval"})
_INTERVAL_STOP_CHANNELS  = frozenset({"interval_stop", "stop_intval"})
_INTERVAL_COLORS = (
    "#E74C3C", "#2ECC71", "#F39C12", "#3498DB", "#9B59B6",
    "#1ABC9C", "#E91E63", "#F1C40F", "#00BCD4", "#FF5722",
)

def _is_interval_marker_channel(channel: str) -> bool:
    return channel in _INTERVAL_START_CHANNELS or channel in _INTERVAL_STOP_CHANNELS

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
    parent interval survives culling.
    """
    if len(instances) <= 1:
        return instances
    by_duration = sorted(
        instances,
        key=lambda inst: ((inst.stop_ns - inst.start_ns), -inst.start_ns, inst.stop_ns),
        reverse=True,
    )
    kept: list = []
    for inst in by_duration:
        if any(
            p.start_ns <= inst.start_ns and p.stop_ns >= inst.stop_ns
            for p in kept
        ):
            continue
        kept.append(inst)
    kept.sort(key=lambda inst: inst.start_ns)
    return kept

def _build_interval_marker_index(
    sti_events: List[StiEvent],
) -> Dict[str, dict]:
    """Per-id sorted marker events for O(log n) viewport clipping."""
    by_id: Dict[str, dict] = {}
    for ev in sti_events:
        is_start = ev.target in _INTERVAL_START_CHANNELS
        if not is_start and ev.target not in _INTERVAL_STOP_CHANNELS:
            continue
        iid = ev.note if ev.note else "0"
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
    stop_pen.setStyle(Qt.DashLine)
    y2 = y + h
    for x, is_start in ticks:
        if x < exp_left - 1.0 or x > exp_right + 1.0:
            continue
        painter.setPen(start_pen if is_start else stop_pen)
        xi = round(x) + 0.5
        painter.drawLine(QLineF(xi, y, xi, y2))

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

def _build_interval_data(
    sti_events: List[StiEvent],
) -> Tuple[List["IntervalInstance"], List[str], Dict[str, List["IntervalInstance"]], int]:
    """Pair interval marker STI events into measurable spans."""
    open_stacks: Dict[str, List[StiEvent]] = {}
    instances: List[IntervalInstance] = []
    unmatched = 0

    def _is_start(ev: StiEvent) -> bool:
        return ev.target in _INTERVAL_START_CHANNELS

    def _ev_id(ev: StiEvent) -> str:
        return ev.note if ev.note else "0"

    ordered = sorted(
        [ev for ev in sti_events if _is_start(ev) or ev.target in _INTERVAL_STOP_CHANNELS],
        key=lambda e: (e.time, 0 if _is_start(e) else 1),
    )
    for ev in ordered:
        iid = _ev_id(ev)
        if _is_start(ev):
            open_stacks.setdefault(iid, []).append(ev)
        else:
            stack = open_stacks.get(iid)
            if not stack:
                continue
            start_ev = stack.pop()
            if ev.time > start_ev.time:
                instances.append(IntervalInstance(
                    id=iid,
                    start_ns=start_ev.time,
                    stop_ns=ev.time,
                    start_core=start_ev.core,
                    stop_core=ev.core,
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

def _plot_point_mark_ns(payload, x_ns: int) -> int:
    """Timeline position for an annotation created from a metrics plot point."""
    if isinstance(payload, IntervalInstance):
        return payload.stop_ns
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
    # Sorted timestamps from STI TICK events - rendered as ruler marks.
    tick_sti_times: List[int]                                               = field(default_factory=list)
    # Core migrations: consecutive slices of the same merge-key on different cores.
    migrations: List[MigrationEvent]                                        = field(default_factory=list)
    migrations_by_mk: Dict[str, List[MigrationEvent]]                       = field(default_factory=dict)
    interval_instances: List["IntervalInstance"]                            = field(default_factory=list)
    interval_ids: List[str]                                                 = field(default_factory=list)
    interval_instances_by_id: Dict[str, List["IntervalInstance"]]            = field(default_factory=dict)
    interval_marker_by_id: Dict[str, dict]                                  = field(default_factory=dict)
    interval_unmatched_starts: int                                          = 0

# ---------------------------------------------------------------------------
# Task-name helpers
# ---------------------------------------------------------------------------

_TASK_RE = re.compile(r"^\[((?:0[xX][0-9a-fA-F]+|\d+))/((?:0[xX][0-9a-fA-F]+|\d+))\](.+)$")
# Matches: idle, idle0, idle 0, idle(0x...), idle 0(0x...), idle0(0x...)
_IDLE_RE = re.compile(
    r"^idle(?:\s*(\d+))?\s*(?:\((?:0[xX][0-9a-fA-F]+|\d+)\))?$",
    re.IGNORECASE,
)

def _parse_int_token(s: str) -> int:
    """Parse an integer token that may be hex (0x...) or decimal (with optional leading zeros)."""
    if s.startswith(("0x", "0X")):
        return int(s, 16)
    return int(s, 10)

@functools.lru_cache(maxsize=16384)
def _parse_task_name(raw: str) -> Tuple[Optional[int], Optional[int], str]:
    """Return (core_id, task_id, display_name) from a raw BTF task name."""
    m = _TASK_RE.match(raw)
    if m:
        return _parse_int_token(m.group(1)), _parse_int_token(m.group(2)), m.group(3).strip()
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
    _, task_id, name = _parse_task_name(raw)
    if _is_idle_task_name(name):
        return _normalize_idle_name(name)
    if task_id is not None and name != "TICK":
        return f"{name}[{task_id}]"
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

def _migration_sti_near_count(trace: "BtfTrace", migs: List[MigrationEvent],
                              window: int = _MIGRATION_STI_WINDOW) -> int:
    if not migs or not trace.sti_events:
        return 0
    sti_times = sorted(e.time for e in trace.sti_events)
    count = 0
    for m in migs:
        lo = m.ns - window
        hi = m.ns + window
        i0 = bisect_left(sti_times, lo)
        i1 = bisect_right(sti_times, hi)
        if i1 > i0:
            count += 1
    return count

def _migration_rows(trace: "BtfTrace",
                    lo: Optional[int] = None, hi: Optional[int] = None
                    ) -> List[tuple]:
    """Rows for the Core Migrations stats table."""
    scale = trace.time_scale
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
        if total <= 0:
            continue
        primary = max(core_time, key=core_time.get)
        primary_pct = 100.0 * core_time[primary] / total
        ping = _count_ping_pong(migs)
        sti_near = _migration_sti_near_count(trace, migs)
        gaps_after = [m.gap_ns for m in migs if m.gap_ns > 0]
        all_gaps = _blocking_time_samples(segs, lo, hi)
        avg_after = (sum(gaps_after) / len(gaps_after)) if gaps_after else 0
        avg_other = (sum(all_gaps) / len(all_gaps)) if all_gaps else 0
        raw = trace.task_repr.get(mk, mk)
        disp = _task_display_name(raw)
        cores_str = ", ".join(sorted(cores, key=_core_sort_key_tuple))
        rows.append((
            mk, disp, len(migs), len(cores), cores_str, primary, primary_pct,
            ping, sti_near,
            _format_time(int(avg_after), scale) if avg_after else "-",
            _format_time(int(avg_other), scale) if avg_other else "-",
        ))
    rows.sort(key=lambda r: (-r[2], r[1].lower()))
    return rows

_TICK_HEALTH_PERIOD = 1000   # expected tick period in trace units (1 ms @ us scale)
_TICK_HEALTH_GAP_FACTOR = 2.0
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

    rows = []
    for mk, preemptors in data.items():
        raw = trace.task_repr.get(mk, mk)
        victim_disp = _task_display_name(raw)
        for pre_disp, durations in preemptors.items():
            total = sum(durations)
            avg = int(round(total / len(durations)))
            mx = max(durations)
            rows.append((
                mk,
                victim_disp,
                pre_disp,
                len(durations),
                _format_time(total, scale),
                _format_time(avg, scale),
                _format_time(mx, scale),
            ))

    rows.sort(key=lambda r: (-_time_label_sort_key(r[4]), r[1].lower(), r[2].lower()))
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
    """Summarise STI TICK timestamps: gaps, missed-tick estimate, health status."""
    times = trace.tick_sti_times
    if lo is not None and hi is not None:
        times = [t for t in times if lo <= t <= hi]
    if not times:
        return {"tick_count": 0, "health": "unknown", "large_gaps": [],
                "avg_period": 0, "max_gap": 0, "missed_estimate": 0}

    threshold = _TICK_HEALTH_PERIOD * _TICK_HEALTH_GAP_FACTOR
    large_gaps = []
    sum_delta = 0
    max_gap = 0
    missed_total = 0
    for i in range(1, len(times)):
        delta = times[i] - times[i - 1]
        sum_delta += delta
        if delta > max_gap:
            max_gap = delta
        if delta > threshold:
            missed = max(0, round(delta / _TICK_HEALTH_PERIOD) - 1)
            missed_total += missed
            large_gaps.append((times[i - 1], times[i], delta, missed))

    avg_period = sum_delta / (len(times) - 1) if len(times) > 1 else _TICK_HEALTH_PERIOD
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
    }

def _migration_heatmap_data(trace: "BtfTrace",
                            lo: Optional[int] = None, hi: Optional[int] = None,
                            time_bins: int = 32) -> Tuple[list, list, int]:
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
                              lo: Optional[int] = None, hi: Optional[int] = None
                              ) -> Tuple[list, list]:
    """Source × destination core counts (one row per source core)."""
    cores = trace.core_names
    n = len(cores)
    core_idx = {c: i for i, c in enumerate(cores)}
    grid = [[0] * n for _ in range(n)]
    for m in trace.migrations:
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

def _compare_csv_cell(v: object) -> str:
    s = str(v)
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
                         mig: List[List]) -> str:
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
    lines.append("Task,Migrations A,Migrations B,Δ,Ping-pong A,Ping-pong B")
    for row in mig:
        if len(row) >= 6:
            lines.append(",".join(_compare_csv_cell(c) for c in row[:6]))

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
                        mig: List[List]) -> str:
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
    mig_body = _rows_html(mig, 6, "No migrated tasks in either trace")

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
    <table><thead><tr><th>Task</th><th>Migr A</th><th>Migr B</th><th>Δ</th><th>Ping-pong A</th><th>Ping-pong B</th></tr></thead>
    <tbody>{mig_body}</tbody></table>
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
                    if _META_KEY_RE.match(key):
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
                _skipped_lines += 1
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

    sti_channels = sorted(
        {e.target for e in sti_events if not _is_interval_marker_channel(e.target)},
        key=_sti_channel_sort_key,
    )
    sti_by_target: Dict[str, List[StiEvent]] = defaultdict(list)
    for _ev in sti_events:
        sti_by_target[_ev.target].append(_ev)

    _interval_instances, _interval_ids, _interval_by_id, _interval_unmatched = (
        _build_interval_data(sti_events)
    )
    _interval_marker_by_id = _build_interval_marker_index(sti_events)

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
            _lst.sort(key=_seg_start_key)
        _core_segs[c].sort(key=_seg_start_key)
        _core_task_order[c] = sorted(_tsm.keys(), key=_task_sort_key)
        _core_task_segs[c]  = _tsm

    # Map raw task_create names to merge keys.
    _task_create_times: Dict[str, int] = {}
    for _raw_ct, _ct_time in _task_create_raw.items():
        _mk_ct = _mk_cache.get(_raw_ct) or _task_merge_key(_raw_ct)
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
    _core_seg_starts:     Dict[str, list] = {}
    _core_seg_lod:        Dict[str, list] = {}
    _core_seg_lod_starts: Dict[str, list] = {}
    _core_seg_lod_ultra:        Dict[str, list] = {}
    _core_seg_lod_ultra_starts: Dict[str, list] = {}
    for _c in _core_names:
        _core_seg_starts[_c] = list(map(_attrgetter('start'), _core_segs[_c]))
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
        tick_sti_times=sorted(tick_sti_times),
        migrations=_migrations,
        migrations_by_mk=dict(_migrations_by_mk),
        interval_instances=_interval_instances,
        interval_ids=_interval_ids,
        interval_instances_by_id=_interval_by_id,
        interval_marker_by_id=_interval_marker_by_id,
        interval_unmatched_starts=_interval_unmatched,
    )

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
    """Frameless persistent info popup - shown on hover-enter, hidden on hover-leave."""

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

    def show_at(self, screen_pos: QPoint, html: str, is_dark: Optional[bool] = None) -> None:
        if is_dark is None:
            app = QApplication.instance()
            if app is not None:
                is_dark = app.palette().color(QPalette.Window).lightness() < 128
            else:
                is_dark = True
        self._apply_stylesheet(bool(is_dark))
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

@functools.lru_cache(maxsize=4096)
def _task_color(task_raw: str) -> QColor:
    """Return a stable QColor for a task name.

    Color is keyed on the full raw name (including [core/id] prefix) so that
    two tasks with the same display name but different IDs get different colors.
    IDLE tasks always use grey shades, differentiated by their IDLE index.
    """
    core_id, tid, name = _parse_task_name(task_raw)
    if _is_idle_task_name(name):
        # Use task_id to differentiate IDLE tasks across cores; fall back to
        # the number suffix in the name, then 0.
        if tid is not None:
            idx = tid
        else:
            idx = _idle_task_index(name)
        greys = [180, 160, 140, 120, 100, 80]
        v = greys[idx % len(greys)]
        return QColor(v, v, v)
    if name in _SPECIAL_COLORS:
        return _SPECIAL_COLORS[name]
    # Use a deterministic hash so palette selection is stable across runs.
    _key = _task_merge_key(task_raw).encode("utf-8", errors="replace")
    palette = _PALETTE_COLORBLIND if _RENDER_RUNTIME.colorblind_active else _PALETTE
    idx = zlib.crc32(_key) % len(palette)
    return QColor(palette[idx])

def _blend_core_tint(base: QColor, core: str) -> QColor:
    tint = _CORE_TINTS.get(core, _CORE_TINTS["Core_?"])
    r = int(base.red()   * (1 - tint.alphaF()) + tint.red()   * tint.alphaF())
    g = int(base.green() * (1 - tint.alphaF()) + tint.green() * tint.alphaF())
    b = int(base.blue()  * (1 - tint.alphaF()) + tint.blue()  * tint.alphaF())
    return QColor(r, g, b)

@functools.lru_cache(maxsize=4096)
def _blended_color(task_raw: str, core: str) -> QColor:
    """Cached blend of a task's base color with a core tint."""
    return _blend_core_tint(_task_color(task_raw), core)

@functools.lru_cache(maxsize=4096)
def _task_brush(task_raw: str) -> QBrush:
    """Cached QBrush for a task's base color."""
    return QBrush(_task_color(task_raw))

@functools.lru_cache(maxsize=4096)
def _task_pen_dark(task_raw: str) -> QPen:
    """Cached dark-border QPen for a task's base color."""
    return QPen(_task_color(task_raw).darker(130), 0.7)

@functools.lru_cache(maxsize=4096)
def _blended_brush(task_raw: str, core: str) -> QBrush:
    """Cached QBrush for a task blended with a core tint."""
    return QBrush(_blended_color(task_raw, core))

@functools.lru_cache(maxsize=4096)
def _blended_pen_dark(task_raw: str, core: str) -> QPen:
    """Cached dark-border QPen for a task blended with a core tint."""
    return QPen(_blended_color(task_raw, core).darker(130), 0.7)

@functools.lru_cache(maxsize=4096)
def _complementary_color_cached(hex_str: str) -> QColor:
    """Cached implementation keyed by hex string (e.g. '#4e9af1')."""
    c = QColor(hex_str)
    h, s, v, _ = c.getHsvF()
    if h < 0:          # achromatic - fall back to a bright contrasting colour
        return QColor(255, 215, 0)
    h = (h + 0.5) % 1.0
    return QColor.fromHsvF(h, min(1.0, max(s, 0.85)), min(1.0, max(v, 0.90)))

def _complementary_color(c: QColor) -> QColor:
    """Return the hue-complementary (opposite on colour wheel) of *c*."""
    return _complementary_color_cached(c.name())

def _complementary_pen(c: QColor) -> QPen:
    """2.5-px highlight pen whose colour is complementary to *c*."""
    return QPen(_complementary_color(c), 2.5)

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

def _clear_render_color_caches(include_complementary: bool = False) -> None:
    """Clear all task/render color caches.

    Keep this centralised so palette/state changes do not rely on duplicated
    call-order across multiple code paths.
    """
    _task_color.cache_clear()
    _blended_color.cache_clear()
    _task_brush.cache_clear()
    _task_pen_dark.cache_clear()
    _blended_brush.cache_clear()
    _blended_pen_dark.cache_clear()
    if include_complementary:
        _complementary_color_cached.cache_clear()

def _set_colorblind_mode(enabled: bool) -> None:
    """Apply colorblind palette mode and invalidate dependent caches."""
    _RENDER_RUNTIME.colorblind_active = bool(enabled)
    _clear_render_color_caches()

def _set_vertical_label_pixmap_mode(enabled: bool) -> None:
    """Apply vertical-label rendering mode at module scope."""
    _RENDER_RUNTIME.vertical_label_use_pixmap = bool(enabled)

def _reset_render_state_for_new_trace() -> None:
    """Reset dynamic render state before loading a new trace."""
    _STI_DYNAMIC_COLORS.clear()
    _clear_render_color_caches(include_complementary=True)

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

# Multipliers to convert a value in the trace's native time unit to nanoseconds.
# Unknown units fall back to 1 (treated as ns).
_NS_MULTIPLIERS: dict[str, int] = {"ns": 1, "us": 1_000, "ms": 1_000_000}

# Fixed preset zoom levels expressed as percentage of fit-to-window.
# 100% = entire trace visible (Fit); smaller % = more zoomed in.
_ZOOM_PRESET_PERCENTAGES: tuple = (
    1, 2, 5, 10, 25, 50, 75,
)

# Ordered tiers for auto-scaling: (threshold_ns, divisor, unit_label)
_TIME_TIERS: tuple = (
    (1_000_000_000, 1_000_000_000, "s"),
    (1_000_000,     1_000_000,     "ms"),
    (1_000,         1_000,         "µs"),
    (0,             1,             "ns"),
)

def _to_ns(value: float, time_scale: str) -> float:
    """Convert *value* from the trace's native *time_scale* unit to nanoseconds."""
    return value * _NS_MULTIPLIERS.get(time_scale, 1)

def _format_time(value: float, time_scale: str = "ns", decimals: int = 3) -> str:
    """Format a timestamp (in the trace's native *time_scale* unit) into a
    human-readable string with automatic unit scaling (ns -> us -> ms -> s).

    *decimals* controls the number of decimal places (default 3).
    Pass ``decimals=1`` for a compact 'xx.x' display.
    """
    ns = _to_ns(value, time_scale)
    fmt = f"{{:.{decimals}f}}"
    for threshold, divisor, label in _TIME_TIERS:
        if ns >= threshold:
            return f"{fmt.format(ns / divisor)} {label}"
    return f"{fmt.format(ns)} ns"  # unreachable; satisfies type checkers

_TIME_LABEL_TO_NS: Dict[str, float] = {
    "ns": 1.0,
    "µs": 1_000.0,
    "us": 1_000.0,
    "ms": 1_000_000.0,
    "s": 1_000_000_000.0,
}

def _time_label_sort_key(text: str) -> float:
    """Convert a formatted duration label back to nanoseconds for table sorting."""
    s = str(text).strip()
    if not s or s == "-":
        return -1.0
    parts = s.split()
    if len(parts) < 2:
        try:
            return float(parts[0])
        except ValueError:
            return 0.0
    try:
        val = float(parts[0])
    except ValueError:
        return 0.0
    return val * _TIME_LABEL_TO_NS.get(parts[1], 1.0)

def _format_timescale_per_px(timescale_per_px: float, time_scale: str = "ns") -> str:
    """Format *timescale_per_px* (value per pixel in the trace's native unit)
    to an auto-scaled human-readable string in 'xx.x unit/px' format.

    Automatically selects the most readable unit from ns, us, ms, s.
    """
    ns = _to_ns(timescale_per_px, time_scale)
    for threshold, divisor, label in _TIME_TIERS:
        if ns >= threshold:
            return f"{ns / divisor:.1f} {label}/px"
    return f"{ns:.1f} ns/px"  # unreachable; satisfies type checkers

def _pixmap_to_png_bytes(pixmap: QPixmap) -> Tuple[bytes, QByteArray]:
    """Encode *pixmap* as PNG; return raw bytes and the backing QByteArray."""
    buf = QByteArray()
    buf_dev = QBuffer(buf)
    buf_dev.open(QIODevice.WriteOnly)
    pixmap.save(buf_dev, 'PNG')
    buf_dev.close()
    return bytes(buf), buf

def _is_wsl() -> bool:
    if os.environ.get('WSL_DISTRO_NAME'):
        return True
    try:
        with open('/proc/version', 'r', encoding='utf-8', errors='ignore') as f:
            return 'microsoft' in f.read().lower()
    except OSError:
        return False

def _copy_png_to_windows_clipboard(png_bytes: bytes) -> bool:
    """WSL helper: copy PNG bytes to the Windows clipboard as an image via PowerShell."""
    if not shutil.which('powershell.exe'):
        return False

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix='btf_snapshot_', suffix='.png', delete=False) as tmp:
            tmp.write(png_bytes)
            tmp_path = tmp.name

        win_path = subprocess.check_output(['wslpath', '-w', tmp_path], text=True).strip()
        ps_script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "Add-Type -AssemblyName System.Drawing; "
            "$img = [System.Drawing.Image]::FromFile($args[0]); "
            "[System.Windows.Forms.Clipboard]::SetImage($img); "
            "$img.Dispose()"
        )
        proc = subprocess.run(
            ['powershell.exe', '-NoProfile', '-STA', '-Command', ps_script, win_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if proc.returncode != 0:
            print(f"[BTF Viewer] clipboard error: {proc.stderr.strip()}", file=sys.stderr)
            return False
        return True
    except (OSError, subprocess.SubprocessError, ValueError):
        return False
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

def _copy_pixmap_to_clipboard(pixmap: QPixmap) -> Optional[str]:
    """Copy *pixmap* to the system clipboard as PNG.

    Returns the external tool name used ('powershell', 'wl-copy', 'xclip',
    'xsel'), or None when the Qt clipboard fallback was used.
    """
    png_bytes, buf = _pixmap_to_png_bytes(pixmap)

    if _is_wsl() and _copy_png_to_windows_clipboard(png_bytes):
        return 'powershell'

    # Prefer tools that explicitly support image MIME types (wl-copy, xclip).
    # xsel is last — it often accepts bytes but does not store image targets reliably.
    for tool, args in [
        ('wl-copy', ['wl-copy', '--type', 'image/png']),
        ('xclip',   ['xclip',   '-selection', 'clipboard', '-t', 'image/png']),
        ('xsel',    ['xsel',    '--clipboard', '--input']),
    ]:
        if shutil.which(tool):
            proc = subprocess.Popen(args, stdin=subprocess.PIPE)
            proc.communicate(png_bytes)
            if proc.returncode == 0:
                return tool

    clipboard = QApplication.clipboard()
    mime = QMimeData()
    mime.setData('image/png', buf)
    mime.setImageData(pixmap.toImage())
    clipboard.setMimeData(mime)
    clipboard.setPixmap(pixmap)
    return None

def _stack_pixmaps_vertically(top: QPixmap, bottom: QPixmap) -> QPixmap:
    """Return a new pixmap with *bottom* drawn below *top*."""
    combined = QPixmap(max(top.width(), bottom.width()),
                       top.height() + bottom.height())
    combined.fill(Qt.transparent)
    painter = QPainter(combined)
    try:
        painter.drawPixmap(0, 0, top)
        painter.drawPixmap(0, top.height(), bottom)
    finally:
        painter.end()
    return combined

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

def _make_rotated_label(scene, text: str, font: "QFont", color: "QColor",
                        x_center: float, y: float, z: float) -> "QGraphicsItem":
    """Add an antialiased rotated label to *scene*.

    Two rendering strategies are available, selected by the module-level flag
    *_VERTICAL_LABEL_USE_PIXMAP_DEFAULT* (default: True on Windows, False elsewhere):

    Pixmap strategy (Windows workaround)
        Renders the text onto a QPixmap horizontally - where all platforms
        apply full antialiasing - then rotates the finished image by -90deg.
        This sidesteps the Windows/GDI limitation that prevents antialiasing
        of rotated text glyphs, producing smooth labels on all Windows
        rendering back-ends (GDI, Direct2D, OpenGL).

    TextItem strategy (default on non-Windows)
        Creates a QGraphicsTextItem (not SimpleTextItem, which renders as a
        filled silhouette) and sets QFont.PreferAntialias so Qt's own
        subpixel renderer is used instead of GDI.  Rotation is applied via
        QGraphicsItem.setRotation(-90deg).  Works correctly on macOS / Linux.

    *x_center* is the horizontal centre of the column the label belongs to.
    The item is horizontally centred on that column.  The *y* parameter is the
    **bottom edge** of the label in scene coordinates - the label text grows
    upward from that point in both rendering paths.
    """
    if _RENDER_RUNTIME.vertical_label_use_pixmap:
        # --- Pixmap path: render text at native res, then rotate the image ---
        pm_font = QFont(font)
        fm = QFontMetrics(pm_font)
        # Add small horizontal/vertical padding to avoid clipping descenders.
        pad_x, pad_y = 2, 1
        px_w = fm.horizontalAdvance(text) + pad_x * 2
        px_h = fm.height() + pad_y * 2
        dpr = QApplication.instance().devicePixelRatio()
        pm = QPixmap(max(1, math.ceil(px_w * dpr)), max(1, math.ceil(px_h * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        # Re-measure against the paint device so that subpixel hinting of the
        # high-DPI pixmap is reflected in the draw rect.
        fm_dev = QFontMetricsF(pm_font, pm)
        dev_w = fm_dev.horizontalAdvance(text) + pad_x * 2
        dev_h = fm_dev.height() + pad_y * 2
        p = QPainter(pm)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.TextAntialiasing)
            p.setFont(pm_font)
            p.setPen(color)
            p.drawText(QRectF(0, 0, dev_w, dev_h), Qt.AlignCenter, text)
        finally:
            p.end()
        # Rotate -90deg and use SmoothTransformation so the resampling step
        # does not introduce additional jaggedness.
        rotated = pm.transformed(QTransform().rotate(-90), Qt.SmoothTransformation)
        rotated.setDevicePixelRatio(dpr)
        item = QGraphicsPixmapItem(rotated)
        # The pixmap has no further rotation applied, so pos.y is the TOP of the
        # image (extends downward).  The TextItem path anchors pos.y at the BOTTOM
        # of the text (it extends upward after the -90deg rotation).  Shift the
        # pixmap up by its own height so both paths share the same y anchor: the
        # bottom edge of the label sits at y, and the text grows upward.
        item.setPos(x_center - rotated.width() / 2.0, y - rotated.height())
        item.setZValue(z)
        item.setAcceptedMouseButtons(Qt.NoButton)
        item.setAcceptHoverEvents(False)
        scene.addItem(item)
        return item
    else:
        # --- TextItem path: rotated QGraphicsTextItem with PreferAntialias ---
        # Force non-GDI antialiasing on Windows so rotated glyphs are smooth.
        aa_font = QFont(font)
        aa_font.setStyleStrategy(QFont.PreferAntialias)
        item = QGraphicsTextItem(text)
        item.setFont(aa_font)
        item.setDefaultTextColor(color)
        item.setRotation(-90)
        # QGraphicsTextItem bounding rect includes a 2 px document margin on
        # each side, so use the real height rather than fm.height() for
        # centering.
        item.setPos(x_center - item.boundingRect().height() / 2, y)
        item.setZValue(z)
        item.setAcceptedMouseButtons(Qt.NoButton)
        item.setAcceptHoverEvents(False)
        scene.addItem(item)
        return item

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
    sub-pixel wide and stacked on top of each other.  Keeping only one
    segment per pixel column reduces the rendered count by up to 30x at the
    default fit-to-width zoom with no visible quality loss.  Callers are
    responsible for passing segments pre-sorted by start time.

    When multiple segments share the same pixel column the one that extends
    furthest to the right (latest end time) is kept.  This prevents a trivial
    sub-pixel segment (e.g. 1 ns) from hiding a long execution segment that
    starts just after it in the same column.
    """
    if len(segs) <= 1:
        return segs
    result: list = []
    prev_bin = -2
    for seg in segs:
        b = math.floor(offset + (seg.start - time_min) * px_per_ns)
        if b != prev_bin:
            result.append(seg)
            prev_bin = b
        elif seg.end > result[-1].end:
            # Same pixel column but this segment extends further right -
            # replace the previous entry so the more important one is visible.
            result[-1] = seg
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
    if (len(result) > _MAX_FINE_SEGS_PER_ROW
            and vp.cur_timescale_per_px >= vp.lod_timescale_per_px
            and lod.lod_segs):
        if lod.lod_starts:
            lo = max(0, bisect_left(lod.lod_starts, vp.ns_lo) - 1)
            hi = min(len(lod.lod_segs), bisect_right(lod.lod_starts, vp.ns_hi) + 1)
            clipped = lod.lod_segs[lo:hi]
        else:
            clipped = lod.lod_segs
        result = _lod_reduce(clipped, vp.time_min, vp.px_per_ns, vp.offset)
    return result

def _orth_cull_params(n_tasks: int) -> Tuple[int, float]:
    """Orthogonal row/column margin for rebuild culling (smaller on large traces)."""
    if n_tasks > _ORTH_BUF_HUGE_TASKS:
        return 24, 2.0
    if n_tasks > _ORTH_BUF_LARGE_TASKS:
        return 30, 2.25
    return _ORTH_BUF_MIN_ROWS, _ORTH_BUF_VIEWPORT_MULT

def _zoom_debounce_ms(n_tasks: int) -> int:
    if n_tasks > _ORTH_BUF_HUGE_TASKS:
        return _ZOOM_DEBOUNCE_HUGE_MS
    if n_tasks > _ORTH_BUF_LARGE_TASKS:
        return _ZOOM_DEBOUNCE_LARGE_MS
    return _ZOOM_DEBOUNCE_MS

def _nice_grid_step(timescale_per_px: float, target_px: float = 100.0) -> int:
    """Return a 'nice' grid step (in ns) so that one step ~= target_px pixels."""
    ideal_ns = max(float(timescale_per_px) * target_px, 1.0)
    if ideal_ns <= _GRID_STEPS[-1]:
        for step in _GRID_STEPS:
            if step >= ideal_ns:
                return step
        return _GRID_STEPS[-1]
    # Fit-to-window on long traces can need multi-second steps; extend the
    # 1-2-5-10 decade ladder beyond the fixed microsecond table.
    mag = 10.0 ** math.floor(math.log10(ideal_ns))
    for mult in (1, 2, 5, 10):
        step = int(round(mag * mult))
        if step >= ideal_ns:
            return max(step, 1)
    return max(int(round(mag * 10)), 1)

def _process_ui_events_safely() -> None:
    """Pump paint/progress updates without allowing user-input re-entrancy."""
    app = QApplication.instance()
    if app is None:
        return
    app.processEvents(QEventLoop.ExcludeUserInputEvents)

# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------

class _SuspendRebuild:
    """Defer TimelineScene.rebuild() until the outermost suspend context exits."""

    __slots__ = ('_scene',)

    def __init__(self, scene: 'TimelineScene') -> None:
        self._scene = scene

    def __enter__(self) -> '_SuspendRebuild':
        self._scene._rebuild_suspend += 1
        return self

    def __exit__(self, *_args) -> None:
        sc = self._scene
        sc._rebuild_suspend = max(0, sc._rebuild_suspend - 1)
        if sc._rebuild_suspend == 0:
            sc.rebuild()

class TimelineScene(QGraphicsScene):
    """Manages the full timeline and renders it as QGraphicsItems.

    The scene is stateless between rebuilds: every zoom or orientation change
    calls rebuild() which calls one of four builder methods:

        _build_horizontal       - task view, horizontal (time on X axis)
        _build_vertical         - task view, vertical   (time on Y axis)
        _build_horizontal_core  - core view, horizontal
        _build_vertical_core    - core view, vertical

    Because there is no incremental update, the scene can handle 1M+ events
    without housekeeping overhead; the cost is paid only when zooming.
    Paint performance is recovered via the 3-tier LOD system in _BatchRowItem.
    """

    scene_rebuilt    = pyqtSignal()          # emitted after every rebuild()
    highlight_changed = pyqtSignal(object, bool) # (task_name_or_None, locked)
    hover_changed    = pyqtSignal()          # emitted when hover cursor position changes
    marks_changed    = pyqtSignal()          # emitted when bookmark/annotation marks change

    def __init__(self, parent=None):
        super().__init__(parent)
        # Disable Qt's BSP spatial index.  The default BSP index updates on
        # every addItem() / removeItem() / clear() call which dominates rebuild
        # time when the scene is torn down and re-created on each scroll/zoom.
        # Hit-testing is O(n_items) with NoIndex; that is fine because a
        # culled rebuild only materialises ~30-70 items at a time.
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
        self._sti_expanded: set = set()             # channels with expanded waveform
        self._sti_log_scale: bool = False           # log2 scale for STI waveform
        self._sti_line_style: str = STI_LINE_STYLE  # waveform draw style: "step" or "linear"
        self._sti_row_h_val:      int = STI_ROW_H       # collapsed STI row height (px)
        self._sti_waveform_h_val: int = STI_WAVEFORM_H  # expanded STI waveform height (px)
        self._font_size: int = FONT_SIZE            # label font size (pt)
        self._max_cursors: int = _DEFAULT_MAX_CURSORS  # max simultaneous cursors
        self._label_width: int = LABEL_WIDTH            # resizable label-column width (px)
        self._row_height: int = ROW_HEIGHT              # row height (px)
        self._row_gap:    int = ROW_GAP                 # gap between rows (px)
        self._hover_highlight: bool = _HOVER_HIGHLIGHT_ENABLED
        self._task_filter_q: str = ""
        self._migrated_only_filter: bool = False
        self._heatmap_filter_mks: Optional[set] = None
        self._rebuild_suspend: int = 0
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
        # view (fit, load, orientation switch, ...), the scroll position at the
        # time _update_viewport_bounds() runs is stale.  Setting this flag
        # makes _update_viewport_bounds() skip orth culling for that one
        # rebuild, ensuring all rows/columns are built.
        self._skip_orth_culling: bool = False
        # Viewport orthogonal bounds (row Y for horizontal view, column X for
        # vertical view).  Initialised to +/-inf so all rows are built on the
        # first rebuild before a live view is attached.
        self._vp_scene_orth_lo: float = -1e18
        self._vp_scene_orth_hi: float = +1e18
        # Half-width of the orthogonal culling margin (px), set in rebuild().
        self._vp_orth_buf: float = 0.0
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
        # Set of cursor-label QGraphicsItems appended to _frozen_top_items by
        # the most recent _draw_cursors() call.  Used to purge stale entries
        # on a direct (non-rebuild) _draw_cursors() call (e.g. cursor drag).
        self._cursor_frozen_top_set: set = set()
        # Set of cursor-label QGraphicsItems appended to _frozen_items by
        # vertical-mode _draw_cursors() calls (left-edge frozen labels).
        self._cursor_frozen_left_set: set = set()
        # -- Mark overlay (bookmarks + annotations) ----------------------
        # Each entry: (ns, label, color_hex)
        self._mark_data: List[tuple] = []
        self._mark_items: list = []    # live QGraphicsItems for marks
        self._mark_frozen_top_set: set = set()   # items added by _draw_marks (top-frozen)
        self._mark_frozen_left_set: set = set()  # items added by _draw_marks (left-frozen)
        # -- Find-hit overlay (all match positions from the Find panel) ---
        self._find_hit_ns_list: List[int] = []
        self._find_hit_items: list = []
        # -- Task highlight state ----------------------------------------
        self._locked_task:  Optional[str] = None   # click-locked task (persistent)
        self._locked_core:  Optional[str] = None   # core context for locked task (core view)
        self._locked_ns:    Optional[int] = None   # reference time of locked selection
        self._locked_segment_key: Optional[tuple] = None  # (mk, start, end, core)
        self._highlighted_interval: Optional["IntervalInstance"] = None
        self._highlighted_interval_mark_ns: Optional[int] = None
        self._hovered_task: Optional[str] = None   # hover task (transient)
        # task_key -> [(QRectF, QColor)] - populated by builders, used for hover overlays
        self._task_row_rects: Dict[str, list] = {}
        self._hover_overlay_items: list = []   # lightweight overlay items (no rebuild)
        # -- Mouse-hover indicator ---------------------------------------
        # Ghost dashed line + time label that follows the mouse; never placed
        # as a real cursor.  Redrawn on every mouse-move, cleared on leave.
        self._hover_ns: Optional[int] = None
        self._hover_line_ns: Optional[int] = None
        self._hover_items: list = []
        self._is_dark_ui: bool = True
        self.set_theme(True, rebuild=False)

    def set_theme(self, is_dark: bool, rebuild: bool = True) -> None:
        """Update scene palette used by row/header background builders."""
        self._is_dark_ui = bool(is_dark)
        if is_dark:
            self._c_ruler_bg = QColor("#2B2B2B")
            self._c_label_bg = QColor("#1E1E1E")
            self._c_row_even = QColor("#252526")
            self._c_row_odd = QColor("#2D2D2D")
            self._c_sep = QColor("#333333")
            self._c_label_txt = QColor("#D4D4D4")
            self._c_sti_bg = QColor("#1A1A2E")
            self._c_sti_lbl = QColor("#88AABB")
            self._c_corner_bg = QColor("#1A1A1A")
            self._c_header_txt = QColor("#888888")
            self._c_core_sum_bg = QColor("#2A2A3E")
            self._c_core_sep = QColor("#444466")
            self._c_core_hdr_bg = QColor("#2B2B45")
            self._c_core_arrow = QColor("#9999CC")
            self._c_core_lbl = QColor("#E0E0E0")
            self._c_core_sub_even = QColor("#1E1E2C")
            self._c_core_sub_odd = QColor("#232330")
            self._c_core_sub_sep = QColor("#2E2E3A")
            self._c_core_sub_lbl = QColor("#B0B0C0")
        else:
            self._c_ruler_bg = QColor("#E0E0E0")
            self._c_label_bg = QColor("#F5F5F5")
            self._c_row_even = QColor("#FFFFFF")
            self._c_row_odd = QColor("#F2F2F2")
            self._c_sep = QColor("#D0D0D0")
            self._c_label_txt = QColor("#333333")
            self._c_sti_bg = QColor("#EEF3F8")
            self._c_sti_lbl = QColor("#3F688F")
            self._c_corner_bg = QColor("#E8E8E8")
            self._c_header_txt = QColor("#666666")
            self._c_core_sum_bg = QColor("#E7ECF3")
            self._c_core_sep = QColor("#C9D3E1")
            self._c_core_hdr_bg = QColor("#DDE6F2")
            self._c_core_arrow = QColor("#5A6E8A")
            self._c_core_lbl = QColor("#1E1E1E")
            self._c_core_sub_even = QColor("#F7F9FC")
            self._c_core_sub_odd = QColor("#EEF2F7")
            self._c_core_sub_sep = QColor("#D5DCE7")
            self._c_core_sub_lbl = QColor("#4E5A6C")
        if rebuild and self._trace is not None:
            self.rebuild()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def suspend_rebuild(self) -> _SuspendRebuild:
        return _SuspendRebuild(self)

    def set_trace(self, trace: BtfTrace, viewport_width: int = 1200) -> None:
        self._trace = trace
        self._heatmap_filter_mks = None
        time_span = max(trace.time_max - trace.time_min, 1)
        avail = max(viewport_width - self._label_width, 100)
        self._timescale_per_px = time_span / avail
        self._timescale_per_px_fit = self._timescale_per_px   # record fit-to-view limit
        # Scale the max-zoom-in limit to the trace's native time unit.
        # _TIMESCALE_PER_PX_DEFAULT is 2 ns/px; dividing by the ns-per-trace-unit
        # multiplier yields the equivalent limit in trace units (e.g. 0.002 us/px
        # for a us-scale trace), ensuring zoom-in works correctly regardless of
        # the time scale used by the BTF file.
        _ns_mult = _NS_MULTIPLIERS.get(trace.time_scale, 1)
        self._timescale_per_px_default = _TIMESCALE_PER_PX_DEFAULT / _ns_mult
        # Do NOT set _skip_orth_culling here: the viewport bounds are valid
        # (window is visible) and orth culling keeps the initial build to
        # O(visible_rows) instead of O(all_rows), preventing a UI freeze
        # when loading large traces (e.g. 128 cores x 1000 tasks).
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

    def toggle_sti_channel(self, channel: str) -> None:
        """Expand or collapse a single STI channel's waveform view.

        Only tag_event / tag[0-7]_event channels support expansion.
        """
        if not _is_tag_sti_channel(channel):
            return
        if channel in self._sti_expanded:
            self._sti_expanded.discard(channel)
        else:
            self._sti_expanded.add(channel)
        self.rebuild()

    def set_sti_log_scale(self, enabled: bool) -> None:
        """Switch the STI waveform y-axis between linear and log2 scale."""
        self._sti_log_scale = bool(enabled)
        if self._sti_expanded:
            self.rebuild()

    def set_sti_line_style(self, style: str) -> None:
        """Switch STI waveform draw style (\"step\" or \"linear\") and rebuild."""
        self._sti_line_style = style if style in ("step", "linear") else STI_LINE_STYLE
        if self._sti_expanded:
            self.rebuild()

    def set_sti_row_h(self, h: int) -> None:
        """Change the collapsed STI row height (px) and rebuild."""
        self._sti_row_h_val = max(12, min(h, 60))
        self.rebuild()

    def set_sti_waveform_h(self, h: int) -> None:
        """Change the expanded STI waveform height (px) and rebuild."""
        self._sti_waveform_h_val = max(40, min(h, 300))
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
        """Set the maximum number of simultaneous cursors (4-8)."""
        self._max_cursors = max(4, min(n, _MAX_CURSORS))
        # Evict oldest cursors if the current count now exceeds the new limit.
        while len(self._cursor_times) > self._max_cursors:
            self._cursor_times.pop(0)
        self._draw_cursors()

    def set_marks(self, bookmarks: list, annotations: list) -> None:
        """Update the mark overlay from bookmark / annotation lists.

        bookmarks   - list of TraceBookmark (ns, label)
        annotations - list of TraceAnnotation (ns, note)
        """
        data = []
        for b in bookmarks:
            data.append((b.ns, b.label or "", "#FFD700", "bookmark", b.id))   # gold
        for a in annotations:
            data.append((a.ns, a.note  or "", "#FF8C00", "annotation", a.id))  # orange
        data.sort(key=lambda t: t[0])
        self._mark_data = data
        self._draw_marks()
        self.marks_changed.emit()

    def _draw_marks(self) -> None:
        """Draw a dotted vertical/horizontal line + label for every mark."""
        _safe_scene_remove_items(self, self._mark_items)
        self._mark_items.clear()
        # Purge frozen entries added by the previous call.
        if self._mark_frozen_top_set:
            self._frozen_top_items = [e for e in self._frozen_top_items
                                      if e[0] not in self._mark_frozen_top_set]
            self._mark_frozen_top_set = set()
        if self._mark_frozen_left_set:
            self._frozen_items = [e for e in self._frozen_items
                                  if e[0] not in self._mark_frozen_left_set]
            self._mark_frozen_left_set = set()

        if self._trace is None or not self._mark_data:
            return

        scene_r  = self.sceneRect()
        font     = _monospace_font(self._font_size)
        fm       = QFontMetrics(font)
        _views   = self.views()
        _scene_top  = _views[0].mapToScene(QPoint(0, 0)).y()  if _views else 0.0
        _scene_left = _views[0].mapToScene(QPoint(0, 0)).x()  if _views else 0.0

        for row_idx, (ns, label, color_hex, *_extra) in enumerate(self._mark_data):
            color = QColor(color_hex)
            kind = _extra[0] if _extra else "bookmark"
            pen  = QPen(color, 1.2, Qt.SolidLine) if kind == "bookmark" else QPen(color, 1.0, Qt.DashLine)

            if self._horizontal:
                x = self._label_width + self._ns_to_px(ns)
                line = QGraphicsLineItem(x, 0, x, scene_r.height())
                line.setPen(pen)
                line.setZValue(28)   # below cursor lines (z=30)
                self.addItem(line)
                self._mark_items.append(line)

                # Small flag polygon at the ruler's bottom edge (y-frozen so
                # it stays in the ruler band regardless of vertical scroll).
                _f_hw = 4      # half-width of the flag base in px
                _f_h  = 6      # flag height in px
                _f_ty = RULER_HEIGHT - 2          # tip  y (local, item.y == scene_top)
                _f_by = _f_ty - _f_h              # base y
                _flag_color = QColor("#FFD700") if kind == "bookmark" else QColor("#FFA500")
                if kind == "bookmark":
                    # Downward-pointing triangle
                    _flag_pts = [QPointF(x - _f_hw, _f_by),
                                 QPointF(x + _f_hw, _f_by),
                                 QPointF(x,         _f_ty)]
                else:
                    # Diamond
                    _mid_y = (_f_by + _f_ty) / 2.0
                    _flag_pts = [QPointF(x,        _f_by),
                                 QPointF(x + _f_hw, _mid_y),
                                 QPointF(x,         _f_ty),
                                 QPointF(x - _f_hw, _mid_y)]
                _flag = QGraphicsPolygonItem(QPolygonF(_flag_pts))
                _flag.setBrush(QBrush(_flag_color))
                _flag.setPen(QPen(Qt.NoPen))
                _flag.setZValue(31)   # above cursor lines (z=30)
                _flag.setToolTip(f"{'Bookmark' if kind == 'bookmark' else 'Annotation'}: {label}")
                self.addItem(_flag)
                self._mark_items.append(_flag)
                self._frozen_top_items.append((_flag, 0))
                self._mark_frozen_top_set.add(_flag)

                short = (label[:24] + "…") if len(label) > 24 else label
                lbl = self.addSimpleText(short, font)
                lbl.setBrush(QBrush(QColor("#000000")))
                lbl.setZValue(29)
                tw = fm.horizontalAdvance(short)
                th = fm.height()
                lbl_x = min(x + 3, scene_r.width() - tw - 4)
                _orig_y = 2 + (row_idx % 4 + 1) * (th + 1)
                lbl_y   = _scene_top + _orig_y + RULER_HEIGHT // 2
                bg = self.addRect(
                    QRectF(0, 0, tw + 4, th + 2),
                    QPen(Qt.NoPen),
                    QBrush(color),
                )
                bg.setZValue(28)
                bg.setPos(lbl_x - 2, lbl_y - 1)
                lbl.setPos(lbl_x, lbl_y)
                self._mark_items.extend([bg, lbl])
                self._frozen_top_items.append((bg,  _orig_y + RULER_HEIGHT // 2 - 1))
                self._frozen_top_items.append((lbl, _orig_y + RULER_HEIGHT // 2))
                self._mark_frozen_top_set.update({bg, lbl})

            else:  # vertical mode
                label_row_h = self._label_width
                y = label_row_h + self._ns_to_px(ns)
                line = QGraphicsLineItem(0, y, scene_r.width(), y)
                line.setPen(pen)
                line.setZValue(28)
                self.addItem(line)
                self._mark_items.append(line)

                # Small flag polygon at the ruler's right edge (x-frozen).
                _f_hw = 4
                _f_h  = 6
                _f_rx = RULER_WIDTH - 2          # rightmost x of flag (local: item.x == scene_left)
                _f_lx = _f_rx - _f_h             # left x
                _flag_color = QColor("#FFD700") if kind == "bookmark" else QColor("#FFA500")
                if kind == "bookmark":
                    _flag_pts = [QPointF(_f_lx, y - _f_hw),
                                 QPointF(_f_lx, y + _f_hw),
                                 QPointF(_f_rx, y)]
                else:
                    _mid_x = (_f_lx + _f_rx) / 2.0
                    _flag_pts = [QPointF(_f_lx, y),
                                 QPointF(_mid_x, y - _f_hw),
                                 QPointF(_f_rx,  y),
                                 QPointF(_mid_x, y + _f_hw)]
                _flag = QGraphicsPolygonItem(QPolygonF(_flag_pts))
                _flag.setBrush(QBrush(_flag_color))
                _flag.setPen(QPen(Qt.NoPen))
                _flag.setZValue(31)
                _flag.setToolTip(f"{'Bookmark' if kind == 'bookmark' else 'Annotation'}: {label}")
                self.addItem(_flag)
                self._mark_items.append(_flag)
                self._frozen_items.append((_flag, 0))
                self._mark_frozen_left_set.add(_flag)

                short = (label[:24] + "…") if len(label) > 24 else label
                lbl = self.addSimpleText(short, font)
                lbl.setBrush(QBrush(QColor("#000000")))
                lbl.setZValue(29)
                tw = fm.horizontalAdvance(short)
                th = fm.height()
                _left_pad = RULER_WIDTH + 4 + (row_idx % 3) * (tw + 6)
                lbl_x = _scene_left + _left_pad
                lbl_y = y + 2
                bg = self.addRect(
                    QRectF(0, 0, tw + 4, th + 2),
                    QPen(Qt.NoPen),
                    QBrush(color),
                )
                bg.setZValue(28)
                bg.setPos(lbl_x - 2, lbl_y - 1)
                lbl.setPos(lbl_x, lbl_y)
                self._mark_items.extend([bg, lbl])
                self._frozen_items.append((bg,  _left_pad - 2))
                self._frozen_items.append((lbl, _left_pad))
                self._mark_frozen_left_set.update({bg, lbl})

    def set_hover_highlight(self, enabled: bool) -> None:
        """Enable or disable hover-over-label task highlighting."""
        self._hover_highlight = enabled
        if not enabled:
            self.clear_hover()

    def set_find_hits(self, ns_list: list) -> None:
        """Update the find-hit overlay with a new list of ns timestamps."""
        self._find_hit_ns_list = list(ns_list)
        self._draw_find_markers()

    def _draw_find_markers(self) -> None:
        """Draw thin vertical/horizontal lines for each find hit."""
        _safe_scene_remove_items(self, self._find_hit_items)
        self._find_hit_items.clear()
        if self._trace is None or not self._find_hit_ns_list:
            return
        scene_r = self.sceneRect()
        pen = QPen(QColor("#FF6B35"), 1.0, Qt.SolidLine)
        pen.setCosmetic(True)
        for ns in self._find_hit_ns_list:
            if self._horizontal:
                x = self._label_width + self._ns_to_px(ns)
                line = QGraphicsLineItem(x, 0, x, scene_r.height())
            else:
                y = self._label_width + self._ns_to_px(ns)
                line = QGraphicsLineItem(0, y, scene_r.width(), y)
            line.setPen(pen)
            line.setZValue(26)   # below marks (z=28) and cursors (z=30)
            self.addItem(line)
            self._find_hit_items.append(line)

    def _dim_brush_if_follow(self, brush: QBrush, merge_key: str) -> QBrush:
        """Dim segments of other tasks when one task is locked in core view."""
        if (self._view_mode != "core" or not self._locked_task
                or self._locked_task == merge_key):
            return brush
        c = brush.color()
        return QBrush(QColor(c.red(), c.green(), c.blue(), 45))

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

    def set_migrated_only_filter(self, enabled: bool) -> None:
        """When enabled, show only tasks that ran on 2+ cores."""
        enabled = bool(enabled)
        if enabled == self._migrated_only_filter:
            return
        self._migrated_only_filter = enabled
        if enabled:
            self._heatmap_filter_mks = None
        self.rebuild()

    def set_heatmap_task_filter(self, merge_keys: Optional[set]) -> None:
        """Show only tasks that migrated in a heatmap drill-down selection."""
        mks = set(merge_keys) if merge_keys else None
        if mks == self._heatmap_filter_mks:
            return
        self._heatmap_filter_mks = mks
        if mks:
            self._migrated_only_filter = False
            # Expand only cores that contain a filtered task so core view
            # draws task sub-rows instead of heavy per-core summary bars.
            tr = self._trace
            if tr is not None:
                for core in tr.core_names:
                    self._core_expanded[core] = any(
                        _task_merge_key(t) in mks
                        for t in tr.core_task_order.get(core, []))
        self.rebuild()

    def set_timescale_per_px_default(self, v: float) -> None:
        """Change the maximum zoom-in limit (in trace-native time-units/px) and rebuild if needed."""
        # Accept any positive value; do not apply a unit-dependent hard range here
        # because the value is already in trace-native units (ns, us, or ms) and
        # a limit of 0.5 makes no sense for us/ms traces (0.5 us/px = 500 ns/px).
        self._timescale_per_px_default = max(1e-9, v)
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
        # Clamp: don't zoom in past _timescale_per_px_default (2 ns/px in trace
        # units, scaled by set_trace) or zoom out past fit-to-view level.
        # _timescale_per_px_default is always <= _timescale_per_px_fit after
        # set_trace() rescales it, so max(default, min(val, fit)) is correct.
        new_val = max(self._timescale_per_px_default,
                      min(new_val, self._timescale_per_px_fit))
        if new_val == self._timescale_per_px:
            return  # already at limit - skip expensive rebuild
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

    def task_orth_scene_coord(self, task_key: str) -> Optional[float]:
        """Return the centre orthogonal scene coordinate of *task_key*'s row/column.

        Horizontal mode: centre Y of the task row.
        Vertical mode:   centre X of the task column.

        Works in both task and core view modes.  In core view, if the task's
        parent core is collapsed (so the task has no dedicated sub-row/col),
        returns the centre of the core's summary row/column as the nearest
        visible representative.  Returns None if the trace is absent or the
        task key is not found at all.
        """
        if self._trace is None:
            return None
        trace = self._trace

        if self._view_mode == "task":
            task_rows = [t for t in trace.tasks if self._task_merge_key_matches_filter(t)]
            try:
                idx = task_rows.index(task_key)
            except ValueError:
                return None
            if self._horizontal:
                row_stride = self._row_height + self._row_gap
                return RULER_HEIGHT + idx * row_stride + self._row_height / 2
            else:
                col_w = max(self._row_height + self._row_gap, 26)
                return RULER_WIDTH + idx * col_w + col_w / 2

        # --- Core view mode -------------------------------------------
        core_names = trace.core_names
        core_tasks = trace.core_task_order
        if self._task_filter_q:
            _fcn, _fct = [], {}
            for _c in core_names:
                _ts = [t for t in core_tasks[_c] if self._task_raw_name_matches_filter(t)]
                if _ts:
                    _fcn.append(_c)
                    _fct[_c] = _ts
            core_names, core_tasks = _fcn, _fct

        if self._horizontal:
            row_stride = self._row_height + self._row_gap
            row_idx = 0
            for core in core_names:
                expanded = self._core_expanded.get(core, True)
                tasks = core_tasks.get(core, [])
                core_row = row_idx
                row_idx += 1  # core summary row
                if expanded:
                    for raw in tasks:
                        if _task_merge_key(raw) == task_key:
                            return RULER_HEIGHT + row_idx * row_stride + self._row_height / 2
                        row_idx += 1
                else:
                    # Collapsed: task not visible as a sub-row; return core centre
                    for raw in tasks:
                        if _task_merge_key(raw) == task_key:
                            return RULER_HEIGHT + core_row * row_stride + self._row_height / 2
        else:
            col_w = max(self._row_height + self._row_gap, 26)
            col_idx = 0
            for core in core_names:
                expanded = self._core_expanded.get(core, True)
                tasks = core_tasks.get(core, [])
                core_col = col_idx
                col_idx += 1  # core summary column
                if expanded:
                    for raw in tasks:
                        if _task_merge_key(raw) == task_key:
                            return RULER_WIDTH + col_idx * col_w + col_w / 2
                        col_idx += 1
                else:
                    for raw in tasks:
                        if _task_merge_key(raw) == task_key:
                            return RULER_WIDTH + core_col * col_w + col_w / 2
        return None

    def task_orth_scene_span(self, task_key: str,
                             core_name: Optional[str] = None) -> Optional[Tuple[float, float]]:
        """Return the visible orthogonal span of *task_key*'s row/column.

        Horizontal mode: ``(top_y, bottom_y)`` of the target row.
        Vertical mode:   ``(left_x, right_x)`` of the target column.

        In core view, ``core_name`` is used to select the exact core-task row/
        column when available; otherwise the first matching task or collapsed
        core summary span is returned.
        """
        if self._trace is None:
            return None
        trace = self._trace

        if self._view_mode == "task":
            task_rows = [t for t in trace.tasks if self._task_merge_key_matches_filter(t)]
            try:
                idx = task_rows.index(task_key)
            except ValueError:
                return None
            if self._horizontal:
                row_stride = self._row_height + self._row_gap
                top = RULER_HEIGHT + idx * row_stride
                return (top, top + self._row_height)
            col_w = max(self._row_height + self._row_gap, 26)
            left = RULER_WIDTH + idx * col_w
            return (left, left + col_w)

        core_names = trace.core_names
        core_tasks = trace.core_task_order
        if self._task_filter_q:
            _fcn, _fct = [], {}
            for _c in core_names:
                _ts = [t for t in core_tasks[_c] if self._task_raw_name_matches_filter(t)]
                if _ts:
                    _fcn.append(_c)
                    _fct[_c] = _ts
            core_names, core_tasks = _fcn, _fct

        if self._horizontal:
            row_stride = self._row_height + self._row_gap
            row_idx = 0
            fallback: Optional[Tuple[float, float]] = None
            for core in core_names:
                expanded = self._core_expanded.get(core, True)
                tasks = core_tasks.get(core, [])
                core_row = row_idx
                row_idx += 1
                if expanded:
                    for raw in tasks:
                        if _task_merge_key(raw) == task_key:
                            top = RULER_HEIGHT + row_idx * row_stride
                            span = (top, top + self._row_height)
                            if core_name is not None and core == core_name:
                                return span
                            if fallback is None:
                                fallback = span
                        row_idx += 1
                else:
                    for raw in tasks:
                        if _task_merge_key(raw) == task_key:
                            top = RULER_HEIGHT + core_row * row_stride
                            span = (top, top + self._row_height)
                            if core_name is not None and core == core_name:
                                return span
                            if fallback is None:
                                fallback = span
                            break
            return fallback

        col_w = max(self._row_height + self._row_gap, 26)
        col_idx = 0
        fallback = None
        for core in core_names:
            expanded = self._core_expanded.get(core, True)
            tasks = core_tasks.get(core, [])
            core_col = col_idx
            col_idx += 1
            if expanded:
                for raw in tasks:
                    if _task_merge_key(raw) == task_key:
                        left = RULER_WIDTH + col_idx * col_w
                        span = (left, left + col_w)
                        if core_name is not None and core == core_name:
                            return span
                        if fallback is None:
                            fallback = span
                    col_idx += 1
            else:
                for raw in tasks:
                    if _task_merge_key(raw) == task_key:
                        left = RULER_WIDTH + core_col * col_w
                        span = (left, left + col_w)
                        if core_name is not None and core == core_name:
                            return span
                        if fallback is None:
                            fallback = span
                        break
        return fallback

    def interval_orth_scene_span(self, interval_id: str) -> Optional[Tuple[float, float]]:
        """Return the visible orthogonal span of an interval row (task view, horizontal)."""
        if self._trace is None or self._view_mode != "task" or not self._show_sti:
            return None
        iid = str(interval_id)
        try:
            idx = self._trace.interval_ids.index(iid)
        except ValueError:
            return None
        if not self._horizontal:
            return None
        task_rows = [t for t in self._trace.tasks if self._task_merge_key_matches_filter(t)]
        sti_rows = list(self._trace.sti_channels)
        if self._task_filter_q:
            sti_rows = [c for c in sti_rows if self._sti_channel_matches_filter(c)]
        row_stride = self._row_height + self._row_gap
        y_top = RULER_HEIGHT + len(task_rows) * row_stride
        for ch in sti_rows:
            h = (self._sti_waveform_h_val if ch in self._sti_expanded
                 else self._sti_row_h_val)
            y_top += h + self._row_gap
        y_top += idx * row_stride
        return (y_top, y_top + self._row_height)

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
        _safe_scene_remove_items(self, self._hover_overlay_items)
        self._hover_overlay_items = []

    @staticmethod
    def _segment_lock_key(seg: TaskSegment) -> tuple:
        return (_task_merge_key(seg.task), seg.start, seg.end, seg.core)

    def _is_segment_locked(self, seg: TaskSegment) -> bool:
        return self._locked_segment_key == self._segment_lock_key(seg)

    def _is_task_lock_active(self, task_key: str) -> bool:
        return self._locked_segment_key is None and self._locked_task == task_key

    def set_highlighted_task(self, task_name: Optional[str],
                             locked: bool = False,
                             core_name: Optional[str] = None,
                             ref_ns: Optional[int] = None) -> None:
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
            self._locked_core  = None
            self._locked_ns    = None
            self._locked_segment_key = None
            self._highlighted_interval = None
            self._highlighted_interval_mark_ns = None
            self._hovered_task = None
            self.highlight_changed.emit(None, False)
            self.rebuild()
        elif locked:
            self._remove_hover_overlay()
            self._locked_task  = task_name
            self._locked_core  = core_name
            self._locked_ns    = ref_ns
            self._locked_segment_key = None
            self._highlighted_interval = None
            self._highlighted_interval_mark_ns = None
            self._hovered_task = None
            self.highlight_changed.emit(task_name, True)
            self.rebuild()
        else:
            # Hover: update overlay only - no rebuild
            self._remove_hover_overlay()
            self._hovered_task = task_name
            self._apply_hover_overlay(task_name)
            self.highlight_changed.emit(self._locked_task,
                                        self._locked_task is not None)

    def set_highlighted_segment(self, seg: Optional[TaskSegment]) -> None:
        """Lock highlight to one exact segment bar (not the whole task)."""
        self._highlighted_interval = None
        self._highlighted_interval_mark_ns = None
        if seg is None:
            self.set_highlighted_task(None)
            return
        self._remove_hover_overlay()
        self._locked_task = _task_merge_key(seg.task)
        self._locked_core = seg.core
        self._locked_ns = seg.start
        self._locked_segment_key = self._segment_lock_key(seg)
        self._hovered_task = None
        self.highlight_changed.emit(self._locked_task, True)
        self.rebuild()

    def set_highlighted_interval(self, inst: Optional["IntervalInstance"],
                                 mark_ns: Optional[int] = None) -> None:
        """Highlight one interval instance row (statistics plot drill-down)."""
        if inst is None:
            if self._highlighted_interval is None:
                return
            self._highlighted_interval = None
            self._highlighted_interval_mark_ns = None
            self.rebuild()
            return
        self._remove_hover_overlay()
        self._locked_task = None
        self._locked_core = None
        self._locked_ns = None
        self._locked_segment_key = None
        self._hovered_task = None
        self._highlighted_interval = inst
        self._highlighted_interval_mark_ns = mark_ns if mark_ns is not None else inst.stop_ns
        self.highlight_changed.emit(None, False)
        self.rebuild()

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
    # Mouse-hover indicator (ghost line)
    # ------------------------------------------------------------------

    def _draw_hover_line(self) -> None:
        """Draw a thin dashed ghost line at self._hover_ns with a time label."""
        if self._trace is None or self._hover_ns is None:
            _safe_scene_remove_items(self, self._hover_items)
            self._hover_items.clear()
            if self._hover_line_ns is not None:
                self._hover_line_ns = None
                self.hover_changed.emit()
            return
        if self._hover_ns == self._hover_line_ns:
            return
        _safe_scene_remove_items(self, self._hover_items)
        self._hover_items.clear()
        self._hover_line_ns = self._hover_ns
        self.hover_changed.emit()
        scene_r = self.sceneRect()
        _views  = self.views()
        try:
            _scene_top  = _views[0].mapToScene(QPoint(0, 0)).y()  if _views else 0.0
            _scene_left = _views[0].mapToScene(QPoint(0, 0)).x()  if _views else 0.0
        except RuntimeError:
            _scene_top = _scene_left = 0.0
        font = _monospace_font(max(8, self._font_size - 1))
        fm   = QFontMetrics(font)
        t_str = _format_time(self._hover_ns, self._trace.time_scale, decimals=3)
        tw = fm.horizontalAdvance(t_str) + 8
        th = fm.height()
        if self._is_dark_ui:
            line_col = QColor(255, 255, 255, 80)
            lbl_bg   = QColor(40, 90, 200, 170)
            lbl_txt  = QColor("#AAC8FF")
        else:
            line_col = QColor(0, 102, 204, 200)
            lbl_bg   = QColor(0, 102, 204, 230)
            lbl_txt  = QColor("#FFFFFF")
        hover_pen = QPen(line_col, 1.2 if not self._is_dark_ui else 1.0, Qt.DashLine)
        hover_pen.setDashPattern([3, 3])
        if self._horizontal:
            x = self._label_width + self._ns_to_px(self._hover_ns)
            line = QGraphicsLineItem(x, 0, x, scene_r.height())
            line.setPen(hover_pen)
            line.setZValue(25)
            self.addItem(line)
            self._hover_items.append(line)
            # Time label centred on x, pinned near the bottom of the ruler
            lbl_x = min(x - tw / 2, scene_r.width() - tw - 4)
            lbl_x = max(self._label_width + 2, lbl_x)
            lbl_y = _scene_top + RULER_HEIGHT - th - 4
            bg = self.addRect(
                QRectF(lbl_x, lbl_y, tw, th + 2),
                QPen(Qt.NoPen), QBrush(lbl_bg))
            bg.setZValue(26)
            lbl = self.addSimpleText(t_str, font)
            lbl.setBrush(QBrush(lbl_txt))
            lbl.setZValue(27)
            lbl.setPos(lbl_x + 4, lbl_y + 1)
            self._hover_items.extend([bg, lbl])
        else:
            label_row_h = self._label_width
            y = label_row_h + self._ns_to_px(self._hover_ns)
            line = QGraphicsLineItem(0, y, scene_r.width(), y)
            line.setPen(hover_pen)
            line.setZValue(25)
            self.addItem(line)
            self._hover_items.append(line)
            # Time label to the right of the ruler, centred vertically on y
            lbl_x = _scene_left + RULER_WIDTH + 4
            lbl_y = y - (th + 2) / 2
            bg = self.addRect(
                QRectF(lbl_x, lbl_y, tw, th + 2),
                QPen(Qt.NoPen), QBrush(lbl_bg))
            bg.setZValue(26)
            lbl = self.addSimpleText(t_str, font)
            lbl.setBrush(QBrush(lbl_txt))
            lbl.setZValue(27)
            lbl.setPos(lbl_x + 4, lbl_y + 1)
            self._hover_items.extend([bg, lbl])

    def clear_hover_line(self) -> None:
        """Remove the hover ghost line from the scene."""
        if not self._hover_items and self._hover_line_ns is None:
            self._hover_ns = None
            return
        _safe_scene_remove_items(self, self._hover_items)
        self._hover_items.clear()
        self._hover_ns = None
        self._hover_line_ns = None
        self.hover_changed.emit()

    # ------------------------------------------------------------------
    # Draw cursor overlay
    # ------------------------------------------------------------------

    def _draw_cursors(self) -> None:
        _safe_scene_remove_items(self, self._cursor_items)
        self._cursor_items.clear()

        # Purge any cursor-label entries that were appended to _frozen_top_items
        # by the previous _draw_cursors() call.  This is only needed on direct
        # calls (e.g. cursor drag); rebuild() already resets _frozen_top_items.
        if self._cursor_frozen_top_set:
            self._frozen_top_items = [e for e in self._frozen_top_items
                                      if e[0] not in self._cursor_frozen_top_set]
            self._cursor_frozen_top_set = set()
        if self._cursor_frozen_left_set:
            self._frozen_items = [e for e in self._frozen_items
                                  if e[0] not in self._cursor_frozen_left_set]
            self._cursor_frozen_left_set = set()

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
        cursor_palette = _cursor_colors(self._is_dark_ui)

        for order, (orig_idx, ns) in enumerate(sorted_cursors):
            color = QColor(cursor_palette[orig_idx % len(cursor_palette)])
            pen   = QPen(color, 1.2, Qt.DashLine)

            if self._horizontal:
                x = self._label_width + self._ns_to_px(ns)
                line = QGraphicsLineItem(x, 0, x, scene_r.height())
                line.setPen(pen)
                line.setZValue(30)
                self.addItem(line)
                self._cursor_items.append(line)

                t_str = _format_time(ns, self._trace.time_scale, decimals=3)
                lbl = self.addSimpleText(f"C{orig_idx+1}: {t_str}", font_big)
                lbl.setBrush(QBrush(QColor("#000000")))
                lbl.setZValue(32)
                tw = fm_bold.horizontalAdvance(lbl.text())
                th = fm_bold.height()
                lbl_x = min(x + 3, scene_r.width() - tw - 4)
                _orig_y = 2 + (orig_idx + 1) * (th + 2)
                lbl_y   = _scene_top + _orig_y
                bg = self.addRect(
                    QRectF(0, 0, tw + 4, th + 2),
                    QPen(Qt.NoPen),
                    QBrush(color),
                )
                bg.setZValue(31)
                bg.setPos(lbl_x - 2, lbl_y - 1)
                lbl.setPos(lbl_x, lbl_y)
                self._cursor_items.extend([bg, lbl])
                # Register label + background as y-frozen so _reposition_frozen_top
                # keeps them in the ruler area regardless of vertical scroll.
                self._frozen_top_items.append((bg, _orig_y - 1))
                self._frozen_top_items.append((lbl, _orig_y))
                self._cursor_frozen_top_set.update({bg, lbl})

                if order > 0:
                    prev_ns = sorted_cursors[order - 1][1]
                    delta   = abs(ns - prev_ns)
                    d_str   = f"Δ {_format_time(delta, self._trace.time_scale, decimals=3)}"
                    mid_x   = self._label_width + self._ns_to_px((ns + prev_ns) // 2)
                    d_lbl   = self.addSimpleText(d_str, font)
                    d_w     = QFontMetrics(font).horizontalAdvance(d_str)
                    d_lbl.setBrush(QBrush(QColor("#000000")))
                    d_lbl.setZValue(32)
                    bg_rect = self.addRect(
                        QRectF(mid_x - d_w / 2 - 3, RULER_HEIGHT + 4,
                               d_w + 6, QFontMetrics(font).height() + 4),
                        QPen(Qt.NoPen),
                        QBrush(color),
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

                t_str = _format_time(ns, self._trace.time_scale, decimals=3)
                lbl = self.addSimpleText(f"C{orig_idx+1}: {t_str}", font_big)
                lbl.setBrush(QBrush(QColor("#000000")))
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
                    QBrush(color),
                )
                bg.setZValue(31)
                bg.setPos(lbl_x - 2, lbl_y - 1)
                lbl.setPos(lbl_x, lbl_y)
                self._cursor_items.extend([bg, lbl])
                # Keep vertical-mode cursor labels frozen at viewport-left.
                self._frozen_items.append((bg, _left_pad - 2))
                self._frozen_items.append((lbl, _left_pad))
                self._cursor_frozen_left_set.update({bg, lbl})

                if order > 0:
                    prev_ns = sorted_cursors[order - 1][1]
                    delta   = abs(ns - prev_ns)
                    d_str   = f"Δ {_format_time(delta, self._trace.time_scale, decimals=3)}"
                    mid_y   = label_row_h + self._ns_to_px((ns + prev_ns) // 2)
                    d_lbl   = self.addSimpleText(d_str, font)
                    dh      = QFontMetrics(font).height()
                    d_lbl.setBrush(QBrush(QColor("#000000")))
                    d_lbl.setZValue(32)
                    bg_rect = self.addRect(
                        QRectF(RULER_WIDTH + 4, mid_y - dh / 2 - 2,
                               QFontMetrics(font).horizontalAdvance(d_str) + 6, dh + 4),
                        QPen(Qt.NoPen), QBrush(color)
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
            # No attached view yet (e.g. during unit tests) - use full range.
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
        # keep +/-inf so the first rebuild always builds all rows.
        if self._skip_orth_culling or vp_rect.width() <= 1 or vp_rect.height() <= 1:
            self._skip_orth_culling = False
            self._vp_scene_orth_lo = -1e18
            self._vp_scene_orth_hi = +1e18
        else:
            _row_stride = self._row_height + self._row_gap
            if self._horizontal:
                _orth_extent = max(_row_stride, vp_rect.height())
            else:
                _orth_extent = max(_row_stride, vp_rect.width())
            _visible_rows = max(1, int(_orth_extent / _row_stride))
            _min_rows, _mult = _orth_cull_params(len(self._trace.tasks))
            _buf_rows = max(
                _min_rows,
                int(_visible_rows * _mult),
            )
            _ORTH_BUF = _row_stride * _buf_rows
            self._vp_orth_buf = _ORTH_BUF
            if self._horizontal:
                vy_lo = view.mapToScene(vp_rect.topLeft()).y()
                vy_hi = view.mapToScene(vp_rect.bottomLeft()).y()
            else:
                vy_lo = view.mapToScene(vp_rect.topLeft()).x()
                vy_hi = view.mapToScene(vp_rect.topRight()).x()
            self._vp_scene_orth_lo = vy_lo - _ORTH_BUF
            self._vp_scene_orth_hi = vy_hi + _ORTH_BUF

    def rebuild(self) -> None:
        if self._rebuild_suspend > 0:
            return
        self._update_viewport_bounds()
        self.clear()
        self._cursor_items = []
        self._mark_items = []
        self._frozen_items = []
        self._frozen_top_items = []
        self._cursor_frozen_top_set = set()
        self._cursor_frozen_left_set = set()
        self._mark_frozen_top_set = set()
        self._mark_frozen_left_set = set()
        self._task_row_rects = {}
        self._hover_overlay_items = []   # clear() removed them from the scene
        self._hover_items = []             # clear() removed them from the scene
        self._hover_line_ns = None
        self._find_hit_items = []
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
        self._draw_marks()
        self._draw_find_markers()
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
        tr = self._trace
        if self._heatmap_filter_mks is not None:
            if merge_key not in self._heatmap_filter_mks:
                return False
        elif tr is not None and self._migrated_only_filter:
            if not _is_migrated_task(tr, merge_key):
                return False
        if not self._task_filter_q:
            return True
        if tr is None:
            return True
        raw = tr.task_repr.get(merge_key, merge_key)
        disp = _task_display_name(raw)
        q = self._task_filter_q
        return (q in merge_key.lower()) or (q in raw.lower()) or (q in disp.lower())

    def _task_raw_name_matches_filter(self, raw_name: str) -> bool:
        if not self._task_filter_q:
            return True
        mk = _task_merge_key(raw_name)
        disp = _task_display_name(raw_name)
        q = self._task_filter_q
        return (q in mk.lower()) or (q in raw_name.lower()) or (q in disp.lower())

    def _core_view_task_filter_active(self) -> bool:
        """True when core view should hide non-matching tasks (heatmap, migrated, search)."""
        return (self._heatmap_filter_mks is not None
                or self._migrated_only_filter
                or bool(self._task_filter_q))

    def _filtered_core_view_tasks(self) -> Tuple[List[str], Dict[str, List[str]]]:
        """Core names and per-core task lists (no TICK) after active filters."""
        trace = self._trace
        core_names = list(trace.core_names)
        core_tasks = {
            c: [t for t in trace.core_task_order.get(c, [])
                if _parse_task_name(t)[2] != "TICK"]
            for c in core_names
        }
        if not self._core_view_task_filter_active():
            return core_names, core_tasks
        out_names: List[str] = []
        out_tasks: Dict[str, List[str]] = {}
        for core in core_names:
            tasks = [t for t in core_tasks[core]
                     if self._task_merge_key_matches_filter(_task_merge_key(t))]
            if tasks:
                out_names.append(core)
                out_tasks[core] = tasks
        return out_names, out_tasks

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
        return self._seg_lod_for_task(_task_merge_key("TICK"))

    def _add_tick_ruler_band(
        self,
        horiz: bool,
        vp: ViewClipParams,
        timeline_span: float,
    ) -> bool:
        """Draw TICK marks on the ruler band. Returns True when anything was drawn."""
        trace = self._trace
        _tick_mk = _task_merge_key("TICK")
        _tick_segs = trace.seg_map_by_merge_key.get(_tick_mk, [])
        _tick_sti = trace.tick_sti_times
        if not _tick_segs and not _tick_sti:
            return False
        _tick_no_pen = QPen(Qt.NoPen)
        _sti_tick_brush = QBrush(QColor("#E8C84A"))
        seg_data: list = []
        xs: list = []

        if horiz:
            band_y = RULER_HEIGHT - 10
            band_h = 8.0
            mark_thin = 2.0
            band_rect = QRectF(vp.offset, band_y, timeline_span, band_h)
            batch_z = 12
            freeze_top = True

            def _mark_rect(t_coord: float) -> QRectF:
                return QRectF(t_coord - 0.5, band_y, mark_thin, band_h)
        else:
            band_x = RULER_WIDTH - 18
            band_w = 14.0
            mark_thin = 2.0
            band_rect = QRectF(band_x, vp.offset, band_w, timeline_span)
            batch_z = 37
            freeze_top = False

            def _mark_rect(t_coord: float) -> QRectF:
                return QRectF(band_x, t_coord - 0.5, band_w, mark_thin)

        def _time_coord(t_ns: int) -> float:
            return vp.offset + (t_ns - vp.time_min) * vp.px_per_ns

        if _tick_segs:
            for _seg in _visible_segs(self._seg_lod_for_tick(), vp):
                tc = _time_coord(_seg.start)
                seg_data.append((
                    _mark_rect(tc),
                    _task_brush(_seg.task), _tick_no_pen, _seg,
                ))
                xs.append((tc - 0.5, tc + 1.5, len(seg_data) - 1))
        if _tick_sti:
            _lo = max(0, bisect_left(_tick_sti, vp.ns_lo) - 1)
            _hi = min(len(_tick_sti), bisect_right(_tick_sti, vp.ns_hi) + 1)
            for _ts in _tick_sti[_lo:_hi]:
                seg_data.append((
                    _mark_rect(_time_coord(_ts)),
                    _sti_tick_brush, _tick_no_pen, None,
                ))

        batch = _BatchRowItem(
            band_rect, seg_data, trace.time_scale, xs=xs,
            time_min=trace.time_min)
        batch.setZValue(batch_z)
        self.addItem(batch)
        if freeze_top:
            self._frozen_top_items.append((batch, 0))
        else:
            self._frozen_items.append((batch, 0))
        return True

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
        interval_rows = trace.interval_ids if self._show_sti else []
        n_task = len(task_rows)
        n_sti  = len(sti_rows)
        n_interval = len(interval_rows)
        total_rows = n_task + n_sti + n_interval
        if total_rows == 0:
            return

        time_span  = trace.time_max - trace.time_min
        timeline_w = time_span / self._timescale_per_px
        _sti_total_h = sum(
            (self._sti_waveform_h_val if c in self._sti_expanded else self._sti_row_h_val) + self._row_gap
            for c in sti_rows)
        _sti_total_h += n_interval * (self._row_height + self._row_gap)
        total_h = RULER_HEIGHT + n_task * (self._row_height + self._row_gap) + _sti_total_h
        total_w = self._label_width + timeline_w
        self.setSceneRect(0, 0, total_w, total_h)

        # --- Background & ruler ------------------------------------------
        _ruler_bg = self.addRect(QRectF(0, 0, total_w, RULER_HEIGHT),
                               QPen(Qt.NoPen), QBrush(self._c_ruler_bg))
        _ruler_bg.setZValue(10)   # above task rows (z=0-2) when frozen at top
        self._frozen_top_items.append((_ruler_bg, 0))
        _lbg = self.addRect(QRectF(0, 0, self._label_width, total_h),
                           QPen(Qt.NoPen), QBrush(self._c_label_bg))
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

        self._add_tick_ruler_band(True, vp, timeline_w)

        # Shared colors/pens/brushes hoisted out of loops
        _bg_even     = QBrush(self._c_row_even)
        _bg_odd      = QBrush(self._c_row_odd)
        _sep_pen     = QPen(self._c_sep, 0.5)
        _lbl_color   = self._c_label_txt
        _stripe_rows: list = []   # accumulated by task + STI loops -> one _RowStripesItem

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
            is_hl = self._is_task_lock_active(task)
            disp      = _task_display_name(raw)
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

            lbl_color    = _complementary_color(row_color) if is_hl else _lbl_color
            lbl_font     = _monospace_font(self._font_size, QFont.Bold) if is_hl else font
            _lbl_avail_w = max(0, lw - 4 - 4)   # left=4, right margin=4
            _lbl_fm      = QFontMetrics(lbl_font) if is_hl else fm
            _lbl_elided  = _lbl_fm.elidedText(disp, Qt.ElideRight, _lbl_avail_w)
            lbl = self.addSimpleText(_lbl_elided, lbl_font)
            lbl.setBrush(QBrush(lbl_color))
            lbl.setPos(4, y_ctr - fm.height() / 2)
            lbl.setZValue(37)
            self._frozen_items.append((lbl, 4))

            pen_hl     = _complementary_pen(row_color)
            seg_data: list = []
            xs:      list = []
            for i_s, seg in enumerate(_visible_segs(self._seg_lod_for_task(task), vp)):
                x1 = lw + (seg.start - _time_min) * _px_per_ns
                x2 = lw + (seg.end   - _time_min) * _px_per_ns
                w  = x2 - x1 if x2 - x1 >= MIN_SEG_WIDTH else MIN_SEG_WIDTH
                _seg_locked = self._is_segment_locked(seg)
                _seg_br     = _blended_brush(seg.task, seg.core)
                _seg_rect   = QRectF(x1, y_top + 1, w, self._row_height - 2)
                seg_data.append((
                    _seg_rect,
                    _seg_br,
                    pen_hl if (is_hl or _seg_locked) else _blended_pen_dark(seg.task, seg.core),
                    seg,
                ))
                xs.append((x1, x1 + w, i_s))
            _inline_labels = len(seg_data) <= 48
            batch = _BatchRowItem(
                QRectF(lw, y_top, timeline_w, self._row_height),
                seg_data, trace.time_scale,
                label_font=font_inline if _inline_labels else None,
                label_fm=fm_inline if _inline_labels else None,
                label_text=disp if _inline_labels else "",
                trace=trace,
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
        # One row per STI channel: collapsed shows diamond markers, expanded
        # shows a step-chart waveform.  Row heights vary per channel.
        _sti_bg = QBrush(self._c_sti_bg)
        _sti_y  = RULER_HEIGHT + n_task * (self._row_height + self._row_gap)
        for channel in sti_rows:
            is_exp     = channel in self._sti_expanded
            expandable = _is_tag_sti_channel(channel)
            row_h  = self._sti_waveform_h_val if is_exp else self._sti_row_h_val
            y_top  = _sti_y
            y_ctr  = y_top + row_h / 2
            _stripe_rows.append((y_top, row_h, self._row_gap, _sti_bg, None))
            # Label with expand/collapse indicator (only for expandable channels)
            if expandable:
                _ind  = "▼" if is_exp else "▶"
                _ltxt = fm.elidedText(f"{_ind} {channel}", Qt.ElideRight, max(0, lw - 4 - 4))
            else:
                _ltxt = fm.elidedText(channel, Qt.ElideRight, max(0, lw - 4 - 4))
            lbl_bg = _StiLabelItem(QRectF(0, y_top, lw, row_h), channel, self,
                                   expandable=expandable)
            lbl_bg.setZValue(36)
            self.addItem(lbl_bg)
            self._frozen_items.append((lbl_bg, 0))
            lbl = self.addSimpleText(_ltxt, font)
            lbl.setBrush(QBrush(self._c_sti_lbl))
            lbl.setPos(4, y_ctr - fm.height() / 2)
            lbl.setZValue(37)
            self._frozen_items.append((lbl, 4))
            _sti_evs_h  = trace.sti_events_by_target.get(channel, [])
            _sti_stts_h = trace.sti_starts_by_target.get(channel, [])
            if is_exp:
                # Expanded: full step-chart waveform (all events, no viewport clip)
                _wf = _BatchStiWaveformItem(
                    QRectF(lw, y_top, timeline_w, row_h),
                    _sti_evs_h, trace.time_scale,
                    time_min=_time_min, px_per_ns=_px_per_ns, x_offset=lw,
                    log_scale=self._sti_log_scale,
                    line_style=self._sti_line_style)
                _wf.setZValue(2)
                self.addItem(_wf)
            else:
                # Collapsed: marker diamonds inside the viewport clip window
                _sti_evs_clipped = self._clip_sti_events(
                    _sti_evs_h, _sti_stts_h, _vp_ns_lo, _vp_ns_hi)
                _sti_markers = [
                    (lw + (ev.time - _time_min) * _px_per_ns, _sti_color(ev.note), ev)
                    for ev in _sti_evs_clipped
                ]
                _sti_item = _BatchStiItem(
                    QRectF(lw, y_top, timeline_w, row_h),
                    _sti_markers, trace.time_scale, horizontal=True, axis=y_ctr,
                    time_min=trace.time_min)
                _sti_item.setZValue(2)
                self.addItem(_sti_item)
            _sti_y += row_h + self._row_gap

        for interval_id in interval_rows:
            row_h = self._row_height
            y_top = _sti_y
            y_ctr = y_top + row_h / 2
            _stripe_rows.append((y_top, row_h, self._row_gap, _sti_bg, None))
            lbl_bg = _StiLabelItem(QRectF(0, y_top, lw, row_h), f"interval:{interval_id}", self,
                                   expandable=False)
            lbl_bg.setZValue(36)
            self.addItem(lbl_bg)
            self._frozen_items.append((lbl_bg, 0))
            color = QColor(_interval_color(interval_id))
            swatch = self.addRect(QRectF(4, y_ctr - 5, 10, 10),
                                   QPen(color.darker(140), 1.0), QBrush(color))
            swatch.setZValue(37)
            self._frozen_items.append((swatch, 4))
            _lbl = fm.elidedText(f"Interval {interval_id}", Qt.ElideRight, max(0, lw - 18 - 4))
            lbl = self.addSimpleText(_lbl, font)
            lbl.setBrush(QBrush(self._c_sti_lbl))
            lbl.setPos(18, y_ctr - fm.height() / 2)
            lbl.setZValue(37)
            self._frozen_items.append((lbl, 18))
            pen = QPen(color.darker(145), 1.25)
            insts = trace.interval_instances_by_id.get(interval_id, [])
            _interval_bars = _interval_bars_for_viewport(
                insts, _time_min, _px_per_ns, lw, _vp_ns_lo, _vp_ns_hi)
            _interval_ticks = _interval_marker_ticks_for_viewport(
                trace, interval_id, _time_min, _px_per_ns, lw, _vp_ns_lo, _vp_ns_hi)
            _hi_times = None
            _hi = self._highlighted_interval
            if _hi is not None and str(_hi.id) == str(interval_id):
                _mark = self._highlighted_interval_mark_ns or _hi.stop_ns
                _hi_times = sorted({_hi.start_ns, _hi.stop_ns, _mark})
            if _interval_bars or _interval_ticks or _hi_times:
                _bar_y = y_top + 1
                _bar_h = row_h - 2
                _bar_item = _IntervalRowBarsItem(
                    QRectF(lw, _bar_y, timeline_w, _bar_h),
                    _interval_bars, _interval_ticks, _bar_y, _bar_h, color, pen,
                    _time_min, _px_per_ns, lw,
                    highlight_times=_hi_times, dark_ui=self._is_dark_ui)
                _bar_item.setZValue(2)
                self.addItem(_bar_item)
            _sti_y += row_h + self._row_gap

        if _stripe_rows:
            _stripes = _RowStripesItem(
                QRectF(0, RULER_HEIGHT, total_w, total_h - RULER_HEIGHT),
                _stripe_rows, lw, total_w)
            _stripes.setZValue(0)
            self.addItem(_stripes)

        # --- Frozen label column header ----------------------------------
        # Drawn last so it sits on top of all other frozen items (z=38-39).
        _has_tick_h = bool(trace.seg_map_by_merge_key.get(_task_merge_key("TICK"), []))
        corner = self.addRect(QRectF(0, 0, lw, RULER_HEIGHT),
                              QPen(Qt.NoPen), QBrush(self._c_corner_bg))
        corner.setZValue(38)
        _hdr_band_h = RULER_HEIGHT - (10 if _has_tick_h else 0)
        hdr = self.addSimpleText("Task / TaskID", font)
        hdr.setBrush(QBrush(self._c_header_txt))
        hdr.setPos(4, _hdr_band_h / 2 - fm.height() / 2)
        hdr.setZValue(39)
        self._frozen_items.append((corner, 0))
        self._frozen_items.append((hdr, 4))
        self._frozen_top_items.append((corner, 0))
        self._frozen_top_items.append((hdr, hdr.pos().y()))
        if _has_tick_h:
            _tick_font = _monospace_font(max(6, self._font_size - 2))
            _tick_fm   = QFontMetrics(_tick_font)
            _tick_hdr = self.addSimpleText("TICK", _tick_font)
            _tick_hdr.setBrush(QBrush(QColor("#E8C84A")))
            _tick_hdr.setPos(4, RULER_HEIGHT - 10 + (10 - _tick_fm.height()) / 2)
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
        # STI columns may be wider when expanded
        total_sti_w = sum(
            (self._sti_waveform_h_val
             if (_is_tag_sti_channel(c) and c in self._sti_expanded)
             else col_w)
            for c in sti_cols
        )
        total_w     = RULER_WIDTH + n_task * col_w + total_sti_w
        total_h     = label_row_h + timeline_h
        self.setSceneRect(0, 0, total_w, total_h)

        # --- Ruler column (left side): frozen to left edge on X scroll ------
        _ruler_col_bg = self.addRect(QRectF(0, 0, RULER_WIDTH, total_h),
                                     QPen(Qt.NoPen), QBrush(self._c_ruler_bg))
        _ruler_col_bg.setZValue(35)  # above cursor lines (z=30-32)
        self._frozen_items.append((_ruler_col_bg, 0))

        # --- Label row (top): frozen to top edge on Y scroll ---------------
        _label_row_bg = self.addRect(QRectF(0, 0, total_w, label_row_h),
                                     QPen(Qt.NoPen), QBrush(self._c_label_bg))
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

        _tick_mk = _task_merge_key("TICK")
        _has_tick_v = self._add_tick_ruler_band(False, vp, timeline_h)

        # --- Task columns ------------------------------------------------
        _bg_even   = QBrush(self._c_row_even)
        _bg_odd    = QBrush(self._c_row_odd)
        _lbl_color = self._c_label_txt
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
            is_hl  = self._is_task_lock_active(task)
            disp      = _task_display_name(raw)
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

            lbl_color    = _complementary_color(col_color) if is_hl else _lbl_color
            lbl_font     = _monospace_font(self._font_size, QFont.Bold) if is_hl else font
            _lbl_avail_v = max(0, label_row_h - 14)
            _lbl_fm_v    = QFontMetrics(lbl_font) if is_hl else fm
            _lbl_disp_v  = _lbl_fm_v.elidedText(disp, Qt.ElideRight, _lbl_avail_v)
            lbl = _make_rotated_label(self, _lbl_disp_v, lbl_font, lbl_color,
                                      x_left + col_w / 2,
                                      label_row_h - LABEL_BOTTOM_MARGIN, 37)
            self._frozen_top_items.append((lbl, lbl.pos().y()))

            pen_hl      = _complementary_pen(col_color)
            seg_data: list = []
            xs:      list = []
            for i_s, seg in enumerate(_visible_segs(self._seg_lod_for_task(task), vp)):
                y1 = label_row_h + (seg.start - _time_min) * _px_per_ns
                y2 = label_row_h + (seg.end   - _time_min) * _px_per_ns
                h  = y2 - y1 if y2 - y1 >= MIN_SEG_WIDTH else MIN_SEG_WIDTH
                _seg_locked = self._is_segment_locked(seg)
                _seg_br     = _blended_brush(seg.task, seg.core)
                _seg_rect   = QRectF(x_left + 1, y1, col_w - 2, h)
                seg_data.append((
                    _seg_rect,
                    _seg_br,
                    pen_hl if (is_hl or _seg_locked) else _blended_pen_dark(seg.task, seg.core),
                    seg,
                ))
                xs.append((y1, y1 + h, i_s))
            _inline_labels = len(seg_data) <= 48
            batch = _BatchRowItem(
                QRectF(x_left, label_row_h, col_w, timeline_h),
                seg_data, trace.time_scale,
                label_font=font_inline if _inline_labels else None,
                label_fm=fm_inline if _inline_labels else None,
                label_text=disp if _inline_labels else "",
                trace=trace,
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
        _sti_x_acc = RULER_WIDTH + n_task * col_w
        for sti_idx, channel in enumerate(sti_cols):
            col_idx    = n_task + sti_idx
            expandable = _is_tag_sti_channel(channel)
            is_exp     = expandable and channel in self._sti_expanded
            cw_sti     = self._sti_waveform_h_val if is_exp else col_w
            x_left     = _sti_x_acc
            x_ctr      = x_left + cw_sti / 2
            self.addRect(QRectF(x_left, label_row_h, cw_sti, timeline_h),
                         QPen(Qt.NoPen), QBrush(self._c_sti_bg)).setZValue(0)

            # Clickable column header (expands/collapses waveform)
            lbl_bg = _StiLabelItem(QRectF(x_left, 0, cw_sti, label_row_h),
                                   channel, self, expandable=expandable)
            lbl_bg.setZValue(36)
            self.addItem(lbl_bg)
            self._frozen_top_items.append((lbl_bg, 0))

            # Rotated label with optional expand indicator
            _ind_txt  = ("▼ " if is_exp else "▶ ") if expandable else ""
            _lbl_avail_v = max(0, label_row_h - 14)
            _lbl_txt  = fm.elidedText(_ind_txt + channel, Qt.ElideRight, _lbl_avail_v)
            lbl = _make_rotated_label(self, _lbl_txt, font, self._c_sti_lbl,
                                      x_ctr,
                                      label_row_h - LABEL_BOTTOM_MARGIN, 37)
            self._frozen_top_items.append((lbl, lbl.pos().y()))

            _sti_evs_v  = trace.sti_events_by_target.get(channel, [])
            _sti_stts_v = trace.sti_starts_by_target.get(channel, [])
            if is_exp:
                # Expanded: full step-chart waveform (time on Y, values on X)
                _sti_evs_clipped_v = self._clip_sti_events(
                    _sti_evs_v, _sti_stts_v, _vp_ns_lo, _vp_ns_hi)
                _wf_col = _BatchStiWaveformColumnItem(
                    QRectF(x_left, label_row_h, cw_sti, timeline_h),
                    _sti_evs_clipped_v, _sti_evs_v,
                    trace.time_scale, trace.time_min, _px_per_ns, label_row_h,
                    log_scale=self._sti_log_scale,
                    line_style=self._sti_line_style)
                _wf_col.setZValue(2)
                self.addItem(_wf_col)
            else:
                _sti_evs_clipped_v = self._clip_sti_events(
                    _sti_evs_v, _sti_stts_v, _vp_ns_lo, _vp_ns_hi)
                _sti_markers_v = [
                    (label_row_h + (ev.time - _time_min) * _px_per_ns, _sti_color(ev.note), ev)
                    for ev in _sti_evs_clipped_v
                ]
                _sti_item_v = _BatchStiItem(
                    QRectF(x_left, label_row_h, cw_sti, timeline_h),
                    _sti_markers_v, trace.time_scale, horizontal=False, axis=x_ctr,
                    time_min=trace.time_min)
                _sti_item_v.setZValue(2)
                self.addItem(_sti_item_v)

            _sti_x_acc += cw_sti

        # --- Corner: ruler-column x label-row intersection ---------------
        _vt_corner_rect = self.addRect(QRectF(0, 0, RULER_WIDTH, label_row_h),
                                       QPen(Qt.NoPen), QBrush(self._c_corner_bg))
        _vt_corner_rect.setZValue(40)   # above ruler (35-37) and label row (10-37)
        self._frozen_items.append((_vt_corner_rect, 0))
        self._frozen_top_items.append((_vt_corner_rect, 0))
        if _has_tick_v:
            _vband_cx  = (RULER_WIDTH - 18) + 14 / 2
            _tick_vlbl = _make_rotated_label(self, "TICK", font, QColor("#E8C84A"),
                                             _vband_cx,
                                             label_row_h - LABEL_BOTTOM_MARGIN, 41)
            self._frozen_items.append((_tick_vlbl, _tick_vlbl.pos().x()))
            self._frozen_top_items.append((_tick_vlbl, _tick_vlbl.pos().y()))

    # ------------------------------------------------------------------
    # Core view builders
    # ------------------------------------------------------------------

    def _build_horizontal_core(self) -> None:
        """Horizontal core view: expandable cores -> per-task sub-rows."""
        trace   = self._trace
        font    = _monospace_font(self._font_size)
        font_sm = _monospace_font(max(6, self._font_size - 1))
        fm      = QFontMetrics(font)
        fm_sm   = QFontMetrics(font_sm)

        # Use pre-built core data cached at parse time (O(1), no segment iteration)
        core_names           = trace.core_names
        core_segs            = trace.core_segs
        sti_rows             = trace.sti_channels if self._show_sti else []
        if self._task_filter_q:
            sti_rows = [c for c in sti_rows if self._sti_channel_matches_filter(c)]

        core_names, core_tasks = self._filtered_core_view_tasks()
        _skip_core_summary_segs = self._core_view_task_filter_active()

        # TICK is a global event - shown as a sticky first row above all cores.
        _has_tick = (bool(trace.seg_map_by_merge_key.get(_task_merge_key("TICK"), []))
                     or bool(trace.tick_sti_times))

        def _row_count(c: str) -> int:
            return 1 + (len(core_tasks[c]) if self._core_expanded.get(c, True) else 0)

        total_rows = sum(_row_count(c) for c in core_names) + len(sti_rows)
        if total_rows == 0:
            return

        time_span  = trace.time_max - trace.time_min
        timeline_w = time_span / self._timescale_per_px
        _n_non_sti = sum(_row_count(c) for c in core_names)
        _sti_total_h = sum(
            (self._sti_waveform_h_val if c in self._sti_expanded else self._sti_row_h_val) + self._row_gap
            for c in sti_rows)
        total_h    = RULER_HEIGHT + _n_non_sti * (self._row_height + self._row_gap) + _sti_total_h
        total_w    = self._label_width + timeline_w
        self.setSceneRect(0, 0, total_w, total_h)

        # --- Background & ruler ------------------------------------------
        _ruler_bg = self.addRect(QRectF(0, 0, total_w, RULER_HEIGHT),
                               QPen(Qt.NoPen), QBrush(self._c_ruler_bg))
        _ruler_bg.setZValue(10)
        self._frozen_top_items.append((_ruler_bg, 0))
        _lbg = self.addRect(QRectF(0, 0, self._label_width, total_h),
                           QPen(Qt.NoPen), QBrush(self._c_label_bg))
        _lbg.setZValue(35)   # must be above cursor lines (z=30-32)
        self._frozen_items.append((_lbg, 0))

        # Grid-only ruler (not frozen - grid lines stay at their scene positions).
        _ruler_grid = _RulerItem(trace, self._timescale_per_px, total_w, total_h,
                                   font, trace.time_scale, self._show_grid,
                                   horiz=True, axis_offset=self._label_width,
                                   draw_header=False)
        _ruler_grid.setZValue(0.5)
        self.addItem(_ruler_grid)
        # Header-only ruler (frozen by Y - always visible at viewport top).
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
        self._add_tick_ruler_band(True, vp, timeline_w)

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
                             QPen(Qt.NoPen), QBrush(self._c_core_sum_bg)).setZValue(0)
                self.addLine(0, y_top + self._row_height + self._row_gap - 1,
                             total_w, y_top + self._row_height + self._row_gap - 1,
                             QPen(self._c_core_sep, 0.8)).setZValue(0.5)

                hdr_item = _CoreHeaderItem(
                    QRectF(0, y_top, lw, self._row_height), core, self)
                hdr_item.setBrush(QBrush(self._c_core_hdr_bg))
                hdr_item.setPen(QPen(Qt.NoPen))
                hdr_item.setZValue(36)
                self.addItem(hdr_item)
                self._frozen_items.append((hdr_item, 0))

                arrow   = "▼" if expanded else "▶"
                arrow_w = fm.horizontalAdvance("▼")
                arr_txt = self.addSimpleText(arrow, font)
                arr_txt.setBrush(QBrush(self._c_core_arrow))
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
                lbl_item.setBrush(QBrush(self._c_core_lbl))
                lbl_item.setPos(arrow_w + 20, y_ctr - fm.height() / 2)
                lbl_item.setZValue(37)
                lbl_item.setAcceptedMouseButtons(Qt.NoButton)
                lbl_item.setAcceptHoverEvents(False)
                self._frozen_items.append((lbl_item, arrow_w + 20))

                # --- Core utilisation % (IDLE excluded) ---
                _total_ns  = trace.time_max - trace.time_min
                _active_ns = sum(s.end - s.start for s in segs
                                 if (_tn := _parse_task_name(s.task)[2]) != "TICK"
                                 and not _is_idle_task_name(_tn))
                _util_pct  = 100.0 * _active_ns / _total_ns if _total_ns > 0 else 0.0
                _util_item = self.addSimpleText(f"{_util_pct:.0f}%", font_sm)
                _util_item.setBrush(QBrush(QColor("#77BB77")))
                _util_item.setPos(lw - _util_w + 4, y_ctr - fm.height() / 2)
                _util_item.setZValue(37)
                _util_item.setAcceptedMouseButtons(Qt.NoButton)
                _util_item.setAcceptHoverEvents(False)
                self._frozen_items.append((_util_item, lw - _util_w + 4))

                if not _skip_core_summary_segs:
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
                        trace=trace,
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
                _tmk   = _task_merge_key(task_name)
                is_hl  = self._is_task_lock_active(_tmk)

                sub_bg = self._c_core_sub_even if sub_idx % 2 == 0 else self._c_core_sub_odd
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
                             QPen(self._c_core_sub_sep, 0.5)).setZValue(0.5)

                stripe = self.addRect(QRectF(26, y_top2 + 3, 3, self._row_height - 6),
                                      QPen(Qt.NoPen), QBrush(_row_color))
                stripe.setZValue(36)
                self._frozen_items.append((stripe, 0))

                # Clickable label background for sub-task row
                disp      = _task_display_name(task_name)
                sub_lbl_bg = _TaskLabelItem(
                    QRectF(0, y_top2, lw, self._row_height), _tmk, self,
                    tooltip_text=disp, core_name=core)
                sub_lbl_bg.setZValue(36)
                self.addItem(sub_lbl_bg)
                self._frozen_items.append((sub_lbl_bg, 0))
                lbl_color = _complementary_color(_row_color) if is_hl else self._c_core_sub_lbl
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

                pen_hl       = _complementary_pen(_row_color)
                _task_pen_cs = _task_pen_dark(task_name)
                _task_br_cs  = self._dim_brush_if_follow(_task_brush(task_name), _tmk)
                seg_data: list = []
                xs:       list = []
                for i_s, seg in enumerate(_visible_segs(
                        self._seg_lod_for_core_task(core, task_name), vp)):
                    x1 = lw + (seg.start - _time_min) * _px_per_ns
                    x2 = lw + (seg.end   - _time_min) * _px_per_ns
                    w  = x2 - x1 if x2 - x1 >= MIN_SEG_WIDTH else MIN_SEG_WIDTH
                    _seg_locked = self._is_segment_locked(seg)
                    seg_data.append((
                        QRectF(x1, y_top2 + 1, w, self._row_height - 2),
                        _task_br_cs,
                        pen_hl if (is_hl or _seg_locked) else _task_pen_cs,
                        seg,
                    ))
                    xs.append((x1, x1 + w, i_s))
                batch = _BatchRowItem(
                    QRectF(lw, y_top2, timeline_w, self._row_height),
                    seg_data, trace.time_scale,
                    label_font=font_sm, label_fm=fm_sm, label_text=disp,
                    trace=trace,
                    xs=xs, time_min=trace.time_min, timescale_per_px=self._timescale_per_px)
                batch.setZValue(1)
                self.addItem(batch)

        # --- STI rows ---------------------------------------------------
        _sti_y = RULER_HEIGHT + row_idx * (self._row_height + self._row_gap)
        for channel in sti_rows:
            is_exp     = channel in self._sti_expanded
            expandable = _is_tag_sti_channel(channel)
            row_h  = self._sti_waveform_h_val if is_exp else self._sti_row_h_val
            y_top  = _sti_y
            y_ctr  = y_top + row_h / 2
            self.addRect(QRectF(lw, y_top, timeline_w, row_h),
                         QPen(Qt.NoPen), QBrush(self._c_sti_bg)).setZValue(0)
            if expandable:
                _ind  = "▼" if is_exp else "▶"
                _ltxt = fm.elidedText(f"{_ind} {channel}", Qt.ElideRight, max(0, lw - 4 - 4))
            else:
                _ltxt = fm.elidedText(channel, Qt.ElideRight, max(0, lw - 4 - 4))
            lbl_bg = _StiLabelItem(QRectF(0, y_top, lw, row_h), channel, self,
                                   expandable=expandable)
            lbl_bg.setZValue(36)
            self.addItem(lbl_bg)
            self._frozen_items.append((lbl_bg, 0))
            lbl = self.addSimpleText(_ltxt, font)
            lbl.setBrush(QBrush(self._c_sti_lbl))
            lbl.setPos(4, y_ctr - fm.height() / 2)
            lbl.setZValue(37)
            self._frozen_items.append((lbl, 4))
            _sti_evs_ch  = trace.sti_events_by_target.get(channel, [])
            _sti_stts_ch = trace.sti_starts_by_target.get(channel, [])
            if is_exp:
                _wf = _BatchStiWaveformItem(
                    QRectF(lw, y_top, timeline_w, row_h),
                    _sti_evs_ch, trace.time_scale,
                    time_min=_time_min, px_per_ns=_px_per_ns, x_offset=lw,
                    log_scale=self._sti_log_scale,
                    line_style=self._sti_line_style)
                _wf.setZValue(2)
                self.addItem(_wf)
            else:
                _sti_evs_clipped = self._clip_sti_events(
                    _sti_evs_ch, _sti_stts_ch, _vp_ns_lo, _vp_ns_hi)
                _sti_markers_ch = [
                    (lw + (ev.time - _time_min) * _px_per_ns, _sti_color(ev.note), ev)
                    for ev in _sti_evs_clipped
                ]
                _sti_item_ch = _BatchStiItem(
                    QRectF(lw, y_top, timeline_w, row_h),
                    _sti_markers_ch, trace.time_scale, horizontal=True, axis=y_ctr,
                    time_min=trace.time_min)
                _sti_item_ch.setZValue(2)
                self.addItem(_sti_item_ch)
            _sti_y += row_h + self._row_gap

        corner = self.addRect(QRectF(0, 0, lw, RULER_HEIGHT),
                              QPen(Qt.NoPen), QBrush(self._c_corner_bg))
        corner.setZValue(38)
        _upper_h = RULER_HEIGHT - (10 if _has_tick else 0)
        hdr_lbl = self.addSimpleText("Core / Task", font)
        hdr_lbl.setBrush(QBrush(self._c_header_txt))
        hdr_lbl.setPos(4, _upper_h / 2 - fm.height() / 2)
        hdr_lbl.setZValue(39)
        self._frozen_items.append((corner, 0))
        self._frozen_items.append((hdr_lbl, 4))
        self._frozen_top_items.append((corner, 0))
        self._frozen_top_items.append((hdr_lbl, hdr_lbl.pos().y()))

    def _build_vertical_core(self) -> None:
        """Vertical core view: expandable core columns -> per-task sub-columns."""
        trace   = self._trace
        font    = _monospace_font(self._font_size)
        font_sm = _monospace_font(max(6, self._font_size - 1))
        fm_sm   = QFontMetrics(font_sm)

        # Use pre-built core data cached at parse time (O(1), no segment iteration)
        core_names           = trace.core_names
        sti_cols             = trace.sti_channels if self._show_sti else []
        if self._task_filter_q:
            sti_cols = [c for c in sti_cols if self._sti_channel_matches_filter(c)]

        core_names, core_tasks = self._filtered_core_view_tasks()
        _skip_core_summary_segs = self._core_view_task_filter_active()

        # TICK is a global event - shown as a band in the ruler column.
        _has_tick = (bool(trace.seg_map_by_merge_key.get(_task_merge_key("TICK"), []))
                     or bool(trace.tick_sti_times))

        def _col_count(c: str) -> int:
            return 1 + (len(core_tasks[c]) if self._core_expanded.get(c, True) else 0)

        _core_col_count = sum(_col_count(c) for c in core_names)
        total_cols = _core_col_count + len(sti_cols)
        if total_cols == 0:
            return

        col_w       = max(self._row_height + self._row_gap, 26)
        label_row_h = self._label_width
        time_span   = trace.time_max - trace.time_min
        timeline_h  = time_span / self._timescale_per_px
        # STI columns may be wider when expanded
        total_sti_w = sum(
            (self._sti_waveform_h_val
             if (_is_tag_sti_channel(c) and c in self._sti_expanded)
             else col_w)
            for c in sti_cols
        )
        total_w     = RULER_WIDTH + _core_col_count * col_w + total_sti_w
        total_h     = label_row_h + timeline_h
        self.setSceneRect(0, 0, total_w, total_h)

        # --- Ruler column (left side): frozen to left edge on X scroll ------
        _ruler_col_bg_c = self.addRect(QRectF(0, 0, RULER_WIDTH, total_h),
                                       QPen(Qt.NoPen), QBrush(self._c_ruler_bg))
        _ruler_col_bg_c.setZValue(35)
        self._frozen_items.append((_ruler_col_bg_c, 0))

        # --- Label row (top): frozen to top edge on Y scroll ---------------
        _label_row_bg_c = self.addRect(QRectF(0, 0, total_w, label_row_h),
                                       QPen(Qt.NoPen), QBrush(self._c_label_bg))
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
        self._add_tick_ruler_band(False, vp, timeline_h)

        col_idx = 0

        # --- Core columns ------------------------------------------------
        # Each core gets one summary column (always visible) plus optional
        # per-task sub-columns that appear when the core is expanded.
        for core in core_names:
            expanded = self._core_expanded.get(core, True)
            tasks    = core_tasks[core]

            x_left = RULER_WIDTH + col_idx * col_w
            col_idx += 1   # advance immediately, independent of viewport cull

            _core_in_vp = not (x_left + col_w < self._vp_scene_orth_lo
                               or x_left > self._vp_scene_orth_hi)
            if _core_in_vp:
                self.addRect(QRectF(x_left, label_row_h, col_w, timeline_h),
                             QPen(Qt.NoPen), QBrush(self._c_core_sum_bg)).setZValue(0)

                # Clickable core column header (v/> expand toggle)
                hdr_item = _CoreHeaderItem(
                    QRectF(x_left, 0, col_w, label_row_h), core, self)
                hdr_item.setBrush(QBrush(self._c_core_hdr_bg))
                hdr_item.setPen(QPen(Qt.NoPen))
                hdr_item.setZValue(36)
                self.addItem(hdr_item)
                self._frozen_top_items.append((hdr_item, 0))

                # Arrow + core name (rotated -90 like task view labels)
                arrow     = "▼" if expanded else "▶"
                arr_label = arrow + " " + core
                _lbl_avail_c = max(0, label_row_h - 14)
                arr_label = QFontMetrics(font).elidedText(arr_label, Qt.ElideRight, _lbl_avail_c)
                arr_txt = _make_rotated_label(self, arr_label, font, self._c_core_arrow,
                                              x_left + col_w / 2,
                                              label_row_h - LABEL_BOTTOM_MARGIN, 37)
                self._frozen_top_items.append((arr_txt, arr_txt.pos().y()))

                if not _skip_core_summary_segs:
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
                        trace=trace,
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

                sub_bg  = self._c_core_sub_even if sub_idx % 2 == 0 else self._c_core_sub_odd
                self.addRect(QRectF(x_left2, label_row_h, col_w, timeline_h),
                             QPen(Qt.NoPen), QBrush(sub_bg)).setZValue(0)

                _tmk       = _task_merge_key(task_name)
                is_hl      = self._is_task_lock_active(_tmk)
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
                disp      = _task_display_name(task_name)
                sub_lbl_bg = _TaskLabelItem(
                    QRectF(x_left2, 0, col_w, label_row_h), _tmk, self,
                    tooltip_text=disp, core_name=core)
                sub_lbl_bg.setZValue(36)
                self.addItem(sub_lbl_bg)
                self._frozen_top_items.append((sub_lbl_bg, 0))
                lbl_color = _complementary_color(_row_color) if is_hl else self._c_core_sub_lbl
                lbl_fnt   = _monospace_font(self._font_size,
                                            QFont.Bold) if is_hl else font
                t_lbl = _make_rotated_label(self, disp, lbl_fnt, lbl_color,
                                            x_left2 + col_w / 2,
                                            label_row_h - LABEL_BOTTOM_MARGIN, 37)
                self._frozen_top_items.append((t_lbl, t_lbl.pos().y()))

                pen_hl       = _complementary_pen(_row_color)
                _task_pen_cs = _task_pen_dark(task_name)
                _task_br_cs  = self._dim_brush_if_follow(_task_brush(task_name), _tmk)
                seg_data: list = []
                xs:       list = []
                for i_s, seg in enumerate(_visible_segs(
                        self._seg_lod_for_core_task(core, task_name), vp)):
                    y1 = label_row_h + (seg.start - _time_min) * _px_per_ns
                    y2 = label_row_h + (seg.end   - _time_min) * _px_per_ns
                    h  = y2 - y1 if y2 - y1 >= MIN_SEG_WIDTH else MIN_SEG_WIDTH
                    _seg_locked = self._is_segment_locked(seg)
                    seg_data.append((
                        QRectF(x_left2 + 1, y1, col_w - 2, h),
                        _task_br_cs,
                        pen_hl if (is_hl or _seg_locked) else _task_pen_cs,
                        seg,
                    ))
                    xs.append((y1, y1 + h, i_s))
                batch = _BatchRowItem(
                    QRectF(x_left2, label_row_h, col_w, timeline_h),
                    seg_data, trace.time_scale,
                    label_font=font_sm, label_fm=fm_sm, label_text=disp,
                    trace=trace,
                    xs=xs, time_min=trace.time_min, timescale_per_px=self._timescale_per_px)
                batch.setZValue(1)
                self.addItem(batch)

        # --- STI columns ------------------------------------------------
        _sti_x_acc_vc = RULER_WIDTH + _core_col_count * col_w
        for channel in sti_cols:
            expandable = _is_tag_sti_channel(channel)
            is_exp     = expandable and channel in self._sti_expanded
            cw_sti_vc  = self._sti_waveform_h_val if is_exp else col_w
            x_left     = _sti_x_acc_vc
            x_ctr_vc   = x_left + cw_sti_vc / 2
            self.addRect(QRectF(x_left, label_row_h, cw_sti_vc, timeline_h),
                         QPen(Qt.NoPen), QBrush(self._c_sti_bg)).setZValue(0)

            # Clickable column header (expands/collapses waveform)
            lbl_bg_vc = _StiLabelItem(QRectF(x_left, 0, cw_sti_vc, label_row_h),
                                      channel, self, expandable=expandable)
            lbl_bg_vc.setZValue(36)
            self.addItem(lbl_bg_vc)
            self._frozen_top_items.append((lbl_bg_vc, 0))

            # Rotated label with optional expand indicator
            _ind_txt_vc  = ("v " if is_exp else "> ") if expandable else ""
            _lbl_avail_vc = max(0, label_row_h - 14)
            _lbl_txt_vc  = QFontMetrics(font).elidedText(
                _ind_txt_vc + channel, Qt.ElideRight, _lbl_avail_vc)
            lbl = _make_rotated_label(self, _lbl_txt_vc, font, self._c_sti_lbl,
                                      x_ctr_vc,
                                      label_row_h - LABEL_BOTTOM_MARGIN, 37)
            self._frozen_top_items.append((lbl, lbl.pos().y()))

            _sti_evs_vc  = trace.sti_events_by_target.get(channel, [])
            _sti_stts_vc = trace.sti_starts_by_target.get(channel, [])
            if is_exp:
                # Expanded: full step-chart waveform (time on Y, values on X)
                _sti_evs_clipped_vc = self._clip_sti_events(
                    _sti_evs_vc, _sti_stts_vc, _vp_ns_lo, _vp_ns_hi)
                _wf_col_vc = _BatchStiWaveformColumnItem(
                    QRectF(x_left, label_row_h, cw_sti_vc, timeline_h),
                    _sti_evs_clipped_vc, _sti_evs_vc,
                    trace.time_scale, trace.time_min, _px_per_ns, label_row_h,
                    log_scale=self._sti_log_scale,
                    line_style=self._sti_line_style)
                _wf_col_vc.setZValue(2)
                self.addItem(_wf_col_vc)
            else:
                _sti_evs_clipped_vc = self._clip_sti_events(
                    _sti_evs_vc, _sti_stts_vc, _vp_ns_lo, _vp_ns_hi)
                _sti_mrk_vc = [
                    (label_row_h + (ev.time - _time_min) * _px_per_ns, _sti_color(ev.note), ev)
                    for ev in _sti_evs_clipped_vc
                ]
                _sti_itm_vc = _BatchStiItem(
                    QRectF(x_left, label_row_h, cw_sti_vc, timeline_h),
                    _sti_mrk_vc, trace.time_scale, horizontal=False, axis=x_ctr_vc,
                    time_min=trace.time_min)
                _sti_itm_vc.setZValue(2)
                self.addItem(_sti_itm_vc)

            col_idx += 1
            _sti_x_acc_vc += cw_sti_vc

        # --- Corner: ruler-column x label-row intersection ---------------
        _vc_corner = self.addRect(QRectF(0, 0, RULER_WIDTH, label_row_h),
                                  QPen(Qt.NoPen), QBrush(self._c_corner_bg))
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
    horiz : True  -> time on X axis (horizontal layout)
             False -> time on Y axis (vertical layout)
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
        step_px  = step_ns / max(npp, 1e-12)
        draw_grid_lines = (
            self._draw_grid and self._show_grid
            and step_px >= _MIN_GRID_SPACING_PX
        )
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
                    if draw_grid_lines:
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
                    if draw_grid_lines:
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

class _IntervalRowBarsItem(QGraphicsItem):
    """Paints all interval bars for one row in a single paint() pass.

    Replaces O(n_intervals) individual QGraphicsRectItems with one
    item per interval row, avoiding multi-second freezes in scene.clear() when
    zooming after many back-to-back intervals are visible.
    """

    __slots__ = ('_bounds', '_bars', '_ticks', '_bar_y', '_bar_h', '_color', '_outline_pen',
                 '_time_min', '_px_per_ns', '_label_width', '_highlight_times', '_dark_ui')

    def __init__(
        self,
        bounding_rect: QRectF,
        bars: list,
        ticks: list,
        bar_y: float,
        bar_h: float,
        color: QColor,
        outline_pen: QPen,
        time_min: int,
        px_per_ns: float,
        label_width: float,
        highlight_times: Optional[list] = None,
        dark_ui: bool = True,
    ) -> None:
        super().__init__()
        self._bounds = bounding_rect
        self._bars = bars          # [(x, w, start_ns, stop_ns), ...] sorted by start x
        self._ticks = ticks        # [(scene_x, is_start), ...]
        self._bar_y = bar_y
        self._bar_h = bar_h
        self._color = color
        self._outline_pen = outline_pen
        self._time_min = time_min
        self._px_per_ns = px_per_ns
        self._label_width = label_width
        self._highlight_times = highlight_times
        self._dark_ui = dark_ui
        self.setFlag(QGraphicsItem.ItemUsesExtendedStyleOption, True)

    def boundingRect(self) -> QRectF:
        return self._bounds

    def paint(self, painter, option, widget=None) -> None:
        bars = self._bars
        ticks = self._ticks
        hi_times = self._highlight_times
        if not bars and not ticks and not hi_times:
            return
        exposed = option.exposedRect
        exp_left = exposed.left()
        exp_right = exposed.right()
        y = self._bar_y
        h = self._bar_h
        pen = self._outline_pen

        if bars:
            lo, hi = 0, len(bars)
            while lo < hi:
                mid = (lo + hi) >> 1
                x, w, _s0, _s1 = bars[mid]
                if x + w < exp_left:
                    lo = mid + 1
                else:
                    hi = mid
            painter.setBrush(self._color)
            for i in range(lo, len(bars)):
                x, w, _start_ns, _stop_ns = bars[i]
                if x >= exp_right:
                    break
                cx = max(x, exp_left)
                cx2 = min(x + w, exp_right)
                cw = cx2 - cx
                if cw < _INTERVAL_MIN_PX:
                    continue
                painter.setPen(pen if cw >= 3.0 else Qt.NoPen)
                painter.drawRect(QRectF(cx, y, cw, h))
        _paint_interval_event_ticks(
            painter, ticks, y, h, self._color, exp_left, exp_right)
        if hi_times:
            _paint_interval_highlight_lines(
                painter, hi_times, y, h, self._time_min, self._label_width,
                self._px_per_ns, exp_left, exp_right, self._dark_ui)

class _RowStripesItem(QGraphicsItem):
    """Draws N row background rectangles and optional separator lines in one pass.

    Replaces 2xN individual QGraphicsRectItem/QGraphicsLineItem scene items with
    a single item, eliminating PyQt bridge-call overhead that accumulates during
    rebuild when many rows are visible simultaneously.

    rows: sequence of (y_top, row_h, gap, brush, sep_pen_or_None)
        sep_pen_or_None - QPen for a horizontal line at y = y_top+row_h+gap-1,
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

    Tier 1 - micro  (lod < _PAINT_LOD_MICRO = 0.12)
        Single tinted rectangle per row.  Used at far-out zoom where all
        segments are sub-pixel.  O(1) draw calls.

    Tier 2 - coarse (lod < _PAINT_LOD_COARSE = 0.45)
        Uses _coarse_data (segments merged within 6 px) via binary search
        on _coarse_xs to skip off-screen entries.  No pen outlines drawn.
        O(visible_merged) draw calls.

    Tier 3 - full detail
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
                 time_min: int = 0, timescale_per_px: float = 0.0,
                 trace: Optional["BtfTrace"] = None):
        super().__init__()
        self._bounding_rect = bounding_rect
        self._seg_data      = seg_data      # [(QRectF, QBrush, QPen, seg|None)]
        self._time_scale    = time_scale
        self._time_min      = time_min
        self._timescale_per_px     = timescale_per_px
        self._trace         = trace
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
        # Qt clips paint() to boundingRect(), so expand it to accommodate 10%
        # segment size growth when at least one segment is highlighted.
        # The enlarged rect is (ROW_HEIGHT+ROW_GAP)*1.10 in the relevant axis,
        # centred on the inner segment rect's midpoint.  Geometry per orientation:
        #   Horiz: inner rect height = ROW_HEIGHT-2, centre at row.y + ROW_HEIGHT/2
        #          -> protrusion above row.y  = _new_dim/2 - ROW_HEIGHT/2  = 3.3 px
        #   Vert:  inner rect width = col_w-2, centre at col.x + col_w/2
        #          where col_w = ROW_HEIGHT+ROW_GAP  -> protrusion = 1.3 px
        # Add 2 px for the 2.5-px pen half-width + rounding safety.
        _has_hl = any(p.widthF() > 2.0 for _, _, p, _ in seg_data) if seg_data else False
        if _has_hl:
            _slot    = ROW_HEIGHT + ROW_GAP  # 26 px
            _new_dim = _slot * 1.10          # 28.6 px
            if self._horiz:
                # Outer band height = ROW_HEIGHT; protrusion = (_new_dim - ROW_HEIGHT) / 2
                _hl_margin = (_new_dim - ROW_HEIGHT) / 2 + 2.0  # ~5.3 px
                self._bounding_rect = QRectF(
                    bounding_rect.x(), bounding_rect.y() - _hl_margin,
                    bounding_rect.width(), bounding_rect.height() + _hl_margin * 2)
            else:
                # Outer band width = col_w = _slot; protrusion = (_new_dim - _slot) / 2
                _hl_margin = (_new_dim - _slot) / 2 + 2.0  # ~3.3 px
                self._bounding_rect = QRectF(
                    bounding_rect.x() - _hl_margin, bounding_rect.y(),
                    bounding_rect.width() + _hl_margin * 2, bounding_rect.height())
        # Pre-compute coarse LOD segment list (merge segments within 6 scene-px)
        self._coarse_data_cache: Optional[list] = None
        horiz = self._horiz
        self._coarse_xs: Optional[list] = None

    def _get_coarse_data(self) -> list:
        if self._coarse_data_cache is None:
            self._coarse_data_cache = self._make_coarse_data()
            horiz = self._horiz
            self._coarse_xs = [
                (r.x(), r.x() + r.width()) if horiz else (r.y(), r.y() + r.height())
                for r, _, _, _ in self._coarse_data_cache
            ]
        return self._coarse_data_cache

    def _get_coarse_xs(self) -> list:
        self._get_coarse_data()
        return self._coarse_xs or []

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
            # Use pre-merged coarse_data.  rebuild() already clips to +/-1.5x
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
            for rect, brush, _, _seg in self._get_coarse_data():
                if brush is not last_brush:
                    painter.setBrush(brush)
                    last_brush = brush
                painter.drawRect(rect)
            if _rebase:
                painter.restore()
            painter.restore()
            return

        # ---- Tier 3: full detail ------------------------------------------------
        # rebuild() already pre-clips segments to +/-1.5x the viewport, so
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
        _horiz     = self._horiz
        for rect, brush, pen, _seg in seg_slice:
            if brush is not last_brush:
                painter.setBrush(brush)
                last_brush = brush
            if pen is not last_pen:
                painter.setPen(pen)
                last_pen = pen
            # Enlarge highlighted segments (pen width > 2.0) by 10% of the
            # full row slot (ROW_HEIGHT + ROW_GAP) so it visibly protrudes
            # past the row boundary into the inter-row gap.
            if pen.widthF() > 2.0:
                if _horiz:
                    _slot   = ROW_HEIGHT + ROW_GAP
                    _new_h  = _slot * 1.10
                    _orig_cy = rect.y() + rect.height() / 2
                    draw_rect = QRectF(rect.x(), _orig_cy - _new_h / 2,
                                       rect.width(), _new_h)
                else:
                    _slot   = ROW_HEIGHT + ROW_GAP
                    _new_w  = _slot * 1.10
                    _orig_cx = rect.x() + rect.width() / 2
                    draw_rect = QRectF(_orig_cx - _new_w / 2, rect.y(),
                                       _new_w, rect.height())
            else:
                draw_rect = rect
            painter.drawRect(draw_rect)
        if _rebase:
            painter.restore()
        # Inline text labels - second pass to minimise font/pen switches.
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
                           f"Duration: {_format_time(dur, self._time_scale)}")
                    tr = self._trace
                    if tr is not None:
                        prev, nxt, seg_idx, total = _seg_core_neighbors(tr, seg)
                        if seg_idx > 0:
                            tip += f"<br>Slice: #{seg_idx}/{total} on {seg.core}"
                        if prev is not None:
                            _, _, pnm = _parse_task_name(prev.task)
                            tip += (f"<br>← Prev on core: {_task_display_name(prev.task)} "
                                    f"({_format_time(prev.end, self._time_scale)})")
                        if nxt is not None:
                            tip += (f"<br>→ Next on core: {_task_display_name(nxt.task)} "
                                    f"({_format_time(nxt.start, self._time_scale)})")
                        if prev is not None:
                            gap = seg.start - prev.end
                            if gap > 0:
                                tip += f"<br>Gap before: {_format_time(gap, self._time_scale)}"
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
                 tooltip_text: str = "", core_name: Optional[str] = None):
        super().__init__(rect)
        self._task_name   = task_name
        self._tl_scene    = tl_scene
        self._tooltip_text = tooltip_text
        self._core_name = core_name
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
            self._tl_scene.set_highlighted_task(None)   # second click -> cancel lock
        else:
            self._tl_scene.set_highlighted_task(
                self._task_name, locked=True, core_name=self._core_name)
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
    """Clickable label area for a core row - toggles expand/collapse."""

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

class _StiLabelItem(QGraphicsRectItem):
    """Clickable label area for an STI channel row - toggles waveform expand/collapse.

    Only tag_event / tag[0-7]_event channels are *expandable*; for other channels
    the item still provides a consistent hit area but does nothing on click.
    """

    _HOVER_BRUSH = QBrush(QColor(100, 180, 255, 50))

    def __init__(self, rect: QRectF, channel: str, tl_scene, expandable: bool = True):
        super().__init__(rect)
        self._channel    = channel
        self._tl_scene   = tl_scene
        self._expandable = expandable
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setAcceptHoverEvents(True)
        if expandable:
            self.setCursor(Qt.PointingHandCursor)
        self.setPen(QPen(Qt.NoPen))
        self.setBrush(QBrush(Qt.transparent))

    def mousePressEvent(self, event):
        if self._expandable:
            self._tl_scene.toggle_sti_channel(self._channel)
        event.accept()

    def hoverEnterEvent(self, event):
        self.setBrush(self._HOVER_BRUSH)
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(Qt.transparent))
        self.update()
        super().hoverLeaveEvent(event)

class _BatchStiWaveformItem(QGraphicsItem):
    """Renders an expanded step-chart waveform for one STI channel.

    Numeric values are taken from ``StiEvent.note`` (falling back to
    ``StiEvent.event``).  Non-numeric notes are assigned a stable integer
    category index so that categorical channels still produce a readable chart.
    When *log_scale* is True the y-axis uses log2(1 + |value|) with the
    original sign preserved.
    """

    def __init__(self, bounding_rect: QRectF, events: list, time_scale: str,
                 time_min: int, px_per_ns: float, x_offset: float,
                 log_scale: bool = False, line_style: str = "step"):
        super().__init__()
        self._bounding_rect = bounding_rect
        self._events        = events      # all StiEvent objects for this channel
        self._time_scale    = time_scale
        self._time_min      = time_min
        self._px_per_ns     = px_per_ns
        self._x_offset      = x_offset
        self._log_scale     = log_scale
        self._line_style    = line_style  # "step" (hold) or "linear" (point-to-point)
        self._category_map: dict = {}     # note -> stable int (for categorical channels)
        self.setCacheMode(QGraphicsItem.NoCache)
        self.setAcceptHoverEvents(True)

    # ------------------------------------------------------------------ helpers
    def _ev_value(self, ev) -> float:
        """Return a numeric float for *ev*; categorical notes map to stable ints."""
        raw = ev.note or ev.event or ""
        try:
            return float(raw)
        except (ValueError, TypeError):
            pass
        if raw not in self._category_map:
            self._category_map[raw] = float(len(self._category_map))
        return self._category_map[raw]

    @staticmethod
    def _signed_log2(v: float) -> float:
        import math
        return math.copysign(math.log2(1.0 + abs(v)), v)

    # ------------------------------------------------------------------ Qt API
    def boundingRect(self) -> QRectF:
        return self._bounding_rect

    def paint(self, painter: QPainter, option, widget=None) -> None:
        if not self._events:
            return

        PAD        = 4
        rect       = self._bounding_rect
        chart_top  = rect.top()    + PAD
        chart_bot  = rect.bottom() - PAD
        chart_h    = chart_bot - chart_top
        if chart_h <= 0:
            return

        vals = [self._ev_value(ev) for ev in self._events]
        if self._log_scale:
            mapped = [self._signed_log2(v) for v in vals]
        else:
            mapped = list(vals)

        v_min = min(mapped)
        v_max = max(mapped)
        if v_min == v_max:
            v_min -= 1.0
            v_max += 1.0
        v_rng = v_max - v_min

        def val_to_y(m: float) -> float:
            return chart_bot - ((m - v_min) / v_rng) * chart_h

        def ev_to_x(ev) -> float:
            return self._x_offset + (ev.time - self._time_min) * self._px_per_ns

        painter.save()

        # Axis lines (top / bottom of chart area)
        _axis_pen = QPen(QColor(255, 255, 255, 28), 0.5, Qt.DashLine)
        painter.setPen(_axis_pen)
        painter.drawLine(QLineF(rect.left(), chart_top, rect.right(), chart_top))
        painter.drawLine(QLineF(rect.left(), chart_bot,  rect.right(), chart_bot))

        # Polyline: step-hold or direct point-to-point
        line_color = QColor("#5BC8FF")
        painter.setPen(QPen(line_color, 1.5))
        painter.setBrush(Qt.NoBrush)

        pts: list = []
        if self._line_style == "linear":
            for ev, m in zip(self._events, mapped):
                pts.append((ev_to_x(ev), val_to_y(m)))
        else:  # "step" (default): hold value until next event
            for ev, m in zip(self._events, mapped):
                x = ev_to_x(ev)
                y = val_to_y(m)
                if pts:
                    prev_x, prev_y = pts[-1]
                    pts.append((x, prev_y))   # horizontal leg of the step
                pts.append((x, y))

        if len(pts) >= 2:
            poly = QPolygonF([QPointF(px, py) for px, py in pts])
            painter.drawPolyline(poly)

        # Event dots
        dot_color = QColor("#80DFFF")
        painter.setPen(QPen(dot_color.darker(130), 0.5))
        painter.setBrush(QBrush(dot_color))
        for ev, m in zip(self._events, mapped):
            x = ev_to_x(ev)
            y = val_to_y(m)
            painter.drawEllipse(QPointF(x, y), 2.5, 2.5)

        painter.restore()

    def hoverMoveEvent(self, event) -> None:
        if not self._events:
            _get_popup().hide()
            super().hoverMoveEvent(event)
            return
        pos_x = event.pos().x()
        HIT   = 8    # px hit-zone half-width
        best_ev   = None
        best_dist = float('inf')
        for ev in self._events:
            x = self._x_offset + (ev.time - self._time_min) * self._px_per_ns
            d = abs(x - pos_x)
            if d < best_dist:
                best_dist = d
                best_ev   = ev
            if x > pos_x + HIT and best_dist <= HIT:
                break
        if best_ev is not None and best_dist <= HIT:
            tip = (f"<b>STI: {best_ev.note}</b><br>"
                   f"Time: {_format_time(best_ev.time, self._time_scale)}<br>"
                   f"Core: {best_ev.core}<br>"
                   f"Target: {best_ev.target}<br>"
                   f"Event: {best_ev.event}")
            _get_popup().show_at(event.screenPos(), tip)
        else:
            _get_popup().hide()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        _get_popup().hide()
        super().hoverLeaveEvent(event)

class _BatchStiWaveformColumnItem(QGraphicsItem):
    """Renders an expanded STI step-chart waveform inside a vertical COLUMN.

    Unlike _BatchStiWaveformItem (time on X, values on Y), this variant uses:
      - Y axis  -> time
      - X axis  -> numeric value

    Parameters
    ----------
    bounding_rect : QRectF   Full column area (x_left..x_right, y_offset..bottom)
    events        : list     Visible StiEvent objects for this channel
    all_events    : list     All StiEvent objects (used to compute stable value range)
    time_min      : int      Trace time_min (scene Y = y_offset + (t - time_min) * px_per_ns)
    px_per_ns     : float    Scene pixels per nanosecond (vertical axis)
    y_offset      : float    Scene Y coordinate of time=time_min
    log_scale     : bool     Use log2(1+|v|) mapping
    line_style    : str      "step" (hold) or "linear"
    """

    def __init__(self, bounding_rect: QRectF, events: list, all_events: list,
                 time_scale: str, time_min: int, px_per_ns: float, y_offset: float,
                 log_scale: bool = False, line_style: str = "linear"):
        super().__init__()
        self._bounding_rect = bounding_rect
        self._events        = events
        self._all_events    = all_events
        self._time_scale    = time_scale
        self._time_min      = time_min
        self._px_per_ns     = px_per_ns
        self._y_offset      = y_offset
        self._log_scale     = log_scale
        self._line_style    = line_style
        self._category_map: dict = {}
        self.setCacheMode(QGraphicsItem.NoCache)

    def _ev_value(self, ev) -> float:
        raw = ev.note or ev.event or ""
        try:
            return float(raw)
        except (ValueError, TypeError):
            pass
        if raw not in self._category_map:
            self._category_map[raw] = float(len(self._category_map))
        return self._category_map[raw]

    @staticmethod
    def _signed_log2(v: float) -> float:
        import math
        return math.copysign(math.log2(1.0 + abs(v)), v)

    def boundingRect(self) -> QRectF:
        return self._bounding_rect

    def paint(self, painter: QPainter, option, widget=None) -> None:
        if not self._events:
            return

        PAD         = 4
        rect        = self._bounding_rect
        chart_left  = rect.left()  + PAD
        chart_right = rect.right() - PAD
        chart_w     = chart_right - chart_left
        if chart_w <= 0:
            return

        # Compute value range from ALL events for stable scaling across zoom
        all_mapped = []
        for ev in self._all_events:
            v = self._ev_value(ev)
            m = self._signed_log2(v) if self._log_scale else v
            all_mapped.append(m)
        if not all_mapped:
            return
        v_min = min(all_mapped)
        v_max = max(all_mapped)
        if v_min == v_max:
            v_min -= 1.0
            v_max += 1.0
        v_rng = v_max - v_min

        def val_to_x(m: float) -> float:
            return chart_left + ((m - v_min) / v_rng) * chart_w

        def ev_to_y(ev) -> float:
            return self._y_offset + (ev.time - self._time_min) * self._px_per_ns

        painter.save()

        # Axis guide lines (left / right of chart area)
        _axis_pen = QPen(QColor(255, 255, 255, 28), 0.5, Qt.DashLine)
        painter.setPen(_axis_pen)
        painter.drawLine(QLineF(chart_left, rect.top(),    chart_left, rect.bottom()))
        painter.drawLine(QLineF(chart_right, rect.top(), chart_right, rect.bottom()))

        # Polyline
        line_color = QColor("#5BC8FF")
        painter.setPen(QPen(line_color, 1.5))
        painter.setBrush(Qt.NoBrush)

        pts: list = []
        for ev in self._events:
            v = self._ev_value(ev)
            m = self._signed_log2(v) if self._log_scale else v
            x = val_to_x(m)
            y = ev_to_y(ev)
            if self._line_style == "step" and pts:
                prev_x, prev_y = pts[-1]
                pts.append((prev_x, y))   # vertical leg: hold prev value in time
            pts.append((x, y))

        # Extend last point to bottom of bounding rect
        if pts:
            last_x, _ = pts[-1]
            pts.append((last_x, rect.bottom()))

        if len(pts) >= 2:
            poly = QPolygonF([QPointF(px, py) for px, py in pts])
            painter.drawPolyline(poly)

        # Event dots
        dot_color = QColor("#80DFFF")
        painter.setPen(QPen(dot_color.darker(130), 0.5))
        painter.setBrush(QBrush(dot_color))
        for ev in self._events:
            v = self._ev_value(ev)
            m = self._signed_log2(v) if self._log_scale else v
            x = val_to_x(m)
            y = ev_to_y(ev)
            painter.drawEllipse(QPointF(x, y), 2.5, 2.5)

        painter.restore()

# ===========================================================================
# Navigator Popup
# ===========================================================================

class _NavigatorPopup(QWidget):
    """260x130 thumbnail that shows the full trace with a viewport indicator.

    Painted entirely in Python and overlaid on the TimelineView viewport at
    the bottom-right corner.  The widget is mouse-transparent so it does not
    interfere with pan / zoom interaction.
    Appearance changes are animated with a 80 ms fade-in / 350 ms fade-out.
    """

    W: int = 260
    H: int = 130
    MARGIN: int = 8   # gap from the viewport edge (px)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedSize(self.W, self.H)
        self._pix: Optional[QPixmap] = None
        self.setVisible(False)

        # Opacity effect + animations
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._anim_in = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._anim_in.setDuration(80)
        self._anim_in.setStartValue(0.0)
        self._anim_in.setEndValue(1.0)
        self._anim_in.setEasingCurve(QEasingCurve.OutCubic)

        self._anim_out = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._anim_out.setDuration(350)
        self._anim_out.setStartValue(1.0)
        self._anim_out.setEndValue(0.0)
        self._anim_out.setEasingCurve(QEasingCurve.InCubic)
        self._anim_out.finished.connect(super().hide)

    def fade_in(self) -> None:
        """Make the popup visible with a fade-in animation."""
        self._anim_out.stop()
        self._opacity_effect.setOpacity(self._opacity_effect.opacity())
        self.reposition()
        super().show()
        self.raise_()
        self._anim_in.setStartValue(self._opacity_effect.opacity())
        self._anim_in.start()

    def fade_out(self) -> None:
        """Fade the popup out, then hide it."""
        if not self.isVisible():
            return
        self._anim_in.stop()
        self._anim_out.setStartValue(self._opacity_effect.opacity())
        self._anim_out.start()

    def reposition(self) -> None:
        """Pin to the bottom-right of the timeline canvas (inside scrollbars)."""
        view = self.parentWidget()
        if view is None:
            return
        # Child of QGraphicsView, not its viewport: map through viewport
        # geometry so the popup stays fixed when the scene scrolls.
        vp = view.viewport() if hasattr(view, "viewport") else view
        x = vp.x() + vp.width()  - self.W - self.MARGIN
        y = vp.y() + vp.height() - self.H - self.MARGIN
        self.move(max(vp.x(), x), max(vp.y(), y))

    def set_pixmap(self, pix: QPixmap) -> None:
        self._pix = pix
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._pix is None:
            return
        p = QPainter(self)
        p.drawPixmap(0, 0, self._pix)
        p.end()

# ===========================================================================
# View
# ===========================================================================

class TimelineView(QGraphicsView):
    """Pan + zoom QGraphicsView wrapping a TimelineScene."""

    zoom_changed         = pyqtSignal(float)
    cursors_changed      = pyqtSignal(list)
    mark_moved           = pyqtSignal(str, int, int)  # kind, id, new_ns - final drop
    mark_dragging        = pyqtSignal(str, int, int)  # kind, id, new_ns - live during drag
    bookmark_requested          = pyqtSignal(int)   # ns at right-click position
    annotation_requested        = pyqtSignal(int)   # ns at right-click position
    clear_bookmarks_requested   = pyqtSignal()      # clear all bookmarks
    clear_annotations_requested = pyqtSignal()      # clear all annotations
    pre_change                  = pyqtSignal()      # emitted before any cursor/mark mutation

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = TimelineScene(self)
        self.setScene(self._scene)

        # -- Qt render settings ------------------------------------------
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.TextAntialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setOptimizationFlags(
            QGraphicsView.DontAdjustForAntialiasing
        )
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setBackgroundBrush(QBrush(QColor("#1E1E1E")))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setFocusPolicy(Qt.StrongFocus)

        # -- Mouse interaction state -------------------------------------
        # Tracks the press position to distinguish click vs drag; button to
        # distinguish left / middle / right action paths in mouseReleaseEvent.
        self._press_pos: Optional[QPoint] = None
        self._press_btn: Qt.MouseButton = Qt.NoButton
        self._drag_threshold    = 6    # px - min movement to enter pan mode
        self._dragging_cursor_idx = -1  # index of cursor being dragged, or -1
        self._cursor_drag_threshold = 8 # px - click-zone around a cursor line
        self._dragging_mark_idx = -1    # index into _mark_data being dragged, or -1
        self._mark_drag_threshold = 6   # px - click-zone around a mark line

        # Label-column resize drag state
        self._LABEL_RESIZE_ZONE   = 6   # px hit zone around the right border
        self._label_resize_dragging = False
        self._label_resize_start_x  = 0
        self._label_resize_start_w  = 0

        # Middle-button time-range selection (drag to select, release to zoom)
        self._mid_press_ns: Optional[int]   = None   # ns at middle-press
        self._mid_band_item = None                   # gray overlay QGraphicsRectItem

        # Double-click rollback: cursor is placed immediately on left-click;
        # if a doubleClickEvent follows, _dbl_click_undo_ns holds the time so
        # we can remove that cursor before zooming (zero latency on single-click).
        self._dbl_click_undo_ns: Optional[int] = None

        # Zoom history for double-click toggle: each _zoom_to_segment() call
        # pushes (timescale_per_px, center_ns, orth_coord, fit_mode, seg_key)
        # so that double-clicking the same segment again restores the prior view.
        self._zoom_history: list = []

        # Segment-boundary jump cache (populated lazily, keyed to trace obj).
        self._seg_starts_cache: List[int] = []
        self._seg_starts_cache_trace: object = None
        # Tab/Shift+Tab time-order navigation cache (populated lazily per trace).
        self._seg_nav_trace: object = None
        self._seg_nav_all: List[tuple] = []          # [(start_ns, end_ns, merge_key, core)]
        self._seg_nav_all_starts: List[int] = []
        self._seg_nav_by_core: Dict[str, List[tuple]] = {}
        self._seg_nav_by_core_starts: Dict[str, List[int]] = {}

        # -- Zoom debounce -----------------------------------------------
        # Wheel events fire very rapidly; we accumulate the zoom factor and
        # fire one rebuild on a short (60 ms) timer. This prevents janky
        # intermediate renders during fast scrolling.
        self._pinch_accum = 1.0
        # macOS native pinch zoom - intercept events on the viewport widget
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
        self._zoom_timer.setInterval(60)   # tuned in load_trace
        self._zoom_timer.timeout.connect(self._flush_zoom)
        self._nav_zoom_timer = QTimer(self)
        self._nav_zoom_timer.setSingleShot(True)
        self._nav_zoom_timer.setInterval(80)
        self._nav_zoom_timer.timeout.connect(self._show_nav)

        # Two-timer scroll-rebuild strategy:
        #   _pan_heartbeat: repeating, fires while the user is scrolling.
        #     Rebuilds when the viewport leaves the cached orth/time region,
        #     rate-limited so momentum scroll does not clear()+rebuild at 20fps.
        #   _pan_timer (settle): single-shot, fires after the last scroll
        #     event for a final strict cleanup rebuild.
        self._pan_timer = QTimer(self)
        self._pan_timer.setSingleShot(True)
        self._pan_timer.setInterval(_PAN_SETTLE_MS)
        self._pan_timer.timeout.connect(self._on_pan_timeout)
        self._pan_heartbeat = QTimer(self)
        self._pan_heartbeat.setSingleShot(False)
        self._pan_heartbeat.setInterval(_PAN_HEARTBEAT_MS)
        self._pan_heartbeat.timeout.connect(self._on_pan_heartbeat)
        self._last_pan_rebuild_ms: float = 0.0
        self._nav_scroll_timer = QTimer(self)
        self._nav_scroll_timer.setSingleShot(True)
        self._nav_scroll_timer.setInterval(_NAV_SCROLL_DEBOUNCE_MS)
        self._nav_scroll_timer.timeout.connect(self._show_nav)

        # -- Fit / resize mode -------------------------------------------
        # Fit-to-window mode: when True, every resize re-runs fit_to_width().
        self._fit_mode: bool = False
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(80)   # ms - debounce rapid resize events
        self._resize_timer.timeout.connect(self._on_resize_timeout)

        # Cache of the last scene-left used for frozen label positioning.
        # Avoids O(n_frozen_items) updates when only vertical scrolling occurs.
        self._frozen_last_scene_left: Optional[float] = None
        # Cache of the last scene-top used for frozen ruler positioning.
        self._frozen_last_scene_top: Optional[float] = None
        # Remember the last viewport position for each orientation.
        # key=True  -> horizontal mode, key=False -> vertical mode
        # value=(center_ns, orth_center_coord, timescale_per_px)
        self._view_pos_by_orientation: Dict[bool, Tuple[int, float, float]] = {}

        # -- Navigator popup overlay ------------------------------------
        # A 260x130 thumbnail at the bottom-right of the canvas whenever the
        # viewport is scrolled / zoomed while content overflows.
        self._nav_popup = _NavigatorPopup(self)
        self._nav_hide_timer = QTimer(self)
        self._nav_hide_timer.setSingleShot(True)
        self._nav_hide_timer.setInterval(1800)  # ms - fade-out after idle
        self._nav_hide_timer.timeout.connect(self._nav_popup.fade_out)
        # Background pixmap cache for the nav popup.  Rebuilt only when the
        # trace, view-mode, STI visibility or expansion state changes.
        # On every scroll we just copy the cached bg and overlay the viewport rect.
        self._nav_bg_pix: Optional[QPixmap] = None
        self._nav_bg_key: object             = None
        self._nav_bg_task_area_h: float      = 0.0   # task-area height used in last bg paint

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _fit_viewport_size(self) -> int:
        """Return the viewport dimension relevant to the time axis for fit calculations."""
        if self._scene._horizontal:
            return max(self.viewport().width(), 800)
        else:
            return max(self.viewport().height(), 600)

    def _time_axis_viewport_px(self) -> int:
        """Actual time-axis pixel extent of the viewport (no fit-time floor)."""
        vp = self.viewport().rect()
        if self._scene._horizontal:
            return max(vp.width(), 1)
        return max(vp.height(), 1)

    def _visible_time_span_ns(self) -> int:
        """Timestamp span currently visible along the time axis."""
        avail = max(self._time_axis_viewport_px() - self._scene._label_width, 100)
        return max(1, int(avail * self._scene._timescale_per_px))

    def _refresh_fit_limit(self) -> None:
        """Recompute fit-to-window timescale clamp for the current orientation."""
        trace = self._scene._trace
        if trace is None:
            return
        time_span = max(trace.time_max - trace.time_min, 1)
        avail = max(self._time_axis_viewport_px() - self._scene._label_width, 100)
        self._scene._timescale_per_px_fit = time_span / avail

    def load_trace(self, trace: BtfTrace) -> None:
        self._fit_mode = True   # new trace always starts in fit mode
        self._zoom_history.clear()  # new trace resets zoom history
        self._zoom_timer.setInterval(_zoom_debounce_ms(len(trace.tasks)))
        self._scene.set_trace(trace, self._fit_viewport_size())
        self.zoom_changed.emit(self._scene.timescale_per_px)
        self._show_nav()

    def add_cursor_at_view_center(self) -> None:
        vp = self.viewport().rect()
        scene_pt = self.mapToScene(vp.center())
        coord = scene_pt.x() if self._scene._horizontal else scene_pt.y()
        ns = self._scene.scene_to_ns(coord)
        self.pre_change.emit()
        self._scene.add_cursor(ns)
        self.cursors_changed.emit(self._scene.cursor_times())

    def add_cursor_at_hover_or_center(self) -> None:
        """Place a cursor at the mouse-pointer position, falling back to viewport centre."""
        hover_ns = self._scene._hover_ns
        if hover_ns is not None:
            self.pre_change.emit()
            self._scene.add_cursor(hover_ns)
            self.cursors_changed.emit(self._scene.cursor_times())
        else:
            self.add_cursor_at_view_center()

    def view_center_ns(self) -> int:
        """Return the timestamp currently at the viewport centre."""
        vp = self.viewport().rect()
        scene_pt = self.mapToScene(vp.center())
        coord = scene_pt.x() if self._scene._horizontal else scene_pt.y()
        return self._scene.scene_to_ns(coord)

    def clear_cursors(self) -> None:
        self.pre_change.emit()
        self._scene.clear_cursors()
        self.cursors_changed.emit([])

    def set_view_mode(self, mode: str) -> None:
        self._scene.set_view_mode(mode)
        if self._fit_mode and self._scene._trace is not None:
            self._show_nav()

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
        old_tpp = self._scene._timescale_per_px
        visible_span = self._visible_time_span_ns()
        self._view_pos_by_orientation[old_h] = (old_ns, old_orth, old_tpp)

        self._scene._horizontal = horizontal
        self._scene._skip_orth_culling = True

        if self._fit_mode:
            self._scene._skip_orth_culling = True
            self.zoom_fit()
            return

        saved = self._view_pos_by_orientation.get(horizontal)
        if saved is not None:
            target_ns, target_orth, target_tpp = saved
            self._scene._timescale_per_px = target_tpp
        else:
            target_ns, target_orth = old_ns, old_orth
            avail = max(self._time_axis_viewport_px() - self._scene._label_width, 100)
            self._scene._timescale_per_px = visible_span / avail

        self._refresh_fit_limit()
        self._scene._timescale_per_px = min(
            self._scene._timescale_per_px, self._scene._timescale_per_px_fit)

        time_span = max(trace.time_max - trace.time_min, 1)
        half_span = max(self._visible_time_span_ns() // 2, time_span // 100)
        self._scene._ns_range_hint = (
            max(trace.time_min, target_ns - half_span),
            min(trace.time_max, target_ns + half_span),
        )

        self._scene.rebuild()

        new_time_coord = self._scene.ns_to_scene_coord(target_ns)
        if horizontal:
            self.centerOn(new_time_coord, target_orth)
        else:
            self.centerOn(target_orth, new_time_coord)
        self.resetTransform()
        self.zoom_changed.emit(self._scene._timescale_per_px)
        self.viewport().update()
        self._show_nav()

    def set_show_sti(self, show: bool) -> None:
        self._scene.set_show_sti(show)

    def set_show_grid(self, show: bool) -> None:
        self._scene.set_show_grid(show)

    def set_sti_log_scale(self, enabled: bool) -> None:
        self._scene.set_sti_log_scale(enabled)

    def set_sti_line_style(self, style: str) -> None:
        self._scene.set_sti_line_style(style)

    def set_sti_row_h(self, h: int) -> None:
        self._scene.set_sti_row_h(h)

    def set_sti_waveform_h(self, h: int) -> None:
        self._scene.set_sti_waveform_h(h)

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
        self._show_nav()

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
        # (viewport_width x timescale_per_px ~= 1280 ns for a typical 640 px window),
        # so centering on the trace midpoint almost never lands on a segment.
        # Instead, scroll to time_min so the first segments are immediately
        # visible - which is the same position the viewer starts at on launch.
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
        # Using the viewport pixel size alone (+/-640 px * 2 ns/px = +/-1280 ns)
        # is too narrow: tasks with long periods may have NO segment in that
        # window.  Instead use +/-(1% of trace span) or +/-10 viewports, whichever
        # is larger.  The 150 % margin inside _update_viewport_bounds adds
        # another 3x on top so the first scroll after 1:1 is also covered.
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

    def _capture_pixmap(self) -> QPixmap:
        """Capture the current visible scene content as a QPixmap."""
        vp = self.viewport()
        vp_rect = vp.rect()
        scene_in_vp = self.mapFromScene(self._scene.sceneRect()).boundingRect()
        content_rect = vp_rect.intersected(scene_in_vp)
        capture_rect = content_rect if not content_rect.isEmpty() else vp_rect
        return vp.grab(capture_rect)

    def save_image(self, filepath: str) -> None:
        """Capture the current visible scene content as a PNG image.

        QWidget.grab() renders exactly what is on screen.  When the scene is
        smaller than the viewport, QGraphicsView centres it and leaves blank
        margins; we crop those away by computing the scene rect in viewport
        coordinates so the output contains only real content.
        """
        pixmap = self._capture_pixmap()
        if not pixmap.save(filepath, "PNG"):
            raise OSError(f"QPixmap.save() failed for path: {filepath}")

    def copy_image_to_clipboard(self) -> Optional[str]:
        """Copy the current visible scene content as a PNG image to the clipboard."""
        return _copy_pixmap_to_clipboard(self._capture_pixmap())

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------
    # mousePressEvent priority (in order of evaluation):
    #   1. MiddleButton  -> start time-range selection band
    #   2. LeftButton near label-column border -> start resize drag
    #   3. LeftButton near a cursor line -> start cursor drag
    #   4. LeftButton inside label column -> let _TaskLabelItem handle it
    #   5. Anything else -> default ScrollHandDrag (pan)
    # ------------------------------------------------------------------

    def _ensure_seg_nav_cache(self) -> None:
        """Build segment-time navigation caches once per loaded trace."""
        sc = self._scene
        tr = sc._trace
        if tr is None:
            self._seg_nav_trace = None
            self._seg_nav_all = []
            self._seg_nav_all_starts = []
            self._seg_nav_by_core = {}
            self._seg_nav_by_core_starts = {}
            return
        if self._seg_nav_trace is tr:
            return

        tick_mk = _task_merge_key("TICK")
        all_events: List[tuple] = []
        by_core: Dict[str, List[tuple]] = defaultdict(list)
        for seg in tr.segments:
            if _is_core_entity(seg.task) or not seg.task:
                continue
            mk = _task_merge_key(seg.task)
            if mk == tick_mk:
                continue
            ev = (seg.start, seg.end, mk, seg.core)
            all_events.append(ev)
            by_core[seg.core].append(ev)

        all_events.sort(key=lambda t: t[0])
        by_core_sorted: Dict[str, List[tuple]] = {}
        by_core_starts: Dict[str, List[int]] = {}
        for core, events in by_core.items():
            events.sort(key=lambda t: t[0])
            by_core_sorted[core] = events
            by_core_starts[core] = [t[0] for t in events]

        self._seg_nav_trace = tr
        self._seg_nav_all = all_events
        self._seg_nav_all_starts = [t[0] for t in all_events]
        self._seg_nav_by_core = by_core_sorted
        self._seg_nav_by_core_starts = by_core_starts

    def _pick_next_task_by_time(self,
                                events: List[tuple],
                                starts: List[int],
                                ref_ns: int,
                                cur_task: Optional[str],
                                forward: bool,
                                task_ok) -> Optional[tuple]:
        """Pick next/previous task event by time, skipping same-task repeats."""
        if not events:
            return None

        if forward:
            idx = bisect_right(starts, ref_ns)
            while idx < len(events):
                start, _end, mk, _core = events[idx]
                if task_ok(mk) and (cur_task is None or mk != cur_task):
                    return events[idx]
                idx += 1
            idx = 0
            while idx < len(events):
                start, _end, mk, _core = events[idx]
                if task_ok(mk) and (cur_task is None or mk != cur_task):
                    return events[idx]
                idx += 1
        else:
            idx = bisect_left(starts, ref_ns) - 1
            while idx >= 0:
                start, _end, mk, _core = events[idx]
                if task_ok(mk) and (cur_task is None or mk != cur_task):
                    return events[idx]
                idx -= 1
            idx = len(events) - 1
            while idx >= 0:
                start, _end, mk, _core = events[idx]
                if task_ok(mk) and (cur_task is None or mk != cur_task):
                    return events[idx]
                idx -= 1
        return None

    def _cycle_highlighted_task(self, forward: bool) -> bool:
        """Select next/previous task by segment time order.

        Task view: global timeline order.
        Core view: timeline order within the selected core.
        """
        sc = self._scene
        tr = sc._trace
        if tr is None:
            return False

        self._ensure_seg_nav_cache()

        target_task: Optional[str] = None
        target_core: Optional[str] = None
        target_ns: Optional[int] = None
        target_seg_end: Optional[int] = None
        cur_task = sc._locked_task
        ref_ns = sc._locked_ns if sc._locked_ns is not None else self.view_center_ns()

        if sc._view_mode == "core":
            core_names = tr.core_names
            core_tasks = tr.core_task_order
            if sc._task_filter_q:
                _fcn, _fct = [], {}
                for _c in core_names:
                    _ts = [t for t in core_tasks[_c] if sc._task_raw_name_matches_filter(t)]
                    if _ts:
                        _fcn.append(_c)
                        _fct[_c] = _ts
                core_names, core_tasks = _fcn, _fct
            if not core_names:
                return False

            target_core = sc._locked_core if sc._locked_core in core_names else None
            if target_core is None and cur_task is not None:
                for _c in core_names:
                    if any(_task_merge_key(raw) == cur_task for raw in core_tasks.get(_c, [])):
                        target_core = _c
                        break
            if target_core is None:
                target_core = core_names[0 if forward else -1]

            allowed_mk = {_task_merge_key(raw) for raw in core_tasks.get(target_core, [])}
            if not allowed_mk:
                return False

            events = self._seg_nav_by_core.get(target_core, [])
            starts = self._seg_nav_by_core_starts.get(target_core, [])
            picked = self._pick_next_task_by_time(
                events, starts, ref_ns, cur_task, forward,
                lambda mk: mk in allowed_mk and sc._task_merge_key_matches_filter(mk),
            )
            if picked is None:
                return False
            target_ns, target_seg_end, target_task, _picked_core = picked
        else:
            events = self._seg_nav_all
            starts = self._seg_nav_all_starts
            picked = self._pick_next_task_by_time(
                events, starts, ref_ns, cur_task, forward,
                lambda mk: sc._task_merge_key_matches_filter(mk),
            )
            if picked is None:
                return False
            target_ns, target_seg_end, target_task, target_core = picked

        if target_task is None or target_ns is None or target_seg_end is None:
            return False

        nav_seg = TaskSegment(
            task=tr.task_repr.get(target_task, target_task),
            start=target_ns,
            end=target_seg_end,
            core=(target_core or "Core_0"),
        )
        sc.set_highlighted_segment(nav_seg)

        time_coord = sc.ns_to_scene_coord(target_ns)
        time_end_coord = sc.ns_to_scene_coord(target_seg_end)
        vp_center_scene = self.mapToScene(self.viewport().rect().center())
        visible_rect = self.mapToScene(self.viewport().rect()).boundingRect()

        orth_span = sc.task_orth_scene_span(target_task, target_core)
        if sc._horizontal:
            content_left = visible_rect.left() + sc._label_width
            time_in_view = (content_left <= time_coord and
                            time_end_coord <= visible_rect.right())
            orth_out_of_view = False
            orth_center = vp_center_scene.y()
            if orth_span is not None:
                orth_top, orth_bottom = orth_span
                orth_center = (orth_top + orth_bottom) / 2
                orth_out_of_view = (orth_bottom <= visible_rect.top() or
                                    orth_top >= visible_rect.bottom())
        else:
            content_top = visible_rect.top() + RULER_WIDTH
            time_in_view = (content_top <= time_coord and
                            time_end_coord <= visible_rect.bottom())
            orth_out_of_view = False
            orth_center = vp_center_scene.x()
            if orth_span is not None:
                orth_left, orth_right = orth_span
                orth_center = (orth_left + orth_right) / 2
                content_left = visible_rect.left() + RULER_WIDTH
                orth_out_of_view = (orth_right <= content_left or
                                    orth_left >= visible_rect.right())

        if not time_in_view or orth_out_of_view:
            if sc._horizontal:
                self.centerOn(time_coord, orth_center if orth_out_of_view else vp_center_scene.y())
            else:
                self.centerOn(orth_center if orth_out_of_view else vp_center_scene.x(),
                              time_coord)
        return True

    def focusNextPrevChild(self, next: bool) -> bool:
        """Use Tab / Shift+Tab for timeline task navigation when view has focus."""
        if self.hasFocus() and self._scene._trace is not None:
            self._cycle_highlighted_task(next)
            return True
        return super().focusNextPrevChild(next)

    def keyPressEvent(self, event) -> None:
        """Arrow-key navigation.

        Horizontal mode - time axis is horizontal:
          Left / Right         - scroll along time axis by 20 % of viewport width
          Shift + Left / Right - jump to previous / next segment boundary
          Up / Down            - scroll along row axis by 20 % of viewport height

        Vertical mode - time axis is vertical:
          Up / Down            - scroll along time axis by 20 % of viewport height
          Shift + Up / Down    - jump to previous / next segment boundary
          Left / Right         - scroll along row axis by 20 % of viewport width

        All other keys pass through to the default handler.
        """
        key  = event.key()
        mods = event.modifiers()
        sc   = self._scene
        horiz = sc._horizontal

        if horiz:
            time_fwd, time_back = Qt.Key_Right, Qt.Key_Left
            row_fwd,  row_back  = Qt.Key_Down,  Qt.Key_Up
        else:
            time_fwd, time_back = Qt.Key_Down,  Qt.Key_Up
            row_fwd,  row_back  = Qt.Key_Right, Qt.Key_Left

        if key in (Qt.Key_Tab, Qt.Key_Backtab):
            is_back = (key == Qt.Key_Backtab) or bool(mods & Qt.ShiftModifier)
            self._cycle_highlighted_task(not is_back)
            event.accept()
            return

        if key in (time_fwd, time_back):
            if mods & Qt.ShiftModifier and sc._trace is not None:
                if self._seg_starts_cache_trace is not sc._trace:
                    s: set = set()
                    for _starts in sc._trace.seg_start_by_merge_key.values():
                        s.update(_starts)
                    self._seg_starts_cache = sorted(s)
                    self._seg_starts_cache_trace = sc._trace
                all_starts = self._seg_starts_cache

                if all_starts:
                    vp = self.viewport().rect()
                    lw = sc._label_width
                    if horiz:
                        edge_lo_ns = sc.scene_to_ns(self.mapToScene(QPoint(lw, 0)).x())
                        edge_hi_ns = sc.scene_to_ns(self.mapToScene(QPoint(vp.right(), 0)).x())
                    else:
                        edge_lo_ns = sc.scene_to_ns(self.mapToScene(QPoint(0, lw)).y())
                        edge_hi_ns = sc.scene_to_ns(self.mapToScene(QPoint(0, vp.bottom())).y())

                    if key == time_fwd:
                        idx = bisect_right(all_starts, edge_hi_ns)
                        target = all_starts[min(idx, len(all_starts) - 1)]
                    else:
                        idx = bisect_left(all_starts, edge_lo_ns) - 1
                        target = all_starts[max(idx, 0)]

                    new_coord = sc.ns_to_scene_coord(target)
                    vp_cur = self.mapToScene(self.viewport().rect().center())
                    if horiz:
                        self.centerOn(new_coord, vp_cur.y())
                    else:
                        self.centerOn(vp_cur.x(), new_coord)
            else:
                if horiz:
                    step_px = max(1, int(self.viewport().width() * 0.20))
                    sb = self.horizontalScrollBar()
                else:
                    step_px = max(1, int(self.viewport().height() * 0.20))
                    sb = self.verticalScrollBar()
                sb.setValue(sb.value() + (step_px if key == time_fwd else -step_px))
            event.accept()
            return

        if key in (row_fwd, row_back):
            if horiz:
                step_px = max(1, int(self.viewport().height() * 0.20))
                sb = self.verticalScrollBar()
            else:
                step_px = max(1, int(self.viewport().width() * 0.20))
                sb = self.horizontalScrollBar()
            sb.setValue(sb.value() + (step_px if key == row_fwd else -step_px))
            event.accept()
            return

        super().keyPressEvent(event)

    def _hit_segment_at(self, scene_pt):
        """Return the TraceSegment under *scene_pt*, or None."""
        for item in self._scene.items(scene_pt):
            if isinstance(item, _BatchRowItem):
                xs = item._xs
                if not xs:
                    break
                x = (scene_pt.x() - item.pos().x()) if self._scene._horizontal \
                    else (scene_pt.y() - item.pos().y())
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
                        seg = item._seg_data[idx][3]
                        if seg is not None:
                            return seg
                break
        return None

    def _zoom_to_segment(self, seg) -> None:
        """Zoom the viewport to fit *seg* with a small margin."""
        # Save current zoom state so a second double-click can restore it.
        vp     = self.viewport().rect()
        vp_cur = self.mapToScene(vp.center())
        if self._scene._horizontal:
            save_ns   = self._scene.scene_to_ns(vp_cur.x())
            save_orth = vp_cur.y()
        else:
            save_ns   = self._scene.scene_to_ns(vp_cur.y())
            save_orth = vp_cur.x()
        seg_key = (seg.start, seg.end, seg.task, seg.core)
        self._zoom_history.append((
            self._scene._timescale_per_px,
            save_ns,
            save_orth,
            self._fit_mode,
            seg_key,
        ))

        dur    = seg.end - seg.start
        margin = max(1, dur // 10)
        ns_lo  = seg.start - margin
        ns_hi  = seg.end   + margin
        vp_px  = vp.width() if self._scene._horizontal else vp.height()
        self._fit_mode = False
        self._scene.zoom_to_range(ns_lo, ns_hi, max(vp_px, 100))
        self.zoom_changed.emit(self._scene.timescale_per_px)
        center_ns = (seg.start + seg.end) // 2
        new_coord = self._scene.ns_to_scene_coord(center_ns)
        vp_cur    = self.mapToScene(vp.center())
        if self._scene._horizontal:
            self.centerOn(new_coord, vp_cur.y())
        else:
            self.centerOn(vp_cur.x(), new_coord)

    def _restore_zoom(self) -> None:
        """Pop the zoom history and restore the previous view."""
        if not self._zoom_history or self._scene._trace is None:
            return
        tpp, center_ns, orth, fit_mode, _seg_key = self._zoom_history.pop()
        self._fit_mode = fit_mode
        if fit_mode:
            self._scene.fit_to_width(self._fit_viewport_size())
        else:
            trace = self._scene._trace
            _span = max(trace.time_max - trace.time_min, 1)
            _vp_half = int(self._fit_viewport_size() * 10 * tpp)
            _half = max(_vp_half, _span // 100)
            self._scene._ns_range_hint = (
                max(trace.time_min, center_ns - _half),
                min(trace.time_max, center_ns + _half),
            )
            self._scene._timescale_per_px = tpp
            self._scene.rebuild()
        self.resetTransform()
        self.zoom_changed.emit(self._scene.timescale_per_px)
        new_coord = self._scene.ns_to_scene_coord(center_ns)
        if self._scene._horizontal:
            self.centerOn(new_coord, orth)
        else:
            self.centerOn(orth, new_coord)

    def mouseDoubleClickEvent(self, event) -> None:
        """Double-click on a segment to zoom the timeline to fit that segment."""
        # Roll back the cursor placed by the preceding mouseReleaseEvent so
        # double-click only zooms and does not leave a cursor behind.
        if self._dbl_click_undo_ns is not None:
            self._scene.remove_nearest_cursor(self._dbl_click_undo_ns)
            self.cursors_changed.emit(self._scene.cursor_times())
            self._dbl_click_undo_ns = None

        # Double-click on label-column resize border -> auto-fit column width
        lw = self._scene._label_width
        if event.button() == Qt.LeftButton and self._scene._trace is not None:
            if self._scene._horizontal:
                in_resize_zone = abs(event.pos().x() - lw) <= self._LABEL_RESIZE_ZONE
            else:
                in_resize_zone = abs(event.pos().y() - lw) <= self._LABEL_RESIZE_ZONE
            if in_resize_zone:
                self._auto_fit_label_column()
                event.accept()
                return

        if event.button() != Qt.LeftButton or self._scene._trace is None:
            super().mouseDoubleClickEvent(event)
            return
        scene_pt = self.mapToScene(event.pos())
        hit_seg  = self._hit_segment_at(scene_pt)
        if hit_seg is None:
            super().mouseDoubleClickEvent(event)
            return
        # If this segment was the last one double-click-zoomed into, restore
        # the previous zoom level instead of zooming in again.
        seg_key = (hit_seg.start, hit_seg.end, hit_seg.task, hit_seg.core)
        if (self._zoom_history
                and self._zoom_history[-1][4] == seg_key):
            self._restore_zoom()
        else:
            self._zoom_to_segment(hit_seg)
        event.accept()

    def _auto_fit_label_column(self) -> None:
        """Resize the label column to fit the widest visible task name."""
        sc = self._scene
        if sc._trace is None:
            return
        font = _monospace_font(sc._font_size)
        fm   = QFontMetrics(font)
        max_w = 60
        for item in sc.items():
            if isinstance(item, _TaskLabelItem):
                w = fm.horizontalAdvance(item._task_name) + 24
                if w > max_w:
                    max_w = w
        new_w = max(60, min(max_w, 600))
        sc.set_label_width(new_w)
        if sc._horizontal:
            self._reposition_frozen()
        else:
            self._reposition_frozen_top()

    def _snap_to_boundary(self, ns: int) -> int:
        """Snap *ns* to the nearest segment boundary (start or end) within 8 px.

        Returns *ns* unchanged when no boundary is close enough or no trace
        is loaded.  Hold Shift while placing / dragging a cursor to activate.
        """
        tr = self._scene._trace
        if tr is None:
            return ns
        window = int(8 * self._scene._timescale_per_px)
        if window <= 0:
            return ns
        ns_lo, ns_hi = ns - window, ns + window
        best_ns   = ns
        best_dist = window + 1
        for mk, starts in tr.seg_start_by_merge_key.items():
            if not starts:
                continue
            i = bisect_left(starts, ns_lo)
            while i < len(starts) and starts[i] <= ns_hi:
                dist = abs(starts[i] - ns)
                if dist < best_dist:
                    best_dist = dist
                    best_ns   = starts[i]
                i += 1
            # Also check segment ends using the paired seg_map_by_merge_key list.
            # Search from bisect_left(starts, ns_lo) backwards a small amount
            # to catch segments that started before ns_lo but end inside the window.
            segs = tr.seg_map_by_merge_key.get(mk, [])
            j_hi = bisect_right(starts, ns_hi)   # exclusive upper bound
            j_lo = max(0, bisect_left(starts, ns_lo) - 32)  # look back 32 segs
            for k in range(j_lo, j_hi):
                seg = segs[k]
                if ns_lo <= seg.end <= ns_hi:
                    dist = abs(seg.end - ns)
                    if dist < best_dist:
                        best_dist = dist
                        best_ns   = seg.end
        return best_ns

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
                    _safe_scene_remove_items(self._scene, [self._mid_band_item])
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
                    self.pre_change.emit()
                    self._dragging_cursor_idx = idx
                    self.setDragMode(QGraphicsView.NoDrag)
                    self.viewport().setCursor(Qt.SizeHorCursor
                                              if self._scene._horizontal
                                              else Qt.SizeVerCursor)
                    event.accept()
                    return

            # --- Check if we're starting a mark drag ---
            mth = self._mark_drag_threshold
            press_coord = scene_pt.x() if self._scene._horizontal else scene_pt.y()
            for idx, mdata in enumerate(self._scene._mark_data):
                mark_ns    = mdata[0]
                mark_coord = self._scene.ns_to_scene_coord(mark_ns)
                if abs(press_coord - mark_coord) <= mth:
                    self.pre_change.emit()
                    self._dragging_mark_idx = idx
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

        # Show resize cursor when hovering near the label border or a cursor/mark line
        if (self._scene._trace is not None and
                not self._label_resize_dragging and
                self._mid_press_ns is None and
                self._dragging_cursor_idx < 0 and
                self._dragging_mark_idx < 0):
            lw = self._scene._label_width
            _near_cursor = False
            _near_mark   = False
            _hover_coord = (self.mapToScene(event.pos()).x() if self._scene._horizontal
                            else self.mapToScene(event.pos()).y())
            if self._scene._cursor_times:
                _near_cursor = any(
                    abs(_hover_coord - self._scene.ns_to_scene_coord(ns)) <= self._cursor_drag_threshold
                    for ns in self._scene._cursor_times
                )
            if self._scene._mark_data:
                _near_mark = any(
                    abs(_hover_coord - self._scene.ns_to_scene_coord(m[0])) <= self._mark_drag_threshold
                    for m in self._scene._mark_data
                )
            if self._scene._horizontal:
                if abs(event.pos().x() - lw) <= self._LABEL_RESIZE_ZONE:
                    self.viewport().setCursor(Qt.SizeHorCursor)
                elif _near_cursor:
                    self.viewport().setCursor(Qt.SplitHCursor)
                elif _near_mark:
                    self.viewport().setCursor(Qt.SplitHCursor)
                else:
                    self.viewport().unsetCursor()
            else:
                if abs(event.pos().y() - lw) <= self._LABEL_RESIZE_ZONE:
                    self.viewport().setCursor(Qt.SizeVerCursor)
                elif _near_cursor:
                    self.viewport().setCursor(Qt.SplitVCursor)
                elif _near_mark:
                    self.viewport().setCursor(Qt.SplitVCursor)
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
                _safe_scene_remove_items(self._scene, [self._mid_band_item])
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
            if event.modifiers() & Qt.ShiftModifier:
                ns = self._snap_to_boundary(ns)
            self._scene._cursor_times[self._dragging_cursor_idx] = ns
            self._scene._draw_cursors()
            self._reposition_frozen_top()   # keep cursor labels in the ruler area
            self.cursors_changed.emit(self._scene.cursor_times())
            event.accept()
            return

        if self._dragging_mark_idx >= 0:
            scene_pt = self.mapToScene(event.pos())
            coord    = scene_pt.x() if self._scene._horizontal else scene_pt.y()
            ns       = self._scene.scene_to_ns(coord)
            tup      = self._scene._mark_data[self._dragging_mark_idx]
            dragged_kind = tup[3]
            dragged_id   = tup[4]
            self._scene._mark_data[self._dragging_mark_idx] = (ns, tup[1], tup[2], tup[3], tup[4])
            self._scene._draw_marks()
            self._reposition_frozen_top()
            self.mark_dragging.emit(dragged_kind, dragged_id, ns)
            # Re-sync index: mark_dragging may have triggered set_marks() re-sort
            for _i, _m in enumerate(self._scene._mark_data):
                if _m[3] == dragged_kind and _m[4] == dragged_id:
                    self._dragging_mark_idx = _i
                    break
            else:
                # Mark was removed externally during drag - abort
                self._dragging_mark_idx = -1
                self.setDragMode(QGraphicsView.ScrollHandDrag)
                self.viewport().unsetCursor()
            self._reposition_frozen_top()  # re-pin after rebuild
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

        # Update mouse-hover ghost line (only when not dragging)
        if (self._scene._trace is not None
                and self._mid_press_ns is None
                and self._dragging_cursor_idx < 0
                and self._dragging_mark_idx < 0
                and not self._label_resize_dragging):
            lw = self._scene._label_width
            in_label = (event.pos().x() < lw if self._scene._horizontal
                        else event.pos().y() < lw)
            if in_label:
                self._scene.clear_hover_line()
            else:
                try:
                    scene_pt = self.mapToScene(event.pos())
                except RuntimeError:
                    self._scene.clear_hover_line()
                else:
                    coord = scene_pt.x() if self._scene._horizontal else scene_pt.y()
                    ns = self._scene.scene_to_ns(coord)
                    self._scene._hover_ns = ns
                    self._scene._draw_hover_line()
        else:
            self._scene.clear_hover_line()

    def leaveEvent(self, event) -> None:
        if self._scene._trace is not None:
            self._scene.clear_hover_line()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        # Dispatch in order (first match returns early):
        #   1. Middle-button release  -> zoom to dragged range
        #   2. Label-column resize end
        #   3. Cursor drag end
        #   4. Left-click (delta <= threshold) inside timeline  -> place cursor
        #   5. Right-click inside timeline -> remove cursor / clear all

        # Middle-button release: zoom to selected range
        if event.button() == Qt.MiddleButton and self._mid_press_ns is not None:
            # Remove band overlay
            if self._mid_band_item is not None:
                _safe_scene_remove_items(self._scene, [self._mid_band_item])
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

        if self._dragging_mark_idx >= 0:
            tup     = self._scene._mark_data[self._dragging_mark_idx]
            new_ns  = tup[0]
            kind    = tup[3]
            mark_id = tup[4]
            self._dragging_mark_idx = -1
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.viewport().unsetCursor()
            self.mark_moved.emit(kind, mark_id, new_ns)
            event.accept()
            return

        # Restore drag mode if it was temporarily disabled for a label click
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        super().mouseReleaseEvent(event)
        if self._press_pos is None:
            return
        delta = (event.pos() - self._press_pos).manhattanLength()
        if delta <= self._drag_threshold:
            # Use viewport coordinates - label column is always the leftmost
            # _label_width pixels on screen regardless of horizontal scroll.
            lw = self._scene._label_width
            in_vp_label  = (event.pos().x()       < lw if self._scene._horizontal
                            else event.pos().y()       < lw)
            # Also block when the press originated inside the label column:
            # a tiny drag (<= drag_threshold) from the label into the timeline
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
                hit_seg = self._hit_segment_at(scene_pt)
                if hit_seg is not None:
                    # Single click on a task segment -> highlight; second click on
                    # same segment -> un-highlight (toggle).
                    if self._scene._locked_segment_key == self._scene._segment_lock_key(hit_seg):
                        self._scene.set_highlighted_segment(None)
                    else:
                        self._scene.set_highlighted_segment(hit_seg)
                    self._dbl_click_undo_ns = None
                else:
                    # Click on ruler or empty area -> place cursor.
                    if event.modifiers() & Qt.ShiftModifier:
                        ns = self._snap_to_boundary(ns)
                    # Place cursor immediately; mouseDoubleClickEvent will roll it
                    # back if this click turns out to be the first of a double-click.
                    self.pre_change.emit()
                    self._scene.add_cursor(ns)
                    self.cursors_changed.emit(self._scene.cursor_times())
                    self._dbl_click_undo_ns = ns
            elif event.button() == Qt.RightButton:
                self.pre_change.emit()
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

        # Shared icon color - timeline always uses a dark background
        _icon_color = "#D4D4D4"

        # --- Segment-specific actions (shown when right-clicking on a segment) ---
        hit_seg = self._hit_segment_at(scene_pt)
        if hit_seg is not None:
            _seg_task = hit_seg.task
            menu.addAction(
                _svg_icon("M4 1.5H3a2 2 0 0 0-2 2V14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V3.5a2 2 0 0 0-2-2h-1v1h1a1 1 0 0 1 1 1V14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1h1v-1zM5 0h6a1 1 0 0 1 1 1v3H4V1a1 1 0 0 1 1-1z", _icon_color),
                f'Copy task name  "{_task_display_name(_seg_task)}"',
                lambda: QApplication.clipboard().setText(_task_display_name(_seg_task))
            )
            menu.addAction(
                _svg_icon(_IC_ZIN, _icon_color),
                "Zoom to this segment",
                lambda _s=hit_seg: self._zoom_to_segment(_s)
            )
            menu.addAction(
                _svg_icon(_IC_LEGEND, _icon_color),
                "Select in Legend",
                lambda _t=_seg_task, _c=hit_seg.core: self._scene.set_highlighted_task(
                    _task_merge_key(_t), locked=True, core_name=_c, ref_ns=hit_seg.start)
            )
            menu.addSeparator()

        # Place cursor
        menu.addAction(
            _svg_icon(_IC_CURSOR, _icon_color),
            f"Place cursor here  ({_format_time(ns, self._scene._trace.time_scale, decimals=3) if self._scene._trace else ''})",
            lambda: (self.pre_change.emit(), self._scene.add_cursor(ns),
                     self.cursors_changed.emit(self._scene.cursor_times()))
        )
        if self._scene.cursor_times():
            # Remove nearest cursor - use an eraser/minus-cursor icon
            menu.addAction(
                _svg_icon("M2 2.5A.5.5 0 0 1 2.5 2h4a.5.5 0 0 1 0 1H3v9h9v-3.5a.5.5 0 0 1 1 0V12.5a.5.5 0 0 1-.5.5h-10a.5.5 0 0 1-.5-.5v-10zM14.854 2.854a.5.5 0 0 0-.708-.708L8 8.293 5.854 6.146a.5.5 0 1 0-.708.708l2.5 2.5a.5.5 0 0 0 .708 0l6.5-6.5z", _icon_color),
                "Remove nearest cursor",
                lambda: (self.pre_change.emit(), self._scene.remove_nearest_cursor(ns),
                         self.cursors_changed.emit(self._scene.cursor_times()))
            )
            menu.addAction(
                _svg_icon(_IC_CLEAR, _icon_color),
                "Clear all cursors",
                lambda: (self.pre_change.emit(), self._scene.clear_cursors(),
                         self.cursors_changed.emit([]))
            )
        if self._scene._trace is not None:
            menu.addSeparator()
            # Bookmark icon - flag/ribbon shape
            menu.addAction(
                _svg_icon("M2 2a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v13.5a.5.5 0 0 1-.74.439L8 13.069l-5.26 2.87A.5.5 0 0 1 2 15.5V2zm2-1a1 1 0 0 0-1 1v12.566l4.74-2.586a.5.5 0 0 1 .48 0L13 14.566V2a1 1 0 0 0-1-1H4z", _icon_color),
                f"Add Bookmark here  ({_format_time(ns, self._scene._trace.time_scale, decimals=3)})",
                lambda: self.bookmark_requested.emit(ns)
            )
            # Annotation icon - pencil/note shape
            menu.addAction(
                _svg_icon("M12.854 0.146a.5.5 0 0 0-.707 0L10.5 1.793 14.207 5.5l1.647-1.646a.5.5 0 0 0 0-.708l-3-3zm.646 6.061L9.793 2.5 3.293 9H3.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.207l6.5-6.5zm-7.468 7.468A.5.5 0 0 1 6 13.5V13h-.5a.5.5 0 0 1-.5-.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.5-.5V10h-.5a.499.499 0 0 1-.175-.032l-.179.178a.5.5 0 0 0-.11.168l-2 5a.5.5 0 0 0 .65.65l5-2a.5.5 0 0 0 .168-.11l.178-.178z", _icon_color),
                f"Add Annotation here  ({_format_time(ns, self._scene._trace.time_scale, decimals=3)})",
                lambda: self.annotation_requested.emit(ns)
            )
            _has_bm = getattr(self, '_has_bookmarks', False)
            _has_an = getattr(self, '_has_annotations', False)
            if _has_bm or _has_an:
                menu.addSeparator()
                if _has_bm:
                    menu.addAction(
                        _svg_icon(_IC_CLEAR, _icon_color),
                        "Clear all bookmarks",
                        lambda: self.clear_bookmarks_requested.emit()
                    )
                if _has_an:
                    menu.addAction(
                        _svg_icon(_IC_CLEAR, _icon_color),
                        "Clear all annotations",
                        lambda: self.clear_annotations_requested.emit()
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
            # Shift+scroll -> pan horizontally; plain scroll -> natural direction
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
                # Mouse left the viewport - ensure any hover highlight is cleared
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
            return  # already at zoom limit - nothing changed, skip scroll/emit
        self.zoom_changed.emit(self._scene.timescale_per_px)

        # After rebuild, keep the time-axis anchor fixed without drifting on
        # the orthogonal axis (prevents left/right drift in vertical mode).
        new_scene_coord = self._scene.ns_to_scene_coord(center_ns)
        cur_scene_center = self.mapToScene(vp_center)
        if is_horiz:
            self.centerOn(new_scene_coord + offset, cur_scene_center.y())
        else:
            self.centerOn(cur_scene_center.x(), new_scene_coord + offset)
        self._nav_zoom_timer.start()

    # ------------------------------------------------------------------
    # Scroll and viewport sync
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Navigator popup
    # ------------------------------------------------------------------

    def _build_nav_bg(self, W: int, H: int, sc, tr, v_total: float) -> 'QPixmap':
        """Render the static background of the nav popup (rows + STI + border).

        Does NOT include the orange viewport indicator - that is painted on a
        copy of this pixmap in ``_paint_nav_pixmap`` so the expensive row
        painting only happens when the trace/mode/STI state actually changes.
        """
        is_dark_ui = getattr(sc, '_is_dark_ui', True)
        nav_bg = QColor(30, 30, 30, 230) if is_dark_ui else QColor(245, 245, 245, 235)
        nav_border = QColor(70, 70, 70) if is_dark_ui else QColor(170, 170, 170)

        pix = QPixmap(W, H)
        pix.fill(nav_bg)

        if tr is None:
            return pix

        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing, False)

        time_span = max(tr.time_max - tr.time_min, 1)

        # ------------------------------------------------------------------
        # Build flat row list
        # ------------------------------------------------------------------
        row_data: list = []

        if sc._view_mode == "task":
            for mk in tr.tasks:
                if not sc._task_merge_key_matches_filter(mk):
                    continue
                segs = (tr.seg_lod_ultra_by_merge_key.get(mk)
                        or tr.seg_map_by_merge_key.get(mk, []))
                if not segs:
                    continue
                # Use per-segment blended color (task color + core tint) to
                # match the main view's _blended_brush(seg.task, seg.core).
                row_data.append({'segs': segs, 'fixed_color': None, 'blend': True})
        else:
            skip_hdr = sc._core_view_task_filter_active()
            core_names, core_tasks = sc._filtered_core_view_tasks()
            for core in core_names:
                if not skip_hdr:
                    hdr_segs = (tr.core_seg_lod_ultra.get(core)
                                or tr.core_segs.get(core, []))
                    if hdr_segs:
                        # Core header: per-segment base task color (no core tint),
                        # matching main view's _task_brush(seg.task).
                        row_data.append({'segs': hdr_segs, 'fixed_color': None, 'blend': False})
                if sc._core_expanded.get(core, True):
                    for task_raw in core_tasks.get(core, []):
                        t_segs = (tr.core_task_seg_lod_ultra.get(core, {}).get(task_raw)
                                  or tr.core_task_segs.get(core, {}).get(task_raw, []))
                        if not t_segs:
                            continue
                        # Sub-task row: base task color (no core tint), matching
                        # main view's _task_brush(task_name).
                        col = QColor(_task_color(task_raw))
                        col.setAlpha(210)
                        row_data.append({'segs': t_segs, 'fixed_color': col})

        sti_row_data: list = []
        if sc._show_sti:
            for ch_idx, ch in enumerate(tr.sti_channels):
                ch_evs = tr.sti_events_by_target.get(ch, [])
                if not ch_evs:
                    continue
                ch_color = QColor(_STI_PALETTE[ch_idx % len(_STI_PALETTE)])
                ch_color.setAlpha(200)
                is_exp = ch in sc._sti_expanded
                sti_row_data.append({'evs': ch_evs, 'color': ch_color, 'is_expanded': is_exp})

        if not row_data and not sti_row_data:
            # Border only
            try:
                p.setPen(QPen(nav_border, 1))
                p.setBrush(Qt.NoBrush)
                p.drawRect(0, 0, W - 1, H - 1)
            finally:
                p.end()
            return pix

        # Compute actual STI height in main-view pixels (matching scene layout) so
        # the thumbnail allocates space proportionally - no more over-represented STI zone.
        _sti_main_h = 0.0
        if sc._show_sti and tr.sti_channels:
            for ch in tr.sti_channels:
                is_exp = ch in sc._sti_expanded
                _sti_main_h += (sc._sti_waveform_h_val if is_exp else sc._sti_row_h_val) + sc._row_gap
        # Use actual content heights for proportioning rather than scrollbar-derived
        # v_total, which can be unreliable (zero/near-zero) before layout settles.
        _task_main_h  = len(row_data) * (sc._row_height + sc._row_gap)
        _tot_h_safe   = max(1.0, _task_main_h + _sti_main_h)
        sti_total_h   = _sti_main_h / _tot_h_safe * H
        task_area_h   = float(H) - sti_total_h
        self._nav_bg_task_area_h = task_area_h  # remembered for potential future use
        n_rows        = max(1, len(row_data))
        row_h         = task_area_h / n_rows if row_data else float(H)
        p.setPen(Qt.NoPen)

        # Per-(task,core) colour cache - keyed by (task, core, blend) to avoid
        # collisions between blended (task mode) and base (core-header) colours.
        _seg_color_cache: dict = {}

        for i, rd in enumerate(row_data):
            y     = i * row_h
            rh    = max(1.0, row_h - 0.5)
            fixed = rd['fixed_color']
            blend = rd.get('blend', False)
            for seg in rd['segs']:
                x1 = (seg.start - tr.time_min) / time_span * W
                x2 = (seg.end   - tr.time_min) / time_span * W
                sw = max(0.5, x2 - x1)
                if fixed is not None:
                    col = fixed
                else:
                    ck = (seg.task, seg.core, blend)
                    col = _seg_color_cache.get(ck)
                    if col is None:
                        if blend:
                            col = QColor(_blended_color(seg.task, seg.core))
                        else:
                            col = QColor(_task_color(seg.task))
                        col.setAlpha(200)
                        _seg_color_cache[ck] = col
                p.fillRect(QRectF(x1, y, sw, rh), col)

        if sti_row_data:
            sti_row_h = sti_total_h / len(sti_row_data)
            for i, rd in enumerate(sti_row_data):
                y   = task_area_h + i * sti_row_h
                rh  = max(2.0, sti_row_h - 0.5)
                col = rd['color']
                evs = rd['evs']
                if rd['is_expanded']:
                    # Single-pass min/max extraction
                    v_min = math.inf
                    v_max = -math.inf
                    fvals: list = []
                    for ev in evs:
                        note_str = (ev.note or '').strip()
                        try:
                            v = float(note_str) if note_str else float(ev.event or 0)
                        except (ValueError, TypeError):
                            fvals.append(None)
                            continue
                        if v < v_min: v_min = v
                        if v > v_max: v_max = v
                        fvals.append(v)
                    # Use the same waveform colours as _BatchStiWaveformItem.
                    _wf_line_col = QColor("#5BC8FF")
                    _wf_dot_col  = QColor("#80DFFF")
                    if math.isfinite(v_min) and v_min != v_max:
                        v_rng = v_max - v_min
                        pts: list = []
                        if sc._sti_line_style == 'step':
                            for ev, v in zip(evs, fvals):
                                if v is None:
                                    continue
                                px = (ev.time - tr.time_min) / time_span * W
                                py = y + rh - (v - v_min) / v_rng * rh
                                if pts:
                                    pts.append(QPointF(px, pts[-1].y()))
                                pts.append(QPointF(px, py))
                        else:  # linear (default)
                            for ev, v in zip(evs, fvals):
                                if v is None:
                                    continue
                                px = (ev.time - tr.time_min) / time_span * W
                                py = y + rh - (v - v_min) / v_rng * rh
                                pts.append(QPointF(px, py))
                        if len(pts) >= 2:
                            p.setPen(QPen(_wf_line_col, 1.0))
                            p.drawPolyline(QPolygonF(pts))
                            p.setPen(Qt.NoPen)
                    else:
                        p.setPen(Qt.NoPen)
                        p.setBrush(QBrush(_wf_dot_col))
                        for ev in evs:
                            x1 = (ev.time - tr.time_min) / time_span * W
                            p.drawEllipse(QPointF(x1, y + rh / 2), 2.0, 2.0)
                else:
                    # Collapsed: draw each event with its per-note colour,
                    # matching the main view's _sti_color(ev.note) per event.
                    p.setPen(Qt.NoPen)
                    for ev in evs:
                        x1 = (ev.time - tr.time_min) / time_span * W
                        p.setBrush(QBrush(_sti_color(ev.note)))
                        p.drawEllipse(QPointF(x1, y + rh / 2), 2.0, 2.0)

        # Static border
        try:
            p.setPen(QPen(nav_border, 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(0, 0, W - 1, H - 1)
        finally:
            p.end()
        return pix

    def _paint_nav_pixmap(self) -> QPixmap:
        """Return a 260x130 minimap pixmap with the viewport indicator overlaid.

        The static background (all rows + border) is cached and only rebuilt
        when the trace, view-mode, STI visibility or expansion state changes.
        On every scroll the function just copies the cache and draws the
        orange rectangle, making per-scroll cost O(1) instead of O(segments).
        """
        W, H = _NavigatorPopup.W, _NavigatorPopup.H
        sc   = self._scene
        tr   = sc._trace

        # ---- Scrollbar metrics (needed for both bg proportions and indicator) ----
        vbar = self.verticalScrollBar() if sc._horizontal else self.horizontalScrollBar()
        v_range = vbar.maximum() - vbar.minimum()
        v_total = v_range + vbar.pageStep()

        # ---- Background cache --------------------------------------------
        bg_key = (id(tr), sc._view_mode, sc._show_sti, getattr(sc, '_is_dark_ui', True),
                  vbar.pageStep(),   # rebuilds on window resize (proportions change)
                  frozenset(sc._sti_expanded),
                  frozenset(sc._core_expanded.items()),
                  frozenset(sc._heatmap_filter_mks or ()),
                  sc._migrated_only_filter,
                  sc._task_filter_q)
        if bg_key != self._nav_bg_key or self._nav_bg_pix is None:
            self._nav_bg_pix = self._build_nav_bg(W, H, sc, tr, float(v_total))
            self._nav_bg_key = bg_key

        # Copy the cached background (Qt pixmap is copy-on-write)
        pix = QPixmap(self._nav_bg_pix)

        if tr is None:
            return pix

        # ---- Overlay: viewport indicator (orange rectangle) ---------------
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing, False)

        time_span = max(tr.time_max - tr.time_min, 1)
        # Compute the actual visible time range directly from the view geometry.
        # sc._vp_ns_lo/hi carry a 150% segment-loading margin and are set to a
        # near-full-range buffer on orientation switches - both produce a
        # misleadingly large (often full-width) indicator rectangle.
        vp_r = self.viewport().rect()
        if sc._horizontal:
            lo_coord = self.mapToScene(vp_r.topLeft()).x()
            hi_coord = self.mapToScene(vp_r.topRight()).x()
        else:
            lo_coord = self.mapToScene(vp_r.topLeft()).y()
            hi_coord = self.mapToScene(vp_r.bottomLeft()).y()
        lw = sc._label_width
        act_ns_lo = tr.time_min + int((lo_coord - lw) * sc._timescale_per_px)
        act_ns_hi = tr.time_min + int((hi_coord - lw) * sc._timescale_per_px)
        act_ns_lo = max(tr.time_min, min(tr.time_max, act_ns_lo))
        act_ns_hi = max(tr.time_min, min(tr.time_max, act_ns_hi))
        if act_ns_lo >= act_ns_hi:
            act_ns_lo, act_ns_hi = tr.time_min, tr.time_max
        vx1 = (act_ns_lo - tr.time_min) / time_span * W
        vx2 = (act_ns_hi - tr.time_min) / time_span * W

        # Thumbnail is proportional to actual view - simple linear indicator mapping.
        content_h = max(1.0, float(v_total) - RULER_HEIGHT)
        if content_h > 0 and v_range > 0:
            scroll_val = max(0.0, float(vbar.value() - vbar.minimum()) - RULER_HEIGHT)
            vy1  = scroll_val / content_h * H
            vy_h = max(1.5, vbar.pageStep() / content_h * H)
        else:
            vy1, vy_h = 0.0, float(H)

        vx1  = max(0.0, min(float(W), vx1))
        vx2  = max(0.0, min(float(W), vx2))
        vy1  = max(0.0, min(float(H), vy1))
        vy_h = min(float(H) - vy1, vy_h)

        try:
            p.setPen(QPen(QColor(255, 140, 0), 1.5))
            p.setBrush(QBrush(QColor(255, 140, 0, 35)))
            p.drawRect(QRectF(vx1, vy1, max(1.5, vx2 - vx1), max(1.5, vy_h)))
        finally:
            p.end()
        return pix

    def _show_nav(self) -> None:
        """Show the navigator popup if the viewport is scrolled while content overflows."""
        hbar = self.horizontalScrollBar()
        vbar = self.verticalScrollBar()
        h_overflow = hbar.maximum() > hbar.minimum()
        v_overflow = vbar.maximum() > vbar.minimum()
        at_fit_limit = (
            self._scene._trace is not None
            and math.isfinite(self._scene._timescale_per_px_fit)
            and self._scene._timescale_per_px >= self._scene._timescale_per_px_fit * 0.999
        )
        # In fit/full mode there may be no scrollbar overflow; keep the
        # navigator eligible to show in both task/core views for consistency.
        keep_visible_full_view = self._fit_mode or at_fit_limit
        if not (h_overflow or v_overflow or keep_visible_full_view):
            self._nav_hide_timer.stop()
            self._nav_popup.hide()
            return
        pix = self._paint_nav_pixmap()
        self._nav_popup.set_pixmap(pix)
        self._nav_popup.reposition()
        self._nav_popup.fade_in()
        # Always auto-fade after interaction; fit/full mode should not pin
        # the navigator open permanently.
        self._nav_hide_timer.start()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        """Called by Qt on every scroll - reposition frozen label-column items."""
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
        #   * Time-axis scroll (dx in horizontal view / dy in vertical view)
        #     refreshes _vp_ns_lo/hi and repopulates segments that were outside
        #     the 10 % margin used during the last rebuild.
        #   * Orthogonal scroll (row/column direction) populates rows/columns
        #     that row-culling skipped during the last rebuild.
        if dx != 0 or dy != 0:
            self._pan_timer.start()            # restart settle countdown
            # Only pump heartbeat rebuilds when the viewport is near or past
            # the cached orth/time margin; in-buffer scroll is paint-only.
            if self._needs_rebuild_for_scroll(strict=False):
                overflow = self._orth_viewport_overflow_px()
                row_stride = max(
                    self._scene._row_height + self._scene._row_gap, 1.0)
                if overflow > 0.0:
                    now_ms = time.monotonic() * 1000.0
                    min_gap = (_PAN_ORTH_URGENT_REBUILD_MS
                               if overflow > row_stride * 0.5
                               else _PAN_HEARTBEAT_MIN_REBUILD_MS)
                    if now_ms - self._last_pan_rebuild_ms >= min_gap:
                        self._last_pan_rebuild_ms = now_ms
                        self._scene.rebuild()
                    elif not self._pan_heartbeat.isActive():
                        self._pan_heartbeat.start()
                elif not self._pan_heartbeat.isActive():
                    self._pan_heartbeat.start()
            self._nav_scroll_timer.start()     # debounce minimap repaint
        if self._nav_popup.isVisible():
            self._nav_popup.reposition()

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
        self._nav_popup.reposition()
        if self._scene._trace is not None:
            self._resize_timer.start()

    def _on_resize_timeout(self) -> None:
        """Debounced resize handler.

        Fit mode  -> rebuild at the new fit zoom so the trace always fills
                    the viewport (no blank space, no scrollbar).
        Zoom mode -> timescale_per_px is NEVER touched.  Only update _timescale_per_px_fit
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
            self._show_nav()
        else:
            # Zoom mode: preserve zoom level exactly.
            self._scene._timescale_per_px_fit = new_fit
            self._reposition_frozen()
            self._reposition_frozen_top()

    def _orth_viewport_overflow_px(self) -> float:
        """How far (px) the live viewport extends past the last orth rebuild."""
        sc = self._scene
        if sc._trace is None:
            return 0.0
        vp_rect = self.viewport().rect()
        if vp_rect.width() <= 1 or vp_rect.height() <= 1:
            return 0.0
        if sc._horizontal:
            orth_lo = self.mapToScene(vp_rect.topLeft()).y()
            orth_hi = self.mapToScene(vp_rect.bottomLeft()).y()
        else:
            orth_lo = self.mapToScene(vp_rect.topLeft()).x()
            orth_hi = self.mapToScene(vp_rect.topRight()).x()
        overflow = 0.0
        if orth_lo < sc._vp_scene_orth_lo:
            overflow = max(overflow, sc._vp_scene_orth_lo - orth_lo)
        if orth_hi > sc._vp_scene_orth_hi:
            overflow = max(overflow, orth_hi - sc._vp_scene_orth_hi)
        return overflow

    def _on_pan_heartbeat(self) -> None:
        """During active scrolling: rebuild if viewport exceeds cached bounds."""
        if not self._pan_timer.isActive():
            # Settle timer already expired; stop heartbeat (no-op if also expired).
            self._pan_heartbeat.stop()
            return
        if self._scene._trace is None or self._zoom_timer.isActive():
            return
        if not self._needs_rebuild_for_scroll(strict=False):
            return
        now_ms = time.monotonic() * 1000.0
        overflow = self._orth_viewport_overflow_px()
        row_stride = max(self._scene._row_height + self._scene._row_gap, 1.0)
        min_gap = (_PAN_ORTH_URGENT_REBUILD_MS
                   if overflow > row_stride * 0.5
                   else _PAN_HEARTBEAT_MIN_REBUILD_MS)
        if now_ms - self._last_pan_rebuild_ms < min_gap:
            return
        self._last_pan_rebuild_ms = now_ms
        self._scene.rebuild()

    def _on_pan_timeout(self) -> None:
        """Final rebuild after scrolling stops."""
        self._pan_heartbeat.stop()
        if self._scene._trace is None or self._zoom_timer.isActive():
            return
        if self._needs_rebuild_for_scroll(strict=True):
            self._last_pan_rebuild_ms = time.monotonic() * 1000.0
            self._scene.rebuild()
        self._show_nav()

    def _needs_rebuild_for_scroll(self, *, strict: bool = True) -> bool:
        """Return True when current viewport exceeds the last rebuild coverage.

        The scene stores expanded time/orthogonal ranges (_vp_ns_* and
        _vp_scene_orth_*) computed at the last rebuild. During scrolling we can
        skip expensive rebuilds while the viewport remains inside those ranges.

        *strict=False* (heartbeat): require the viewport to penetrate further
        into the culling margin before triggering rebuild, and use a smaller
        time-axis hysteresis so fit-to-window vertical scroll stays cheap.
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

        time_slack = 0
        orth_slack = 0.0
        if not strict:
            span = max(self._scene._vp_ns_hi - self._scene._vp_ns_lo, 1)
            time_slack = max(int(span * 0.05), 1)
            # Prefetch rebuild ~2 rows before the orth margin edge.  The old
            # 25 % positive slack let fast vertical scroll outrun built rows.
            row_stride = max(self._scene._row_height + self._scene._row_gap, 1.0)
            orth_slack = -row_stride * 2

        # Time-axis coverage exceeded -> need rebuild to repopulate segments.
        if ns_lo < self._scene._vp_ns_lo - time_slack or ns_hi > self._scene._vp_ns_hi + time_slack:
            return True

        # Orthogonal coverage exceeded -> need rebuild to populate culled rows/cols.
        if orth_lo < self._scene._vp_scene_orth_lo - orth_slack:
            return True
        if orth_hi > self._scene._vp_scene_orth_hi + orth_slack:
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
        self.setMinimumWidth(420)

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
        _process_ui_events_safely()

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
        _process_ui_events_safely()

# ---------------------------------------------------------------------------
# Background parse thread
# ---------------------------------------------------------------------------

class _ParseThread(QThread):
    """Parses a BTF file in a background thread, emitting progress updates."""
    done     = pyqtSignal(object)   # BtfTrace
    errored  = pyqtSignal(str)
    cancelled = pyqtSignal()
    progress = pyqtSignal(int, str) # pct, message

    def __init__(self, path: str):
        super().__init__()
        self._path = path

    def run(self):
        try:
            self.done.emit(_parse_btf(
                self._path,
                progress_callback=self.progress.emit,
                cancel_check=self.isInterruptionRequested,
            ))
        except _ParseCancelledError:
            self.cancelled.emit()
        except Exception as exc:
            self.errored.emit(f"{exc}\n\n{traceback.format_exc()}")

# ---------------------------------------------------------------------------
# Cursor status-bar widget
# ---------------------------------------------------------------------------

class _CursorButton(QPushButton):
    """Status-bar cursor badge.  Click -> jumps to cursor position."""

    def __init__(self, text: str, color: str, is_dark: bool = True,
                 parent: QWidget = None):
        super().__init__(text, parent)
        self._color   = color
        self._is_dark = is_dark
        self.setStyleSheet(self._make_style(color, is_dark=is_dark))
        self.setCursor(Qt.PointingHandCursor)

    @staticmethod
    def _make_style(c: str, is_dark: bool = True) -> str:
        if is_dark:
            bg, hbg, pressed = "#2A2A2A", "#3A3A3A", "#4A4A4A"
        else:
            bg, hbg, pressed = "#F0F0F0", "#E0E0E0", "#D0D0D0"
        return (
            f"QPushButton {{ color: {c}; background: {bg}; "
            f"border: 1px solid {c}; border-right: none; "
            f"border-radius: 3px; border-top-right-radius: 0; border-bottom-right-radius: 0; "
            f"padding: 1px 7px; font-size: {UI_FONT_SIZE}pt; "
            f"font-family: \"{_get_fixed_font_family()}\"; }}"
            f"QPushButton:hover   {{ background: {hbg}; }}"
            f"QPushButton:pressed {{ background: {pressed}; }}"
        )

    def update_style(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self.setStyleSheet(self._make_style(self._color, is_dark=is_dark))

class _CursorDeleteButton(QPushButton):
    """Small x button paired with a _CursorButton to form a delete pill."""

    def __init__(self, color: str, is_dark: bool = True, parent: QWidget = None):
        super().__init__("x", parent)
        self._color   = color
        self._is_dark = is_dark
        self.setStyleSheet(self._make_style(color, is_dark=is_dark))
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(18)
        self.setToolTip("Delete cursor")

    @staticmethod
    def _make_style(c: str, is_dark: bool = True) -> str:
        if is_dark:
            bg, hbg, pressed = "#2A2A2A", "#5A1A1A", "#4A4A4A"
        else:
            bg, hbg, pressed = "#F0F0F0", "#FAEAEA", "#D0D0D0"
        return (
            f"QPushButton {{ color: {c}; background: {bg}; "
            f"border: 1px solid {c}; "
            f"border-radius: 3px; border-top-left-radius: 0; border-bottom-left-radius: 0; "
            f"padding: 1px 2px; font-size: {UI_FONT_SIZE}pt; }}"
            f"QPushButton:hover   {{ background: {hbg}; color: #FF4444; border-color: #FF4444; }}"
            f"QPushButton:pressed {{ background: {pressed}; }}"
        )

    def update_style(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self.setStyleSheet(self._make_style(self._color, is_dark=is_dark))

class _CursorBarWidget(QWidget):
    """A row of per-cursor badge+delete pills in the status bar."""
    jump_requested          = pyqtSignal(int)   # ns - scroll timeline
    cursor_delete_requested = pyqtSignal(int)   # ns - remove this cursor

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(2, 0, 2, 0)
        self._layout.setSpacing(4)
        # Each entry: (badge _CursorButton, del _CursorDeleteButton)
        self._pills: list = []
        self._delta_label: Optional[QLabel] = None
        self._is_dark: bool = True

    def update_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        for badge, del_btn in self._pills:
            badge.update_style(is_dark)
            del_btn.update_style(is_dark)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clear_layout(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._pills.clear()
        self._delta_label = None

    def _make_pill(self, orig_idx: int, t: int, color: str) -> None:
        """Create one badge+x pill and append to layout / _pills."""
        badge = _CursorButton(f"C{orig_idx + 1}", color, is_dark=self._is_dark)
        badge.setToolTip(f"C{orig_idx + 1}: click to jump to this cursor")
        del_btn = _CursorDeleteButton(color, is_dark=self._is_dark)
        # Wire up signals (ns captured per pill)
        ns_cap = t
        badge.clicked.connect(
            lambda checked=False, ns=ns_cap: self.jump_requested.emit(ns))
        del_btn.clicked.connect(
            lambda checked=False, ns=ns_cap: self.cursor_delete_requested.emit(ns))
        self._layout.addWidget(badge)
        self._layout.addWidget(del_btn)
        self._layout.setSpacing(0)   # badge and x are flush; space injected via margin
        self._pills.append((badge, del_btn))

    # ------------------------------------------------------------------

    def rebuild(self, times: list, trace) -> None:
        if not times or trace is None:
            if self._pills or self._delta_label is not None:
                self._clear_layout()
            return

        ts     = trace.time_scale
        colors = _cursor_colors(self._is_dark)
        sorted_pairs = sorted(enumerate(times), key=lambda x: x[1])

        if len(sorted_pairs) != len(self._pills):
            # Cursor count changed - full rebuild.
            self._clear_layout()
            for i, (orig_idx, t) in enumerate(sorted_pairs):
                color = colors[orig_idx % len(colors)]
                badge = _CursorButton(
                    f"C{orig_idx + 1}: {_format_time(t, ts, decimals=3)}", color,
                    is_dark=self._is_dark)
                badge.setToolTip(f"C{orig_idx + 1}: click to jump to this cursor")
                del_btn = _CursorDeleteButton(color, is_dark=self._is_dark)
                ns_cap = t
                badge.clicked.connect(
                    lambda checked=False, ns=ns_cap: self.jump_requested.emit(ns))
                del_btn.clicked.connect(
                    lambda checked=False, ns=ns_cap: self.cursor_delete_requested.emit(ns))
                self._layout.addWidget(badge)
                self._layout.addWidget(del_btn)
                if i < len(sorted_pairs) - 1:
                    spacer = QWidget()
                    spacer.setFixedWidth(4)
                    self._layout.addWidget(spacer)
                self._pills.append((badge, del_btn))

            if len(sorted_pairs) >= 2:
                delta_parts = []
                for i in range(1, len(sorted_pairs)):
                    d = sorted_pairs[i][1] - sorted_pairs[i - 1][1]
                    freq_str = f"{1e9 / d:.1f} Hz" if d > 0 else "\u221e Hz"
                    delta_parts.append(f"\u0394{i}={_format_time(d, ts, decimals=3)} ({freq_str})")
                dlbl = QLabel("   " + "   ".join(delta_parts))
                dlbl.setStyleSheet(
                    f"font-size:{UI_FONT_SIZE}pt;"
                    f" font-family:\"{_get_fixed_font_family()}\"; padding:0 4px;"
                )
                self._layout.addWidget(dlbl)
                self._delta_label = dlbl
        else:
            # Same count - update text in-place (no widget churn).
            for order, (orig_idx, t) in enumerate(sorted_pairs):
                badge, del_btn = self._pills[order]
                badge.setText(f"C{orig_idx + 1}: {_format_time(t, ts, decimals=3)}")
                badge.setToolTip(f"C{orig_idx + 1}: click to jump to this cursor")
                try:
                    badge.clicked.disconnect()
                    del_btn.clicked.disconnect()
                except RuntimeError:
                    pass
                ns_cap = t
                badge.clicked.connect(
                    lambda checked=False, ns=ns_cap: self.jump_requested.emit(ns))
                del_btn.clicked.connect(
                    lambda checked=False, ns=ns_cap: self.cursor_delete_requested.emit(ns))

            if self._delta_label is not None and len(sorted_pairs) >= 2:
                delta_parts = []
                for i in range(1, len(sorted_pairs)):
                    d = sorted_pairs[i][1] - sorted_pairs[i - 1][1]
                    freq_str = f"{1e9 / d:.1f} Hz" if d > 0 else "\u221e Hz"
                    delta_parts.append(f"\u0394{i}={_format_time(d, ts, decimals=3)} ({freq_str})")
                self._delta_label.setText("   " + "   ".join(delta_parts))

# ---------------------------------------------------------------------------
# Legend widget
# ---------------------------------------------------------------------------

class _LegendTaskRow(QWidget):
    """A single task row in the legend that emits a click signal."""

    clicked   = pyqtSignal(str)   # task merge key

    def __init__(self, task_name: str, display_name: str,
                 color: QColor, tooltip: str = "", is_dark: bool = True,
                 parent=None):
        super().__init__(parent)
        self._task_name = task_name
        self._locked    = False
        self._hovered   = False
        # Theme-variant hover BG and swatch border
        self._bg_hover = QColor(255, 255, 255, 18) if is_dark else QColor(0, 0, 0, 20)
        self._bg_locked = QColor(255, 215, 0, 45)
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
        self.setAttribute(Qt.WA_StyledBackground, False)

    def matches_filter(self, q: str) -> bool:
        """Case-insensitive filter match against merge-key or display name."""
        if not q:
            return True
        ql = q.lower()
        return (ql in self._task_name.lower()) or (ql in self._lbl.text().lower())

    def set_locked(self, locked: bool) -> None:
        """Update the visual appearance to reflect click-lock state."""
        self._locked = locked
        self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        # Paint lightweight hover/locked background without stylesheet churn.
        bg = self._bg_locked if self._locked else (self._bg_hover if self._hovered else None)
        if bg is not None:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(bg))
            p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 3, 3)
        super().paintEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._task_name)
        event.accept()   # prevent bubbling up to _LegendWidget.mousePressEvent

class _LegendWidget(QWidget):
    """Compact scrollable colour legend with click -> timeline highlight."""

    task_clicked     = pyqtSignal(str)   # click: task merge key
    cancel_highlight = pyqtSignal()      # click on background -> cancel highlight
    filter_changed   = pyqtSignal(str)   # search text changed
    migrated_filter_changed = pyqtSignal(bool)
    clear_heatmap_filter = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 0, 6)  # no right margin: lets scroll bar sit flush at edge
        outer.setSpacing(4)
        self.setObjectName("legend_root")
        self.setAutoFillBackground(True)
        self._is_dark: bool = True
        self._trace_ref = None        # cached for update_theme() rebuild
        self._show_sti_flag: bool = True
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("#1E1E1E"))
        self.setPalette(palette)
        self._task_rows: Dict[str, _LegendTaskRow] = {}   # raw name -> row widget
        self._sti_rows: List[tuple] = []  # [(channel_or_note_lc, row_widget)]
        self._heatmap_filter_mks: Optional[set] = None
        self._heatmap_filter_label: Optional[str] = None
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter tasks...")
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
        self._migrated_only_cb = QCheckBox("Migrated tasks only")
        self._migrated_only_cb.setToolTip(
            "Show only tasks that executed on two or more CPU cores")
        self._migrated_only_cb.toggled.connect(self._on_migrated_only_toggled)
        outer.addWidget(self._migrated_only_cb)

        self._heatmap_banner = QWidget()
        hb = QHBoxLayout(self._heatmap_banner)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.setSpacing(6)
        self._heatmap_banner_label = QLabel()
        self._heatmap_banner_label.setWordWrap(True)
        self._heatmap_banner_label.setStyleSheet("color:#5B9BD5; font-size:11px;")
        hb.addWidget(self._heatmap_banner_label, 1)
        self._heatmap_clear_btn = QPushButton("Clear")
        self._heatmap_clear_btn.setToolTip("Show all tasks (clear heatmap filter)")
        self._heatmap_clear_btn.clicked.connect(self.clear_heatmap_filter.emit)
        hb.addWidget(self._heatmap_clear_btn)
        self._heatmap_banner.setVisible(False)
        outer.addWidget(self._heatmap_banner)

        # Sticky-search layout: only the legend rows scroll.
        self._list_host = QWidget()
        self._list_host.setObjectName("legend_list_host")
        self._list_host.setAutoFillBackground(True)
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        self._scroll = QScrollArea()
        self._scroll.setObjectName("legend_scroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setWidget(self._list_host)
        self._scroll.viewport().setObjectName("legend_scroll_viewport")
        self._scroll.viewport().setAutoFillBackground(True)
        outer.addWidget(self._scroll, 1)

    def update_theme(self, is_dark: bool) -> None:
        """Switch the legend palette and search-box styling to match the app theme."""
        self._is_dark = is_dark
        bg = QColor("#1E1E1E") if is_dark else QColor("#F5F5F5")
        palette = self.palette()
        palette.setColor(QPalette.Window, bg)
        self.setPalette(palette)
        # Keep child surfaces explicitly in sync; otherwise some platforms keep
        # stale dark backgrounds on the scroll viewport when switching theme.
        for w in (self._list_host, self._scroll.viewport()):
            p = w.palette()
            p.setColor(QPalette.Window, bg)
            p.setColor(QPalette.Base, bg)
            w.setPalette(p)
        self._scroll.setStyleSheet(
            f"QScrollArea#legend_scroll {{ background:{bg.name()}; border:none; }}"
            f"QWidget#legend_scroll_viewport {{ background:{bg.name()}; }}"
            f"QWidget#legend_list_host {{ background:{bg.name()}; }}"
        )
        _fs = f"{getattr(QApplication.instance(), '_ui_font_size_val', UI_FONT_SIZE)}pt"
        if is_dark:
            self._search.setStyleSheet(
                f"QLineEdit {{ background:#2D2D2D; color:#D4D4D4; border:1px solid #555; "
                f"border-radius:3px; padding:2px 4px; font-size:{_fs}; }}"
            )
        else:
            self._search.setStyleSheet(
                f"QLineEdit {{ background:#FFFFFF; color:#1E1E1E; border:1px solid #AAAAAA; "
                f"border-radius:3px; padding:2px 4px; font-size:{_fs}; }}"
            )
        if self._trace_ref is not None:
            self.rebuild(self._trace_ref, show_sti=self._show_sti_flag)

    def set_locked_task(self, task_name: Optional[str]) -> None:
        """Visually mark *task_name* as click-locked (or clear all locks)."""
        for raw, row in self._task_rows.items():
            is_match = (raw == task_name)
            row.set_locked(is_match)
            if is_match:
                self._scroll.ensureWidgetVisible(row)

    def set_heatmap_filter(self, label: Optional[str],
                           merge_keys: Optional[set]) -> None:
        """Show banner and limit legend rows to heatmap drill-down selection."""
        self._heatmap_filter_label = label
        self._heatmap_filter_mks = set(merge_keys) if merge_keys else None
        active = self._heatmap_filter_mks is not None
        self._heatmap_banner.setVisible(active)
        if active:
            n = len(self._heatmap_filter_mks)
            self._heatmap_banner_label.setText(
                f"Heatmap: {label or 'filtered'} ({n})")
        self._filter_tasks(self._search.text())

    def set_migrated_only_checked(self, checked: bool) -> None:
        """Set migrated-only checkbox without re-emitting toggled signal."""
        self._migrated_only_cb.blockSignals(True)
        self._migrated_only_cb.setChecked(bool(checked))
        self._migrated_only_cb.blockSignals(False)

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

            tint_lbl = QLabel(self._core_tint_legend_html(is_dark))
            tint_lbl.setTextFormat(Qt.RichText)
            tint_lbl.setWordWrap(True)
            self._list_layout.addWidget(tint_lbl)

            # trace.tasks contains merge keys; task_repr maps each to its raw name.
            for _mk in trace.tasks:
                _rep_raw = trace.task_repr.get(_mk, _mk)
                color = _task_color(_rep_raw)
                display = _task_display_name(_rep_raw)
                row = _LegendTaskRow(_mk, display, color, tooltip=_rep_raw, is_dark=is_dark)
                row.clicked.connect(self.task_clicked)
                self._task_rows[_mk] = row
                self._list_layout.addWidget(row)

            # Legend is task-only by design: STI events are not listed here.

            self._list_layout.addStretch()
            self._filter_tasks(self._search.text())
        finally:
            self.setUpdatesEnabled(True)

    def _on_migrated_only_toggled(self, checked: bool) -> None:
        self.migrated_filter_changed.emit(bool(checked))
        self._filter_tasks(self._search.text())

    def _on_search_text_changed(self, text: str) -> None:
        """Apply legend filter immediately, debounce expensive timeline rebuild."""
        self._filter_tasks(text)
        self._filter_emit_timer.start()

    def _filter_tasks(self, text: str) -> None:
        """Show / hide task and STI rows in the legend based on the search filter."""
        q = text.strip().lower()
        trace = self._trace_ref
        for mk, row in self._task_rows.items():
            visible = row.matches_filter(q)
            if visible and self._heatmap_filter_mks is not None:
                visible = mk in self._heatmap_filter_mks
            if visible and self._migrated_only_cb.isChecked() and trace is not None:
                visible = _is_migrated_task(trace, mk)
            row.setVisible(visible)
        for key_lc, row_w in self._sti_rows:
            row_w.setVisible((not q) or (q in key_lc))

    @staticmethod
    def _core_tint_legend_html(is_dark: bool) -> str:
        lines = ["<b>Core tints (Task View)</b>"]
        tint_desc = {
            "Core_0": "base colour",
            "Core_1": "blue tint",
            "Core_2": "green tint",
            "Core_3": "red tint",
        }
        for core, desc in tint_desc.items():
            col = _core_color(core)
            lines.append(
                f"<span style='color:{col};'>\u25a0</span> {core}: {desc}")
        lines.append("<span style='color:#888888;'>\u25a0</span> Core_4+: grey tint")
        color = "#AAAAAA" if is_dark else "#555555"
        return f"<span style='color:{color}; font-size:8pt;'>" + "<br>".join(lines) + "</span>"

# ===========================================================================
# Metrics Plot Dialog
# ===========================================================================

class _ScatterWidget(QWidget):
    """Scatter plot: X = trace timestamp, Y = metric value.  Click a point to jump."""

    point_clicked = pyqtSignal(object)   # payload: TaskSegment (exec) or int ns (inter-arrival)

    def __init__(self, points, time_scale: str, color: "QColor",
                 is_dark: bool, parent=None) -> None:
        super().__init__(parent)
        # points: List[(x_ns, y_value, payload)]
        # payload is either a TaskSegment (exec) or int (ns, inter-arrival)
        self._points     = points
        self._time_scale = time_scale
        self._color      = color
        self._is_dark    = is_dark
        self._highlight  = -1   # index of highlighted point (-1 = none)
        self._hover_idx  = -1   # index of hovered point for tooltip
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)

    def set_points(self, points: list) -> None:
        """Replace plotted points and repaint (live cursor-range updates)."""
        self._points = list(points)
        if self._highlight >= len(self._points):
            self._highlight = -1
        if self._hover_idx >= len(self._points):
            self._hover_idx = -1
        self.update()

    def set_dark(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self.update()

    def _screen_coords(self, w: int, h: int, ml: int, mr: int, mt: int, mb: int):
        """Return (sx_list, sy_list) mapping each point to widget pixels."""
        if not self._points:
            return [], []
        xs = [p[0] for p in self._points]
        ys = [p[1] for p in self._points]
        x0, x1 = min(xs), max(xs)
        y0, y1 = 0, max(ys) if max(ys) > 0 else 1
        xspan = max(x1 - x0, 1)
        yspan = max(y1 - y0, 1)
        pw = w - ml - mr
        ph = h - mt - mb
        sx = [ml + int((x - x0) / xspan * pw) for x in xs]
        sy = [mt + ph - int((y - y0) / yspan * ph) for y in ys]
        return sx, sy

    @staticmethod
    def _marker_right_margin(fm) -> int:
        return max(14, max(fm.horizontalAdvance(lbl) for lbl in ("avg", "p50", "p95")) + 12)

    def paintEvent(self, event) -> None:  # noqa: N802
        w, h = self.width(), self.height()
        ML, MT, MB = 56, 14, 36   # margins

        dark  = self._is_dark
        bg    = QColor("#1E1E1E") if dark else QColor("#F8F8F8")
        grid  = QColor("#2E2E2E") if dark else QColor("#E0E0E0")
        txt   = QColor("#AAAAAA") if dark else QColor("#555555")
        axln  = QColor("#555555") if dark else QColor("#AAAAAA")

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(0, 0, w, h, bg)

        if not self._points:
            p.setPen(txt)
            p.drawText(QRect(0, 0, w, h), Qt.AlignCenter, "No data in selected range")
            p.end()
            return

        xs = [pt[0] for pt in self._points]
        ys = [pt[1] for pt in self._points]
        x0, x1 = min(xs), max(xs)
        y0, y1 = 0, max(ys) if ys else 1
        xspan = max(x1 - x0, 1)
        yspan = max(y1 - y0, 1)

        def sx(x): return ML + int((x - x0) / xspan * pw)
        def sy(y): return MT + ph - int((y - y0) / yspan * ph)

        # Grid + axes
        sf = QFont(); sf.setPointSize(7)
        p.setFont(sf)
        MR = self._marker_right_margin(p.fontMetrics())
        pw = w - ML - MR
        ph = h - MT - MB
        p.setPen(QPen(grid, 1, Qt.DotLine))
        for fi in range(5):
            gy = MT + int(fi / 4 * ph)
            p.drawLine(ML, gy, ML + pw, gy)
        p.setPen(QPen(axln, 1))
        p.drawLine(ML, MT, ML, MT + ph)
        p.drawLine(ML, MT + ph, ML + pw, MT + ph)

        # Y-axis labels
        p.setPen(txt)
        vals_sorted = sorted(ys)
        n = len(vals_sorted)
        p50_val = vals_sorted[min(n - 1, int(n * 0.50))]
        avg_val = sum(ys) / len(ys) if ys else 0
        p95_val = vals_sorted[min(n - 1, int(n * 0.95))]
        for fi in range(5):
            val = y0 + (y1 - y0) * fi / 4
            gy  = MT + ph - int(fi / 4 * ph)
            lbl = _format_time(int(val), self._time_scale, decimals=1)
            p.drawText(QRect(0, gy - 8, ML - 4, 16), Qt.AlignRight | Qt.AlignVCenter, lbl)

        # X-axis labels (3 ticks)
        for fi in range(3):
            val = x0 + xspan * fi / 2
            gx  = sx(val)
            lbl = _format_time(int(val), self._time_scale, decimals=1)
            p.drawText(QRect(gx - 40, MT + ph + 4, 80, 16),
                       Qt.AlignHCenter | Qt.AlignTop, lbl)

        # avg / p50 / p95 horizontal reference lines
        for val, lbl_text, ref_color in [
            (avg_val, "avg", QColor("#CE93D8")),
            (p50_val, "p50", QColor("#4CAF50")),
            (p95_val, "p95", QColor("#FF9800")),
        ]:
            gy = sy(val)
            p.setPen(QPen(ref_color, 1, Qt.DashLine))
            p.drawLine(ML, gy, ML + pw, gy)
            p.setPen(ref_color)
            p.setFont(sf)
            p.drawText(ML + pw + 2, gy + 4, lbl_text)

        # Points
        dot_color = QColor(self._color)
        dot_color.setAlpha(200)
        hl_color  = QColor("#FFFFFF")
        p.setPen(Qt.NoPen)
        for i, pt in enumerate(self._points):
            cx = sx(pt[0])
            cy = sy(pt[1])
            if i == self._highlight:
                p.setBrush(QBrush(hl_color))
                p.drawEllipse(cx - 5, cy - 5, 10, 10)
            else:
                p.setBrush(QBrush(dot_color))
                p.drawEllipse(cx - 3, cy - 3, 6, 6)

        # Hover tooltip
        if self._hover_idx >= 0 and self._hover_idx < len(self._points):
            hpt = self._points[self._hover_idx]
            line1 = _format_time(int(hpt[1]), self._time_scale)
            line2 = "@ " + _format_time(int(hpt[0]), self._time_scale)
            tf = QFont(); tf.setPointSize(8)
            p.setFont(tf)
            fm = p.fontMetrics()
            tw = max(fm.horizontalAdvance(line1), fm.horizontalAdvance(line2))
            th = fm.height() * 2 + 6
            pad = 6
            bw_ = tw + pad * 2
            bh_ = th + pad * 2
            hx = sx(hpt[0])
            hy = sy(hpt[1])
            bx = hx + 10
            by = hy - bh_ // 2
            if bx + bw_ > w - 2:
                bx = hx - bw_ - 10
            if by < 2:
                by = 2
            if by + bh_ > h - 2:
                by = h - bh_ - 2
            bg2 = QColor("#2A2A2A") if dark else QColor("#F0F0F0")
            bg2.setAlpha(230)
            border_c = QColor("#555555") if dark else QColor("#BBBBBB")
            p.setBrush(QBrush(bg2))
            p.setPen(QPen(border_c, 1))
            p.drawRoundedRect(bx, by, bw_, bh_, 4, 4)
            p.setPen(QColor("#EEEEEE") if dark else QColor("#222222"))
            p.drawText(bx + pad, by + pad + fm.ascent(), line1)
            p.setPen(QColor("#AAAAAA") if dark else QColor("#666666"))
            p.drawText(bx + pad, by + pad + fm.height() + fm.ascent(), line2)

        p.end()

    def _nearest_point(self, ex: int, ey: int, threshold: int = 12):
        """Return (distance_sq, index) of the nearest scatter point within threshold px."""
        if not self._points:
            return float("inf"), -1
        w, h = self.width(), self.height()
        ML, MT, MB = 56, 14, 36
        xs = [p[0] for p in self._points]
        ys = [p[1] for p in self._points]
        x0, x1 = min(xs), max(xs)
        y1 = max(ys) if ys else 1
        sf = QFont(); sf.setPointSize(7)
        MR = self._marker_right_margin(QFontMetrics(sf))
        pw = w - ML - MR
        ph = h - MT - MB
        def sx(x): return ML + int((x - x0) / max(x1 - x0, 1) * pw)
        def sy(y): return MT + ph - int(y / max(y1, 1) * ph)
        best_d, best_i = float("inf"), -1
        for i, pt in enumerate(self._points):
            dx = sx(pt[0]) - ex
            dy = sy(pt[1]) - ey
            d  = dx * dx + dy * dy
            if d < best_d:
                best_d, best_i = d, i
        if best_d <= threshold * threshold:
            return best_d, best_i
        return float("inf"), -1

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        _, idx = self._nearest_point(event.x(), event.y(), threshold=12)
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover_idx != -1:
            self._hover_idx = -1
            self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton or not self._points:
            return
        _, best_i = self._nearest_point(event.x(), event.y(), threshold=8)

        if best_i >= 0:
            self._highlight = best_i
            self.update()
            self.point_clicked.emit(self._points[best_i])

class _HistogramWidget(QWidget):
    """Histogram of metric values with p50/p95 markers."""

    def __init__(self, values, time_scale: str, color: "QColor",
                 is_dark: bool, parent=None) -> None:
        super().__init__(parent)
        self._values     = sorted(values)
        self._time_scale = time_scale
        self._color      = color
        self._is_dark    = is_dark
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_values(self, values: list) -> None:
        """Replace histogram samples and repaint."""
        self._values = sorted(values)
        self.update()

    def set_dark(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        N_BINS = 50
        w, h  = self.width(), self.height()
        ML, MT, MB = 56, 14, 36

        dark = self._is_dark
        bg   = QColor("#1E1E1E") if dark else QColor("#F8F8F8")
        grid = QColor("#2E2E2E") if dark else QColor("#E0E0E0")
        txt  = QColor("#AAAAAA") if dark else QColor("#555555")
        axln = QColor("#555555") if dark else QColor("#AAAAAA")

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.fillRect(0, 0, w, h, bg)

        if not self._values:
            p.setPen(txt)
            p.drawText(QRect(0, 0, w, h), Qt.AlignCenter, "No data in selected range")
            p.end()
            return

        vals = self._values
        n    = len(vals)
        v0, v1 = vals[0], vals[-1]
        vspan  = max(v1 - v0, 1)
        p50 = vals[min(n - 1, int(n * 0.50))]
        avg = sum(vals) / n if n else 0
        p95 = vals[min(n - 1, int(n * 0.95))]

        # Build bins
        bin_w_val = vspan / N_BINS
        counts    = [0] * N_BINS
        for v in vals:
            bi = min(N_BINS - 1, int((v - v0) / bin_w_val))
            counts[bi] += 1
        max_count = max(counts) if counts else 1

        sf = QFont(); sf.setPointSize(7)
        p.setFont(sf)
        fm = p.fontMetrics()
        marker_labels = ("avg", "p50", "p95")
        MR = max(14, max(fm.horizontalAdvance(lbl) for lbl in marker_labels) + 10)
        pw = w - ML - MR
        ph = h - MT - MB
        bw = max(1, pw // N_BINS)

        # Grid
        p.setPen(QPen(grid, 1, Qt.DotLine))
        for fi in (1, 2, 3, 4):
            gy = MT + int((1 - fi / 4) * ph)
            p.drawLine(ML, gy, ML + pw, gy)
        p.setPen(QPen(axln, 1))
        p.drawLine(ML, MT, ML, MT + ph)
        p.drawLine(ML, MT + ph, ML + pw, MT + ph)

        # Y labels
        p.setPen(txt)
        for fi in range(5):
            cnt = int(max_count * fi / 4)
            gy  = MT + ph - int(fi / 4 * ph)
            p.drawText(QRect(0, gy - 8, ML - 4, 16), Qt.AlignRight | Qt.AlignVCenter, str(cnt))

        # X labels (3)
        for fi in range(3):
            val = v0 + vspan * fi / 2
            gx  = ML + int(fi / 2 * pw)
            lbl = _format_time(int(val), self._time_scale, decimals=1)
            p.drawText(QRect(gx - 40, MT + ph + 4, 80, 16),
                       Qt.AlignHCenter | Qt.AlignTop, lbl)

        # Bars
        bar_color = QColor(self._color); bar_color.setAlpha(180)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(bar_color))
        for bi, cnt in enumerate(counts):
            if cnt == 0:
                continue
            bx = ML + int(bi * pw / N_BINS)
            bh = int(cnt / max_count * ph)
            p.drawRect(bx, MT + ph - bh, max(1, bw - 1), bh)

        # avg / p50 / p95 vertical lines
        p.setRenderHint(QPainter.Antialiasing, True)
        for val, lbl_text, lcolor in [
            (avg, marker_labels[0], QColor("#CE93D8")),
            (p50, marker_labels[1], QColor("#4CAF50")),
            (p95, marker_labels[2], QColor("#FF9800")),
        ]:
            gx = ML + int((val - v0) / vspan * pw)
            p.setPen(QPen(lcolor, 2, Qt.DashLine))
            p.drawLine(gx, MT, gx, MT + ph)
            p.setPen(lcolor)
            p.setFont(sf)
            p.drawText(gx + 3, MT + 12, lbl_text)

        p.end()

class _MetricsPlotDialog(QDialog):
    """Modeless popup: scatter plot + histogram for one task metric.

    ``points``  - List of (x_ns, y_value, payload) where payload is
                  a TaskSegment (exec) or int (inter-arrival start ns).
    ``on_point_click`` - called with the trace-ns when a scatter point is clicked.
    """

    closed = pyqtSignal()

    def __init__(self, title: str,
                 points,
                 time_scale: str,
                 color: "QColor",
                 on_point_click,
                 is_dark: bool,
                 scope_scoped: bool,
                 scope_badge: str,
                 scope_detail: str,
                 parent=None) -> None:
        super().__init__(parent, Qt.Window)
        self._title        = title
        self._is_dark      = is_dark
        self._on_pt_click  = on_point_click
        self.setWindowTitle(title)
        self.resize(820, 620)
        self.setMinimumSize(500, 400)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(4)

        self._scope_banner = QLabel()
        self._scope_banner.setWordWrap(True)
        self._scope_scoped = scope_scoped
        self._scope_badge = scope_badge
        self._scope_detail = scope_detail
        root.addWidget(self._scope_banner)
        self._set_scope_banner(scope_scoped, scope_badge, scope_detail)

        # Content area (scatter + histogram) - grabbed for PNG/SVG export
        self._content = QWidget()
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(4)

        values = [pt[1] for pt in points]
        self._scatter = _ScatterWidget(points, time_scale, color, is_dark)
        self._histogram = _HistogramWidget(values, time_scale, color, is_dark)

        self._scatter.point_clicked.connect(self._on_scatter_click)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self._scatter)
        splitter.addWidget(self._histogram)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        cl.addWidget(splitter)

        root.addWidget(self._content, 1)

        # Button bar
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 4, 0, 0)
        btn_png = QPushButton("Export PNG")
        btn_svg = QPushButton("Export SVG")
        btn_cls = QPushButton("Close")
        btn_png.clicked.connect(self._export_png)
        btn_svg.clicked.connect(self._export_svg)
        btn_cls.clicked.connect(self.close)
        btn_row.addWidget(btn_png)
        btn_row.addWidget(btn_svg)
        btn_row.addStretch()
        btn_row.addWidget(btn_cls)
        root.addLayout(btn_row)

    def _set_scope_banner(self, scoped: bool, badge: str, detail: str) -> None:
        """Show a high-contrast banner indicating cursor-range vs full-trace scope."""
        if scoped:
            if self._is_dark:
                bg, border, badge_bg, badge_fg, detail_fg = (
                    "#4E342E", "#FF9800", "#FF9800", "#1A1200", "#FFE0B2")
            else:
                bg, border, badge_bg, badge_fg, detail_fg = (
                    "#FFF3E0", "#F57C00", "#FF9800", "#1A1200", "#5D4037")
        else:
            if self._is_dark:
                bg, border, badge_bg, badge_fg, detail_fg = (
                    "#263238", "#78909C", "#546E7A", "#ECEFF1", "#B0BEC5")
            else:
                bg, border, badge_bg, badge_fg, detail_fg = (
                    "#ECEFF1", "#90A4AE", "#CFD8DC", "#37474F", "#546E7A")
        self._scope_banner.setText(
            f'<span style="background:{badge_bg}; color:{badge_fg}; font-weight:700; '
            f'padding:2px 8px; border-radius:3px; letter-spacing:0.5px;">'
            f'{badge.upper()}</span>&nbsp;&nbsp;'
            f'<span style="color:{detail_fg};">{detail}</span>')
        self._scope_banner.setStyleSheet(
            f"background:{bg}; border-left:4px solid {border}; "
            f"padding:8px 12px; border-radius:4px;")

    def update_data(self, title: str, points: list,
                    *, scope_scoped: bool, scope_badge: str,
                    scope_detail: str) -> None:
        """Refresh scatter + histogram when cursor range or scope changes."""
        self._title = title
        self.setWindowTitle(title)
        self._scope_scoped = scope_scoped
        self._scope_badge = scope_badge
        self._scope_detail = scope_detail
        self._set_scope_banner(scope_scoped, scope_badge, scope_detail)
        self._scatter.set_points(points)
        self._histogram.set_values([p[1] for p in points])

    def closeEvent(self, event) -> None:  # noqa: N802
        self.closed.emit()
        super().closeEvent(event)

    def set_dark(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._scatter.set_dark(is_dark)
        self._histogram.set_dark(is_dark)
        self._set_scope_banner(self._scope_scoped, self._scope_badge, self._scope_detail)
        self._content.update()
        self.update()

    def _on_scatter_click(self, pt) -> None:
        if self._on_pt_click and pt:
            self._on_pt_click(pt[0], pt[1], pt[2])

    def _export_png(self) -> None:
        pixmap = self._content.grab()
        dlg = SnapshotEditorDialog(pixmap, self)
        _exec_centred(dlg, self)

    def _export_svg(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export SVG",
            self._title.replace(" ", "_").replace("-", "-") + ".svg",
            "SVG files (*.svg);;All files (*)",
        )
        if not path:
            return
        try:
            sz  = self._content.size()
            gen = QSvgGenerator()
            gen.setFileName(path)
            gen.setSize(sz)
            gen.setViewBox(QRectF(0, 0, sz.width(), sz.height()))
            gen.setTitle(self._title)
            gen.setDescription("Generated by RTOS BTF Viewer")
            painter = QPainter(gen)
            try:
                self._content.render(painter)
            finally:
                painter.end()
        except (OSError, RuntimeError) as exc:
            QMessageBox.critical(self, "SVG Export Error", str(exc))

# ---------------------------------------------------------------------------
# Statistics dock panel
# ---------------------------------------------------------------------------

class _StatsHoverRow(QWidget):
    """Progress-bar stat row that highlights on mouse-over."""

    def __init__(self, is_dark: bool, on_click=None, parent=None) -> None:
        super().__init__(parent)
        self._on_click = on_click
        self._hover_bg = "#3A3A50" if is_dark else "#E0E0EC"
        self._hovered = False
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        if on_click is not None:
            self.setCursor(Qt.PointingHandCursor)

    def _apply_hover(self, hovered: bool) -> None:
        if hovered == self._hovered:
            return
        self._hovered = hovered
        if hovered:
            self.setStyleSheet(
                f"background-color: {self._hover_bg}; border-radius: 2px;")
        else:
            self.setStyleSheet("background: transparent; border-radius: 2px;")

    def track_widget(self, w: QWidget) -> None:
        """Track *w* so hover works when the pointer is over child controls."""
        w.setMouseTracking(True)
        w.installEventFilter(self)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._apply_hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._apply_hover(False)
        super().leaveEvent(event)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        et = event.type()
        if et in (QEvent.Enter, QEvent.HoverEnter):
            self._apply_hover(True)
        elif et in (QEvent.Leave, QEvent.HoverLeave):
            QTimer.singleShot(0, self._sync_hover)
        elif (et == QEvent.MouseButtonPress and event.button() == Qt.LeftButton
              and self._on_click is not None):
            self._on_click()
            return True
        return False

    def _sync_hover(self) -> None:
        self._apply_hover(self.underMouse())

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._on_click is not None:
            self._on_click()
            event.accept()
            return
        super().mousePressEvent(event)

class _StatsTableHoverFilter(QObject):
    """Clear stats-table row hover highlight when the pointer leaves the table."""

    def __init__(self, clear_fn) -> None:
        super().__init__()
        self._clear_fn = clear_fn

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Leave:
            self._clear_fn()
        return False

class _StatsSortItem(QTableWidgetItem):
    """Table cell that sorts by an explicit key (numeric/time) instead of display text."""

    def __init__(self, text, sort_key=None) -> None:
        super().__init__(str(text))
        self._sort_key = sort_key if sort_key is not None else str(text).lower()

    def __lt__(self, other) -> bool:  # noqa: N802
        if isinstance(other, _StatsSortItem):
            a, b = self._sort_key, other._sort_key
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                return a < b
            return str(a).lower() < str(b).lower()
        return super().__lt__(other)

class _StatsSectionGrip(QWidget):
    """Horizontal drag handle below a stats table to adjust its max height."""

    height_changed = pyqtSignal(int)

    _MIN_H = 80
    _MAX_H = 480

    def __init__(self, is_dark: bool, get_height_fn, parent=None) -> None:
        super().__init__(parent)
        self._is_dark = is_dark
        self._get_height = get_height_fn
        self._dragging = False
        self._start_y = 0
        self._start_h = STATS_TABLE_DEFAULT_H
        self.setFixedHeight(8)
        self.setCursor(Qt.SizeVerCursor)
        self.setToolTip("Drag to resize table height")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)

    def set_dark(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._start_y = int(event.globalY())
            self._start_h = self._get_height()
            self.grabMouse()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging:
            delta = int(event.globalY()) - self._start_y
            self.height_changed.emit(
                max(self._MIN_H, min(self._MAX_H, self._start_h + delta)))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            if self.mouseGrabber() is self:
                self.releaseMouse()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        p = QPainter(self)
        c = QColor("#6688CC" if self.underMouse()
                   else ("#555568" if self._is_dark else "#BBBBBB"))
        y = self.height() // 2
        p.setPen(QPen(c, 2))
        p.drawLine(4, y, self.width() - 4, y)
        p.end()

class _TraceCompareDialog(QDialog):
    """Compare summary, top tasks, and core migrations between two open trace tabs."""

    def __init__(self, win: "MainWindow", parent=None) -> None:
        super().__init__(parent or win)
        self.setWindowTitle("Trace Compare")
        self.setModal(True)
        self.resize(760, 480)
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Trace A:"))
        self._combo_a = QComboBox()
        row.addWidget(self._combo_a, 1)
        row.addWidget(QLabel("Trace B:"))
        self._combo_b = QComboBox()
        row.addWidget(self._combo_b, 1)
        lay.addLayout(row)

        self._scope_cb = QCheckBox(
            "Limit to each tab's cursor range (C1–Cn, when 2+ cursors placed)")
        lay.addWidget(self._scope_cb)

        self._pages = QTabWidget()
        self._summary_table = QTableWidget(0, 4)
        self._summary_table.setHorizontalHeaderLabels(
            ["Metric", "Trace A", "Trace B", "Δ"])
        self._top_table = QTableWidget(0, 4)
        self._top_table.setHorizontalHeaderLabels(
            ["Task", "CPU% A", "CPU% B", "Δ"])
        self._mig_table = QTableWidget(0, 6)
        self._mig_table.setHorizontalHeaderLabels(
            ["Task", "Migrations A", "Migrations B", "Δ", "Ping-pong A", "Ping-pong B"])
        for tbl in (self._summary_table, self._top_table, self._mig_table):
            tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
            tbl.verticalHeader().setVisible(False)
            tbl.horizontalHeader().setStretchLastSection(True)
        self._pages.addTab(self._summary_table, "Summary")
        self._pages.addTab(self._top_table, "Top Tasks")
        self._pages.addTab(self._mig_table, "Core Migrations")
        lay.addWidget(self._pages, 1)

        exp_row = QHBoxLayout()
        exp_row.setContentsMargins(8, 6, 8, 8)
        exp_row.setSpacing(8)
        _ic = "#9E9E9E"
        self._btn_export_csv = QPushButton("Export CSV")
        self._btn_export_csv.setIcon(_svg_icon(_IC_EXPORT_CSV, _ic))
        self._btn_export_csv.setToolTip("Export compare tables as CSV")
        self._btn_export_csv.clicked.connect(self._export_csv)
        exp_row.addWidget(self._btn_export_csv)
        self._btn_export_html = QPushButton("Export HTML")
        self._btn_export_html.setIcon(_svg_icon_markup(
            '<rect x="2.5" y="2" width="11" height="12" rx="1" fill="none" '
            f'stroke="{_ic}" stroke-width="1.2"/>'
            '<path d="M5.5 6.5 3.5 8.5l2 2M10.5 6.5l2 2-2 2" fill="none" '
            f'stroke="{_ic}" stroke-width="1.2" stroke-linecap="round"/>',
        ))
        self._btn_export_html.setToolTip("Export compare report as HTML")
        self._btn_export_html.clicked.connect(self._export_html)
        exp_row.addWidget(self._btn_export_html)
        exp_row.addStretch(1)
        lay.addLayout(exp_row)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        lay.addWidget(btns)
        self._win = win
        for i, tab in enumerate(win._tabs):
            label = os.path.basename(tab.path)
            self._combo_a.addItem(label, i)
            self._combo_b.addItem(label, i)
        if win._tabs:
            self._combo_b.setCurrentIndex(min(1, len(win._tabs) - 1))
        self._combo_a.currentIndexChanged.connect(self._refresh)
        self._combo_b.currentIndexChanged.connect(self._refresh)
        self._scope_cb.toggled.connect(self._refresh)
        self._refresh()

    def _range_for_trace(self, combo: QComboBox) -> Tuple[Optional[int], Optional[int]]:
        if not self._scope_cb.isChecked():
            return None, None
        idx = combo.currentData()
        if idx is None:
            return None, None
        return _cursor_range_for_tab(self._win, idx)

    def _trace_for_combo(self, combo: QComboBox) -> Optional[BtfTrace]:
        idx = combo.currentData()
        if idx is None or idx < 0 or idx >= len(self._win._tabs):
            return None
        return self._win._tabs[idx].trace

    @staticmethod
    def _fill_table(table: QTableWidget, rows: List[List], left_cols: int = 1) -> None:
        table.setRowCount(len(rows))
        for ri, vals in enumerate(rows):
            for ci, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                if ci < left_cols:
                    item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                else:
                    item.setTextAlignment(Qt.AlignVCenter | Qt.AlignRight)
                table.setItem(ri, ci, item)

    def _refresh(self) -> None:
        ta = self._trace_for_combo(self._combo_a)
        tb = self._trace_for_combo(self._combo_b)
        self._refresh_summary(ta, tb)
        self._refresh_top_tasks(ta, tb)
        self._refresh_migrations(ta, tb)

    def _refresh_summary(self, ta: Optional[BtfTrace], tb: Optional[BtfTrace]) -> None:
        if ta is None or tb is None:
            self._summary_table.setRowCount(0)
            return
        lo_a, hi_a = self._range_for_trace(self._combo_a)
        lo_b, hi_b = self._range_for_trace(self._combo_b)
        a = _trace_summary_snapshot(ta, lo_a, hi_a)
        b = _trace_summary_snapshot(tb, lo_b, hi_b)
        scale = a["time_scale"]
        rows = [
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
        self._fill_table(self._summary_table, rows)

    def _refresh_top_tasks(self, ta: Optional[BtfTrace], tb: Optional[BtfTrace]) -> None:
        lo_a, hi_a = self._range_for_trace(self._combo_a)
        lo_b, hi_b = self._range_for_trace(self._combo_b)
        map_a = _top_tasks_cpu_by_name(ta, lo=lo_a, hi=hi_a) if ta else {}
        map_b = _top_tasks_cpu_by_name(tb, lo=lo_b, hi=hi_b) if tb else {}
        names = sorted(set(map_a) | set(map_b),
                       key=lambda n: (-max(map_a.get(n, 0.0), map_b.get(n, 0.0)), n.lower()))
        rows: List[List] = []
        for name in names:
            pa = map_a.get(name)
            pb = map_b.get(name)
            a_val = pa if pa is not None else 0.0
            b_val = pb if pb is not None else 0.0
            rows.append([
                name,
                f"{pa:.1f}" if pa is not None else "—",
                f"{pb:.1f}" if pb is not None else "—",
                _fmt_signed_pct_delta(a_val - b_val),
            ])
        self._fill_table(self._top_table, rows)

    def _refresh_migrations(self, ta: Optional[BtfTrace], tb: Optional[BtfTrace]) -> None:
        lo_a, hi_a = self._range_for_trace(self._combo_a)
        lo_b, hi_b = self._range_for_trace(self._combo_b)
        rows_a = {r[0]: r for r in (_migration_rows(ta, lo_a, hi_a) if ta else [])}
        rows_b = {r[0]: r for r in (_migration_rows(tb, lo_b, hi_b) if tb else [])}
        keys = sorted(set(rows_a) | set(rows_b),
                      key=lambda k: rows_a.get(k, rows_b.get(k))[1].lower())
        mig_rows: List[List] = []
        for mk in keys:
            ra = rows_a.get(mk)
            rb = rows_b.get(mk)
            name = (ra or rb)[1]
            ma = ra[2] if ra else 0
            mb = rb[2] if rb else 0
            pa = ra[7] if ra else 0
            pb = rb[7] if rb else 0
            mig_rows.append([name, ma, mb, ma - mb, pa, pb])
        self._fill_table(self._mig_table, mig_rows)

    def _tab_name(self, combo: QComboBox) -> str:
        return combo.currentText() or "Trace"

    def _export_csv(self) -> None:
        ta = self._trace_for_combo(self._combo_a)
        tb = self._trace_for_combo(self._combo_b)
        if ta is None or tb is None:
            QMessageBox.warning(self, "Export CSV", "Select two loaded traces to export.")
            return

        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Trace Compare CSV",
            f"trace-compare-{stamp}.csv",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return

        text = _build_compare_csv(
            self._tab_name(self._combo_a),
            self._tab_name(self._combo_b),
            self._scope_cb.isChecked(),
            _table_widget_rows(self._summary_table),
            _table_widget_rows(self._top_table),
            _table_widget_rows(self._mig_table),
        )
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                fh.write(text)
        except OSError as exc:
            QMessageBox.critical(self, "Export Error", f"Could not export CSV:\n{exc}")
            return

        wnd = self.window()
        if isinstance(wnd, QMainWindow):
            wnd.statusBar().showMessage(f"Exported trace compare: {path}", 4000)

    def _export_html(self) -> None:
        ta = self._trace_for_combo(self._combo_a)
        tb = self._trace_for_combo(self._combo_b)
        if ta is None or tb is None:
            QMessageBox.warning(self, "Export HTML", "Select two loaded traces to export.")
            return

        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Trace Compare HTML",
            f"trace-compare-{stamp}.html",
            "HTML files (*.html);;All files (*)",
        )
        if not path:
            return

        report = _build_compare_html(
            self._tab_name(self._combo_a),
            self._tab_name(self._combo_b),
            self._scope_cb.isChecked(),
            _table_widget_rows(self._summary_table),
            _table_widget_rows(self._top_table),
            _table_widget_rows(self._mig_table),
        )
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(report)
        except OSError as exc:
            QMessageBox.critical(self, "Export Error", f"Could not export HTML:\n{exc}")
            return

        wnd = self.window()
        if isinstance(wnd, QMainWindow):
            wnd.statusBar().showMessage(f"Exported trace compare: {path}", 4000)

class _MigrationHeatmapWidget(QWidget):
    """Paint labelled rows × time-bin migration counts (pairs or core×core matrix)."""

    cell_clicked = pyqtSignal(int, int)
    row_clicked = pyqtSignal(int)

    _ROW_H = 16
    _CELL_MIN_W = 8
    _MATRIX_CELL_MIN_W = 8
    _LEFT_PAD = 6
    _COL_HEADER_H = 40
    _MATRIX_HEADER_LABEL_PITCH = 12

    def __init__(self, row_labels: List[str], grid: list, parent=None):
        super().__init__(parent)
        self._mode = 'pairs'
        self._row_labels: List[str] = []
        self._col_labels: List[str] = []
        self._grid: list = [[]]
        self._max_val = 0
        self._label_w = 52
        self._hover_ri: Optional[int] = None
        self.setMouseTracking(True)
        self.set_data(row_labels, grid)

    def _scroll_offsets(self) -> Tuple[int, int]:
        parent = self.parentWidget()
        if isinstance(parent, QScrollArea):
            return (parent.horizontalScrollBar().value(),
                    parent.verticalScrollBar().value())
        return 0, 0

    def _header_h(self) -> int:
        return self._COL_HEADER_H if self._mode == 'matrix' else 0

    def _content_size(self) -> QSize:
        if self._mode == 'matrix':
            n_bins = len(self._col_labels) or 1
            cell_w = self._MATRIX_CELL_MIN_W
            w = self._LEFT_PAD + self._label_w + n_bins * cell_w + 8
            h = max(60, self._header_h() + len(self._row_labels) * self._ROW_H + 8)
        else:
            n_bins = len(self._grid[0]) if self._grid and self._grid[0] else 1
            w = self._LEFT_PAD + self._label_w + n_bins * self._CELL_MIN_W + 8
            h = max(60, len(self._row_labels) * self._ROW_H + 8)
        return QSize(w, h)

    def _sync_widget_size(self) -> None:
        """Match widget geometry to grid so QScrollArea range updates on drill-down."""
        size = self._content_size()
        parent = self.parentWidget()
        if isinstance(parent, QScrollArea):
            vp_w = parent.viewport().width()
            if vp_w > 0:
                size.setWidth(max(size.width(), vp_w))
        self.setMinimumSize(size)
        self.resize(size)
        self.updateGeometry()

    def set_data(self, row_labels: List[str], grid: list) -> None:
        self._mode = 'pairs'
        self._hover_ri = None
        self._row_labels = list(row_labels)
        self._col_labels = []
        self._grid = grid if grid else [[]]
        self._max_val = max((v for row in self._grid for v in row), default=0)
        fm = QFontMetrics(self.font())
        max_lbl = max((fm.horizontalAdvance(lbl) for lbl in self._row_labels), default=0)
        self._label_w = max(52, max_lbl + 10)
        self._sync_widget_size()
        self.update()

    def set_matrix_data(self, row_labels: List[str], col_labels: List[str],
                        grid: list) -> None:
        self._mode = 'matrix'
        self._hover_ri = None
        self._row_labels = list(row_labels)
        self._col_labels = list(col_labels)
        self._grid = grid if grid else [[]]
        self._max_val = max((v for row in self._grid for v in row), default=0)
        fm = QFontMetrics(self.font())
        max_lbl = max(
            (fm.horizontalAdvance(lbl) for lbl in self._row_labels + self._col_labels),
            default=0)
        self._label_w = max(52, max_lbl + 10)
        self._sync_widget_size()
        self.update()

    def sizeHint(self) -> QSize:
        return self._content_size()

    def _cell_geometry(self) -> Tuple[int, float]:
        if self._mode == 'matrix':
            n_bins = len(self._col_labels) or 1
            x0 = self._LEFT_PAD + self._label_w
            return x0, float(self._MATRIX_CELL_MIN_W)
        n_bins = len(self._grid[0]) if self._grid else 1
        x0 = self._LEFT_PAD + self._label_w
        cell_w = max(self._CELL_MIN_W, (self.width() - x0 - 4) // max(1, n_bins))
        return x0, float(cell_w)

    def _matrix_col_label_step(self, cell_w: float) -> int:
        return max(1, int(math.ceil(self._MATRIX_HEADER_LABEL_PITCH / max(cell_w, 1))))

    def _matrix_row_has_migrations(self, ri: int) -> bool:
        if ri < 0 or ri >= len(self._grid):
            return False
        for bi, v in enumerate(self._grid[ri]):
            if self._mode == 'matrix' and ri == bi:
                continue
            if v > 0:
                return True
        return False

    def set_hover_pos(self, _x: float, y: float) -> None:
        header_h = self._header_h()
        if y < header_h + 4:
            hover_ri = None
        else:
            ri = int((y - header_h - 4) // self._ROW_H)
            hover_ri = ri if 0 <= ri < len(self._row_labels) else None
        if hover_ri != self._hover_ri:
            self._hover_ri = hover_ri
            self.update()

    def clear_hover(self) -> None:
        if self._hover_ri is not None:
            self._hover_ri = None
            self.update()

    def mouseMoveEvent(self, event) -> None:
        pos = event.position() if hasattr(event, "position") else None
        self.set_hover_pos(
            pos.x() if pos else event.x(),
            pos.y() if pos else event.y(),
        )
        return super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self.clear_hover()
        return super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or not self._row_labels:
            return super().mousePressEvent(event)
        pos = event.position() if hasattr(event, "position") else None
        x = pos.x() if pos else event.x()
        y = pos.y() if pos else event.y()
        header_h = self._header_h()
        if y < header_h + 4:
            return super().mousePressEvent(event)
        ri = int((y - header_h - 4) // self._ROW_H)
        if ri < 0 or ri >= len(self._row_labels):
            return super().mousePressEvent(event)
        if self._mode == 'matrix':
            if self._matrix_row_has_migrations(ri):
                self.row_clicked.emit(ri)
            return super().mousePressEvent(event)
        x0, cell_w = self._cell_geometry()
        if x < x0:
            return super().mousePressEvent(event)
        bi = int((x - x0) // cell_w)
        n_cols = len(self._col_labels) if self._mode == 'matrix' else len(self._grid[0])
        if bi < 0 or bi >= n_cols:
            return super().mousePressEvent(event)
        if self._grid[ri][bi] <= 0:
            return super().mousePressEvent(event)
        self.cell_clicked.emit(ri, bi)
        return super().mousePressEvent(event)

    def _paint_matrix_headers(self, p: QPainter, clip: QRect, scroll_x: int,
                              scroll_y: int, x0: int, cell_w: float) -> None:
        if scroll_y > self._COL_HEADER_H:
            return
        label_right = self._LEFT_PAD + self._label_w
        header_top = scroll_y
        axis_y = header_top + self._COL_HEADER_H - 3
        if clip.bottom() < header_top or clip.top() > axis_y + 4:
            return
        p.fillRect(QRectF(scroll_x, header_top, label_right, self._COL_HEADER_H),
                   self.palette().color(QPalette.Window))
        p.setPen(QPen(QColor("#888888")))
        p.drawText(QRectF(scroll_x, header_top, label_right - 4, self._COL_HEADER_H),
                   Qt.AlignRight | Qt.AlignVCenter, "to→")
        step = self._matrix_col_label_step(cell_w)
        small = QFont(self.font())
        small.setPointSize(max(7, small.pointSize() - 2))
        p.setFont(small)
        for bi, lbl in enumerate(self._col_labels):
            if bi % step != 0:
                continue
            hx = x0 + bi * cell_w
            if hx + cell_w <= label_right:
                continue
            cx = hx + (cell_w * step) / 2
            cy = header_top + self._COL_HEADER_H - 4
            p.save()
            p.translate(cx, cy)
            p.rotate(-90)
            p.drawText(0, 0, lbl)
            p.restore()
        p.setFont(self.font())

    def paintEvent(self, event) -> None:
        if not self._row_labels:
            return
        clip = event.rect()
        p = QPainter(self)
        p.setClipRect(clip)
        scroll_x, scroll_y = self._scroll_offsets()
        header_h = self._header_h()
        w = self.width()
        x0, cell_w = self._cell_geometry()
        n_cols = len(self._col_labels) if self._mode == 'matrix' else (
            len(self._grid[0]) if self._grid and self._grid[0] else 1)
        label_right = self._LEFT_PAD + self._label_w
        bg = self.palette().color(QPalette.Window)
        ri_start = max(0, int((clip.top() - header_h - 4) // self._ROW_H))
        ri_end = min(len(self._row_labels),
                     int((clip.bottom() - header_h - 4) // self._ROW_H) + 1)

        if self._mode == 'matrix':
            self._paint_matrix_headers(p, clip, scroll_x, scroll_y, x0, cell_w)

        for ri in range(ri_start, ri_end):
            if ri >= len(self._grid):
                continue
            y = header_h + 4 + ri * self._ROW_H
            lbl = self._row_labels[ri]
            p.fillRect(QRectF(scroll_x, y, label_right, self._ROW_H - 1), bg)
            p.setPen(QPen(QColor("#888888")))
            p.drawText(
                QRectF(self._LEFT_PAD + scroll_x, y, self._label_w, self._ROW_H),
                Qt.AlignLeft | Qt.AlignVCenter,
                lbl,
            )
            x = x0
            for bi, v in enumerate(self._grid[ri]):
                if bi >= n_cols:
                    break
                is_diag = self._mode == 'matrix' and ri == bi
                cell_right = x + cell_w
                if cell_right > label_right and x < w:
                    if is_diag:
                        p.fillRect(QRectF(x, y, cell_w - 1, self._ROW_H - 3),
                                   QColor(91, 155, 213, 8))
                    else:
                        alpha = int(50 + 180 * v / self._max_val) if self._max_val else 30
                        p.fillRect(QRectF(x, y, cell_w - 1, self._ROW_H - 3),
                                   QColor(91, 155, 213, alpha if v else 15))
                x += cell_w
            if self._hover_ri == ri:
                row_w = label_right + n_cols * cell_w
                p.fillRect(QRectF(0, y, row_w, self._ROW_H - 1),
                           QColor(91, 155, 213, 46))
        p.end()

class _MigrationHeatmapDialog(QDialog):
    """Popup: hierarchical migration heatmap (core-pair → task drill-down)."""

    def __init__(self, trace: "BtfTrace", parent=None,
                 on_drill: Optional[Callable] = None,
                 on_clear: Optional[Callable] = None):
        super().__init__(parent)
        self.setWindowTitle("Migration Heatmap")
        self.setMinimumSize(480, 320)
        self.setModal(False)
        self._trace = trace
        self._on_drill = on_drill
        self._on_clear = on_clear
        self._level = 0
        self._scope_lo: Optional[int] = None
        self._scope_hi: Optional[int] = None
        self._scope_suffix = ""
        self._pairs: list = []
        self._grid0: list = []
        self._t_min = trace.time_min
        self._t_max = trace.time_max
        self._bin_w = 1.0
        self._time_bins = 32
        self._task_rows: list = []
        self._task_grid: list = []
        self._drill_fc = ""
        self._drill_tc = ""
        self._drill_label = ""
        self._drill_bin_lo = 0
        self._drill_bin_hi = 0
        self._filter_count = 0
        self._owner_tab_path: Optional[str] = None
        self._scope_cache: Dict[Tuple[Optional[int], Optional[int]], dict] = {}
        self._uses_matrix = _migration_heatmap_uses_matrix(trace)
        self._matrix_cores: list = []
        self._matrix_grid: list = []

        lo = hi = None
        wnd = parent
        if isinstance(wnd, QMainWindow):
            tab = wnd._active_tab
            if tab is not None:
                times = sorted(tab.view._scene.cursor_times())
                if len(times) >= 2:
                    lo, hi = times[0], times[-1]
                    self._scope_suffix = (
                        f"  (C1–C{len(times)}: "
                        f"{_format_time(lo, trace.time_scale)} … "
                        f"{_format_time(hi, trace.time_scale)})")
        self._scope_lo = lo
        self._scope_hi = hi
        pairs, grid, time_bins = _migration_heatmap_data(trace, lo, hi)
        self._pairs = pairs
        self._grid0 = grid
        if self._uses_matrix:
            self._matrix_cores, self._matrix_grid = _migration_heatmap_matrix(
                trace, lo, hi)
        self._time_bins = time_bins
        t_min = lo if lo is not None else trace.time_min
        t_hi = hi if hi is not None else trace.time_max
        span = max(t_hi - t_min, 1)
        self._t_min = t_min
        self._t_max = t_hi
        self._bin_w = span / time_bins
        self._ov_t_min = t_min
        self._ov_t_max = t_hi
        self._ov_bin_w = span / time_bins
        self._ov_time_bins = time_bins
        self._cache_scope_grid(lo, hi, pairs, grid, time_bins, t_min, t_hi, span)

        lay = QVBoxLayout(self)
        nav = QHBoxLayout()
        self._back_btn = QPushButton("← Back")
        self._back_btn.setVisible(False)
        self._back_btn.clicked.connect(self._go_back)
        nav.addWidget(self._back_btn)
        nav.addStretch(1)
        lay.addLayout(nav)

        self._sub_label = QLabel()
        lay.addWidget(self._sub_label)

        self._empty_label = QLabel("No migrations in scope.")
        self._empty_label.setVisible(False)
        lay.addWidget(self._empty_label)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._canvas = _MigrationHeatmapWidget([], [[]])
        self._canvas.cell_clicked.connect(self._on_cell_clicked)
        self._canvas.row_clicked.connect(self._on_matrix_row_clicked)
        self._scroll.setWidget(self._canvas)
        self._scroll.viewport().setMouseTracking(True)
        self._scroll.viewport().installEventFilter(self)
        self._scroll.verticalScrollBar().valueChanged.connect(
            lambda _v: self._canvas.update())
        self._scroll.horizontalScrollBar().valueChanged.connect(
            lambda _v: self._canvas.update())
        lay.addWidget(self._scroll, 1)

        self._hint_label = QLabel()
        self._hint_label.setStyleSheet("color:#888888;")
        lay.addWidget(self._hint_label)

        self._filter_bar = QLabel()
        self._filter_bar.setVisible(False)
        self._filter_bar.setStyleSheet(
            "color:#5B9BD5; padding:6px 8px; background:rgba(91,155,213,0.12);"
            "border:1px solid rgba(91,155,213,0.35); border-radius:4px;")
        lay.addWidget(self._filter_bar)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        if on_clear is not None:
            self._show_all_btn = btns.addButton(
                "Show all tasks", QDialogButtonBox.ActionRole)
            self._show_all_btn.setToolTip(
                "Clear heatmap task filter and show all tasks")
            self._show_all_btn.clicked.connect(on_clear)
        else:
            self._show_all_btn = None
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        lay.addWidget(btns)

        self._go_level0()

    def eventFilter(self, watched, event) -> bool:
        if watched is self._scroll.viewport():
            et = event.type()
            if et == QEvent.MouseMove:
                pos = self._canvas.mapFrom(self._scroll.viewport(), event.pos())
                self._canvas.set_hover_pos(pos.x(), pos.y())
            elif et == QEvent.Leave:
                self._canvas.clear_hover()
        return super().eventFilter(watched, event)

    def set_filter_banner(self, label: Optional[str], count: int) -> None:
        self._filter_count = count
        active = count > 0
        self._filter_bar.setVisible(active)
        if active:
            self._filter_bar.setText(
                f"Showing {count} task{'s' if count != 1 else ''}: "
                f"{label or 'filtered'}")
        self._update_show_all_btn()

    def _update_show_all_btn(self) -> None:
        if self._show_all_btn is not None:
            self._show_all_btn.setEnabled(self._filter_count > 0)

    def _owner_tab_still_active(self, owner_tab_path: Optional[str]) -> bool:
        if owner_tab_path is None:
            return True
        wnd = self.parent()
        if not isinstance(wnd, QMainWindow):
            return True
        tab = wnd._active_tab
        return tab is not None and tab.path == owner_tab_path

    def _cache_scope_grid(self, lo: Optional[int], hi: Optional[int],
                          pairs: list, grid: list, time_bins: int,
                          t_min: int, t_hi: int, span: int) -> None:
        ent = {
            'pairs': pairs,
            'grid0': grid,
            'time_bins': time_bins,
            'ov_t_min': t_min,
            'ov_t_max': t_hi,
            'ov_bin_w': span / time_bins,
            'ov_time_bins': time_bins,
        }
        if self._uses_matrix:
            ent['matrix_cores'], ent['matrix_grid'] = _migration_heatmap_matrix(
                self._trace, lo, hi)
        self._scope_cache[(lo, hi)] = ent

    def _apply_scope_cache(self, lo: Optional[int], hi: Optional[int]) -> bool:
        ent = self._scope_cache.get((lo, hi))
        if ent is None:
            return False
        self._pairs = ent['pairs']
        self._grid0 = ent['grid0']
        self._time_bins = ent['time_bins']
        self._ov_t_min = ent['ov_t_min']
        self._ov_t_max = ent['ov_t_max']
        self._ov_bin_w = ent['ov_bin_w']
        self._ov_time_bins = ent['ov_time_bins']
        if self._uses_matrix:
            self._matrix_cores = ent.get('matrix_cores', [])
            self._matrix_grid = ent.get('matrix_grid', [])
        return True

    def refresh_scope(self) -> None:
        """Rebuild level-0 grid from current cursor scope (full trace if <2 cursors)."""
        lo = hi = None
        suffix = ""
        wnd = self.parent()
        if isinstance(wnd, QMainWindow):
            tab = wnd._active_tab
            if tab is not None:
                times = sorted(tab.view._scene.cursor_times())
                if len(times) >= 2:
                    lo, hi = times[0], times[-1]
                    suffix = (
                        f"  (C1–C{len(times)}: "
                        f"{_format_time(lo, self._trace.time_scale)} … "
                        f"{_format_time(hi, self._trace.time_scale)})")
        self._scope_suffix = suffix
        if self._apply_scope_cache(lo, hi):
            self._go_level0()
            return
        pairs, grid, time_bins = _migration_heatmap_data(
            self._trace, lo, hi)
        self._pairs = pairs
        self._grid0 = grid
        if self._uses_matrix:
            self._matrix_cores, self._matrix_grid = _migration_heatmap_matrix(
                self._trace, lo, hi)
        t_min = lo if lo is not None else self._trace.time_min
        t_hi = hi if hi is not None else self._trace.time_max
        span = max(t_hi - t_min, 1)
        self._cache_scope_grid(lo, hi, pairs, grid, time_bins, t_min, t_hi, span)
        self._ov_t_min = t_min
        self._ov_t_max = t_hi
        self._ov_bin_w = span / time_bins
        self._ov_time_bins = time_bins
        self._go_level0()

    def _set_canvas(self, row_labels: List[str], grid: list) -> None:
        self._canvas.set_data(row_labels, grid)

    def _schedule_level1(self, fc: str, tc: str, label: str,
                         bin_lo: int, bin_hi: int, parent_bin_index: int) -> None:
        owner = self._owner_tab_path
        QTimer.singleShot(
            0, lambda fc=fc, tc=tc, label=label, bin_lo=bin_lo, bin_hi=bin_hi,
            parent_bin_index=parent_bin_index, owner=owner:
                self._go_level1(
                    fc, tc, label, bin_lo, bin_hi, parent_bin_index, owner))

    def _schedule_drill(self, fc: str, tc: str, label: str,
                        bin_lo: int, bin_hi: int, merge_keys: set) -> None:
        if not self._on_drill:
            return
        owner = self._owner_tab_path
        QTimer.singleShot(
            0, lambda fc=fc, tc=tc, label=label, bin_lo=bin_lo, bin_hi=bin_hi,
            merge_keys=merge_keys, owner=owner:
                self._dispatch_drill(
                    fc, tc, label, bin_lo, bin_hi, merge_keys, owner))

    def _dispatch_drill(self, fc: str, tc: str, label: str,
                        bin_lo: int, bin_hi: int, merge_keys: set,
                        owner_tab_path: Optional[str]) -> None:
        if not self._on_drill or not self._owner_tab_still_active(owner_tab_path):
            return
        self._on_drill(fc, tc, label, bin_lo, bin_hi, merge_keys)

    def _scroll_heatmap_to_top(self) -> None:
        """Reset scroll after level/content change (level-1 grid is often shorter)."""
        def _do() -> None:
            self._canvas._sync_widget_size()
            self._scroll.updateGeometry()
            self._scroll.verticalScrollBar().setValue(0)
            self._scroll.horizontalScrollBar().setValue(0)
        QTimer.singleShot(0, _do)

    def _go_back(self) -> None:
        if self._level <= 0:
            return
        if self._uses_matrix and self._level == 2:
            self._show_outgoing_level(self._drill_fc)
        elif self._uses_matrix and self._level == 1:
            self._go_level0()
        else:
            self._go_level0()
        self._scroll_heatmap_to_top()

    def _go_level0(self) -> None:
        self._level = 0
        self._back_btn.setVisible(False)
        self._t_min = self._ov_t_min
        self._t_max = self._ov_t_max
        self._bin_w = self._ov_bin_w
        self._time_bins = self._ov_time_bins
        if self._uses_matrix:
            n = len(self._matrix_cores)
            self._sub_label.setText(
                f"Core × core migration counts ({n} cores, row = from, "
                f"column = to){self._scope_suffix}")
            has_data = (self._matrix_cores
                        and any(self._matrix_grid[i][j] > 0
                                for i in range(len(self._matrix_grid))
                                for j in range(len(self._matrix_grid[i]))
                                if i != j))
            self._empty_label.setVisible(not has_data)
            self._scroll.setVisible(has_data)
            if has_data:
                row_lbls = [_core_short_name(c) for c in self._matrix_cores]
                col_lbls = row_lbls
                self._canvas.set_matrix_data(row_lbls, col_lbls, self._matrix_grid)
            self._hint_label.setText(
                "Rows: source (from) core · Columns: destination (to) core · "
                "Hover a row to highlight · Click a row for outgoing pairs")
        else:
            self._sub_label.setText(
                f"Core-pair migrations over time bins{self._scope_suffix}")
            has_data = (self._pairs
                        and any(any(r for r in row) for row in self._grid0))
            self._empty_label.setVisible(not has_data)
            self._scroll.setVisible(has_data)
            if has_data:
                labels = [p[2] for p in self._pairs]
                self._set_canvas(labels, self._grid0)
            self._hint_label.setText(
                "Rows: from→to core pairs · Columns: time bins · "
                "Click a cell to drill into tasks")
        self._update_show_all_btn()
        self._scroll_heatmap_to_top()

    def _show_outgoing_level(self, from_core: str) -> None:
        """Matrix drill-down: outgoing pairs × time bins for one source core."""
        self._level = 1
        self._drill_fc = from_core
        self._drill_tc = ""
        self._drill_label = _core_short_name(from_core)
        self._back_btn.setVisible(True)
        lo = self._scope_lo
        hi = self._scope_hi
        pairs, grid, time_bins, t_min, t_hi, bin_w = _migration_core_outgoing_heatmap(
            self._trace, from_core, lo, hi, self._ov_time_bins)
        self._pairs = pairs
        self._grid0 = grid
        self._t_min = t_min
        self._t_max = t_hi
        self._bin_w = bin_w
        self._time_bins = time_bins
        src = _core_short_name(from_core)
        self._sub_label.setText(
            f"Outgoing migrations from {src} · rows = destination cores · "
            f"columns = time bins{self._scope_suffix}")
        has_data = bool(grid and any(any(r for r in row) for row in grid))
        self._empty_label.setVisible(not has_data)
        self._empty_label.setText("No migrations in scope.")
        self._scroll.setVisible(has_data)
        if has_data:
            self._set_canvas([p[2] for p in pairs], grid)
        self._hint_label.setText(
            "Rows: outgoing core pairs · Columns: time bins · "
            "Hover a row to highlight · Click a cell to drill into tasks")
        self._update_show_all_btn()
        self._scroll_heatmap_to_top()

    def _on_matrix_row_clicked(self, ri: int) -> None:
        if not self._uses_matrix or self._level != 0:
            return
        if ri < 0 or ri >= len(self._matrix_cores):
            return
        self._show_outgoing_level(self._matrix_cores[ri])

    def _show_pair_time_level(self, fc: str, tc: str, label: str) -> None:
        """Matrix drill-down: time bins for one core pair."""
        self._level = 1
        self._drill_fc = fc
        self._drill_tc = tc
        self._drill_label = label
        self._back_btn.setVisible(True)
        lo = self._scope_lo
        hi = self._scope_hi
        pairs, grid, time_bins, t_min, t_hi, bin_w = _migration_pair_time_bins(
            self._trace, fc, tc, lo, hi, self._ov_time_bins)
        self._t_min = t_min
        self._t_max = t_hi
        self._bin_w = bin_w
        self._time_bins = time_bins
        self._sub_label.setText(
            f"Time bins · {label}{self._scope_suffix}")
        has_data = bool(grid and any(any(r for r in row) for row in grid))
        self._empty_label.setVisible(not has_data)
        self._empty_label.setText("No migrations in scope.")
        self._scroll.setVisible(has_data)
        if has_data:
            self._set_canvas([label], grid)
        self._hint_label.setText(
            "Columns: time bins · Click a cell to drill into tasks")
        self._update_show_all_btn()
        self._scroll_heatmap_to_top()

    def _go_level1(self, fc: str, tc: str, label: str,
                    bin_lo: int, bin_hi: int, parent_bin_index: int,
                    owner_tab_path: Optional[str] = None) -> None:
        if not self._owner_tab_still_active(owner_tab_path):
            return
        self._level = 2 if self._uses_matrix else 1
        self._drill_fc = fc
        self._drill_tc = tc
        self._drill_label = label
        self._drill_bin_lo = bin_lo
        self._drill_bin_hi = bin_hi
        self._back_btn.setVisible(True)
        ts = self._trace.time_scale
        self._sub_label.setText(
            f"Tasks · {label} · "
            f"{_format_time(bin_lo, ts)}–{_format_time(bin_hi, ts)}")
        rows, grid, time_bins, t_min, t_hi, bin_w = _migration_task_heatmap_data(
            self._trace, fc, tc, bin_lo, bin_hi, self._ov_time_bins,
            parent_bin_index=parent_bin_index,
            parent_time_bins=self._ov_time_bins)
        self._task_rows = rows
        self._task_grid = grid
        self._t_min = t_min
        self._t_max = t_hi
        self._bin_w = bin_w
        self._time_bins = time_bins
        has_data = bool(rows)
        self._empty_label.setVisible(not has_data)
        self._empty_label.setText("No task migrations in this cell.")
        self._scroll.setVisible(has_data)
        if has_data:
            self._set_canvas([r[1] for r in rows], grid)
        self._hint_label.setText(
            "Rows: tasks · Columns: sub-bins · "
            "Click a cell to zoom and filter in Task View")
        self._update_show_all_btn()
        self._scroll_heatmap_to_top()

    def _on_cell_clicked(self, ri: int, bi: int) -> None:
        if self._uses_matrix and self._level == 1:
            if ri < 0 or bi < 0 or bi >= self._time_bins:
                return
            if (not self._canvas._grid or ri >= len(self._canvas._grid)
                    or bi >= len(self._canvas._grid[ri])
                    or self._canvas._grid[ri][bi] <= 0):
                return
            if ri >= len(self._pairs):
                return
            fc, tc, label = self._pairs[ri]
            bin_lo, bin_hi = _heatmap_bin_range(
                self._t_min, self._bin_w, self._time_bins, self._t_max, bi)
            self._schedule_level1(
                fc, tc, label, bin_lo, bin_hi, bi)
            return
        if self._level == 0:
            if ri < 0 or ri >= len(self._pairs):
                return
            fc, tc, label = self._pairs[ri]
            if bi < 0 or bi >= len(self._grid0[0]) or self._grid0[ri][bi] <= 0:
                return
            bin_lo, bin_hi = _heatmap_bin_range(
                self._t_min, self._bin_w, self._time_bins, self._t_max, bi)
            self._schedule_level1(fc, tc, label, bin_lo, bin_hi, bi)
            return
        task_level = 2 if self._uses_matrix else 1
        if self._level != task_level:
            return
        if ri < 0 or ri >= len(self._task_rows):
            return
        mk, disp = self._task_rows[ri]
        if bi < 0 or bi >= len(self._task_grid[0]) or self._task_grid[ri][bi] <= 0:
            return
        sub_lo, sub_hi = _heatmap_bin_range(
            self._t_min, self._bin_w, self._time_bins, self._t_max, bi)
        pair_lbl = f"{self._drill_label} · {disp}"
        self._schedule_drill(self._drill_fc, self._drill_tc, pair_lbl,
                             sub_lo, sub_hi, {mk})

class _StatsPanel(QWidget):
    """Dock panel showing trace statistics (span, core utilisation, top tasks)."""

    task_clicked = pyqtSignal(str)   # merge key of the clicked task row
    segment_jump   = pyqtSignal(int)    # ns - scroll timeline to this timestamp
    plot_point_clicked = pyqtSignal(object, int, str)  # payload, mark_ns, note

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ui_font_size: int = UI_FONT_SIZE
        self._is_dark: bool = True
        self._plot_dlg = None   # keep reference to prevent GC
        self._plot_mk: Optional[str] = None
        self._plot_kind: Optional[str] = None   # "exec", "block", "inter", "preempt", "interval"
        self._plot_preemptor: Optional[str] = None
        self._plot_interval_id: Optional[str] = None
        self._trace: Optional["BtfTrace"] = None
        self._cursor_times: List[int] = []
        self._scope_to_cursors: bool = True
        self._section_collapsed: Dict[str, bool] = {
            "cores": False,
            "tasks": False,
            "migrations": False,
            "exec": False,
            "block": False,
            "inter": False,
            "health": False,
            "preemption": False,
            "intervals": False,
        }
        self._section_headers: Dict[str, QPushButton] = {}
        self._section_bodies: Dict[str, QWidget] = {}
        self._section_populate: Dict[str, object] = {}
        self._section_table_heights: Dict[str, int] = {
            "migrations": STATS_TABLE_MIG_DEFAULT_H,
            "exec": STATS_TABLE_DEFAULT_H,
            "block": STATS_TABLE_DEFAULT_H,
            "inter": STATS_TABLE_DEFAULT_H,
            "preemption": STATS_TABLE_MIG_DEFAULT_H,
            "intervals": STATS_TABLE_DEFAULT_H,
        }
        self._table_grips: List[_StatsSectionGrip] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scope_row = QHBoxLayout()
        scope_row.setContentsMargins(8, 6, 8, 0)
        scope_row.setSpacing(6)
        self._scope_cb = QCheckBox("Limit to cursor range (C1–Cn)")
        self._scope_cb.setChecked(True)
        self._scope_cb.setEnabled(False)
        self._scope_cb.setToolTip(
            "When two or more cursors are placed, restrict all statistics\n"
            "to the time window from C1 through the last cursor.")
        self._scope_cb.toggled.connect(self._on_scope_toggled)
        scope_row.addWidget(self._scope_cb)
        self._scope_label = QLabel("")
        self._scope_label.setStyleSheet("color:#888888;")
        scope_row.addWidget(self._scope_label, 1)
        _ic = "#9E9E9E"
        self._btn_stats_expand = QToolButton()
        self._btn_stats_expand.setIcon(_svg_icon(_IC_SECTIONS_EXPAND, _ic))
        self._btn_stats_expand.setIconSize(QSize(14, 14))
        self._btn_stats_expand.setToolTip("Expand all statistics sections")
        self._btn_stats_expand.setAutoRaise(True)
        self._btn_stats_expand.clicked.connect(self._expand_all_sections)
        scope_row.addWidget(self._btn_stats_expand)
        self._btn_stats_collapse = QToolButton()
        self._btn_stats_collapse.setIcon(_svg_icon(_IC_SECTIONS_COLLAPSE, _ic))
        self._btn_stats_collapse.setIconSize(QSize(14, 14))
        self._btn_stats_collapse.setToolTip("Collapse all statistics sections")
        self._btn_stats_collapse.setAutoRaise(True)
        self._btn_stats_collapse.clicked.connect(self._collapse_all_sections)
        scope_row.addWidget(self._btn_stats_collapse)
        outer.addLayout(scope_row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self._scroll = scroll
        self._inner = QWidget()
        self._inner.setObjectName("stats_inner")
        self._ilay = QVBoxLayout(self._inner)
        self._ilay.setContentsMargins(8, 6, 8, 6)
        self._ilay.setSpacing(2)
        self._ilay.addStretch()
        scroll.setWidget(self._inner)
        outer.addWidget(scroll)
        self._apply_panel_theme()

        exp_row = QHBoxLayout()
        exp_row.setContentsMargins(8, 6, 8, 8)
        exp_row.setSpacing(8)
        self._btn_export_csv = QPushButton("Export CSV")
        self._btn_export_csv.clicked.connect(self._export_csv)
        self._btn_export_csv.setEnabled(False)
        exp_row.addWidget(self._btn_export_csv)
        self._btn_export_html = QPushButton("Export HTML")
        self._btn_export_html.clicked.connect(self._export_html)
        self._btn_export_html.setEnabled(False)
        exp_row.addWidget(self._btn_export_html)
        self._btn_compare_mig = QPushButton("Trace Compare…")
        self._btn_compare_mig.setToolTip(
            "Compare summary, top tasks, and core migrations between two open trace tabs")
        self._btn_compare_mig.setEnabled(False)
        exp_row.addWidget(self._btn_compare_mig)
        outer.addLayout(exp_row)

    def _clear(self) -> None:
        self._table_grips.clear()
        self._section_headers.clear()
        self._section_bodies.clear()
        self._section_populate.clear()
        while self._ilay.count():
            item = self._ilay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def apply_section_table_heights(self, heights: Dict[str, int]) -> None:
        """Apply persisted max heights for collapsible stats tables."""
        for key, val in heights.items():
            if key in self._section_table_heights:
                self._section_table_heights[key] = max(
                    _StatsSectionGrip._MIN_H,
                    min(_StatsSectionGrip._MAX_H, int(val)),
                )

    def section_table_heights(self) -> Dict[str, int]:
        return dict(self._section_table_heights)

    def _apply_table_display_height(self, table: QTableWidget, h: int) -> int:
        """Set an explicit pixel height so drag-resize is visible (scroll inside table)."""
        h = max(_StatsSectionGrip._MIN_H, min(_StatsSectionGrip._MAX_H, int(h)))
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        table.setMinimumHeight(h)
        table.setMaximumHeight(h)
        table.updateGeometry()
        host = table.parentWidget()
        if host is not None:
            host.updateGeometry()
        return h

    def _wrap_table_with_resizer(self, lay: QVBoxLayout, table: QTableWidget,
                                 section_id: str) -> None:
        """Add *table* plus a drag grip; height is stored in *_section_table_heights*."""
        default_h = (STATS_TABLE_MIG_DEFAULT_H if section_id == "migrations"
                     else STATS_TABLE_DEFAULT_H)
        h = self._section_table_heights.get(section_id, default_h)
        h = self._apply_table_display_height(table, h)
        self._section_table_heights[section_id] = h

        grip = _StatsSectionGrip(self._is_dark, lambda: table.height())
        self._table_grips.append(grip)

        def _on_height(new_h: int) -> None:
            self._section_table_heights[section_id] = self._apply_table_display_height(
                table, new_h)

        grip.height_changed.connect(_on_height)
        lay.addWidget(table)
        lay.addWidget(grip)

    def _apply_panel_theme(self) -> None:
        """Keep stats scroll surfaces in sync (Windows native style ignores QSS)."""
        bg = QColor("#1E1E1E") if self._is_dark else QColor("#F5F5F5")
        bg_name = bg.name()
        scroll = getattr(self, "_scroll", None)
        inner = getattr(self, "_inner", None)
        targets = [self]
        if scroll is not None:
            scroll.setObjectName("stats_scroll")
            scroll.viewport().setObjectName("stats_scroll_viewport")
            targets.extend((scroll, scroll.viewport()))
        if inner is not None:
            targets.append(inner)
        for w in targets:
            pal = w.palette()
            pal.setColor(QPalette.Window, bg)
            pal.setColor(QPalette.Base, bg)
            w.setPalette(pal)
            w.setAutoFillBackground(True)
        if scroll is not None:
            scroll.setStyleSheet(
                f"QScrollArea#stats_scroll {{ background:{bg_name}; border:none; }}"
                f"QWidget#stats_scroll_viewport {{ background:{bg_name}; }}"
                f"QWidget#stats_inner {{ background:{bg_name}; }}"
            )
            scroll.viewport().setStyleSheet(
                f"background-color: {bg_name}; border: none;"
            )

    def _stats_table_colors(self) -> Tuple[QColor, QColor, str]:
        """Theme colours for stats tables (match MainWindow._theme_tokens)."""
        if self._is_dark:
            return QColor("#121212"), QColor("#D4D4D4"), "#9A9A9A"
        return QColor("#FFFFFF"), QColor("#1E1E1E"), "#666666"

    def _stats_table_qss(self, ui_fs: str, bg: str, fg: str, muted: str) -> str:
        """QSS for stats-panel tables."""
        return (
            f"font-size:{ui_fs};"
            f"QTableWidget#stats_table{{background:{bg}; color:{fg}; border:none;}}"
            f"QWidget#stats_table_viewport{{background:{bg};}}"
            "QTableWidget::item{border:none; padding:0px 3px;}"
            f"QHeaderView::section{{border:none; background:transparent; "
            f"color:{muted}; padding:0px 3px;}}"
        )

    def _apply_stats_table_theme(self, table: QTableWidget, ui_fs: str) -> QBrush:
        """Paint stats-table surfaces explicitly (required on Windows Qt)."""
        bg, fg, muted = self._stats_table_colors()
        bg_name = bg.name()
        fg_name = fg.name()
        table.setObjectName("stats_table")
        table.viewport().setObjectName("stats_table_viewport")
        table.setStyleSheet(self._stats_table_qss(ui_fs, bg_name, fg_name, muted))
        for w in (table, table.viewport()):
            pal = w.palette()
            pal.setColor(QPalette.Window, bg)
            pal.setColor(QPalette.Base, bg)
            pal.setColor(QPalette.Text, fg)
            w.setPalette(pal)
            w.setAutoFillBackground(True)
        table.viewport().setStyleSheet(
            f"background-color: {bg_name}; border: none;"
        )
        return QBrush(bg)

    def _lbl(self, text: str, color: str = "", bold: bool = False,
              ui_fs: str = "") -> QLabel:
        w = QLabel(text)
        parts = ["background:transparent;"]
        if color:
            parts.insert(0, f"color:{color};")
        if bold:
            parts.append("font-weight:bold;")
        if ui_fs:
            parts.append(f"font-size:{ui_fs};")
        w.setStyleSheet(" ".join(parts))
        return w

    def _add_utilisation_row(self, blay: QVBoxLayout, ui_fs: str,
                             label: str, pct: float, *,
                             chunk_color: str, pct_color: str,
                             label_min_width: int = 72,
                             on_click=None, click_tip: str = "") -> None:
        """Add a core/task CPU bar row (progress bar + %), with hover highlight."""
        row = _StatsHoverRow(self._is_dark, on_click=on_click)
        row.setFixedHeight(STATS_UTIL_ROW_H)
        hlay = QHBoxLayout(row)
        hlay.setContentsMargins(0, 0, 0, 0)
        hlay.setSpacing(6)
        hlay.setAlignment(Qt.AlignVCenter)

        label_w = max(label_min_width, STATS_UTIL_LABEL_W)
        name_lbl = self._lbl(label, ui_fs=ui_fs)
        _fm = name_lbl.fontMetrics()
        name_lbl.setText(_fm.elidedText(label, Qt.ElideRight, label_w - 4))
        name_lbl.setFixedWidth(label_w)
        if click_tip:
            name_lbl.setToolTip(click_tip)
        hlay.addWidget(name_lbl)
        row.track_widget(name_lbl)

        pbar = QProgressBar()
        pbar.setRange(0, 1000)
        pbar.setValue(int(round(max(0.0, min(100.0, pct)) * 10.0)))
        pbar.setTextVisible(False)
        pbar.setFixedHeight(STATS_UTIL_BAR_H)
        pbar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        pbar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid #888888;
                border-radius: 3px;
                background: palette(alternateBase);
                max-height: {STATS_UTIL_BAR_H}px;
                min-height: {STATS_UTIL_BAR_H}px;
            }}
            QProgressBar::chunk {{
                background-color: {chunk_color};
                border-radius: 2px;
            }}
        """)
        hlay.addWidget(pbar, 1)
        row.track_widget(pbar)

        pct_lbl = self._lbl(f"{pct:.1f}%", color=pct_color, ui_fs=ui_fs)
        pct_lbl.setFixedWidth(STATS_UTIL_PCT_W)
        pct_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        hlay.addWidget(pct_lbl)
        row.track_widget(pct_lbl)

        blay.addWidget(row)

    def _wrap_util_rows_scroll(self, blay: QVBoxLayout, inner: QWidget,
                              row_count: int) -> None:
        """Scroll utilisation rows vertically when there are more than 8."""
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded if row_count > STATS_MAX_VISIBLE_ROWS
            else Qt.ScrollBarAlwaysOff)
        vis = min(max(row_count, 1), STATS_MAX_VISIBLE_ROWS)
        scroll_h = (vis * STATS_UTIL_ROW_H
                    + max(0, vis - 1) * STATS_UTIL_ROW_GAP + 2)
        scroll.setFixedHeight(scroll_h)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        blay.addWidget(scroll)

    def rebuild_with_font(self, trace: "BtfTrace", ui_font_size: int) -> None:
        """Re-build using the given *ui_font_size* so labels pick it up."""
        self._ui_font_size = ui_font_size
        self.rebuild(trace)

    def set_dark(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_panel_theme()
        for grip in self._table_grips:
            grip.set_dark(is_dark)
        if self._plot_dlg is not None:
            self._plot_dlg.set_dark(is_dark)

    def set_cursor_times(self, times: list, *, refresh_stats: bool = True) -> None:
        """Update placed cursor timestamps; optionally rebuild statistics."""
        was_scoped = (
            self._trace is not None
            and self._scope_to_cursors
            and len(self._cursor_times) >= 2
        )
        self._cursor_times = list(times)
        can_scope = len(times) >= 2
        self._scope_cb.blockSignals(True)
        self._scope_cb.setEnabled(can_scope)
        if not can_scope:
            self._scope_to_cursors = False
            self._scope_cb.setChecked(False)
        else:
            self._scope_cb.setChecked(self._scope_to_cursors)
        self._scope_cb.blockSignals(False)
        self._update_scope_header()
        scoped = self._stats_range() is not None
        leave_scoped = was_scoped and not scoped
        if refresh_stats and self._trace is not None and (scoped or leave_scoped):
            self.rebuild(self._trace)
        if self._plot_dlg is not None and self._plot_dlg.isVisible():
            self._refresh_open_plot()

    def _on_scope_toggled(self, checked: bool) -> None:
        self._scope_to_cursors = bool(checked)
        self._update_scope_header()
        if self._trace is not None:
            self.rebuild(self._trace)
        self._refresh_open_plot()

    def _stats_range(self) -> Optional[Tuple[int, int, int]]:
        """Return (lo, hi, n_cursors) when cursor-scoped stats are active."""
        if not self._scope_to_cursors or len(self._cursor_times) < 2 or self._trace is None:
            return None
        t_sorted = sorted(self._cursor_times)
        lo, hi = t_sorted[0], t_sorted[-1]
        if hi <= lo:
            return None
        return lo, hi, len(t_sorted)

    def _update_scope_header(self) -> None:
        rng = self._stats_range()
        if rng is None:
            self._scope_label.setText(
                "Place 2+ cursors to measure a time window" if len(self._cursor_times) < 2 else "")
            return
        lo, hi, n_cur = rng
        unit = self._trace.time_scale
        self._scope_label.setText(
            f"C1–C{n_cur}: {_format_time(lo, unit)} … {_format_time(hi, unit)}  "
            f"({_format_time(hi - lo, unit)})")

    def _scope_suffix(self) -> str:
        return " (cursor range)" if self._stats_range() is not None else ""

    def _plot_scope_banner(self) -> Tuple[bool, str, str]:
        """Return (is_scoped, badge_label, detail_text) for metrics plot dialogs."""
        rng = self._stats_range()
        if rng is None or self._trace is None:
            return False, "Full trace", "Not limited to cursors — all slices in the loaded trace"
        lo, hi, n_cur = rng
        unit = self._trace.time_scale
        detail = (
            f"C1–C{n_cur}: {_format_time(lo, unit)} … {_format_time(hi, unit)} "
            f"({_format_time(hi - lo, unit)})"
        )
        return True, "Cursor range", detail

    def _build_plot_points(self, trace: "BtfTrace", mk: str, kind: str
                           ) -> Optional[Tuple[str, list, "QColor"]]:
        """Return (title, points, color) for a task metric chart, or None if no task."""
        rng = self._stats_range()
        lo = hi = None
        if rng is not None:
            lo, hi, _ = rng
        scope = self._scope_suffix()
        if kind == "interval":
            iid = self._plot_interval_id or mk
            pts = _interval_plot_points(trace, iid, lo, hi)
            if not pts:
                return None
            title = f"Interval {iid} — Duration{scope}"
            color = QColor(_interval_color(iid))
            return title, pts, color
        segs = trace.seg_map_by_merge_key.get(mk, [])
        if not segs:
            return None
        raw = trace.task_repr.get(mk, mk)
        name = _task_display_name(raw)
        color = _task_color(raw)
        if kind == "exec":
            if lo is not None and hi is not None:
                segs = [s for s in segs if _seg_fully_in_range(s, lo, hi)]
            pts = [(s.start, s.end - s.start, s)
                   for s in segs if s.end > s.start]
            title = f"{name} — Execution Time{scope}"
        elif kind == "block":
            ordered = sorted(segs, key=lambda s: s.start)
            pts = []
            for i in range(1, len(ordered)):
                prev, nxt = ordered[i - 1], ordered[i]
                if lo is not None and hi is not None:
                    if not (_seg_fully_in_range(prev, lo, hi)
                            and _seg_fully_in_range(nxt, lo, hi)):
                        continue
                gap = nxt.start - prev.end
                if gap > 0:
                    pts.append((nxt.start, gap, nxt))
            title = f"{name} — Blocking Time{scope}"
        elif kind == "inter":
            starts = sorted(s.start for s in segs)
            start_to_seg = {s.start: s for s in segs}
            pts = []
            for i in range(1, len(starts)):
                if starts[i] <= starts[i - 1]:
                    continue
                if lo is not None and hi is not None and (starts[i] < lo or starts[i] > hi):
                    continue
                pts.append((starts[i], starts[i] - starts[i - 1],
                            start_to_seg.get(starts[i])))
            title = f"{name} — Inter-Arrival Time{scope}"
        elif kind == "preempt":
            preemptor = self._plot_preemptor
            if not preemptor:
                return None
            pts = _preemption_chain_plot_points(trace, mk, preemptor, lo, hi)
            title = f"{name} ← preempted by {preemptor}{scope}"
        else:
            return None
        return title, pts, color

    def _on_plot_dialog_closed(self) -> None:
        self._plot_dlg = None
        self._plot_mk = None
        self._plot_kind = None
        self._plot_preemptor = None
        self._plot_interval_id = None

    def _open_interval_plot(self, trace: "BtfTrace", interval_id: str) -> None:
        self._open_plot(trace, interval_id, "interval", interval_id=interval_id)

    def capture_plot_session(self) -> Tuple[Optional[str], Optional[str], bool, Optional[str]]:
        """Return (mk, kind, visible, preemptor) for the current metrics plot dialog."""
        open_ = self._plot_dlg is not None and self._plot_dlg.isVisible()
        return self._plot_mk, self._plot_kind, open_, self._plot_preemptor

    def clear_plot_session(self) -> None:
        """Close the metrics plot and clear tracking (used on tab switch)."""
        if self._plot_dlg is not None:
            try:
                self._plot_dlg.closed.disconnect(self._on_plot_dialog_closed)
            except TypeError:
                pass
            self._plot_dlg.close()
        self._plot_dlg = None
        self._plot_mk = None
        self._plot_kind = None
        self._plot_preemptor = None
        self._plot_interval_id = None

    def restore_plot_session(self, trace: Optional["BtfTrace"],
                             mk: Optional[str], kind: Optional[str],
                             open_: bool,
                             preemptor: Optional[str] = None) -> None:
        """Re-open the metrics plot saved for a trace tab, if it was visible."""
        self.clear_plot_session()
        if not open_ or not mk or not kind or trace is None:
            return
        self._open_plot(trace, mk, kind, preemptor=preemptor)

    def _refresh_open_plot(self) -> None:
        """Live-update the metrics popup when cursors or scope change."""
        dlg = self._plot_dlg
        if (dlg is None or not dlg.isVisible()
                or self._trace is None or self._plot_mk is None
                or self._plot_kind is None):
            return
        built = self._build_plot_points(self._trace, self._plot_mk, self._plot_kind)
        if built is None:
            return
        title, pts, _color = built
        scoped, badge, detail = self._plot_scope_banner()
        dlg.update_data(title, pts, scope_scoped=scoped,
                        scope_badge=badge, scope_detail=detail)

    def _open_plot(self, trace, mk: str, kind: str,
                   preemptor: Optional[str] = None,
                   interval_id: Optional[str] = None) -> None:
        """Open a metrics distribution popup for the given task and metric kind."""
        self._plot_preemptor = preemptor
        self._plot_interval_id = interval_id
        built = self._build_plot_points(trace, mk, kind)
        if built is None:
            return
        title, pts, color = built
        if not pts:
            return
        scoped, badge, detail = self._plot_scope_banner()
        self._plot_mk = mk
        self._plot_kind = kind
        _on_click = self._on_plot_scatter_click
        if self._plot_dlg is not None:
            try:
                self._plot_dlg.closed.disconnect(self._on_plot_dialog_closed)
            except TypeError:
                pass
            self._plot_dlg.close()
        self._plot_dlg = _MetricsPlotDialog(
            title, pts, trace.time_scale, color,
            on_point_click=_on_click,
            is_dark=self._is_dark,
            scope_scoped=scoped,
            scope_badge=badge,
            scope_detail=detail,
            parent=self.window(),
        )
        self._plot_dlg.closed.connect(self._on_plot_dialog_closed)
        self._plot_dlg.show()

    def _on_plot_scatter_click(self, x_ns: int, y_ns: int, payload) -> None:
        """Scatter plot point: jump timeline and add an annotation (not a cursor)."""
        if self._trace is None or payload is None:
            return
        note = _format_plot_point_note(
            self._trace, self._plot_kind or "", self._plot_mk,
            self._plot_preemptor, x_ns, y_ns, payload)
        mark_ns = _plot_point_mark_ns(payload, x_ns)
        self.plot_point_clicked.emit(payload, mark_ns, note)

    def _sep(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        return f

    def _update_section_header_icon(self, section_id: str) -> None:
        hdr = self._section_headers.get(section_id)
        if hdr is not None:
            collapsed = self._section_collapsed.get(section_id, False)
            hdr.setIcon(_stats_chevron_icon(collapsed, self._is_dark))

    def _ensure_section_body(self, section_id: str) -> None:
        """Create a section body on first expand; reuse on later toggles."""
        body = self._section_bodies.get(section_id)
        if body is not None:
            body.setVisible(True)
            return
        populate = self._section_populate.get(section_id)
        hdr = self._section_headers.get(section_id)
        if populate is None or hdr is None:
            return
        body = QWidget()
        blay = QVBoxLayout(body)
        blay.setContentsMargins(0, 0, 0, 0)
        blay.setSpacing(2)
        populate(blay)
        idx = self._ilay.indexOf(hdr)
        self._ilay.insertWidget(idx + 1, body)
        self._section_bodies[section_id] = body

    def _set_section_collapsed(self, section_id: str, collapsed: bool) -> None:
        self._section_collapsed[section_id] = collapsed
        if collapsed:
            body = self._section_bodies.get(section_id)
            if body is not None:
                body.setVisible(False)
        else:
            self._ensure_section_body(section_id)
        self._update_section_header_icon(section_id)

    def _toggle_section(self, section_id: str) -> None:
        self._set_section_collapsed(
            section_id, not self._section_collapsed.get(section_id, False))

    def _expand_all_sections(self) -> None:
        self._inner.setUpdatesEnabled(False)
        try:
            for key in self._section_collapsed:
                self._set_section_collapsed(key, False)
        finally:
            self._inner.setUpdatesEnabled(True)

    def _collapse_all_sections(self) -> None:
        self._inner.setUpdatesEnabled(False)
        try:
            for key in self._section_collapsed:
                self._set_section_collapsed(key, True)
        finally:
            self._inner.setUpdatesEnabled(True)

    def _add_collapsible_section(self, section_id: str, title: str, ui_fs: str,
                               populate) -> None:
        """Add a collapsible statistics section (parity with web StatisticsPanel)."""
        self._ilay.addWidget(self._sep())
        collapsed = self._section_collapsed.get(section_id, False)
        hdr = QPushButton(title)
        hdr.setFlat(True)
        hdr.setCursor(Qt.PointingHandCursor)
        hdr.setIcon(_stats_chevron_icon(collapsed, self._is_dark))
        hdr.setIconSize(QSize(10, 10))
        hdr.setStyleSheet(
            f"text-align:left; padding:2px 0 2px 2px; border:none; background:transparent;"
            f" font-weight:bold; font-size:{ui_fs};"
        )
        hdr.clicked.connect(
            lambda _checked=False, sid=section_id: self._toggle_section(sid))
        self._ilay.addWidget(hdr)
        self._section_headers[section_id] = hdr
        self._section_populate[section_id] = populate
        if not collapsed:
            self._ensure_section_body(section_id)

    def _core_util_rows(self, trace: "BtfTrace",
                        lo: Optional[int] = None, hi: Optional[int] = None) -> List[Tuple[str, float]]:
        if lo is not None and hi is not None:
            total_ns = hi - lo
        else:
            total_ns = trace.time_max - trace.time_min
        if total_ns <= 0:
            return []
        rows: List[Tuple[str, float]] = []
        for core in trace.core_names:
            segs = trace.core_segs.get(core, [])
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

    def _task_cpu_rows(self, trace: "BtfTrace", limit: int = 10,
                       lo: Optional[int] = None, hi: Optional[int] = None) -> List[Tuple[str, str, float]]:
        if lo is not None and hi is not None:
            total_ns = hi - lo
        else:
            total_ns = trace.time_max - trace.time_min
        if total_ns <= 0:
            return []
        task_times: Dict[str, int] = {}
        for mk, segs in trace.seg_map_by_merge_key.items():
            raw = trace.task_repr.get(mk, mk)
            _, _, tname = _parse_task_name(raw)
            if _is_idle_task_name(tname) or tname == "TICK":
                continue
            if lo is not None and hi is not None:
                task_times[mk] = sum(_seg_overlap_ns(s, lo, hi) for s in segs)
            else:
                task_times[mk] = sum(s.end - s.start for s in segs)

        rows: List[Tuple[str, str, float]] = []
        for mk, t_ns in sorted(task_times.items(), key=lambda kv: kv[1], reverse=True)[:limit]:
            if t_ns <= 0:
                continue
            raw = trace.task_repr.get(mk, mk)
            rows.append((mk, _task_display_name(raw), 100.0 * t_ns / total_ns))
        return rows

    def _summarize_samples(self, samples: List[int], scale: str) -> Optional[Tuple[str, str, str, str]]:
        if not samples:
            return None
        vals = sorted(samples)
        n = len(vals)
        p95_idx = min(n - 1, math.ceil(n * 0.95) - 1)
        avg = int(round(sum(vals) / n))
        return (
            _format_time(vals[0], scale),
            _format_time(avg, scale),
            _format_time(vals[-1], scale),
            _format_time(vals[p95_idx], scale),
        )

    def _summarize_samples_export(self, samples: List[int], scale: str) -> Optional[Tuple[str, str, str, str, str, str]]:
        if not samples:
            return None
        vals = sorted(samples)
        n = len(vals)
        p50_idx = min(n - 1, math.ceil(n * 0.50) - 1)
        p95_idx = min(n - 1, math.ceil(n * 0.95) - 1)
        avg = int(round(sum(vals) / n))
        trim_n = int(math.floor(n * 0.05))
        trim_vals = vals[trim_n:n - trim_n] if (2 * trim_n) < n else vals
        trim_avg = int(round(sum(trim_vals) / len(trim_vals)))
        return (
            _format_time(vals[0], scale),
            _format_time(avg, scale),
            _format_time(trim_avg, scale),
            _format_time(vals[-1], scale),
            _format_time(vals[p50_idx], scale),
            _format_time(vals[p95_idx], scale),
        )

    def _exec_slice_samples(self, segs: list,
                            lo: Optional[int] = None, hi: Optional[int] = None) -> List[int]:
        if lo is not None and hi is not None:
            return [s.end - s.start for s in segs
                    if (s.end - s.start) > 0 and _seg_fully_in_range(s, lo, hi)]
        return [s.end - s.start for s in segs if (s.end - s.start) > 0]

    def _inter_arrival_samples(self, segs: list,
                               lo: Optional[int] = None, hi: Optional[int] = None) -> List[int]:
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

    def _exec_slice_rows(self, trace: "BtfTrace",
                         lo: Optional[int] = None, hi: Optional[int] = None) -> List[Tuple[str, int, float, str, str, str, str]]:
        rows: List[Tuple[str, int, float, str, str, str, str]] = []
        if lo is not None and hi is not None:
            total_ns = hi - lo
        else:
            total_ns = trace.time_max - trace.time_min
        if total_ns <= 0:
            return rows
        for mk, segs in trace.seg_map_by_merge_key.items():
            if not segs:
                continue
            raw = trace.task_repr.get(mk, mk)
            _, _, tname = _parse_task_name(raw)
            if _is_idle_task_name(tname) or tname == "TICK":
                continue
            samples = self._exec_slice_samples(segs, lo, hi)
            summary = self._summarize_samples(samples, trace.time_scale)
            if summary is None:
                continue
            mn, avg, mx, p95 = summary
            cpu_pct = 100.0 * sum(samples) / total_ns
            rows.append((mk, _task_display_name(raw), len(samples), cpu_pct, mn, avg, mx, p95))
        rows.sort(key=lambda r: (-r[3], -r[2], r[1].lower()))
        return rows

    def _inter_arrival_rows(self, trace: "BtfTrace",
                            lo: Optional[int] = None, hi: Optional[int] = None) -> List[Tuple[str, int, str, str, str, str]]:
        rows: List[Tuple[str, int, str, str, str, str]] = []
        for mk, segs in trace.seg_map_by_merge_key.items():
            if len(segs) < 2:
                continue
            raw = trace.task_repr.get(mk, mk)
            _, _, tname = _parse_task_name(raw)
            if _is_idle_task_name(tname) or tname == "TICK":
                continue
            samples = self._inter_arrival_samples(segs, lo, hi)
            summary = self._summarize_samples(samples, trace.time_scale)
            if summary is None:
                continue
            mn, avg, mx, p95 = summary
            if lo is not None and hi is not None:
                n_runs = sum(1 for s in segs if lo <= s.start <= hi)
            else:
                n_runs = len(segs)
            rows.append((mk, _task_display_name(raw), n_runs, mn, avg, mx, p95))
        rows.sort(key=lambda r: (-r[2], r[1].lower()))
        return rows

    def _blocking_time_rows(self, trace: "BtfTrace",
                            lo: Optional[int] = None, hi: Optional[int] = None
                            ) -> List[Tuple[str, int, str, str, str, str]]:
        rows: List[Tuple[str, int, str, str, str, str]] = []
        for mk, segs in trace.seg_map_by_merge_key.items():
            if len(segs) < 2:
                continue
            raw = trace.task_repr.get(mk, mk)
            _, _, tname = _parse_task_name(raw)
            if _is_idle_task_name(tname) or tname == "TICK":
                continue
            samples = _blocking_time_samples(segs, lo, hi)
            summary = self._summarize_samples(samples, trace.time_scale)
            if summary is None:
                continue
            mn, avg, mx, p95 = summary
            rows.append((mk, _task_display_name(raw), len(samples), mn, avg, mx, p95))
        rows.sort(key=lambda r: (-r[2], r[1].lower()))
        return rows

    def _blocking_time_rows_export(self, trace: "BtfTrace",
                                   lo: Optional[int] = None, hi: Optional[int] = None
                                   ) -> List[Tuple[str, int, str, str, str, str, str, str]]:
        rows: List[Tuple[str, int, str, str, str, str, str, str]] = []
        for mk, segs in trace.seg_map_by_merge_key.items():
            if len(segs) < 2:
                continue
            raw = trace.task_repr.get(mk, mk)
            _, _, tname = _parse_task_name(raw)
            if _is_idle_task_name(tname) or tname == "TICK":
                continue
            samples = _blocking_time_samples(segs, lo, hi)
            summary = self._summarize_samples_export(samples, trace.time_scale)
            if summary is None:
                continue
            mn, avg, tmean, mx, p50, p95 = summary
            rows.append((mk, _task_display_name(raw), len(samples), mn, avg, tmean, mx, p50, p95))
        rows.sort(key=lambda r: (-r[2], r[1].lower()))
        return rows

    def _activate_extreme_segment(self, trace: "BtfTrace", mk: str, kind: str,
                                  seg: Optional["TaskSegment"], find_max: bool) -> None:
        if seg is None:
            return
        note = _format_extreme_segment_note(trace, mk, kind, seg, find_max)
        self.plot_point_clicked.emit(seg, seg.start, note)

    def _on_wcet_click(self, trace: "BtfTrace", mk: str,
                       lo: Optional[int], hi: Optional[int]) -> None:
        segs = trace.seg_map_by_merge_key.get(mk, [])
        self._activate_extreme_segment(
            trace, mk, "exec", _find_wcet_segment(segs, lo, hi), True)

    def _on_bcet_click(self, trace: "BtfTrace", mk: str,
                       lo: Optional[int], hi: Optional[int]) -> None:
        segs = trace.seg_map_by_merge_key.get(mk, [])
        self._activate_extreme_segment(
            trace, mk, "exec", _find_bcet_segment(segs, lo, hi), False)

    def _on_blocking_extreme_click(self, trace: "BtfTrace", mk: str,
                                   lo: Optional[int], hi: Optional[int],
                                   find_max: bool) -> None:
        segs = trace.seg_map_by_merge_key.get(mk, [])
        self._activate_extreme_segment(
            trace, mk, "block",
            _find_extreme_blocking_segment(segs, lo, hi, find_max=find_max),
            find_max)

    def _on_inter_extreme_click(self, trace: "BtfTrace", mk: str,
                                lo: Optional[int], hi: Optional[int],
                                find_max: bool) -> None:
        segs = trace.seg_map_by_merge_key.get(mk, [])
        self._activate_extreme_segment(
            trace, mk, "inter",
            _find_extreme_inter_arrival_segment(segs, lo, hi, find_max=find_max),
            find_max)

    def _exec_slice_rows_export(self, trace: "BtfTrace",
                                lo: Optional[int] = None, hi: Optional[int] = None) -> List[Tuple[str, int, float, str, str, str, str, str, str]]:
        rows: List[Tuple[str, int, float, str, str, str, str, str, str]] = []
        if lo is not None and hi is not None:
            total_ns = hi - lo
        else:
            total_ns = trace.time_max - trace.time_min
        if total_ns <= 0:
            return rows
        for mk, segs in trace.seg_map_by_merge_key.items():
            if not segs:
                continue
            raw = trace.task_repr.get(mk, mk)
            _, _, tname = _parse_task_name(raw)
            if _is_idle_task_name(tname) or tname == "TICK":
                continue
            samples = self._exec_slice_samples(segs, lo, hi)
            summary = self._summarize_samples_export(samples, trace.time_scale)
            if summary is None:
                continue
            mn, avg, tmean, mx, p50, p95 = summary
            cpu_pct = 100.0 * sum(samples) / total_ns
            rows.append((mk, _task_display_name(raw), len(samples), cpu_pct, mn, avg, tmean, mx, p50, p95))
        rows.sort(key=lambda r: (-r[3], -r[2], r[1].lower()))
        return rows

    def _inter_arrival_rows_export(self, trace: "BtfTrace",
                                   lo: Optional[int] = None, hi: Optional[int] = None) -> List[Tuple[str, int, str, str, str, str, str, str]]:
        rows: List[Tuple[str, int, str, str, str, str, str, str]] = []
        for mk, segs in trace.seg_map_by_merge_key.items():
            if len(segs) < 2:
                continue
            raw = trace.task_repr.get(mk, mk)
            _, _, tname = _parse_task_name(raw)
            if _is_idle_task_name(tname) or tname == "TICK":
                continue
            samples = self._inter_arrival_samples(segs, lo, hi)
            summary = self._summarize_samples_export(samples, trace.time_scale)
            if summary is None:
                continue
            mn, avg, tmean, mx, p50, p95 = summary
            if lo is not None and hi is not None:
                n_runs = sum(1 for s in segs if lo <= s.start <= hi)
            else:
                n_runs = len(segs)
            rows.append((mk, _task_display_name(raw), n_runs, mn, avg, tmean, mx, p50, p95))
        rows.sort(key=lambda r: (-r[2], r[1].lower()))
        return rows

    def _build_stats_table(self, rows: List[tuple], ui_fs: str, empty_hint: str,
                           include_cpu: bool = False,
                           count_header: str = "Runs",
                           section_id: str = "exec",
                           migrations: bool = False,
                           on_row_click=None, on_min_click=None,
                           on_max_click=None) -> QWidget:
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        if not rows:
            lay.addWidget(self._lbl(empty_hint, color="#888888", ui_fs=ui_fs))
            return host

        if migrations:
            headers = ["Task", "Migr", "Cores", "Primary", "Ping", "STI±",
                       "Gap after", "Gap other"]
            cols = len(headers)
        else:
            cols = 7 if include_cpu else 6
            headers = (["Task", count_header, "CPU%", "Min", "Avg", "Max", "p95"]
                       if include_cpu
                       else ["Task", count_header, "Min", "Avg", "Max", "p95"])
        table = QTableWidget(len(rows), cols)
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.setFocusPolicy(Qt.NoFocus)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(migrations)
        table.setShowGrid(False)
        table.setFrameShape(QFrame.NoFrame)
        table.verticalHeader().setDefaultSectionSize(STATS_TABLE_ROW_H)
        table.verticalHeader().setMinimumSectionSize(STATS_TABLE_ROW_H)
        table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        table.horizontalHeader().setFixedHeight(18)
        table.horizontalHeader().setSectionsClickable(True)
        table.horizontalHeader().setSortIndicatorShown(True)
        if migrations:
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        _default_bg = self._apply_stats_table_theme(table, ui_fs)

        _min_col = 3 if include_cpu else 2
        _max_col = 5 if include_cpu else 4
        _link_color = QBrush(QColor("#88AAFF"))
        _hover_bg = QBrush(QColor("#3A3A50") if self._is_dark else QColor("#E0E0EC"))
        _hovered_row = [-1]
        _interactive = bool(on_row_click or on_min_click or on_max_click)
        _row_tip = "Click to view distribution chart"

        def _clear_row_hover() -> None:
            row = _hovered_row[0]
            if row < 0:
                return
            for c in range(cols):
                item = table.item(row, c)
                if item is not None:
                    item.setBackground(_default_bg)
            _hovered_row[0] = -1

        def _set_row_hover(row: int) -> None:
            if not _interactive or row < 0:
                return
            if row == _hovered_row[0]:
                return
            _clear_row_hover()
            _hovered_row[0] = row
            for c in range(cols):
                item = table.item(row, c)
                if item is not None:
                    item.setBackground(_hover_bg)

        for r, row in enumerate(rows):
            if migrations:
                mk, name, n_mig, n_cores, _cores, primary, primary_pct, ping, sti, g_after, g_other = row
                vals = [
                    name, str(n_mig), str(n_cores),
                    f"{primary} ({primary_pct:.0f}%)",
                    str(ping), str(sti), g_after, g_other,
                ]
                sort_keys = [
                    name.lower(), n_mig, n_cores, primary_pct, ping, sti,
                    _time_label_sort_key(g_after), _time_label_sort_key(g_other),
                ]
            elif include_cpu:
                mk_r, name, runs, cpu, mn, avg, mx, p95 = row
                vals = [name, runs, f"{cpu:.1f}%", mn, avg, mx, p95]
                sort_keys = [
                    name.lower(), runs, cpu,
                    _time_label_sort_key(mn), _time_label_sort_key(avg),
                    _time_label_sort_key(mx), _time_label_sort_key(p95),
                ]
            else:
                mk_r, name, runs, mn, avg, mx, p95 = row
                vals = [name, runs, mn, avg, mx, p95]
                sort_keys = [
                    name.lower(), runs,
                    _time_label_sort_key(mn), _time_label_sort_key(avg),
                    _time_label_sort_key(mx), _time_label_sort_key(p95),
                ]

            for c, v in enumerate(vals):
                item = _StatsSortItem(v, sort_keys[c])
                item.setBackground(_default_bg)
                if migrations:
                    if c == 0:
                        item.setData(Qt.UserRole, mk)
                elif c == 0:
                    item.setData(Qt.UserRole, mk_r)
                    tip = (f"{_row_tip} for {name}"
                           if on_row_click is not None else str(name))
                    item.setToolTip(tip)
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if not migrations:
                    if c == _min_col and on_min_click is not None:
                        item.setToolTip(f"Click to jump to shortest slice for {name}")
                        item.setForeground(_link_color)
                    elif c == _max_col and on_max_click is not None:
                        item.setToolTip(
                            f"Click to jump to longest slice (WCET) for {name}"
                            if include_cpu else
                            f"Click to jump to longest sample for {name}")
                        item.setForeground(_link_color)
                    elif on_row_click is not None:
                        item.setToolTip(f"{_row_tip} for {name}")
                table.setItem(r, c, item)

        if not migrations:
            table.resizeColumnsToContents()
            table.horizontalHeader().setStretchLastSection(False)
            p95_col = 6 if include_cpu else 5
            table.setColumnWidth(p95_col, min(table.columnWidth(p95_col), 76))
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        table.setAlternatingRowColors(False)
        table.setShowGrid(False)

        if _interactive:
            if migrations:
                def _cell_clicked_mig(_row: int, _col: int) -> None:
                    item = table.item(_row, 0)
                    if item is not None and on_row_click is not None:
                        on_row_click(item.data(Qt.UserRole))
                table.cellClicked.connect(_cell_clicked_mig)
            else:
                def _cell_clicked(r: int, c: int) -> None:
                    item = table.item(r, 0)
                    if item is None:
                        return
                    mk = item.data(Qt.UserRole)
                    if mk is None:
                        return
                    if on_min_click is not None and c == _min_col:
                        on_min_click(mk)
                    elif on_max_click is not None and c == _max_col:
                        on_max_click(mk)
                    elif on_row_click is not None:
                        on_row_click(mk)
                table.cellClicked.connect(_cell_clicked)
            table.setCursor(Qt.PointingHandCursor)
            table.setMouseTracking(True)
            table.viewport().setMouseTracking(True)
            if migrations:
                table.cellEntered.connect(_set_row_hover)
            else:
                table.itemEntered.connect(
                    lambda item: _set_row_hover(item.row()) if item is not None else None)
            _hover_filter = _StatsTableHoverFilter(_clear_row_hover)
            table.viewport().installEventFilter(_hover_filter)
            host._stats_hover_filter = _hover_filter  # prevent GC

        table.setWordWrap(False)

        for r in range(table.rowCount()):
            table.setRowHeight(r, STATS_TABLE_ROW_H)

        table.setSortingEnabled(True)

        self._wrap_table_with_resizer(lay, table, section_id)
        return host

    def _build_preemption_table(self, rows: List[tuple], ui_fs: str,
                                empty_hint: str, on_row_click=None) -> QWidget:
        """Specialised stats table for Preemption Chain (Victim | Preemptor | Count | Total | Avg | Max)."""
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        if not rows:
            lay.addWidget(self._lbl(empty_hint, color="#888888", ui_fs=ui_fs))
            return host

        headers = ["Victim", "Preemptor", "Count", "Total", "Avg", "Max"]
        cols = len(headers)
        table = QTableWidget(len(rows), cols)
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.setFocusPolicy(Qt.NoFocus)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.setShowGrid(False)
        table.setFrameShape(QFrame.NoFrame)
        table.verticalHeader().setDefaultSectionSize(STATS_TABLE_ROW_H)
        table.verticalHeader().setMinimumSectionSize(STATS_TABLE_ROW_H)
        table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        table.horizontalHeader().setFixedHeight(18)
        table.horizontalHeader().setSectionsClickable(True)
        table.horizontalHeader().setSortIndicatorShown(True)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        _default_bg = self._apply_stats_table_theme(table, ui_fs)
        _hover_bg = QBrush(QColor("#3A3A50") if self._is_dark else QColor("#E0E0EC"))
        _hovered_row = [-1]

        def _clear_hover() -> None:
            row = _hovered_row[0]
            if row < 0:
                return
            for c in range(cols):
                item = table.item(row, c)
                if item is not None:
                    item.setBackground(_default_bg)
            _hovered_row[0] = -1

        def _set_hover(row: int) -> None:
            if row == _hovered_row[0]:
                return
            _clear_hover()
            _hovered_row[0] = row
            for c in range(cols):
                item = table.item(row, c)
                if item is not None:
                    item.setBackground(_hover_bg)

        for r, row in enumerate(rows):
            mk, victim, preemptor, count, total, avg, mx = row
            sort_keys = [
                victim.lower(), preemptor.lower(), count,
                _time_label_sort_key(total),
                _time_label_sort_key(avg),
                _time_label_sort_key(mx),
            ]
            vals = [victim, preemptor, str(count), total, avg, mx]
            for c, v in enumerate(vals):
                item = _StatsSortItem(v, sort_keys[c])
                item.setBackground(_default_bg)
                if c == 0:
                    item.setData(Qt.UserRole, mk)
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    item.setToolTip("Click to view preemption distribution chart")
                elif c == 1:
                    item.setData(Qt.UserRole, preemptor)
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    item.setToolTip("Click to view preemption distribution chart")
                else:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(r, c, item)

        table.setAlternatingRowColors(False)
        table.setWordWrap(False)
        for r in range(table.rowCount()):
            table.setRowHeight(r, STATS_TABLE_ROW_H)
        table.setSortingEnabled(True)

        if on_row_click is not None:
            def _cell_clicked(row: int, _col: int) -> None:
                mk_item = table.item(row, 0)
                pre_item = table.item(row, 1)
                if mk_item is not None and pre_item is not None:
                    preemptor = pre_item.data(Qt.UserRole)
                    if preemptor is not None:
                        on_row_click(mk_item.data(Qt.UserRole), preemptor)
            table.cellClicked.connect(_cell_clicked)
            table.setCursor(Qt.PointingHandCursor)
            table.setMouseTracking(True)
            table.viewport().setMouseTracking(True)
            table.cellEntered.connect(_set_hover)
            _hover_filter = _StatsTableHoverFilter(_clear_hover)
            table.viewport().installEventFilter(_hover_filter)
            host._preempt_hover_filter = _hover_filter

        self._wrap_table_with_resizer(lay, table, "preemption")
        return host

    def _export_html(self) -> None:
        trace = self._trace
        if trace is None:
            return

        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Statistics HTML",
            f"statistics-{stamp}.html",
            "HTML files (*.html);;All files (*)",
        )
        if not path:
            return

        rng = self._stats_range()
        lo = hi = None
        if rng is not None:
            lo, hi, _n_cur = rng
            total_ns = hi - lo
            span_str = _format_time(total_ns, trace.time_scale)
            scope_title = f" (cursor range C1–C{_n_cur})"
        else:
            total_ns = trace.time_max - trace.time_min
            span_str = _format_time(total_ns, trace.time_scale)
            scope_title = ""

        if lo is not None and hi is not None:
            sti_count = sum(
                1 for ev in trace.sti_events
                if not _is_tag_sti_channel(ev.target) and lo <= ev.time <= hi)
        else:
            sti_count = sum(1 for ev in trace.sti_events if not _is_tag_sti_channel(ev.target))
        core_rows = self._core_util_rows(trace, lo, hi)
        task_rows = self._task_cpu_rows(trace, lo=lo, hi=hi)
        exec_rows = self._exec_slice_rows_export(trace, lo, hi)
        inter_rows = self._inter_arrival_rows_export(trace, lo, hi)
        block_rows = self._blocking_time_rows_export(trace, lo, hi)
        mig_rows = _migration_rows(trace, lo, hi)
        preempt_rows, _ = _preemption_chain_rows(trace, lo, hi)
        interval_rows = _interval_stats_rows(trace, lo, hi)
        ctx_count, core_gaps = _scheduling_stats(trace, lo, hi)
        tick = _tick_health_report(trace, lo, hi)

        def _esc(v: object) -> str:
            return html.escape(str(v), quote=True)

        sched_kpi = ""
        if ctx_count > 0 or core_gaps:
            gap_avg = int(round(sum(core_gaps) / len(core_gaps))) if core_gaps else 0
            gap_max = max(core_gaps) if core_gaps else 0
            sched_kpi = (
                f"<article class=\"kpi\"><div class=\"k\">Context switches{_esc(scope_title)}</div>"
                f"<div class=\"v\">{ctx_count:,}</div></article>"
            )
            if core_gaps:
                sched_kpi += (
                    f"<article class=\"kpi\"><div class=\"k\">Core gap avg{_esc(scope_title)}</div>"
                    f"<div class=\"v\">{_esc(_format_time(gap_avg, trace.time_scale))}</div></article>"
                    f"<article class=\"kpi\"><div class=\"k\">Core gap max{_esc(scope_title)}</div>"
                    f"<div class=\"v\">{_esc(_format_time(gap_max, trace.time_scale))}</div></article>"
                )

        def _render_stats_table(title: str,
                                rows: List[Tuple[str, int, str, str, str, str, str, str]]) -> str:
            body = "".join(
                f"<tr><td>{_esc(name)}</td><td>{runs}</td><td>{_esc(mn)}</td><td>{_esc(avg)}</td><td>{_esc(tmean)}</td><td>{_esc(mx)}</td><td>{_esc(p50)}</td><td>{_esc(p95)}</td></tr>"
                for mk_r, name, runs, mn, avg, tmean, mx, p50, p95 in rows
            ) or '<tr><td colspan="8" class="empty">No data</td></tr>'
            return (
                f"<section class=\"report-card\"><h2>{_esc(title)}</h2>"
                "<table><thead><tr><th>Task</th><th>Runs</th><th>Min</th><th>Avg</th><th>TrimMean(5%)</th><th>Max</th><th>p50</th><th>p95</th></tr></thead>"
                f"<tbody>{body}</tbody></table></section>"
            )

        def _render_exec_table(rows: List[Tuple[str, int, float, str, str, str, str, str, str]]) -> str:
            body = "".join(
                f"<tr><td>{_esc(name)}</td><td>{runs}</td><td>{cpu:.1f}%</td><td>{_esc(mn)}</td><td>{_esc(avg)}</td><td>{_esc(tmean)}</td><td>{_esc(mx)}</td><td>{_esc(p50)}</td><td>{_esc(p95)}</td></tr>"
                for mk_r, name, runs, cpu, mn, avg, tmean, mx, p50, p95 in rows
            ) or '<tr><td colspan="9" class="empty">No data</td></tr>'
            return (
                f"<section class=\"report-card\"><h2>Execution Time Per Slice{_esc(scope_title)}</h2>"
                "<table><thead><tr><th>Task</th><th>Runs</th><th>CPU%</th><th>Min</th><th>Avg</th><th>TrimMean(5%)</th><th>Max</th><th>p50</th><th>p95</th></tr></thead>"
                f"<tbody>{body}</tbody></table></section>"
            )

        core_body = "".join(
            f"<tr><td>{_esc(core)}</td><td>{pct:.1f}%</td></tr>"
            for core, pct in core_rows
        ) or '<tr><td colspan="2" class="empty">No data</td></tr>'

        task_body = "".join(
            f"<tr><td>{_esc(name)}</td><td>{pct:.1f}%</td></tr>"
            for _, name, pct in task_rows
        ) or '<tr><td colspan="2" class="empty">No data</td></tr>'

        if tick["tick_count"]:
            tick_gap_body = "".join(
                f"<tr><td>{_esc(_format_time(s, trace.time_scale))}</td>"
                f"<td>{_esc(_format_time(e, trace.time_scale))}</td>"
                f"<td>{_esc(_format_time(d, trace.time_scale))}</td><td>{missed}</td></tr>"
                for s, e, d, missed in tick["large_gaps"]
            ) or '<tr><td colspan="4" class="empty">No large gaps</td></tr>'
            tick_health_html = f"""
    <section class=\"report-card\">
    <h2>Trace Health (TICK){_esc(scope_title)}</h2>
    <table>
      <tbody>
        <tr><td>Status</td><td>{_esc(tick['health'].upper())}</td></tr>
        <tr><td>Ticks</td><td>{tick['tick_count']:,}</td></tr>
        <tr><td>Avg period</td><td>{_esc(_format_time(tick['avg_period'], trace.time_scale))}</td></tr>
        <tr><td>Max gap</td><td>{_esc(_format_time(tick['max_gap'], trace.time_scale))}</td></tr>
        <tr><td>Missed ticks (est.)</td><td>{tick['missed_estimate']}</td></tr>
      </tbody>
    </table>
    <h2 style=\"margin-top:12px;font-size:14px;\">Large TICK gaps</h2>
    <table>
      <thead><tr><th>Start</th><th>End</th><th>Gap</th><th>Missed</th></tr></thead>
      <tbody>{tick_gap_body}</tbody>
    </table>
  </section>"""
        else:
            tick_health_html = (
                f"<section class=\"report-card\"><h2>Trace Health (TICK){_esc(scope_title)}</h2>"
                "<p class=\"empty\">No STI TICK events</p></section>"
            )

        if lo is not None and hi is not None:
            task_count = sum(
                1 for _segs in trace.seg_map_by_merge_key.values()
                if any(_seg_overlaps_range(s, lo, hi) for s in _segs)
            )
            seg_count = sum(1 for s in trace.segments if _seg_overlaps_range(s, lo, hi))
            range_note = (
                f"<li><strong>Cursor range:</strong> C1–C{_n_cur}, "
                f"{_esc(_format_time(lo, trace.time_scale))} … "
                f"{_esc(_format_time(hi, trace.time_scale))}. "
                f"CPU% uses overlapping active time; slice metrics use segments fully inside the range.</li>"
            )
        else:
            task_count = len(trace.tasks)
            seg_count = len(trace.segments)
            range_note = ""

        report = f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>BTF Statistics Report</title>
  <style>
        :root {{
            --bg: #e9edf3;
            --paper: #ffffff;
            --ink: #182230;
            --muted: #5f6f82;
            --line: #d9e0ea;
            --line-strong: #c8d2e0;
            --header: #16324f;
            --accent: #2a6fb2;
            --stripe: #f7f9fc;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            padding: 28px;
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            color: var(--ink);
            background: radial-gradient(circle at top right, #f6f8fb 0%, var(--bg) 52%, #dde4ee 100%);
        }}
        .report {{ max-width: 1160px; margin: 0 auto; }}
        .report-head {{
            background: linear-gradient(135deg, var(--header) 0%, #21496f 100%);
            color: #f3f7fd;
            border-radius: 14px;
            padding: 20px 24px;
            box-shadow: 0 10px 28px rgba(17, 44, 69, 0.24);
            margin-bottom: 18px;
        }}
        h1 {{ margin: 0; font-size: 28px; letter-spacing: 0.2px; }}
        .sub {{ margin-top: 6px; color: #cfe1f7; font-size: 13px; }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 10px;
            margin-bottom: 16px;
        }}
        .kpi {{
            background: var(--paper);
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 12px 14px;
            box-shadow: 0 2px 8px rgba(30, 60, 90, 0.06);
        }}
        .kpi .k {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.6px; }}
        .kpi .v {{ margin-top: 4px; font-size: 20px; font-weight: 700; color: #0f2b47; }}
        .report-card {{
            margin: 14px 0;
            background: var(--paper);
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 12px 14px 14px;
            box-shadow: 0 2px 10px rgba(30, 60, 90, 0.06);
        }}
        h2 {{ margin: 0 0 10px 0; color: #123355; font-size: 17px; }}
        .notes {{ border-left: 4px solid var(--accent); }}
        .notes ul {{ margin: 8px 0 0 18px; padding: 0; }}
        .notes li {{ margin: 6px 0; line-height: 1.45; }}
        table {{ border-collapse: separate; border-spacing: 0; width: 100%; }}
        th, td {{ border-bottom: 1px solid var(--line); padding: 8px 10px; font-size: 13px; text-align: right; }}
        th:first-child, td:first-child {{ text-align: left; }}
        thead th {{
            background: #f1f5fb;
            color: #284563;
            font-weight: 600;
            border-top: 1px solid var(--line-strong);
            border-bottom: 1px solid var(--line-strong);
        }}
        tbody tr:nth-child(even) td {{ background: var(--stripe); }}
        .empty {{ text-align: center !important; color: var(--muted); }}
        .report-foot {{ margin-top: 14px; color: var(--muted); font-size: 12px; text-align: right; }}
  </style>
</head>
<body>
    <div class=\"report\">
        <header class=\"report-head\">
            <h1>BTF Statistics Report</h1>
            <div class=\"sub\">Generated: {_esc(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}</div>
        </header>

        <section class=\"kpi-grid\">
            <article class=\"kpi\"><div class=\"k\">Span{_esc(scope_title)}</div><div class=\"v\">{_esc(span_str)}</div></article>
            <article class=\"kpi\"><div class=\"k\">Tasks</div><div class=\"v\">{task_count:,}</div></article>
            <article class=\"kpi\"><div class=\"k\">Segments</div><div class=\"v\">{seg_count:,}</div></article>
            <article class=\"kpi\"><div class=\"k\">STI Events</div><div class=\"v\">{sti_count:,}</div></article>
            {sched_kpi}
        </section>

        <section class=\"report-card notes\">
        <h2>Statistics Notes</h2>
        <ul>
            {range_note}
            <li><strong>Execution Time Per Slice:</strong> Duration of each continuous task run between two context switches. Lower and tighter values indicate more predictable execution.</li>
            <li><strong>Inter-Arrival Time:</strong> Time between consecutive activations of the same task (slice start to next slice start). It reflects activation cadence and jitter.</li>
            <li><strong>Blocking Time:</strong> Off-CPU gap between the end of one slice and the start of the next for the same task. High values may indicate preemption, blocking on a resource, or long scheduling delays.</li>
      <li><strong>Preemption Chain Analysis:</strong> For each blocking gap of a victim task, identifies which task ran on the same core during that gap. High counts or long totals point to recurring preemption bottlenecks.</li>
      <li><strong>Interval Analysis:</strong> Paired interval_start / interval_stop spans per user-defined id (count, min/avg/max/p95 duration). See viewer docs for pairing limitations when the same id is used from multiple concurrent tasks.</li>
            <li><strong>Context switches:</strong> Count of segment boundaries on all cores whose start time falls inside the statistics scope.</li>
            <li><strong>Min (Minimum):</strong> The fastest execution time recorded. It represents the best-case scenario under zero system load.</li>
            <li><strong>Max (Maximum):</strong> The slowest execution time recorded. It identifies worst-case bottlenecks, spikes, or resource contention.</li>
            <li><strong>Average (Mean):</strong> Total execution time divided by the number of slices. It shows general performance but is heavily skewed by extreme outliers.</li>
            <li><strong>TrimMean(5%):</strong> Average after removing the fastest 5% and slowest 5% slices. It reflects typical performance while reducing outlier impact.</li>
            <li><strong>P50 (Median):</strong> The midpoint latency where half of slices are faster and half are slower. It captures typical-case behaviour.</li>
            <li><strong>P95 (95th Percentile):</strong> The threshold under which 95% of all slices execute. It is the best metric for user experience because it ignores rare anomalies while capturing real-world slowdowns.</li>
        </ul>
    </section>

    <section class=\"report-card\">
    <h2>Core Utilisation (excl. IDLE/TICK){_esc(scope_title)}</h2>
    <table>
      <thead><tr><th>Core</th><th>CPU %</th></tr></thead>
      <tbody>{core_body}</tbody>
    </table>
  </section>

    <section class=\"report-card\">
    <h2>Top Tasks by CPU (excl. IDLE/TICK){_esc(scope_title)}</h2>
    <table>
      <thead><tr><th>Task</th><th>CPU %</th></tr></thead>
      <tbody>{task_body}</tbody>
    </table>
  </section>
    {tick_health_html}
    {_render_exec_table(exec_rows)}
    <section class=\"report-card\">
    <h2>Core Migrations{_esc(scope_title)}</h2>
    <table>
      <thead><tr><th>Task</th><th>Migr</th><th>Cores</th><th>Primary</th><th>Ping</th><th>STI±</th><th>Gap after</th><th>Gap other</th></tr></thead>
      <tbody>{"".join(
        f"<tr><td>{_esc(r[1])}</td><td>{r[2]}</td><td>{r[3]}</td>"
        f"<td>{_esc(r[5])} ({r[6]:.0f}%)</td><td>{r[7]}</td><td>{r[8]}</td>"
        f"<td>{_esc(r[9])}</td><td>{_esc(r[10])}</td></tr>"
        for r in mig_rows) or '<tr><td colspan="8" class="empty">No data</td></tr>'}</tbody>
    </table>
  </section>
    {_render_stats_table(f'Blocking Time (off-CPU gap){scope_title}', block_rows)}
    {_render_stats_table(f'Inter-Arrival Time{scope_title}', inter_rows)}
    <section class=\"report-card\"><h2>Preemption Chain Analysis{_esc(scope_title)}</h2>
    <table><thead><tr><th>Victim</th><th>Preemptor</th><th>Count</th><th>Total</th><th>Avg</th><th>Max</th></tr></thead>
    <tbody>{"".join(
        f"<tr><td>{_esc(r[1])}</td><td>{_esc(r[2])}</td><td>{r[3]}</td><td>{_esc(r[4])}</td><td>{_esc(r[5])}</td><td>{_esc(r[6])}</td></tr>"
        for r in preempt_rows) or "<tr><td colspan=\"6\" class=\"empty\">No preemption events found</td></tr>"}</tbody></table></section>
    <section class=\"report-card\"><h2>Interval Analysis{_esc(scope_title)}</h2>
    <table><thead><tr><th>ID</th><th>Label</th><th>Count</th><th>Min</th><th>Avg</th><th>Max</th><th>p95</th></tr></thead>
    <tbody>{"".join(
        f"<tr><td>{_esc(r[0])}</td><td>{_esc(r[1])}</td><td>{r[2]}</td><td>{_esc(r[3])}</td><td>{_esc(r[4])}</td><td>{_esc(r[5])}</td><td>{_esc(r[6])}</td></tr>"
        for r in interval_rows) or "<tr><td colspan=\"7\" class=\"empty\">No interval data</td></tr>"}</tbody></table></section>
        <div class=\"report-foot\">Generated by BTF Viewer</div>
    </div>
</body>
</html>
"""

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(report)
        except OSError as exc:
            QMessageBox.critical(self, "Export Error", f"Could not export HTML:\n{exc}")
            return

        wnd = self.window()
        if isinstance(wnd, QMainWindow):
            wnd.statusBar().showMessage(f"Exported statistics: {path}", 4000)

    def _export_csv(self) -> None:
        trace = self._trace
        if trace is None:
            return

        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Statistics CSV",
            f"statistics-{stamp}.csv",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return

        rng = self._stats_range()
        lo = hi = None
        scope_suffix = ""
        if rng is not None:
            lo, hi, n_cur = rng
            total_ns = hi - lo
            span_str = _format_time(total_ns, trace.time_scale)
            scope_suffix = f" (cursor range C1–C{n_cur})"
        else:
            total_ns = trace.time_max - trace.time_min
            span_str = _format_time(total_ns, trace.time_scale)
        span_str = span_str.replace("µs", "us").replace("μs", "us")

        if lo is not None and hi is not None:
            sti_count = sum(
                1 for ev in trace.sti_events
                if not _is_tag_sti_channel(ev.target) and lo <= ev.time <= hi)
            task_count = sum(
                1 for _segs in trace.seg_map_by_merge_key.values()
                if any(_seg_overlaps_range(s, lo, hi) for s in _segs)
            )
            seg_count = sum(1 for s in trace.segments if _seg_overlaps_range(s, lo, hi))
        else:
            sti_count = sum(1 for ev in trace.sti_events if not _is_tag_sti_channel(ev.target))
            task_count = len(trace.tasks)
            seg_count = len(trace.segments)

        core_rows = self._core_util_rows(trace, lo, hi)
        task_rows = self._task_cpu_rows(trace, lo=lo, hi=hi)
        exec_rows = self._exec_slice_rows_export(trace, lo, hi)
        inter_rows = self._inter_arrival_rows_export(trace, lo, hi)
        block_rows = self._blocking_time_rows_export(trace, lo, hi)
        mig_rows = _migration_rows(trace, lo, hi)
        preempt_rows_csv, _ = _preemption_chain_rows(trace, lo, hi)
        interval_rows_csv = _interval_stats_rows(trace, lo, hi)
        ctx_count, core_gaps = _scheduling_stats(trace, lo, hi)
        tick = _tick_health_report(trace, lo, hi)

        def _us(v: object) -> str:
            return str(v).replace("µs", "us").replace("μs", "us")

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)

                writer.writerow(["Summary"])
                writer.writerow(["Metric", "Value"])
                writer.writerow([f"Span{scope_suffix}", _us(span_str)])
                if scope_suffix:
                    writer.writerow(["Cursor range", scope_suffix.strip(" ()")])
                writer.writerow(["Tasks", task_count])
                writer.writerow(["Segments", seg_count])
                writer.writerow(["STI Events", sti_count])
                writer.writerow([f"Context switches{scope_suffix}", ctx_count])
                if core_gaps:
                    gap_avg = int(round(sum(core_gaps) / len(core_gaps)))
                    writer.writerow([f"Core gap avg{scope_suffix}", _us(_format_time(gap_avg, trace.time_scale))])
                    writer.writerow([f"Core gap max{scope_suffix}", _us(_format_time(max(core_gaps), trace.time_scale))])

                writer.writerow([])
                writer.writerow([f"Core Utilisation (excl. IDLE/TICK){scope_suffix}"])
                writer.writerow(["Core", "CPU %"])
                if core_rows:
                    for core, pct in core_rows:
                        writer.writerow([core, f"{pct:.1f}%"])
                else:
                    writer.writerow(["No data", ""])

                writer.writerow([])
                writer.writerow([f"Top Tasks by CPU (excl. IDLE/TICK){scope_suffix}"])
                writer.writerow(["Task", "CPU %"])
                if task_rows:
                    for _, name, pct in task_rows:
                        writer.writerow([name, f"{pct:.1f}%"])
                else:
                    writer.writerow(["No data", ""])

                writer.writerow([])
                writer.writerow([f"Trace Health (TICK){scope_suffix}"])
                if tick["tick_count"]:
                    writer.writerow(["Status", tick["health"].upper()])
                    writer.writerow(["Ticks", tick["tick_count"]])
                    writer.writerow(["Avg period", _us(_format_time(tick["avg_period"], trace.time_scale))])
                    writer.writerow(["Max gap", _us(_format_time(tick["max_gap"], trace.time_scale))])
                    writer.writerow(["Missed ticks (est.)", tick["missed_estimate"]])
                    writer.writerow([])
                    writer.writerow(["Large TICK gaps"])
                    writer.writerow(["Start", "End", "Gap", "Missed"])
                    if tick["large_gaps"]:
                        for start, end, dur, missed in tick["large_gaps"]:
                            writer.writerow([
                                _us(_format_time(start, trace.time_scale)),
                                _us(_format_time(end, trace.time_scale)),
                                _us(_format_time(dur, trace.time_scale)),
                                missed,
                            ])
                    else:
                        writer.writerow(["No large gaps", "", "", ""])
                else:
                    writer.writerow(["No STI TICK events", ""])

                writer.writerow([])
                writer.writerow([f"Execution Time Per Slice{scope_suffix}"])
                writer.writerow(["Task", "Runs", "CPU%", "Min", "Avg", "TrimMean(5%)", "Max", "p50", "p95"])
                if exec_rows:
                    for mk_r, name, runs, cpu, mn, avg, tmean, mx, p50, p95 in exec_rows:
                        writer.writerow([name, runs, f"{cpu:.1f}%", _us(mn), _us(avg), _us(tmean), _us(mx), _us(p50), _us(p95)])
                else:
                    writer.writerow(["No data", "", "", "", "", "", "", "", ""])

                writer.writerow([])
                writer.writerow([f"Core Migrations{scope_suffix}"])
                writer.writerow(["Task", "Migrations", "Core count", "Primary core",
                                 "Primary %", "Ping-pong", "STI near",
                                 "Avg gap after", "Avg gap other"])
                if mig_rows:
                    for _mk, name, n_mig, n_cores, _cs, primary, pct, ping, sti, ga, go in mig_rows:
                        writer.writerow([name, n_mig, n_cores, primary, f"{pct:.1f}",
                                         ping, sti, _us(ga), _us(go)])
                else:
                    writer.writerow(["No data", "", "", "", "", "", "", "", ""])

                writer.writerow([])
                writer.writerow([f"Blocking Time (off-CPU gap){scope_suffix}"])
                writer.writerow(["Task", "Gaps", "Min", "Avg", "TrimMean(5%)", "Max", "p50", "p95"])
                if block_rows:
                    for mk_r, name, runs, mn, avg, tmean, mx, p50, p95 in block_rows:
                        writer.writerow([name, runs, _us(mn), _us(avg), _us(tmean), _us(mx), _us(p50), _us(p95)])
                else:
                    writer.writerow(["No data", "", "", "", "", "", "", ""])

                writer.writerow([])
                writer.writerow([f"Inter-Arrival Time{scope_suffix}"])
                writer.writerow(["Task", "Runs", "Min", "Avg", "TrimMean(5%)", "Max", "p50", "p95"])
                if inter_rows:
                    for mk_r, name, runs, mn, avg, tmean, mx, p50, p95 in inter_rows:
                        writer.writerow([name, runs, _us(mn), _us(avg), _us(tmean), _us(mx), _us(p50), _us(p95)])
                else:
                    writer.writerow(["No data", "", "", "", "", "", "", ""])

                writer.writerow([])
                writer.writerow([f"Preemption Chain Analysis{scope_suffix}"])
                writer.writerow(["Victim", "Preemptor", "Count", "Total", "Avg", "Max"])
                if preempt_rows_csv:
                    for _mk, victim, preemptor, count, total, avg, mx in preempt_rows_csv:
                        writer.writerow([victim, preemptor, count, _us(total), _us(avg), _us(mx)])
                else:
                    writer.writerow(["No preemption events found", "", "", "", "", ""])

                writer.writerow([])
                writer.writerow([f"Interval Analysis{scope_suffix}"])
                writer.writerow(["ID", "Label", "Count", "Min", "Avg", "Max", "p95"])
                if interval_rows_csv:
                    for iid, label, count, mn, avg, mx, p95 in interval_rows_csv:
                        writer.writerow([iid, label, count, _us(mn), _us(avg), _us(mx), _us(p95)])
                else:
                    writer.writerow(["No interval data", "", "", "", "", "", ""])

            wnd = self.window()
            if isinstance(wnd, QMainWindow):
                wnd.statusBar().showMessage(f"Exported statistics: {path}", 4000)
        except OSError as exc:
            QMessageBox.critical(self, "Export Error", f"Could not export CSV:\n{exc}")

    def rebuild(self, trace: "BtfTrace") -> None:
        self._trace = trace
        self._btn_export_csv.setEnabled(True)
        self._btn_export_html.setEnabled(True)
        wnd = self.window()
        self._btn_compare_mig.setEnabled(
            isinstance(wnd, QMainWindow) and len(getattr(wnd, "_tabs", ())) >= 2)
        self._clear()
        self._update_scope_header()

        rng = self._stats_range()
        lo = hi = None
        scope = self._scope_suffix()
        if rng is not None:
            lo, hi, _n_cur = rng
            total_ns = hi - lo
            span_str = _format_time(total_ns, trace.time_scale)
            sti_count = sum(
                1 for ev in trace.sti_events
                if not _is_tag_sti_channel(ev.target) and lo <= ev.time <= hi)
            task_count = sum(
                1 for _segs in trace.seg_map_by_merge_key.values()
                if any(_seg_overlaps_range(s, lo, hi) for s in _segs)
            )
            seg_count = sum(1 for s in trace.segments if _seg_overlaps_range(s, lo, hi))
        else:
            total_ns = trace.time_max - trace.time_min
            span_str = _format_time(total_ns, trace.time_scale)
            sti_count = sum(1 for ev in trace.sti_events if not _is_tag_sti_channel(ev.target))
            task_count = len(trace.tasks)
            seg_count = len(trace.segments)

        _fs = f"{self._ui_font_size}pt"

        # -- Summary row ---------------------------------------------------
        self._ilay.addWidget(self._lbl(
            f"Span: {span_str}{scope}  |  Tasks: {task_count}  |  "
            f"Segments: {seg_count:,}  |  STI events: {sti_count:,}",
            color="#888888",
            ui_fs=_fs,
        ))

        ctx_count, core_gaps = _scheduling_stats(trace, lo, hi)
        if ctx_count > 0:
            sched_parts = [f"Context switches: {ctx_count:,}{scope}"]
            if core_gaps:
                gap_avg = int(round(sum(core_gaps) / len(core_gaps)))
                sched_parts.append(
                    f"Core gap avg: {_format_time(gap_avg, trace.time_scale)}")
                sched_parts.append(
                    f"max: {_format_time(max(core_gaps), trace.time_scale)}")
            self._ilay.addWidget(self._lbl(
                "  |  ".join(sched_parts),
                color="#888888",
                ui_fs=_fs,
            ))

        # -- Core utilisation (excl. IDLE) ---------------------------------
        if trace.core_names:
            def _populate_cores(blay: QVBoxLayout) -> None:
                inner = QWidget()
                ilay = QVBoxLayout(inner)
                ilay.setContentsMargins(0, 0, 0, 0)
                ilay.setSpacing(STATS_UTIL_ROW_GAP)
                core_rows = self._core_util_rows(trace, lo, hi)
                for core, pct in core_rows:
                    self._add_utilisation_row(
                        ilay, _fs, f"  {core}:", pct,
                        chunk_color="#5FCF6F", pct_color="#77BB77",
                        label_min_width=72,
                    )
                self._wrap_util_rows_scroll(blay, inner, len(core_rows))

            self._add_collapsible_section(
                "cores",
                f"Core Utilisation (excl. IDLE/TICK){scope}",
                _fs,
                _populate_cores,
            )

        # -- Top tasks by CPU time (excl. IDLE, top 10) -------------------
        def _populate_tasks(blay: QVBoxLayout) -> None:
            task_rows = self._task_cpu_rows(trace, lo=lo, hi=hi)
            if not task_rows:
                blay.addWidget(self._lbl("No user tasks found", color="#888888", ui_fs=_fs))
                return
            inner = QWidget()
            ilay = QVBoxLayout(inner)
            ilay.setContentsMargins(0, 0, 0, 0)
            ilay.setSpacing(STATS_UTIL_ROW_GAP)
            for mk, disp, pct in task_rows:
                self._add_utilisation_row(
                    ilay, _fs, f"  {disp}", pct,
                    chunk_color="#5B9BD5", pct_color="#6AAADD",
                    label_min_width=100,
                    on_click=lambda key=mk: self.task_clicked.emit(key),
                    click_tip=f"Click to highlight \u2018{disp}\u2019 in the timeline",
                )
            self._wrap_util_rows_scroll(blay, inner, len(task_rows))

        self._add_collapsible_section(
            "tasks",
            f"Top Tasks by CPU (excl. IDLE/TICK){scope}",
            _fs,
            _populate_tasks,
        )

        # -- Trace health (TICK) ------------------------------------------
        _tick = _tick_health_report(trace, lo, hi)

        def _populate_health(blay: QVBoxLayout) -> None:
            if _tick["tick_count"] == 0:
                blay.addWidget(self._lbl("No STI TICK events", color="#888888", ui_fs=_fs))
                return
            colors = {"good": "#5FCF6F", "warning": "#E8C84A", "critical": "#E85D5D"}
            blay.addWidget(self._lbl(
                f"{_tick['health'].upper()}  ·  {_tick['tick_count']:,} ticks  ·  "
                f"avg {_format_time(_tick['avg_period'], trace.time_scale)}  ·  "
                f"max gap {_format_time(_tick['max_gap'], trace.time_scale)}",
                color=colors.get(_tick["health"], "#888888"),
                ui_fs=_fs,
            ))
            if _tick["large_gaps"]:
                blay.addWidget(self._lbl(
                    f"{len(_tick['large_gaps'])} large gap(s) · "
                    f"~{_tick['missed_estimate']} missed ticks",
                    color="#888888", ui_fs=_fs))
                table = QTableWidget(min(8, len(_tick["large_gaps"])), 4)
                table.setHorizontalHeaderLabels(["Start", "End", "Gap", "Missed"])
                table.setEditTriggers(QAbstractItemView.NoEditTriggers)
                table.verticalHeader().setVisible(False)
                table.setShowGrid(False)
                table.setFrameShape(QFrame.NoFrame)
                table.horizontalHeader().setSectionsClickable(True)
                table.horizontalHeader().setSortIndicatorShown(True)
                _item_bg = self._apply_stats_table_theme(table, _fs)
                for r, (start, end, dur, missed) in enumerate(_tick["large_gaps"][:8]):
                    for c, val in enumerate((
                        _format_time(start, trace.time_scale),
                        _format_time(end, trace.time_scale),
                        _format_time(dur, trace.time_scale),
                        str(missed),
                    )):
                        keys = (
                            start, end, dur, missed,
                        )
                        item = _StatsSortItem(val, keys[c])
                        item.setBackground(_item_bg)
                        table.setItem(r, c, item)
                table.setSortingEnabled(True)
                table.setFixedHeight(
                    STATS_TABLE_HEADER_H + min(8, len(_tick["large_gaps"])) * STATS_TABLE_ROW_H + 2)
                blay.addWidget(table)

        self._add_collapsible_section(
            "health",
            f"Trace Health (TICK){scope}",
            _fs,
            _populate_health,
        )

        # -- Core migrations ----------------------------------------------
        _mig_rows = _migration_rows(trace, lo, hi)
        empty_mig = ("No multi-core tasks in cursor range" if scope
                     else "No tasks ran on more than one core")

        def _on_mig_row(mk: str) -> None:
            migs = trace.migrations_by_mk.get(mk, [])
            if lo is not None and hi is not None:
                scoped = [m for m in migs if lo <= m.ns <= hi]
            else:
                scoped = migs
            if scoped:
                self.segment_jump.emit(scoped[0].ns)
            self.task_clicked.emit(mk)

        def _populate_mig(blay: QVBoxLayout) -> None:
            blay.addWidget(self._build_stats_table(
                _mig_rows, _fs, empty_mig,
                section_id="migrations", migrations=True,
                on_row_click=_on_mig_row))

        self._add_collapsible_section(
            "migrations",
            f"Core Migrations{scope}",
            _fs,
            _populate_mig,
        )

        # -- Execution time per slice -------------------------------------
        _exec_rows = self._exec_slice_rows(trace, lo, hi)
        empty_exec = ("No slices fully inside cursor range" if scope
                      else "No user-task slices found")

        def _populate_exec(blay: QVBoxLayout) -> None:
            blay.addWidget(self._build_stats_table(
                _exec_rows,
                _fs,
                empty_exec,
                include_cpu=True,
                section_id="exec",
                on_row_click=lambda mk: self._open_plot(trace, mk, "exec"),
                on_min_click=lambda mk: self._on_bcet_click(trace, mk, lo, hi),
                on_max_click=lambda mk: self._on_wcet_click(trace, mk, lo, hi),
            ))

        self._add_collapsible_section(
            "exec",
            f"Execution Time Per Slice{scope}",
            _fs,
            _populate_exec,
        )

        # -- Blocking time (off-CPU between activations) --------------------
        _block_rows = self._blocking_time_rows(trace, lo, hi)
        empty_block = ("No off-CPU gaps fully inside cursor range" if scope
                       else "Need at least 2 activations per task")

        def _populate_block(blay: QVBoxLayout) -> None:
            blay.addWidget(self._build_stats_table(
                _block_rows,
                _fs,
                empty_block,
                count_header="Gaps",
                section_id="block",
                on_row_click=lambda mk: self._open_plot(trace, mk, "block"),
                on_min_click=lambda mk: self._on_blocking_extreme_click(
                    trace, mk, lo, hi, False),
                on_max_click=lambda mk: self._on_blocking_extreme_click(
                    trace, mk, lo, hi, True),
            ))

        self._add_collapsible_section(
            "block",
            f"Blocking Time (off-CPU gap){scope}",
            _fs,
            _populate_block,
        )

        # -- Inter-arrival time -------------------------------------------
        _inter_rows = self._inter_arrival_rows(trace, lo, hi)

        def _populate_inter(blay: QVBoxLayout) -> None:
            blay.addWidget(self._build_stats_table(
                _inter_rows,
                _fs,
                "Need at least 2 activations per task",
                section_id="inter",
                on_row_click=lambda mk: self._open_plot(trace, mk, "inter"),
                on_min_click=lambda mk: self._on_inter_extreme_click(
                    trace, mk, lo, hi, False),
                on_max_click=lambda mk: self._on_inter_extreme_click(
                    trace, mk, lo, hi, True),
            ))

        self._add_collapsible_section(
            "inter",
            f"Inter-Arrival Time{scope}",
            _fs,
            _populate_inter,
        )

        # -- Preemption Chain Analysis ----------------------------------------
        _preempt_rows, _preempt_truncated = _preemption_chain_rows(trace, lo, hi)
        empty_preempt = ("No preemption events in cursor range" if scope
                         else "No preemption events found (single-task or idle-only trace)")

        def _populate_preempt(blay: QVBoxLayout) -> None:
            if _preempt_truncated:
                blay.addWidget(self._lbl(
                    f"Showing top {PREEMPTION_CHAIN_MAX_ROWS:,} pairs by total preemption time.",
                    color="#888888", ui_fs=_fs))
            blay.addWidget(self._build_preemption_table(
                _preempt_rows, _fs, empty_preempt,
                on_row_click=lambda mk, preemptor: self._open_plot(
                    trace, mk, "preempt", preemptor=preemptor),
            ))

        self._add_collapsible_section(
            "preemption",
            f"Preemption Chain Analysis{scope}",
            _fs,
            _populate_preempt,
        )

        # -- Interval Analysis ------------------------------------------------
        _interval_rows = _interval_stats_rows(trace, lo, hi)
        empty_interval = ("No interval data in cursor range" if scope
                          else "No paired interval_start / interval_stop events in trace")

        def _populate_intervals(blay: QVBoxLayout) -> None:
            blay.addWidget(self._build_stats_table(
                [(r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in _interval_rows],
                _fs,
                empty_interval,
                count_header="Count",
                section_id="intervals",
                on_row_click=lambda iid: self._open_interval_plot(trace, iid),
            ))

        self._add_collapsible_section(
            "intervals",
            f"Interval Analysis{scope}",
            _fs,
            _populate_intervals,
        )

        self._ilay.addStretch()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _JumpToTimeDialog(QDialog):
    """Modal dialog that lets the user type a time and jump the timeline to it.

    Accepted input formats (case-insensitive):
        - Raw integer nanoseconds: "123456789"
        - With unit:  "10 ns", "2.5 us",  "1.5 ms", "0.001 s",
                       "10us", "1.5ms"  (no space between value and unit)
    """

    def __init__(self, trace, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Jump to Time")
        self.setModal(True)
        self.setMinimumWidth(320)
        self._ns: Optional[int] = None

        lbl = QLabel("Enter a time value (e.g. 1.5&nbsp;µs, 200&nbsp;ns, 0.001&nbsp;ms):")
        lbl.setWordWrap(True)

        self._edit = QLineEdit()
        self._edit.setPlaceholderText("e.g. 1.5 us  or  1500 ns")
        self._err_lbl = QLabel("")
        self._err_lbl.setStyleSheet("color: #FF6666;")

        if trace is not None:
            lo = _format_time(trace.time_min, trace.time_scale)
            hi = _format_time(trace.time_max, trace.time_scale)
            range_lbl = QLabel(f"Trace range: {lo} → {hi}")
            range_lbl.setStyleSheet("color: #888888; font-size: 9pt;")
        else:
            range_lbl = None

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(lbl)
        lay.addWidget(self._edit)
        lay.addWidget(self._err_lbl)
        if range_lbl is not None:
            lay.addWidget(range_lbl)
        lay.addWidget(buttons)

        self._edit.returnPressed.connect(self._accept)

    def _accept(self) -> None:
        text = self._edit.text().strip()
        ns = _parse_time_input(text)
        if ns is None:
            self._err_lbl.setText("Unrecognised format. Try: 1.5 us, 200 ns, 1500000")
            return
        self._ns = ns
        self.accept()

    def result_ns(self) -> Optional[int]:
        return self._ns

def _parse_time_input(text: str) -> Optional[int]:
    """Parse a human-readable time string into nanoseconds.

    Accepts: "1234", "1.5 us", "200ns", "2.5 ms", "0.001 s",
             case-insensitive, optional space between value and unit.
    Returns None on parse failure.
    """
    import re as _re
    text = text.strip()
    m = _re.fullmatch(r"([+-]?\d+(?:\.\d*)?(?:e[+-]?\d+)?)\s*(ns?|us?|\u00b5s?|ms?|s)?",
                      text, _re.IGNORECASE)
    if not m:
        return None
    val_str, unit = m.group(1), (m.group(2) or "ns").lower()
    try:
        val = float(val_str)
    except ValueError:
        return None
    unit = unit.rstrip("s") if unit.endswith("s") and len(unit) > 1 else unit
    multipliers = {"n": 1, "u": 1_000, "us": 1_000, "m": 1_000_000, "s": 1_000_000_000}
    prefix = unit[0] if unit else "n"
    mult = multipliers.get(prefix, 1)
    return int(round(val * mult))

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
    [files]    last_file, last_dir, open_tabs_json, active_tab_index
    [tab_view] per-trace zoom/cursor layout (key = trace_<sha256[:16]>)
    """

    RC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btf_viewer.rc")

    _DEFAULTS: Dict[str, Dict[str, str]] = {
        "window": {
            "width":     str(DEFAULT_WINDOW_WIDTH),
            "height":    str(DEFAULT_WINDOW_HEIGHT),
            "x":         str(DEFAULT_WINDOW_X),
            "y":         str(DEFAULT_WINDOW_Y),
            "maximized": "false",
            "dock_state": DEFAULT_DOCK_STATE_B64,
            "dock_metrics": "",
            "dock_layout_version": DEFAULT_DOCK_LAYOUT_VERSION,
        },
        "view": {
            "font_size":         str(FONT_SIZE),
            "theme":             "dark",
            "horizontal":        "true",
            "view_mode":         "task",
            "show_sti":          "true",
            "show_grid":         "true",
            "show_marks":        "true",
            "show_find":         "false",
            # Vertical-mode label rendering workaround: on Windows, GDI cannot
            # antialias rotated text, so the pixmap path is the better default.
            "vert_label_pixmap": str(_VERTICAL_LABEL_USE_PIXMAP_DEFAULT).lower(),
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
            "open_tabs_json": "[]",
            "active_tab_index": "0",
        },
    }

    def __init__(self) -> None:
        self._cfg = configparser.ConfigParser()
        self._dirty = False
        self._last_error: str = ""
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
                fh.write("# btf_viewer.rc - RTOS BTF Viewer settings\n")
                fh.write("# This file is managed automatically; you may edit it by hand.\n\n")
                self._cfg.write(fh)
            self._dirty = False
            self._last_error = ""
        except OSError:
            self._last_error = "Unable to write settings file"

    def flush(self) -> None:
        """Flush pending deferred writes, if any."""
        if self._dirty:
            self._flush()

    def last_error(self) -> str:
        """Return the most recent settings write error, or an empty string."""
        return self._last_error

    def clear_error(self) -> None:
        """Clear stored settings write error after the UI has reported it."""
        self._last_error = ""

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
    def set(self, section: str, key: str, value, *, flush: bool = True) -> None:
        """Set *key* in *section* and optionally flush to disk."""
        if not self._cfg.has_section(section):
            self._cfg.add_section(section)
        self._cfg.set(section, key, str(value))
        if flush:
            self._flush()
        else:
            self._dirty = True

    def set_many(self, section: str, pairs: Dict[str, str], *, flush: bool = True) -> None:
        """Set multiple keys at once with a single disk flush."""
        if not self._cfg.has_section(section):
            self._cfg.add_section(section)
        for key, value in pairs.items():
            self._cfg.set(section, key, str(value))
        if flush:
            self._flush()
        else:
            self._dirty = True

    def prune_section(self, section: str, keep: int) -> None:
        """Remove the oldest entries from *section*, keeping at most *keep* entries."""
        if not self._cfg.has_section(section):
            return
        keys = self._cfg.options(section)
        if len(keys) > keep:
            for k in keys[:-keep]:
                self._cfg.remove_option(section, k)
            self._flush()

    def align_section_keys(self, section: str, allowed_keys: set[str]) -> None:
        """Drop keys from *section* that are not in *allowed_keys*."""
        if not self._cfg.has_section(section):
            return
        removed = False
        for k in list(self._cfg.options(section)):
            if k not in allowed_keys:
                self._cfg.remove_option(section, k)
                removed = True
        if removed:
            self._dirty = True

# ---------------------------------------------------------------------------
# About Dialog
# ---------------------------------------------------------------------------

class _AboutDialog(QDialog):
    """Modern About dialog - app icon header, theme-aware, quick-reference table."""

    def __init__(self, parent, *, is_dark: bool):
        super().__init__(parent, Qt.Dialog)
        self.setWindowTitle("About RTOS BTF Viewer")
        self.setModal(True)
        self.setMinimumWidth(380)

        # Theme palette
        if is_dark:
            hdr_bg  = "#1E1E1E"; bg     = "#252526"; sep_c  = "#3A3A3A"
            title_c = "#FFFFFF";  sub_c  = "#9E9E9E"; sect_c = "#5B9BD5"
            key_c   = "#7EC8E3"; body_c = "#D4D4D4"
            btn_bg  = "#0E4D80"; btn_hov = "#1565C0"; btn_txt = "#FFFFFF"
            blk_bg  = "#2B2B2C"; blk_bd = "#3A3A3A"
        else:
            hdr_bg  = "#F0F0F0"; bg     = "#FAFAFA"; sep_c  = "#CCCCCC"
            title_c = "#1E1E1E"; sub_c  = "#666666"; sect_c = "#005A9E"
            key_c   = "#005A9E"; body_c = "#333333"
            btn_bg  = "#005A9E"; btn_hov = "#1472B5"; btn_txt = "#FFFFFF"
            blk_bg  = "#FFFFFF"; blk_bd = "#D5D5D5"

        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # -- Header: icon + title + tagline -------------------------------
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

        name_lbl = QLabel("RTOS BTF Viewer")
        name_lbl.setAlignment(Qt.AlignHCenter)
        name_lbl.setObjectName("about_title")
        hv.addWidget(name_lbl)

        sub_lbl = QLabel(f"RTOS context-switch timeline visualiser  *  v{_APP_VERSION}")
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

        # -- Info body -----------------------------------------------------
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
            g.setContentsMargins(0, 0, 0, 0)
            g.setHorizontalSpacing(16)
            g.setVerticalSpacing(3)
            g.setColumnStretch(1, 1)
            for r, (k, v) in enumerate(rows):
                kl = QLabel(k); kl.setObjectName("about_key")
                vl = QLabel(v); vl.setObjectName("about_body")
                vl.setWordWrap(True)
                g.addWidget(kl, r, 0, Qt.AlignTop)
                g.addWidget(vl, r, 1)
            return w

        def _block(title: str, rows) -> QWidget:
            box = QFrame()
            box.setObjectName("about_block")
            bv = QVBoxLayout(box)
            bv.setContentsMargins(12, 10, 12, 10)
            bv.setSpacing(8)
            bv.addWidget(_sect(title))
            bv.addWidget(_kv_table(rows))
            return box

        iv.addWidget(_block("View Modes", [
            ("Task View", "one row per task"),
            ("Core View", "expandable rows per CPU core"),
        ]))
        iv.addWidget(_block("Controls", [
            ("Left-click",       "place / drag cursor"),
            ("Ctrl+Wheel",       "zoom in / out  \u00b7  Scroll \u2014 pan"),
            ("Ctrl+0",           "fit to window"),
            ("Ctrl+R",           "zoom to cursor range"),
            ("Tab / Shift+Tab",  "cycle to next / previous task segment"),
        ]))
        iv.addWidget(_block("Application", [
            ("Product",   "RTOS BTF Viewer"),
            ("Purpose",   "Interactive viewer for Best Trace Format (.btf) RTOS scheduling traces"),
            ("Runtime",   f"Python {sys.version_info.major}.{sys.version_info.minor}  *  PyQt5 desktop application"),
        ]))
        iv.addWidget(_block("License", [
            ("License",   "MIT License"),
        ]))
        root.addWidget(info_w)

        root.addWidget(_hsep())

        # -- Footer --------------------------------------------------------
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

        # -- Scoped stylesheet ---------------------------------------------
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
            QFrame#about_block          {{ background:{blk_bg}; border:1px solid {blk_bd};
                                           border-radius:8px; }}
            QFrame#about_sep            {{ border:none; background:{sep_c};
                                           max-height:1px; }}
            QPushButton#about_btn       {{ background:{btn_bg}; color:{btn_txt};
                                           border:none; border-radius:5px;
                                           font-size:10pt; font-weight:600;
                                           padding:0px 22px; }}
            QPushButton#about_btn:hover {{ background:{btn_hov}; }}
        """)

        self.adjustSize()

        # Match the web app's visual proportion: slightly wider, less tall.
        # Target ratio is width / height ~= 1.28.
        _target_ratio = 1.28
        _w = max(520, min(640, self.sizeHint().width()))
        _h_need = self.sizeHint().height()
        _h_target = int(round(_w / _target_ratio))
        if _h_target < _h_need:
            _h = _h_need
            _w = int(round(_h * _target_ratio))
        else:
            _h = _h_target
        self.setFixedSize(_w, _h)

# ---------------------------------------------------------------------------
# Settings Dialog
# ---------------------------------------------------------------------------

class _SettingsDialog(QDialog):
    """Modal settings dialog - sidebar navigation: Appearance | Display | Layout."""

    _INPUT_W = 110   # fixed pixel width for all spin / combo inputs

    # Emitted whenever any control value changes so _open_settings can
    # apply a live preview while the dialog is still open.
    live_preview = pyqtSignal()

    def _schedule_live_preview(self, *_args) -> None:
        """Coalesce rapid control changes and defer preview to next UI turn."""
        self._preview_timer.start()

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
                 vert_label_pixmap: bool,
                 zoom_unit: str,
                 label_width: int, row_height: int, row_gap: int,
                 sti_row_h: int, sti_waveform_h: int, sti_line_style: str,
                 timescale_per_px_default: float,
                 is_dark: bool,
                 cpu_load_row_h: int = CPU_LOAD_ROW_H,
                 cpu_load: bool = True,
                 colorblind_safe: bool = False):
        super().__init__(parent, Qt.Dialog)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumSize(580, 360)

        # Defer heavy live-preview work until the current widget event
        # (e.g. combo popup close) has finished to keep selection responsive.
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(0)
        self._preview_timer.timeout.connect(self.live_preview.emit)

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
        self._sidebar.setFont(_dlg_font)   # explicit - CSS font-size is ignored by macOS native item delegate
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

        self._colorblind_cb = QCheckBox("Colorblind-safe colors (Okabe-Ito palette)")
        self._colorblind_cb.setChecked(colorblind_safe)
        self._colorblind_cb.setToolTip(
            "Replace the task colour palette with the Okabe-Ito 8-colour set,\n"
            "designed to be distinguishable for deuteranopia and protanopia.")
        f1.addRow("", self._colorblind_cb)

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
        self._cpu_load_cb = QCheckBox("CPU load graph")
        self._cpu_load_cb.setChecked(cpu_load)
        v2.addWidget(self._indented(self._cpu_load_cb))

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
        self._vert_label_pixmap_cb = QCheckBox("Vertical labels: use pixmap rendering (Windows fix)")
        self._vert_label_pixmap_cb.setChecked(vert_label_pixmap)
        self._vert_label_pixmap_cb.setToolTip(
            "Render vertical-mode task labels onto a QPixmap first, then\n"
            "rotate the image. Avoids the Windows GDI limitation that\n"
            "prevents antialiasing of rotated text. Enabled by default on\n"
            "Windows; other platforms use the native text path.")
        v2.addWidget(self._indented(self._sti_cb))
        v2.addWidget(self._indented(self._grid_cb))
        v2.addWidget(self._indented(self._hover_hl_cb))
        v2.addWidget(self._indented(self._vert_label_pixmap_cb))
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
        f3.addRow("", self._section("STI rows"))

        self._sti_row_h_spin = QSpinBox()
        self._sti_row_h_spin.setRange(12, 60)
        self._sti_row_h_spin.setSuffix(" px")
        self._sti_row_h_spin.setValue(sti_row_h)
        self._sti_row_h_spin.setToolTip("Height of collapsed STI channel rows (12\u201360 px)")
        f3.addRow("STI collapsed height:", _inp(self._sti_row_h_spin))

        self._sti_waveform_h_spin = QSpinBox()
        self._sti_waveform_h_spin.setRange(40, 300)
        self._sti_waveform_h_spin.setSuffix(" px")
        self._sti_waveform_h_spin.setValue(sti_waveform_h)
        self._sti_waveform_h_spin.setToolTip("Height of expanded STI waveform rows (40\u2013300 px)")
        f3.addRow("STI expanded height:", _inp(self._sti_waveform_h_spin))

        self._sti_line_style_combo = QComboBox()
        self._sti_line_style_combo.addItem("Step (hold value)", "step")
        self._sti_line_style_combo.addItem("Linear (point to point)", "linear")
        _style_idx = 1 if sti_line_style == "linear" else 0
        self._sti_line_style_combo.setCurrentIndex(_style_idx)
        self._sti_line_style_combo.setToolTip(
            "How the waveform line is drawn between events:\n"
            "\u2022 Step: hold the previous value until the next event (staircase)\n"
            "\u2022 Linear: connect events with a straight diagonal line")
        f3.addRow("STI line style:", _inp(self._sti_line_style_combo))

        f3.addRow(self._hline())
        f3.addRow("", self._section("Zoom & cursors"))

        self._timescale_per_px_spin = QDoubleSpinBox()
        self._timescale_per_px_spin.setRange(0.5, 200.0)
        self._timescale_per_px_spin.setSingleStep(0.5)
        self._timescale_per_px_spin.setDecimals(1)
        _disp_zoom_unit = "µs" if zoom_unit == "us" else zoom_unit
        self._timescale_per_px_spin.setSuffix(f" {_disp_zoom_unit}/px")
        self._timescale_per_px_spin.setValue(timescale_per_px_default)
        self._timescale_per_px_spin.setToolTip(
            f"Maximum zoom-in level (0.5\u2013200 {_disp_zoom_unit}/px).\n"
            "Also sets the target level of the 1:1 zoom button.")
        f3.addRow("1:1 zoom level:", _inp(self._timescale_per_px_spin))

        self._cursor_spin = QSpinBox()
        self._cursor_spin.setRange(4, _MAX_CURSORS)
        self._cursor_spin.setValue(max_cursors)
        self._cursor_spin.setToolTip(f"Maximum number of simultaneous cursors (4\u2013{_MAX_CURSORS})")
        f3.addRow("Max cursors:", _inp(self._cursor_spin))

        f3.addRow(self._hline())
        f3.addRow("", self._section("CPU Load Graph"))

        self._cpu_row_h_spin = QSpinBox()
        self._cpu_row_h_spin.setRange(16, 120)
        self._cpu_row_h_spin.setSuffix(" px")
        self._cpu_row_h_spin.setValue(cpu_load_row_h)
        self._cpu_row_h_spin.setToolTip("Height of each CPU load row (16\u2013120 px) \u2014 independent of timeline row height")
        f3.addRow("Row height:", _inp(self._cpu_row_h_spin))

        self._content_stack.addWidget(p3)

        # -- Sidebar <-> stack sync ---------------------------------------------
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

        _btn_w, _btn_h = 88, 30   # minimum size for both buttons

        btn_reset = QPushButton("Reset to Defaults")
        btn_reset.setObjectName("btn_cancel")
        btn_reset.setMinimumWidth(_btn_w)
        btn_reset.setFixedHeight(_btn_h)
        btn_reset.setToolTip("Restore all settings on this page to their built-in defaults")
        btn_reset.clicked.connect(self._reset_to_defaults)
        footer.addWidget(btn_reset)

        footer.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("btn_cancel")
        btn_cancel.setMinimumWidth(_btn_w)
        btn_cancel.setFixedHeight(_btn_h)
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("OK")
        btn_ok.setObjectName("btn_ok")
        btn_ok.setMinimumWidth(_btn_w)
        btn_ok.setFixedHeight(_btn_h)
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)

        footer.addWidget(btn_cancel)
        footer.addSpacing(8)
        footer.addWidget(btn_ok)
        root.addWidget(footer_w)

        # -- Scoped stylesheet ------------------------------------------------
        self.setStyleSheet(self._dialog_ss(is_dark, _ui_fs))

        # -- Live-preview wiring -----------------------------------------------
        # Each signal sends a typed argument (int/float).  Route them through
        # a single-shot timer so expensive preview work runs after the current
        # UI event completes (keeps combo selection close responsive).
        for _sig in (
            self._theme_combo.currentIndexChanged,
            self._colorblind_cb.stateChanged,
            self._font_spin.valueChanged,
            self._ui_font_spin.valueChanged,
            self._cursor_spin.valueChanged,
            self._sti_cb.stateChanged,
            self._grid_cb.stateChanged,
            self._legend_cb.stateChanged,
            self._stats_cb.stateChanged,
            self._marks_cb.stateChanged,
            self._cpu_load_cb.stateChanged,
            self._hover_hl_cb.stateChanged,
            self._vert_label_pixmap_cb.stateChanged,
            self._label_width_spin.valueChanged,
            self._row_height_spin.valueChanged,
            self._row_gap_spin.valueChanged,
            self._sti_row_h_spin.valueChanged,
            self._sti_waveform_h_spin.valueChanged,
            self._sti_line_style_combo.currentIndexChanged,
            self._timescale_per_px_spin.valueChanged,
            self._cpu_row_h_spin.valueChanged,
        ):
            _sig.connect(self._schedule_live_preview)

        self.adjustSize()

    # -- Reset all controls to built-in defaults ---------------------------
    def _reset_to_defaults(self) -> None:
        """Restore every control to its module-level default value."""
        self._theme_combo.setCurrentIndex(0)           # Dark
        self._colorblind_cb.setChecked(False)
        self._font_spin.setValue(FONT_SIZE)
        self._ui_font_spin.setValue(UI_FONT_SIZE)
        self._sti_cb.setChecked(True)
        self._grid_cb.setChecked(True)
        self._legend_cb.setChecked(True)
        self._stats_cb.setChecked(True)
        self._marks_cb.setChecked(True)
        self._cpu_load_cb.setChecked(True)
        self._hover_hl_cb.setChecked(_HOVER_HIGHLIGHT_ENABLED)
        self._vert_label_pixmap_cb.setChecked(_VERTICAL_LABEL_USE_PIXMAP_DEFAULT)
        self._label_width_spin.setValue(LABEL_WIDTH)
        self._row_height_spin.setValue(ROW_HEIGHT)
        self._row_gap_spin.setValue(ROW_GAP)
        self._sti_row_h_spin.setValue(STI_ROW_H)
        self._sti_waveform_h_spin.setValue(STI_WAVEFORM_H)
        self._sti_line_style_combo.setCurrentIndex(1 if STI_LINE_STYLE == "linear" else 0)
        self._timescale_per_px_spin.setValue(_TIMESCALE_PER_PX_DEFAULT)
        self._cursor_spin.setValue(_DEFAULT_MAX_CURSORS)
        self._cpu_row_h_spin.setValue(CPU_LOAD_ROW_H)

    # -- result accessors (read after exec_() == Accepted) ------------------
    @property
    def colorblind_safe(self) -> bool:        return self._colorblind_cb.isChecked()
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
    def cpu_load(self) -> bool:           return self._cpu_load_cb.isChecked()
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
    def sti_row_h(self) -> int:           return self._sti_row_h_spin.value()
    @property
    def sti_waveform_h(self) -> int:      return self._sti_waveform_h_spin.value()
    @property
    def sti_line_style(self) -> str:      return self._sti_line_style_combo.currentData()
    @property
    def timescale_per_px_default(self) -> float: return self._timescale_per_px_spin.value()
    @property
    def cpu_load_row_h(self) -> int:      return self._cpu_row_h_spin.value()
    @property
    def is_dark(self) -> bool:            return self._theme_combo.currentIndex() == 0
    @property
    def show_marks(self) -> bool:         return self._marks_cb.isChecked()
    @property
    def show_hover_highlight(self) -> bool: return self._hover_hl_cb.isChecked()
    @property
    def vert_label_pixmap(self) -> bool:    return self._vert_label_pixmap_cb.isChecked()
# ---------------------------------------------------------------------------
# Snapshot Annotation Editor
# ---------------------------------------------------------------------------

def _point_to_seg_dist(px: float, py: float,
                       x1: float, y1: float,
                       x2: float, y2: float) -> float:
    """Shortest distance from point (px,py) to segment (x1,y1)-(x2,y2)."""
    dx, dy = x2 - x1, y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-6:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length_sq))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

_SNAP_ANGLES = [a * math.pi / 180 for a in (0, 45, 90, 135, 180, -135, -90, -45)]
_SNAP_THRESH = 2 * math.pi / 180

def _snap_line_end(x1: float, y1: float, x2: float, y2: float, force: bool = False):
    """Return (x2, y2) snapped to the nearest 45deg axis.

    force=True  (Shift held): always snap to nearest axis.
    force=False : snap only when within 2deg threshold.
    """
    dx, dy = x2 - x1, y2 - y1
    dist = math.hypot(dx, dy)
    if dist < 2:
        return x2, y2
    angle = math.atan2(dy, dx)   # range [-pi, pi]
    best      = None
    best_diff = math.inf if force else _SNAP_THRESH
    for snap in _SNAP_ANGLES:
        diff = angle - snap
        if diff >  math.pi: diff -= 2 * math.pi
        if diff < -math.pi: diff += 2 * math.pi
        abs_diff = abs(diff)
        if abs_diff < best_diff:
            best_diff = abs_diff
            best = snap
    if best is not None:
        return x1 + dist * math.cos(best), y1 + dist * math.sin(best)
    return x2, y2

def _constrain_box(x1: float, y1: float, x2: float, y2: float):
    dx = x2 - x1
    dy = y2 - y1
    size = min(abs(dx), abs(dy))
    return {
        'x': x1 + (-size if dx < 0 else 0),
        'y': y1 + (-size if dy < 0 else 0),
        'w': size,
        'h': size,
    }

class _AnnotationCanvas(QWidget):
    """Canvas widget that renders the background image and all annotation shapes."""

    def __init__(self, editor: 'SnapshotEditorDialog', disp_w: int, disp_h: int) -> None:
        super().__init__(editor)
        self._editor = editor
        self.setFixedSize(disp_w, disp_h)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)

    def paintEvent(self, event) -> None:  # noqa: N802
        ed = self._editor
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # Background image scaled to display size
        painter.drawPixmap(0, 0, ed._disp_w, ed._disp_h, ed._orig_pixmap)
        # Scale painter to image coordinates
        painter.scale(ed._scale, ed._scale)
        # Two-pass rendering: white outline, then colour
        visible = [
            s for i, s in enumerate(ed._shapes)
            if not ed._should_skip_text_shape_paint(i, s)
        ]
        ed._paint_shapes(painter, visible, QColor('#ffffff'), 2)
        if ed._drawing:
            ed._paint_shapes(painter, [ed._drawing], QColor('#ffffff'), 2)
        ed._paint_shapes(painter, visible)
        if ed._drawing:
            ed._paint_shapes(painter, [ed._drawing])
        if ed._selected_idx >= 0 and ed._selected_idx < len(ed._shapes) and ed._drawing is None:
            ed._paint_selection(painter, ed._shapes[ed._selected_idx])
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton:
            return
        ed = self._editor
        if ed._text_edit_active() and ed._tool != 'text':
            ed._commit_text_edit()
        x, y = ed._to_img(event.x(), event.y())
        if ed._tool == 'text':
            hit = ed._hit_test(x, y)
            if hit >= 0 and ed._shapes[hit]['type'] == 'text':
                ed._selected_idx = hit
                self.update()
                return
            ed._begin_text_edit(shape_idx=-1, img_x=x, img_y=y, angle=0.0,
                                initial='', color=ed._color, font_size=ed._font_size)
            return
        else:
            handle = ed._hit_control_point(x, y)
            if handle and ed._selected_idx >= 0:
                ed._drag_idx = ed._selected_idx
                ed._drag_mode = 'handle'
                ed._drag_handle = handle
                ed._drag_anchor = ed._get_handle_anchor(ed._shapes[ed._drag_idx], handle)
                self.setCursor(ed._cursor_for_handle(handle))
                return

            # Try to pick up an existing shape for dragging
            hit = ed._hit_test(x, y)
            if hit >= 0:
                if bool(event.modifiers() & Qt.ControlModifier):
                    new_idx = ed._duplicate_shape(hit)
                    ed._selected_idx = new_idx
                    ed._sync_dash_from_shape(new_idx)
                    ed._drag_idx = new_idx
                    ed._drag_prev = (x, y)
                    ed._drag_mode = 'move'
                    ed._drag_handle = ''
                    ed._drag_anchor = None
                    self.setCursor(Qt.SizeAllCursor)
                    self.update()
                    return
                ed._selected_idx = hit
                ed._sync_dash_from_shape(hit)
                ed._drag_idx = hit
                ed._drag_prev = (x, y)
                ed._drag_mode = 'move'
                ed._drag_handle = ''
                ed._drag_anchor = None
                self.setCursor(Qt.SizeAllCursor)
                self.update()
            else:
                ed._selected_idx = -1
                ed._drawing = {
                    'type': ed._tool,
                    'color': QColor(ed._color),
                    'width': ed._line_width,
                    'dashed': ed._dashed,
                    'x1': x, 'y1': y,
                    'x2': x, 'y2': y,
                    'x': x, 'y': y, 'w': 0.0, 'h': 0.0,
                }

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        ed = self._editor
        x, y = ed._to_img(event.x(), event.y())
        if ed._drag_mode == 'handle' and ed._drag_idx >= 0 and ed._drag_handle:
            force = bool(event.modifiers() & Qt.ShiftModifier)
            ed._resize_shape_by_handle(ed._drag_idx, ed._drag_handle, x, y, force)
            self.update()
        elif ed._drag_mode == 'move' and ed._drag_idx >= 0:
            dx = x - ed._drag_prev[0]
            dy = y - ed._drag_prev[1]
            ed._move_shape(ed._drag_idx, dx, dy)
            ed._drag_prev = (x, y)
            self.update()
        elif ed._drawing is not None:
            d = ed._drawing
            if d['type'] in SnapshotEditorDialog._LINE_TOOLS:
                force = bool(event.modifiers() & Qt.ShiftModifier)
                d['x2'], d['y2'] = _snap_line_end(d['x1'], d['y1'], x, y, force)
            else:
                d['x2'] = x;  d['y2'] = y
                x1 = d['x1']; y1 = d['y1']
                if bool(event.modifiers() & Qt.ShiftModifier):
                    box = _constrain_box(x1, y1, x, y)
                    d['x'] = box['x'];  d['y'] = box['y']
                    d['w'] = box['w'];  d['h'] = box['h']
                else:
                    d['x'] = min(x1, x); d['y'] = min(y1, y)
                    d['w'] = abs(x - x1); d['h'] = abs(y - y1)
            self.update()
        else:
            # Update cursor to hint movable shape or active control handle.
            handle = ed._hit_control_point(x, y)
            ed._hover_handle = handle or ''
            if handle:
                self.setCursor(ed._cursor_for_handle(handle))
                return
            hit = ed._hit_test(x, y)
            ed._hover_idx = hit
            self.setCursor(Qt.SizeAllCursor if hit >= 0 else Qt.CrossCursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton:
            return
        ed = self._editor
        if ed._drag_mode in ('move', 'handle') and ed._drag_idx >= 0:
            ed._drag_idx = -1
            ed._drag_mode = 'none'
            ed._drag_handle = ''
            ed._drag_anchor = None
            self.setCursor(Qt.SizeAllCursor if ed._selected_idx >= 0 else Qt.CrossCursor)
            self.update()
        elif ed._drawing is not None:
            x, y = ed._to_img(event.x(), event.y())
            d = ed._drawing
            if d['type'] in SnapshotEditorDialog._LINE_TOOLS:
                force = bool(event.modifiers() & Qt.ShiftModifier)
                d['x2'], d['y2'] = _snap_line_end(d['x1'], d['y1'], x, y, force)
            else:
                d['x2'] = x;  d['y2'] = y
                x1 = d['x1']; y1 = d['y1']
                if bool(event.modifiers() & Qt.ShiftModifier):
                    box = _constrain_box(x1, y1, x, y)
                    d['x'] = box['x'];  d['y'] = box['y']
                    d['w'] = box['w'];  d['h'] = box['h']
                else:
                    d['x'] = min(x1, x); d['y'] = min(y1, y)
                    d['w'] = abs(x - x1); d['h'] = abs(y - y1)
            # Discard zero-size shapes (accidental single click with no drag)
            span = max(abs(d['x2'] - d['x1']), abs(d['y2'] - d['y1']),
                       abs(d['w']), abs(d['h']))
            if span > 2:
                ed._shapes.append(d)
                ed._selected_idx = len(ed._shapes) - 1
            ed._drawing = None
            self.update()

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        # Guard against the spurious second context-menu event Qt fires after
        # QMenu.exec_() returns on Linux (button-press AND button-release both
        # generate a QContextMenuEvent).  The flag is held until the secondary
        # dialog is fully closed, so no residual event can sneak through.
        if getattr(self, '_ctx_busy', False):
            event.accept()
            return

        from PyQt5.QtWidgets import QColorDialog, QMenu
        ed = self._editor
        x, y = ed._to_img(event.x(), event.y())
        idx = ed._hit_test(x, y)
        if idx < 0:
            return

        ed._selected_idx = idx
        self.update()

        event.accept()
        self._ctx_busy = True

        shape = ed._shapes[idx]
        is_text = shape['type'] == 'text'

        menu = QMenu(self)
        act_delete    = menu.addAction("Delete")
        menu.addSeparator()
        act_color     = menu.addAction("Change Color...")
        act_size      = None if is_text else menu.addAction("Change Size...")
        act_edit_text = menu.addAction("Edit Text...") if is_text else menu.addAction("Edit Label...")
        act_font_size = menu.addAction("Change Font Size...") if is_text else None

        chosen = menu.exec_(event.globalPos())

        if chosen is None or chosen == act_delete:
            if chosen == act_delete:
                ed._shapes.pop(idx)
                if ed._selected_idx == idx:
                    ed._selected_idx = -1
                elif ed._selected_idx > idx:
                    ed._selected_idx -= 1
                self.update()
            # Release guard after one event-loop cycle so any residual
            # context-menu event already in the queue gets swallowed first.
            QTimer.singleShot(0, lambda: setattr(self, '_ctx_busy', False))
            return

        # For actions that open a secondary dialog: hold the guard inside the
        # dialog via try/finally - it is released only after the dialog closes.
        def _open_dialog():
            try:
                if chosen == act_color:
                    color = QColorDialog.getColor(shape['color'], self, "Pick Colour")
                    if color.isValid():
                        shape['color'] = color
                        self.update()
                elif act_size and chosen == act_size:
                    val, ok = QInputDialog.getInt(
                        self, "Change Size", "Stroke width (px):",
                        shape.get('width', 3), 1, 20)
                    if ok:
                        shape['width'] = val
                        self.update()
                elif act_edit_text and chosen == act_edit_text:
                    ed._begin_edit_shape_text(idx)
                    self.update()
                elif act_font_size and chosen == act_font_size:
                    val, ok = QInputDialog.getInt(
                        self, "Change Font Size", "Font size (pt):",
                        shape.get('font_size', 20), 8, 72)
                    if ok:
                        shape['font_size'] = val
                        self.update()
            finally:
                self._ctx_busy = False  # released only after dialog fully closes

        QTimer.singleShot(0, _open_dialog)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton:
            return
        ed = self._editor
        x, y = ed._to_img(event.x(), event.y())
        idx = ed._hit_test(x, y)
        if idx < 0:
            return
        ed._selected_idx = idx
        ed._drag_idx = -1
        ed._drag_mode = 'none'
        ed._drag_handle = ''
        ed._drag_anchor = None
        ed._begin_edit_shape_text(idx)
        self.update()

class SnapshotEditorDialog(QDialog):
    """Annotation editor dialog opened when the user captures a viewport snapshot.

    Supported tools: arrow, double-arrow, line, rectangle, circle, text.
    Use the Dash checkbox for dashed strokes on line-based shapes and boxes.
    All shapes are rendered with a white outline pass followed by a colour
    pass, mirroring the web-app behaviour.
    """

    _TOOLS = ('arrow', 'dblarrow', 'line', 'rect', 'circle', 'text')
    _LINE_TOOLS = ('arrow', 'dblarrow', 'line', 'dash')
    _TOOL_LABELS = {
        'arrow':    'Arrow',
        'dblarrow': 'Double Arrow',
        'line':     'Line',
        'rect':   'Rectangle  (Shift: square)',
        'circle': 'Circle / Ellipse  (Shift: circle)',
        'text':   'Add Text (click to place)',
    }
    # SVG icon data for each tool (mirrors the web app icons)
    _TOOL_ICONS = {
        'arrow':  b'<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M2 14L13 3M13 3H7M13 3V9"/></svg>',
        'dblarrow': b'<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h8M4 8l2.5-2.5M4 8l2.5 2.5M12 8l-2.5-2.5M12 8l-2.5 2.5"/></svg>',
        'line':  b'<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><line x1="2" y1="14" x2="14" y2="2"/></svg>',
        'rect':  b'<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="2" y="3" width="12" height="9" rx="1"/></svg>',
        'circle':b'<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6"><ellipse cx="8" cy="8" rx="6" ry="5"/></svg>',
        'text':  b'<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M3 4h10M8 4v9M5 13h6"/></svg>',
    }

    @staticmethod
    def _make_svg_icon(svg_bytes: bytes, color: str = '#b0b0cc', size: int = 16) -> 'QIcon':
        """Render SVG bytes (with `currentColor`) to a QIcon pair (normal + checked)."""
        from PyQt5.QtSvg import QSvgRenderer
        from PyQt5.QtGui import QIcon, QPixmap
        from PyQt5.QtCore import Qt

        def _render(stroke: str) -> QPixmap:
            data = svg_bytes.replace(b'currentColor', stroke.encode())
            renderer = QSvgRenderer(data)
            pm = QPixmap(size, size)
            pm.fill(Qt.transparent)
            from PyQt5.QtGui import QPainter
            p = QPainter(pm)
            try:
                renderer.render(p)
            finally:
                p.end()
            return pm

        icon = QIcon()
        icon.addPixmap(_render(color),   QIcon.Normal,  QIcon.Off)
        icon.addPixmap(_render('#e3f2fd'), QIcon.Normal, QIcon.On)
        return icon

    def __init__(self, pixmap: QPixmap, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        # Normalize DPR so draw/edit/export all use one pixel coordinate space.
        # QWidget.grab() can return a high-DPI pixmap (e.g. DPR=2 on macOS),
        # while annotation geometry is stored in raw pixel units.
        # Keeping DPR>1 here causes exported objects to be offset/scaled.
        self._orig_pixmap: QPixmap = QPixmap(pixmap)
        if abs(self._orig_pixmap.devicePixelRatioF() - 1.0) > 1e-6:
            self._orig_pixmap.setDevicePixelRatio(1.0)
        self._shapes: list = []
        self._drawing: Optional[dict] = None
        self._drag_idx: int = -1
        self._drag_prev: tuple = (0.0, 0.0)
        self._drag_mode: str = 'none'      # none | move | handle
        self._drag_handle: str = ''
        self._drag_anchor: Optional[tuple] = None
        self._selected_idx: int = -1
        self._hover_idx: int = -1
        self._hover_handle: str = ''
        self._tool: str = 'arrow'
        self._color: QColor = QColor('#ff4444')
        self._line_width: int = 3
        self._font_size: int = 20
        self._dashed: bool = False
        self._text_edit_shape_idx: int = -1
        self._text_edit_img_x: float = 0.0
        self._text_edit_img_y: float = 0.0

        # Compute display scale so the canvas fits the available screen area
        screen = QApplication.desktop().availableGeometry(self)
        max_w = screen.width() - 120
        max_h = screen.height() - 220
        iw, ih = pixmap.width(), pixmap.height()
        self._scale: float = max(0.01, min(1.0, max_w / max(iw, 1), max_h / max(ih, 1)))
        self._disp_w: int = max(1, int(iw * self._scale))
        self._disp_h: int = max(1, int(ih * self._scale))

        self._build_ui()
        self.setWindowTitle("Snapshot Editor")
        self.setModal(True)
        QShortcut(QKeySequence("Ctrl+Z"), self, self._undo)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        main = QVBoxLayout(self)
        main.setContentsMargins(6, 6, 6, 6)
        main.setSpacing(4)

        # ---- Tool bar ----
        tb = QHBoxLayout()
        tb.setSpacing(2)
        self._tool_btns: dict = {}
        _tool_btn_ss = (
            "QPushButton {"
            "  border: 1px solid #888; border-radius: 3px; padding: 2px 4px;"
            "}"
            "QPushButton:checked {"
            "  background-color: #1976D2; color: #ffffff;"
            "  border: 1px solid #0D47A1;"
            "}"
            "QPushButton:hover:!checked { background-color: #3a3a3a; }"
        )
        _ICON_H = 28          # uniform height for every toolbar widget
        for tid in self._TOOLS:
            btn = QPushButton()
            btn.setIcon(self._make_svg_icon(self._TOOL_ICONS[tid]))
            btn.setIconSize(QSize(16, 16))
            btn.setCheckable(True)
            btn.setChecked(tid == self._tool)
            btn.setFixedSize(_ICON_H, _ICON_H)
            btn.setToolTip(self._TOOL_LABELS[tid])
            btn.setStyleSheet(_tool_btn_ss)
            btn.clicked.connect(lambda _checked, t=tid: self._select_tool(t))
            tb.addWidget(btn)
            self._tool_btns[tid] = btn

        tb.addSpacing(8)
        tb.addWidget(QLabel("Color:"))
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(_ICON_H, _ICON_H)
        self._color_btn.setToolTip("Pick colour")
        self._color_btn.clicked.connect(self._pick_color)
        self._refresh_color_btn()
        tb.addWidget(self._color_btn)

        tb.addSpacing(8)
        tb.addWidget(QLabel("Size:"))
        self._width_spin = QSpinBox()
        self._width_spin.setRange(1, 20)
        self._width_spin.setValue(self._line_width)
        self._width_spin.setSuffix(" px")
        self._width_spin.setFixedHeight(_ICON_H)
        self._width_spin.setToolTip("Stroke width")
        self._width_spin.valueChanged.connect(lambda v: setattr(self, '_line_width', v))
        tb.addWidget(self._width_spin)

        self._dash_cb = QCheckBox("Dash")
        self._dash_cb.setChecked(self._dashed)
        self._dash_cb.setToolTip("Dashed stroke for lines, arrows, rectangles, and circles")
        self._dash_cb.setFixedHeight(_ICON_H)
        self._dash_cb.toggled.connect(self._on_dash_toggled)
        tb.addWidget(self._dash_cb)

        tb.addSpacing(8)
        tb.addWidget(QLabel("Font:"))
        self._font_spin = QSpinBox()
        self._font_spin.setRange(8, 72)
        self._font_spin.setValue(self._font_size)
        self._font_spin.setSuffix(" pt")
        self._font_spin.setFixedHeight(_ICON_H)
        self._font_spin.setToolTip("Text font size")
        self._font_spin.valueChanged.connect(lambda v: setattr(self, '_font_size', v))
        tb.addWidget(self._font_spin)
        tb.addStretch()
        main.addLayout(tb)

        # ---- Canvas in a scroll area ----
        self._canvas = _AnnotationCanvas(self, self._disp_w, self._disp_h)
        self._canvas.setFocusPolicy(Qt.ClickFocus)
        scroll = QScrollArea()
        scroll.setWidget(self._canvas)
        scroll.setWidgetResizable(False)
        scroll.setFrameShape(QFrame.NoFrame)
        main.addWidget(scroll, stretch=1)

        self._text_input = QLineEdit(self._canvas)
        self._text_input.hide()
        self._text_input.returnPressed.connect(self._commit_text_edit)
        self._text_input.installEventFilter(self)

        # ---- Bottom bar ----
        bot = QHBoxLayout()
        bot.setSpacing(6)
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(self._on_copy)
        save_btn = QPushButton("Save PNG...")
        save_btn.clicked.connect(self._on_save)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        self._status_lbl = QLabel("")
        bot.addWidget(copy_btn)
        bot.addWidget(save_btn)
        bot.addStretch()
        bot.addWidget(self._status_lbl)
        bot.addWidget(close_btn)
        main.addLayout(bot)

        self.resize(self._disp_w + 40, self._disp_h + 130)

    # ------------------------------------------------------------------
    # Tool / colour helpers
    # ------------------------------------------------------------------

    def _select_tool(self, tool: str) -> None:
        self._tool = tool
        self._hover_handle = ''
        for tid, btn in self._tool_btns.items():
            btn.setChecked(tid == tool)

    def _on_dash_toggled(self, checked: bool) -> None:
        self._dashed = checked
        if 0 <= self._selected_idx < len(self._shapes):
            shape = self._shapes[self._selected_idx]
            if shape['type'] != 'text':
                shape['dashed'] = checked
                self._canvas.update()

    def _sync_dash_from_shape(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._shapes):
            return
        shape = self._shapes[idx]
        if shape['type'] == 'text':
            return
        dashed = bool(shape.get('dashed')) or shape['type'] == 'dash'
        self._dashed = dashed
        self._dash_cb.blockSignals(True)
        self._dash_cb.setChecked(dashed)
        self._dash_cb.blockSignals(False)

    def _pick_color(self) -> None:
        from PyQt5.QtWidgets import QColorDialog  # always available, import locally
        color = QColorDialog.getColor(self._color, self, "Pick Colour")
        if color.isValid():
            self._color = color
            self._refresh_color_btn()

    def _refresh_color_btn(self) -> None:
        self._color_btn.setStyleSheet(
            f"background-color: {self._color.name()}; border: 1px solid #888;")

    def _to_img(self, cx: float, cy: float) -> tuple:
        """Convert canvas display coordinates to image pixel coordinates."""
        return cx / self._scale, cy / self._scale

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._text_input:
            if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
                self._cancel_text_edit()
                return True
            if event.type() == QEvent.FocusOut:
                QTimer.singleShot(0, self._deferred_commit_text_edit)
        return super().eventFilter(obj, event)

    def _deferred_commit_text_edit(self) -> None:
        if not self._text_input.isVisible():
            return
        if QApplication.focusWidget() is self._text_input:
            return
        self._commit_text_edit()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            if self._text_edit_active():
                self._cancel_text_edit()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._commit_text_edit()
        super().closeEvent(event)

    def _text_edit_active(self) -> bool:
        return self._text_input.isVisible()

    def _should_skip_text_shape_paint(self, idx: int, shape: dict) -> bool:
        return (self._text_edit_active()
                and idx == self._text_edit_shape_idx
                and shape['type'] == 'text')

    def _is_editing_shape_label(self, shape: dict) -> bool:
        if not self._text_edit_active() or self._text_edit_shape_idx < 0:
            return False
        if self._text_edit_shape_idx >= len(self._shapes):
            return False
        ref = self._shapes[self._text_edit_shape_idx]
        return ref is shape and shape.get('type') != 'text'

    @staticmethod
    def _shape_label_anchor(shape: dict, font_size: int) -> dict:
        fs = shape.get('label_font_size', font_size)
        col = shape['color']
        t = shape['type']
        if t in SnapshotEditorDialog._LINE_TOOLS:
            return {
                'x': (shape['x1'] + shape['x2']) / 2.0,
                'y': (shape['y1'] + shape['y2']) / 2.0,
                'angle': SnapshotEditorDialog._label_angle_for_line(
                    shape['x1'], shape['y1'], shape['x2'], shape['y2']),
                'font_size': fs,
                'color': col,
            }
        if t in ('rect', 'circle'):
            return {
                'x': shape['x'] + shape['w'] / 2.0,
                'y': shape['y'] + shape['h'] / 2.0,
                'angle': 0.0,
                'font_size': fs,
                'color': col,
            }
        return {'x': 0.0, 'y': 0.0, 'angle': 0.0, 'font_size': fs, 'color': col}

    def _hide_text_edit(self) -> None:
        self._text_input.clearFocus()
        self._text_input.hide()
        self._text_edit_shape_idx = -1
        self._canvas.setFocus()
        self._canvas.update()

    def _cancel_text_edit(self) -> None:
        if not self._text_edit_active():
            return
        self._text_input.blockSignals(True)
        self._text_input.clear()
        self._text_input.blockSignals(False)
        self._hide_text_edit()

    def _commit_text_edit(self) -> None:
        if not self._text_edit_active():
            return
        self._text_input.blockSignals(True)
        try:
            text = self._text_input.text().strip()
            idx = self._text_edit_shape_idx
            if idx >= 0:
                shape = self._shapes[idx]
                if shape['type'] == 'text':
                    if text:
                        shape['text'] = text
                    else:
                        self._shapes.pop(idx)
                        if self._selected_idx == idx:
                            self._selected_idx = -1
                        elif self._selected_idx > idx:
                            self._selected_idx -= 1
                elif text:
                    shape['label'] = text
                    shape.setdefault('label_font_size', self._font_size)
                else:
                    shape.pop('label', None)
                    shape.pop('label_font_size', None)
            elif text:
                self._shapes.append({
                    'type': 'text',
                    'color': QColor(self._color),
                    'font_size': self._font_size,
                    'x': self._text_edit_img_x,
                    'y': self._text_edit_img_y,
                    'text': text,
                })
                self._selected_idx = -1
            self._text_input.clear()
            self._hide_text_edit()
        finally:
            self._text_input.blockSignals(False)

    def _position_text_edit(self, img_x: float, img_y: float, angle: float,
                            color: QColor, font_size: int, initial: str,
                            center: bool) -> None:
        px = max(10, int(font_size * self._scale))
        est_w = max(80, int(max(len(initial or 'M'), 4) * font_size * 0.65 * self._scale) + 16)
        est_h = px + 10
        dx = int(img_x * self._scale)
        dy = int(img_y * self._scale)
        if center:
            x = dx - est_w // 2
            y = dy - est_h // 2
        else:
            x = dx
            y = dy
        x = max(0, min(x, self._disp_w - est_w))
        y = max(0, min(y, self._disp_h - est_h))
        self._text_input.setStyleSheet(
            "QLineEdit {"
            f"  color: {color.name()};"
            "  background: rgba(0, 0, 0, 90);"
            "  border: 1px dashed rgba(255,255,255,180);"
            "  font-weight: bold;"
            f"  font-size: {px}px;"
            "  padding: 2px 4px;"
            "}")
        self._text_input.setGeometry(x, y, est_w, est_h)
        self._text_input.setText(initial)
        self._text_input.show()
        self._text_input.raise_()
        self._text_input.setFocus(Qt.OtherFocusReason)
        self._text_input.selectAll()

    def _begin_text_edit(
        self,
        shape_idx: int = -1,
        img_x: float = 0.0,
        img_y: float = 0.0,
        angle: float = 0.0,
        initial: str = '',
        color: Optional[QColor] = None,
        font_size: Optional[int] = None,
        center: bool = False,
    ) -> None:
        self._commit_text_edit()
        col = color if color is not None else self._color
        fs = font_size if font_size is not None else self._font_size
        self._text_edit_shape_idx = shape_idx
        self._text_edit_img_x = img_x
        self._text_edit_img_y = img_y
        self._position_text_edit(img_x, img_y, angle, col, fs, initial, center)
        self._canvas.update()

    def _begin_edit_shape_text(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._shapes):
            return
        self._selected_idx = idx
        shape = self._shapes[idx]
        if shape['type'] == 'text':
            self._begin_text_edit(
                shape_idx=idx,
                img_x=shape['x'],
                img_y=shape['y'],
                angle=0.0,
                initial=shape.get('text', ''),
                color=shape['color'],
                font_size=shape.get('font_size', self._font_size),
                center=False,
            )
        else:
            anchor = self._shape_label_anchor(shape, self._font_size)
            self._begin_text_edit(
                shape_idx=idx,
                img_x=anchor['x'],
                img_y=anchor['y'],
                angle=anchor['angle'],
                initial=shape.get('label', ''),
                color=anchor['color'],
                font_size=anchor['font_size'],
                center=True,
            )

    # ------------------------------------------------------------------
    # Undo
    # ------------------------------------------------------------------

    def _undo(self) -> None:
        if self._text_edit_active():
            self._cancel_text_edit()
            return
        if self._shapes:
            self._shapes.pop()
            if self._selected_idx >= len(self._shapes):
                self._selected_idx = -1
            self._canvas.update()

    # ------------------------------------------------------------------
    # Hit-testing and shape movement
    # ------------------------------------------------------------------

    def _hit_test(self, x: float, y: float) -> int:
        """Return index of the topmost shape at image-coord (x,y), or -1."""
        thr = 10.0 / max(self._scale, 0.01)  # 10 display px in image space
        for i in range(len(self._shapes) - 1, -1, -1):
            s = self._shapes[i]
            t = s['type']
            if t in self._LINE_TOOLS:
                d = _point_to_seg_dist(x, y, s['x1'], s['y1'], s['x2'], s['y2'])
                if d < thr + s.get('width', 2):
                    return i
            elif t in ('rect', 'circle'):
                rx, ry, rw, rh = s['x'], s['y'], s['w'], s['h']
                if rw < 0: rx += rw; rw = -rw
                if rh < 0: ry += rh; rh = -rh
                if rx - thr <= x <= rx + rw + thr and ry - thr <= y <= ry + rh + thr:
                    return i
            elif t == 'text':
                fs = s['font_size']
                approx_w = len(s['text']) * fs * 0.65
                if (s['x'] - thr <= x <= s['x'] + approx_w + thr and
                        s['y'] - thr <= y <= s['y'] + fs + thr):
                    return i
        return -1

    def _move_shape(self, idx: int, dx: float, dy: float) -> None:
        """Translate shape at *idx* by (dx, dy) in image coordinates."""
        s = self._shapes[idx]
        t = s['type']
        if t in self._LINE_TOOLS:
            s['x1'] += dx;  s['y1'] += dy
            s['x2'] += dx;  s['y2'] += dy
        elif t in ('rect', 'circle'):
            s['x'] += dx;  s['y'] += dy
        elif t == 'text':
            s['x'] += dx;  s['y'] += dy

    def _duplicate_shape(self, idx: int) -> int:
        """Append a copy of shape *idx* and return the new index."""
        s = self._shapes[idx]
        t = s['type']
        dup: dict = {'type': t, 'color': QColor(s['color'])}
        if t in self._LINE_TOOLS:
            dup['width'] = s.get('width', 2)
            dup['x1'] = s['x1']
            dup['y1'] = s['y1']
            dup['x2'] = s['x2']
            dup['y2'] = s['y2']
        elif t in ('rect', 'circle'):
            dup['width'] = s.get('width', 2)
            dup['x'] = s['x']
            dup['y'] = s['y']
            dup['w'] = s['w']
            dup['h'] = s['h']
        elif t == 'text':
            dup['font_size'] = s['font_size']
            dup['x'] = s['x']
            dup['y'] = s['y']
            dup['text'] = s['text']
        if s.get('label'):
            dup['label'] = s['label']
        if s.get('label_font_size'):
            dup['label_font_size'] = s['label_font_size']
        if s.get('dashed') or t == 'dash':
            dup['dashed'] = True
        self._shapes.append(dup)
        return len(self._shapes) - 1

    def _get_control_points(self, shape: dict) -> list:
        t = shape['type']
        if t in self._LINE_TOOLS:
            return [
                ('start', shape['x1'], shape['y1']),
                ('end', shape['x2'], shape['y2']),
            ]
        if t in ('rect', 'circle'):
            x, y, w, h = shape['x'], shape['y'], shape['w'], shape['h']
            return [
                ('nw', x, y), ('n', x + w / 2.0, y), ('ne', x + w, y),
                ('e', x + w, y + h / 2.0),
                ('se', x + w, y + h), ('s', x + w / 2.0, y + h), ('sw', x, y + h),
                ('w', x, y + h / 2.0),
            ]
        return []

    def _hit_control_point(self, x: float, y: float) -> Optional[str]:
        if self._selected_idx < 0 or self._selected_idx >= len(self._shapes):
            return None
        points = self._get_control_points(self._shapes[self._selected_idx])
        if not points:
            return None
        thr = max(8.0, 10.0 / max(self._scale, 0.01))
        for hid, hx, hy in points:
            if math.hypot(x - hx, y - hy) <= thr:
                return hid
        return None

    def _get_handle_anchor(self, shape: dict, handle: str) -> Optional[tuple]:
        if shape['type'] not in ('rect', 'circle'):
            return None
        x, y, w, h = shape['x'], shape['y'], shape['w'], shape['h']
        if handle == 'nw': return (x + w, y + h)
        if handle == 'ne': return (x, y + h)
        if handle == 'se': return (x, y)
        if handle == 'sw': return (x + w, y)
        return None

    def _cursor_for_handle(self, handle: str):
        if handle in ('nw', 'se'):
            return Qt.SizeFDiagCursor
        if handle in ('ne', 'sw'):
            return Qt.SizeBDiagCursor
        if handle in ('n', 's'):
            return Qt.SizeVerCursor
        if handle in ('e', 'w'):
            return Qt.SizeHorCursor
        return Qt.CrossCursor

    def _resize_shape_by_handle(self, idx: int, handle: str, x: float, y: float, force_snap: bool = False) -> None:
        s = self._shapes[idx]
        t = s['type']

        if t in self._LINE_TOOLS:
            if handle == 'start':
                s['x1'], s['y1'] = _snap_line_end(s['x2'], s['y2'], x, y, force_snap)
            elif handle == 'end':
                s['x2'], s['y2'] = _snap_line_end(s['x1'], s['y1'], x, y, force_snap)
            return

        if t not in ('rect', 'circle'):
            return

        if handle == 'n':
            bottom = s['y'] + s['h']
            top = y
            s['y'] = min(top, bottom)
            s['h'] = abs(bottom - top)
            return
        if handle == 's':
            top = s['y']
            bottom = y
            s['y'] = min(top, bottom)
            s['h'] = abs(bottom - top)
            return
        if handle == 'w':
            right = s['x'] + s['w']
            left = x
            s['x'] = min(left, right)
            s['w'] = abs(right - left)
            return
        if handle == 'e':
            left = s['x']
            right = x
            s['x'] = min(left, right)
            s['w'] = abs(right - left)
            return

        if handle in ('nw', 'ne', 'se', 'sw') and self._drag_anchor is not None:
            ax, ay = self._drag_anchor
            x1, y1 = x, y
            if force_snap:
                dx = x1 - ax
                dy = y1 - ay
                size = min(abs(dx), abs(dy))
                x1 = ax + (-size if dx < 0 else size)
                y1 = ay + (-size if dy < 0 else size)
            s['x'] = min(x1, ax)
            s['y'] = min(y1, ay)
            s['w'] = abs(x1 - ax)
            s['h'] = abs(y1 - ay)

    def _shape_bounds(self, shape: dict) -> tuple:
        t = shape['type']
        if t in ('rect', 'circle'):
            return shape['x'], shape['y'], shape['w'], shape['h']
        if t == 'text':
            fs = shape.get('font_size', 20)
            w = len(shape.get('text', '')) * fs * 0.65
            return shape['x'], shape['y'], w, fs
        x1 = min(shape['x1'], shape['x2'])
        y1 = min(shape['y1'], shape['y2'])
        return x1, y1, abs(shape['x2'] - shape['x1']), abs(shape['y2'] - shape['y1'])

    def _paint_selection(self, painter: QPainter, shape: dict) -> None:
        x, y, w, h = self._shape_bounds(shape)
        sel_pen = QPen(QColor('#50beff'), max(1.0, 1.5 / max(self._scale, 0.01)), Qt.DashLine)
        sel_pen.setDashPattern([5.0 / max(self._scale, 0.01), 4.0 / max(self._scale, 0.01)])
        painter.setPen(sel_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(x, y, max(1.0, w), max(1.0, h)))

        points = self._get_control_points(shape)
        if not points:
            return
        r = max(4.0, 6.0 / max(self._scale, 0.01))
        outline_pen = QPen(QColor('#2c8cff'), max(1.2, 1.8 / max(self._scale, 0.01)))
        painter.setPen(outline_pen)
        painter.setBrush(QBrush(QColor('#ffffff')))
        for _hid, px, py in points:
            painter.drawEllipse(QPointF(px, py), r, r)

    # ------------------------------------------------------------------
    # Shape rendering
    # ------------------------------------------------------------------

    @staticmethod
    def _shape_is_dashed(shape: dict) -> bool:
        return bool(shape.get('dashed')) or shape.get('type') == 'dash'

    def _stroke_pen(
        self,
        col: QColor,
        w: float,
        dashed: bool = False,
        cap=Qt.RoundCap,
        join=Qt.RoundJoin,
    ) -> QPen:
        if dashed:
            pen = QPen(col, w, Qt.CustomDashLine, cap, join)
            pen.setDashPattern([20.0 / max(w, 1), 10.0 / max(w, 1)])
        else:
            pen = QPen(col, w, Qt.SolidLine, cap, join)
        return pen

    def _paint_shapes(
        self,
        painter: QPainter,
        shapes: list,
        override_color: Optional[QColor] = None,
        extra_width: int = 0,
    ) -> None:
        for shape in shapes:
            t = shape['type']
            col = override_color if override_color is not None else shape['color']
            w = shape.get('width', 2) + extra_width
            if t == 'text':
                self._paint_text(painter, shape, override_color, extra_width)
            elif t == 'arrow' or t == 'dblarrow':
                self._paint_line_arrow(
                    painter, shape, col, w, extra_width, double=(t == 'dblarrow'))
            elif t == 'line' or t == 'dash':
                dashed = self._shape_is_dashed(shape)
                painter.setPen(self._stroke_pen(col, w, dashed))
                painter.setBrush(Qt.NoBrush)
                self._draw_line_with_label_gap(
                    painter,
                    shape['x1'], shape['y1'], shape['x2'], shape['y2'],
                    self._line_label_gap_half(shape),
                )
            elif t == 'rect':
                dashed = self._shape_is_dashed(shape)
                pen = self._stroke_pen(col, w, dashed, Qt.SquareCap, Qt.MiterJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(QRectF(shape['x'], shape['y'],
                                        shape['w'], shape['h']))
            elif t == 'circle':
                dashed = self._shape_is_dashed(shape)
                painter.setPen(self._stroke_pen(col, w, dashed))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QRectF(shape['x'], shape['y'],
                                           shape['w'], shape['h']))
            if t != 'text' and shape.get('label') and not self._is_editing_shape_label(shape):
                self._paint_attached_label(painter, shape, override_color, extra_width)

    @staticmethod
    def _label_angle_for_line(x1: float, y1: float, x2: float, y2: float) -> float:
        angle = math.atan2(y2 - y1, x2 - x1)
        if angle > math.pi / 2:
            angle -= math.pi
        elif angle < -math.pi / 2:
            angle += math.pi
        return angle

    def _line_label_gap_half(self, shape: dict) -> float:
        label = shape.get('label')
        if not label:
            return 0.0
        fs = shape.get('label_font_size', self._font_size)
        return max(len(label) * fs * 0.65, fs) / 2.0 + 6.0

    @staticmethod
    def _draw_line_with_label_gap(
        painter: QPainter,
        x1: float, y1: float, x2: float, y2: float,
        gap_half: float,
    ) -> None:
        if gap_half <= 0:
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            return
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 1:
            return
        if gap_half * 2.2 >= length:
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            return
        ux, uy = dx / length, dy / length
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        painter.drawLine(
            QPointF(x1, y1), QPointF(mx - ux * gap_half, my - uy * gap_half))
        painter.drawLine(
            QPointF(mx + ux * gap_half, my + uy * gap_half), QPointF(x2, y2))

    def _paint_attached_label(
        self,
        painter: QPainter,
        shape: dict,
        override_color: Optional[QColor] = None,
        extra_width: int = 0,
    ) -> None:
        label = shape.get('label')
        if not label or shape['type'] == 'text':
            return
        t = shape['type']
        col = override_color if override_color is not None else shape['color']
        fs = shape.get('label_font_size', self._font_size)
        font = QFont()
        font.setBold(True)
        font.setPixelSize(fs)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(label)

        if t in self._LINE_TOOLS:
            cx = (shape['x1'] + shape['x2']) / 2.0
            cy = (shape['y1'] + shape['y2']) / 2.0
            angle = self._label_angle_for_line(
                shape['x1'], shape['y1'], shape['x2'], shape['y2'])
        elif t in ('rect', 'circle'):
            cx = shape['x'] + shape['w'] / 2.0
            cy = shape['y'] + shape['h'] / 2.0
            angle = 0.0
        else:
            return

        painter.save()
        painter.translate(cx, cy)
        if angle:
            painter.rotate(math.degrees(angle))
        path = QPainterPath()
        path.addText(QPointF(-tw / 2.0, fm.ascent() / 2.0), font, label)
        if override_color is not None:
            stroke_w = 4 + extra_width * 2
            painter.strokePath(
                path,
                QPen(col, stroke_w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        else:
            painter.setPen(Qt.NoPen)
            painter.fillPath(path, col)
        painter.restore()

    def _paint_line_arrow(
        self,
        painter: QPainter,
        shape: dict,
        col: QColor,
        w: int,
        extra_width: int,
        *,
        double: bool = False,
    ) -> None:
        x1, y1 = shape['x1'], shape['y1']
        x2, y2 = shape['x2'], shape['y2']
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 1:
            return
        angle = math.atan2(y2 - y1, x2 - x1)
        arrow_len = max(12.0, shape['width'] * 4.0)
        arrow_ang = math.pi / 6.0
        if double:
            inset = arrow_len * 0.6
            sx = x1 + inset * math.cos(angle)
            sy = y1 + inset * math.sin(angle)
            ex = x2 - inset * math.cos(angle)
            ey = y2 - inset * math.sin(angle)
            tips = ((x2, y2, angle), (x1, y1, angle + math.pi))
        else:
            sx, sy = x1, y1
            ex = x2 - arrow_len * 0.6 * math.cos(angle)
            ey = y2 - arrow_len * 0.6 * math.sin(angle)
            tips = ((x2, y2, angle),)

        painter.setPen(self._stroke_pen(col, w, self._shape_is_dashed(shape)))
        painter.setBrush(Qt.NoBrush)
        self._draw_line_with_label_gap(
            painter, sx, sy, ex, ey, self._line_label_gap_half(shape))

        stroke_w = max(1, extra_width)
        painter.setPen(QPen(col, stroke_w, Qt.SolidLine))
        painter.setBrush(QBrush(col))
        for tip_x, tip_y, ang in tips:
            tip = QPointF(tip_x, tip_y)
            p1 = QPointF(tip_x - arrow_len * math.cos(ang - arrow_ang),
                         tip_y - arrow_len * math.sin(ang - arrow_ang))
            p2 = QPointF(tip_x - arrow_len * math.cos(ang + arrow_ang),
                         tip_y - arrow_len * math.sin(ang + arrow_ang))
            painter.drawPolygon(QPolygonF([tip, p1, p2]))

    def _paint_text(
        self,
        painter: QPainter,
        shape: dict,
        override_color: Optional[QColor],
        extra_width: int,
    ) -> None:
        col = override_color if override_color is not None else shape['color']
        font = QFont()
        font.setBold(True)
        font.setPixelSize(shape['font_size'])
        fm = QFontMetrics(font)
        baseline_y = shape['y'] + fm.ascent()
        path = QPainterPath()
        path.addText(shape['x'], baseline_y, font, shape['text'])
        if override_color is not None:
            # Outline pass: stroke path with a wider pen (4 px -> 2 px halo each side)
            stroke_w = 4 + extra_width * 2
            painter.strokePath(path,
                               QPen(col, stroke_w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        else:
            # Colour pass: fill the glyph path
            painter.setPen(Qt.NoPen)
            painter.fillPath(path, col)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _render_final_pixmap(self) -> QPixmap:
        """Composite the original image and all annotations at full resolution."""
        self._commit_text_edit()
        result = QPixmap(self._orig_pixmap)
        painter = QPainter(result)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            self._paint_shapes(painter, self._shapes, QColor('#ffffff'), 2)
            self._paint_shapes(painter, self._shapes)
        finally:
            painter.end()
        return result

    def _on_copy(self) -> None:
        _copy_pixmap_to_clipboard(self._render_final_pixmap())
        self._show_status("Copied to clipboard!")

    def _on_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Annotated Image", "annotated-snapshot.png",
            "PNG images (*.png);;All files (*)"
        )
        if not path:
            return
        pixmap = self._render_final_pixmap()
        if not pixmap.save(path, "PNG"):
            QMessageBox.critical(self, "Save Error", f"Could not save image:\n{path}")
            return
        self._show_status(f"Saved: {os.path.basename(path)}")

    def _show_status(self, msg: str) -> None:
        self._status_lbl.setText(msg)
        QTimer.singleShot(3000, lambda: self._status_lbl.setText(""))

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

def _exec_centred(dlg, parent):
    """Call exec_() after centring *dlg* over *parent*.
    Pre-positioning the window before exec_() prevents an X11 placement flash
    where the WM briefly maps the window at a stale position before
    repositioning it to honour Qt's centering request.
    """
    pg = parent.frameGeometry()
    w  = dlg.width()  if dlg.width()  > 0 else dlg.sizeHint().width()
    h  = dlg.height() if dlg.height() > 0 else dlg.sizeHint().height()
    dlg.move(
        max(0, pg.x() + (pg.width()  - w) // 2),
        max(0, pg.y() + (pg.height() - h) // 2),
    )
    return dlg.exec_()

# ===========================================================================
# CPU Load Graph
# ===========================================================================

# ===========================================================================
# CPU Load Graph
# ===========================================================================

class _CpuLoadGraph(QWidget):
    """Synchronised CPU load chart below the main timeline.

    View modes
    ----------
    Task view + no selection  -> 1 row: total CPU usage across all cores
    Task view + task selected -> 1 row: selected task's CPU usage
    Core view + no selection  -> 1 row per core at full row height
    Core view + task selected -> 1 row per core showing that task's usage on each core

    Rows can be collapsed (core view only): collapsed height = CPU_LOAD_COLLAPSED_H px,
    label still visible. Click label to toggle. Expand/Collapse All button syncs via
    set_all_expanded().
    """

    _NUM_BINS = 1024

    def __init__(self, view: "TimelineView", parent: QWidget = None) -> None:
        super().__init__(parent)
        self._view                                          = view
        self._trace                                         = None
        self._is_dark: bool                                 = True
        self._view_mode: str                                = "task"
        self._selected_task: Optional[str]                  = None
        self._collapsed_cores: set                          = set()
        self._row_h: int                                    = CPU_LOAD_ROW_H
        self._core_bins:      Dict[str, List[float]]        = {}
        self._task_bins:      Dict[str, List[float]]        = {}
        self._task_core_bins: Dict[str, Dict[str, List[float]]] = {}
        self._total_bins:     List[float]                   = []
        self._avg_load:       Dict[str, float]              = {}
        self._bin_w_ns: float                               = 1.0
        self._font_size: int                                = 8
        self._hover_y: int                                  = -1
        self.setMinimumSize(40, 40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setMouseTracking(True)
        self._scroll_area: Optional["QScrollArea"] = None
        self.setToolTip(
            "CPU load over time - synchronised with timeline\n"
            "Core view: click a label to collapse/expand that core row"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_trace(self, trace) -> None:
        self._trace           = trace
        self._selected_task   = None
        self._collapsed_cores = set()
        self._core_bins       = {}
        self._task_bins       = {}
        self._task_core_bins  = {}
        self._total_bins      = []
        self._avg_load        = {}
        if trace is not None:
            self._compute_bins(trace)
        self.updateGeometry()
        self.update()

    def set_task(self, task_name, locked: bool) -> None:
        self._selected_task = task_name if (locked and task_name) else None
        self.updateGeometry()
        self.update()

    def set_dark(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self.update()

    def set_view_mode(self, mode: str) -> None:
        self._view_mode = mode
        self.updateGeometry()
        self.update()

    def set_row_h(self, h: int) -> None:
        self._row_h = max(12, h)
        self.updateGeometry()
        self.update()

    def set_font_size(self, size: int) -> None:
        self._font_size = max(6, size)
        self.update()

    def set_core_expanded(self, core: str, expanded: bool) -> None:
        if expanded:
            self._collapsed_cores.discard(core)
        else:
            self._collapsed_cores.add(core)
        self.updateGeometry()
        self.update()

    def set_all_expanded(self, expanded: bool) -> None:
        if expanded:
            self._collapsed_cores.clear()
        else:
            if self._trace:
                self._collapsed_cores = set(self._trace.core_names or [])
        self.updateGeometry()
        self.update()

    # ------------------------------------------------------------------
    # Size hint - drives QScrollArea scrollbar
    # ------------------------------------------------------------------

    def sizeHint(self) -> "QSize":
        return self.minimumSizeHint()

    def minimumSizeHint(self) -> "QSize":
        _TITLE_H = 22
        rows    = self._get_rows()
        total_h = _TITLE_H + sum(self._row_effective_h(k, key) + CPU_LOAD_ROW_GAP
                                  for k, key, _, _ in rows)
        return QSize(200, max(40, total_h))

    def _sync_scroll_size(self) -> None:
        """Resize to full content height so QScrollArea can scroll when cores overflow."""
        scroll = self._scroll_area
        if scroll is None:
            return
        vp = scroll.viewport()
        w = vp.width()
        if w <= 0:
            return
        h = self.minimumSizeHint().height()
        if self.width() != w or self.height() != h:
            self.resize(w, h)

    def updateGeometry(self) -> None:  # noqa: N802
        super().updateGeometry()
        self._sync_scroll_size()

    # ------------------------------------------------------------------
    # Pre-computation  (difference-array trick - O(n_segs + n_bins))
    # ------------------------------------------------------------------

    def _compute_bins(self, trace) -> None:
        n     = self._NUM_BINS
        t_min = trace.time_min
        t_max = trace.time_max
        span  = max(t_max - t_min, 1)
        bin_w = span / n
        self._bin_w_ns = bin_w

        cores = trace.core_names or []
        core_busy: Dict[str, List[float]]                        = {c: [0.0] * n for c in cores}
        core_diff: Dict[str, List[float]]                        = {c: [0.0] * (n + 2) for c in cores}
        task_busy: Dict[str, List[float]]                        = {}
        task_diff: Dict[str, List[float]]                        = {}
        task_core_busy: Dict[str, Dict[str, List[float]]]        = {}
        task_core_diff: Dict[str, Dict[str, List[float]]]        = {}

        for seg in trace.segments:
            mk   = _task_merge_key(seg.task)
            name = _parse_task_name(seg.task)[2]
            skip = _is_idle_task_name(name) or name.upper() == "TICK"

            b0 = max(0, min(n - 1, int((seg.start - t_min) / bin_w)))
            b1 = max(0, min(n - 1, int((seg.end   - t_min) / bin_w)))

            first_end = t_min + (b0 + 1) * bin_w
            first_c   = min(seg.end, first_end) - seg.start

            # Per-core accumulation (skip IDLE / TICK for core load)
            if not skip and seg.core in core_busy:
                cb = core_busy[seg.core]; cd = core_diff[seg.core]
                cb[b0] += first_c
                if b1 > b0:
                    cb[b1] += max(0.0, seg.end - (t_min + b1 * bin_w))
                    if b1 > b0 + 1:
                        cd[b0 + 1] += bin_w; cd[b1] -= bin_w

            # Per-task total accumulation
            if mk not in task_busy:
                task_busy[mk] = [0.0] * n
                task_diff[mk] = [0.0] * (n + 2)
            tb = task_busy[mk]; td = task_diff[mk]
            tb[b0] += first_c
            if b1 > b0:
                tb[b1] += max(0.0, seg.end - (t_min + b1 * bin_w))
                if b1 > b0 + 1:
                    td[b0 + 1] += bin_w; td[b1] -= bin_w

            # Per-task per-core accumulation
            if mk not in task_core_busy:
                task_core_busy[mk] = {}
                task_core_diff[mk] = {}
            if seg.core not in task_core_busy[mk]:
                task_core_busy[mk][seg.core] = [0.0] * n
                task_core_diff[mk][seg.core] = [0.0] * (n + 2)
            tc  = task_core_busy[mk][seg.core]
            tcd = task_core_diff[mk][seg.core]
            tc[b0] += first_c
            if b1 > b0:
                tc[b1] += max(0.0, seg.end - (t_min + b1 * bin_w))
                if b1 > b0 + 1:
                    tcd[b0 + 1] += bin_w; tcd[b1] -= bin_w

        inv = 1.0 / bin_w

        # Materialise core bins
        for core in cores:
            run = 0.0; bb, bd = core_busy[core], core_diff[core]
            for i in range(n):
                run += bd[i]; bb[i] += run
            self._core_bins[core] = [min(1.0, max(0.0, v * inv)) for v in bb]

        # Materialise task bins
        for mk in task_busy:
            run = 0.0; tb2, td2 = task_busy[mk], task_diff[mk]
            for i in range(n):
                run += td2[i]; tb2[i] += run
            self._task_bins[mk] = [min(1.0, max(0.0, v * inv)) for v in tb2]

        # Materialise task-core bins
        for mk in task_core_busy:
            self._task_core_bins[mk] = {}
            for core in task_core_busy[mk]:
                run = 0.0; tc2 = task_core_busy[mk][core]; tcd2 = task_core_diff[mk][core]
                for i in range(n):
                    run += tcd2[i]; tc2[i] += run
                self._task_core_bins[mk][core] = [min(1.0, max(0.0, v * inv)) for v in tc2]

        # Total bins - average non-IDLE load across all cores
        nc = max(1, len(cores))
        self._total_bins = [
            min(1.0, sum(self._core_bins[c][i] for c in cores) / nc)
            for i in range(n)
        ] if cores else []

        # Average load per key (for label percentage display)
        self._avg_load = {}
        for core in cores:
            b = self._core_bins.get(core, [])
            self._avg_load[core] = sum(b) / len(b) if b else 0.0
        for mk, b in self._task_bins.items():
            self._avg_load[mk] = sum(b) / len(b) if b else 0.0
        if self._total_bins:
            self._avg_load["total"] = sum(self._total_bins) / len(self._total_bins)

    # ------------------------------------------------------------------
    # Row helpers
    # ------------------------------------------------------------------

    def _get_rows(self) -> List[tuple]:
        """Return [(kind, key, label, QColor), ...] for currently displayed rows."""
        if not self._trace:
            return []
        task  = self._selected_task
        cores = self._trace.core_names or []

        if self._view_mode == "task":
            if task and task in self._task_bins:
                raw = self._trace.task_repr.get(task, task)
                return [("task", task, _task_display_name(raw), _task_color(raw))]
            return [("total", "total", "CPU Load", QColor("#4CAF50"))]

        # Core view - one row per core
        return [("core", c, c, QColor(_core_color(c))) for c in cores]

    def _row_effective_h(self, kind: str, key: str) -> int:
        if kind == "core" and key in self._collapsed_cores:
            return CPU_LOAD_COLLAPSED_H
        return self._row_h

    def _bins_for_row(self, kind: str, key: str):
        task = self._selected_task
        if kind == "total":
            return self._total_bins or None
        if kind == "task":
            return self._task_bins.get(key)
        # "core" - show task's load on this core if a task is selected
        if task:
            return self._task_core_bins.get(task, {}).get(key)
        return self._core_bins.get(key)

    def _bin_indices_for_ns_range(self, ns_lo: int, ns_hi: int) -> Tuple[int, int]:
        n = self._NUM_BINS
        t_min = self._trace.time_min
        b0 = max(0, min(n - 1, int((ns_lo - t_min) / self._bin_w_ns)))
        b1 = max(0, min(n - 1, int((ns_hi - t_min) / self._bin_w_ns)))
        if b1 < b0:
            b0, b1 = b1, b0
        return b0, b1

    def _avg_bins_in_ns_range(self, bins: Optional[List[float]],
                              ns_lo: int, ns_hi: int) -> float:
        if not bins:
            return 0.0
        b0, b1 = self._bin_indices_for_ns_range(ns_lo, ns_hi)
        sl = bins[b0:b1 + 1]
        return sum(sl) / len(sl) if sl else 0.0

    def _load_at_ns(self, bins: Optional[List[float]], ns: int) -> float:
        if not bins:
            return 0.0
        b0, _ = self._bin_indices_for_ns_range(ns, ns)
        return bins[b0]

    def _cursor_range_ns(self, scene) -> Optional[Tuple[int, int]]:
        times = getattr(scene, '_cursor_times', None) or []
        if len(times) < 2:
            return None
        s = sorted(times)
        lo, hi = s[0], s[-1]
        if hi <= lo:
            return None
        return lo, hi

    def _plot_right_x(self) -> int:
        """Right edge of the timeline plot area (excludes timeline v-scrollbar)."""
        return max(1, self._view.viewport().width())

    def _plot_axis_span(self, lw: int) -> int:
        return max(1, self._plot_right_x() - lw - 1)

    def _row_at_y(self, y: int) -> Optional[Tuple[str, str, int, int]]:
        """Return (kind, key, row_y, row_h) for plot row at widget *y*, or None."""
        _TITLE_H = 22
        ry = _TITLE_H
        for kind, key, _, _ in self._get_rows():
            rh = self._row_effective_h(kind, key)
            if ry <= y < ry + rh:
                return kind, key, ry, rh
            ry += rh + CPU_LOAD_ROW_GAP
        return None

    def _draw_load_badge(self, painter: QPainter, x: int, row_y: int,
                         text: str, dark: bool, *, full: bool = False) -> None:
        """Draw a small load/time badge anchored near *x* on a CPU load row."""
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(text) + 8
        bx = max(self._view._scene._label_width + 2,
                 min(self._plot_right_x() - tw - 2, x - tw // 2))
        by = row_y + 2
        bg = QColor(40, 40, 40, 210) if dark else QColor(255, 255, 255, 230)
        fg = QColor("#FFFFFF") if dark else QColor("#111111")
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(bx, by, tw, 12, 2, 2)
        painter.setPen(fg)
        sf = QFont(painter.font())
        sf.setPointSize(max(5, self._font_size - (1 if full else 2)))
        painter.setFont(sf)
        painter.drawText(QRect(bx + 4, by, tw - 8, 12), Qt.AlignVCenter | Qt.AlignLeft, text)

    def _visible_time_ns_range(self, scene) -> Tuple[int, int]:
        if self._trace is None:
            return 0, 1
        vp = self._view.viewport().rect()
        if scene._horizontal:
            c_lo = self._view.mapToScene(QPoint(scene._label_width, 0)).x()
            c_hi = self._view.mapToScene(QPoint(vp.right(), 0)).x()
        else:
            c_lo = self._view.mapToScene(QPoint(0, scene._label_width)).y()
            c_hi = self._view.mapToScene(QPoint(0, vp.bottom())).y()
        ns_a = scene.scene_to_ns(c_lo)
        ns_b = scene.scene_to_ns(c_hi)
        ns_lo = max(self._trace.time_min, min(ns_a, ns_b))
        ns_hi = min(self._trace.time_max, max(ns_a, ns_b))
        if ns_hi <= ns_lo:
            ns_hi = min(self._trace.time_max, ns_lo + 1)
        return ns_lo, ns_hi

    def _time_ns_at_pos(self, pos) -> Optional[int]:
        scene = self._view._scene
        if self._trace is None or scene is None:
            return None
        if not (hasattr(scene, '_timescale_per_px') and hasattr(scene, '_label_width')):
            return None
        axis_px = pos.x()
        axis_start = scene._label_width
        if scene._timescale_per_px <= 0 or axis_px < axis_start:
            return None
        if axis_px >= self._plot_right_x():
            return None
        ns_lo, ns_hi = self._visible_time_ns_range(scene)
        span_px = self._plot_axis_span(axis_start)
        frac = (axis_px - axis_start) / span_px
        ns = int(ns_lo + frac * (ns_hi - ns_lo))
        return max(self._trace.time_min, min(self._trace.time_max, ns))

    def _time_overlay_x(self, ns: int, scene, ns_lo: int, ns_hi: int) -> int:
        lw = scene._label_width
        span = max(1, ns_hi - ns_lo)
        frac = (ns - ns_lo) / span
        return int(lw + frac * self._plot_axis_span(lw))

    def _draw_time_overlay_line(self, painter: QPainter, scene, x: int,
                                title_h: int, width_limit: int, color: QColor,
                                dashed: bool = False, width: float = 1.0) -> None:
        pen = QPen(color, width, Qt.DashLine if dashed else Qt.SolidLine)
        if dashed and pen.style() == Qt.DashLine:
            pen.setDashPattern([3, 3])
        painter.setPen(pen)
        if scene._label_width <= x < width_limit:
            painter.drawLine(x, title_h, x, self.height())

    # ------------------------------------------------------------------
    # Mouse - click label strip (core view) to collapse / expand
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        scene = self._view._scene
        if not scene or not hasattr(scene, '_label_width'):
            super().mousePressEvent(event)
            return
        if event.button() == Qt.LeftButton and self._trace and self._view_mode == "core":
            if event.x() < scene._label_width:
                _TITLE_H = 22
                ry = _TITLE_H
                for kind, key, _, _ in self._get_rows():
                    rh = self._row_effective_h(kind, key)
                    if ry <= event.y() < ry + rh:
                        self.set_core_expanded(key, key in self._collapsed_cores)
                        event.accept()
                        return
                    ry += rh + CPU_LOAD_ROW_GAP
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        scene = self._view._scene
        if self._trace is None or scene is None:
            super().mouseMoveEvent(event)
            return
        hover_ns = self._time_ns_at_pos(event.pos())
        if hover_ns is None:
            self._hover_y = -1
            scene.clear_hover_line()
        else:
            self._hover_y = event.y()
            scene._hover_ns = hover_ns
            scene._draw_hover_line()
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        scene = self._view._scene
        if scene is not None:
            self._hover_y = -1
            scene.clear_hover_line()
        super().leaveEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        self._handle_wheel(event)

    def _graph_pos_from(self, pos: QPoint, source: QWidget) -> QPoint:
        scroll = self._scroll_area
        if scroll is not None and source is scroll.viewport():
            return self.mapFrom(scroll.viewport(), pos)
        if scroll is not None and source is scroll:
            return self.mapFrom(scroll, pos)
        return pos

    def _handle_wheel(self, event, graph_pos: Optional[QPoint] = None,
                      source: Optional[QWidget] = None) -> None:
        scene = self._view._scene
        if self._trace is None or scene is None:
            if source is None:
                super().wheelEvent(event)
            return

        pos = graph_pos
        if pos is None:
            pos = (event.position().toPoint()
                   if hasattr(event, "position") else event.pos())
        if source is not None:
            pos = self._graph_pos_from(pos, source)

        mods = event.modifiers()
        zoom_mod = Qt.ControlModifier | Qt.MetaModifier
        if mods & zoom_mod:
            angle = event.angleDelta().y()
            if angle == 0:
                event.accept()
                return
            factor = 1.15 if angle > 0 else 1 / 1.15
            global_pos = self.mapToGlobal(pos)
            anchor = self._view.mapFromGlobal(global_pos)
            self._view._fit_mode = False
            self._view._zoom_accum *= factor
            if self._view._zoom_anchor_pos is None:
                self._view._zoom_anchor_pos = anchor
            self._view._zoom_timer.start()
            event.accept()
            return

        dy = event.angleDelta().y()
        dx = event.angleDelta().x()
        scroll = self._scroll_area
        if (scroll is not None and dy != 0
                and not (mods & Qt.ShiftModifier)
                and abs(dy) >= abs(dx)):
            vp = scroll.viewport()
            if self.height() > vp.height():
                vsb = scroll.verticalScrollBar()
                vsb.setValue(vsb.value() - dy)
                event.accept()
                return

        hsb = self._view.horizontalScrollBar()
        vsb = self._view.verticalScrollBar()
        if mods & Qt.ShiftModifier:
            if dy != 0:
                hsb.setValue(hsb.value() - dy)
        else:
            if dx != 0:
                hsb.setValue(hsb.value() - dx)
            if dy != 0:
                vsb.setValue(vsb.value() - dy)
        event.accept()

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        dark = self._is_dark
        bg   = QColor("#1E1E1E") if dark else QColor("#F5F5F5")
        w    = self.width()
        h    = self.height()

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.fillRect(0, 0, w, h, bg)

        scene = self._view._scene
        if self._trace is None or scene is None:
            return
        if not (hasattr(scene, '_timescale_per_px') and hasattr(scene, '_label_width')):
            return

        tpp    = scene._timescale_per_px
        lw     = scene._label_width
        t_min  = self._trace.time_min
        t_max  = self._trace.time_max
        n      = self._NUM_BINS
        bin_w  = self._bin_w_ns
        if tpp <= 0:
            return

        rows = self._get_rows()
        plot_right = self._plot_right_x()

        sepc = QColor("#444444") if dark else QColor("#AAAAAA")
        txtc = QColor("#AAAAAA") if dark else QColor("#444444")
        grdc = QColor("#2E2E2E") if dark else QColor("#D0D0D0")

        vis_ns_lo, vis_ns_hi = self._visible_time_ns_range(scene)
        vis_span = max(1, vis_ns_hi - vis_ns_lo)
        cursor_rng = self._cursor_range_ns(scene)
        scale = self._trace.time_scale

        # Pre-compute pixel->bin mapping once (reused for every row)
        axis_span = self._plot_axis_span(lw)
        sx_to_bi: Dict[int, int] = {}
        for sx in range(lw, min(w, plot_right)):
            frac = (sx - lw) / axis_span
            t = vis_ns_lo + frac * vis_span
            if t_min <= t <= t_max:
                sx_to_bi[sx] = min(n - 1, max(0, int((t - t_min) / bin_w)))

        _TITLE_H  = 22
        sf_title  = QFont(); sf_title.setPointSize(self._font_size)
        sf_norm   = QFont(); sf_norm.setPointSize(self._font_size)
        sf_small  = QFont(); sf_small.setPointSize(max(6, self._font_size - 1))
        sf_pct    = QFont(); sf_pct.setPointSize(max(5, self._font_size - 3))
        pct_muted = QColor("#555555") if dark else QColor("#AAAAAA")
        white_col = QColor("#FFFFFF") if dark else QColor("#111111")
        green_col = QColor("#4CAF50")

        # -- Title bar (same bg as rows) --------------------------------
        p.setFont(sf_title)
        p.setPen(txtc)
        p.drawText(QRect(4, 0, lw - 6, _TITLE_H), Qt.AlignVCenter | Qt.AlignLeft, "CPU LOAD")
        p.setPen(QPen(sepc, 1))
        p.drawLine(0, _TITLE_H, w, _TITLE_H)

        ry = _TITLE_H
        for kind, key, lbl_text, color in rows:
            rh = self._row_effective_h(kind, key)
            if ry >= h:
                break
            effective_h = min(rh, h - ry)
            collapsed   = (kind == "core" and key in self._collapsed_cores)
            bins_for_pct = self._bins_for_row(kind, key)
            vis_avg = self._avg_bins_in_ns_range(bins_for_pct, vis_ns_lo, vis_ns_hi)
            pct_text = f"{vis_avg * 100:.0f}%"
            if cursor_rng is not None:
                cr_avg = self._avg_bins_in_ns_range(
                    bins_for_pct, cursor_rng[0], cursor_rng[1])
                pct_text = f"{pct_text} · C:{cr_avg * 100:.0f}%"
            indicator   = "▶" if collapsed else "▼"

            # -- Label: white triangle -> coloured circle -> white name -> green % -
            dot_r  = min(5, effective_h // 4)
            dot_cy = ry + effective_h // 2

            # 1. Triangle (white)
            p.setFont(sf_small if collapsed else sf_norm)
            p.setPen(white_col)
            p.drawText(QRect(2, ry, 14, effective_h), Qt.AlignVCenter | Qt.AlignLeft, indicator)

            # 2. Coloured circle
            dot_cx = 20 + dot_r
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(color))
            p.drawEllipse(dot_cx - dot_r, dot_cy - dot_r, dot_r * 2, dot_r * 2)
            p.setRenderHint(QPainter.Antialiasing, False)

            # 3. Core name (white)
            name_x = dot_cx + dot_r + 4
            p.setPen(white_col)
            p.drawText(QRect(name_x, ry, lw - name_x - 72, effective_h), Qt.AlignVCenter | Qt.AlignLeft, lbl_text)

            # 4. Percentage (green) — visible-window avg; · C:… when 2+ cursors
            p.setPen(green_col)
            p.drawText(QRect(lw - 72, ry, 68, effective_h), Qt.AlignVCenter | Qt.AlignRight, pct_text)

            if not collapsed:
                # Cursor-range shading (behind bars)
                if cursor_rng is not None:
                    cr_lo, cr_hi = cursor_rng
                    shade_lo = max(vis_ns_lo, cr_lo)
                    shade_hi = min(vis_ns_hi, cr_hi)
                    if shade_hi > shade_lo:
                        sx0 = self._time_overlay_x(shade_lo, scene, vis_ns_lo, vis_ns_hi)
                        sx1 = self._time_overlay_x(shade_hi, scene, vis_ns_lo, vis_ns_hi)
                        if sx1 > sx0:
                            shade = QColor(68, 153, 255, 38) if dark else QColor(42, 111, 178, 42)
                            p.fillRect(sx0, ry + 1, sx1 - sx0, effective_h - 2, shade)

                # Grid lines at 25 / 50 / 75 / 100 % with labels
                # "0" at bottom; "100" omitted (would overflow above the row)
                p.setFont(sf_pct)
                p.setPen(pct_muted)
                p.drawText(QRect(lw + 3, ry + effective_h - 12, 28, 12),
                           Qt.AlignLeft | Qt.AlignBottom, "0")
                for pct in (0.25, 0.5, 0.75, 1.0):
                    gy = ry + effective_h - 1 - int(pct * effective_h)
                    p.setPen(QPen(grdc, 1, Qt.DotLine))
                    p.drawLine(lw + 1, gy, plot_right, gy)
                    if pct < 1.0:   # skip "100" - would overflow into row above
                        p.setPen(pct_muted)
                        p.drawText(QRect(lw + 3, gy - 12, 28, 12),
                                   Qt.AlignLeft | Qt.AlignBottom, str(int(pct * 100)))

                # Load bars
                bins = self._bins_for_row(kind, key)
                if bins:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QBrush(color))
                    for sx, bi in sx_to_bi.items():
                        load = bins[bi]
                        if load <= 0.001:
                            continue
                        bh = max(1, int(load * effective_h))
                        p.drawRect(sx, ry + effective_h - bh, 1, bh)

            # Row separator
            p.setPen(QPen(sepc, 1))
            p.drawLine(0, ry + effective_h, w, ry + effective_h)

            ry += rh + CPU_LOAD_ROW_GAP

        # -- Overlay: bookmarks & annotations -------------------------
        if hasattr(scene, '_mark_data') and tpp > 0:
            for m_ns, _m_lbl, m_color_hex, m_kind, _m_id in scene._mark_data:
                sx = self._time_overlay_x(m_ns, scene, vis_ns_lo, vis_ns_hi)
                col = QColor(m_color_hex)
                self._draw_time_overlay_line(
                    p, scene, sx, _TITLE_H, plot_right, col,
                    dashed=(m_kind != "bookmark"),
                    width=1.2 if m_kind == "bookmark" else 1.0,
                )

        # -- Overlay: placed cursors ------------------------------------
        if hasattr(scene, '_cursor_times') and tpp > 0:
            cursor_palette = _cursor_colors(dark)
            for c_idx, c_ns in enumerate(scene._cursor_times):
                sx = self._time_overlay_x(c_ns, scene, vis_ns_lo, vis_ns_hi)
                cur_col = QColor(cursor_palette[c_idx % len(cursor_palette)])
                self._draw_time_overlay_line(
                    p, scene, sx, _TITLE_H, plot_right, cur_col,
                    dashed=True, width=1.2,
                )

        # -- Overlay: hover cursor + per-row load badges -------------------
        hover_ns = getattr(scene, '_hover_ns', None)
        hover_row = self._row_at_y(self._hover_y) if self._hover_y >= 0 else None
        if hover_ns is not None and tpp > 0:
            sx = self._time_overlay_x(hover_ns, scene, vis_ns_lo, vis_ns_hi)
            hov_col = (QColor(255, 255, 255, 80) if dark
                       else QColor(0, 102, 204, 200))
            self._draw_time_overlay_line(
                p, scene, sx, _TITLE_H, plot_right, hov_col,
                dashed=True, width=1.0,
            )
            ry_h = _TITLE_H
            for kind, key, _lbl_text, _color in rows:
                rh = self._row_effective_h(kind, key)
                collapsed = (kind == "core" and key in self._collapsed_cores)
                if not collapsed and lw <= sx < plot_right:
                    bins_h = self._bins_for_row(kind, key)
                    load = self._load_at_ns(bins_h, hover_ns)
                    load_pct = f"{load * 100:.0f}%"
                    is_primary = (hover_row is not None
                                  and hover_row[0] == kind and hover_row[1] == key)
                    if is_primary:
                        badge = (f"{load_pct} · "
                                 f"{_format_time(hover_ns, scale)}")
                    else:
                        badge = load_pct
                    self._draw_load_badge(p, sx, ry_h, badge, dark, full=is_primary)
                ry_h += rh + CPU_LOAD_ROW_GAP

        # Label column separator (full height)
        p.setPen(QPen(sepc, 1))
        p.drawLine(lw, 0, lw, h)
        if w > plot_right:
            p.fillRect(plot_right, 0, w - plot_right, h, bg)

        p.end()

def _dialog_guard(fn):
    """Decorator: prevents a dialog-opening method from being entered while it
    is already running (e.g. due to spurious double-trigger on Linux/X11).
    The guard is held for the entire duration of the modal call via try/finally,
    so any re-entrant invocation that arrives while the dialog is open is
    silently dropped.
    """
    _attr = '_dguard_' + fn.__name__

    def _wrapper(self, *args, **kwargs):
        if getattr(self, _attr, False):
            return
        setattr(self, _attr, True)
        try:
            return fn(self, *args, **kwargs)
        finally:
            setattr(self, _attr, False)

    _wrapper.__name__ = fn.__name__
    _wrapper.__doc__  = fn.__doc__
    return _wrapper

class _LeftTabStyle(QProxyStyle):
    """Force left tab-bar alignment (ignored by the macOS native QStyle)."""

    def styleHint(self, hint, option=None, widget=None, returnData=None):  # noqa: N802
        if hint == QStyle.SH_TabBar_Alignment:
            return int(Qt.AlignLeft)
        return super().styleHint(hint, option, widget, returnData)

class _LeftAlignedTabBar(QTabBar):
    """Tab bar that stays left-aligned (macOS native style centers tabs by default)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setExpanding(False)
        if sys.platform == "darwin":
            base = QStyleFactory.create("Fusion") or QApplication.style()
            self.setStyle(_LeftTabStyle(base))

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.setExpanding(False)

class _TraceTab:
    """One open trace file: timeline, CPU load graph, and per-tab marks/find state."""

    __slots__ = (
        "path", "trace", "view", "cpu_load_graph", "cpu_load_scroll", "cpu_splitter",
        "bookmarks", "annotations", "mark_next_id",
        "find_hits", "find_hit_idx", "find_marker_ns",
        "undo_stack", "redo_stack",
        "plot_mk", "plot_kind", "plot_preemptor", "plot_open",
    )

    def __init__(self, path: str, trace: "BtfTrace", win: "MainWindow") -> None:
        self.path = path
        self.trace = trace
        self.bookmarks: List[TraceBookmark] = []
        self.annotations: List[TraceAnnotation] = []
        self.mark_next_id = 1
        self.find_hits: List[int] = []
        self.find_hit_idx = -1
        self.find_marker_ns: Optional[int] = None
        self.undo_stack: list = []
        self.redo_stack: list = []
        self.plot_mk: Optional[str] = None
        self.plot_kind: Optional[str] = None
        self.plot_preemptor: Optional[str] = None
        self.plot_open: bool = False

        self.view = TimelineView(win)
        win._wire_timeline_view(self.view)

        self.cpu_load_graph = _CpuLoadGraph(self.view)
        self.cpu_load_graph.set_dark(win._is_dark)
        win._wire_cpu_load_graph(self.view, self.cpu_load_graph)

        self.cpu_load_scroll = QScrollArea()
        win._setup_cpu_load_scroll(self.cpu_load_scroll, self.cpu_load_graph)

        self.cpu_splitter = QSplitter(Qt.Vertical)
        self.cpu_splitter.addWidget(self.view)
        self.cpu_splitter.addWidget(self.cpu_load_scroll)
        self.cpu_splitter.setStretchFactor(0, 1)
        self.cpu_splitter.setStretchFactor(1, 0)
        self.cpu_splitter.setSizes([600, CPU_LOAD_ROW_H])
        self.cpu_splitter.setHandleWidth(6)
        self.cpu_splitter.setCollapsible(0, False)
        self.cpu_splitter.setCollapsible(1, False)
        self.cpu_splitter.splitterMoved.connect(win._on_cpu_splitter_moved)
        if not win._show_cpu_load:
            self.cpu_load_scroll.hide()

class MainWindow(QMainWindow):

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self):
        super().__init__()
        self._tabs: List[_TraceTab] = []
        self._previous_tab_index: int = -1
        self._tab_switch_guard: bool = False
        self._bound_scene = None
        self._legend_cancel_fn = None
        self._parse_thread: Optional[_ParseThread] = None
        self._load_in_progress: bool = False
        self._progress_dialog: Optional[QProgressDialog] = None
        self._session_restore_queue: List[str] = []
        self._session_restore_active_idx: int = -1
        self._settings = _RcSettings()

        # -- Runtime state for settings managed via _SettingsDialog ----------
        self._show_sti:              bool  = True
        self._show_grid:             bool  = True
        self._show_legend:           bool  = True
        self._show_stats:            bool  = True
        self._show_cpu_load:         bool  = True
        self._cpu_splitter_user_sized: bool = False
        self._cpu_splitter_bottom_h: Optional[int] = None
        self._show_marks:            bool  = True
        self._font_size_val:         int   = FONT_SIZE
        self._ui_font_size_val:      int   = UI_FONT_SIZE
        self._max_cursors_val:       int   = _DEFAULT_MAX_CURSORS
        self._label_width_val:       int   = LABEL_WIDTH
        self._row_height_val:        int   = ROW_HEIGHT
        self._row_gap_val:            int   = ROW_GAP
        self._sti_row_h_val:          int   = STI_ROW_H
        self._sti_waveform_h_val:     int   = STI_WAVEFORM_H
        self._sti_line_style_val:     str   = STI_LINE_STYLE
        self._timescale_per_px_default_val:  float = _TIMESCALE_PER_PX_DEFAULT
        self._hover_highlight_val:    bool  = _HOVER_HIGHLIGHT_ENABLED
        self._vert_label_pixmap_val:  bool  = _RENDER_RUNTIME.vertical_label_use_pixmap
        self._cpu_load_row_h_val:     int   = CPU_LOAD_ROW_H
        self._colorblind_val:         bool  = False
        self._bookmarks: List[TraceBookmark] = []
        self._annotations: List[TraceAnnotation] = []
        self._mark_next_id: int = 1
        self._find_hits: List[int] = []
        self._find_hit_idx: int = -1
        self._find_marker_ns: Optional[int] = None
        self._find_marker_items: List[QGraphicsItem] = []
        self._heatmap_dlg: Optional[_MigrationHeatmapDialog] = None
        self._heatmap_view_snapshot: Optional[dict] = None
        self._defer_stats_refresh: bool = False
        self._tb_icon_actions: list = []   # (QAction, icon_path_data) for theme-aware icons

        self.setWindowTitle("RTOS BTF Viewer")
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)

        # Apply saved theme BEFORE building the UI (affects the Qt stylesheet).
        self._is_dark = (self._settings.get("view", "theme", "dark") == "dark")
        self._apply_theme(self._is_dark)

        self._build_ui()
        self._build_menus()
        self._build_toolbar()
        self._build_status_bar()
        # Re-apply the selected theme now that all widgets/docks exist.
        self._apply_theme(self._is_dark)
        self._view_mode = "task"

        _tab_fwd = QShortcut(QKeySequence("Ctrl+Tab"), self)
        _tab_fwd.setContext(Qt.WidgetWithChildrenShortcut)
        _tab_fwd.activated.connect(lambda: self._cycle_trace_tab(True))
        _tab_bwd = QShortcut(QKeySequence("Ctrl+Shift+Tab"), self)
        _tab_bwd.setContext(Qt.WidgetWithChildrenShortcut)
        _tab_bwd.activated.connect(lambda: self._cycle_trace_tab(False))

        # Restore all persisted settings (geometry, zoom, orientation, ...).
        self._restore_settings()

    # ------------------------------------------------------------------
    # Multi-tab trace access
    # ------------------------------------------------------------------

    @property
    def _active_tab(self) -> Optional[_TraceTab]:
        if not hasattr(self, "_tab_widget"):
            return None
        idx = self._tab_widget.currentIndex()
        if 0 <= idx < len(self._tabs):
            return self._tabs[idx]
        return None

    @property
    def _view(self) -> TimelineView:
        tab = self._active_tab
        if tab is not None:
            return tab.view
        return self._settings_view

    @property
    def _trace(self) -> Optional[BtfTrace]:
        tab = self._active_tab
        return tab.trace if tab is not None else None

    @property
    def _current_file(self) -> str:
        tab = self._active_tab
        return tab.path if tab is not None else ""

    @property
    def _cpu_load_graph(self) -> _CpuLoadGraph:
        tab = self._active_tab
        if tab is not None:
            return tab.cpu_load_graph
        return self._settings_cpu_graph

    @property
    def _cpu_load_scroll(self) -> QScrollArea:
        tab = self._active_tab
        if tab is not None:
            return tab.cpu_load_scroll
        return self._settings_cpu_scroll

    @property
    def _cpu_splitter(self) -> QSplitter:
        tab = self._active_tab
        if tab is not None:
            return tab.cpu_splitter
        raise RuntimeError("No active trace tab")

    def _iter_tab_views(self):
        for tab in self._tabs:
            yield tab.view
        if hasattr(self, "_settings_view"):
            yield self._settings_view

    def _find_tab_index(self, path: str) -> int:
        norm = os.path.abspath(os.path.expanduser(path))
        for i, tab in enumerate(self._tabs):
            if os.path.abspath(tab.path) == norm:
                return i
        return -1

    def _wire_timeline_view(self, view: TimelineView) -> None:
        view.zoom_changed.connect(lambda tpp, v=view: self._on_zoom_changed(tpp, v))
        view.cursors_changed.connect(lambda times, v=view: self._on_cursors_changed(times, v))
        view.mark_moved.connect(self._on_mark_moved)
        view.mark_dragging.connect(self._on_mark_dragging)
        view.bookmark_requested.connect(self._add_bookmark_at_ns)
        view.annotation_requested.connect(self._add_annotation_at_ns)
        view.clear_bookmarks_requested.connect(self._clear_all_bookmarks)
        view.clear_annotations_requested.connect(self._clear_all_annotations)
        view.pre_change.connect(self._push_undo_snapshot)
        view.horizontalScrollBar().valueChanged.connect(
            lambda _val, v=view: self._on_view_scrolled(v))
        view.verticalScrollBar().valueChanged.connect(
            lambda _val, v=view: self._on_view_scrolled(v))

    def _setup_cpu_load_scroll(self, scroll: QScrollArea, graph: _CpuLoadGraph) -> None:
        """Wire CPU load graph into a scroll area with vertical scroll when cores overflow."""
        scroll.setWidget(graph)
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        graph._scroll_area = scroll

        class _CpuLoadScrollSync(QObject):
            def __init__(self, g: _CpuLoadGraph, v: "TimelineView", sa: QScrollArea) -> None:
                super().__init__(g)
                self._graph = g
                self._view = v
                self._scroll = sa

            def eventFilter(self, obj, event):  # noqa: N802
                if event.type() == QEvent.Resize:
                    self._graph._sync_scroll_size()
                    return False
                if event.type() == QEvent.Wheel:
                    pos = (event.position().toPoint()
                           if hasattr(event, "position") else event.pos())
                    self._graph._handle_wheel(event, pos, obj)
                    return True
                if event.type() == QEvent.NativeGesture:
                    _ZOOM_GESTURE = getattr(Qt, "ZoomNativeGesture", 3)
                    try:
                        if int(event.gestureType()) == int(_ZOOM_GESTURE):
                            pt = event.pos()
                            global_pos = self._scroll.viewport().mapToGlobal(pt)
                            anchor = self._view.mapFromGlobal(global_pos)
                            factor = 1.0 + event.value()
                            if factor > 0.1:
                                self._view._fit_mode = False
                                self._view._do_zoom(factor, anchor)
                            return True
                    except AttributeError:
                        pass
                return False

        filt = _CpuLoadScrollSync(graph, graph._view, scroll)
        graph._scroll_sync_filter = filt
        scroll.viewport().installEventFilter(filt)
        scroll.installEventFilter(filt)
        graph._sync_scroll_size()
        self._sync_cpu_load_scroll_theme(scroll, graph, self._is_dark)

    def _wire_cpu_load_graph(self, view: TimelineView, graph: _CpuLoadGraph) -> None:
        def _repaint_cpu_graph(*_args) -> None:
            graph.update()

        view.zoom_changed.connect(_repaint_cpu_graph)
        view.horizontalScrollBar().valueChanged.connect(_repaint_cpu_graph)
        view.verticalScrollBar().valueChanged.connect(_repaint_cpu_graph)
        view.verticalScrollBar().rangeChanged.connect(_repaint_cpu_graph)
        view._scene.highlight_changed.connect(graph.set_task)
        view._scene.hover_changed.connect(_repaint_cpu_graph)
        view._scene.marks_changed.connect(_repaint_cpu_graph)
        view.cursors_changed.connect(lambda _: _repaint_cpu_graph())

        class _CpuGraphViewportSync(QObject):
            def eventFilter(self, obj, event):
                if event.type() == QEvent.Resize:
                    graph.update()
                return False

        filt = _CpuGraphViewportSync(graph)
        graph._viewport_sync_filter = filt
        view.viewport().installEventFilter(filt)

    def _sync_timeline_view_theme(self, view: TimelineView, is_dark: bool) -> None:
        """Keep QGraphicsView and its viewport background in sync with the app theme."""
        c = self._theme_tokens(is_dark)
        bg = QColor(c["win_bg"])
        view.setBackgroundBrush(QBrush(bg))
        for w in (view, view.viewport()):
            pal = w.palette()
            pal.setColor(QPalette.Window, bg)
            pal.setColor(QPalette.Base, bg)
            w.setPalette(pal)
            w.setAutoFillBackground(True)
        view.viewport().setStyleSheet(
            f"background-color: {c['win_bg']}; border: none;"
        )

    def _sync_cpu_load_scroll_theme(
        self, scroll: QScrollArea, graph: _CpuLoadGraph, is_dark: bool,
    ) -> None:
        """Keep CPU load scroll area and graph widget backgrounds in sync with the theme."""
        c = self._theme_tokens(is_dark)
        bg = QColor(c["scroll_bg"])
        graph.set_dark(is_dark)
        scroll.setObjectName("cpu_load_scroll")
        scroll.viewport().setObjectName("cpu_load_scroll_viewport")
        scroll.viewport().setAutoFillBackground(True)
        graph.setAutoFillBackground(True)
        for w in (scroll, scroll.viewport(), graph):
            pal = w.palette()
            pal.setColor(QPalette.Window, bg)
            pal.setColor(QPalette.Base, bg)
            w.setPalette(pal)
        scroll.setStyleSheet(
            f"QScrollArea#cpu_load_scroll {{ background:{c['scroll_bg']}; border:none; }}"
            f"QWidget#cpu_load_scroll_viewport {{ background:{c['scroll_bg']}; }}"
        )
        graph.update()

    def _sync_trace_tab_widget_theme(self, is_dark: bool) -> None:
        """Keep trace-file tab bar and pane backgrounds in sync with the app theme."""
        if not hasattr(self, "_tab_widget"):
            return
        c = self._theme_tokens(is_dark)
        win_bg = QColor(c["win_bg"])
        strip_bg = QColor(c["mid"])
        _ui_fs = f"{getattr(self, '_ui_font_size_val', UI_FONT_SIZE)}pt"

        tw = self._tab_widget
        tb = tw.tabBar()
        tb.setExpanding(False)
        if sys.platform == "darwin":
            base = QStyleFactory.create("Fusion") or QApplication.style()
            tb.setStyle(_LeftTabStyle(base))
            tw.setStyle(_LeftTabStyle(base))
        tw.setObjectName("trace_tab_widget")
        tb.setObjectName("trace_tab_bar")

        for w in (tw, tb):
            pal = w.palette()
            pal.setColor(QPalette.Window, win_bg)
            pal.setColor(QPalette.Base, win_bg)
            pal.setColor(QPalette.Button, QColor(c["tab_bg"]))
            pal.setColor(QPalette.ButtonText, QColor(c["tab_fg"]))
            w.setPalette(pal)
            w.setAutoFillBackground(True)

        for attr in ("_central_stack", "_welcome_page"):
            host = getattr(self, attr, None)
            if host is None:
                continue
            pal = host.palette()
            pal.setColor(QPalette.Window, win_bg)
            pal.setColor(QPalette.Base, win_bg)
            host.setPalette(pal)
            host.setAutoFillBackground(True)

        tw.setStyleSheet(
            f"QTabWidget#trace_tab_widget {{ background:{c['win_bg']}; }}"
            f"QTabWidget#trace_tab_widget::tab-bar {{ alignment: left; }}"
            f"QTabWidget#trace_tab_widget::pane {{ background:{c['win_bg']}; "
            f"border:1px solid {c['sep']}; top:-1px; }}"
            f"QTabWidget#trace_tab_widget QTabBar#trace_tab_bar {{ "
            f"background:{c['mid']}; border-bottom:1px solid {c['sep']}; }}"
            f"QTabWidget#trace_tab_widget QTabBar#trace_tab_bar::tab {{ "
            f"background:{c['tab_bg']}; color:{c['tab_fg']}; padding:4px 12px; "
            f"border:none; border-bottom:2px solid transparent; font-size:{_ui_fs}; }}"
            f"QTabWidget#trace_tab_widget QTabBar#trace_tab_bar::tab:selected {{ "
            f"background:{c['tab_sel_bg']}; color:{c['tab_sel_fg']}; "
            f"border-bottom:2px solid {c['accent']}; }}"
            f"QTabWidget#trace_tab_widget QTabBar#trace_tab_bar::tab:hover:!selected {{ "
            f"background:{c['tab_hover_bg']}; color:{c['tab_hover_fg']}; }}"
        )

    def _apply_view_settings(self, view: TimelineView) -> None:
        view.set_font_size(self._font_size_val)
        view.set_max_cursors(self._max_cursors_val)
        sc = view._scene
        sc.set_label_width(self._label_width_val)
        sc.set_row_height(self._row_height_val)
        sc.set_row_gap(self._row_gap_val)
        sc.set_timescale_per_px_default(self._timescale_per_px_default_val)
        sc.set_sti_row_h(self._sti_row_h_val)
        sc.set_sti_waveform_h(self._sti_waveform_h_val)
        sc.set_sti_line_style(self._sti_line_style_val)
        sc.set_hover_highlight(self._hover_highlight_val)
        sc.set_theme(self._is_dark, rebuild=False)
        self._sync_timeline_view_theme(view, self._is_dark)
        view.set_horizontal(self._act_horiz.isChecked() if hasattr(self, "_act_horiz") else True)
        view.set_show_sti(self._show_sti)
        view.set_show_grid(self._show_grid)
        view.set_view_mode(self._view_mode if hasattr(self, "_view_mode") else "task")

    def _sync_cpu_load_graph(self, tab: _TraceTab) -> None:
        """Align one tab's CPU load graph with global view mode and timeline state."""
        graph = tab.cpu_load_graph
        graph.set_dark(self._is_dark)
        mode = self._view_mode if hasattr(self, "_view_mode") else "task"
        graph.set_view_mode(mode)
        graph.set_row_h(self._cpu_load_row_h_val)
        trace = tab.trace
        if mode == "core" and trace and trace.core_names:
            sc = tab.view._scene
            for core in trace.core_names:
                graph.set_core_expanded(core, sc._core_expanded.get(core, True))

    def _stash_tab_state(self, tab: _TraceTab) -> None:
        tab.bookmarks = list(self._bookmarks)
        tab.annotations = list(self._annotations)
        tab.mark_next_id = self._mark_next_id
        tab.find_hits = list(self._find_hits)
        tab.find_hit_idx = self._find_hit_idx
        tab.find_marker_ns = self._find_marker_ns
        tab.undo_stack = list(self._undo_stack)
        tab.redo_stack = list(self._redo_stack)
        tab.plot_mk, tab.plot_kind, tab.plot_open, tab.plot_preemptor = (
            self._stats_panel.capture_plot_session())
        self._persist_trace_state(tab.path, tab.bookmarks, tab.annotations, tab.mark_next_id)
        self._persist_tab_view_state(tab)

    def _persist_tab_view_state(self, tab: _TraceTab) -> None:
        """Save zoom/cursor layout for one tab (keyed by trace path hash)."""
        if not tab.path or tab.trace is None:
            return
        sc = tab.view._scene
        payload = {
            "zoom": -1 if tab.view._fit_mode else sc.timescale_per_px,
            "fit_mode": bool(tab.view._fit_mode),
            "cursors": list(sc.cursor_times()),
        }
        key = self._trace_state_key(tab.path)
        self._settings.set("tab_view", key, json.dumps(payload, ensure_ascii=True), flush=False)

    def _load_tab_view_state(self, tab: _TraceTab) -> None:
        """Restore zoom/cursors saved for *tab* in btf_viewer.rc."""
        raw = self._settings.get("tab_view", self._trace_state_key(tab.path), "")
        if not raw.strip():
            tab.view.zoom_changed.emit(tab.view._scene.timescale_per_px)
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            tab.view.zoom_changed.emit(tab.view._scene.timescale_per_px)
            return
        sc = tab.view._scene
        fit_mode = bool(payload.get("fit_mode", True))
        zoom = float(payload.get("zoom", -1))
        if not fit_mode and zoom > 0:
            sc._timescale_per_px = max(sc._timescale_per_px_default, zoom)
            tab.view._fit_mode = False
            sc.rebuild()
        for ns in payload.get("cursors", []):
            try:
                sc.add_cursor(int(ns))
            except (ValueError, TypeError):
                pass
        if sc.cursor_times():
            tab.view.cursors_changed.emit(sc.cursor_times())
        tab.view.zoom_changed.emit(sc.timescale_per_px)

    def _persist_open_tabs(self) -> None:
        """Write open tab paths and active tab index to btf_viewer.rc."""
        for tab in self._tabs:
            self._persist_tab_view_state(tab)
        paths = [tab.path for tab in self._tabs]
        active_idx = self._tab_widget.currentIndex() if self._tabs else -1
        if 0 <= active_idx < len(paths):
            last_file = paths[active_idx]
        elif paths:
            last_file = paths[-1]
        else:
            last_file = ""
        last_dir = os.path.dirname(last_file) if last_file else self._settings.get(
            "files", "last_dir", os.path.expanduser("~"))
        self._settings.set_many("files", {
            "open_tabs_json": json.dumps(paths, ensure_ascii=True),
            "active_tab_index": str(max(0, active_idx)),
            "last_file": last_file,
            "last_dir": last_dir,
        }, flush=False)
        self._settings.prune_section("tab_view", 16)

    def _restore_session_tabs(self) -> None:
        """Re-open tabs saved in the previous session (called at startup)."""
        raw = self._settings.get("files", "open_tabs_json", "")
        paths: List[str] = []
        try:
            if raw.strip():
                loaded = json.loads(raw)
                if isinstance(loaded, list):
                    paths = [str(p) for p in loaded if str(p).strip()]
        except (json.JSONDecodeError, TypeError, ValueError):
            paths = []
        if not paths:
            last = self._settings.get("files", "last_file", "")
            if last and not os.path.isabs(last):
                base_dir = os.path.dirname(os.path.abspath(__file__))
                last = os.path.abspath(os.path.join(base_dir, last))
            if last:
                paths = [last]
        seen: set = set()
        unique: List[str] = []
        for p in paths:
            norm = os.path.abspath(os.path.expanduser(p))
            if norm in seen or not os.path.isfile(norm):
                continue
            seen.add(norm)
            unique.append(norm)
        if not unique:
            return
        saved_active = self._settings.get_int("files", "active_tab_index", 0)
        self._session_restore_active_idx = min(max(0, saved_active), len(unique) - 1)
        self._session_restore_queue = unique[1:]
        self._open_file(unique[0])

    def _continue_session_restore(self) -> None:
        """Load the next tab from the startup queue, then focus the saved active tab."""
        if self._session_restore_queue:
            path = self._session_restore_queue.pop(0)
            QTimer.singleShot(50, lambda p=path: self._open_file(p))
            return
        if self._session_restore_active_idx >= 0 and self._tabs:
            idx = min(self._session_restore_active_idx, len(self._tabs) - 1)
            self._tab_switch_guard = True
            try:
                self._tab_widget.setCurrentIndex(idx)
            finally:
                self._tab_switch_guard = False
            self._previous_tab_index = idx
            self._restore_tab_state(self._tabs[idx])
        self._session_restore_active_idx = -1

    def _stash_active_tab_state(self) -> None:
        tab = self._active_tab
        if tab is None:
            return
        self._stash_tab_state(tab)

    def _restore_tab_state(self, tab: _TraceTab) -> None:
        self._bookmarks = list(tab.bookmarks)
        self._annotations = list(tab.annotations)
        self._mark_next_id = tab.mark_next_id
        self._find_hits = list(tab.find_hits)
        self._find_hit_idx = tab.find_hit_idx
        self._find_marker_ns = tab.find_marker_ns
        self._undo_stack = list(tab.undo_stack)
        self._redo_stack = list(tab.redo_stack)
        self._rebuild_bookmark_list()
        self._rebuild_annotation_list()
        self._sync_panels_to_active_tab()
        self._act_undo.setEnabled(bool(self._undo_stack))
        self._act_redo.setEnabled(bool(self._redo_stack))

    def _sync_panels_to_active_tab(self) -> None:
        self._sync_heatmap_dialog_to_tab()
        tab = self._active_tab
        trace = self._trace
        if tab is None or trace is None:
            return
        self._legend.rebuild(trace, show_sti=self._show_sti)
        mks = self._view._scene._heatmap_filter_mks
        self._legend.set_heatmap_filter(
            "filtered" if mks else None, mks)
        self._sync_show_all_tasks_btn()
        self._stats_panel._ui_font_size = self._ui_font_size_val
        self._stats_panel.set_cursor_times(self._view._scene.cursor_times(), refresh_stats=False)
        self._stats_panel.rebuild(trace)
        self._cpu_load_graph.set_trace(trace)
        self._cpu_load_graph.set_font_size(self._font_size_val)
        self._sync_cpu_load_graph(tab)
        self._bind_legend_to_scene(self._view._scene)
        self._recompute_find_hits()
        self._refresh_find_marker()
        self._refresh_zoom_ui_unit()
        self._on_cursors_changed(self._view._scene.cursor_times(), self._view)
        self._sync_toolbar_to_active_tab()
        self._update_status_for_active_tab()
        self._update_tab_actions()
        if self._show_cpu_load:
            if self._cpu_splitter_user_sized:
                self._apply_saved_cpu_splitter(tab)
            else:
                self._autofit_cpu_load_height()

    def _update_status_for_active_tab(self) -> None:
        trace = self._trace
        if trace is None:
            self._status_file.setText("  No file loaded")
            self._status_file.setToolTip("")
            self.setWindowTitle("RTOS BTF Viewer")
            return
        fname = os.path.basename(self._current_file)
        ts = _format_time(trace.time_max - trace.time_min, trace.time_scale)
        n_seg = len(trace.segments)
        n_sti = len(trace.sti_events)
        self.setWindowTitle(f"RTOS BTF Viewer – {fname}")
        self._status_file.setText(f"  {fname}  |  span: {ts}")
        self._status_file.setToolTip(
            f"tasks: {len(trace.tasks)}  "
            f"segments: {n_seg}  "
            f"STI events: {n_sti}"
        )

    def _update_tab_actions(self) -> None:
        has_trace = self._trace is not None
        for act in (self._act_save_img, self._act_save_svg, self._act_copy_img):
            act.setEnabled(has_trace)
        if hasattr(self, "_act_close_tab"):
            self._act_close_tab.setEnabled(len(self._tabs) > 0)

    def _bind_legend_to_scene(self, scene) -> None:
        if self._bound_scene is scene:
            return
        self._unbind_legend_from_scene()
        self._bound_scene = scene
        self._legend_cancel_fn = lambda: scene.set_highlighted_task(None)
        self._legend.cancel_highlight.connect(self._legend_cancel_fn)
        self._legend.filter_changed.connect(scene.set_task_filter)
        scene.highlight_changed.connect(self._on_scene_highlight_for_legend)

    def _unbind_legend_from_scene(self) -> None:
        if self._bound_scene is None:
            return
        scene = self._bound_scene
        try:
            if self._legend_cancel_fn is not None:
                self._legend.cancel_highlight.disconnect(self._legend_cancel_fn)
            self._legend.filter_changed.disconnect(scene.set_task_filter)
            scene.highlight_changed.disconnect(self._on_scene_highlight_for_legend)
        except (TypeError, RuntimeError):
            pass
        self._bound_scene = None
        self._legend_cancel_fn = None

    def _on_scene_highlight_for_legend(self, task, locked: bool) -> None:
        self._legend.set_locked_task(task if locked else None)

    def _on_trace_tab_changed(self, index: int) -> None:
        if self._tab_switch_guard:
            return
        prev = self._previous_tab_index
        if 0 <= prev < len(self._tabs) and prev != index:
            self._stash_tab_state(self._tabs[prev])
            self._stats_panel.clear_plot_session()
        if 0 <= index < len(self._tabs):
            tab = self._tabs[index]
            self._restore_tab_state(tab)
            self._stats_panel.restore_plot_session(
                tab.trace, tab.plot_mk, tab.plot_kind, tab.plot_open,
                preemptor=tab.plot_preemptor)
        else:
            self._update_tab_actions()
        self._previous_tab_index = index

    def _close_trace_tab(self, index: int) -> None:
        if index < 0 or index >= len(self._tabs):
            return
        if self._active_tab is self._tabs[index]:
            self._stash_active_tab_state()
            self._stats_panel.clear_plot_session()
        tab = self._tabs[index]
        tab.view._zoom_timer.stop()
        tab.view._pan_timer.stop()
        tab.view._pan_heartbeat.stop()
        tab.view._resize_timer.stop()
        tab.cpu_load_graph.set_trace(None)
        sc = tab.view._scene
        if self._bound_scene is sc:
            self._unbind_legend_from_scene()
        sc._trace = None
        sc.clear()
        self._tab_switch_guard = True
        try:
            self._tab_widget.removeTab(index)
        finally:
            self._tab_switch_guard = False
        self._tabs.pop(index)
        tab.cpu_splitter.deleteLater()
        if not self._tabs:
            self._central_stack.setCurrentIndex(0)
            self._unbind_legend_from_scene()
            self._bookmarks = []
            self._annotations = []
            self._mark_next_id = 1
            self._find_hits = []
            self._find_hit_idx = -1
            self._find_marker_ns = None
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._rebuild_bookmark_list()
            self._rebuild_annotation_list()
            self._previous_tab_index = -1
            self._update_status_for_active_tab()
        else:
            new_idx = min(index, len(self._tabs) - 1)
            self._tab_widget.setCurrentIndex(new_idx)
            self._previous_tab_index = new_idx
        self._update_tab_actions()

    def _add_trace_tab(self, path: str, trace: BtfTrace) -> _TraceTab:
        tab = _TraceTab(path, trace, self)
        self._apply_view_settings(tab.view)
        c = self._theme_tokens(self._is_dark)
        win_bg = QColor(c["win_bg"])
        tab_pal = tab.cpu_splitter.palette()
        tab_pal.setColor(QPalette.Window, win_bg)
        tab.cpu_splitter.setPalette(tab_pal)
        tab.cpu_splitter.setAutoFillBackground(True)
        self._tabs.append(tab)
        idx = self._tab_widget.addTab(tab.cpu_splitter, os.path.basename(path))
        self._tab_widget.setTabToolTip(idx, path)
        self._central_stack.setCurrentIndex(1)
        QTimer.singleShot(0, lambda t=tab: self._apply_saved_cpu_splitter(t))
        self._tab_switch_guard = True
        try:
            self._tab_widget.setCurrentIndex(idx)
        finally:
            self._tab_switch_guard = False
        self._previous_tab_index = idx
        return tab

    # ------------------------------------------------------------------
    # Lifecycle persistence
    # ------------------------------------------------------------------

    def _apply_default_dock_sizes(self) -> None:
        """Apply startup dock dimensions.

        Called via QTimer.singleShot(0) so the window is already visible and
        the dock layout engine has completed its first pass - resizeDocks() is
        a no-op when called before the window is shown.

                Default structure:
                    - Top: Legend
                    - Bottom: tabbed pages (Statistics / Marks)

                We first set side-panel width, then split with a taller
                bottom tabbed page.
        """
        self.resizeDocks(
            [self._legend_dock, self._marks_dock],
            [520, 520],
            Qt.Horizontal,
        )
        self.resizeDocks(
            [self._legend_dock, self._marks_dock],
            [2, 5],
            Qt.Vertical,
        )
        self._stats_dock.raise_()

    def _dock_profile_key(self, width: int, height: int) -> str:
        """Build a stable per-window-size key for dock/layout persistence."""
        return f"{max(400, int(width))}x{max(300, int(height))}"

    def _collect_dock_metrics(self) -> str:
        """Return compact CSV metrics snapshot for dock sizes."""
        right_w = int(max(self._legend_dock.width(), self._marks_dock.width(), self._stats_dock.width()))
        legend_h = int(self._legend_dock.height())
        marks_h = int(self._marks_dock.height())
        stats_h = int(self._stats_dock.height())
        label_w = int(self._view._scene._label_width)
        return f"{right_w},{legend_h},{marks_h},{stats_h},{label_w}"

    def _restore_dock_metrics(self, packed: str) -> None:
        """Apply dock-size metrics persisted via _collect_dock_metrics()."""
        try:
            parts = [int(p.strip()) for p in packed.split(",")]
            if len(parts) != 5:
                return
            right_w, legend_h, marks_h, stats_h, label_w = parts
        except (ValueError, TypeError):
            return

        if right_w > 0:
            self.resizeDocks(
                [self._legend_dock, self._marks_dock],
                [right_w, right_w],
                Qt.Horizontal,
            )
        # Marks and Statistics are tabified, so they share one bottom area.
        # Use the larger of marks/stats as the intended bottom-group height.
        bottom_h = max(int(marks_h), int(stats_h))
        if legend_h > 0 and bottom_h > 0:
            self.resizeDocks(
                [self._legend_dock, self._marks_dock],
                [legend_h, bottom_h],
                Qt.Vertical,
            )
        if label_w >= 60:
            self._label_width_val = label_w
            self._view._scene.set_label_width(label_w)

    def _restore_settings(self) -> None:
        """Apply all values from btf_viewer.rc after the UI has been built."""
        s = self._settings

        # Window geometry
        w = s.get_int("window", "width",  DEFAULT_WINDOW_WIDTH)
        h = s.get_int("window", "height", DEFAULT_WINDOW_HEIGHT)
        self.resize(max(400, w), max(300, h))
        x = s.get_int("window", "x", DEFAULT_WINDOW_X)
        y = s.get_int("window", "y", DEFAULT_WINDOW_Y)
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

        # CPU load graph visibility
        saved_cpl = s.get_bool("view", "show_cpu_load", True)
        if not saved_cpl:
            self._show_cpu_load = False
            self._cpu_load_scroll.hide()
            if hasattr(self, '_tb_cpu_load_btn'):
                self._tb_cpu_load_btn.setChecked(False)

        # CPU load graph row height
        saved_clrh = s.get_int("view", "cpu_load_row_h", CPU_LOAD_ROW_H)
        if saved_clrh != CPU_LOAD_ROW_H:
            self._cpu_load_row_h_val = saved_clrh
            self._cpu_load_graph.set_row_h(saved_clrh)

        saved_cpu_bottom = s.get_int("view", "cpu_splitter_bottom_h", 0)
        if saved_cpu_bottom > 0:
            self._cpu_splitter_bottom_h = saved_cpu_bottom
            self._cpu_splitter_user_sized = s.get_bool(
                "view", "cpu_splitter_user_sized", False)
            for tab in self._tabs:
                self._apply_saved_cpu_splitter(tab)

        if hasattr(self, "_stats_panel"):
            _stats_heights: Dict[str, int] = {}
            for _sid in ("migrations", "exec", "block", "inter"):
                _default = (STATS_TABLE_MIG_DEFAULT_H if _sid == "migrations"
                            else STATS_TABLE_DEFAULT_H)
                _h = s.get_int("stats", f"table_height_{_sid}", _default)
                _stats_heights[_sid] = _h
            self._stats_panel.apply_section_table_heights(_stats_heights)

        # STI row heights and line style
        saved_srh = s.get_int("view", "sti_row_h", STI_ROW_H)
        if saved_srh != STI_ROW_H:
            self._sti_row_h_val = saved_srh
            self._view._scene.set_sti_row_h(saved_srh)
        saved_swh = s.get_int("view", "sti_waveform_h", STI_WAVEFORM_H)
        if saved_swh != STI_WAVEFORM_H:
            self._sti_waveform_h_val = saved_swh
            self._view._scene.set_sti_waveform_h(saved_swh)
        saved_sls = s.get("view", "sti_line_style", STI_LINE_STYLE)
        if saved_sls != STI_LINE_STYLE:
            self._sti_line_style_val = saved_sls
            self._view._scene.set_sti_line_style(saved_sls)

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

        # Vertical label pixmap workaround (applied after orientation so the
        # horizontal-mode guard in _set_vert_label_pixmap correctly skips the
        # rebuild when the scene is already in horizontal layout).
        # Compare against the instance field (not the mutable global) so that
        # any interim global mutation cannot cause the saved setting to be skipped.
        saved_vlp = s.get_bool("view", "vert_label_pixmap", self._vert_label_pixmap_val)
        if saved_vlp != self._vert_label_pixmap_val:
            self._set_vert_label_pixmap(saved_vlp, persist=False)

        # Colorblind-safe task palette
        saved_cb = s.get_bool("view", "colorblind_safe", False)
        if saved_cb:
            self._set_colorblind_safe(True)

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

        # Dock layout (marks/stats/legend sizes & positions).
        # dock_layout_version gates restoration: if the saved version is older
        # than the current one the saved geometry is discarded so new defaults
        # (resizeDocks in _build_ui) take effect automatically.
        _DOCK_LAYOUT_VERSION = DEFAULT_DOCK_LAYOUT_VERSION
        _profile_key = self._dock_profile_key(self.width(), self.height())
        _profile_dock = s.get("dock_profiles", _profile_key, "")
        _window_dock = s.get("window", "dock_state", "")
        _window_metrics = s.get("window", "dock_metrics", "").strip()
        # Prefer [window] values so manual .rc edits take effect immediately;
        # fall back to per-size profile values when window keys are empty.
        # Special case: if user explicitly provides window.dock_metrics but
        # clears window.dock_state, do NOT resurrect stale per-size profile
        # dock state - apply metrics-driven sizing instead.
        _saved_dock = _window_dock or ("" if (_window_metrics and not _window_dock) else _profile_dock)
        _saved_ver  = s.get("window", "dock_layout_version", "0")
        if _saved_dock and _saved_ver == _DOCK_LAYOUT_VERSION:
            self.restoreState(QByteArray.fromBase64(_saved_dock.encode("ascii")))
            # First run/profile-miss bootstrap: use window.dock_state +
            # view.label_width as defaults and seed the per-size profile.
            if not _profile_dock and _window_dock:
                s.set("dock_profiles", _profile_key, _window_dock, flush=False)
                s.set("dock_profile_label_width", _profile_key,
                      str(s.get_int("view", "label_width", LABEL_WIDTH)), flush=False)

            _saved_profile_lw = s.get_int("dock_profile_label_width", _profile_key, -1)
            if _saved_profile_lw < 60:
                _saved_profile_lw = s.get_int("view", "label_width", LABEL_WIDTH)
            if _saved_profile_lw >= 60:
                self._label_width_val = _saved_profile_lw
                self._view._scene.set_label_width(_saved_profile_lw)
            _saved_metrics = s.get("window", "dock_metrics", "") or s.get("dock_profile_metrics", _profile_key, "")
            if _saved_metrics:
                QTimer.singleShot(0, lambda m=_saved_metrics: self._restore_dock_metrics(m))
            s.flush()
        else:
            # Stale / absent saved state - clear it so it gets rewritten on exit.
            s.set_many("window", {"dock_state": "", "dock_layout_version": _DOCK_LAYOUT_VERSION})
            _saved_metrics = s.get("window", "dock_metrics", "")
            if _saved_metrics:
                # Honour explicit rc sizing even without a serialized dock_state.
                def _apply_metrics_only(m=_saved_metrics):
                    self._apply_default_dock_sizes()
                    self._restore_dock_metrics(m)
                QTimer.singleShot(0, _apply_metrics_only)
            else:
                # Apply default dock sizes after the window is shown (resizeDocks is
                # a no-op before the layout engine has run its first pass).
                QTimer.singleShot(0, self._apply_default_dock_sizes)

        # Keep the Light-theme menu label in sync when we restored a light theme.
        if not self._is_dark:
            self._act_theme.setText("Switch to &Dark Theme")

        self._refresh_zoom_ui_unit()
        if self._show_stats:
            QTimer.singleShot(0, self._stats_dock.raise_)

    def closeEvent(self, event) -> None:
        """Persist all runtime state to btf_viewer.rc on exit."""
        for tab in self._tabs:
            tab.view._zoom_timer.stop()
            tab.view._pan_timer.stop()
            tab.view._pan_heartbeat.stop()
            tab.view._resize_timer.stop()
        if hasattr(self, "_settings_view"):
            self._settings_view._zoom_timer.stop()
            self._settings_view._pan_timer.stop()
            self._settings_view._pan_heartbeat.stop()
            self._settings_view._resize_timer.stop()

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
        if not self._stop_parse_thread(wait_ms=3000):
            event.ignore()
            self._status_file.setText("  Parser is still stopping; please close again.")
            return

        self._save_current_trace_state()
        self._persist_settings()
        self._report_settings_io_failure(prefix="Settings save warning")

        # Hide the window immediately so cleanup freezes are not visible.
        self.hide()
        self._teardown_scene()

        super().closeEvent(event)

    def _report_settings_io_failure(self, prefix: str = "Settings warning") -> None:
        """Surface any deferred settings I/O failure in the status area."""
        err = self._settings.last_error()
        if not err:
            return
        self.statusBar().showMessage(f"{prefix}: {err}", 6000)
        self._settings.clear_error()

    def _persist_settings(self) -> None:
        """Write all runtime state to the config file (btf_viewer.rc)."""
        s = self._settings
        _MAX_DOCK_PROFILES = 12
        # Capture the live scene value so drag-resized label width is persisted.
        self._label_width_val = int(self._view._scene._label_width)
        # Window geometry - only save non-maximised size/position so we can
        # restore the proper normal-state geometry if the user un-maximises.
        if self.isMaximized():
            s.set("window", "maximized", "true", flush=False)
        else:
            s.set_many("window", {
                "maximized": "false",
                "width":     str(self.width()),
                "height":    str(self.height()),
                "x":         str(self.x()),
                "y":         str(self.y()),
            }, flush=False)

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
        }, flush=False)

        if self._cpu_splitter_bottom_h is not None and self._cpu_splitter_bottom_h > 0:
            s.set_many("view", {
                "cpu_splitter_bottom_h": str(self._cpu_splitter_bottom_h),
                "cpu_splitter_user_sized": str(self._cpu_splitter_user_sized).lower(),
            }, flush=False)

        if hasattr(self, "_stats_panel"):
            for _sid, _h in self._stats_panel.section_table_heights().items():
                s.set("stats", f"table_height_{_sid}", str(_h), flush=False)

        # Dock layout - serialise the full QMainWindow state (all dock sizes,
        # positions, tabbing) as a base64 string so it survives restarts.
        _DOCK_LAYOUT_VERSION = DEFAULT_DOCK_LAYOUT_VERSION
        _dock_bytes: QByteArray = self.saveState()
        _dock_b64 = bytes(_dock_bytes.toBase64()).decode("ascii")
        s.set_many("window", {
            "dock_state":          _dock_b64,
            "dock_metrics":        self._collect_dock_metrics(),
            "dock_layout_version": _DOCK_LAYOUT_VERSION,
        }, flush=False)

        # Per-window-size layout/profile persistence (dock/page geometry + left panel).
        _profile_key = self._dock_profile_key(self.width(), self.height())
        s.set("dock_profiles", _profile_key, _dock_b64, flush=False)
        s.set("dock_profile_label_width", _profile_key, str(self._label_width_val), flush=False)
        s.set("dock_profile_metrics", _profile_key, self._collect_dock_metrics(), flush=False)
        # Keep only the newest size profiles and keep both sections aligned.
        s.prune_section("dock_profiles", _MAX_DOCK_PROFILES)
        _keys = set(s._cfg.options("dock_profiles")) if s._cfg.has_section("dock_profiles") else set()
        s.align_section_keys("dock_profile_label_width", _keys)
        s.align_section_keys("dock_profile_metrics", _keys)

        # Zoom - save current ns/px so we can re-apply it the next time the
        # same file is opened.  -1 means "use fit-to-width" (no saved zoom).
        if self._view._scene._trace is not None and not self._view._fit_mode:
            s.set("zoom", "timescale_per_px", str(self._view._scene.timescale_per_px), flush=False)
        else:
            s.set("zoom", "timescale_per_px", "-1", flush=False)

        # Cursor positions - saved as space-separated ns timestamps so they are
        # restored the next time the same file is opened.
        _cursor_times = self._view._scene.cursor_times()
        s.set("cursors", "positions",
              " ".join(str(t) for t in _cursor_times) if _cursor_times else "",
              flush=False)
        self._persist_open_tabs()
        s.flush()
        self._report_settings_io_failure(prefix="Settings save warning")

    def _stop_parse_thread(self, wait_ms: int) -> bool:
        """Stop current parser thread safely; return True when fully stopped."""
        if self._parse_thread is None:
            return True
        if self._parse_thread.isRunning():
            self._parse_thread.requestInterruption()
            self._parse_thread.wait(wait_ms)
            if self._parse_thread.isRunning():
                return False
        self._disconnect_parse_signals()
        self._parse_thread = None
        return True

    def _teardown_scene(self) -> None:
        """Release all scene items and free trace data on background threads."""
        traces_to_free: List[BtfTrace] = []
        for tab in self._tabs:
            tab.cpu_load_graph.set_trace(None)
            _scene = tab.view._scene
            _scene._trace = None
            for _item, _ in _scene._frozen_items:
                if hasattr(_item, '_seg_data'):
                    _item._seg_data = []
                    _item._xs = []
                    _item._coarse_data_cache = None
                    _item._coarse_xs = None
            _scene._frozen_items = []
            _scene._frozen_top_items = []
            _scene._cursor_items = []
            _scene._hover_overlay_items = []
            _scene._hover_items = []
            _scene._hover_line_ns = None
            _scene._task_row_rects = {}
            _scene.clear()
            if tab.trace is not None:
                traces_to_free.append(tab.trace)
                tab.trace = None
        self._tabs.clear()

        # ---- 4b. Release the module-level info popup --------------------------
        # _info_popup is a frameless QLabel parented to nothing.  Freeing it
        # here prevents a C++ object-after-destruction crash during interpreter
        # shutdown when the QApplication is torn down before the GC collects it.
        global _info_popup
        if _info_popup is not None:
            _info_popup.hide()
            _info_popup.deleteLater()
            _info_popup = None

        # ---- 5. Free trace data on a background thread -----------------------
        # The trace can hold millions of TaskSegment objects; handing the last
        # reference to a non-daemon background thread lets Python's GC run
        # there instead of on the main thread.  Using daemon=False ensures the
        # thread is not killed prematurely at interpreter shutdown (a daemon
        # thread killed before it finishes would bounce the reference back to
        # the main-thread teardown, negating the benefit).
        for _trace_to_free in traces_to_free:
            def _drop(_t=_trace_to_free):
                del _t
            threading.Thread(target=_drop, daemon=False).start()

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
        self._is_dark = bool(is_dark)

        # Application-wide font (menus, toolbar, status bar).
        _ui_font_size = getattr(self, '_ui_font_size_val', UI_FONT_SIZE)
        _ui_fs = f"{_ui_font_size}pt"
        base_font = app.font()
        base_font.setPointSize(_ui_font_size)
        app.setFont(base_font)

        # macOS native combo widgets ignore inherited/stylesheet font-size;
        # force it directly on the toolbar combo if it exists already.
        combo = getattr(self, '_zoom_preset_combo', None)
        if combo is not None:
            combo.setFont(base_font)

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
            QToolBar QComboBox {{ font-size:{_ui_fs}; padding:1px 4px; min-height:0; }}
            QStatusBar  {{ background:{c['win_bg']}; color:{c['status_text']}; font-size:{_ui_fs};
                           border-top:1px solid {c['sep']}; }}
            QStatusBar QLabel {{ font-size:{_ui_fs}; color:{c['sub_text']}; }}
            QStatusBar QLabel#zoomScaleLabel {{ font-size:{_ui_fs}; color:{c['status_text']}; }}
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
            QDockWidget {{ border:1px solid {c['sep']}; }}
            QDockWidget::title {{ background:{c['dock_title_bg']}; color:{c['dock_title_fg']};
                                  padding:4px; font-size:{_ui_fs}; }}
            QMainWindow::separator {{ background:{c['sep']}; width:1px; height:1px; }}
            QPushButton {{ background:{c['mid']}; color:{c['text']};
                         border:1px solid {c['input_border']}; border-radius:3px;
                         padding:3px 10px; font-size:{_ui_fs}; }}
            QPushButton:hover   {{ background:{c['tb_hover']}; }}
            QPushButton:pressed {{ background:{c['tb_pressed']}; color:#FFFFFF; }}
            QPushButton:disabled {{ color:{c['tb_disabled']}; background:{c['mid']}; }}
            QListWidget {{ background:{c['win_base']}; color:{c['text']};
                         border:1px solid {c['input_border']}; font-size:{_ui_fs}; }}
            QListWidget::item {{ font-size:{_ui_fs}; }}
            QListWidget::item:selected {{ background:{c['accent']}; color:#FFFFFF; }}
            QListWidget::item:hover:!selected {{ background:{c['list_hover']}; }}
            QTableWidget {{ background:{c['win_base']}; color:{c['text']};
                         border:1px solid {c['input_border']}; font-size:{_ui_fs};
                         gridline-color:{c['sep']}; }}
            QTableWidget::item {{ font-size:{_ui_fs}; padding:2px 4px; }}
            QTableWidget::item:selected {{ background:{c['accent']}; color:#FFFFFF; }}
            QHeaderView::section {{ background:{c['mid']}; color:{c['text']};
                         border:none; border-bottom:1px solid {c['sep']};
                         padding:3px 6px; font-size:{_ui_fs}; }}
            QTabWidget::pane {{ background:{c['win_bg']}; border:1px solid {c['sep']}; }}
            QTabWidget {{ background:{c['win_bg']}; }}
            QTabBar {{ background:{c['mid']}; }}
            QStackedWidget {{ background:{c['win_bg']}; }}
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
            QSplitter::handle {{
                background:{c['sep']};
            }}
            QSplitter::handle:hover {{
                background:{c['accent']};
            }}
            QSplitter::handle:vertical {{
                height:6px;
            }}
            QSplitter::handle:horizontal {{
                width:6px;
            }}
        """)

        # --- Per-widget overrides not reachable via app-wide QSS ----------
        if hasattr(self, '_range_stats_label'):
            self._range_stats_label.setStyleSheet(f"color:{c['muted_text']};")
        if hasattr(self, '_find_status'):
            self._find_status.setStyleSheet(f"color:{c['muted_text']};")
        if hasattr(self, '_cur_hint'):
            self._cur_hint.setStyleSheet(f"color:{c['muted_text']}; font-size:9pt;")
        if hasattr(self, '_welcome_label'):
            self._welcome_label.setText(
                f"<h2 style='color:{c['welcome_h2']};'>RTOS BTF Viewer</h2>"
                f"<p style='color:{c['welcome_p']}; font-size:11pt;'>"
                "Drop a <b>.btf</b> file here<br>"
                "or press <b>Ctrl+O</b> to open one</p>"
            )
        if hasattr(self, '_view'):
            c = self._theme_tokens(is_dark)
            win_bg = QColor(c["win_bg"])
            for view in self._iter_tab_views():
                self._sync_timeline_view_theme(view, is_dark)
                view._scene.set_theme(is_dark, rebuild=(view._scene._trace is not None))
            for tab in self._tabs:
                tab_pal = tab.cpu_splitter.palette()
                tab_pal.setColor(QPalette.Window, win_bg)
                tab.cpu_splitter.setPalette(tab_pal)
                tab.cpu_splitter.setAutoFillBackground(True)
                self._sync_cpu_load_scroll_theme(
                    tab.cpu_load_scroll, tab.cpu_load_graph, is_dark,
                )
            if hasattr(self, "_settings_cpu_scroll") and hasattr(self, "_settings_cpu_graph"):
                self._sync_cpu_load_scroll_theme(
                    self._settings_cpu_scroll, self._settings_cpu_graph, is_dark,
                )
        self._sync_trace_tab_widget_theme(is_dark)
        if hasattr(self, '_legend'):
            self._legend.update_theme(is_dark)
        if hasattr(self, '_legend_dock') and self._legend_dock.widget() is not None:
            _legend_host = self._legend_dock.widget()
            _host_pal = _legend_host.palette()
            _host_pal.setColor(QPalette.Window, QColor(c['win_bg']))
            _host_pal.setColor(QPalette.Base, QColor(c['win_bg']))
            _legend_host.setPalette(_host_pal)
        if hasattr(self, '_stats_panel'):
            self._stats_panel.set_dark(is_dark)
        if hasattr(self, '_stats_panel'):
            self._stats_panel._ui_font_size = _ui_font_size
            if self._trace is not None:
                self._stats_panel.rebuild(self._trace)
        if hasattr(self, '_cursor_bar'):
            self._cursor_bar.update_theme(is_dark)
            if self._trace is not None:
                self._cursor_bar.rebuild(self._view._scene.cursor_times(), self._trace)
        if getattr(self, '_tb_icon_actions', None):
            _ic_color = "#CCCCCC" if is_dark else "#555555"
            for _act, _ic_path in self._tb_icon_actions:
                _act.setIcon(_svg_icon(_ic_path, _ic_color))
        if hasattr(self, '_tb_theme_btn'):
            _theme_ic = _IC_THEME_LIGHT if is_dark else _IC_THEME_DARK
            self._tb_theme_btn.setIcon(_svg_icon(_theme_ic, _ic_color))
            self._tb_theme_btn.setToolTip(
                "Switch to light theme" if is_dark else "Switch to dark theme"
            )
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
        # Hidden settings template view (used before any trace tab exists).
        self._settings_view = TimelineView(self)
        self._wire_timeline_view(self._settings_view)
        self._settings_cpu_graph = _CpuLoadGraph(self._settings_view)
        self._settings_cpu_graph.set_dark(self._is_dark)
        self._wire_cpu_load_graph(self._settings_view, self._settings_cpu_graph)
        self._settings_cpu_scroll = QScrollArea()
        self._setup_cpu_load_scroll(self._settings_cpu_scroll, self._settings_cpu_graph)
        self._settings_cpu_scroll.hide()

        # Undo / Redo stacks (cursor + mark state; synced per tab on switch)
        self._undo_stack: list = []
        self._redo_stack: list = []
        self._undo_suppress: bool = False

        self._welcome_page = QWidget()
        _wl = QVBoxLayout(self._welcome_page)
        _wl.setAlignment(Qt.AlignCenter)
        _wlbl = QLabel(
            "<h2 style='color:#888;'>RTOS BTF Viewer</h2>"
            "<p style='color:#666; font-size:11pt;'>"
            "Drop a <b>.btf</b> file here<br>"
            "or press <b>Ctrl+O</b> to open one</p>"
        )
        _wlbl.setTextFormat(Qt.RichText)
        _wlbl.setAlignment(Qt.AlignCenter)
        _wl.addWidget(_wlbl)
        self._welcome_label = _wlbl

        self._tab_widget = QTabWidget()
        self._tab_widget.setTabBar(_LeftAlignedTabBar(self._tab_widget))
        self._tab_widget.setTabsClosable(True)
        # Native document-mode tabs on macOS ignore QSS/palette theme updates.
        if sys.platform == "darwin":
            self._tab_widget.setDocumentMode(False)
            base = QStyleFactory.create("Fusion") or QApplication.style()
            self._tab_widget.setStyle(_LeftTabStyle(base))
        else:
            self._tab_widget.setDocumentMode(True)
        self._tab_widget.setMovable(True)
        self._tab_widget.tabCloseRequested.connect(self._close_trace_tab)
        self._tab_widget.currentChanged.connect(self._on_trace_tab_changed)

        self._central_stack = QStackedWidget()
        self._central_stack.addWidget(self._welcome_page)
        self._central_stack.addWidget(self._tab_widget)
        self._central_stack.setCurrentIndex(0)
        self.setCentralWidget(self._central_stack)

        # --- Legend dock (right panel) ---
        self._build_legend_dock()

        # --- Statistics dock (bottom panel) ---
        self._build_stats_dock()

        # --- Marks dock (bookmarks + annotations) ---
        marks_host = QWidget()
        marks_v = QVBoxLayout(marks_host)
        marks_v.setContentsMargins(6, 6, 6, 6)
        marks_v.setSpacing(6)
        marks_tabs = QTabWidget()

        # ---- Cursors comparison tab ----
        cur_page = QWidget()
        cur_v = QVBoxLayout(cur_page)
        cur_v.setContentsMargins(0, 0, 0, 0)
        cur_v.setSpacing(2)
        self._cursor_table = QTableWidget(0, 4)
        self._cursor_table.setHorizontalHeaderLabels(["#", "Time", "Task at cursor", "Delta to C1"])
        self._cursor_table.horizontalHeader().setStretchLastSection(True)
        self._cursor_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._cursor_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._cursor_table.verticalHeader().setVisible(False)
        self._cursor_table.setAlternatingRowColors(True)
        self._cursor_table.cellClicked.connect(self._on_cursor_table_clicked)
        cur_v.addWidget(self._cursor_table)
        self._cur_hint = QLabel("Click a row to navigate to that cursor")
        self._cur_hint.setStyleSheet("color:#999; font-size:9pt;")
        cur_v.addWidget(self._cur_hint)
        marks_tabs.addTab(cur_page, "Curs.")

        bm_page = QWidget()
        bm_v = QVBoxLayout(bm_page)
        bm_v.setContentsMargins(0, 0, 0, 0)
        bm_v.setSpacing(4)
        self._bookmark_list = QListWidget()
        self._bookmark_list.itemClicked.connect(lambda item: self._jump_to_ns(int(item.data(Qt.UserRole + 1))))
        self._bookmark_list.itemDoubleClicked.connect(lambda item: self._jump_to_ns(int(item.data(Qt.UserRole + 1))))
        self._bookmark_list.itemChanged.connect(self._on_bookmark_item_changed)
        _bm_del_key = QShortcut(QKeySequence(Qt.Key_Delete), self._bookmark_list)
        _bm_del_key.setContext(Qt.WidgetShortcut)
        _bm_del_key.activated.connect(self._delete_selected_bookmark)
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
        marks_tabs.addTab(bm_page, "Bookm.")

        an_page = QWidget()
        an_v = QVBoxLayout(an_page)
        an_v.setContentsMargins(0, 0, 0, 0)
        an_v.setSpacing(4)
        self._annotation_list = QListWidget()
        self._annotation_list.itemClicked.connect(lambda item: self._jump_to_ns(int(item.data(Qt.UserRole + 1))))
        self._annotation_list.itemDoubleClicked.connect(
            lambda item: self._edit_selected_annotation())
        _an_del_key = QShortcut(QKeySequence(Qt.Key_Delete), self._annotation_list)
        _an_del_key.setContext(Qt.WidgetShortcut)
        _an_del_key.activated.connect(self._delete_selected_annotation)
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
        marks_tabs.addTab(an_page, "Anno.")
        marks_v.addWidget(marks_tabs)
        self._range_stats_label = QLabel("Range: place two cursors to measure")
        self._range_stats_label.setStyleSheet("color:#999;")
        self._range_stats_label.setWordWrap(True)
        marks_v.addWidget(self._range_stats_label)

        marks_io_row = QHBoxLayout()
        marks_import_btn = QPushButton("v Import Marks")
        marks_import_btn.setToolTip("Load bookmarks and annotations from a CSV file")
        marks_import_btn.clicked.connect(self._import_marks_csv)
        marks_io_row.addWidget(marks_import_btn)
        marks_export_btn = QPushButton("↑ Export Marks")
        marks_export_btn.setToolTip("Save all bookmarks and annotations to a CSV file")
        marks_export_btn.clicked.connect(self._export_marks_csv)
        marks_io_row.addWidget(marks_export_btn)
        marks_session_btn = QPushButton("Session")
        marks_session_btn.setToolTip(
            "Export portable session JSON (cursors, marks, viewport — Web compatible)")
        marks_session_btn.clicked.connect(self._export_portable_session)
        marks_io_row.addWidget(marks_session_btn)
        marks_session_import_btn = QPushButton("Import Session")
        marks_session_import_btn.setToolTip("Import portable session JSON")
        marks_session_import_btn.clicked.connect(self._import_portable_session)
        marks_io_row.addWidget(marks_session_import_btn)
        marks_v.addLayout(marks_io_row)

        marks_dock = QDockWidget("Marks", self)
        marks_dock.setObjectName("dock_marks")
        marks_dock.setWidget(marks_host)
        marks_dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        marks_dock.setMinimumWidth(190)
        marks_dock.setMinimumHeight(260)  # enough to show 2 core rows + headings without scrolling
        self.addDockWidget(Qt.RightDockWidgetArea, marks_dock)
        self._marks_dock = marks_dock

        # --- Find dock ---
        find_host = QWidget()
        find_v = QVBoxLayout(find_host)
        find_v.setContentsMargins(6, 6, 6, 6)
        find_v.setSpacing(6)
        self._find_input = QLineEdit()
        self._find_input.setPlaceholderText("Find task, annotation, or migration…")
        self._find_input.textChanged.connect(self._recompute_find_hits)
        find_v.addWidget(self._find_input)
        self._find_mode_combo = QComboBox()
        self._find_mode_combo.addItems(["Contains", "Exact", "Regex", "Migrations"])
        self._find_mode_combo.setCurrentIndex(0)
        self._find_mode_combo.currentIndexChanged.connect(self._recompute_find_hits)
        find_v.addWidget(self._find_mode_combo)
        find_btns = QHBoxLayout()
        find_btns.setContentsMargins(0, 0, 0, 0)
        find_prev = QPushButton("Previous")
        find_prev.clicked.connect(self._find_prev)
        find_prev.setToolTip("Find previous match  (Shift+F3)")
        find_next = QPushButton("Next")
        find_next.clicked.connect(self._find_next)
        find_next.setToolTip("Find next match  (F3)")
        find_btns.addWidget(find_prev)
        find_btns.addWidget(find_next)
        find_v.addLayout(find_btns)
        self._find_status = QLabel("0 matches")
        self._find_status.setStyleSheet("color:#999;")
        find_v.addWidget(self._find_status)
        find_dock = QDockWidget("Find & Jump", self)
        find_dock.setObjectName("dock_find")
        find_dock.setWidget(find_host)
        find_dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        find_dock.setMinimumWidth(190)
        find_dock.setMaximumWidth(260)
        find_dock.setMinimumHeight(120)
        self.addDockWidget(Qt.RightDockWidgetArea, find_dock)
        self._find_dock = find_dock
        # Default: Legend on top, bottom as tabbed pages (Statistics / Marks).
        self.splitDockWidget(self._legend_dock, self._marks_dock, Qt.Vertical)
        self.tabifyDockWidget(self._stats_dock, self._marks_dock)
        self._stats_dock.raise_()

        # Keep Find available below the tab group (typically hidden by default).
        self.splitDockWidget(self._marks_dock, self._find_dock, Qt.Vertical)
        # Default dock sizes are applied in _restore_settings via QTimer.singleShot
        # AFTER the window is shown, where resizeDocks() is actually effective.

        # Keep runtime state in sync if the user closes a dock via its X button
        self._legend_dock.visibilityChanged.connect(
            lambda v: setattr(self, "_show_legend", v))
        self._stats_dock.visibilityChanged.connect(
            lambda v: setattr(self, "_show_stats", v))
        self._marks_dock.visibilityChanged.connect(
            lambda v: setattr(self, "_show_marks", v))
        self._find_dock.visibilityChanged.connect(self._on_find_dock_visibility_changed)

        # --- Signal wiring: legend <-> scene highlight sync (bound per active tab) ---
        self._legend.task_clicked.connect(self._on_legend_task_clicked)
        self._legend.migrated_filter_changed.connect(self._on_legend_migrated_filter)
        self._legend.clear_heatmap_filter.connect(self._clear_heatmap_task_filter)

    def _on_close_tab_action(self) -> None:
        idx = self._tab_widget.currentIndex()
        if idx >= 0:
            self._close_trace_tab(idx)

    def _build_legend_dock(self) -> None:
        """Create the legend dock and host container."""
        self._legend = _LegendWidget()
        self._legend.setMinimumWidth(180)
        legend_host = QWidget()
        legend_host.setObjectName("legend_dock_host")
        legend_host.setAutoFillBackground(True)
        legend_v = QVBoxLayout(legend_host)
        legend_v.setContentsMargins(0, 0, 0, 0)
        legend_v.setSpacing(0)
        legend_v.addWidget(self._legend)
        dock = QDockWidget("Legend", self)
        dock.setObjectName("dock_legend")
        dock.setWidget(legend_host)
        dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self._legend_dock = dock

    def _build_stats_dock(self) -> None:
        """Create the statistics dock."""
        self._stats_panel = _StatsPanel()
        self._stats_panel.task_clicked.connect(self._on_legend_task_clicked)
        self._stats_panel.segment_jump.connect(self._on_segment_jump)
        self._stats_panel.plot_point_clicked.connect(self._on_stats_plot_point_clicked)
        self._stats_panel._btn_compare_mig.clicked.connect(self._open_trace_compare)
        stats_dock = QDockWidget("Statistics", self)
        stats_dock.setObjectName("dock_statistics")
        stats_dock.setWidget(self._stats_panel)
        stats_dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.RightDockWidgetArea, stats_dock)
        self._stats_dock = stats_dock

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
        self._act_save_svg = fm.addAction("Save as &SVG…", self._on_save_svg, "Ctrl+Shift+S")
        self._act_save_svg.setEnabled(False)
        self._act_copy_img = fm.addAction("&Copy Image to Clipboard", self._on_copy_image, "Ctrl+Shift+C")
        self._act_copy_img.setEnabled(False)
        self._act_close_tab = fm.addAction("Close &Tab", self._on_close_tab_action, QKeySequence.Close)
        self._act_close_tab.setEnabled(False)
        fm.addSeparator()
        _quit_act = fm.addAction("E&xit", self.close)
        _quit_act.setShortcut(QKeySequence("Ctrl+Q"))

        # --- Edit menu (undo/redo) ---
        em = mb.addMenu("&Edit")
        self._act_undo = em.addAction("&Undo", self._cmd_undo, QKeySequence.Undo)
        self._act_undo.setEnabled(False)
        self._act_redo = em.addAction("&Redo", self._cmd_redo, QKeySequence.Redo)
        self._act_redo.setShortcut(QKeySequence("Ctrl+Y"))   # override platform default
        self._act_redo.setEnabled(False)

        # --- View menu (layout, visibility, zoom, mode, theme) ---
        vm = mb.addMenu("&View")
        self._act_horiz = vm.addAction("&Horizontal layout", lambda: self._set_orientation(True))
        self._act_vert  = vm.addAction("&Vertical layout",   lambda: self._set_orientation(False))
        self._act_horiz.setCheckable(True)
        self._act_vert.setCheckable(True)
        self._act_horiz.setChecked(True)
        vm.addSeparator()
        vm.addAction("&Zoom In",        lambda: self._view.zoom_in(),   QKeySequence.ZoomIn)
        vm.addAction("Zoom &Out",       lambda: self._view.zoom_out(),  QKeySequence.ZoomOut)
        vm.addAction("&Fit to window",  lambda: self._view.zoom_fit(),  "Ctrl+0")
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
        cm.addAction("Place cursor at pointer\tC",
                     lambda: self._view.add_cursor_at_hover_or_center(), "C")
        cm.addAction("Clear all cursors\tShift+C",
                     lambda: self._view.clear_cursors(), "Shift+C")
        cm.addSeparator()
        cm.addAction("Tip: Left-click on timeline to place cursor").setEnabled(False)
        cm.addAction("Right-click on timeline to remove nearest cursor").setEnabled(False)

        # --- Navigate menu ---
        nm = mb.addMenu("&Navigate")
        act_bookmark = nm.addAction("Add &Bookmark", self._add_bookmark_at_center, "Ctrl+B")
        act_bookmark.setShortcuts([QKeySequence("Ctrl+B"), QKeySequence("M"), QKeySequence("B")])
        act_annotation = nm.addAction("Add &Annotation…", self._prompt_annotation_at_center, "Ctrl+Shift+B")
        act_annotation.setShortcuts([QKeySequence("Ctrl+Shift+B"), QKeySequence("A")])
        nm.addAction("Clear all &Bookmarks", self._clear_all_bookmarks, "Shift+B")
        nm.addAction("Clear all Ann&otations", self._clear_all_annotations, "Shift+A")
        nm.addSeparator()
        self._act_zoom_range = nm.addAction(
            "Zoom to Cursor &Range", self._zoom_to_cursor_range, "Ctrl+R"
        )
        self._act_zoom_range.setEnabled(False)
        nm.addSeparator()
        nm.addAction("Jump to &Start", self._jump_to_trace_start, "Ctrl+Home")
        nm.addAction("Jump to En&d",   self._jump_to_trace_end,   "Ctrl+End")
        nm.addAction("Jump to &Time…", self._on_jump_to_time,     "Ctrl+G")
        nm.addSeparator()
        nm.addAction("&Find", self._focus_find, QKeySequence.Find)
        nm.addAction("Find &Next", self._find_next, QKeySequence.FindNext)
        nm.addAction("Find &Previous", self._find_prev, QKeySequence.FindPrevious)

        # --- Help menu ---
        hm = mb.addMenu("&Help")
        hm.addAction("&Keyboard && Mouse Shortcuts…", self._on_keyboard_shortcuts)
        hm.addSeparator()
        hm.addAction("&About", self._on_about)

        # Sync Show Marks / Show Find check state with dock X-button
        self._marks_dock.visibilityChanged.connect(self._act_show_marks.setChecked)
        self._find_dock.visibilityChanged.connect(self._act_show_find.setChecked)

    def _build_toolbar(self) -> None:
        tb = self.addToolBar("Main")
        tb.setObjectName("toolbar_main")
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
        _ia("Open",     self._on_open,         _IC_OPEN,     "Open BTF trace file  (Ctrl+O)")
        _ia("Save PNG", self._on_save_image,   _IC_SAVE,     "Open snapshot editor  (Ctrl+S)")
        _ia("Save SVG", self._on_save_svg,     _IC_SAVE_SVG, "Save viewport as SVG  (Ctrl+Shift+S)")
        _ia("Shot",     self._open_snapshot_editor, _IC_SHOT,
            "Capture viewport snapshot for annotation  (Ctrl+S)")
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
        _ia("Zoom In",  lambda: self._view.zoom_in(),   _IC_ZIN,  "Zoom in  (Ctrl++)")
        _ia("Zoom Out", lambda: self._view.zoom_out(),  _IC_ZOUT, "Zoom out  (Ctrl+-)")
        self._act_zoom_1to1 = _ia("1:1", lambda: self._view.zoom_1to1(), _IC_1TO1, "Zoom to 1:1 scale")
        _ia("Fit",      lambda: self._view.zoom_fit(),  _IC_FIT,  "Fit entire trace to window  (Ctrl+0)")
        self._tb_zoom_range_btn = _ia("Range", self._zoom_to_cursor_range, _IC_EXPAND,
                                      "Zoom view to fit between cursor C1 and C2  (Ctrl+R)")
        self._tb_zoom_range_btn.setEnabled(False)

        # Zoom-preset quick-pick combo (labels/values rebuilt per trace unit)
        self._zoom_presets: list = []   # populated by _rebuild_zoom_presets()
        self._zoom_preset_combo = QComboBox()
        # Use a QListView popup instead of macOS native NSMenu - the native
        # popup ignores stylesheets and looks inconsistent with the themed UI.
        self._zoom_preset_combo.setView(QListView())
        _combo_font = self._zoom_preset_combo.font()
        _combo_font.setPointSize(getattr(self, '_ui_font_size_val', UI_FONT_SIZE))
        self._zoom_preset_combo.setFont(_combo_font)
        self._zoom_preset_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._zoom_preset_combo.setMinimumWidth(100)
        self._zoom_preset_combo.setToolTip("Zoom preset — pick a fixed scale or Fit")
        self._zoom_preset_combo.activated.connect(self._on_zoom_preset_selected)
        tb.addWidget(self._zoom_preset_combo)
        self._rebuild_zoom_presets()   # populate with default ns-based labels

        tb.addSeparator()

        # --- View mode toggle (Task / Core) ---
        self._tb_task_btn = _ia("Task", lambda: self._set_view_mode("task"), _IC_TASK,
                                "Task View — one row per task, merges across cores")
        self._tb_core_btn = _ia("Core", lambda: self._set_view_mode("core"), _IC_CORE,
                                "Core View — one expandable row per CPU core")
        self._tb_task_btn.setCheckable(True)
        self._tb_core_btn.setCheckable(True)
        self._tb_task_btn.setChecked(True)
        # Task/Core are mode toggles - show short text beside icon so the active
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
        self._tb_cpu_load_btn = _ia("Load", self._toggle_cpu_load_graph, _IC_CPU_LOAD,
                                    "Show / hide CPU load graph")
        self._tb_cpu_load_btn.setCheckable(True)
        self._tb_cpu_load_btn.setChecked(True)
        _clw = tb.widgetForAction(self._tb_cpu_load_btn)
        if _clw:
            _clw.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._tb_heatmap_btn = _ia(
            "Heatmap", self._open_migration_heatmap, _IC_HEATMAP,
            "Migration heatmap — core-pair counts over time (multi-core traces only)")
        self._tb_heatmap_btn.setEnabled(False)
        self._tb_show_all_tasks_btn = _ia(
            "All tasks", self._clear_heatmap_task_filter, _IC_TASK,
            "Clear heatmap task filter and show all tasks")
        self._tb_show_all_tasks_btn.setVisible(False)
        tb.addSeparator()

        # --- STI waveform scale toggle ---
        self._tb_log2_btn = tb.addAction("Log₂", self._toggle_sti_log_scale)
        self._tb_log2_btn.setCheckable(True)
        self._tb_log2_btn.setChecked(False)
        self._tb_log2_btn.setToolTip(
            "STI waveform y-axis: toggle between linear and log₂ scale\n"
            "(only active when an STI row is expanded)")
        _l2w = tb.widgetForAction(self._tb_log2_btn)
        if _l2w:
            _l2w.setToolButtonStyle(Qt.ToolButtonTextOnly)
        tb.addSeparator()

        # --- Theme and settings ---
        self._tb_theme_btn = _ia(
            "Theme", self._toggle_theme,
            _IC_THEME_LIGHT if self._is_dark else _IC_THEME_DARK,
            "Switch to light theme" if self._is_dark else "Switch to dark theme"
        )
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

        # --- Cursor range stats (compact; shown only when >=2 cursors active) ---
        self._status_range = QLabel("")
        self._status_range.setContentsMargins(6, 0, 6, 0)
        self._status_range.setVisible(False)

        # --- RIGHT permanent zone ---

        # Quick view toggles - compact pill-style checkboxes
        self._sti_toggle_cb = QCheckBox("STI")
        self._sti_toggle_cb.setChecked(self._show_sti)
        self._sti_toggle_cb.setToolTip("Show or hide STI event markers")
        self._sti_toggle_cb.toggled.connect(self._set_show_sti)

        self._grid_toggle_cb = QCheckBox("Grid")
        self._grid_toggle_cb.setChecked(self._show_grid)
        self._grid_toggle_cb.setToolTip("Show or hide the time grid")
        self._grid_toggle_cb.toggled.connect(self._set_show_grid)

        # Zoom scale - e.g. "2.5 us/px"; brighter text via #zoomScaleLabel CSS rule
        self._zoom_scale_label = QLabel("—")
        self._zoom_scale_label.setObjectName("zoomScaleLabel")
        self._zoom_scale_label.setContentsMargins(8, 0, 2, 0)
        self._zoom_scale_label.setMinimumWidth(80)   # prevents layout jitter on unit change

        # Visible span - e.g. "*  125.4 us visible"; dimmer sub_text colour
        self._zoom_visible_label = QLabel("")
        self._zoom_visible_label.setContentsMargins(0, 0, 8, 0)

        sb.addWidget(self._status_file)
        sb.addPermanentWidget(self._cursor_bar)
        sb.addPermanentWidget(self._status_range)
        sb.addPermanentWidget(self._sti_toggle_cb)
        sb.addPermanentWidget(self._grid_toggle_cb)
        sb.addPermanentWidget(self._zoom_scale_label)
        sb.addPermanentWidget(self._zoom_visible_label)

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
        for view in self._iter_tab_views():
            view.set_horizontal(horizontal)
        self._refresh_find_marker()

    def _set_show_sti(self, show: bool, persist: bool = True) -> None:
        """Apply STI visibility and keep all STI UI controls in sync."""
        self._show_sti = bool(show)
        for view in self._iter_tab_views():
            view.set_show_sti(self._show_sti)
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
        for view in self._iter_tab_views():
            view.set_show_grid(self._show_grid)
        if hasattr(self, "_grid_toggle_cb"):
            self._grid_toggle_cb.blockSignals(True)
            self._grid_toggle_cb.setChecked(self._show_grid)
            self._grid_toggle_cb.blockSignals(False)
        if persist:
            self._settings.set("view", "show_grid", str(self._show_grid).lower())

    def _toggle_sti_log_scale(self) -> None:
        """Toggle the STI waveform y-axis between linear and log2 scale."""
        enabled = self._tb_log2_btn.isChecked()
        self._view.set_sti_log_scale(enabled)

    def _set_vert_label_pixmap(self, enabled: bool, persist: bool = True) -> None:
        """Switch the vertical-label rendering strategy and rebuild the scene."""
        self._vert_label_pixmap_val = bool(enabled)
        _set_vertical_label_pixmap_mode(self._vert_label_pixmap_val)
        # Rebuild so the new label strategy takes effect immediately.
        # Skip the rebuild if the scene is in horizontal mode - the vertical-
        # label pixmap setting has no effect there, so the rebuild is wasted.
        if not self._view._scene._horizontal:
            self._view._scene.rebuild()
        if persist:
            self._settings.set("view", "vert_label_pixmap",
                               str(self._vert_label_pixmap_val).lower())

    def _set_colorblind_safe(self, enabled: bool) -> None:
        """Switch the task colour palette to/from the Okabe-Ito colorblind-safe set."""
        self._colorblind_val = bool(enabled)
        _set_colorblind_mode(self._colorblind_val)
        if self._view._scene._trace is not None:
            self._view._scene.rebuild()
        # Also refresh legend swatches which cache colors at build time.
        if self._trace is not None:
            self._legend.rebuild(self._trace)

    def _current_time_unit(self) -> str:
        if self._trace is not None and getattr(self._trace, "time_scale", ""):
            return self._trace.time_scale
        return "ns"

    def _rebuild_zoom_presets(self) -> None:
        """Rebuild the zoom-preset combo with percentage-based presets.

        Each percentage represents how much of the total trace is visible:
        Fit = 100%, 50% = half the trace visible (zoomed in 2x), etc.
        The active selection is reset to "Fit" (index 0); _on_zoom_changed()
        will re-sync the combo to the correct slot once the next zoom event fires.
        """
        sc = self._view._scene
        fit_tpp = sc._timescale_per_px_fit if sc else float('inf')
        min_tpp = sc._timescale_per_px_default if sc else 0
        # Each entry: (label, timescale_per_px | None).
        # "Fit" is always first; percentage presets from smallest to largest.
        self._zoom_presets = []
        for pct in _ZOOM_PRESET_PERCENTAGES:
            tpp = fit_tpp * pct / 100.0
            if tpp < min_tpp:
                continue
            self._zoom_presets.append((f"{pct}%", tpp))
        self._zoom_presets.append(("Fit", None))  # Fit is always last (100%)
        self._zoom_preset_combo.blockSignals(True)
        self._zoom_preset_combo.clear()
        for label, _ in self._zoom_presets:
            self._zoom_preset_combo.addItem(label)
        fit_idx = len(self._zoom_presets) - 1
        self._zoom_preset_combo.setCurrentIndex(fit_idx)  # re-synced by next _on_zoom_changed()
        self._zoom_preset_combo.blockSignals(False)

    def _refresh_zoom_ui_unit(self) -> None:
        self._rebuild_zoom_presets()
        unit = self._current_time_unit()
        _zoom_str = _format_timescale_per_px(self._timescale_per_px_default_val, unit).replace("/px", "/pixel")
        self._act_zoom_1to1.setToolTip(f"Zoom to {_zoom_str}")
        if self._trace is None:
            self._zoom_scale_label.setText("—")
            self._zoom_visible_label.setText("")
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
            scene = self._view._scene
            trace = scene._trace
            if trace and trace.core_names:
                all_expanded = all(
                    scene._core_expanded.get(c, True) for c in trace.core_names)
                self._tb_expand_all_btn.setChecked(all_expanded)
        for tab in self._tabs:
            tab.view.set_view_mode(mode)
            self._sync_cpu_load_graph(tab)
        if not self._tabs:
            self._view.set_view_mode(mode)
            self._cpu_load_graph.set_view_mode(mode)
        self._refresh_find_marker()
        if self._cpu_splitter_user_sized:
            self._apply_saved_cpu_splitter()
        else:
            self._autofit_cpu_load_height()

    def _on_cpu_splitter_moved(self, pos: int = 0, index: int = 0) -> None:
        """Remember manual timeline / CPU load split so autofit does not override it."""
        self._cpu_splitter_user_sized = True
        sizes = self._cpu_splitter.sizes()
        if len(sizes) >= 2 and sizes[1] > 0:
            self._cpu_splitter_bottom_h = sizes[1]

    def _apply_saved_cpu_splitter(self, tab: Optional[_TraceTab] = None) -> None:
        """Restore a user-resized CPU load pane height on *tab*."""
        tab = tab or self._active_tab
        if tab is None or not self._cpu_splitter_user_sized:
            return
        bottom = self._cpu_splitter_bottom_h
        if bottom is None or bottom <= 0:
            return
        splitter = tab.cpu_splitter
        total = max(splitter.height(), bottom + 120)
        bottom = min(bottom, total - 100)
        splitter.setSizes([total - bottom, bottom])

    def _autofit_cpu_load_height(self) -> None:
        """Resize the CPU load splitter pane; cap height so extra cores scroll inside."""
        if self._cpu_splitter_user_sized:
            return
        if not self._show_cpu_load or not self._cpu_load_scroll.isVisible():
            return
        preferred = self._cpu_load_graph.sizeHint().height()
        # Small margin for the scroll-area frame / horizontal scrollbar track.
        preferred = preferred + 6
        # Do not grow the pane without bound — match web CPU_LOAD_MAX_H and scroll inside.
        fit_h = min(preferred, CPU_LOAD_PANE_MAX_H)
        sizes = self._cpu_splitter.sizes()
        total = sum(sizes)
        new_bottom = max(40, min(fit_h, total - 100))
        self._cpu_splitter.setSizes([total - new_bottom, new_bottom])
        self._cpu_load_graph._sync_scroll_size()

    def _close_heatmap_dialog(self) -> None:
        if self._heatmap_dlg is not None:
            self._heatmap_dlg.close()
            self._heatmap_dlg = None

    def _sync_heatmap_dialog_to_tab(self) -> None:
        dlg = self._heatmap_dlg
        if dlg is None:
            return
        tab = self._active_tab
        owner = getattr(dlg, "_owner_tab_path", None)
        cur = tab.path if tab else None
        if tab is None or cur != owner:
            self._close_heatmap_dialog()
            return
        dlg.refresh_scope()
        mks = tab.view._scene._heatmap_filter_mks
        dlg.set_filter_banner(
            getattr(self._legend, "_heatmap_filter_label", None),
            len(mks) if mks else 0)

    def _capture_heatmap_view_snapshot(self, tab: _TraceTab) -> None:
        """Remember timeline zoom/pan/cursors before heatmap drill-down."""
        view = tab.view
        sc = view._scene
        vp = view.viewport().rect()
        center = view.mapToScene(vp.center())
        is_horiz = sc._horizontal
        center_ns = sc.scene_to_ns(center.x() if is_horiz else center.y())
        orth = center.y() if is_horiz else center.x()
        self._heatmap_view_snapshot = {
            "fit_mode": bool(view._fit_mode),
            "timescale_per_px": sc.timescale_per_px,
            "cursors": list(sc.cursor_times()),
            "center_ns": center_ns,
            "orth": orth,
            "horizontal": is_horiz,
        }

    def _center_view_on_heatmap_snapshot(self, tab: _TraceTab, snap: dict) -> None:
        if snap.get("fit_mode"):
            return
        view = tab.view
        sc = view._scene
        coord = sc.ns_to_scene_coord(int(snap["center_ns"]))
        if snap["horizontal"]:
            view.centerOn(coord, float(snap["orth"]))
        else:
            view.centerOn(float(snap["orth"]), coord)

    def _clear_heatmap_task_filter(self) -> None:
        had_filter = self._heatmap_filter_active()
        tab = self._active_tab
        if tab is None:
            self._legend.set_heatmap_filter(None, None)
            if self._heatmap_dlg is not None:
                self._heatmap_dlg.set_filter_banner(None, 0)
            return

        view = tab.view
        sc = view._scene
        snap = self._heatmap_view_snapshot
        restored = snap is not None
        had_highlight = sc._locked_task is not None or sc._hovered_task is not None

        with sc.suspend_rebuild():
            sc._heatmap_filter_mks = None
            sc._remove_hover_overlay()
            sc._locked_task = None
            sc._locked_core = None
            sc._locked_ns = None
            sc._locked_segment_key = None
            sc._hovered_task = None

            self._legend.set_heatmap_filter(None, None)
            self._legend.set_locked_task(None)

            if snap:
                view._fit_mode = bool(snap["fit_mode"])
                sc._ns_range_hint = None
                if view._fit_mode:
                    avail = view._fit_viewport_size()
                    tr = sc._trace
                    time_span = max(tr.time_max - tr.time_min, 1)
                    sc._timescale_per_px = time_span / max(
                        avail - sc._label_width, 100)
                    sc._timescale_per_px_fit = sc._timescale_per_px
                    view.resetTransform()
                else:
                    sc._timescale_per_px = max(
                        sc._timescale_per_px_default,
                        float(snap["timescale_per_px"]))
                sc._cursor_times = []
                for ns in snap.get("cursors", []):
                    try:
                        sc._cursor_times.append(int(ns))
                    except (ValueError, TypeError):
                        pass
            elif not restored:
                view._fit_mode = False
                sc._cursor_times = []

        if snap:
            self._center_view_on_heatmap_snapshot(tab, snap)

        _process_ui_events_safely()

        self._defer_stats_refresh = True
        try:
            view.cursors_changed.emit(sc.cursor_times())
            view.zoom_changed.emit(sc.timescale_per_px)
        finally:
            self._defer_stats_refresh = False

        if had_highlight:
            sc.highlight_changed.emit(None, False)
        self._sync_show_all_tasks_btn()
        if self._heatmap_dlg is not None:
            dlg = self._heatmap_dlg
            QTimer.singleShot(0, lambda d=dlg: self._finish_heatmap_clear_ui(d))
        if (
            self._stats_panel._scope_to_cursors
            and len(sc.cursor_times()) >= 2
        ):
            times_copy = list(sc.cursor_times())
            QTimer.singleShot(
                0, lambda: self._stats_panel.set_cursor_times(
                    times_copy, refresh_stats=True))
        if had_filter or restored:
            self.statusBar().showMessage("Showing all tasks", 3000)
        self._heatmap_view_snapshot = None

    def _finish_heatmap_clear_ui(self, dlg: _MigrationHeatmapDialog) -> None:
        dlg.refresh_scope()
        dlg.set_filter_banner(None, 0)

    def _open_migration_heatmap(self) -> None:
        trace = self._trace
        if trace is None or not _trace_is_multi_core(trace):
            return
        if self._heatmap_dlg is not None:
            self._heatmap_dlg.raise_()
            self._heatmap_dlg.activateWindow()
            return
        tab = self._active_tab
        if tab is not None:
            self._capture_heatmap_view_snapshot(tab)
        dlg = _MigrationHeatmapDialog(
            trace, parent=self, on_drill=self._on_heatmap_drill,
            on_clear=self._clear_heatmap_task_filter)
        dlg._owner_tab_path = (
            self._active_tab.path if self._active_tab else None)
        dlg.finished.connect(self._on_heatmap_dlg_closed)
        self._heatmap_dlg = dlg
        tab = self._active_tab
        mks = tab.view._scene._heatmap_filter_mks if tab else None
        dlg.set_filter_banner(
            getattr(self._legend, "_heatmap_filter_label", None),
            len(mks) if mks else 0)
        dlg.show()

    def _on_heatmap_dlg_closed(self, _result: int = 0) -> None:
        self._heatmap_dlg = None

    def _heatmap_filter_active(self) -> bool:
        tab = self._active_tab
        if tab is None:
            return False
        return tab.view._scene._heatmap_filter_mks is not None

    def _sync_show_all_tasks_btn(self) -> None:
        if hasattr(self, "_tb_show_all_tasks_btn"):
            self._tb_show_all_tasks_btn.setVisible(self._heatmap_filter_active())

    def _on_heatmap_drill(self, from_core: str, to_core: str, label: str,
                          bin_lo: int, bin_hi: int, merge_keys: set) -> None:
        if not merge_keys:
            return
        tab = self._active_tab
        if tab is None:
            return
        dlg = self._heatmap_dlg
        owner = getattr(dlg, "_owner_tab_path", None) if dlg else None
        if owner is not None and tab.path != owner:
            return
        self._set_view_mode("task")
        self._legend.set_migrated_only_checked(False)
        tab.view._scene.set_heatmap_task_filter(set(merge_keys))
        self._legend.set_heatmap_filter(label, merge_keys)
        self._sync_show_all_tasks_btn()
        if self._heatmap_dlg is not None:
            self._heatmap_dlg.set_filter_banner(label, len(merge_keys))
        view = tab.view
        view._fit_mode = False
        view.clear_cursors()
        view._scene.add_cursor(bin_lo)
        view._scene.add_cursor(bin_hi)
        view.cursors_changed.emit(view._scene.cursor_times())
        vp_px = max(view.viewport().width() - view._scene._label_width, 100)
        view._scene.zoom_to_range(bin_lo, bin_hi, vp_px)
        view.scroll_to_ns((bin_lo + bin_hi) // 2)
        view.zoom_changed.emit(view._scene.timescale_per_px)
        if len(merge_keys) == 1:
            mk = next(iter(merge_keys))
            self._on_legend_task_clicked(mk)
        else:
            view._scene.set_highlighted_task(None)
        self._stats_panel.set_cursor_times(
            view._scene.cursor_times(), refresh_stats=False)
        n = len(merge_keys)
        self.statusBar().showMessage(
            f"Heatmap {label}: showing {n} task(s) with migrations in "
            f"{_format_time(bin_lo, self._trace.time_scale)}–"
            f"{_format_time(bin_hi, self._trace.time_scale)}. "
            f"Toolbar All tasks or Legend Clear to show all.",
            8000)

    def _sync_heatmap_toolbar(self) -> None:
        if not hasattr(self, "_tb_heatmap_btn"):
            return
        trace = self._trace
        self._tb_heatmap_btn.setEnabled(
            trace is not None and _trace_is_multi_core(trace))

    def _toggle_expand_all_cores(self) -> None:
        """Expand or collapse all cores based on the button's checked state."""
        expanded = self._tb_expand_all_btn.isChecked()
        self._view.set_all_cores_expanded(expanded)
        self._cpu_load_graph.set_all_expanded(expanded)

    def _toggle_cpu_load_graph(self) -> None:
        """Show or hide the CPU load graph panel."""
        visible = self._tb_cpu_load_btn.isChecked()
        self._show_cpu_load = visible
        for tab in self._tabs:
            tab.cpu_load_scroll.setVisible(visible)
        if visible and self._active_tab is not None:
            if self._cpu_splitter_user_sized:
                self._apply_saved_cpu_splitter()
            else:
                self._autofit_cpu_load_height()

    def _sync_toolbar_to_active_tab(self) -> None:
        """Refresh toolbar toggles that reflect per-tab view state."""
        self._sync_heatmap_toolbar()
        if hasattr(self, "_tb_cpu_load_btn"):
            self._tb_cpu_load_btn.blockSignals(True)
            self._tb_cpu_load_btn.setChecked(self._show_cpu_load)
            self._tb_cpu_load_btn.blockSignals(False)
        if hasattr(self, "_tb_log2_btn"):
            log2 = bool(self._view._scene._sti_log_scale)
            self._tb_log2_btn.blockSignals(True)
            self._tb_log2_btn.setChecked(log2)
            self._tb_log2_btn.blockSignals(False)
        if hasattr(self, "_tb_expand_all_btn") and self._view_mode == "core":
            scene = self._view._scene
            trace = scene._trace
            if trace and trace.core_names:
                all_expanded = all(
                    scene._core_expanded.get(c, True) for c in trace.core_names)
                self._tb_expand_all_btn.blockSignals(True)
                self._tb_expand_all_btn.setChecked(all_expanded)
                self._tb_expand_all_btn.blockSignals(False)

    # -- File actions ---------------------------------------------------

    @_dialog_guard
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
        # Load existing JSON list
        raw_json = self._settings.get("files", "recent_json", "")
        try:
            entries = json.loads(raw_json) if raw_json.strip() else []
        except (json.JSONDecodeError, ValueError):
            entries = []
        # Remove any existing entry for this path
        entries = [e for e in entries if e.get("path") != norm]
        # Build new entry with metadata
        try:
            size  = os.path.getsize(norm)
            mtime = int(os.path.getmtime(norm))
        except OSError:
            size, mtime = 0, 0
        entries.insert(0, {"path": norm, "size": size, "mtime": mtime})
        self._settings.set("files", "recent_json", json.dumps(entries[:8], ensure_ascii=True), flush=False)
        # Keep legacy key for backwards compatibility
        self._settings.set("files", "recent", "|".join(e["path"] for e in entries[:8]), flush=False)

    def _rebuild_recent_menu(self) -> None:
        self._recent_menu.clear()
        # Try new JSON format first
        raw_json = self._settings.get("files", "recent_json", "")
        entries = []
        try:
            entries = json.loads(raw_json) if raw_json.strip() else []
        except (json.JSONDecodeError, ValueError):
            entries = []
        # Fall back to legacy pipe-separated list
        if not entries:
            raw = self._settings.get("files", "recent", "")
            for p in [x for x in raw.split("|") if x.strip()]:
                entries.append({"path": p, "size": 0, "mtime": 0})
        if not entries:
            act = self._recent_menu.addAction("No recent files")
            act.setEnabled(False)
            return
        for entry in entries:
            p = entry.get("path", "")
            if not p:
                continue
            parts = p.replace("\\", "/").split("/")
            label = "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
            size  = entry.get("size", 0)
            mtime = entry.get("mtime", 0)
            meta_parts = []
            if size > 0:
                if size >= 1_048_576:
                    meta_parts.append(f"{size / 1_048_576:.1f} MB")
                elif size >= 1024:
                    meta_parts.append(f"{size // 1024} KB")
                else:
                    meta_parts.append(f"{size} B")
            if mtime > 0:
                dt = datetime.datetime.fromtimestamp(mtime)
                meta_parts.append(dt.strftime("%Y-%m-%d"))
            if meta_parts:
                label = f"{label}  [{', '.join(meta_parts)}]"
            self._recent_menu.addAction(label, lambda checked=False, _p=p: self._open_file(_p)) \
                .setToolTip(p)

    def _trace_state_key(self, path: str) -> str:
        norm = os.path.abspath(path)
        digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
        return f"trace_{digest}"

    def _save_current_trace_state(self) -> None:
        if not self._current_file:
            return
        self._persist_trace_state(
            self._current_file, self._bookmarks, self._annotations, self._mark_next_id)

    def _persist_trace_state(self, path: str, bookmarks, annotations, mark_next_id: int) -> None:
        if not path:
            return
        key = self._trace_state_key(path)
        payload = {
            "next_id": mark_next_id,
            "bookmarks": [{"id": b.id, "ns": b.ns, "label": b.label} for b in bookmarks],
            "annotations": [{"id": a.id, "ns": a.ns, "note": a.note} for a in annotations],
        }
        self._settings.set("trace_state", key, json.dumps(payload, ensure_ascii=True), flush=False)
        self._settings.prune_section("trace_state", 8)
        self._settings.flush()

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
                    if self._trace is not None:
                        b = TraceBookmark(bid, max(0, min(b.ns, self._trace.time_max)), b.label)
                    self._bookmarks.append(b)
                    max_id = max(max_id, b.id)
                for entry in payload.get("annotations", []):
                    note = str(entry.get("note", "")).strip()
                    aid = int(entry.get("id", 0))
                    if aid <= 0:
                        aid = max_id + 1
                    a = TraceAnnotation(aid, int(entry.get("ns", 0)), note)
                    if self._trace is not None:
                        a = TraceAnnotation(aid, max(0, min(a.ns, self._trace.time_max)), a.note)
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

    def _scroll_to_segment(self, seg) -> None:
        """Scroll to and highlight *seg* without placing a cursor."""
        if self._trace is None or seg is None:
            return
        self._view.scroll_to_ns(seg.start)
        sc = self._view._scene
        mk = _task_merge_key(seg.task)
        core_name = seg.core if sc._view_mode == "core" else None
        span = sc.task_orth_scene_span(mk, core_name=core_name)
        if span is not None:
            orth = (span[0] + span[1]) / 2
            time_coord = sc.ns_to_scene_coord(seg.start)
            if sc._horizontal:
                self._view.centerOn(time_coord, orth)
            else:
                self._view.centerOn(orth, time_coord)
            self._view.viewport().update()
        sc.set_highlighted_segment(seg)

    def _scroll_to_interval(self, inst: "IntervalInstance", mark_ns: int) -> None:
        """Zoom to and scroll vertically to an interval instance (statistics plot drill-down)."""
        if self._trace is None or inst is None:
            return
        sc = self._view._scene
        vp = self._view.viewport().rect()
        is_horiz = sc._horizontal
        vp_px = max(vp.width() if is_horiz else vp.height(), 100)
        margin = max(1, (inst.stop_ns - inst.start_ns) // 10)
        ns_lo = max(self._trace.time_min, inst.start_ns - margin)
        ns_hi = min(self._trace.time_max, inst.stop_ns + margin)
        self._view._fit_mode = False
        sc.zoom_to_range(ns_lo, ns_hi, vp_px)
        span = sc.interval_orth_scene_span(inst.id)
        cur = self._view.mapToScene(vp.center())
        if span is not None:
            orth = (span[0] + span[1]) / 2
            if is_horiz:
                self._view.centerOn(cur.x(), orth)
            else:
                self._view.centerOn(orth, cur.y())
        self._view.zoom_changed.emit(sc.timescale_per_px)
        sc.set_highlighted_interval(inst, mark_ns)
        self._view.viewport().update()

    def _on_segment_jump(self, ns: int) -> None:
        """Scroll the timeline to *ns* (non-annotation stats jumps, e.g. TICK gaps)."""
        if self._trace is None:
            return
        self._view.scroll_to_ns(ns)

    def _on_stats_plot_point_clicked(self, payload, mark_ns: int, note: str) -> None:
        """Metrics plot point: jump/highlight and add an annotation with *note*."""
        if self._trace is None:
            return
        if isinstance(payload, TaskSegment):
            self._scroll_to_segment(payload)
        elif isinstance(payload, IntervalInstance):
            self._scroll_to_interval(payload, mark_ns)
        else:
            self._view.scroll_to_ns(mark_ns)
        self._add_annotation_with_note(mark_ns, note)

    def _add_bookmark_at_center(self) -> None:
        if self._trace is None:
            return
        self._push_undo_snapshot()
        # Priority: hover position -> first placed cursor -> viewport centre
        hover_ns   = self._view._scene._hover_ns
        cursor_times = self._view._scene.cursor_times()
        ns = (hover_ns if hover_ns is not None
              else cursor_times[0] if cursor_times
              else self._view.view_center_ns())
        unit = self._current_time_unit()
        label = f"Bookmark @{_format_time(ns, unit, decimals=3)}"
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
        self._push_undo_snapshot()
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
            txt = b.label or f"Bookmark @{_format_time(b.ns, unit, decimals=3)}"
            item = QListWidgetItem(txt)
            item.setData(Qt.UserRole, int(b.id))
            item.setData(Qt.UserRole + 1, int(b.ns))
            item.setToolTip(f"{_format_time(b.ns, unit, decimals=3)}")
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self._bookmark_list.addItem(item)
        self._bookmark_list.blockSignals(False)
        self._view._scene.set_marks(self._bookmarks, self._annotations)
        self._view._has_bookmarks = bool(self._bookmarks)

    def _on_bookmark_item_changed(self, item: QListWidgetItem) -> None:
        if item is None:
            return
        bid = int(item.data(Qt.UserRole))
        new_label = item.text().strip()
        for b in self._bookmarks:
            if b.id == bid:
                # Empty label -> revert to the default timestamp label so the
                # bookmark keeps useful identity information.
                b.label = new_label or f"Bookmark @{_format_time(b.ns, self._current_time_unit(), decimals=3)}"
                break
        self._save_current_trace_state()

    def _add_annotation_at_center(self) -> None:
        if self._trace is None:
            return
        note = self._annotation_input.text().strip()
        if not note:
            return
        self._push_undo_snapshot()
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
        self._push_undo_snapshot()
        unit = self._current_time_unit()
        label = f"Bookmark @{_format_time(ns, unit, decimals=3)}"
        self._bookmarks.append(TraceBookmark(id=self._mark_next_id, ns=ns, label=label))
        self._mark_next_id += 1
        self._bookmarks.sort(key=lambda b: b.ns)
        self._rebuild_bookmark_list()
        self._save_current_trace_state()
        self._marks_dock.setVisible(True)
        self._marks_dock.raise_()

    def _add_annotation_at_ns(self, ns: int) -> None:
        """Add an annotation at timestamp with an empty note."""
        self._add_annotation_with_note(ns, "")

    def _add_annotation_with_note(self, ns: int, note: str) -> None:
        """Add an annotation at *ns* with the given note text."""
        if self._trace is None:
            return
        self._push_undo_snapshot()
        self._annotations.append(TraceAnnotation(id=self._mark_next_id, ns=ns, note=note or ""))
        self._mark_next_id += 1
        self._annotations.sort(key=lambda a: a.ns)
        self._rebuild_annotation_list()
        self._save_current_trace_state()
        self._marks_dock.setVisible(True)
        self._marks_dock.raise_()

    def _clear_all_bookmarks(self) -> None:
        """Remove every bookmark (undoable)."""
        if not self._bookmarks:
            return
        self._push_undo_snapshot()
        self._bookmarks.clear()
        self._rebuild_bookmark_list()
        self._save_current_trace_state()

    def _clear_all_annotations(self) -> None:
        """Remove every annotation (undoable)."""
        if not self._annotations:
            return
        self._push_undo_snapshot()
        self._annotations.clear()
        self._rebuild_annotation_list()
        self._save_current_trace_state()

    def _jump_selected_annotation(self) -> None:
        item = self._annotation_list.currentItem()
        if item is None:
            return
        self._jump_to_ns(int(item.data(Qt.UserRole + 1)))

    def _delete_selected_annotation(self) -> None:
        item = self._annotation_list.currentItem()
        if item is None:
            return
        self._push_undo_snapshot()
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
                dlg = QInputDialog(self)
                dlg.setWindowTitle("Edit Annotation")
                dlg.setLabelText("Note:")
                dlg.setTextValue(a.note)
                dlg.setInputMode(QInputDialog.TextInput)
                dlg.adjustSize()
                if _exec_centred(dlg, self) != QDialog.Accepted:
                    return
                note = dlg.textValue().strip()
                self._push_undo_snapshot()
                a.note = note
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
            txt = f"{_format_time(a.ns, unit, decimals=3)}  {a.note}"
            item = QListWidgetItem(txt)
            item.setData(Qt.UserRole, int(a.id))
            item.setData(Qt.UserRole + 1, int(a.ns))
            item.setToolTip(f"@ {_format_time(a.ns, unit, decimals=3)}\n{a.note}")
            self._annotation_list.addItem(item)
        self._annotation_list.blockSignals(False)
        self._view._scene.set_marks(self._bookmarks, self._annotations)
        self._view._has_annotations = bool(self._annotations)

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
            self._view._scene.set_find_hits([])
            return
        query = self._find_input.text().strip()
        # Clear highlights whenever the find dock is hidden or query is empty
        if not query or not self._find_dock.isVisible():
            self._find_status.setText("0 matches")
            self._view._scene.set_find_hits([])
            return
        mode = self._find_mode_combo.currentText().lower()
        if mode == "migrations":
            q_lower = query.lower()
            for m in getattr(self._trace, "migrations", ()):
                raw = self._trace.task_repr.get(m.merge_key, m.merge_key)
                disp = _task_display_name(raw)
                hay = f"{m.merge_key} {raw} {disp} {m.from_core} {m.to_core}"
                if (not q_lower or q_lower in hay.lower()
                        or q_lower in m.from_core.lower()
                        or q_lower in m.to_core.lower()):
                    self._find_hits.append(m.ns)
            self._find_hits = sorted(set(self._find_hits))
            self._find_status.setText(f"{len(self._find_hits)} migration matches")
            self._view._scene.set_find_hits(self._find_hits)
            if not self._find_hits:
                self._set_find_marker_ns(None)
            return
        regex_obj = None
        if mode == "regex":
            if len(query) > _MAX_FIND_REGEX_LEN:
                self._find_status.setText("Regex too long")
                self._view._scene.set_find_hits([])
                return
            try:
                regex_obj = re.compile(query, re.IGNORECASE)
            except re.error:
                self._find_status.setText("Regex error")
                self._set_find_marker_ns(None)
                return
        for mk, segs in self._trace.seg_map_by_merge_key.items():
            raw = self._trace.task_repr.get(mk, mk)
            disp = _task_display_name(raw)
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
        self._view._scene.set_find_hits(self._find_hits)
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
            # No previous jump - seed from viewport position.
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

    def _on_view_scrolled(self, view: TimelineView) -> None:
        if view is not self._view:
            return
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
                    self._parse_thread.cancelled,
                    self._parse_thread.progress):
            try:
                sig.disconnect()
            except (TypeError, RuntimeError):
                pass

    def _open_file(self, path: str) -> None:
        path = os.path.abspath(os.path.expanduser(path))

        existing = self._find_tab_index(path)
        if existing >= 0:
            self._tab_widget.setCurrentIndex(existing)
            if self._session_restore_queue or self._session_restore_active_idx >= 0:
                self._continue_session_restore()
            return

        if self._load_in_progress:
            self._status_file.setText("  A load is already in progress…")
            return
        self._load_in_progress = True

        self._stash_active_tab_state()

        if self._progress_dialog is not None:
            self._progress_dialog.close()
            self._progress_dialog = None

        # Abort any in-progress load before starting a new one.
        # _stop_parse_thread() preserves the required shutdown ordering.
        if not self._stop_parse_thread(wait_ms=2000):
            self._status_file.setText("  Previous load is still stopping…")
            self._load_in_progress = False
            return

        # Show a wait cursor and status message while parsing
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self._status_file.setText(f"  Loading {os.path.basename(path)}…")
        # Reset dynamic render state so new traces never inherit stale colors.
        _reset_render_state_for_new_trace()
        _process_ui_events_safely()

        # Progress dialog - created before closures so progress_dialog is defined.
        progress_dialog = _LoadProgressDialog(
            f"Loading {os.path.basename(path)}…", self)
        progress_dialog.show_centered(self.geometry())
        self._progress_dialog = progress_dialog

        def _teardown_loading_dialog() -> None:
            try:
                progress_dialog.close()
                progress_dialog.deleteLater()
            except RuntimeError:
                pass
            if self._progress_dialog is progress_dialog:
                self._progress_dialog = None
            self._load_in_progress = False
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()

        def _on_done(trace):
            # Disconnect all signals FIRST, before processEvents() or dropping the
            # thread reference.  This destroys the PyQtSlotProxy objects and their
            # QObject::removePostedEvents() call purges any still-queued progress/
            # errored events from the main-thread event queue.  Without this, a
            # queued progress event whose proxy was freed by _parse_thread=None
            # would be dispatched by sendPostedEvents -> SIGBUS crash.
            self._disconnect_parse_signals()
            progress_dialog.update_progress(100, "Building scene…")
            _process_ui_events_safely()   # let the dialog repaint before heavy build
            self._parse_thread = None
            try:
                self._finalize_loaded_trace(trace, path, progress_dialog)
            except (ValueError, RuntimeError, KeyError, OSError) as exc:
                self._status_file.setText("  No file loaded")
                QMessageBox.critical(self, "Render Error",
                                     f"Failed to display:\n{path}\n\n{exc}")
            finally:
                _teardown_loading_dialog()   # close after all heavy work is done

        def _on_error(msg):
            # Same rationale as _on_done: disconnect first to purge any
            # stale queued events before the thread / proxies are freed.
            self._disconnect_parse_signals()
            _teardown_loading_dialog()
            self._parse_thread = None
            self._status_file.setText("  No file loaded")
            QMessageBox.critical(self, "Parse Error",
                                 f"Failed to parse:\n{path}\n\n{msg}")

        def _on_cancelled():
            # Cancellation can happen when a load is interrupted before
            # done/errored handlers run. Ensure UI state is always restored.
            self._disconnect_parse_signals()
            _teardown_loading_dialog()
            self._parse_thread = None
            self._status_file.setText("  Load cancelled")

        thread = _ParseThread(path)
        thread.done.connect(_on_done)
        thread.errored.connect(_on_error)
        thread.cancelled.connect(_on_cancelled)
        thread.progress.connect(progress_dialog.update_progress)
        # Keep a reference so the thread is not garbage-collected
        self._parse_thread = thread
        try:
            thread.start()
        except Exception as exc:
            _teardown_loading_dialog()
            self._disconnect_parse_signals()
            self._parse_thread = None
            self._status_file.setText("  No file loaded")
            QMessageBox.critical(self, "Load Error",
                                 f"Failed to start parser thread:\n{path}\n\n{exc}")

    def _finalize_loaded_trace(self, trace: BtfTrace, path: str,
                               progress_dialog: _LoadProgressDialog) -> None:
        """Complete all post-parse UI/state updates for a successful load."""
        self._settings.set("files", "last_dir", os.path.dirname(path), flush=False)

        tab = self._add_trace_tab(path, trace)
        _process_ui_events_safely()
        tab.view.load_trace(trace)
        self._timescale_per_px_default_val = tab.view._scene._timescale_per_px_default
        self._refresh_zoom_ui_unit()
        self._load_trace_state(path)
        tab.bookmarks = list(self._bookmarks)
        tab.annotations = list(self._annotations)
        tab.mark_next_id = self._mark_next_id
        self._recompute_find_hits()
        tab.find_hits = list(self._find_hits)
        tab.find_hit_idx = self._find_hit_idx
        tab.find_marker_ns = self._find_marker_ns
        self._load_tab_view_state(tab)

        progress_dialog.update_progress(100, "Building legend…")
        _process_ui_events_safely()
        self._sync_panels_to_active_tab()

        self._undo_stack.clear()
        self._redo_stack.clear()
        tab.undo_stack = []
        tab.redo_stack = []
        self._act_undo.setEnabled(False)
        self._act_redo.setEnabled(False)
        if self._show_stats:
            self._stats_dock.show()
            self._stats_dock.raise_()
        if self._show_cpu_load:
            self._cpu_load_scroll.show()

        self._save_recent_files(path)
        self._rebuild_recent_menu()
        self._settings.flush()
        self._report_settings_io_failure(prefix="Settings save warning")
        warn = (trace.meta or {}).get("_version_warning")
        if warn:
            self.statusBar().showMessage(warn, 8000)
        self._continue_session_restore()

    def _capture_viewport_pixmap(self) -> QPixmap:
        """Capture the active tab's timeline viewport, optionally with CPU load graph."""
        tl_pix = self._view._capture_pixmap()
        if self._show_cpu_load and self._cpu_load_scroll.isVisible():
            return _stack_pixmaps_vertically(tl_pix, self._cpu_load_graph.grab())
        return tl_pix

    @_dialog_guard
    def _open_snapshot_editor(self) -> None:
        """Capture the viewport and open the annotation editor (web Shot parity)."""
        if self._trace is None:
            return
        pixmap = self._capture_viewport_pixmap()
        if pixmap.isNull():
            QMessageBox.warning(self, "Snapshot", "Unable to capture the viewport.")
            return
        dlg = SnapshotEditorDialog(pixmap, self)
        _exec_centred(dlg, self)

    def _on_save_image(self) -> None:
        self._open_snapshot_editor()

    @_dialog_guard
    def _on_save_svg(self) -> None:
        if self._trace is None:
            return
        base = os.path.splitext(self._current_file)[0] if self._current_file else "trace"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save SVG", base + ".svg",
            "SVG files (*.svg);;All files (*)"
        )
        if not path:
            return
        try:
            view = self._view
            scene = view._scene
            vp_rect = view.viewport().rect()
            scene_rect = QRectF(
                view.mapToScene(vp_rect.topLeft()),
                view.mapToScene(vp_rect.bottomRight()),
            )
            w = vp_rect.width()
            h = vp_rect.height()
            include_cpu = (self._show_cpu_load and self._cpu_load_scroll.isVisible())
            cpu_h = self._cpu_load_graph.height() if include_cpu else 0
            total_h = h + cpu_h
            gen = QSvgGenerator()
            gen.setFileName(path)
            gen.setSize(QSize(int(w), int(total_h)))
            gen.setViewBox(QRectF(0, 0, w, total_h))
            gen.setTitle("BTF Timeline")
            gen.setDescription("Generated by RTOS BTF Viewer")
            painter = QPainter(gen)
            try:
                scene.render(painter, QRectF(0, 0, w, h), scene_rect)
                if include_cpu:
                    painter.translate(0, h)
                    self._cpu_load_graph.render(painter)
                    painter.translate(0, -h)
            finally:
                painter.end()
            self.statusBar().showMessage(f"Saved: {path}", 4000)
        except (OSError, RuntimeError) as exc:
            QMessageBox.critical(self, "Save Error", f"Could not save SVG:\n{exc}")

    @_dialog_guard
    def _on_copy_image(self) -> None:
        if self._trace is None:
            return
        _copy_pixmap_to_clipboard(self._capture_viewport_pixmap())
        self.statusBar().showMessage("Copied to clipboard!", 4000)

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
            self._cpu_load_graph.set_font_size(self._font_size_val)
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
        if vals.get("show_cpu_load", self._show_cpu_load) != self._show_cpu_load:
            self._show_cpu_load = vals["show_cpu_load"]
            for tab in self._tabs:
                tab.cpu_load_scroll.setVisible(self._show_cpu_load)
            self._tb_cpu_load_btn.setChecked(self._show_cpu_load)
        if vals["show_hover_highlight"] != self._hover_highlight_val:
            self._hover_highlight_val = vals["show_hover_highlight"]
            self._view._scene.set_hover_highlight(self._hover_highlight_val)
        if vals["vert_label_pixmap"] != self._vert_label_pixmap_val:
            self._set_vert_label_pixmap(vals["vert_label_pixmap"], persist=False)
        if vals["colorblind_safe"] != self._colorblind_val:
            self._colorblind_val = vals["colorblind_safe"]
            self._set_colorblind_safe(self._colorblind_val)
        if vals["label_width"] != self._label_width_val:
            self._label_width_val = vals["label_width"]
            self._view._scene.set_label_width(self._label_width_val)
        if vals["row_height"] != self._row_height_val:
            self._row_height_val = vals["row_height"]
            self._view._scene.set_row_height(self._row_height_val)
        if vals["row_gap"] != self._row_gap_val:
            self._row_gap_val = vals["row_gap"]
            self._view._scene.set_row_gap(self._row_gap_val)
        if vals["sti_row_h"] != self._sti_row_h_val:
            self._sti_row_h_val = vals["sti_row_h"]
            self._view.set_sti_row_h(self._sti_row_h_val)
        if vals["sti_waveform_h"] != self._sti_waveform_h_val:
            self._sti_waveform_h_val = vals["sti_waveform_h"]
            self._view.set_sti_waveform_h(self._sti_waveform_h_val)
        if vals["sti_line_style"] != self._sti_line_style_val:
            self._sti_line_style_val = vals["sti_line_style"]
            self._view.set_sti_line_style(self._sti_line_style_val)
        if vals["timescale_per_px_default"] != self._timescale_per_px_default_val:
            self._timescale_per_px_default_val = vals["timescale_per_px_default"]
            self._view._scene.set_timescale_per_px_default(self._timescale_per_px_default_val)
            self._refresh_zoom_ui_unit()
        if vals.get("cpu_load_row_h", self._cpu_load_row_h_val) != self._cpu_load_row_h_val:
            self._cpu_load_row_h_val = vals["cpu_load_row_h"]
            self._cpu_load_graph.set_row_h(self._cpu_load_row_h_val)

    def _persist_settings_after_dlg(self, snap: dict) -> None:
        """Write to disk any settings that differ from the pre-dialog snapshot."""
        updates: Dict[str, str] = {}
        if snap["is_dark"] != self._is_dark:
            updates["theme"] = "dark" if self._is_dark else "light"
        if snap["font_size"] != self._font_size_val:
            updates["font_size"] = str(self._font_size_val)
        if snap["ui_font_size"] != self._ui_font_size_val:
            updates["ui_font_size"] = str(self._ui_font_size_val)
        if snap["max_cursors"] != self._max_cursors_val:
            updates["max_cursors"] = str(self._max_cursors_val)
        if snap["show_sti"] != self._show_sti:
            updates["show_sti"] = str(self._show_sti).lower()
        if snap["show_grid"] != self._show_grid:
            updates["show_grid"] = str(self._show_grid).lower()
        if snap["show_legend"] != self._show_legend:
            updates["show_legend"] = str(self._show_legend).lower()
        if snap["show_stats"] != self._show_stats:
            updates["show_stats"] = str(self._show_stats).lower()
        if snap["show_marks"] != self._show_marks:
            updates["show_marks"] = str(self._show_marks).lower()
        if snap.get("show_cpu_load", self._show_cpu_load) != self._show_cpu_load:
            updates["show_cpu_load"] = str(self._show_cpu_load).lower()
        if snap["show_hover_highlight"] != self._hover_highlight_val:
            updates["hover_highlight"] = str(self._hover_highlight_val).lower()
        if snap["vert_label_pixmap"] != self._vert_label_pixmap_val:
            updates["vert_label_pixmap"] = str(self._vert_label_pixmap_val).lower()
        if snap["colorblind_safe"] != self._colorblind_val:
            updates["colorblind_safe"] = str(self._colorblind_val).lower()
        if snap["label_width"] != self._label_width_val:
            updates["label_width"] = str(self._label_width_val)
        if snap["row_height"] != self._row_height_val:
            updates["row_height"] = str(self._row_height_val)
        if snap["row_gap"] != self._row_gap_val:
            updates["row_gap"] = str(self._row_gap_val)
        if snap["sti_row_h"] != self._sti_row_h_val:
            updates["sti_row_h"] = str(self._sti_row_h_val)
        if snap["sti_waveform_h"] != self._sti_waveform_h_val:
            updates["sti_waveform_h"] = str(self._sti_waveform_h_val)
        if snap["sti_line_style"] != self._sti_line_style_val:
            updates["sti_line_style"] = self._sti_line_style_val
        if snap["timescale_per_px_default"] != self._timescale_per_px_default_val:
            updates["timescale_per_px_default"] = str(self._timescale_per_px_default_val)
        if snap.get("cpu_load_row_h", self._cpu_load_row_h_val) != self._cpu_load_row_h_val:
            updates["cpu_load_row_h"] = str(self._cpu_load_row_h_val)
        if updates:
            self._settings.set_many("view", updates)
            self._report_settings_io_failure(prefix="Settings save warning")

    @_dialog_guard
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
            "show_cpu_load":            self._show_cpu_load,
            "show_hover_highlight":     self._hover_highlight_val,
            "vert_label_pixmap":        self._vert_label_pixmap_val,
            "colorblind_safe":          self._colorblind_val,
            "label_width":              self._label_width_val,
            "row_height":               self._row_height_val,
            "row_gap":                  self._row_gap_val,
            "sti_row_h":                self._sti_row_h_val,
            "sti_waveform_h":           self._sti_waveform_h_val,
            "sti_line_style":           self._sti_line_style_val,
            "timescale_per_px_default": self._timescale_per_px_default_val,
            "cpu_load_row_h":           self._cpu_load_row_h_val,
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
            cpu_load=self._show_cpu_load,
            label_width=self._label_width_val,
            row_height=self._row_height_val,
            row_gap=self._row_gap_val,
            sti_row_h=self._sti_row_h_val,
            sti_waveform_h=self._sti_waveform_h_val,
            sti_line_style=self._sti_line_style_val,
            timescale_per_px_default=self._timescale_per_px_default_val,
            is_dark=self._is_dark,
            show_hover_highlight=self._hover_highlight_val,
            vert_label_pixmap=self._vert_label_pixmap_val,
            colorblind_safe=self._colorblind_val,
            zoom_unit=self._current_time_unit(),
            cpu_load_row_h=self._cpu_load_row_h_val,
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
            "show_cpu_load":            dlg.cpu_load,
            "show_hover_highlight":     dlg.show_hover_highlight,
            "vert_label_pixmap":        dlg.vert_label_pixmap,
            "colorblind_safe":          dlg.colorblind_safe,
            "label_width":              dlg.label_width,
            "row_height":               dlg.row_height,
            "row_gap":                  dlg.row_gap,
            "sti_row_h":                dlg.sti_row_h,
            "sti_waveform_h":           dlg.sti_waveform_h,
            "sti_line_style":           dlg.sti_line_style,
            "timescale_per_px_default": dlg.timescale_per_px_default,
            "cpu_load_row_h":           dlg.cpu_load_row_h,
        }))
        # The dialog carries its own scoped stylesheet (set at construction
        # time).  Re-apply it on every live_preview so that switching the
        # theme combo immediately repaints the dialog itself too.
        dlg.live_preview.connect(
            lambda: dlg.setStyleSheet(
                _SettingsDialog._dialog_ss(dlg.is_dark, f"{dlg.ui_font_size}pt")
            )
        )
        if _exec_centred(dlg, self) == QDialog.Accepted:
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

    def _on_zoom_preset_selected(self, index: int) -> None:
        """Apply the zoom level chosen in the presets combo."""
        if index < 0 or index >= len(self._zoom_presets):
            return
        label, tpp = self._zoom_presets[index]
        if tpp is None:
            self._view.zoom_fit()
        else:
            if self._view._scene._trace is None:
                return
            self._view._fit_mode = False
            sc = self._view._scene
            sc._timescale_per_px = max(sc._timescale_per_px_default,
                                       min(tpp, sc._timescale_per_px_fit))
            sc.rebuild()
            self._view.zoom_changed.emit(sc.timescale_per_px)

    def _on_zoom_changed(self, timescale_per_px: float,
                         view: TimelineView = None) -> None:
        if view is not None and view is not self._view:
            return
        # Rebuild percentage presets if the fit level changed (resize / new trace).
        sc = self._view._scene
        cur_fit = sc._timescale_per_px_fit if sc else float('inf')
        if cur_fit != getattr(self, '_last_fit_tpp', None):
            self._last_fit_tpp = cur_fit
            self._rebuild_zoom_presets()
        unit = self._current_time_unit()
        scale_str = _format_timescale_per_px(timescale_per_px, unit)
        self._zoom_scale_label.setText(scale_str)
        if self._trace is not None:
            vp = self._view.viewport().rect()
            horiz = self._view._scene._horizontal
            vp_px = vp.width() if horiz else vp.height()
            vis_str = _format_time(vp_px * timescale_per_px, unit, decimals=1)
            self._zoom_visible_label.setText(f"·  {vis_str} visible")
            self._zoom_scale_label.setToolTip(f"Zoom: {scale_str}\nVisible: {vis_str}")
        else:
            self._zoom_visible_label.setText("")
            self._zoom_scale_label.setToolTip("Current zoom level (time per pixel)")
        # Sync zoom-preset combo
        fit_idx = len(self._zoom_presets) - 1  # "Fit" is always last
        if self._view._fit_mode:
            self._zoom_preset_combo.setCurrentIndex(fit_idx)
        else:
            matched = False
            for idx, (_, tpp) in enumerate(self._zoom_presets):
                if tpp is not None and abs(timescale_per_px - tpp) / max(tpp, 1e-12) < 0.01:
                    self._zoom_preset_combo.setCurrentIndex(idx)
                    matched = True
                    break
            if not matched:
                self._zoom_preset_combo.setCurrentIndex(-1)  # no preset matches
        self._refresh_find_marker()

    def _on_cursor_delete(self, ns: int) -> None:
        """Remove the cursor whose timestamp matches *ns* (from a badge drag-out)."""
        self._view._scene.remove_nearest_cursor(ns)
        self._view.cursors_changed.emit(self._view._scene.cursor_times())

    def _on_cursors_changed(self, times: list, view: TimelineView = None) -> None:
        if view is not None and view is not self._view:
            return
        placed_n = len(times)
        prev_n = getattr(self, "_placed_cursor_count", 0)
        refresh_stats = False
        if hasattr(self, "_stats_panel") and not self._defer_stats_refresh:
            panel = self._stats_panel
            if panel._scope_to_cursors and (placed_n >= 2 or prev_n >= 2):
                refresh_stats = True
        self._placed_cursor_count = placed_n
        if hasattr(self, "_stats_panel"):
            self._stats_panel.set_cursor_times(times, refresh_stats=refresh_stats)
        self._cursor_bar.rebuild(times, self._trace)
        has_range = len(times) >= 2
        self._act_zoom_range.setEnabled(has_range)
        self._tb_zoom_range_btn.setEnabled(has_range)
        if self._trace is None or not has_range:
            self._range_stats_label.setText("Range: place two cursors to measure")
            self._status_range.setVisible(False)
            self._rebuild_cursor_table()
            return
        t_sorted = sorted(times)
        lo = t_sorted[0]
        hi = t_sorted[-1]
        dt = max(0, hi - lo)
        unit = self._current_time_unit()
        switches, task_acc, durations = _range_stats_over_segments(
            self._trace, lo, hi)
        top_task = "-"
        top_ns = 0
        if task_acc:
            top_task, top_ns = max(task_acc.items(), key=lambda kv: kv[1])
        top_pct = (100.0 * top_ns / dt) if dt > 0 else 0.0
        self._range_stats_label.setText(
            f"Range C1-C{len(times)}: {_format_time(dt, unit, decimals=1)} | slices: {switches} | "
            f"top: {top_task} ({top_pct:.1f}%)"
        )
        # Compact status-bar version: span + segment min/max/avg
        if durations:
            d_min = _format_time(min(durations), unit, decimals=1)
            d_max = _format_time(max(durations), unit, decimals=1)
            d_avg = _format_time(sum(durations) / len(durations), unit, decimals=1)
            range_text = (
                f"Range: {_format_time(dt, unit, decimals=1)}  "
                f"min {d_min}  max {d_max}  avg {d_avg}"
            )
        else:
            range_text = f"Range: {_format_time(dt, unit, decimals=1)}  (no segments)"
        self._status_range.setText(range_text)
        self._status_range.setToolTip(range_text)
        self._status_range.setVisible(True)
        self._rebuild_cursor_table()

    def _on_mark_dragging(self, kind: str, mark_id: int, new_ns: int) -> None:
        """Live-update the bookmark/annotation panel while dragging on the timeline."""
        unit = self._current_time_unit()
        if kind == "bookmark":
            for b in self._bookmarks:
                if b.id == mark_id:
                    b.ns = new_ns
                    if b.label.startswith("Bookmark @"):
                        b.label = f"Bookmark @{_format_time(new_ns, unit, decimals=3)}"
                    break
            self._rebuild_bookmark_list()
        else:
            for a in self._annotations:
                if a.id == mark_id:
                    a.ns = new_ns
                    break
            self._rebuild_annotation_list()
        # No _save_current_trace_state - only persist on final drop

    def _on_mark_moved(self, kind: str, mark_id: int, new_ns: int) -> None:
        """Finalise a mark drag: persist state (data already updated by _on_mark_dragging)."""
        self._save_current_trace_state()

    # ------------------------------------------------------------------
    # Cursor comparison table
    # ------------------------------------------------------------------

    def _task_at_time(self, ns: int) -> str:
        """Return the display name(s) of tasks running at *ns* (nanoseconds)."""
        if self._trace is None:
            return "—"
        import bisect
        found: list = []
        for mk, segs in self._trace.seg_map_by_merge_key.items():
            starts = self._trace.seg_start_by_merge_key.get(mk)
            if not starts:
                continue
            pos = bisect.bisect_right(starts, ns) - 1
            if pos >= 0 and segs[pos].end >= ns:
                raw = self._trace.task_repr.get(mk, mk)
                found.append(_task_display_name(raw))
        return ", ".join(dict.fromkeys(found)) if found else "—"

    def _rebuild_cursor_table(self) -> None:
        """Populate the Cursors comparison tab with current cursor data."""
        if not hasattr(self, "_cursor_table"):
            return
        times = self._view._scene.cursor_times()
        if not times or self._trace is None:
            self._cursor_table.setRowCount(0)
            return
        unit = self._current_time_unit()
        sorted_times = sorted(times)
        c1 = sorted_times[0]
        self._cursor_table.setRowCount(len(sorted_times))
        for row, ns in enumerate(sorted_times):
            ci = QTableWidgetItem(f"C{row + 1}")
            ci.setData(Qt.UserRole, ns)
            ti = QTableWidgetItem(_format_time(ns, unit, decimals=3))
            task_item = QTableWidgetItem(self._task_at_time(ns))
            if row == 0:
                delta_item = QTableWidgetItem("—")
            else:
                dt = ns - c1
                sign = "+" if dt >= 0 else ""
                delta_item = QTableWidgetItem(f"{sign}{_format_time(abs(dt), unit, decimals=3)}")
            for it in (ci, ti, task_item, delta_item):
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            self._cursor_table.setItem(row, 0, ci)
            self._cursor_table.setItem(row, 1, ti)
            self._cursor_table.setItem(row, 2, task_item)
            self._cursor_table.setItem(row, 3, delta_item)
        self._cursor_table.resizeColumnsToContents()

    def _on_cursor_table_clicked(self, row: int, _col: int) -> None:
        """Jump the timeline to the cursor selected in the comparison table."""
        item = self._cursor_table.item(row, 0)
        if item is not None:
            ns = item.data(Qt.UserRole)
            if ns is not None:
                self._jump_to_ns(int(ns))

    # ------------------------------------------------------------------
    # Undo / Redo
    # ------------------------------------------------------------------

    def _push_undo_snapshot(self) -> None:
        """Capture the current cursor + mark state onto the undo stack."""
        if self._undo_suppress:
            return
        snap = (
            list(self._view._scene._cursor_times),
            [TraceBookmark(b.id, b.ns, b.label) for b in self._bookmarks],
            [TraceAnnotation(a.id, a.ns, a.note) for a in self._annotations],
            self._mark_next_id,
        )
        self._undo_stack.append(snap)
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._act_undo.setEnabled(True)
        self._act_redo.setEnabled(False)

    def _restore_snapshot(self, snap: tuple) -> None:
        """Restore cursor + mark state from a snapshot tuple."""
        cursor_times, bookmarks, annotations, next_id = snap
        self._undo_suppress = True
        # Restore cursors
        self._view._scene._cursor_times[:] = cursor_times
        self._view._scene._draw_cursors()
        self._view._reposition_frozen_top()
        self._view.cursors_changed.emit(list(cursor_times))
        # Restore marks
        self._bookmarks    = bookmarks
        self._annotations  = annotations
        self._mark_next_id = next_id
        self._rebuild_bookmark_list()
        self._rebuild_annotation_list()
        self._save_current_trace_state()
        self._undo_suppress = False

    def _cmd_undo(self) -> None:
        """Undo the last cursor/mark mutation (Ctrl+Z)."""
        if not self._undo_stack:
            return
        # Push current state to redo stack
        snap = (
            list(self._view._scene._cursor_times),
            [TraceBookmark(b.id, b.ns, b.label) for b in self._bookmarks],
            [TraceAnnotation(a.id, a.ns, a.note) for a in self._annotations],
            self._mark_next_id,
        )
        self._redo_stack.append(snap)
        self._act_redo.setEnabled(True)
        snap = self._undo_stack.pop()
        self._act_undo.setEnabled(bool(self._undo_stack))
        self._restore_snapshot(snap)

    def _cmd_redo(self) -> None:
        """Redo the last undone cursor/mark mutation (Ctrl+Y)."""
        if not self._redo_stack:
            return
        snap = (
            list(self._view._scene._cursor_times),
            [TraceBookmark(b.id, b.ns, b.label) for b in self._bookmarks],
            [TraceAnnotation(a.id, a.ns, a.note) for a in self._annotations],
            self._mark_next_id,
        )
        self._undo_stack.append(snap)
        self._act_undo.setEnabled(True)
        snap = self._redo_stack.pop()
        self._act_redo.setEnabled(bool(self._redo_stack))
        self._restore_snapshot(snap)

    def _on_legend_task_clicked(self, task: str) -> None:
        """Toggle click-locked highlight for *task* from the Legend panel."""
        sc = self._view._scene
        if sc._locked_task == task:
            sc.set_highlighted_task(None)          # second click on same -> cancel
        else:
            sc.set_highlighted_task(task, locked=True)
            self._scroll_view_to_task(task)

    def _on_legend_migrated_filter(self, enabled: bool) -> None:
        for view in self._iter_tab_views():
            view._scene.set_migrated_only_filter(enabled)
        if enabled:
            self._legend.set_heatmap_filter(None, None)
            self._sync_show_all_tasks_btn()

    @_dialog_guard
    def _open_trace_compare(self, _checked: bool = False) -> None:
        if len(self._tabs) < 2:
            QMessageBox.information(
                self, "Trace Compare",
                "Open at least two trace tabs to compare traces.")
            return
        _exec_centred(_TraceCompareDialog(self, parent=self), self)

    def _scroll_view_to_task(self, task: str) -> None:
        """Scroll the orthogonal axis to bring *task*'s row/column fully into view.

        The time-axis scroll position is preserved; only the row (horizontal
        mode) or column (vertical mode) axis is adjusted.  Scrolls whenever
        the row/column is partially or fully outside the current viewport.
        """
        sc = self._view._scene
        orth = sc.task_orth_scene_coord(task)
        if orth is None:
            return
        # Compute the full extent of the row (horizontal) or column (vertical).
        if sc._horizontal:
            half = sc._row_height / 2
        else:
            half = max(sc._row_height + sc._row_gap, 26) / 2
        row_lo = orth - half
        row_hi = orth + half

        vp = self._view.viewport().rect()
        if sc._horizontal:
            vp_lo = self._view.mapToScene(vp.topLeft()).y()
            vp_hi = self._view.mapToScene(vp.bottomLeft()).y()
            if row_lo >= vp_lo and row_hi <= vp_hi:
                return                              # row fully visible - nothing to do
            cur = self._view.mapToScene(vp.center())
            self._view.centerOn(cur.x(), orth)
        else:
            vp_lo = self._view.mapToScene(vp.topLeft()).x()
            vp_hi = self._view.mapToScene(vp.topRight()).x()
            if row_lo >= vp_lo and row_hi <= vp_hi:
                return                              # column fully visible - nothing to do
            cur = self._view.mapToScene(vp.center())
            self._view.centerOn(orth, cur.y())

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
        #   avail = vp_px - label_w  ->  ns_hi_scene - ns_lo_scene == avail
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

    @_dialog_guard
    def _on_jump_to_time(self) -> None:
        """Open the Jump-to-Time dialog (Ctrl+G)."""
        dlg = _JumpToTimeDialog(self._trace, parent=self)
        if _exec_centred(dlg, self) == QDialog.Accepted:
            ns = dlg.result_ns()
            if ns is not None:
                self._jump_to_ns(ns)

    def _prompt_annotation_at_center(self) -> None:
        """Prompt for a note then add annotation at the first cursor (or viewport centre)."""
        if self._trace is None:
            return
        # Priority: hover position -> first placed cursor -> viewport centre
        hover_ns     = self._view._scene._hover_ns
        cursor_times = self._view._scene.cursor_times()
        ns = (hover_ns if hover_ns is not None
              else cursor_times[0] if cursor_times
              else self._view.view_center_ns())
        self._add_annotation_at_ns(ns)

    # -- Marks export ---------------------------------------------------

    def _cycle_trace_tab(self, forward: bool = True) -> None:
        """Switch to next/previous trace tab (Ctrl+Tab / Ctrl+Shift+Tab)."""
        n = len(self._tabs)
        if n < 2:
            return
        cur = self._tab_widget.currentIndex()
        if cur < 0:
            cur = 0
        nxt = (cur + 1) % n if forward else (cur - 1) % n
        self._tab_widget.setCurrentIndex(nxt)

    def _build_portable_session_payload(self) -> dict:
        """Build portable session dict (format shared with Web viewer)."""
        if self._trace is None:
            raise ValueError("No trace loaded")
        tab = self._active_tab
        sc = self._view._scene
        view = self._view
        ns_lo, ns_hi = self._cpu_load_graph._visible_time_ns_range(sc)
        vp_rect = view.viewport().rect()
        times = sc.cursor_times()
        max_c = max(self._max_cursors_val, len(times))
        cursors = [times[i] if i < len(times) else None for i in range(max_c)]
        marks = []
        for b in self._bookmarks:
            marks.append({
                "id": b.id, "ns": b.ns, "label": b.label or "", "type": "bookmark",
            })
        for a in self._annotations:
            marks.append({
                "id": a.id, "ns": a.ns, "label": a.note or "", "type": "annotation",
            })
        marks.sort(key=lambda m: m["ns"])
        find_idx = self._find_mode_combo.currentIndex()
        find_mode = (_PORTABLE_FIND_MODES[find_idx]
                     if 0 <= find_idx < len(_PORTABLE_FIND_MODES) else "contains")
        return {
            "version": SESSION_PORTABLE_VERSION,
            "traceName": os.path.basename(tab.path if tab else self._current_file or "trace.btf"),
            "exportedAt": datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
            "cursors": cursors,
            "marks": marks,
            "markNextId": self._mark_next_id,
            "timelineViewport": {
                "timeStart": ns_lo,
                "timeEnd": ns_hi,
                "scrollY": view.verticalScrollBar().value() if sc._horizontal else 0,
                "scrollX": view.horizontalScrollBar().value() if not sc._horizontal else 0,
                "canvasW": vp_rect.width(),
                "canvasH": vp_rect.height(),
            },
            "timelineOptions": {
                "viewMode": sc._view_mode,
                "orientation": "h" if sc._horizontal else "v",
                "showGrid": self._show_grid,
                "showSti": self._show_sti,
                "showCpuLoad": self._show_cpu_load,
                "darkMode": self._is_dark,
                "migratedOnlyFilter": sc._migrated_only_filter,
            },
            "findQuery": self._find_input.text().strip(),
            "findMode": find_mode,
            "pinnedHighlightKey": sc._locked_task,
        }

    def _apply_portable_session_payload(self, data: dict) -> None:
        """Restore cursors, marks, viewport, and UI state from portable session JSON."""
        if not isinstance(data, dict):
            raise ValueError("Invalid session file")
        if data.get("version") != SESSION_PORTABLE_VERSION:
            raise ValueError(f"Unsupported session version: {data.get('version')}")

        exp_name = data.get("traceName") or ""
        cur_name = os.path.basename(self._current_file or "")
        if exp_name and cur_name and exp_name != cur_name:
            self.statusBar().showMessage(
                f"Session is for \"{exp_name}\" (current: {cur_name})", 5000)

        self._push_undo_snapshot()
        sc = self._view._scene
        view = self._view

        opts = data.get("timelineOptions") or {}
        if opts.get("viewMode") in ("task", "core"):
            self._set_view_mode(opts["viewMode"])
        want_horiz = opts.get("orientation", "h") != "v"
        if sc._horizontal != want_horiz:
            self._set_orientation(want_horiz)
        if "showGrid" in opts:
            self._set_show_grid(bool(opts["showGrid"]), persist=False)
        if "showSti" in opts:
            self._set_show_sti(bool(opts["showSti"]), persist=False)
        if "showCpuLoad" in opts:
            want_cpu = bool(opts["showCpuLoad"])
            self._show_cpu_load = want_cpu
            for tab in self._tabs:
                tab.cpu_load_scroll.setVisible(want_cpu)
            if hasattr(self, "_tb_cpu_load_btn"):
                self._tb_cpu_load_btn.blockSignals(True)
                self._tb_cpu_load_btn.setChecked(want_cpu)
                self._tb_cpu_load_btn.blockSignals(False)
        if "darkMode" in opts:
            want_dark = bool(opts["darkMode"])
            if self._is_dark != want_dark:
                self._is_dark = want_dark
                self._apply_theme(want_dark)
        sc.set_migrated_only_filter(bool(opts.get("migratedOnlyFilter", False)))
        self._legend.set_migrated_only_checked(sc._migrated_only_filter)

        tvp = data.get("timelineViewport")
        if isinstance(tvp, dict) and self._trace is not None:
            try:
                t0 = int(tvp.get("timeStart", 0))
                t1 = int(tvp.get("timeEnd", 0))
            except (TypeError, ValueError):
                t0 = t1 = 0
            if t1 > t0:
                vp_rect = view.viewport().rect()
                is_horiz = sc._horizontal
                vp_px = max(vp_rect.width() if is_horiz else vp_rect.height(), 100)
                view._fit_mode = False
                sc.zoom_to_range(t0, t1, vp_px)
                view.zoom_changed.emit(sc.timescale_per_px)
                if is_horiz and "scrollY" in tvp:
                    view.verticalScrollBar().setValue(int(tvp["scrollY"]))
                if not is_horiz and "scrollX" in tvp:
                    view.horizontalScrollBar().setValue(int(tvp["scrollX"]))

        curs = data.get("cursors") or []
        placed = sum(1 for c in curs if c is not None)
        if placed:
            needed = min(_MAX_CURSORS, max(self._max_cursors_val, len(curs)))
            if needed != self._max_cursors_val:
                self._max_cursors_val = needed
                view.set_max_cursors(needed)
        sc.clear_cursors()
        for ns in curs:
            if ns is not None:
                sc.add_cursor(int(ns))
        view.cursors_changed.emit(sc.cursor_times())

        self._bookmarks.clear()
        self._annotations.clear()
        max_id = self._mark_next_id
        for m in data.get("marks") or []:
            try:
                mid = int(m.get("id", max_id))
                ns = int(m["ns"])
            except (TypeError, ValueError, KeyError):
                continue
            label = m.get("label") or ""
            max_id = max(max_id, mid + 1)
            if m.get("type") == "annotation":
                self._annotations.append(TraceAnnotation(id=mid, ns=ns, note=label))
            else:
                self._bookmarks.append(TraceBookmark(id=mid, ns=ns, label=label))
        if data.get("markNextId") is not None:
            self._mark_next_id = int(data["markNextId"])
        else:
            self._mark_next_id = max_id
        self._rebuild_bookmark_list()
        self._rebuild_annotation_list()

        self._find_input.blockSignals(True)
        self._find_input.setText(data.get("findQuery") or "")
        self._find_input.blockSignals(False)
        mode = (data.get("findMode") or "contains").lower()
        try:
            self._find_mode_combo.setCurrentIndex(_PORTABLE_FIND_MODES.index(mode))
        except ValueError:
            self._find_mode_combo.setCurrentIndex(0)
        self._recompute_find_hits()

        mk = data.get("pinnedHighlightKey")
        if mk:
            sc.set_highlighted_task(mk, locked=True)
        else:
            sc.set_highlighted_task(None)

        if tab := self._active_tab:
            self._stash_tab_state(tab)

    def _export_portable_session(self) -> None:
        """Export portable session JSON (Web-compatible)."""
        try:
            payload = self._build_portable_session_payload()
        except ValueError as exc:
            QMessageBox.information(self, "Export Session", str(exc))
            return
        base = os.path.splitext(os.path.basename(self._current_file or "trace"))[0]
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Session",
            os.path.join(os.path.dirname(self._current_file or ""), f"{base}-session.json"),
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=True)
                fh.write("\n")
            self.statusBar().showMessage(
                f"Session exported → {os.path.basename(path)}", 4000)
        except OSError as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    def _import_portable_session(self) -> None:
        """Import portable session JSON."""
        if self._trace is None:
            QMessageBox.information(self, "Import Session", "Open a trace first.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Session",
            os.path.dirname(self._current_file or ""),
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            self._apply_portable_session_payload(data)
            self.statusBar().showMessage(
                f"Session imported from {os.path.basename(path)}", 4000)
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
            QMessageBox.critical(self, "Import Session", str(exc))

    def _export_marks_csv(self) -> None:
        """Export all bookmarks and annotations to a CSV file."""
        if self._trace is None:
            return

        def _csv_time_text(ns: int, unit: str) -> str:
            # Keep CSV locale-safe for tools that misdecode micro-sign glyphs.
            return _format_time(ns, unit).replace("µs", "us").replace("μs", "us")

        unit = self._current_time_unit()
        time_scale = self._trace.time_scale
        rows = []
        for b in self._bookmarks:
            rows.append(("bookmark",   _csv_time_text(b.ns, unit), b.ns, b.label))
        for a in self._annotations:
            rows.append(("annotation", _csv_time_text(a.ns, unit), a.ns, a.note))
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
            # utf-8-sig prepends BOM for Excel compatibility on non-UTF8 locales.
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh, quoting=csv.QUOTE_ALL)
                writer.writerow(["type", "time", time_scale, "label"])
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
        # Timescale conversion: value * from_mult / to_mult  (both relative to ns)
        _ns_mult_table: dict[str, int] = {"ns": 1, "us": 1_000, "ms": 1_000_000, "s": 1_000_000_000}
        trace_scale = self._trace.time_scale if self._trace else "ns"
        def _convert_scale(value: float, from_scale: str, to_scale: str) -> int:
            if from_scale == to_scale:
                return int(value)
            from_mult = _ns_mult_table.get(from_scale, 1)
            to_mult   = _ns_mult_table.get(to_scale, 1)
            return int(value * from_mult / to_mult)
        _MAX_CSV_ROWS = 100_000   # guard against memory exhaustion from huge files
        try:
            imported = 0
            with open(path, "r", newline="", encoding="utf-8") as fh:
                reader = csv.reader(fh)
                rows = list(itertools.islice(reader, _MAX_CSV_ROWS))
            if not rows:
                return
            # Header row: col[0]="type", col[1]="time", col[2]=timescale (e.g. "us"), col[3]="label"
            header = rows[0]
            has_header = len(header) > 0 and header[0].strip().lower() == "type"
            if has_header:
                csv_scale = header[2].strip().lower() if len(header) > 2 else trace_scale
                if csv_scale not in _ns_mult_table:
                    csv_scale = trace_scale
                data_rows = rows[1:]
            else:
                csv_scale = trace_scale
                data_rows = rows
            for cols in data_rows:
                if len(cols) < 3:
                    continue
                kind = cols[0].strip().lower()
                try:
                    raw = float(cols[2])
                    if not math.isfinite(raw):
                        continue
                except (ValueError, IndexError):
                    continue
                ns = _convert_scale(raw, csv_scale, trace_scale)
                label = cols[3].strip() if len(cols) > 3 else ""
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
        except (OSError, OverflowError, ValueError, TypeError) as exc:
            QMessageBox.critical(self, "Import Error", str(exc))

    # -- Find dock ------------------------------------------------------

    def _on_find_dock_visibility_changed(self, visible: bool) -> None:
        """Clear highlight overlays when the Find dock is hidden."""
        if not visible:
            self._recompute_find_hits()

    # -- Help -----------------------------------------------------------

    @_dialog_guard
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
                ("Ctrl+W",       "Close active tab"),
                ("Ctrl+Tab",     "Next trace tab"),
                ("Ctrl+Shift+Tab", "Previous trace tab"),
                ("Ctrl+S",       "Open snapshot editor"),
                ("Ctrl+Shift+C", "Copy viewport to clipboard"),
                ("Ctrl+Q",       "Quit  (Alt+F4 also works on Windows)"),
            ]),
            ("Edit", [
                ("Ctrl+Z",    "Undo last cursor / mark change"),
                ("Ctrl+Y",    "Redo"),
            ]),
            ("View / Zoom", [
                ("Ctrl++",               "Zoom in"),
                ("Ctrl+-",               "Zoom out"),
                ("Ctrl+0",               "Fit entire trace to window"),
                ("Ctrl+R",               "Zoom to cursor range"),
                ("Ctrl+,",               "Open Settings"),
                ("Double-click",         "Zoom to segment under cursor"),
                ("Dbl-click label edge", "Auto-fit label column width"),
            ]),
            ("Navigation", [
                ("Ctrl+Home",         "Jump to trace start"),
                ("Ctrl+End",          "Jump to trace end"),
                ("Ctrl+G",            "Jump to specific time"),
                ("← / →",            "Scroll time / row axis"),
                ("↑ / ↓",            "Scroll row / time axis"),
                ("Shift+← / →",      "Prev/next boundary (horiz)"),
                ("Shift+↑ / ↓",      "Prev/next boundary (vert)"),
                ("Tab",               "Next task segment"),
                ("Shift+Tab",         "Previous task segment"),
            ]),
            ("Cursors", [
                ("Left-click",             "Place cursor"),
                ("Shift+Left-click",       "Snap to segment boundary"),
                ("Right-click",            "Remove nearest cursor"),
                ("Right-click on segment", "Context menu"),
                ("Shift+Right-click",      "Clear all cursors"),
                ("C",                      "Place cursor at pointer (falls back to centre)"),
                ("Shift+C",                "Clear all cursors"),
                ("× in status bar",        "Delete that cursor"),
            ]),
            ("Find", [
                ("Ctrl+F",    "Open Find bar"),
                ("F3",        "Find next"),
                ("Shift+F3",  "Find previous"),
            ]),
            ("Marks", [
                ("B / M / Ctrl+B",      "Add bookmark at current cursor"),
                ("Shift+B",             "Clear all bookmarks"),
                ("A / Ctrl+Shift+B",    "Add annotation at current cursor"),
                ("Shift+A",             "Clear all annotations"),
                ("Gold ▼ on ruler",     "Bookmark flag"),
                ("Orange ◆ on ruler",   "Annotation flag"),
            ]),
            ("Mouse / Trackpad", [
                ("Scroll wheel",                  "Pan vertically (rows)"),
                ("Shift+Scroll",                  "Pan horizontally (time)"),
                ("Ctrl+Scroll",                   "Zoom in/out around cursor"),
                ("Two-finger pinch  (macOS)",     "Zoom in/out"),
                ("Left-drag  (on background)",    "Pan timeline"),
                ("Middle-click-drag",             "Draw time-range selection band → zoom"),
                ("Left-click  (timeline)",        "Place cursor at click position"),
                ("Shift+Left-click",              "Snap cursor to nearest segment boundary"),
                ("Right-click  (timeline)",       "Remove nearest cursor / context menu"),
                ("Shift+Right-click",             "Clear all cursors"),
                ("Double-click  (segment)",       "Zoom to that segment"),
                ("Left-drag  (label edge)",       "Resize label column"),
                ("Double-click  (label edge)",    "Auto-fit label column width"),
                ("Left-drag  (cursor line)",      "Drag cursor to new position"),
                ("Left-drag  (mark flag)",        "Move bookmark / annotation"),
            ]),
        ]

        def _sec_html(sec_list):
            h = ""
            for section, items in sec_list:
                h += (
                    f"<tr><td colspan='2' style='padding-top:8px;'>"
                    f"<b style='color:{c_head};'>{section}</b></td></tr>"
                )
                for key, desc in items:
                    h += (
                        f"<tr>"
                        f"<td style='color:{c_key}; font-family:&quot;{_get_fixed_font_family()}&quot;; white-space:nowrap;"
                        f" background:{c_bg}; padding:2px 6px; border-radius:3px;'>{key}</td>"
                        f"<td style='color:{c_body}; padding-left:8px; white-space:nowrap;'>{desc}</td>"
                        f"</tr>"
                    )
            return h

        mid = (len(sections) + 1) // 2
        left_html  = f"<table style='border-collapse:collapse;' cellpadding='3'>{_sec_html(sections[:mid])}</table>"
        right_html = f"<table style='border-collapse:collapse;' cellpadding='3'>{_sec_html(sections[mid:])}</table>"

        dlg = QDialog(self)
        dlg.setWindowTitle("Keyboard & Mouse Shortcuts")
        dlg.setMinimumWidth(780)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 12, 16, 12)
        cols = QHBoxLayout()
        cols.setSpacing(20)
        for col_html in (left_html, right_html):
            lbl = QLabel(col_html)
            lbl.setTextFormat(Qt.RichText)
            lbl.setWordWrap(False)
            lbl.setAlignment(Qt.AlignTop)
            cols.addWidget(lbl, 1)
        layout.addLayout(cols)
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok)
        btn_box.accepted.connect(dlg.accept)
        layout.addWidget(btn_box)
        _exec_centred(dlg, self)

    @_dialog_guard
    def _on_about(self) -> None:
        _exec_centred(_AboutDialog(self, is_dark=self._is_dark), self)

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
    app.setApplicationName("RTOS BTF Viewer")
    app.setApplicationDisplayName("RTOS BTF Viewer")
    app.setOrganizationName("btf_viewer")

    win = MainWindow()
    win.show()
    _process_ui_events_safely()  # ensure the window is painted before any file open

    if len(sys.argv) > 1:
        path = sys.argv[1]
        if os.path.isfile(path):
            QTimer.singleShot(100, lambda: win._open_file(path))
    else:
        QTimer.singleShot(100, win._restore_session_tabs)

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
