"""BTF Viewer — view module (source). Do not edit btf_viewer.py; run make bundle."""
from __future__ import annotations

from ._imports import *  # noqa: F403,F401
from .config import *  # noqa: F403,F401
from .parser import *  # noqa: F403,F401
from .timeline_util import *  # noqa: F403,F401
from .graphics_items import *  # noqa: F403,F401
from .scene import *  # noqa: F403,F401

# ===========================================================================
# Navigator Popup
# ===========================================================================

class _NavigatorPopup(QWidget):
    """260x130 thumbnail that shows the full trace with a viewport indicator.

    Painted entirely in Python and overlaid on the TimelineView viewport at
    the bottom-right corner.  Click outside the indicator jumps the main view;
    drag the indicator to pan time / scroll position.
    Appearance changes are animated with a 80 ms fade-in / 350 ms fade-out.
    """

    W: int = 260
    H: int = 130
    MARGIN: int = 8   # gap from the viewport edge (px)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pix: Optional[QPixmap] = None
        self.setVisible(False)
        self._dragging: bool = False
        self._grab_x: float = 0.0
        self._grab_y: float = 0.0

        # Opacity effect + animations
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._anim_in = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._anim_in.setDuration(80)
        self._anim_in.setStartValue(0.0)
        self._anim_in.setEndValue(1.0)
        self._anim_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._anim_out = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._anim_out.setDuration(350)
        self._anim_out.setStartValue(1.0)
        self._anim_out.setEndValue(0.0)
        self._anim_out.setEasingCurve(QEasingCurve.Type.InCubic)
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
        # Keep above CPU-load overlay (and any other bottom chrome) so the
        # pan window is not covered by a raised sibling of the timeline pane.
        inset = int(getattr(view, "_nav_bottom_inset", 0) or 0)
        x = vp.x() + vp.width()  - self.W - self.MARGIN
        y = vp.y() + vp.height() - self.H - self.MARGIN - inset
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

    def _begin_nav_drag(self, grab_x: float, grab_y: float) -> None:
        """Start dragging the viewport indicator (app-level capture for Wayland)."""
        self._dragging = True
        self._grab_x = grab_x
        self._grab_y = grab_y
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

    def _end_nav_drag(self) -> None:
        self._dragging = False
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        view = self.parentWidget()
        if view is not None and hasattr(view, '_nav_popup_handle_release'):
            view._nav_popup_handle_release()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        """App-level mouse capture during nav-indicator drag (Wayland-safe)."""
        if not self._dragging:
            return False
        et = event.type()
        if et == QEvent.Type.MouseMove:
            gpos = event.globalPosition()
            local = self.mapFromGlobal(QPoint(int(gpos.x()), int(gpos.y())))
            view = self.parentWidget()
            if view is not None and hasattr(view, '_nav_popup_handle_drag'):
                view._nav_popup_handle_drag(
                    local.x(), local.y(), self._grab_x, self._grab_y)
            return True
        if (et == QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.LeftButton):
            self._end_nav_drag()
            return True
        return False

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            view = self.parentWidget()
            if view is not None and hasattr(view, '_nav_popup_handle_press'):
                if view._nav_popup_handle_press(
                        event.position().x(), event.position().y(), self):
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging:
            view = self.parentWidget()
            if view is not None and hasattr(view, '_nav_popup_handle_drag'):
                view._nav_popup_handle_drag(
                    event.position().x(), event.position().y(),
                    self._grab_x, self._grab_y)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._end_nav_drag()
            event.accept()
            return
        super().mouseReleaseEvent(event)

_RESIZE_EDGE_PX = 6
_RIGHT_DOCK_MIN_W = 180  # Web parity: RIGHT_PANEL_MIN_W in web/src/App.vue
# Fits the 3-column AI Templates grid (shared Statistics / AI dock).
_RIGHT_DOCK_DEFAULT_W = 450  # Web parity: RIGHT_PANEL_WIDTH in web/src/config.js
_RIGHT_DOCK_MAX_W = 520  # Web parity: RIGHT_PANEL_MAX_W in web/src/config.js

def _relax_layout_width_constraints(lay: QLayout) -> None:
    """Stop nested layouts from preserving a previously wide minimum width."""
    lay.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
    for i in range(lay.count()):
        item = lay.itemAt(i)
        if item is None:
            continue
        sub = item.layout()
        if sub is not None:
            _relax_layout_width_constraints(sub)

def _in_legend_panel(w: QWidget) -> bool:
    """True when *w* belongs to the Legend dock (must not get Ignored width policy)."""
    p: Optional[QWidget] = w
    while p is not None:
        if p.objectName() in (
                "legend_root", "legend_list_host", "legend_task_list",
                "legend_scroll", "legend_scroll_viewport"):
            return True
        p = p.parentWidget()
    return False


def _in_ai_actions_bar(w: QWidget) -> bool:
    """True when *w* is in the AI panel Clear/Stop/Ask bar (must keep width)."""
    p: Optional[QWidget] = w
    while p is not None:
        if p.objectName() == "aiActions":
            return True
        if p.objectName() == "aiTemplates":
            return True
        p = p.parentWidget()
    return False

def _relax_widget_tree(root: QWidget) -> None:
    """Clear horizontal minimum-size hints so a dock column can narrow."""
    for w in (root, *root.findChildren(QWidget)):
        if isinstance(w, _StatsSectionGrip) or _in_legend_panel(w):
            continue
        if w.objectName() == "stats_scope_action":
            continue
        # AI header actions: Ignored + row stretch collapses them to 0 width.
        if _in_ai_actions_bar(w):
            w.setMinimumWidth(0)
            continue
        w.setMinimumWidth(0)
        # Only relax push/tool buttons — QLabel and other controls need real width.
        if isinstance(w, (QPushButton, QToolButton)):
            pol = w.sizePolicy()
            pol.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
            w.setSizePolicy(pol)
    if root.layout() is not None:
        _relax_layout_width_constraints(root.layout())

class _HoverCursor:
    """Application-level hover cursor for resize split lines."""

    _shape: Optional[Qt.CursorShape] = None
    _RESIZE_SHAPES = frozenset((
        Qt.CursorShape.SizeVerCursor,
        Qt.CursorShape.SizeHorCursor,
        Qt.CursorShape.SplitVCursor,
        Qt.CursorShape.SplitHCursor,
    ))

    @staticmethod
    def _modal_cursor_active() -> bool:
        oc = QApplication.overrideCursor()
        return oc is not None and oc.shape() in (
            Qt.CursorShape.WaitCursor, Qt.CursorShape.BusyCursor, Qt.CursorShape.ForbiddenCursor)

    @classmethod
    def show(cls, shape: Qt.CursorShape) -> None:
        if cls._modal_cursor_active():
            cls._shape = None
            return
        if QApplication.instance() is None:
            return
        if cls._shape == shape:
            return
        if cls._shape is not None:
            QApplication.restoreOverrideCursor()
        QApplication.setOverrideCursor(QCursor(shape))
        cls._shape = shape

    @classmethod
    def hide(cls, shape: Optional[Qt.CursorShape] = None) -> None:
        owned = cls._shape
        if shape is not None and owned is not None and owned != shape:
            return
        cls._shape = None
        if QApplication.instance() is None:
            return
        oc = QApplication.overrideCursor()
        if oc is None:
            return
        live = oc.shape()
        if live in (
            Qt.CursorShape.WaitCursor, Qt.CursorShape.BusyCursor,
            Qt.CursorShape.ForbiddenCursor,
        ):
            return
        # macOS/Cocoa often remaps SizeVer ↔ SplitV / SizeNS. After a failed
        # exact-shape compare we used to drop `_shape` and leave the override.
        if owned is not None or live in cls._RESIZE_SHAPES:
            QApplication.restoreOverrideCursor()

class _SplitterHandleCursorFilter(QObject):
    """Drive _HoverCursor from QSplitter handle enter/leave."""

    def __init__(self, handle: QWidget, shape: Qt.CursorShape) -> None:
        super().__init__(handle)
        self._shape = shape
        self._active = False
        handle.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        handle.setMouseTracking(True)
        handle.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        et = event.type()
        if et in (QEvent.Type.Enter, QEvent.Type.HoverEnter):
            _HoverCursor.show(self._shape)
            self._active = True
        elif et in (QEvent.Type.Leave, QEvent.Type.HoverLeave, QEvent.Type.Hide):
            if self._active:
                _HoverCursor.hide(self._shape)
                self._active = False
        return False

def _install_splitter_handle_cursor(splitter: QSplitter, index: int) -> None:
    """Attach resize hover cursor to one QSplitter handle."""
    handle = splitter.handle(index)
    if handle is None:
        return
    shape = (Qt.CursorShape.SizeVerCursor if splitter.orientation() == Qt.Orientation.Vertical
             else Qt.CursorShape.SizeHorCursor)
    handle.setCursor(shape)
    if getattr(handle, "_hover_cursor_filter", None) is None:
        handle._hover_cursor_filter = _SplitterHandleCursorFilter(handle, shape)

class _ResizeSplitter(QSplitter):
    """QSplitter whose handles show a resize cursor on hover."""

    def createHandle(self):
        handle = super().createHandle()
        idx = self.count() - 1
        if idx >= 1:
            _install_splitter_handle_cursor(self, idx)
        return handle

def _wire_splitter_handle_cursors(root: QWidget) -> None:
    """Set resize cursors on every visible QSplitter handle under *root*."""
    for splitter in root.findChildren(QSplitter):
        for i in range(1, splitter.count()):
            _install_splitter_handle_cursor(splitter, i)

class _EdgeResizeCursorFilter(QObject):
    """Show a resize cursor when the pointer is near a widget edge."""

    def __init__(self, host: QWidget, edges: list,
                 margin: int = _RESIZE_EDGE_PX) -> None:
        super().__init__(host)
        self._host = host
        self._edges = edges   # (edge, cursor, optional enabled callable)
        self._margin = margin
        self._armed = False
        self._cursor: Optional[Qt.CursorShape] = None

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is not self._host:
            return False
        et = event.type()
        if et in (QEvent.Type.MouseMove, QEvent.Type.HoverMove):
            cursor = self._cursor_at(event.position().toPoint())
            if cursor is not None:
                if self._cursor != cursor:
                    if self._armed:
                        _HoverCursor.hide(self._cursor)
                    self._cursor = cursor
                    self._armed = True
                    _HoverCursor.show(cursor)
            elif self._armed:
                _HoverCursor.hide(self._cursor)
                self._armed = False
                self._cursor = None
        elif et in (QEvent.Type.Leave, QEvent.Type.HoverLeave, QEvent.Type.Hide):
            if self._armed:
                _HoverCursor.hide(self._cursor)
                self._armed = False
                self._cursor = None
        return False

    def _cursor_at(self, pos: QPoint):
        w, h = self._host.width(), self._host.height()
        for edge, cursor, enabled in self._edges:
            if enabled is not None and not enabled():
                continue
            if edge == "left" and pos.x() <= self._margin:
                return cursor
            if edge == "right" and pos.x() >= w - self._margin:
                return cursor
            if edge == "top" and pos.y() <= self._margin:
                return cursor
            if edge == "bottom" and pos.y() >= h - self._margin:
                return cursor
        return None

class _DockWidthResizeFilter(QObject):
    """Drag the central/right-dock seam to resize the right panel (web panel-resizer parity)."""

    def __init__(self, host: QWidget, win: "MainWindow", edge: str,
                 margin: int = _RESIZE_EDGE_PX,
                 enabled: Optional[Callable[[], bool]] = None) -> None:
        super().__init__(host)
        self._host = host
        self._win = win
        self._edge = edge  # "left" (dock) or "right" (central pane)
        self._margin = margin
        self._enabled = enabled
        self._hover_armed = False
        self._hover_cursor: Optional[Qt.CursorShape] = None
        self._dragging = False
        self._start_global_x = 0.0
        self._start_width = 0

    def _active(self) -> bool:
        if self._enabled is not None and not self._enabled():
            return False
        return self._win._any_visible_right_dock()

    def _on_edge(self, pos: QPoint) -> bool:
        w = self._host.width()
        if self._edge == "left":
            return pos.x() <= self._margin
        if self._edge == "right":
            return pos.x() >= w - self._margin
        return False

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if self._dragging and obj is not self._host:
            et = event.type()
            if et == QEvent.Type.MouseMove:
                _HoverCursor.show(Qt.CursorShape.SizeHorCursor)
                self._apply_drag(event.globalPosition().x())
                return True
            if (et == QEvent.Type.MouseButtonRelease
                    and event.button() == Qt.MouseButton.LeftButton):
                self._end_drag()
                return True
            return False

        if obj is not self._host:
            return False

        et = event.type()
        if (et == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
                and self._active()
                and self._on_edge(event.position().toPoint())):
            self._begin_drag(event.globalPosition().x())
            return True

        if et in (QEvent.Type.MouseMove, QEvent.Type.HoverMove):
            if self._active() and self._on_edge(event.position().toPoint()):
                if not self._hover_armed:
                    self._hover_armed = True
                    self._hover_cursor = Qt.CursorShape.SizeHorCursor
                    _HoverCursor.show(self._hover_cursor)
            elif self._hover_armed:
                _HoverCursor.hide(self._hover_cursor)
                self._hover_armed = False
                self._hover_cursor = None
        elif et in (QEvent.Type.Leave, QEvent.Type.HoverLeave, QEvent.Type.Hide):
            if self._hover_armed:
                _HoverCursor.hide(self._hover_cursor)
                self._hover_armed = False
                self._hover_cursor = None
        return False

    def _begin_drag(self, global_x: float) -> None:
        self._dragging = True
        self._win._right_dock_custom_drag = True
        self._start_global_x = global_x
        self._start_width = self._win._current_right_dock_width()
        _HoverCursor.show(Qt.CursorShape.SizeHorCursor)
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

    def _apply_drag(self, global_x: float) -> None:
        delta = global_x - self._start_global_x
        # Match web App.vue: nextW = startW - dx (drag left → wider right panel).
        width = self._start_width - delta
        self._win._apply_right_dock_width(width)

    def _end_drag(self) -> None:
        self._dragging = False
        self._win._right_dock_custom_drag = False
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)
        self._win._relax_right_dock_content_widths()
        self._win._apply_right_dock_width(self._win._current_right_dock_width())
        _wire_splitter_handle_cursors(self._win)

