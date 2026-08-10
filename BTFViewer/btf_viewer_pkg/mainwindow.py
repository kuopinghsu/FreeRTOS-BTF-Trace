"""BTF Viewer — mainwindow module (source). Do not edit btf_viewer.py; run make bundle."""
from __future__ import annotations

from ._imports import *  # noqa: F403,F401
from .config import *  # noqa: F403,F401
from .parser import *  # noqa: F403,F401
from .timeline_util import *  # noqa: F403,F401
from .graphics_items import *  # noqa: F403,F401
from .scene import *  # noqa: F403,F401
from .view import *  # noqa: F403,F401
from .stats import *  # noqa: F403,F401
from .stats import _RcSettings, _parse_task_deadlines_text, _AnalysisFindingsDialog, _format_analysis_findings_text
from .ai_assistant import (
    create_ai_assistant_panel,
    AI_PRESET_FIELDS,
    AI_PRESETS,
    DEFAULT_AI_PRESET,
    DEFAULT_AI_RESPONSE_LANGUAGE,
    ai_jump_annotation_note,
    migrate_ai_settings,
    normalize_ai_preset,
)
from .mvvm import MainViewModel, MvvmSettingsMixin, TraceTabViewModel
from .mvvm.tab_viewport import apply_viewport, viewport_from_json, viewport_to_json
from .trace_quality import trace_quality_summary
from .perfetto_export import export_perfetto

class _CpuLoadScrollArea(QScrollArea):
    """Scroll host for the CPU load graph — pane height comes from the splitter, not row count."""

    _MIN_PANE_H = 40

    def minimumSize(self) -> "QSize":  # noqa: N802
        return QSize(200, self._MIN_PANE_H)

    def minimumSizeHint(self) -> "QSize":  # noqa: N802
        return QSize(200, self._MIN_PANE_H)

    def sizeHint(self) -> "QSize":  # noqa: N802
        return QSize(200, self._MIN_PANE_H)

