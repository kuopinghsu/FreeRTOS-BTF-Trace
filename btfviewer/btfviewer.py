"""
btf_viewer.py – Single-file BTF Trace Viewer (PyQt5).

Usage:
    python btf_viewer.py [trace.btf]

Parses FreeRTOS .btf context-switch traces and renders an interactive
Gantt-style timeline with multi-cursor, drag-to-move, zoom/pan, core
view (expandable per-core rows), and SVG export.
"""

from __future__ import annotations

import math
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import (
    QEvent, QPoint, QPointF, QRectF, QSettings, Qt, QTimer, pyqtSignal,
)
from PyQt5.QtGui import (
    QBrush, QColor, QFont, QFontDatabase, QFontMetrics, QKeySequence, QPainter,
    QPalette, QPen, QPixmap, QPolygonF, QTransform, QWheelEvent,
)
from PyQt5.QtWidgets import (
    QAction, QApplication, QCheckBox, QDockWidget, QFileDialog,
    QFrame, QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPolygonItem,
    QGraphicsRectItem, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QSlider, QSpacerItem, QSpinBox, QSplitter,
    QStatusBar, QToolBar, QToolTip, QVBoxLayout, QWidget,
)
from PyQt5.QtSvg import QSvgGenerator  # noqa: F401 – kept for optional future SVG use

# ===========================================================================
# BTF Parser
# ===========================================================================

@dataclass
class RawEvent:
    time: int
    source: str
    src_inst: int
    event_type: str
    target: str
    tgt_inst: int
    event: str
    note: str

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
    time_min: int
    time_max: int
    meta: Dict[str, str] = field(default_factory=dict)

# ---------------------------------------------------------------------------
# Task-name helpers
# ---------------------------------------------------------------------------

_TASK_RE = re.compile(r"^\[(\d+)/(\d+)\](.+)$")

def parse_task_name(raw: str) -> Tuple[Optional[int], Optional[int], str]:
    """Return (core_id, task_id, display_name) from a raw BTF task name."""
    m = _TASK_RE.match(raw)
    if m:
        return int(m.group(1)), int(m.group(2)), m.group(3).strip()
    return None, None, raw

def task_display_name(raw: str) -> str:
    """Short display name: 'Name[id]' for regular tasks; bare name for IDLE/TICK."""
    _, task_id, name = parse_task_name(raw)
    if task_id is not None and not re.match(r"^IDLE\d*$|^TICK$", name):
        return f"{name}[{task_id}]"
    return name

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

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _is_core_entity(name: str) -> bool:
    return name.startswith("Core_")