class _RightDockResizeGuard(QObject):
    """Keep the main-window frame fixed when the right dock column is resized."""

    def __init__(self, win: "MainWindow", dock: QDockWidget) -> None:
        super().__init__(dock)
        self._win = win
        self._dock = dock
        self._last_w = dock.width()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._dock and event.type() == QEvent.Type.Resize:
            if getattr(self._win, "_right_dock_custom_drag", False):
                return False
            w = self._dock.width()
            if w != self._last_w:
                self._last_w = w
                self._win._schedule_stabilize_right_dock_layout()
        return False

class _LabelGripDragCapture(QObject):
    """App-level mouse capture for label-column resize (Wayland-safe)."""

    def __init__(self, grip: "_LabelColumnGripItem") -> None:
        super().__init__()
        self._grip = grip

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        grip = self._grip
        if not grip._dragging:
            return False
        et = event.type()
        if et == QEvent.Type.MouseMove:
            _HoverCursor.show(Qt.CursorShape.SizeHorCursor)
            view = grip._view()
            if view is not None:
                view._apply_label_width_drag(
                    int(grip._start_w + (event.globalPosition().x() - grip._start_global_x)))
            return True
        if (et == QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.LeftButton):
            grip._finish_label_drag()
            return True
        return False

class _LabelColumnGripItem(QGraphicsItem):
    """Frozen scene-item resize grip (moves with the label column on horizontal pan)."""

    GRIP_W = 10

    def __init__(self, scene: "TimelineScene", total_h: float) -> None:
        super().__init__()
        self._scene = scene
        self._total_h = total_h
        self._dragging = False
        self._start_global_x = 0.0
        self._start_w = 0
        self._hovered = False
        self._drag_capture = _LabelGripDragCapture(self)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setToolTip("Drag to resize label column")
        self.setZValue(42)

    def _view(self) -> Optional["TimelineView"]:
        views = self._scene.views()
        return views[0] if views else None

    def boundingRect(self) -> QRectF:
        hw = self.GRIP_W / 2.0
        return QRectF(-hw, 0, self.GRIP_W, self._total_h)

    def paint(self, painter, _option, _widget=None) -> None:
        dark = getattr(self._scene, "_is_dark_ui", True)
        line = QColor("#4a9eff") if (self._dragging or self._hovered) else (
            QColor("#666666") if dark else QColor("#CCCCCC"))
        painter.setPen(QPen(line, 2))
        painter.drawLine(QPointF(0, 0), QPointF(0, self._total_h))

    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def _finish_label_drag(self) -> None:
        self._dragging = False
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self._drag_capture)
        view = self._view()
        if view is not None:
            view._finish_label_width_drag()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._start_global_x = event.globalPosition().x()
            self._start_w = self._scene._label_width
            _HoverCursor.show(Qt.CursorShape.SizeHorCursor)
            app = QApplication.instance()
            if app:
                app.installEventFilter(self._drag_capture)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            view = self._view()
            if view is not None:
                _HoverCursor.show(Qt.CursorShape.SizeHorCursor)
                view._apply_label_width_drag(
                    int(self._start_w + (event.globalPosition().x() - self._start_global_x)))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._finish_label_drag()
            event.accept()
            return
        super().mouseReleaseEvent(event)

class _LabelColumnGrip(QWidget):
    """Legacy viewport QWidget grip — hidden; use _LabelColumnGripItem instead."""

    GRIP_W = 10

    def __init__(self, view: "TimelineView") -> None:
        super().__init__(view.viewport())
        self._view = view
        self._dragging = False
        self._start_global_x = 0
        self._start_w = 0
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setToolTip("Drag to resize label column")
        self.hide()

    def paintEvent(self, _event) -> None:
        dark = getattr(self._view._scene, "_dark_ui", True)
        line = QColor("#4a9eff") if (self._dragging or self.underMouse()) else (
            QColor("#666666") if dark else QColor("#CCCCCC"))
        p = QPainter(self)
        try:
            cx = self.width() // 2
            p.setPen(QPen(line, 2))
            p.drawLine(cx, 0, cx, self.height())
        finally:
            p.end()

    def eventFilter(self, obj, event) -> bool:
        """App-level mouse capture during drag — Wayland-safe replacement for grabMouse()."""
        if not self._dragging:
            return False
        et = event.type()
        if et == QEvent.Type.MouseMove:
            _HoverCursor.show(Qt.CursorShape.SizeHorCursor)
            self._view._apply_label_width_drag(
                self._start_w + (event.globalPosition().x() - self._start_global_x))
            return True
        if et == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            app = QApplication.instance()
            if app:
                app.removeEventFilter(self)
            self._view._finish_label_width_drag()
            return True
        return False

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._start_global_x = event.globalPosition().x()
            self._start_w = self._view._scene._label_width
            _HoverCursor.show(Qt.CursorShape.SizeHorCursor)
            app = QApplication.instance()
            if app:
                app.installEventFilter(self)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            _HoverCursor.show(Qt.CursorShape.SizeHorCursor)
            self._view._apply_label_width_drag(
                self._start_w + (event.globalPosition().x() - self._start_global_x))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            app = QApplication.instance()
            if app:
                app.removeEventFilter(self)
            self._view._finish_label_width_drag()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def enterEvent(self, _event) -> None:
        _HoverCursor.show(Qt.CursorShape.SizeHorCursor)
        self.update()

    def leaveEvent(self, _event) -> None:
        if not self._dragging:
            _HoverCursor.hide(Qt.CursorShape.SizeHorCursor)
        self.update()

# ===========================================================================
# View
# ===========================================================================

def _is_zoom_native_gesture(event) -> bool:
    """True for macOS trackpad pinch (Qt6 NativeGestureType is not int()-able)."""
    try:
        return event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture
    except AttributeError:
        return False

def _native_gesture_local_pos(event) -> QPoint:
    if hasattr(event, "position"):
        p = event.position()
        return p.toPoint() if hasattr(p, "toPoint") else QPoint(int(p.x()), int(p.y()))
    return event.pos()

def _native_gesture_zoom_factor(event) -> float:
    try:
        return 1.0 + float(event.value())
    except (AttributeError, TypeError, ValueError):
        return 1.0

def _fix_collapsed_time_ns_range(
    ns_lo: int,
    ns_hi: int,
    lo_coord: float,
    hi_coord: float,
    t_min: int,
    t_max: int,
    tpp: float,
    *,
    min_span_ns: int = 0,
) -> Tuple[int, int]:
    """When clamped viewport time bounds collapse or invert, anchor at the edge."""
    if ns_lo < ns_hi:
        return ns_lo, ns_hi
    span_ns = max(1, int(abs(hi_coord - lo_coord) * tpp))
    if hi_coord < lo_coord and min_span_ns > 0:
        span_ns = max(span_ns, min_span_ns)
    if hi_coord < lo_coord or ns_hi >= t_max - 1:
        ns_hi = t_max
        ns_lo = max(t_min, t_max - span_ns)
    elif ns_lo <= t_min + 1:
        ns_lo = t_min
        ns_hi = min(t_max, t_min + span_ns)
    else:
        ns_lo = max(t_min, min(ns_lo, t_max - 1))
        ns_hi = min(t_max, max(ns_hi, ns_lo + 1))
    return ns_lo, ns_hi

