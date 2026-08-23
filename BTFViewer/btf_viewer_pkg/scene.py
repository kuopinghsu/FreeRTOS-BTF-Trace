"""BTF Viewer — scene module (source). Do not edit btf_viewer.py; run make bundle."""
from __future__ import annotations

from ._imports import *  # noqa: F403,F401
from .config import *  # noqa: F403,F401
from .parser import *  # noqa: F403,F401
from .timeline_util import *  # noqa: F403,F401
from .graphics_items import *  # noqa: F403,F401

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

    scene_rebuilt    = Signal()          # emitted after every rebuild()
    highlight_changed = Signal(object, bool) # (task_name_or_None, locked)
    task_filter_changed = Signal()     # legend / heatmap / migrated filter changed
    hover_changed    = Signal()          # emitted when hover cursor position changes
    marks_changed    = Signal()          # emitted when bookmark/annotation marks change

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
        self._core_expanded: Dict[str, bool] = {}   # True = task sub-rows visible
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
        self._time_decimals: int = _DEFAULT_TIME_DECIMALS  # UI time-display decimal precision
        self._task_filter_q: str = ""
        self._migrated_only_filter: bool = False
        self._heatmap_filter_mks: Optional[set] = None
        self._heatmap_filter_label: Optional[str] = None
        self._core_filter_keys: Optional[set] = None   # Core Filter (Core View only)
        self._rebuild_suspend: int = 0
        # -- Viewport time bounds (updated at each rebuild for segment clipping) --
        # Set to None initially; _update_viewport_bounds() fills them from the
        # attached QGraphicsView, or falls back to the full trace time range.
        self._vp_ns_lo: int = 0
        self._vp_ns_hi: int = 0
        # Scene time-axis origin (ns).  Timeline coords are relative to this value
        # so QGraphicsScene width stays within Qt's scroll-bar range (~2e9 px).
        self._scene_origin_ns: int = 0
        # Pins scene time origin before rebuild() when jumping along the trace.
        self._virt_jump_origin_ns: Optional[int] = None
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
        # Unpadded task-axis extent from the last rebuild (rows only, no gutters).
        self._orth_content_px: Optional[float] = None
        # Half-width of the orthogonal culling margin (px), set in rebuild().
        self._vp_orth_buf: float = 0.0
        # -- Frozen label-column items -----------------------------------
        # List of (item, orig_x_offset); repositioned on every scroll so
        # the label column stays pinned to the left edge of the viewport.
        self._frozen_items: List[tuple] = []
        # Timeline row backgrounds (not frozen) clipped to the viewport splitter on pan.
        self._row_stripe_item: Optional["_RowStripesItem"] = None
        self._timeline_bg_rects: List = []
        self._timeline_sep_lines: List = []
        self._ruler_grid_item: Optional["_RulerItem"] = None
        # -- Frozen top-row (ruler + TICK band) items --------------------
        # List of (item, orig_y_offset); repositioned on vertical scroll so
        # the time-scale ruler stays pinned to the top edge of the viewport.
        self._frozen_top_items: List[tuple] = []
        # -- Cursor overlay ----------------------------------------------
        # Stored as ns timestamps; drawn as colored dash-lines above everything.
        self._cursor_times: List[int] = []
        self._cursor_items: list = []    # live QGraphicsItems for cursors
        self._cursor_halo_items: list = []   # contrast halo lines, tracked separately
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
        self._finding_overlay_ns: List[int] = []
        self._finding_overlay_items: list = []
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
        self._hover_frozen_top_set: set = set()
        self._hover_frozen_left_set: set = set()
        # -- Ctrl+drag measure ruler --------------------------------------
        # Transient double-arrow line + Δtime label shown while measuring;
        # cleared as soon as the drag (or Ctrl key) ends.
        self._measure_items: list = []
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

    def _core_is_expanded(self, core: str) -> bool:
        """Whether a core's per-task sub-rows are shown (default collapsed)."""
        return self._core_expanded.get(core, False)

    def set_trace(self, trace: BtfTrace, viewport_width: int = 1200) -> None:
        self._trace = trace
        self._scene_origin_ns = trace.time_min
        self._heatmap_filter_mks = None
        self._heatmap_filter_label = None
        self._task_filter_q = ""
        self._migrated_only_filter = False
        self._core_filter_keys = None
        self._core_expanded.clear()
        if trace.core_names:
            _auto_expand = len(trace.core_names) <= _AUTO_EXPAND_CORES_MAX
            for _c in trace.core_names:
                self._core_expanded[_c] = _auto_expand
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
        self._core_expanded[core_name] = not self._core_is_expanded(core_name)
        self.rebuild()

    def set_core_expanded(self, core_name: str, expanded: bool) -> None:
        """Expand or collapse a single core's task sub-rows in the core view."""
        if self._core_expanded.get(core_name) == expanded:
            return
        self._core_expanded[core_name] = expanded
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
            pen  = QPen(color, 1.2, Qt.PenStyle.SolidLine) if kind == "bookmark" else QPen(color, 1.0, Qt.PenStyle.DashLine)

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
                _flag.setPen(QPen(Qt.PenStyle.NoPen))
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
                    QPen(Qt.PenStyle.NoPen),
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
                _flag.setPen(QPen(Qt.PenStyle.NoPen))
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
                    QPen(Qt.PenStyle.NoPen),
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

    def set_time_decimals(self, n: int) -> None:
        """Change the decimal-digit precision of UI time displays and rebuild."""
        self._time_decimals = max(0, min(int(n), 9))
        self.rebuild()

    def set_find_hits(self, ns_list: list) -> None:
        """Update the find-hit overlay with a new list of ns timestamps."""
        self._find_hit_ns_list = list(ns_list)
        self._draw_find_markers()

    def set_finding_overlays(self, ns_list: list) -> None:
        """Vertical markers for Analysis Finding times (not user-editable marks)."""
        self._finding_overlay_ns = list(ns_list or [])
        self._draw_finding_overlays()

    def _draw_find_markers(self) -> None:
        """Draw thin vertical/horizontal lines for each find hit."""
        _safe_scene_remove_items(self, self._find_hit_items)
        self._find_hit_items.clear()
        if self._trace is None or not self._find_hit_ns_list:
            return
        scene_r = self.sceneRect()
        pen = QPen(QColor("#FF6B35"), 1.0, Qt.PenStyle.SolidLine)
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

    def _draw_finding_overlays(self) -> None:
        _safe_scene_remove_items(self, self._finding_overlay_items)
        self._finding_overlay_items.clear()
        if self._trace is None or not self._finding_overlay_ns:
            return
        scene_r = self.sceneRect()
        pen = QPen(QColor("#C084FC"), 1.0, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        for ns in self._finding_overlay_ns:
            if self._horizontal:
                x = self._label_width + self._ns_to_px(ns)
                line = QGraphicsLineItem(x, 0, x, scene_r.height())
            else:
                y = self._label_width + self._ns_to_px(ns)
                line = QGraphicsLineItem(0, y, scene_r.width(), y)
            line.setPen(pen)
            line.setZValue(25)
            self.addItem(line)
            self._finding_overlay_items.append(line)

    def _dim_brush_if_follow(self, brush: QBrush, merge_key: str) -> QBrush:
        """Dim segments of other tasks when one task is lock-highlighted."""
        if not self._locked_task or self._locked_task == merge_key:
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
        self.task_filter_changed.emit()

    def set_migrated_only_filter(self, enabled: bool) -> None:
        """When enabled, show only tasks that ran on 2+ cores."""
        enabled = bool(enabled)
        if enabled == self._migrated_only_filter and not (
                enabled and self._heatmap_filter_mks):
            return
        self._migrated_only_filter = enabled
        if enabled:
            self._heatmap_filter_mks = None
            self._heatmap_filter_label = None
        self.rebuild()
        self.task_filter_changed.emit()

    def set_heatmap_task_filter(self, merge_keys: Optional[set],
                                label: Optional[str] = None) -> None:
        """Show only tasks that migrated in a heatmap drill-down selection."""
        mks = set(merge_keys) if merge_keys else None
        if mks == self._heatmap_filter_mks and label == self._heatmap_filter_label:
            return
        self._heatmap_filter_mks = mks
        if mks:
            self._migrated_only_filter = False
            if label is not None:
                self._heatmap_filter_label = label
            # Expand only cores that contain a filtered task so core view
            # draws task sub-rows instead of heavy per-core summary bars.
            tr = self._trace
            if tr is not None:
                for core in tr.core_names:
                    self._core_expanded[core] = any(
                        _task_merge_key(t) in mks
                        for t in tr.core_task_order.get(core, []))
        else:
            self._heatmap_filter_label = None
        self.rebuild()
        self.task_filter_changed.emit()

    def apply_tab_filters(self, filters: dict, *, rebuild: bool = True) -> None:
        """Restore saved filter fields (single rebuild when *rebuild* is True)."""
        if not filters:
            return
        q = (filters.get("taskFilterText") or "").strip().lower()
        mks_raw = filters.get("taskFilterKeys")
        mks = set(mks_raw) if mks_raw else None
        migrated = bool(filters.get("migratedOnlyFilter")) and mks is None
        label = filters.get("heatmapFilterLabel") if mks else None
        core_keys_raw = filters.get("coreFilterKeys")
        core_keys = set(core_keys_raw) if core_keys_raw else None
        if (q == self._task_filter_q and migrated == self._migrated_only_filter
                and mks == self._heatmap_filter_mks
                and label == self._heatmap_filter_label
                and core_keys == self._core_filter_keys):
            return
        self._task_filter_q = q
        self._migrated_only_filter = migrated
        self._heatmap_filter_mks = mks
        self._heatmap_filter_label = label
        self._core_filter_keys = core_keys
        if mks and self._trace is not None:
            for core in self._trace.core_names:
                self._core_expanded[core] = any(
                    _task_merge_key(t) in mks
                    for t in self._trace.core_task_order.get(core, []))
        if rebuild:
            self.rebuild()
            self.task_filter_changed.emit()

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
        self._label_width = max(60, min(int(width), 600))
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
        # Clamp: don't zoom in past _timescale_per_px_default (2 ns/px in
        # trace units, scaled by set_trace). Don't zoom out past Fit-to-window
        # (_timescale_per_px_fit). Matches Web's wheel/zoomCenter cap.
        new_val = max(self._timescale_per_px_default, new_val)
        if self._timescale_per_px_fit < float("inf"):
            new_val = min(self._timescale_per_px_fit, new_val)
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
        ns = int((coord - self._label_width) * self._timescale_per_px) + self._scene_origin_ns
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
                expanded = self._core_is_expanded(core)
                tasks = core_tasks.get(core, [])
                core_row = row_idx
                if task_key == core:
                    return RULER_HEIGHT + core_row * row_stride + self._row_height / 2
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
                expanded = self._core_is_expanded(core)
                tasks = core_tasks.get(core, [])
                core_col = col_idx
                if task_key == core:
                    return RULER_WIDTH + core_col * col_w + col_w / 2
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
                expanded = self._core_is_expanded(core)
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
            expanded = self._core_is_expanded(core)
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

    def _sti_orth_extent(self, sti_channels: list, horizontal: bool) -> float:
        """Total orthogonal size consumed by STI rows/columns."""
        col_w = max(self._row_height + self._row_gap, 26)
        total = 0.0
        for ch in sti_channels:
            if horizontal:
                h = (self._sti_waveform_h_val if ch in self._sti_expanded
                     else self._sti_row_h_val)
                total += h + self._row_gap
            else:
                cw = (self._sti_waveform_h_val
                      if (_is_tag_sti_channel(ch) and ch in self._sti_expanded)
                      else col_w)
                total += cw
        return total

    def _primary_orth_count(self) -> int:
        """Task/core row or column count before STI and interval lanes."""
        trace = self._trace
        if self._view_mode == "task":
            return len([t for t in trace.tasks if self._task_merge_key_matches_filter(t)])
        core_names, core_tasks = self._filtered_core_view_tasks()
        n = 0
        for c in core_names:
            n += 1
            if self._core_is_expanded(c):
                n += len(core_tasks[c])
        return n

    def _filtered_sti_channels(self) -> list:
        sti = list(self._trace.sti_channels) if self._show_sti else []
        if self._task_filter_q:
            sti = [c for c in sti if self._sti_channel_matches_filter(c)]
        return sti

    def interval_orth_scene_span(self, interval_id: str) -> Optional[Tuple[float, float]]:
        """Return the visible orthogonal span of an interval row/column."""
        if self._trace is None or not self._show_sti:
            return None
        iid = str(interval_id)
        try:
            idx = self._trace.interval_ids.index(iid)
        except ValueError:
            return None
        sti = self._filtered_sti_channels()
        if self._horizontal:
            row_stride = self._row_height + self._row_gap
            y_top = (RULER_HEIGHT
                     + self._primary_orth_count() * row_stride
                     + self._sti_orth_extent(sti, True)
                     + idx * row_stride)
            return (y_top, y_top + self._row_height)
        col_w = max(self._row_height + self._row_gap, 26)
        x_left = (RULER_WIDTH
                  + self._primary_orth_count() * col_w
                  + self._sti_orth_extent(sti, False)
                  + idx * col_w)
        return (x_left, x_left + col_w)

    def sti_channel_orth_scene_span(self, channel: str) -> Optional[Tuple[float, float]]:
        """Return the visible orthogonal span of an STI channel row/column."""
        if self._trace is None or not self._show_sti:
            return None
        sti = self._filtered_sti_channels()
        try:
            idx = sti.index(channel)
        except ValueError:
            return None
        if self._horizontal:
            row_stride_base = self._row_height + self._row_gap
            y_top = RULER_HEIGHT + self._primary_orth_count() * row_stride_base
            for ch in sti[:idx]:
                h = (self._sti_waveform_h_val if ch in self._sti_expanded
                     else self._sti_row_h_val)
                y_top += h + self._row_gap
            h = (self._sti_waveform_h_val if channel in self._sti_expanded
                 else self._sti_row_h_val)
            return (y_top, y_top + h)
        col_w = max(self._row_height + self._row_gap, 26)
        x_left = RULER_WIDTH + self._primary_orth_count() * col_w
        for ch in sti[:idx]:
            cw = (self._sti_waveform_h_val
                  if (_is_tag_sti_channel(ch) and ch in self._sti_expanded)
                  else col_w)
            x_left += cw
        cw = (self._sti_waveform_h_val
              if (_is_tag_sti_channel(channel) and channel in self._sti_expanded)
              else col_w)
        return (x_left, x_left + cw)

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

    def remove_cursor_at_index(self, index: int) -> None:
        """Remove cursor by list index (click-near-remove)."""
        if 0 <= index < len(self._cursor_times):
            self._cursor_times.pop(index)
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

    def _purge_hover_frozen(self) -> None:
        """Remove hover label entries from frozen overlay lists."""
        if self._hover_frozen_top_set:
            self._frozen_top_items = [e for e in self._frozen_top_items
                                      if e[0] not in self._hover_frozen_top_set]
            self._hover_frozen_top_set = set()
        if self._hover_frozen_left_set:
            self._frozen_items = [e for e in self._frozen_items
                                  if e[0] not in self._hover_frozen_left_set]
            self._hover_frozen_left_set = set()

    def _draw_hover_line(self) -> None:
        """Draw a thin dashed ghost line at self._hover_ns with a time label."""
        if self._trace is None or self._hover_ns is None:
            _safe_scene_remove_items(self, self._hover_items)
            self._hover_items.clear()
            self._purge_hover_frozen()
            if self._hover_line_ns is not None:
                self._hover_line_ns = None
                self.hover_changed.emit()
            return
        if self._hover_ns == self._hover_line_ns:
            return
        _safe_scene_remove_items(self, self._hover_items)
        self._hover_items.clear()
        self._purge_hover_frozen()
        self._hover_line_ns = self._hover_ns
        self.hover_changed.emit()
        scene_r = self.sceneRect()
        font = _monospace_font(max(8, self._font_size - 1))
        fm   = QFontMetrics(font)
        t_str = _format_time(self._hover_ns, self._trace.time_scale, decimals=self._time_decimals)
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
        hover_pen = QPen(line_col, 1.2 if not self._is_dark_ui else 1.0, Qt.PenStyle.DashLine)
        hover_pen.setDashPattern([3, 3])
        if self._horizontal:
            x = self._label_width + self._ns_to_px(self._hover_ns)
            line = QGraphicsLineItem(x, 0, x, scene_r.height())
            line.setPen(hover_pen)
            line.setZValue(25)
            line.setAcceptHoverEvents(False)
            self.addItem(line)
            self._hover_items.append(line)
            # Time label centred on x, pinned near the bottom of the ruler band.
            lbl_x = min(x - tw / 2, scene_r.width() - tw - 4)
            lbl_x = max(self._label_width + 2, lbl_x)
            _orig_y_bg = RULER_HEIGHT - th - 4
            _orig_y_lbl = _orig_y_bg + 1
            bg = self.addRect(
                QRectF(0, 0, tw, th + 2),
                QPen(Qt.PenStyle.NoPen), QBrush(lbl_bg))
            bg.setZValue(26)
            bg.setAcceptHoverEvents(False)
            bg.setPos(lbl_x, _orig_y_bg)
            lbl = self.addSimpleText(t_str, font)
            lbl.setBrush(QBrush(lbl_txt))
            lbl.setZValue(27)
            lbl.setAcceptHoverEvents(False)
            lbl.setPos(lbl_x + 4, _orig_y_lbl)
            self._hover_items.extend([bg, lbl])
            self._frozen_top_items.append((bg, _orig_y_bg))
            self._frozen_top_items.append((lbl, _orig_y_lbl))
            self._hover_frozen_top_set.update({bg, lbl})
        else:
            label_row_h = self._label_width
            y = label_row_h + self._ns_to_px(self._hover_ns)
            line = QGraphicsLineItem(RULER_WIDTH, y, scene_r.width(), y)
            line.setPen(hover_pen)
            line.setZValue(25)
            line.setAcceptHoverEvents(False)
            self.addItem(line)
            self._hover_items.append(line)
            # Match web drawHoverLineVertical: label right-aligned in ruler column.
            tw_text = fm.horizontalAdvance(t_str)
            _badge_w = tw_text + 8
            _badge_h = 14
            ly = max(label_row_h + 3, min(y - 7, int(scene_r.height()) - 17))
            _bg_x = RULER_WIDTH - 2 - _badge_w
            _lbl_x = RULER_WIDTH - 4 - tw_text
            bg = self.addRect(
                QRectF(0, 0, _badge_w, _badge_h),
                QPen(Qt.PenStyle.NoPen), QBrush(lbl_bg))
            bg.setZValue(37)
            bg.setAcceptHoverEvents(False)
            bg.setPos(_bg_x, ly)
            lbl = self.addSimpleText(t_str, font)
            lbl.setBrush(QBrush(lbl_txt))
            lbl.setZValue(38)
            lbl.setAcceptHoverEvents(False)
            lbl.setPos(_lbl_x, ly + (_badge_h - th) / 2)
            self._hover_items.extend([bg, lbl])
            self._frozen_items.append((bg, _bg_x))
            self._frozen_items.append((lbl, _lbl_x))
            self._hover_frozen_left_set.update({bg, lbl})

        self._pin_cursor_overlays()

    def clear_hover_line(self) -> None:
        """Remove the hover ghost line from the scene."""
        if not self._hover_items and self._hover_line_ns is None:
            self._hover_ns = None
            return
        _safe_scene_remove_items(self, self._hover_items)
        self._hover_items.clear()
        self._purge_hover_frozen()
        self._hover_ns = None
        self._hover_line_ns = None
        self.hover_changed.emit()

    # ------------------------------------------------------------------
    # Ctrl+drag measure ruler
    # ------------------------------------------------------------------

    def _draw_measure_ruler(self, ns_a: int, ns_b: int, anchor_coord: float) -> None:
        """Draw a transient double-arrow ruler + Δtime label from ns_a to ns_b.

        anchor_coord is the scene Y (horizontal mode) or X (vertical mode) at
        which the ruler is drawn - fixed at the row/column where the Ctrl+drag
        started, so the line stays straight (horizontal or vertical) even if
        the mouse wanders off-axis during the drag.
        """
        _safe_scene_remove_items(self, self._measure_items)
        self._measure_items.clear()
        if self._trace is None:
            return

        coord_a = self.ns_to_scene_coord(ns_a)
        coord_b = self.ns_to_scene_coord(ns_b)
        lo, hi  = (coord_a, coord_b) if coord_a <= coord_b else (coord_b, coord_a)
        d_str = f"Δ {_format_time(abs(ns_b - ns_a), self._trace.time_scale, decimals=self._time_decimals)}"

        color = QColor("#FFB300")   # amber - distinct from cursor/hover/mark colours
        pen   = QPen(color, 1.6, Qt.PenStyle.SolidLine)
        font  = _monospace_font(self._font_size, QFont.Bold)
        fm    = QFontMetrics(font)
        arrow = 6
        half  = 3
        tw    = fm.horizontalAdvance(d_str)
        th    = fm.height()

        if self._horizontal:
            y = anchor_coord
            line = QGraphicsLineItem(lo, y, hi, y)
            line.setPen(pen)
            line.setZValue(60)
            self.addItem(line)
            self._measure_items.append(line)

            for tip_x, sign in ((lo, 1), (hi, -1)):
                pts = [QPointF(tip_x, y),
                       QPointF(tip_x + sign * arrow, y - half),
                       QPointF(tip_x + sign * arrow, y + half)]
                tri = QGraphicsPolygonItem(QPolygonF(pts))
                tri.setBrush(QBrush(color))
                tri.setPen(QPen(Qt.PenStyle.NoPen))
                tri.setZValue(61)
                self.addItem(tri)
                self._measure_items.append(tri)

            mid_x = (lo + hi) / 2
            lbl_y = y - th - 8
            bg = self.addRect(QRectF(0, 0, tw + 8, th + 4),
                               QPen(Qt.PenStyle.NoPen), QBrush(color))
            bg.setZValue(61)
            bg.setPos(mid_x - tw / 2 - 4, lbl_y)
            lbl = self.addSimpleText(d_str, font)
            lbl.setBrush(QBrush(QColor("#000000")))
            lbl.setZValue(62)
            lbl.setPos(mid_x - tw / 2, lbl_y + 2)
            self._measure_items.extend([bg, lbl])
        else:
            x = anchor_coord
            line = QGraphicsLineItem(x, lo, x, hi)
            line.setPen(pen)
            line.setZValue(60)
            self.addItem(line)
            self._measure_items.append(line)

            for tip_y, sign in ((lo, 1), (hi, -1)):
                pts = [QPointF(x, tip_y),
                       QPointF(x - half, tip_y + sign * arrow),
                       QPointF(x + half, tip_y + sign * arrow)]
                tri = QGraphicsPolygonItem(QPolygonF(pts))
                tri.setBrush(QBrush(color))
                tri.setPen(QPen(Qt.PenStyle.NoPen))
                tri.setZValue(61)
                self.addItem(tri)
                self._measure_items.append(tri)

            mid_y = (lo + hi) / 2
            lbl_x = x + 8
            bg = self.addRect(QRectF(0, 0, tw + 8, th + 4),
                               QPen(Qt.PenStyle.NoPen), QBrush(color))
            bg.setZValue(61)
            bg.setPos(lbl_x, mid_y - th / 2 - 2)
            lbl = self.addSimpleText(d_str, font)
            lbl.setBrush(QBrush(QColor("#000000")))
            lbl.setZValue(62)
            lbl.setPos(lbl_x + 4, mid_y - th / 2)
            self._measure_items.extend([bg, lbl])

    def clear_measure_ruler(self) -> None:
        """Remove the transient measure-ruler overlay from the scene."""
        if not self._measure_items:
            return
        _safe_scene_remove_items(self, self._measure_items)
        self._measure_items.clear()

    # ------------------------------------------------------------------
    # Draw cursor overlay
    # ------------------------------------------------------------------

    def _draw_cursors(self) -> None:
        _safe_scene_remove_items(self, self._cursor_items)
        self._cursor_items.clear()
        _safe_scene_remove_items(self, self._cursor_halo_items)
        self._cursor_halo_items.clear()

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

        sorted_cursors = sorted(enumerate(self._cursor_times), key=lambda x: x[1])
        cursor_palette = _cursor_colors(self._is_dark_ui)
        # Halo drawn under every cursor line so the marker stays visible over
        # task segments whose colour is close to the cursor's own colour.
        halo_color = QColor(0, 0, 0, 140) if self._is_dark_ui else QColor(255, 255, 255, 170)
        halo_pen = QPen(halo_color, 2.6, Qt.PenStyle.SolidLine)
        # Delta badges get their own row, below every cursor's own badge row -
        # otherwise when two cursors are close together on screen (a common
        # case: measuring a short interval), the delta's midpoint lands right
        # on top of the later cursor's badge and both become unreadable.
        delta_row_index = len(sorted_cursors) + 1

        for order, (orig_idx, ns) in enumerate(sorted_cursors):
            color = QColor(cursor_palette[orig_idx % len(cursor_palette)])
            pen   = QPen(color, 1.2, Qt.PenStyle.DashLine)

            if self._horizontal:
                x = self._label_width + self._ns_to_px(ns)
                halo = QGraphicsLineItem(x, 0, x, scene_r.height())
                halo.setPen(halo_pen)
                halo.setZValue(29)
                self.addItem(halo)
                self._cursor_halo_items.append(halo)
                line = QGraphicsLineItem(x, 0, x, scene_r.height())
                line.setPen(pen)
                line.setZValue(30)
                self.addItem(line)
                self._cursor_items.append(line)

                t_str = _format_time(ns, self._trace.time_scale, decimals=self._time_decimals)
                lbl = self.addSimpleText(f"C{orig_idx+1}: {t_str}", font_big)
                lbl.setBrush(QBrush(QColor("#000000")))
                lbl.setZValue(32)
                tw = fm_bold.horizontalAdvance(lbl.text())
                th = fm_bold.height()
                lbl_x = min(x + 3, scene_r.width() - tw - 4)
                _orig_y = 2 + (orig_idx + 1) * (th + 2)
                bg = self.addRect(
                    QRectF(0, 0, tw + 4, th + 2),
                    QPen(Qt.PenStyle.NoPen),
                    QBrush(color),
                )
                bg.setZValue(31)
                bg.setPos(lbl_x - 2, _orig_y - 1)
                lbl.setPos(lbl_x, _orig_y)
                self._cursor_items.extend([bg, lbl])
                # Register label + background as y-frozen so _reposition_frozen_top
                # keeps them in the ruler area regardless of vertical scroll.
                self._frozen_top_items.append((bg, _orig_y - 1))
                self._frozen_top_items.append((lbl, _orig_y))
                self._cursor_frozen_top_set.update({bg, lbl})

                if order > 0:
                    prev_ns = sorted_cursors[order - 1][1]
                    delta   = abs(ns - prev_ns)
                    d_str   = f"Δ {_format_time(delta, self._trace.time_scale, decimals=self._time_decimals)}"
                    mid_x   = self._label_width + self._ns_to_px((ns + prev_ns) // 2)
                    d_lbl   = self.addSimpleText(d_str, font)
                    d_w     = QFontMetrics(font).horizontalAdvance(d_str)
                    d_h     = QFontMetrics(font).height()
                    d_lbl.setBrush(QBrush(QColor("#000000")))
                    d_lbl.setZValue(32)
                    # Own dedicated row below all cursor badges - never shares
                    # a row with a cursor's own badge, even when the cursors
                    # are close enough together that the midpoint would
                    # otherwise land on top of it (see delta_row_index above).
                    _delta_orig_y_lbl = 2 + delta_row_index * (th + 2)
                    _delta_orig_y_bg = _delta_orig_y_lbl - 1
                    bg_rect = self.addRect(
                        QRectF(0, 0, d_w + 6, d_h + 2),
                        QPen(Qt.PenStyle.NoPen),
                        QBrush(color),
                    )
                    bg_rect.setZValue(31)
                    bg_rect.setPos(mid_x - d_w / 2 - 3, _delta_orig_y_bg)
                    d_lbl.setPos(mid_x - d_w / 2, _delta_orig_y_lbl)
                    self._cursor_items.extend([bg_rect, d_lbl])
                    self._frozen_top_items.append((bg_rect, _delta_orig_y_bg))
                    self._frozen_top_items.append((d_lbl, _delta_orig_y_lbl))
                    self._cursor_frozen_top_set.update({bg_rect, d_lbl})

            else:  # vertical mode
                label_row_h = self._label_width
                y = label_row_h + self._ns_to_px(ns)
                halo = QGraphicsLineItem(0, y, scene_r.width(), y)
                halo.setPen(halo_pen)
                halo.setZValue(29)
                self.addItem(halo)
                self._cursor_halo_items.append(halo)
                line = QGraphicsLineItem(0, y, scene_r.width(), y)
                line.setPen(pen)
                line.setZValue(30)
                self.addItem(line)
                self._cursor_items.append(line)

                t_str = _format_time(ns, self._trace.time_scale, decimals=self._time_decimals)
                lbl = self.addSimpleText(f"C{orig_idx+1}: {t_str}", font_big)
                lbl.setBrush(QBrush(QColor("#000000")))
                lbl.setZValue(38)
                tw = fm_bold.horizontalAdvance(lbl.text())
                th = fm_bold.height()
                # Match web vertical layout: badge in left ruler column at x=2.
                _pad = 4
                _badge_h = 14
                _left_bg_x = 2
                _left_lbl_x = _left_bg_x + _pad
                _lbl_y = min(y + 2, scene_r.height() - _badge_h - 2)
                bg = self.addRect(
                    QRectF(0, 0, tw + _pad * 2, _badge_h),
                    QPen(Qt.PenStyle.NoPen),
                    QBrush(color),
                )
                bg.setZValue(37)
                bg.setPos(_left_bg_x, _lbl_y)
                lbl.setPos(_left_lbl_x, _lbl_y + (_badge_h - th) / 2)
                self._cursor_items.extend([bg, lbl])
                self._frozen_items.append((bg, _left_bg_x))
                self._frozen_items.append((lbl, _left_lbl_x))
                self._cursor_frozen_left_set.update({bg, lbl})

                if order > 0:
                    prev_ns = sorted_cursors[order - 1][1]
                    delta   = abs(ns - prev_ns)
                    d_str   = f"Δ {_format_time(delta, self._trace.time_scale, decimals=self._time_decimals)}"
                    d_lbl   = self.addSimpleText(d_str, font)
                    dh      = QFontMetrics(font).height()
                    dw      = QFontMetrics(font).horizontalAdvance(d_str)
                    d_lbl.setBrush(QBrush(QColor("#000000")))
                    d_lbl.setZValue(32)
                    # Align Δ with the later cursor label row (same Y as C2, C3, …).
                    _delta_x = RULER_WIDTH + 4
                    bg_rect = self.addRect(
                        QRectF(0, 0, dw + 6, _badge_h),
                        QPen(Qt.PenStyle.NoPen), QBrush(color)
                    )
                    bg_rect.setZValue(31)
                    bg_rect.setPos(_delta_x, _lbl_y)
                    d_lbl.setPos(_delta_x + 3, _lbl_y + (_badge_h - dh) / 2)
                    self._cursor_items.extend([bg_rect, d_lbl])
                    self._frozen_items.append((bg_rect, _delta_x))
                    self._frozen_items.append((d_lbl, _delta_x + 3))
                    self._cursor_frozen_left_set.update({bg_rect, d_lbl})

        self._pin_cursor_overlays()

    def _pin_cursor_overlays(self) -> None:
        """Re-anchor cursor/delta labels after draw (viewport-frozen coordinates)."""
        view = self.views()[0] if self.views() else None
        if view is None:
            return
        view._frozen_last_scene_top = None
        view._frozen_last_scene_left = None
        view._reposition_frozen_top()
        view._reposition_frozen()

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
            lw_pt = int(self._label_width)
            lo_coord = view.mapToScene(QPoint(lw_pt, vp_rect.top())).x()
            hi_coord = view.mapToScene(vp_rect.topRight()).x()
        else:
            lw_pt = int(self._label_width)
            lo_coord = view.mapToScene(QPoint(vp_rect.left(), lw_pt)).y()
            hi_coord = view.mapToScene(vp_rect.bottomLeft()).y()

        lw = self._label_width
        origin = self._scene_origin_ns
        ns_lo = origin + int((lo_coord - lw) * self._timescale_per_px)
        ns_hi = origin + int((hi_coord - lw) * self._timescale_per_px)

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
        page_ns = max(1, int(view._timeline_viewport_px() * self._timescale_per_px))
        if ns_lo >= ns_hi:
            # At trace start/end the clamped window can collapse to a point.
            # Do NOT fall back to the full trace (that jumps virtual scroll to
            # the left); keep a minimal span anchored at the visible edge.
            ns_lo, ns_hi = _fix_collapsed_time_ns_range(
                ns_lo, ns_hi, lo_coord, hi_coord, t_min, t_max,
                self._timescale_per_px, min_span_ns=page_ns)

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

    def _viewport_orth_extent(self) -> float:
        """Task-axis scene extent that matches the current viewport (rows in H-mode)."""
        view = self.views()[0] if self.views() else None
        if view is None:
            return 0.0
        vp = view.viewport().rect()
        if vp.width() <= 1 or vp.height() <= 1:
            return 0.0
        if self._horizontal:
            tl = view.mapToScene(vp.topLeft())
            bl = view.mapToScene(vp.bottomLeft())
            return max(1.0, bl.y() - tl.y())
        tl = view.mapToScene(vp.topLeft())
        tr = view.mapToScene(vp.topRight())
        return max(1.0, tr.x() - tl.x())

    def _orth_scroll_gutter(self) -> float:
        view = self.views()[0] if self.views() else None
        if view is None:
            return 0.0
        fn = getattr(view, "orth_scroll_gutter_px", None)
        return float(fn()) if callable(fn) else 0.0

    def _finalize_orth_size(self, content_orth: float) -> float:
        """Fill the task axis to the viewport; pad so rows clear overlays/chrome.

        Padding (scrollbar track + CPU-load overlay inset) is applied whenever
        content exceeds the *usable* viewport (full viewport minus gutters), so
        the last task row can scroll out from under the CPU-load overlay.
        """
        vp = self._viewport_orth_extent()
        gutter = self._orth_scroll_gutter()
        usable = max(1.0, vp - gutter)
        orth = max(content_orth, vp)
        if content_orth > usable + 0.5:
            orth = max(orth, content_orth + gutter)
        return orth

    def _add_orth_filler_horizontal(self, content_h: float, total_h: float,
                                    total_w: float, lw: float, last_row_idx: int) -> None:
        if content_h >= total_h - 0.5:
            return
        brush = QBrush(self._c_row_even if last_row_idx % 2 == 0 else self._c_row_odd)
        rect = self.addRect(
            QRectF(lw, content_h, total_w - lw, total_h - content_h),
            QPen(Qt.PenStyle.NoPen), brush)
        rect.setZValue(0)
        self._track_timeline_bg(rect)

    def _add_orth_filler_vertical(self, content_w: float, total_w: float,
                                  total_h: float, label_row_h: float,
                                  last_col_idx: int) -> None:
        if content_w >= total_w - 0.5:
            return
        brush = QBrush(self._c_row_even if last_col_idx % 2 == 0 else self._c_row_odd)
        rect = self.addRect(
            QRectF(content_w, label_row_h, total_w - content_w, total_h - label_row_h),
            QPen(Qt.PenStyle.NoPen), brush)
        rect.setZValue(0)

    def rebuild(self) -> None:
        if self._rebuild_suspend > 0:
            return
        view = self.views()[0] if self.views() else None
        virt_active = (getattr(view, '_virtual_time_scroll_active', False)
                       if view is not None else False)
        virt_window_shift = (getattr(view, '_virt_scroll_rebuild', False)
                             if view is not None else False)
        # Orthogonal rebuild: clip/load the time window from canonical virt
        # (not the live viewport, which scene.clear() will corrupt) and
        # remember the native bar value to restore after the scene is rebuilt.
        if (view is not None and virt_active and self._trace is not None
                and not virt_window_shift
                and self._virt_jump_origin_ns is None):
            # Reuse the loaded time slice from the last rebuild.  A tight
            # virt-centered hint shrinks the scene after horizontal panning
            # (native bar max drops below the preserved scroll → time jump).
            if self._vp_ns_lo < self._vp_ns_hi:
                self._ns_range_hint = (self._vp_ns_lo, self._vp_ns_hi)
            else:
                ns_lo_v = view._ns_lo_from_virt_px(view._virt_time_scroll_px)
                page_ns = view._timeline_viewport_px() * self._timescale_per_px
                margin_ns = max(1, int(page_ns * 0.75))
                self._ns_range_hint = (
                    max(self._trace.time_min, int(ns_lo_v - margin_ns)),
                    min(self._trace.time_max, int(ns_lo_v + page_ns + margin_ns)),
                )
            view._preserve_virt_scroll = True
            view._preserved_virt_scroll_px = view._virt_time_scroll_px
        self._update_viewport_bounds()
        if self._virt_jump_origin_ns is not None:
            self._scene_origin_ns = self._virt_jump_origin_ns
            self._virt_jump_origin_ns = None
        elif virt_active:
            # Orth / margin rebuild: keep the sliding-window origin; do not
            # re-anchor to _vp_ns_lo (would jump time when scrolling rows).
            pass
        elif (self._trace is not None
              and view is not None
              and not getattr(view, "_fit_mode", False)
              and self._timescale_per_px > self._timescale_per_px_fit * 1.02):
            # Zoomed out past Fit: origin may sit before time_min (overscan
            # so C1–C2 can sit at the viewport center). Do not re-anchor to
            # clamped _vp_ns_lo. Fit mode must still reset to time_min.
            pass
        elif self._trace is not None:
            self._scene_origin_ns = self._vp_ns_lo
        self.clear()
        self._cursor_items = []
        self._cursor_halo_items = []
        self._mark_items = []
        self._frozen_items = []
        self._frozen_top_items = []
        self._row_stripe_item = None
        self._timeline_bg_rects = []
        self._timeline_sep_lines = []
        self._ruler_grid_item = None
        self._cursor_frozen_top_set = set()
        self._cursor_frozen_left_set = set()
        self._mark_frozen_top_set = set()
        self._mark_frozen_left_set = set()
        self._hover_frozen_top_set = set()
        self._hover_frozen_left_set = set()
        self._task_row_rects = {}
        self._hover_overlay_items = []   # clear() removed them from the scene
        self._hover_items = []             # clear() removed them from the scene
        self._hover_line_ns = None
        self._measure_items = []           # clear() removed them from the scene
        self._find_hit_items = []
        self._finding_overlay_items = []
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
        self._draw_finding_overlays()
        if self._hover_ns is not None:
            self._draw_hover_line()
        self.scene_rebuilt.emit()

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def _ns_to_px(self, ns: int) -> float:
        return (ns - self._scene_origin_ns) / self._timescale_per_px

    def _scene_timeline_span_px(self) -> float:
        """Visible timeline span in pixels (capped for Qt scroll-bar limits)."""
        visible_ns = max(self._vp_ns_hi - self._vp_ns_lo, 1)
        span_px = visible_ns / self._timescale_per_px
        views = self.views()
        if views:
            # Zoomed out past Fit, the viewport is wider than the trace.
            # Size the scene to the viewport so empty margin (and a cursor
            # midpoint placed at screen center) is real scene space, not
            # QGraphicsView letterboxing that AlignLeft cannot pan.
            span_px = max(span_px, views[0]._timeline_viewport_px())
        return min(span_px, _MAX_SCENE_TIMELINE_PX)

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

    def set_core_filter(self, keys: Optional[List[str]]) -> None:
        """Core Filter (Core View only) — narrows Scope to a subset of cores."""
        self._core_filter_keys = set(keys) if keys else None
        self.rebuild()

    def _core_filter_active(self) -> bool:
        """True when the Core Filter narrows Scope to fewer than all cores."""
        if not self._core_filter_keys or self._trace is None:
            return False
        return len(self._core_filter_keys) < len(self._trace.core_names)

    def _filtered_core_view_tasks(self) -> Tuple[List[str], Dict[str, List[str]]]:
        """Core names and per-core task lists (no TICK) after active filters."""
        trace = self._trace
        core_names = list(trace.core_names)
        if self._core_filter_keys:
            core_names = [c for c in core_names if c in self._core_filter_keys]
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
            time_min=self._scene_origin_ns,
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

    def _track_timeline_bg(self, item) -> None:
        """Register a timeline row background rect clipped on horizontal pan."""
        self._timeline_bg_rects.append(item)

    def _track_timeline_sep_line(self, item) -> None:
        """Register a horizontal row separator clipped on horizontal pan."""
        self._timeline_sep_lines.append(item)

    def _add_frozen_label_grip(self, lw: float, total_h: float) -> None:
        """Scene-frozen resize grip (stays on the label/timeline boundary while panning)."""
        grip = _LabelColumnGripItem(self, total_h)
        self.addItem(grip)
        self._frozen_items.append((grip, int(lw)))

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
        _tick_no_pen = QPen(Qt.PenStyle.NoPen)
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
            time_min=vp.time_min, time_decimals=self._time_decimals)
        batch.setZValue(batch_z)
        self.addItem(batch)
        if freeze_top:
            self._frozen_top_items.append((batch, 0))
        else:
            self._frozen_items.append((batch, 0))
        return True

    def _add_priority_boost_bands(
        self,
        trace: "BtfTrace",
        task_mk: str,
        bounds: QRectF,
        horiz: bool,
        time_min: int,
        px_per_ns: float,
        vp_ns_lo: int,
        vp_ns_hi: int,
    ) -> None:
        """Draw priority boost / inversion indicator stripes on a task row or column."""
        if not trace.has_priority_instrumentation:
            return
        episodes = trace.priority_episodes_by_mk.get(task_mk)
        if not episodes:
            return
        row_dim = bounds.height() if horiz else bounds.width()
        band_thick = max(3, int(row_dim * 0.30))
        offset = bounds.x() if horiz else bounds.y()
        bands = _priority_boost_bands_for_viewport(
            episodes, horiz, time_min, px_per_ns, offset, vp_ns_lo, vp_ns_hi)
        if not bands:
            return
        if horiz:
            bar_y = bounds.y() + bounds.height() - band_thick
            bar_h = band_thick
            bar_x = 0.0
            bar_w = 0.0
        else:
            bar_x = bounds.x() + bounds.width() - band_thick
            bar_w = band_thick
            bar_y = 0.0
            bar_h = 0.0
        item = _PriorityBoostBandsItem(
            bounds, bands, horiz, bar_y, bar_h, bar_x, bar_w,
            dark_ui=self._is_dark_ui)
        item.setZValue(3)
        self.addItem(item)

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

    def _add_interval_horizontal_rows(
        self,
        trace,
        interval_rows: list,
        y_cursor: float,
        lw: float,
        timeline_w: float,
        font: QFont,
        fm: QFontMetrics,
        time_min: int,
        px_per_ns: float,
        vp_ns_lo: int,
        vp_ns_hi: int,
        stripe_rows: Optional[list] = None,
    ) -> float:
        """Paint interval rows starting at y_cursor; return y after the last row."""
        _sti_bg = QBrush(self._c_sti_bg)
        for interval_id in interval_rows:
            row_h = self._row_height
            y_top = y_cursor
            y_ctr = y_top + row_h / 2
            # Always paint an opaque row background (not only via stripe_rows).
            # Core-view builders call this without stripe_rows; without a fill the
            # row is transparent and shows as white on light page backgrounds
            # (e.g. GitHub README light mode).
            _bg = self.addRect(
                QRectF(lw, y_top, timeline_w, row_h),
                QPen(Qt.PenStyle.NoPen), _sti_bg)
            _bg.setZValue(0)
            self._track_timeline_bg(_bg)
            if stripe_rows is not None:
                stripe_rows.append((y_top, row_h, self._row_gap, _sti_bg, None))
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
            _lbl = fm.elidedText(f"Interval {interval_id}", Qt.TextElideMode.ElideRight, max(0, lw - 18 - 4))
            lbl = self.addSimpleText(_lbl, font)
            lbl.setBrush(QBrush(self._c_sti_lbl))
            lbl.setPos(18, y_ctr - fm.height() / 2)
            lbl.setZValue(37)
            self._frozen_items.append((lbl, 18))
            pen = QPen(color.darker(145), 1.25)
            insts, _pre_culled = _interval_instances_for_draw(trace, interval_id)
            _interval_bars = _interval_bars_for_viewport(
                insts, time_min, px_per_ns, lw, vp_ns_lo, vp_ns_hi,
                instances_nested_culled=_pre_culled)
            _interval_ticks = _interval_marker_ticks_for_viewport(
                trace, interval_id, time_min, px_per_ns, lw, vp_ns_lo, vp_ns_hi)
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
                    time_min, px_per_ns, lw,
                    highlight_times=_hi_times, dark_ui=self._is_dark_ui)
                _bar_item.setZValue(2)
                self.addItem(_bar_item)
            y_cursor += row_h + self._row_gap
        return y_cursor

    def _add_interval_vertical_columns(
        self,
        trace,
        interval_rows: list,
        x_cursor: float,
        col_w: float,
        label_row_h: float,
        timeline_h: float,
        font: QFont,
        time_min: int,
        px_per_ns: float,
        vp_ns_lo: int,
        vp_ns_hi: int,
    ) -> float:
        """Paint interval columns starting at x_cursor; return x after the last column."""
        for interval_id in interval_rows:
            x_left = x_cursor
            x_ctr = x_left + col_w / 2
            self.addRect(QRectF(x_left, label_row_h, col_w, timeline_h),
                         QPen(Qt.PenStyle.NoPen), QBrush(self._c_sti_bg)).setZValue(0)
            lbl_bg = _StiLabelItem(QRectF(x_left, 0, col_w, label_row_h),
                                   f"interval:{interval_id}", self, expandable=False)
            lbl_bg.setZValue(36)
            self.addItem(lbl_bg)
            self._frozen_top_items.append((lbl_bg, 0))
            color = QColor(_interval_color(interval_id))
            stripe = self.addRect(
                QRectF(x_left + 3, label_row_h - 4, col_w - 6, 3),
                QPen(Qt.PenStyle.NoPen), QBrush(color))
            stripe.setZValue(38)
            self._frozen_top_items.append((stripe, stripe.pos().y()))
            _lbl_avail = max(0, label_row_h - 14)
            _lbl_txt = QFontMetrics(font).elidedText(
                f"Interval {interval_id}", Qt.TextElideMode.ElideRight, _lbl_avail)
            lbl = _make_rotated_label(self, _lbl_txt, font, color,
                                      x_ctr, label_row_h - LABEL_BOTTOM_MARGIN, 37)
            self._frozen_top_items.append((lbl, lbl.pos().y()))
            pen = QPen(color.darker(145), 1.25)
            insts, _pre_culled = _interval_instances_for_draw(trace, interval_id)
            _interval_bars = _interval_bars_for_viewport_vertical(
                insts, time_min, px_per_ns, label_row_h, vp_ns_lo, vp_ns_hi,
                instances_nested_culled=_pre_culled)
            _interval_ticks = _interval_marker_ticks_for_viewport_vertical(
                trace, interval_id, time_min, px_per_ns, label_row_h, vp_ns_lo, vp_ns_hi)
            _hi_times = None
            _hi = self._highlighted_interval
            if _hi is not None and str(_hi.id) == str(interval_id):
                _mark = self._highlighted_interval_mark_ns or _hi.stop_ns
                _hi_times = sorted({_hi.start_ns, _hi.stop_ns, _mark})
            if _interval_bars or _interval_ticks or _hi_times:
                _bar_x = x_left + 1
                _bar_w = col_w - 2
                _bar_item = _IntervalRowBarsItem(
                    QRectF(_bar_x, label_row_h, _bar_w, timeline_h),
                    _interval_bars, _interval_ticks, 0.0, 0.0, color, pen,
                    time_min, px_per_ns, label_row_h,
                    highlight_times=_hi_times, dark_ui=self._is_dark_ui,
                    vertical=True, bar_x=_bar_x, bar_w=_bar_w,
                    time_axis_offset=label_row_h)
                _bar_item.setZValue(2)
                self.addItem(_bar_item)
            x_cursor += col_w
        return x_cursor

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
        timeline_w = self._scene_timeline_span_px()
        _sti_total_h = sum(
            (self._sti_waveform_h_val if c in self._sti_expanded else self._sti_row_h_val) + self._row_gap
            for c in sti_rows)
        _sti_total_h += n_interval * (self._row_height + self._row_gap)
        _row_stride = self._row_height + self._row_gap
        content_h = RULER_HEIGHT + n_task * _row_stride + _sti_total_h
        self._orth_content_px = float(content_h)
        total_h = self._finalize_orth_size(content_h)
        total_w = self._label_width + timeline_w
        self.setSceneRect(0, 0, total_w, total_h)

        # --- Background & ruler ------------------------------------------
        _ruler_bg = self.addRect(QRectF(0, 0, total_w, RULER_HEIGHT),
                               QPen(Qt.PenStyle.NoPen), QBrush(self._c_ruler_bg))
        _ruler_bg.setZValue(10)   # above task rows (z=0-2) when frozen at top
        self._frozen_top_items.append((_ruler_bg, 0))
        _lbg = self.addRect(QRectF(0, 0, self._label_width, total_h),
                           QPen(Qt.PenStyle.NoPen), QBrush(self._c_label_bg))
        _lbg.setZValue(35)   # must be above cursor lines (z=30-32)
        self._frozen_items.append((_lbg, 0))

        # Grid-only ruler: grid lines stay at absolute scene positions (not frozen).
        _ruler_grid = _RulerItem(trace, self._timescale_per_px, total_w, total_h,
                                   font, trace.time_scale, self._show_grid,
                                   horiz=True, axis_offset=self._label_width,
                                   draw_header=False,
                                   scene_origin_ns=self._scene_origin_ns)
        _ruler_grid.setZValue(0.5)
        self.addItem(_ruler_grid)
        self._ruler_grid_item = _ruler_grid
        # Header-only ruler: tick marks + labels, frozen to the top edge.
        _ruler_hdr = _RulerItem(trace, self._timescale_per_px, total_w, total_h,
                                 font, trace.time_scale, show_grid=False,
                                 horiz=True, axis_offset=self._label_width,
                                 draw_grid=False,
                                 scene_origin_ns=self._scene_origin_ns)
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
            disp      = _task_display_name(raw) + _task_priority_label_suffix(trace, task)
            row_color = _task_color(raw)
            self._task_row_rects[task] = [(QRectF(lw, y_top, timeline_w, self._row_height), row_color)]

            _stripe_rows.append((y_top, self._row_height, self._row_gap,
                                 _bg_even if row_idx % 2 == 0 else _bg_odd, _sep_pen))
            if is_hl:
                hl_bg = QColor(row_color.red(), row_color.green(), row_color.blue(), 35)
                hl_border = QPen(row_color.lighter(160), 1.0)
                _hl_rect = self.addRect(QRectF(lw, y_top, timeline_w, self._row_height),
                                        hl_border, QBrush(hl_bg))
                _hl_rect.setZValue(0.9)
                self._track_timeline_bg(_hl_rect)

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
            _lbl_elided  = _lbl_fm.elidedText(disp, Qt.TextElideMode.ElideRight, _lbl_avail_w)
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
                _seg_br     = self._dim_brush_if_follow(
                    _blended_brush(seg.task, seg.core), task)
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
                xs=xs, time_min=vp.time_min, timescale_per_px=self._timescale_per_px)
            batch.setZValue(1)
            self.addItem(batch)

            self._add_priority_boost_bands(
                trace, task,
                QRectF(lw, y_top, timeline_w, self._row_height),
                True, _time_min, _px_per_ns, _vp_ns_lo, _vp_ns_hi)

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
                _ltxt = fm.elidedText(f"{_ind} {channel}", Qt.TextElideMode.ElideRight, max(0, lw - 4 - 4))
            else:
                _ltxt = fm.elidedText(channel, Qt.TextElideMode.ElideRight, max(0, lw - 4 - 4))
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
                    time_min=vp.time_min)
                _sti_item.setZValue(2)
                self.addItem(_sti_item)
            _sti_y += row_h + self._row_gap

        _sti_y = self._add_interval_horizontal_rows(
            trace, interval_rows, _sti_y, lw, timeline_w, font, fm,
            _time_min, _px_per_ns, _vp_ns_lo, _vp_ns_hi, _stripe_rows)

        if _stripe_rows:
            _stripes = _RowStripesItem(
                QRectF(0, RULER_HEIGHT, total_w, total_h - RULER_HEIGHT),
                _stripe_rows, lw, total_w)
            _stripes.setZValue(0)
            self.addItem(_stripes)
            self._row_stripe_item = _stripes

        self._add_orth_filler_horizontal(
            content_h, total_h, total_w, lw, n_task + n_sti + n_interval)

        # --- Frozen label column header ----------------------------------
        # Drawn last so it sits on top of all other frozen items (z=38-39).
        _has_tick_h = bool(trace.seg_map_by_merge_key.get(_task_merge_key("TICK"), []))
        corner = self.addRect(QRectF(0, 0, lw, RULER_HEIGHT),
                              QPen(Qt.PenStyle.NoPen), QBrush(self._c_corner_bg))
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
        self._add_frozen_label_grip(lw, total_h)

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
        interval_cols = trace.interval_ids if self._show_sti else []
        n_task = len(task_cols)
        n_sti  = len(sti_cols)
        n_interval = len(interval_cols)
        total_cols = n_task + n_sti + n_interval
        if total_cols == 0:
            return

        col_w       = max(self._row_height + self._row_gap, 26)
        label_row_h = self._label_width
        time_span   = trace.time_max - trace.time_min
        timeline_h  = self._scene_timeline_span_px()
        # STI columns may be wider when expanded
        total_sti_w = sum(
            (self._sti_waveform_h_val
             if (_is_tag_sti_channel(c) and c in self._sti_expanded)
             else col_w)
            for c in sti_cols
        )
        total_sti_w += n_interval * col_w
        content_w = RULER_WIDTH + n_task * col_w + total_sti_w
        self._orth_content_px = float(content_w)
        total_w = self._finalize_orth_size(content_w)
        total_h = label_row_h + timeline_h
        self.setSceneRect(0, 0, total_w, total_h)

        # --- Ruler column (left side): frozen to left edge on X scroll ------
        _ruler_col_bg = self.addRect(QRectF(0, 0, RULER_WIDTH, total_h),
                                     QPen(Qt.PenStyle.NoPen), QBrush(self._c_ruler_bg))
        _ruler_col_bg.setZValue(35)  # above cursor lines (z=30-32)
        self._frozen_items.append((_ruler_col_bg, 0))

        # --- Label row (top): frozen to top edge on Y scroll ---------------
        _label_row_bg = self.addRect(QRectF(0, 0, total_w, label_row_h),
                                     QPen(Qt.PenStyle.NoPen), QBrush(self._c_label_bg))
        _label_row_bg.setZValue(35)  # above cursor lines (z=30-32), same as ruler column
        self._frozen_top_items.append((_label_row_bg, 0))

        # Grid-only ruler: horizontal lines at absolute Y positions (not frozen).
        _ruler_grid = _RulerItem(trace, self._timescale_per_px, total_w, total_h,
                                   font, trace.time_scale, self._show_grid,
                                   horiz=False, axis_offset=label_row_h,
                                   draw_header=False,
                                   scene_origin_ns=self._scene_origin_ns)
        _ruler_grid.setZValue(0.5)
        self.addItem(_ruler_grid)
        # Header-only ruler: tick marks + labels, frozen to left edge.
        _ruler_hdr = _RulerItem(trace, self._timescale_per_px, total_w, total_h,
                                  font, trace.time_scale, show_grid=False,
                                  horiz=False, axis_offset=label_row_h,
                                  draw_grid=False,
                                 scene_origin_ns=self._scene_origin_ns)
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
            disp      = _task_display_name(raw) + _task_priority_label_suffix(trace, task)
            col_color = _task_color(raw)
            self._task_row_rects[task] = [(QRectF(x_left, label_row_h, col_w, timeline_h), col_color)]

            self.addRect(QRectF(x_left, label_row_h, col_w, timeline_h),
                         QPen(Qt.PenStyle.NoPen),
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
            _lbl_disp_v  = _lbl_fm_v.elidedText(disp, Qt.TextElideMode.ElideRight, _lbl_avail_v)
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
                _seg_br     = self._dim_brush_if_follow(
                    _blended_brush(seg.task, seg.core), task)
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
                xs=xs, time_min=vp.time_min, timescale_per_px=self._timescale_per_px,
                time_decimals=self._time_decimals)
            batch.setZValue(1)
            self.addItem(batch)

            self._add_priority_boost_bands(
                trace, task,
                QRectF(x_left, label_row_h, col_w, timeline_h),
                False, _time_min, _px_per_ns, _vp_ns_lo, _vp_ns_hi)

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
                         QPen(Qt.PenStyle.NoPen), QBrush(self._c_sti_bg)).setZValue(0)

            # Clickable column header (expands/collapses waveform)
            lbl_bg = _StiLabelItem(QRectF(x_left, 0, cw_sti, label_row_h),
                                   channel, self, expandable=expandable)
            lbl_bg.setZValue(36)
            self.addItem(lbl_bg)
            self._frozen_top_items.append((lbl_bg, 0))

            # Rotated label with optional expand indicator
            _ind_txt  = ("▼ " if is_exp else "▶ ") if expandable else ""
            _lbl_avail_v = max(0, label_row_h - 14)
            _lbl_txt  = fm.elidedText(_ind_txt + channel, Qt.TextElideMode.ElideRight, _lbl_avail_v)
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
                    time_min=vp.time_min)
                _sti_item_v.setZValue(2)
                self.addItem(_sti_item_v)

            _sti_x_acc += cw_sti

        _sti_x_acc = self._add_interval_vertical_columns(
            trace, interval_cols, _sti_x_acc, col_w, label_row_h, timeline_h,
            font, _time_min, _px_per_ns, _vp_ns_lo, _vp_ns_hi)

        self._add_orth_filler_vertical(
            _sti_x_acc, total_w, total_h, label_row_h, n_task + n_sti + n_interval)

        # --- Corner: ruler-column x label-row intersection ---------------
        _vt_corner_rect = self.addRect(QRectF(0, 0, RULER_WIDTH, label_row_h),
                                       QPen(Qt.PenStyle.NoPen), QBrush(self._c_corner_bg))
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
        interval_rows        = trace.interval_ids if self._show_sti else []

        core_names, core_tasks = self._filtered_core_view_tasks()
        _skip_core_summary_segs = self._core_view_task_filter_active()

        # TICK is a global event - shown as a sticky first row above all cores.
        _has_tick = (bool(trace.seg_map_by_merge_key.get(_task_merge_key("TICK"), []))
                     or bool(trace.tick_sti_times))

        def _row_count(c: str) -> int:
            return 1 + (len(core_tasks[c]) if self._core_is_expanded(c) else 0)

        total_rows = sum(_row_count(c) for c in core_names) + len(sti_rows) + len(interval_rows)
        if total_rows == 0:
            return

        time_span  = trace.time_max - trace.time_min
        timeline_w = self._scene_timeline_span_px()
        _n_non_sti = sum(_row_count(c) for c in core_names)
        _sti_total_h = sum(
            (self._sti_waveform_h_val if c in self._sti_expanded else self._sti_row_h_val) + self._row_gap
            for c in sti_rows)
        _sti_total_h += len(interval_rows) * (self._row_height + self._row_gap)
        _row_stride = self._row_height + self._row_gap
        content_h = RULER_HEIGHT + _n_non_sti * _row_stride + _sti_total_h
        self._orth_content_px = float(content_h)
        total_h = self._finalize_orth_size(content_h)
        total_w = self._label_width + timeline_w
        self.setSceneRect(0, 0, total_w, total_h)

        # --- Background & ruler ------------------------------------------
        _ruler_bg = self.addRect(QRectF(0, 0, total_w, RULER_HEIGHT),
                               QPen(Qt.PenStyle.NoPen), QBrush(self._c_ruler_bg))
        _ruler_bg.setZValue(10)
        self._frozen_top_items.append((_ruler_bg, 0))
        _lbg = self.addRect(QRectF(0, 0, self._label_width, total_h),
                           QPen(Qt.PenStyle.NoPen), QBrush(self._c_label_bg))
        _lbg.setZValue(35)   # must be above cursor lines (z=30-32)
        self._frozen_items.append((_lbg, 0))

        # Grid-only ruler (not frozen - grid lines stay at their scene positions).
        _ruler_grid = _RulerItem(trace, self._timescale_per_px, total_w, total_h,
                                   font, trace.time_scale, self._show_grid,
                                   horiz=True, axis_offset=self._label_width,
                                   draw_header=False,
                                   scene_origin_ns=self._scene_origin_ns)
        _ruler_grid.setZValue(0.5)
        self.addItem(_ruler_grid)
        self._ruler_grid_item = _ruler_grid
        # Header-only ruler (frozen by Y - always visible at viewport top).
        _ruler_hdr = _RulerItem(trace, self._timescale_per_px, total_w, total_h,
                                 font, trace.time_scale, show_grid=False,
                                 horiz=True, axis_offset=self._label_width,
                                 draw_grid=False,
                                 scene_origin_ns=self._scene_origin_ns)
        _ruler_hdr.setZValue(11)
        self.addItem(_ruler_hdr)
        self._frozen_top_items.append((_ruler_hdr, 0))

        _time_min  = self._scene_origin_ns
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
            expanded = self._core_is_expanded(core)
            tasks    = core_tasks[core]
            segs     = core_segs[core]
            dot_c    = QColor(_core_color(core))

            y_top = RULER_HEIGHT + row_idx * (self._row_height + self._row_gap)
            y_ctr = y_top + self._row_height / 2
            row_idx += 1   # advance immediately, independent of viewport cull

            _core_in_vp = not (y_top + self._row_height < self._vp_scene_orth_lo
                               or y_top > self._vp_scene_orth_hi)
            if _core_in_vp:
                _core_bg = self.addRect(QRectF(lw, y_top, timeline_w, self._row_height),
                                        QPen(Qt.PenStyle.NoPen), QBrush(self._c_core_sum_bg))
                _core_bg.setZValue(0)
                self._track_timeline_bg(_core_bg)
                _sep = self.addLine(0, y_top + self._row_height + self._row_gap - 1,
                                    total_w, y_top + self._row_height + self._row_gap - 1,
                                    QPen(self._c_core_sep, 0.8))
                _sep.setZValue(0.5)
                self._track_timeline_sep_line(_sep)

                hdr_item = _CoreHeaderItem(
                    QRectF(0, y_top, lw, self._row_height), core, self)
                hdr_item.setBrush(QBrush(self._c_core_hdr_bg))
                hdr_item.setPen(QPen(Qt.PenStyle.NoPen))
                hdr_item.setZValue(36)
                self.addItem(hdr_item)
                self._frozen_items.append((hdr_item, 0))

                arrow   = "▼" if expanded else "▶"
                arrow_w = fm.horizontalAdvance("▼")
                arr_txt = self.addSimpleText(arrow, font)
                arr_txt.setBrush(QBrush(self._c_core_arrow))
                arr_txt.setPos(3, y_ctr - fm.height() / 2)
                arr_txt.setZValue(37)
                arr_txt.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                arr_txt.setAcceptHoverEvents(False)
                self._frozen_items.append((arr_txt, 3))

                dot_item = QGraphicsEllipseItem(0, -5, 10, 10)
                dot_item.setPen(QPen(Qt.PenStyle.NoPen))
                dot_item.setBrush(QBrush(dot_c))
                dot_item.setPos(arrow_w + 6, y_ctr)
                dot_item.setZValue(37)
                dot_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                dot_item.setAcceptHoverEvents(False)
                self.addItem(dot_item)
                self._frozen_items.append((dot_item, arrow_w + 6))

                _util_w         = fm.horizontalAdvance("100%") + 8
                _core_lbl_avail = max(0, lw - (arrow_w + 20) - 4 - _util_w)
                lbl_item = self.addSimpleText(
                    fm.elidedText(core, Qt.TextElideMode.ElideRight, _core_lbl_avail), font)
                lbl_item.setBrush(QBrush(self._c_core_lbl))
                lbl_item.setPos(arrow_w + 20, y_ctr - fm.height() / 2)
                lbl_item.setZValue(37)
                lbl_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                lbl_item.setAcceptHoverEvents(False)
                self._frozen_items.append((lbl_item, arrow_w + 20))

                # --- Core utilisation % (IDLE excluded) ---
                _util_pct  = _core_util_pct_for(trace, core)
                _util_item = self.addSimpleText(f"{_util_pct:.0f}%", font_sm)
                _util_item.setBrush(QBrush(QColor("#77BB77")))
                _util_item.setPos(lw - _util_w + 4, y_ctr - fm.height() / 2)
                _util_item.setZValue(37)
                _util_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
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
                        xs=xs, time_min=vp.time_min, time_decimals=self._time_decimals)
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
                _sub_bg_rect = self.addRect(QRectF(lw, y_top2, timeline_w, self._row_height),
                                            QPen(Qt.PenStyle.NoPen), QBrush(sub_bg))
                _sub_bg_rect.setZValue(0)
                self._track_timeline_bg(_sub_bg_rect)
                _row_color = _task_color(task_name)
                self._task_row_rects.setdefault(_tmk, []).append(
                    (QRectF(lw, y_top2, timeline_w, self._row_height), _row_color))
                if is_hl:
                    hl_bg = QColor(_row_color.red(), _row_color.green(), _row_color.blue(), 35)
                    _sub_hl = self.addRect(QRectF(lw, y_top2, timeline_w, self._row_height),
                                           QPen(_row_color.lighter(160), 1.0), QBrush(hl_bg))
                    _sub_hl.setZValue(0.9)
                    self._track_timeline_bg(_sub_hl)
                _sub_sep = self.addLine(0, y_top2 + self._row_height + self._row_gap - 1,
                                        total_w, y_top2 + self._row_height + self._row_gap - 1,
                                        QPen(self._c_core_sub_sep, 0.5))
                _sub_sep.setZValue(0.5)
                self._track_timeline_sep_line(_sub_sep)

                stripe = self.addRect(QRectF(26, y_top2 + 3, 3, self._row_height - 6),
                                      QPen(Qt.PenStyle.NoPen), QBrush(_row_color))
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
                    disp, Qt.TextElideMode.ElideRight, _sub_avail)
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
                    xs=xs, time_min=vp.time_min, timescale_per_px=self._timescale_per_px,
                    time_decimals=self._time_decimals)
                batch.setZValue(1)
                self.addItem(batch)

                self._add_priority_boost_bands(
                    trace, _tmk,
                    QRectF(lw, y_top2, timeline_w, self._row_height),
                    True, _time_min, _px_per_ns, _vp_ns_lo, _vp_ns_hi)

        # --- STI rows ---------------------------------------------------
        _sti_y = RULER_HEIGHT + row_idx * (self._row_height + self._row_gap)
        for channel in sti_rows:
            is_exp     = channel in self._sti_expanded
            expandable = _is_tag_sti_channel(channel)
            row_h  = self._sti_waveform_h_val if is_exp else self._sti_row_h_val
            y_top  = _sti_y
            y_ctr  = y_top + row_h / 2
            _sti_bg_rect = self.addRect(QRectF(lw, y_top, timeline_w, row_h),
                                        QPen(Qt.PenStyle.NoPen), QBrush(self._c_sti_bg))
            _sti_bg_rect.setZValue(0)
            self._track_timeline_bg(_sti_bg_rect)
            if expandable:
                _ind  = "▼" if is_exp else "▶"
                _ltxt = fm.elidedText(f"{_ind} {channel}", Qt.TextElideMode.ElideRight, max(0, lw - 4 - 4))
            else:
                _ltxt = fm.elidedText(channel, Qt.TextElideMode.ElideRight, max(0, lw - 4 - 4))
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
                    time_min=vp.time_min)
                _sti_item_ch.setZValue(2)
                self.addItem(_sti_item_ch)
            _sti_y += row_h + self._row_gap

        self._add_interval_horizontal_rows(
            trace, interval_rows, _sti_y, lw, timeline_w, font, fm,
            _time_min, _px_per_ns, _vp_ns_lo, _vp_ns_hi)

        corner = self.addRect(QRectF(0, 0, lw, RULER_HEIGHT),
                              QPen(Qt.PenStyle.NoPen), QBrush(self._c_corner_bg))
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
        self._add_orth_filler_horizontal(
            content_h, total_h, total_w, lw, total_rows)
        self._add_frozen_label_grip(lw, total_h)

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
        interval_cols        = trace.interval_ids if self._show_sti else []

        core_names, core_tasks = self._filtered_core_view_tasks()
        _skip_core_summary_segs = self._core_view_task_filter_active()

        # TICK is a global event - shown as a band in the ruler column.
        _has_tick = (bool(trace.seg_map_by_merge_key.get(_task_merge_key("TICK"), []))
                     or bool(trace.tick_sti_times))

        def _col_count(c: str) -> int:
            return 1 + (len(core_tasks[c]) if self._core_is_expanded(c) else 0)

        _core_col_count = sum(_col_count(c) for c in core_names)
        total_cols = _core_col_count + len(sti_cols) + len(interval_cols)
        if total_cols == 0:
            return

        col_w       = max(self._row_height + self._row_gap, 26)
        label_row_h = self._label_width
        time_span   = trace.time_max - trace.time_min
        timeline_h  = self._scene_timeline_span_px()
        # STI columns may be wider when expanded
        total_sti_w = sum(
            (self._sti_waveform_h_val
             if (_is_tag_sti_channel(c) and c in self._sti_expanded)
             else col_w)
            for c in sti_cols
        )
        total_sti_w += len(interval_cols) * col_w
        content_w = RULER_WIDTH + _core_col_count * col_w + total_sti_w
        self._orth_content_px = float(content_w)
        total_w = self._finalize_orth_size(content_w)
        total_h = label_row_h + timeline_h
        self.setSceneRect(0, 0, total_w, total_h)

        # --- Ruler column (left side): frozen to left edge on X scroll ------
        _ruler_col_bg_c = self.addRect(QRectF(0, 0, RULER_WIDTH, total_h),
                                       QPen(Qt.PenStyle.NoPen), QBrush(self._c_ruler_bg))
        _ruler_col_bg_c.setZValue(35)
        self._frozen_items.append((_ruler_col_bg_c, 0))

        # --- Label row (top): frozen to top edge on Y scroll ---------------
        _label_row_bg_c = self.addRect(QRectF(0, 0, total_w, label_row_h),
                                       QPen(Qt.PenStyle.NoPen), QBrush(self._c_label_bg))
        _label_row_bg_c.setZValue(10)
        self._frozen_top_items.append((_label_row_bg_c, 0))

        # Grid-only ruler: horizontal grid lines at absolute Y positions.
        _ruler_grid_c = _RulerItem(trace, self._timescale_per_px, total_w, total_h,
                                     font, trace.time_scale, self._show_grid,
                                     horiz=False, axis_offset=label_row_h,
                                     draw_header=False,
                                   scene_origin_ns=self._scene_origin_ns)
        _ruler_grid_c.setZValue(0.5)
        self.addItem(_ruler_grid_c)
        # Header-only ruler: tick marks + labels, frozen to left edge.
        _ruler_hdr_c = _RulerItem(trace, self._timescale_per_px, total_w, total_h,
                                    font, trace.time_scale, show_grid=False,
                                    horiz=False, axis_offset=label_row_h,
                                    draw_grid=False,
                                 scene_origin_ns=self._scene_origin_ns)
        _ruler_hdr_c.setZValue(36)
        self.addItem(_ruler_hdr_c)
        self._frozen_items.append((_ruler_hdr_c, 0))

        _time_min  = self._scene_origin_ns
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
            expanded = self._core_is_expanded(core)
            tasks    = core_tasks[core]

            x_left = RULER_WIDTH + col_idx * col_w
            col_idx += 1   # advance immediately, independent of viewport cull

            _core_in_vp = not (x_left + col_w < self._vp_scene_orth_lo
                               or x_left > self._vp_scene_orth_hi)
            if _core_in_vp:
                self.addRect(QRectF(x_left, label_row_h, col_w, timeline_h),
                             QPen(Qt.PenStyle.NoPen), QBrush(self._c_core_sum_bg)).setZValue(0)

                # Clickable core column header (v/> expand toggle)
                hdr_item = _CoreHeaderItem(
                    QRectF(x_left, 0, col_w, label_row_h), core, self)
                hdr_item.setBrush(QBrush(self._c_core_hdr_bg))
                hdr_item.setPen(QPen(Qt.PenStyle.NoPen))
                hdr_item.setZValue(36)
                self.addItem(hdr_item)
                self._frozen_top_items.append((hdr_item, 0))

                # Arrow + core name (rotated -90 like task view labels)
                arrow     = "▼" if expanded else "▶"
                arr_label = arrow + " " + core
                _lbl_avail_c = max(0, label_row_h - 14)
                arr_label = QFontMetrics(font).elidedText(arr_label, Qt.TextElideMode.ElideRight, _lbl_avail_c)
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
                        xs=xs, time_min=vp.time_min, time_decimals=self._time_decimals)
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
                             QPen(Qt.PenStyle.NoPen), QBrush(sub_bg)).setZValue(0)

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
                    QPen(Qt.PenStyle.NoPen), QBrush(_row_color))
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
                    xs=xs, time_min=vp.time_min, timescale_per_px=self._timescale_per_px,
                    time_decimals=self._time_decimals)
                batch.setZValue(1)
                self.addItem(batch)

                self._add_priority_boost_bands(
                    trace, _tmk,
                    QRectF(x_left2, label_row_h, col_w, timeline_h),
                    False, _time_min, _px_per_ns, _vp_ns_lo, _vp_ns_hi)

        # --- STI columns ------------------------------------------------
        _sti_x_acc_vc = RULER_WIDTH + _core_col_count * col_w
        for channel in sti_cols:
            expandable = _is_tag_sti_channel(channel)
            is_exp     = expandable and channel in self._sti_expanded
            cw_sti_vc  = self._sti_waveform_h_val if is_exp else col_w
            x_left     = _sti_x_acc_vc
            x_ctr_vc   = x_left + cw_sti_vc / 2
            self.addRect(QRectF(x_left, label_row_h, cw_sti_vc, timeline_h),
                         QPen(Qt.PenStyle.NoPen), QBrush(self._c_sti_bg)).setZValue(0)

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
                _ind_txt_vc + channel, Qt.TextElideMode.ElideRight, _lbl_avail_vc)
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
                    time_min=vp.time_min)
                _sti_itm_vc.setZValue(2)
                self.addItem(_sti_itm_vc)

            col_idx += 1
            _sti_x_acc_vc += cw_sti_vc

        _sti_x_acc_vc = self._add_interval_vertical_columns(
            trace, interval_cols, _sti_x_acc_vc, col_w, label_row_h, timeline_h,
            font, _time_min, _px_per_ns, _vp_ns_lo, _vp_ns_hi)

        self._add_orth_filler_vertical(
            _sti_x_acc_vc, total_w, total_h, label_row_h, col_idx)

        # --- Corner: ruler-column x label-row intersection ---------------
        _vc_corner = self.addRect(QRectF(0, 0, RULER_WIDTH, label_row_h),
                                  QPen(Qt.PenStyle.NoPen), QBrush(self._c_corner_bg))
        _vc_corner.setZValue(40)
        self._frozen_items.append((_vc_corner, 0))
        self._frozen_top_items.append((_vc_corner, 0))

