"""BTF Viewer — graphics_items module (source). Do not edit btf_viewer.py; run make bundle."""
from __future__ import annotations

from ._imports import *  # noqa: F403,F401
from .config import *  # noqa: F403,F401
from .parser import *  # noqa: F403,F401
from .timeline_util import *  # noqa: F403,F401

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
                 draw_header: bool = True, draw_grid: bool = True,
                 scene_origin_ns: Optional[int] = None):
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
        self._grid_clip_x = axis_offset
        self._scene_origin_ns = (
            trace.time_min if scene_origin_ns is None else scene_origin_ns)
        fm = QFontMetrics(font)
        self._text_ascent = fm.ascent()
        # Tell Qt to supply the real exposed rect, not the full bounding rect
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption, True)
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)

    def boundingRect(self) -> QRectF:
        if not self._draw_grid:
            # Header-only variant: tight rect = just the ruler strip/column.
            if self._horiz:
                return QRectF(0, 0, self._total_w, RULER_HEIGHT)
            else:
                return QRectF(0, 0, RULER_WIDTH, self._total_h)
        return QRectF(0, 0, self._total_w, self._total_h)

    def set_grid_clip_x(self, clip_x: float) -> None:
        """Hide vertical grid lines left of *clip_x* (viewport splitter alignment)."""
        if abs(clip_x - self._grid_clip_x) < 0.5:
            return
        self._grid_clip_x = clip_x
        self.update()

    def paint(self, painter, option, widget=None) -> None:
        trace    = self._trace
        npp      = self._npp
        t_min    = trace.time_min
        t_max    = trace.time_max
        origin   = self._scene_origin_ns
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
            ns_lo    = origin + int(px_lo * npp) - step_ns
            ns_hi    = origin + int(px_hi * npp) + step_ns
            ns_lo    = max(t_min, ns_lo)
            ns_hi    = min(t_max + step_ns, ns_hi)
            # Grid anchored to t_min so the first tick is always at t_min ("0").
            first    = t_min + ((ns_lo - t_min) // step_ns) * step_ns
            t = first
            while t <= ns_hi:
                if t >= t_min:
                    x = off + (t - origin) / npp
                    if draw_grid_lines and x >= self._grid_clip_x - 0.5:
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
            ns_lo    = origin + int(py_lo * npp) - step_ns
            ns_hi    = origin + int(py_hi * npp) + step_ns
            ns_lo    = max(t_min, ns_lo)
            ns_hi    = min(t_max + step_ns, ns_hi)
            # Grid anchored to t_min so the first tick is always at t_min ("0").
            first    = t_min + ((ns_lo - t_min) // step_ns) * step_ns
            t = first
            while t <= ns_hi:
                if t >= t_min:
                    y = off + (t - origin) / npp
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

class _PriorityBoostBandsItem(QGraphicsItem):
    """Bottom (horizontal) or right-edge (vertical) stripes for priority boost episodes."""

    __slots__ = ('_bounds', '_bands', '_horiz', '_bar_y', '_bar_h', '_bar_x', '_bar_w', '_dark_ui')

    def __init__(
        self,
        bounding_rect: QRectF,
        bands: list,
        horiz: bool,
        bar_y: float,
        bar_h: float,
        bar_x: float,
        bar_w: float,
        dark_ui: bool = True,
    ) -> None:
        super().__init__()
        self._bounds = bounding_rect
        self._bands = bands
        self._horiz = horiz
        self._bar_y = bar_y
        self._bar_h = bar_h
        self._bar_x = bar_x
        self._bar_w = bar_w
        self._dark_ui = dark_ui
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption, True)

    def boundingRect(self) -> QRectF:
        return self._bounds

    def paint(self, painter, option, widget=None) -> None:
        if not self._bands:
            return
        exposed = option.exposedRect
        if self._horiz:
            exp_lo = exposed.left()
            exp_hi = exposed.right()
            for x, w, inv in self._bands:
                if x + w < exp_lo or x >= exp_hi:
                    continue
                cx = max(x, exp_lo)
                cx2 = min(x + w, exp_hi)
                cw = cx2 - cx
                if cw < 0.5:
                    continue
                base = QColor("#E74C3C" if inv else "#F39C12")
                fill = QColor(base)
                fill.setAlpha(184 if self._dark_ui else 133)
                painter.fillRect(QRectF(cx, self._bar_y, cw, self._bar_h), fill)
                if cw >= 4:
                    painter.setPen(QPen(base))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(QRectF(cx + 0.5, self._bar_y + 0.5, cw - 1, self._bar_h - 1))
        else:
            exp_lo = exposed.top()
            exp_hi = exposed.bottom()
            for y, h, inv in self._bands:
                if y + h < exp_lo or y >= exp_hi:
                    continue
                cy = max(y, exp_lo)
                cy2 = min(y + h, exp_hi)
                ch = cy2 - cy
                if ch < 0.5:
                    continue
                base = QColor("#E74C3C" if inv else "#F39C12")
                fill = QColor(base)
                fill.setAlpha(184 if self._dark_ui else 133)
                painter.fillRect(QRectF(self._bar_x, cy, self._bar_w, ch), fill)
                if ch >= 4:
                    painter.setPen(QPen(base))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(QRectF(self._bar_x + 0.5, cy + 0.5, self._bar_w - 1, ch - 1))

class _IntervalRowBarsItem(QGraphicsItem):
    """Paints all interval bars for one row in a single paint() pass.

    Replaces O(n_intervals) individual QGraphicsRectItems with one
    item per interval row, avoiding multi-second freezes in scene.clear() when
    zooming after many back-to-back intervals are visible.
    """

    __slots__ = ('_bounds', '_bars', '_ticks', '_bar_y', '_bar_h', '_color', '_outline_pen',
                 '_time_min', '_px_per_ns', '_label_width', '_highlight_times', '_dark_ui',
                 '_vertical', '_bar_x', '_bar_w', '_time_axis_offset')

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
        vertical: bool = False,
        bar_x: Optional[float] = None,
        bar_w: Optional[float] = None,
        time_axis_offset: Optional[float] = None,
    ) -> None:
        super().__init__()
        self._bounds = bounding_rect
        self._bars = bars
        self._ticks = ticks
        self._vertical = vertical
        self._bar_y = bar_y
        self._bar_h = bar_h
        self._bar_x = bar_x if bar_x is not None else 0.0
        self._bar_w = bar_w if bar_w is not None else bar_h
        self._color = color
        self._outline_pen = outline_pen
        self._time_min = time_min
        self._px_per_ns = px_per_ns
        self._label_width = label_width
        self._time_axis_offset = (time_axis_offset if time_axis_offset is not None
                                  else label_width)
        self._highlight_times = highlight_times
        self._dark_ui = dark_ui
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption, True)

    def boundingRect(self) -> QRectF:
        return self._bounds

    def paint(self, painter, option, widget=None) -> None:
        bars = self._bars
        ticks = self._ticks
        hi_times = self._highlight_times
        if not bars and not ticks and not hi_times:
            return
        exposed = option.exposedRect
        if self._vertical:
            exp_lo = exposed.top()
            exp_hi = exposed.bottom()
            x = self._bar_x
            w = self._bar_w
            pen = self._outline_pen
            if bars:
                lo, hi = 0, len(bars)
                while lo < hi:
                    mid = (lo + hi) >> 1
                    y, h, _s0, _s1 = bars[mid]
                    if y + h < exp_lo:
                        lo = mid + 1
                    else:
                        hi = mid
                painter.setBrush(self._color)
                for i in range(lo, len(bars)):
                    y, h, _start_ns, _stop_ns = bars[i]
                    if y >= exp_hi:
                        break
                    cy = max(y, exp_lo)
                    cy2 = min(y + h, exp_hi)
                    ch = cy2 - cy
                    if ch < _INTERVAL_MIN_PX:
                        continue
                    painter.setPen(pen if ch >= 3.0 else Qt.PenStyle.NoPen)
                    painter.drawRect(QRectF(x, cy, w, ch))
            _paint_interval_event_ticks_vertical(
                painter, ticks, x, w, self._color, exp_lo, exp_hi)
            if hi_times:
                _paint_interval_highlight_lines_vertical(
                    painter, hi_times, x, w, self._time_min, self._time_axis_offset,
                    self._px_per_ns, exp_lo, exp_hi, self._dark_ui)
            return

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
                painter.setPen(pen if cw >= 3.0 else Qt.PenStyle.NoPen)
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
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption, True)

    def boundingRect(self) -> QRectF:
        return self._bounding_rect

    def set_timeline_left(self, timeline_x: float) -> None:
        """Move the painted stripe region's left edge (viewport splitter sync)."""
        if abs(timeline_x - self._timeline_x) < 0.5:
            return
        self._timeline_x = timeline_x
        self.update()

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
        painter.setPen(Qt.PenStyle.NoPen)
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
                painter.setBrush(Qt.BrushStyle.NoBrush)
                last_pen = sep_pen
            painter.drawLine(QLineF(tx, sep_y, total_w, sep_y))

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
    time_decimals : int
        Decimal-digit precision used when formatting times in this segment's tooltip.
    """

    def __init__(self, bounding_rect: QRectF, seg_data: list, time_scale: str,
                 label_font=None, label_fm=None, label_text: str = "",
                 presorted: bool = False, xs: Optional[list] = None,
                 time_min: int = 0, timescale_per_px: float = 0.0,
                 trace: Optional["BtfTrace"] = None, time_decimals: int = 3):
        super().__init__()
        self._bounding_rect = bounding_rect
        self._seg_data      = seg_data      # [(QRectF, QBrush, QPen, seg|None)]
        self._time_scale    = time_scale
        self._time_min      = time_min
        self._timescale_per_px     = timescale_per_px
        self._trace         = trace
        self._time_decimals = time_decimals
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

    def _hit_seg_index(self, point: QPointF) -> Optional[int]:
        """Index into ``_seg_data`` for the bar under *point*, or None.

        ``boundingRect`` spans the whole row so paint/clipping stay cheap.
        Hover hit-testing must use the bars themselves; otherwise leaving a
        segment into the empty part of the same row never sends hoverLeave
        and the info popup stays up.
        """
        if not self._xs:
            return None
        br = self._bounding_rect
        if self._horiz:
            if point.y() < br.top() or point.y() > br.bottom():
                return None
            x = point.x()
        else:
            if point.x() < br.left() or point.x() > br.right():
                return None
            x = point.y()
        xs = self._xs
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
                    return idx
        return None

    def contains(self, point: QPointF) -> bool:
        return self._hit_seg_index(point) is not None

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
                painter.setPen(Qt.PenStyle.NoPen)
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
            painter.setPen(Qt.PenStyle.NoPen)
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
                                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                                         draw_txt)
                    else:
                        painter.drawText(scene_rect,
                                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
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
                        draw_txt = fm.elidedText(txt, Qt.TextElideMode.ElideRight, int(text_w) - 4)
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
                        draw_txt = fm.elidedText(txt, Qt.TextElideMode.ElideRight, int(text_h) - 4)
                        if draw_txt == "\u2026":
                            continue
                    painter.save()
                    painter.translate(vis_rect.x() + vis_rect.width() / 2,
                                      text_y - _base_y + text_h / 2)
                    painter.rotate(90)
                    painter.drawText(
                        QRectF(-text_h / 2, -vis_rect.width() / 2, text_h, vis_rect.width()),
                        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                        draw_txt,
                    )
                    painter.restore()
                    any_label_drawn = True
                painter.restore()
        painter.restore()

    def hoverMoveEvent(self, event) -> None:
        idx = self._hit_seg_index(event.pos())
        if idx is None:
            _get_popup().hide()
            super().hoverMoveEvent(event)
            return
        seg = self._seg_data[idx][3]
        dur = seg.end - seg.start
        tip = (f"<b>{seg.task}</b><br>"
               f"Core: {seg.core}<br>"
               f"Start: {_format_time(seg.start, self._time_scale, decimals=self._time_decimals)}<br>"
               f"End:   {_format_time(seg.end,   self._time_scale, decimals=self._time_decimals)}<br>"
               f"Duration: {_format_time(dur, self._time_scale, decimals=self._time_decimals)}")
        tr = self._trace
        if tr is not None:
            prev, nxt, seg_idx, total = _seg_core_neighbors(tr, seg)
            if seg_idx > 0:
                tip += f"<br>Slice: #{seg_idx}/{total} on {seg.core}"
            if prev is not None:
                _, _, pnm = _parse_task_name(prev.task)
                tip += (f"<br>← Prev on core: {_task_display_name(prev.task)} "
                        f"({_format_time(prev.end, self._time_scale, decimals=self._time_decimals)})")
            if nxt is not None:
                tip += (f"<br>→ Next on core: {_task_display_name(nxt.task)} "
                        f"({_format_time(nxt.start, self._time_scale, decimals=self._time_decimals)})")
            if prev is not None:
                gap = seg.start - prev.end
                if gap > 0:
                    tip += f"<br>Gap before: {_format_time(gap, self._time_scale, decimals=self._time_decimals)}"
        _get_popup().show_at(event.screenPos(), tip, host=event.widget())
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
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)

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
                _get_popup().show_at(event.screenPos(), tip, host=event.widget())
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
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self._update_brush()

    def _update_brush(self) -> None:
        if self._tl_scene._locked_task == self._task_name:
            self.setBrush(self._HIGHLIGHT_BRUSH)
        else:
            self.setBrush(QBrush(Qt.GlobalColor.transparent))

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
            _get_popup().show_at(event.screenPos(), self._tooltip_text, host=event.widget())
        super().hoverEnterEvent(event)
        if self._tl_scene._hover_highlight:
            # Defer rebuild so it never runs while this item's event handler is active
            task = self._task_name
            scene = self._tl_scene
            QTimer.singleShot(0, lambda: scene.set_highlighted_task(task, locked=False))

    def hoverMoveEvent(self, event):
        if self._tooltip_text:
            _get_popup().show_at(event.screenPos(), self._tooltip_text, host=event.widget())
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

    def __init__(self, rect: QRectF, core_name: str, tl_scene):
        super().__init__(rect)
        self._core_name = core_name
        self._tl_scene  = tl_scene
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _normal_brush(self) -> QBrush:
        return QBrush(self._tl_scene._c_core_hdr_bg)

    def _hover_brush(self) -> QBrush:
        sc = self._tl_scene
        if sc._is_dark_ui:
            return QBrush(QColor(100, 100, 220, 55))
        h = sc._c_core_hdr_bg.lighter(108)
        return QBrush(QColor(h.red(), h.green(), h.blue(), 160))

    def mousePressEvent(self, event):
        self._tl_scene.toggle_core(self._core_name)
        event.accept()

    def hoverEnterEvent(self, event):
        self.setBrush(self._hover_brush())
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(self._normal_brush())
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
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptHoverEvents(True)
        if expandable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(Qt.GlobalColor.transparent))

    def mousePressEvent(self, event):
        if self._expandable:
            self._tl_scene.toggle_sti_channel(self._channel)
        event.accept()

    def hoverEnterEvent(self, event):
        self.setBrush(self._HOVER_BRUSH)
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(Qt.GlobalColor.transparent))
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
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)
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
        _axis_pen = QPen(QColor(255, 255, 255, 28), 0.5, Qt.PenStyle.DashLine)
        painter.setPen(_axis_pen)
        painter.drawLine(QLineF(rect.left(), chart_top, rect.right(), chart_top))
        painter.drawLine(QLineF(rect.left(), chart_bot,  rect.right(), chart_bot))

        # Polyline: step-hold or direct point-to-point
        line_color = QColor("#5BC8FF")
        painter.setPen(QPen(line_color, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)

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
            _get_popup().show_at(event.screenPos(), tip, host=event.widget())
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
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)

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
        _axis_pen = QPen(QColor(255, 255, 255, 28), 0.5, Qt.PenStyle.DashLine)
        painter.setPen(_axis_pen)
        painter.drawLine(QLineF(chart_left, rect.top(),    chart_left, rect.bottom()))
        painter.drawLine(QLineF(chart_right, rect.top(), chart_right, rect.bottom()))

        # Polyline
        line_color = QColor("#5BC8FF")
        painter.setPen(QPen(line_color, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)

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