class TimelineView(QGraphicsView):
    """Pan + zoom QGraphicsView wrapping a TimelineScene."""

    zoom_changed         = Signal(float)
    viewport_changed     = Signal()
    label_width_changed  = Signal(int)
    label_width_resizing = Signal(int)  # live drag; CPU load repaints without persisting
    cursors_changed      = Signal(list)
    mark_moved           = Signal(str, int, int)  # kind, id, new_ns - final drop
    mark_dragging        = Signal(str, int, int)  # kind, id, new_ns - live during drag
    bookmark_requested          = Signal(int)   # ns at right-click position
    annotation_requested        = Signal(int)   # ns at right-click position
    explain_region_requested    = Signal()      # explain cursor region with AI
    ask_ai_event_requested       = Signal(object)  # {task, core, start, stop, ns}
    clear_bookmarks_requested   = Signal()      # clear all bookmarks
    clear_annotations_requested = Signal()      # clear all annotations
    pre_change                  = Signal()      # emitted before any cursor/mark mutation

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
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._programmatic_viewport = 0

        # -- Mouse interaction state -------------------------------------
        # Tracks the press position to distinguish click vs drag; button to
        # distinguish left / middle / right action paths in mouseReleaseEvent.
        self._press_pos: Optional[QPoint] = None
        self._press_btn: Qt.MouseButton = Qt.MouseButton.NoButton
        self._drag_threshold    = 6    # px - min movement to enter pan mode
        self._dragging_cursor_idx = -1  # index of cursor being dragged, or -1
        self._cursor_drag_threshold = 8 # px - click-zone around a cursor line
        self._dragging_mark_idx = -1    # index into _mark_data being dragged, or -1
        self._mark_drag_threshold = 6   # px - click-zone around a mark line

        # Label-column resize drag state
        self._LABEL_RESIZE_ZONE   = 10  # px hit zone around the right border
        self._label_resize_dragging = False
        self._label_resize_start_x  = 0
        self._label_resize_start_w  = 0
        self._label_grip = _LabelColumnGrip(self)

        # Middle-button time-range selection (drag to select, release to zoom)
        self._mid_press_ns: Optional[int]   = None   # ns at middle-press
        self._mid_band_item = None                   # gray overlay QGraphicsRectItem

        # Ctrl+drag measure ruler (double-arrow line + Δtime, hidden on release)
        self._measure_press_ns: Optional[int] = None
        self._measure_anchor_coord: float = 0.0   # perpendicular scene coord (row/col)

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
        self._scene.scene_rebuilt.connect(self._on_scene_rebuilt_scroll)
        self._scene.scene_rebuilt.connect(self._reposition_frozen)
        self._scene.scene_rebuilt.connect(self._reposition_frozen_top)
        self._scene.scene_rebuilt.connect(self._sync_timeline_column_clip)
        self._scene.scene_rebuilt.connect(self._update_label_grip_geometry)

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
        # Extra bottom margin so the popup clears the CPU-load overlay that
        # _CpuLoadStack paints on top of the full-height timeline pane.
        self._nav_bottom_inset: int = 0
        # Background pixmap cache for the nav popup.  Rebuilt only when the
        # trace, view-mode, STI visibility or expansion state changes.
        # On every scroll we just copy the cached bg and overlay the viewport rect.
        self._nav_bg_pix: Optional[QPixmap] = None
        self._nav_bg_key: object             = None
        self._nav_bg_task_area_h: float      = 0.0   # task-area height used in last bg paint

        # Full-trace time scrollbar (overlay; native bar stays scene-local/hidden).
        self._virt_time_scroll_px: float = 0.0
        self._virt_scroll_scale: float = 1.0
        self._syncing_time_scrollbar: bool = False
        self._virtual_time_scroll_active: bool = False
        self._native_time_bar_interaction_conn = None
        self._virt_scroll_rebuild: bool = False
        self._syncing_virt_bar: bool = False
        self._virt_bar_dragging: bool = False
        self._time_scroll_external: bool = False
        self._time_scroll_bar: Optional[QScrollBar] = None
        self._time_scroll_internal = QScrollBar(Qt.Orientation.Horizontal, self)
        self._bind_time_scroll_bar(self._time_scroll_internal)
        self._time_scroll_internal.hide()
        # Belt-and-suspenders: scrollbar-driven pan must re-pin ruler overlays even
        # when scrollContentsBy is skipped (virtual scroll / batched setValue).
        self.verticalScrollBar().valueChanged.connect(self._on_vertical_scroll_changed)
        self.horizontalScrollBar().valueChanged.connect(self._on_horizontal_scroll_changed)
        self._last_window_shift_ms: float = 0.0
        self._pending_shift_ns_lo: Optional[float] = None
        self._pending_shift_ns_hi: Optional[float] = None
        self._window_shift_timer = QTimer(self)
        self._window_shift_timer.setSingleShot(True)
        self._window_shift_timer.timeout.connect(self._flush_pending_window_shift)
        self._zoom_reanchor_pending: bool = False
        self._preserve_virt_scroll: bool = False
        self._preserved_virt_scroll_px: float = 0.0
        self.zoom_changed.connect(self._defer_virt_scroll_sync)

    @property
    def _virt_trace_bar(self) -> QScrollBar:
        return self._time_scroll_bar or self._time_scroll_internal

    def attach_time_scroll_bar(self, bar: QScrollBar) -> None:
        """Use a sibling scrollbar below the canvas (horizontal task layout)."""
        self._time_scroll_bar = bar
        self._time_scroll_external = True
        self._bind_time_scroll_bar(bar)
        self._time_scroll_internal.hide()

    def _bind_time_scroll_bar(self, bar: QScrollBar) -> None:
        bar.valueChanged.connect(self._on_virt_trace_bar_changed)
        bar.sliderPressed.connect(self._on_virt_trace_bar_pressed)
        bar.sliderReleased.connect(self._on_virt_trace_bar_released)
        bar.installEventFilter(self)
        bar.hide()

    # ------------------------------------------------------------------
    # Full-trace time scrollbar (overlay when zoomed past fit-to-window)
    #
    # Virtual-scroll model
    # --------------------
    # _virt_time_scroll_px  - canonical position along the full trace (px from
    #                         trace.time_min); authoritative whenever virtual
    #                         scroll is active.
    # _apply_virt_time_scroll_px() - sole applicator that moves the viewport.
    # _reposition_time_at_viewport() - place an ns at a viewport pixel (zoom anchor).
    # _navigate_time_to_ns()         - center an ns on the time axis.
    # _capture_virt_time_scroll_px() - read canonical from the live viewport
    #                         (after in-window Qt wheel / native scroll only).
    # _push_virt_trace_bar() - reflect canonical position on the overlay bar.
    # ------------------------------------------------------------------

    def _should_use_virtual_scroll(self) -> bool:
        """True when zoomed in past fit-to-window (overlay scrollbar model)."""
        if self._fit_mode or self._scene._trace is None:
            return False
        fit = self._scene._timescale_per_px_fit
        if math.isfinite(fit) and self._scene._timescale_per_px >= fit * 0.999:
            return False
        return True

    def _timeline_offset_px(self, vp_pos: QPoint) -> float:
        """Pixels from the viewport origin to *vp_pos* along the time axis (past labels)."""
        lw = float(self._scene._label_width)
        if self._scene._horizontal:
            return max(0.0, float(vp_pos.x()) - lw)
        return max(0.0, float(vp_pos.y()) - lw)

    def _virt_px_for_ns_at_offset(self, ns: float, timeline_offset_px: float) -> float:
        """Full-trace scroll px placing *ns* at *timeline_offset_px* into the timeline area."""
        tpp = self._scene._timescale_per_px
        return self._virt_px_from_ns_lo(float(ns) - timeline_offset_px * tpp)

    def _reposition_time_at_viewport(
        self,
        ns: int,
        vp_pos: QPoint,
        orth_scene: Optional[float] = None,
        *,
        force_window: bool = False,
    ) -> None:
        """Keep *ns* fixed at *vp_pos* on the time axis (zoom anchor / cursor jump)."""
        if self._scene._trace is None:
            return
        trace = self._scene._trace
        ns = max(trace.time_min, min(trace.time_max, int(ns)))
        is_horiz = self._scene._horizontal
        vp_center = self.viewport().rect().center()
        offset = ((vp_center.x() - vp_pos.x()) if is_horiz
                  else (vp_center.y() - vp_pos.y()))
        if self._should_use_virtual_scroll():
            if not self._virtual_time_scroll_active:
                self._set_virtual_scroll_enabled(True)
            off = self._timeline_offset_px(vp_pos)
            self._apply_virt_time_scroll_px(
                self._virt_px_for_ns_at_offset(ns, off),
                force_window=force_window,
            )
            return
        new_coord = self._scene.ns_to_scene_coord(ns)
        if orth_scene is None:
            cur = self.mapToScene(vp_center)
            orth_scene = cur.y() if is_horiz else cur.x()
        if is_horiz:
            self.centerOn(new_coord + offset, orth_scene)
        else:
            self.centerOn(orth_scene, new_coord + offset)

    def _set_virt_from_time_anchor(self, anchor_ns: int, vp_pos: QPoint) -> None:
        """Update canonical scroll px so *anchor_ns* stays at *vp_pos*."""
        off = self._timeline_offset_px(vp_pos)
        self._virt_time_scroll_px = self._clamp_virt_time_scroll_px(
            self._virt_px_for_ns_at_offset(anchor_ns, off))

    def _defer_virt_scroll_sync(self, _tpp: float) -> None:
        QTimer.singleShot(0, self._sync_virt_after_zoom)

    def _sync_virt_after_zoom(self) -> None:
        if self._scene._trace is None:
            return
        if self._fit_mode:
            self._virt_time_scroll_px = 0.0
            self._set_virtual_scroll_enabled(False)
        elif not self._should_use_virtual_scroll():
            self._set_virtual_scroll_enabled(False)
        else:
            if not self._virtual_time_scroll_active:
                self._set_virtual_scroll_enabled(True)
            else:
                self._update_virt_trace_bar_range()
            self._push_virt_trace_bar()

    def _native_time_axis_bar(self) -> QScrollBar:
        return (self.horizontalScrollBar() if self._scene._horizontal
                else self.verticalScrollBar())

    def _time_axis_track_thickness(self) -> int:
        bar = self._native_time_axis_bar()
        if self._scene._horizontal:
            return max(TIMELINE_SCROLL_GUTTER, bar.sizeHint().height())
        return max(TIMELINE_SCROLL_GUTTER, bar.sizeHint().width())

    def _collapse_native_time_bar(self, collapsed: bool) -> None:
        """Keep native time bar in the tree for macOS wheel routing; hide visually."""
        bar = self._native_time_axis_bar()
        track = self._time_axis_track_thickness()
        if collapsed:
            if self._scene._horizontal:
                bar.setStyleSheet(
                    f"QScrollBar:horizontal {{ height: {track}px; max-height: {track}px;"
                    f" min-height: {track}px; border: none; background: transparent; }}"
                    "QScrollBar::handle:horizontal { min-width: 0; max-width: 0;"
                    " background: transparent; }"
                    "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal"
                    " { width: 0; }"
                    "QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal"
                    " { background: none; }")
                bar.setFixedHeight(track)
            else:
                bar.setStyleSheet(
                    f"QScrollBar:vertical {{ width: {track}px; max-width: {track}px;"
                    f" min-width: {track}px; border: none; background: transparent; }}"
                    "QScrollBar::handle:vertical { min-height: 0; max-height: 0;"
                    " background: transparent; }"
                    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical"
                    " { height: 0; }"
                    "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical"
                    " { background: none; }")
                bar.setFixedWidth(track)
            bar.show()
        else:
            bar.setStyleSheet("")
            bar.setMinimumHeight(0)
            bar.setMaximumHeight(16777215)
            bar.setMinimumWidth(0)
            bar.setMaximumWidth(16777215)
            if self._scene._horizontal:
                bar.setFixedHeight(bar.sizeHint().height())
            else:
                bar.setFixedWidth(bar.sizeHint().width())
            bar.show()

    def _time_axis_track_rect(self) -> QRect:
        """Rect for an in-view time scrollbar overlay (vertical layout / settings only)."""
        vp = self.viewport()
        vsb = self.verticalScrollBar()
        hsb = self.horizontalScrollBar()
        if self._scene._horizontal:
            track_h = self._time_axis_track_thickness()
            v_w = vsb.width() if vsb.isVisible() else 0
            y = vp.y() + vp.height()
            h = min(track_h, max(1, self.height() - y))
            if h < 4:
                corner = vsb.height() if vsb.isVisible() else 0
                h = min(track_h, max(1, self.height() - corner))
                y = max(0, self.height() - corner - h)
            return QRect(0, y, max(1, self.width() - v_w), max(4, h))
        track_w = self._time_axis_track_thickness()
        h_h = hsb.height() if hsb.isVisible() else 0
        x = vp.x() + vp.width()
        w = min(track_w, max(1, self.width() - x))
        if w < 4:
            w = min(track_w, max(1, self.width() - h_h))
            x = max(0, self.width() - h_h - w)
        return QRect(x, 0, max(4, w), max(1, self.height() - h_h))

    def orth_scroll_gutter_px(self) -> int:
        """Scene padding on the task axis so the last row clears chrome overlays.

        Includes native/virtual scrollbar tracks and, in horizontal layout, the
        CPU-load overlay height (``_nav_bottom_inset``) so tasks can scroll out
        from under the overlay.  Hiding the CPU load clears that inset.
        """
        sc = self._scene
        gutter = TIMELINE_SCROLL_GUTTER
        if sc._horizontal:
            if (not self._time_scroll_external
                    and (self._virtual_time_scroll_active or self._virt_trace_bar.isVisible())):
                gutter = max(gutter, self._virt_trace_bar.height() or TIMELINE_SCROLL_GUTTER)
            hbar = self.horizontalScrollBar()
            if (not self._time_scroll_external
                    and hbar.isVisible() and hbar.maximum() > hbar.minimum()):
                gutter = max(gutter, hbar.height())
            # CPU-load overlay covers the bottom of the full-height timeline.
            gutter = max(gutter, int(self._nav_bottom_inset or 0))
        else:
            if self._virtual_time_scroll_active or self._virt_trace_bar.isVisible():
                gutter = max(gutter, self._virt_trace_bar.width() or TIMELINE_SCROLL_GUTTER)
            vbar = self.verticalScrollBar()
            if vbar.isVisible() and vbar.maximum() > vbar.minimum():
                gutter = max(gutter, vbar.width())
        return gutter

    def _set_virtual_scroll_enabled(self, enabled: bool) -> None:
        self._virtual_time_scroll_active = bool(enabled)
        native = self._native_time_axis_bar()
        overlay = self._virt_trace_bar
        if enabled and self._scene._trace is not None:
            if self._time_scroll_external and self._scene._horizontal:
                self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            else:
                self._collapse_native_time_bar(True)
            overlay.show()
            self._position_virt_trace_bar()
            self._sync_native_scene_scrollbar()
            native.installEventFilter(self)
            if self._native_time_bar_interaction_conn is None:
                self._native_time_bar_interaction_conn = native.valueChanged.connect(
                    self._on_native_time_bar_interaction)
            if not self._zoom_reanchor_pending:
                self._capture_virt_time_scroll_px()
            self._update_virt_trace_bar_range()
            self._push_virt_trace_bar()
        else:
            conn = self._native_time_bar_interaction_conn
            if conn is not None:
                try:
                    QObject.disconnect(conn)
                except (RuntimeError, TypeError):
                    pass
                self._native_time_bar_interaction_conn = None
            native.removeEventFilter(self)
            overlay.hide()
            if self._time_scroll_external and self._scene._horizontal:
                self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
            else:
                self._collapse_native_time_bar(False)

    def _position_virt_trace_bar(self) -> None:
        if not self._virt_trace_bar.isVisible():
            return
        bar = self._virt_trace_bar
        if self._time_scroll_external and self._scene._horizontal:
            bar.setFixedHeight(self._time_axis_track_thickness())
            return
        bar.setOrientation(
            Qt.Orientation.Horizontal if self._scene._horizontal
            else Qt.Orientation.Vertical)
        bar.setGeometry(self._time_axis_track_rect())
        bar.raise_()

    def _sync_native_scene_scrollbar(self) -> None:
        """Keep the hidden native bar matched to the sliding scene window."""
        if self._fit_mode or self._scene._trace is None:
            return
        bar = self._native_time_axis_bar()
        if self._scene._horizontal:
            scene_span = int(self._scene.sceneRect().width())
            page = int(self._timeline_viewport_px())
        else:
            scene_span = int(self._scene.sceneRect().height())
            page = int(self._timeline_viewport_px())
        bar.blockSignals(True)
        bar.setRange(0, max(0, scene_span - page))
        bar.setPageStep(max(1, min(page, max(1, bar.maximum()))))
        bar.setSingleStep(max(1, page // 20))
        bar.blockSignals(False)

    def _timeline_viewport_px(self) -> float:
        return max(1.0, self._time_axis_viewport_px() - self._scene._label_width)

    def _full_trace_timeline_px(self) -> float:
        trace = self._scene._trace
        if trace is None:
            return 1.0
        span = max(trace.time_max - trace.time_min, 1)
        return max(1.0, span / self._scene._timescale_per_px)

    def _visible_time_ns_range(self) -> Tuple[int, int]:
        trace = self._scene._trace
        if trace is None:
            return 0, 0
        sc = self._scene
        lo_coord, hi_coord = self._timeline_viewport_time_coords()
        lw = sc._label_width
        origin = sc._scene_origin_ns
        tpp = sc._timescale_per_px
        ns_lo = origin + int((lo_coord - lw) * tpp)
        ns_hi = origin + int((hi_coord - lw) * tpp)
        ns_lo = max(trace.time_min, min(trace.time_max, ns_lo))
        ns_hi = max(trace.time_min, min(trace.time_max, ns_hi))
        page_ns = max(1, int(self._timeline_viewport_px() * tpp))
        if ns_lo >= ns_hi:
            ns_lo, ns_hi = _fix_collapsed_time_ns_range(
                ns_lo, ns_hi, lo_coord, hi_coord,
                trace.time_min, trace.time_max, tpp, min_span_ns=page_ns)
        return ns_lo, ns_hi

    def _virt_px_from_ns_lo(self, ns_lo: float) -> float:
        trace = self._scene._trace
        if trace is None:
            return 0.0
        return max(0.0, (ns_lo - trace.time_min) / self._scene._timescale_per_px)

    def _ns_lo_from_virt_px(self, virt_px: float) -> float:
        trace = self._scene._trace
        if trace is None:
            return 0.0
        return trace.time_min + virt_px * self._scene._timescale_per_px

    def _clamp_virt_time_scroll_px(self, virt_px: float) -> float:
        max_px = max(0.0, self._full_trace_timeline_px() - self._timeline_viewport_px())
        return max(0.0, min(max_px, virt_px))

    def _max_virt_time_scroll_px(self) -> float:
        return max(0.0, self._full_trace_timeline_px() - self._timeline_viewport_px())

    def _virt_scroll_at_trace_start(self, slack_px: float = 0.5) -> bool:
        return self._virt_time_scroll_px <= slack_px

    def _virt_scroll_at_trace_end(self, slack_px: float = 0.5) -> bool:
        return self._virt_time_scroll_px >= self._max_virt_time_scroll_px() - slack_px

    def _native_scroll_for_ns_lo(self, ns_lo: float) -> int:
        """Scene-local scroll placing *ns_lo* at the timeline viewport's left edge.

        Does not include label_width: the frozen label column is repositioned
        separately via _reposition_frozen(), so only timeline pixels scroll.
        """
        sc = self._scene
        tpp = sc._timescale_per_px
        return max(0, int(round((ns_lo - sc._scene_origin_ns) / tpp)))

    def _ideal_native_scroll_for_ns_lo(self, ns_lo: float) -> int:
        """Scene-local scroll for *ns_lo* without clamping to the native bar range."""
        sc = self._scene
        tpp = sc._timescale_per_px
        return int(round((ns_lo - sc._scene_origin_ns) / tpp))

    def _timeline_viewport_time_coords(self) -> Tuple[float, float]:
        """Scene time-axis coordinates at the left and right timeline viewport edges."""
        lw = self._scene._label_width
        vp_rect = self.viewport().rect()
        if self._scene._horizontal:
            lo = self.mapToScene(QPoint(int(lw), vp_rect.top())).x()
            hi = self.mapToScene(vp_rect.topRight()).x()
        else:
            lo = self.mapToScene(QPoint(vp_rect.left(), int(lw))).y()
            hi = self.mapToScene(vp_rect.bottomLeft()).y()
        return lo, hi

    def _update_virt_trace_bar_range(self) -> None:
        """Map the full trace onto the overlay bar (thumb shrinks when zoomed in)."""
        if not self._virtual_time_scroll_active or self._scene._trace is None:
            return
        full_px = self._full_trace_timeline_px()
        page_px = self._timeline_viewport_px()
        max_scroll_px = max(0.0, full_px - page_px)
        if max_scroll_px > _VIRT_SCROLL_MAX:
            self._virt_scroll_scale = max_scroll_px / _VIRT_SCROLL_MAX
            bar_max = _VIRT_SCROLL_MAX
        else:
            self._virt_scroll_scale = 1.0
            bar_max = int(max_scroll_px)
        page_step = max(1, int(page_px / self._virt_scroll_scale))
        bar = self._virt_trace_bar
        bar.blockSignals(True)
        bar.setRange(0, max(0, bar_max))
        bar.setPageStep(min(page_step, max(1, bar_max or 1)))
        bar.setSingleStep(max(1, int(20.0 / self._virt_scroll_scale)))
        bar.blockSignals(False)

    def _capture_virt_time_scroll_px(self) -> None:
        """Update canonical scroll position from the current viewport."""
        if not self._virtual_time_scroll_active or self._scene._trace is None:
            return
        if (self._preserve_virt_scroll or self._virt_scroll_rebuild
                or self._zoom_reanchor_pending):
            return
        self._virt_time_scroll_px = self._virt_px_from_ns_lo(
            float(self._visible_time_ns_range()[0]))

    def _push_virt_trace_bar(self) -> None:
        """Reflect canonical _virt_time_scroll_px on the overlay scrollbar."""
        if (not self._virtual_time_scroll_active
                or self._scene._trace is None
                or self._virt_bar_dragging):
            return
        val = int(self._virt_time_scroll_px / self._virt_scroll_scale)
        bar = self._virt_trace_bar
        val = max(bar.minimum(), min(bar.maximum(), val))
        self._syncing_virt_bar = True
        try:
            bar.blockSignals(True)
            bar.setValue(val)
            bar.blockSignals(False)
        finally:
            self._syncing_virt_bar = False

    def _sync_virt_trace_bar_from_view(self) -> None:
        """Capture viewport position, then update the overlay bar."""
        if self._preserve_virt_scroll:
            return
        self._capture_virt_time_scroll_px()
        self._push_virt_trace_bar()

    def set_nav_bottom_inset(self, px: int) -> None:
        """Reserve bottom pixels so the navigator clears an overlay (CPU load).

        Also refreshes the task-axis scene extent so the vertical scrollbar
        range grows/shrinks with the CPU-load overlay (without a full rebuild).
        """
        inset = max(0, int(px))
        if inset == self._nav_bottom_inset:
            return
        self._nav_bottom_inset = inset
        if self._nav_popup.isVisible():
            self._nav_popup.reposition()
        self._sync_orth_scene_extent()

    def _sync_orth_scene_extent(self) -> None:
        """Resize scene orth axis to content + current overlay/scrollbar gutters."""
        sc = self._scene
        if sc._trace is None:
            return
        content = getattr(sc, "_orth_content_px", None)
        if content is None:
            return
        new_orth = sc._finalize_orth_size(float(content))
        rect = sc.sceneRect()
        if sc._horizontal:
            if abs(rect.height() - new_orth) < 1.0:
                return
            sc.setSceneRect(0, 0, rect.width(), new_orth)
            bar = self.verticalScrollBar()
        else:
            if abs(rect.width() - new_orth) < 1.0:
                return
            sc.setSceneRect(0, 0, new_orth, rect.height())
            bar = self.horizontalScrollBar()
        bar.setValue(min(bar.value(), bar.maximum()))
        self._reposition_frozen()
        self._reposition_frozen_top()

    def _refresh_nav_pan_window(self, *, force_show: bool = False) -> None:
        """Repaint and show the navigator minimap (orange viewport box)."""
        if not self._navigator_eligible():
            self._nav_hide_timer.stop()
            self._nav_popup.hide()
            return
        pix = self._paint_nav_pixmap()
        self._nav_popup.set_pixmap(pix)
        self._nav_popup.reposition()
        if force_show or not self._nav_popup.isVisible():
            self._nav_popup.fade_in()
        if not self._nav_popup._dragging:
            self._nav_hide_timer.start()

    def begin_programmatic_viewport(self) -> None:
        """Ignore inspector follow while Jump/Spotlight zooms the timeline."""
        self._programmatic_viewport = getattr(self, "_programmatic_viewport", 0) + 1

    def end_programmatic_viewport(self) -> None:
        n = getattr(self, "_programmatic_viewport", 0) - 1
        self._programmatic_viewport = n if n > 0 else 0

    def _after_time_axis_pan(self, *, immediate: bool = False) -> None:
        """Refresh navigator/minimap after any time-axis pan (wheel, bar, overlay)."""
        if not getattr(self, "_programmatic_viewport", 0):
            self.viewport_changed.emit()
        self._pan_timer.start()
        if immediate or self._virt_bar_dragging:
            self._refresh_nav_pan_window(force_show=True)
            return
        interval = (_NAV_SCROLL_ACTIVE_MS
                    if self._virtual_time_scroll_active
                    else _NAV_SCROLL_DEBOUNCE_MS)
        self._nav_scroll_timer.setInterval(interval)
        self._nav_scroll_timer.start()
        if self._nav_popup.isVisible():
            self._refresh_nav_pan_window()

    def _loaded_window_covers_viewport_ns(self, ns_lo: float, ns_hi: float) -> bool:
        """True when the viewport time range still fits the last rebuild's segment band."""
        sc = self._scene
        if sc._trace is None:
            return True
        prefetch_ns = max(1, int((ns_hi - ns_lo) * 0.08))
        return (ns_lo >= sc._vp_ns_lo + prefetch_ns
                and ns_hi <= sc._vp_ns_hi - prefetch_ns)

    def _needs_window_shift_for_time(
        self, ns_lo: float, ns_hi: float, bar: QScrollBar,
    ) -> bool:
        """True when native in-scene scroll cannot satisfy the target position."""
        trace = self._scene._trace
        if trace is None:
            return False
        ideal = self._ideal_native_scroll_for_ns_lo(ns_lo)
        if ideal < bar.minimum() or ideal > bar.maximum():
            return True
        page_px = self._timeline_viewport_px()
        tpp = self._scene._timescale_per_px
        edge_slack = max(2, int(page_px * 0.05))
        edge_ns = max(1, int(page_px * tpp * 0.02))

        # Already showing the trace start/end — do not slide the loaded window.
        if ns_hi >= trace.time_max - edge_ns and ideal >= bar.maximum() - edge_slack:
            return False
        if ns_lo <= trace.time_min + edge_ns and ideal <= bar.minimum() + edge_slack:
            return False

        at_native_edge = (ideal <= bar.minimum() + edge_slack
                          or ideal >= bar.maximum() - edge_slack)
        if not at_native_edge:
            return False
        return not self._loaded_window_covers_viewport_ns(ns_lo, ns_hi)

    def _apply_virt_time_scroll_px(
        self,
        virt_px: float,
        *,
        force_window: bool = False,
        sync_bar: bool = True,
    ) -> None:
        """Move the timeline to *virt_px* along the full trace (single applicator)."""
        trace = self._scene._trace
        if trace is None:
            return
        prev_virt = self._virt_time_scroll_px
        virt_px = self._clamp_virt_time_scroll_px(float(virt_px))
        if not force_window and abs(virt_px - prev_virt) < 0.5:
            self._virt_time_scroll_px = virt_px
            if sync_bar and not self._virt_bar_dragging:
                self._push_virt_trace_bar()
            return
        ns_lo = max(float(trace.time_min), min(float(trace.time_max),
                    self._ns_lo_from_virt_px(virt_px)))
        page_px = self._timeline_viewport_px()
        tpp = self._scene._timescale_per_px
        ns_hi = min(float(trace.time_max), ns_lo + page_px * tpp)
        self._sync_native_scene_scrollbar()
        bar = self._native_time_axis_bar()
        ideal = self._ideal_native_scroll_for_ns_lo(ns_lo)
        if ideal >= bar.minimum() and ideal <= bar.maximum():
            self._virt_time_scroll_px = virt_px
            moved = self._set_native_time_scroll_local(ideal)
            if not moved and abs(virt_px - prev_virt) >= 0.5:
                self._shift_time_window_to(ns_lo, ns_hi, force=True)
                return
            if sync_bar and not self._virt_bar_dragging:
                self._push_virt_trace_bar()
            self._after_time_axis_pan(immediate=self._virt_bar_dragging)
        else:
            self._shift_time_window_to(ns_lo, ns_hi, force=force_window)

    def _scroll_time_axis_native(self, delta: int) -> None:
        """Scroll along the native time scrollbar (non-virtual / scene-local)."""
        if delta == 0 or self._scene._trace is None:
            return
        sc = self._scene
        bar = self._native_time_axis_bar()
        new_val = bar.value() - delta
        if bar.minimum() <= new_val <= bar.maximum():
            if sc._horizontal:
                self.scrollContentsBy(-delta, 0)
            else:
                self.scrollContentsBy(0, -delta)
        else:
            bar.setValue(max(bar.minimum(), min(bar.maximum(), new_val)))

    def _scroll_orth_axis_by(self, delta: int) -> None:
        """Scroll along the row/column axis (same path as dragging the scrollbar)."""
        if delta == 0 or self._scene._trace is None:
            return
        bar = (self.verticalScrollBar() if self._scene._horizontal
               else self.horizontalScrollBar())
        new_val = max(bar.minimum(), min(bar.maximum(), bar.value() - delta))
        if new_val != bar.value():
            bar.setValue(new_val)

    def _scroll_time_axis_virt_by(self, delta: int) -> None:
        """Pan the time axis when virtual scroll is active (Qt native delta sign)."""
        if delta == 0 or self._scene._trace is None:
            return
        # delta > 0  -> earlier time; delta < 0 -> later time (matches native bar).
        if delta > 0 and self._virt_scroll_at_trace_start():
            return
        if delta < 0 and self._virt_scroll_at_trace_end():
            return
        new_virt = self._virt_time_scroll_px - delta
        self._apply_virt_time_scroll_px(
            new_virt, sync_bar=True, force_window=True)

    def _wheel_gesture_plan(self, event: QWheelEvent) -> Tuple[bool, int, bool, int]:
        """Return (do_time, time_delta, do_orth, orth_delta) for a wheel/trackpad event.

        Classify by scroll *magnitude* first (pixelDelta with angleDelta fill-in).
        angleDelta is only used when magnitudes tie, so horizontal pans are not
        stolen by small vertical noise and vice versa.
        """
        ad = event.angleDelta()
        dx, dy = self._wheel_pan_deltas(event)
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        horiz = self._scene._horizontal
        if horiz:
            mag_time, mag_orth = (dy, dx) if shift else (dx, dy)
            ad_time, ad_orth = ad.x(), ad.y()
        else:
            mag_time, mag_orth = (dx, dy) if shift else (dy, dx)
            ad_time, ad_orth = ad.y(), ad.x()

        if mag_time == 0 and ad_time != 0:
            mag_time = ad_time // 8
        if mag_orth == 0 and ad_orth != 0:
            mag_orth = ad_orth // 8

        mt, mo = abs(mag_time), abs(mag_orth)
        if mt == 0 and mo == 0:
            return False, 0, False, 0
        # Near trace start/end, prefer orthogonal pans on ambiguous diagonals so
        # corner scrolls (e.g. bottom-right -> top-right) do not drag time axis.
        if (self._virtual_time_scroll_active and mo > 0 and mt > 0
                and (self._virt_scroll_at_trace_start()
                     or self._virt_scroll_at_trace_end())
                and mo >= mt * 0.7):
            return False, 0, True, mag_orth
        if mo > mt:
            return False, 0, True, mag_orth
        if mt > mo:
            return True, mag_time, False, 0
        if abs(ad_orth) > abs(ad_time):
            return False, 0, mag_orth != 0, mag_orth
        return mag_time != 0, mag_time, mag_orth != 0, mag_orth

    def _on_virt_trace_bar_pressed(self) -> None:
        self._virt_bar_dragging = True
        self._refresh_nav_pan_window(force_show=True)

    def _on_virt_trace_bar_released(self) -> None:
        self._virt_bar_dragging = False
        self._sync_virt_trace_bar_from_view()
        self._refresh_nav_pan_window(force_show=True)

    def _on_virt_trace_bar_changed(self, value: int) -> None:
        if not self._virtual_time_scroll_active or self._syncing_virt_bar:
            return
        self._apply_virt_time_scroll_px(
            value * self._virt_scroll_scale,
            force_window=True,
            sync_bar=False,
        )

    def _on_native_time_bar_interaction(self, _value: int = 0) -> None:
        """Native (scene-local) time bar moved by the user."""
        if (self._syncing_time_scrollbar or self._preserve_virt_scroll
                or self._scene._trace is None):
            return
        if self._virtual_time_scroll_active:
            if not self._virt_bar_dragging:
                self._sync_virt_trace_bar_from_view()
            self._after_time_axis_pan(immediate=True)

    def _set_native_time_scroll_local(self, local_px: int) -> bool:
        """Scroll the scene-local time bar to *local_px*. Returns True if it moved."""
        self._sync_native_scene_scrollbar()
        bar = self._native_time_axis_bar()
        target = max(bar.minimum(), min(bar.maximum(), int(local_px)))
        if target == bar.value():
            return False
        self._syncing_time_scrollbar = True
        try:
            bar.setValue(target)
        finally:
            self._syncing_time_scrollbar = False
        if self._scene._horizontal:
            self._reposition_frozen()
        else:
            self._reposition_frozen_top()
        return True

    def _flush_pending_window_shift(self) -> None:
        if self._pending_shift_ns_lo is None:
            return
        ns_lo = self._pending_shift_ns_lo
        self._pending_shift_ns_lo = None
        self._pending_shift_ns_hi = None
        self._apply_virt_time_scroll_px(
            self._virt_px_from_ns_lo(ns_lo), force_window=True)

    def _shift_time_window_to(
        self, ns_lo: float, ns_hi: float, *, force: bool = False,
    ) -> None:
        trace = self._scene._trace
        if trace is None:
            return
        tpp = self._scene._timescale_per_px
        page_px = self._timeline_viewport_px()
        page_ns = page_px * tpp
        edge_ns = max(1, int(page_ns * 0.02))
        max_left_ns = trace.time_max - page_ns
        left_ns = int(round(max(trace.time_min, min(trace.time_max, ns_lo))))
        if (ns_hi >= trace.time_max - edge_ns
                and left_ns >= max_left_ns - edge_ns):
            self._pending_shift_ns_lo = None
            self._pending_shift_ns_hi = None
            self._window_shift_timer.stop()
            self._virt_time_scroll_px = self._clamp_virt_time_scroll_px(
                self._max_virt_time_scroll_px())
            pin_local = self._native_scroll_for_ns_lo(float(max_left_ns))
            self._set_native_time_scroll_local(pin_local)
            if not self._virt_bar_dragging:
                self._push_virt_trace_bar()
            self._after_time_axis_pan(immediate=self._virt_bar_dragging)
            return
        if not force and not self._virt_bar_dragging:
            now_ms = time.monotonic() * 1000.0
            elapsed = now_ms - self._last_window_shift_ms
            if elapsed < _WINDOW_SHIFT_MIN_MS:
                self._pending_shift_ns_lo = float(ns_lo)
                self._pending_shift_ns_hi = float(ns_hi)
                self._after_time_axis_pan()
                if not self._window_shift_timer.isActive():
                    self._window_shift_timer.start(
                        max(1, int(_WINDOW_SHIFT_MIN_MS - elapsed)))
                return
        self._pending_shift_ns_lo = None
        self._pending_shift_ns_hi = None
        self._window_shift_timer.stop()
        self._last_window_shift_ms = time.monotonic() * 1000.0
        margin_ns = max(1, int(page_px * tpp * 0.75))
        sc = self._scene
        sc._ns_range_hint = (
            max(trace.time_min, left_ns - margin_ns),
            min(trace.time_max, int(round(ns_hi)) + margin_ns),
        )
        sc._virt_jump_origin_ns = left_ns
        self._virt_scroll_rebuild = True
        try:
            sc.rebuild()
        finally:
            self._virt_scroll_rebuild = False
        self._virt_time_scroll_px = self._virt_px_from_ns_lo(float(left_ns))
        self._set_native_time_scroll_local(self._native_scroll_for_ns_lo(float(left_ns)))
        if not self._virt_bar_dragging:
            self._push_virt_trace_bar()
        self._pan_timer.stop()
        self._pan_heartbeat.stop()
        self._after_time_axis_pan(immediate=self._virt_bar_dragging)

    def _pan_time_axis_px(self, step_px: int) -> None:
        """Scroll the time axis by *step_px* (positive = forward along time)."""
        if step_px == 0 or self._scene._trace is None:
            return
        if self._virtual_time_scroll_active:
            self._scroll_time_axis_virt_by(-step_px)
        else:
            self._scroll_time_axis_native(-step_px)

    def _navigate_time_to_ns(self, ns: int, orth_scene: Optional[float] = None) -> None:
        """Center the time axis on *ns*, preserving the orthogonal scroll position."""
        if self._scene._trace is None:
            return
        trace = self._scene._trace
        ns = max(trace.time_min, min(trace.time_max, int(ns)))
        if self._should_use_virtual_scroll():
            if not self._virtual_time_scroll_active:
                self._set_virtual_scroll_enabled(True)
            vp_center = self.viewport().rect().center()
            half_off = self._timeline_offset_px(vp_center)
            ns_lo = float(ns) - half_off * self._scene._timescale_per_px
            self._apply_virt_time_scroll_px(self._virt_px_from_ns_lo(ns_lo))
            return
        new_coord = self._scene.ns_to_scene_coord(ns)
        if orth_scene is None:
            vp_cur = self.mapToScene(self.viewport().rect().center())
            orth_scene = vp_cur.y() if self._scene._horizontal else vp_cur.x()
        if self._scene._horizontal:
            self.centerOn(new_coord, orth_scene)
        else:
            self.centerOn(orth_scene, new_coord)

    def _has_scroll_overflow(self) -> bool:
        """True when the viewport can scroll on either axis."""
        vbar = self.verticalScrollBar()
        if self._virtual_time_scroll_active:
            h_ok = self._virt_trace_bar.maximum() > self._virt_trace_bar.minimum()
        else:
            hbar = self._native_time_axis_bar()
            h_ok = hbar.maximum() > hbar.minimum()
        return h_ok or vbar.maximum() > vbar.minimum()

    def _navigator_eligible(self) -> bool:
        """True when the navigator minimap should be shown."""
        if self._has_scroll_overflow():
            return True
        trace = self._scene._trace
        if trace is None:
            return False
        at_fit_limit = (
            math.isfinite(self._scene._timescale_per_px_fit)
            and self._scene._timescale_per_px >= self._scene._timescale_per_px_fit * 0.999
        )
        return self._fit_mode or at_fit_limit

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
        self._update_label_grip_geometry()

    def _update_label_grip_geometry(self) -> None:
        """Hide the legacy viewport QWidget grip (scene-frozen grip is used instead)."""
        self._label_grip.hide()

    def _apply_label_width_drag(self, new_w: int) -> None:
        """Live label-column resize during splitter drag."""
        self._scene.set_label_width(int(new_w))
        if self._scene._horizontal:
            self._reposition_frozen()
            if self._fit_mode and self._scene._trace is not None:
                self._scene.fit_to_width(self._fit_viewport_size())
                self.zoom_changed.emit(self._scene.timescale_per_px)
        else:
            self._reposition_frozen_top()
        self._update_label_grip_geometry()
        self.label_width_resizing.emit(int(self._scene._label_width))

    def _finish_label_width_drag(self) -> None:
        """Commit label-column width after splitter drag."""
        self.label_width_changed.emit(int(self._scene._label_width))
        _HoverCursor.hide(Qt.CursorShape.SizeHorCursor)
        _HoverCursor.hide(Qt.CursorShape.SizeVerCursor)

    def _set_view_hover_cursor(self, shape: Optional[Qt.CursorShape]) -> None:
        if shape is None:
            _HoverCursor.hide()
        else:
            _HoverCursor.show(shape)

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
        self._navigate_time_to_ns(ns)
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
        self._update_label_grip_geometry()
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

    def _cancel_pending_zoom(self) -> None:
        """Drop coalesced wheel/toolbar zoom so it cannot undo Fit / 1:1."""
        self._zoom_timer.stop()
        self._zoom_accum = 1.0
        self._zoom_anchor_pos = None
        self._pinch_accum = 1.0

    def _prepare_full_trace_window(self) -> None:
        """Leave virtual sliding-window mode and load the full trace span."""
        self._window_shift_timer.stop()
        self._pending_shift_ns_lo = None
        self._pending_shift_ns_hi = None
        self._virt_time_scroll_px = 0.0
        self._zoom_reanchor_pending = False
        self._preserve_virt_scroll = False
        self._set_virtual_scroll_enabled(False)
        sc = self._scene
        sc._ns_range_hint = None
        sc._virt_jump_origin_ns = None
        trace = sc._trace
        if trace is not None:
            sc._scene_origin_ns = trace.time_min
            sc._ns_range_hint = (trace.time_min, trace.time_max)

    def zoom_fit(self) -> None:
        self._cancel_pending_zoom()
        self._fit_mode = True
        self._prepare_full_trace_window()
        self._scene.fit_to_width(self._fit_viewport_size())
        # Ensure the view transform is identity: all zoom is handled at the
        # scene level (timescale_per_px) so there must be no view-level scale active.
        # fitInView() would set a persistent QTransform that is not needed here.
        self.resetTransform()
        bar = self._native_time_axis_bar()
        bar.setValue(bar.minimum())
        self.zoom_changed.emit(self._scene.timescale_per_px)
        self._show_nav()

    def zoom_1to1(self) -> None:
        """Set zoom to exactly _TIMESCALE_PER_PX_DEFAULT ns/px, scrolling to trace start when in fit mode."""
        if self._scene._trace is None:
            return
        self._cancel_pending_zoom()
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
        if self._should_use_virtual_scroll():
            self._navigate_time_to_ns(center_ns, orth_scene=scene_pt.y() if self._scene._horizontal else scene_pt.x())
        elif self._scene._horizontal:
            self.centerOn(new_coord, scene_pt.y())
        else:
            self.centerOn(scene_pt.x(), new_coord)

    def _capture_pixmap(self) -> Tuple[QPixmap, float]:
        """Capture the current visible scene content as a QPixmap."""
        vp = self.viewport()
        vp_rect = vp.rect()
        scene_in_vp = self.mapFromScene(self._scene.sceneRect()).boundingRect()
        content_rect = vp_rect.intersected(scene_in_vp)
        capture_rect = content_rect if not content_rect.isEmpty() else vp_rect
        return _normalize_grab_pixmap(vp.grab(capture_rect))

    def save_image(self, filepath: str) -> None:
        """Capture the current visible scene content as a PNG image.

        QWidget.grab() renders exactly what is on screen.  When the scene is
        smaller than the viewport, QGraphicsView centres it and leaves blank
        margins; we crop those away by computing the scene rect in viewport
        coordinates so the output contains only real content.
        """
        pixmap, dpr = self._capture_pixmap()
        if not _save_snapshot_png(pixmap, filepath, dpr):
            raise OSError(f"QPixmap.save() failed for path: {filepath}")

    def copy_image_to_clipboard(self) -> Optional[str]:
        """Copy the current visible scene content as a PNG image to the clipboard."""
        pixmap, dpr = self._capture_pixmap()
        return _copy_pixmap_to_clipboard(pixmap, dpr)

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
            if self._should_use_virtual_scroll() and not orth_out_of_view:
                vp_center_pt = self.viewport().rect().center()
                vp_scene = self.mapToScene(vp_center_pt)
                orth_keep = vp_scene.y() if sc._horizontal else vp_scene.x()
                self._reposition_time_at_viewport(
                    target_ns, vp_center_pt, orth_scene=orth_keep)
            elif sc._horizontal:
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

    def _time_axis_step_px(self) -> int:
        horiz = self._scene._horizontal
        return max(1, int(
            (self.viewport().width() if horiz else self.viewport().height()) * 0.20))

    def _orth_axis_step_px(self) -> int:
        horiz = self._scene._horizontal
        return max(1, int(
            (self.viewport().height() if horiz else self.viewport().width()) * 0.20))

    def _pan_orth_axis_px(self, step_px: int) -> None:
        if step_px == 0:
            return
        self._scroll_orth_axis_by(-step_px)

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
            time_fwd, time_back = Qt.Key.Key_Right, Qt.Key.Key_Left
            row_fwd,  row_back  = Qt.Key.Key_Down,  Qt.Key.Key_Up
        else:
            time_fwd, time_back = Qt.Key.Key_Down,  Qt.Key.Key_Up
            row_fwd,  row_back  = Qt.Key.Key_Right, Qt.Key.Key_Left

        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            is_back = (key == Qt.Key.Key_Backtab) or bool(mods & Qt.KeyboardModifier.ShiftModifier)
            self._cycle_highlighted_task(not is_back)
            event.accept()
            return

        if key in (time_fwd, time_back):
            if mods & Qt.KeyboardModifier.ShiftModifier and sc._trace is not None:
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

                    self._navigate_time_to_ns(target)
            else:
                self._pan_time_axis_px(
                    self._time_axis_step_px() if key == time_fwd
                    else -self._time_axis_step_px())
            event.accept()
            return

        if key in (row_fwd, row_back):
            step = self._orth_axis_step_px()
            self._pan_orth_axis_px(step if key == row_fwd else -step)
            event.accept()
            return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        # Releasing Ctrl mid-drag hides the measure-ruler even if the mouse
        # button is still held down.
        if (not event.isAutoRepeat()
                and event.key() == Qt.Key.Key_Control
                and self._measure_press_ns is not None):
            self._measure_press_ns = None
            self._scene.clear_measure_ruler()
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self._set_view_hover_cursor(None)
            event.accept()
            return
        super().keyReleaseEvent(event)

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
        self._navigate_time_to_ns(center_ns)

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
        self._navigate_time_to_ns(center_ns, orth_scene=orth)

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
        if event.button() == Qt.MouseButton.LeftButton and self._scene._trace is not None:
            if self._scene._horizontal:
                in_resize_zone = abs(event.position().x() - lw) <= self._LABEL_RESIZE_ZONE
            else:
                in_resize_zone = abs(event.position().y() - lw) <= self._LABEL_RESIZE_ZONE
            if in_resize_zone:
                self._auto_fit_label_column()
                event.accept()
                return

        if event.button() != Qt.MouseButton.LeftButton or self._scene._trace is None:
            super().mouseDoubleClickEvent(event)
            return
        scene_pt = self.mapToScene(event.position().toPoint())
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
        self._update_label_grip_geometry()
        self.label_width_changed.emit(int(sc._label_width))

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
        if self._scene._trace is not None:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._press_pos = event.position().toPoint()
        self._press_btn = event.button()

        if event.button() == Qt.MouseButton.MiddleButton:
            if self._scene._trace is not None:
                scene_pt = self.mapToScene(event.position().toPoint())
                coord = scene_pt.x() if self._scene._horizontal else scene_pt.y()
                self._mid_press_ns = self._scene.scene_to_ns(coord)
                # Remove any stale band
                if self._mid_band_item is not None:
                    _safe_scene_remove_items(self._scene, [self._mid_band_item])
                    self._mid_band_item = None
                self.setDragMode(QGraphicsView.NoDrag)
                event.accept()
                return

        if event.button() == Qt.MouseButton.LeftButton:
            # --- Ctrl+drag: measure-ruler tool (takes priority over the
            #     resize/cursor/mark drags below so it works anywhere) ---
            if (event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and self._scene._trace is not None):
                lw = self._scene._label_width
                in_label = (event.position().x() < lw if self._scene._horizontal
                            else event.position().y() < lw)
                if not in_label:
                    scene_pt = self.mapToScene(event.position().toPoint())
                    coord = scene_pt.x() if self._scene._horizontal else scene_pt.y()
                    self._measure_press_ns = self._scene.scene_to_ns(coord)
                    self._measure_anchor_coord = (scene_pt.y() if self._scene._horizontal
                                                   else scene_pt.x())
                    self.setDragMode(QGraphicsView.NoDrag)
                    _HoverCursor.show(Qt.CursorShape.CrossCursor)
                    event.accept()
                    return

            # --- Check if we're starting a label-column/row resize drag ---
            if self._scene._horizontal:
                lw = self._scene._label_width
                if abs(event.position().x() - lw) <= self._LABEL_RESIZE_ZONE:
                    self._label_resize_dragging = True
                    self._label_resize_start_x  = event.position().x()
                    self._label_resize_start_w  = lw
                    self.setDragMode(QGraphicsView.NoDrag)
                    _HoverCursor.show(Qt.CursorShape.SizeHorCursor)
                    event.accept()
                    return
            else:
                lw = self._scene._label_width
                if abs(event.position().y() - lw) <= self._LABEL_RESIZE_ZONE:
                    self._label_resize_dragging = True
                    self._label_resize_start_x  = event.position().y()   # reused as start coord
                    self._label_resize_start_w  = lw
                    self.setDragMode(QGraphicsView.NoDrag)
                    _HoverCursor.show(Qt.CursorShape.SizeVerCursor)
                    event.accept()
                    return

            # --- Check if we're starting a cursor drag ---
            scene_pt = self.mapToScene(event.position().toPoint())
            th = self._cursor_drag_threshold
            for idx, cursor_ns in enumerate(self._scene._cursor_times):
                cursor_coord = self._scene.ns_to_scene_coord(cursor_ns)
                press_coord  = scene_pt.x() if self._scene._horizontal else scene_pt.y()
                if abs(press_coord - cursor_coord) <= th:
                    self.pre_change.emit()
                    self._dragging_cursor_idx = idx
                    self.setDragMode(QGraphicsView.NoDrag)
                    _HoverCursor.show(Qt.CursorShape.SizeHorCursor
                                      if self._scene._horizontal
                                      else Qt.CursorShape.SizeVerCursor)
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
                    _HoverCursor.show(Qt.CursorShape.SizeHorCursor
                                      if self._scene._horizontal
                                      else Qt.CursorShape.SizeVerCursor)
                    event.accept()
                    return

            # --- Clicking inside the label column: disable ScrollHandDrag so
            #     _TaskLabelItem (and _CoreHeaderItem) can receive the click.
            #     If the click does NOT land on any _TaskLabelItem, cancel the
            #     current highlight (click on empty label-column area). ---
            lw = self._scene._label_width
            in_vp_label = (event.position().x() < lw if self._scene._horizontal
                           else event.position().y() < lw)
            if in_vp_label:
                self.setDragMode(QGraphicsView.NoDrag)
                scene_pt2 = self.mapToScene(event.position().toPoint())
                hits = [it for it in self._scene.items(scene_pt2)
                        if isinstance(it, _TaskLabelItem)]
                if not hits and self._scene._locked_task is not None:
                    self._scene.set_highlighted_task(None)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        # Dispatch in order of drag states (mutually exclusive):
        #   0. Ctrl+drag measure ruler  (_measure_press_ns is not None)
        #   1. Label-column resize drag  (_label_resize_dragging)
        #   2. Hover cursor near label border  (show resize cursor hint)
        #   3. Middle-button range selection  (_mid_press_ns)
        #   4. Cursor drag  (_dragging_cursor_idx >= 0)
        #   5. Default pan  (super().mouseMoveEvent)
        #      + fallback: clear stale hover if mouse leaves label column

        # Ctrl+drag measure ruler: redraw the double-arrow line + Δtime label
        if self._measure_press_ns is not None:
            scene_pt = self.mapToScene(event.position().toPoint())
            coord    = scene_pt.x() if self._scene._horizontal else scene_pt.y()
            cur_ns   = self._scene.scene_to_ns(coord)
            self._scene._draw_measure_ruler(self._measure_press_ns, cur_ns,
                                             self._measure_anchor_coord)
            # Keep the ghost hover line tracking the mouse during the drag too.
            self._scene._hover_ns = cur_ns
            self._scene._draw_hover_line()
            event.accept()
            return

        # Label-column/row resize drag
        if self._label_resize_dragging:
            if self._scene._horizontal:
                delta = event.position().x() - self._label_resize_start_x
            else:
                delta = event.position().y() - self._label_resize_start_x
            self._apply_label_width_drag(self._label_resize_start_w + delta)
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
            _hover_coord = (self.mapToScene(event.position().toPoint()).x() if self._scene._horizontal
                            else self.mapToScene(event.position().toPoint()).y())
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
                if abs(event.position().x() - lw) <= self._LABEL_RESIZE_ZONE:
                    self._set_view_hover_cursor(Qt.CursorShape.SizeHorCursor)
                elif _near_cursor:
                    self._set_view_hover_cursor(Qt.CursorShape.SplitHCursor)
                elif _near_mark:
                    self._set_view_hover_cursor(Qt.CursorShape.SplitHCursor)
                else:
                    self._set_view_hover_cursor(None)
            else:
                if abs(event.position().y() - lw) <= self._LABEL_RESIZE_ZONE:
                    self._set_view_hover_cursor(Qt.CursorShape.SizeVerCursor)
                elif _near_cursor:
                    self._set_view_hover_cursor(Qt.CursorShape.SplitVCursor)
                elif _near_mark:
                    self._set_view_hover_cursor(Qt.CursorShape.SplitVCursor)
                else:
                    self._set_view_hover_cursor(None)

        # Middle-button drag: update gray selection band
        if self._mid_press_ns is not None:
            scene_pt = self.mapToScene(event.position().toPoint())
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
            scene_pt = self.mapToScene(event.position().toPoint())
            coord    = scene_pt.x() if self._scene._horizontal else scene_pt.y()
            ns       = self._scene.scene_to_ns(coord)
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                ns = self._snap_to_boundary(ns)
            self._scene._cursor_times[self._dragging_cursor_idx] = ns
            self._scene._draw_cursors()
            self._reposition_frozen_top()   # keep cursor labels in the ruler area
            self.cursors_changed.emit(self._scene.cursor_times())
            event.accept()
            return

        if self._dragging_mark_idx >= 0:
            scene_pt = self.mapToScene(event.position().toPoint())
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
                self._set_view_hover_cursor(None)
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
            in_label = (event.position().x() < lw if self._scene._horizontal
                        else event.position().y() < lw)
            if not in_label:
                self._scene.clear_hover()

        # Update mouse-hover ghost line (only when not dragging)
        if (self._scene._trace is not None
                and self._mid_press_ns is None
                and self._dragging_cursor_idx < 0
                and self._dragging_mark_idx < 0
                and not self._label_resize_dragging):
            lw = self._scene._label_width
            in_label = (event.position().x() < lw if self._scene._horizontal
                        else event.position().y() < lw)
            if in_label:
                self._scene.clear_hover_line()
            else:
                try:
                    scene_pt = self.mapToScene(event.position().toPoint())
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
        if self._measure_press_ns is not None:
            self._measure_press_ns = None
            self._scene.clear_measure_ruler()
            self.setDragMode(QGraphicsView.ScrollHandDrag)
        self._set_view_hover_cursor(None)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        # Dispatch in order (first match returns early):
        #   0. Ctrl+drag measure-ruler release -> hide the ruler overlay
        #   1. Middle-button release  -> zoom to dragged range
        #   2. Label-column resize end
        #   3. Cursor drag end
        #   4. Left-click (delta <= threshold) inside timeline  -> place cursor
        #   5. Right-click inside timeline -> remove cursor / clear all

        # Ctrl+drag measure-ruler release: hide the ruler overlay
        if self._measure_press_ns is not None:
            self._measure_press_ns = None
            self._scene.clear_measure_ruler()
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self._set_view_hover_cursor(None)
            event.accept()
            return

        # Middle-button release: zoom to selected range
        if event.button() == Qt.MouseButton.MiddleButton and self._mid_press_ns is not None:
            # Remove band overlay
            if self._mid_band_item is not None:
                _safe_scene_remove_items(self._scene, [self._mid_band_item])
                self._mid_band_item = None
            scene_pt  = self.mapToScene(event.position().toPoint())
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
            self._finish_label_width_drag()
            event.accept()
            return

        if self._dragging_cursor_idx >= 0:
            self._dragging_cursor_idx = -1
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self._set_view_hover_cursor(None)
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
            self._set_view_hover_cursor(None)
            self.mark_moved.emit(kind, mark_id, new_ns)
            event.accept()
            return

        # Restore drag mode if it was temporarily disabled for a label click
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        super().mouseReleaseEvent(event)
        if self._press_pos is None:
            return
        delta = (event.position().toPoint() - self._press_pos).manhattanLength()
        if delta <= self._drag_threshold:
            # Use viewport coordinates - label column is always the leftmost
            # _label_width pixels on screen regardless of horizontal scroll.
            lw = self._scene._label_width
            in_vp_label  = (event.position().x()       < lw if self._scene._horizontal
                            else event.position().y()       < lw)
            # Also block when the press originated inside the label column:
            # a tiny drag (<= drag_threshold) from the label into the timeline
            # must not place a cursor.
            press_in_label = (self._press_pos.x() < lw if self._scene._horizontal
                              else self._press_pos.y() < lw)
            if in_vp_label or press_in_label:
                self._press_pos = None
                return
            scene_pt = self.mapToScene(event.position().toPoint())
            coord = scene_pt.x() if self._scene._horizontal else scene_pt.y()
            ns = self._scene.scene_to_ns(coord)
            if event.button() == Qt.MouseButton.LeftButton:
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
                    # Click on ruler or empty area -> place or remove cursor.
                    if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                        ns = self._snap_to_boundary(ns)
                    # Click near an existing cursor removes it (matches web viewer).
                    _removed = False
                    for _ci, _cns in enumerate(self._scene._cursor_times):
                        _cc = self._scene.ns_to_scene_coord(_cns)
                        if abs(_cc - coord) <= self._cursor_drag_threshold:
                            self.pre_change.emit()
                            self._scene.remove_cursor_at_index(_ci)
                            self.cursors_changed.emit(self._scene.cursor_times())
                            self._dbl_click_undo_ns = None
                            _removed = True
                            break
                    if not _removed:
                        # Place cursor immediately; mouseDoubleClickEvent will roll it
                        # back if this click turns out to be the first of a double-click.
                        self.pre_change.emit()
                        self._scene.add_cursor(ns)
                        self.cursors_changed.emit(self._scene.cursor_times())
                        self._dbl_click_undo_ns = ns
            elif event.button() == Qt.MouseButton.RightButton:
                self.pre_change.emit()
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self._scene.clear_cursors()
                else:
                    self._scene.remove_nearest_cursor(ns)
                self.cursors_changed.emit(self._scene.cursor_times())
        self._press_pos = None

    def contextMenuEvent(self, event) -> None:
        # Suppress the context menu when the click lands inside the label column.
        # QContextMenuEvent uses .pos()/.globalPos() - NOT .position() (QMouseEvent only)
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
            menu.addAction(
                _svg_icon("M0 2a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4.414l-2.707 2.707A1 1 0 0 1 0 14.586V2zm2-1a1 1 0 0 0-1 1v10.586L3.293 10.5H14a1 1 0 0 0 1-1V2a1 1 0 0 0-1-1H2z", _icon_color),
                "Ask AI about this event",
                lambda _t=_seg_task, _c=hit_seg.core, _s=hit_seg, _ns=ns: self.ask_ai_event_requested.emit({
                    "task": _task_display_name(_t),
                    "core": _c,
                    "start": _s.start,
                    "stop": _s.end,
                    "ns": _ns,
                })
            )
            menu.addSeparator()

        # Place cursor
        menu.addAction(
            _svg_icon(_IC_CURSOR, _icon_color),
            f"Place cursor here  ({_format_time(ns, self._scene._trace.time_scale, decimals=self._scene._time_decimals) if self._scene._trace else ''})",
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
        if len(self._scene.cursor_times()) >= 2:
            menu.addAction(
                _svg_icon("M0 2a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4.414l-2.707 2.707A1 1 0 0 1 0 14.586V2zm2-1a1 1 0 0 0-1 1v10.586L3.293 10.5H14a1 1 0 0 0 1-1V2a1 1 0 0 0-1-1H2z", _icon_color),
                "Explain this region with AI",
                lambda: self.explain_region_requested.emit()
            )
        if self._scene._trace is not None:
            menu.addSeparator()
            # Bookmark icon - flag/ribbon shape
            menu.addAction(
                _svg_icon("M2 2a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v13.5a.5.5 0 0 1-.74.439L8 13.069l-5.26 2.87A.5.5 0 0 1 2 15.5V2zm2-1a1 1 0 0 0-1 1v12.566l4.74-2.586a.5.5 0 0 1 .48 0L13 14.566V2a1 1 0 0 0-1-1H4z", _icon_color),
                f"Add Bookmark here  ({_format_time(ns, self._scene._trace.time_scale, decimals=self._scene._time_decimals)})",
                lambda: self.bookmark_requested.emit(ns)
            )
            # Annotation icon - pencil/note shape
            menu.addAction(
                _svg_icon("M12.854 0.146a.5.5 0 0 0-.707 0L10.5 1.793 14.207 5.5l1.647-1.646a.5.5 0 0 0 0-.708l-3-3zm.646 6.061L9.793 2.5 3.293 9H3.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.207l6.5-6.5zm-7.468 7.468A.5.5 0 0 1 6 13.5V13h-.5a.5.5 0 0 1-.5-.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.5-.5V10h-.5a.499.499 0 0 1-.175-.032l-.179.178a.5.5 0 0 0-.11.168l-2 5a.5.5 0 0 0 .65.65l5-2a.5.5 0 0 0 .168-.11l.178-.178z", _icon_color),
                f"Add Annotation here  ({_format_time(ns, self._scene._trace.time_scale, decimals=self._scene._time_decimals)})",
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
        menu.exec(event.globalPos())

    # ------------------------------------------------------------------
    # Wheel and touch zoom
    # ------------------------------------------------------------------

    def _apply_native_pinch_zoom(self, event) -> None:
        factor = _native_gesture_zoom_factor(event)
        if factor <= 0.1:
            return
        self._fit_mode = False
        self._do_zoom(factor, _native_gesture_local_pos(event))

    def event(self, event) -> bool:  # noqa: N802
        # macOS delivers pinch gestures to QGraphicsView, not only the viewport.
        try:
            if (event.type() == QEvent.Type.NativeGesture
                    and _is_zoom_native_gesture(event)):
                self._apply_native_pinch_zoom(event)
                return True
            return super().event(event)
        except KeyboardInterrupt:
            return False

    def _wheel_pan_deltas(self, event: QWheelEvent) -> Tuple[int, int]:
        """Return (dx, dy) for pan; macOS trackpad prefers pixelDelta."""
        pd = event.pixelDelta()
        ad = event.angleDelta()
        if pd.x() != 0 or pd.y() != 0:
            # macOS may zero one pixelDelta axis when the time scrollbar has
            # range; recover that axis from angleDelta so vertical row pans work.
            dx = pd.x() if pd.x() != 0 else ad.x() // 8
            dy = pd.y() if pd.y() != 0 else ad.y() // 8
            return dx, dy
        return ad.x() // 8, ad.y() // 8

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            angle  = event.angleDelta().y()
            factor = 1.15 if angle > 0 else 1 / 1.15
            # Accumulate factor; record anchor from the *first* event in the
            # batch so the zoom stays anchored at the initial cursor position.
            self._zoom_accum *= factor
            if self._zoom_anchor_pos is None:
                self._zoom_anchor_pos = event.position().toPoint()
            # Exit fit mode immediately so a resize event that fires inside
            # the 60 ms debounce window does not snap back to fit-to-width.
            self._fit_mode = False
            self._zoom_timer.start()   # restart the debounce window
            event.accept()
        elif self._should_use_virtual_scroll() and self._scene._trace is not None:
            if not self._virtual_time_scroll_active:
                self._set_virtual_scroll_enabled(True)
            do_time, time_d, do_orth, orth_d = self._wheel_gesture_plan(event)
            if do_time and time_d != 0:
                self._scroll_time_axis_virt_by(-time_d)
            if do_orth and orth_d != 0:
                self._scroll_orth_axis_by(orth_d)
                self._pan_timer.start()
            event.accept()
        else:
            super().wheelEvent(event)
            if event.isAccepted():
                self._pan_timer.start()

    def _flush_zoom(self) -> None:
        """Called by the debounce timer: apply all accumulated wheel-zoom at once."""
        factor = self._zoom_accum
        anchor = self._zoom_anchor_pos
        self._zoom_accum       = 1.0
        self._zoom_anchor_pos  = None
        # Fit/1:1 cancel the timer; ignore a stale timeout that already queued.
        if factor != 1.0 and not self._fit_mode:
            self._do_zoom(factor, anchor)

    def eventFilter(self, obj, e) -> bool:
        """Intercept native pinch-zoom gestures delivered to the viewport."""
        virt_bar = getattr(self, "_time_scroll_bar", None)
        if virt_bar is None:
            virt_bar = getattr(self, "_time_scroll_internal", None)
        if virt_bar is not None and obj is virt_bar and e.type() == QEvent.Type.Wheel:
            self.wheelEvent(e)
            return True
        if e.type() == QEvent.Type.Wheel:
            we = e
            if not (we.modifiers() & Qt.KeyboardModifier.ControlModifier):
                if (self._should_use_virtual_scroll()
                        and self._scene._trace is not None):
                    if obj is self.viewport() or obj is self._native_time_axis_bar():
                        self.wheelEvent(we)
                        return True
        if obj is self.viewport():
            if e.type() == QEvent.Type.Leave:
                # Mouse left the viewport - ensure any hover highlight is cleared
                self._scene.clear_hover()
                return False
            if e.type() == QEvent.Type.NativeGesture and _is_zoom_native_gesture(e):
                self._apply_native_pinch_zoom(e)
                return True
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

        prev_timescale_per_px = self._scene.timescale_per_px
        trace = self._scene._trace
        anchor_ns = center_ns
        if trace is not None:
            target_timescale = prev_timescale_per_px / factor
            target_timescale = max(
                self._scene._timescale_per_px_default,
                min(target_timescale, self._scene._timescale_per_px_fit),
            )
            if target_timescale != prev_timescale_per_px:
                anchor_off_px = self._timeline_offset_px(vp_pos)
                anchor_left_ns = int(anchor_ns - anchor_off_px * target_timescale)
                anchor_left_ns = max(trace.time_min, min(trace.time_max, anchor_left_ns))
                vis_ns = max(1, int(self._timeline_viewport_px() * target_timescale))
                margin_ns = max(vis_ns // 2, (trace.time_max - trace.time_min) // 100)
                hint_lo = max(trace.time_min, anchor_left_ns - margin_ns)
                hint_hi = min(trace.time_max, anchor_left_ns + vis_ns + margin_ns)
                if hint_hi > hint_lo:
                    self._scene._ns_range_hint = (hint_lo, hint_hi)
                if target_timescale < self._scene._timescale_per_px_fit * 0.999:
                    self._scene._virt_jump_origin_ns = anchor_left_ns
        self._zoom_reanchor_pending = True
        try:
            self._scene.zoom(factor)
            if self._scene.timescale_per_px == prev_timescale_per_px:
                return  # already at zoom limit - nothing changed, skip scroll/emit
            if self._should_use_virtual_scroll():
                self._set_virt_from_time_anchor(anchor_ns, vp_pos)
            self.zoom_changed.emit(self._scene.timescale_per_px)

            # Keep the zoom anchor fixed on screen (virt scroll or centerOn).
            cur_scene_center = self.mapToScene(vp_center)
            if is_horiz:
                orth = cur_scene_center.y()
            else:
                orth = cur_scene_center.x()
            self._reposition_time_at_viewport(
                anchor_ns, vp_pos, orth_scene=orth, force_window=True)
            self._nav_zoom_timer.start()
        finally:
            self._zoom_reanchor_pending = False
            if trace is not None:
                self._scene._virt_jump_origin_ns = None

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
                if sc._core_is_expanded(core):
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
                p.setBrush(Qt.BrushStyle.NoBrush)
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
        p.setPen(Qt.PenStyle.NoPen)

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
                            p.setPen(Qt.PenStyle.NoPen)
                    else:
                        p.setPen(Qt.PenStyle.NoPen)
                        p.setBrush(QBrush(_wf_dot_col))
                        for ev in evs:
                            x1 = (ev.time - tr.time_min) / time_span * W
                            p.drawEllipse(QPointF(x1, y + rh / 2), 2.0, 2.0)
                else:
                    # Collapsed: draw each event with its per-note colour,
                    # matching the main view's _sti_color(ev.note) per event.
                    p.setPen(Qt.PenStyle.NoPen)
                    for ev in evs:
                        x1 = (ev.time - tr.time_min) / time_span * W
                        p.setBrush(QBrush(_sti_color(ev.note)))
                        p.drawEllipse(QPointF(x1, y + rh / 2), 2.0, 2.0)

        # Static border
        try:
            p.setPen(QPen(nav_border, 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
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
        m = self._nav_popup_metrics()
        vx1, vy1, vw, vh = m['vx1'], m['vy1'], m['vw'], m['vh']

        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing, False)
        try:
            p.setPen(QPen(QColor(255, 140, 0), 1.5))
            p.setBrush(QBrush(QColor(255, 140, 0, 35)))
            p.drawRect(QRectF(vx1, vy1, vw, vh))
        finally:
            p.end()
        return pix

    @staticmethod
    def _nav_strip_rect(
        total_main: float, visible_main: float, scroll_pos: float, strip_area_h: float,
    ) -> Tuple[float, float]:
        """Map main-view orth scroll to overview strip position/size (web parity)."""
        area_h = max(1.0, strip_area_h)
        if total_main <= visible_main or total_main <= 0:
            return 0.0, area_h
        size = max(2.0, (visible_main / total_main) * area_h)
        max_pos = max(0.0, area_h - size)
        pos = (scroll_pos / (total_main - visible_main)) * max_pos
        return pos, size

    def _nav_orth_scroll_state(self) -> Tuple[float, float, float]:
        """Return (scroll_pos, total_main, visible_main) for the orth axis (tasks + STI)."""
        sc = self._scene
        vp_rect = self.viewport().rect()
        scene_rect = sc.sceneRect()
        if sc._horizontal:
            orth_scene = self.mapToScene(QPoint(0, RULER_HEIGHT)).y()
            scroll_pos = max(0.0, orth_scene - RULER_HEIGHT)
            total_main = max(1.0, float(scene_rect.height()) - RULER_HEIGHT)
            visible_main = max(1.0, float(vp_rect.height()) - RULER_HEIGHT)
        else:
            orth_scene = self.mapToScene(QPoint(RULER_WIDTH, 0)).x()
            scroll_pos = max(0.0, orth_scene - RULER_WIDTH)
            total_main = max(1.0, float(scene_rect.width()) - RULER_WIDTH)
            visible_main = max(1.0, float(vp_rect.width()) - RULER_WIDTH)
        return scroll_pos, total_main, visible_main

    def _set_nav_orth_scroll_pos(self, target: float) -> None:
        """Scroll the orth axis to *target* (px below ruler / right of ruler column)."""
        current, _, _ = self._nav_orth_scroll_state()
        delta = int(round(target - current))
        if delta != 0:
            self._scroll_orth_axis_by(-delta)

    def _nav_popup_metrics(self) -> dict:
        """Return navigator minimap geometry for painting and interaction."""
        W = float(_NavigatorPopup.W)
        H = float(_NavigatorPopup.H)
        sc = self._scene
        tr = sc._trace
        # Full minimap height (task strip + STI); indicator moves over entire thumbnail.
        strip_h = H

        if tr is None:
            return {
                'W': W, 'H': H, 'strip_h': strip_h, 'time_span': 1, 'vis_span_ns': 1,
                'vx1': 0.0, 'vy1': 0.0, 'vw': W, 'vh': strip_h,
                'scroll_pos': 0.0, 'total_main': 1.0, 'visible_main': 1.0,
            }

        time_span = max(tr.time_max - tr.time_min, 1)
        vis_span_ns = self._visible_time_span_ns()
        vp_r = self.viewport().rect()
        if sc._horizontal:
            lo_coord = self.mapToScene(vp_r.topLeft()).x()
            hi_coord = self.mapToScene(vp_r.topRight()).x()
        else:
            lo_coord = self.mapToScene(vp_r.topLeft()).y()
            hi_coord = self.mapToScene(vp_r.bottomLeft()).y()
        lw = sc._label_width
        origin = sc._scene_origin_ns
        act_ns_lo = origin + int((lo_coord - lw) * sc._timescale_per_px)
        act_ns_hi = origin + int((hi_coord - lw) * sc._timescale_per_px)
        act_ns_lo = max(tr.time_min, min(tr.time_max, act_ns_lo))
        act_ns_hi = max(tr.time_min, min(tr.time_max, act_ns_hi))
        page_ns = max(1, int(self._timeline_viewport_px() * sc._timescale_per_px))
        if act_ns_lo >= act_ns_hi:
            act_ns_lo, act_ns_hi = _fix_collapsed_time_ns_range(
                act_ns_lo, act_ns_hi, lo_coord, hi_coord,
                tr.time_min, tr.time_max, sc._timescale_per_px,
                min_span_ns=page_ns)
        vx1 = (act_ns_lo - tr.time_min) / time_span * W
        vx2 = (act_ns_hi - tr.time_min) / time_span * W

        scroll_pos, total_main, visible_main = self._nav_orth_scroll_state()
        vy1, vy_h = self._nav_strip_rect(
            total_main, visible_main, scroll_pos, strip_h)

        vx1 = max(0.0, min(W, vx1))
        vx2 = max(0.0, min(W, vx2))
        vy1 = max(0.0, min(strip_h, vy1))
        vy_h = min(strip_h - vy1, vy_h)
        vw = max(1.5, vx2 - vx1)
        vh = max(1.5, vy_h)

        return {
            'W': W, 'H': H, 'strip_h': strip_h, 'time_span': time_span,
            'vis_span_ns': vis_span_ns,
            'vx1': vx1, 'vy1': vy1, 'vw': vw, 'vh': vh,
            'scroll_pos': scroll_pos, 'total_main': total_main,
            'visible_main': visible_main,
        }

    def _nav_popup_apply_from_indicator_pos(self, vx1: float, vy1: float) -> None:
        """Move the main view so the nav indicator sits at *vx1*, *vy1*."""
        sc = self._scene
        tr = sc._trace
        if tr is None:
            return
        m = self._nav_popup_metrics()
        W = m['W']
        vw, vh = m['vw'], m['vh']
        strip_h = m['strip_h']
        vx1 = max(0.0, min(W - vw, vx1))
        vy1 = max(0.0, min(strip_h - vh, vy1))

        scrollable_w = max(W - vw, 1.0)
        ratio_x = vx1 / scrollable_w
        target_lo_ns = tr.time_min + int(ratio_x * max(0, m['time_span'] - m['vis_span_ns']))
        target_center_ns = target_lo_ns + m['vis_span_ns'] // 2
        self._navigate_time_to_ns(target_center_ns)

        scrollable_h = max(strip_h - vh, 1.0)
        ratio_y = vy1 / scrollable_h
        target_scroll = ratio_y * max(0.0, m['total_main'] - m['visible_main'])
        self._set_nav_orth_scroll_pos(target_scroll)

        self._refresh_nav_pan_window(force_show=True)

    def _nav_popup_jump_to(self, cx: float, cy: float) -> None:
        """Jump the main timeline to the time / scroll under a nav click."""
        sc = self._scene
        tr = sc._trace
        if tr is None:
            return
        m = self._nav_popup_metrics()
        W = m['W']
        strip_h = m['strip_h']
        ratio_x = max(0.0, min(1.0, cx / max(W, 1.0)))
        ratio_y = max(0.0, min(1.0, cy / max(strip_h, 1.0)))

        target_lo_ns = tr.time_min + int(ratio_x * max(0, m['time_span'] - m['vis_span_ns']))
        target_center_ns = target_lo_ns + m['vis_span_ns'] // 2
        self._navigate_time_to_ns(target_center_ns)

        target_scroll = ratio_y * max(0.0, m['total_main'] - m['visible_main'])
        self._set_nav_orth_scroll_pos(target_scroll)

        self._refresh_nav_pan_window(force_show=True)

    def _nav_popup_handle_press(self, cx: float, cy: float,
                                popup: '_NavigatorPopup') -> bool:
        """Begin nav drag or jump on click."""
        m = self._nav_popup_metrics()
        rect = QRectF(m['vx1'], m['vy1'], m['vw'], m['vh'])
        if rect.contains(cx, cy):
            popup._begin_nav_drag(cx - m['vx1'], cy - m['vy1'])
            self._nav_hide_timer.stop()
            return True
        self._nav_popup_jump_to(cx, cy)
        return True

    def _nav_popup_handle_drag(self, cx: float, cy: float,
                               grab_x: float, grab_y: float) -> None:
        """Drag the nav viewport indicator."""
        self._nav_popup_apply_from_indicator_pos(cx - grab_x, cy - grab_y)
        self._nav_hide_timer.stop()

    def _nav_popup_handle_release(self) -> None:
        """End nav indicator drag."""
        self._nav_hide_timer.start()

    def _show_nav(self) -> None:
        """Show the navigator popup if the viewport is scrolled while content overflows."""
        self._refresh_nav_pan_window(force_show=True)

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        """Called by Qt on every scroll - reposition frozen label-column items."""
        if self._syncing_time_scrollbar:
            super().scrollContentsBy(dx, dy)
            if dx != 0:
                self._reposition_frozen()
            if dy != 0:
                self._reposition_frozen_top()
            return
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
            if (self._virtual_time_scroll_active and self._scene._trace is not None
                    and not self._virt_bar_dragging):
                time_d = dx if self._scene._horizontal else dy
                if time_d != 0:
                    if (not self._preserve_virt_scroll
                            and not self._virt_scroll_at_trace_start()
                            and not self._virt_scroll_at_trace_end()):
                        self._sync_virt_trace_bar_from_view()
                    self._after_time_axis_pan()
                    return
        if self._nav_popup.isVisible():
            self._nav_popup.reposition()

    def _on_scene_rebuilt_scroll(self) -> None:
        """Reset scene-local scroll after sliding-window origin shift."""
        self._frozen_last_scene_left = None
        self._frozen_last_scene_top = None
        if self._fit_mode:
            return
        if self._virt_scroll_rebuild:
            pass
        elif self._zoom_reanchor_pending:
            pass
        elif self._virtual_time_scroll_active:
            if self._preserve_virt_scroll:
                prev = self._preserved_virt_scroll_px
                self._preserve_virt_scroll = False
                self._virt_time_scroll_px = self._clamp_virt_time_scroll_px(prev)
                self._sync_native_scene_scrollbar()
                bar = self._native_time_axis_bar()
                ideal = self._native_scroll_for_ns_lo(
                    self._ns_lo_from_virt_px(self._virt_time_scroll_px))
                target = max(bar.minimum(), min(bar.maximum(), ideal))
                self._set_native_time_scroll_local(target)
            else:
                self._virt_time_scroll_px = self._clamp_virt_time_scroll_px(
                    self._virt_time_scroll_px)
                local = self._native_scroll_for_ns_lo(
                    self._ns_lo_from_virt_px(self._virt_time_scroll_px))
                self._set_native_time_scroll_local(local)
        else:
            if self._scene._horizontal:
                self.horizontalScrollBar().setValue(0)
            else:
                self.verticalScrollBar().setValue(0)
        if self._virtual_time_scroll_active:
            self._sync_native_scene_scrollbar()
            self._update_virt_trace_bar_range()
            if not self._zoom_reanchor_pending:
                self._push_virt_trace_bar()

    def _sync_timeline_column_clip(self) -> None:
        """Clip timeline row backgrounds / grid to the viewport splitter edge."""
        sc = self._scene
        if not sc._horizontal or sc._trace is None or self._virt_scroll_rebuild:
            return
        lw = float(sc._label_width)
        scroll = self.mapToScene(QPoint(0, 0)).x()
        tx = lw + scroll
        total_w = sc.sceneRect().width()
        tw = max(0.0, total_w - tx)
        stripe = sc._row_stripe_item
        if stripe is not None:
            stripe.set_timeline_left(tx)
        for rect_item in sc._timeline_bg_rects:
            r = rect_item.rect()
            rect_item.setRect(QRectF(tx, r.y(), tw, r.height()))
        for sep_line in sc._timeline_sep_lines:
            ln = sep_line.line()
            sep_line.setLine(tx, ln.y1(), total_w, ln.y2())
        grid = sc._ruler_grid_item
        if grid is not None:
            grid.set_grid_clip_x(tx)

    def _reposition_frozen(self) -> None:
        """Move all frozen label-column scene items so they stay at the left edge."""
        if not self._scene._frozen_items:
            return
        if self._virt_scroll_rebuild:
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
            if isinstance(item, _LabelColumnGripItem):
                item.setX(scene_left + self._scene._label_width)
            else:
                item.setX(scene_left + orig_x)
        self._sync_timeline_column_clip()

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

    def _on_vertical_scroll_changed(self, _value: int) -> None:
        """Re-pin ruler-band overlays after vertical (row-axis) scroll."""
        if not self._scene._horizontal:
            return
        self._frozen_last_scene_top = None
        self._reposition_frozen_top()

    def _on_horizontal_scroll_changed(self, _value: int) -> None:
        """Re-pin overlays after horizontal scroll in vertical-layout mode."""
        if self._scene._horizontal:
            return
        self._frozen_last_scene_left = None
        self._frozen_last_scene_top = None
        self._reposition_frozen()
        self._reposition_frozen_top()

    # ------------------------------------------------------------------
    # Resize handling
    # ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        """Reflow the timeline on every resize to preserve the current zoom ratio."""
        super().resizeEvent(event)
        self._update_label_grip_geometry()
        win = self.window()
        splitting = getattr(win, "_cpu_splitter_resizing", False)
        if not splitting:
            self._position_virt_trace_bar()
        self._nav_popup.reposition()
        if self._scene._trace is not None and not splitting:
            self._resize_timer.start()

    def _on_cpu_load_pane_toggled(self) -> None:
        """Layout-only update after CPU-load show/hide (web ``v-if`` parity).

        Horizontal layout: time-axis width is unchanged, so never rebuild the
        QGraphicsScene here.  Vertical layout uses the normal fit/zoom path.
        """
        if self._scene._trace is None:
            return
        if not self._scene._horizontal:
            self._on_resize_timeout()
            return
        self._apply_orth_only_resize_chrome()

    def _apply_orth_only_resize_chrome(self) -> None:
        """Reposition frozen chrome after a height-only viewport change.

        Does not call ``rebuild()`` and does not force ``viewport().update()`` —
        a forced full paint here made CPU-load toggle slower than letting Qt
        expose only the damaged region.
        """
        if self._scene._trace is None:
            return
        vsize = self._fit_viewport_size()
        time_span = max(
            self._scene._trace.time_max - self._scene._trace.time_min, 1)
        avail = max(vsize - self._scene._label_width, 100)
        self._scene._timescale_per_px_fit = time_span / avail
        self._reposition_frozen()
        self._reposition_frozen_top()
        self._update_virt_trace_bar_range()
        if self._virtual_time_scroll_active:
            if self._fit_mode:
                self._push_virt_trace_bar()
            else:
                self._apply_virt_time_scroll_px(self._virt_time_scroll_px)

    def _on_resize_timeout(self) -> None:
        """Debounced resize handler.

        Fit mode  -> rebuild at the new fit zoom so the trace always fills
                    the viewport (no blank space, no scrollbar).
        Zoom mode -> timescale_per_px is NEVER touched.  Only update _timescale_per_px_fit
                    so the zoom-out clamp reflects the new viewport size, and
                    reposition the frozen label column items.

        Orthogonal-only resizes (CPU-load show/hide in horizontal layout) leave
        the time-axis pixel size unchanged, so fit mode must NOT force a full
        scene rebuild.
        """
        if self._scene._trace is None:
            return
        win = self.window()
        if getattr(win, "_cpu_splitter_resizing", False):
            self._reposition_frozen()
            self._reposition_frozen_top()
            self._update_virt_trace_bar_range()
            if self._virtual_time_scroll_active:
                self._push_virt_trace_bar()
            return
        vsize = self._fit_viewport_size()
        time_span = max(
            self._scene._trace.time_max - self._scene._trace.time_min, 1)
        avail   = max(vsize - self._scene._label_width, 100)
        new_fit = time_span / avail

        if self._fit_mode:
            if self._virtual_time_scroll_active:
                self._prepare_full_trace_window()
            old_tsp = self._scene._timescale_per_px
            self._scene._timescale_per_px_fit = new_fit
            self._scene._timescale_per_px     = new_fit
            timescale_changed = (
                abs(old_tsp - new_fit) > max(1e-12, abs(new_fit) * 1e-9))
            if timescale_changed:
                self._scene.rebuild()
                self.resetTransform()
                self.zoom_changed.emit(self._scene.timescale_per_px)
                self._show_nav()
            else:
                # Height-only (or otherwise time-axis-unchanged) resize.
                self._apply_orth_only_resize_chrome()
        else:
            # Zoom mode: preserve zoom level and canonical scroll position.
            self._scene._timescale_per_px_fit = new_fit
            # Horizontal: height-only changes are chrome-only.  Vertical: the
            # time axis is height, so orth-fill / coverage rebuilds still apply.
            if (not self._scene._horizontal) and self._needs_orth_fill_rebuild():
                self._scene.rebuild()
            self._reposition_frozen()
            self._reposition_frozen_top()
            self._update_virt_trace_bar_range()
            if self._virtual_time_scroll_active:
                self._apply_virt_time_scroll_px(self._virt_time_scroll_px)

    def _needs_orth_fill_rebuild(self) -> bool:
        """True when the scene should grow/shrink to match viewport fill rules."""
        sc = self._scene
        if sc._trace is None:
            return False
        vp = sc._viewport_orth_extent()
        if vp <= 0:
            return False
        content = getattr(sc, "_orth_content_px", None)
        if content is None:
            rect = sc.sceneRect()
            content = rect.height() if sc._horizontal else rect.width()
        desired = sc._finalize_orth_size(float(content))
        rect = sc.sceneRect()
        current = rect.height() if sc._horizontal else rect.width()
        return abs(desired - current) > 1.0

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
        if self._pending_shift_ns_lo is not None:
            self._flush_pending_window_shift()
        if self._needs_rebuild_for_scroll(strict=True):
            self._last_pan_rebuild_ms = time.monotonic() * 1000.0
            self._scene.rebuild()
        if self._navigator_eligible():
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
            lo_coord, hi_coord = self._timeline_viewport_time_coords()
            orth_lo = self.mapToScene(vp_rect.topLeft()).y()
            orth_hi = self.mapToScene(vp_rect.bottomLeft()).y()
        else:
            lo_coord, hi_coord = self._timeline_viewport_time_coords()
            orth_lo = self.mapToScene(vp_rect.topLeft()).x()
            orth_hi = self.mapToScene(vp_rect.topRight()).x()

        ns_lo = max(t_min, min(t_max, self._scene._scene_origin_ns + int((lo_coord - lw) * timescale_per_px)))
        ns_hi = max(t_min, min(t_max, self._scene._scene_origin_ns + int((hi_coord - lw) * timescale_per_px)))

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
        # Virtual scroll slides the loaded window explicitly via _shift_time_window_to.
        if not self._virtual_time_scroll_active:
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