class _CpuLoadGraph(QWidget):
    """Synchronised CPU load chart below the main timeline.

    View modes
    ----------
    Task view + no selection  -> 1 row: total CPU usage across all cores
    Task view + task selected -> 1 row: selected task's CPU usage
    Core view + no selection  -> 1 row per core at full row height
    Core view + task selected -> 1 row per core showing that task's usage on each core

    Rows can be collapsed (core view only): collapsed height = CPU_LOAD_COLLAPSED_H px,
    label still visible. Click label to toggle. The title-bar icon expands/collapses
    all CPU load core rows independently of the task timeline.
    """

    expand_all_toggled = Signal(bool)
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
        self._bin_w_ns: float                               = 1.0
        self._font_size: int                                = 8
        self._time_decimals: int                             = 3
        self._hover_y: int                                  = -1
        self._title_icon_rect: Optional[QRect]               = None
        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.setMouseTracking(True)
        self._scroll_area: Optional["QScrollArea"] = None
        self._sync_scroll_size_guard: bool = False
        self._sync_scroll_size_timer = QTimer(self)
        self._sync_scroll_size_timer.setSingleShot(True)
        self._sync_scroll_size_timer.timeout.connect(self._sync_scroll_size)
        # QPixmap cache for the static bars/labels/grid/overlay content.
        # Only the hover overlay is drawn outside the cache.
        self._bars_pm: Optional["QPixmap"] = None
        self._bars_pm_key: object = None
        self.setToolTip(
            "CPU load over time - synchronised with timeline\n"
            "Core view: title icon expands/collapses all cores; "
            "click a label to toggle one core row"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_trace(self, trace) -> None:
        # Same object: tab switch / chrome re-sync. Keep the lock-highlight
        # filter and skip bin rebuild (bins are derived from this trace).
        if trace is self._trace:
            self._bars_pm_key = None
            self.updateGeometry()
            self.update()
            return
        self._trace           = trace
        self._selected_task   = None
        self._collapsed_cores = set()
        self._core_bins       = {}
        self._task_bins       = {}
        self._task_core_bins  = {}
        self._total_bins      = []
        self._bars_pm_key     = None      # invalidate paint cache
        if trace is not None:
            self._compute_bins(trace)
        self.updateGeometry()
        self.update()

    def set_task(self, task_name, locked: bool) -> None:
        self._selected_task = task_name if (locked and task_name) else None
        self._bars_pm_key   = None        # invalidate paint cache
        self.updateGeometry()
        self.update()

    def set_dark(self, is_dark: bool) -> None:
        self._is_dark     = is_dark
        self._bars_pm_key = None          # invalidate paint cache
        self.update()

    def set_view_mode(self, mode: str) -> None:
        self._view_mode   = mode
        self._bars_pm_key = None          # invalidate paint cache
        self.updateGeometry()
        self.update()

    def set_row_h(self, h: int) -> None:
        self._row_h       = max(12, h)
        self._bars_pm_key = None          # invalidate paint cache
        self.updateGeometry()
        self.update()

    def set_font_size(self, size: int) -> None:
        self._font_size = max(6, size)
        self.update()

    def set_time_decimals(self, n: int) -> None:
        self._time_decimals = max(0, min(int(n), 9))
        self.update()

    def set_core_expanded(self, core: str, expanded: bool) -> None:
        if expanded:
            self._collapsed_cores.discard(core)
        else:
            self._collapsed_cores.add(core)
        self._schedule_sync_scroll_size()
        self.update()

    def set_all_expanded(self, expanded: bool) -> None:
        if expanded:
            self._collapsed_cores.clear()
        else:
            if self._trace:
                self._collapsed_cores = set(self._trace.core_names or [])
        self._schedule_sync_scroll_size()
        self.update()

    def _all_cores_expanded(self) -> bool:
        cores = (self._trace.core_names or []) if self._trace else []
        if len(cores) <= 1:
            return True
        return all(c not in self._collapsed_cores for c in cores)

    def _title_expand_icon_rect(self, fm_title: QFontMetrics) -> QRect:
        text_w = fm_title.horizontalAdvance("CPU LOAD")
        icon_x = 4 + text_w + 6
        return QRect(icon_x, 4, 14, 14)

    def _toggle_title_expand_all(self) -> None:
        new_expanded = not self._all_cores_expanded()
        self.set_all_expanded(new_expanded)
        self.expand_all_toggled.emit(new_expanded)

    # ------------------------------------------------------------------
    # Size hint - drives QScrollArea scrollbar
    # ------------------------------------------------------------------

    def preferred_pane_height(self) -> int:
        """Height for autofit / splitter sizing — not the inner widget geometry."""
        content = max(40, self._content_height())
        return min(content + 6, CPU_LOAD_PANE_MAX_H)

    def sizeHint(self) -> "QSize":
        # Viewport-sized — preferred_pane_height() is for autofit / splitter only.
        h = self.height() if self.height() >= 40 else 40
        return QSize(max(200, self.width() if self.width() > 0 else 200), h)

    def minimumSize(self) -> "QSize":
        return QSize(200, 40)

    def minimumSizeHint(self) -> "QSize":
        return QSize(200, 40)

    def _content_height(self) -> int:
        _TITLE_H = 22
        rows = self._get_rows()
        return _TITLE_H + sum(
            self._row_effective_h(k, key) + CPU_LOAD_ROW_GAP for k, key, _, _ in rows
        )

    def _splitter_drag_active(self) -> bool:
        win = self.window()
        return bool(getattr(win, "_cpu_splitter_resizing", False))

    def _schedule_sync_scroll_size(self) -> None:
        """Coalesce scroll-area resize/layout updates (avoids splitter-drag loops)."""
        if self._splitter_drag_active():
            return
        self._sync_scroll_size_timer.start(0)

    def _sync_scroll_size(self) -> None:
        """Size the graph to full row content so QScrollArea shows a vertical bar."""
        if self._sync_scroll_size_guard or self._splitter_drag_active():
            return
        scroll = self._scroll_area
        if scroll is None:
            return
        vp = scroll.viewport()
        if vp is None or vp.width() <= 0:
            return
        w = max(1, vp.width())
        h = max(40, self._content_height())
        if self.width() == w and self.height() == h:
            return
        self._sync_scroll_size_guard = True
        try:
            self.resize(w, h)
        finally:
            self._sync_scroll_size_guard = False

    def updateGeometry(self) -> None:  # noqa: N802
        super().updateGeometry()
        self._schedule_sync_scroll_size()

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

    # ------------------------------------------------------------------
    # Row helpers
    # ------------------------------------------------------------------

    def _scene(self):
        return self._view._scene if self._view else None

    def _filtered_task_merge_keys(self) -> List[str]:
        sc = self._scene()
        if sc is None or self._trace is None or not sc._core_view_task_filter_active():
            return []
        return [t for t in self._trace.tasks if sc._task_merge_key_matches_filter(t)]

    def _aggregate_filtered_task_bins(self, merge_keys: List[str]) -> Optional[List[float]]:
        if not merge_keys or self._trace is None:
            return None
        n = self._NUM_BINS
        n_cores = max(1, len(self._trace.core_names or []))
        out = [0.0] * n
        any_bins = False
        for mk in merge_keys:
            bins = self._task_bins.get(mk)
            if not bins:
                continue
            any_bins = True
            for i in range(n):
                out[i] += bins[i]
        if not any_bins:
            return None
        for i in range(n):
            out[i] = min(1.0, out[i] / n_cores)
        return out

    def _aggregate_filtered_task_core_bins(self, merge_keys: List[str],
                                          core: str) -> Optional[List[float]]:
        if not merge_keys or not core:
            return None
        n = self._NUM_BINS
        out = [0.0] * n
        any_bins = False
        for mk in merge_keys:
            bins = self._task_core_bins.get(mk, {}).get(core)
            if not bins:
                continue
            any_bins = True
            for i in range(n):
                out[i] += bins[i]
        if not any_bins:
            return None
        for i in range(n):
            out[i] = min(1.0, out[i])
        return out

    def _get_rows(self) -> List[tuple]:
        """Return [(kind, key, label, QColor), ...] for currently displayed rows."""
        if not self._trace:
            return []
        task  = self._selected_task
        cores = self._trace.core_names or []
        filter_keys = self._filtered_task_merge_keys()
        filter_active = bool(filter_keys)

        if task:
            # Locked/selected task → always show that task's usage per core.
            return [("core", c, c, QColor(_core_color(c))) for c in cores]

        if filter_active:
            if self._view_mode == "task":
                return [("filtered", "filtered", "CPU Load", QColor("#4CAF50"))]
            sc = self._scene()
            core_names = sc._filtered_core_view_tasks()[0] if sc else cores
            return [("core", c, c, QColor(_core_color(c))) for c in core_names]

        if self._view_mode == "task":
            return [("total", "total", "CPU Load", QColor("#4CAF50"))]

        # Core view - one row per core (all tasks on core)
        return [("core", c, c, QColor(_core_color(c))) for c in cores]

    def _row_effective_h(self, kind: str, key: str) -> int:
        if kind == "core" and key in self._collapsed_cores:
            return CPU_LOAD_COLLAPSED_H
        return self._row_h

    def _bins_for_row(self, kind: str, key: str):
        task = self._selected_task
        if kind == "filtered":
            return self._aggregate_filtered_task_bins(self._filtered_task_merge_keys())
        if kind == "total":
            return self._total_bins or None
        if kind == "task":
            return self._task_bins.get(key)
        # "core" - selected task on core, or filtered tasks on core, or all tasks
        if task:
            return self._task_core_bins.get(task, {}).get(key)
        filter_keys = self._filtered_task_merge_keys()
        if kind == "core" and filter_keys:
            return self._aggregate_filtered_task_core_bins(filter_keys, key)
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
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(bx, by, tw, 12, 2, 2)
        painter.setPen(fg)
        sf = _monospace_font(max(5, self._font_size - (1 if full else 2)))
        painter.setFont(sf)
        painter.drawText(QRect(bx + 4, by, tw - 8, 12), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

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
        pen = QPen(color, width, Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine)
        if dashed and pen.style() == Qt.PenStyle.DashLine:
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
        if (event.button() == Qt.MouseButton.LeftButton
                and self._trace and self._view_mode == "core"):
            pt = event.position().toPoint()
            if (self._title_icon_rect is not None
                    and self._title_icon_rect.contains(pt)):
                self._toggle_title_expand_all()
                event.accept()
                return
            if event.position().x() < scene._label_width:
                _TITLE_H = 22
                ry = _TITLE_H
                for kind, key, _, _ in self._get_rows():
                    rh = self._row_effective_h(kind, key)
                    if ry <= event.position().y() < ry + rh:
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
        hover_ns = self._time_ns_at_pos(event.position().toPoint())
        if hover_ns is None:
            self._hover_y = -1
            scene.clear_hover_line()
        else:
            self._hover_y = event.position().y()
            scene._hover_ns = hover_ns
            scene._draw_hover_line()
            self.update()
        pt = event.position().toPoint()
        if (self._title_icon_rect is not None
                and self._title_icon_rect.contains(pt)):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif self.cursor().shape() == Qt.CursorShape.PointingHandCursor:
            self.unsetCursor()
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
                   if hasattr(event, "position") else event.position().toPoint())
        if source is not None:
            pos = self._graph_pos_from(pos, source)

        mods = event.modifiers()
        zoom_mod = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
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
                and not (mods & Qt.KeyboardModifier.ShiftModifier)
                and abs(dy) >= abs(dx)):
            vp = scroll.viewport()
            if self.height() > vp.height():
                vsb = scroll.verticalScrollBar()
                vsb.setValue(vsb.value() - dy)
                event.accept()
                return

        hsb = self._view.horizontalScrollBar()
        vsb = self._view.verticalScrollBar()
        if mods & Qt.KeyboardModifier.ShiftModifier:
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

    def _draw_static_content(self, p: "QPainter", w: int, h: int, dark: bool,
                              bg: "QColor", scene, tpp: float, lw: int,
                              vis_ns_lo: int, vis_ns_hi: int) -> None:
        """Render bars, labels, grid and overlays (marks/cursors) into *p*.
        Called on cache miss; the hover overlay is painted separately on top."""
        t_min  = self._trace.time_min
        t_max  = self._trace.time_max
        n      = self._NUM_BINS
        bin_w  = self._bin_w_ns

        rows       = self._get_rows()
        plot_right = self._plot_right_x()

        sepc = QColor("#444444") if dark else QColor("#AAAAAA")
        txtc = QColor("#AAAAAA") if dark else QColor("#444444")
        grdc = QColor("#2E2E2E") if dark else QColor("#D0D0D0")

        vis_span   = max(1, vis_ns_hi - vis_ns_lo)
        cursor_rng = self._cursor_range_ns(scene)

        # Pre-compute pixel→bin runs, shared across all rows.
        # Adjacent pixels that map to the same bin are merged into one run so
        # bar rendering makes one drawRect per run instead of one per pixel.
        # At 1:1 zoom (few bins visible) this reduces ~1760 calls to ~24;
        # at fit zoom the saving is smaller but the loop cost is the same.
        # Each run: (start_sx, run_width, bin_index)
        axis_span = self._plot_axis_span(lw)
        px_runs: List[Tuple[int, int, int]] = []
        if axis_span > 0:
            bi_per_px  = vis_span / axis_span / bin_w
            bi_float   = max(0.0, (vis_ns_lo - t_min) / bin_w)
            run_start  = lw
            run_bi     = -1
            sx_limit   = min(w, plot_right)
            for sx in range(lw, sx_limit):
                bi = int(bi_float)
                bi = bi if 0 <= bi < n else (0 if bi < 0 else n - 1)
                if bi != run_bi:
                    if run_bi >= 0:
                        px_runs.append((run_start, sx - run_start, run_bi))
                    run_start = sx
                    run_bi    = bi
                bi_float += bi_per_px
            if run_bi >= 0:
                px_runs.append((run_start, sx_limit - run_start, run_bi))

        _TITLE_H  = 22
        sf_title  = _monospace_font(self._font_size)
        sf_norm   = _monospace_font(self._font_size)
        sf_small  = _monospace_font(max(6, self._font_size - 1))
        sf_pct    = _monospace_font(max(5, self._font_size - 3))
        fm_pct    = QFontMetrics(sf_pct)   # computed once outside the row loop
        pct_muted = QColor("#555555") if dark else QColor("#AAAAAA")
        white_col = QColor("#FFFFFF") if dark else QColor("#111111")
        green_col = QColor("#4CAF50")

        # -- Title bar -------------------------------------------------------
        p.setFont(sf_title)
        p.setPen(txtc)
        p.drawText(QRect(4, 0, lw - 6, _TITLE_H),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "CPU LOAD")
        cores = (self._trace.core_names or []) if self._trace else []
        if self._view_mode == "core" and len(cores) > 1:
            fm_title = QFontMetrics(sf_title)
            all_exp  = self._all_cores_expanded()
            path     = _IC_SECTIONS_EXPAND if not all_exp else _IC_SECTIONS_COLLAPSE
            icon_col = "#AAAAAA" if dark else "#666666"
            ico      = _svg_icon(path, icon_col, 12)
            self._title_icon_rect = self._title_expand_icon_rect(fm_title)
            ico.paint(p, self._title_icon_rect)
        else:
            self._title_icon_rect = None
        p.setPen(QPen(sepc, 1))
        p.drawLine(0, _TITLE_H, w, _TITLE_H)

        ry = _TITLE_H
        for kind, key, lbl_text, color in rows:
            rh = self._row_effective_h(kind, key)
            if ry >= h:
                break
            effective_h = min(rh, h - ry)
            collapsed   = (kind == "core" and key in self._collapsed_cores)
            bins     = self._bins_for_row(kind, key)   # called once; reused below
            vis_avg  = self._avg_bins_in_ns_range(bins, vis_ns_lo, vis_ns_hi)
            pct_text = f"{vis_avg * 100:.0f}%"
            if cursor_rng is not None:
                cr_avg = self._avg_bins_in_ns_range(
                    bins, cursor_rng[0], cursor_rng[1])
                pct_text = f"{pct_text} · C:{cr_avg * 100:.0f}%"
            indicator = "▶" if collapsed else "▼"

            dot_r  = min(5, effective_h // 4)
            dot_cy = ry + effective_h // 2

            # 1. Collapse/expand triangle
            p.setFont(sf_small if collapsed else sf_norm)
            p.setPen(white_col)
            p.drawText(QRect(2, ry, 14, effective_h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, indicator)

            # 2. Coloured dot
            dot_cx = 20 + dot_r
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
            p.drawEllipse(dot_cx - dot_r, dot_cy - dot_r, dot_r * 2, dot_r * 2)
            p.setRenderHint(QPainter.Antialiasing, False)

            # 3. Row label
            name_x = dot_cx + dot_r + 4
            p.setFont(sf_pct)
            pct_col_w = min(
                max(CPU_LOAD_PCT_COL_MIN,
                    fm_pct.horizontalAdvance(pct_text) + CPU_LOAD_PCT_COL_PAD),
                max(CPU_LOAD_PCT_COL_MIN, lw - name_x - 8),
            )
            p.setFont(sf_small if collapsed else sf_norm)
            p.setPen(white_col)
            name_w = max(0, lw - name_x - pct_col_w - 6)
            p.drawText(QRect(name_x, ry, name_w, effective_h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, lbl_text)

            # 4. Percentage label
            p.setFont(sf_pct)
            p.setPen(green_col)
            p.drawText(QRect(lw - pct_col_w - 4, ry, pct_col_w, effective_h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, pct_text)

            if not collapsed:
                # Grid lines at 25/50/75/100%
                p.setFont(sf_pct)
                p.setPen(pct_muted)
                p.drawText(QRect(lw + 3, ry + effective_h - 12, 28, 12),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, "0")
                for pct in (0.25, 0.5, 0.75, 1.0):
                    gy = ry + effective_h - 1 - int(pct * effective_h)
                    p.setPen(QPen(grdc, 1, Qt.PenStyle.DotLine))
                    p.drawLine(lw + 1, gy, plot_right, gy)
                    if pct < 1.0:
                        p.setPen(pct_muted)
                        p.drawText(QRect(lw + 3, gy - 12, 28, 12),
                                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                                   str(int(pct * 100)))

                # Load bars — one drawRect per run of same-bin pixels.
                if bins:  # reuse bins fetched above for pct_text
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(color))
                    bottom = ry + effective_h
                    for run_sx, run_w, bi in px_runs:
                        load = bins[bi]
                        if load <= 0.001:
                            continue
                        bh = max(1, int(load * effective_h))
                        p.drawRect(run_sx, bottom - bh, run_w, bh)

                # Cursor-range shading
                if cursor_rng is not None:
                    cr_lo, cr_hi = cursor_rng
                    shade_lo = max(vis_ns_lo, cr_lo)
                    shade_hi = min(vis_ns_hi, cr_hi)
                    if shade_hi > shade_lo:
                        sx0 = self._time_overlay_x(shade_lo, scene, vis_ns_lo, vis_ns_hi)
                        sx1 = self._time_overlay_x(shade_hi, scene, vis_ns_lo, vis_ns_hi)
                        if sx1 > sx0:
                            shade = (QColor(68, 153, 255, 72) if dark
                                     else QColor(42, 111, 178, 58))
                            p.fillRect(sx0, ry + 1, sx1 - sx0, effective_h - 2, shade)

            # Row separator
            p.setPen(QPen(sepc, 1))
            p.drawLine(0, ry + effective_h, w, ry + effective_h)
            ry += rh + CPU_LOAD_ROW_GAP

        # -- Overlay: bookmarks & annotations --------------------------------
        if hasattr(scene, '_mark_data') and tpp > 0:
            for m_ns, _m_lbl, m_color_hex, m_kind, _m_id in scene._mark_data:
                sx  = self._time_overlay_x(m_ns, scene, vis_ns_lo, vis_ns_hi)
                col = QColor(m_color_hex)
                self._draw_time_overlay_line(
                    p, scene, sx, _TITLE_H, plot_right, col,
                    dashed=(m_kind != "bookmark"),
                    width=1.2 if m_kind == "bookmark" else 1.0,
                )

        # -- Overlay: placed cursors -----------------------------------------
        if hasattr(scene, '_cursor_times') and tpp > 0:
            cursor_palette = _cursor_colors(dark)
            for c_idx, c_ns in enumerate(scene._cursor_times):
                sx      = self._time_overlay_x(c_ns, scene, vis_ns_lo, vis_ns_hi)
                cur_col = QColor(cursor_palette[c_idx % len(cursor_palette)])
                self._draw_time_overlay_line(
                    p, scene, sx, _TITLE_H, plot_right, cur_col,
                    dashed=True, width=1.2,
                )

        # Label column separator (full height)
        p.setPen(QPen(sepc, 1))
        p.drawLine(lw, 0, lw, h)
        if w > plot_right:
            p.fillRect(plot_right, 0, w - plot_right, h, bg)

    def paintEvent(self, event) -> None:  # noqa: N802
        dark = self._is_dark
        bg   = QColor("#1E1E1E") if dark else QColor("#F5F5F5")
        w    = self.width()
        h    = self.height()

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)

        scene = self._view._scene
        if self._trace is None or scene is None:
            p.fillRect(0, 0, w, h, bg)
            p.end()
            return
        if not (hasattr(scene, '_timescale_per_px') and hasattr(scene, '_label_width')):
            p.fillRect(0, 0, w, h, bg)
            p.end()
            return

        tpp = scene._timescale_per_px
        lw  = int(scene._label_width)
        if tpp <= 0:
            p.fillRect(0, 0, w, h, bg)
            p.end()
            return

        vis_ns_lo, vis_ns_hi = self._visible_time_ns_range(scene)

        # Build the cache key for all static content.
        # Hover overlay is excluded — it is always rendered fresh on top.
        filter_keys  = tuple(self._filtered_task_merge_keys())
        cursor_times = tuple(getattr(scene, '_cursor_times', ()) or ())
        mark_data    = tuple(getattr(scene, '_mark_data',    ()) or ())

        pm_key = (
            vis_ns_lo, vis_ns_hi, w, h, lw,
            self._row_h, self._is_dark, self._view_mode,
            self._selected_task, id(self._trace),
            tuple(sorted(self._collapsed_cores)),
            filter_keys,
            cursor_times,
            mark_data,
        )

        # Render static content into the pixmap only on cache miss.
        # Reuse the existing buffer when dimensions are unchanged to avoid
        # a per-frame QPixmap allocation during scrolling.
        if pm_key != self._bars_pm_key:
            if (self._bars_pm is None
                    or self._bars_pm.width() != w
                    or self._bars_pm.height() != h):
                self._bars_pm = QPixmap(max(1, w), max(1, h))
            pm_p = QPainter(self._bars_pm)
            pm_p.setRenderHint(QPainter.Antialiasing, False)
            pm_p.fillRect(0, 0, w, h, bg)
            self._draw_static_content(pm_p, w, h, dark, bg, scene, tpp, lw,
                                      vis_ns_lo, vis_ns_hi)
            pm_p.end()
            self._bars_pm_key = pm_key

        # Blit the cached static pixmap.
        p.drawPixmap(0, 0, self._bars_pm)

        # Hover overlay — rendered fresh every repaint so cursor movement is instant.
        hover_ns  = getattr(scene, '_hover_ns', None)
        if hover_ns is not None and tpp > 0:
            rows       = self._get_rows()
            plot_right = self._plot_right_x()
            _TITLE_H   = 22
            hover_row  = self._row_at_y(self._hover_y) if self._hover_y >= 0 else None
            sx         = self._time_overlay_x(hover_ns, scene, vis_ns_lo, vis_ns_hi)
            hov_col    = (QColor(255, 255, 255, 80) if dark
                          else QColor(0, 102, 204, 200))
            self._draw_time_overlay_line(
                p, scene, sx, _TITLE_H, plot_right, hov_col,
                dashed=True, width=1.0,
            )
            ry_h  = _TITLE_H
            scale = self._trace.time_scale
            for kind, key, _lbl_text, _color in rows:
                rh        = self._row_effective_h(kind, key)
                collapsed = (kind == "core" and key in self._collapsed_cores)
                if not collapsed and lw <= sx < plot_right:
                    bins_h   = self._bins_for_row(kind, key)
                    load     = self._load_at_ns(bins_h, hover_ns)
                    load_pct = f"{load * 100:.0f}%"
                    is_primary = (hover_row is not None
                                  and hover_row[0] == kind and hover_row[1] == key)
                    badge = (f"{load_pct} · {_format_time(hover_ns, scale, decimals=self._time_decimals)}"
                             if is_primary else load_pct)
                    self._draw_load_badge(p, sx, ry_h, badge, dark, full=is_primary)
                ry_h += rh + CPU_LOAD_ROW_GAP

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

def _new_fusion_base_style() -> QStyle:
    """Return a Fusion style for macOS tab-bar proxy styling.

    Each QProxyStyle must own a distinct base style; reusing one Fusion instance
    across multiple proxies deletes the shared C++ object after the first proxy
    is constructed.
    """
    return QStyleFactory.create("Fusion") or QApplication.style()

class _LeftTabStyle(QProxyStyle):
    """Force left tab-bar alignment (ignored by the macOS native QStyle)."""

    def __init__(self, base: Optional[QStyle] = None) -> None:
        if base is None:
            base = _new_fusion_base_style()
        super().__init__(base)
        self._base_style = base

    def styleHint(self, hint, option=None, widget=None, returnData=None):  # noqa: N802
        if hint == QStyle.StyleHint.SH_TabBar_Alignment:
            return int(Qt.AlignmentFlag.AlignLeft)
        return super().styleHint(hint, option, widget, returnData)

class _LeftAlignedTabBar(QTabBar):
    """Tab bar that stays left-aligned (macOS native style centers tabs by default)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setExpanding(False)
        if sys.platform == "darwin":
            self.setStyle(_LeftTabStyle())

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.setExpanding(False)

class _TimelinePane(QWidget):
    """Task timeline + dedicated time scrollbar row (below the canvas, above CPU split)."""

    def __init__(self, view: "TimelineView", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.view = view
        self.time_scroll = QScrollBar(Qt.Orientation.Horizontal, self)
        self.time_scroll.hide()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, TIMELINE_SPLITTER_GAP)
        lay.setSpacing(0)
        lay.addWidget(view, 1)
        lay.addWidget(self.time_scroll, 0)
        view.attach_time_scroll_bar(self.time_scroll)

class _CpuLoadStack(QWidget):
    """Timeline fills the pane; CPU load overlays the bottom.

    Show/hide never changes the timeline widget geometry, so QGraphicsView does
    not rebuild or repaint on Load toggle (the desktop cost vs the web ``v-if``).

    The overlay stops short of the task-axis scrollbar (right edge in the default
    horizontal layout) so the thumb stays visible when scrolled into the overlay
    band. Scene orth padding (``_nav_bottom_inset``) still lets last rows clear
    the strip.
    """

    splitterMoved = Signal(int, int)  # pos, index — QSplitter-compatible

    def __init__(
        self,
        timeline_pane: QWidget,
        cpu_scroll: QWidget,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._timeline = timeline_pane
        self._cpu = cpu_scroll
        self._handle = QWidget(self)
        self._handle.setObjectName("cpu_load_handle")
        self._handle.setCursor(Qt.CursorShape.SplitVCursor)
        self._handle_h = 6
        self._cpu_h = CPU_LOAD_ROW_H
        self._cpu_visible = True
        self._dragging = False
        self._drag_global_y = 0
        self._drag_h0 = 0
        self._timeline.setParent(self)
        self._cpu.setParent(self)
        self._handle.setParent(self)
        self._handle.installEventFilter(self)
        self._handle.setAutoFillBackground(True)

    def handle(self, index: int = 1) -> QWidget:  # noqa: ARG002
        return self._handle

    def handleWidth(self) -> int:
        return self._handle_h

    def setSizes(self, sizes: List[int]) -> None:
        if len(sizes) >= 2 and sizes[1] > 0:
            self._cpu_h = int(sizes[1])
        self._reposition()

    def sizes(self) -> List[int]:
        h = max(self.height(), 0)
        if not self._cpu_visible:
            return [h, 0]
        cpu_h = self._cpu.height() if self._cpu.isVisible() else max(self._cpu_h, 0)
        return [max(0, h - cpu_h - self._handle_h), cpu_h]

    def set_cpu_visible(self, visible: bool) -> None:
        """Show or hide the CPU overlay without resizing the timeline."""
        visible = bool(visible)
        if self._cpu_visible == visible:
            if visible:
                self._reposition()
            return
        self._cpu_visible = visible
        self._reposition()

    def cpu_visible(self) -> bool:
        return self._cpu_visible

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reposition()

    def _orth_vbar_gutter_px(self) -> int:
        """Right inset so the task-axis vertical scrollbar is not covered.

        Default (horizontal) layout scrolls tasks with the view's vertical bar.
        Leave that strip clear; the timeline keeps full width underneath.
        """
        view = getattr(self._timeline, "view", None)
        if view is None:
            return 0
        scene = getattr(view, "_scene", None)
        if scene is not None and not getattr(scene, "_horizontal", True):
            # Vertical time axis: orth scroll is the bottom horizontal bar —
            # a right inset would not help; keep full-width overlay.
            return 0
        bar = view.verticalScrollBar()
        if bar is None:
            return 0
        # Prefer geometry in stack coords (includes view frame / layout offsets).
        if bar.isVisible() and bar.width() > 0 and self.width() > 0:
            bar_left = bar.mapTo(self, QPoint(0, 0)).x()
            return max(0, self.width() - bar_left)
        hint = bar.sizeHint().width()
        return max(0, int(hint))

    def _reposition(self) -> None:
        w = max(self.width(), 0)
        h = max(self.height(), 0)
        # Timeline always fills the stack — toggle must not change this geometry.
        self._timeline.setGeometry(0, 0, w, h)
        if not self._cpu_visible or h <= 0 or w <= 0:
            self._handle.hide()
            self._cpu.hide()
            self._sync_nav_bottom_inset(0)
            return
        max_cpu = max(40, h - 100 - self._handle_h)
        cpu_h = max(
            _CpuLoadScrollArea._MIN_PANE_H,
            min(int(self._cpu_h), CPU_LOAD_PANE_MAX_H, max_cpu),
        )
        self._cpu_h = cpu_h
        y_handle = h - cpu_h - self._handle_h
        # Keep the orth vertical scrollbar track clear of the overlay.
        overlay_w = max(0, w - self._orth_vbar_gutter_px())
        self._handle.setGeometry(0, y_handle, overlay_w, self._handle_h)
        self._cpu.setGeometry(0, y_handle + self._handle_h, overlay_w, cpu_h)
        self._handle.show()
        self._cpu.show()
        self._handle.raise_()
        self._cpu.raise_()
        # Navigator is a child of TimelineView; lift it above this overlay.
        self._sync_nav_bottom_inset_from_handle(y_handle)

    def _sync_nav_bottom_inset(self, inset: int) -> None:
        view = getattr(self._timeline, "view", None)
        if view is not None and hasattr(view, "set_nav_bottom_inset"):
            view.set_nav_bottom_inset(inset)

    def _sync_nav_bottom_inset_from_handle(self, y_handle: int) -> None:
        """Pixels of TimelineView covered by the CPU overlay / splitter handle."""
        view = getattr(self._timeline, "view", None)
        if view is None or not hasattr(view, "set_nav_bottom_inset"):
            return
        view_bottom = view.mapTo(self, QPoint(0, view.height())).y()
        # Keep a small gap so the popup sits clearly above the handle.
        inset = max(0, view_bottom - y_handle)
        view.set_nav_bottom_inset(inset)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is not self._handle:
            return super().eventFilter(obj, event)
        et = event.type()
        if et == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self._dragging = True
                gp = event.globalPosition().toPoint()
                self._drag_global_y = gp.y()
                self._drag_h0 = self.sizes()[1] if self._cpu_visible else self._cpu_h
            return False
        if et == QEvent.Type.MouseMove and self._dragging:
            gp = event.globalPosition().toPoint()
            dy = gp.y() - self._drag_global_y
            # Handle sits above the CPU pane: drag up → taller CPU, down → shorter.
            self._cpu_h = self._drag_h0 - dy
            self._reposition()
            self.splitterMoved.emit(self._handle.y(), 1)
            return False
        if et == QEvent.Type.MouseButtonRelease:
            self._dragging = False
            return False
        return False

class _CpuSplitterHandleFilter(QObject):
    """Mark CPU-load splitter drags so layout/rebuild stays deferred until release."""

    def __init__(self, handle: QWidget, win: "MainWindow") -> None:
        super().__init__(handle)
        self._win = win

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.MouseButtonPress:
            self._win._cpu_splitter_user_drag = True
            self._win._cpu_splitter_resizing = True
            self._win._cpu_splitter_drag_timer.stop()
        elif event.type() == QEvent.Type.MouseButtonRelease:
            self._win._cpu_splitter_user_drag = False
            self._win._cpu_splitter_drag_timer.start()
        return False

class _TraceTab:
    """One open trace file: timeline widgets + TraceTabViewModel document state."""

    __slots__ = (
        "vm", "view", "cpu_load_graph", "cpu_load_scroll", "cpu_splitter",
        "_timeline_pane", "_stats_built",
    )

    def __init__(self, path: str, trace: "BtfTrace", win: "MainWindow") -> None:
        self.vm = TraceTabViewModel(path, trace, win)

        self.view = TimelineView(win)
        win._wire_timeline_view(self.view)

        self.cpu_load_graph = _CpuLoadGraph(self.view)
        self.cpu_load_graph.set_dark(win._is_dark)
        win._wire_cpu_load_graph(self.view, self.cpu_load_graph)

        self.cpu_load_scroll = _CpuLoadScrollArea()
        win._setup_cpu_load_scroll(self.cpu_load_scroll, self.cpu_load_graph)

        self._timeline_pane = _TimelinePane(self.view)
        self.cpu_splitter = _CpuLoadStack(self._timeline_pane, self.cpu_load_scroll)
        self.cpu_splitter.setSizes([600, CPU_LOAD_ROW_H])
        self.cpu_splitter.splitterMoved.connect(win._on_cpu_splitter_moved)
        handle = self.cpu_splitter.handle(1)
        if handle is not None:
            filt = _CpuSplitterHandleFilter(handle, win)
            handle.installEventFilter(filt)
            win._cpu_splitter_handle_filters.append(filt)
        if not win._show_cpu_load:
            self.cpu_splitter.set_cpu_visible(False)
        self._stats_built = False

    @property
    def path(self) -> str:
        return self.vm.path

    @property
    def trace(self) -> Optional["BtfTrace"]:
        return self.vm.trace

    @property
    def bookmarks(self) -> List[TraceBookmark]:
        return self.vm.bookmarks

    @bookmarks.setter
    def bookmarks(self, value: List[TraceBookmark]) -> None:
        self.vm.bookmarks = value

    @property
    def annotations(self) -> List[TraceAnnotation]:
        return self.vm.annotations

    @annotations.setter
    def annotations(self, value: List[TraceAnnotation]) -> None:
        self.vm.annotations = value

    @property
    def mark_next_id(self) -> int:
        return self.vm.mark_next_id

    @mark_next_id.setter
    def mark_next_id(self, value: int) -> None:
        self.vm.mark_next_id = value

    @property
    def find_hits(self) -> List[int]:
        return self.vm.find_hits

    @find_hits.setter
    def find_hits(self, value: List[int]) -> None:
        self.vm.find_hits = value

    @property
    def find_hit_idx(self) -> int:
        return self.vm.find_hit_idx

    @find_hit_idx.setter
    def find_hit_idx(self, value: int) -> None:
        self.vm.find_hit_idx = value

    @property
    def find_marker_ns(self) -> Optional[int]:
        return self.vm.find_marker_ns

    @find_marker_ns.setter
    def find_marker_ns(self, value: Optional[int]) -> None:
        self.vm.find_marker_ns = value

    @property
    def undo_stack(self) -> list:
        return self.vm.undo_stack

    @undo_stack.setter
    def undo_stack(self, value: list) -> None:
        self.vm.undo_stack = value

    @property
    def redo_stack(self) -> list:
        return self.vm.redo_stack

    @redo_stack.setter
    def redo_stack(self, value: list) -> None:
        self.vm.redo_stack = value

    @property
    def plot_mk(self) -> Optional[str]:
        return self.vm.plot_mk

    @plot_mk.setter
    def plot_mk(self, value: Optional[str]) -> None:
        self.vm.plot_mk = value

    @property
    def plot_kind(self) -> Optional[str]:
        return self.vm.plot_kind

    @plot_kind.setter
    def plot_kind(self, value: Optional[str]) -> None:
        self.vm.plot_kind = value

    @property
    def plot_preemptor(self) -> Optional[str]:
        return self.vm.plot_preemptor

    @plot_preemptor.setter
    def plot_preemptor(self, value: Optional[str]) -> None:
        self.vm.plot_preemptor = value

    @property
    def plot_open(self) -> bool:
        return self.vm.plot_open

    @plot_open.setter
    def plot_open(self, value: bool) -> None:
        self.vm.plot_open = value

    @property
    def plot_interval_id(self) -> Optional[str]:
        return self.vm.plot_interval_id

    @plot_interval_id.setter
    def plot_interval_id(self, value: Optional[str]) -> None:
        self.vm.plot_interval_id = value

class MainWindow(MvvmSettingsMixin, QMainWindow):

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self):
        super().__init__()
        self.setWindowIcon(app_icon())
        self._vm = MainViewModel(self)
        self._tabs: List[_TraceTab] = []
        self._previous_tab_index: int = -1
        self._tab_switch_guard: bool = False
        self._bound_scene = None
        self._legend_cancel_fn = None
        self._parse_thread: Optional[_ParseThread] = None
        self._orphaned_parse_threads: List[_ParseThread] = []
        self._settings = _RcSettings()
        self._dock_width_apply_guard: bool = False
        self._applying_dock_prefs: bool = False
        self._restoring_settings: bool = False
        self._dock_layout_settling: bool = False
        self._startup_dock_layout_done: bool = False
        self._startup_dock_timer: Optional[QTimer] = None
        self._dock_startup_metrics: Optional[str] = None
        self._dock_startup_needs_defaults: bool = False
        self._dock_width_pending: Optional[float] = None
        self._dock_stabilize_timer: Optional[QTimer] = None
        self._right_dock_custom_drag: bool = False
        self._progress_dialog: Optional[QProgressDialog] = None

        self._find_marker_items: List[QGraphicsItem] = []
        self._heatmap_dlg: Optional[_CorridorInspectorDialog] = None
        self._heatmap_view_snapshot: Optional[dict] = None
        self._chord_dlg: Optional[_CorridorInspectorDialog] = None
        self._defer_stats_refresh: bool = False
        self._shutting_down: bool = False
        self._persisting_settings: bool = False
        self._applying_theme: bool = False
        self._theme_widgets_pending: bool = False
        self._theme_op_id: int = 0
        self._theme_change_in_flight: bool = False
        self._tb_icon_actions: list = []   # (QAction, icon_path_data) for theme-aware icons
        self._cpu_splitter_resizing: bool = False
        self._cpu_splitter_user_drag: bool = False
        self._cpu_splitter_programmatic: bool = False
        self._cpu_splitter_handle_filters: List[QObject] = []
        self._pending_open_paths: List[str] = []
        self._cpu_splitter_drag_timer = QTimer(self)
        self._cpu_splitter_drag_timer.setSingleShot(True)
        self._cpu_splitter_drag_timer.setInterval(120)
        self._cpu_splitter_drag_timer.timeout.connect(self._on_cpu_splitter_drag_end)
        self._cpu_load_autofit_timer = QTimer(self)
        self._cpu_load_autofit_timer.setSingleShot(True)
        self._cpu_load_autofit_timer.setInterval(80)
        self._cpu_load_autofit_timer.timeout.connect(self._on_cpu_load_autofit_timeout)

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
        _tab_fwd.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        _tab_fwd.activated.connect(lambda: self._cycle_trace_tab(True))
        _tab_bwd = QShortcut(QKeySequence("Ctrl+Shift+Tab"), self)
        _tab_bwd.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        _tab_bwd.activated.connect(lambda: self._cycle_trace_tab(False))

        _sc_find = QShortcut(QKeySequence.StandardKey.Find, self)
        _sc_find.setContext(Qt.ShortcutContext.ApplicationShortcut)
        _sc_find.activated.connect(self._focus_find)
        _sc_find_next = QShortcut(QKeySequence.StandardKey.FindNext, self)
        _sc_find_next.setContext(Qt.ShortcutContext.ApplicationShortcut)
        _sc_find_next.activated.connect(self._find_next)
        _sc_find_prev = QShortcut(QKeySequence.StandardKey.FindPrevious, self)
        _sc_find_prev.setContext(Qt.ShortcutContext.ApplicationShortcut)
        _sc_find_prev.activated.connect(self._find_prev)

        for _key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            _sc = QShortcut(QKeySequence(_key), self)
            _sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            _sc.activated.connect(
                lambda k=_key: self._pan_timeline_arrow(k))

        # Restore all persisted settings (geometry, zoom, orientation, ...).
        self._restore_settings()
        self._vm.settings.settings_changed.connect(self._on_settings_changed)
        self._wired_tab_vm: Optional[TraceTabViewModel] = None
        self._vm.active_tab_changed.connect(self._wire_active_tab_vm_signals)

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._on_app_about_to_quit)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._schedule_startup_dock_layout()

    def _schedule_startup_dock_layout(self, delay_ms: int = 50) -> None:
        """Coalesced post-show dock restore (sizes, then visibility on next tick)."""
        if self._startup_dock_layout_done or self._shutting_down:
            return
        timer = self._startup_dock_timer
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._run_startup_dock_layout)
            self._startup_dock_timer = timer
        timer.start(max(0, int(delay_ms)))

    def _run_startup_dock_layout(self) -> None:
        """Apply persisted dock sizes; visibility is applied after resizeDocks()."""
        if self._startup_dock_layout_done or self._shutting_down:
            return
        if not hasattr(self, "_panel_dock"):
            return
        self._dock_layout_settling = True
        try:
            self._reload_panel_visibility_prefs_from_rc()
            self._apply_dock_visibility_respecting_rc()
            if self._dock_startup_needs_defaults:
                self._apply_default_dock_sizes()
            elif self._dock_startup_metrics:
                self._apply_dock_metrics_sizes(self._dock_startup_metrics)
            else:
                self._apply_default_dock_sizes()
            self._apply_dock_visibility_respecting_rc()
            if self._show_stats:
                self._focus_statistics_panel()
        finally:
            self._dock_layout_settling = False
            self._restoring_settings = False
            self._startup_dock_layout_done = True
        QTimer.singleShot(150, self._verify_startup_dock_visibility)
        QTimer.singleShot(400, self._verify_startup_dock_visibility)

    def _finish_startup_dock_layout(self) -> None:
        """Legacy hook (visibility now applied in _run_startup_dock_layout)."""
        pass

    def _verify_startup_dock_visibility(self) -> None:
        """Last-chance pass if Qt layout settled with docks still hidden."""
        if self._shutting_down or not hasattr(self, "_panel_dock"):
            return
        self._reload_panel_visibility_prefs_from_rc()
        panel_on = self._right_panel_wanted()
        panel_bad = panel_on and not self._panel_dock.isVisible()
        if not panel_bad:
            return
        self._dock_layout_settling = True
        try:
            self._apply_dock_visibility_respecting_rc()
        finally:
            self._dock_layout_settling = False

    def _on_app_about_to_quit(self) -> None:
        """Last-chance parse-thread join (closeEvent already did the heavy lifting)."""
        self._stop_parse_thread(wait_ms=200)

    def _dismiss_auxiliary_windows(self) -> None:
        """Close modeless dialogs so they do not prolong QWidget teardown."""
        if hasattr(self, "_stats_panel"):
            self._stats_panel.clear_plot_session()
        self._close_heatmap_dialog()
        self._close_chord_dialog()
        if self._progress_dialog is not None:
            self._progress_dialog.close()
            self._progress_dialog = None

    @property
    def _active_tab_vm(self) -> Optional[TraceTabViewModel]:
        tab = self._active_tab
        return tab.vm if tab is not None else None

    @property
    def _bookmarks(self) -> List[TraceBookmark]:
        vm = self._active_tab_vm
        return vm.bookmarks if vm is not None else []

    @_bookmarks.setter
    def _bookmarks(self, value: List[TraceBookmark]) -> None:
        vm = self._active_tab_vm
        if vm is not None:
            vm.bookmarks = value

    @property
    def _annotations(self) -> List[TraceAnnotation]:
        vm = self._active_tab_vm
        return vm.annotations if vm is not None else []

    @_annotations.setter
    def _annotations(self, value: List[TraceAnnotation]) -> None:
        vm = self._active_tab_vm
        if vm is not None:
            vm.annotations = value

    @property
    def _mark_next_id(self) -> int:
        vm = self._active_tab_vm
        return vm.mark_next_id if vm is not None else 1

    @_mark_next_id.setter
    def _mark_next_id(self, value: int) -> None:
        vm = self._active_tab_vm
        if vm is not None:
            vm.mark_next_id = value

    @property
    def _find_hits(self) -> List[int]:
        vm = self._active_tab_vm
        return vm.find_hits if vm is not None else []

    @_find_hits.setter
    def _find_hits(self, value: List[int]) -> None:
        vm = self._active_tab_vm
        if vm is not None:
            vm.find_hits = value

    @property
    def _find_hit_idx(self) -> int:
        vm = self._active_tab_vm
        return vm.find_hit_idx if vm is not None else -1

    @_find_hit_idx.setter
    def _find_hit_idx(self, value: int) -> None:
        vm = self._active_tab_vm
        if vm is not None:
            vm.find_hit_idx = value

    @property
    def _find_marker_ns(self) -> Optional[int]:
        vm = self._active_tab_vm
        return vm.find_marker_ns if vm is not None else None

    @_find_marker_ns.setter
    def _find_marker_ns(self, value: Optional[int]) -> None:
        vm = self._active_tab_vm
        if vm is not None:
            vm.find_marker_ns = value

    @property
    def _undo_stack(self) -> list:
        vm = self._active_tab_vm
        return vm.undo_stack if vm is not None else []

    @_undo_stack.setter
    def _undo_stack(self, value: list) -> None:
        vm = self._active_tab_vm
        if vm is not None:
            vm.undo_stack = value

    @property
    def _redo_stack(self) -> list:
        vm = self._active_tab_vm
        return vm.redo_stack if vm is not None else []

    @_redo_stack.setter
    def _redo_stack(self, value: list) -> None:
        vm = self._active_tab_vm
        if vm is not None:
            vm.redo_stack = value

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
    def _cpu_splitter(self) -> "_CpuLoadStack":
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
        return self._vm.tab_for_path(path, normalizer=_normalize_open_path)

    def _wire_timeline_view(self, view: TimelineView) -> None:
        view.zoom_changed.connect(lambda tpp, v=view: self._on_zoom_changed(tpp, v))
        view.viewport_changed.connect(
            lambda v=view: self._on_timeline_viewport_changed(v))
        view.label_width_changed.connect(
            lambda w, v=view: self._on_label_width_changed(w, v))
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

    def _setup_cpu_load_scroll(self, scroll: _CpuLoadScrollArea, graph: _CpuLoadGraph) -> None:
        """Wire CPU load graph into a scroll area with vertical scroll when cores overflow."""
        scroll.setWidget(graph)
        scroll.setWidgetResizable(False)
        scroll.setMinimumHeight(_CpuLoadScrollArea._MIN_PANE_H)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        graph._scroll_area = scroll

        class _CpuLoadScrollSync(QObject):
            def __init__(self, g: _CpuLoadGraph, v: "TimelineView", sa: QScrollArea) -> None:
                super().__init__(g)
                self._graph = g
                self._view = v
                self._scroll = sa

            def eventFilter(self, obj, event):  # noqa: N802
                if event.type() == QEvent.Type.Resize:
                    self._graph._schedule_sync_scroll_size()
                    return False
                if event.type() == QEvent.Type.Wheel:
                    pos = (event.position().toPoint()
                           if hasattr(event, "position") else event.position().toPoint())
                    self._graph._handle_wheel(event, pos, obj)
                    return True
                if event.type() == QEvent.Type.NativeGesture and _is_zoom_native_gesture(event):
                    pt = _native_gesture_local_pos(event)
                    global_pos = self._scroll.viewport().mapToGlobal(pt)
                    anchor = self._view.mapFromGlobal(global_pos)
                    factor = _native_gesture_zoom_factor(event)
                    if factor > 0.1:
                        self._view._fit_mode = False
                        self._view._do_zoom(factor, anchor)
                    return True
                return False

        filt = _CpuLoadScrollSync(graph, graph._view, scroll)
        graph._scroll_sync_filter = filt
        scroll.viewport().installEventFilter(filt)
        scroll.installEventFilter(filt)
        scroll.verticalScrollBar().valueChanged.connect(lambda _v: graph.update())
        graph._sync_scroll_size()
        self._sync_cpu_load_scroll_theme(scroll, graph, self._is_dark)

    def _wire_cpu_load_graph(self, view: TimelineView, graph: _CpuLoadGraph) -> None:
        def _repaint_cpu_graph(*_args) -> None:
            graph.update()

        view.zoom_changed.connect(_repaint_cpu_graph)
        view.horizontalScrollBar().valueChanged.connect(_repaint_cpu_graph)
        view.verticalScrollBar().valueChanged.connect(_repaint_cpu_graph)
        view.verticalScrollBar().rangeChanged.connect(_repaint_cpu_graph)
        def _on_highlight_changed(task_name, locked) -> None:
            graph.set_task(task_name, locked)
            if not self._cpu_splitter_user_sized:
                self._autofit_cpu_load_height()

        view._scene.highlight_changed.connect(_on_highlight_changed)
        view._scene.hover_changed.connect(_repaint_cpu_graph)
        view._scene.marks_changed.connect(_repaint_cpu_graph)
        view.cursors_changed.connect(lambda _: _repaint_cpu_graph())

        view.label_width_changed.connect(lambda _w: _repaint_cpu_graph())
        view.label_width_resizing.connect(lambda _w: _repaint_cpu_graph())

        def _on_task_filter_changed() -> None:
            graph.updateGeometry()
            graph.update()
            self._autofit_cpu_load_height()

        view._scene.task_filter_changed.connect(_on_task_filter_changed)

        def _on_cpu_expand_all_toggled(_expanded: bool) -> None:
            if view is self._view and not self._cpu_splitter_user_sized:
                self._autofit_cpu_load_height()

        graph.expand_all_toggled.connect(_on_cpu_expand_all_toggled)

        class _CpuGraphViewportSync(QObject):
            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.Resize:
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
        graph.update()

    def _sync_trace_tab_widget_theme(self, is_dark: bool) -> None:
        """Keep trace-file tab bar and pane backgrounds in sync with the app theme."""
        if not hasattr(self, "_tab_widget"):
            return
        c = self._theme_tokens(is_dark)
        win_bg = QColor(c["win_bg"])

        tw = self._tab_widget
        tb = tw.tabBar()
        tb.setExpanding(False)
        if sys.platform == "darwin" and not getattr(self, "_trace_tabs_left_style_applied", False):
            tb.setStyle(_LeftTabStyle())
            tw.setStyle(_LeftTabStyle())
            self._trace_tabs_left_style_applied = True
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

    def _sync_panel_tabs_theme(self, is_dark: bool) -> None:
        """Keep Statistics / Marks / Find tab surfaces in sync with the app theme."""
        if not hasattr(self, "_panel_tabs"):
            return
        c = self._theme_tokens(is_dark)
        win_bg = QColor(c["win_bg"])

        tw = self._panel_tabs
        tb = tw.tabBar()
        tb.setExpanding(False)
        if sys.platform == "darwin" and not getattr(self, "_panel_tabs_left_style_applied", False):
            tw.setStyle(_LeftTabStyle())
            tb.setStyle(_LeftTabStyle())
            self._panel_tabs_left_style_applied = True
        tw.setObjectName("panel_tab_widget")
        tb.setObjectName("panel_tab_bar")
        tw.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        tb.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        mid_bg = QColor(c["mid"])
        pal = tw.palette()
        pal.setColor(QPalette.Window, win_bg)
        pal.setColor(QPalette.Base, win_bg)
        pal.setColor(QPalette.Button, QColor(c["tab_bg"]))
        pal.setColor(QPalette.ButtonText, QColor(c["tab_fg"]))
        tw.setPalette(pal)
        tw.setAutoFillBackground(True)
        pal = tb.palette()
        pal.setColor(QPalette.Window, mid_bg)
        pal.setColor(QPalette.Base, mid_bg)
        pal.setColor(QPalette.Button, QColor(c["tab_bg"]))
        pal.setColor(QPalette.ButtonText, QColor(c["tab_fg"]))
        tb.setPalette(pal)
        tb.setAutoFillBackground(True)

        for host in (
            getattr(self, "_marks_host", None),
            getattr(self, "_find_host", None),
            getattr(self, "_stats_panel", None),
        ):
            if host is None:
                continue
            pal = host.palette()
            pal.setColor(QPalette.Window, win_bg)
            pal.setColor(QPalette.Base, win_bg)
            host.setPalette(pal)
            host.setAutoFillBackground(True)

        marks_tabs = getattr(self, "_marks_tabs", None)
        if marks_tabs is not None:
            marks_tabs.setObjectName("marks_tab_widget")
            mtb = marks_tabs.tabBar()
            mtb.setObjectName("marks_tab_bar")
            for w in (marks_tabs, mtb):
                pal = w.palette()
                pal.setColor(QPalette.Window, win_bg)
                pal.setColor(QPalette.Base, win_bg)
                w.setPalette(pal)
                w.setAutoFillBackground(True)
            for i in range(marks_tabs.count()):
                page = marks_tabs.widget(i)
                if page is None:
                    continue
                pal = page.palette()
                pal.setColor(QPalette.Window, win_bg)
                pal.setColor(QPalette.Base, win_bg)
                page.setPalette(pal)
                page.setAutoFillBackground(True)

        panel_dock = getattr(self, "_panel_dock", None)
        if panel_dock is not None:
            pal = panel_dock.palette()
            pal.setColor(QPalette.Window, win_bg)
            pal.setColor(QPalette.Base, win_bg)
            panel_dock.setPalette(pal)
            panel_dock.setAutoFillBackground(True)

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
        sc.set_time_decimals(self._time_decimals_val)
        self._cpu_load_graph.set_time_decimals(self._time_decimals_val)
        sc.set_theme(self._is_dark, rebuild=False)
        self._sync_timeline_view_theme(view, self._is_dark)
        view.set_horizontal(self._vm.settings.horizontal)
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
        # Timeline lock survives tab switch; set_trace() used to wipe the CPU
        # filter. Re-apply so Load shows the highlighted task, not all tasks.
        locked = getattr(tab.view._scene, "_locked_task", None)
        graph.set_task(locked, locked is not None)

    def _capture_legend_filters_to_scene(self, scene) -> None:
        """Copy shared legend UI into *scene* without rebuild (tab switch / persist)."""
        if scene is None:
            return
        self._legend._filter_emit_timer.stop()
        scene._task_filter_q = self._legend._search.text().strip().lower()
        scene._migrated_only_filter = bool(
            self._legend._migrated_only_cb.isChecked()
            and not scene._heatmap_filter_mks)

    def _sync_legend_filters_from_scene(self, scene) -> None:
        """Refresh shared legend UI from *scene* filter state."""
        if scene is None:
            return
        self._legend.set_filter_text(scene._task_filter_q)
        self._legend.set_migrated_only_checked(scene._migrated_only_filter)
        self._legend.set_heatmap_filter(scene._heatmap_filter_label, scene._heatmap_filter_mks)

    def _stash_tab_state(self, tab: _TraceTab) -> None:
        tab.vm.stats.copy_from_panel(self._stats_panel)
        tab.vm.stats.cursor_times = list(tab.view._scene.cursor_times())
        tab.vm.capture_viewport_from_view(tab.view)
        tab.vm.find_query = self._find_input.text()
        tab.vm.find_mode = self._find_mode_combo.currentText()
        mk, kind, open_, preemptor, interval_id = self._stats_panel.capture_plot_session()
        tab.vm.set_plot_session(mk, kind, open_, preemptor, interval_id)
        self._persist_trace_state(tab.path, tab.bookmarks, tab.annotations, tab.mark_next_id)
        self._persist_tab_view_state(tab)

    def _restore_find_widgets_from_tab(self, tab: _TraceTab) -> None:
        """Restore Find panel widgets from per-tab view-model (no recompute)."""
        self._find_input.blockSignals(True)
        self._find_mode_combo.blockSignals(True)
        try:
            self._find_input.setText(tab.vm.find_query)
            idx = self._find_mode_combo.findText(
                tab.vm.find_mode, Qt.MatchFlag.MatchFixedString)
            if idx >= 0:
                self._find_mode_combo.setCurrentIndex(idx)
        finally:
            self._find_input.blockSignals(False)
            self._find_mode_combo.blockSignals(False)

    def _wire_active_tab_vm_signals(self, _vm=None) -> None:
        """Connect undo_changed on the active tab VM (MVVM → toolbar)."""
        vm = self._active_tab_vm
        if vm is self._wired_tab_vm:
            self._sync_undo_actions()
            return
        if self._wired_tab_vm is not None:
            try:
                self._wired_tab_vm.undo_changed.disconnect(self._sync_undo_actions)
            except TypeError:
                pass
        self._wired_tab_vm = vm
        if vm is not None:
            vm.undo_changed.connect(self._sync_undo_actions)
        self._sync_undo_actions()

    def _sync_undo_actions(self) -> None:
        if not hasattr(self, "_act_undo"):
            return
        vm = self._active_tab_vm
        self._act_undo.setEnabled(bool(vm and vm.undo_stack))
        self._act_redo.setEnabled(bool(vm and vm.redo_stack))

    def _persist_tab_view_state(self, tab: _TraceTab) -> None:
        """Save zoom/cursor layout for one tab (keyed by trace path hash)."""
        if not tab.path or tab.trace is None:
            return
        tab.vm.capture_viewport_from_view(tab.view)
        key = self._trace_state_key(tab.path)
        self._settings.set(
            "tab_view", key, viewport_to_json(tab.vm.viewport), flush=False)

    def _load_tab_view_state(self, tab: _TraceTab) -> None:
        """Restore zoom/cursors saved for *tab* in btf_viewer.rc."""
        view = tab.view
        sc = view._scene
        raw = self._settings.get("tab_view", self._trace_state_key(tab.path), "")
        vp = viewport_from_json(raw)
        if vp is None:
            view.zoom_changed.emit(sc.timescale_per_px)
            view._refresh_nav_pan_window(force_show=view._navigator_eligible())
            return
        tab.vm.viewport = vp
        apply_viewport(view, vp)

    def _persist_open_tabs(self) -> None:
        """Write open tab paths and active tab index to btf_viewer.rc."""
        tab = self._active_tab
        if tab is not None:
            self._capture_legend_filters_to_scene(tab.view._scene)
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
        self._settings.prune_section("tab_view", 16, flush=False)

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
        if self._load_in_progress:
            return
        if self._session_restore_queue:
            path = self._session_restore_queue.pop(0)
            self._open_file(path)
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
            self._focus_statistics_panel()
            QTimer.singleShot(0, self._focus_statistics_panel)
        self._session_restore_active_idx = -1

    def _stash_active_tab_state(self) -> None:
        tab = self._active_tab
        if tab is None:
            return
        self._capture_legend_filters_to_scene(tab.view._scene)
        self._stash_tab_state(tab)

    def _restore_tab_state(self, tab: _TraceTab) -> None:
        self._rebuild_bookmark_list()
        self._rebuild_annotation_list()
        self._restore_find_widgets_from_tab(tab)
        if self._load_in_progress:
            self._sync_panels_light()
        else:
            self._sync_panels_to_active_tab()
            tab._stats_built = True
        self._wire_active_tab_vm_signals()

    def _focus_statistics_panel(self, force: bool = False) -> None:
        """Show and activate the Statistics tab in the right panel."""
        if force:
            self._show_stats = True
            self._sync_panel_tab_visibility()
        if not self._show_stats:
            return
        self._focus_panel_tab(_PANEL_TAB_STATS)

    def _focus_panel_tab(self, tab_index: int) -> None:
        """Show the right panel dock and switch to *tab_index*."""
        self._panel_dock.setVisible(True)
        self._panel_dock.raise_()
        if self._panel_tabs.isTabVisible(tab_index):
            self._panel_tabs.setCurrentIndex(tab_index)

    def _sync_panel_tab_visibility(self) -> None:
        """Apply show_stats / show_marks / show_find / show_ai to panel tab visibility."""
        if not hasattr(self, "_panel_tabs"):
            return
        self._panel_tabs.setTabVisible(_PANEL_TAB_STATS, self._show_stats)
        self._panel_tabs.setTabVisible(_PANEL_TAB_MARKS, self._show_marks)
        self._panel_tabs.setTabVisible(_PANEL_TAB_FIND, self._show_find)
        self._panel_tabs.setTabVisible(_PANEL_TAB_LEGEND, self._show_legend)
        self._panel_tabs.setTabVisible(_PANEL_TAB_AI, self._ai_panel_wanted())
        visible = [
            i for i in (
                _PANEL_TAB_STATS, _PANEL_TAB_MARKS, _PANEL_TAB_FIND,
                _PANEL_TAB_LEGEND, _PANEL_TAB_AI,
            )
            if self._panel_tabs.isTabVisible(i)
        ]
        if visible and self._panel_tabs.currentIndex() not in visible:
            self._panel_tabs.setCurrentIndex(visible[0])
        self._sync_panel_menu_checks()

    def _sync_panel_menu_checks(self) -> None:
        """Keep View menu check marks honest about the panel flags.

        setChecked() only emits toggled(), not triggered(), so this never
        re-enters the toggle slots.
        """
        for attr, flag in (
            ("_act_show_legend", getattr(self, "_show_legend", True)),
            ("_act_show_marks", self._show_marks),
            ("_act_show_find", self._show_find),
            ("_act_show_ai", getattr(self, "_show_ai", True)),
        ):
            act = getattr(self, attr, None)
            if act is not None and act.isChecked() != flag:
                act.setChecked(flag)

    def _ai_feature_enabled(self) -> bool:
        """Settings → AI → Enable AI Assistant."""
        s = getattr(self, "_settings", None)
        if s is None:
            return True
        return s.get_bool("ai", "enabled", True)

    def _ai_panel_wanted(self) -> bool:
        """AI tab is shown only when the feature is enabled and Display shows it."""
        return bool(getattr(self, "_show_ai", True)) and self._ai_feature_enabled()

    def _right_panel_wanted(self) -> bool:
        return bool(
            self._show_stats
            or self._show_marks
            or self._show_find
            or self._show_legend
            or self._ai_panel_wanted()
        )

    def _toggle_show_legend_panel(self) -> None:
        self._show_legend = not self._show_legend
        if hasattr(self, "_act_show_legend"):
            self._act_show_legend.setChecked(self._show_legend)
        self._sync_panel_tab_visibility()
        if self._show_legend:
            self._focus_panel_tab(_PANEL_TAB_LEGEND)

    def _toggle_show_marks_panel(self) -> None:
        self._show_marks = not self._show_marks
        self._act_show_marks.setChecked(self._show_marks)
        self._sync_panel_tab_visibility()
        if self._show_marks:
            self._focus_panel_tab(_PANEL_TAB_MARKS)

    def _toggle_show_find_panel(self) -> None:
        self._show_find = not self._show_find
        self._act_show_find.setChecked(self._show_find)
        self._sync_panel_tab_visibility()
        if self._show_find:
            self._focus_find()
        else:
            self._recompute_find_hits()

    def _dismiss_load_progress(self, progress_dialog: Optional["_LoadProgressDialog"] = None) -> None:
        """Close the load progress overlay (safe if already dismissed)."""
        dlg = progress_dialog if progress_dialog is not None else self._progress_dialog
        if dlg is None:
            return
        try:
            dlg.close()
            dlg.deleteLater()
        except RuntimeError:
            pass
        if self._progress_dialog is dlg:
            self._progress_dialog = None
        if QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()

    def _sync_panels_light(self) -> None:
        """Legend and bindings without rebuilding the statistics panel."""
        self._sync_heatmap_dialog_to_tab()
        self._sync_chord_dialog_to_tab()
        tab = self._active_tab
        trace = self._trace
        if tab is None or trace is None:
            return
        self._legend.rebuild(trace, show_sti=self._show_sti)
        sc = tab.view._scene
        self._sync_legend_filters_from_scene(sc)
        self._sync_show_all_tasks_btn()
        self._stats_panel._ui_font_size = self._ui_font_size_val
        tab.vm.stats.apply_to_panel(self._stats_panel, refresh_stats=False)
        self._stats_panel.set_cursor_times(self._view._scene.cursor_times(), refresh_stats=False)
        self._bind_legend_to_scene(sc)

    def _sync_panels_stats_and_chrome(self) -> None:
        """Statistics panel, CPU graph, and toolbar chrome after trace load."""
        tab = self._active_tab
        trace = self._trace
        if tab is None or trace is None:
            return
        self._stats_panel._ui_font_size = self._ui_font_size_val
        self._stats_panel.rebuild(trace)
        _budget = self._settings.get_float("analysis", "cpu_budget_pct", 0.0)
        _dl_text = self._settings.get("analysis", "task_deadlines", "")
        self._stats_panel.set_analysis_settings(
            _budget, _parse_task_deadlines_text(_dl_text))
        QTimer.singleShot(0, self._stats_panel.sync_util_layout)
        self._cpu_load_graph.set_trace(trace)
        self._cpu_load_graph.set_font_size(self._font_size_val)
        self._sync_cpu_load_graph(tab)
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

    def _sync_panels_to_active_tab(self) -> None:
        self._sync_panels_light()
        self._sync_panels_stats_and_chrome()

    def _update_status_for_active_tab(self) -> None:
        trace = self._trace
        if trace is None:
            self._status_file.setText("  No file loaded")
            self._status_file.setToolTip("")
            self.setWindowTitle("RTOS BTF Viewer")
            return
        fname = _trace_display_name(self._current_file)
        ts = _format_time(trace.time_max - trace.time_min, trace.time_scale,
                          decimals=self._time_decimals_val)
        n_tasks = len(trace.tasks)
        n_seg = len(trace.segments)
        n_sti = len(trace.sti_events)
        # Match web status-bar summary: creator · tasks · segments · STI · total
        parts: list[str] = []
        creator = (trace.meta or {}).get("creator", "").strip()
        if creator:
            parts.append(creator)
        parts.append(f"{n_tasks} tasks")
        parts.append(f"{n_seg:,} segments")
        parts.append(f"{n_sti:,} STI events")
        parts.append(f"{ts} total")
        summary = " · ".join(parts)
        self.setWindowTitle(f"RTOS BTF Viewer – {fname}")
        self._status_file.setText(f"  {fname}  |  {summary}")
        tip = self._current_file or fname
        self._status_file.setToolTip(f"{tip}\n{summary}")

    def _update_tab_actions(self) -> None:
        has_trace = self._trace is not None
        for act in (
            self._act_save_img, self._act_save_svg, self._act_copy_img,
            self._act_export_perfetto,
        ):
            act.setEnabled(has_trace)
        if hasattr(self, "_act_close_tab"):
            has_tabs = len(self._tabs) > 0
            self._act_close_tab.setEnabled(has_tabs)
            self._act_close_all_tabs.setEnabled(has_tabs)

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
            prev_tab = self._tabs[prev]
            self._capture_legend_filters_to_scene(prev_tab.view._scene)
            self._stash_tab_state(prev_tab)
            self._stats_panel.clear_plot_session()
        if 0 <= index < len(self._tabs):
            tab = self._tabs[index]
            self._vm.set_active_index(index)
            self._restore_tab_state(tab)
            self._stats_panel.restore_plot_session(
                tab.trace, tab.plot_mk, tab.plot_kind, tab.plot_open,
                preemptor=tab.plot_preemptor,
                interval_id=tab.plot_interval_id)
        else:
            self._vm.set_active_index(-1)
            self._update_tab_actions()
        self._previous_tab_index = index
        self._update_trace_quality_banner()

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
        self._vm.remove_tab(index)
        tab.cpu_splitter.deleteLater()
        if not self._tabs:
            self._central_stack.setCurrentIndex(0)
            self._unbind_legend_from_scene()
            self._vm.set_active_index(-1)
            self._rebuild_bookmark_list()
            self._rebuild_annotation_list()
            self._previous_tab_index = -1
            self._update_status_for_active_tab()
            self._clear_panels_for_empty_session()
        else:
            new_idx = min(index, len(self._tabs) - 1)
            # Guard the setCurrentIndex so the auto-selection that Qt already
            # performed during removeTab (guard was True then) doesn't fire a
            # second handler call, then explicitly drive _on_trace_tab_changed
            # once — this guarantees stats/toolbar are rebuilt even when the
            # QTabWidget's current index didn't change (already at new_idx).
            self._tab_switch_guard = True
            try:
                self._tab_widget.setCurrentIndex(new_idx)
            finally:
                self._tab_switch_guard = False
            self._on_trace_tab_changed(new_idx)
        self._update_tab_actions()
        self._sync_ai_compare_template()

    def _add_trace_tab(self, path: str, trace: BtfTrace) -> _TraceTab:
        tab = _TraceTab(path, trace, self)
        self._vm.add_tab(tab.vm)
        self._apply_view_settings(tab.view)
        c = self._theme_tokens(self._is_dark)
        win_bg = QColor(c["win_bg"])
        tab_pal = tab.cpu_splitter.palette()
        tab_pal.setColor(QPalette.Window, win_bg)
        tab.cpu_splitter.setPalette(tab_pal)
        tab.cpu_splitter.setAutoFillBackground(True)
        self._tabs.append(tab)
        self._central_stack.setCurrentIndex(1)
        self._tab_switch_guard = True
        try:
            idx = self._tab_widget.addTab(tab.cpu_splitter, _trace_display_name(path))
            self._tab_widget.setTabToolTip(idx, path)
            self._tab_widget.setCurrentIndex(idx)
        finally:
            self._tab_switch_guard = False
        self._previous_tab_index = idx
        self._sync_ai_compare_template()
        return tab

    # ------------------------------------------------------------------
    # Lifecycle persistence
    # ------------------------------------------------------------------

    def _any_visible_right_dock(self) -> bool:
        for dock in self._right_docks():
            if dock.isVisible() and not dock.isFloating():
                if self.dockWidgetArea(dock) == Qt.DockWidgetArea.RightDockWidgetArea:
                    return True
        return False

    def _current_right_dock_width(self) -> int:
        widths: list[int] = []
        for dock in self._right_docks():
            if dock.isVisible() and not dock.isFloating():
                if self.dockWidgetArea(dock) == Qt.DockWidgetArea.RightDockWidgetArea:
                    widths.append(int(dock.width()))
        if widths:
            return max(widths)
        return 330

    def _right_docks(self) -> Tuple[QDockWidget, ...]:
        dock = getattr(self, "_panel_dock", None)
        return (dock,) if dock is not None else ()

    def _visible_right_docks(self) -> List[QDockWidget]:
        docks: List[QDockWidget] = []
        for dock in self._right_docks():
            if dock.isVisible() and not dock.isFloating():
                if self.dockWidgetArea(dock) == Qt.DockWidgetArea.RightDockWidgetArea:
                    docks.append(dock)
        return docks

    def _relax_right_dock_content_widths(self) -> None:
        """Prevent dock children from pinning a wide minimum after the panel is expanded."""
        for dock in self._right_docks():
            dock.setMinimumWidth(_RIGHT_DOCK_MIN_W)
            host = dock.widget()
            if host is not None:
                _relax_widget_tree(host)
                host.setMaximumWidth(16777215)
        panel = getattr(self, "_stats_panel", None)
        if panel is not None:
            panel.relax_content_width()
        legend = getattr(self, "_legend", None)
        if legend is not None:
            legend.restore_row_layout()
        cursor_table = getattr(self, "_cursor_table", None)
        if cursor_table is not None:
            _StatsPanel._fix_stats_table_column_widths(cursor_table)

    def _resize_right_dock_column(self, w: int) -> None:
        docks = list(self._right_docks())
        if not docks:
            return
        sizes = [w] * len(docks)
        if self.isMaximized() or self.isFullScreen():
            self.resizeDocks(docks, sizes, Qt.Orientation.Horizontal)
            return
        # resizeDocks() on Windows can change the outer window width instead of
        # only stealing/giving space to the central widget — pin the frame.
        frame = self.geometry()
        self.resizeDocks(docks, sizes, Qt.Orientation.Horizontal)
        if self.geometry() != frame:
            self.setGeometry(frame)
            self.resizeDocks(docks, sizes, Qt.Orientation.Horizontal)

    def _schedule_stabilize_right_dock_layout(self) -> None:
        """Coalesce native dock splitter resizes into one stabilization pass."""
        timer = self._dock_stabilize_timer
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(0)
            timer.timeout.connect(self._stabilize_right_dock_layout)
            self._dock_stabilize_timer = timer
        timer.start()

    def _stabilize_right_dock_layout(self) -> None:
        """Reconcile dock/central split after native splitter drags."""
        self._apply_right_dock_width(self._current_right_dock_width())

    def _apply_right_dock_width(self, width: float) -> None:
        self._dock_width_pending = float(width)
        self._run_right_dock_width_apply()

    def _run_right_dock_width_apply(self) -> None:
        if self._dock_width_apply_guard:
            return
        if self._dock_width_pending is None:
            return
        self._dock_width_apply_guard = True
        try:
            while self._dock_width_pending is not None:
                width = self._dock_width_pending
                self._dock_width_pending = None
                w = max(_RIGHT_DOCK_MIN_W, min(_RIGHT_DOCK_MAX_W, int(width)))
                self._relax_right_dock_content_widths()
                self._resize_right_dock_column(w)
                self._relax_right_dock_content_widths()
            panel = getattr(self, "_stats_panel", None)
            if panel is not None:
                QTimer.singleShot(0, panel.sync_util_layout)
        finally:
            self._dock_width_apply_guard = False
            if self._dock_width_pending is not None:
                QTimer.singleShot(0, self._run_right_dock_width_apply)

    @staticmethod
    def _apply_right_dock_min_width(dock: QDockWidget) -> None:
        """Keep all right-column docks on the same resize floor."""
        dock.setMinimumWidth(_RIGHT_DOCK_MIN_W)
        dock.setMaximumWidth(_RIGHT_DOCK_MAX_W)
        host = dock.widget()
        if host is not None:
            host.setMinimumWidth(0)
            if host.layout() is not None:
                _relax_layout_width_constraints(host.layout())

    def _apply_default_dock_sizes(self) -> None:
        """Apply startup dock dimensions.

        Called via QTimer.singleShot(0) so the window is already visible and
        the dock layout engine has completed its first pass - resizeDocks() is
        a no-op when called before the window is shown.

                Default structure: one right dock with tabbed pages
                (Statistics / Marks / Find / Legend / AI).
        """
        self._resize_right_dock_column(520)
        self._focus_statistics_panel()
        self._relax_right_dock_content_widths()
        _wire_splitter_handle_cursors(self)

    def _apply_dock_metrics_sizes(self, packed: str) -> None:
        """Apply persisted dock widths/heights (visibility handled separately)."""
        try:
            parts = [int(p.strip()) for p in packed.split(",")]
            if len(parts) != 5:
                return
            right_w, _legend_h, _marks_h, _stats_h, label_w = parts
        except (ValueError, TypeError):
            return

        if right_w > 0:
            self._resize_right_dock_column(right_w)
        if label_w >= 60:
            self._label_width_val = label_w
            self._view._scene.set_label_width(label_w)
        self._relax_right_dock_content_widths()
        _wire_splitter_handle_cursors(self)

    def _dock_profile_key(self, width: int, height: int) -> str:
        """Build a stable per-window-size key for dock/layout persistence."""
        return f"{max(400, int(width))}x{max(300, int(height))}"

    def _collect_dock_metrics(self) -> str:
        """Return compact CSV metrics snapshot for dock sizes."""
        right_w = int(self._panel_dock.width())
        panel_h = int(self._panel_dock.height())
        label_w = int(self._view._scene._label_width)
        return f"{right_w},0,{panel_h},{panel_h},{label_w}"

    def _restore_dock_metrics(self, packed: str) -> None:
        """Apply dock-size metrics persisted via _collect_dock_metrics()."""
        self._apply_dock_metrics_sizes(packed)

    def _complete_startup_dock_layout(self) -> None:
        """Legacy entry point — delegates to the coalesced startup scheduler."""
        self._schedule_startup_dock_layout(0)

    def _apply_view_prefs_from_vm(self) -> None:
        """Apply AppSettingsViewModel values to timeline widgets (after RC load)."""
        self._apply_settings_to_all_tabs()

    def _on_settings_changed(self) -> None:
        """Push AppSettingsViewModel changes to all open tabs and chrome."""
        if (self._shutting_down or self._persisting_settings
                or self._load_in_progress or self._theme_change_in_flight):
            return
        self._apply_settings_to_all_tabs()

    def _apply_settings_to_all_tabs(self) -> None:
        """Apply AppSettingsViewModel values to timeline widgets and docks."""
        if getattr(self, "_applying_settings", False):
            return
        if not hasattr(self, "_view"):
            return
        self._applying_settings = True
        try:
            self._apply_settings_to_all_tabs_impl()
        finally:
            self._applying_settings = False

    def _reload_panel_visibility_prefs_from_rc(self) -> None:
        """Re-read Layout panel flags from btf_viewer.rc (authoritative for panel visibility)."""
        s = self._settings
        self._show_legend = s.get_bool("view", "show_legend", True)
        self._show_stats = s.get_bool("view", "show_stats", True)
        self._show_marks = s.get_bool("view", "show_marks", True)
        self._show_find = s.get_bool("view", "show_find", True)
        self._show_ai = s.get_bool("view", "show_ai", True)
        self._sync_panel_menu_checks()

    def _ensure_right_docks_layout(self) -> None:
        """Keep the tabbed right panel attached after float/close."""
        if not hasattr(self, "_panel_dock"):
            return
        panel = self._panel_dock
        if self.dockWidgetArea(panel) == Qt.DockWidgetArea.NoDockWidgetArea:
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, panel)

    def _block_dock_widget_signals(self, block: bool) -> None:
        dock = getattr(self, "_panel_dock", None)
        if dock is not None:
            dock.blockSignals(block)

    def _set_dock_visible(self, dock: QDockWidget, visible: bool) -> None:
        """Show/hide a dock; re-attach and sync toggleViewAction."""
        if visible and dock is getattr(self, "_panel_dock", None):
            self._ensure_right_docks_layout()
        action = dock.toggleViewAction()
        if action is not None:
            action.blockSignals(True)
            try:
                checked = action.isChecked()
                if visible and not checked:
                    action.setChecked(True)
                    action.trigger()
                elif not visible and checked:
                    action.setChecked(False)
                    action.trigger()
            finally:
                action.blockSignals(False)
        if visible:
            dock.setVisible(True)
            dock.show()
        else:
            dock.setVisible(False)

    def _apply_dock_visibility_from_prefs(self) -> None:
        """Show/hide the right panel from view prefs; legend is a tab inside it."""
        if not hasattr(self, "_panel_dock"):
            return
        self._applying_dock_prefs = True
        self._block_dock_widget_signals(True)
        try:
            self._sync_panel_tab_visibility()
            panel_on = self._right_panel_wanted()
            if panel_on:
                self._set_dock_visible(self._panel_dock, True)
                self._panel_dock.raise_()
            else:
                self._set_dock_visible(self._panel_dock, False)
        finally:
            self._block_dock_widget_signals(False)
            self._applying_dock_prefs = False

    def _apply_dock_visibility_respecting_rc(self) -> None:
        """Apply dock visibility; re-read RC once if the panel failed to show."""
        self._apply_dock_visibility_from_prefs()
        if not hasattr(self, "_panel_dock"):
            return
        panel_on = self._right_panel_wanted()
        panel_bad = panel_on and not self._panel_dock.isVisible()
        if panel_bad:
            self._reload_panel_visibility_prefs_from_rc()
            self._apply_dock_visibility_from_prefs()

    def _sync_panel_visibility_prefs_for_persist(self) -> bool:
        """Legend visibility is the show_legend tab flag (not a separate dock)."""
        return self._show_legend

    def _finalize_dock_layout_from_rc(self) -> None:
        """Apply Layout checkboxes after restoreState / resizeDocks (deferred)."""
        self._complete_startup_dock_layout()

    def _apply_settings_to_all_tabs_impl(self) -> None:
        self._view.set_font_size(self._font_size_val)
        self._apply_theme(self._is_dark)
        self._view.set_max_cursors(self._max_cursors_val)
        for view in self._iter_tab_views():
            self._apply_view_settings(view)
        for tab in self._tabs:
            self._sync_cpu_load_graph(tab)

        if not self._show_cpu_load:
            for tab in self._tabs:
                tab.cpu_splitter.set_cpu_visible(False)
            if hasattr(self, "_tb_cpu_load_btn"):
                self._tb_cpu_load_btn.setChecked(False)
        elif hasattr(self, "_tb_cpu_load_btn"):
            self._tb_cpu_load_btn.setChecked(True)
            for tab in self._tabs:
                tab.cpu_splitter.set_cpu_visible(True)

        self._cpu_load_graph.set_row_h(self._cpu_load_row_h_val)

        horizontal = self._vm.settings.horizontal
        if hasattr(self, "_act_horiz"):
            self._act_horiz.setChecked(horizontal)
            self._act_vert.setChecked(not horizontal)
            self._tb_horiz_btn.setChecked(horizontal)
            self._tb_vert_btn.setChecked(not horizontal)
        self._sync_view_mode_toolbar()
        if self._vm.settings.colorblind:
            self._set_colorblind_safe(True)

        self._set_show_sti(self._show_sti, persist=False)
        self._set_show_grid(self._show_grid, persist=False)

        if not self._restoring_settings:
            self._apply_dock_visibility_from_prefs()

    def _restore_settings(self) -> None:
        """Apply all values from btf_viewer.rc after the UI has been built."""
        self._restoring_settings = True
        self._dock_startup_metrics = None
        self._dock_startup_needs_defaults = False
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

        self._vm.settings.load_theme_from_rc(s)
        self._vm.settings.load_view_prefs_from_rc(s)
        self._apply_view_prefs_from_vm()

        if hasattr(self, "_stats_panel"):
            _stats_heights: Dict[str, int] = {}
            for _sid in ("migrations", "exec", "block", "inter"):
                _default = (STATS_TABLE_MIG_DEFAULT_H if _sid == "migrations"
                            else STATS_TABLE_DEFAULT_H)
                _h = s.get_int("stats", f"table_height_{_sid}", _default)
                _stats_heights[_sid] = _h
            self._stats_panel.apply_section_table_heights(_stats_heights)
            self._stats_panel.set_section_pins(
                s.get("stats", "pinned_sections", ""), emit=False)
            self._stats_panel.set_section_order(
                s.get("stats", "section_order", ""), emit=False)

        # Dock layout: sizes from dock_metrics; visibility from [view] show_* keys.
        # Qt saveState/restoreState embeds dock visibility and fights show_legend,
        # so we no longer restore the serialized dock_state blob (v10+).
        _DOCK_LAYOUT_VERSION = DEFAULT_DOCK_LAYOUT_VERSION
        _profile_key = self._dock_profile_key(self.width(), self.height())

        _saved_profile_lw = s.get_int("dock_profile_label_width", _profile_key, -1)
        if _saved_profile_lw < 60:
            _saved_profile_lw = s.get_int("view", "label_width", LABEL_WIDTH)
        if _saved_profile_lw >= 60:
            self._label_width_val = _saved_profile_lw
            self._view._scene.set_label_width(_saved_profile_lw)

        _saved_metrics = (
            s.get("window", "dock_metrics", "").strip()
            or s.get("dock_profile_metrics", _profile_key, "").strip()
        )
        if _saved_metrics:
            self._dock_startup_metrics = _saved_metrics
        else:
            self._dock_startup_needs_defaults = True

        _saved_ver = s.get("window", "dock_layout_version", "0")
        if _saved_ver != _DOCK_LAYOUT_VERSION:
            s.set_many("window", {
                "dock_state": "",
                "dock_layout_version": _DOCK_LAYOUT_VERSION,
            }, flush=False)

        # Panel visibility and resizeDocks run once after the window is shown.
        self._schedule_startup_dock_layout()

        # Keep the Light-theme menu label in sync when we restored a light theme.
        if not self._is_dark:
            self._act_theme.setText("Switch to &Dark Theme")

        self._refresh_zoom_ui_unit()

    def resizeEvent(self, event) -> None:  # noqa: N802
        """Re-autofit CPU load pane height when the window grows (stretch factor 0)."""
        super().resizeEvent(event)
        if (self._shutting_down or self._cpu_splitter_user_sized
                or not self._show_cpu_load or self._active_tab is None):
            return
        self._cpu_load_autofit_timer.start()

    def _on_cpu_load_autofit_timeout(self) -> None:
        if (self._shutting_down or self._cpu_splitter_user_sized
                or not self._show_cpu_load):
            return
        self._autofit_cpu_load_height()

    def closeEvent(self, event) -> None:
        """Persist runtime state and exit quickly (avoid blocking GC on large traces)."""
        self._shutting_down = True
        self._block_dock_widget_signals(True)

        for tab in self._tabs:
            tab.view._zoom_timer.stop()
            tab.view._pan_timer.stop()
            tab.view._pan_heartbeat.stop()
            tab.view._resize_timer.stop()
        self._cpu_load_autofit_timer.stop()
        if hasattr(self, "_settings_view"):
            self._settings_view._zoom_timer.stop()
            self._settings_view._pan_timer.stop()
            self._settings_view._pan_heartbeat.stop()
            self._settings_view._resize_timer.stop()

        self._dismiss_auxiliary_windows()

        # Stop an in-flight parse if the user quits during load.  On exit we do
        # not block indefinitely — orphan a still-running worker and let the OS
        # reclaim the process rather than freezing the UI for a large trace.
        if not self._stop_parse_thread(wait_ms=1000):
            self._disconnect_parse_signals()
            self._parse_thread = None

        self._save_current_trace_state()
        # Persist while docks are still visible — hide() would fire spurious
        # visibilityChanged(False) and save show_legend=false incorrectly.
        self._persist_settings()
        self._report_settings_io_failure(prefix="Settings save warning")

        self.hide()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

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
        self._persisting_settings = True
        try:
            # Read live label width without touching AppSettingsViewModel setters
            # (those emit settings_changed and rebuild the whole UI on large traces).
            label_width = int(self._view._scene._label_width)
            self._vm.settings._model.label_width = label_width

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

            show_legend = self._show_legend

            # View settings
            s.set_many("view", {
                "theme":         "dark" if self._is_dark else "light",
                "horizontal":    str(self._view._scene._horizontal).lower(),
                "view_mode":     self._view_mode,
                "show_sti":      str(self._show_sti).lower(),
                "show_grid":     str(self._show_grid).lower(),
                "show_legend":   str(show_legend).lower(),
                "show_stats":    str(self._show_stats).lower(),
                "show_marks":    str(self._show_marks).lower(),
                "show_find":     str(self._show_find).lower(),
                "show_ai":       str(getattr(self, "_show_ai", True)).lower(),
                "font_size":     str(self._font_size_val),
                "ui_font_size":  str(self._ui_font_size_val),
                "max_cursors":   str(self._max_cursors_val),
                "label_width":       str(label_width),
                "row_height":        str(self._row_height_val),
                "row_gap":           str(self._row_gap_val),
                "timescale_per_px_default": str(self._timescale_per_px_default_val),
                "hover_highlight":   str(self._hover_highlight_val).lower(),
                "time_decimals":     str(self._time_decimals_val),
            }, flush=False)

            if self._cpu_splitter_bottom_h is not None and self._cpu_splitter_bottom_h > 0:
                s.set_many("view", {
                    "cpu_splitter_bottom_h": str(self._cpu_splitter_bottom_h),
                    "cpu_splitter_user_sized": str(self._cpu_splitter_user_sized).lower(),
                }, flush=False)

            if hasattr(self, "_stats_panel"):
                for _sid, _h in self._stats_panel.section_table_heights().items():
                    s.set("stats", f"table_height_{_sid}", str(_h), flush=False)
                s.set(
                    "stats", "pinned_sections",
                    stats_pins_to_rc(self._stats_panel.section_pins()),
                    flush=False,
                )
                s.set(
                    "stats", "section_order",
                    stats_section_order_to_rc(self._stats_panel.section_order()),
                    flush=False,
                )

            # Dock layout - serialise dock sizes/positions (visibility is in [view]).
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
            s.set("dock_profile_label_width", _profile_key, str(label_width), flush=False)
            s.set("dock_profile_metrics", _profile_key, self._collect_dock_metrics(), flush=False)
            # Keep only the newest size profiles and keep both sections aligned.
            s.prune_section("dock_profiles", _MAX_DOCK_PROFILES, flush=False)
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
        finally:
            self._persisting_settings = False

    def _finish_parse_thread(self, wait_ms: int = 30_000) -> bool:
        """Disconnect, join, and schedule deletion of the current parser thread."""
        thread = self._parse_thread
        if thread is None:
            return True
        self._disconnect_parse_signals()
        self._parse_thread = None
        if thread.isRunning():
            thread.wait(wait_ms)
        if thread.isRunning():
            # Still running after the wait budget: destroying the Python wrapper
            # now while the underlying QThread is alive risks a crash, so keep a
            # reference and let Qt delete it once the thread actually finishes.
            thread.finished.connect(thread.deleteLater)
            self._orphaned_parse_threads.append(thread)
            return False
        thread.deleteLater()
        return True

    def _stop_parse_thread(self, wait_ms: int) -> bool:
        """Stop current parser thread safely; return True when fully stopped."""
        thread = self._parse_thread
        if thread is None:
            return True
        if thread.isRunning():
            thread.requestInterruption()
        return self._finish_parse_thread(wait_ms=wait_ms)

    def _teardown_scene(self) -> None:
        """Detach trace data quickly on exit.

        Avoid ``QGraphicsScene.clear()`` and background ``del`` threads here:
        both can take many seconds on multi-million-segment traces and block
        process exit (non-daemon GC threads hold the interpreter open).
        """
        global _info_popup
        if _info_popup is not None:
            _info_popup.hide()
            _info_popup = None

        for tab in self._tabs:
            tab.cpu_load_graph.set_trace(None)
            sc = tab.view._scene
            sc._trace = None
            sc._frozen_items = []
            sc._frozen_top_items = []
            sc._cursor_items = []
            sc._hover_overlay_items = []
            sc._hover_items = []
            sc._hover_line_ns = None
            sc._task_row_rects = {}
            tab.vm.trace = None
        self._tabs.clear()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            if any(is_btf_open_path(u.toLocalFile()) for u in event.mimeData().urls()):
                event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if is_btf_open_path(path):
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

    def _apply_theme(self, is_dark: bool, *, op: int | None = None) -> None:
        """Apply the dark or light UI theme to the entire application.

        This is the single authoritative method for all theme changes.
        Color values are defined in ``_theme_tokens``; all QSS and widget
        overrides are driven from that table so there is only one place
        to edit when adjusting a color.

        Heavy per-widget sync and rebuilds are deferred to the next event-loop
        tick so they do not run while Qt is still repolishing widgets after
        ``app.setStyleSheet`` (avoids macOS crashes).
        """
        if op is not None and op != self._theme_op_id:
            return
        if self._applying_theme:
            if op is not None:
                QTimer.singleShot(20, lambda: self._apply_theme_if_current(op, is_dark))
            return
        self._applying_theme = True
        app = QApplication.instance()
        _ok = False
        self.setUpdatesEnabled(False)
        try:
            self._is_dark = bool(is_dark)

            # Application-wide font (menus, toolbar, status bar).
            _ui_font_size = getattr(self, '_ui_font_size_val', UI_FONT_SIZE)
            _ui_fs = _ui_font_stylesheet_size(_ui_font_size)
            base_font = _application_ui_font(_ui_font_size)
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
            QToolBar  {{ background:{c['mid']}; color:{c['text']}; border:none; spacing:4px;
                         font-size:{_ui_fs}; }}
            QToolBar::separator {{ width:1px; background:{c['sep']}; margin:3px 2px; }}
            QToolButton {{ font-size:{_ui_fs}; color:{c['text']}; background:transparent; }}
            QToolButton:hover    {{ background:{c['tb_hover']};      border-radius:3px; color:{c['text']}; }}
            QToolButton:pressed  {{ background:{c['tb_pressed']};    border-radius:3px; color:{c['text']}; }}
            QToolButton:checked  {{ background:{c['tb_checked_bg']}; border-radius:3px; color:{c['tb_checked_fg']}; }}
            QToolButton:disabled {{ color:{c['tb_disabled']}; }}
            QToolBar QComboBox {{ font-size:{_ui_fs}; color:{c['text']}; padding:1px 4px; min-height:0; }}
            QStatusBar  {{ background:{c['win_bg']}; color:{c['status_text']}; font-size:{_ui_fs};
                           border-top:1px solid {c['sep']}; }}
            QStatusBar QLabel {{ font-size:{_ui_fs}; color:{c['sub_text']}; }}
            QStatusBar QLabel#zoomScaleLabel {{ font-size:{_ui_fs}; color:{c['status_text']}; }}
            QStatusBar QCheckBox {{ font-size:{_ui_fs}; color:{c['sub_text']}; padding: 0 4px; }}
            QLabel      {{ font-size:{_ui_fs}; }}
            QLabel#trace_quality_banner {{
                background:#5c3d00; color:#ffe8a3; padding:6px 12px; font-size:12px;
                border-bottom:1px solid #8a6200;
            }}
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
            QTableWidget#stats_table {{ background:{c['win_base']}; color:{c['text']};
                         border:none; gridline-color:transparent; }}
            QTableWidget#stats_table::item {{ color:{c['text']};
                         border:none; padding:0px 3px; }}
            QHeaderView#stats_table_header::section {{ background:{c['mid']};
                         color:{c['muted_text']}; border:none; padding:0px 10px 0px 3px; }}
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
            QWidget#cpu_load_handle {{
                background:{c['sep']};
            }}
            QWidget#cpu_load_handle:hover {{
                background:{c['accent']};
            }}
            QSplitter::handle:horizontal {{
                width:6px;
            }}
            QTabWidget#trace_tab_widget {{ background:{c['win_bg']}; }}
            QTabWidget#trace_tab_widget::tab-bar {{ alignment: left; }}
            QTabWidget#trace_tab_widget::pane {{ background:{c['win_bg']};
                         border:1px solid {c['sep']}; top:-1px; }}
            QTabWidget#trace_tab_widget QTabBar#trace_tab_bar {{
                         background:{c['mid']}; border-bottom:1px solid {c['sep']}; }}
            QTabWidget#trace_tab_widget QTabBar#trace_tab_bar::tab {{
                         background:{c['tab_bg']}; color:{c['tab_fg']}; padding:4px 12px;
                         border:none; border-bottom:2px solid transparent;
                         font-size:{_ui_fs}; }}
            QTabWidget#trace_tab_widget QTabBar#trace_tab_bar::tab:selected {{
                         background:{c['tab_sel_bg']}; color:{c['tab_sel_fg']};
                         border-bottom:2px solid {c['accent']}; }}
            QTabWidget#trace_tab_widget QTabBar#trace_tab_bar::tab:hover:!selected {{
                         background:{c['tab_hover_bg']}; color:{c['tab_hover_fg']}; }}
            QTabWidget#panel_tab_widget {{ background:{c['win_bg']}; }}
            QTabWidget#panel_tab_widget::tab-bar {{
                         background:{c['mid']}; border-bottom:1px solid {c['sep']}; }}
            QTabWidget#panel_tab_widget::pane {{ background:{c['win_bg']};
                         border:1px solid {c['sep']}; top:-1px; }}
            QTabWidget#panel_tab_widget QTabBar#panel_tab_bar {{
                         background:{c['mid']}; border-bottom:1px solid {c['sep']}; }}
            QTabWidget#panel_tab_widget QTabBar#panel_tab_bar::tab {{
                         background:{c['tab_bg']}; color:{c['tab_fg']}; padding:4px 12px;
                         border:none; border-bottom:2px solid transparent;
                         font-size:{_ui_fs}; }}
            QTabWidget#panel_tab_widget QTabBar#panel_tab_bar::tab:selected {{
                         background:{c['tab_sel_bg']}; color:{c['tab_sel_fg']};
                         border-bottom:2px solid {c['accent']}; }}
            QTabWidget#panel_tab_widget QTabBar#panel_tab_bar::tab:hover:!selected {{
                         background:{c['tab_hover_bg']}; color:{c['tab_hover_fg']}; }}
            QTabWidget#marks_tab_widget {{ background:{c['win_bg']}; }}
            QTabWidget#marks_tab_widget::pane {{ background:{c['win_bg']};
                         border:1px solid {c['sep']}; top:-1px; }}
            QTabWidget#marks_tab_widget QTabBar#marks_tab_bar {{
                         background:{c['win_bg']}; }}
        """)
            _ok = True
        finally:
            self.setUpdatesEnabled(True)
            self._applying_theme = False
            if not _ok and op is not None:
                self._release_theme_change()

        if hasattr(self, '_view'):
            self._schedule_theme_widgets(op)
        elif op is not None:
            # No view yet (called before _build_ui); nothing to schedule.
            self._release_theme_change()

    def _schedule_theme_widgets(self, op: int | None = None) -> None:
        """Defer per-widget theme sync until after app QSS has settled."""
        if self._shutting_down:
            return
        if op is None:
            op = self._theme_op_id
        if not self._theme_widgets_pending:
            self._theme_widgets_pending = True
            QTimer.singleShot(10, lambda: self._apply_theme_widgets_if_current(op))

    def _apply_theme_widgets_if_current(self, op: int) -> None:
        if op != self._theme_op_id:
            self._theme_widgets_pending = False
            return
        QTimer.singleShot(0, lambda: self._apply_theme_widgets_chrome(op))

    def _apply_theme_widgets_chrome(self, op: int) -> None:
        """Dock chrome, stats, toolbar — no timeline/graphics surfaces."""
        if op != self._theme_op_id or self._shutting_down:
            return
        self._apply_theme_widgets(op=op)

    def _apply_theme_widgets_timeline(self, op: int) -> None:
        """Timeline / CPU-load surfaces (deferred from chrome pass)."""
        if op != self._theme_op_id or self._shutting_down:
            return
        is_dark = self._is_dark
        c = self._theme_tokens(is_dark)
        if not hasattr(self, '_view'):
            self._release_theme_change()
            return
        win_bg = QColor(c["win_bg"])
        defer_rebuilds = False
        _ok = False
        self.setUpdatesEnabled(False)
        try:
            for view in self._iter_tab_views():
                self._sync_timeline_view_theme(view, is_dark)
                view._scene.set_theme(is_dark, rebuild=False)
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
            defer_rebuilds = any(
                v._scene._trace is not None for v in self._iter_tab_views())
            _ok = True
        finally:
            self.setUpdatesEnabled(True)
            if not _ok:
                self._release_theme_change()
        if defer_rebuilds:
            QTimer.singleShot(0, lambda: self._finish_theme_rebuilds_if_current(op))
        else:
            self._release_theme_change()

    def _apply_theme_widgets(self, *, op: int | None = None) -> None:
        """Per-widget palette/stylesheet sync (runs on the next event-loop tick)."""
        self._theme_widgets_pending = False
        if op is not None and op != self._theme_op_id:
            return
        if self._shutting_down:
            return
        if self._applying_theme:
            if op is not None:
                QTimer.singleShot(20, lambda: self._apply_theme_widgets_if_current(op))
            return
        self._applying_theme = True
        is_dark = self._is_dark
        c = self._theme_tokens(is_dark)
        _ui_font_size = getattr(self, '_ui_font_size_val', UI_FONT_SIZE)
        defer_rebuilds = False
        _ok = False
        self.setUpdatesEnabled(False)
        try:
            if hasattr(self, '_range_stats_label'):
                _pal = self._range_stats_label.palette()
                _pal.setColor(QPalette.WindowText, QColor(c['muted_text']))
                self._range_stats_label.setPalette(_pal)
            if hasattr(self, '_find_status'):
                _pal = self._find_status.palette()
                _pal.setColor(QPalette.WindowText, QColor(c['muted_text']))
                self._find_status.setPalette(_pal)
            if hasattr(self, '_cur_hint'):
                _pal = self._cur_hint.palette()
                _pal.setColor(QPalette.WindowText, QColor(c['muted_text']))
                self._cur_hint.setPalette(_pal)
            if hasattr(self, '_welcome_label'):
                self._welcome_label.setText(
                    f"<h2 style='color:{c['welcome_h2']};'>RTOS BTF Viewer</h2>"
                    f"<p style='color:{c['welcome_p']}; font-size:11pt;'>"
                    "Drop a <b>.btf</b> file here<br>"
                    "or press <b>Ctrl+O</b> to open one</p>"
                )
            if hasattr(self, '_view'):
                defer_rebuilds = any(
                    v._scene._trace is not None for v in self._iter_tab_views())
            self._sync_trace_tab_widget_theme(is_dark)
            self._sync_panel_tabs_theme(is_dark)
            if hasattr(self, '_legend'):
                self._legend.update_theme(is_dark, defer_rebuild=defer_rebuilds)
            if getattr(self, '_legend_host', None) is not None:
                _legend_host = self._legend_host
                _host_pal = _legend_host.palette()
                _host_pal.setColor(QPalette.Window, QColor(c['win_bg']))
                _host_pal.setColor(QPalette.Base, QColor(c['win_bg']))
                _legend_host.setPalette(_host_pal)
            if hasattr(self, '_stats_panel'):
                self._stats_panel.set_dark(is_dark, refresh_tables=False)
            if hasattr(self, '_stats_panel'):
                self._stats_panel._ui_font_size = _ui_font_size
                self._stats_panel._sync_stats_panel_chrome_font()
            if hasattr(self, '_cursor_bar'):
                self._cursor_bar.update_theme(is_dark, _ui_font_size)
            _ic_color = "#CCCCCC" if is_dark else "#555555"
            if getattr(self, '_tb_icon_actions', None):
                for _act, _ic_path in self._tb_icon_actions:
                    _act.setIcon(_svg_icon(_ic_path, _ic_color))
            if hasattr(self, '_tb_show_all_tasks_btn'):
                _all_fg = c.get('tb_checked_fg', _ic_color)
                self._tb_show_all_tasks_btn.setIcon(
                    _heatmap_clear_icon(_all_fg, is_dark=is_dark))
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
            self._sync_toolbar_theme(c)
            _ok = True
        finally:
            self.setUpdatesEnabled(True)
            self._applying_theme = False
            if not _ok:
                self._release_theme_change()

        if defer_rebuilds:
            rebuild_op = op if op is not None else self._theme_op_id
            QTimer.singleShot(0, lambda: self._apply_theme_widgets_timeline(rebuild_op))
        else:
            if hasattr(self, '_stats_panel') and self._stats_panel._trace is not None:
                QTimer.singleShot(0, self._stats_panel._refresh_stats_table_themes)
            self._release_theme_change()

    def _release_theme_change(self) -> None:
        self._theme_change_in_flight = False

    def _finish_theme_rebuilds_if_current(self, op: int) -> None:
        if op != self._theme_op_id:
            self._release_theme_change()
            return
        self._finish_theme_rebuilds()

    def _finish_theme_rebuilds(self) -> None:
        if self._shutting_down:
            self._release_theme_change()
            return
        op = self._theme_op_id
        if hasattr(self, '_stats_panel'):
            QTimer.singleShot(0, self._stats_panel._refresh_stats_table_themes)
        QTimer.singleShot(50, lambda: self._rebuild_timelines_for_theme_if_current(op))

    def _rebuild_timelines_for_theme_if_current(self, op: int) -> None:
        if op != self._theme_op_id or self._shutting_down:
            self._release_theme_change()
            return
        self.setUpdatesEnabled(False)
        try:
            for view in self._iter_tab_views():
                sc = view._scene
                if sc._trace is not None:
                    sc.rebuild()
                    view.viewport().update()
        finally:
            self.setUpdatesEnabled(True)
            self._release_theme_change()

    def _sync_toolbar_theme(self, c: dict) -> None:
        """Explicit toolbar palette (Windows / Fusion may ignore QSS text colour)."""
        tb = getattr(self, "_tb", None)
        if tb is None:
            return
        fg = QColor(c["text"])
        bg = QColor(c["mid"])
        pal = tb.palette()
        pal.setColor(QPalette.ColorRole.Window, bg)
        pal.setColor(QPalette.ColorRole.WindowText, fg)
        pal.setColor(QPalette.ColorRole.ButtonText, fg)
        pal.setColor(QPalette.ColorRole.Text, fg)
        pal.setColor(QPalette.ColorRole.Button, bg)
        tb.setPalette(pal)
        tb.setAutoFillBackground(True)
        for btn in tb.findChildren(QToolButton):
            bp = btn.palette()
            bp.setColor(QPalette.ColorRole.ButtonText, fg)
            bp.setColor(QPalette.ColorRole.WindowText, fg)
            btn.setPalette(bp)
        combo = getattr(self, "_zoom_preset_combo", None)
        if combo is not None:
            cp = combo.palette()
            cp.setColor(QPalette.ColorRole.Text, fg)
            cp.setColor(QPalette.ColorRole.ButtonText, fg)
            combo.setPalette(cp)

    # Thin wrappers kept for any external callers.
    def _apply_dark_theme(self)  -> None: self._apply_theme(True)
    def _apply_light_theme(self) -> None: self._apply_theme(False)

    def _toggle_theme(self) -> None:
        if self._theme_change_in_flight:
            return
        self._theme_change_in_flight = True
        self._theme_op_id += 1
        op = self._theme_op_id
        self._is_dark = not self._is_dark
        self._settings.set("view", "theme", "dark" if self._is_dark else "light")
        QTimer.singleShot(0, lambda: self._apply_theme_if_current(op, self._is_dark))

    def _apply_theme_if_current(self, op: int, is_dark: bool) -> None:
        if op != self._theme_op_id:
            return
        self._apply_theme(is_dark, op=op)

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

        # Undo / Redo stacks live in TraceTabViewModel (per tab).
        self._undo_suppress: bool = False

        self._welcome_page = QWidget()
        _wl = QVBoxLayout(self._welcome_page)
        _wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _wlbl = QLabel(
            "<h2 style='color:#888;'>RTOS BTF Viewer</h2>"
            "<p style='color:#666; font-size:11pt;'>"
            "Drop a <b>.btf</b> file here<br>"
            "or press <b>Ctrl+O</b> to open one</p>"
        )
        _wlbl.setTextFormat(Qt.TextFormat.RichText)
        _wlbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _wl.addWidget(_wlbl)
        self._welcome_label = _wlbl

        self._tab_widget = QTabWidget()
        self._tab_widget.setTabBar(_LeftAlignedTabBar(self._tab_widget))
        self._tab_widget.setTabsClosable(True)
        # Native document-mode tabs on macOS ignore QSS/palette theme updates.
        if sys.platform == "darwin":
            self._tab_widget.setDocumentMode(False)
            self._tab_widget.setStyle(_LeftTabStyle())
        else:
            self._tab_widget.setDocumentMode(True)
        self._tab_widget.setMovable(True)
        self._tab_widget.tabCloseRequested.connect(self._close_trace_tab)
        self._tab_widget.currentChanged.connect(self._on_trace_tab_changed)

        self._central_stack = QStackedWidget()
        self._central_stack.addWidget(self._welcome_page)
        self._central_stack.addWidget(self._tab_widget)
        self._central_stack.setCurrentIndex(0)

        self._trace_quality_banner = QLabel()
        self._trace_quality_banner.setObjectName("trace_quality_banner")
        self._trace_quality_banner.setWordWrap(True)
        self._trace_quality_banner.setVisible(False)

        self._central_host = QWidget()
        _central_lay = QVBoxLayout(self._central_host)
        _central_lay.setContentsMargins(0, 0, 0, 0)
        _central_lay.setSpacing(0)
        _central_lay.addWidget(self._trace_quality_banner)
        _central_lay.addWidget(self._central_stack, 1)
        self.setCentralWidget(self._central_host)

        # --- Legend panel (hosted in the right-panel Legend tab) ---
        self._build_legend_panel()

        # --- Statistics panel (widget only; hosted in right-panel tabs) ---
        self._build_stats_panel()

        # --- Marks dock (bookmarks + annotations) ---
        marks_host = QWidget()
        marks_host.setMinimumWidth(0)
        self._marks_host = marks_host
        marks_v = QVBoxLayout(marks_host)
        marks_v.setContentsMargins(6, 6, 6, 6)
        marks_v.setSpacing(6)
        marks_v.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        marks_tabs = QTabWidget()

        # ---- Cursors comparison tab ----
        cur_page = QWidget()
        cur_v = QVBoxLayout(cur_page)
        cur_v.setContentsMargins(0, 0, 0, 0)
        cur_v.setSpacing(2)
        self._cursor_table = QTableWidget(0, 4)
        self._cursor_table.setHorizontalHeaderLabels(["#", "Time", "Task at cursor", "Delta to C1"])
        self._cursor_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._cursor_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._cursor_table.verticalHeader().setVisible(False)
        self._cursor_table.setAlternatingRowColors(True)
        self._cursor_table.cellClicked.connect(self._on_cursor_table_clicked)
        _StatsPanel._fix_stats_table_column_widths(self._cursor_table)
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
        self._bookmark_list.itemClicked.connect(lambda item: self._jump_to_ns(int(item.data(Qt.ItemDataRole.UserRole + 1))))
        self._bookmark_list.itemDoubleClicked.connect(lambda item: self._jump_to_ns(int(item.data(Qt.ItemDataRole.UserRole + 1))))
        self._bookmark_list.itemChanged.connect(self._on_bookmark_item_changed)
        _bm_del_key = QShortcut(QKeySequence(Qt.Key.Key_Delete), self._bookmark_list)
        _bm_del_key.setContext(Qt.ShortcutContext.WidgetShortcut)
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
        self._annotation_list.itemClicked.connect(lambda item: self._jump_to_ns(int(item.data(Qt.ItemDataRole.UserRole + 1))))
        self._annotation_list.itemDoubleClicked.connect(
            lambda item: self._edit_selected_annotation())
        _an_del_key = QShortcut(QKeySequence(Qt.Key.Key_Delete), self._annotation_list)
        _an_del_key.setContext(Qt.ShortcutContext.WidgetShortcut)
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
        self._marks_tabs = marks_tabs
        self._range_stats_label = QLabel("Range: place two cursors to measure")
        self._range_stats_label.setStyleSheet("color:#999;")
        self._range_stats_label.setWordWrap(True)
        marks_v.addWidget(self._range_stats_label)

        marks_io_row = QGridLayout()
        marks_io_row.setContentsMargins(0, 0, 0, 0)
        marks_io_row.setHorizontalSpacing(6)
        marks_io_row.setVerticalSpacing(4)
        marks_import_btn = QPushButton("Import")
        marks_import_btn.setToolTip("Load bookmarks and annotations from a CSV file")
        marks_import_btn.clicked.connect(self._import_marks_csv)
        marks_io_row.addWidget(marks_import_btn, 0, 0)
        marks_export_btn = QPushButton("Export")
        marks_export_btn.setToolTip("Save all bookmarks and annotations to a CSV file")
        marks_export_btn.clicked.connect(self._export_marks_csv)
        marks_io_row.addWidget(marks_export_btn, 0, 1)
        marks_session_btn = QPushButton("Session")
        marks_session_btn.setToolTip(
            "Export portable session JSON (cursors, marks, viewport — Web compatible)")
        marks_session_btn.clicked.connect(self._export_portable_session)
        marks_io_row.addWidget(marks_session_btn, 1, 0)
        marks_session_import_btn = QPushButton("Import session")
        marks_session_import_btn.setToolTip("Import portable session JSON")
        marks_session_import_btn.clicked.connect(self._import_portable_session)
        marks_io_row.addWidget(marks_session_import_btn, 1, 1)
        for btn in (marks_import_btn, marks_export_btn, marks_session_btn,
                    marks_session_import_btn):
            btn.setMinimumWidth(0)
            btn.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        marks_v.addLayout(marks_io_row)

        # --- Find panel (tab content) ---
        find_host = QWidget()
        find_host.setMinimumWidth(0)
        self._find_host = find_host
        find_v = QVBoxLayout(find_host)
        find_v.setContentsMargins(6, 6, 6, 6)
        find_v.setSpacing(6)
        self._find_input = QLineEdit()
        self._find_input.setPlaceholderText("Find task, annotation, or migration…")
        self._find_input.textChanged.connect(self._recompute_find_hits)
        self._find_input.returnPressed.connect(self._find_next)
        find_v.addWidget(self._find_input)
        self._find_mode_combo = QComboBox()
        self._find_mode_combo.addItems([
            "Contains", "Exact", "Regex", "Migrations",
            "STI", "Intervals", "Lifecycle", "Pointers",
        ])
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

        # --- AI Assistant panel (tab content) ---
        self._ai_panel = create_ai_assistant_panel(
            self,
            get_context=self._ai_build_context,
            get_settings=self._ai_read_settings,
            on_open_settings=lambda: self._open_settings("AI"),
            on_save_settings=self._ai_save_settings_patch,
            on_jump=self._ai_jump_time_unit,
            get_loaded_tabs=self._ai_list_loaded_tabs,
            build_compare_context=self._ai_build_compare_context,
        )

        # --- Right panel: Statistics / Marks / Find / Legend / AI (web parity) ---
        self._panel_tabs = QTabWidget()
        if sys.platform == "darwin":
            self._panel_tabs.setTabBar(_LeftAlignedTabBar(self._panel_tabs))
        self._panel_tabs.setDocumentMode(False)
        self._panel_tabs.addTab(self._stats_panel, "Statistics")
        self._panel_tabs.addTab(marks_host, "Marks")
        self._panel_tabs.addTab(find_host, "Find")
        self._panel_tabs.addTab(self._legend_host, "Legend")
        self._panel_tabs.addTab(self._ai_panel, "AI")

        panel_dock = QDockWidget("", self)
        panel_dock.setObjectName("dock_panel")
        panel_dock.setWidget(self._panel_tabs)
        panel_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self._apply_right_dock_min_width(panel_dock)
        panel_dock.setMinimumHeight(200)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, panel_dock)
        self._panel_dock = panel_dock
        # Legacy aliases — all panel tabs live in one dock.
        self._stats_dock = panel_dock
        self._marks_dock = panel_dock
        self._find_dock = panel_dock

        self._sync_panel_tab_visibility()
        self._focus_statistics_panel()
        # Default dock sizes are applied in _restore_settings via QTimer.singleShot
        # AFTER the window is shown, where resizeDocks() is actually effective.

        # Keep runtime state in sync if the user closes a dock via its X button
        self._panel_dock.visibilityChanged.connect(self._on_panel_dock_visibility_changed)

        self._wire_resize_cursors()

        # --- Signal wiring: legend <-> scene highlight sync (bound per active tab) ---
        self._legend.task_clicked.connect(self._on_legend_task_clicked)
        self._legend.migrated_filter_changed.connect(self._on_legend_migrated_filter)
        self._legend.clear_heatmap_filter.connect(self._clear_heatmap_task_filter)

    def _on_close_tab_action(self) -> None:
        idx = self._tab_widget.currentIndex()
        if idx >= 0:
            self._close_trace_tab(idx)

    def _clear_panels_for_empty_session(self) -> None:
        """Drop last-trace chrome after Close All / last tab close."""
        if hasattr(self, "_stats_panel"):
            self._stats_panel.clear_trace()
        if hasattr(self, "_legend"):
            self._legend.rebuild(None, show_sti=self._show_sti)
        if hasattr(self, "_find_input"):
            self._find_input.blockSignals(True)
            self._find_input.clear()
            self._find_input.blockSignals(False)
        if hasattr(self, "_find_status"):
            self._find_status.setText("0 matches")
        self._close_heatmap_dialog()
        self._close_chord_dialog()
        if hasattr(self, "_tb_analysis_btn"):
            self._tb_analysis_btn.setEnabled(False)

    def _on_close_all_tabs_action(self) -> None:
        for _ in range(len(self._tabs)):
            self._close_trace_tab(0)

    def _wire_resize_cursors(self) -> None:
        """Resize cursors on splitters and dock/central pane edges."""
        vert = Qt.CursorShape.SizeVerCursor
        margin = _RESIZE_EDGE_PX

        def _dock_active(dock: QDockWidget):
            return (lambda: dock.isVisible() and not dock.isFloating())

        for w in (self._central_stack, self._tab_widget):
            w.setMouseTracking(True)
            w.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            filt = _DockWidthResizeFilter(
                w, self, "right", margin, self._any_visible_right_dock)
            w.installEventFilter(filt)
            w._dock_width_resize_filter = filt  # prevent GC

        for dock in self._right_docks():
            dock.setMouseTracking(True)
            dock.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            ok = _dock_active(dock)
            width_filt = _DockWidthResizeFilter(dock, self, "left", margin, ok)
            dock.installEventFilter(width_filt)
            dock._dock_width_resize_filter = width_filt

        resize_guard = _RightDockResizeGuard(self, self._panel_dock)
        self._panel_dock.installEventFilter(resize_guard)
        self._panel_dock._dock_resize_guard = resize_guard

        QTimer.singleShot(0, lambda: _wire_splitter_handle_cursors(self))

    def _build_legend_panel(self) -> None:
        """Create the legend widget hosted in the right-panel Legend tab."""
        self._legend = _LegendWidget()
        self._legend.setMinimumWidth(0)
        legend_host = QWidget()
        legend_host.setObjectName("legend_tab_host")
        legend_host.setAutoFillBackground(True)
        legend_v = QVBoxLayout(legend_host)
        legend_v.setContentsMargins(6, 6, 6, 6)
        legend_v.setSpacing(0)
        legend_v.addWidget(self._legend)
        self._legend_host = legend_host

    def _build_stats_panel(self) -> None:
        """Create the statistics panel widget (hosted in the right-panel tab bar)."""
        self._stats_panel = _StatsPanel()
        self._stats_panel.task_clicked.connect(self._on_legend_task_clicked)
        self._stats_panel.segment_jump.connect(self._on_segment_jump)
        self._stats_panel.plot_point_clicked.connect(self._on_stats_plot_point_clicked)
        self._stats_panel.core_clicked.connect(self._on_stats_core_clicked)
        self._stats_panel.open_pair_heatmap.connect(self._on_open_pair_heatmap)
        self._stats_panel.open_pair_chord.connect(self._on_open_pair_chord)
        self._stats_panel.open_settings_requested.connect(self._open_settings)
        self._stats_panel.section_pins_changed.connect(self._on_section_pins_changed)
        self._stats_panel.section_order_changed.connect(self._on_section_order_changed)
        self._stats_panel._btn_compare_mig.clicked.connect(self._open_trace_compare)
        self.setAcceptDrops(True)

    def _on_section_pins_changed(self, _pins: list) -> None:
        """Persist pinned statistics sections to btf_viewer.rc immediately."""
        if self._restoring_settings or self._shutting_down:
            return
        try:
            self._settings.set(
                "stats", "pinned_sections",
                stats_pins_to_rc(self._stats_panel.section_pins()),
                flush=True,
            )
        except Exception:
            pass

    def _on_section_order_changed(self, _order: list) -> None:
        """Persist statistics section order to btf_viewer.rc immediately."""
        if self._restoring_settings or self._shutting_down:
            return
        try:
            self._settings.set(
                "stats", "section_order",
                stats_section_order_to_rc(self._stats_panel.section_order()),
                flush=True,
            )
        except Exception:
            pass

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
        self._act_export_perfetto = fm.addAction(
            "Export &Perfetto…", self._on_export_perfetto, "Ctrl+Shift+E")
        self._act_export_perfetto.setEnabled(False)
        self._act_close_tab = fm.addAction("Close &Tab", self._on_close_tab_action, QKeySequence.Close)
        self._act_close_tab.setEnabled(False)
        self._act_close_all_tabs = fm.addAction("Close &All Tabs", self._on_close_all_tabs_action)
        self._act_close_all_tabs.setEnabled(False)
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
        _fit_act = vm.addAction("&Fit to window",  lambda: self._view.zoom_fit())
        _fit_act.setShortcuts([QKeySequence("Ctrl+0"), QKeySequence("F")])
        vm.addSeparator()
        self._act_task_view = vm.addAction("Task &View", lambda: self._set_view_mode("task"))
        self._act_core_view = vm.addAction("&Core View", lambda: self._set_view_mode("core"))
        self._act_task_view.setCheckable(True)
        self._act_core_view.setCheckable(True)
        self._act_task_view.setChecked(True)
        vm.addSeparator()
        self._act_theme = vm.addAction("Switch to &Light Theme", self._toggle_theme)
        self._act_theme.setShortcut(QKeySequence("D"))
        _grid_act = vm.addAction("Toggle &Grid lines", lambda: self._set_show_grid(not self._show_grid))
        _grid_act.setShortcut(QKeySequence("G"))
        _sti_act  = vm.addAction("Toggle &STI events", lambda: self._set_show_sti(not self._show_sti))
        _sti_act.setShortcut(QKeySequence("I"))
        vm.addSeparator()
        vm.addAction("⚙ &Settings…", self._open_settings, "Ctrl+,")
        vm.addSeparator()
        self._act_show_legend = vm.addAction("Show Le&gend Panel", self._toggle_show_legend_panel)
        self._act_show_legend.setCheckable(True)
        self._act_show_legend.setChecked(self._show_legend)
        self._act_show_marks = vm.addAction("Show &Marks Panel", self._toggle_show_marks_panel)
        self._act_show_marks.setCheckable(True)
        self._act_show_marks.setChecked(self._show_marks)
        self._act_show_find = vm.addAction("Show &Find Panel", self._toggle_show_find_panel)
        self._act_show_find.setCheckable(True)
        self._act_show_find.setChecked(self._show_find)
        self._act_show_ai = vm.addAction("Show &AI Assistant", self._toggle_show_ai_panel)
        self._act_show_ai.setCheckable(True)
        self._act_show_ai.setChecked(getattr(self, "_show_ai", True))
        self._sync_ai_menu()

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

    def _build_toolbar(self) -> None:
        tb = self.addToolBar("Main")
        tb.setObjectName("toolbar_main")
        self._tb = tb
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
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
                                      "Zoom view to fit between cursor C1 and last cursor  (Ctrl+R)")
        self._tb_zoom_range_btn.setEnabled(False)

        _ia("Find", self._focus_find, _IC_FIND,
            "Find task, annotation, or migration  (Ctrl+F)")
        self._tb_find_btn = self._tb_icon_actions[-1][0]
        self._tb_find_btn.setShortcut(QKeySequence.StandardKey.Find)

        # Zoom-preset quick-pick combo (labels/values rebuilt per trace unit)
        self._zoom_presets: list = []   # populated by _rebuild_zoom_presets()
        self._zoom_preset_combo = QComboBox()
        # Use a QListView popup instead of macOS native NSMenu - the native
        # popup ignores stylesheets and looks inconsistent with the themed UI.
        self._zoom_preset_combo.setView(QListView())
        self._zoom_preset_combo.setFont(_application_ui_font(
            getattr(self, '_ui_font_size_val', UI_FONT_SIZE)))
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
                _mw.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
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
            _clw.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._tb_heatmap_btn = _ia(
            "Heatmap", self._open_migration_heatmap, _IC_HEATMAP,
            "Migration & Corridor Inspector — topology + timeline "
            "(multi-core traces only)")
        self._tb_heatmap_btn.setEnabled(False)
        self._tb_show_all_tasks_btn = tb.addAction(
            "All tasks", self._clear_heatmap_task_filter)
        self._tb_show_all_tasks_btn.setCheckable(True)
        self._tb_show_all_tasks_btn.setChecked(True)
        self._tb_show_all_tasks_btn.setIcon(
            _heatmap_clear_icon(is_dark=getattr(self, "_is_dark", True)))
        self._tb_show_all_tasks_btn.setToolTip(
            "Clear heatmap task filter and show all tasks")
        self._tb_show_all_tasks_btn.setVisible(False)
        _saw = tb.widgetForAction(self._tb_show_all_tasks_btn)
        if _saw:
            _saw.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            _saw.setAutoExclusive(False)
        self._tb_analysis_btn = _ia(
            "Analysis", self._open_analysis_findings, _IC_ANALYSIS,
            "Analysis Findings — heuristic load balance, WCET, blocking, "
            "thrashing, deadlines, tick, sync")
        self._tb_analysis_btn.setEnabled(False)
        _aw = tb.widgetForAction(self._tb_analysis_btn)
        if _aw:
            _aw.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
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
            _l2w.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
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

    def _update_trace_quality_banner(self, trace: Optional[BtfTrace] = None) -> None:
        """Show BTF quality / version warnings above the timeline (web parity)."""
        banner = getattr(self, "_trace_quality_banner", None)
        if banner is None:
            return
        if trace is None:
            trace = self._trace
        text = trace_quality_summary(trace)
        if text:
            banner.setText(text)
            banner.setVisible(True)
        else:
            banner.clear()
            banner.setVisible(False)

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
        self._vm.settings.blockSignals(True)
        try:
            self._vm.settings.horizontal = horizontal
        finally:
            self._vm.settings.blockSignals(False)
        self._refresh_find_marker()

    def _set_show_sti(self, show: bool, persist: bool = True) -> None:
        """Apply STI visibility and keep all STI UI controls in sync."""
        show = bool(show)
        if show == self._show_sti:
            return
        self._show_sti = show
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

    def _sync_view_mode_toolbar(self) -> None:
        """Refresh Task/Core toolbar toggles from the current view mode."""
        if not hasattr(self, "_act_task_view"):
            return
        mode = self._view_mode
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
                    scene._core_is_expanded(c) for c in trace.core_names)
                self._tb_expand_all_btn.setChecked(all_expanded)

    def _set_view_mode(self, mode: str) -> None:
        if mode == self._view_mode:
            return
        # Update the model without settings_changed — that handler rebuilds the
        # legend via _set_show_sti even though task/core mode does not change it.
        self._vm.settings._model.view_mode = mode
        self._sync_view_mode_toolbar()
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

    def _set_cpu_splitter_sizes(self, splitter: "_CpuLoadStack", sizes: List[int]) -> None:
        """Apply CPU pane height without treating the move as a user drag."""
        self._cpu_splitter_programmatic = True
        try:
            splitter.setSizes(sizes)
        finally:
            self._cpu_splitter_programmatic = False

    def _remember_cpu_splitter_sizes(self, sizes: List[int]) -> None:
        """Record splitter sizes without triggering settings_changed (see app_settings)."""
        if len(sizes) < 2 or sizes[1] <= 0:
            return
        m = self._vm.settings._model
        m.cpu_splitter_user_sized = True
        m.cpu_splitter_bottom_h = sizes[1]

    def _persist_cpu_splitter_prefs(self) -> None:
        """Write CPU load splitter prefs to rc without re-applying layout."""
        if self._cpu_splitter_bottom_h is None or self._cpu_splitter_bottom_h <= 0:
            return
        self._settings.set_many("view", {
            "cpu_splitter_bottom_h": str(self._cpu_splitter_bottom_h),
            "cpu_splitter_user_sized": str(self._cpu_splitter_user_sized).lower(),
        }, flush=False)

    def _on_cpu_splitter_moved(self, pos: int = 0, index: int = 0) -> None:
        """Remember manual timeline / CPU load split; defer layout until release."""
        if self._cpu_splitter_programmatic or not self._cpu_splitter_user_drag:
            return
        self._cpu_splitter_resizing = True
        self._remember_cpu_splitter_sizes(self._cpu_splitter.sizes())
        self._cpu_splitter_drag_timer.start()

    def _on_cpu_splitter_drag_end(self) -> None:
        """Finish CPU load pane drag — overlay height only, no timeline resize."""
        self._cpu_splitter_resizing = False
        self._cpu_splitter_user_drag = False
        self._persist_cpu_splitter_prefs()
        if tab := self._active_tab:
            tab.cpu_load_graph._schedule_sync_scroll_size()

    def _apply_saved_cpu_splitter(
        self, tab: Optional[_TraceTab] = None, *, force: bool = False,
    ) -> None:
        """Restore a user-resized CPU load pane height on *tab*."""
        if not force and getattr(self, "_cpu_splitter_resizing", False):
            return
        tab = tab or self._active_tab
        if tab is None or not self._cpu_splitter_user_sized:
            return
        bottom = self._cpu_splitter_bottom_h
        if bottom is None or bottom <= 0:
            return
        stack = tab.cpu_splitter
        total = stack.height()
        if total <= 0:
            return
        handle = stack.handleWidth()
        avail = max(140, total - handle)
        bottom = max(
            _CpuLoadScrollArea._MIN_PANE_H,
            min(bottom, CPU_LOAD_PANE_MAX_H, avail - 100),
        )
        top = avail - bottom
        cur = stack.sizes()
        if len(cur) >= 2 and abs(cur[0] - top) <= 1 and abs(cur[1] - bottom) <= 1:
            return
        self._set_cpu_splitter_sizes(stack, [top, bottom])

    def _autofit_cpu_load_height(self) -> None:
        """Resize the CPU load overlay; cap height so extra cores scroll inside."""
        if self._cpu_splitter_user_sized:
            return
        if not self._show_cpu_load:
            return
        tab = self._active_tab
        if tab is None or not tab.cpu_splitter.cpu_visible():
            return
        fit_h = self._cpu_load_graph.preferred_pane_height()
        sizes = tab.cpu_splitter.sizes()
        total = sum(sizes) if sizes else tab.cpu_splitter.height()
        if total <= 0:
            total = tab.cpu_splitter.height()
        new_bottom = max(40, min(fit_h, total - 100))
        self._set_cpu_splitter_sizes(
            tab.cpu_splitter, [max(0, total - new_bottom), new_bottom])
        self._cpu_load_graph._schedule_sync_scroll_size()

    def _drain_pending_open_paths(self) -> None:
        """Open files queued while a previous load was still finishing."""
        while self._pending_open_paths and not self._load_in_progress:
            path = self._pending_open_paths.pop(0)
            self._open_file(path)
            return

    def _finish_load_pipeline(self) -> None:
        """Clear the load guard and resume queued opens / session restore."""
        self._load_in_progress = False
        self._continue_session_restore()
        self._drain_pending_open_paths()

    def _finalize_tab_deferred_work(self, tab: _TraceTab) -> None:
        """Build per-tab CPU bins and statistics after the timeline is shown."""
        if tab not in self._tabs or tab.trace is None:
            return
        if tab is not self._active_tab:
            tab.cpu_load_graph.set_trace(tab.trace)
            tab.cpu_load_graph.set_font_size(self._font_size_val)
            self._sync_cpu_load_graph(tab)
            tab._stats_built = False
            return
        self.statusBar().showMessage("Building statistics…", 0)
        _process_ui_events_safely()
        try:
            self._sync_panels_stats_and_chrome()
            tab._stats_built = True
        finally:
            self.statusBar().clearMessage()

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
        sc = tab.view._scene
        mks = sc._heatmap_filter_mks
        dlg.set_filter_banner(sc._heatmap_filter_label, len(mks) if mks else 0)

    def _close_chord_dialog(self) -> None:
        if self._chord_dlg is not None:
            self._chord_dlg.close()
            self._chord_dlg = None

    def _sync_chord_dialog_to_tab(self) -> None:
        dlg = self._chord_dlg
        if dlg is None:
            return
        tab = self._active_tab
        owner = getattr(dlg, "_owner_tab_path", None)
        cur = tab.path if tab else None
        if tab is None or cur != owner:
            self._close_chord_dialog()
            return
        dlg.refresh_scope()

    def _toggle_show_ai_panel(self) -> None:
        self._show_ai = not getattr(self, "_show_ai", True)
        if hasattr(self, "_act_show_ai"):
            self._act_show_ai.setChecked(self._show_ai)
        self._sync_panel_tab_visibility()
        self._apply_dock_visibility_from_prefs()
        if self._show_ai and self._ai_feature_enabled():
            self._focus_ai_panel()

    def _focus_ai_panel(self) -> None:
        if not self._ai_feature_enabled():
            self._open_settings("AI")
            return
        self._show_ai = True
        if hasattr(self, "_act_show_ai"):
            self._act_show_ai.setChecked(True)
        self._sync_panel_tab_visibility()
        self._apply_dock_visibility_from_prefs()
        self._focus_panel_tab(_PANEL_TAB_AI)
        if hasattr(self, "_panel_dock"):
            self._panel_dock.show()
            self._panel_dock.raise_()

    def _sync_ai_menu(self) -> None:
        """Show/hide View → Show AI Assistant when the feature is enabled."""
        if hasattr(self, "_act_show_ai"):
            enabled_feat = self._ai_feature_enabled()
            self._act_show_ai.setVisible(enabled_feat)
            self._act_show_ai.setEnabled(enabled_feat)

    # Keys the pre-preset schema used that no longer exist. ``openai_*`` is not
    # listed: those names now belong to the OpenAI preset, and
    # ``migrate_ai_settings`` decides what they meant.
    _AI_LEGACY_KEYS = ("provider", "openai_preset", "ollama_url")

    @classmethod
    def _ai_setting_keys(cls) -> list:
        keys = ["enabled", "preset", "response_language"]
        keys += [
            f"{pid}_{field}"
            for pid, _label, _base, _model in AI_PRESETS
            for field in AI_PRESET_FIELDS
        ]
        return keys

    def _ai_read_settings(self) -> dict:
        """AI section of btf_viewer.rc, migrating pre-preset keys on first read."""
        s = self._settings
        keys = self._ai_setting_keys()
        cfg = {k: s.get("ai", k, "") for k in keys}
        cfg["enabled"] = cfg["enabled"] or "true"
        cfg["response_language"] = (
            cfg["response_language"] or DEFAULT_AI_RESPONSE_LANGUAGE)

        legacy = {k: s.get("ai", k, "") for k in self._AI_LEGACY_KEYS}
        patch = migrate_ai_settings({**cfg, **legacy})
        if not (cfg["preset"] or patch.get("preset")):
            patch["preset"] = DEFAULT_AI_PRESET
        if patch:
            cfg.update(patch)
            s.set_many("ai", patch)
        if any(v for v in legacy.values()):
            # Migration is one-shot: drop the pre-preset keys from the file.
            s.align_section_keys("ai", set(keys))
            s.flush()
        cfg["preset"] = normalize_ai_preset(cfg["preset"])
        return cfg

    def _ai_save_settings_patch(self, patch: dict) -> None:
        """Persist a subset of AI settings (e.g. Language… dialog)."""
        if not patch:
            return
        clean = {str(k): str(v) for k, v in patch.items() if v is not None}
        if not clean:
            return
        self._settings.set_many("ai", clean)

    def _ai_build_context(self) -> dict:
        if not hasattr(self, "_stats_panel") or self._trace is None:
            return {"findings_text": "No trace loaded.", "scope": "", "span": "", "cores": ""}
        findings, scope_title = self._stats_panel.build_analysis_findings()
        text = _format_analysis_findings_text(findings, scope_title)
        tr = self._trace
        span = _format_time(tr.time_max - tr.time_min, tr.time_scale)
        return {
            "findings_text": text,
            "scope": scope_title or "full trace",
            "span": span,
            "cores": len(tr.core_names or []),
        }

    def _ai_list_loaded_tabs(self) -> list:
        """Loaded BTF tabs for the Trace Compare AI template."""
        out = []
        for i, tab in enumerate(self._tabs):
            if getattr(tab, "trace", None) is None:
                continue
            path = getattr(tab, "path", "") or ""
            name = _trace_display_name(path) if path else f"Tab {i + 1}"
            out.append({"index": i, "name": name})
        return out

    def _ai_build_compare_context(self, idx_a: int, idx_b: int) -> dict:
        """Build Trace Compare CSV context for AI (cursor scope on, like the dialog)."""
        tabs = self._tabs
        if not (0 <= idx_a < len(tabs) and 0 <= idx_b < len(tabs)):
            raise ValueError("Invalid tab index for Trace Compare")
        tab_a, tab_b = tabs[idx_a], tabs[idx_b]
        tr_a, tr_b = tab_a.trace, tab_b.trace
        if tr_a is None or tr_b is None:
            raise ValueError("Both tabs must have a loaded trace")
        name_a = _trace_display_name(tab_a.path) if tab_a.path else f"Tab {idx_a + 1}"
        name_b = _trace_display_name(tab_b.path) if tab_b.path else f"Tab {idx_b + 1}"
        scope_enabled = True
        lo_a, hi_a = _cursor_range_for_tab(self, idx_a)
        lo_b, hi_b = _cursor_range_for_tab(self, idx_b)
        if not scope_enabled:
            lo_a = hi_a = lo_b = hi_b = None
        tables = _build_trace_compare_rows(tr_a, tr_b, lo_a, hi_a, lo_b, hi_b)
        csv_text = _build_compare_csv(name_a, name_b, scope_enabled, tables)
        if len(csv_text) > 60000:
            csv_text = csv_text[:60000] + "\n… (truncated for AI context)"
        findings = (
            f"Trace Compare tables (CSV) for {name_a} vs {name_b}.\n"
            f"Cursor scope per tab: yes (when 2+ cursors placed).\n\n"
            f"{csv_text}"
        )
        return {
            "findings_text": findings,
            "scope": f"Trace Compare: {name_a} vs {name_b}",
            "span": "",
            "cores": "",
        }

    def _sync_ai_compare_template(self) -> None:
        panel = getattr(self, "_ai_panel", None)
        if panel is None:
            return
        if hasattr(panel, "refresh_enabled_state"):
            panel.refresh_enabled_state()
        elif hasattr(panel, "refresh_template_availability"):
            panel.refresh_template_availability()

    def _ai_jump_time_unit(self, value: float) -> None:
        """Jump to *value* (trace time unit) and drop an annotation there."""
        if self._trace is None:
            return
        ns = int(float(value))
        note = ai_jump_annotation_note(value)
        self._jump_to_ns(ns)
        for ann in self._annotations:
            if int(ann.ns) == ns and ann.note == note:
                return
        self._add_annotation_with_note(ns, note, show_marks_panel=False)

    def _open_analysis_findings(self) -> None:
        """Show Analysis Findings dialog for the active tab / cursor scope."""
        if self._trace is None or self._stats_panel is None:
            return
        findings, scope_title = self._stats_panel.build_analysis_findings()
        dlg = _AnalysisFindingsDialog(
            findings, scope_title, parent=self,
            ai_enabled=self._ai_feature_enabled(),
        )
        dlg.exec()
        if not getattr(dlg, "wants_ai_query", False):
            return
        if getattr(dlg, "_ai_needs_settings", False):
            self._open_settings("AI")
            return
        self._focus_ai_panel()
        panel = getattr(self, "_ai_panel", None)
        if panel is not None and hasattr(panel, "query_analysis_findings"):
            QTimer.singleShot(0, panel.query_analysis_findings)

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
            sc._heatmap_filter_label = None
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

    def _finish_heatmap_clear_ui(self, dlg: _CorridorInspectorDialog) -> None:
        dlg.refresh_scope()
        dlg.set_filter_banner(None, 0)

    def _open_corridor_inspector(self, initial_mode: str = "heatmap") -> None:
        trace = self._trace
        if trace is None or not _trace_is_multi_core(trace):
            return
        # Single shared inspector instance (heatmap + chord entry points).
        dlg = self._heatmap_dlg or self._chord_dlg
        if dlg is not None:
            if hasattr(dlg, "set_ai_enabled"):
                dlg.set_ai_enabled(self._ai_feature_enabled())
            if initial_mode == "chord" and hasattr(dlg, "_show_topology"):
                dlg._show_topology(True)
            dlg.raise_()
            dlg.activateWindow()
            self._heatmap_dlg = dlg
            self._chord_dlg = dlg
            return
        tab = self._active_tab
        if tab is not None:
            self._capture_heatmap_view_snapshot(tab)
        dlg = _CorridorInspectorDialog(
            trace, parent=self,
            on_spotlight=self._on_corridor_spotlight,
            on_clear=self._clear_heatmap_task_filter,
            on_jump=self._on_corridor_jump,
            initial_mode=initial_mode,
            ai_enabled=self._ai_feature_enabled(),
            on_query_ai=self._query_corridor_with_ai)
        dlg._owner_tab_path = (
            self._active_tab.path if self._active_tab else None)
        dlg.finished.connect(self._on_inspector_dlg_closed)
        self._heatmap_dlg = dlg
        self._chord_dlg = dlg
        tab = self._active_tab
        sc = tab.view._scene if tab else None
        mks = sc._heatmap_filter_mks if sc else None
        dlg.set_filter_banner(
            sc._heatmap_filter_label if sc else None,
            len(mks) if mks else 0)
        dlg.show()

    def _query_corridor_with_ai(self, ai_enabled: bool = True) -> None:
        """Inspector Query with AI… → Migration thrash template."""
        if not ai_enabled:
            self._open_settings("AI")
            return
        self._focus_ai_panel()
        panel = getattr(self, "_ai_panel", None)
        if panel is not None and hasattr(panel, "query_migration_thrash"):
            QTimer.singleShot(0, panel.query_migration_thrash)

    def _open_migration_heatmap(self) -> None:
        self._open_corridor_inspector("heatmap")

    def _open_chord_diagram(self) -> None:
        self._open_corridor_inspector("chord")

    def _on_inspector_dlg_closed(self, _result: int = 0) -> None:
        self._heatmap_dlg = None
        self._chord_dlg = None

    def _on_heatmap_dlg_closed(self, _result: int = 0) -> None:
        self._on_inspector_dlg_closed(_result)

    def _on_chord_dlg_closed(self, _result: int = 0) -> None:
        self._on_inspector_dlg_closed(_result)

    def _on_corridor_spotlight(self, from_core: str, to_core: str, label: str,
                               bin_lo: int, bin_hi: int, merge_keys: set,
                               lock_task_key: Optional[str] = None) -> None:
        self._on_heatmap_drill(from_core, to_core, label, bin_lo, bin_hi,
                               merge_keys, lock_task_key=lock_task_key,
                               enable_cpu_load=True)

    def _on_corridor_jump(self, bin_lo: int, bin_hi: int,
                          lock_task_key: Optional[str] = None) -> None:
        """Triage Jump To: place C1–C2 and scroll the main timeline to the peak bin."""
        tab = self._active_tab
        if tab is None or self._trace is None:
            return
        view = tab.view
        view.begin_programmatic_viewport()
        try:
            view._fit_mode = False
            view.clear_cursors()
            view._scene.add_cursor(int(bin_lo))
            view._scene.add_cursor(int(bin_hi))
            view.cursors_changed.emit(view._scene.cursor_times())
            vp_px = max(view.viewport().width() - view._scene._label_width, 100)
            view._scene.zoom_to_range(int(bin_lo), int(bin_hi), vp_px)
            view.scroll_to_ns((int(bin_lo) + int(bin_hi)) // 2)
            view.zoom_changed.emit(view._scene.timescale_per_px)
        finally:
            view.end_programmatic_viewport()
        if hasattr(self, "_tb_cpu_load_btn") and not self._tb_cpu_load_btn.isChecked():
            self._tb_cpu_load_btn.setChecked(True)
            self._toggle_cpu_load_graph()
        if lock_task_key:
            self._on_legend_task_clicked(lock_task_key)
        if hasattr(self, "_stats_panel"):
            self._stats_panel.set_cursor_times(
                view._scene.cursor_times(), refresh_stats=False)
        self.statusBar().showMessage(
            f"Jumped to hotspot "
            f"{_format_time(bin_lo, self._trace.time_scale)}–"
            f"{_format_time(bin_hi, self._trace.time_scale)}",
            5000)

    def _on_open_pair_heatmap(self, from_core: str, to_core: str,
                              bounce_only: bool = False) -> None:
        """Core-Pair chart footer: open heatmap focused on From→To."""
        self._open_migration_heatmap()
        dlg = self._heatmap_dlg
        if dlg is None:
            return
        if not dlg.focus_pair(from_core, to_core, bounce_only=bounce_only):
            self.statusBar().showMessage(
                f"No heatmap data for {from_core}→{to_core} in scope", 4000)
        else:
            dlg.raise_()
            dlg.activateWindow()

    def _on_open_pair_chord(self, from_core: str, to_core: str,
                            bounce_only: bool = False) -> None:
        """Core-Pair chart footer: open chord with source core highlighted."""
        self._open_chord_diagram()
        dlg = self._chord_dlg
        if dlg is None:
            return
        if not dlg.focus_pair(from_core, to_core, bounce_only=bounce_only):
            self.statusBar().showMessage(
                f"No chord data for {from_core}→{to_core} in scope", 4000)
        else:
            dlg.raise_()
            dlg.activateWindow()

    def _heatmap_filter_active(self) -> bool:
        tab = self._active_tab
        if tab is None:
            return False
        return tab.view._scene._heatmap_filter_mks is not None

    def _sync_show_all_tasks_btn(self) -> None:
        if not hasattr(self, "_tb_show_all_tasks_btn"):
            return
        active = self._heatmap_filter_active()
        self._tb_show_all_tasks_btn.setVisible(active)
        self._tb_show_all_tasks_btn.setChecked(active)

    def _on_heatmap_drill(self, from_core: str, to_core: str, label: str,
                          bin_lo: int, bin_hi: int, merge_keys: set,
                          lock_task_key: Optional[str] = None,
                          enable_cpu_load: bool = False) -> None:
        if not merge_keys:
            return
        tab = self._active_tab
        if tab is None:
            return
        dlg = self._heatmap_dlg or self._chord_dlg
        owner = getattr(dlg, "_owner_tab_path", None) if dlg else None
        if owner is not None and tab.path != owner:
            return
        self._set_view_mode("task")
        self._legend.set_migrated_only_checked(False)
        tab.view._scene.set_heatmap_task_filter(set(merge_keys), label=label)
        self._legend.set_heatmap_filter(label, merge_keys)
        self._sync_show_all_tasks_btn()
        if dlg is not None:
            dlg.set_filter_banner(label, len(merge_keys))
        if enable_cpu_load and not self._tb_cpu_load_btn.isChecked():
            self._tb_cpu_load_btn.setChecked(True)
            self._toggle_cpu_load_graph()
        view = tab.view
        view.begin_programmatic_viewport()
        try:
            view._fit_mode = False
            view.clear_cursors()
            view._scene.add_cursor(bin_lo)
            view._scene.add_cursor(bin_hi)
            view.cursors_changed.emit(view._scene.cursor_times())
            vp_px = max(view.viewport().width() - view._scene._label_width, 100)
            view._scene.zoom_to_range(bin_lo, bin_hi, vp_px)
            view.scroll_to_ns((bin_lo + bin_hi) // 2)
            view.zoom_changed.emit(view._scene.timescale_per_px)
        finally:
            view.end_programmatic_viewport()
        lock_mk = lock_task_key or (next(iter(merge_keys)) if len(merge_keys) == 1 else None)
        if lock_mk:
            self._on_legend_task_clicked(lock_mk)
        else:
            view._scene.set_highlighted_task(None)
        self._stats_panel.set_cursor_times(
            view._scene.cursor_times(), refresh_stats=False)
        n = len(merge_keys)
        self.statusBar().showMessage(
            f"Spotlight {label}: showing {n} task(s) · "
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
        """Expand or collapse all timeline core rows (CPU load pane is independent)."""
        expanded = self._tb_expand_all_btn.isChecked()
        self._view.set_all_cores_expanded(expanded)

    def _toggle_cpu_load_graph(self) -> None:
        """Show or hide the CPU load graph panel.

        Overlay layout: the timeline widget is never resized.  Update the
        settings model quietly — assigning ``_show_cpu_load`` emits
        ``settings_changed`` and re-applies every view setting (a dozen scene
        rebuilds), which is what made Load feel slower than the web.
        """
        visible = self._tb_cpu_load_btn.isChecked()
        if self._vm.settings._model.show_cpu_load != visible:
            self._vm.settings._model.show_cpu_load = visible
            self._settings.set(
                "view", "show_cpu_load", str(visible).lower(), flush=False)
        for tab in self._tabs:
            tab.cpu_splitter.set_cpu_visible(visible)
        if visible and self._active_tab is not None:
            if self._cpu_splitter_user_sized:
                self._apply_saved_cpu_splitter(self._active_tab, force=True)
            else:
                self._autofit_cpu_load_height()

    def _sync_toolbar_to_active_tab(self) -> None:
        """Refresh toolbar toggles that reflect per-tab view state."""
        self._sync_heatmap_toolbar()
        if hasattr(self, "_tb_analysis_btn"):
            self._tb_analysis_btn.setEnabled(self._trace is not None)
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
                    scene._core_is_expanded(c) for c in trace.core_names)
                self._tb_expand_all_btn.blockSignals(True)
                self._tb_expand_all_btn.setChecked(all_expanded)
                self._tb_expand_all_btn.blockSignals(False)

    # -- File actions ---------------------------------------------------

    @_dialog_guard
    def _on_open(self) -> None:
        last_dir = self._settings.get("files", "last_dir", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(
            self, "Open BTF trace", last_dir,
            _BTF_OPEN_FILTER
        )
        if path:
            self._open_file(path)

    def _save_recent_files(self, path: str) -> None:
        norm = _normalize_open_path(path)
        # Load existing JSON list
        raw_json = self._settings.get("files", "recent_json", "")
        try:
            entries = json.loads(raw_json) if raw_json.strip() else []
        except (json.JSONDecodeError, ValueError):
            entries = []
        # Remove any existing entry for this path
        entries = [e for e in entries if e.get("path") != norm]
        # Build new entry with metadata (zip::member → size the archive)
        try:
            size_path, _member = _split_zip_member_path(norm)
            size  = os.path.getsize(size_path)
            mtime = int(os.path.getmtime(size_path))
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
        self._settings.prune_section("trace_state", 8, flush=False)
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
        sc.set_highlighted_interval(inst, mark_ns)
        center_ns = mark_ns if mark_ns is not None else (inst.start_ns + inst.stop_ns) // 2
        time_coord = sc.ns_to_scene_coord(center_ns)
        span = sc.interval_orth_scene_span(inst.id)
        if span is not None:
            orth = (span[0] + span[1]) / 2
            if is_horiz:
                self._view.centerOn(time_coord, orth)
            else:
                self._view.centerOn(orth, time_coord)
        else:
            cur = self._view.mapToScene(vp.center())
            if is_horiz:
                self._view.centerOn(time_coord, cur.y())
            else:
                self._view.centerOn(cur.x(), time_coord)
        self._view.zoom_changed.emit(sc.timescale_per_px)
        self._view.viewport().update()

    def _scroll_to_tag_sample(self, sample: "TagSample", mark_ns: int) -> None:
        """Zoom to and scroll vertically to a tag STI sample."""
        if self._trace is None or sample is None:
            return
        sc = self._view._scene
        vp = self._view.viewport().rect()
        is_horiz = sc._horizontal
        vp_px = max(vp.width() if is_horiz else vp.height(), 100)
        center_ns = mark_ns if mark_ns is not None else sample.time_ns
        span = max(1000, (self._trace.time_max - self._trace.time_min) // 200)
        ns_lo = max(self._trace.time_min, center_ns - span)
        ns_hi = min(self._trace.time_max, center_ns + span)
        self._view._fit_mode = False
        sc.zoom_to_range(ns_lo, ns_hi, vp_px)
        time_coord = sc.ns_to_scene_coord(center_ns)
        orth_span = sc.sti_channel_orth_scene_span(sample.channel)
        if orth_span is not None:
            orth = (orth_span[0] + orth_span[1]) / 2
            if is_horiz:
                self._view.centerOn(time_coord, orth)
            else:
                self._view.centerOn(orth, time_coord)
        else:
            self._view.scroll_to_ns(center_ns)
        self._view.zoom_changed.emit(sc.timescale_per_px)
        self._view.viewport().update()

    def _scroll_to_sync_issue(self, iss: "SyncIssueRef", mark_ns: int) -> None:
        """Zoom to and highlight a mutex/sem pairing issue."""
        if self._trace is None or iss is None:
            return
        sc = self._view._scene
        vp = self._view.viewport().rect()
        is_horiz = sc._horizontal
        vp_px = max(vp.width() if is_horiz else vp.height(), 100)
        seg = _segment_at_core_time(self._trace.core_segs, iss.core, iss.time_ns,
                                    self._trace.core_seg_starts)
        center_ns = mark_ns if mark_ns is not None else iss.time_ns
        if seg is not None:
            margin = max(1, (seg.end - seg.start) // 10)
            ns_lo = max(self._trace.time_min, seg.start - margin)
            ns_hi = min(self._trace.time_max, seg.end + margin)
            sc.set_highlighted_segment(seg)
        else:
            span = max(1000, (self._trace.time_max - self._trace.time_min) // 200)
            ns_lo = max(self._trace.time_min, iss.time_ns - span)
            ns_hi = min(self._trace.time_max, iss.time_ns + span)
            sc.set_highlighted_segment(None)
        self._view._fit_mode = False
        sc.zoom_to_range(ns_lo, ns_hi, vp_px)
        time_coord = sc.ns_to_scene_coord(center_ns)
        if seg is not None:
            mk = _task_merge_key(seg.task)
            core_name = seg.core if sc._view_mode == "core" else None
            span = sc.task_orth_scene_span(mk, core_name=core_name)
            if span is not None:
                orth = (span[0] + span[1]) / 2
                if is_horiz:
                    self._view.centerOn(time_coord, orth)
                else:
                    self._view.centerOn(orth, time_coord)
            else:
                self._view.scroll_to_ns(center_ns)
        else:
            self._view.scroll_to_ns(center_ns)
        self._view.zoom_changed.emit(sc.timescale_per_px)
        self._view.viewport().update()

    def _scroll_to_priority_episode(self, ep: "PriorityEpisode", mark_ns: int) -> None:
        """Zoom to a priority boost episode and highlight the task row."""
        if self._trace is None or ep is None:
            return
        sc = self._view._scene
        vp = self._view.viewport().rect()
        is_horiz = sc._horizontal
        vp_px = max(vp.width() if is_horiz else vp.height(), 100)
        margin = max(1, (ep.stop_ns - ep.start_ns) // 10)
        ns_lo = max(self._trace.time_min, ep.start_ns - margin)
        ns_hi = min(self._trace.time_max, ep.stop_ns + margin)
        self._view._fit_mode = False
        sc.zoom_to_range(ns_lo, ns_hi, vp_px)
        sc.set_highlighted_task(ep.mk, locked=True)
        center_ns = mark_ns if mark_ns is not None else (ep.start_ns + ep.stop_ns) // 2
        time_coord = sc.ns_to_scene_coord(center_ns)
        span = sc.task_orth_scene_span(ep.mk)
        if span is not None:
            orth = (span[0] + span[1]) / 2
            if is_horiz:
                self._view.centerOn(time_coord, orth)
            else:
                self._view.centerOn(orth, time_coord)
        else:
            cur = self._view.mapToScene(vp.center())
            if is_horiz:
                self._view.centerOn(time_coord, cur.y())
            else:
                self._view.centerOn(cur.x(), time_coord)
        self._view.zoom_changed.emit(sc.timescale_per_px)
        self._view.viewport().update()

    def _on_segment_jump(self, ns: int) -> None:
        """Scroll the timeline to *ns* (non-annotation stats jumps, e.g. TICK gaps)."""
        if self._trace is None:
            return
        self._view.scroll_to_ns(ns)

    def _on_stats_core_clicked(self, core: str) -> None:
        """Core Time Breakdown row click: switch to Core View and expand *core*."""
        if self._trace is None:
            return
        if self._view_mode != "core":
            self._set_view_mode("core")
        sc = self._view._scene
        sc.set_core_expanded(core, True)
        self._cpu_load_graph.set_core_expanded(core, True)

    def _on_stats_plot_point_clicked(self, payload, mark_ns: int, note: str) -> None:
        """Metrics plot point: jump/highlight and add an annotation with *note*."""
        if self._trace is None:
            return
        if isinstance(payload, TaskSegment):
            self._scroll_to_segment(payload)
        elif isinstance(payload, IntervalInstance):
            self._scroll_to_interval(payload, mark_ns)
        elif isinstance(payload, TagSample):
            self._scroll_to_tag_sample(payload, mark_ns)
        elif isinstance(payload, PriorityEpisode):
            self._scroll_to_priority_episode(payload, mark_ns)
        elif isinstance(payload, SyncIssueRef):
            self._scroll_to_sync_issue(payload, mark_ns)
        else:
            self._view.scroll_to_ns(mark_ns)
        self._ensure_stats_plot_annotation(mark_ns, note)

    def _ensure_stats_plot_annotation(self, mark_ns: int, note: str) -> None:
        """Add a stats-plot annotation unless one already exists at the same point."""
        note = note or ""
        for ann in self._annotations:
            if ann.ns == mark_ns and ann.note == note:
                self._focus_marks_annotation_panel(ann.id)
                return
        self._add_annotation_with_note(mark_ns, note, focus_annotation_tab=True)

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
        label = f"Bookmark @{_format_time(ns, unit, decimals=self._time_decimals_val)}"
        self._bookmarks.append(TraceBookmark(id=self._mark_next_id, ns=ns, label=label))
        self._mark_next_id += 1
        self._bookmarks.sort(key=lambda b: b.ns)
        self._rebuild_bookmark_list()
        self._save_current_trace_state()

    def _jump_selected_bookmark(self) -> None:
        item = self._bookmark_list.currentItem()
        if item is None:
            return
        self._jump_to_ns(int(item.data(Qt.ItemDataRole.UserRole + 1)))

    def _delete_selected_bookmark(self) -> None:
        item = self._bookmark_list.currentItem()
        if item is None:
            return
        self._push_undo_snapshot()
        bid = int(item.data(Qt.ItemDataRole.UserRole))
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
            txt = b.label or f"Bookmark @{_format_time(b.ns, unit, decimals=self._time_decimals_val)}"
            item = QListWidgetItem(txt)
            item.setData(Qt.ItemDataRole.UserRole, int(b.id))
            item.setData(Qt.ItemDataRole.UserRole + 1, int(b.ns))
            item.setToolTip(f"{_format_time(b.ns, unit, decimals=self._time_decimals_val)}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self._bookmark_list.addItem(item)
        self._bookmark_list.blockSignals(False)
        self._view._scene.set_marks(self._bookmarks, self._annotations)
        self._view._has_bookmarks = bool(self._bookmarks)

    def _on_bookmark_item_changed(self, item: QListWidgetItem) -> None:
        if item is None:
            return
        bid = int(item.data(Qt.ItemDataRole.UserRole))
        new_label = item.text().strip()
        for b in self._bookmarks:
            if b.id == bid:
                # Empty label -> revert to the default timestamp label so the
                # bookmark keeps useful identity information.
                b.label = new_label or f"Bookmark @{_format_time(b.ns, self._current_time_unit(), decimals=self._time_decimals_val)}"
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
        label = f"Bookmark @{_format_time(ns, unit, decimals=self._time_decimals_val)}"
        self._bookmarks.append(TraceBookmark(id=self._mark_next_id, ns=ns, label=label))
        self._mark_next_id += 1
        self._bookmarks.sort(key=lambda b: b.ns)
        self._rebuild_bookmark_list()
        self._save_current_trace_state()
        self._focus_panel_tab(_PANEL_TAB_MARKS)

    def _add_annotation_at_ns(self, ns: int) -> None:
        """Add an annotation at timestamp with an empty note."""
        self._add_annotation_with_note(ns, "")

    def _add_annotation_with_note(
        self, ns: int, note: str, *, focus_annotation_tab: bool = False,
        show_marks_panel: bool = True,
    ) -> None:
        """Add an annotation at *ns* with the given note text."""
        if self._trace is None:
            return
        tmin = int(self._trace.time_min)
        tmax = int(self._trace.time_max)
        if tmax < tmin:
            tmax = tmin
        ns = max(tmin, min(tmax, int(ns)))
        self._push_undo_snapshot()
        ann_id = self._mark_next_id
        self._annotations.append(TraceAnnotation(id=ann_id, ns=ns, note=note or ""))
        self._mark_next_id += 1
        self._annotations.sort(key=lambda a: a.ns)
        self._rebuild_annotation_list()
        self._save_current_trace_state()
        if focus_annotation_tab:
            self._focus_marks_annotation_panel(ann_id)
        elif show_marks_panel:
            self._focus_panel_tab(_PANEL_TAB_MARKS)

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
        self._jump_to_ns(int(item.data(Qt.ItemDataRole.UserRole + 1)))

    def _delete_selected_annotation(self) -> None:
        item = self._annotation_list.currentItem()
        if item is None:
            return
        self._push_undo_snapshot()
        aid = int(item.data(Qt.ItemDataRole.UserRole))
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
        aid = int(item.data(Qt.ItemDataRole.UserRole))
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
            txt = f"{_format_time(a.ns, unit, decimals=self._time_decimals_val)}  {a.note}"
            item = QListWidgetItem(txt)
            item.setData(Qt.ItemDataRole.UserRole, int(a.id))
            item.setData(Qt.ItemDataRole.UserRole + 1, int(a.ns))
            item.setToolTip(f"@ {_format_time(a.ns, unit, decimals=self._time_decimals_val)}\n{a.note}")
            self._annotation_list.addItem(item)
        self._annotation_list.blockSignals(False)
        self._view._scene.set_marks(self._bookmarks, self._annotations)
        self._view._has_annotations = bool(self._annotations)

    def _focus_marks_annotation_panel(self, annotation_id: Optional[int] = None) -> None:
        """Show Marks tab, switch to Anno. sub-tab, optionally select a row."""
        self._show_marks = True
        self._sync_panel_tab_visibility()
        self._focus_panel_tab(_PANEL_TAB_MARKS)
        self._marks_tabs.setCurrentIndex(2)
        if annotation_id is not None:
            for row in range(self._annotation_list.count()):
                item = self._annotation_list.item(row)
                if item is not None and int(item.data(Qt.ItemDataRole.UserRole)) == annotation_id:
                    self._annotation_list.setCurrentItem(item)
                    self._annotation_list.scrollToItem(item)
                    break

    def _typing_focus_active(self) -> bool:
        fw = QApplication.focusWidget()
        return fw is not None and isinstance(
            fw, (QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox))

    def _pan_timeline_arrow(self, key: Qt.Key) -> None:
        """Application-level arrow pan when focus is not in a text/spin field."""
        if self._typing_focus_active():
            return
        view = self._view
        sc = view._scene
        if sc._trace is None:
            return
        horiz = sc._horizontal
        if horiz:
            time_fwd, time_back = Qt.Key.Key_Right, Qt.Key.Key_Left
            row_fwd, row_back = Qt.Key.Key_Down, Qt.Key.Key_Up
        else:
            time_fwd, time_back = Qt.Key.Key_Down, Qt.Key.Key_Up
            row_fwd, row_back = Qt.Key.Key_Right, Qt.Key.Key_Left
        if key in (time_fwd, time_back):
            view._pan_time_axis_px(
                view._time_axis_step_px() if key == time_fwd
                else -view._time_axis_step_px())
        elif key in (row_fwd, row_back):
            view._pan_orth_axis_px(
                view._orth_axis_step_px() if key == row_fwd
                else -view._orth_axis_step_px())

    def _focus_find(self) -> None:
        """Show the Find tab and focus the search field."""
        self._show_find = True
        self._act_show_find.setChecked(True)
        self._sync_panel_tab_visibility()
        self._focus_panel_tab(_PANEL_TAB_FIND)
        self._find_input.setFocus()
        self._find_input.selectAll()
        self._recompute_find_hits()

    def _recompute_find_hits(self) -> None:
        vm = self._active_tab_vm
        if vm is None or self._trace is None:
            self._find_status.setText("0 matches")
            self._view._scene.set_find_hits([])
            return
        vm.find_query = self._find_input.text()
        vm.find_mode = self._find_mode_combo.currentText()
        status = vm.recompute_find_hits()
        self._find_status.setText(status)
        self._view._scene.set_find_hits(vm.find_hits)
        if not vm.find_hits:
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
        pen = QPen(QColor("#FFD54F"), 1.5, Qt.PenStyle.DotLine)
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
        path = _normalize_open_path(path)

        try:
            expanded = _expand_open_paths(path)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            QMessageBox.warning(self, "Open Error", str(exc))
            if self._session_restore_queue or self._session_restore_active_idx >= 0:
                self._continue_session_restore()
            return

        if len(expanded) > 1:
            # Multi-BTF zip: open the first member, queue the rest as tabs.
            path = expanded[0]
            for extra in expanded[1:]:
                if extra not in self._pending_open_paths:
                    self._pending_open_paths.append(extra)
            self.statusBar().showMessage(
                f"Opening {len(expanded)} traces from ZIP…", 4000)

        existing = self._find_tab_index(path)
        if existing >= 0:
            self._tab_widget.setCurrentIndex(existing)
            self._focus_statistics_panel(force=True)
            QTimer.singleShot(0, lambda: self._focus_statistics_panel(force=True))
            if self._session_restore_queue or self._session_restore_active_idx >= 0:
                self._continue_session_restore()
            self._drain_pending_open_paths()
            return

        if self._load_in_progress:
            if path not in self._pending_open_paths:
                self._pending_open_paths.append(path)
            self._status_file.setText("  Queued — finishing current load…")
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
        _HoverCursor.hide()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        load_label = _trace_display_name(path)
        self._status_file.setText(f"  Loading {load_label}…")
        # Reset dynamic render state so new traces never inherit stale colors.
        _reset_render_state_for_new_trace()
        _process_ui_events_safely()

        # Progress dialog - created before closures so progress_dialog is defined.
        progress_dialog = _LoadProgressDialog(
            f"Loading {load_label}…", self)
        progress_dialog.show_centered(self.geometry())
        self._progress_dialog = progress_dialog

        def _teardown_loading_dialog(*, clear_load_flag: bool = True) -> None:
            try:
                progress_dialog.close()
                progress_dialog.deleteLater()
            except RuntimeError:
                pass
            if self._progress_dialog is progress_dialog:
                self._progress_dialog = None
            if clear_load_flag:
                self._load_in_progress = False
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()

        def _on_done(trace):
            load_ok = False
            try:
                progress_dialog.update_progress(100, "Building scene…")
                _process_ui_events_safely()   # let the dialog repaint before heavy build
                try:
                    self._finalize_loaded_trace(trace, path, progress_dialog)
                    load_ok = True
                except (ValueError, RuntimeError, KeyError, OSError) as exc:
                    self._status_file.setText("  No file loaded")
                    QMessageBox.critical(self, "Render Error",
                                         f"Failed to display:\n{path}\n\n{exc}")
            finally:
                if self._progress_dialog is progress_dialog:
                    _teardown_loading_dialog(clear_load_flag=not load_ok)
                self._finish_parse_thread()

        def _on_error(msg):
            try:
                self._status_file.setText("  No file loaded")
                QMessageBox.critical(self, "Parse Error",
                                     f"Failed to parse:\n{path}\n\n{msg}")
            finally:
                _teardown_loading_dialog()
                self._finish_parse_thread()

        def _on_cancelled():
            try:
                self._status_file.setText("  Load cancelled")
            finally:
                _teardown_loading_dialog()
                self._finish_parse_thread()

        thread = _ParseThread(path, self)
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
            self._finish_parse_thread()
            self._status_file.setText("  No file loaded")
            QMessageBox.critical(self, "Load Error",
                                 f"Failed to start parser thread:\n{path}\n\n{exc}")

    def _finalize_loaded_trace(self, trace: BtfTrace, path: str,
                               progress_dialog: _LoadProgressDialog) -> None:
        """Complete all post-parse UI/state updates for a successful load."""
        self._settings.set(
            "files", "last_dir",
            os.path.dirname(_split_zip_member_path(path)[0]),
            flush=False)

        tab = self._add_trace_tab(path, trace)
        _process_ui_events_safely()
        tab.view.load_trace(trace)
        self._timescale_per_px_default_val = tab.view._scene._timescale_per_px_default
        self._refresh_zoom_ui_unit()
        self._load_trace_state(path)
        self._recompute_find_hits()
        self._load_tab_view_state(tab)
        self._close_heatmap_dialog()
        self._close_chord_dialog()
        self._heatmap_view_snapshot = None
        tab.view._scene.set_heatmap_task_filter(None)

        progress_dialog.update_progress(100, "Building legend…")
        _process_ui_events_safely()
        self._sync_panels_light()
        self._dismiss_load_progress(progress_dialog)

        def _deferred_stats_sync() -> None:
            try:
                self._finalize_tab_deferred_work(tab)
            finally:
                self._finish_load_pipeline()

        QTimer.singleShot(0, _deferred_stats_sync)

        self._undo_stack.clear()
        self._redo_stack.clear()
        self._act_undo.setEnabled(False)
        self._act_redo.setEnabled(False)
        self._focus_statistics_panel(force=True)
        if self._show_cpu_load and self._active_tab is not None:
            self._active_tab.cpu_splitter.set_cpu_visible(True)
            if self._cpu_splitter_user_sized:
                self._apply_saved_cpu_splitter(self._active_tab, force=True)
            else:
                self._autofit_cpu_load_height()

        self._save_recent_files(path)
        self._rebuild_recent_menu()
        self._settings.flush()
        self._report_settings_io_failure(prefix="Settings save warning")
        self._update_trace_quality_banner(trace)

    def _capture_viewport_pixmap(self) -> Tuple[QPixmap, float]:
        """Capture the active tab's timeline viewport, optionally with CPU load graph."""
        tl_pix, dpr = self._view._capture_pixmap()
        if self._show_cpu_load and self._cpu_load_scroll.isVisible():
            cpu_pix, cpu_dpr = _normalize_grab_pixmap(self._cpu_load_graph.grab())
            return _stack_pixmaps_vertically(tl_pix, cpu_pix), max(dpr, cpu_dpr)
        return tl_pix, dpr

    @_dialog_guard
    def _open_snapshot_editor(self) -> None:
        """Capture the viewport and open the annotation editor (web Shot parity)."""
        if self._trace is None:
            return
        pixmap, capture_dpr = self._capture_viewport_pixmap()
        if pixmap.isNull():
            QMessageBox.warning(self, "Snapshot", "Unable to capture the viewport.")
            return
        dlg = SnapshotEditorDialog(pixmap, self, capture_dpr=capture_dpr)
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
            with _svg_safe_app_style():
                painter = QPainter(gen)
                try:
                    scene.render(painter, QRectF(0, 0, w, h), scene_rect)
                    if include_cpu:
                        painter.translate(0, h)
                        self._cpu_load_graph.render(painter, QPoint(0, 0))
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
        pixmap, capture_dpr = self._capture_viewport_pixmap()
        _copy_pixmap_to_clipboard(pixmap, capture_dpr)
        self.statusBar().showMessage("Copied to clipboard!", 4000)

    @_dialog_guard
    def _on_export_perfetto(self) -> None:
        """Export the loaded trace as Chrome Trace JSON for ui.perfetto.dev."""
        if self._trace is None:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Export Perfetto")
        box.setIcon(QMessageBox.Question)
        box.setText("Choose the time range to export.")
        box.setInformativeText(
            "Full trace exports every event. Current viewport clips to the "
            "visible timeline window (same units as the BTF timeScale)."
        )
        full_btn = box.addButton("Full trace", QMessageBox.AcceptRole)
        vp_btn = box.addButton("Current viewport", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(full_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is None or clicked not in (full_btn, vp_btn):
            return
        lo = hi = None
        if clicked is vp_btn:
            scene = getattr(self._view, "_scene", None)
            if scene is None:
                QMessageBox.warning(
                    self, "Export Perfetto",
                    "Timeline is not ready; cannot read the current viewport.")
                return
            lo, hi = self._visible_time_ns_range(scene)
            if hi <= lo:
                QMessageBox.warning(
                    self, "Export Perfetto",
                    "Current viewport is empty; choose Full trace instead.")
                return
        base = os.path.splitext(self._current_file)[0] if self._current_file else "trace"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Perfetto",
            base + ".json",
            "Perfetto / Chrome Trace (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            export_perfetto(self._trace, path, lo=lo, hi=hi)
            scope = (
                f"viewport [{lo}, {hi})" if lo is not None
                else "full trace"
            )
            self.statusBar().showMessage(
                f"Perfetto exported ({scope}) → {os.path.basename(path)}", 4000)
        except (OSError, TypeError, ValueError, AttributeError, RuntimeError) as exc:
            QMessageBox.critical(
                self, "Export Error", f"Could not export Perfetto file:\n{exc}")

    # -- Settings actions -----------------------------------------------

    def _apply_settings_preview(self, vals: dict) -> None:
        """Apply *vals* dict to the live UI without writing to disk.

        Used for both live preview (called on every dialog change) and
        cancel-revert (called with the pre-dialog snapshot).
        """
        # Batch theme rebuilds: both is_dark and ui_font_size trigger
        # _apply_theme; accumulate and call once to avoid double-flicker.
        _need_theme = False
        _ui_font_changed = False
        if vals["is_dark"] != self._is_dark:
            self._is_dark = vals["is_dark"]
            _need_theme = True
        if vals["ui_font_size"] != self._ui_font_size_val:
            self._ui_font_size_val = vals["ui_font_size"]
            _ui_font_changed = True
            _need_theme = True
        if _need_theme:
            self._apply_theme(self._is_dark)
        if _ui_font_changed and hasattr(self, "_stats_panel"):
            self._stats_panel.apply_ui_font_size(self._ui_font_size_val)
        if _ui_font_changed and hasattr(self, "_cursor_bar"):
            self._cursor_bar.update_theme(self._is_dark, self._ui_font_size_val)
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
            if hasattr(self, "_act_show_legend"):
                self._act_show_legend.setChecked(self._show_legend)
            self._sync_panel_tab_visibility()
            if self._show_legend:
                self._focus_panel_tab(_PANEL_TAB_LEGEND)
        if vals["show_stats"] != self._show_stats:
            self._show_stats = vals["show_stats"]
            self._sync_panel_tab_visibility()
        if vals["show_marks"] != self._show_marks:
            self._show_marks = vals["show_marks"]
            self._sync_panel_tab_visibility()
        if vals.get("show_find", self._show_find) != self._show_find:
            self._show_find = vals["show_find"]
            self._act_show_find.setChecked(self._show_find)
            self._sync_panel_tab_visibility()
        if vals.get("show_ai", getattr(self, "_show_ai", True)) != getattr(self, "_show_ai", True):
            self._show_ai = vals["show_ai"]
            if hasattr(self, "_act_show_ai"):
                self._act_show_ai.setChecked(self._show_ai)
            self._sync_panel_tab_visibility()
        if vals.get("show_cpu_load", self._show_cpu_load) != self._show_cpu_load:
            # Quiet model update — avoid settings_changed → full view rebuild.
            self._vm.settings._model.show_cpu_load = bool(vals["show_cpu_load"])
            for tab in self._tabs:
                tab.cpu_splitter.set_cpu_visible(self._show_cpu_load)
            self._tb_cpu_load_btn.setChecked(self._show_cpu_load)
            if self._show_cpu_load and self._active_tab is not None:
                if self._cpu_splitter_user_sized:
                    self._apply_saved_cpu_splitter(self._active_tab, force=True)
                else:
                    self._autofit_cpu_load_height()
        if vals["show_hover_highlight"] != self._hover_highlight_val:
            self._hover_highlight_val = vals["show_hover_highlight"]
            self._view._scene.set_hover_highlight(self._hover_highlight_val)
        if vals.get("time_decimals", self._time_decimals_val) != self._time_decimals_val:
            self._time_decimals_val = vals["time_decimals"]
            self._view._scene.set_time_decimals(self._time_decimals_val)
            self._cpu_load_graph.set_time_decimals(self._time_decimals_val)
            self._cursor_bar.rebuild(self._view._scene.cursor_times(), self._trace,
                                     time_decimals=self._time_decimals_val)
            self._update_status_for_active_tab()
            self._rebuild_bookmark_list()
            self._rebuild_annotation_list()
            self._rebuild_cursor_table()
        if vals["colorblind_safe"] != self._colorblind_val:
            self._colorblind_val = vals["colorblind_safe"]
            self._set_colorblind_safe(self._colorblind_val)
        if vals["label_width"] != self._label_width_val:
            self._label_width_val = vals["label_width"]
            self._view._scene.set_label_width(self._label_width_val)
            self._cpu_load_graph.update()
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
        if snap.get("show_find", self._show_find) != self._show_find:
            updates["show_find"] = str(self._show_find).lower()
        if snap.get("show_ai", getattr(self, "_show_ai", True)) != getattr(self, "_show_ai", True):
            updates["show_ai"] = str(self._show_ai).lower()
        if snap.get("show_cpu_load", self._show_cpu_load) != self._show_cpu_load:
            updates["show_cpu_load"] = str(self._show_cpu_load).lower()
        if snap["show_hover_highlight"] != self._hover_highlight_val:
            updates["hover_highlight"] = str(self._hover_highlight_val).lower()
        if snap.get("time_decimals", self._time_decimals_val) != self._time_decimals_val:
            updates["time_decimals"] = str(self._time_decimals_val)
        if snap["colorblind_safe"] != self._colorblind_val:
            updates["colorblind_safe"] = str(self._colorblind_val).lower()
        if snap["label_width"] != self._label_width_val:
            updates["label_width"] = str(self._label_width_val)
            self._persist_label_width(self._label_width_val, flush=False)
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
    def _open_settings(self, page: str = "Appearance") -> None:
        """Open the Settings dialog with live preview; reverts on Cancel.

        *page* selects the sidebar page: ``Appearance``, ``Display``, ``Layout``, or ``AI``.
        """
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
            "show_find":                self._show_find,
            "show_ai":                  getattr(self, "_show_ai", True),
            "show_cpu_load":            self._show_cpu_load,
            "show_hover_highlight":     self._hover_highlight_val,
            "colorblind_safe":          self._colorblind_val,
            "label_width":              self._label_width_val,
            "row_height":               self._row_height_val,
            "row_gap":                  self._row_gap_val,
            "sti_row_h":                self._sti_row_h_val,
            "sti_waveform_h":           self._sti_waveform_h_val,
            "sti_line_style":           self._sti_line_style_val,
            "timescale_per_px_default": self._timescale_per_px_default_val,
            "cpu_load_row_h":           self._cpu_load_row_h_val,
            "cpu_budget_pct":           self._settings.get_float("analysis", "cpu_budget_pct", 0.0),
            "task_deadlines_text":      self._settings.get("analysis", "task_deadlines", ""),
            "time_decimals":            self._time_decimals_val,
        }
        _ai_cfg = self._ai_read_settings()
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
            show_find=self._show_find,
            show_ai=getattr(self, "_show_ai", True),
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
            colorblind_safe=self._colorblind_val,
            zoom_unit=self._current_time_unit(),
            cpu_load_row_h=self._cpu_load_row_h_val,
            cpu_budget_pct=_snap["cpu_budget_pct"],
            task_deadlines_text=_snap["task_deadlines_text"],
            time_decimals=self._time_decimals_val,
            ai_enabled=self._settings.get_bool("ai", "enabled", True),
            ai_preset=_ai_cfg["preset"],
            ai_preset_settings={
                pid: {
                    field: _ai_cfg.get(f"{pid}_{field}", "")
                    for field in AI_PRESET_FIELDS
                }
                for pid, _label, _base, _model in AI_PRESETS
            },
            response_language=_ai_cfg["response_language"],
            initial_page=page if isinstance(page, str) else "Appearance",
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
            "show_find":                dlg.show_find,
            "show_ai":                  dlg.show_ai,
            "show_cpu_load":            dlg.cpu_load,
            "show_hover_highlight":     dlg.show_hover_highlight,
            "colorblind_safe":          dlg.colorblind_safe,
            "label_width":              dlg.label_width,
            "row_height":               dlg.row_height,
            "row_gap":                  dlg.row_gap,
            "sti_row_h":                dlg.sti_row_h,
            "sti_waveform_h":           dlg.sti_waveform_h,
            "sti_line_style":           dlg.sti_line_style,
            "timescale_per_px_default": dlg.timescale_per_px_default,
            "cpu_load_row_h":           dlg.cpu_load_row_h,
            "time_decimals":            dlg.time_decimals,
        }))
        # The dialog carries its own scoped stylesheet (set at construction
        # time).  Re-apply it on every live_preview so that switching the
        # theme combo immediately repaints the dialog itself too.
        dlg.live_preview.connect(
            lambda: dlg.setStyleSheet(
                _SettingsDialog._dialog_ss(
                    dlg.is_dark, _ui_font_stylesheet_size(dlg.ui_font_size))
            )
        )
        if _exec_centred(dlg, self) == QDialog.Accepted:
            self._persist_settings_after_dlg(_snap)
            _new_budget = dlg.cpu_budget_pct
            _new_dl_text = dlg.task_deadlines_text
            if (_snap["cpu_budget_pct"] != _new_budget
                    or _snap["task_deadlines_text"] != _new_dl_text):
                self._settings.set_many("analysis", {
                    "cpu_budget_pct": str(_new_budget),
                    "task_deadlines": _new_dl_text,
                })
                if hasattr(self, "_stats_panel"):
                    self._stats_panel.set_analysis_settings(
                        _new_budget, _parse_task_deadlines_text(_new_dl_text))
            _ai_upd = {
                "enabled": str(dlg.ai_enabled).lower(),
                "preset": dlg.ai_preset or DEFAULT_AI_PRESET,
                "response_language": dlg.response_language or DEFAULT_AI_RESPONSE_LANGUAGE,
            }
            for _pid, _vals in dlg.ai_preset_settings.items():
                for _field in AI_PRESET_FIELDS:
                    _ai_upd[f"{_pid}_{_field}"] = _vals.get(_field, "")
            _ai_changed = any(
                str(_ai_cfg.get(_key, "")) != _val for _key, _val in _ai_upd.items()
            )
            if _ai_changed:
                self._settings.set_many("ai", _ai_upd)
            # Tab visibility follows Enable AI even when only that flag changed.
            self._sync_panel_tab_visibility()
            self._apply_dock_visibility_from_prefs()
            self._sync_ai_menu()
            self._sync_ai_compare_template()
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

    def _persist_label_width(self, width: int, *, flush: bool = True) -> None:
        """Write label-column width to btf_viewer.rc (view + per-window profile)."""
        w = max(60, min(int(width), 600))
        self._label_width_val = w
        self._settings.set("view", "label_width", str(w), flush=False)
        _profile_key = self._dock_profile_key(self.width(), self.height())
        self._settings.set("dock_profile_label_width", _profile_key, str(w), flush=flush)

    def _on_label_width_changed(self, width: int,
                                view: Optional[TimelineView] = None) -> None:
        """Persist label-column width after drag-resize or auto-fit."""
        v = view if view is not None else self._view
        if v is not self._view:
            return
        self._persist_label_width(width)

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
        self._on_timeline_viewport_changed(self._view)

    def _on_timeline_viewport_changed(self, view: TimelineView = None) -> None:
        if view is not None and view is not self._view:
            return
        active = view if view is not None else self._view
        if active is not None and getattr(active, "_programmatic_viewport", 0):
            return
        if self._heatmap_dlg is None:
            return
        dlg = self._heatmap_dlg
        if hasattr(dlg, "follow_scope"):
            dlg.follow_scope()
        timer = getattr(self, "_inspector_vp_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._sync_heatmap_dialog_to_tab)
            self._inspector_vp_timer = timer
        timer.start(120)

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
        self._cursor_bar.rebuild(times, self._trace, time_decimals=self._time_decimals_val)
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
                        b.label = f"Bookmark @{_format_time(new_ns, unit, decimals=self._time_decimals_val)}"
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
            ci.setData(Qt.ItemDataRole.UserRole, ns)
            ti = QTableWidgetItem(_format_time(ns, unit, decimals=self._time_decimals_val))
            task_item = QTableWidgetItem(self._task_at_time(ns))
            if row == 0:
                delta_item = QTableWidgetItem("—")
            else:
                dt = ns - c1
                sign = "+" if dt >= 0 else ""
                delta_item = QTableWidgetItem(f"{sign}{_format_time(abs(dt), unit, decimals=self._time_decimals_val)}")
            for it in (ci, ti, task_item, delta_item):
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._cursor_table.setItem(row, 0, ci)
            self._cursor_table.setItem(row, 1, ti)
            self._cursor_table.setItem(row, 2, task_item)
            self._cursor_table.setItem(row, 3, delta_item)
        self._cursor_table.resizeColumnsToContents()

    def _on_cursor_table_clicked(self, row: int, _col: int) -> None:
        """Jump the timeline to the cursor selected in the comparison table."""
        item = self._cursor_table.item(row, 0)
        if item is not None:
            ns = item.data(Qt.ItemDataRole.UserRole)
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
        stack = list(self._undo_stack)
        stack.append(snap)
        if len(stack) > 50:
            stack.pop(0)
        self._undo_stack = stack
        self._redo_stack = []

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
        redo = list(self._redo_stack)
        redo.append(snap)
        self._redo_stack = redo
        undo = list(self._undo_stack)
        snap = undo.pop()
        self._undo_stack = undo
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
        undo = list(self._undo_stack)
        undo.append(snap)
        self._undo_stack = undo
        redo = list(self._redo_stack)
        snap = redo.pop()
        self._redo_stack = redo
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
        tab = self._active_tab
        if tab is None:
            return
        tab.view._scene.set_migrated_only_filter(enabled)
        if enabled:
            self._legend.set_heatmap_filter(None, None)
            self._sync_show_all_tasks_btn()
        if not self._cpu_splitter_user_sized:
            self._autofit_cpu_load_height()

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
        """Fit the view tightly between the earliest and latest cursor."""
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
        mk, kind, plot_open, preemptor, interval_id = self._stats_panel.capture_plot_session()
        plot_payload = None
        if plot_open and kind:
            plot_payload = {
                "mk": mk,
                "kind": kind,
                "preemptor": preemptor,
                "intervalId": interval_id,
            }
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
            },
            "tabFilters": _snapshot_tab_filters(sc),
            "findQuery": self._find_input.text().strip(),
            "findMode": find_mode,
            "pinnedHighlightKey": sc._locked_task,
            "scopeToCursors": bool(getattr(self._stats_panel, "_scope_to_cursors", True)),
            "openPlot": plot_payload,
            "compareScopeToCursors": True,
        }

    def _apply_portable_session_payload(self, data: dict) -> None:
        """Restore cursors, marks, viewport, and UI state from portable session JSON."""
        if not isinstance(data, dict):
            raise ValueError("Invalid session file")
        if data.get("version") not in (1, SESSION_PORTABLE_VERSION):
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
            # Quiet model update — avoid settings_changed → full view rebuild.
            self._vm.settings._model.show_cpu_load = want_cpu
            for tab in self._tabs:
                tab.cpu_splitter.set_cpu_visible(want_cpu)
            if hasattr(self, "_tb_cpu_load_btn"):
                self._tb_cpu_load_btn.blockSignals(True)
                self._tb_cpu_load_btn.setChecked(want_cpu)
                self._tb_cpu_load_btn.blockSignals(False)
            if want_cpu and self._active_tab is not None:
                if self._cpu_splitter_user_sized:
                    self._apply_saved_cpu_splitter(self._active_tab, force=True)
                else:
                    self._autofit_cpu_load_height()
        if "darkMode" in opts:
            want_dark = bool(opts["darkMode"])
            if self._is_dark != want_dark:
                self._is_dark = want_dark
                self._theme_op_id += 1
                self._apply_theme(want_dark, op=self._theme_op_id)

        filters = _sanitize_tab_filters(data.get("tabFilters"))
        if filters is None:
            filters = _sanitize_tab_filters({
                "migratedOnlyFilter": opts.get("migratedOnlyFilter", False),
            })
        if filters:
            sc.apply_tab_filters(filters)
            self._sync_legend_filters_from_scene(sc)
            self._sync_show_all_tasks_btn()

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

        if "scopeToCursors" in data and hasattr(self._stats_panel, "_scope_cb"):
            self._stats_panel._scope_cb.blockSignals(True)
            self._stats_panel._scope_cb.setChecked(bool(data.get("scopeToCursors", True)))
            self._stats_panel._scope_cb.blockSignals(False)
            self._stats_panel._on_scope_toggled(bool(data.get("scopeToCursors", True)))

        plot = data.get("openPlot")
        if isinstance(plot, dict) and self._trace is not None:
            self._stats_panel.restore_plot_session(
                self._trace,
                plot.get("mk"),
                plot.get("kind"),
                True,
                plot.get("preemptor"),
                plot.get("intervalId"),
            )

        if tab := self._active_tab:
            self._stash_tab_state(tab)

    def _export_portable_session(self) -> None:
        """Export portable session JSON (Web-compatible)."""
        try:
            if tab := self._active_tab:
                self._capture_legend_filters_to_scene(tab.view._scene)
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
                writer = _SafeCsvWriter(fh, quoting=csv.QUOTE_ALL)
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

    # -- Right panel / Find ------------------------------------------------

    def _on_panel_dock_visibility_changed(self, visible: bool) -> None:
        """Clear find overlays when the entire right panel is hidden."""
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
                ("Ctrl+Shift+S", "Save viewport as SVG"),
                ("Ctrl+Shift+C", "Copy viewport to clipboard"),
                ("Ctrl+Shift+E", "Export Perfetto (Chrome Trace JSON)"),
                ("Ctrl+Q",       "Quit  (Alt+F4 also works on Windows)"),
            ]),
            ("Edit", [
                ("Ctrl+Z",    "Undo last cursor / mark change"),
                ("Ctrl+Y",    "Redo"),
            ]),
            ("View / Zoom", [
                ("Ctrl++",               "Zoom in"),
                ("Ctrl+-",               "Zoom out"),
                ("Ctrl+0 / F",           "Fit entire trace to window"),
                ("Ctrl+R",               "Zoom to earliest–latest cursor"),
                ("Ctrl+,",               "Open Settings"),
                ("G",                    "Toggle grid lines on/off"),
                ("I",                    "Toggle STI event rows on/off"),
                ("D",                    "Toggle dark / light theme"),
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
                ("Left-click (near cursor)", "Remove that cursor"),
                ("Left-click (elsewhere)",   "Place cursor (Shift = snap to segment boundary)"),
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
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setWordWrap(False)
            lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
            cols.addWidget(lbl, 1)
        layout.addLayout(cols)
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok)
        btn_box.accepted.connect(dlg.accept)
        layout.addWidget(btn_box)
        _exec_centred(dlg, self)

    @_dialog_guard
    def _on_about(self) -> None:
        _exec_centred(
            _AboutDialog(
                self, is_dark=self._is_dark,
                ui_font_size=getattr(self, "_ui_font_size_val", UI_FONT_SIZE)),
            self)