def parse_btf(filepath: str) -> BtfTrace:
    """Parse a .btf file and return a BtfTrace."""

    raw_events: List[RawEvent] = []
    meta: Dict[str, str] = {}
    time_scale = "ns"

    with open(filepath, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n").rstrip("\r")
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
                time = int(parts[0].strip())
            except ValueError:
                continue

            raw_events.append(RawEvent(
                time=time,
                source=parts[1].strip(),
                src_inst=int(parts[2].strip()) if parts[2].strip().isdigit() else 0,
                event_type=parts[3].strip(),
                target=parts[4].strip(),
                tgt_inst=int(parts[5].strip()) if parts[5].strip().isdigit() else 0,
                event=parts[6].strip(),
                note=parts[7].strip() if len(parts) > 7 else "",
            ))

    t_events_by_time: Dict[int, List[RawEvent]] = defaultdict(list)
    sti_events: List[StiEvent] = []

    for ev in raw_events:
        if ev.event_type == "T":
            t_events_by_time[ev.time].append(ev)
        elif ev.event_type == "STI":
            sti_events.append(StiEvent(
                time=ev.time,
                core=ev.source,
                target=ev.target,
                event=ev.event,
                note=ev.note,
            ))

    open_seg: Dict[str, Tuple[int, str]] = {}
    last_core: Dict[str, str] = {}
    segments: List[TaskSegment] = []
    all_task_names: set = set()

    def _close_seg(task: str, end_time: int) -> None:
        if task in open_seg:
            start, core = open_seg.pop(task)
            if end_time > start:
                segments.append(TaskSegment(task=task, start=start, end=end_time, core=core))

    def _open_seg(task: str, start_time: int, core: str) -> None:
        _close_seg(task, start_time)
        open_seg[task] = (start_time, core)
        last_core[task] = core

    for ts in sorted(t_events_by_time):
        events = t_events_by_time[ts]

        core_preempts: Dict[str, str] = {}
        for ev in events:
            if ev.event == "preempt" and _is_core_entity(ev.source):
                core_preempts[ev.target] = ev.source
                all_task_names.add(ev.target)

        for ev in events:
            if ev.event != "resume":
                continue
            all_task_names.add(ev.target)
            all_task_names.add(ev.source)

            out_task = ev.source
            in_task  = ev.target

            if out_task in core_preempts:
                core = core_preempts[out_task]
            elif _is_core_entity(out_task):
                core = out_task
            elif out_task in last_core:
                core = last_core[out_task]
            else:
                core = "Core_?"

            _close_seg(out_task, ts)
            _open_seg(in_task, ts, core)

        for ev in events:
            if ev.event == "preempt":
                all_task_names.add(ev.target)
                if ev.target not in (e.source for e in events if e.event == "resume"):
                    core = core_preempts.get(ev.target, last_core.get(ev.target, "Core_?"))
                    _close_seg(ev.target, ts)
                    if _is_core_entity(ev.source):
                        last_core[ev.target] = ev.source

        for ev in events:
            if ev.event == "preempt" and ev.note == "task_create":
                all_task_names.add(ev.target)

    if raw_events:
        max_time = max(e.time for e in raw_events)
        for task in list(open_seg.keys()):
            _close_seg(task, max_time)
    else:
        max_time = 0

    task_set = {t for t in all_task_names if not _is_core_entity(t) and t}
    for seg in segments:
        task_set.add(seg.task)
    tasks = sorted(task_set, key=task_sort_key)

    sti_channel_set = {f"{e.core}/{e.target}" for e in sti_events}
    sti_channels = sorted(sti_channel_set)

    time_min = min((e.time for e in raw_events), default=0)
    time_max = max((e.time for e in raw_events), default=0)

    return BtfTrace(
        time_scale=time_scale,
        tasks=tasks,
        segments=segments,
        sti_events=sti_events,
        sti_channels=sti_channels,
        time_min=time_min,
        time_max=time_max,
        meta=meta,
    )

# ===========================================================================
# Timeline Widget
# ===========================================================================

# ---------------------------------------------------------------------------
# Constants / theme
# ---------------------------------------------------------------------------

LABEL_WIDTH   = 160
RULER_HEIGHT  = 40
ROW_HEIGHT    = 22
_FONT_SIZE    = 14   # default label font size (pt); adjustable at runtime
_UI_FONT_SIZE = 12   # fixed UI font size for menus, toolbar, status bar (pt)
ROW_GAP       = 4
STI_ROW_H     = 18
STI_MARKER_H  = 10
MIN_SEG_WIDTH = 1.0

MAX_CURSORS = 4
_CURSOR_COLORS = ["#FF4444", "#44FF88", "#4499FF", "#FFAA22"]

NS_PER_PX_DEFAULT = 1.0

_GRID_STEPS = [
    1, 2, 5, 10, 20, 50, 100, 200, 500,
    1_000, 2_000, 5_000, 10_000, 20_000, 50_000,
    100_000, 200_000, 500_000,
    1_000_000, 5_000_000, 10_000_000,
]

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

_PALETTE = [
    "#4E9AF1", "#F1884E", "#4EF188", "#F14E9A",
    "#9A4EF1", "#F1D94E", "#4EF1D9", "#F14E4E",
    "#88C057", "#C057C0", "#57C0C0", "#C09057",
    "#7B68EE", "#EE687B", "#68EE7B", "#EEB468",
]

_CORE_TINTS = {
    "Core_0": QColor(255, 255, 255, 0),
    "Core_1": QColor(0,   0,   40,  40),
    "Core_2": QColor(0,   40,  0,   40),
    "Core_3": QColor(40,  0,   0,   40),
    "Core_?": QColor(60,  60,  60,  60),
}

_SPECIAL_COLORS = {
    "TICK": QColor("#E8C84A"),
}

def _task_colour(task_raw: str) -> QColor:
    """Return a stable QColor for a task name.

    Colour is keyed on the full raw name (including [core/id] prefix) so that
    two tasks with the same display name but different IDs get different colours.
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
    if task_raw in _SPECIAL_COLORS:
        return _SPECIAL_COLORS[task_raw]
    # Hash on full raw name so same display name + different ID → different colour
    idx = hash(task_raw) % len(_PALETTE)
    return QColor(_PALETTE[idx])

def _blend_core_tint(base: QColor, core: str) -> QColor:
    tint = _CORE_TINTS.get(core, _CORE_TINTS["Core_?"])
    r = int(base.red()   * (1 - tint.alphaF()) + tint.red()   * tint.alphaF())
    g = int(base.green() * (1 - tint.alphaF()) + tint.green() * tint.alphaF())
    b = int(base.blue()  * (1 - tint.alphaF()) + tint.blue()  * tint.alphaF())
    return QColor(r, g, b)

_STI_COLOURS = {
    "take_mutex":   QColor("#E05050"),
    "give_mutex":   QColor("#50C050"),
    "create_mutex": QColor("#5080E0"),
    "trigger":      QColor("#C08030"),
}

def _sti_colour(note: str) -> QColor:
    return _STI_COLOURS.get(note, QColor("#AAAAAA"))

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

def _monospace_font(size: int, weight: int = QFont.Normal) -> QFont:
    """Return a monospace QFont using the system fixed font.

    Using QFontDatabase.systemFont avoids the Qt alias resolution warning
    that occurs when requesting the generic family name "Monospace" directly.
    """
    font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    font.setPointSize(size)
    font.setWeight(weight)
    return font

# Resolved family name of the system fixed-pitch font, used in Qt stylesheets.
# Embedding the concrete name avoids the slow "Monospace" alias lookup that
# would occur if the CSS generic family name "monospace" were used instead.
_FIXED_FONT_FAMILY: str = QFontDatabase.systemFont(QFontDatabase.FixedFont).family()

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
    """Draws the full timeline onto a QGraphicsScene."""

    scene_rebuilt    = pyqtSignal()          # emitted after every rebuild()
    highlight_changed = pyqtSignal(object, bool) # (task_name_or_None, locked)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._trace: Optional[BtfTrace] = None
        self._horizontal = True
        self._ns_per_px   = NS_PER_PX_DEFAULT
        self._show_sti    = True
        self._show_grid   = True
        self._view_mode   = "task"       # "task" or "core"
        self._core_expanded: Dict[str, bool] = {}   # True = expanded (default)
        self._font_size: int = _FONT_SIZE            # label font size (pt)
        # Frozen label-column items: List of (item, orig_x_offset)
        self._frozen_items: List[tuple] = []
        # Cursor state (stored as ns timestamps, drawn as overlay)
        self._cursor_times: List[int] = []
        self._cursor_items: list = []    # live QGraphicsItems for cursors
        # Highlighted task name (clicking a task label toggles highlight)
        self._locked_task:  Optional[str] = None   # click-locked task (persistent)
        self._hovered_task: Optional[str] = None   # hover task (transient)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_trace(self, trace: BtfTrace, viewport_width: int = 1200) -> None:
        self._trace = trace
        time_span = max(trace.time_max - trace.time_min, 1)
        avail = max(viewport_width - LABEL_WIDTH, 100)
        self._ns_per_px = time_span / avail
        self.rebuild()

    def set_horizontal(self, horizontal: bool) -> None:
        self._horizontal = horizontal
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
        self.rebuild()

    def toggle_core(self, core_name: str) -> None:
        """Expand or collapse a core's task sub-rows in the core view."""
        self._core_expanded[core_name] = not self._core_expanded.get(core_name, True)
        self.rebuild()

    @property
    def ns_per_px(self) -> float:
        return self._ns_per_px

    @ns_per_px.setter
    def ns_per_px(self, v: float) -> None:
        self._ns_per_px = max(v, 1e-4)
        self.rebuild()

    def set_font_size(self, size: int) -> None:
        """Change label font size (pt) and rebuild."""
        self._font_size = max(6, min(size, 24))
        self.rebuild()

    def zoom(self, factor: float, center_ns: Optional[int] = None) -> None:
        self._ns_per_px /= factor
        self._ns_per_px = max(self._ns_per_px, 1e-4)
        self.rebuild()

    def fit_to_width(self, viewport_width: int) -> None:
        if self._trace is None:
            return
        time_span = max(self._trace.time_max - self._trace.time_min, 1)
        avail = max(viewport_width - LABEL_WIDTH, 100)
        self._ns_per_px = time_span / avail
        self.rebuild()

    # ------------------------------------------------------------------
    # Cursor API
    # ------------------------------------------------------------------

    def scene_to_ns(self, coord: float) -> int:
        """Convert a scene X (horizontal) or Y (vertical) coord to ns."""
        if self._trace is None:
            return 0
        ns = int((coord - LABEL_WIDTH) * self._ns_per_px) + self._trace.time_min
        return max(self._trace.time_min, min(self._trace.time_max, ns))

    def ns_to_scene_coord(self, ns: int) -> float:
        """Convert a timestamp to the scene X (horizontal) or Y (vertical) coordinate."""
        return LABEL_WIDTH + self._ns_to_px(ns)

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

    def set_highlighted_task(self, task_name: Optional[str],
                             locked: bool = False) -> None:
        """Set or clear the highlighted task on the timeline.

        - ``task_name=None`` always clears the highlight and the lock.
        - ``locked=True``  pins the highlight (triggered by a click).
        - ``locked=False`` is a transient hover highlight; it is ignored
          when a click-locked highlight is already active.
        """
        if task_name is None:
            self._locked_task  = None
            self._hovered_task = None
        elif locked:
            self._locked_task  = task_name
            self._hovered_task = None
        else:
            # Hover: always update regardless of whether a lock exists
            self._hovered_task = task_name
        self.highlight_changed.emit(self._locked_task,
                                    self._locked_task is not None)
        self.rebuild()

    def clear_hover(self) -> None:
        """Clear the transient hover highlight and restore the locked state."""
        if self._hovered_task is None:
            return   # nothing to clear, skip rebuild
        self._hovered_task = None
        self.highlight_changed.emit(self._locked_task,
                                    self._locked_task is not None)
        self.rebuild()

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
        fm_big   = QFontMetrics(font_big)

        sorted_cursors = sorted(enumerate(self._cursor_times), key=lambda x: x[1])

        for order, (orig_idx, ns) in enumerate(sorted_cursors):
            color = QColor(_CURSOR_COLORS[orig_idx % MAX_CURSORS])
            pen   = QPen(color, 1.2, Qt.DashLine)

            if self._horizontal:
                x = LABEL_WIDTH + self._ns_to_px(ns)
                line = QGraphicsLineItem(x, 0, x, scene_r.height())
                line.setPen(pen)
                line.setZValue(30)
                self.addItem(line)
                self._cursor_items.append(line)

                t_str = _format_time(ns, self._trace.time_scale)
                lbl = self.addSimpleText(f"C{orig_idx+1}: {t_str}", font_big)
                lbl.setBrush(QBrush(color))
                lbl.setZValue(32)
                tw = fm_big.horizontalAdvance(lbl.text())
                th = fm_big.height()
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
                    mid_x   = LABEL_WIDTH + self._ns_to_px((ns + prev_ns) // 2)
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
                label_row_h = LABEL_WIDTH
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
                tw = fm_big.horizontalAdvance(lbl.text())
                th = fm_big.height()
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
                        QRectF(RULER_HEIGHT + 4, mid_y - dh / 2 - 2,
                               QFontMetrics(font).horizontalAdvance(d_str) + 6, dh + 4),
                        QPen(Qt.NoPen), QBrush(QColor(0, 0, 0, 160))
                    )
                    bg_rect.setZValue(31)
                    d_lbl.setPos(RULER_HEIGHT + 7, mid_y - dh / 2)
                    self._cursor_items.extend([bg_rect, d_lbl])

    # ------------------------------------------------------------------
    # Build / rebuild
    # ------------------------------------------------------------------

    def rebuild(self) -> None:
        self.clear()
        self._cursor_items = []
        self._frozen_items = []
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
        self._draw_cursors()
        self.scene_rebuilt.emit()

    def _ns_to_px(self, ns: int) -> float:
        return (ns - self._trace.time_min) / self._ns_per_px

    def _build_horizontal(self) -> None:
        trace = self._trace
        font = _monospace_font(self._font_size)
        fm   = QFontMetrics(font)

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
        total_w = LABEL_WIDTH + timeline_w
        self.setSceneRect(0, 0, total_w, total_h)

        self.addRect(QRectF(0, 0, total_w, RULER_HEIGHT),
                     QPen(Qt.NoPen), QBrush(QColor("#2B2B2B"))).setZValue(-1)
        _lbg = self.addRect(QRectF(0, 0, LABEL_WIDTH, total_h),
                            QPen(Qt.NoPen), QBrush(QColor("#1E1E1E")))
        _lbg.setZValue(35)   # must be above cursor lines (z=30-32)
        self._frozen_items.append((_lbg, 0))

        step_ns    = _nice_grid_step(self._ns_per_px, 100)
        first_tick = (trace.time_min // step_ns) * step_ns
        tick_pen   = QPen(QColor("#555555"), 0.8)
        text_color = QColor("#AAAAAA")

        t = first_tick
        while t <= trace.time_max + step_ns:
            x = LABEL_WIDTH + self._ns_to_px(t)
            if trace.time_min <= t <= trace.time_max + step_ns:
                if self._show_grid:
                    self.addLine(x, RULER_HEIGHT, x, total_h, tick_pen).setZValue(0.5)
                self.addLine(x, RULER_HEIGHT - 6, x, RULER_HEIGHT,
                             QPen(QColor("#888888"), 1)).setZValue(2)
                lbl = self.addSimpleText(_format_time(t, trace.time_scale), font)
                lbl.setBrush(QBrush(text_color))
                lbl.setPos(x + 2, 2)
                lbl.setZValue(2)
            t += step_ns

        seg_map: Dict[str, List] = {tk: [] for tk in task_rows}
        for seg in trace.segments:
            if seg.task in seg_map:
                seg_map[seg.task].append(seg)

        for row_idx, task in enumerate(task_rows):
            y_top = RULER_HEIGHT + row_idx * (ROW_HEIGHT + ROW_GAP)
            y_ctr = y_top + ROW_HEIGHT / 2

            is_hl = (task == self._locked_task or task == self._hovered_task)

            bg_color = QColor("#252526") if row_idx % 2 == 0 else QColor("#2D2D2D")
            self.addRect(QRectF(LABEL_WIDTH, y_top, timeline_w, ROW_HEIGHT),
                         QPen(Qt.NoPen), QBrush(bg_color)).setZValue(0)
            if is_hl:
                tc = _task_colour(task)
                hl_bg = QColor(tc.red(), tc.green(), tc.blue(), 35)
                hl_border = QPen(tc.lighter(160), 1.0)
                self.addRect(QRectF(LABEL_WIDTH, y_top, timeline_w, ROW_HEIGHT),
                             hl_border, QBrush(hl_bg)).setZValue(0.9)
            self.addLine(0, y_top + ROW_HEIGHT + ROW_GAP - 1,
                         total_w, y_top + ROW_HEIGHT + ROW_GAP - 1,
                         QPen(QColor("#333333"), 0.5)).setZValue(0.5)

            # Clickable label background
            lbl_bg = _TaskLabelItem(QRectF(0, y_top, LABEL_WIDTH, ROW_HEIGHT), task, self)
            lbl_bg.setZValue(36)
            self.addItem(lbl_bg)
            self._frozen_items.append((lbl_bg, 0))

            lbl_color = QColor("#FFD700") if is_hl else QColor("#D4D4D4")
            lbl_font  = _monospace_font(self._font_size, QFont.Bold) if is_hl else font
            lbl = self.addSimpleText(task_display_name(task), lbl_font)
            lbl.setBrush(QBrush(lbl_color))
            lbl.setPos(4, y_ctr - fm.height() / 2)
            lbl.setZValue(37)
            self._frozen_items.append((lbl, 4))

            base_color = _task_colour(task)
            for seg in seg_map[task]:
                color = _blend_core_tint(base_color, seg.core)
                x1 = LABEL_WIDTH + self._ns_to_px(seg.start)
                x2 = LABEL_WIDTH + self._ns_to_px(seg.end)
                w  = max(x2 - x1, MIN_SEG_WIDTH)
                ri = _SegmentItem(QRectF(x1, y_top + 1, w, ROW_HEIGHT - 2),
                                  seg, trace.time_scale)
                ri.setBrush(QBrush(color))
                ri.setPen(QPen(QColor("#FFFFFF"), 1.5) if is_hl
                          else QPen(color.darker(130), 0.4))
                ri.setZValue(1)
                self.addItem(ri)
                disp = task_display_name(task)
                if w > fm.horizontalAdvance(disp) + 4:
                    ti = self.addSimpleText(disp, font)
                    ti.setBrush(QBrush(QColor("#FFFFFF")))
                    ti.setPos(x1 + 2, y_ctr - fm.height() / 2)
                    ti.setZValue(2)

        for sti_idx, channel in enumerate(sti_rows):
            row_idx = n_task + sti_idx
            y_top   = RULER_HEIGHT + row_idx * (ROW_HEIGHT + ROW_GAP)
            y_ctr   = y_top + ROW_HEIGHT / 2
            core_part, _, _ = channel.partition("/")
            self.addRect(QRectF(LABEL_WIDTH, y_top, timeline_w, ROW_HEIGHT),
                         QPen(Qt.NoPen), QBrush(QColor("#1A1A2E"))).setZValue(0)
            lbl = self.addSimpleText(f"{core_part} STI", font)
            lbl.setBrush(QBrush(QColor("#88AABB")))
            lbl.setPos(4, y_ctr - fm.height() / 2)
            lbl.setZValue(37)
            self._frozen_items.append((lbl, 4))
            for ev in trace.sti_events:
                if f"{ev.core}/{ev.target}" != channel:
                    continue
                x  = LABEL_WIDTH + self._ns_to_px(ev.time)
                mk = _StiMarkerItem(ev, trace.time_scale, horizontal=True)
                mk.setPos(x, y_ctr)
                mk.setZValue(2)
                self.addItem(mk)

        corner = self.addRect(QRectF(0, 0, LABEL_WIDTH, RULER_HEIGHT),
                              QPen(Qt.NoPen), QBrush(QColor("#1A1A1A")))
        corner.setZValue(38)
        hdr = self.addSimpleText("Task / Channel", font)
        hdr.setBrush(QBrush(QColor("#888888")))
        hdr.setPos(4, RULER_HEIGHT / 2 - fm.height() / 2)
        hdr.setZValue(39)
        self._frozen_items.append((corner, 0))
        self._frozen_items.append((hdr, 4))

    def _build_vertical(self) -> None:
        trace = self._trace
        font = _monospace_font(self._font_size)
        fm   = QFontMetrics(font)

        task_cols = trace.tasks
        sti_cols  = trace.sti_channels if self._show_sti else []
        n_task = len(task_cols)
        n_sti  = len(sti_cols)
        total_cols = n_task + n_sti
        if total_cols == 0:
            return

        col_w       = max(ROW_HEIGHT + ROW_GAP, 26)
        label_row_h = LABEL_WIDTH
        time_span   = trace.time_max - trace.time_min
        timeline_h  = time_span / self._ns_per_px
        total_w     = col_w * total_cols + RULER_HEIGHT
        total_h     = label_row_h + timeline_h
        self.setSceneRect(0, 0, total_w, total_h)

        self.addRect(QRectF(0, 0, RULER_HEIGHT, total_h),
                     QPen(Qt.NoPen), QBrush(QColor("#2B2B2B"))).setZValue(-1)
        self.addRect(QRectF(0, 0, total_w, label_row_h),
                     QPen(Qt.NoPen), QBrush(QColor("#1E1E1E"))).setZValue(0)

        step_ns    = _nice_grid_step(self._ns_per_px, 100)
        first_tick = (trace.time_min // step_ns) * step_ns
        tick_pen   = QPen(QColor("#3A3A3A"), 0.5)
        text_color = QColor("#AAAAAA")

        t = first_tick
        while t <= trace.time_max + step_ns:
            y = label_row_h + self._ns_to_px(t)
            if trace.time_min <= t <= trace.time_max + step_ns:
                if self._show_grid:
                    self.addLine(RULER_HEIGHT, y, total_w, y, tick_pen).setZValue(0.5)
                self.addLine(RULER_HEIGHT - 6, y, RULER_HEIGHT, y,
                             QPen(QColor("#888888"), 1)).setZValue(2)
                lbl = self.addSimpleText(_format_time(t, trace.time_scale), font)
                lbl.setBrush(QBrush(text_color))
                lbl.setPos(2, y - 2)
                lbl.setZValue(2)
            t += step_ns

        seg_map: Dict[str, list] = {tk: [] for tk in task_cols}
        for seg in trace.segments:
            if seg.task in seg_map:
                seg_map[seg.task].append(seg)

        for col_idx, task in enumerate(task_cols):
            x_left   = RULER_HEIGHT + col_idx * col_w
            is_hl    = (task == self._locked_task or task == self._hovered_task)

            bg_color = QColor("#252526") if col_idx % 2 == 0 else QColor("#2D2D2D")
            self.addRect(QRectF(x_left, label_row_h, col_w, timeline_h),
                         QPen(Qt.NoPen), QBrush(bg_color)).setZValue(0)
            if is_hl:
                tc = _task_colour(task)
                hl_bg = QColor(tc.red(), tc.green(), tc.blue(), 35)
                self.addRect(QRectF(x_left, label_row_h, col_w, timeline_h),
                             QPen(tc.lighter(160), 1.0), QBrush(hl_bg)).setZValue(0.9)

            # Clickable label area at the top of each column
            lbl_bg = _TaskLabelItem(QRectF(x_left, 0, col_w, label_row_h), task, self)
            lbl_bg.setZValue(4)
            self.addItem(lbl_bg)

            lbl_color = QColor("#FFD700") if is_hl else QColor("#D4D4D4")
            lbl_font  = _monospace_font(self._font_size, QFont.Bold) if is_hl else font
            lbl = self.addSimpleText(task_display_name(task), lbl_font)
            lbl.setBrush(QBrush(lbl_color))
            lbl.setRotation(-90)
            lbl.setPos(x_left + col_w / 2 + fm.height() / 2, label_row_h - 4)
            lbl.setZValue(5)

            base_color = _task_colour(task)
            for seg in seg_map[task]:
                color = _blend_core_tint(base_color, seg.core)
                y1 = label_row_h + self._ns_to_px(seg.start)
                y2 = label_row_h + self._ns_to_px(seg.end)
                h  = max(y2 - y1, MIN_SEG_WIDTH)
                ri = _SegmentItem(QRectF(x_left + 1, y1, col_w - 2, h),
                                  seg, trace.time_scale)
                ri.setBrush(QBrush(base_color))
                ri.setPen(QPen(QColor("#FFFFFF"), 1.5) if is_hl
                          else QPen(base_color.darker(130), 0.4))
                ri.setZValue(1)
                self.addItem(ri)

        for sti_idx, channel in enumerate(sti_cols):
            col_idx = n_task + sti_idx
            x_left  = RULER_HEIGHT + col_idx * col_w
            core_part, _, _ = channel.partition("/")
            self.addRect(QRectF(x_left, label_row_h, col_w, timeline_h),
                         QPen(Qt.NoPen), QBrush(QColor("#1A1A2E"))).setZValue(0)
            lbl = self.addSimpleText(f"{core_part} STI", font)
            lbl.setBrush(QBrush(QColor("#88AABB")))
            lbl.setRotation(-90)
            lbl.setPos(x_left + col_w / 2 + fm.height() / 2, label_row_h - 4)
            lbl.setZValue(3)
            for ev in trace.sti_events:
                if f"{ev.core}/{ev.target}" != channel:
                    continue
                y     = label_row_h + self._ns_to_px(ev.time)
                x_ctr = x_left + col_w / 2
                mk    = _StiMarkerItem(ev, trace.time_scale, horizontal=False)
                mk.setPos(x_ctr, y)
                mk.setZValue(2)
                self.addItem(mk)

        self.addRect(QRectF(0, 0, RULER_HEIGHT, label_row_h),
                     QPen(Qt.NoPen), QBrush(QColor("#1A1A1A"))).setZValue(5)

    # ------------------------------------------------------------------
    # Core view builders
    # ------------------------------------------------------------------

    def _build_horizontal_core(self) -> None:
        """Horizontal core view: expandable cores → per-task sub-rows."""
        trace   = self._trace
        font    = _monospace_font(self._font_size)
        font_sm = _monospace_font(max(6, self._font_size - 1))
        fm      = QFontMetrics(font)

        core_names = sorted({seg.core for seg in trace.segments},
                            key=lambda c: (0 if c.startswith("Core_") else 1, c))
        sti_rows   = trace.sti_channels if self._show_sti else []

        core_segs: Dict[str, list] = {c: [] for c in core_names}
        for seg in trace.segments:
            if seg.core in core_segs:
                core_segs[seg.core].append(seg)

        core_tasks: Dict[str, list] = {}
        for c in core_names:
            seen: dict = {}
            for seg in core_segs[c]:
                seen.setdefault(seg.task, True)
            core_tasks[c] = sorted(seen.keys(), key=task_sort_key)

        def _row_count(c: str) -> int:
            return 1 + (len(core_tasks[c]) if self._core_expanded.get(c, True) else 0)

        total_rows = sum(_row_count(c) for c in core_names) + len(sti_rows)
        if total_rows == 0:
            return

        time_span  = trace.time_max - trace.time_min
        timeline_w = time_span / self._ns_per_px
        total_h    = RULER_HEIGHT + total_rows * (ROW_HEIGHT + ROW_GAP)
        total_w    = LABEL_WIDTH + timeline_w
        self.setSceneRect(0, 0, total_w, total_h)

        self.addRect(QRectF(0, 0, total_w, RULER_HEIGHT),
                     QPen(Qt.NoPen), QBrush(QColor("#2B2B2B"))).setZValue(-1)
        _lbg = self.addRect(QRectF(0, 0, LABEL_WIDTH, total_h),
                            QPen(Qt.NoPen), QBrush(QColor("#1E1E1E")))
        _lbg.setZValue(35)   # must be above cursor lines (z=30-32)
        self._frozen_items.append((_lbg, 0))

        step_ns    = _nice_grid_step(self._ns_per_px, 100)
        first_tick = (trace.time_min // step_ns) * step_ns
        text_color = QColor("#AAAAAA")
        tick_pen   = QPen(QColor("#555555"), 0.8)
        t_tick = first_tick
        while t_tick <= trace.time_max + step_ns:
            x = LABEL_WIDTH + self._ns_to_px(t_tick)
            if trace.time_min <= t_tick <= trace.time_max + step_ns:
                if self._show_grid:
                    self.addLine(x, RULER_HEIGHT, x, total_h, tick_pen).setZValue(0.5)
                self.addLine(x, RULER_HEIGHT - 6, x, RULER_HEIGHT,
                             QPen(QColor("#888888"), 1)).setZValue(2)
                lbl = self.addSimpleText(_format_time(t_tick, trace.time_scale), font)
                lbl.setBrush(QBrush(text_color))
                lbl.setPos(x + 2, 2)
                lbl.setZValue(2)
            t_tick += step_ns

        core_dot_colors = {"Core_0": "#FF9933", "Core_1": "#33BBFF",
                           "Core_2": "#66FF88", "Core_3": "#FF66AA"}
        row_idx = 0

        for core in core_names:
            expanded = self._core_expanded.get(core, True)
            tasks    = core_tasks[core]
            segs     = core_segs[core]
            dot_c    = QColor(core_dot_colors.get(core, "#AAAAAA"))

            y_top = RULER_HEIGHT + row_idx * (ROW_HEIGHT + ROW_GAP)
            y_ctr = y_top + ROW_HEIGHT / 2

            self.addRect(QRectF(LABEL_WIDTH, y_top, timeline_w, ROW_HEIGHT),
                         QPen(Qt.NoPen), QBrush(QColor("#2A2A3E"))).setZValue(0)
            self.addLine(0, y_top + ROW_HEIGHT + ROW_GAP - 1,
                         total_w, y_top + ROW_HEIGHT + ROW_GAP - 1,
                         QPen(QColor("#444466"), 0.8)).setZValue(0.5)

            hdr_item = _CoreHeaderItem(
                QRectF(0, y_top, LABEL_WIDTH, ROW_HEIGHT), core, self)
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

            lbl_item = self.addSimpleText(core, font)
            lbl_item.setBrush(QBrush(QColor("#E0E0E0")))
            lbl_item.setPos(arrow_w + 20, y_ctr - fm.height() / 2)
            lbl_item.setZValue(37)
            lbl_item.setAcceptedMouseButtons(Qt.NoButton)
            lbl_item.setAcceptHoverEvents(False)
            self._frozen_items.append((lbl_item, arrow_w + 20))

            for seg in segs:
                color = _task_colour(seg.task)
                x1 = LABEL_WIDTH + self._ns_to_px(seg.start)
                x2 = LABEL_WIDTH + self._ns_to_px(seg.end)
                w  = max(x2 - x1, MIN_SEG_WIDTH)
                ri = _SegmentItem(QRectF(x1, y_top + 2, w, ROW_HEIGHT - 4),
                                  seg, trace.time_scale)
                ri.setBrush(QBrush(color))
                ri.setPen(QPen(color.darker(130), 0.4))
                ri.setZValue(1)
                self.addItem(ri)

            row_idx += 1

            if not expanded:
                continue

            task_seg_map: Dict[str, list] = {tk: [] for tk in tasks}
            for seg in segs:
                if seg.task in task_seg_map:
                    task_seg_map[seg.task].append(seg)

            for sub_idx, task_name in enumerate(tasks):
                y_top2 = RULER_HEIGHT + row_idx * (ROW_HEIGHT + ROW_GAP)
                y_ctr2 = y_top2 + ROW_HEIGHT / 2

                is_hl  = (task_name == self._locked_task or task_name == self._hovered_task)

                sub_bg = QColor("#1E1E2C") if sub_idx % 2 == 0 else QColor("#232330")
                self.addRect(QRectF(LABEL_WIDTH, y_top2, timeline_w, ROW_HEIGHT),
                             QPen(Qt.NoPen), QBrush(sub_bg)).setZValue(0)
                if is_hl:
                    tc = _task_colour(task_name)
                    hl_bg = QColor(tc.red(), tc.green(), tc.blue(), 35)
                    self.addRect(QRectF(LABEL_WIDTH, y_top2, timeline_w, ROW_HEIGHT),
                                 QPen(tc.lighter(160), 1.0), QBrush(hl_bg)).setZValue(0.9)
                self.addLine(0, y_top2 + ROW_HEIGHT + ROW_GAP - 1,
                             total_w, y_top2 + ROW_HEIGHT + ROW_GAP - 1,
                             QPen(QColor("#2E2E3A"), 0.5)).setZValue(0.5)

                task_color = _task_colour(task_name)
                stripe = self.addRect(QRectF(26, y_top2 + 3, 3, ROW_HEIGHT - 6),
                                      QPen(Qt.NoPen), QBrush(task_color))
                stripe.setZValue(36)
                self._frozen_items.append((stripe, 0))

                # Clickable label background for sub-task row
                sub_lbl_bg = _TaskLabelItem(
                    QRectF(0, y_top2, LABEL_WIDTH, ROW_HEIGHT), task_name, self)
                sub_lbl_bg.setZValue(36)
                self.addItem(sub_lbl_bg)
                self._frozen_items.append((sub_lbl_bg, 0))

                disp      = task_display_name(task_name)
                lbl_color = QColor("#FFD700") if is_hl else QColor("#B0B0C0")
                lbl_fnt   = _monospace_font(max(6, self._font_size - 1),
                                            QFont.Bold) if is_hl else font_sm
                t_lbl = self.addSimpleText(disp, lbl_fnt)
                t_lbl.setBrush(QBrush(lbl_color))
                t_lbl.setPos(33, y_ctr2 - fm.height() / 2)
                t_lbl.setZValue(37)
                self._frozen_items.append((t_lbl, 33))

                for seg in task_seg_map[task_name]:
                    color = _task_colour(seg.task)
                    x1 = LABEL_WIDTH + self._ns_to_px(seg.start)
                    x2 = LABEL_WIDTH + self._ns_to_px(seg.end)
                    w  = max(x2 - x1, MIN_SEG_WIDTH)
                    ri2 = _SegmentItem(QRectF(x1, y_top2 + 1, w, ROW_HEIGHT - 2),
                                       seg, trace.time_scale)
                    ri2.setBrush(QBrush(color))
                    ri2.setPen(QPen(QColor("#FFFFFF"), 1.5) if is_hl
                               else QPen(color.darker(130), 0.4))
                    ri2.setZValue(1)
                    self.addItem(ri2)
                    if w > fm.horizontalAdvance(disp) + 4:
                        ti = self.addSimpleText(disp, font_sm)
                        ti.setBrush(QBrush(QColor("#FFFFFF")))
                        ti.setPos(x1 + 2, y_ctr2 - fm.height() / 2)
                        ti.setZValue(2)

                row_idx += 1

        for channel in sti_rows:
            y_top = RULER_HEIGHT + row_idx * (ROW_HEIGHT + ROW_GAP)
            y_ctr = y_top + ROW_HEIGHT / 2
            core_part, _, _ = channel.partition("/")
            self.addRect(QRectF(LABEL_WIDTH, y_top, timeline_w, ROW_HEIGHT),
                         QPen(Qt.NoPen), QBrush(QColor("#1A1A2E"))).setZValue(0)
            lbl = self.addSimpleText(f"{core_part} STI", font)
            lbl.setBrush(QBrush(QColor("#88AABB")))
            lbl.setPos(4, y_ctr - fm.height() / 2)
            lbl.setZValue(37)
            self._frozen_items.append((lbl, 4))
            for ev in trace.sti_events:
                if f"{ev.core}/{ev.target}" != channel:
                    continue
                x  = LABEL_WIDTH + self._ns_to_px(ev.time)
                mk = _StiMarkerItem(ev, trace.time_scale, horizontal=True)
                mk.setPos(x, y_ctr)
                mk.setZValue(2)
                self.addItem(mk)
            row_idx += 1

        corner = self.addRect(QRectF(0, 0, LABEL_WIDTH, RULER_HEIGHT),
                              QPen(Qt.NoPen), QBrush(QColor("#1A1A1A")))
        corner.setZValue(38)
        hdr_lbl = self.addSimpleText("Core / Channel", font)
        hdr_lbl.setBrush(QBrush(QColor("#888888")))
        hdr_lbl.setPos(4, RULER_HEIGHT / 2 - fm.height() / 2)
        hdr_lbl.setZValue(39)
        self._frozen_items.append((corner, 0))
        self._frozen_items.append((hdr_lbl, 4))

    def _build_vertical_core(self) -> None:
        """Vertical core view: one column per CPU core, time runs top→bottom."""
        trace = self._trace
        font  = _monospace_font(self._font_size)
        fm    = QFontMetrics(font)

        core_names = sorted({seg.core for seg in trace.segments},
                            key=lambda c: (0 if c.startswith("Core_") else 1, c))
        sti_cols   = trace.sti_channels if self._show_sti else []
        n_core     = len(core_names)
        n_sti      = len(sti_cols)
        total_cols = n_core + n_sti
        if total_cols == 0:
            return

        col_w       = max(ROW_HEIGHT + ROW_GAP, 26)
        label_row_h = LABEL_WIDTH
        time_span   = trace.time_max - trace.time_min
        timeline_h  = time_span / self._ns_per_px
        total_w     = col_w * total_cols + RULER_HEIGHT
        total_h     = label_row_h + timeline_h
        self.setSceneRect(0, 0, total_w, total_h)

        self.addRect(QRectF(0, 0, RULER_HEIGHT, total_h),
                     QPen(Qt.NoPen), QBrush(QColor("#2B2B2B"))).setZValue(-1)
        self.addRect(QRectF(0, 0, total_w, label_row_h),
                     QPen(Qt.NoPen), QBrush(QColor("#1E1E1E"))).setZValue(0)

        step_ns    = _nice_grid_step(self._ns_per_px, 100)
        first_tick = (trace.time_min // step_ns) * step_ns
        text_color = QColor("#AAAAAA")
        tick_pen   = QPen(QColor("#3A3A3A"), 0.5)

        t = first_tick
        while t <= trace.time_max + step_ns:
            y = label_row_h + self._ns_to_px(t)
            if trace.time_min <= t <= trace.time_max + step_ns:
                if self._show_grid:
                    self.addLine(RULER_HEIGHT, y, total_w, y, tick_pen).setZValue(0.5)
                self.addLine(RULER_HEIGHT - 6, y, RULER_HEIGHT, y,
                             QPen(QColor("#888888"), 1)).setZValue(2)
                lbl = self.addSimpleText(_format_time(t, trace.time_scale), font)
                lbl.setBrush(QBrush(text_color))
                lbl.setPos(2, y - 2)
                lbl.setZValue(2)
            t += step_ns

        core_segs: Dict[str, list] = {c: [] for c in core_names}
        for seg in trace.segments:
            if seg.core in core_segs:
                core_segs[seg.core].append(seg)

        core_dot_colors = {"Core_0": "#FF9933", "Core_1": "#33BBFF",
                           "Core_2": "#66FF88", "Core_3": "#FF66AA"}

        for col_idx, core in enumerate(core_names):
            x_left = RULER_HEIGHT + col_idx * col_w
            bg_c   = QColor("#252526") if col_idx % 2 == 0 else QColor("#2D2D2D")
            self.addRect(QRectF(x_left, label_row_h, col_w, timeline_h),
                         QPen(Qt.NoPen), QBrush(bg_c)).setZValue(0)
            lbl = self.addSimpleText(core, font)
            lbl.setBrush(QBrush(QColor("#E0E0E0")))
            lbl.setRotation(-90)
            lbl.setPos(x_left + col_w / 2 + fm.height() / 2, label_row_h - 4)
            lbl.setZValue(3)
            for seg in core_segs[core]:
                color = _task_colour(seg.task)
                y1 = label_row_h + self._ns_to_px(seg.start)
                y2 = label_row_h + self._ns_to_px(seg.end)
                h  = max(y2 - y1, MIN_SEG_WIDTH)
                ri = _SegmentItem(QRectF(x_left + 1, y1, col_w - 2, h),
                                  seg, trace.time_scale)
                ri.setBrush(QBrush(color))
                ri.setPen(QPen(color.darker(130), 0.4))
                ri.setZValue(1)
                self.addItem(ri)

        for sti_idx, channel in enumerate(sti_cols):
            col_idx = n_core + sti_idx
            x_left  = RULER_HEIGHT + col_idx * col_w
            core_part, _, _ = channel.partition("/")
            self.addRect(QRectF(x_left, label_row_h, col_w, timeline_h),
                         QPen(Qt.NoPen), QBrush(QColor("#1A1A2E"))).setZValue(0)
            lbl = self.addSimpleText(f"{core_part} STI", font)
            lbl.setBrush(QBrush(QColor("#88AABB")))
            lbl.setRotation(-90)
            lbl.setPos(x_left + col_w / 2 + fm.height() / 2, label_row_h - 4)
            lbl.setZValue(3)
            for ev in trace.sti_events:
                if f"{ev.core}/{ev.target}" != channel:
                    continue
                y     = label_row_h + self._ns_to_px(ev.time)
                x_ctr = x_left + col_w / 2
                mk    = _StiMarkerItem(ev, trace.time_scale, horizontal=False)
                mk.setPos(x_ctr, y)
                mk.setZValue(2)
                self.addItem(mk)

        self.addRect(QRectF(0, 0, RULER_HEIGHT, label_row_h),
                     QPen(Qt.NoPen), QBrush(QColor("#1A1A1A"))).setZValue(5)

# ---------------------------------------------------------------------------
# Custom graphics items
# ---------------------------------------------------------------------------

class _TaskLabelItem(QGraphicsRectItem):
    """Clickable task-name label area in the timeline label column.

    Clicking toggles the highlight for that task's segments on the timeline.
    """

    _HOVER_BRUSH     = QBrush(QColor(255, 255, 255, 18))
    _HIGHLIGHT_BRUSH = QBrush(QColor(255, 215, 0, 45))

    def __init__(self, rect: QRectF, task_name: str, tl_scene):
        super().__init__(rect)
        self._task_name = task_name
        self._tl_scene  = tl_scene
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
        super().hoverEnterEvent(event)
        # Defer rebuild so it never runs while this item's event handler is active
        task = self._task_name
        scene = self._tl_scene
        QTimer.singleShot(0, lambda: scene.set_highlighted_task(task, locked=False))

    def hoverLeaveEvent(self, event):
        self._update_brush()
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

class _SegmentItem(QGraphicsRectItem):
    """A coloured execution-segment rectangle with tooltip."""

    def __init__(self, rect: QRectF, seg, time_scale: str):
        super().__init__(rect)
        self._seg = seg
        self._time_scale = time_scale
        self.setAcceptHoverEvents(True)

    def hoverEnterEvent(self, event):
        seg = self._seg
        dur = seg.end - seg.start
        tip = (f"<b>{seg.task}</b><br>"
               f"Core: {seg.core}<br>"
               f"Start: {_format_time(seg.start, self._time_scale)}<br>"
               f"End:   {_format_time(seg.end,   self._time_scale)}<br>"
               f"Duration: {_format_time(dur,    self._time_scale)}")
        QToolTip.showText(event.screenPos(), tip)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        QToolTip.hideText()
        super().hoverLeaveEvent(event)

class _StiMarkerItem(QGraphicsPolygonItem):
    """A small triangle marker for STI events, with tooltip."""

    def __init__(self, ev, time_scale: str, horizontal: bool):
        r = STI_MARKER_H
        if horizontal:
            pts = QPolygonF([QPointF(0, -r), QPointF(r, r), QPointF(-r, r)])
        else:
            pts = QPolygonF([QPointF(-r, 0), QPointF(r, -r), QPointF(r, r)])
        super().__init__(pts)
        color = _sti_colour(ev.note)
        self.setBrush(QBrush(color))
        self.setPen(QPen(color.darker(150), 0.5))
        self._ev = ev
        self._time_scale = time_scale
        self.setAcceptHoverEvents(True)

    def hoverEnterEvent(self, event):
        ev = self._ev
        tip = (f"<b>STI: {ev.note}</b><br>"
               f"Time: {_format_time(ev.time, self._time_scale)}<br>"
               f"Core: {ev.core}<br>"
               f"Target: {ev.target}<br>"
               f"Event: {ev.event}")
        QToolTip.showText(event.screenPos(), tip)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        QToolTip.hideText()
        super().hoverLeaveEvent(event)

# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

class TimelineView(QGraphicsView):
    """Pan + zoom QGraphicsView wrapping a TimelineScene."""

    zoom_changed    = pyqtSignal(float)
    cursors_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = TimelineScene(self)
        self.setScene(self._scene)

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
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)

        self._press_pos: Optional[QPoint] = None
        self._press_btn: Qt.MouseButton = Qt.NoButton
        self._drag_threshold    = 6
        self._dragging_cursor_idx = -1
        self._cursor_drag_threshold = 8

        self._pinch_accum = 1.0
        # macOS native pinch zoom — intercept events on the viewport widget
        self.viewport().installEventFilter(self)
        # Reposition frozen label-column items whenever the scene is rebuilt
        self._scene.scene_rebuilt.connect(self._reposition_frozen)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_trace(self, trace: BtfTrace) -> None:
        vw = max(self.viewport().width(), 800)
        self._scene.set_trace(trace, vw)
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
        self._scene.zoom(2.0)
        self.zoom_changed.emit(self._scene.ns_per_px)

    def zoom_out(self) -> None:
        self._scene.zoom(0.5)
        self.zoom_changed.emit(self._scene.ns_per_px)

    def zoom_fit(self) -> None:
        vw = max(self.viewport().width(), 800)
        self._scene.fit_to_width(vw)
        # Ensure the view transform is identity: all zoom is handled at the
        # scene level (ns_per_px) so there must be no view-level scale active.
        # fitInView() would set a persistent QTransform that is not needed here.
        self.resetTransform()
        self.zoom_changed.emit(self._scene.ns_per_px)

    def reset_zoom(self) -> None:
        self.resetTransform()

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

    # ------------------------------------------------------------------
    # Mouse: click → place cursor, drag → pan
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        self._press_pos = event.pos()
        self._press_btn = event.button()

        if event.button() == Qt.LeftButton:
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
            in_vp_label = (event.pos().x() < LABEL_WIDTH if self._scene._horizontal
                           else event.pos().y() < LABEL_WIDTH)
            if in_vp_label:
                self.setDragMode(QGraphicsView.NoDrag)
                scene_pt2 = self.mapToScene(event.pos())
                hits = [it for it in self._scene.items(scene_pt2)
                        if isinstance(it, _TaskLabelItem)]
                if not hits and self._scene._locked_task is not None:
                    self._scene.set_highlighted_task(None)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
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

    def mouseReleaseEvent(self, event) -> None:
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
            # LABEL_WIDTH pixels on screen regardless of horizontal scroll.
            in_vp_label = (event.pos().x() < LABEL_WIDTH if self._scene._horizontal
                           else event.pos().y() < LABEL_WIDTH)
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
            self._do_zoom(factor, event.pos())
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

    def eventFilter(self, obj, e) -> bool:
        """Intercept native pinch-zoom gestures delivered to the viewport."""
        if obj is self.viewport() and e.type() == QEvent.NativeGesture:
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

    def event(self, e) -> bool:
        return super().event(e)

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        """Called by Qt on every scroll — reposition frozen label-column items."""
        super().scrollContentsBy(dx, dy)
        self._reposition_frozen()

    def _reposition_frozen(self) -> None:
        """Move all frozen label-column scene items so they stay at the left edge."""
        if not self._scene._frozen_items:
            return
        scene_left = self.mapToScene(QPoint(0, 0)).x()
        for item, orig_x in self._scene._frozen_items:
            item.setX(scene_left + orig_x)

    def _do_zoom(self, factor: float, vp_pos=None) -> None:
        """Zoom by factor, keeping vp_pos (viewport coords) fixed on screen."""
        if vp_pos is None:
            vp_pos = self.viewport().rect().center()
        # Convert anchor viewport position to ns coordinate
        scene_pt = self.mapToScene(vp_pos)
        center_ns = self._scene.scene_to_ns(scene_pt.x())
        # Compute the viewport-center offset from the anchor
        vp_center = self.viewport().rect().center()
        offset_x = vp_center.x() - vp_pos.x()

        self._scene.zoom(factor)
        self.zoom_changed.emit(self._scene.ns_per_px)

        # After rebuild, scroll so center_ns reappears at the same viewport x
        new_scene_x = self._scene.ns_to_scene_coord(center_ns)
        cur_scene_y = self.mapToScene(vp_center).y()
        self.centerOn(new_scene_x + offset_x, cur_scene_y)

# ===========================================================================
# Main Window
# ===========================================================================

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
            f"font-family: \"{_FIXED_FONT_FAMILY}\"; }}"
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
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._buttons.clear()
        self._delta_label = None

        if not times or trace is None:
            return

        ts     = trace.time_scale
        colors = ["#FF6666", "#66FF99", "#6699FF", "#FFBB44"]
        sorted_pairs = sorted(enumerate(times), key=lambda x: x[1])

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
                f"color:#FFFFFF; font-size:{_UI_FONT_SIZE}pt; font-family:\"{_FIXED_FONT_FAMILY}\"; padding:0 4px;"
            )
            self._layout.addWidget(dlbl)
            self._delta_label = dlbl

# ---------------------------------------------------------------------------
# Legend widget
# ---------------------------------------------------------------------------

class _LegendTaskRow(QWidget):
    """A single task row in the legend that emits hover/click signals."""

    hovered   = pyqtSignal(str)   # task raw name
    unhovered = pyqtSignal(str)   # task raw name
    clicked   = pyqtSignal(str)   # task raw name

    _BG_NORMAL  = "background: transparent;"
    _BG_HOVER   = "background: rgba(255,255,255,18); border-radius:3px;"
    _BG_LOCKED  = "background: rgba(255,215,0,45);  border-radius:3px;"

    def __init__(self, task_name: str, display_name: str,
                 color: QColor, parent=None):
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
        self._lbl.setToolTip(task_name)
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
        self.hovered.emit(self._task_name)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._locked:
            self._set_bg(self._BG_NORMAL)
        self.unhovered.emit(self._task_name)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._task_name)
        event.accept()   # prevent bubbling up to LegendWidget.mousePressEvent


class LegendWidget(QWidget):
    """Compact scrollable colour legend with hover/click → timeline highlight."""

    task_hovered     = pyqtSignal(str)   # hover enter: task raw name
    task_unhovered   = pyqtSignal(str)   # hover leave: task raw name
    task_clicked     = pyqtSignal(str)   # click: task raw name
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
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        header = QLabel("<b style='color:#AAAAAA'>Tasks</b>")
        header.setTextFormat(Qt.RichText)
        self._layout.addWidget(header)

        for task in trace.tasks:
            color = _task_colour(task)
            display = task_display_name(task)
            row = _LegendTaskRow(task, display, color)
            row.hovered.connect(self.task_hovered)
            row.unhovered.connect(self.task_unhovered)
            row.clicked.connect(self.task_clicked)
            self._task_rows[task] = row
            self._layout.addWidget(row)

        if trace.sti_channels:
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet("color:#444;")
            self._layout.addWidget(sep)

            hdr2 = QLabel("<b style='color:#88AABB'>STI Events</b>")
            hdr2.setTextFormat(Qt.RichText)
            self._layout.addWidget(hdr2)

            for note, color in [
                ("take_mutex",   _sti_colour("take_mutex")),
                ("give_mutex",   _sti_colour("give_mutex")),
                ("create_mutex", _sti_colour("create_mutex")),
                ("trigger",      _sti_colour("trigger")),
            ]:
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
# Main Window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self._trace: Optional[BtfTrace] = None
        self._current_file: str = ""
        self._settings = QSettings("btf_viewer", "btf_viewer")

        self.setWindowTitle("BTF Trace Viewer")
        self.resize(1280, 720)
        self._apply_dark_theme()
        self._build_ui()
        self._build_menus()
        self._build_toolbar()
        self._build_status_bar()
        self._view_mode = "task"

        # Apply saved font size before loading a file
        saved_fs = self._settings.value("font_size", _FONT_SIZE, int)
        if saved_fs != _FONT_SIZE:
            self._view.set_font_size(saved_fs)

        last = self._settings.value("last_file", "")
        if last and os.path.isfile(last):
            self._open_file(last)

    def _apply_dark_theme(self) -> None:
        app     = QApplication.instance()

        # Set the application-wide UI font to 12 pt (menus, toolbar, status bar).
        # Timeline task labels use _FONT_SIZE (14 pt) independently.
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
            QToolButton {{ font-size:{_ui_fs}; }}
            QStatusBar  {{ background:#1E1E1E; color:#AAAAAA; font-size:{_ui_fs}; }}
            QLabel      {{ font-size:{_ui_fs}; }}
            QCheckBox   {{ font-size:{_ui_fs}; }}
            QSpinBox    {{ font-size:{_ui_fs}; }}
            QDockWidget::title {{ background:#2D2D2D; color:#AAAAAA;
                                  padding:4px; font-size:{_ui_fs}; }}
            QScrollArea {{ background:#1E1E1E; border:none; }}
        """)

    def _build_ui(self) -> None:
        self._view = TimelineView(self)
        self._view.zoom_changed.connect(self._on_zoom_changed)
        self._view.cursors_changed.connect(self._on_cursors_changed)
        self._view.cursors_changed.connect(
            lambda times: self._cursor_bar.rebuild(times, self._trace)
        )
        self.setCentralWidget(self._view)

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

        # Legend hover → transient highlight; click → toggle locked highlight
        sc = self._view._scene
        self._legend.task_hovered.connect(
            lambda t: sc.set_highlighted_task(t, locked=False)
        )
        self._legend.task_unhovered.connect(lambda _t: sc.clear_hover())
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

        fm = mb.addMenu("&File")
        self._act_open = fm.addAction("&Open…", self._on_open, QKeySequence.Open)
        fm.addSeparator()
        self._act_save_img = fm.addAction("Save as &Image (PNG)…", self._on_save_image, "Ctrl+S")
        self._act_save_img.setEnabled(False)
        fm.addSeparator()
        fm.addAction("E&xit", self.close, QKeySequence.Quit)

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
        vm.addAction("&Reset zoom",     self._view.reset_zoom,"Ctrl+R")
        vm.addSeparator()
        self._act_legend = vm.addAction("Show &Legend")
        self._act_legend.setShortcut("Ctrl+L")
        self._act_legend.setCheckable(True)
        self._act_legend.setChecked(True)
        self._act_legend.toggled.connect(self._legend_dock.setVisible)
        self._legend_dock.visibilityChanged.connect(self._act_legend.setChecked)
        vm.addSeparator()
        self._act_task_view = vm.addAction("Task &View", lambda: self._set_view_mode("task"))
        self._act_core_view = vm.addAction("&Core View", lambda: self._set_view_mode("core"))
        self._act_task_view.setCheckable(True)
        self._act_core_view.setCheckable(True)
        self._act_task_view.setChecked(True)

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

        hm = mb.addMenu("&Help")
        hm.addAction("&About", self._on_about)

    def _build_toolbar(self) -> None:
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        tb.addAction("📂 Open",    self._on_open)
        tb.addAction("💾 Save PNG", self._on_save_image)
        tb.addSeparator()
        tb.addAction("↔ Horizontal", lambda: self._set_orientation(True))
        tb.addAction("↕ Vertical",   lambda: self._set_orientation(False))
        tb.addSeparator()
        tb.addAction("🔍+",     self._view.zoom_in)
        tb.addAction("🔍-",     self._view.zoom_out)
        tb.addAction("⊡ Fit",   self._view.zoom_fit)
        tb.addAction("⟳ Reset", self._view.reset_zoom)
        tb.addSeparator()

        self._tb_task_btn = tb.addAction("Task View", lambda: self._set_view_mode("task"))
        self._tb_core_btn = tb.addAction("Core View", lambda: self._set_view_mode("core"))
        self._tb_task_btn.setCheckable(True)
        self._tb_core_btn.setCheckable(True)
        self._tb_task_btn.setChecked(True)
        tb.addSeparator()

        tb.addAction("│C Place cursor", self._view.add_cursor_at_view_center)
        tb.addAction("✕ Clear cursors", self._view.clear_cursors)
        tb.addSeparator()
        self._tb_legend_btn = tb.addAction("📋 Legend", lambda: self._act_legend.toggle())
        self._tb_legend_btn.setCheckable(True)
        self._tb_legend_btn.setChecked(True)
        self._tb_legend_btn.setToolTip("Show / hide the Legend panel  (Ctrl+L)")
        self._legend_dock.visibilityChanged.connect(self._tb_legend_btn.setChecked)
        tb.addSeparator()

        self._zoom_label = QLabel("Zoom: —")
        self._zoom_label.setStyleSheet("color:#AAAAAA; padding: 0 8px;")
        tb.addWidget(self._zoom_label)

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
        self._font_spin.setValue(self._settings.value("font_size", _FONT_SIZE, int))
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
        self._status_file  = QLabel("No file loaded")
        self._status_stats = QLabel("")
        self._cursor_bar   = CursorBarWidget()
        self._cursor_bar.jump_requested.connect(self._view.scroll_to_ns)
        self._cursor_bar.cursor_delete_requested.connect(self._on_cursor_delete)
        self._status_hint  = QLabel(
            "Left-click: place cursor  |  Drag cursor: move it  |  "
            "Right-click: remove  |  Ctrl+Wheel / Pinch: zoom  |  Scroll: pan"
        )
        self._status_hint.setStyleSheet("color:#666;")
        sb.addWidget(self._status_file)
        sb.addPermanentWidget(self._cursor_bar)
        sb.addPermanentWidget(self._status_stats)
        sb.addPermanentWidget(self._status_hint)

    # ------------------------------------------------------------------
    # Slots / callbacks
    # ------------------------------------------------------------------

    def _on_open(self) -> None:
        last_dir = self._settings.value("last_dir", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(
            self, "Open BTF trace", last_dir,
            "BTF files (*.btf);;All files (*)"
        )
        if path:
            self._open_file(path)

    def _open_file(self, path: str) -> None:
        try:
            trace = parse_btf(path)
        except Exception as exc:
            QMessageBox.critical(self, "Parse Error", f"Failed to parse:\n{path}\n\n{exc}")
            return

        self._trace = trace
        self._current_file = path
        self._settings.setValue("last_file", path)
        self._settings.setValue("last_dir",  os.path.dirname(path))

        self._view.load_trace(trace)
        self._legend.rebuild(trace)
        self._act_save_img.setEnabled(True)

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

    def _set_orientation(self, horizontal: bool) -> None:
        self._act_horiz.setChecked(horizontal)
        self._act_vert.setChecked(not horizontal)
        self._view.set_horizontal(horizontal)

    def _set_view_mode(self, mode: str) -> None:
        self._view_mode = mode
        is_task = (mode == "task")
        self._act_task_view.setChecked(is_task)
        self._act_core_view.setChecked(not is_task)
        self._tb_task_btn.setChecked(is_task)
        self._tb_core_btn.setChecked(not is_task)
        self._view.set_view_mode(mode)

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
        self._settings.setValue("font_size", size)

    def _on_zoom_changed(self, ns_per_px: float) -> None:
        if ns_per_px >= 1_000_000:
            z = f"{ns_per_px/1_000_000:.1f} ms/px"
        elif ns_per_px >= 1_000:
            z = f"{ns_per_px/1_000:.1f} µs/px"
        else:
            z = f"{ns_per_px:.1f} ns/px"
        self._zoom_label.setText(f"Zoom: {z}")

    def _on_cursors_changed(self, times) -> None:
        pass

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
        QMessageBox.about(
            self, "About BTF Trace Viewer",
            "<h3>BTF Trace Viewer</h3>"
            "<p>FreeRTOS context-switch visualiser for .btf files.</p>"
            "<p><b>View modes:</b><br>"
            "• <b>Task View</b> – one row per task<br>"
            "• <b>Core View</b> – one expandable row per CPU core</p>"
            "<p><b>Controls:</b><br>"
            "• <b>Left-click</b> – place cursor  |  <b>Drag</b> cursor line – move it<br>"
            "• <b>Right-click</b> – remove cursor  |  <b>Status badge</b> – jump to cursor<br>"
            "• <b>Ctrl+Wheel</b> / pinch – zoom  |  <b>Scroll</b> – pan<br>"
            "• <b>Ctrl+0</b> – fit  |  <b>Ctrl+R</b> – reset zoom</p>"
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
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps,   True)

    app = QApplication(sys.argv)
    app.setApplicationName("BTF Trace Viewer")
    app.setOrganizationName("btf_viewer")

    win = MainWindow()
    win.show()

    if len(sys.argv) > 1:
        path = sys.argv[1]
        if os.path.isfile(path):
            win._open_file(path)

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
