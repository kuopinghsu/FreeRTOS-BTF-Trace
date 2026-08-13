"""BTF Viewer — stats module (source). Do not edit btf_viewer.py; run make bundle."""
from __future__ import annotations

from ._imports import *  # noqa: F403,F401
from .config import *  # noqa: F403,F401
from .config import (  # private symbols are not pulled in by import *
    _IC_EXPORT_CSV,
    _IC_PIN,
    _IC_PIN_FILLED,
    _IC_REFRESH,
    _IC_SECTIONS_COLLAPSE,
    _IC_SECTIONS_EXPAND,
    _IC_SECTIONS_RESET_ORDER,
    _application_ui_font,
    _pixmap_from_embedded_app_icon,
    _stats_chevron_icon,
    _svg_icon,
    _svg_icon_markup,
    _svg_pixmap,
    _ui_font_stylesheet_size,
    default_stats_section_order,
    is_default_stats_section_order,
    move_stats_section,
    normalize_stats_pins,
    normalize_stats_section_order,
)
from .html_report import btf_html_report_document
from .parser import *  # noqa: F403,F401
from .parser import (  # private symbols are not pulled in by import *
    _gini_coefficient,
    _core_util_stddev,
    _concurrency_level_plot_points,
    _concurrent_core_active_rows,
    _dispatch_latency_by_mk,
    _dispatch_latency_plot_points,
    _format_plot_point_note,
    _plot_point_mark_ns,
    _switch_overhead_plot_points,
    _switch_overhead_rows,
    _build_corridor_inspector_model,
    _default_corridor_top_pct,
    _trace_has_core_bounce_holds,
    _filter_corridors_by_direction,
    _filter_corridors_by_task_query,
    _corridor_groups_by_source,
    _core_short_name,
    _build_chord_layout,
    _CHORD_ARC_INNER,
    _CHORD_ARC_OUTER,
    _CHORD_GRAD_SOURCE_STOP,
    _chord_hit_ring,
    _chord_ring_geometry,
    _heatmap_bin_range,
    _core_util_pct_rows,
    _task_segs_in_range,
    _chord_label_step,
    _chord_label_visible,
)
from .timeline_util import *  # noqa: F403,F401
from .timeline_util import (  # noqa: F401 — star-import skips leading _
    _format_time, _get_fixed_font_family, _get_sans_font_family, _monospace_font,
)
from .graphics_items import *  # noqa: F403,F401
from .scene import *  # noqa: F403,F401
from .view import *  # noqa: F403,F401
from .ai_case import EXPLAIN_LEVELS
from .ai_investigation import (
    append_migration_burst_anomaly,
    append_wcet_anomaly_finding,
    enrich_findings_with_ids,
)
from .ai_assistant import (  # noqa: F401
    AI_AUTH_API_KEY,
    AI_AUTH_BROWSER,
    AI_AUTH_MODE_LABELS,
    AI_AUTH_NONE,
    AI_PRESET_FIELDS,
    AI_PRESET_KEY_URLS,
    AI_PRESET_OLLAMA,
    AI_PRESETS,
    AI_RESPONSE_LANGUAGES,
    DEFAULT_AI_BASE_URL,
    DEFAULT_AI_MODEL,
    DEFAULT_AI_PRESET,
    DEFAULT_AI_RESPONSE_LANGUAGE,
    AI_MCP_LOG_FILENAME,
    ai_auth_status,
    ai_list_models,
    ai_preset_info,
    ai_preset_signin_label,
    ai_preset_signin_url,
    ai_test_connection,
    default_ai_auth_mode,
    format_ai_tls_verify,
    normalize_ai_auth_mode,
    normalize_ai_preset,
    parse_ai_settings_json,
    parse_ai_tls_verify,
    resolve_ai_api_key,
    resolve_ai_settings,
)
from .rc_secrets import (
    decrypt_secret,
    encrypt_secret,
    is_ai_api_key_option,
    is_encrypted_secret,
)


class _AiTestWorker(QObject):
    """Background worker for Settings → AI → Test connection.

    Lives on the GUI thread; HTTP work runs in a plain Python thread so we
    never hit QThread/moveToThread/deleteLater affinity crashes.
    """

    progress = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        parent: QObject,
        *,
        base_url: str,
        model_name: str,
        api_key: str = "",
        tls_verify: bool = True,
        log_mcp: bool = False,
    ) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._model = model_name
        self._api_key = api_key
        self._tls_verify = tls_verify
        self._log_mcp = bool(log_mcp)

    def start(self) -> None:
        threading.Thread(target=self._run, name="ai-test", daemon=True).start()

    def _run(self) -> None:
        try:
            msg = ai_test_connection(
                base_url=self._base_url,
                model=self._model,
                api_key=self._api_key,
                tls_verify=self._tls_verify,
                on_progress=lambda s: self.progress.emit(s),
                log_mcp=self._log_mcp,
            )
            self.finished.emit(msg)
        except Exception as exc:
            self.failed.emit(str(exc))


class _AiListModelsWorker(QObject):
    """Background ``GET /models`` for Settings → AI refresh."""

    finished = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        parent: QObject,
        *,
        base_url: str,
        api_key: str = "",
        tls_verify: bool = True,
        log_mcp: bool = False,
    ) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._api_key = api_key
        self._tls_verify = tls_verify
        self._log_mcp = bool(log_mcp)

    def start(self) -> None:
        threading.Thread(target=self._run, name="ai-list-models", daemon=True).start()

    def _run(self) -> None:
        try:
            names = ai_list_models(
                base_url=self._base_url,
                api_key=resolve_ai_api_key(self._api_key),
                tls_verify=self._tls_verify,
                log_mcp=self._log_mcp,
            )
            self.finished.emit([str(n) for n in names if n])
        except Exception as exc:
            self.failed.emit(str(exc))


class _LoadProgressDialog(QWidget):
    """Borderless progress dialog that paints reliably on macOS.

    QProgressDialog on macOS respects setMinimumDuration(0) but still defers
    its first paint until after the event loop has had at least one idle
    cycle.  When files are opened at startup the window manager hasn't
    settled yet, so the dialog can appear blank or not at all.

    This replacement widget uses a plain QWidget with Qt.WindowType.Tool window flag,
    which bypasses the macOS sheet mechanism entirely and paints immediately.
    """

    def __init__(self, title: str, parent=None):
        # The frameless Qt.WindowType.Tool variant is primarily needed on macOS to avoid
        # delayed first paint at startup. On Windows it may leave a tiny black
        # artifact near (0, 0), so use a regular dialog there.
        if sys.platform == "darwin":
            flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        else:
            flags = Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint | Qt.WindowType.CustomizeWindowHint
        super().__init__(parent, flags)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
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
        if obj is self.parent() and event.type() == QEvent.Type.Move:
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
    done     = Signal(object)   # BtfTrace
    errored  = Signal(str)
    cancelled = Signal()
    progress = Signal(int, str) # pct, message

    def __init__(self, path: str, parent: Optional[QObject] = None):
        super().__init__(parent)
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
                 ui_font_size: int = UI_FONT_SIZE, parent: QWidget = None):
        super().__init__(text, parent)
        self._color   = color
        self._is_dark = is_dark
        self._ui_font_size = ui_font_size
        self.setStyleSheet(self._make_style(color, is_dark=is_dark,
                                           ui_font_size=ui_font_size))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @staticmethod
    def _make_style(c: str, is_dark: bool = True,
                    ui_font_size: int = UI_FONT_SIZE) -> str:
        if is_dark:
            bg, hbg, pressed = "#2A2A2A", "#3A3A3A", "#4A4A4A"
        else:
            bg, hbg, pressed = "#F0F0F0", "#E0E0E0", "#D0D0D0"
        ui_fs = _ui_font_stylesheet_size(ui_font_size)
        return (
            f"QPushButton {{ color: {c}; background: {bg}; "
            f"border: 1px solid {c}; border-right: none; "
            f"border-radius: 3px; border-top-right-radius: 0; border-bottom-right-radius: 0; "
            f"padding: 1px 7px; font-size: {ui_fs}; "
            f"font-family: \"{_get_fixed_font_family()}\"; }}"
            f"QPushButton:hover   {{ background: {hbg}; }}"
            f"QPushButton:pressed {{ background: {pressed}; }}"
        )

    def update_style(self, is_dark: bool,
                     ui_font_size: int | None = None) -> None:
        self._is_dark = is_dark
        if ui_font_size is not None:
            self._ui_font_size = ui_font_size
        self.setStyleSheet(self._make_style(self._color, is_dark=is_dark,
                                            ui_font_size=self._ui_font_size))

class _CursorDeleteButton(QPushButton):
    """Small x button paired with a _CursorButton to form a delete pill."""

    def __init__(self, color: str, is_dark: bool = True,
                 ui_font_size: int = UI_FONT_SIZE, parent: QWidget = None):
        super().__init__("x", parent)
        self._color   = color
        self._is_dark = is_dark
        self._ui_font_size = ui_font_size
        self.setStyleSheet(self._make_style(color, is_dark=is_dark,
                                            ui_font_size=ui_font_size))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(18)
        self.setToolTip("Delete cursor")

    @staticmethod
    def _make_style(c: str, is_dark: bool = True,
                    ui_font_size: int = UI_FONT_SIZE) -> str:
        if is_dark:
            bg, hbg, pressed = "#2A2A2A", "#5A1A1A", "#4A4A4A"
        else:
            bg, hbg, pressed = "#F0F0F0", "#FAEAEA", "#D0D0D0"
        ui_fs = _ui_font_stylesheet_size(ui_font_size)
        return (
            f"QPushButton {{ color: {c}; background: {bg}; "
            f"border: 1px solid {c}; "
            f"border-radius: 3px; border-top-left-radius: 0; border-bottom-left-radius: 0; "
            f"padding: 1px 2px; font-size: {ui_fs}; }}"
            f"QPushButton:hover   {{ background: {hbg}; color: #FF4444; border-color: #FF4444; }}"
            f"QPushButton:pressed {{ background: {pressed}; }}"
        )

    def update_style(self, is_dark: bool,
                     ui_font_size: int | None = None) -> None:
        self._is_dark = is_dark
        if ui_font_size is not None:
            self._ui_font_size = ui_font_size
        self.setStyleSheet(self._make_style(self._color, is_dark=is_dark,
                                            ui_font_size=self._ui_font_size))

class _CursorBarWidget(QWidget):
    """A row of per-cursor badge+delete pills in the status bar."""
    jump_requested          = Signal(int)   # ns - scroll timeline
    cursor_delete_requested = Signal(int)   # ns - remove this cursor

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(2, 0, 2, 0)
        self._layout.setSpacing(4)
        # Each entry: (badge _CursorButton, del _CursorDeleteButton)
        self._pills: list = []
        self._delta_label: Optional[QLabel] = None
        self._is_dark: bool = True
        self._ui_font_size: int = UI_FONT_SIZE
        self._time_decimals: int = 3

    def _delta_label_style(self) -> str:
        return (
            f"font-size:{_ui_font_stylesheet_size(self._ui_font_size)};"
            f" font-family:\"{_get_fixed_font_family()}\"; padding:0 4px;"
        )

    def update_theme(self, is_dark: bool,
                     ui_font_size: int | None = None) -> None:
        self._is_dark = is_dark
        if ui_font_size is not None:
            self._ui_font_size = ui_font_size
        for badge, del_btn in self._pills:
            badge.update_style(is_dark, self._ui_font_size)
            del_btn.update_style(is_dark, self._ui_font_size)
        if self._delta_label is not None:
            self._delta_label.setStyleSheet(self._delta_label_style())

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
        badge = _CursorButton(f"C{orig_idx + 1}", color, is_dark=self._is_dark,
                              ui_font_size=self._ui_font_size)
        badge.setToolTip(f"C{orig_idx + 1}: click to jump to this cursor")
        del_btn = _CursorDeleteButton(color, is_dark=self._is_dark,
                                      ui_font_size=self._ui_font_size)
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

    def rebuild(self, times: list, trace, time_decimals: int | None = None) -> None:
        if time_decimals is not None:
            self._time_decimals = time_decimals
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
                    f"C{orig_idx + 1}: {_format_time(t, ts, decimals=self._time_decimals)}", color,
                    is_dark=self._is_dark, ui_font_size=self._ui_font_size)
                badge.setToolTip(f"C{orig_idx + 1}: click to jump to this cursor")
                del_btn = _CursorDeleteButton(color, is_dark=self._is_dark,
                                              ui_font_size=self._ui_font_size)
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
                    delta_parts.append(f"\u0394{i}={_format_time(d, ts, decimals=self._time_decimals)} ({freq_str})")
                dlbl = QLabel("   " + "   ".join(delta_parts))
                dlbl.setStyleSheet(self._delta_label_style())
                self._layout.addWidget(dlbl)
                self._delta_label = dlbl
        else:
            # Same count - update text in-place (no widget churn).
            for order, (orig_idx, t) in enumerate(sorted_pairs):
                badge, del_btn = self._pills[order]
                badge.setText(f"C{orig_idx + 1}: {_format_time(t, ts, decimals=self._time_decimals)}")
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
                    delta_parts.append(f"\u0394{i}={_format_time(d, ts, decimals=self._time_decimals)} ({freq_str})")
                self._delta_label.setText("   " + "   ".join(delta_parts))

# ---------------------------------------------------------------------------
# Legend widget
# ---------------------------------------------------------------------------

class _LegendTaskRow(QWidget):
    """A single task row in the legend that emits a click signal."""

    clicked   = Signal(str)   # task merge key

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

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

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
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(bg))
            p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 3, 3)
        super().paintEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._task_name)
        event.accept()   # prevent bubbling up to _LegendWidget.mousePressEvent

class _LegendWidget(QWidget):
    """Compact scrollable colour legend with click -> timeline highlight."""

    task_clicked     = Signal(str)   # click: task merge key
    cancel_highlight = Signal()      # click on background -> cancel highlight
    filter_changed   = Signal(str)   # search text changed
    migrated_filter_changed = Signal(bool)
    clear_heatmap_filter = Signal()

    @staticmethod
    def _swatch_icon(color: QColor, is_dark: bool) -> QIcon:
        pix = QPixmap(14, 14)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setBrush(QBrush(color))
        border = QColor("#555555") if is_dark else QColor("#AAAAAA")
        p.setPen(QPen(border))
        p.drawRoundedRect(1, 1, 12, 12, 2, 2)
        p.end()
        return QIcon(pix)

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
        palette.setColor(QPalette.ColorRole.Window, QColor("#1E1E1E"))
        self.setPalette(palette)
        self._task_items: Dict[str, QListWidgetItem] = {}
        self._task_display: Dict[str, str] = {}
        self._sti_rows: List[tuple] = []  # [(channel_or_note_lc, row_widget)]
        self._heatmap_filter_mks: Optional[set] = None
        self._heatmap_filter_label: Optional[str] = None
        self._locked_task: Optional[str] = None
        self._locked_bg = QBrush(QColor(255, 215, 0, 45))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter tasks...")
        self._sync_search_theme()
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

        self._list_host = QWidget()
        self._list_host.setObjectName("legend_list_host")
        self._list_host.setAutoFillBackground(True)
        list_outer = QVBoxLayout(self._list_host)
        list_outer.setContentsMargins(0, 0, 0, 0)
        list_outer.setSpacing(2)
        self._task_header = QLabel()
        self._task_header.setTextFormat(Qt.TextFormat.RichText)
        list_outer.addWidget(self._task_header)
        self._task_list = QListWidget()
        self._task_list.setObjectName("legend_task_list")
        self._task_list.setFrameShape(QFrame.Shape.NoFrame)
        self._task_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._task_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self._task_list.setUniformItemSizes(True)
        # Compact rows: Windows applies large default item padding once any
        # QListWidget::item QSS is set app-wide; pin icon size + padding here.
        self._task_list.setIconSize(QSize(14, 14))
        self._task_list.setSpacing(0)
        self._task_list.setStyleSheet(
            "QListWidget#legend_task_list{border:none;outline:none;}"
            "QListWidget#legend_task_list::item{"
            "padding:1px 2px;margin:0px;min-height:14px;}"
        )
        self._task_list.itemClicked.connect(self._on_task_item_clicked)
        list_outer.addWidget(self._task_list, 1)
        self._scroll = QScrollArea()
        self._scroll.setObjectName("legend_scroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidget(self._list_host)
        self._scroll.viewport().setObjectName("legend_scroll_viewport")
        self._scroll.viewport().setAutoFillBackground(True)
        outer.addWidget(self._scroll, 1)

    def _sync_search_theme(self) -> None:
        """Keep the filter field colours in sync (palette avoids per-widget QSS crashes)."""
        if self._is_dark:
            bg, fg, ph = QColor("#2D2D2D"), QColor("#D4D4D4"), QColor("#888888")
        else:
            bg, fg, ph = QColor("#FFFFFF"), QColor("#1E1E1E"), QColor("#999999")
        pal = self._search.palette()
        pal.setColor(QPalette.Base, bg)
        pal.setColor(QPalette.Text, fg)
        pal.setColor(QPalette.PlaceholderText, ph)
        self._search.setPalette(pal)
        self._search.setAutoFillBackground(True)

    def update_theme(self, is_dark: bool, *, defer_rebuild: bool = False) -> None:
        """Switch the legend palette and search-box styling to match the app theme."""
        self._is_dark = is_dark
        bg = QColor("#1E1E1E") if is_dark else QColor("#F5F5F5")
        palette = self.palette()
        palette.setColor(QPalette.Window, bg)
        self.setPalette(palette)
        # Keep child surfaces explicitly in sync; otherwise some platforms keep
        # stale dark backgrounds on the scroll viewport when switching theme.
        for w in (self._list_host, self._scroll.viewport(), self._task_list):
            p = w.palette()
            p.setColor(QPalette.ColorRole.Window, bg)
            p.setColor(QPalette.ColorRole.Base, bg)
            w.setPalette(p)
            w.setAutoFillBackground(True)
        self._sync_search_theme()
        if self._trace_ref is not None and not defer_rebuild:
            self.rebuild(self._trace_ref, show_sti=self._show_sti_flag)

    def restore_row_layout(self) -> None:
        """Legend list items do not need dock-shrink width repair."""
        return

    def set_locked_task(self, task_name: Optional[str]) -> None:
        """Visually mark *task_name* as click-locked (or clear all locks)."""
        scroll_to = task_name if task_name != self._locked_task else None
        self._locked_task = task_name
        clear = QBrush()
        for mk, item in self._task_items.items():
            is_match = (mk == task_name)
            item.setBackground(self._locked_bg if is_match else clear)
            if is_match and scroll_to is not None:
                self._task_list.scrollToItem(
                    item, QAbstractItemView.ScrollHint.EnsureVisible)

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

    def set_filter_text(self, text: str) -> None:
        """Set legend search text without notifying the timeline scene."""
        self._filter_emit_timer.stop()
        self._search.blockSignals(True)
        self._search.setText(text or "")
        self._search.blockSignals(False)
        self._filter_tasks(self._search.text())

    def mousePressEvent(self, event) -> None:
        """Click on the legend background (outside a task row) cancels highlight."""
        self.cancel_highlight.emit()
        super().mousePressEvent(event)

    def _on_task_item_clicked(self, item: QListWidgetItem) -> None:
        mk = item.data(Qt.ItemDataRole.UserRole)
        if mk:
            self.task_clicked.emit(str(mk))

    def _item_matches_filter(self, mk: str, q: str) -> bool:
        if not q:
            return True
        disp = self._task_display.get(mk, mk)
        ql = q.lower()
        return (ql in mk.lower()) or (ql in disp.lower())

    def rebuild(self, trace: Optional[BtfTrace], *, show_sti: bool = True) -> None:
        self._trace_ref      = trace
        self._show_sti_flag  = show_sti
        self._task_items.clear()
        self._task_display.clear()
        self._sti_rows = []
        scroll_pos = self._task_list.verticalScrollBar().value()

        is_dark = self._is_dark
        hdr_color = "#AAAAAA" if is_dark else "#555555"
        self._task_header.setText(f"<b style='color:{hdr_color}'>Tasks</b>")
        self._task_list.setUpdatesEnabled(False)
        try:
            self._task_list.clear()
            if trace is None:
                return
            app = QApplication.instance()
            fm = self._task_list.fontMetrics()
            row_h = max(16, fm.height() + 4)
            for i, _mk in enumerate(trace.tasks):
                _rep_raw = trace.task_repr.get(_mk, _mk)
                color = _task_color(_rep_raw)
                display = _task_display_name(_rep_raw)
                item = QListWidgetItem(self._swatch_icon(color, is_dark), display)
                item.setData(Qt.ItemDataRole.UserRole, _mk)
                item.setToolTip(_rep_raw)
                item.setSizeHint(QSize(0, row_h))
                self._task_list.addItem(item)
                self._task_items[_mk] = item
                self._task_display[_mk] = display
                if app is not None and i > 0 and (i % 256) == 0:
                    app.processEvents()
            self._filter_tasks(self._search.text())
        finally:
            self._task_list.setUpdatesEnabled(True)
        self._task_list.verticalScrollBar().setValue(scroll_pos)

    def _on_migrated_only_toggled(self, checked: bool) -> None:
        self.migrated_filter_changed.emit(bool(checked))
        self._filter_tasks(self._search.text())

    def _on_search_text_changed(self, text: str) -> None:
        """Apply legend filter immediately, debounce expensive timeline rebuild."""
        self._filter_tasks(text)
        self._filter_emit_timer.start()

    def _filter_tasks(self, text: str) -> None:
        """Show / hide task rows in the legend based on the search filter."""
        q = text.strip().lower()
        trace = self._trace_ref
        for mk, item in self._task_items.items():
            visible = self._item_matches_filter(mk, q)
            if visible and self._heatmap_filter_mks is not None:
                visible = mk in self._heatmap_filter_mks
            if visible and self._migrated_only_cb.isChecked() and trace is not None:
                visible = _is_migrated_task(trace, mk)
            item.setHidden(not visible)
        for key_lc, row_w in self._sti_rows:
            row_w.setVisible((not q) or (q in key_lc))

# ===========================================================================
# Metrics Plot Dialog
# ===========================================================================

class _ScatterWidget(QWidget):
    """Scatter plot: X = trace timestamp, Y = metric value.  Click a point to jump."""

    point_clicked = Signal(object)   # payload: TaskSegment (exec) or int ns (inter-arrival)

    def __init__(self, points, time_scale: str, color: "QColor",
                 is_dark: bool, parent=None, *, y_as_time: bool = True,
                 show_variability: bool = False) -> None:
        super().__init__(parent)
        # points: List[(x_ns, y_value, payload)]
        # payload is either a TaskSegment (exec) or int (ns, inter-arrival)
        self._points     = points
        self._time_scale = time_scale
        self._color      = color
        self._is_dark    = is_dark
        self._y_as_time  = y_as_time
        self._show_variability = bool(show_variability)
        self._highlight  = -1   # index of highlighted point (-1 = none)
        self._hover_idx  = -1   # index of hovered point for tooltip
        self._crosshair_idx = -1  # nearest point for crosshair guides
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_points(self, points: list) -> None:
        """Replace plotted points and repaint (live cursor-range updates)."""
        self._points = list(points)
        if self._highlight >= len(self._points):
            self._highlight = -1
        if self._hover_idx >= len(self._points):
            self._hover_idx = -1
        if self._crosshair_idx >= len(self._points):
            self._crosshair_idx = -1
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
        labels = ("min", "avg", "p50", "p95", "max")
        return max(14, max(fm.horizontalAdvance(lbl) for lbl in labels) + 12)

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
            p.drawText(QRect(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "No data in selected range")
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
        p.setPen(QPen(grid, 1, Qt.PenStyle.DotLine))
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
        p50_val = vals_sorted[min(n - 1, math.ceil(n * 0.50) - 1)]
        avg_val = sum(ys) / len(ys) if ys else 0
        stddev_val = math.sqrt(
            sum((value - avg_val) ** 2 for value in ys) / n
        )
        p95_val = vals_sorted[min(n - 1, math.ceil(n * 0.95) - 1)]
        for fi in range(5):
            val = y0 + (y1 - y0) * fi / 4
            gy  = MT + ph - int(fi / 4 * ph)
            if self._y_as_time:
                lbl = _format_time(int(val), self._time_scale, decimals=1)
            else:
                lbl = _format_tag_value(val)
            p.drawText(QRect(0, gy - 8, ML - 4, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, lbl)

        # X-axis labels (3 ticks)
        for fi in range(3):
            val = x0 + xspan * fi / 2
            gx  = sx(val)
            lbl = _format_time(int(val), self._time_scale, decimals=1)
            p.drawText(QRect(gx - 40, MT + ph + 4, 80, 16),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, lbl)

        if self._show_variability:
            # Average ± one population standard deviation. Clamp to the visible
            # duration axis; the band is descriptive, not a confidence interval.
            sigma_lo = max(y0, avg_val - stddev_val)
            sigma_hi = min(y1, avg_val + stddev_val)
            band_top = sy(sigma_hi)
            band_bottom = sy(sigma_lo)
            sigma_color = QColor("#CE93D8")
            sigma_color.setAlpha(38 if dark else 30)
            p.fillRect(
                QRect(ML, band_top, pw, max(1, band_bottom - band_top)),
                sigma_color,
            )

        ref_lines = [
            (avg_val, "avg", QColor("#CE93D8")),
            (p50_val, "p50", QColor("#4CAF50")),
            (p95_val, "p95", QColor("#FF9800")),
        ]
        for val, lbl_text, ref_color in ref_lines:
            gy = sy(val)
            p.setPen(QPen(ref_color, 1, Qt.PenStyle.DashLine))
            p.drawLine(ML, gy, ML + pw, gy)
            p.setPen(ref_color)
            p.setFont(sf)
            p.drawText(ML + pw + 2, gy + 4, lbl_text)

        # Crosshair guides to the nearest point under the cursor
        if self._crosshair_idx >= 0 and self._crosshair_idx < len(self._points):
            hpt = self._points[self._crosshair_idx]
            cx = sx(hpt[0])
            cy = sy(hpt[1])
            self._draw_crosshair_grad(p, cx, cy, ML, MT, pw, ph, dark)

        # Points
        hl_color  = QColor("#FFFFFF")
        p.setPen(Qt.PenStyle.NoPen)
        for i, pt in enumerate(self._points):
            cx = sx(pt[0])
            cy = sy(pt[1])
            if i == self._highlight:
                p.setBrush(QBrush(hl_color))
                p.drawEllipse(cx - 5, cy - 5, 10, 10)
            else:
                if len(pt) >= 4:
                    dot_color = QColor(pt[3])
                else:
                    dot_color = QColor(self._color)
                dot_color.setAlpha(200)
                p.setBrush(QBrush(dot_color))
                p.drawEllipse(cx - 3, cy - 3, 6, 6)

        # Hover tooltip
        if self._hover_idx >= 0 and self._hover_idx < len(self._points):
            hpt = self._points[self._hover_idx]
            if self._y_as_time:
                line1 = _format_time(int(hpt[1]), self._time_scale)
            else:
                line1 = _format_tag_value(hpt[1])
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

    @staticmethod
    def _draw_crosshair_grad(p, cx: int, cy: int, ml: int, mt: int, pw: int, ph: int,
                             dark: bool) -> None:
        """Fade crosshair lines through the nearest scatter point."""
        accent = QColor("#FFA03C" if dark else "#C8460A")

        def _fade(alpha: int) -> QColor:
            c = QColor(accent)
            c.setAlpha(alpha)
            return c

        gv = QLinearGradient(float(cx), float(mt), float(cx), float(mt + ph))
        gv.setColorAt(0.0, _fade(0))
        gv.setColorAt(0.5, _fade(210))
        gv.setColorAt(1.0, _fade(0))
        p.setPen(QPen(QBrush(gv), 1))
        p.drawLine(cx, mt, cx, mt + ph)

        gh = QLinearGradient(float(ml), float(cy), float(ml + pw), float(cy))
        gh.setColorAt(0.0, _fade(0))
        gh.setColorAt(0.5, _fade(210))
        gh.setColorAt(1.0, _fade(0))
        p.setPen(QPen(QBrush(gh), 1))
        p.drawLine(ml, cy, ml + pw, cy)

    def _plot_margins(self) -> tuple:
        w, h = self.width(), self.height()
        ml, mt, mb = 56, 14, 36
        sf = QFont(); sf.setPointSize(7)
        mr = self._marker_right_margin(QFontMetrics(sf))
        pw = w - ml - mr
        ph = h - mt - mb
        return ml, mt, mb, mr, pw, ph

    def _plot_coord_funcs(self, ml: int, mt: int, pw: int, ph: int):
        if not self._points:
            return None, None, None, None
        xs = [p[0] for p in self._points]
        ys = [p[1] for p in self._points]
        x0, x1 = min(xs), max(xs)
        y0, y1 = 0, max(ys) if max(ys) > 0 else 1
        xspan = max(x1 - x0, 1)
        yspan = max(y1 - y0, 1)

        def sx(x): return ml + int((x - x0) / xspan * pw)
        def sy(y): return mt + ph - int((y - y0) / yspan * ph)
        return sx, sy, x0, x1

    def _nearest_point_index(self, ex: float, ey: float) -> int:
        """Index of the nearest scatter point when *ex*, *ey* is inside the plot area."""
        if not self._points:
            return -1
        ml, mt, _mb, _mr, pw, ph = self._plot_margins()
        if not (ml <= ex <= ml + pw and mt <= ey <= mt + ph):
            return -1
        sx, sy, _, _ = self._plot_coord_funcs(ml, mt, pw, ph)
        if sx is None:
            return -1
        best_d, best_i = float("inf"), -1
        for i, pt in enumerate(self._points):
            dx = sx(pt[0]) - ex
            dy = sy(pt[1]) - ey
            d = dx * dx + dy * dy
            if d < best_d:
                best_d, best_i = d, i
        return best_i

    def _nearest_point(self, ex: int, ey: int, threshold: int = 12):
        """Return (distance_sq, index) of the nearest scatter point within threshold px."""
        idx = self._nearest_point_index(ex, ey)
        if idx < 0:
            return float("inf"), -1
        ml, mt, _mb, _mr, pw, ph = self._plot_margins()
        sx, sy, _, _ = self._plot_coord_funcs(ml, mt, pw, ph)
        pt = self._points[idx]
        dx = sx(pt[0]) - ex
        dy = sy(pt[1]) - ey
        best_d = dx * dx + dy * dy
        if best_d <= threshold * threshold:
            return best_d, idx
        return float("inf"), -1

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        ex = event.position().x()
        ey = event.position().y()
        cross_idx = self._nearest_point_index(ex, ey)
        _, hover_idx = self._nearest_point(ex, ey, threshold=12)
        if cross_idx != self._crosshair_idx or hover_idx != self._hover_idx:
            self._crosshair_idx = cross_idx
            self._hover_idx = hover_idx
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover_idx != -1 or self._crosshair_idx != -1:
            self._hover_idx = -1
            self._crosshair_idx = -1
            self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or not self._points:
            return
        _, best_i = self._nearest_point(event.position().x(), event.position().y(), threshold=8)

        if best_i >= 0:
            self._highlight = best_i
            self.update()
            self.point_clicked.emit(self._points[best_i])

def _hist_percentile(sorted_vals: list, p: float) -> float:
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    idx = min(n - 1, max(0, int(math.floor(p * (n - 1)))))
    return float(sorted_vals[idx])

def _hist_summarize(values: list) -> dict:
    vals = sorted(values)
    n = len(vals)
    if n == 0:
        return {}
    avg = sum(vals) / n
    return {
        "min": float(vals[0]),
        "max": float(vals[-1]),
        "avg": avg,
        "stddev": math.sqrt(sum((value - avg) ** 2 for value in vals) / n),
        "p5": _hist_percentile(vals, 0.05),
        "p50": _hist_percentile(vals, 0.50),
        "p95": _hist_percentile(vals, 0.95),
        "p99": _hist_percentile(vals, 0.99),
    }

def _hist_detect_scale_mode(values: list, summary: dict) -> str:
    if len(values) < 4:
        return "linear"
    min_v = summary["min"]
    max_v = summary["max"]
    p5 = summary["p5"]
    p95 = summary["p95"]
    span = max(1.0, max_v - min_v)
    core_span = max(1.0, p95 - p5)
    tail_ratio = max_v / max(p95, 1.0)
    crowded = core_span / span < 0.55
    if min_v > 0:
        range_ratio = max_v / max(min_v, 1.0)
        if range_ratio >= 40 or (tail_ratio >= 4 and crowded):
            return "log"
    if tail_ratio >= 2 or crowded:
        return "percentile"
    return "linear"

def _hist_fd_bin_count(values: list, min_val: float, max_val: float) -> int:
    n = len(values)
    if n < 2:
        return 40
    p25 = _hist_percentile(values, 0.25)
    p75 = _hist_percentile(values, 0.75)
    iqr = max(1.0, p75 - p25)
    bin_w = (2 * iqr) / (n ** (1 / 3))
    span = max(1.0, max_val - min_val)
    return min(80, max(12, int(round(span / bin_w))))

def _hist_should_use_log_y(counts: list) -> bool:
    positive = [c for c in counts if c > 0]
    if len(positive) < 2:
        return False
    max_count = max(positive)
    positive.sort()
    median = positive[len(positive) // 2]
    return max_count >= 12 and median > 0 and max_count / median >= 8

def _hist_log_spaced_edges(min_val: float, max_val: float, bin_count: int) -> list:
    lo = max(min_val, 1.0)
    hi = max(lo + 1.0, max_val)
    log_lo = math.log10(lo)
    log_hi = math.log10(hi)
    return [10 ** (log_lo + (log_hi - log_lo) * i / bin_count) for i in range(bin_count + 1)]

def _hist_bin_index_for_value(value: float, edges: list) -> int:
    last = len(edges) - 2
    if value <= edges[0]:
        return 0
    if value >= edges[last + 1]:
        return last
    for i in range(last + 1):
        if value < edges[i + 1]:
            return i
    return last

def _hist_build_bins(values: list, scale_mode: str, summary: dict) -> dict:
    min_v = summary["min"]
    max_v = summary["max"]
    p5 = summary["p5"]
    p95 = summary["p95"]
    if scale_mode == "percentile":
        lo = min(p5, p95)
        hi = max(lo + 1.0, p95)
        regular_bins = _hist_fd_bin_count(values, lo, hi)
        step = (hi - lo) / regular_bins
        edges = [lo + step * i for i in range(regular_bins + 1)]
        counts = [0] * regular_bins
        overflow = underflow = 0
        for v in values:
            if v < lo:
                underflow += 1
            elif v > hi:
                overflow += 1
            else:
                counts[_hist_bin_index_for_value(v, edges)] += 1
        return {
            "counts": counts, "edges": edges, "display_min": lo, "display_max": hi,
            "overflow": overflow, "underflow": underflow,
            "has_overflow_bin": overflow > 0, "has_underflow_bin": underflow > 0,
            "x_scale": "linear",
        }
    if scale_mode == "log" and min_v > 0:
        bin_count = 40
        edges = _hist_log_spaced_edges(min_v, max_v, bin_count)
        counts = [0] * bin_count
        for v in values:
            counts[_hist_bin_index_for_value(v, edges)] += 1
        return {
            "counts": counts, "edges": edges, "display_min": min_v, "display_max": max_v,
            "overflow": 0, "underflow": 0,
            "has_overflow_bin": False, "has_underflow_bin": False,
            "x_scale": "log",
        }
    lo = min_v
    hi = max_v
    span = max(1.0, hi - lo)
    bin_count = _hist_fd_bin_count(values, lo, hi)
    step = span / bin_count
    edges = [lo + step * i for i in range(bin_count + 1)]
    counts = [0] * bin_count
    for v in values:
        counts[_hist_bin_index_for_value(v, edges)] += 1
    return {
        "counts": counts, "edges": edges, "display_min": lo, "display_max": hi,
        "overflow": 0, "underflow": 0,
        "has_overflow_bin": False, "has_underflow_bin": False,
        "x_scale": "linear",
    }

def _hist_slot_layout(bin_spec: dict, plot_w: int) -> tuple:
    counts = bin_spec["counts"]
    leading = 1 if bin_spec["has_underflow_bin"] else 0
    regular_slots = len(counts)
    slot_count = leading + regular_slots + (1 if bin_spec["has_overflow_bin"] else 0)
    slot_w = plot_w / max(1, slot_count)
    regular_w = regular_slots * slot_w
    return slot_count, slot_w, leading, regular_slots, regular_w

def _hist_value_to_x(value: float, bin_spec: dict, plot_w: int, margin_left: int) -> int:
    display_min = bin_spec["display_min"]
    display_max = bin_spec["display_max"]
    _slot_count, slot_w, leading, regular_slots, regular_w = _hist_slot_layout(bin_spec, plot_w)
    region_left = margin_left + int(leading * slot_w)

    if bin_spec["has_underflow_bin"] and value < display_min:
        return margin_left + int(slot_w * 0.5)
    if bin_spec["has_overflow_bin"] and value > display_max:
        slot = leading + regular_slots
        return margin_left + int(slot * slot_w + slot_w * 0.5)

    if bin_spec["x_scale"] == "log":
        lo = max(display_min, 1.0)
        hi = max(lo + 1.0, display_max)
        log_lo = math.log10(lo)
        log_hi = math.log10(hi)
        t = (math.log10(max(value, lo)) - log_lo) / max(1e-9, log_hi - log_lo)
        return region_left + int(t * regular_w)
    span = max(1.0, display_max - display_min)
    t = (value - display_min) / span
    return region_left + int(t * regular_w)

def _hist_build_bar_layout(bin_spec: dict, plot_w: int, plot_h: int,
                           margin_left: int, margin_top: int, log_y: bool) -> tuple:
    counts = bin_spec["counts"]
    edges = bin_spec["edges"]
    overflow = bin_spec["overflow"]
    underflow = bin_spec["underflow"]
    has_overflow = bin_spec["has_overflow_bin"]
    has_underflow = bin_spec["has_underflow_bin"]
    slot_count = len(counts) + (1 if has_overflow else 0) + (1 if has_underflow else 0)
    slot_w = plot_w / max(1, slot_count)
    max_count = max(1, *counts, overflow, underflow)

    def count_height(count: int) -> int:
        if count <= 0:
            return 0
        if not log_y:
            return int(count / max_count * plot_h)
        return int(math.log10(count + 1) / math.log10(max_count + 1) * plot_h)

    bars = []
    slot = 0
    if has_underflow:
        h = count_height(underflow)
        bars.append((margin_left + int(slot * slot_w), margin_top + plot_h - h,
                     max(1, int(slot_w) - 1), h, "underflow"))
        slot += 1
    for i, cnt in enumerate(counts):
        h = count_height(cnt)
        bars.append((margin_left + int(slot * slot_w), margin_top + plot_h - h,
                     max(1, int(slot_w) - 1), h, "regular"))
        slot += 1
    if has_overflow:
        h = count_height(overflow)
        bars.append((margin_left + int(slot * slot_w), margin_top + plot_h - h,
                     max(1, int(slot_w) - 1), h, "overflow"))
    return bars, max_count, slot_count, slot_w

def _hist_build_caption(scale_mode: str, summary: dict, bin_spec: dict,
                        log_y: bool, time_scale: str,
                        *, value_as_time: bool = True) -> str:
    parts = []
    if scale_mode == "percentile":
        parts.append("p5–p95 view")
        if bin_spec["overflow"] > 0:
            parts.append(f"{bin_spec['overflow']} above p95")
        if bin_spec["underflow"] > 0:
            parts.append(f"{bin_spec['underflow']} below p5")
    elif scale_mode == "log":
        parts.append("log-scaled duration axis" if value_as_time
                     else "log-scaled value axis")
    else:
        parts.append("linear scale")
    if log_y:
        parts.append("log-scaled counts")
    fmt = (lambda v: _format_time(int(v), time_scale, decimals=1)) if value_as_time else _format_tag_value
    parts.append(f"full range {fmt(summary['min'])}–{fmt(summary['max'])}")
    return " · ".join(parts)

def _hist_format_axis_value(val: float, time_scale: str, *, value_as_time: bool) -> str:
    if value_as_time:
        return _format_time(int(val), time_scale, decimals=1)
    return _format_tag_value(val)

def _hist_build_model(values: list, time_scale: str, scale_mode: str = "auto",
                      *, value_as_time: bool = True,
                      show_variability: bool = False) -> Optional[dict]:
    if not values:
        return None
    sorted_vals = sorted(values)
    summary = _hist_summarize(sorted_vals)
    resolved = _hist_detect_scale_mode(sorted_vals, summary) if scale_mode == "auto" else scale_mode
    effective = "percentile" if resolved == "log" and summary["min"] <= 0 else resolved
    bin_spec = _hist_build_bins(sorted_vals, effective, summary)
    margin_left, margin_right, margin_top, margin_bottom = 56, 44, 28, 36
    plot_w = 820 - margin_left - margin_right
    plot_h = 240 - margin_top - margin_bottom
    log_y = _hist_should_use_log_y(
        bin_spec["counts"] + [bin_spec["overflow"], bin_spec["underflow"]])
    bars, max_count, slot_count, slot_w = _hist_build_bar_layout(
        bin_spec, plot_w, plot_h, margin_left, margin_top, log_y)
    _sc, _sw, leading, regular_slots, regular_w = _hist_slot_layout(bin_spec, plot_w)
    region_left = margin_left + int(leading * _sw)

    def scale_x(val: float) -> int:
        return _hist_value_to_x(val, bin_spec, plot_w, margin_left)

    x_ticks = []
    if bin_spec["x_scale"] == "log":
        lo = max(bin_spec["display_min"], 1.0)
        hi = max(lo + 1.0, bin_spec["display_max"])
        log_lo = math.log10(lo)
        log_hi = math.log10(hi)
        for d in range(int(math.floor(log_lo)), int(math.ceil(log_hi)) + 1):
            for m in (1, 2, 5):
                val = m * (10 ** d)
                if val < lo * 0.999 or val > hi * 1.001:
                    continue
                t = (math.log10(val) - log_lo) / max(1e-9, log_hi - log_lo)
                x_ticks.append((region_left + int(t * regular_w),
                                _hist_format_axis_value(val, time_scale,
                                                        value_as_time=value_as_time)))
                if len(x_ticks) >= 7:
                    break
            if len(x_ticks) >= 7:
                break
        if not x_ticks:
            for fi in range(3):
                log_val = log_lo + (log_hi - log_lo) * fi / 2
                val = int(round(10 ** log_val))
                x_ticks.append((region_left + int(fi / 2 * regular_w),
                                _hist_format_axis_value(val, time_scale,
                                                        value_as_time=value_as_time)))
    else:
        for fi in range(3):
            val = int(round(bin_spec["display_min"] +
                            (bin_spec["display_max"] - bin_spec["display_min"]) * fi / 2))
            x_ticks.append((region_left + int(fi / 2 * regular_w),
                            _hist_format_axis_value(val, time_scale,
                                                    value_as_time=value_as_time)))
        if bin_spec["has_overflow_bin"]:
            x_ticks.append((margin_left + int((leading + regular_slots + 0.5) * _sw), ">p95"))

    y_ticks = []
    for fi in range(5):
        ratio = 1 - fi / 4
        if log_y:
            cnt = int(round(10 ** (math.log10(max_count + 1) * ratio) - 1))
            bar_h = int(math.log10(cnt + 1) / math.log10(max_count + 1) * plot_h)
        else:
            cnt = int(round(max_count * ratio))
            bar_h = int(cnt / max(1, max_count) * plot_h)
        y_ticks.append((margin_top + plot_h - bar_h, str(cnt)))

    cdf_points = []
    n = len(sorted_vals)
    if n >= 2:
        raw_cdf = []
        for i, val in enumerate(sorted_vals):
            pct = (i + 1) / n
            gx = _hist_value_to_x(val, bin_spec, plot_w, margin_left)
            gy = margin_top + plot_h - int(pct * plot_h)
            raw_cdf.append((gx, gy))
        for gx, gy in raw_cdf:
            if cdf_points and abs(cdf_points[-1][0] - gx) < 1:
                cdf_points[-1] = (gx, gy)
            elif not cdf_points or gx >= cdf_points[-1][0] - 1:
                cdf_points.append((gx, gy))
        if len(cdf_points) > 90:
            step = max(1, math.ceil(len(cdf_points) / 80))
            sampled = cdf_points[::step]
            if sampled[-1] != cdf_points[-1]:
                sampled.append(cdf_points[-1])
            cdf_points = sampled
    cdf_ticks = [(margin_top + plot_h - int(p / 100 * plot_h), f"{p}%") for p in (0, 50, 100)]

    refs = [
        (summary["avg"], "avg", QColor("#CE93D8")),
        (summary["p50"], "p50", QColor("#4CAF50")),
        (summary["p95"], "p95", QColor("#FF9800")),
    ]
    ref_lines = []
    for val, lbl, color in refs:
        gx = scale_x(val)
        if margin_left <= gx <= margin_left + plot_w:
            ref_lines.append((gx, lbl, color))

    sigma_band = None
    if show_variability:
        sigma_lo = max(summary["min"], summary["avg"] - summary["stddev"])
        sigma_hi = min(summary["max"], summary["avg"] + summary["stddev"])
        x0 = scale_x(sigma_lo)
        x1 = scale_x(sigma_hi)
        plot_right = margin_left + plot_w
        if x1 >= margin_left and x0 <= plot_right:
            sigma_band = (
                max(margin_left, min(x0, x1)),
                min(plot_right, max(x0, x1)),
            )

    return {
        "summary": summary,
        "effective_mode": effective,
        "caption": _hist_build_caption(effective, summary, bin_spec, log_y, time_scale,
                                       value_as_time=value_as_time),
        "margin_left": margin_left,
        "margin_right": margin_right,
        "margin_top": margin_top,
        "margin_bottom": margin_bottom,
        "plot_w": plot_w,
        "plot_h": plot_h,
        "bars": bars,
        "x_ticks": x_ticks,
        "y_ticks": y_ticks,
        "cdf_points": cdf_points,
        "cdf_ticks": cdf_ticks,
        "ref_lines": ref_lines,
        "sigma_band": sigma_band,
        "log_y": log_y,
        "max_count": max_count,
    }

class _HistogramWidget(QWidget):
    """Histogram of metric values with adaptive scaling, CDF overlay, and markers."""

    def __init__(self, values, time_scale: str, color: "QColor",
                 is_dark: bool, parent=None, *, value_as_time: bool = True,
                 show_variability: bool = False) -> None:
        super().__init__(parent)
        self._values      = sorted(values)
        self._time_scale  = time_scale
        self._color       = color
        self._is_dark     = is_dark
        self._scale_mode  = "auto"
        self._value_as_time = value_as_time
        self._show_variability = bool(show_variability)
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_values(self, values: list) -> None:
        """Replace histogram samples and repaint."""
        self._values = sorted(values)
        self.update()

    def set_scale_mode(self, mode: str) -> None:
        self._scale_mode = mode if mode in ("auto", "linear", "percentile", "log") else "auto"
        self.update()

    def set_dark(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        w, h = self.width(), self.height()
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
            p.drawText(QRect(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "No data in selected range")
            p.end()
            return

        model = _hist_build_model(self._values, self._time_scale, self._scale_mode,
                                  value_as_time=self._value_as_time,
                                  show_variability=self._show_variability)
        if not model:
            p.end()
            return

        ML = model["margin_left"]
        MR = model["margin_right"]
        MT = model["margin_top"]
        MB = model["margin_bottom"]
        pw = w - ML - MR
        ph = h - MT - MB
        scale = pw / max(1, model["plot_w"])

        sf = QFont(); sf.setPointSize(7)
        p.setFont(sf)
        fm = p.fontMetrics()
        marker_labels = ("min", "avg", "p50", "p95", "max")
        MR_labels = max(14, max(fm.horizontalAdvance(lbl) for lbl in marker_labels) + 10)
        pw = w - ML - MR_labels
        ph = h - MT - MB
        scale = pw / max(1, model["plot_w"])

        # Caption
        p.setPen(txt)
        p.drawText(QRect(ML, 4, pw, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   model["caption"])

        # Grid + axes
        p.setPen(QPen(grid, 1, Qt.PenStyle.DotLine))
        for gy, _lbl in model["y_ticks"]:
            p.drawLine(ML, int(MT + (gy - model["margin_top"]) * ph / max(1, model["plot_h"])),
                       ML + pw, int(MT + (gy - model["margin_top"]) * ph / max(1, model["plot_h"])))
        p.setPen(QPen(axln, 1))
        p.drawLine(ML, MT, ML, MT + ph)
        p.drawLine(ML, MT + ph, ML + pw, MT + ph)
        p.setPen(QPen(axln, 1, Qt.PenStyle.DashLine))
        p.drawLine(ML + pw, MT, ML + pw, MT + ph)

        # Y labels
        p.setPen(txt)
        for gy, lbl in model["y_ticks"]:
            y = int(MT + (gy - model["margin_top"]) * ph / max(1, model["plot_h"]))
            p.drawText(QRect(0, y - 8, ML - 4, 16),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, lbl)

        # CDF axis labels
        for gy, lbl in model["cdf_ticks"]:
            y = int(MT + (gy - model["margin_top"]) * ph / max(1, model["plot_h"]))
            p.drawText(QRect(ML + pw + 4, y - 8, MR_labels - 4, 16),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, lbl)

        # X labels
        for gx, lbl in model["x_ticks"]:
            x = int(ML + (gx - model["margin_left"]) * scale)
            p.drawText(QRect(x - 40, MT + ph + 4, 80, 16),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, lbl)

        # Average ± one population standard deviation, behind the bars.
        sigma_band = model.get("sigma_band")
        if sigma_band is not None:
            bx0, bx1 = sigma_band
            x0 = int(ML + (bx0 - model["margin_left"]) * scale)
            x1 = int(ML + (bx1 - model["margin_left"]) * scale)
            sigma_color = QColor("#CE93D8")
            sigma_color.setAlpha(38 if dark else 30)
            p.fillRect(QRect(x0, MT, max(1, x1 - x0), ph), sigma_color)

        # Bars
        bar_color = QColor(self._color); bar_color.setAlpha(180)
        overflow_color = QColor(self._color); overflow_color.setAlpha(100)
        p.setPen(Qt.PenStyle.NoPen)
        for bx, by, bw, bh, kind in model["bars"]:
            x = int(ML + (bx - model["margin_left"]) * scale)
            y = int(MT + (by - model["margin_top"]) * ph / max(1, model["plot_h"]))
            bar_h = int(bh * ph / max(1, model["plot_h"]))
            bar_w = max(1, int(bw * scale))
            p.setBrush(QBrush(overflow_color if kind in ("overflow", "underflow") else bar_color))
            p.drawRect(x, y, bar_w, bar_h)

        # CDF line
        if len(model["cdf_points"]) > 1:
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setPen(QPen(QColor("#90CAF9"), 1.5))
            path_pts = []
            for gx, gy in model["cdf_points"]:
                path_pts.append(QPoint(int(ML + (gx - model["margin_left"]) * scale),
                                       int(MT + (gy - model["margin_top"]) * ph / max(1, model["plot_h"]))))
            for i in range(1, len(path_pts)):
                p.drawLine(path_pts[i - 1], path_pts[i])

        p.setRenderHint(QPainter.Antialiasing, True)
        for gx, lbl_text, lcolor in model["ref_lines"]:
            x = int(ML + (gx - model["margin_left"]) * scale)
            p.setPen(QPen(lcolor, 2, Qt.PenStyle.DashLine))
            p.drawLine(x, MT, x, MT + ph)
            p.setPen(lcolor)
            p.setFont(sf)
            p.drawText(x + 3, MT + 12, lbl_text)

        p.end()

_MIG_PLOT_TABS = (("mig_dwell", "Dwell"), ("mig_rate", "Rate"), ("mig_gap", "Gap"))
_PAIR_PLOT_TABS = (("pair_gap", "Gap"), ("pair_rate", "Rate"))
_TAG_PLOT_TABS = (("tag", "Value"), ("tag_interval", "Interval"))

class _MetricsPlotDialog(QDialog):
    """Modeless popup: scatter plot + histogram for one task metric.

    ``points``  - List of (x_ns, y_value, payload) where payload is
                  a TaskSegment (exec) or int (inter-arrival start ns).
    ``on_point_click`` - called with the trace-ns when a scatter point is clicked.
    """

    closed = Signal()

    def __init__(self, title: str,
                 points,
                 time_scale: str,
                 color: "QColor",
                 on_point_click,
                 is_dark: bool,
                 scope_scoped: bool,
                 scope_badge: str,
                 scope_detail: str,
                 y_as_time: bool = True,
                 show_variability: bool = False,
                 tabs: Optional[Sequence[Tuple[str, str]]] = None,
                 active_tab: Optional[str] = None,
                 on_tab_change=None,
                 on_open_heatmap=None,
                 on_open_chord=None,
                 parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self._title        = title
        self._is_dark      = is_dark
        self._on_pt_click  = on_point_click
        self._on_tab_change = on_tab_change
        self._on_open_heatmap = on_open_heatmap
        self._on_open_chord = on_open_chord
        self._btn_open_heatmap: Optional[QPushButton] = None
        self._btn_open_chord: Optional[QPushButton] = None
        self.setWindowTitle(title)
        self.resize(820, 620)
        self.setMinimumSize(500, 400)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(4)

        self._tab_buttons: Dict[str, QPushButton] = {}
        self._active_tab = active_tab
        if tabs:
            tab_row = QHBoxLayout()
            tab_row.setContentsMargins(0, 0, 0, 0)
            tab_row.setSpacing(4)
            self._tab_group = QButtonGroup(self)
            self._tab_group.setExclusive(True)
            tab_ss = self._tab_button_stylesheet(is_dark)
            for kind, label in tabs:
                btn = QPushButton(label)
                btn.setObjectName("plot_tab")
                btn.setCheckable(True)
                btn.setChecked(kind == active_tab)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setToolTip(f"Show the {label} distribution")
                btn.setStyleSheet(tab_ss)
                btn.clicked.connect(lambda _checked, k=kind: self._on_tab_clicked(k))
                self._tab_group.addButton(btn)
                tab_row.addWidget(btn)
                self._tab_buttons[kind] = btn
            tab_row.addStretch(1)
            root.addLayout(tab_row)

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
        self._y_as_time = y_as_time
        self._scatter = _ScatterWidget(points, time_scale, color, is_dark,
                                       y_as_time=y_as_time,
                                       show_variability=show_variability)
        self._histogram = _HistogramWidget(values, time_scale, color, is_dark,
                                           value_as_time=y_as_time,
                                           show_variability=show_variability)

        hist_toolbar = QHBoxLayout()
        hist_toolbar.setContentsMargins(0, 0, 0, 0)
        hist_toolbar.setSpacing(8)
        hist_lbl = QLabel("Histogram scale")
        self._hist_scale = QComboBox()
        log_label = "Log duration" if y_as_time else "Log scale"
        self._hist_scale.addItems(["Auto", "Linear", "p5–p95", log_label])
        self._hist_scale.setCurrentIndex(0)
        self._hist_scale.currentIndexChanged.connect(self._on_hist_scale_changed)
        hist_toolbar.addWidget(hist_lbl)
        hist_toolbar.addWidget(self._hist_scale)
        hist_toolbar.addStretch()

        self._scatter.point_clicked.connect(self._on_scatter_click)

        splitter = _ResizeSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._scatter)
        hist_panel = QWidget()
        hist_layout = QVBoxLayout(hist_panel)
        hist_layout.setContentsMargins(0, 0, 0, 0)
        hist_layout.setSpacing(2)
        hist_layout.addLayout(hist_toolbar)
        hist_layout.addWidget(self._histogram, 1)
        splitter.addWidget(hist_panel)
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
        # clicked(bool) would bind `checked` to the callbacks' first default
        # parameter, so swallow it here.
        if on_open_heatmap is not None:
            btn_hm = QPushButton("Open Heatmap")
            btn_hm.setToolTip(
                "Open the Migration Heatmap focused on this core pair")
            btn_hm.clicked.connect(lambda _checked=False: on_open_heatmap())
            btn_row.addWidget(btn_hm)
            self._btn_open_heatmap = btn_hm
        if on_open_chord is not None:
            btn_ch = QPushButton("Open Chord")
            btn_ch.setToolTip(
                "Open the Migration Chord Diagram with this pair highlighted")
            btn_ch.clicked.connect(lambda _checked=False: on_open_chord())
            btn_row.addWidget(btn_ch)
            self._btn_open_chord = btn_ch
        btn_row.addStretch()
        btn_row.addWidget(btn_cls)
        root.addLayout(btn_row)

    @staticmethod
    def _tab_button_stylesheet(is_dark: bool) -> str:
        """Segmented tabs: the active metric gets an accent fill + bottom edge.

        Mirrors the web .plot-tab-btn.active accent so the current view type is
        obvious; a plain checkable QPushButton reads as unselected on macOS.
        """
        # Unchecked tabs inherit the palette text colour so they stay legible
        # under both the light and dark application stylesheets.
        border, hover = ("#5A5A5A", "#3A3A3A") if is_dark else ("#C0C0C0", "#E8E8E8")
        return (
            "QPushButton#plot_tab {"
            f"  border: 1px solid {border}; border-bottom: 2px solid {border};"
            "  border-radius: 5px; padding: 3px 12px; font-weight: 600;"
            "  background: transparent;"
            "}"
            f"QPushButton#plot_tab:hover:!checked {{ background: {hover}; }}"
            "QPushButton#plot_tab:checked {"
            "  background: #1976D2; border: 1px solid #1976D2;"
            "  border-bottom: 2px solid #0D47A1; color: #FFFFFF;"
            "}"
        )

    def _on_tab_clicked(self, kind: str) -> None:
        if self._on_tab_change is not None:
            self._on_tab_change(kind)

    def active_tab(self) -> Optional[str]:
        return self._active_tab

    def set_active_tab(self, kind: str) -> None:
        """Sync the highlighted tab, e.g. after a switch was rejected."""
        btn = self._tab_buttons.get(kind)
        if btn is None:
            return
        self._active_tab = kind
        if not btn.isChecked():
            btn.setChecked(True)

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
        self._hist_scale.blockSignals(True)
        self._hist_scale.setCurrentIndex(0)
        self._hist_scale.blockSignals(False)
        self._histogram.set_scale_mode("auto")

    def _on_hist_scale_changed(self, index: int) -> None:
        modes = ("auto", "linear", "percentile", "log")
        if 0 <= index < len(modes):
            self._histogram.set_scale_mode(modes[index])

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
        pixmap, capture_dpr = _normalize_grab_pixmap(self._content.grab())
        dlg = SnapshotEditorDialog(pixmap, self, capture_dpr=capture_dpr)
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
            with _svg_safe_app_style():
                painter = QPainter(gen)
                try:
                    self._content.render(painter, QPoint(0, 0))
                finally:
                    painter.end()
        except (OSError, RuntimeError) as exc:
            QMessageBox.critical(self, "SVG Export Error", str(exc))

# ---------------------------------------------------------------------------
# Statistics dock panel
# ---------------------------------------------------------------------------

class _ElidedUtilLabel(QLabel):
    """Fixed-width util row label; elides when the stats column is narrow."""

    def __init__(self, text: str, *, column_width: int,
                 parent=None) -> None:
        super().__init__(parent)
        self._full_text = text
        self._column_width = max(STATS_UTIL_LABEL_MIN_W, int(column_width))
        self.setFixedWidth(self._column_width)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._apply_elide()

    def set_column_width(self, width: int) -> None:
        width = max(STATS_UTIL_LABEL_MIN_W, int(width))
        if width == self._column_width:
            return
        self._column_width = width
        self.setFixedWidth(width)
        self._apply_elide()

    def _apply_elide(self) -> None:
        w = max(1, self._column_width - 2)
        self.setText(self.fontMetrics().elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, w))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._column_width, STATS_UTIL_ROW_H)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(STATS_UTIL_LABEL_MIN_W, STATS_UTIL_ROW_H)

class _StatsHoverRow(QWidget):
    """Progress-bar stat row that highlights on mouse-over."""

    def __init__(self, is_dark: bool, on_click=None, parent=None) -> None:
        super().__init__(parent)
        self._on_click = on_click
        self._hover_bg = QColor("#3A3A50") if is_dark else QColor("#E0E0EC")
        self._hovered = False
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        if on_click is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _apply_hover(self, hovered: bool) -> None:
        if hovered == self._hovered:
            return
        self._hovered = hovered
        self.update()

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
        if et in (QEvent.Type.Enter, QEvent.Type.HoverEnter):
            self._apply_hover(True)
        elif et in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
            # Context-bound singleShot: cancelled if this row is deleteLater()'d
            # before the timer fires (e.g. statistics panel rebuild while hovering).
            QTimer.singleShot(0, self, self._sync_hover)
        elif (et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton
              and self._on_click is not None):
            self._on_click()
            return True
        return False

    def _sync_hover(self) -> None:
        # Belt-and-suspenders: context-bound timers should not fire after delete,
        # but a stale Python wrapper must not call into a destroyed C++ object.
        try:
            hovered = self.underMouse()
        except RuntimeError:
            return
        self._apply_hover(hovered)

    def update_theme(self, is_dark: bool) -> None:
        self._hover_bg = QColor("#3A3A50") if is_dark else QColor("#E0E0EC")
        if self._hovered:
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._hovered:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(self._hover_bg))
            p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 2, 2)
        super().paintEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._on_click is not None:
            self._on_click()
            event.accept()
            return
        super().mousePressEvent(event)

class _IconTextButton(QWidget):
    """Clickable icon + label (macOS QPushButton QSS often suppresses setIcon)."""

    clicked = Signal()

    def __init__(self, text: str, icon_path: str, icon_color: str, *,
                 ui_fs: str, fg: str, border: str, bg: str, hover_bg: str,
                 parent=None) -> None:
        super().__init__(parent)
        self._fg = fg
        self._border = border
        self._bg = bg
        self._hover_bg = hover_bg
        self._hovered = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 3, 10, 3)
        lay.setSpacing(5)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(_svg_pixmap(icon_path, icon_color, 14))
        icon_lbl.setFixedSize(14, 14)
        icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay.addWidget(icon_lbl)
        text_lbl = QLabel(text)
        text_lbl.setStyleSheet(
            f"color:{fg}; font-size:{ui_fs}; font-weight:600; background:transparent;")
        text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay.addWidget(text_lbl)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bg = self._hover_bg if self._hovered else self._bg
        p.setPen(QPen(QColor(self._border)))
        p.setBrush(QBrush(QColor(bg)))
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 4, 4)
        super().paintEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class _StatsPinButton(QLabel):
    """Section pin toggle.

    Uses a QLabel pixmap instead of QToolButton/QPushButton.setIcon — macOS
    application stylesheets routinely suppress tool-button icons.
    """

    clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("stats_section_pin")
        self.setFixedSize(22, 22)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._pinned = False
        self._hovered = False

    def set_pinned(self, pinned: bool, *, dark: bool = True) -> None:
        self._pinned = bool(pinned)
        muted = "#D0D0D0" if dark else "#555555"
        accent = "#7EC8E3" if dark else "#2A6FB2"
        path = _IC_PIN_FILLED if self._pinned else _IC_PIN
        color = accent if self._pinned else muted
        self.setPixmap(_svg_pixmap(path, color, 14))
        self.setToolTip(
            "Unpin — allow this section to collapse"
            if self._pinned else
            "Pin — keep this section expanded")
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._hovered:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(128, 128, 128, 70)))
            p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 3, 3)
            p.end()
        super().paintEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


_STATS_SECTION_MIME = "application/x-btf-stats-section"


class _StatsSectionDragFilter(QObject):
    """Drag a statistics section header to reorder sections in the panel."""

    def __init__(self, panel: "_StatsPanel", section_id: str,
                 grip: QWidget) -> None:
        super().__init__(panel)
        self._panel = panel
        self._section_id = section_id
        self._grip = grip
        self._press_pos: Optional[QPoint] = None

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        et = event.type()
        if obj is self._grip:
            if et == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._press_pos = event.position().toPoint()
            elif et == QEvent.Type.MouseButtonRelease:
                self._press_pos = None
            elif et == QEvent.Type.MouseMove:
                if (self._press_pos is not None
                    and event.buttons() & Qt.MouseButton.LeftButton):
                    delta = event.position().toPoint() - self._press_pos
                    if delta.manhattanLength() >= QApplication.startDragDistance():
                        self._press_pos = None
                        drag = QDrag(obj)
                        mime = QMimeData()
                        mime.setData(
                            _STATS_SECTION_MIME,
                            self._section_id.encode("utf-8"))
                        mime.setText(self._section_id)
                        drag.setMimeData(mime)
                        self._panel._begin_section_drag(self._section_id)
                        try:
                            drag.exec(Qt.DropAction.MoveAction)
                        finally:
                            self._panel._end_section_drag()
                        return True
        if et == QEvent.Type.DragEnter:
            if event.mimeData().hasFormat(_STATS_SECTION_MIME):
                event.acceptProposedAction()
                self._panel._set_section_drop_target(self._section_id)
                return True
        elif et == QEvent.Type.DragMove:
            if event.mimeData().hasFormat(_STATS_SECTION_MIME):
                event.acceptProposedAction()
                self._panel._set_section_drop_target(self._section_id)
                return True
        elif et == QEvent.Type.Drop:
            if event.mimeData().hasFormat(_STATS_SECTION_MIME):
                raw = bytes(event.mimeData().data(_STATS_SECTION_MIME))
                src = raw.decode("utf-8", errors="ignore").strip()
                self._panel._set_section_drop_target(None)
                if src:
                    self._panel._on_section_drop(src, self._section_id)
                event.acceptProposedAction()
                return True
        return False


class _UtilScrollResizeFilter(QObject):
    """Keep util rows inside the scroll viewport when the panel is resized."""

    def __init__(self, panel: "_StatsPanel", scroll: QScrollArea,
                 inner: QWidget) -> None:
        super().__init__(panel)
        self._panel = panel
        self._scroll = scroll
        self._inner = inner

    def pin_inner_width(self) -> None:
        vw = self._scroll.viewport().width()
        if vw > 0:
            self._inner.setMaximumWidth(vw)
            self._inner.setMinimumWidth(0)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Resize:
            self.pin_inner_width()
            QTimer.singleShot(0, self._panel.sync_util_layout)
        return False

class _StatsPanelViewportFilter(QObject):
    """Keep stats content within the visible scroll viewport width."""

    def __init__(self, panel: "_StatsPanel") -> None:
        super().__init__(panel)
        self._panel = panel

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Resize:
            self._panel._pin_main_inner_width()
            self._panel._update_scroll_tail_height()
            QTimer.singleShot(0, self._panel.sync_util_layout)
        return False

class _StatsTableHoverFilter(QObject):
    """Clear stats-table row hover highlight when the pointer leaves the table."""

    def __init__(self, clear_fn) -> None:
        super().__init__()
        self._clear_fn = clear_fn

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Leave:
            self._clear_fn()
        return False

class _StatsItemDelegate(QStyledItemDelegate):
    """Paint stats-table cells (background fill + text) ourselves instead of
    delegating to `QStyle::drawControl(CE_ItemViewItem, ...)`.

    Some native/desktop QStyle plugins (GTK/Breeze-style integration, some
    style-sheet-proxy configurations, etc.) do not honour a
    `QTableWidgetItem`'s `Qt::BackgroundRole` brush when painting item-view
    cells, which silently defeats per-row hover highlighting set via
    `item.setBackground(...)` — even though the underlying item data is
    correct and the exact same code renders fine under Qt's own Fusion/
    offscreen style. Painting the background and text directly bypasses
    QStyle/QSS entirely for this one aspect, so the highlight is guaranteed
    to be visible regardless of the active widget style. Stats-table items
    are plain text cells (no icons/checkboxes), so a minimal re-implementation
    is sufficient.
    """

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802
        painter.save()
        opt_state = option.state
        if opt_state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.color(
                QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight))
            pen_color = option.palette.color(
                QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText)
        else:
            bg = index.data(Qt.ItemDataRole.BackgroundRole)
            if isinstance(bg, QBrush) and bg.style() != Qt.BrushStyle.NoBrush:
                painter.fillRect(option.rect, bg)
            fg = index.data(Qt.ItemDataRole.ForegroundRole)
            pen_color = (fg.color() if isinstance(fg, QBrush) and
                         fg.style() != Qt.BrushStyle.NoBrush else
                         option.palette.color(QPalette.ColorRole.Text))
        painter.setPen(pen_color)
        font = index.data(Qt.ItemDataRole.FontRole)
        painter.setFont(font if isinstance(font, QFont) else option.font)
        align = index.data(Qt.ItemDataRole.TextAlignmentRole)
        align = int(align) if align is not None else int(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        rect = option.rect.adjusted(3, 0, -3, 0)
        painter.drawText(rect, align, "" if text is None else str(text))
        painter.restore()

class _StatsTableBodyCursorFilter(QObject):
    """Pointing-hand cursor over clickable table cells only (not resize grips)."""

    def __init__(self, table: QTableWidget) -> None:
        super().__init__(table)
        self._table = table
        self._armed = False

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        et = event.type()
        if et == QEvent.Type.MouseMove:
            if self._table.indexAt(event.position().toPoint()).isValid():
                obj.setCursor(Qt.CursorShape.PointingHandCursor)
                self._armed = True
            elif self._armed:
                obj.unsetCursor()
                self._armed = False
        elif et == QEvent.Type.Leave:
            if self._armed:
                obj.unsetCursor()
                self._armed = False
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

    height_changed = Signal(int)

    _MIN_H = 80
    _MAX_H = 480

    def __init__(self, is_dark: bool, get_height_fn, parent=None,
                 *, min_h: Optional[int] = None) -> None:
        super().__init__(parent)
        self._is_dark = is_dark
        self._get_height = get_height_fn
        self._min_h = self._MIN_H if min_h is None else int(min_h)
        self._dragging = False
        self._start_y = 0
        self._start_h = STATS_TABLE_DEFAULT_H
        self.setFixedHeight(8)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setToolTip("Drag to resize table height")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def set_dark(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self.update()

    def _event_global_y(self, event) -> int:
        gp = event.globalPosition() if hasattr(event, "globalPosition") else None
        if gp is not None:
            return int(gp.y())
        return int(event.globalY())

    def _drag_start(self, global_y: int) -> None:
        """Begin a resize drag. grabMouse() works on macOS; the app filter is a
        Wayland backup. Do not swallow filtered events or Cocoa can drop the
        matching mouse-release."""
        self._dragging = True
        self._start_y = global_y
        self._start_h = self._get_height()
        _HoverCursor.show(Qt.CursorShape.SizeVerCursor)
        self.grabMouse()
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

    def _drag_move(self, global_y: int) -> None:
        _HoverCursor.show(Qt.CursorShape.SizeVerCursor)
        delta = global_y - self._start_y
        self.height_changed.emit(
            max(self._min_h, min(self._MAX_H, self._start_h + delta)))

    def _drag_end(self) -> None:
        if not self._dragging:
            _HoverCursor.hide(Qt.CursorShape.SizeVerCursor)
            return
        self._dragging = False
        if QWidget.mouseGrabber() is self:
            self.releaseMouse()
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)
        _HoverCursor.hide(Qt.CursorShape.SizeVerCursor)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        """Follow the pointer during drag without consuming the event."""
        if not self._dragging:
            return False
        et = event.type()
        if et == QEvent.Type.MouseMove:
            if not (QApplication.mouseButtons() & Qt.MouseButton.LeftButton):
                self._drag_end()
                return False
            self._drag_move(self._event_global_y(event))
            return False
        if et == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            self._drag_end()
            return False
        return False

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start(self._event_global_y(event))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging:
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                self._drag_end()
                event.accept()
                return
            self._drag_move(self._event_global_y(event))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._drag_end()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if not self._dragging:
            _HoverCursor.hide(Qt.CursorShape.SizeVerCursor)
        self.update()
        super().leaveEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        if self._dragging:
            self._drag_end()
        else:
            _HoverCursor.hide(Qt.CursorShape.SizeVerCursor)
        super().hideEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        p = QPainter(self)
        if self.underMouse() or self._dragging:
            c = QColor("#6688CC")
        else:
            c = QColor("#3C3C3C" if self._is_dark else "#DDDDDD")
        y = self.height() // 2
        p.setPen(QPen(c, 1))
        p.drawLine(0, y, self.width(), y)
        p.end()

class _TraceCompareDialog(QDialog):
    """Compare summary and Statistics-aligned metrics between two tabs."""

    def __init__(
        self,
        win: "MainWindow",
        parent=None,
        idx_a: Optional[int] = None,
        idx_b: Optional[int] = None,
        ai_enabled: bool = True,
        on_query_ai: Optional[Callable] = None,
    ) -> None:
        parent_w = parent if parent is not None else (
            win if isinstance(win, QWidget) else None)
        super().__init__(parent_w)
        self.setWindowTitle("Trace Compare")
        self.setModal(True)
        self.resize(980, 560)
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
        self._scope_cb.setChecked(True)
        lay.addWidget(self._scope_cb)

        self._pages = QTabWidget()
        self._summary_table = QTableWidget(0, 4)
        self._summary_table.setHorizontalHeaderLabels(
            ["Metric", "Trace A", "Trace B", "Δ"])
        self._top_table = QTableWidget(0, 4)
        self._top_table.setHorizontalHeaderLabels(
            ["Task", "CPU% A", "CPU% B", "Δ"])
        self._core_util_table = QTableWidget(0, 4)
        self._core_util_table.setHorizontalHeaderLabels(
            ["Core", "Util% A", "Util% B", "Δ"])
        self._mig_table = QTableWidget(0, 16)
        self._mig_table.setHorizontalHeaderLabels(
            ["Task", "Migr A", "Migr B", "Δ", "Rate A", "Rate B", "Rate Δ",
             "Dwell A", "Dwell B", "Dwell Δ", "Ping A", "Ping B",
             "Cores A", "Cores B", "Primary A", "Primary B"])
        self._exec_table = QTableWidget(0, 8)
        self._exec_table.setHorizontalHeaderLabels(
            ["Task", "Runs A", "Runs B", "Avg A", "Avg B", "Max A", "Max B", "Δ max"])
        self._block_table = QTableWidget(0, 8)
        self._block_table.setHorizontalHeaderLabels(
            ["Task", "Gaps A", "Gaps B", "Avg A", "Avg B", "Max A", "Max B", "Δ avg"])
        self._inter_table = QTableWidget(0, 8)
        self._inter_table.setHorizontalHeaderLabels(
            ["Task", "Runs A", "Runs B", "Avg A", "Avg B", "Max A", "Max B", "Δ avg"])
        self._preempt_table = QTableWidget(0, 6)
        self._preempt_table.setHorizontalHeaderLabels(
            ["Victim", "Count A", "Count B", "Δ", "Total A", "Total B"])
        self._sync_table = QTableWidget(0, 4)
        self._sync_table.setHorizontalHeaderLabels(
            ["Metric", "Trace A", "Trace B", "Δ"])
        self._all_tables = (
            self._summary_table, self._top_table, self._core_util_table,
            self._mig_table, self._exec_table, self._block_table,
            self._inter_table, self._preempt_table, self._sync_table,
        )
        for tbl in self._all_tables:
            tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            tbl.verticalHeader().setVisible(False)
            tbl.horizontalHeader().setStretchLastSection(True)
        self._pages.addTab(self._summary_table, "Summary")
        self._pages.addTab(self._top_table, "Top Tasks")
        self._pages.addTab(self._core_util_table, "Core Util")
        self._pages.addTab(self._mig_table, "Core Migrations")
        self._pages.addTab(self._exec_table, "Execution")
        self._pages.addTab(self._block_table, "Blocking")
        self._pages.addTab(self._inter_table, "Inter-Arrival")
        self._pages.addTab(self._preempt_table, "Preemption")
        self._pages.addTab(self._sync_table, "Sync")
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
        self._ai_enabled = bool(ai_enabled)
        self._on_query_ai = on_query_ai
        self._ai_btn = btns.addButton(
            "Query with AI…", QDialogButtonBox.ButtonRole.ActionRole)
        self._ai_btn.clicked.connect(self._query_with_ai)
        self.set_ai_enabled(self._ai_enabled)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        lay.addWidget(btns)
        self._win = win
        for i, tab in enumerate(win._tabs):
            label = os.path.basename(tab.path)
            self._combo_a.addItem(label, i)
            self._combo_b.addItem(label, i)
        if win._tabs:
            ia = 0 if idx_a is None else max(0, min(int(idx_a), len(win._tabs) - 1))
            ib = min(1, len(win._tabs) - 1) if idx_b is None else max(
                0, min(int(idx_b), len(win._tabs) - 1))
            self._combo_a.setCurrentIndex(ia)
            self._combo_b.setCurrentIndex(ib)
        self._combo_a.currentIndexChanged.connect(self._refresh)
        self._combo_b.currentIndexChanged.connect(self._refresh)
        self._scope_cb.toggled.connect(self._refresh)
        self._refresh()

    def set_ai_enabled(self, enabled: bool) -> None:
        self._ai_enabled = bool(enabled)
        if getattr(self, "_ai_btn", None) is None:
            return
        self._ai_btn.setToolTip(
            "Open the AI Assistant and walk through these Trace Compare tables"
            if self._ai_enabled else
            "Enable AI Assistant in Settings → AI")

    def _selected_tab_indices(self) -> Tuple[Optional[int], Optional[int]]:
        return self._combo_a.currentData(), self._combo_b.currentData()

    def _query_with_ai(self) -> None:
        idx_a, idx_b = self._selected_tab_indices()
        enabled = self._ai_enabled
        cb = self._on_query_ai
        self.done(int(QDialog.DialogCode.Accepted))
        if cb is not None:
            cb(enabled, idx_a, idx_b)

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

    def _compare_args(self):
        ta = self._trace_for_combo(self._combo_a)
        tb = self._trace_for_combo(self._combo_b)
        if ta is None or tb is None:
            return None
        lo_a, hi_a = self._range_for_trace(self._combo_a)
        lo_b, hi_b = self._range_for_trace(self._combo_b)
        return ta, tb, lo_a, hi_a, lo_b, hi_b

    @staticmethod
    def _fill_table(table: QTableWidget, rows: List[List], left_cols: int = 1) -> None:
        table.setRowCount(len(rows))
        for ri, vals in enumerate(rows):
            for ci, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                if ci < left_cols:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                table.setItem(ri, ci, item)

    def _refresh(self) -> None:
        args = self._compare_args()
        if args is None:
            for tbl in self._all_tables:
                tbl.setRowCount(0)
            return
        tables = _build_trace_compare_rows(*args)
        self._fill_table(self._summary_table, tables.get("summary", []))
        self._fill_table(self._top_table, tables.get("top", []))
        self._fill_table(self._core_util_table, tables.get("core_util", []))
        self._fill_table(self._mig_table, tables.get("migrations", []))
        self._fill_table(self._exec_table, tables.get("execution", []))
        self._fill_table(self._block_table, tables.get("blocking", []))
        self._fill_table(self._inter_table, tables.get("inter_arrival", []))
        self._fill_table(self._preempt_table, tables.get("preemption", []))
        self._fill_table(self._sync_table, tables.get("sync", []))

    def _tab_name(self, combo: QComboBox) -> str:
        return combo.currentText() or "Trace"

    def _export_csv(self) -> None:
        args = self._compare_args()
        if args is None:
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

        tables = _build_trace_compare_rows(*args)
        text = _build_compare_csv(
            self._tab_name(self._combo_a),
            self._tab_name(self._combo_b),
            self._scope_cb.isChecked(),
            tables,
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
        args = self._compare_args()
        if args is None:
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

        tables = _build_trace_compare_rows(*args)
        report = _build_compare_html(
            self._tab_name(self._combo_a),
            self._tab_name(self._combo_b),
            self._scope_cb.isChecked(),
            tables,
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

    cell_clicked = Signal(int, int)
    row_clicked = Signal(int)

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

    def _cell_geometry(self, layout_w: Optional[int] = None) -> Tuple[int, float]:
        if self._mode == 'matrix':
            n_bins = len(self._col_labels) or 1
            x0 = self._LEFT_PAD + self._label_w
            return x0, float(self._MATRIX_CELL_MIN_W)
        n_bins = len(self._grid[0]) if self._grid else 1
        x0 = self._LEFT_PAD + self._label_w
        w = layout_w if layout_w is not None else self.width()
        cell_w = max(self._CELL_MIN_W, (w - x0 - 4) // max(1, n_bins))
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

    def set_hover_row(self, ri: Optional[int]) -> None:
        """Programmatically highlight a row (e.g. Core-Pair focus)."""
        hover_ri = ri if ri is not None and 0 <= ri < len(self._row_labels) else None
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
            pos.x() if pos else event.position().x(),
            pos.y() if pos else event.position().y(),
        )
        return super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self.clear_hover()
        return super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self._row_labels:
            return super().mousePressEvent(event)
        pos = event.position() if hasattr(event, "position") else None
        x = pos.x() if pos else event.position().x()
        y = pos.y() if pos else event.position().y()
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
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "to→")
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
        try:
            self._paint_grid(p, scroll_x, scroll_y, clip, show_hover=True)
        finally:
            p.end()

    def _paint_grid(self, p: QPainter, scroll_x: int, scroll_y: int, clip: QRect,
                    *, show_hover: bool = True, layout_w: Optional[int] = None) -> None:
        if not self._row_labels:
            return
        header_h = self._header_h()
        w = layout_w if layout_w is not None else self.width()
        x0, cell_w = self._cell_geometry(layout_w=w)
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
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
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
            if show_hover and self._hover_ri == ri:
                row_w = label_right + n_cols * cell_w
                p.fillRect(QRectF(0, y, row_w, self._ROW_H - 1),
                           QColor(91, 155, 213, 46))

    def render_full_pixmap(self) -> QPixmap:
        """Render the full heatmap grid (all rows/columns) for PNG export."""
        size = self._content_size()
        pix = QPixmap(size)
        pix.fill(self.palette().color(QPalette.Window))
        saved_hover = self._hover_ri
        self._hover_ri = None
        p = QPainter(pix)
        try:
            self._paint_grid(
                p, 0, 0, QRect(0, 0, size.width(), size.height()),
                show_hover=False, layout_w=size.width())
        finally:
            p.end()
            self._hover_ri = saved_hover
        return pix

    def render_full_svg(self, path: str, title: str) -> None:
        """Render the full heatmap grid to an SVG file."""
        size = self._content_size()
        gen = QSvgGenerator()
        gen.setFileName(path)
        gen.setSize(size)
        gen.setViewBox(QRectF(0, 0, size.width(), size.height()))
        gen.setTitle(title)
        gen.setDescription("Generated by RTOS BTF Viewer")
        saved_hover = self._hover_ri
        self._hover_ri = None
        p = QPainter(gen)
        try:
            self._paint_grid(
                p, 0, 0, QRect(0, 0, size.width(), size.height()),
                show_hover=False, layout_w=size.width())
        finally:
            p.end()
            self._hover_ri = saved_hover

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
        self._bounce_only: bool = False

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
        self._bounce_filter_btn = QPushButton("Show: All Migrations")
        self._bounce_filter_btn.setCheckable(True)
        self._bounce_filter_btn.setChecked(False)
        self._bounce_filter_btn.setToolTip(
            "Toggle between showing all migrations and only lock-bounce migrations\n"
            "(migrations that occurred while a mutex was held across different cores).")
        self._bounce_filter_btn.clicked.connect(self._on_bounce_filter_toggled)
        self._bounce_filter_btn.setVisible(_trace_has_core_bounce_holds(trace))
        nav.addWidget(self._bounce_filter_btn)
        lay.addLayout(nav)

        self._sub_label = QLabel()
        lay.addWidget(self._sub_label)

        self._empty_label = QLabel("No migrations in scope.")
        self._empty_label.setVisible(False)
        lay.addWidget(self._empty_label)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
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

        export_row = QHBoxLayout()
        export_row.setContentsMargins(0, 4, 0, 0)
        self._btn_export_png = QPushButton("Export PNG")
        self._btn_export_svg = QPushButton("Export SVG")
        self._btn_export_png.clicked.connect(self._export_png)
        self._btn_export_svg.clicked.connect(self._export_svg)
        self._btn_export_png.setEnabled(False)
        self._btn_export_svg.setEnabled(False)
        export_row.addWidget(self._btn_export_png)
        export_row.addWidget(self._btn_export_svg)
        export_row.addStretch(1)
        lay.addLayout(export_row)

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

    def focus_pair(self, from_core: str, to_core: str,
                   bounce_only: bool = False) -> bool:
        """Open (or re-filter) the heatmap focused on a directed core pair.

        Prefer Bounce Only when *bounce_only* is true. Returns False if the
        pair has no migrations under the current scope/filter.
        """
        if bool(self._bounce_only) != bool(bounce_only):
            self._bounce_filter_btn.setChecked(bool(bounce_only))
            self._on_bounce_filter_toggled(bool(bounce_only))
        else:
            self._go_level0()
        label = f"{_core_short_name(from_core)}→{_core_short_name(to_core)}"
        if self._uses_matrix:
            if from_core not in self._matrix_cores:
                return False
            self._show_outgoing_level(from_core)
            found = next(
                ((fc, tc, lbl) for fc, tc, lbl in self._pairs
                 if fc == from_core and tc == to_core),
                None,
            )
            if found is None:
                return False
            self._show_pair_time_level(found[0], found[1], found[2])
            return True
        # Non-matrix: top level is already pair × time — scroll to the row.
        ri = next(
            (i for i, (fc, tc, _lbl) in enumerate(self._pairs)
             if fc == from_core and tc == to_core),
            -1,
        )
        if ri < 0:
            return False
        self._canvas.set_hover_row(ri)
        self._scroll_heatmap_to_row(ri)
        self._sub_label.setText(
            f"Core-pair migrations over time bins · focused {label}"
            f"{self._scope_suffix}")
        return True

    def eventFilter(self, watched, event) -> bool:
        if watched is self._scroll.viewport():
            et = event.type()
            if et == QEvent.Type.MouseMove:
                pos = self._canvas.mapFrom(self._scroll.viewport(), event.position().toPoint())
                self._canvas.set_hover_pos(pos.x(), pos.y())
            elif et == QEvent.Type.Leave:
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

    def _on_bounce_filter_toggled(self, checked: bool) -> None:
        """Toggle heatmap between all migrations and lock-bounce-only migrations."""
        self._bounce_only = checked
        self._bounce_filter_btn.setText(
            "Show: Bounce Only" if checked else "Show: All Migrations")
        # Invalidate scope cache so grids are recomputed with the new filter
        self._scope_cache.clear()
        lo, hi = self._scope_lo, self._scope_hi
        pairs, grid, time_bins = _migration_heatmap_data(
            self._trace, lo, hi, bounce_only=self._bounce_only)
        self._pairs = pairs
        self._grid0 = grid
        if self._uses_matrix:
            self._matrix_cores, self._matrix_grid = _migration_heatmap_matrix(
                self._trace, lo, hi, bounce_only=self._bounce_only)
        t_min = lo if lo is not None else self._trace.time_min
        t_hi = hi if hi is not None else self._trace.time_max
        span = max(t_hi - t_min, 1)
        self._ov_t_min = t_min
        self._ov_t_max = t_hi
        self._ov_bin_w = span / time_bins
        self._ov_time_bins = time_bins
        self._cache_scope_grid(lo, hi, pairs, grid, time_bins, t_min, t_hi, span)
        self._go_level0()

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
            self._trace, lo, hi, bounce_only=self._bounce_only)
        self._pairs = pairs
        self._grid0 = grid
        if self._uses_matrix:
            self._matrix_cores, self._matrix_grid = _migration_heatmap_matrix(
                self._trace, lo, hi, bounce_only=self._bounce_only)
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

    def _export_level_slug(self) -> str:
        if self._uses_matrix:
            if self._level == 0:
                return "matrix"
            if self._level == 1:
                return "outgoing"
            return "tasks"
        if self._level >= 1:
            return "tasks"
        return "pairs"

    def _export_base_name(self) -> str:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"migration-heatmap-{self._export_level_slug()}-{stamp}"

    def _export_png(self) -> None:
        if not self._canvas._row_labels:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Migration Heatmap PNG",
            self._export_base_name() + ".png",
            "PNG files (*.png);;All files (*)",
        )
        if not path:
            return
        try:
            if self._canvas.render_full_pixmap().save(path):
                wnd = self.parent()
                if isinstance(wnd, QMainWindow):
                    wnd.statusBar().showMessage(f"Exported heatmap: {path}", 4000)
            else:
                QMessageBox.critical(self, "Export Error", "Could not save PNG.")
        except (OSError, RuntimeError) as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    def _export_svg(self) -> None:
        if not self._canvas._row_labels:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Migration Heatmap SVG",
            self._export_base_name() + ".svg",
            "SVG files (*.svg);;All files (*)",
        )
        if not path:
            return
        try:
            self._canvas.render_full_svg(path, "Migration Heatmap")
            wnd = self.parent()
            if isinstance(wnd, QMainWindow):
                wnd.statusBar().showMessage(f"Exported heatmap: {path}", 4000)
        except (OSError, RuntimeError) as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    def _scroll_heatmap_to_top(self) -> None:
        """Reset scroll after level/content change (level-1 grid is often shorter)."""
        def _do() -> None:
            self._canvas._sync_widget_size()
            self._scroll.updateGeometry()
            self._scroll.verticalScrollBar().setValue(0)
            self._scroll.horizontalScrollBar().setValue(0)
        QTimer.singleShot(0, _do)

    def _scroll_heatmap_to_row(self, ri: int) -> None:
        """Scroll so *ri* is near the top of the viewport."""
        def _do() -> None:
            self._canvas._sync_widget_size()
            self._scroll.updateGeometry()
            y = max(0, ri * self._canvas._ROW_H)
            self._scroll.verticalScrollBar().setValue(y)
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

    def _set_heatmap_has_data(self, has_data: bool) -> None:
        self._empty_label.setVisible(not has_data)
        self._scroll.setVisible(has_data)
        self._btn_export_png.setEnabled(has_data)
        self._btn_export_svg.setEnabled(has_data)

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
            self._set_heatmap_has_data(has_data)
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
            self._set_heatmap_has_data(has_data)
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
        self._set_heatmap_has_data(has_data)
        self._empty_label.setText("No migrations in scope.")
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
        self._set_heatmap_has_data(has_data)
        self._empty_label.setText("No migrations in scope.")
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
        self._set_heatmap_has_data(has_data)
        self._empty_label.setText("No task migrations in this cell.")
        if has_data:
            # Annotate row labels with ingress (▼) / egress (▲) / balanced (⇄)
            # indicators by comparing this direction vs. the reverse direction
            # for each task over the full cursor scope.
            scope_lo = self._scope_lo
            scope_hi = self._scope_hi
            rev_totals: Dict[str, int] = {}
            for _m in self._trace.migrations:
                if _m.from_core != tc or _m.to_core != fc:
                    continue
                if scope_lo is not None and _m.ns < scope_lo:
                    continue
                if scope_hi is not None and _m.ns > scope_hi:
                    continue
                rev_totals[_m.merge_key] = rev_totals.get(_m.merge_key, 0) + 1
            annotated_labels: List[str] = []
            for (mk, disp), row_counts in zip(rows, grid):
                fwd = sum(row_counts)
                rev = rev_totals.get(mk, 0)
                if fwd > rev * 1.5:
                    sym = "▲"   # primarily egress from fc
                elif rev > fwd * 1.5:
                    sym = "▼"   # primarily ingress back to fc
                else:
                    sym = "⇄"   # balanced / symmetric
                annotated_labels.append(f"{sym} {disp}")
            self._set_canvas(annotated_labels, grid)
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

class _ChordDiagramWidget(QWidget):
    """Paint core-to-core migration volume as a circular chord diagram.

    *compact=True* matches web MiniChordPanel (inspector sidebar).
    *compact=False* matches web ChordDiagramDialog (standalone popup).
    """

    hover_changed = Signal(object)  # emits int core index, or None
    hover_info = Signal(object)  # None | {type, ...} for inspector footer
    core_clicked = Signal(object)  # {clear: True} or {core_index, side}
    pair_clicked = Signal(int)  # second core index (shift-click)
    corridor_clicked = Signal(str, str)  # from_core, to_core
    corridor_dbl = Signal(str, str)

    def __init__(self, parent=None, *, compact: bool = False):
        super().__init__(parent)
        self._compact = bool(compact)
        # MiniChordPanel OUTER_PAD=36; standalone ChordDiagramDialog = 48.
        self._outer_pad = 36.0 if self._compact else 48.0
        self._min_radius = 16.0 if self._compact else 20.0
        self._bidir_sep = 5.0 if self._compact else 6.0
        self._ribbon_alpha = 0.72 if self._compact else 0.75
        self._label_gap = 12.0 if self._compact else 14.0
        self._matrix_pad = 36.0 if self._compact else 40.0
        self._cores: List[str] = []
        self._grid: list = [[]]
        self._layout: Optional[ChordLayout] = None
        self._max_count = 0
        self._hover_index: Optional[int] = None
        self._hover_side: Optional[str] = None  # 'egress' | 'ingress'
        self._hover_corridor: Optional[Tuple[int, int]] = None
        self._last_hover_info = None
        self._pinned_hover = False
        self._focus_pair: Optional[Tuple[int, int]] = None
        self._focus_cores: List[int] = []
        self._direction_mode = "all"
        self._view_mode = "circle"
        self.setMouseTracking(True)
        if self._compact:
            self.setMinimumSize(160, 160)
        else:
            self.setMinimumSize(200, 200)
        self._circle_btn = QPushButton("Circle", self)
        self._matrix_btn = QPushButton("Matrix", self)
        fs = 10 if self._compact else 11
        for _b in (self._circle_btn, self._matrix_btn):
            _b.setCheckable(True)
            _b.setVisible(False)
            _b.setFixedHeight(20 if self._compact else 22)
            _b.setStyleSheet(
                f"QPushButton {{ font-size:{fs}px; padding:2px 6px; }}")
        self._circle_btn.clicked.connect(lambda: self.set_view_mode("circle"))
        self._matrix_btn.clicked.connect(lambda: self.set_view_mode("matrix"))

    def set_data(self, cores: List[str], grid: list) -> None:
        cores_l = list(cores or [])
        grid_l = [list(row) for row in (grid or [])] or [[]]
        if cores_l == self._cores and grid_l == self._grid:
            return
        self._cores = cores_l
        self._grid = grid_l
        self._layout = _build_chord_layout(self._cores, self._grid)
        m = 0
        for i in range(len(self._cores)):
            row = self._grid[i] if i < len(self._grid) else []
            for j in range(len(self._cores)):
                if i == j:
                    continue
                v = row[j] if j < len(row) else 0
                if v > m:
                    m = v
        self._max_count = m
        if self._hover_index is not None or self._hover_corridor is not None:
            self._hover_index = None
            self._hover_side = None
            self._hover_corridor = None
            self.hover_changed.emit(None)
            self._emit_hover_info(None)
        self._pinned_hover = False
        prev_n = getattr(self, "_last_core_n", 0)
        n = len(self._cores)
        if n > 16 and prev_n <= 16:
            self._view_mode = "matrix"
        elif n <= 16:
            self._view_mode = "circle"
        self._last_core_n = n
        self._sync_view_toggle()
        self.update()

    def set_direction_mode(self, mode: str) -> None:
        m = mode if mode in ("all", "egress", "ingress") else "all"
        if m == self._direction_mode:
            return
        self._direction_mode = m
        self.update()

    def set_focus_cores(self, indices: Optional[list] = None) -> None:
        out: List[int] = []
        n = len(self._cores)
        for i in indices or []:
            try:
                ii = int(i)
            except (TypeError, ValueError):
                continue
            if 0 <= ii < n:
                out.append(ii)
        if out == self._focus_cores:
            return
        self._focus_cores = out
        self.update()

    def set_view_mode(self, mode: str) -> None:
        m = "matrix" if mode == "matrix" else "circle"
        self._view_mode = m
        self._sync_view_toggle()
        self.update()

    def _sync_view_toggle(self) -> None:
        show = len(self._cores) > 16
        self._circle_btn.setVisible(show)
        self._matrix_btn.setVisible(show)
        self._circle_btn.setChecked(self._view_mode == "circle")
        self._matrix_btn.setChecked(self._view_mode == "matrix")
        self._layout_view_toggle()

    def _layout_view_toggle(self) -> None:
        if not self._circle_btn.isVisible():
            return
        self._circle_btn.adjustSize()
        self._matrix_btn.adjustSize()
        # Web MiniChordPanel: top-right, 4px inset.
        gap, inset = 4, 4
        mw = self._matrix_btn.width()
        cw = self._circle_btn.width()
        self._matrix_btn.move(max(inset, self.width() - inset - mw), inset)
        self._circle_btn.move(
            max(inset, self._matrix_btn.x() - gap - cw), inset)

    def resizeEvent(self, event) -> None:
        self._layout_view_toggle()
        return super().resizeEvent(event)

    def set_hover_index(self, index: Optional[int], *, pinned: bool = False) -> None:
        """Programmatically highlight a core arc (and its chords)."""
        if index is not None and not (0 <= index < len(self._cores)):
            index = None
        self._pinned_hover = bool(pinned) and index is not None
        if index != self._hover_index:
            self._hover_index = index
            self._hover_side = None if index is None else self._hover_side
            self.hover_changed.emit(index)
            self.update()
        elif pinned:
            self.update()

    def clear_hover(self) -> None:
        if self._pinned_hover:
            return
        if (self._hover_index is not None or self._hover_side is not None
                or self._hover_corridor is not None):
            self._hover_index = None
            self._hover_side = None
            self._hover_corridor = None
            self.hover_changed.emit(None)
            self._emit_hover_info(None)
            self.update()

    def leaveEvent(self, event) -> None:
        self.clear_hover()
        return super().leaveEvent(event)

    @staticmethod
    def _point_at(cx: float, cy: float, angle: float, r: float) -> QPointF:
        return QPointF(cx + r * math.cos(angle), cy + r * math.sin(angle))

    def _geometry(self, w: Optional[int] = None,
                 h: Optional[int] = None) -> Tuple[float, float, float]:
        w = w if w is not None else self.width()
        h = h if h is not None else self.height()
        cx, cy = w / 2.0, h / 2.0
        radius = max(self._min_radius, min(w, h) / 2.0 - self._outer_pad)
        return cx, cy, radius

    def mouseMoveEvent(self, event) -> None:
        pos = event.position() if hasattr(event, "position") else event.pos()
        self._update_hover(pos.x(), pos.y())
        return super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        pos = event.position() if hasattr(event, "position") else event.pos()
        mx, my = pos.x(), pos.y()
        corr = self._hit_corridor(mx, my)
        if corr is not None:
            i, j = corr
            self.corridor_clicked.emit(self._cores[i], self._cores[j])
            return super().mousePressEvent(event)
        hit = self._hit_arc(mx, my)
        if hit is None:
            self.core_clicked.emit({"clear": True})
            return super().mousePressEvent(event)
        mods = event.modifiers()
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        if shift:
            self.pair_clicked.emit(int(hit[0]))
        else:
            self.core_clicked.emit({"core_index": int(hit[0]), "side": hit[1]})
        return super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        pos = event.position() if hasattr(event, "position") else event.pos()
        corr = self._hit_corridor(pos.x(), pos.y())
        if corr is not None:
            i, j = corr
            self.corridor_dbl.emit(self._cores[i], self._cores[j])
        return super().mouseDoubleClickEvent(event)

    def _hit_matrix_cell(self, mx: float, my: float) -> Optional[Tuple[int, int]]:
        n = len(self._cores)
        if not n:
            return None
        w, h = self.width(), self.height()
        pad_l = pad_t = self._matrix_pad
        cell = max(4.0, min((w - pad_l - 8) / n, (h - pad_t - 8) / n))
        j = int((mx - pad_l) / cell)
        i = int((my - pad_t) / cell)
        if i < 0 or j < 0 or i >= n or j >= n or i == j:
            return None
        row = self._grid[i] if i < len(self._grid) else []
        v = row[j] if j < len(row) else 0
        if not v:
            return None
        return i, j

    def _hit_arc(self, mx: float, my: float) -> Optional[Tuple[int, str]]:
        if self._view_mode == "matrix":
            return None
        layout = self._layout
        if layout is None or not layout.arcs:
            return None
        cx, cy, R = self._geometry()
        dx, dy = mx - cx, my - cy
        dist = math.hypot(dx, dy)
        side = _chord_hit_ring(dist, R)
        if side is None:
            return None
        angle = math.atan2(dy, dx)
        for arc in layout.arcs:
            a = angle
            while a < arc.start_angle:
                a += 2 * math.pi
            while a > arc.start_angle + 2 * math.pi:
                a -= 2 * math.pi
            if a <= arc.end_angle:
                return arc.index, side
        return None

    @staticmethod
    def _dist_point_to_quad(mx: float, my: float, p1: QPointF, ctrl: QPointF,
                            p2: QPointF, steps: int = 16) -> float:
        best = 1e18
        for k in range(steps + 1):
            t = k / float(steps)
            u = 1.0 - t
            x = u * u * p1.x() + 2 * u * t * ctrl.x() + t * t * p2.x()
            y = u * u * p1.y() + 2 * u * t * ctrl.y() + t * t * p2.y()
            d = math.hypot(mx - x, my - y)
            if d < best:
                best = d
        return best

    def _emit_hover_info(self, info) -> None:
        if info == self._last_hover_info:
            return
        self._last_hover_info = info
        self.hover_info.emit(info)

    def _hit_corridor(self, mx: float, my: float) -> Optional[Tuple[int, int]]:
        if self._view_mode == "matrix":
            return self._hit_matrix_cell(mx, my)
        layout = self._layout
        if layout is None or not self._cores:
            return None
        cx, cy, R = self._geometry()
        _r_e, _r_i, r_ribbon = _chord_ring_geometry(R)
        best = None
        best_d = 1e18
        n = len(self._cores)
        max_c = float(self._max_count or 1)
        pt = QPointF(mx, my)
        stroker = QPainterPathStroker()
        grid = self._grid
        for i in range(n):
            row = grid[i] if i < len(grid) else []
            for j in range(n):
                if i == j:
                    continue
                count = row[j] if j < len(row) else 0
                if not count:
                    continue
                a0 = layout.egress_tick_angle(i, j)
                a1 = layout.ingress_tick_angle(j, i)
                src_half, dst_half = layout.ribbon_half_widths(i, j, max_c)
                bidir = (grid[j][i] if j < len(grid) and i < len(grid[j]) else 0) > 0
                sign = 1 if i < j else -1
                off = self._bidir_sep * sign if bidir else 0.0
                path = self._tapered_ribbon_path(
                    cx, cy, r_ribbon, a0, a1, src_half, dst_half, off)
                p1 = self._point_at(cx, cy, a0, r_ribbon)
                p2 = self._point_at(cx, cy, a1, r_ribbon)
                mx_ = (p1.x() + p2.x()) / 2
                my_ = (p1.y() + p2.y()) / 2
                vx, vy = mx_ - cx, my_ - cy
                vlen = math.hypot(vx, vy) or 1.0
                perp_x, perp_y = -vy / vlen, vx / vlen
                pull = 0.18
                ctrl = QPointF(
                    cx + (vx / vlen) * r_ribbon * pull + perp_x * off,
                    cy + (vy / vlen) * r_ribbon * pull + perp_y * off)
                score = self._dist_point_to_quad(mx, my, p1, ctrl, p2)
                stroker.setWidth(max(10.0, float(src_half + dst_half) + 4.0))
                fat = stroker.createStroke(path)
                thresh = max(float(src_half), float(dst_half), 4.0) + 8.0
                if not (path.contains(pt) or fat.contains(pt) or score <= thresh):
                    continue
                if score < best_d:
                    best_d = score
                    best = (i, j)
        return best

    def _update_hover(self, mx: float, my: float) -> None:
        if self._view_mode == "matrix":
            cell = self._hit_matrix_cell(mx, my)
            if cell is None:
                self.clear_hover()
                return
            i, j = cell
            info = {
                "type": "corridor",
                "from": self._cores[i],
                "to": self._cores[j],
                "count": (self._grid[i][j] if i < len(self._grid)
                          and j < len(self._grid[i]) else 0),
            }
            changed = self._hover_corridor != cell
            self._hover_corridor = cell
            self._hover_index = i
            self._hover_side = "egress"
            self._emit_hover_info(info)
            if changed:
                self.hover_changed.emit(i)
                self.update()
            return
        corr = self._hit_corridor(mx, my)
        if corr is not None:
            i, j = corr
            info = {
                "type": "corridor",
                "from": self._cores[i],
                "to": self._cores[j],
                "count": (self._grid[i][j] if i < len(self._grid)
                          and j < len(self._grid[i]) else 0),
            }
            changed = (self._hover_corridor != corr
                       or self._hover_index != i)
            self._hover_corridor = corr
            self._hover_index = i
            self._hover_side = "egress"
            self._emit_hover_info(info)
            if changed:
                self.hover_changed.emit(i)
                self.update()
            return
        hit = self._hit_arc(mx, my)
        if hit is None:
            self.clear_hover()
            return
        found, side = hit
        self._hover_corridor = None
        self._emit_hover_info({"type": "core", "index": found, "side": side})
        if found != self._hover_index or side != self._hover_side:
            self._hover_index = found
            self._hover_side = side
            self.hover_changed.emit(found)
            self.update()

    def _mono_font(self, px: int, bold: bool = False) -> QFont:
        font = QFont(_get_fixed_font_family())
        font.setPixelSize(int(px))
        font.setBold(bool(bold))
        return font

    def _stroke_arc(self, p: QPainter, cx: float, cy: float, r: float,
                    a0: float, a1: float, pen: QPen) -> None:
        """True circular arc; angles match canvas (0=east, +clockwise, y-down)."""
        span = a1 - a0
        if abs(span) < 1e-9 or r <= 0:
            return
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        # Qt: 0=3 o'clock, +CCW; negate so increasing math angle is clockwise.
        start_16 = int(round(-math.degrees(a0) * 16))
        span_16 = int(round(-math.degrees(span) * 16))
        if span_16 == 0:
            return
        p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), start_16, span_16)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            self._paint(p, self.width(), self.height())
        finally:
            p.end()

    def _paint_matrix(self, p: QPainter, w: int, h: int) -> None:
        cores = self._cores
        n = len(cores)
        if not n:
            return
        pad_l = pad_t = self._matrix_pad
        cell = max(4.0, min((w - pad_l - 8) / n, (h - pad_t - 8) / n))
        max_c = float(self._max_count or 1)
        label_color = self.palette().color(QPalette.ColorRole.WindowText)
        label_color.setAlpha(160)
        p.setFont(self._mono_font(9))
        p.setPen(label_color)
        extra = set(self._focus_cores or [])
        if self._hover_index is not None:
            extra.add(int(self._hover_index))
        fp = self._focus_pair
        if fp:
            extra.add(int(fp[0]))
            extra.add(int(fp[1]))
        hc = getattr(self, "_hover_corridor", None)
        if hc:
            extra.add(int(hc[0]))
            extra.add(int(hc[1]))
        step = _chord_label_step(n, min_px=14.0, span_px=n * cell)
        for i, core in enumerate(cores):
            if not _chord_label_visible(i, step, extra):
                continue
            name = _core_short_name(core)
            p.drawText(
                QRectF(0, pad_t + i * cell, pad_l - 4, cell),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                name)
            p.save()
            p.translate(pad_l + i * cell + cell / 2.0, pad_t - 4)
            p.rotate(-45)
            p.drawText(QPointF(0, 0), name)
            p.restore()
        grid = self._grid
        focus_pair = self._focus_pair
        dmode = self._direction_mode
        focus_cores = self._focus_cores
        for i in range(n):
            row = grid[i] if i < len(grid) else []
            for j in range(n):
                v = 0 if i == j else (row[j] if j < len(row) else 0)
                if dmode == "egress" and focus_cores and i != focus_cores[0]:
                    v = 0
                if dmode == "ingress" and focus_cores and j != focus_cores[0]:
                    v = 0
                x = pad_l + j * cell
                y = pad_t + i * cell
                is_dim = self._is_dim_pair(i, j)
                r = QRectF(x, y, max(1.0, cell - 1), max(1.0, cell - 1))
                if not v:
                    p.setOpacity(0.15)
                    p.fillRect(r, QColor("#444444"))
                else:
                    p.setOpacity(
                        (0.08 if is_dim else 0.9)
                        * min(1.0, 0.25 + 0.75 * (v / max_c)))
                    p.fillRect(r, QColor(_core_color(cores[i])))
        p.setOpacity(1.0)

    def _paint(self, p: QPainter, w: int, h: int) -> None:
        cores = self._cores
        layout = self._layout
        if not cores:
            return
        if self._view_mode == "matrix":
            self._paint_matrix(p, w, h)
            return
        if layout is None or not layout.arcs:
            return
        cx, cy, R = self._geometry(w, h)
        r_egress, r_ingress, r_ribbon = _chord_ring_geometry(R)
        max_count = self._max_count or 1
        hovered = self._hover_index
        hover_side = self._hover_side
        focus_pair = getattr(self, "_focus_pair", None)
        grid = self._grid

        for i in range(len(cores)):
            row = grid[i] if i < len(grid) else []
            for j in range(len(cores)):
                if i == j:
                    continue
                count = row[j] if j < len(row) else 0
                if not count:
                    continue
                focus_cores = self._focus_cores
                dmode = self._direction_mode
                if dmode == "egress" and focus_cores and i != focus_cores[0]:
                    continue
                if dmode == "ingress" and focus_cores and j != focus_cores[0]:
                    continue
                bidir = (grid[j][i] if j < len(grid) and i < len(grid[j]) else 0) > 0
                a0 = layout.egress_tick_angle(i, j)
                a1 = layout.ingress_tick_angle(j, i)
                src_half, dst_half = layout.ribbon_half_widths(i, j, max_count)
                sign = 1 if i < j else -1
                bidir_offset = self._bidir_sep * sign if bidir else 0.0
                path = self._tapered_ribbon_path(
                    cx, cy, r_ribbon, a0, a1, src_half, dst_half, bidir_offset)
                p1 = self._point_at(cx, cy, a0, r_ribbon)
                p2 = self._point_at(cx, cy, a1, r_ribbon)

                is_dim = self._is_dim_pair(i, j)
                hot = self._hover_corridor == (i, j)
                p.setOpacity(
                    0.05 if is_dim else (0.95 if hot else self._ribbon_alpha))

                grad = QLinearGradient(p1, p2)
                grad.setColorAt(0.0, QColor(_core_color(cores[i])))
                grad.setColorAt(_CHORD_GRAD_SOURCE_STOP, QColor(_core_color(cores[i])))
                grad.setColorAt(1.0, QColor(_core_color(cores[j])))
                p.setBrush(QBrush(grad))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawPath(path)
        p.setOpacity(1.0)

        label_color = self.palette().color(QPalette.ColorRole.WindowText)
        label_color.setAlpha(160)
        if self._compact:
            normal_font, bold_font = self._mono_font(10), self._mono_font(11, True)
        else:
            normal_font, bold_font = self._mono_font(11), self._mono_font(12, True)

        extra_lbl = set(self._focus_cores or [])
        if hovered is not None:
            extra_lbl.add(int(hovered))
        if focus_pair:
            extra_lbl.add(int(focus_pair[0]))
            extra_lbl.add(int(focus_pair[1]))
        hc = getattr(self, "_hover_corridor", None)
        if hc:
            extra_lbl.add(int(hc[0]))
            extra_lbl.add(int(hc[1]))
        circ = 2.0 * math.pi * max(R, 1.0)
        label_step = _chord_label_step(len(cores), min_px=16.0, span_px=circ)

        for arc in layout.arcs:
            is_hover = hovered == arc.index
            focused = is_hover or self._arc_focused(arc.index)
            dim_arc = (
                (hovered is not None or focus_pair is not None
                 or bool(self._focus_cores))
                and not focused)
            # Outer = egress / departures
            pen_out = QPen(QColor(_core_color(arc.core)))
            pen_out.setWidthF(_CHORD_ARC_OUTER)
            pen_out.setCapStyle(Qt.PenCapStyle.FlatCap)
            if dim_arc:
                p.setOpacity(0.25)
            elif hover_side == "ingress" and is_hover:
                p.setOpacity(0.35)
            else:
                p.setOpacity(1.0)
            self._stroke_arc(
                p, cx, cy, r_egress, arc.start_angle, arc.end_angle, pen_out)
            # Inner = ingress / arrivals
            pen_in = QPen(QColor(_core_color(arc.core)))
            pen_in.setWidthF(_CHORD_ARC_INNER)
            pen_in.setCapStyle(Qt.PenCapStyle.FlatCap)
            if dim_arc:
                p.setOpacity(0.25)
            elif hover_side == "egress" and is_hover:
                p.setOpacity(0.35)
            else:
                p.setOpacity(0.85)
            self._stroke_arc(
                p, cx, cy, r_ingress, arc.start_angle, arc.end_angle, pen_in)

            if not _chord_label_visible(arc.index, label_step, extra_lbl):
                continue
            mid = (arc.start_angle + arc.end_angle) / 2
            lp = self._point_at(
                cx, cy, mid, r_egress + _CHORD_ARC_OUTER / 2 + self._label_gap)
            use_bold = focused if self._compact else is_hover
            p.setFont(bold_font if use_bold else normal_font)
            p.setOpacity(1.0)
            p.setPen(label_color)
            fm = QFontMetricsF(p.font())
            text = _core_short_name(arc.core)
            text_w = fm.horizontalAdvance(text)
            cos_mid = math.cos(mid)
            if cos_mid > 0.15:
                tx = lp.x()
            elif cos_mid < -0.15:
                tx = lp.x() - text_w
            else:
                tx = lp.x() - text_w / 2
            ty = lp.y() + (fm.ascent() - fm.descent()) / 2
            p.drawText(QPointF(tx, ty), text)
        p.setOpacity(1.0)

    def _tapered_ribbon_path(self, cx, cy, r_inner, a0, a1,
                            src_half, dst_half, bidir_offset) -> QPainterPath:
        p1 = self._point_at(cx, cy, a0, r_inner)
        p2 = self._point_at(cx, cy, a1, r_inner)
        mx = (p1.x() + p2.x()) / 2
        my = (p1.y() + p2.y()) / 2
        vx, vy = mx - cx, my - cy
        vlen = math.hypot(vx, vy) or 1.0
        vx, vy = vx / vlen, vy / vlen
        perp_x, perp_y = -vy, vx
        pull = 0.18
        ctrl = QPointF(cx + vx * r_inner * pull + perp_x * bidir_offset,
                       cy + vy * r_inner * pull + perp_y * bidir_offset)
        t0x, t0y = ctrl.x() - p1.x(), ctrl.y() - p1.y()
        t0len = math.hypot(t0x, t0y) or 1.0
        n0x, n0y = -t0y / t0len, t0x / t0len
        t1x, t1y = p2.x() - ctrl.x(), p2.y() - ctrl.y()
        t1len = math.hypot(t1x, t1y) or 1.0
        n1x, n1y = -t1y / t1len, t1x / t1len
        mid_n_x = (n0x + n1x) / 2
        mid_n_y = (n0y + n1y) / 2
        mid_half = (src_half + dst_half) / 2
        sL = QPointF(p1.x() + n0x * src_half, p1.y() + n0y * src_half)
        sR = QPointF(p1.x() - n0x * src_half, p1.y() - n0y * src_half)
        dL = QPointF(p2.x() + n1x * dst_half, p2.y() + n1y * dst_half)
        dR = QPointF(p2.x() - n1x * dst_half, p2.y() - n1y * dst_half)
        cL = QPointF(ctrl.x() + mid_n_x * mid_half, ctrl.y() + mid_n_y * mid_half)
        cR = QPointF(ctrl.x() - mid_n_x * mid_half, ctrl.y() - mid_n_y * mid_half)
        path = QPainterPath()
        path.moveTo(sL)
        path.quadTo(cL, dL)
        path.lineTo(dR)
        path.quadTo(cR, sR)
        path.closeSubpath()
        return path

    def set_focus_pair(self, from_core: Optional[str], to_core: Optional[str]) -> None:
        if from_core and to_core and from_core in self._cores and to_core in self._cores:
            self._focus_pair = (self._cores.index(from_core), self._cores.index(to_core))
        else:
            self._focus_pair = None
        self.update()

    def _arc_focused(self, index: int) -> bool:
        if self._focus_pair is not None and index in self._focus_pair:
            return True
        return index in (self._focus_cores or [])

    def _is_dim_pair(self, i: int, j: int) -> bool:
        focus_pair = self._focus_pair
        if focus_pair is not None:
            fi, tj = focus_pair
            return not (i == fi and j == tj)
        fc = self._focus_cores or []
        if len(fc) == 1:
            return i != fc[0] and j != fc[0]
        if len(fc) == 2:
            a, b = fc[0], fc[1]
            return not ((i == a and j == b) or (i == b and j == a))
        hovered = self._hover_index
        hover_side = self._hover_side
        if hover_side == "egress":
            return hovered is not None and i != hovered
        if hover_side == "ingress":
            return hovered is not None and j != hovered
        return hovered is not None and hovered != i and hovered != j

    def grab_full_pixmap(self) -> QPixmap:
        """Snapshot the current diagram as-rendered (fixed-size, unlike the
        heatmap's scrollable full-content export — the chord diagram always
        fits its viewport)."""
        return self.grab()

    def render_full_svg(self, path: str, title: str) -> None:
        """Hand-build the SVG markup (mirrors the web app's exportChordSvg)
        instead of replaying _paint() onto a QSvgGenerator: Qt's SVG backend
        does not preserve QLinearGradient-brushed QPen strokes (they
        serialize as solid black), so the gradient chords must be emitted as
        real <linearGradient> defs referenced by each chord's <path>."""
        def esc(v) -> str:
            return (str(v).replace("&", "&amp;").replace("<", "&lt;")
                    .replace(">", "&gt;").replace('"', "&quot;"))

        cores = self._cores
        layout = self._layout
        w, h = self.width(), self.height()
        if not cores or layout is None or not layout.arcs:
            return
        cx, cy, R = self._geometry(w, h)
        r_egress, r_ingress, r_ribbon = _chord_ring_geometry(R)
        max_count = self._max_count or 1
        grid = self._grid
        bg = self.palette().color(QPalette.Window).name()

        defs = []
        chord_paths = []
        for i in range(len(cores)):
            row = grid[i] if i < len(grid) else []
            for j in range(len(cores)):
                if i == j:
                    continue
                count = row[j] if j < len(row) else 0
                if not count:
                    continue
                bidir = (grid[j][i] if j < len(grid) and i < len(grid[j]) else 0) > 0
                p1 = self._point_at(cx, cy, layout.egress_tick_angle(i, j), r_ribbon)
                p2 = self._point_at(cx, cy, layout.ingress_tick_angle(j, i), r_ribbon)
                mx, my = (p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2
                vx, vy = mx - cx, my - cy
                vlen = math.hypot(vx, vy) or 1.0
                vx, vy = vx / vlen, vy / vlen
                perp_x, perp_y = -vy, vx
                sign = 1 if i < j else -1
                bidir_offset = self._bidir_sep * sign if bidir else 0.0
                pull = 0.18
                ctrl_x = cx + vx * r_ribbon * pull + perp_x * bidir_offset
                ctrl_y = cy + vy * r_ribbon * pull + perp_y * bidir_offset
                width = max(1.0, min(12.0, 1 + 10 * (count / max_count)))
                gid = f"chord-grad-{i}-{j}"
                defs.append(
                    f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" '
                    f'x1="{p1.x():.2f}" y1="{p1.y():.2f}" x2="{p2.x():.2f}" y2="{p2.y():.2f}">'
                    f'<stop offset="0" stop-color="{esc(_core_color(cores[i]))}"/>'
                    f'<stop offset="1" stop-color="{esc(_core_color(cores[j]))}"/>'
                    '</linearGradient>')
                chord_paths.append(
                    f'<path d="M {p1.x():.2f} {p1.y():.2f} Q {ctrl_x:.2f} {ctrl_y:.2f} '
                    f'{p2.x():.2f} {p2.y():.2f}" stroke="url(#{gid})" '
                    f'stroke-width="{width:.2f}" stroke-opacity="{self._ribbon_alpha:.2f}" '
                    'fill="none" stroke-linecap="butt"/>')

        arc_parts = []
        svg_step = _chord_label_step(
            len(cores), min_px=16.0, span_px=2.0 * math.pi * max(R, 1.0))
        for arc in layout.arcs:
            large_arc = 1 if (arc.end_angle - arc.start_angle) > math.pi else 0
            for rr, sw, opac in (
                    (r_egress, _CHORD_ARC_OUTER, 1.0),
                    (r_ingress, _CHORD_ARC_INNER, 0.85)):
                p1 = self._point_at(cx, cy, arc.start_angle, rr)
                p2 = self._point_at(cx, cy, arc.end_angle, rr)
                arc_parts.append(
                    f'<path d="M {p1.x():.2f} {p1.y():.2f} A {rr:.2f} {rr:.2f} 0 '
                    f'{large_arc} 1 {p2.x():.2f} {p2.y():.2f}" '
                    f'stroke="{esc(_core_color(arc.core))}" stroke-width="{sw}" '
                    f'stroke-opacity="{opac}" fill="none" stroke-linecap="butt"/>')
            if not _chord_label_visible(arc.index, svg_step):
                continue
            mid = (arc.start_angle + arc.end_angle) / 2
            lp = self._point_at(
                cx, cy, mid, r_egress + _CHORD_ARC_OUTER / 2 + self._label_gap)
            cos_mid = math.cos(mid)
            anchor = "start" if cos_mid > 0.15 else "end" if cos_mid < -0.15 else "middle"
            fsz = 10 if self._compact else 11
            arc_parts.append(
                f'<text x="{lp.x():.2f}" y="{lp.y():.2f}" fill="#888888" '
                f'font-family="{_get_fixed_font_family()}" font-size="{fsz}" '
                f'text-anchor="{anchor}" '
                f'dominant-baseline="middle">{esc(_core_short_name(arc.core))}</text>')

        parts = [
            '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}">',
            f'<title>{esc(title)}</title>',
            f'<rect width="100%" height="100%" fill="{bg}"/>',
            '<defs>', *defs, '</defs>',
            *chord_paths,
            *arc_parts,
            '</svg>',
        ]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(parts))

class _CorridorTimelineCanvas(QWidget):
    """Viewport-sized heatmap canvas (web .ci-grid-canvas); scroll via host bar."""

    corridor_clicked = Signal(object, int)  # corridor dict, bin index
    corridor_dbl = Signal(object, int)

    _ROW_H = 22
    _LABEL_W = 78
    _HEAD_H = 40
    _FOOT_H = 16

    def __init__(self, host: "QScrollArea", parent=None):
        super().__init__(parent)
        self._host = host
        self._corridors: list = []
        self._time_bins = 32
        self._max_bin = 1
        self._t_min = 0
        self._t_max = 1
        self._bin_w = 1.0
        self._time_scale = "ns"
        self._selected = None
        self._highlight_bin = -1
        self._hover_ri = -1
        self._hover_bi = -1
        self.setMouseTracking(True)
        self.setAutoFillBackground(True)
        self._tip = QLabel(self)
        self._tip.setObjectName("corridorGridTip")
        self._tip.setWordWrap(True)
        self._tip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._tip.setStyleSheet(
            "QLabel#corridorGridTip {"
            "background: palette(window); color: palette(window-text);"
            "border: 1px solid palette(mid); border-radius: 4px;"
            f"padding: 6px 8px; font-family: \"{_get_fixed_font_family()}\"; font-size: 11px;"
            "}"
        )
        self._tip.hide()

    def _content_h(self) -> int:
        n = len(self._corridors)
        return self._HEAD_H + n * self._ROW_H + self._FOOT_H

    def _scroll_y(self) -> int:
        return int(self._host.verticalScrollBar().value())

    def set_model(self, corridors, time_bins, max_bin, t_min, t_max, bin_w, time_scale):
        self._corridors = list(corridors or [])
        self._time_bins = time_bins
        self._max_bin = max(1, max_bin)
        self._t_min, self._t_max, self._bin_w = t_min, t_max, bin_w
        self._time_scale = time_scale
        self.update()

    def set_selection(self, corridor, highlight_bin=-1):
        self._selected = corridor
        self._highlight_bin = highlight_bin
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        try:
            self._paint_corridor_grid(p)
        finally:
            p.end()

    def _paint_corridor_grid(self, p):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setClipRect(self.rect())
        w = self.width()
        row_h, head_h, label_w, foot_h = (
            self._ROW_H, self._HEAD_H, self._LABEL_W, self._FOOT_H)
        corridors = self._corridors
        bins = max(self._time_bins, 1)
        plot_w = max(1.0, w - label_w)
        cell_w = plot_w / bins
        sy = self._scroll_y()
        vp_h = max(1, self.height())
        bg = self.palette().color(QPalette.ColorRole.Window)
        fg = QColor("#888888")
        p.fillRect(self.rect(), bg)
        plot_top = head_h
        plot_bot = max(plot_top, vp_h - foot_h)
        p.save()
        p.setClipRect(QRectF(0, plot_top, w, plot_bot - plot_top))
        first = max(0, (sy - head_h) // row_h)
        last = min(len(corridors) - 1, (sy + vp_h - head_h) // row_h + 1)
        for ri in range(first, last + 1):
            c = corridors[ri]
            y = head_h + ri * row_h - sy
            if y + row_h < plot_top or y > plot_bot:
                continue
            sel = self._selected
            selected = bool(
                sel
                and sel.get("from_core") == c["from_core"]
                and sel.get("to_core") == c["to_core"])
            if selected:
                p.fillRect(0, y, w, row_h, QColor(100, 160, 255, 30))
            p.setPen(fg)
            font = _monospace_font(8, QFont.Bold if selected else QFont.Normal)
            p.setFont(font)
            p.drawText(QRectF(2, y, label_w - 6, row_h),
                       int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                       c.get("label", ""))
            for b in range(bins):
                v = c["bins"][b] if b < len(c["bins"]) else 0
                bv = c["bounce_bins"][b] if b < len(c["bounce_bins"]) else 0
                x = label_w + b * cell_w
                if v > 0:
                    intensity = min(1.0, v / self._max_bin)
                    p.fillRect(QRectF(x + 0.5, y + 2, cell_w - 1, row_h - 4),
                               QColor(70, 130, 220, int(40 + 190 * intensity)))
                else:
                    p.fillRect(QRectF(x + 0.5, y + 2, cell_w - 1, row_h - 4),
                               QColor(127, 127, 127, 16))
                if bv > 0 and v > 0 and bv / v >= 0.15:
                    p.setPen(QPen(QColor(232, 120, 32, 160), 1))
                    for s in range(int(-row_h), int(cell_w + row_h), 4):
                        p.drawLine(QPointF(x + s, y + row_h),
                                   QPointF(x + s + row_h, y))
                if selected and self._highlight_bin == b:
                    p.setPen(QPen(QColor(255, 220, 80, 220), 1))
                    p.drawRect(QRectF(x + 0.5, y + 1, cell_w - 1, row_h - 2))
                elif self._hover_ri == ri and self._hover_bi == b:
                    p.setPen(QPen(QColor(180, 200, 255, 180), 1))
                    p.drawRect(QRectF(x + 0.5, y + 1, cell_w - 1, row_h - 2))
        p.restore()
        # Sticky time axis (parity with web .ci-grid-canvas).
        p.fillRect(QRectF(0, 0, w, head_h), bg)
        p.setPen(fg)
        p.setFont(_monospace_font(8))
        p.drawText(4, 12,
                   "Y: corridor (src→dst)   X: time   color: mig count   hatch: lock bounce")
        p.drawText(4, 26, "src→dst")
        tick_n = min(bins, 6)
        fm = QFontMetrics(p.font())
        for t in range(tick_n + 1):
            frac = t / tick_n
            ns = int(self._t_min + frac * (self._t_max - self._t_min))
            x = label_w + frac * plot_w
            label = _format_time(ns, self._time_scale)
            ty = 26
            if frac < 0.05:
                p.drawText(int(x), ty, label)
            elif frac > 0.95:
                p.drawText(int(x) - fm.horizontalAdvance(label), ty, label)
            else:
                p.drawText(int(x) - fm.horizontalAdvance(label) // 2, ty, label)
        foot_y = vp_h - foot_h
        p.fillRect(QRectF(0, foot_y, w, foot_h), bg)
        p.setPen(fg)
        p.drawText(QRectF(label_w, foot_y, plot_w, foot_h),
                   int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
                   "Time →")

    def _hit(self, pos):
        x, y = pos.x(), pos.y()
        if y < self._HEAD_H or y > self.height() - self._FOOT_H:
            return None
        ri = int((y + self._scroll_y() - self._HEAD_H) / self._ROW_H)
        plot_w = max(1.0, self.width() - self._LABEL_W)
        cell_w = plot_w / max(self._time_bins, 1)
        bi = int((x - self._LABEL_W) / cell_w)
        if ri < 0 or ri >= len(self._corridors) or bi < 0 or bi >= self._time_bins:
            return None
        return self._corridors[ri], ri, bi

    def _bin_tip(self, c, bi) -> str:
        bin_lo, bin_hi = _heatmap_bin_range(
            self._t_min, self._bin_w, self._time_bins, self._t_max, bi)
        n = c["bins"][bi] if bi < len(c["bins"]) else 0
        bv = c["bounce_bins"][bi] if bi < len(c["bounce_bins"]) else 0
        lines = [
            c.get("label", ""),
            f"{_format_time(bin_lo, self._time_scale)} – "
            f"{_format_time(bin_hi, self._time_scale)}",
            f"{n} migration{'s' if n != 1 else ''}",
        ]
        if bv:
            lines.append(f"{bv} lock bounce{'s' if bv != 1 else ''}")
        tasks = c.get("tasks") or []
        if n and tasks:
            lines.append(f"top task: {tasks[0].get('label', '')}")
        lines.append("click to select bin · double-click to spotlight")
        return "\n".join(lines)

    def _hide_tip(self) -> None:
        self._tip.hide()

    def _show_tip_at(self, local_pos, text: str) -> None:
        self._tip.setText(text)
        self._tip.adjustSize()
        pad = 12
        x = int(local_pos.x()) + pad
        y = int(local_pos.y()) + pad
        tw, th = self._tip.sizeHint().width(), self._tip.sizeHint().height()
        x = max(4, min(x, max(4, self.width() - tw - 4)))
        y = max(4, min(y, max(4, self.height() - th - 4)))
        self._tip.move(x, y)
        self._tip.resize(tw, th)
        self._tip.show()
        self._tip.raise_()

    def mouseMoveEvent(self, event):
        pos = event.position() if hasattr(event, "position") else event.pos()
        hit = self._hit(pos)
        if hit is None:
            if self._hover_ri != -1:
                self._hover_ri = self._hover_bi = -1
                self.update()
            self._hide_tip()
            return super().mouseMoveEvent(event)
        c, ri, bi = hit
        if ri != self._hover_ri or bi != self._hover_bi:
            self._hover_ri, self._hover_bi = ri, bi
            self.update()
        self._show_tip_at(pos, self._bin_tip(c, bi))
        return super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_ri = self._hover_bi = -1
        self._hide_tip()
        self.update()
        return super().leaveEvent(event)

    def mousePressEvent(self, event):
        hit = self._hit(event.position() if hasattr(event, "position") else event.pos())
        if hit:
            self.corridor_clicked.emit(hit[0], hit[2])
        return super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        hit = self._hit(event.position() if hasattr(event, "position") else event.pos())
        if hit and hit[0]["bins"][hit[2]] > 0:
            self.corridor_dbl.emit(hit[0], hit[2])
        return super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        bar = self._host.verticalScrollBar()
        bar.setValue(bar.value() - int(event.angleDelta().y()))
        event.accept()


class _CorridorTimelineGrid(QScrollArea):
    """Scrollable corridor heatmap (web .ci-grid-body overflow:auto)."""

    corridor_clicked = Signal(object, int)
    corridor_dbl = Signal(object, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.horizontalScrollBar().hide()
        self.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setMinimumHeight(120)
        self.setMinimumWidth(280)
        self._spacer = QWidget()
        self._spacer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setWidget(self._spacer)
        self._canvas = _CorridorTimelineCanvas(self, self.viewport())
        self._canvas.corridor_clicked.connect(self.corridor_clicked.emit)
        self._canvas.corridor_dbl.connect(self.corridor_dbl.emit)
        self.verticalScrollBar().valueChanged.connect(
            lambda _v: self._canvas.update())
        self.viewport().setMouseTracking(True)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(480, 240)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(200, 80)

    def _sync_overlay(self) -> None:
        # Spacer is 1px wide (web .ci-grid-spacer) so only vertical scroll
        # appears; canvas then uses the viewport *after* the bar is shown.
        content_h = max(1, self._canvas._content_h())
        self._spacer.setFixedSize(1, content_h)
        vp = self.viewport()
        vw, vh = max(1, vp.width()), max(1, vp.height())
        self._canvas.setGeometry(0, 0, vw, vh)
        self._canvas.raise_()
        self._canvas.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_overlay()

    def set_model(self, corridors, time_bins, max_bin, t_min, t_max, bin_w,
                  time_scale) -> None:
        self._canvas.set_model(
            corridors, time_bins, max_bin, t_min, t_max, bin_w, time_scale)
        self._sync_overlay()

    def set_selection(self, corridor, highlight_bin=-1) -> None:
        self._canvas.set_selection(corridor, highlight_bin)
        self._ensure_corridor_visible(corridor)

    def _ensure_corridor_visible(self, corridor) -> None:
        if not corridor:
            return
        head = self._canvas._HEAD_H
        row_h = self._canvas._ROW_H
        foot = self._canvas._FOOT_H
        idx = None
        for ri, c in enumerate(self._canvas._corridors):
            if (c.get("from_core") == corridor.get("from_core")
                    and c.get("to_core") == corridor.get("to_core")):
                idx = ri
                break
        if idx is None:
            return
        y = head + idx * row_h
        vp = max(1, self.viewport().height())
        bar = self.verticalScrollBar()
        top = bar.value()
        vis_top = top + head
        vis_bot = top + vp - foot
        if y < vis_top:
            bar.setValue(max(0, y - head))
        elif y + row_h > vis_bot:
            bar.setValue(max(0, y + row_h - (vp - foot)))


# Web .ci-field select / .ci-task-filter: 12px + padding 2px 6px.
_CI_FIELD_H = 22
# Web .ci-sidebar-body height 220px + chrome.
_CI_SIDEBAR_H = 248


def _dim_css_color(widget: QWidget) -> str:
    """Muted text color blended from the current palette (theme-aware)."""
    fg = widget.palette().color(QPalette.ColorRole.WindowText)
    bg = widget.palette().color(QPalette.ColorRole.Window)
    r = int(bg.red() * 0.55 + fg.red() * 0.45)
    g = int(bg.green() * 0.55 + fg.green() * 0.45)
    b = int(bg.blue() * 0.55 + fg.blue() * 0.45)
    return f"#{r:02x}{g:02x}{b:02x}"


class _CorridorInspectorDialog(QDialog):
    """Unified Migration & Corridor Inspector (TODO2) — tree + timeline + mini-chord."""

    def __init__(self, trace: "BtfTrace", parent=None,
                 on_spotlight: Optional[Callable] = None,
                 on_clear: Optional[Callable] = None,
                 on_jump: Optional[Callable] = None,
                 initial_mode: str = "heatmap",
                 ai_enabled: bool = True,
                 on_query_ai: Optional[Callable] = None):
        super().__init__(parent)
        self.setWindowTitle("Migration & Corridor Inspector")
        self.setMinimumSize(720, 520)
        self.resize(980, 680)
        self.setModal(False)
        self._trace = trace
        self._on_spotlight = on_spotlight
        self._on_clear = on_clear
        self._on_jump = on_jump
        self._ai_enabled = ai_enabled
        self._on_query_ai = on_query_ai
        self._bounce_only = False
        self._top_pct = _default_corridor_top_pct(len(trace.core_names))
        self._scope_lo = self._scope_hi = None
        self._scope_suffix = ""
        self._owner_tab_path: Optional[str] = None
        self._model: dict = {}
        self._selected = None
        self._selected_task = None
        self._display_corridors: list = []
        self._display_groups: list = []
        self._direction_mode = "all"
        self._task_query = ""
        self._locked_cores: list = []
        self._expanded_groups: set = set()
        self._expanded_corridors: set = set()
        self._sidebar_dock = "bottom"
        self._initial_mode = initial_mode
        self._scope_follow = True
        self._HINT_DEFAULT = (
            "Click a time cell to select that bin · double-click for Spotlight · "
            "outer ring = egress · inner ring = ingress")

        lay = QVBoxLayout(self)

        # One control height for combos + task filter (app QSS makes QComboBox
        # 1.6em and QLineEdit auto — they look mismatched in this toolbar).
        # Keep this row fixed so an empty-state / long subtitle cannot push it down.
        bar = QWidget()
        bar.setObjectName("ciToolbar")
        bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        bar.setStyleSheet(
            "#ciToolbar QComboBox, #ciToolbar QLineEdit, #ciToolbar QPushButton {"
            f"  height: {_CI_FIELD_H}px; min-height: {_CI_FIELD_H}px;"
            f"  max-height: {_CI_FIELD_H}px;"
            "  padding: 0px 6px; border-radius: 4px; font-size: 12px;"
            "}"
            "#ciToolbar QComboBox { padding-right: 20px; }"
            "#ciToolbar QComboBox::drop-down {"
            "  subcontrol-origin: padding; subcontrol-position: center right;"
            "  width: 16px; border: none;"
            "}"
            "#ciToolbar QComboBox QAbstractItemView {"
            "  outline: none; padding: 2px; font-size: 12px;"
            "}"
            "#ciToolbar QComboBox QAbstractItemView::item {"
            f"  min-height: {_CI_FIELD_H}px; padding: 2px 6px;"
            "}"
        )
        toolbar = QHBoxLayout(bar)
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(8)
        toolbar.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        top_lbl = QLabel("Top corridors")
        toolbar.addWidget(top_lbl)
        self._top_combo = QComboBox()
        for pct, label in ((10, "Top 10%"), (25, "Top 25%"), (50, "Top 50%"), (100, "All")):
            self._top_combo.addItem(label, pct)
        idx = self._top_combo.findData(self._top_pct)
        if idx >= 0:
            self._top_combo.setCurrentIndex(idx)
        self._top_combo.currentIndexChanged.connect(self._on_top_changed)
        toolbar.addWidget(self._top_combo)
        self._bounce_btn = QPushButton("All Migrations")
        self._bounce_btn.setCheckable(True)
        self._bounce_btn.clicked.connect(self._on_bounce_toggled)
        self._bounce_btn.setVisible(_trace_has_core_bounce_holds(trace))
        toolbar.addWidget(self._bounce_btn)
        dir_lbl = QLabel("Direction")
        toolbar.addWidget(dir_lbl)
        self._dir_combo = QComboBox()
        self._dir_combo.addItem("All", "all")
        self._dir_combo.addItem("Egress Only", "egress")
        self._dir_combo.addItem("Ingress Only", "ingress")
        self._dir_combo.currentIndexChanged.connect(self._on_dir_changed)
        toolbar.addWidget(self._dir_combo)
        task_lbl = QLabel("Task filter")
        toolbar.addWidget(task_lbl)
        self._task_edit = QLineEdit()
        self._task_edit.setPlaceholderText("name or exact id")
        self._task_edit.setClearButtonEnabled(True)
        self._task_edit.setFixedWidth(140)
        self._task_edit.textChanged.connect(self._on_task_filter_changed)
        toolbar.addWidget(self._task_edit)
        toolbar.addStretch(1)
        for _w in (self._top_combo, self._dir_combo, self._task_edit, self._bounce_btn):
            self._style_inspector_field(_w)
        lay.addWidget(bar)
        self._sub = QLabel()
        self._sub.setObjectName("ciSub")
        self._sub.setWordWrap(False)
        self._sub.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._sub.setStyleSheet(f"color:{_dim_css_color(self)}; font-size:11px;")
        lay.addWidget(self._sub)
        self._scope_note = QLabel(
            "Note: this map follows the current timeline viewport, not the full "
            "trace. Press Fit (F / Ctrl+0) to show the full range.")
        self._scope_note.setObjectName("ciScopeNote")
        self._scope_note.setWordWrap(True)
        self._scope_note.setStyleSheet(
            f"color:{_dim_css_color(self)}; font-size:11px;")
        lay.addWidget(self._scope_note)

        self._triage = QLabel()
        self._triage.setStyleSheet(
            "background:rgba(232,160,32,0.10);border:1px solid rgba(232,160,32,0.35);"
            "border-radius:4px;padding:6px;")
        self._triage_btn = QPushButton("Jump To")
        self._triage_btn.clicked.connect(self._jump_hotspot)
        triage_row = QHBoxLayout()
        triage_row.addWidget(self._triage, 1)
        triage_row.addWidget(self._triage_btn)
        self._triage_wrap = QWidget()
        self._triage_wrap.setLayout(triage_row)
        self._triage_wrap.setVisible(False)
        lay.addWidget(self._triage_wrap)

        split = QSplitter(Qt.Orientation.Horizontal)
        self._split = split
        self._tree = QTreeWidget()
        self._tree.setObjectName("corridorInspectorTree")
        self._tree.setHeaderLabels(["Corridor / Task", "Vol", "Bounce", "Net"])
        self._tree.setIndentation(12)
        self._tree.setUniformRowHeights(True)
        self._tree.setAllColumnsShowFocus(True)
        self._tree.setMouseTracking(True)
        self._tree.viewport().setMouseTracking(True)
        self._tree.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._tree.setStyleSheet(
            "#corridorInspectorTree { show-decoration-selected: 1; outline: none; }"
            "#corridorInspectorTree::item { border: none; padding: 2px 0; }"
            "#corridorInspectorTree::item:hover {"
            "  background: rgba(127, 127, 127, 0.18);"
            "}"
            "#corridorInspectorTree::item:selected {"
            "  background: rgba(100, 160, 255, 0.28);"
            "  color: palette(text);"
            "}"
            "#corridorInspectorTree::item:selected:hover {"
            "  background: rgba(100, 160, 255, 0.36);"
            "}"
        )
        self._tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        hdr = self._tree.header()
        hdr.setStretchLastSection(False)
        hdr.setMinimumSectionSize(40)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._tree.setColumnWidth(0, 168)
        self._tree.setColumnWidth(1, 52)
        self._tree.setColumnWidth(2, 60)
        self._tree.setColumnWidth(3, 56)
        self._tree.setMinimumWidth(280)
        self._tree.itemClicked.connect(self._on_tree_click)
        self._tree.itemDoubleClicked.connect(self._on_tree_dbl)
        self._tree.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._tree.setMinimumHeight(80)
        split.addWidget(self._tree)
        self._grid = _CorridorTimelineGrid()
        self._grid.setMinimumWidth(280)
        self._grid.corridor_clicked.connect(self._on_grid_clicked)
        self._grid.corridor_dbl.connect(self._spotlight_corridor_bin)
        split.addWidget(self._grid)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([340, 640])

        self._chord = _ChordDiagramWidget(compact=True)
        self._chord.setMinimumHeight(180)
        self._chord.setMinimumWidth(200)
        self._chord.core_clicked.connect(self._on_chord_core)
        self._chord.pair_clicked.connect(self._on_chord_pair)
        self._chord.corridor_clicked.connect(self._on_chord_corridor)
        self._chord.corridor_dbl.connect(self._on_chord_corridor_dbl)
        self._chord.hover_info.connect(self._on_chord_hover_info)

        self._card_title = QLabel()
        self._card_title.setStyleSheet("font-weight:600;")
        self._card_title.setWordWrap(True)
        self._card = QLabel("Click a corridor or chord ribbon to inspect.")
        self._card.setWordWrap(True)
        self._card.setStyleSheet(f"color:{_dim_css_color(self)};")
        self._inspect_btn = QPushButton("Inspect in Timeline")
        self._inspect_btn.setVisible(False)
        self._inspect_btn.clicked.connect(self._on_inspect_in_timeline)
        card_lay = QVBoxLayout()
        card_lay.setContentsMargins(10, 4, 4, 4)
        card_lay.addWidget(self._card_title)
        card_lay.addWidget(self._card, 1)
        card_lay.addWidget(self._inspect_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self._card_panel = QWidget()
        self._card_panel.setLayout(card_lay)
        self._card_panel.setMinimumWidth(180)

        self._side_body = QSplitter(Qt.Orientation.Horizontal)
        self._side_body.addWidget(self._chord)
        self._side_body.addWidget(self._card_panel)
        # Web .ci-sidebar-body: 1fr : 0.7fr, height 220px.
        self._side_body.setStretchFactor(0, 10)
        self._side_body.setStretchFactor(1, 7)
        self._side_body.setSizes([320, 224])
        self._side_body.setChildrenCollapsible(False)

        self._side_toggle = QPushButton(
            "Hide topology" if initial_mode == "chord" else "Show topology")
        self._side_toggle.setFlat(True)
        self._side_toggle.clicked.connect(self._toggle_side)
        self._dock_combo = QComboBox()
        self._dock_combo.addItem("Bottom", "bottom")
        self._dock_combo.addItem("Right", "right")
        self._dock_combo.currentIndexChanged.connect(self._on_dock_changed)
        self._style_inspector_field(self._dock_combo)
        self._dock_combo.setStyleSheet(
            f"QComboBox {{ min-height: {_CI_FIELD_H}px; max-height: {_CI_FIELD_H}px;"
            "  padding: 2px 20px 2px 6px; border-radius: 4px; font-size: 12px; }"
            "QComboBox::drop-down {"
            "  subcontrol-origin: padding; subcontrol-position: center right;"
            "  width: 16px; border: none; }"
            "QComboBox QAbstractItemView { outline: none; padding: 2px; font-size: 12px; }"
            "QComboBox QAbstractItemView::item {"
            f"  min-height: {_CI_FIELD_H}px; padding: 2px 6px; }}")
        chrome = QHBoxLayout()
        chrome.setContentsMargins(4, 2, 4, 2)
        chrome.addWidget(self._side_toggle)
        chrome.addStretch(1)
        self._dock_lbl = QLabel("Dock")
        chrome.addWidget(self._dock_lbl)
        chrome.addWidget(self._dock_combo)

        side_lay = QVBoxLayout()
        side_lay.setContentsMargins(6, 4, 6, 6)
        side_lay.setSpacing(4)
        side_lay.addLayout(chrome)
        side_lay.addWidget(self._side_body, 1)
        self._side_wrap = QWidget()
        self._side_wrap.setObjectName("corridorInspectorSidebar")
        self._side_wrap.setStyleSheet(
            "#corridorInspectorSidebar {"
            "  border: 1px solid rgba(127,127,127,0.35);"
            "  border-radius: 4px;"
            "}"
        )
        self._side_wrap.setLayout(side_lay)

        self._empty = QLabel("No migrations in scope.")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setStyleSheet(f"color:{_dim_css_color(self)};")
        self._empty.hide()
        self._work = QWidget()
        work_stack = QGridLayout(self._work)
        work_stack.setContentsMargins(0, 0, 0, 0)
        work_stack.setSpacing(0)
        work_stack.addWidget(split, 0, 0)
        work_stack.addWidget(self._empty, 0, 0)
        self._empty.raise_()

        self._outer = QSplitter(Qt.Orientation.Vertical)
        self._outer.addWidget(self._work)
        self._outer.addWidget(self._side_wrap)
        self._outer.setStretchFactor(0, 1)
        self._outer.setStretchFactor(1, 0)
        self._outer.setSizes([440, _CI_SIDEBAR_H])
        lay.addWidget(self._outer, 1)

        self._hint = QLabel(self._HINT_DEFAULT)
        self._hint.setStyleSheet(f"color:{_dim_css_color(self)};")
        lay.addWidget(self._hint)

        self._show_topology(initial_mode == "chord", apply_layout=False)
        self._apply_sidebar_layout()

        self._filter_bar = QWidget()
        fb = QHBoxLayout(self._filter_bar)
        fb.setContentsMargins(0, 0, 0, 0)
        self._filter_lbl = QLabel()
        fb.addWidget(self._filter_lbl, 1)
        clear_btn = QPushButton("Show all tasks")
        clear_btn.clicked.connect(self._clear_filter)
        fb.addWidget(clear_btn)
        self._filter_bar.setVisible(False)
        lay.addWidget(self._filter_bar)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        self._ai_btn = btns.addButton(
            "Query with AI…", QDialogButtonBox.ButtonRole.ActionRole)
        self._ai_btn.clicked.connect(self._query_with_ai)
        self.set_ai_enabled(ai_enabled)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self.refresh_scope()
        QTimer.singleShot(0, self._fit_tree_pane)

    def set_ai_enabled(self, enabled: bool) -> None:
        self._ai_enabled = bool(enabled)
        if getattr(self, "_ai_btn", None) is None:
            return
        self._ai_btn.setToolTip(
            "Open the AI Assistant and walk through migration / corridor findings"
            if self._ai_enabled else
            "Enable AI Assistant in Settings → AI")

    def _query_with_ai(self) -> None:
        if self._on_query_ai is not None:
            self._on_query_ai(self._ai_enabled)

    @staticmethod
    def _style_inspector_field(widget) -> None:
        """Match combo / line-edit / button height and styled popup lists."""
        widget.setFixedHeight(_CI_FIELD_H)
        widget.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        if isinstance(widget, QComboBox):
            widget.setView(QListView(widget))
            widget.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToContents)
            hint_w = max(widget.minimumSizeHint().width(), 108)
            widget.setMinimumWidth(hint_w)
            view = widget.view()
            if view is not None:
                view.setMinimumWidth(hint_w)
                view.setUniformItemSizes(True)

    def _toggle_side(self) -> None:
        self._show_topology(not self._side_body.isVisible())

    def _show_topology(self, vis: bool, apply_layout: bool = True) -> None:
        self._side_wrap.setVisible(True)
        self._side_body.setVisible(bool(vis))
        self._dock_lbl.setVisible(bool(vis))
        self._dock_combo.setVisible(bool(vis))
        self._side_toggle.setText("Hide topology" if vis else "Show topology")
        if apply_layout:
            self._apply_sidebar_layout()

    def _on_dock_changed(self, _idx: int = 0) -> None:
        self._sidebar_dock = str(self._dock_combo.currentData() or "bottom")
        self._apply_sidebar_layout()

    def _apply_sidebar_layout(self) -> None:
        expanded = self._side_body.isVisible()
        dock = self._sidebar_dock
        self._side_wrap.setMaximumWidth(16777215)
        self._side_wrap.setMaximumHeight(16777215)
        if dock == "right":
            self._outer.setOrientation(Qt.Orientation.Horizontal)
            self._side_body.setOrientation(Qt.Orientation.Vertical)
            self._card_panel.setStyleSheet(
                "border-top: 1px solid rgba(127,127,127,0.35);")
            if expanded:
                self._side_wrap.setMinimumWidth(240)
                self._side_wrap.setMinimumHeight(0)
                self._outer.setSizes([680, 340])
                self._side_body.setSizes([220, 160])
            else:
                self._side_wrap.setMinimumWidth(120)
                self._side_wrap.setMaximumWidth(168)
                self._side_wrap.setMinimumHeight(0)
                self._outer.setSizes([800, 140])
        else:
            self._outer.setOrientation(Qt.Orientation.Vertical)
            self._side_body.setOrientation(Qt.Orientation.Horizontal)
            self._card_panel.setStyleSheet(
                "border-left: 1px solid rgba(127,127,127,0.35);")
            self._side_wrap.setMinimumWidth(0)
            if expanded:
                # Lock height so the heatmap splitter cannot overlap topology.
                self._side_wrap.setMinimumHeight(_CI_SIDEBAR_H)
                self._side_wrap.setMaximumHeight(_CI_SIDEBAR_H)
                main_h = max(120, self._outer.height() - _CI_SIDEBAR_H)
                self._outer.setSizes([main_h, _CI_SIDEBAR_H])
                self._side_body.setSizes([320, 224])
            else:
                self._side_wrap.setMinimumHeight(0)
                self._outer.setSizes([640, 36])
        self._side_body.setStretchFactor(0, 10)
        self._side_body.setStretchFactor(1, 7)
        self._outer.setStretchFactor(0, 1)
        self._outer.setStretchFactor(1, 0)

    def _on_top_changed(self, _idx: int = 0) -> None:
        self._top_pct = int(self._top_combo.currentData())
        self._rebuild()

    def _on_bounce_toggled(self, checked: bool) -> None:
        self._bounce_only = checked
        self._bounce_btn.setText(
            "Lock Bounces Only" if checked else "All Migrations")
        self._rebuild()

    def _on_dir_changed(self, _idx: int = 0) -> None:
        self._direction_mode = str(self._dir_combo.currentData() or "all")
        self._refresh_filtered_view()

    def _on_task_filter_changed(self, text: str) -> None:
        self._task_query = text or ""
        self._refresh_filtered_view()

    def _rebuild(self) -> None:
        self._model = _build_corridor_inspector_model(
            self._trace, self._scope_lo, self._scope_hi,
            bounce_only=self._bounce_only, top_pct=self._top_pct)
        hotspot = self._model.get("hotspot")
        if hotspot:
            self._triage.setText(hotspot["summary"])
            self._triage_wrap.setVisible(True)
        else:
            self._triage_wrap.setVisible(False)
        self._refresh_filtered_view()

    def _refresh_filtered_view(self) -> None:
        q = (self._task_query or "").strip()
        # Search all in-scope corridors when filtering by name/id so Top-N
        # cannot hide a matching task (web parity).
        src = (self._model.get("all_corridors") or self._model.get("corridors")
               or []) if q else (self._model.get("corridors") or [])
        vis = _filter_corridors_by_task_query(src, q)
        vis = _filter_corridors_by_direction(
            vis, self._direction_mode, self._selected)
        self._display_corridors = vis
        group_by = bool(self._model.get("group_by_source"))
        self._display_groups = (
            _corridor_groups_by_source(vis) if group_by else [])
        has = any(c.get("count", 0) > 0 for c in vis)
        if not has:
            self._empty.setText(
                "No corridors match this task filter." if q
                else "No migrations in scope.")
        self._empty.setVisible(not has)
        n = len(self._model.get("cores") or [])
        n_corr = len(vis)
        qnote = f" · filter “{self._task_query.strip()}”" if self._task_query.strip() else ""
        self._sub.setText(
            f"{n} cores · {n_corr} corridors · Top {self._top_pct}%"
            f"{qnote}{self._scope_suffix}")
        cores = self._model.get("cores") or []
        pair_count = {(c["from_core"], c["to_core"]): c["count"] for c in vis}
        filtered_grid = []
        for i, fc in enumerate(cores):
            row = []
            for j, tc in enumerate(cores):
                if i == j:
                    row.append(0)
                else:
                    row.append(pair_count.get((fc, tc), 0))
            filtered_grid.append(row)
        max_bin = 0
        for c in vis:
            for v in c.get("bins") or []:
                if v > max_bin:
                    max_bin = v
        self._populate_tree()
        self._chord.set_data(cores, filtered_grid)
        self._chord.set_direction_mode(self._direction_mode)
        focus: list = []
        sel = self._selected
        if sel and self._direction_mode == "egress" and sel.get("from_core") in cores:
            focus = [cores.index(sel["from_core"])]
        elif sel and self._direction_mode == "ingress" and sel.get("to_core") in cores:
            focus = [cores.index(sel["to_core"])]
        elif self._locked_cores:
            focus = [i for i in self._locked_cores if 0 <= i < len(cores)]
        self._chord.set_focus_cores(focus)
        if sel:
            self._chord.set_focus_pair(sel.get("from_core"), sel.get("to_core"))
        else:
            self._chord.set_focus_pair(None, None)
        self._grid.set_model(
            vis,
            self._model.get("time_bins", 32),
            max_bin or 1,
            self._model.get("t_min", 0),
            self._model.get("t_max", 1),
            self._model.get("bin_w", 1),
            self._trace.time_scale,
        )
        if sel:
            self._restore_tree_selection()

    def _fit_tree_pane(self) -> None:
        """Keep Corridor/Task readable without stealing the heatmap."""
        tree = self._tree
        if tree.topLevelItemCount():
            tree.resizeColumnToContents(0)
            name_w = min(200, max(140, tree.columnWidth(0)))
        else:
            name_w = 168
        tree.setColumnWidth(0, name_w)
        tree.setColumnWidth(1, 52)
        tree.setColumnWidth(2, 60)
        tree.setColumnWidth(3, 56)
        sb = tree.verticalScrollBar()
        sb_w = sb.sizeHint().width() if sb and sb.isVisible() else 16
        need = name_w + 52 + 60 + 56 + sb_w + tree.frameWidth() * 2 + 12
        need = max(300, min(need, 380))
        total = self._split.width()
        if total < 200:
            total = max(self.width() - 40, 900)
        self._split.setSizes([need, max(280, total - need)])
        self._grid._sync_overlay()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_sidebar_layout()
        self._fit_tree_pane()

    def _make_corridor_item(self, c: dict) -> QTreeWidgetItem:
        num_align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        net = c["net"]
        net_s = f"+{net} ▲" if net > 0 else (f"{net} ▼" if net < 0 else "0")
        item = QTreeWidgetItem([
            c["label"], str(c["count"]),
            f"{c['bounce_pct']:.0f}%", net_s,
        ])
        item.setData(0, Qt.ItemDataRole.UserRole, c)
        for col in (1, 2, 3):
            item.setTextAlignment(col, num_align)
        for t in c.get("tasks") or []:
            child = QTreeWidgetItem([
                f"└── {t['label']}", str(t["count"]),
                f"{t['bounce_pct']:.0f}%", f"{t['share_pct']:.0f}%",
            ])
            child.setData(0, Qt.ItemDataRole.UserRole, {"corridor": c, "task": t})
            for col in (1, 2, 3):
                child.setTextAlignment(col, num_align)
            item.addChild(child)
        return item

    def _remember_expanded_groups(self) -> None:
        expanded_groups = set()
        expanded_corridors = set()

        def walk(item) -> None:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if item.isExpanded():
                if isinstance(data, dict) and "group" in data:
                    expanded_groups.add(data["group"])
                if isinstance(data, dict) and "from_core" in data:
                    expanded_corridors.add(
                        (data.get("from_core"), data.get("to_core")))
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i))
        if expanded_groups or self._display_groups:
            self._expanded_groups = expanded_groups
        if expanded_corridors or self._expanded_corridors:
            self._expanded_corridors = expanded_corridors

    def _corridor_key(self, c: dict) -> tuple:
        return (c.get("from_core"), c.get("to_core"))

    def _populate_tree(self) -> None:
        self._remember_expanded_groups()
        self._tree.clear()
        num_align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        groups = self._display_groups
        if groups:
            for g in groups:
                gitem = QTreeWidgetItem([
                    g["label"], str(g["count"]), "—", "—",
                ])
                gitem.setData(0, Qt.ItemDataRole.UserRole, {"group": g["source"]})
                for col in (1, 2, 3):
                    gitem.setTextAlignment(col, num_align)
                for c in g.get("corridors") or []:
                    child = self._make_corridor_item(c)
                    gitem.addChild(child)
                    if self._corridor_key(c) in self._expanded_corridors:
                        child.setExpanded(True)
                self._tree.addTopLevelItem(gitem)
                if g["source"] in self._expanded_groups:
                    gitem.setExpanded(True)
        else:
            for c in self._display_corridors:
                item = self._make_corridor_item(c)
                self._tree.addTopLevelItem(item)
                if self._corridor_key(c) in self._expanded_corridors:
                    item.setExpanded(True)
        self._fit_tree_pane()

    def _restore_tree_selection(self) -> None:
        c = self._selected
        if not c:
            return
        if self._selected_task:
            self._reveal_task_in_tree(c, self._selected_task)
        else:
            self._reveal_corridor_in_tree(c)

    def _reveal_corridor_in_tree(self, c: dict) -> None:
        found = self._find_corridor_item(c)
        if found is None:
            return
        parent = found.parent()
        if parent:
            parent.setExpanded(True)
            pdata = parent.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(pdata, dict) and pdata.get("group"):
                self._expanded_groups.add(pdata["group"])
        self._tree.setCurrentItem(found)
        self._tree.scrollToItem(found)

    def _reveal_task_in_tree(self, c: dict, task: dict) -> None:
        corr_item = self._find_corridor_item(c)
        if corr_item is None:
            return
        parent = corr_item.parent()
        if parent:
            parent.setExpanded(True)
        corr_item.setExpanded(True)
        self._expanded_corridors.add(self._corridor_key(c))
        want_mk = task.get("mk")
        for i in range(corr_item.childCount()):
            child = corr_item.child(i)
            data = child.data(0, Qt.ItemDataRole.UserRole)
            t = data.get("task") if isinstance(data, dict) else None
            if isinstance(t, dict) and t.get("mk") == want_mk:
                self._tree.setCurrentItem(child)
                self._tree.scrollToItem(child)
                return
        self._tree.setCurrentItem(corr_item)
        self._tree.scrollToItem(corr_item)

    def _find_corridor_item(self, c: dict):
        want_from, want_to = c.get("from_core"), c.get("to_core")

        def walk(item):
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if (isinstance(data, dict) and data.get("from_core") == want_from
                    and data.get("to_core") == want_to):
                return item
            for i in range(item.childCount()):
                found = walk(item.child(i))
                if found:
                    return found
            return None

        for i in range(self._tree.topLevelItemCount()):
            found = walk(self._tree.topLevelItem(i))
            if found:
                return found
        return None

    def _on_grid_clicked(self, c: dict, bi: int) -> None:
        self._select_corridor(c, bi)

    def _set_card(self, title: str = "", lines: Optional[list] = None,
                  *, can_spotlight: bool = False) -> None:
        title = title or ""
        self._card_title.setText(title)
        self._card_title.setVisible(bool(title))
        if lines:
            self._card.setText("\n".join(str(x) for x in lines if x is not None))
        else:
            self._card.setText("Click a corridor or chord ribbon to inspect.")
        self._inspect_btn.setVisible(bool(can_spotlight))

    def _on_inspect_in_timeline(self) -> None:
        c = self._selected
        if not c:
            return
        bi = getattr(self._grid, "_highlight_bin", -1)
        if not (isinstance(bi, int) and bi >= 0):
            bi = c.get("peak_bin", -1)
        self._spotlight_corridor(c, bi if isinstance(bi, int) and bi >= 0 else None)

    def _show_core_card(self, core_index: int) -> None:
        stats = self._model.get("core_stats") or []
        if not (0 <= core_index < len(stats)):
            self._set_card()
            return
        st = stats[core_index]
        net = st.get("net", 0)
        net_s = f"+{net} net gain" if net > 0 else (
            f"{net} net loss" if net < 0 else "balanced")
        lines = [
            f"Outgoing {st.get('out', 0)} / Incoming {st.get('in', 0)}",
            f"Net: {net_s}",
        ]
        for t in (st.get("top_tasks") or [])[:3]:
            lines.append(f"{t.get('label')}: {t.get('count')}")
        self._set_card(_core_short_name(st.get("core") or ""), lines)

    def _select_corridor(self, c: dict, bin_index: Optional[int] = None,
                         *, reveal_tree: bool = True,
                         task: Optional[dict] = None) -> None:
        self._selected = c
        self._selected_task = task
        self._locked_cores = []
        if self._direction_mode != "all":
            self._refresh_filtered_view()
        bi = bin_index if bin_index is not None else c.get("peak_bin", -1)
        self._grid.set_selection(c, bi if bi is not None else -1)
        self._chord.set_focus_pair(c.get("from_core"), c.get("to_core"))
        self._chord.set_focus_cores([])
        offender = c.get("primary_task")
        lines = [
            f"Directed Vol: {c['count']:,} migrations ({c['rate_per_s']:.1f}/s)",
            f"Lock Bounces: {c['bounces']} ({c['bounce_pct']:.0f}% cache-line bounces)",
        ]
        if task:
            lines.append(
                f"Selected task: {task.get('label')} "
                f"({task.get('count', 0)} mig, "
                f"{task.get('share_pct', 0):.0f}% share)")
        elif offender:
            lines.append(
                f"Primary Offender: {offender['label']} "
                f"({offender['share_pct']:.0f}% share)")
        else:
            lines.append("No task attribution")
        if isinstance(bi, int) and bi >= 0:
            t_min = self._model.get("t_min", 0)
            t_max = self._model.get("t_max", 1)
            bin_w = self._model.get("bin_w", 1)
            time_bins = self._model.get("time_bins", 32)
            bin_lo, bin_hi = _heatmap_bin_range(
                t_min, bin_w, time_bins, t_max, bi)
            n = c["bins"][bi] if bi < len(c["bins"]) else 0
            bv = (c["bounce_bins"][bi]
                  if bi < len(c.get("bounce_bins") or []) else 0)
            extra = f"{n} mig"
            if bv:
                extra += f", {bv} bounce"
            lines.append(
                f"Selected bin {bi + 1}/{time_bins}: "
                f"{_format_time(bin_lo, self._trace.time_scale)}–"
                f"{_format_time(bin_hi, self._trace.time_scale)} · {extra}")
        self._set_card(f"Corridor: {c['label']}", lines, can_spotlight=True)
        if reveal_tree:
            self._restore_tree_selection()

    def _on_chord_core(self, payload) -> None:
        if not isinstance(payload, dict) or payload.get("clear"):
            self._locked_cores = []
            self._selected = None
            self._selected_task = None
            self._chord.set_focus_cores([])
            self._chord.set_focus_pair(None, None)
            self._grid.set_selection(None, -1)
            self._set_card()
            if self._direction_mode != "all":
                self._refresh_filtered_view()
            return
        idx = int(payload.get("core_index", -1))
        cores = self._model.get("cores") or []
        if not (0 <= idx < len(cores)):
            return
        self._locked_cores = [idx]
        self._selected = None
        self._selected_task = None
        self._chord.set_focus_pair(None, None)
        self._chord.set_focus_cores(self._locked_cores)
        self._grid.set_selection(None, -1)
        self._show_core_card(idx)
        if self._direction_mode != "all":
            self._refresh_filtered_view()

    def _on_chord_pair(self, core_index: int) -> None:
        cores = self._model.get("cores") or []
        if not (0 <= int(core_index) < len(cores)):
            return
        cur = list(self._locked_cores)
        if len(cur) == 1 and cur[0] != int(core_index):
            self._locked_cores = [cur[0], int(core_index)]
            a, b = cores[cur[0]], cores[int(core_index)]
            found = None
            for c in (self._model.get("all_corridors") or []):
                if c.get("from_core") == a and c.get("to_core") == b:
                    found = c
                    break
            if found is None:
                for c in (self._model.get("all_corridors") or []):
                    if c.get("from_core") == b and c.get("to_core") == a:
                        found = c
                        break
            self._show_topology(True)
            if found:
                self._select_corridor(found)
                return
            self._selected = None
            self._selected_task = None
            self._chord.set_focus_pair(None, None)
            self._chord.set_focus_cores(self._locked_cores)
            self._set_card(
                f"Pair isolate: {_core_short_name(a)} ↔ {_core_short_name(b)}",
                ["No directed corridor in scope."],
            )
            return
        self._on_chord_core({"core_index": int(core_index)})

    def _on_chord_corridor(self, from_core: str, to_core: str) -> None:
        found = None
        for c in (self._display_corridors or []) + (self._model.get("all_corridors") or []):
            if c.get("from_core") == from_core and c.get("to_core") == to_core:
                found = c
                break
        if found:
            if self._display_groups:
                self._expanded_groups.add(found["from_core"])
            self._show_topology(True)
            self._select_corridor(found)

    def _on_chord_corridor_dbl(self, from_core: str, to_core: str) -> None:
        for c in self._model.get("all_corridors") or []:
            if c.get("from_core") == from_core and c.get("to_core") == to_core:
                self._spotlight_corridor(c)
                return

    def _on_tree_click(self, item, _col) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, dict) and "group" in data:
            return
        if isinstance(data, dict) and "from_core" in data:
            self._expanded_corridors.add(self._corridor_key(data))
            self._select_corridor(data, reveal_tree=False)
        elif isinstance(data, dict) and "corridor" in data:
            self._expanded_corridors.add(
                self._corridor_key(data["corridor"]))
            self._select_corridor(
                data["corridor"], reveal_tree=False, task=data.get("task"))

    def _on_tree_dbl(self, item, _col) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, dict) and "task" in data:
            self._spotlight_task(data["corridor"], data["task"])
        elif isinstance(data, dict) and "from_core" in data:
            self._spotlight_corridor(data)

    def _jump_hotspot(self) -> None:
        h = self._model.get("hotspot")
        if not h:
            return
        found = None
        for c in self._model.get("all_corridors") or []:
            if c["from_core"] == h["from_core"] and c["to_core"] == h["to_core"]:
                found = c
                break
        if not found:
            return
        if self._display_groups:
            self._expanded_groups.add(found["from_core"])
        self._select_corridor(found, found.get("peak_bin"))
        if not self._on_jump:
            return
        t_min = self._model.get("t_min", 0)
        t_max = self._model.get("t_max", 1)
        bin_w = self._model.get("bin_w", 1)
        time_bins = self._model.get("time_bins", 32)
        bi = found.get("peak_bin", 0) or 0
        bin_lo, bin_hi = _heatmap_bin_range(t_min, bin_w, time_bins, t_max, bi)
        primary = (found.get("primary_task") or {}).get("mk")
        self._freeze_scope()
        self._on_jump(bin_lo, bin_hi, primary)

    def _spotlight_corridor_bin(self, c: dict, bi: int) -> None:
        self._spotlight_corridor(c, bi)

    def _spotlight_corridor(self, c: dict, bin_index: Optional[int] = None) -> None:
        if not self._on_spotlight:
            return
        self._freeze_scope()
        t_min = self._model["t_min"]
        t_max = self._model["t_max"]
        bin_w = self._model["bin_w"]
        time_bins = self._model["time_bins"]
        if bin_index is None:
            bin_index = c.get("peak_bin", 0)
        bin_lo, bin_hi = _heatmap_bin_range(t_min, bin_w, time_bins, t_max, bin_index)
        mks = {t["mk"] for t in c.get("tasks") or []}
        primary = (c.get("primary_task") or {}).get("mk")
        self._on_spotlight(c["from_core"], c["to_core"], c["label"],
                           bin_lo, bin_hi, mks, primary)

    def _spotlight_task(self, c: dict, t: dict) -> None:
        if not self._on_spotlight:
            return
        self._freeze_scope()
        self._on_spotlight(
            c["from_core"], c["to_core"], f"{c['label']} · {t['label']}",
            self._model["t_min"], self._model["t_max"], {t["mk"]}, t["mk"])

    def focus_pair(self, from_core: str, to_core: str,
                   bounce_only: bool = False) -> bool:
        if bool(self._bounce_only) != bool(bounce_only):
            self._bounce_btn.setChecked(bool(bounce_only))
            self._on_bounce_toggled(bool(bounce_only))
        else:
            self._rebuild()
        for c in self._model.get("all_corridors") or []:
            if c["from_core"] == from_core and c["to_core"] == to_core:
                self._show_topology(True)
                self._select_corridor(c)
                return True
        return False

    def set_filter_banner(self, label: Optional[str], count: int) -> None:
        if label and count:
            self._filter_lbl.setText(f"Showing {count} task(s): {label}")
            self._filter_bar.setVisible(True)
        else:
            self._filter_bar.setVisible(False)

    def _clear_filter(self) -> None:
        if self._on_clear:
            self._on_clear()

    def follow_scope(self) -> None:
        """Resume mirroring the main timeline viewport after Jump/Spotlight."""
        self._scope_follow = True

    def _freeze_scope(self) -> None:
        self._scope_follow = False

    def _on_chord_hover_info(self, info) -> None:
        if isinstance(info, dict) and info.get("type") == "corridor":
            self._hint.setText(
                f"{_core_short_name(info.get('from'))}→"
                f"{_core_short_name(info.get('to'))}: {info.get('count', 0)}")
            return
        self._hint.setText(self._HINT_DEFAULT)

    def refresh_scope(self) -> None:
        if not getattr(self, "_scope_follow", True) and self._model:
            return
        lo = hi = None
        suffix = ""
        wnd = self.parent()
        if isinstance(wnd, QMainWindow):
            tab = getattr(wnd, "_active_tab", None)
            view = getattr(tab, "view", None) if tab is not None else None
            if view is not None and hasattr(view, "_visible_time_ns_range"):
                try:
                    vlo, vhi = view._visible_time_ns_range()
                except Exception:
                    vlo = vhi = None
                if vlo is not None and vhi is not None and vhi > vlo:
                    lo, hi = int(vlo), int(vhi)
                    suffix = (
                        f"  (viewport: "
                        f"{_format_time(lo, self._trace.time_scale)} … "
                        f"{_format_time(hi, self._trace.time_scale)})")
        if lo == self._scope_lo and hi == self._scope_hi and self._model:
            self._scope_suffix = suffix
            return
        self._scope_lo, self._scope_hi = lo, hi
        self._scope_suffix = suffix
        self._rebuild()


class _ChordDiagramDialog(QDialog):
    """Popup: core-to-core migration volume as a directional chord diagram."""

    def __init__(self, trace: "BtfTrace", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Migration Chord Diagram")
        self.setMinimumSize(420, 420)
        self.resize(520, 560)
        self.setModal(False)
        self._trace = trace
        self._bounce_only = False
        self._scope_lo: Optional[int] = None
        self._scope_hi: Optional[int] = None
        self._scope_suffix = ""
        self._owner_tab_path: Optional[str] = None
        self._cores: list = []
        self._grid: list = []

        lay = QVBoxLayout(self)

        nav = QHBoxLayout()
        nav.addStretch(1)
        self._bounce_filter_btn = QPushButton("Show: All Migrations")
        self._bounce_filter_btn.setCheckable(True)
        self._bounce_filter_btn.setChecked(False)
        self._bounce_filter_btn.setToolTip(
            "Toggle between showing all migrations and only lock-bounce migrations\n"
            "(migrations that occurred while a mutex was held across different cores).")
        self._bounce_filter_btn.clicked.connect(self._on_bounce_filter_toggled)
        self._bounce_filter_btn.setVisible(_trace_has_core_bounce_holds(trace))
        nav.addWidget(self._bounce_filter_btn)
        lay.addLayout(nav)

        self._sub_label = QLabel()
        lay.addWidget(self._sub_label)

        self._empty_label = QLabel("No migrations in scope.")
        self._empty_label.setVisible(False)
        lay.addWidget(self._empty_label)

        self._canvas = _ChordDiagramWidget()
        self._canvas.hover_changed.connect(self._on_hover_changed)
        lay.addWidget(self._canvas, 1)

        # Fixed-height hover label (never conditionally hidden) so its
        # reserved space never shifts the canvas's available height — the
        # chord diagram's radius derives from the canvas's own size, so any
        # layout jump here would visibly resize the diagram on hover.
        self._hover_label = QLabel(" ")
        self._hover_label.setFixedHeight(
            QFontMetrics(self._hover_label.font()).height() + 2)
        lay.addWidget(self._hover_label)

        self._hint_label = QLabel(
            "Hover a core arc to highlight its migrations · chord width = "
            "migration count · color fades from source to destination core")
        self._hint_label.setStyleSheet(f"color:{_dim_css_color(self)};")
        self._hint_label.setWordWrap(True)
        lay.addWidget(self._hint_label)

        export_row = QHBoxLayout()
        export_row.setContentsMargins(0, 4, 0, 0)
        self._btn_export_png = QPushButton("Export PNG")
        self._btn_export_png.clicked.connect(self._export_png)
        export_row.addWidget(self._btn_export_png)
        self._btn_export_svg = QPushButton("Export SVG")
        self._btn_export_svg.clicked.connect(self._export_svg)
        export_row.addWidget(self._btn_export_svg)
        export_row.addStretch(1)
        lay.addLayout(export_row)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        lay.addWidget(btns)

        self.refresh_scope()

    def _on_hover_changed(self, index) -> None:
        self._hover_label.setText(self._hover_title(index))

    def _hover_title(self, index) -> str:
        if index is None:
            return " "
        cores = self._cores
        grid = self._grid
        if index < 0 or index >= len(cores):
            return " "
        core = cores[index]
        out_total = 0
        in_total = 0
        parts = []
        for j in range(len(cores)):
            if j == index:
                continue
            o = grid[index][j] if index < len(grid) and j < len(grid[index]) else 0
            i_ = grid[j][index] if j < len(grid) and index < len(grid[j]) else 0
            out_total += o
            in_total += i_
            if o:
                parts.append(
                    f"{_core_short_name(core)}→{_core_short_name(cores[j])}: {o}")
            if i_:
                parts.append(
                    f"{_core_short_name(cores[j])}→{_core_short_name(core)}: {i_}")
        summary = f"{_core_short_name(core)} · {out_total} out / {in_total} in"
        return f"{summary} · {' · '.join(parts)}" if parts else summary

    def _has_data(self) -> bool:
        cores = self._cores
        grid = self._grid
        for i in range(len(cores)):
            row = grid[i] if i < len(grid) else []
            for j in range(len(cores)):
                if i != j and (row[j] if j < len(row) else 0) > 0:
                    return True
        return False

    def _rebuild(self) -> None:
        n = len(self._cores)
        self._sub_label.setText(
            f"Core-to-core migration volume as directional chords ({n} cores)"
            f"{self._scope_suffix}")
        has_data = self._has_data()
        self._empty_label.setVisible(not has_data)
        self._canvas.setVisible(has_data)
        self._btn_export_png.setEnabled(has_data)
        self._btn_export_svg.setEnabled(has_data)
        if has_data:
            self._canvas.set_data(self._cores, self._grid)
        self._hover_label.setText(" ")

    def focus_pair(self, from_core: str, to_core: str,
                   bounce_only: bool = False) -> bool:
        """Re-filter and pin-highlight the source core of a directed pair."""
        if bool(self._bounce_only) != bool(bounce_only):
            self._bounce_filter_btn.setChecked(bool(bounce_only))
            self._on_bounce_filter_toggled(bool(bounce_only))
        else:
            self._reload_data()
            self._rebuild()
        try:
            fi = self._cores.index(from_core)
        except ValueError:
            return False
        if to_core not in self._cores:
            return False
        self._canvas.set_hover_index(fi, pinned=True)
        label = f"{_core_short_name(from_core)}→{_core_short_name(to_core)}"
        self._sub_label.setText(
            f"Core-to-core migration volume · focused {label}"
            f"{self._scope_suffix}")
        self._hover_label.setText(self._hover_title(fi) or " ")
        return True

    def _on_bounce_filter_toggled(self, checked: bool) -> None:
        self._bounce_only = checked
        self._bounce_filter_btn.setText(
            "Show: Lock-Bounce Only" if checked else "Show: All Migrations")
        self._reload_data()
        self._rebuild()

    def _reload_data(self) -> None:
        cores, grid = _migration_heatmap_matrix(
            self._trace, self._scope_lo, self._scope_hi,
            bounce_only=self._bounce_only)
        self._cores = cores
        self._grid = grid

    def refresh_scope(self) -> None:
        """Rebuild from current cursor scope (full trace if <2 cursors)."""
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
        self._scope_lo, self._scope_hi = lo, hi
        self._scope_suffix = suffix
        self._reload_data()
        self._rebuild()

    def _export_base_name(self) -> str:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"migration-chord-{stamp}"

    def _export_png(self) -> None:
        if not self._has_data():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Chord Diagram PNG",
            self._export_base_name() + ".png", "PNG Image (*.png)")
        if not path:
            return
        self._canvas.grab_full_pixmap().save(path, "PNG")

    def _export_svg(self) -> None:
        if not self._has_data():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Chord Diagram SVG",
            self._export_base_name() + ".svg", "SVG Image (*.svg)")
        if not path:
            return
        self._canvas.render_full_svg(path, "Migration Chord Diagram")

def _load_balance_metrics(pcts: List[float]) -> Optional[dict]:
    """Return {score, gini, stddev, zone, amber, red} for ≥2 core util %, else None."""
    if len(pcts) < 2:
        return None
    if sum(pcts) <= 0.0:
        return None
    gini = _gini_coefficient(pcts)
    stddev = _core_util_stddev(pcts)
    score = max(0.0, 100.0 * (1.0 - gini))
    # Align with Analysis Findings: red when score < 70%; amber when σ > 30%.
    if score < 70.0:
        zone = "red"
    elif stddev > 30.0:
        zone = "amber"
    else:
        zone = "ok"
    return {
        "score": score,
        "gini": gini,
        "stddev": stddev,
        "zone": zone,
        "amber": zone in ("amber", "red"),
        "red": zone == "red",
    }


def _lb_polar(cx: float, cy: float, r: float, deg: float) -> Tuple[float, float]:
    rad = math.radians(deg)
    return cx + math.cos(rad) * r, cy - math.sin(rad) * r


def _lb_semicircle(cx: float, cy: float, r: float) -> str:
    sx, sy = _lb_polar(cx, cy, r, 180.0)
    ex, ey = _lb_polar(cx, cy, r, 0.0)
    return f"M {sx:.2f} {sy:.2f} A {r} {r} 0 0 1 {ex:.2f} {ey:.2f}"


_LB_SIGMA_SCALE = 60.0
_LB_SIGMA_WARN = 30.0
_LB_SIGMA_RED = 50.0


def _lb_value_arc(value: float, max_v: float, cx: float, cy: float, r: float) -> str:
    m = max(1e-9, float(max_v))
    s = max(0.0, min(m, float(value)))
    end_deg = 180.0 - (s / m) * 180.0
    sx, sy = _lb_polar(cx, cy, r, 180.0)
    ex, ey = _lb_polar(cx, cy, r, end_deg)
    sweep = 180.0 - end_deg
    if sweep < 0.5:
        return f"M {sx:.2f} {sy:.2f}"
    return f"M {sx:.2f} {sy:.2f} A {r} {r} 0 0 1 {ex:.2f} {ey:.2f}"


def _lb_sigma_zone(stddev: float) -> str:
    if stddev > _LB_SIGMA_RED:
        return "red"
    if stddev > _LB_SIGMA_WARN:
        return "amber"
    return "ok"


def _lb_zone_palette(zone: str) -> Tuple[str, str, str, str]:
    """Return (accent, end_color, grad0, grad1)."""
    if zone == "red":
        return "#C62828", "#E53935", "#EF5350", "#E53935"
    if zone == "amber":
        return "#C47F00", "#E0A020", "#3B82F6", "#14B8A6"
    return "#1a8a2a", "#22C55E", "#3B82F6", "#14B8A6"


def _lb_gauge_svg_body(
    *,
    uid: str,
    cx: float,
    cy: float,
    value: float,
    max_v: float,
    zone: str,
    title: str,
    value_label: str,
    legend: str,
    r: float = 48.0,
    needle_len: float = 32.0,
    stroke_w: float = 8.0,
) -> str:
    accent, end_color, grad0, grad1 = _lb_zone_palette(zone)
    bg = _lb_semicircle(cx, cy, r)
    fill = _lb_value_arc(value, max_v, cx, cy, r)
    end_deg = 180.0 - (max(0.0, min(max_v, value)) / max(1e-9, max_v)) * 180.0
    rad = math.radians(end_deg)
    tip_x = cx + math.cos(rad) * needle_len
    tip_y = cy - math.sin(rad) * needle_len
    value_y = cy - round(r * 0.28)
    sans = _get_sans_font_family()
    return (
        "<defs>"
        f'<linearGradient id="{uid}" x1="0%" y1="0%" x2="100%" y2="0%">'
        f'<stop offset="0%" stop-color="{grad0}"/>'
        f'<stop offset="55%" stop-color="{grad1}"/>'
        f'<stop offset="100%" stop-color="{end_color}"/>'
        "</linearGradient></defs>"
        f'<text x="{cx}" y="18" text-anchor="middle" fill="#1A2030" '
        f'font-family="{sans}" font-size="10" font-weight="600">{title}</text>'
        f'<path d="{bg}" fill="none" stroke="#D8DCE4" stroke-width="{stroke_w:.0f}" '
        f'stroke-linecap="round"/>'
        f'<path d="{fill}" fill="none" stroke="url(#{uid})" stroke-width="{stroke_w:.0f}" '
        f'stroke-linecap="round"/>'
        f'<line x1="{cx}" y1="{cy}" x2="{tip_x:.2f}" y2="{tip_y:.2f}" '
        f'stroke="#1A2030" stroke-width="2" stroke-linecap="round"/>'
        f'<circle cx="{cx}" cy="{cy}" r="3.5" fill="#FFFFFF" stroke="#1A2030" stroke-width="1.75"/>'
        f'<text x="{cx}" y="{value_y:.0f}" text-anchor="middle" fill="{accent}" '
        f'font-family="{sans}" font-size="12" font-weight="700">'
        f"{value_label}</text>"
        f'<text x="{cx}" y="{cy + 16:.0f}" text-anchor="middle" fill="#6A7388" '
        f'font-family="{sans}" font-size="9">{legend}</text>'
    )


def _load_balance_gauge_svg(metrics: dict, *, width: int = 300, dark: bool = False) -> str:
    """Dual Score + σ gauges SVG for HTML export (parity with web)."""
    del dark  # export is always light/print-friendly
    score = max(0.0, min(100.0, float(metrics.get("score", 0.0))))
    gini = float(metrics.get("gini", 0.0))
    stddev = float(metrics.get("stddev", 0.0))
    zone = str(metrics.get("zone") or "")
    if zone not in ("ok", "amber", "red"):
        if score < 70.0:
            zone = "red"
        elif stddev > 30.0:
            zone = "amber"
        else:
            zone = "ok"
    score_zone = "red" if score < 70.0 else "ok"
    sigma_zone = _lb_sigma_zone(stddev)
    view_w, view_h = 300, 150
    left_cx, right_cx, cy = 70.0, 230.0, 88.0
    uid = f"lb{abs(int(score * 17 + stddev * 13))}"
    h = int(round(width * view_h / view_w))
    times = "\u00d7"
    minus = "\u2212"
    sans = _get_sans_font_family()
    mono = _get_fixed_font_family()
    if zone == "red":
        card_stroke = "#E57373"
    elif zone == "amber":
        card_stroke = "#E0A020"
    else:
        card_stroke = "#E2E5EC"
    left = _lb_gauge_svg_body(
        uid=f"{uid}S",
        cx=left_cx,
        cy=cy,
        value=score,
        max_v=100.0,
        zone=score_zone,
        title="Load Balance Score",
        value_label=f"{score:.0f}%",
        legend="100 = balanced · 0 = overload",
    )
    right = _lb_gauge_svg_body(
        uid=f"{uid}D",
        cx=right_cx,
        cy=cy,
        value=min(stddev, _LB_SIGMA_SCALE),
        max_v=_LB_SIGMA_SCALE,
        zone=sigma_zone,
        title="Std Deviation (σ)",
        value_label=f"{stddev:.1f}%",
        legend=f"0–{_LB_SIGMA_SCALE:.0f}% · warn &gt; {_LB_SIGMA_WARN:.0f}%",
    )
    chip = ""
    if zone == "red":
        chip = (
            '<rect x="210" y="8" width="80" height="18" rx="5" fill="#FDECEA" stroke="#E57373"/>'
            f'<text x="250" y="21" text-anchor="middle" fill="#C62828" '
            f'font-family="{sans}" font-size="10" font-weight="700">'
            "Unbalanced</text>"
        )
    elif zone == "amber":
        chip = (
            '<rect x="228" y="8" width="62" height="18" rx="5" fill="#FFF6E5" stroke="#E0A020"/>'
            f'<text x="259" y="21" text-anchor="middle" fill="#C47F00" '
            f'font-family="{sans}" font-size="10" font-weight="700">'
            "σ &gt; 30%</text>"
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {view_w} {view_h}" '
        f'width="{width}" height="{h}" role="img" '
        f'aria-label="Load Balance Score {score:.0f} percent, sigma {stddev:.1f} percent">'
        f'<rect width="{view_w}" height="{view_h}" rx="8" fill="#F7F8FA" stroke="{card_stroke}"/>'
        f"{left}{right}"
        f'<text x="{view_w / 2}" y="{view_h - 8}" text-anchor="middle" fill="#6A7388" '
        f'font-family="{mono}" font-size="9">'
        f"G={gini:.3f} · Score=100{times}(1{minus}Gini)</text>"
        f"{chip}</svg>"
    )


def _load_balance_gauge_img_html(metrics: dict, *, width: int = 300) -> str:
    """HTML snippet with dual gauges as an embedded SVG data-URI <img>."""
    svg = _load_balance_gauge_svg(metrics, width=width)
    score = max(0.0, min(100.0, float(metrics.get("score", 0.0))))
    stddev = float(metrics.get("stddev", 0.0))
    zone = str(metrics.get("zone") or "ok")
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    data_uri = f"data:image/svg+xml;base64,{b64}"
    h = int(round(width * 150 / 300))
    return (
        f'<div class="lb-gauge-embed" style="margin:8px 0 12px;">'
        f'<img src="{data_uri}" width="{width}" height="{h}" '
        f'alt="Load Balance Score {score:.0f}%, σ={stddev:.1f}% ({zone})" '
        f'style="display:block;max-width:100%;height:auto;border:0;"/>'
        f"</div>"
    )


class _LoadBalanceGaugeWidget(QWidget):
    """Side-by-side Load Balance Score + σ gauges for the Statistics panel."""

    _VW, _VH = 320, 200
    _SIGMA_SCALE = _LB_SIGMA_SCALE

    def __init__(self, metrics: dict, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._metrics = dict(metrics)
        self.setMinimumHeight(170)
        self.setMaximumHeight(230)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(
            "Load Balance Score = 100% × (1 − Gini); σ = population stddev of core util %. "
            "Score red when < 70%. σ amber when > 30%."
        )

    def set_metrics(self, metrics: dict) -> None:
        self._metrics = dict(metrics)
        self.update()

    def sizeHint(self):  # noqa: N802
        return QSize(self._VW, self._VH)

    def _paint_one_gauge(
        self,
        p: QPainter,
        *,
        rect: QRectF,
        value: float,
        max_v: float,
        zone: str,
        title: str,
        value_label: str,
        caption: str,
        card_bg: QColor,
        fg: QColor,
        muted: QColor,
        border: QColor,
    ) -> None:
        header = QFont(self.font())
        header.setPointSizeF(max(8.0, self.font().pointSizeF() - 0.5))
        header.setBold(True)
        p.setFont(header)
        p.setPen(fg)
        p.drawText(
            QRectF(rect.left() + 4, rect.top(), rect.width() - 8, 16),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            title,
        )
        if zone == "red":
            chip = QRectF(rect.right() - 78, rect.top() + 1, 74, 16)
            p.setPen(QPen(QColor("#E57373"), 1.0))
            p.setBrush(QColor("#FDECEA"))
            p.drawRoundedRect(chip, 8, 8)
            chip_font = QFont(self.font())
            chip_font.setPointSizeF(7.5)
            chip_font.setBold(True)
            p.setFont(chip_font)
            p.setPen(QColor("#C62828"))
            p.drawText(chip, int(Qt.AlignmentFlag.AlignCenter), "Unbalanced")
        elif zone == "amber":
            chip = QRectF(rect.right() - 62, rect.top() + 1, 58, 16)
            p.setPen(QPen(QColor("#E0A020"), 1.0))
            p.setBrush(QColor("#FFF6E5"))
            p.drawRoundedRect(chip, 8, 8)
            chip_font = QFont(self.font())
            chip_font.setPointSizeF(7.5)
            chip_font.setBold(True)
            p.setFont(chip_font)
            p.setPen(QColor("#C47F00"))
            p.drawText(chip, int(Qt.AlignmentFlag.AlignCenter), "σ > 30%")

        cy = rect.bottom() - 22
        cx = rect.center().x()
        r = min(rect.width() * 0.38, max(28.0, rect.height() - 48))
        needle_len = r * 0.68
        track_c = QColor(border)
        track_c.setAlpha(max(70, border.alpha()))
        p.setPen(QPen(track_c, 8.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), 180 * 16, -180 * 16)

        frac = max(0.0, min(1.0, value / max(1e-9, max_v)))
        grad = QLinearGradient(cx - r, cy, cx + r, cy)
        if zone == "red":
            grad.setColorAt(0.0, QColor("#EF5350"))
            grad.setColorAt(0.55, QColor("#E53935"))
            grad.setColorAt(1.0, QColor("#C62828"))
        else:
            grad.setColorAt(0.0, QColor("#3B82F6"))
            grad.setColorAt(0.55, QColor("#14B8A6"))
            grad.setColorAt(1.0, QColor("#E0A020" if zone == "amber" else "#22C55E"))
        span = -int(frac * 180.0 * 16)
        p.setPen(QPen(QBrush(grad), 8.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), 180 * 16, span)

        end_deg = 180.0 - frac * 180.0
        rad = math.radians(end_deg)
        nx = cx + math.cos(rad) * needle_len
        ny = cy - math.sin(rad) * needle_len
        p.setPen(QPen(fg, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(cx, cy), QPointF(nx, ny))
        p.setBrush(card_bg)
        p.setPen(QPen(fg, 1.75))
        p.drawEllipse(QPointF(cx, cy), 3.5, 3.5)

        score_font = QFont(self.font())
        score_font.setPointSizeF(11.0)
        score_font.setBold(True)
        p.setFont(score_font)
        if zone == "red":
            p.setPen(QColor("#C62828"))
        elif zone == "amber":
            p.setPen(QColor("#C47F00"))
        else:
            p.setPen(QColor("#1a8a2a"))
        # Sit in the arc hollow just above the hub — avoid overlapping the stroke.
        p.drawText(
            QRectF(cx - 40, cy - r * 0.42, 80, 20),
            int(Qt.AlignmentFlag.AlignCenter),
            value_label,
        )

        cap = QFont(self.font())
        cap.setPointSizeF(7.5)
        p.setFont(cap)
        p.setPen(muted)
        p.drawText(
            QRectF(rect.left() + 2, rect.bottom() - 14, rect.width() - 4, 12),
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
            caption,
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        score = max(0.0, min(100.0, float(self._metrics.get("score", 0.0))))
        gini = float(self._metrics.get("gini", 0.0))
        stddev = float(self._metrics.get("stddev", 0.0))
        zone = str(self._metrics.get("zone") or "")
        if zone not in ("ok", "amber", "red"):
            if score < 70.0:
                zone = "red"
            elif stddev > 30.0:
                zone = "amber"
            else:
                zone = "ok"
        score_zone = "red" if score < 70.0 else "ok"
        sigma_zone = _lb_sigma_zone(stddev)

        bg = self.palette().color(QPalette.ColorRole.Window)
        fg = self.palette().color(QPalette.ColorRole.WindowText)
        muted = QColor(fg)
        muted.setAlpha(150)
        border = self.palette().color(QPalette.ColorRole.Mid)
        if not border.isValid() or border.alpha() == 0:
            border = QColor(fg)
            border.setAlpha(45)

        card_bg = QColor(bg)
        if zone == "red":
            border = QColor("#E57373")
            card_bg = QColor(
                min(255, int(bg.red() * 0.94 + 198 * 0.06)),
                min(255, int(bg.green() * 0.94 + 40 * 0.06)),
                min(255, int(bg.blue() * 0.94 + 40 * 0.06)),
            )
        elif zone == "amber":
            border = QColor("#E0A020")

        p.setPen(QPen(border, 1.0))
        p.setBrush(card_bg)
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0), 8, 8)

        footer_h = 34 if zone == "red" else 18
        body = QRectF(6, 6, self.width() - 12, self.height() - footer_h - 10)
        half_w = (body.width() - 8) / 2.0
        left = QRectF(body.left(), body.top(), half_w, body.height())
        right = QRectF(body.left() + half_w + 8, body.top(), half_w, body.height())

        self._paint_one_gauge(
            p,
            rect=left,
            value=score,
            max_v=100.0,
            zone=score_zone,
            title="Load Balance Score",
            value_label=f"{score:.0f}%",
            caption="100 = balanced · 0 = overload",
            card_bg=card_bg,
            fg=fg,
            muted=muted,
            border=border,
        )
        self._paint_one_gauge(
            p,
            rect=right,
            value=min(stddev, self._SIGMA_SCALE),
            max_v=self._SIGMA_SCALE,
            zone=sigma_zone,
            title="Std Deviation (σ)",
            value_label=f"{stddev:.1f}%",
            caption=f"0–{self._SIGMA_SCALE:.0f}% · warn > 30%",
            card_bg=card_bg,
            fg=fg,
            muted=muted,
            border=border,
        )

        y = self.height() - footer_h
        if zone == "red":
            alert = QRectF(8, y, self.width() - 16, 14)
            p.setPen(QPen(QColor("#E57373"), 1.0))
            p.setBrush(QColor("#FDECEA"))
            p.drawRoundedRect(alert, 5, 5)
            alert_font = QFont(self.font())
            alert_font.setPointSizeF(7.5)
            alert_font.setBold(True)
            p.setFont(alert_font)
            p.setPen(QColor("#C62828"))
            p.drawText(
                alert,
                int(Qt.AlignmentFlag.AlignCenter),
                "Red zone: score < 70% — load is unbalanced",
            )
            y += 16

        meta_font = QFont(_get_fixed_font_family())
        meta_font.setPointSizeF(8.0)
        p.setFont(meta_font)
        p.setPen(muted)
        p.drawText(
            QRectF(8, y, self.width() - 16, 14),
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
            f"G={gini:.3f} · Score = 100 × (1 − Gini)",
        )


# ---------------------------------------------------------------------------
# Analysis Findings (Statistics HTML report heuristics)
# ---------------------------------------------------------------------------

_WF_FINDING_CAP = 5
_WF_LOAD_SIGMA_WARN = 30.0
# Load Balance Score = 100×(1−Gini). Warn below this; only call "balanced" above OK.
_WF_LOAD_SCORE_WARN = 70.0
_WF_LOAD_SCORE_OK = 85.0
_WF_THRASH_PING_MIN = 3
_WF_THRASH_RATE_PER_S = 1.0
_WF_THRASH_MIG_MIN = 10
_WF_PAIR_BOUNCE_PCT = 25.0
_WF_PAIR_COUNT_MIN = 5
_WF_WCET_MAX_AVG_RATIO = 5.0
_WF_MIG_BURST_RATE = 10.0


def _finding(
    severity: str,
    title: str,
    text: str,
    *,
    fid: str = "",
    task: str = "",
    evidence: Optional[list] = None,
) -> dict:
    out = {
        "severity": severity,
        "title": title,
        "text": text,
        "id": fid or "",
        "task": task or "",
        "evidence": list(evidence or []),
    }
    return out


def _build_workflow_analysis_findings(
    *,
    core_rows: List[Tuple[str, float]],
    exec_rows: list,
    block_rows: list,
    mig_rows: list,
    pair_rows: list,
    priority_rows: list,
    sync_rows: list,
    sync_issues: list,
    tick: dict,
    deadline_viols: Optional[dict] = None,
    time_scale: str = "ns",
) -> List[dict]:
    """Return interpretive findings for the Statistics HTML report.

    Each finding is ``{severity, title, text, id?, task?, evidence?}`` where
    *severity* is ``info`` / ``warning`` / ``error``.
    """
    findings: List[dict] = []

    # Load balance
    pcts = [pct for _, pct in core_rows]
    if len(pcts) >= 2:
        gini = _gini_coefficient(pcts)
        sigma = _core_util_stddev(pcts)
        score = max(0.0, 100.0 * (1.0 - gini))
        metrics = f"Load Balance Score {score:.0f}% (σ={sigma:.1f}%, G={gini:.3f})"
        if score < _WF_LOAD_SCORE_WARN or sigma > _WF_LOAD_SIGMA_WARN:
            findings.append(_finding(
                "warning",
                "Load imbalance across cores",
                f"{metrics}. Uneven core placement — "
                "check Core Affinity and Core Migrations.",
                fid="load_imbalance",
            ))
        elif score >= _WF_LOAD_SCORE_OK:
            findings.append(_finding(
                "info",
                "Core utilisation balance",
                f"{metrics} — cores look reasonably balanced.",
                fid="load_balance_ok",
            ))
        else:
            findings.append(_finding(
                "info",
                "Core utilisation balance",
                f"{metrics} — moderate spread; review Core Utilisation "
                "if the workload is expected to be even.",
                fid="load_balance_moderate",
            ))

    # WCET / high CPU tasks
    if exec_rows:
        top = exec_rows[:_WF_FINDING_CAP]
        names = ", ".join(f"{r[1]} ({r[3]:.1f}%, Max {r[7]})" for r in top)
        findings.append(_finding(
            "info",
            "Top tasks by CPU (WCET candidates)",
            f"Highest CPU% tasks: {names}. "
            "Open Execution Time and click Max to jump to the worst-case slice.",
            fid="top_cpu",
        ))

    # Blocking
    if block_rows:
        top_b = sorted(block_rows, key=lambda r: (-r[2], r[1].lower()))[:_WF_FINDING_CAP]
        names = ", ".join(f"{r[1]} (n={r[2]}, Max {r[6]})" for r in top_b)
        findings.append(_finding(
            "warning" if top_b and top_b[0][2] >= 20 else "info",
            "Blocking / scheduling-delay candidates",
            f"Tasks with the most off-CPU gaps: {names}. "
            "Cross-check Preemption Chain and Mutex/Semaphore.",
            fid="blocking",
        ))

    # Priority inversion — row: (mk, label, base, peak, n, total_str, pattern, total_ns)
    inv_rows = [
        r for r in (priority_rows or [])
        if len(r) > 6 and "L/M/H" in str(r[6])
    ]
    if inv_rows:
        names = ", ".join(str(r[1]) for r in inv_rows[:_WF_FINDING_CAP])
        findings.append(_finding(
            "warning",
            "Priority inversion (L/M/H) suspected",
            f"Tasks with L/M/H pattern: {names}. "
            "Inspect Priority Inheritance boost episodes and the holding mutex.",
            fid="priority_inversion",
        ))

    # Core thrashing / excessive bouncing
    thrash: List[str] = []
    burst_rows: List[Tuple[str, float, int]] = []
    for r in (mig_rows or []):
        (_mk, name, n_mig, _nc, _cs, _pri, primary_pct,
         ping, _sti, _ga, _go, _rate_lbl, rate_per_s, _dwell_lbl, dwell_tu) = r
        hot = (
            ping >= _WF_THRASH_PING_MIN
            or (isinstance(rate_per_s, (int, float))
                and rate_per_s >= _WF_THRASH_RATE_PER_S and n_mig >= _WF_THRASH_MIG_MIN)
            or (n_mig >= _WF_THRASH_MIG_MIN and dwell_tu > 0
                and primary_pct < 55.0 and _nc >= 2)
        )
        if hot:
            thrash.append(
                f"{name} (Migr={n_mig}, Rate={_rate_lbl}, Dwell={_dwell_lbl}, Ping={ping})"
            )
        if isinstance(rate_per_s, (int, float)):
            burst_rows.append((str(name), float(rate_per_s), int(n_mig)))
    if thrash:
        findings.append(_finding(
            "warning",
            "Excessive bouncing / core thrashing",
            "High migration rate, short dwell, and/or ping-pong detected: "
            + "; ".join(thrash[:_WF_FINDING_CAP])
            + ". See Core-Pair Migration Summary and the Migration Heatmap.",
            fid="thrashing",
        ))

    hot_pairs: List[str] = []
    for fc, tc, cnt, bnc, avg_gap in (pair_rows or []):
        bounce_pct = (100.0 * bnc / cnt) if cnt else 0.0
        if cnt >= _WF_PAIR_COUNT_MIN and bounce_pct >= _WF_PAIR_BOUNCE_PCT:
            hot_pairs.append(
                f"{fc}→{tc} (Count={cnt}, Bounce={bounce_pct:.0f}%, "
                f"AvgGap={_format_time(int(avg_gap), time_scale) if avg_gap else '—'})"
            )
        elif cnt >= max(_WF_PAIR_COUNT_MIN * 2, 20) and not thrash:
            hot_pairs.append(f"{fc}→{tc} (Count={cnt})")
    if hot_pairs:
        findings.append(_finding(
            "warning",
            "Hot core-pair migration traffic",
            "Directed pairs with heavy traffic and/or lock-bounce share: "
            + "; ".join(hot_pairs[:_WF_FINDING_CAP])
            + ".",
            fid="hot_pairs",
        ))

    # Deadlines / CPU budget
    if deadline_viols:
        sv = deadline_viols.get("slice_violations") or []
        cv = deadline_viols.get("cpu_violations") or []
        if sv or cv:
            parts = []
            if sv:
                parts.append(f"{len(sv)} slice deadline violation(s)")
            if cv:
                parts.append(f"{len(cv)} CPU budget violation(s)")
            findings.append(_finding(
                "error",
                "Deadline / CPU budget breaches",
                ", ".join(parts) + " in scope. "
                "See Deadlines / CPU budget tables below.",
                fid="deadlines",
            ))

    # Tick health
    if tick and tick.get("tick_count"):
        health = str(tick.get("health", "")).lower()
        missed = int(tick.get("missed_estimate") or 0)
        if health and health != "good":
            findings.append(_finding(
                "warning" if health != "bad" else "error",
                f"Trace Health (TICK) = {health.upper()}",
                f"Mode={'TICKLESS' if tick.get('is_tickless') else 'TICK'}, "
                f"CV={float(tick.get('tick_cv') or 0) * 100:.2f}%, "
                f"missed≈{missed}. Investigate large TICK gaps and long slices.",
                fid="tick_health",
            ))
        elif missed > 0:
            findings.append(_finding(
                "warning",
                "Estimated missed ticks",
                f"About {missed} missed tick(s) estimated from large gaps. "
                "See Trace Health (TICK) large-gap table.",
                fid="missed_ticks",
            ))

    # Sync / mutex bounces
    bounce_objs = 0
    for r in (sync_rows or []):
        if len(r) > 10 and r[10] > 0:
            bounce_objs += 1
    issue_n = len(sync_issues or [])
    bounce_issues = sum(
        1 for i in (sync_issues or [])
        if "BOUNCE" in str(i.get("kind", "")).upper()
        or "MIGRATION_WHILE_HELD" in str(i.get("kind", "")).upper()
        or "bounc" in str(i.get("detail", "")).lower()
    )
    if bounce_objs or bounce_issues:
        findings.append(_finding(
            "warning",
            "Mutex / semaphore core-boundary bounces",
            f"{bounce_objs} sync object(s) with Core bounce > 0"
            + (f"; {bounce_issues} CORE_MIGRATION_WHILE_HELD-style issue(s)"
               if bounce_issues else "")
            + ". Cross-check Core-Pair Migration Summary Bounce %.",
            fid="sync_bounce",
        ))
    elif issue_n > 0:
        findings.append(_finding(
            "warning",
            "Sync pairing issues",
            f"{issue_n} mutex/semaphore pairing issue(s) in scope "
            "(orphan give, unmatched take, etc.).",
            fid="sync_issues",
        ))

    # Anomalies (beyond fixed thrash/load thresholds)
    append_migration_burst_anomaly(
        findings, burst_rows, rate_threshold=_WF_MIG_BURST_RATE)

    actionable = [f for f in findings if f["severity"] in ("warning", "error")]
    if not actionable and not any(f["title"].startswith("Top tasks") for f in findings):
        findings.append(_finding(
            "info",
            "No analysis heuristics flagged",
            "No load-imbalance, thrashing, deadline, tick, or sync warnings "
            "in the current scope. Review the tables below for detail.",
            fid="none",
        ))

    return enrich_findings_with_ids(findings)


def _format_analysis_findings_text(
    findings: List[dict], scope_title: str = "",
) -> str:
    """Plain-text export of Analysis Findings."""
    lines = [f"Analysis Findings{scope_title}".rstrip(), ""]
    lines.append(
        "Heuristic summary of load balance, WCET, blocking, thrashing, "
        "deadlines, tick health, and sync."
    )
    lines.append("")
    if not findings:
        lines.append("No findings for the current scope")
    else:
        for i, f in enumerate(findings, 1):
            sev = str(f.get("severity", "info")).upper()
            title = str(f.get("title", "Finding"))
            text = str(f.get("text", ""))
            fid = str(f.get("id") or "").strip()
            id_bit = f" id={fid}" if fid else ""
            lines.append(f"{i}. [{sev}]{id_bit} {title}")
            lines.append(f"   {text}")
            for ev in (f.get("evidence") or []):
                if isinstance(ev, dict) and ev.get("time") is not None:
                    lines.append(
                        f"   evidence: {ev.get('label') or 'event'} jump:{ev.get('time')}"
                    )
                elif ev:
                    lines.append(f"   evidence: {ev}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_workflow_analysis_html(
    findings: List[dict], scope_title: str = "",
) -> str:
    """Render Analysis Findings as an HTML report-card section."""
    if not findings:
        return ""

    def _esc(v: object) -> str:
        return html.escape(str(v), quote=True)

    items = []
    for f in findings:
        sev = f.get("severity", "info")
        cls = {
            "error": "sev-error",
            "warning": "sev-warning",
            "info": "finding-info",
        }.get(sev, "finding-info")
        items.append(
            f'<li class="{cls}">'
            f'<strong>{_esc(f.get("title", "Finding"))}</strong>'
            f' — {_esc(f.get("text", ""))}'
            f"</li>"
        )
    body = "".join(items)
    return (
        f'<section class="report-card notes analysis-findings">'
        f"<h2>Analysis Findings{_esc(scope_title)}</h2>"
        f"<p class=\"detail-note\">Heuristic summary of load balance, WCET, "
        f"blocking, thrashing, deadlines, tick health, and sync.</p>"
        f"<ul class=\"findings-list\">{body}</ul></section>"
    )


class _AnalysisFindingsDialog(QDialog):
    """Toolbar Analysis dialog — lists heuristic findings for the current scope."""

    def __init__(self, findings: List[dict], scope_title: str = "", parent=None,
                 ai_enabled: bool = True, ui_font_size: int = UI_FONT_SIZE):
        super().__init__(parent)
        self._findings = findings or []
        self._scope_title = scope_title or ""
        self.wants_ai_query = False
        self._ai_needs_settings = False
        self.wants_ai_finding_id = ""
        self.wants_ai_template = "findings"
        self.setWindowTitle(f"Analysis Findings{self._scope_title}")
        self.setModal(True)
        # Match menus/toolbar (Settings → Display → UI / menus), not a fixed 11pt.
        ui_pt = max(6, min(int(ui_font_size), 24))
        ui_font = _application_ui_font(ui_pt)
        ui_fs = _ui_font_stylesheet_size(ui_pt)
        self.setFont(ui_font)
        # Wide enough for Ask-AI button labels (esp. "Auto investigate…") in one row.
        self.setMinimumSize(900, 480)
        self.resize(960, 600)

        note = QLabel(
            "Heuristic summary of load balance, WCET, blocking, thrashing, "
            "deadlines, tick health, and sync.\n"
            "Select a finding before Verify, Explain, or Auto investigate."
        )
        note.setWordWrap(True)
        note.setObjectName("analysisNote")
        note.setStyleSheet(
            f"color: #9a9a9a; font-size: {ui_fs}; padding-bottom: 2px;")

        list_w = QListWidget()
        list_w.setFont(ui_font)
        list_w.setWordWrap(True)
        list_w.setSpacing(6)
        list_w.setUniformItemSizes(False)
        list_w.setAlternatingRowColors(True)
        list_w.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        list_w.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        list_w.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        list_w.setStyleSheet(
            f"QListWidget {{ padding: 8px; outline: none; border-radius: 6px;"
            f" font-size: {ui_fs}; }}"
            "QListWidget::item {"
            "  padding: 10px 12px;"
            "  margin: 3px 0;"
            "  border-radius: 6px;"
            "}"
            "QListWidget::item:selected {"
            "  background: rgba(52, 152, 219, 0.30);"
            "}"
        )
        self._list_w = list_w
        if self._findings:
            for f in self._findings:
                sev = f.get("severity", "info")
                title = str(f.get("title", "Finding")).strip() or "Finding"
                text = str(f.get("text", "")).strip()
                badge = {"error": "●", "warning": "●"}.get(str(sev), "○")
                display = f"{badge}  {title}\n{text}" if text else f"{badge}  {title}"
                item = QListWidgetItem(display)
                item.setData(Qt.ItemDataRole.UserRole, f.get("id") or "")
                item.setFont(ui_font)
                if sev == "error":
                    item.setForeground(QBrush(QColor("#e74c3c")))
                elif sev == "warning":
                    item.setForeground(QBrush(QColor("#e67e22")))
                fm = QFontMetrics(ui_font)
                wrap_w = 640
                body_h = fm.boundingRect(
                    0, 0, wrap_w, 8000,
                    int(Qt.TextFlag.TextWordWrap),
                    display,
                ).height()
                # Scale row height with UI font (was tuned for forced 11pt).
                pad = max(16, int(round(ui_pt * 2.0)))
                min_h = max(40, int(round(ui_pt * 5.0)))
                item.setSizeHint(QSize(wrap_w, max(min_h, body_h + pad)))
                list_w.addItem(item)
            list_w.setCurrentRow(0)
        else:
            empty = QListWidgetItem("No findings for the current scope")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            empty.setFont(ui_font)
            list_w.addItem(empty)

        def _make_ai_btn(label: str, tip_on: str, tip_off: str, template: str,
                         *, primary: bool = False) -> QPushButton:
            btn = QPushButton(label)
            btn.setFont(ui_font)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(max(28, int(round(ui_pt * 3.2))))
            # Prefer natural text width — avoid MinimumExpanding which clips labels.
            btn.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Fixed,
            )
            fm = btn.fontMetrics()
            btn.setMinimumWidth(fm.horizontalAdvance(label) + 36)
            btn.setToolTip(tip_on if ai_enabled else tip_off)
            if primary:
                btn.setStyleSheet(
                    "QPushButton {"
                    f"  padding: 7px 16px; border-radius: 6px; font-size: {ui_fs};"
                    "  background: #3498db; color: white; border: none;"
                    "  font-weight: 600;"
                    "}"
                    "QPushButton:hover { background: #5dade2; }"
                    "QPushButton:pressed { background: #2e86c1; }"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ padding: 7px 16px; border-radius: 6px;"
                    f" font-size: {ui_fs}; }}"
                )
            btn.clicked.connect(
                lambda _checked=False, t=template: self._query_with_ai(
                    ai_enabled, t))
            return btn

        def _make_explain_btn() -> QToolButton:
            btn = QToolButton()
            btn.setText("Explain…")
            btn.setFont(ui_font)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(max(28, int(round(ui_pt * 3.2))))
            btn.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Fixed,
            )
            fm = btn.fontMetrics()
            btn.setMinimumWidth(fm.horizontalAdvance("Explain…") + 36)
            btn.setToolTip(
                "Quick / Technical / Deep explanation of the selected finding"
                if ai_enabled else "Enable AI Assistant in Settings → AI"
            )
            btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            btn.setStyleSheet(
                f"QToolButton {{ padding: 7px 16px; border-radius: 6px;"
                f" font-size: {ui_fs}; }}"
            )
            menu = QMenu(btn)
            for level in EXPLAIN_LEVELS:
                act = menu.addAction(str(level).title())
                act.triggered.connect(
                    lambda _=False, lv=level: self._query_with_ai(
                        ai_enabled, "explain_finding", level=lv)
                )
            btn.setMenu(menu)
            return btn

        ai_label = QLabel("Ask AI")
        ai_label.setStyleSheet(
            f"color: #8a8a8a; font-size: {ui_fs}; font-weight: 600;"
            " letter-spacing: 0.4px; padding-top: 2px;"
        )

        ai_row = QHBoxLayout()
        ai_row.setContentsMargins(0, 0, 0, 0)
        ai_row.setSpacing(10)
        ai_btns = [
            _make_ai_btn(
                "Investigate…",
                "Open the AI Assistant and investigate the top findings with tools",
                "Enable AI Assistant in Settings → AI",
                "investigate",
                primary=True,
            ),
            _make_ai_btn(
                "Root cause…",
                "Open the AI Assistant for evidence-driven root-cause analysis",
                "Enable AI Assistant in Settings → AI",
                "root_cause",
            ),
            _make_ai_btn(
                "Verify with AI…",
                "Open the AI Assistant and verify the selected finding with evidence",
                "Enable AI Assistant in Settings → AI",
                "verify",
            ),
            _make_explain_btn(),
            _make_ai_btn(
                "Auto investigate…",
                "Run the automatic investigate → correlate → critical-path → "
                "what-if/optimize workflow",
                "Enable AI Assistant in Settings → AI",
                "auto_investigate",
            ),
            _make_ai_btn(
                "Query with AI…",
                "Open the AI Assistant and walk through these Analysis Findings",
                "Enable AI Assistant in Settings → AI",
                "findings",
            ),
        ]
        for btn in ai_btns:
            ai_row.addWidget(btn)
        ai_row.addStretch(1)

        btn_h = max(28, int(round(ui_pt * 3.2)))
        save_btn = QPushButton("Save as Text…")
        save_btn.setFont(ui_font)
        save_btn.setMinimumHeight(btn_h)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setToolTip("Download findings as a plain-text file")
        save_btn.setStyleSheet(
            f"QPushButton {{ padding: 7px 14px; border-radius: 6px;"
            f" font-size: {ui_fs}; }}"
        )
        save_btn.clicked.connect(self._save_as_text)

        close_btn = QPushButton("Close")
        close_btn.setFont(ui_font)
        close_btn.setMinimumHeight(btn_h)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setDefault(True)
        close_btn.setStyleSheet(
            f"QPushButton {{ padding: 7px 18px; border-radius: 6px;"
            f" font-size: {ui_fs}; }}"
        )
        close_btn.clicked.connect(self.reject)

        util_row = QHBoxLayout()
        util_row.setContentsMargins(0, 0, 0, 0)
        util_row.setSpacing(10)
        util_row.addWidget(save_btn)
        util_row.addStretch(1)
        util_row.addWidget(close_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("margin-top: 2px; margin-bottom: 2px;")

        footer = QVBoxLayout()
        footer.setContentsMargins(0, 4, 0, 0)
        footer.setSpacing(8)
        footer.addWidget(ai_label)
        footer.addLayout(ai_row)
        footer.addWidget(sep)
        footer.addLayout(util_row)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(12)
        lay.addWidget(note)
        lay.addWidget(list_w, 1)
        lay.addLayout(footer)

        # Ensure the dialog is at least as wide as the Ask-AI button row.
        footer_w = sum(b.minimumWidth() for b in ai_btns) + 10 * (len(ai_btns) - 1) + 48
        if self.minimumWidth() < footer_w:
            self.setMinimumWidth(footer_w)
        if self.width() < footer_w:
            self.resize(footer_w, self.height())

    def _query_with_ai(
        self, ai_enabled: bool, template_id: str = "findings",
        *, level: str = "",
    ) -> None:
        self.wants_ai_query = True
        self.wants_ai_template = template_id or "findings"
        self.wants_ai_finding_id = ""
        self.wants_ai_level = str(level or "")
        if template_id in ("verify", "auto_investigate", "explain_finding"):
            item = self._list_w.currentItem()
            if item is not None:
                self.wants_ai_finding_id = str(
                    item.data(Qt.ItemDataRole.UserRole) or "")
        self._ai_needs_settings = not ai_enabled
        self.accept()

    def _save_as_text(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Analysis Findings",
            "analysis-findings.txt",
            "Text files (*.txt);;All files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".txt"):
            path += ".txt"
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(_format_analysis_findings_text(
                    self._findings, self._scope_title))
        except OSError as exc:
            QMessageBox.warning(
                self, "Save failed", f"Could not write file:\n{exc}")


def _parse_task_deadlines_text(text: str) -> Dict[str, int]:
    """Parse a newline-separated 'TaskName=nanoseconds' text into a dict."""
    out: Dict[str, int] = {}
    for line in text.splitlines():
        t = line.strip()
        if not t or t.startswith("#"):
            continue
        eq = t.find("=")
        if eq <= 0:
            continue
        key = t[:eq].strip()
        try:
            val = int(t[eq + 1:].strip())
        except ValueError:
            continue
        if key and val > 0:
            out[key] = val
    return out


class _StatsPanel(QWidget):
    """Dock panel showing trace statistics (span, core utilisation, top tasks)."""

    task_clicked = Signal(str)   # merge key of the clicked task row
    segment_jump   = Signal(int)    # ns - scroll timeline to this timestamp
    plot_point_clicked = Signal(object, int, str)  # payload, mark_ns, note
    core_clicked = Signal(str)   # core name of the clicked core row
    # Core-Pair chart footer → open heatmap/chord focused on (from, to, bounce_only)
    open_pair_heatmap = Signal(str, str, bool)
    open_pair_chord = Signal(str, str, bool)
    # Open Settings dialog on a named sidebar page (e.g. "Display")
    open_settings_requested = Signal(str)
    # Pinned section IDs (stay expanded); persist to btf_viewer.rc
    section_pins_changed = Signal(list)
    # Section display order; persist to btf_viewer.rc
    section_order_changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ui_font_size: int = UI_FONT_SIZE
        self._is_dark: bool = True
        self._stats_item_delegate = _StatsItemDelegate(self)
        self._plot_dlg = None   # keep reference to prevent GC
        self._plot_mk: Optional[str] = None
        self._plot_kind: Optional[str] = None   # "exec", "block", "inter", "preempt", "interval", "tag", "tick"
        self._plot_preemptor: Optional[str] = None
        self._plot_interval_id: Optional[str] = None
        self._trace: Optional["BtfTrace"] = None
        self._export_scope_override: Optional[Tuple[int, int]] = None
        self._cursor_times: List[int] = []
        self._scope_to_cursors: bool = True
        self._section_collapsed: Dict[str, bool] = default_section_collapsed()
        self._section_pins: List[str] = []
        self._section_order: List[str] = normalize_stats_section_order(None)
        self._pending_sections: List[Tuple[str, str, str, object]] = []
        self._drop_target_sid: Optional[str] = None
        self._dragging_sid: Optional[str] = None
        self._section_headers: Dict[str, QPushButton] = {}
        self._section_header_rows: Dict[str, QWidget] = {}
        self._section_seps: Dict[str, QWidget] = {}
        self._section_pin_btns: Dict[str, _StatsPinButton] = {}
        self._section_bodies: Dict[str, QWidget] = {}
        self._section_populate: Dict[str, object] = {}
        self._section_drag_filters: List[_StatsSectionDragFilter] = []
        self._section_drag_filter_by_id: Dict[str, _StatsSectionDragFilter] = {}
        self._section_table_heights: Dict[str, int] = default_section_table_heights()
        self._table_grips: List[_StatsSectionGrip] = []
        self._util_label_col_natural: int = STATS_UTIL_LABEL_W
        self._util_label_col_w: int = STATS_UTIL_LABEL_W
        self._util_scroll_areas: List[QScrollArea] = []
        self._util_scroll_filters: List[_UtilScrollResizeFilter] = []
        self._defer_heavy_sections: bool = False
        self._defer_heavy_collapse_done: bool = False
        self._deferred_sections: List[str] = []
        self._defer_populate_timer = QTimer(self)
        self._defer_populate_timer.setSingleShot(True)
        self._defer_populate_timer.timeout.connect(self._populate_next_deferred_section)
        self._cpu_budget_pct: float = 0.0
        self._task_deadlines_ns: Dict[str, int] = {}
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        scope_block = QVBoxLayout()
        scope_block.setContentsMargins(8, 6, 8, 0)
        scope_block.setSpacing(4)
        scope_top = QHBoxLayout()
        scope_top.setSpacing(6)
        self._scope_cb = QCheckBox("Limit to C1–Cn")
        self._scope_cb.setChecked(True)
        self._scope_cb.setEnabled(False)
        self._scope_cb.setToolTip(
            "Limit statistics to the time window from C1 through the last cursor")
        self._scope_cb.toggled.connect(self._on_scope_toggled)
        _scope_pol = self._scope_cb.sizePolicy()
        _scope_pol.setHorizontalPolicy(QSizePolicy.Policy.MinimumExpanding)
        self._scope_cb.setSizePolicy(_scope_pol)
        self._scope_cb.setMinimumWidth(0)
        scope_top.addWidget(self._scope_cb, 1)
        self._btn_stats_expand = self._make_scope_action_button(
            _IC_SECTIONS_EXPAND, "Expand all statistics sections", self._expand_all_sections)
        scope_top.addWidget(self._btn_stats_expand, 0)
        self._btn_stats_collapse = self._make_scope_action_button(
            _IC_SECTIONS_COLLAPSE, "Collapse all statistics sections",
            self._collapse_all_sections)
        scope_top.addWidget(self._btn_stats_collapse, 0)
        self._btn_stats_reset_order = self._make_scope_action_button(
            _IC_SECTIONS_RESET_ORDER,
            "Reset statistics section order to default",
            self._reset_section_order)
        scope_top.addWidget(self._btn_stats_reset_order, 0)
        self._update_reset_order_button()
        scope_block.addLayout(scope_top)
        self._scope_label = QLabel("")
        self._scope_label.setStyleSheet("color:#888888;")
        self._scope_label.setWordWrap(True)
        self._scope_label.setMinimumWidth(0)
        scope_block.addWidget(self._scope_label)
        outer.addLayout(scope_block)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setMinimumWidth(0)
        self._scroll = scroll
        self._inner = QWidget()
        self._inner.setObjectName("stats_inner")
        self._inner.setMinimumWidth(0)
        self._ilay = QVBoxLayout(self._inner)
        self._ilay.setContentsMargins(8, 6, 8, 6)
        self._ilay.setSpacing(2)
        # Trailing pad so late sections can scroll up to the top of the viewport
        # (a layout stretch collapses when content is taller than the viewport).
        self._scroll_tail = QWidget()
        self._scroll_tail.setObjectName("stats_scroll_tail")
        self._scroll_tail.setMinimumHeight(0)
        self._ilay.addWidget(self._scroll_tail)
        scroll.setWidget(self._inner)
        outer.addWidget(scroll)
        self._main_viewport_filter = _StatsPanelViewportFilter(self)
        scroll.viewport().installEventFilter(self._main_viewport_filter)
        self._apply_panel_theme()

        exp_row = QVBoxLayout()
        exp_row.setContentsMargins(8, 6, 8, 8)
        exp_row.setSpacing(4)
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
        for btn in (self._btn_export_csv, self._btn_export_html, self._btn_compare_mig):
            btn.setMinimumWidth(0)
            btn.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        outer.addLayout(exp_row)
        self._sync_stats_panel_chrome_font()

    def _ui_fs(self) -> str:
        """CSS font-size token matching app menus/toolbar (_ui_font_stylesheet_size)."""
        return _ui_font_stylesheet_size(self._ui_font_size)

    def _sync_stats_panel_chrome_font(self) -> None:
        """Apply UI / menu font size to stats panel chrome (scope row, export buttons)."""
        ui_fs = self._ui_fs()
        font = _application_ui_font(self._ui_font_size)
        self._scope_cb.setFont(font)
        self._scope_label.setStyleSheet(f"color:#888888; font-size:{ui_fs};")
        for btn in (
            self._btn_stats_expand, self._btn_stats_collapse,
            self._btn_stats_reset_order,
            self._btn_export_csv, self._btn_export_html, self._btn_compare_mig,
        ):
            btn.setFont(font)

    def apply_ui_font_size(self, ui_font_size: int) -> None:
        """Re-layout stats content when UI / menu font size changes."""
        self._ui_font_size = int(ui_font_size)
        self._sync_stats_panel_chrome_font()
        if self._trace is not None:
            self.rebuild(self._trace)
        else:
            self._refresh_stats_table_themes()

    def _scope_action_icon_color(self) -> str:
        return "#9E9E9E" if self._is_dark else "#666666"

    def _make_scope_action_button(self, icon_path: str, tooltip: str,
                                  slot) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("stats_scope_action")
        btn.setIcon(_svg_icon(icon_path, self._scope_action_icon_color()))
        btn.setIconSize(QSize(14, 14))
        btn.setToolTip(tooltip)
        btn.setAutoRaise(True)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.setFixedSize(26, 26)
        pol = btn.sizePolicy()
        pol.setHorizontalPolicy(QSizePolicy.Policy.Fixed)
        pol.setVerticalPolicy(QSizePolicy.Policy.Fixed)
        btn.setSizePolicy(pol)
        btn.clicked.connect(slot)
        return btn

    def _pin_scope_action_buttons(self) -> None:
        for btn in (self._btn_stats_expand, self._btn_stats_collapse,
                    self._btn_stats_reset_order):
            btn.setFixedSize(26, 26)
            pol = btn.sizePolicy()
            pol.setHorizontalPolicy(QSizePolicy.Policy.Fixed)
            pol.setVerticalPolicy(QSizePolicy.Policy.Fixed)
            btn.setSizePolicy(pol)

    def _update_scope_action_icons(self) -> None:
        color = self._scope_action_icon_color()
        self._btn_stats_expand.setIcon(_svg_icon(_IC_SECTIONS_EXPAND, color))
        self._btn_stats_collapse.setIcon(_svg_icon(_IC_SECTIONS_COLLAPSE, color))
        self._update_reset_order_button()
        self._sync_pin_buttons()

    def _update_reset_order_button(self) -> None:
        custom = not is_default_stats_section_order(self._section_order)
        self._btn_stats_reset_order.setEnabled(custom)
        color = self._scope_action_icon_color() if custom else (
            "#555555" if self._is_dark else "#B0B0B0")
        self._btn_stats_reset_order.setIcon(
            _svg_icon(_IC_SECTIONS_RESET_ORDER, color))
        self._btn_stats_reset_order.setToolTip(
            "Reset statistics section order to default"
            if custom else
            "Section order is already the default")

    def _clear(self) -> None:
        self._defer_populate_timer.stop()
        self._deferred_sections.clear()
        self._defer_heavy_sections = False
        self._defer_heavy_collapse_done = False
        self._table_grips.clear()
        self._util_scroll_areas.clear()
        self._util_scroll_filters.clear()
        self._section_headers.clear()
        self._section_header_rows.clear()
        self._section_seps.clear()
        self._section_pin_btns.clear()
        self._section_bodies.clear()
        self._section_populate.clear()
        self._section_drag_filters.clear()
        self._section_drag_filter_by_id.clear()
        self._pending_sections.clear()
        self._drop_target_sid = None
        self._dragging_sid = None
        self._scroll_tail = None
        while self._ilay.count():
            item = self._ilay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def apply_section_table_heights(self, heights: Dict[str, int]) -> None:
        """Apply persisted max heights for collapsible stats tables."""
        for key, val in heights.items():
            if key in self._section_table_heights:
                h = int(val)
                # Older sessions saved cores height as util-rows only (gauges
                # lived outside the scroll). Bump those up so the default
                # viewport still shows gauges + two cores.
                if key == "cores" and h < STATS_LB_GAUGE_H:
                    h = STATS_CORES_UTIL_DEFAULT_H
                lo, hi = self._section_height_bounds(key)
                self._section_table_heights[key] = max(lo, min(hi, h))

    def section_table_heights(self) -> Dict[str, int]:
        return dict(self._section_table_heights)

    def section_pins(self) -> List[str]:
        return list(self._section_pins)

    def set_section_pins(self, pins, *, emit: bool = False) -> None:
        """Apply persisted pin list; pinned sections stay expanded."""
        self._section_pins = normalize_stats_pins(pins)
        pinned = set(self._section_pins)
        for sid in pinned:
            self._section_collapsed[sid] = False
            if sid in self._section_headers:
                self._set_section_collapsed(sid, False)
        self._sync_pin_buttons()
        if emit:
            self.section_pins_changed.emit(list(self._section_pins))

    def section_order(self) -> List[str]:
        return list(self._section_order)

    def set_section_order(self, order, *, emit: bool = False) -> None:
        """Apply persisted statistics section order."""
        self._section_order = normalize_stats_section_order(order)
        if self._section_header_rows:
            self._apply_section_layout_order()
        self._update_reset_order_button()
        if emit:
            self.section_order_changed.emit(list(self._section_order))

    def _sync_pin_buttons(self) -> None:
        pinned = set(self._section_pins)
        for sid, btn in self._section_pin_btns.items():
            btn.set_pinned(sid in pinned, dark=self._is_dark)


    def capture_layout_state(self) -> dict:
        """Return statistics panel layout/scope state for the MVVM layer."""
        return {
            "cursor_times": list(self._cursor_times),
            "scope_to_cursors": bool(self._scope_to_cursors),
            "export_scope_override": self._export_scope_override,
            "section_collapsed": dict(self._section_collapsed),
            "section_table_heights": dict(self._section_table_heights),
            "util_label_col_w": int(self._util_label_col_w),
        }

    def apply_layout_state(
        self, model, *, refresh_stats: bool = True,
    ) -> None:
        """Restore statistics panel layout/scope state from the MVVM layer."""
        self._section_table_heights.update(model.section_table_heights)
        self._util_label_col_w = model.util_label_col_w
        self._export_scope_override = model.export_scope_override
        self._scope_to_cursors = model.scope_to_cursors
        if hasattr(self, "_scope_cb"):
            self._scope_cb.blockSignals(True)
            self._scope_cb.setChecked(model.scope_to_cursors)
            self._scope_cb.blockSignals(False)
        for section_id, collapsed in model.section_collapsed.items():
            if section_id in self._section_headers:
                self._set_section_collapsed(section_id, collapsed)
        self.set_cursor_times(model.cursor_times, refresh_stats=refresh_stats)
        self.apply_section_table_heights(model.section_table_heights)

    @staticmethod
    def _section_height_bounds(section_id: str = "") -> Tuple[int, int]:
        """Return (min_h, max_h) for a stats section viewport."""
        if section_id == "cores":
            return STATS_CORES_UTIL_MIN_H, _StatsSectionGrip._MAX_H
        if section_id == "tasks":
            return STATS_UTIL_MIN_H, _StatsSectionGrip._MAX_H
        return _StatsSectionGrip._MIN_H, _StatsSectionGrip._MAX_H

    def _apply_table_display_height(self, table, h: int,
                                    *, section_id: str = "") -> int:
        """Set an explicit pixel height so drag-resize is visible (scroll inside)."""
        lo, hi = self._section_height_bounds(section_id)
        h = max(lo, min(hi, int(h)))
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        table.setMinimumHeight(h)
        table.setMaximumHeight(h)
        table.updateGeometry()
        host = table.parentWidget()
        if host is not None:
            host.updateGeometry()
        return h

    @staticmethod
    def _wire_stats_table_click_cursor(table: QTableWidget) -> None:
        """Pointing-hand over data cells; leave resize grips with their own cursor."""
        table.setMouseTracking(True)
        vp = table.viewport()
        vp.setMouseTracking(True)
        filt = _StatsTableBodyCursorFilter(table)
        vp.installEventFilter(filt)
        table._body_cursor_filter = filt  # prevent GC

    def _wire_stats_table_row_hover(self, table: QTableWidget) -> None:
        """Highlight every cell in the row under the mouse; restore colours on leave."""
        state = {"row": -1, "orig": []}

        def _clear_row_hover() -> None:
            row = state["row"]
            if row < 0:
                return
            for c, bg in enumerate(state["orig"]):
                item = table.item(row, c)
                if item is not None:
                    item.setBackground(bg)
            state["row"] = -1
            state["orig"] = []

        def _set_row_hover(row: int) -> None:
            if row < 0 or row == state["row"]:
                return
            _clear_row_hover()
            state["row"] = row
            state["orig"] = [
                table.item(row, c).background() if table.item(row, c) is not None else QBrush()
                for c in range(table.columnCount())
            ]
            # Recomputed on every hover (not captured once at wiring time) so
            # a theme toggle takes effect immediately without needing a
            # table rebuild/app restart.
            hover_bg = self._stats_table_hover_bg()
            for c in range(table.columnCount()):
                item = table.item(row, c)
                if item is not None:
                    item.setBackground(hover_bg)

        table.setMouseTracking(True)
        table.viewport().setMouseTracking(True)
        table.itemEntered.connect(
            lambda item: _set_row_hover(item.row()) if item is not None else None)
        hover_filter = _StatsTableHoverFilter(_clear_row_hover)
        table.viewport().installEventFilter(hover_filter)
        table._stats_row_hover_filter = hover_filter  # prevent GC

    def relax_content_width(self) -> None:
        """Let the dock shrink below a previously expanded content width."""
        _relax_widget_tree(self)
        if self._inner is not None:
            _relax_widget_tree(self._inner)
        self._pin_scope_action_buttons()
        for table in self.findChildren(QTableWidget):
            table.setMinimumWidth(0)
            hdr = table.horizontalHeader()
            if hdr.stretchLastSection():
                hdr.setStretchLastSection(False)
                table.resizeColumnsToContents()
            for c in range(table.columnCount()):
                hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)

    @staticmethod
    def _fix_stats_table_column_widths(table: QTableWidget) -> None:
        """Keep table columns content-sized so widening the dock does not latch min width."""
        if table.columnCount() <= 0:
            return
        hdr = table.horizontalHeader()
        hdr.setStretchLastSection(False)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setMinimumWidth(0)
        table.resizeColumnsToContents()
        for c in range(table.columnCount()):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)

    def _wrap_table_with_resizer(self, lay: QVBoxLayout, table: QTableWidget,
                                 section_id: str) -> None:
        """Add *table* plus a drag grip; height is stored in *_section_table_heights*."""
        self._fix_stats_table_column_widths(table)
        default_h = (STATS_TABLE_MIG_DEFAULT_H if section_id == "migrations"
                     else STATS_TABLE_DEFAULT_H)
        h = self._section_table_heights.get(section_id, default_h)
        h = self._apply_table_display_height(table, h, section_id=section_id)
        self._section_table_heights[section_id] = h

        grip = _StatsSectionGrip(self._is_dark, lambda: table.height())
        self._table_grips.append(grip)

        def _on_height(new_h: int) -> None:
            self._section_table_heights[section_id] = self._apply_table_display_height(
                table, new_h, section_id=section_id)

        grip.height_changed.connect(_on_height)
        lay.addWidget(table)
        lay.addWidget(grip)

    def _apply_panel_theme(self) -> None:
        """Keep stats scroll surfaces in sync (Windows native style ignores QSS)."""
        bg = QColor("#1E1E1E") if self._is_dark else QColor("#F5F5F5")
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
        for sep in self.findChildren(QFrame):
            if sep.objectName() == "stats_sep":
                self._style_stats_sep(sep)

    def _refresh_stats_table_themes(self) -> None:
        """Re-apply table colours without rebuilding the whole statistics panel."""
        ui_fs = self._ui_fs()
        for table in self.findChildren(QTableWidget):
            if table.objectName() == "stats_table":
                self._apply_stats_table_theme(table, ui_fs)
        for row in self.findChildren(_StatsHoverRow):
            row.update_theme(self._is_dark)
        # Update utilisation row name labels whose colour was set at creation time.
        fg = "#D4D4D4" if self._is_dark else "#1E1E1E"
        lbl_style = f"color:{fg}; background:transparent;"
        if ui_fs:
            lbl_style += f" font-size:{ui_fs};"
        for lbl in self.findChildren(_ElidedUtilLabel):
            lbl.setStyleSheet(lbl_style)

    def _stats_table_colors(self) -> Tuple[QColor, QColor, str, QColor]:
        """Theme colours for stats tables (match MainWindow._theme_tokens)."""
        if self._is_dark:
            return (
                QColor("#121212"), QColor("#D4D4D4"), "#9A9A9A", QColor("#2D2D2D"),
            )
        return QColor("#FFFFFF"), QColor("#1E1E1E"), "#666666", QColor("#E0E0E0")

    def _stats_table_hover_bg(self) -> QBrush:
        return QBrush(QColor("#3A3A50") if self._is_dark else QColor("#E0E0EC"))

    def _stats_table_qss(self, ui_fs: str, bg: str, fg: str, muted: str,
                         hdr_bg: str) -> str:
        """QSS for stats-panel tables.

        Deliberately does NOT set a `background` on `::item` — doing so makes
        Qt's style paint that flat colour for every cell regardless of the
        item's `Qt::BackgroundRole` brush, which silently defeats per-row
        hover highlighting (and any other per-item background, e.g. status
        colouring) set via `item.setBackground(...)` in Python. The item's
        own background brush (always set explicitly when cells are built)
        is what actually paints the base colour; only `color`/border/padding
        need to come from the stylesheet.
        """
        return (
            f"font-size:{ui_fs};"
            f"QTableWidget#stats_table{{background:{bg}; color:{fg}; border:none;}}"
            f"QWidget#stats_table_viewport{{background:{bg};}}"
            f"QTableWidget#stats_table::item{{color:{fg}; "
            f"border:none; padding:0px 3px;}}"
            # Extra trailing padding so the sort arrow sits beside the label
            # instead of over it (Qt draws the indicator on the section edge).
            f"QHeaderView#stats_table_header::section{{border:none; "
            f"background:{hdr_bg}; color:{muted}; padding:0px 10px 0px 3px;}}"
        )

    def _sync_stats_table_item_backgrounds(self, table: QTableWidget,
                                           default_bg: QBrush) -> None:
        """Keep per-cell brushes in sync after a theme change."""
        for r in range(table.rowCount()):
            for c in range(table.columnCount()):
                item = table.item(r, c)
                if item is not None:
                    item.setBackground(default_bg)

    def _apply_stats_table_theme(self, table: QTableWidget, ui_fs: str) -> QBrush:
        """Paint stats-table surfaces explicitly (required on Windows Qt)."""
        bg, fg, muted, hdr_bg = self._stats_table_colors()
        bg_name = bg.name()
        fg_name = fg.name()
        hdr_name = hdr_bg.name()
        table.setObjectName("stats_table")
        table.viewport().setObjectName("stats_table_viewport")
        table.setStyleSheet(
            self._stats_table_qss(ui_fs, bg_name, fg_name, muted, hdr_name))
        table.setItemDelegate(self._stats_item_delegate)
        table.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        table.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        for w in (table, table.viewport()):
            pal = w.palette()
            pal.setColor(QPalette.Window, bg)
            pal.setColor(QPalette.Base, bg)
            pal.setColor(QPalette.Text, fg)
            w.setPalette(pal)
            w.setAutoFillBackground(True)
        hdr = table.horizontalHeader()
        hdr.setObjectName("stats_table_header")
        hdr.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        hdr.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hp = hdr.palette()
        hp.setColor(QPalette.Window, hdr_bg)
        hp.setColor(QPalette.Button, hdr_bg)
        hp.setColor(QPalette.WindowText, QColor(muted))
        hdr.setPalette(hp)
        hdr.setAutoFillBackground(True)
        self._enforce_stats_table_row_geometry(table)
        default_bg = QBrush(bg)
        self._sync_stats_table_item_backgrounds(table, default_bg)
        return default_bg

    @staticmethod
    def _enforce_stats_table_row_geometry(table: QTableWidget) -> None:
        """Force compact header/body row heights on every stats table.

        ``QTableWidget(n, cols)`` allocates rows at the platform default height
        before ``setDefaultSectionSize`` runs; that API only affects *new*
        sections, so Windows ends up with taller rows in tables that never call
        ``setRowHeight``. Centralise the fix here for all themed stats tables.
        """
        vh = table.verticalHeader()
        # Minimum first: Qt clamps defaultSectionSize to the current minimum
        # (often ~19px from the style), which leaves Windows rows tall if
        # default is set while the style minimum is still in force.
        vh.setMinimumSectionSize(STATS_TABLE_ROW_H)
        vh.setDefaultSectionSize(STATS_TABLE_ROW_H)
        vh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        table.horizontalHeader().setFixedHeight(STATS_TABLE_HEADER_H)
        for r in range(table.rowCount()):
            table.setRowHeight(r, STATS_TABLE_ROW_H)

    def _compute_util_label_col_width(self, labels: List[str]) -> int:
        """Widest util label (capped); shared by core and task rows for bar alignment."""
        if not labels:
            return STATS_UTIL_LABEL_W
        fm = QFontMetrics(self.font())
        max_w = STATS_UTIL_LABEL_MIN_W
        for text in labels:
            max_w = max(max_w, fm.horizontalAdvance(text) + 6)
        return min(STATS_UTIL_LABEL_W, max_w)

    def _pin_main_inner_width(self) -> None:
        vw = self._scroll.viewport().width()
        if vw > 0:
            self._inner.setMaximumWidth(vw)
            self._inner.setMinimumWidth(0)

    def _util_row_budget_width(self) -> int:
        """Pixel width available for one util row (label + bar + %)."""
        budgets: List[int] = []
        for scroll in self._util_scroll_areas:
            vw = scroll.viewport().width()
            if vw > 0:
                budgets.append(vw)
        if budgets:
            return min(budgets)
        main_scroll = getattr(self, "_scroll", None)
        if main_scroll is not None:
            mvw = main_scroll.viewport().width()
            if mvw > 0:
                return max(0, mvw - 16)
        pw = self.width()
        if pw > 0:
            return max(0, pw - 16)
        return 0

    def _pin_util_scroll_widths(self) -> None:
        for filt in self._util_scroll_filters:
            filt.pin_inner_width()

    def _resolve_util_label_width(self, natural_w: int) -> int:
        """Fit the shared label column and bar into the current row budget."""
        budget = self._util_row_budget_width()
        if budget <= 0:
            return min(natural_w, STATS_UTIL_LABEL_W)
        overhead = STATS_UTIL_PCT_W + 6 * 2
        max_label = budget - overhead - STATS_UTIL_BAR_MIN_W
        max_label = max(STATS_UTIL_LABEL_MIN_W, max_label)
        return max(STATS_UTIL_LABEL_MIN_W,
                   min(natural_w, STATS_UTIL_LABEL_W, max_label))

    def sync_util_layout(self) -> None:
        """Reflow util rows after the stats dock / panel width changes."""
        self._pin_main_inner_width()
        self._pin_util_scroll_widths()
        self._sync_util_label_column_width()

    def _sync_util_label_column_width(self) -> None:
        col_w = self._resolve_util_label_width(self._util_label_col_natural)
        if col_w == self._util_label_col_w:
            return
        self._util_label_col_w = col_w
        for lbl in self.findChildren(_ElidedUtilLabel):
            lbl.set_column_width(col_w)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.sync_util_layout()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self.sync_util_layout)

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

    def _deadline_settings_link(self, ui_fs: str, *, configured: bool) -> QLabel:
        """Clickable Settings → Display link for deadline / CPU budget config."""
        lead = ("Edit thresholds in" if configured
                else "Configure deadline / CPU budget thresholds in")
        lbl = QLabel(
            f'<span style="color:#888888;">{lead} </span>'
            f'<a href="settings:display" style="color:#5B9BD5; text-decoration:none;">'
            f'Settings \u2192 Display</a>'
            f'<span style="color:#888888;"> (Analysis thresholds)</span>'
        )
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        lbl.setOpenExternalLinks(False)
        lbl.setWordWrap(True)
        lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        if ui_fs:
            lbl.setStyleSheet(f"font-size:{ui_fs}; background:transparent;")
        lbl.linkActivated.connect(
            lambda _href: self.open_settings_requested.emit("Display"))
        return lbl

    @staticmethod
    def _tick_mode_badge_style(is_dark: bool, is_tickless: bool, ui_fs: str) -> str:
        """TICK / TICKLESS badge colours (readable in dark and light themes)."""
        if is_tickless:
            fg, border = "#FFB74D", "#FFB74D"
            bg = "#3A2E15" if is_dark else "#FFF4E5"
        else:
            fg, border = "#64B5F6", "#64B5F6"
            bg = "#162336" if is_dark else "#E8F4FC"
        return (
            f"font-weight:bold; font-size:{ui_fs}; color:{fg};"
            f" border:1px solid {border}; background:{bg};"
            f" border-radius:3px; padding:0 4px;"
        )

    def _tick_dist_btn_colors(self) -> Tuple[str, str, str, str, str]:
        """(fg, icon, border, bg, hover_bg) for Tick Distribution button."""
        if self._is_dark:
            return "#FFCC80", "#FFB74D", "#FFB74D", "#3A2E15", "#4A3820"
        return "#BF360C", "#E65100", "#E65100", "#FFF4E5", "#FFE8CC"

    def _make_tick_dist_button(self, ui_fs: str) -> _IconTextButton:
        """Bar-chart button for tick-interval distribution (Trace Health)."""
        fg, icon, border, bg, hover_bg = self._tick_dist_btn_colors()
        btn = _IconTextButton(
            "Tick Distribution\u2026", _IC_TICK_DIST, icon,
            ui_fs=ui_fs, fg=fg, border=border, bg=bg, hover_bg=hover_bg,
        )
        btn.setToolTip("Open tick interval distribution chart")
        btn.clicked.connect(lambda: self._open_tick_dist_plot(self._trace))
        return btn

    @staticmethod
    def _html_export_util_css() -> str:
        """CSS for CPU utilisation bars in statistics HTML export."""
        return """
        .util-list { display: flex; flex-direction: column; gap: 4px; }
        .util-row {
            display: flex;
            align-items: center;
            gap: 8px;
            min-height: 18px;
        }
        .util-label {
            flex: 0 0 128px;
            max-width: 128px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            text-align: left;
            font-size: 13px;
            color: var(--ink);
        }
        .util-bar {
            flex: 1 1 auto;
            height: 8px;
            min-width: 24px;
            border-radius: 4px;
            background: var(--line);
            overflow: hidden;
        }
        .util-bar-fill {
            height: 100%;
            border-radius: 4px;
            background: #5FCF6F;
        }
        .util-row-task .util-bar-fill { background: #5B9BD5; }
        .util-pct {
            flex: 0 0 44px;
            text-align: left;
            font-size: 13px;
        }
        .util-pct-core { color: #77BB77; }
        .util-pct-task { color: #6AAADD; }
        """

    @staticmethod
    def _html_export_util_bar_row(label: str, pct: float, kind: str) -> str:
        """One label + progress bar + % row for HTML export."""
        pct_v = max(0.0, min(100.0, float(pct)))
        esc = html.escape(str(label), quote=True)
        row_cls = "util-row util-row-core" if kind == "core" else "util-row util-row-task"
        pct_cls = "util-pct util-pct-core" if kind == "core" else "util-pct util-pct-task"
        return (
            f'<div class="{row_cls}">'
            f'<span class="util-label">{esc}</span>'
            f'<div class="util-bar"><div class="util-bar-fill" '
            f'style="width:{pct_v:.1f}%"></div></div>'
            f'<span class="{pct_cls}">{pct_v:.1f}%</span>'
            f"</div>"
        )

    @classmethod
    def _html_export_util_section(cls, title: str, rows: list, kind: str) -> str:
        """Report card with utilisation bar rows (core or task)."""
        esc_title = html.escape(title, quote=True)
        if not rows:
            body = '<p class="empty">No data</p>'
        else:
            items = "".join(
                cls._html_export_util_bar_row(label, pct, kind)
                for label, pct in rows
            )
            body = f'<div class="util-list">{items}</div>'
        return f'<section class="report-card"><h2>{esc_title}</h2>{body}</section>'

    @staticmethod
    def _html_make_collapsible_sections(doc_html: str) -> Tuple[str, str]:
        """Wrap every ``<section class="report-card ...">`` block in ``<details>``
        so it can be collapsed/expanded, and build a table-of-contents nav
        linking to each one. Returns ``(nav_html, transformed_doc_html)``.
        """
        # Titles (prefix match, ignoring any appended scope suffix) expanded by default.
        default_expanded = (
            "Analysis Findings",
            "Statistics Notes",
            "Core Utilisation (excl. IDLE/TICK)",
            "Top Tasks by CPU (excl. IDLE/TICK)",
            "Trace Health (TICK)",
        )
        toc_entries: List[Tuple[str, str]] = []
        counter = 0

        def _wrap(m: "re.Match") -> str:
            nonlocal counter
            classes, inner = m.group(1), m.group(2)
            h2_m = re.search(r"<h2[^>]*>.*?</h2>", inner, re.S)
            if h2_m:
                title_html = h2_m.group(0)
                title_text = re.sub(r"<[^>]+>", "", title_html)
                rest = inner[h2_m.end():]
            else:
                title_html, title_text, rest = "<h2>Section</h2>", "Section", inner
            counter += 1
            sec_id = f"sec-{counter}"
            toc_entries.append((sec_id, title_text))
            open_attr = " open" if title_text.startswith(default_expanded) else ""
            return (
                f'<details class="{classes}" id="{sec_id}"{open_attr}>'
                f"<summary>{title_html}</summary>{rest}</details>"
            )

        new_doc = re.sub(
            r'<section class="(report-card[^"]*)">(.*?)</section>',
            _wrap, doc_html, flags=re.S,
        )
        if not toc_entries:
            return "", new_doc
        items = "".join(
            f'<li><a href="#{sec_id}">{title}</a></li>'
            for sec_id, title in toc_entries
        )
        nav = f'<nav class="report-toc"><h2>Table of Contents</h2><ul>{items}</ul></nav>'
        return nav, new_doc

    def _add_utilisation_row(self, blay: QVBoxLayout, ui_fs: str,
                             label: str, pct: float, *,
                             chunk_color: str, pct_color: str,
                             on_click=None, click_tip: str = "") -> None:
        """Add a core/task CPU bar row (progress bar + %), with hover highlight."""
        row = _StatsHoverRow(self._is_dark, on_click=on_click)
        row.setFixedHeight(STATS_UTIL_ROW_H)
        row.setMinimumWidth(0)
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        hlay = QHBoxLayout(row)
        hlay.setContentsMargins(0, 0, 0, 0)
        hlay.setSpacing(6)
        hlay.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        name_lbl = _ElidedUtilLabel(label, column_width=self._util_label_col_w)
        _fg = "#D4D4D4" if self._is_dark else "#1E1E1E"
        _style = f"color:{_fg}; background:transparent;"
        if ui_fs:
            _style += f" font-size:{ui_fs};"
        name_lbl.setStyleSheet(_style)
        if click_tip:
            name_lbl.setToolTip(click_tip)
        hlay.addWidget(name_lbl, 0)

        pbar = QProgressBar()
        pbar.setRange(0, 1000)
        pbar.setValue(int(round(max(0.0, min(100.0, pct)) * 10.0)))
        pbar.setTextVisible(False)
        pbar.setFixedHeight(STATS_UTIL_BAR_H)
        pbar.setMinimumWidth(0)
        pbar.setMaximumWidth(16777215)
        pbar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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
        pct_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hlay.addWidget(pct_lbl, 0)
        row.track_widget(name_lbl)
        row.track_widget(pct_lbl)
        hlay.setStretch(0, 0)
        hlay.setStretch(1, 1)
        hlay.setStretch(2, 0)

        blay.addWidget(row)

    def _wrap_util_rows_scroll(self, blay: QVBoxLayout, inner: QWidget,
                              row_count: int, section_id: str = "") -> None:
        """Scroll utilisation rows vertically.  When *section_id* is given a
        resize grip is added so the user can drag the section height."""
        inner.setMinimumWidth(0)
        inner.setMaximumWidth(16777215)
        inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Always use AsNeeded: Load Balance gauges inside the cores scroll make
        # content taller than row_count alone; extra cores scroll beneath.
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        max_vis = (STATS_CORES_DEFAULT_VISIBLE_ROWS if section_id == "cores"
                   else STATS_MAX_VISIBLE_ROWS)
        vis = min(max(row_count, 1), max_vis)
        scroll_h = (vis * STATS_UTIL_ROW_H
                    + max(0, vis - 1) * STATS_UTIL_ROW_GAP + 2)
        if section_id == "cores" and any(
                isinstance(ch, _LoadBalanceGaugeWidget)
                for ch in inner.findChildren(_LoadBalanceGaugeWidget)):
            scroll_h += STATS_LB_GAUGE_H
        if section_id:
            h = self._section_table_heights.get(section_id, scroll_h)
            self._section_table_heights[section_id] = self._apply_table_display_height(
                scroll, h, section_id=section_id)
        else:
            scroll.setFixedHeight(scroll_h)
            scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        filt = _UtilScrollResizeFilter(self, scroll, inner)
        scroll.viewport().installEventFilter(filt)
        self._util_scroll_filters.append(filt)
        self._util_scroll_areas.append(scroll)
        blay.addWidget(scroll)
        if section_id:
            lo, _hi = self._section_height_bounds(section_id)
            grip = _StatsSectionGrip(
                self._is_dark, lambda s=scroll: s.height(), min_h=lo)
            self._table_grips.append(grip)
            def _on_util_height(new_h: int, _scroll=scroll, _sid=section_id) -> None:
                self._section_table_heights[_sid] = self._apply_table_display_height(
                    _scroll, new_h, section_id=_sid)
            grip.height_changed.connect(_on_util_height)
            blay.addWidget(grip)
        QTimer.singleShot(0, filt.pin_inner_width)
        QTimer.singleShot(0, self.sync_util_layout)

    def rebuild_with_font(self, trace: "BtfTrace", ui_font_size: int) -> None:
        """Re-build using the given *ui_font_size* so labels pick it up."""
        self._ui_font_size = int(ui_font_size)
        self._sync_stats_panel_chrome_font()
        self.rebuild(trace)

    def set_analysis_settings(self, cpu_budget_pct: float, task_deadlines_ns: Dict[str, int]) -> None:
        """Update deadline/budget settings; rebuilds the stats panel if a trace is loaded."""
        changed = (self._cpu_budget_pct != cpu_budget_pct
                   or self._task_deadlines_ns != task_deadlines_ns)
        self._cpu_budget_pct = float(cpu_budget_pct)
        self._task_deadlines_ns = dict(task_deadlines_ns)
        if changed and self._trace is not None:
            self.rebuild(self._trace)

    def set_dark(self, is_dark: bool, *, refresh_tables: bool = True) -> None:
        self._is_dark = is_dark
        self._apply_panel_theme()
        self._update_scope_action_icons()
        for sid in self._section_headers:
            self._update_section_header_icon(sid)
        for grip in self._table_grips:
            grip.set_dark(is_dark)
        if refresh_tables:
            self._refresh_stats_table_themes()
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
        if self._export_scope_override is not None:
            lo, hi = self._export_scope_override
            if hi > lo:
                return lo, hi, 2
            return None
        if not self._scope_to_cursors or len(self._cursor_times) < 2 or self._trace is None:
            return None
        t_sorted = sorted(self._cursor_times)
        lo, hi = t_sorted[0], t_sorted[-1]
        if hi <= lo:
            return None
        return lo, hi, len(t_sorted)

    def _update_scope_header(self) -> None:
        if self._trace is None:
            self._scope_label.setText("")
            return
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
        if kind == "tick":
            times = list(trace.tick_sti_times)
            if lo is not None and hi is not None:
                times = [t for t in times if lo <= t <= hi]
            if len(times) < 2:
                return None
            pts = [
                (times[i], times[i] - times[i - 1], None)
                for i in range(1, len(times))
            ]
            title = f"Tick Interval Distribution{scope}"
            return title, pts, QColor("#64B5F6")
        if kind == "interval":
            iid = self._plot_interval_id or mk
            pts = _interval_plot_points(trace, iid, lo, hi)
            if not pts:
                return None
            title = f"Interval {iid} — Duration{scope}"
            color = QColor(_interval_color(iid))
            return title, pts, color
        if kind in ("tag", "tag_interval"):
            ch = mk
            if kind == "tag_interval":
                pts = _tag_interval_plot_points(trace, ch, lo, hi)
                if not pts:
                    return None
                title = f"{_tag_channel_label(ch)} — Interval{scope}"
            else:
                pts = _tag_plot_points(trace, ch, lo, hi)
                if not pts:
                    return None
                title = f"{_tag_channel_label(ch)} — Value{scope}"
            color = QColor(_tag_color(ch))
            return title, pts, color
        if kind == "priority":
            pts = _priority_plot_points(trace, mk, lo, hi)
            if not pts:
                return None
            raw = trace.task_repr.get(mk, mk)
            name = _task_display_name(raw)
            base = trace.task_base_priority.get(mk, pts[0][2].base_pri)
            peak = max(ep.peak_pri for _, _, ep in pts)
            title = f"{name} — Priority Boost (base {base}→peak {peak}){scope}"
            color = QColor("#F39C12")
            pts = [
                (x, y, ep,
                 QColor("#E74C3C" if ep.inversion_suspect else "#F39C12"))
                for x, y, ep in pts
            ]
            return title, pts, color
        if kind in ("mig_dwell", "mig_rate", "mig_gap"):
            raw = trace.task_repr.get(mk, mk)
            name = _task_display_name(raw)
            color = _task_color(raw)
            if kind == "mig_dwell":
                pts = _migration_dwell_plot_points(trace, mk, lo, hi)
                title = f"{name} — On-Core Dwell Time{scope}"
            elif kind == "mig_rate":
                pts = _migration_rate_plot_points(trace, mk, lo, hi)
                title = f"{name} — Time Between Migrations{scope}"
            else:
                pts = _migration_gap_plot_points(trace, mk, lo, hi)
                title = f"{name} — Post-Migration Gap{scope}"
            return title, pts, color
        if kind in ("pair_gap", "pair_rate"):
            pair = _parse_pair_plot_key(mk)
            if pair is None:
                return None
            fc, tc = pair
            migs = _pair_migrations(trace, fc, tc, lo, hi)
            if not migs:
                return None
            bounce_ns = trace.lock_bounce_migration_ns
            bounces = sum(1 for m in migs if m.ns in bounce_ns)
            bounce_pct = 100.0 * bounces / len(migs)
            avg_gap = sum(m.gap_ns for m in migs) // len(migs)
            hdr = (
                f"{fc} → {tc} · {len(migs)} migr · Bounce {bounce_pct:.1f}% · "
                f"Avg Gap {_format_time(avg_gap, trace.time_scale)}"
            )
            color = QColor(_core_color(fc))
            if kind == "pair_gap":
                pts = _pair_gap_plot_points(trace, fc, tc, lo, hi)
                title = f"{hdr} — Post-Migration Gap{scope}"
            else:
                pts = _pair_rate_plot_points(trace, fc, tc, lo, hi)
                title = f"{hdr} — Time Between Pair Migrations{scope}"
            if not pts:
                return None
            return title, pts, color
        if kind == "dispatch":
            segs = trace.seg_map_by_merge_key.get(mk, [])
            if not segs:
                return None
            raw = trace.task_repr.get(mk, mk)
            name = _task_display_name(raw)
            color = _task_color(raw)
            pts = _dispatch_latency_plot_points(trace, mk, lo, hi)
            if not pts:
                return None
            title = f"{name} — Dispatch Latency{scope}"
            return title, pts, color
        if kind == "switch_overhead":
            pts = _switch_overhead_plot_points(trace, mk, lo, hi)
            if not pts:
                return None
            title = f"{mk} — Kernel Switch Overhead{scope}"
            return title, pts, QColor(_core_color(mk))
        if kind == "concurrency":
            try:
                n_active = int(mk)
            except (TypeError, ValueError):
                return None
            pts = _concurrency_level_plot_points(trace, n_active, lo, hi)
            if not pts:
                return None
            title = f"{n_active} Active Cores — Interval Duration{scope}"
            return title, pts, QColor("#64B5F6")
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

    def _open_tag_plot(self, trace: "BtfTrace", channel: str) -> None:
        self._open_plot(trace, channel, "tag")

    def _open_priority_plot(self, trace: "BtfTrace", mk: str) -> None:
        self._open_plot(trace, mk, "priority")

    def _open_tick_dist_plot(self, trace: "BtfTrace") -> None:
        """Open a tick-interval distribution scatter+histogram plot."""
        self._open_plot(trace, "__tick_dist__", "tick")

    def capture_plot_session(
        self,
    ) -> Tuple[Optional[str], Optional[str], bool, Optional[str], Optional[str]]:
        """Return (mk, kind, visible, preemptor, interval_id) for the metrics plot dialog."""
        open_ = self._plot_dlg is not None and self._plot_dlg.isVisible()
        return (self._plot_mk, self._plot_kind, open_, self._plot_preemptor,
                self._plot_interval_id)

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
                             preemptor: Optional[str] = None,
                             interval_id: Optional[str] = None) -> None:
        """Re-open the metrics plot saved for a trace tab, if it was visible."""
        self.clear_plot_session()
        if not open_ or not kind or trace is None:
            return
        if kind == "tick":
            self._open_tick_dist_plot(trace)
            return
        if kind in ("tag", "tag_interval") and mk:
            self._open_plot(trace, mk, kind)
            return
        if kind == "interval" and mk:
            iid = interval_id or mk
            self._open_interval_plot(trace, iid)
            return
        if not mk:
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
        y_as_time = kind not in ("tag",)
        show_variability = kind in ("exec", "block", "inter", "dispatch", "switch_overhead")
        _on_click = self._on_plot_scatter_click
        if self._plot_dlg is not None:
            try:
                self._plot_dlg.closed.disconnect(self._on_plot_dialog_closed)
            except TypeError:
                pass
            self._plot_dlg.close()
        tabs = (_MIG_PLOT_TABS if kind.startswith("mig_")
                else _PAIR_PLOT_TABS if kind.startswith("pair_")
                else _TAG_PLOT_TABS if kind in ("tag", "tag_interval")
                else None)
        on_hm = on_ch = None
        if kind.startswith("pair_"):
            pair = _parse_pair_plot_key(mk)
            if pair is not None:
                fc, tc = pair
                prefer_bounce = self._pair_bounce_prefer(trace, fc, tc)
                on_hm = (lambda f=fc, t=tc, b=prefer_bounce:
                         self.open_pair_heatmap.emit(f, t, b))
                on_ch = (lambda f=fc, t=tc, b=prefer_bounce:
                         self.open_pair_chord.emit(f, t, b))
        self._plot_dlg = _MetricsPlotDialog(
            title, pts, trace.time_scale, color,
            on_point_click=_on_click,
            is_dark=self._is_dark,
            scope_scoped=scoped,
            scope_badge=badge,
            scope_detail=detail,
            y_as_time=y_as_time,
            show_variability=show_variability,
            tabs=tabs,
            active_tab=kind if tabs else None,
            on_tab_change=self._on_plot_tab_changed if tabs else None,
            on_open_heatmap=on_hm,
            on_open_chord=on_ch,
            parent=self.window(),
        )
        self._plot_dlg.closed.connect(self._on_plot_dialog_closed)
        self._plot_dlg.show()

    def _on_plot_tab_changed(self, new_kind: str) -> None:
        """Switch the open migration plot dialog to a different metric tab in place."""
        if (self._plot_dlg is None or self._trace is None
                or self._plot_mk is None or new_kind == self._plot_kind):
            return
        built = self._build_plot_points(self._trace, self._plot_mk, new_kind)
        if built is None or not built[1]:
            # Nothing to show: keep the previous tab highlighted.
            if self._plot_kind is not None:
                self._plot_dlg.set_active_tab(self._plot_kind)
            return
        title, pts, _color = built
        self._plot_kind = new_kind
        self._plot_dlg.set_active_tab(new_kind)
        scoped, badge, detail = self._plot_scope_banner()
        self._plot_dlg.update_data(title, pts, scope_scoped=scoped,
                                   scope_badge=badge, scope_detail=detail)

    def _pair_bounce_prefer(self, trace: "BtfTrace",
                            from_core: str, to_core: str) -> bool:
        """True when Bounce % is high enough to default Bounce Only on Heatmap/Chord."""
        rng = self._stats_range()
        lo = hi = None
        if rng is not None:
            lo, hi, _ = rng
        migs = _pair_migrations(trace, from_core, to_core, lo, hi)
        if len(migs) < _WF_PAIR_COUNT_MIN:
            return False
        bounce_ns = trace.lock_bounce_migration_ns
        pct = 100.0 * sum(1 for m in migs if m.ns in bounce_ns) / len(migs)
        return pct >= _WF_PAIR_BOUNCE_PCT

    def _open_pair_plot(self, trace: "BtfTrace",
                        from_core: str, to_core: str) -> None:
        """Open Gap/Rate distribution for a directed core pair."""
        self._open_plot(trace, _pair_plot_key(from_core, to_core), "pair_gap")

    def _on_plot_scatter_click(self, x_ns: int, y_ns: int, payload) -> None:
        """Scatter plot point: jump timeline and add an annotation (not a cursor)."""
        if self._trace is None:
            return
        if payload is None and self._plot_kind not in (
                "tick", "switch_overhead", "concurrency"):
            return
        note = _format_plot_point_note(
            self._trace, self._plot_kind or "", self._plot_mk,
            self._plot_preemptor, x_ns, y_ns, payload)
        mark_ns = _plot_point_mark_ns(payload, x_ns)
        self.plot_point_clicked.emit(payload, mark_ns, note)

    def _stats_sep_color(self) -> str:
        """Match web StatisticsPanel .stats-sep (var(--border))."""
        return "#3C3C3C" if self._is_dark else "#DDDDDD"

    def _style_stats_sep(self, frame: QFrame) -> None:
        c = self._stats_sep_color()
        frame.setStyleSheet(
            f"QFrame#stats_sep {{ background-color:{c}; border:none; "
            f"min-height:1px; max-height:1px; }}"
        )

    def _sep(self) -> QFrame:
        f = QFrame()
        f.setObjectName("stats_sep")
        f.setFrameShape(QFrame.NoFrame)
        f.setFixedHeight(1)
        f.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._style_stats_sep(f)
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
        hdr_row = self._section_header_rows.get(section_id)
        if populate is None or hdr_row is None:
            return
        body = QWidget()
        blay = QVBoxLayout(body)
        blay.setContentsMargins(0, 0, 0, 0)
        blay.setSpacing(2)
        populate(blay)
        idx = self._ilay.indexOf(hdr_row)
        self._ilay.insertWidget(idx + 1, body)
        self._section_bodies[section_id] = body
        filt = self._section_drag_filter_by_id.get(section_id)
        if filt is not None:
            body.setAcceptDrops(True)
            body.installEventFilter(filt)
        self._refresh_section_drag_chrome(section_id)

    def _schedule_deferred_section_populate(self) -> None:
        if self._deferred_sections:
            self._defer_populate_timer.start(0)

    def _populate_next_deferred_section(self) -> None:
        """Populate one deferred statistics section per event-loop turn."""
        while self._deferred_sections:
            section_id = self._deferred_sections.pop(0)
            if self._section_collapsed.get(section_id, False):
                continue
            if section_id in self._section_bodies:
                continue
            self._ensure_section_body(section_id)
            app = QApplication.instance()
            if app is not None:
                app.processEvents()
            break
        if self._deferred_sections:
            self._defer_populate_timer.start(0)

    def _set_section_collapsed(self, section_id: str, collapsed: bool) -> None:
        if collapsed and section_id in self._section_pins:
            collapsed = False
        self._section_collapsed[section_id] = collapsed
        if collapsed:
            body = self._section_bodies.get(section_id)
            if body is not None:
                body.setVisible(False)
        else:
            self._ensure_section_body(section_id)
        self._update_section_header_icon(section_id)

    def _ensure_scroll_tail(self) -> QWidget:
        """Trailing spacer that lets any section header scroll to the viewport top."""
        tail = getattr(self, "_scroll_tail", None)
        if tail is None:
            tail = QWidget()
            tail.setObjectName("stats_scroll_tail")
            tail.setMinimumHeight(0)
            self._ilay.addWidget(tail)
            self._scroll_tail = tail
        return tail

    def _update_scroll_tail_height(self) -> None:
        """Size the trailing pad to roughly one viewport so late sections can pin."""
        if not hasattr(self, "_scroll"):
            return
        tail = self._ensure_scroll_tail()
        vh = max(0, int(self._scroll.viewport().height()))
        # Leave a small strip so the header is not flush against the bottom chrome.
        tail.setFixedHeight(max(0, vh - 24))

    def scroll_section_into_view(self, section_id: str, *, margin: int = 8,
                                 prefer_top: bool = True) -> None:
        """Scroll so *section_id* is visible; prefer pinning its header near the top.

        Expanded tables are often taller than the viewport, so ``ensureWidgetVisible``
        on the header alone can leave the body clipped. Pinning the header near the
        top of the scroll area keeps the table content on screen for demos.
        A trailing viewport-sized pad is required so sections near the end of the
        list can actually reach the top (layout stretch alone collapses when the
        content is taller than the viewport).
        """
        row = self._section_header_rows.get(section_id)
        if row is None or not hasattr(self, "_scroll"):
            return
        body = self._section_bodies.get(section_id)
        self._update_scroll_tail_height()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        inner = self._inner
        if inner is not None:
            inner.adjustSize()
            inner.updateGeometry()
        if app is not None:
            app.processEvents()

        bar = self._scroll.verticalScrollBar()
        if prefer_top:
            # Map header top into the scrollable content coordinate system.
            origin = row.mapTo(inner, QPoint(0, 0))
            target = max(0, int(origin.y()) - max(0, int(margin)))
            bar.setValue(min(target, bar.maximum()))
            # If layout still settling, fall back to ensure-visible so the
            # header/body are at least on screen.
            vh = max(1, int(self._scroll.viewport().height()))
            top = int(bar.value())
            header_y = int(row.mapTo(inner, QPoint(0, 0)).y())
            if header_y < top or header_y > top + vh - 4:
                self._scroll.ensureWidgetVisible(row, 0, max(0, int(margin)))
                if body is not None and body.isVisible():
                    self._scroll.ensureWidgetVisible(
                        body, 0, max(0, int(margin)))
            return

        self._scroll.ensureWidgetVisible(row, 0, max(0, int(margin)))
        if body is not None and body.isVisible():
            self._scroll.ensureWidgetVisible(body, 0, max(0, int(margin)))

    def scroll_stats_to_top(self) -> None:
        """Scroll the statistics list to the top."""
        if not hasattr(self, "_scroll"):
            return
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.minimum())

    def _toggle_section(self, section_id: str) -> None:
        if section_id in self._section_pins:
            return
        self._set_section_collapsed(
            section_id, not self._section_collapsed.get(section_id, False))

    def _toggle_section_pin(self, section_id: str) -> None:
        pins = list(self._section_pins)
        if section_id in pins:
            pins = [p for p in pins if p != section_id]
        else:
            pins.append(section_id)
            self._set_section_collapsed(section_id, False)
        self._section_pins = normalize_stats_pins(pins)
        self._sync_pin_buttons()
        self.section_pins_changed.emit(list(self._section_pins))

    def _expand_all_sections(self) -> None:
        self._inner.setUpdatesEnabled(False)
        try:
            for key in self._section_headers:
                self._set_section_collapsed(key, False)
        finally:
            self._inner.setUpdatesEnabled(True)

    def _collapse_all_sections(self) -> None:
        self._inner.setUpdatesEnabled(False)
        try:
            pinned = set(self._section_pins)
            for key in self._section_headers:
                if key in pinned:
                    continue
                self._set_section_collapsed(key, True)
        finally:
            self._inner.setUpdatesEnabled(True)

    def _add_collapsible_section(self, section_id: str, title: str, ui_fs: str,
                               populate) -> None:
        """Queue a collapsible section; flushed in persisted order at rebuild end."""
        self._pending_sections.append((section_id, title, ui_fs, populate))

    def _flush_pending_sections(self) -> None:
        if not self._pending_sections:
            return
        pending = {
            sid: (title, ui_fs, pop)
            for sid, title, ui_fs, pop in self._pending_sections
        }
        order = [
            sid for sid in normalize_stats_section_order(self._section_order)
            if sid in pending
        ]
        for sid, _title, _ui_fs, _pop in self._pending_sections:
            if sid not in order:
                order.append(sid)
        self._pending_sections.clear()
        for sid in order:
            title, ui_fs, populate = pending[sid]
            self._mount_collapsible_section(sid, title, ui_fs, populate)

    def _mount_collapsible_section(self, section_id: str, title: str, ui_fs: str,
                                   populate) -> None:
        """Add a collapsible statistics section (parity with web StatisticsPanel)."""
        self._section_collapsed.setdefault(section_id, False)
        if section_id in self._section_pins:
            self._section_collapsed[section_id] = False
        sep = self._sep()
        self._ilay.addWidget(sep)
        self._section_seps[section_id] = sep
        collapsed = self._section_collapsed.get(section_id, False)
        row = QWidget()
        row.setObjectName("stats_section_header_row")
        row.setAcceptDrops(True)
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(2, 2, 2, 2)
        row_lay.setSpacing(2)
        grip = QLabel("⠿")
        grip.setObjectName("stats_section_grip")
        grip.setFixedWidth(14)
        grip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grip.setToolTip("Drag to reorder this section")
        grip.setStyleSheet(
            f"color:#888888; font-size:{ui_fs}; padding:0; border:none;"
            " background:transparent;")
        grip.setCursor(Qt.CursorShape.OpenHandCursor)
        hdr = QPushButton(title)
        hdr.setFlat(True)
        hdr.setCursor(Qt.CursorShape.PointingHandCursor)
        hdr.setIcon(_stats_chevron_icon(collapsed, self._is_dark))
        hdr.setIconSize(QSize(10, 10))
        hdr.setStyleSheet(
            f"text-align:left; padding:2px 0 2px 2px; border:none; background:transparent;"
            f" font-weight:bold; font-size:{ui_fs};"
        )
        hdr.clicked.connect(
            lambda _checked=False, sid=section_id: self._toggle_section(sid))
        pin = _StatsPinButton()
        pin.clicked.connect(
            lambda sid=section_id: self._toggle_section_pin(sid))
        row_lay.addWidget(grip, 0)
        row_lay.addWidget(hdr, 1)
        row_lay.addWidget(pin, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._ilay.addWidget(row)
        self._section_headers[section_id] = hdr
        self._section_header_rows[section_id] = row
        self._section_pin_btns[section_id] = pin
        self._section_populate[section_id] = populate
        filt = _StatsSectionDragFilter(self, section_id, grip)
        self._section_drag_filters.append(filt)
        self._section_drag_filter_by_id[section_id] = filt
        for w in (row, grip, hdr, pin):
            w.setAcceptDrops(True)
            w.installEventFilter(filt)
        self._sync_pin_buttons()
        if not collapsed:
            if (self._defer_heavy_sections
                    and section_id in STATS_HEAVY_SECTIONS):
                if section_id not in self._deferred_sections:
                    self._deferred_sections.append(section_id)
            else:
                self._ensure_section_body(section_id)

    def _begin_section_drag(self, section_id: str) -> None:
        self._dragging_sid = section_id
        self._set_section_drop_target(None)
        self._refresh_section_drag_chrome(section_id)

    def _end_section_drag(self) -> None:
        src = self._dragging_sid
        self._dragging_sid = None
        self._set_section_drop_target(None)
        if src:
            self._refresh_section_drag_chrome(src)

    def _set_section_drop_target(self, section_id: Optional[str]) -> None:
        """Highlight the drop destination (parity with web ``.drag-over``)."""
        if section_id and section_id == self._dragging_sid:
            section_id = None
        if self._drop_target_sid == section_id:
            return
        prev = self._drop_target_sid
        self._drop_target_sid = section_id
        if prev:
            self._refresh_section_drag_chrome(prev)
        if section_id:
            self._refresh_section_drag_chrome(section_id)

    def _refresh_section_drag_chrome(self, section_id: str) -> None:
        row = self._section_header_rows.get(section_id)
        body = self._section_bodies.get(section_id)
        if row is None and body is None:
            return
        is_src = section_id == self._dragging_sid
        is_dst = (section_id == self._drop_target_sid
                  and section_id != self._dragging_sid)
        accent = "#7EC8E3" if self._is_dark else "#2A6FB2"
        fill = ("rgba(126, 200, 227, 40)" if self._is_dark
                else "rgba(42, 111, 178, 35)")
        for w in (row, body):
            if w is None:
                continue
            if is_src:
                effect = QGraphicsOpacityEffect(w)
                effect.setOpacity(0.55)
                w.setGraphicsEffect(effect)
            else:
                w.setGraphicsEffect(None)
        if row is not None:
            if is_dst:
                row.setStyleSheet(
                    f"QWidget#stats_section_header_row {{"
                    f" border: 1px dashed {accent};"
                    f" border-radius: 4px;"
                    f" background-color: {fill};"
                    f" }}")
            else:
                row.setStyleSheet("")
        if body is not None:
            if is_dst:
                body.setStyleSheet(
                    f"QWidget {{"
                    f" border: 1px dashed {accent};"
                    f" border-radius: 4px;"
                    f" background-color: {fill};"
                    f" }}")
            else:
                body.setStyleSheet("")

    def _on_section_drop(self, src: str, dst: str) -> None:
        self._set_section_drop_target(None)
        if not src or not dst or src == dst:
            return
        new_order = move_stats_section(self._section_order, src, dst)
        if new_order == self._section_order:
            return
        self._section_order = new_order
        self._apply_section_layout_order()
        self._update_reset_order_button()
        self.section_order_changed.emit(list(self._section_order))

    def _reset_section_order(self) -> None:
        """Restore the built-in catalogue section order."""
        default = default_stats_section_order()
        if self._section_order == default:
            self._update_reset_order_button()
            return
        self._section_order = default
        self._apply_section_layout_order()
        self._update_reset_order_button()
        self.section_order_changed.emit(list(self._section_order))

    def _apply_section_layout_order(self) -> None:
        """Re-insert mounted section widgets (sep + header + body) in order."""
        mounted = [
            sid for sid in normalize_stats_section_order(self._section_order)
            if sid in self._section_header_rows
        ]
        for sid in self._section_header_rows:
            if sid not in mounted:
                mounted.append(sid)
        if not mounted:
            return
        widgets: List[QWidget] = []
        for sid in mounted:
            for w in (
                self._section_seps.get(sid),
                self._section_header_rows.get(sid),
                self._section_bodies.get(sid),
            ):
                if w is None:
                    continue
                self._ilay.removeWidget(w)
                widgets.append(w)
        stretch_idx = self._ilay.count()
        for i in range(self._ilay.count()):
            item = self._ilay.itemAt(i)
            if item is not None and item.spacerItem() is not None:
                stretch_idx = i
                break
        for i, w in enumerate(widgets):
            self._ilay.insertWidget(stretch_idx + i, w)

    def _core_util_rows(self, trace: "BtfTrace",
                        lo: Optional[int] = None, hi: Optional[int] = None) -> List[Tuple[str, float]]:
        return _core_util_pct_rows(trace, lo, hi)

    def _task_cpu_rows(self, trace: "BtfTrace", limit: int = 10,
                       lo: Optional[int] = None, hi: Optional[int] = None) -> List[Tuple[str, str, float]]:
        if lo is not None and hi is not None:
            total_ns = hi - lo
        else:
            total_ns = trace.time_max - trace.time_min
        if total_ns <= 0:
            return []
        task_times: Dict[str, int] = {}
        if lo is None and hi is None and trace.task_cpu_ns:
            task_times = dict(trace.task_cpu_ns)
        else:
            for mk, segs in trace.seg_map_by_merge_key.items():
                raw = trace.task_repr.get(mk, mk)
                _, _, tname = _parse_task_name(raw)
                if _is_idle_task_name(tname) or tname == "TICK":
                    continue
                if lo is not None and hi is not None:
                    task_times[mk] = sum(
                        _seg_overlap_ns(s, lo, hi)
                        for s in _task_segs_in_range(trace, mk, lo, hi)
                    )
                else:
                    task_times[mk] = sum(s.end - s.start for s in segs)

        rows: List[Tuple[str, str, float]] = []
        for mk, t_ns in sorted(task_times.items(), key=lambda kv: kv[1], reverse=True)[:limit]:
            if t_ns <= 0:
                continue
            raw = trace.task_repr.get(mk, mk)
            rows.append((mk, _task_display_name(raw), 100.0 * t_ns / total_ns))
        return rows

    def _summarize_samples(
        self, samples: List[int], scale: str
    ) -> Optional[Tuple[str, str, str, str, str, str]]:
        if not samples:
            return None
        vals = sorted(samples)
        n = len(vals)
        p95_idx = min(n - 1, math.ceil(n * 0.95) - 1)
        mean = sum(vals) / n
        avg = int(round(mean))
        jitter = vals[-1] - vals[0]
        stddev = int(round(math.sqrt(sum((v - mean) ** 2 for v in vals) / n)))
        return (
            _format_time(vals[0], scale),
            _format_time(avg, scale),
            _format_time(vals[-1], scale),
            _format_time(jitter, scale),
            _format_time(stddev, scale),
            _format_time(vals[p95_idx], scale),
        )

    def _summarize_samples_export(
        self, samples: List[int], scale: str
    ) -> Optional[Tuple[str, str, str, str, str, str, str, str]]:
        if not samples:
            return None
        vals = sorted(samples)
        n = len(vals)
        p50_idx = min(n - 1, math.ceil(n * 0.50) - 1)
        p95_idx = min(n - 1, math.ceil(n * 0.95) - 1)
        mean = sum(vals) / n
        avg = int(round(mean))
        trim_n = int(math.floor(n * 0.05))
        trim_vals = vals[trim_n:n - trim_n] if (2 * trim_n) < n else vals
        trim_avg = int(round(sum(trim_vals) / len(trim_vals)))
        jitter = vals[-1] - vals[0]
        stddev = int(round(math.sqrt(sum((v - mean) ** 2 for v in vals) / n)))
        return (
            _format_time(vals[0], scale),
            _format_time(avg, scale),
            _format_time(trim_avg, scale),
            _format_time(vals[-1], scale),
            _format_time(jitter, scale),
            _format_time(stddev, scale),
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
                         lo: Optional[int] = None,
                         hi: Optional[int] = None) -> List[tuple]:
        rows: List[tuple] = []
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
            mn, avg, mx, jitter, stddev, p95 = summary
            cpu_pct = 100.0 * sum(samples) / total_ns
            rows.append((
                mk, _task_display_name(raw), len(samples), cpu_pct,
                mn, avg, mx, jitter, stddev, p95,
            ))
        rows.sort(key=lambda r: (-r[3], -r[2], r[1].lower()))
        return rows

    def _inter_arrival_rows(self, trace: "BtfTrace",
                            lo: Optional[int] = None,
                            hi: Optional[int] = None) -> List[tuple]:
        rows: List[tuple] = []
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
            mn, avg, mx, jitter, stddev, p95 = summary
            if lo is not None and hi is not None:
                n_runs = sum(1 for s in segs if lo <= s.start <= hi)
            else:
                n_runs = len(segs)
            rows.append((
                mk, _task_display_name(raw), n_runs,
                mn, avg, mx, jitter, stddev, p95,
            ))
        rows.sort(key=lambda r: (-r[2], r[1].lower()))
        return rows

    def _blocking_time_rows(self, trace: "BtfTrace",
                            lo: Optional[int] = None, hi: Optional[int] = None
                            ) -> List[tuple]:
        rows: List[tuple] = []
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
            mn, avg, mx, jitter, stddev, p95 = summary
            rows.append((
                mk, _task_display_name(raw), len(samples),
                mn, avg, mx, jitter, stddev, p95,
            ))
        rows.sort(key=lambda r: (-r[2], r[1].lower()))
        return rows

    def _dispatch_latency_rows(self, trace: "BtfTrace",
                               lo: Optional[int] = None, hi: Optional[int] = None
                               ) -> List[tuple]:
        """Per-task dispatch latency (STI resume / create → next switch-in)."""
        rows: List[tuple] = []
        by_mk = _dispatch_latency_by_mk(trace, lo, hi)
        for mk, data in by_mk.items():
            raw = trace.task_repr.get(mk, mk)
            _, _, tname = _parse_task_name(raw)
            if _is_idle_task_name(tname) or tname == "TICK":
                continue
            summary = self._summarize_samples(data["samples"], trace.time_scale)
            if summary is None:
                continue
            mn, avg, mx, jitter, stddev, p95 = summary
            rows.append((
                mk, _task_display_name(raw), len(data["samples"]),
                mn, avg, mx, jitter, stddev, p95,
                data.get("min_seg"), data.get("max_seg"),
            ))
        rows.sort(key=lambda r: (-r[2], r[1].lower()))
        return rows

    def _on_dispatch_extreme_click(self, trace: "BtfTrace", mk: str,
                                   lo, hi, find_max: bool) -> None:
        by_mk = _dispatch_latency_by_mk(trace, lo, hi)
        data = by_mk.get(mk)
        if not data:
            return
        seg = data["max_seg"] if find_max else data["min_seg"]
        lat_ns = data["max_ns"] if find_max else data["min_ns"]
        if seg is None or lat_ns is None:
            return
        kind = "max dispatch latency" if find_max else "min dispatch latency"
        note = (
            f"{_task_display_name(trace.task_repr.get(mk, mk))} — {kind} "
            f"({_format_time(lat_ns, trace.time_scale)} ready→run)"
        )
        self.plot_point_clicked.emit(seg, seg.start, note)

    def _blocking_time_rows_export(self, trace: "BtfTrace",
                                   lo: Optional[int] = None, hi: Optional[int] = None
                                   ) -> List[tuple]:
        rows: List[tuple] = []
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
            mn, avg, tmean, mx, jitter, stddev, p50, p95 = summary
            rows.append((
                mk, _task_display_name(raw), len(samples),
                mn, avg, tmean, mx, jitter, stddev, p50, p95,
            ))
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
                                lo: Optional[int] = None,
                                hi: Optional[int] = None) -> List[tuple]:
        rows: List[tuple] = []
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
            mn, avg, tmean, mx, jitter, stddev, p50, p95 = summary
            cpu_pct = 100.0 * sum(samples) / total_ns
            rows.append((
                mk, _task_display_name(raw), len(samples), cpu_pct,
                mn, avg, tmean, mx, jitter, stddev, p50, p95,
            ))
        rows.sort(key=lambda r: (-r[3], -r[2], r[1].lower()))
        return rows

    def _inter_arrival_rows_export(self, trace: "BtfTrace",
                                   lo: Optional[int] = None,
                                   hi: Optional[int] = None) -> List[tuple]:
        rows: List[tuple] = []
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
            mn, avg, tmean, mx, jitter, stddev, p50, p95 = summary
            if lo is not None and hi is not None:
                n_runs = sum(1 for s in segs if lo <= s.start <= hi)
            else:
                n_runs = len(segs)
            rows.append((
                mk, _task_display_name(raw), n_runs,
                mn, avg, tmean, mx, jitter, stddev, p50, p95,
            ))
        rows.sort(key=lambda r: (-r[2], r[1].lower()))
        return rows

    def _build_stats_table(self, rows: List[tuple], ui_fs: str, empty_hint: str,
                           include_cpu: bool = False,
                           count_header: str = "Runs",
                           section_id: str = "exec",
                           include_variability: bool = False,
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
            headers = ["Task", "Migr", "Rate", "Dwell", "Cores", "Primary", "Ping", "STI±",
                       "Gap after", "Gap other"]
            cols = len(headers)
        elif include_variability:
            headers = (
                ["Task", count_header, "CPU%", "Min", "Avg", "Max",
                 "Jitter", "σ", "p95"]
                if include_cpu
                else ["Task", count_header, "Min", "Avg", "Max",
                      "Jitter", "σ", "p95"]
            )
            cols = len(headers)
        else:
            cols = 7 if include_cpu else 6
            headers = (["Task", count_header, "CPU%", "Min", "Avg", "Max", "p95"]
                       if include_cpu
                       else ["Task", count_header, "Min", "Avg", "Max", "p95"])
        table = QTableWidget(len(rows), cols)
        if migrations:
            _mig_header_tips = [
                "Task display name",
                "Migration count in the current statistics scope",
                "Migrations per second of on-CPU time; /tick = per on-CPU scheduler tick",
                "Average on-CPU slice duration before block, yield, or migration",
                "Distinct cores used in scope",
                "Core with the most active time in scope (share %)",
                "Ping-pong migrations (A→B→A within 1 µs)",
                "Migrations with an STI event within ±500 ns",
                "Average off-CPU gap immediately after a migration",
                "Average blocking gap elsewhere for this task",
            ]
            for ci, (hdr, tip) in enumerate(zip(headers, _mig_header_tips)):
                item = QTableWidgetItem(hdr)
                item.setToolTip(tip)
                table.setHorizontalHeaderItem(ci, item)
        elif include_variability:
            _metric_header_tips = {
                "Jitter": "Observed range: maximum minus minimum sample duration",
                "σ": "Population standard deviation of sample durations in scope",
            }
            for ci, hdr in enumerate(headers):
                item = QTableWidgetItem(hdr)
                tip = _metric_header_tips.get(hdr)
                if tip:
                    item.setToolTip(tip)
                table.setHorizontalHeaderItem(ci, item)
        else:
            table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(migrations)
        table.setShowGrid(False)
        table.setFrameShape(QFrame.NoFrame)
        table.verticalHeader().setDefaultSectionSize(STATS_TABLE_ROW_H)
        table.verticalHeader().setMinimumSectionSize(STATS_TABLE_ROW_H)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        table.horizontalHeader().setFixedHeight(18)
        table.horizontalHeader().setSectionsClickable(True)
        table.horizontalHeader().setSortIndicatorShown(True)
        if migrations:
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _default_bg = self._apply_stats_table_theme(table, ui_fs)

        _min_col = 3 if include_cpu else 2
        _max_col = 5 if include_cpu else 4
        _link_color = QBrush(QColor("#88AAFF"))
        _hovered_row = [-1]
        _interactive = bool(on_row_click or on_min_click or on_max_click)
        _row_tip = "Click to view distribution chart"
        _metric_key = (_tag_value_sort_key if section_id == "tags"
                       else _time_label_sort_key)

        def _clear_row_hover() -> None:
            row = _hovered_row[0]
            if row < 0:
                return
            bg = QBrush(self._stats_table_colors()[0])
            for c in range(cols):
                item = table.item(row, c)
                if item is not None:
                    item.setBackground(bg)
            _hovered_row[0] = -1

        def _set_row_hover(row: int) -> None:
            if row < 0:
                return
            if row == _hovered_row[0]:
                return
            _clear_row_hover()
            _hovered_row[0] = row
            hover = self._stats_table_hover_bg()
            for c in range(cols):
                item = table.item(row, c)
                if item is not None:
                    item.setBackground(hover)

        for r, row in enumerate(rows):
            if migrations:
                mk, name, n_mig, n_cores, _cores, primary, primary_pct, ping, sti, g_after, g_other, migr_rate, _rate_per_s, avg_dwell, _avg_dwell_tu = row
                vals = [
                    name, str(n_mig), migr_rate, avg_dwell, str(n_cores),
                    f"{primary} ({primary_pct:.0f}%)",
                    str(ping), str(sti), g_after, g_other,
                ]
                sort_keys = [
                    name.lower(), n_mig, _rate_per_s, _avg_dwell_tu, n_cores, primary_pct,
                    ping, sti,
                    _time_label_sort_key(g_after), _time_label_sort_key(g_other),
                ]
            elif include_cpu and include_variability:
                mk_r, name, runs, cpu, mn, avg, mx, jitter, stddev, p95 = row
                vals = [
                    name, runs, f"{cpu:.1f}%", mn, avg, mx,
                    jitter, stddev, p95,
                ]
                sort_keys = [
                    name.lower(), runs, cpu,
                    _time_label_sort_key(mn), _time_label_sort_key(avg),
                    _time_label_sort_key(mx), _time_label_sort_key(jitter),
                    _time_label_sort_key(stddev), _time_label_sort_key(p95),
                ]
            elif include_cpu:
                mk_r, name, runs, cpu, mn, avg, mx, p95 = row
                vals = [name, runs, f"{cpu:.1f}%", mn, avg, mx, p95]
                sort_keys = [
                    name.lower(), runs, cpu,
                    _time_label_sort_key(mn), _time_label_sort_key(avg),
                    _time_label_sort_key(mx), _time_label_sort_key(p95),
                ]
            elif section_id == "tags" and len(row) >= 11:
                mk_r, name, runs, mn, avg, mx, p95 = row[:7]
                mn_raw, avg_raw, mx_raw, p95_raw = row[7:11]
                vals = [name, runs, mn, avg, mx, p95]
                sort_keys = [name.lower(), runs, mn_raw, avg_raw, mx_raw, p95_raw]
            elif include_variability:
                mk_r, name, runs, mn, avg, mx, jitter, stddev, p95 = row
                vals = [name, runs, mn, avg, mx, jitter, stddev, p95]
                sort_keys = [
                    name.lower(), runs,
                    _metric_key(mn), _metric_key(avg), _metric_key(mx),
                    _metric_key(jitter), _metric_key(stddev), _metric_key(p95),
                ]
            else:
                mk_r, name, runs, mn, avg, mx, p95 = row
                vals = [name, runs, mn, avg, mx, p95]
                sort_keys = [
                    name.lower(), runs,
                    _metric_key(mn), _metric_key(avg),
                    _metric_key(mx), _metric_key(p95),
                ]

            for c, v in enumerate(vals):
                item = _StatsSortItem(v, sort_keys[c])
                item.setBackground(_default_bg)
                if migrations:
                    if c == 0:
                        item.setData(Qt.ItemDataRole.UserRole, mk)
                        if on_row_click is not None:
                            item.setToolTip(
                                f"Click to view migration dwell/rate/gap distribution for {name}")
                elif c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, mk_r)
                    tip = (f"{_row_tip} for {name}"
                           if on_row_click is not None else str(name))
                    item.setToolTip(tip)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if not migrations:
                    if c == _min_col and on_min_click is not None:
                        tip_kind = ("slice" if include_cpu
                                    else "sample" if section_id == "tags"
                                    else "gap" if section_id == "block"
                                    else "inter-arrival" if section_id == "inter"
                                    else "sample")
                        item.setToolTip(
                            f"Click to jump to shortest {tip_kind} for {name}")
                        item.setForeground(_link_color)
                    elif c == _max_col and on_max_click is not None:
                        if include_cpu:
                            item.setToolTip(
                                f"Click to jump to longest slice (WCET) for {name}")
                        elif section_id == "block":
                            item.setToolTip(
                                f"Click to jump to longest off-CPU gap for {name}")
                        elif section_id == "inter":
                            item.setToolTip(
                                f"Click to jump to longest inter-arrival for {name}")
                        else:
                            item.setToolTip(
                                f"Click to jump to longest sample for {name}")
                        item.setForeground(_link_color)
                    elif on_row_click is not None:
                        item.setToolTip(f"{_row_tip} for {name}")
                table.setItem(r, c, item)

        if not migrations:
            table.resizeColumnsToContents()
            table.horizontalHeader().setStretchLastSection(False)
            p95_col = cols - 1
            table.setColumnWidth(p95_col, min(table.columnWidth(p95_col), 76))
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setAlternatingRowColors(False)
        table.setShowGrid(False)

        # Row hover for every stats table (click handlers stay interactive-only).
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

        if _interactive:
            if migrations:
                def _cell_clicked_mig(_row: int, _col: int) -> None:
                    item = table.item(_row, 0)
                    if item is not None and on_row_click is not None:
                        on_row_click(item.data(Qt.ItemDataRole.UserRole))
                table.cellClicked.connect(_cell_clicked_mig)
            else:
                def _cell_clicked(r: int, c: int) -> None:
                    item = table.item(r, 0)
                    if item is None:
                        return
                    mk = item.data(Qt.ItemDataRole.UserRole)
                    if mk is None:
                        return
                    if on_min_click is not None and c == _min_col:
                        on_min_click(mk)
                    elif on_max_click is not None and c == _max_col:
                        on_max_click(mk)
                    elif on_row_click is not None:
                        on_row_click(mk)
                table.cellClicked.connect(_cell_clicked)
            self._wire_stats_table_click_cursor(table)

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
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.setShowGrid(False)
        table.setFrameShape(QFrame.NoFrame)
        table.verticalHeader().setDefaultSectionSize(STATS_TABLE_ROW_H)
        table.verticalHeader().setMinimumSectionSize(STATS_TABLE_ROW_H)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        table.horizontalHeader().setFixedHeight(18)
        table.horizontalHeader().setSectionsClickable(True)
        table.horizontalHeader().setSortIndicatorShown(True)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        _default_bg = self._apply_stats_table_theme(table, ui_fs)
        _hovered_row = [-1]

        def _clear_hover() -> None:
            row = _hovered_row[0]
            if row < 0:
                return
            bg = QBrush(self._stats_table_colors()[0])
            for c in range(cols):
                item = table.item(row, c)
                if item is not None:
                    item.setBackground(bg)
            _hovered_row[0] = -1

        def _set_hover(row: int) -> None:
            if row == _hovered_row[0]:
                return
            _clear_hover()
            _hovered_row[0] = row
            hover = self._stats_table_hover_bg()
            for c in range(cols):
                item = table.item(row, c)
                if item is not None:
                    item.setBackground(hover)

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
                    item.setData(Qt.ItemDataRole.UserRole, mk)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    item.setToolTip("Click to view preemption distribution chart")
                elif c == 1:
                    item.setData(Qt.ItemDataRole.UserRole, preemptor)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    item.setToolTip("Click to view preemption distribution chart")
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(r, c, item)

        table.setAlternatingRowColors(False)
        table.setWordWrap(False)
        for r in range(table.rowCount()):
            table.setRowHeight(r, STATS_TABLE_ROW_H)
        table.setSortingEnabled(True)

        table.setMouseTracking(True)
        table.viewport().setMouseTracking(True)
        table.cellEntered.connect(_set_hover)
        _hover_filter = _StatsTableHoverFilter(_clear_hover)
        table.viewport().installEventFilter(_hover_filter)
        host._preempt_hover_filter = _hover_filter

        if on_row_click is not None:
            def _cell_clicked(row: int, _col: int) -> None:
                mk_item = table.item(row, 0)
                pre_item = table.item(row, 1)
                if mk_item is not None and pre_item is not None:
                    preemptor = pre_item.data(Qt.ItemDataRole.UserRole)
                    if preemptor is not None:
                        on_row_click(mk_item.data(Qt.ItemDataRole.UserRole), preemptor)
            table.cellClicked.connect(_cell_clicked)
            self._wire_stats_table_click_cursor(table)

        self._wrap_table_with_resizer(lay, table, "preemption")
        return host

    def _append_exec_anomaly_findings(
        self,
        findings: List[dict],
        trace: "BtfTrace",
        lo: Optional[int],
        hi: Optional[int],
    ) -> List[dict]:
        """Append WCET Max/Avg spike anomalies using numeric slice samples."""
        spike_rows = []
        for mk, segs in (getattr(trace, "seg_map_by_merge_key", None) or {}).items():
            if not segs:
                continue
            raw = trace.task_repr.get(mk, mk)
            _, _, tname = _parse_task_name(raw)
            if _is_idle_task_name(tname) or tname == "TICK":
                continue
            samples = self._exec_slice_samples(segs, lo, hi)
            if len(samples) < 5:
                continue
            avg_ns = sum(samples) / len(samples)
            spike_rows.append((
                _task_display_name(raw), avg_ns, float(max(samples)), len(samples),
            ))
        append_wcet_anomaly_finding(
            findings, spike_rows, ratio_threshold=_WF_WCET_MAX_AVG_RATIO)
        return enrich_findings_with_ids(findings)

    def build_analysis_findings(self) -> Tuple[List[dict], str]:
        """Return (findings, scope_title) for the toolbar Analysis dialog."""
        trace = self._trace
        if trace is None:
            return [], ""
        rng = self._stats_range()
        lo = hi = None
        if rng is not None:
            lo, hi, _n_cur = rng
            scope_title = f" (cursor range C1–C{_n_cur})"
        else:
            scope_title = ""
        core_rows = self._core_util_rows(trace, lo, hi)
        exec_rows = self._exec_slice_rows_export(trace, lo, hi)
        block_rows = self._blocking_time_rows_export(trace, lo, hi)
        mig_rows = _migration_rows(trace, lo, hi)
        pair_rows = _core_pair_rows(trace, lo, hi)
        priority_rows = _priority_stats_rows(trace, lo, hi)
        sync_rows = _sync_object_stats_rows(trace, lo, hi)
        sync_issues = [
            i for i in trace.sync_issues
            if _sync_in_scope(i["time_ns"], lo, hi)
        ] if trace.has_sync_object_instrumentation else []
        tick = _tick_health_report(trace, lo, hi)
        dl_viols = None
        if self._cpu_budget_pct > 0 or self._task_deadlines_ns:
            dl_viols = _deadline_violations(
                trace, self._cpu_budget_pct, self._task_deadlines_ns, lo, hi)
        findings = _build_workflow_analysis_findings(
            core_rows=core_rows,
            exec_rows=exec_rows,
            block_rows=block_rows,
            mig_rows=mig_rows,
            pair_rows=pair_rows,
            priority_rows=priority_rows,
            sync_rows=sync_rows,
            sync_issues=sync_issues,
            tick=tick,
            deadline_viols=dl_viols,
            time_scale=trace.time_scale,
        )
        findings = self._append_exec_anomaly_findings(findings, trace, lo, hi)
        return findings, scope_title

    def write_statistics_html_report(self, path: str) -> None:
        trace = self._trace
        if trace is None:
            raise ValueError("no trace loaded")

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
        tag_rows = _tag_stats_rows(trace, lo, hi)
        priority_rows = _priority_stats_rows(trace, lo, hi)
        priority_eps = _priority_episode_detail_rows(trace, lo, hi)
        sync_rows = _sync_object_stats_rows(trace, lo, hi)
        sync_issues_scoped = [
            i for i in trace.sync_issues
            if _sync_in_scope(i["time_ns"], lo, hi)
        ] if trace.has_sync_object_instrumentation else []
        sync_holds = _sync_object_hold_detail_rows(trace, lo, hi)
        interval_inst = _interval_instance_detail_rows(trace, lo, hi)
        tag_samples = _tag_sample_detail_rows(trace, lo, hi)
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
                                rows: List[tuple]) -> str:
            body = "".join(
                f"<tr><td>{_esc(name)}</td><td>{runs}</td><td>{_esc(mn)}</td>"
                f"<td>{_esc(avg)}</td><td>{_esc(tmean)}</td><td>{_esc(mx)}</td>"
                f"<td>{_esc(jitter)}</td><td>{_esc(stddev)}</td>"
                f"<td>{_esc(p50)}</td><td>{_esc(p95)}</td></tr>"
                for (mk_r, name, runs, mn, avg, tmean, mx,
                     jitter, stddev, p50, p95) in rows
            ) or '<tr><td colspan="10" class="empty">No data</td></tr>'
            return (
                f"<section class=\"report-card\"><h2>{_esc(title)}</h2>"
                "<table><thead><tr><th>Task</th><th>Runs</th><th>Min</th>"
                "<th>Avg</th><th>TrimMean(5%)</th><th>Max</th>"
                "<th>Jitter</th><th>σ</th><th>p50</th><th>p95</th></tr></thead>"
                f"<tbody>{body}</tbody></table></section>"
            )

        def _render_exec_table(rows: List[tuple]) -> str:
            body = "".join(
                f"<tr><td>{_esc(name)}</td><td>{runs}</td><td>{cpu:.1f}%</td>"
                f"<td>{_esc(mn)}</td><td>{_esc(avg)}</td><td>{_esc(tmean)}</td>"
                f"<td>{_esc(mx)}</td><td>{_esc(jitter)}</td><td>{_esc(stddev)}</td>"
                f"<td>{_esc(p50)}</td><td>{_esc(p95)}</td></tr>"
                for (mk_r, name, runs, cpu, mn, avg, tmean, mx,
                     jitter, stddev, p50, p95) in rows
            ) or '<tr><td colspan="11" class="empty">No data</td></tr>'
            return (
                f"<section class=\"report-card\"><h2>Execution Time Per Slice{_esc(scope_title)}</h2>"
                "<table><thead><tr><th>Task</th><th>Runs</th><th>CPU%</th>"
                "<th>Min</th><th>Avg</th><th>TrimMean(5%)</th><th>Max</th>"
                "<th>Jitter</th><th>σ</th><th>p50</th><th>p95</th></tr></thead>"
                f"<tbody>{body}</tbody></table></section>"
            )

        _core_util_pcts = [pct for _, pct in core_rows]
        _lb_badge_html = ""
        _lb = _load_balance_metrics(_core_util_pcts)
        if _lb is not None:
            _lb_badge_html = _load_balance_gauge_img_html(_lb, width=300)
        core_util_html = (
            self._html_export_util_section(
                f"Core Utilisation (excl. IDLE/TICK){scope_title}",
                [(core, pct) for core, pct in core_rows],
                "core",
            ).replace("<div class=\"util-list\">", _lb_badge_html + "<div class=\"util-list\">", 1)
        )
        task_util_html = self._html_export_util_section(
            f"Top Tasks by CPU (excl. IDLE/TICK){scope_title}",
            [(name, pct) for _, name, pct in task_rows],
            "task",
        )

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
        <tr><td>Mode</td><td>{'TICKLESS' if tick['is_tickless'] else 'TICK'}</td></tr>
        <tr><td>Interval CV</td><td>{tick['tick_cv'] * 100.0:.2f}%</td></tr>
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

        def _sev_class(severity: str) -> str:
            if severity == "error":
                return "sev-error"
            if severity == "warning":
                return "sev-warning"
            return ""

        priority_html = ""
        if trace.has_priority_instrumentation:
            pri_body = "".join(
                f"<tr><td>{_esc(r[1])}</td><td>{r[2]}</td><td>{r[3]}</td><td>{r[4]}</td>"
                f"<td>{_esc(r[5])}</td><td>{_esc(r[6])}</td></tr>"
                for r in priority_rows
            ) or '<tr><td colspan="6" class="empty">No priority boosts in scope</td></tr>'
            ep_body = "".join(
                f"<tr><td>{_esc(ep['task'])}</td><td>{_esc(ep['pri'])}</td>"
                f"<td>{_esc(ep['start'])}</td><td>{_esc(ep['stop'])}</td>"
                f"<td>{_esc(ep['duration'])}</td><td>{_esc(ep['pattern'])}</td></tr>"
                for ep in priority_eps
            ) or '<tr><td colspan="6" class="empty">No boost episodes in scope</td></tr>'
            ep_note = ('<p class="detail-note">Showing first 200 boost episodes in scope.</p>'
                       if len(priority_eps) >= 200 else "")
            priority_html = f"""
    <section class=\"report-card\"><h2>Priority Inheritance{_esc(scope_title)}</h2>
    <table><thead><tr><th>Task</th><th>Base</th><th>Peak</th><th>Boosts</th><th>Boosted</th><th>Pattern</th></tr></thead>
    <tbody>{pri_body}</tbody></table>
    <h3 class=\"sub\">Boost episodes</h3>{ep_note}
    <table><thead><tr><th>Task</th><th>pri</th><th>Start</th><th>End</th><th>Duration</th><th>Pattern</th></tr></thead>
    <tbody>{ep_body}</tbody></table></section>"""

        sync_html = ""
        queue_html = ""
        if trace.has_sync_object_instrumentation:
            sync_body = "".join(
                f"<tr><td>{_esc(r[3])}</td><td>{_esc(r[1])}</td><td>{r[4]}</td><td>{r[5]}</td>"
                f"<td class=\"{'sev-warning' if len(r) > 10 and r[10] > 0 else ''}\">{r[10] if len(r) > 10 else 0}</td>"
                f"<td>{_esc(r[6])}</td><td class=\"{'sev-error' if r[8] == 'error' else 'sev-warning' if r[8] == 'warning' else ''}\">"
                f"{_esc(r[7])}</td></tr>"
                for r in sync_rows
            ) or '<tr><td colspan="7" class="empty">No mutex/sem activity in scope</td></tr>'
            issue_body = "".join(
                f"<tr><td>{_esc(i.get('obj_key') or '—')}</td>"
                f"<td>{_esc(_format_time(i['time_ns'], trace.time_scale))}</td>"
                f"<td>{_esc(i.get('detail', ''))}</td>"
                f"<td class=\"{_sev_class(i.get('severity', ''))}\">{_esc(i.get('kind', ''))}</td>"
                f"<td>{_esc(i.get('task_label') or '—')}</td>"
                f"<td>{_esc(i.get('core') or '')}</td></tr>"
                for i in sync_issues_scoped
            ) or '<tr><td colspan="6" class="empty">No pairing issues in scope</td></tr>'
            hold_body = "".join(
                f"<tr><td>{_esc(h['object'])}</td><td>{_esc(h['holder'])}</td>"
                f"<td>{_esc(h['start'])}</td><td>{_esc(h['stop'])}</td>"
                f"<td>{_esc(h['duration'])}</td><td>{_esc(h['take_core'])}</td>"
                f"<td>{_esc(h['give_core'])}</td></tr>"
                for h in sync_holds
            ) or '<tr><td colspan="7" class="empty">No paired holds in scope</td></tr>'
            hold_note = ('<p class="detail-note">Showing longest 150 hold episodes in scope.</p>'
                         if len(sync_holds) >= 150 else "")
            sync_html = f"""
    <section class=\"report-card\"><h2>Mutex / Semaphore{_esc(scope_title)}</h2>
    <table><thead><tr><th>Object</th><th>Kind</th><th>Holds</th><th>Issues</th><th>Bounces</th><th>Avg hold</th><th>Status</th></tr></thead>
    <tbody>{sync_body}</tbody></table>
    <h3 class=\"sub\">Pairing issues</h3>
    <table><thead><tr><th>Object</th><th>Time</th><th>Detail</th><th>Issue</th><th>Task</th><th>Core</th></tr></thead>
    <tbody>{issue_body}</tbody></table>
    <h3 class=\"sub\">Hold episodes (longest first)</h3>{hold_note}
    <table><thead><tr><th>Object</th><th>Holder</th><th>Take</th><th>Give</th><th>Duration</th><th>Take core</th><th>Give core</th></tr></thead>
    <tbody>{hold_body}</tbody></table></section>"""

            _queue_html_rows = _sync_object_stats_rows(trace, lo, hi, kind_filter="queue")
            if _queue_html_rows:
                q_body = "".join(
                    f"<tr><td>{_esc(r[3])}</td><td>{_esc(r[1])}</td><td>{r[4]}</td><td>{r[5]}</td>"
                    f"<td class=\"{'sev-warning' if len(r) > 10 and r[10] > 0 else ''}\">{r[10] if len(r) > 10 else 0}</td>"
                    f"<td>{_esc(r[6])}</td><td class=\"{'sev-error' if r[8] == 'error' else 'sev-warning' if r[8] == 'warning' else ''}\">"
                    f"{_esc(r[7])}</td></tr>"
                    for r in _queue_html_rows
                )
                queue_html = (
                    f'<section class="report-card"><h2>Queue{_esc(scope_title)}</h2>'
                    '<table><thead><tr><th>Object</th><th>Kind</th><th>Holds</th>'
                    '<th>Issues</th><th>Bounces</th><th>Avg hold</th><th>Status</th></tr></thead>'
                    f'<tbody>{q_body}</tbody></table></section>'
                )

        interval_body = "".join(
            f"<tr><td>{_esc(r[0])}</td><td>{_esc(r[1])}</td><td>{r[2]}</td>"
            f"<td>{_esc(r[3])}</td><td>{_esc(r[4])}</td><td>{_esc(r[5])}</td><td>{_esc(r[6])}</td></tr>"
            for r in interval_rows
        ) or '<tr><td colspan="7" class="empty">No interval data</td></tr>'
        inst_body = "".join(
            f"<tr><td>{_esc(inst['id'])}</td><td>{_esc(inst['task_id'])}</td>"
            f"<td>{_esc(inst['start'])}</td><td>{_esc(inst['stop'])}</td>"
            f"<td>{_esc(inst['duration'])}</td><td>{_esc(inst['start_core'])}</td>"
            f"<td>{_esc(inst['stop_core'])}</td></tr>"
            for inst in interval_inst
        ) or '<tr><td colspan="7" class="empty">No interval instances in scope</td></tr>'
        inst_note = ('<p class="detail-note">Showing longest 200 interval instances in scope.</p>'
                     if len(interval_inst) >= 200 else "")
        interval_html = f"""
    <section class=\"report-card\"><h2>Interval Analysis{_esc(scope_title)}</h2>
    <table><thead><tr><th>ID</th><th>Label</th><th>Count</th><th>Min</th><th>Avg</th><th>Max</th><th>p95</th></tr></thead>
    <tbody>{interval_body}</tbody></table>
    <h3 class=\"sub\">Interval instances (longest first)</h3>{inst_note}
    <table><thead><tr><th>ID</th><th>Task id</th><th>Start</th><th>Stop</th><th>Duration</th><th>Start core</th><th>Stop core</th></tr></thead>
    <tbody>{inst_body}</tbody></table></section>"""

        tag_body = "".join(
            f"<tr><td>{_esc(r[0])}</td><td>{_esc(r[1])}</td><td>{r[2]}</td>"
            f"<td>{_esc(r[3])}</td><td>{_esc(r[4])}</td><td>{_esc(r[5])}</td><td>{_esc(r[6])}</td></tr>"
            for r in tag_rows
        ) or '<tr><td colspan="7" class="empty">No tag data</td></tr>'
        tag_sample_body = "".join(
            f"<tr><td>{_esc(s['label'])}</td><td>{_esc(s['time'])}</td>"
            f"<td>{_esc(s['value'])}</td><td>{_esc(s['core'] or '—')}</td></tr>"
            for s in tag_samples
        ) or '<tr><td colspan="4" class="empty">No tag samples in scope</td></tr>'
        tag_note = ('<p class="detail-note">Showing highest 200 tag samples in scope.</p>'
                    if len(tag_samples) >= 200 else "")
        tag_html = f"""
    <section class=\"report-card\"><h2>Tag Analysis{_esc(scope_title)}</h2>
    <table><thead><tr><th>Channel</th><th>Label</th><th>Count</th><th>Min</th><th>Avg</th><th>Max</th><th>p95</th></tr></thead>
    <tbody>{tag_body}</tbody></table>
    <h3 class=\"sub\">Tag samples (highest value first)</h3>{tag_note}
    <table><thead><tr><th>Tag</th><th>Time</th><th>Value</th><th>Core</th></tr></thead>
    <tbody>{tag_sample_body}</tbody></table></section>"""

        ts = trace.time_scale
        lc_rows_html = _task_lifecycle_rows(trace, lo, hi)
        lc_body = "".join(
            f"<tr><td>{_esc(label)}</td>"
            f"<td>{_esc(_format_time(cns, ts)) if cns is not None else '—'}</td>"
            f"<td>{_esc(_format_time(dns, ts)) if dns is not None else '—'}</td>"
            f"<td>{nsus}/{nres}</td>"
            f"<td>{_esc(_format_time(alive, ts)) if alive else '—'}</td>"
            f"<td>{nev}</td><td>{nruns}</td></tr>"
            for mk, label, cns, dns, nsus, nres, alive, nev, nruns in lc_rows_html
        ) or '<tr><td colspan="7" class="empty">No lifecycle events</td></tr>'
        lifecycle_html = (
            f'<section class="report-card"><h2>Task Lifecycle{_esc(scope_title)}</h2>'
            '<table><thead><tr><th>Task</th><th>Created</th><th>Deleted</th>'
            '<th>Susp/Res</th><th>Alive span</th><th>Events</th><th>Runs</th></tr></thead>'
            f'<tbody>{lc_body}</tbody></table></section>'
        )

        pair_rows_html = _core_pair_rows(trace, lo, hi)
        pair_body = "".join(
            f"<tr><td>{_esc(fc)}</td><td>{_esc(tc)}</td><td>{cnt}</td><td>{bnc}</td>"
            f"<td>{100.0*bnc/cnt:.1f}%</td><td>{_esc(_format_time(avg_gap, ts))}</td></tr>"
            for fc, tc, cnt, bnc, avg_gap in pair_rows_html
        ) or '<tr><td colspan="6" class="empty">No migrations in scope</td></tr>'
        core_pair_html = (
            f'<section class="report-card"><h2>Core-Pair Migration Summary{_esc(scope_title)}</h2>'
            '<table><thead><tr><th>From</th><th>To</th><th>Count</th>'
            '<th>Bounces</th><th>Bounce %</th><th>Avg Gap</th></tr></thead>'
            f'<tbody>{pair_body}</tbody></table></section>'
        )

        bd_rows_html = _core_time_breakdown(trace, lo, hi)
        bd_body = "".join(
            f"<tr><td>{_esc(core)}</td>"
            f"<td>{100.0*a/max(sp,1):.1f}%</td><td>{100.0*i_/max(sp,1):.1f}%</td>"
            f"<td>{100.0*t_/max(sp,1):.1f}%</td><td>{100.0*g/max(sp,1):.1f}%</td></tr>"
            for core, a, i_, t_, g, sp in bd_rows_html
        ) or '<tr><td colspan="5" class="empty">No core data</td></tr>'
        core_breakdown_html = (
            f'<section class="report-card"><h2>Core Time Breakdown{_esc(scope_title)}</h2>'
            '<table><thead><tr><th>Core</th><th>Active %</th><th>Idle %</th>'
            '<th>Tick %</th><th>Gap %</th></tr></thead>'
            f'<tbody>{bd_body}</tbody></table></section>'
        )

        cc_rows_html = _concurrent_core_active_rows(trace, lo, hi)
        cc_body = "".join(
            f"<tr><td>{n}</td><td>{_esc(_format_time(dur, ts))}</td>"
            f"<td>{pct:.1f}%</td></tr>"
            for n, dur, pct in cc_rows_html
        ) or '<tr><td colspan="3" class="empty">No data</td></tr>'
        concurrency_html = (
            f'<section class="report-card"><h2>Concurrent Core Active Distribution{_esc(scope_title)}</h2>'
            '<table><thead><tr><th>Active Cores</th><th>Duration</th>'
            '<th>% of Span</th></tr></thead>'
            f'<tbody>{cc_body}</tbody></table></section>'
        )

        sw_rows_html = _switch_overhead_rows(trace, lo, hi)
        sw_body = "".join(
            f"<tr><td>{_esc(core)}</td><td>{n_sw}</td>"
            f"<td>{_esc(_format_time(mn, ts))}</td><td>{_esc(_format_time(avg, ts))}</td>"
            f"<td>{_esc(_format_time(mx, ts))}</td><td>{_esc(_format_time(total, ts))}</td>"
            f"<td>{pct:.2f}%</td></tr>"
            for core, n_sw, mn, avg, mx, total, pct in sw_rows_html
        ) or '<tr><td colspan="7" class="empty">No data</td></tr>'
        switch_overhead_html = (
            f'<section class="report-card"><h2>Kernel Switch Overhead{_esc(scope_title)}</h2>'
            '<table><thead><tr><th>Core</th><th>Switches</th><th>Min</th><th>Avg</th>'
            '<th>Max</th><th>Total Overhead</th><th>% of Core</th></tr></thead>'
            f'<tbody>{sw_body}</tbody></table></section>'
        )

        disp_rows_html = self._dispatch_latency_rows(trace, lo, hi)
        disp_body = "".join(
            f"<tr><td>{_esc(label)}</td><td>{n}</td>"
            f"<td>{_esc(mn)}</td><td>{_esc(avg)}</td><td>{_esc(mx)}</td>"
            f"<td>{_esc(jitter)}</td><td>{_esc(stddev)}</td><td>{_esc(p95)}</td></tr>"
            for (_mk, label, n, mn, avg, mx, jitter, stddev, p95,
                 _a, _b) in disp_rows_html
        ) or (
            '<tr><td colspan="8" class="empty">No dispatch samples '
            '(needs STI resume Name[id] or create→first-run)</td></tr>'
        )
        dispatch_html = (
            f'<section class="report-card"><h2>Dispatch / Scheduling Latency{_esc(scope_title)}</h2>'
            '<p class="detail-note">Ready from STI resume / create; sync wakes not attributed.</p>'
            '<table><thead><tr><th>Task</th><th>Activations</th><th>Min</th><th>Avg</th>'
            '<th>Max</th><th>Jitter</th><th>σ</th><th>p95</th></tr></thead>'
            f'<tbody>{disp_body}</tbody></table></section>'
        )

        aff_rows_html = _task_core_affinity_rows(trace, lo, hi)
        aff_body = "".join(
            f"<tr><td>{_esc(label)}</td><td>{_esc(mhex)}</td><td>{_esc(obs)}</td>"
            f"<td style=\"{'color:#c0392b;font-weight:600' if viol != chr(8212) else ''}\">{_esc(viol)}</td></tr>"
            for label, mhex, obs, viol in aff_rows_html
        ) or '<tr><td colspan="4" class="empty">No affinity_set events</td></tr>'
        affinity_html = (
            f'<section class="report-card"><h2>Core Affinity{_esc(scope_title)}</h2>'
            '<table><thead><tr><th>Task</th><th>Mask</th><th>Observed Cores</th>'
            '<th>Violations</th></tr></thead>'
            f'<tbody>{aff_body}</tbody></table></section>'
        )

        # Deadlines / CPU budget
        _dl_viols = _deadline_violations(trace, self._cpu_budget_pct, self._task_deadlines_ns, lo, hi)
        _sv = _dl_viols["slice_violations"]
        _cv = _dl_viols["cpu_violations"]
        deadline_html = ""
        if self._cpu_budget_pct > 0 or self._task_deadlines_ns:
            sv_body = "".join(
                f"<tr><td>{_esc(lbl)}</td><td>{_esc(dur)}</td><td>{_esc(lim)}</td>"
                f'<td style="color:#c0392b;font-weight:600">{_esc(over)}</td></tr>'
                for lbl, dur, lim, over, *_rest in _sv
            ) or '<tr><td colspan="4" class="empty">No slice violations</td></tr>'
            cv_body = "".join(
                f'<tr><td>{_esc(lbl)}</td><td style="color:#c0392b;font-weight:600">{_esc(pct)}</td>'
                f"<td>{_esc(bgt)}</td></tr>"
                for lbl, pct, bgt, *_rest in _cv
            ) or '<tr><td colspan="3" class="empty">No CPU budget violations</td></tr>'
            deadline_html = (
                f'<section class="report-card"><h2>Deadlines / CPU budget{_esc(scope_title)}</h2>'
                "<h3>Slice over deadline</h3>"
                "<table><thead><tr><th>Task</th><th>Duration</th><th>Limit</th><th>Over by</th></tr></thead>"
                f"<tbody>{sv_body}</tbody></table>"
                "<h3>CPU budget exceeded</h3>"
                "<table><thead><tr><th>Task</th><th>CPU %</th><th>Budget</th></tr></thead>"
                f"<tbody>{cv_body}</tbody></table></section>"
            )

        analysis_findings = _build_workflow_analysis_findings(
            core_rows=core_rows,
            exec_rows=exec_rows,
            block_rows=block_rows,
            mig_rows=mig_rows,
            pair_rows=pair_rows_html,
            priority_rows=priority_rows,
            sync_rows=sync_rows,
            sync_issues=sync_issues_scoped,
            tick=tick,
            deadline_viols=_dl_viols if (self._cpu_budget_pct > 0 or self._task_deadlines_ns) else None,
            time_scale=trace.time_scale,
        )
        analysis_findings = self._append_exec_anomaly_findings(
            analysis_findings, trace, lo, hi)
        analysis_html = _render_workflow_analysis_html(analysis_findings, scope_title)

        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        stats_extra_css = f"""
:root {{ --line-strong: #c8d2e0; --stripe: #f7f9fc; }}
.report.report-wide {{ max-width: 1160px; }}
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
.detail-note {{ margin: 6px 0 8px; font-size: 12px; color: var(--muted); }}
h3.sub {{ margin: 14px 0 8px; font-size: 14px; color: #284563; font-weight: 600; }}
.sev-error {{ color: #c0392b; font-weight: 600; }}
.sev-warning {{ color: #d68910; font-weight: 600; }}
.finding-info {{ color: var(--ink); }}
.findings-list {{ margin: 8px 0 0 18px; padding: 0; }}
.findings-list li {{ margin: 8px 0; line-height: 1.45; }}
.finding-wf {{
  color: var(--muted); font-size: 11px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.4px;
}}
.analysis-findings {{ border-left: 4px solid #c0392b; }}
.report-toc {{
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px 14px;
  margin: 14px 0;
  box-shadow: 0 2px 10px rgba(30, 60, 90, 0.06);
}}
.report-toc h2 {{ margin: 0 0 8px 0; }}
.report-toc ul {{ margin: 0; padding: 0 0 0 18px; columns: 2; column-gap: 24px; }}
.report-toc li {{ margin: 4px 0; }}
.report-toc a {{ color: var(--accent); text-decoration: none; }}
.report-toc a:hover {{ text-decoration: underline; }}
details.report-card {{ scroll-margin-top: 12px; }}
details.report-card > summary {{ cursor: pointer; list-style: none; }}
details.report-card > summary::-webkit-details-marker {{ display: none; }}
details.report-card > summary h2 {{ display: inline-block; margin: 0; }}
details.report-card > summary::before {{
  content: "\\25B8";
  display: inline-block;
  width: 14px;
  margin-right: 6px;
  color: var(--accent);
  transition: transform 0.15s ease;
}}
details.report-card[open] > summary::before {{ transform: rotate(90deg); }}
{self._html_export_util_css()}
""".strip()

        body = f"""
        <section class=\"kpi-grid\">
            <article class=\"kpi\"><div class=\"k\">Span{_esc(scope_title)}</div><div class=\"v\">{_esc(span_str)}</div></article>
            <article class=\"kpi\"><div class=\"k\">Tasks</div><div class=\"v\">{task_count:,}</div></article>
            <article class=\"kpi\"><div class=\"k\">Segments</div><div class=\"v\">{seg_count:,}</div></article>
            <article class=\"kpi\"><div class=\"k\">STI Events</div><div class=\"v\">{sti_count:,}</div></article>
            {sched_kpi}
        </section>

        <!--TOC-->

        {analysis_html}

        <section class=\"report-card notes\">
        <h2>Statistics Notes</h2>
        <ul>
            {range_note}
            <li><strong>Execution Time Per Slice:</strong> Duration of each continuous task run between two context switches. Lower and tighter values indicate more predictable execution.</li>
            <li><strong>Inter-Arrival Time:</strong> Time between consecutive activations of the same task (slice start to next slice start). It reflects activation cadence and jitter.</li>
            <li><strong>Blocking Time:</strong> Off-CPU gap between the end of one slice and the start of the next for the same task. It is not end-to-end response time, which requires explicit release and completion events.</li>
      <li><strong>Preemption Chain Analysis:</strong> For each blocking gap of a victim task, identifies which task ran on the same core during that gap. High counts or long totals point to recurring preemption bottlenecks.</li>
      <li><strong>Priority Inheritance:</strong> When traces include <code>create pri:N</code> and priority STI events, lists tasks boosted above base priority. Detail table lists each boost episode.</li>
      <li><strong>Mutex / Semaphore:</strong> Pairs take/give STI by object pointer; detail tables list pairing issues and hold episodes.</li>
      <li><strong>Interval Analysis:</strong> Paired interval_start / interval_stop spans per user-defined id. Detail table lists individual instances.</li>
      <li><strong>Tag Analysis:</strong> Numeric samples from tag0_event … tag7_event STI channels (note field); scatter plot shows value over time.</li>
            <li><strong>Context switches:</strong> Count of segment boundaries on all cores whose start time falls inside the statistics scope.</li>
            <li><strong>Min (Minimum):</strong> The fastest execution time recorded. It represents the best-case scenario under zero system load.</li>
            <li><strong>Max (Maximum):</strong> The slowest execution time recorded. It identifies worst-case bottlenecks, spikes, or resource contention.</li>
            <li><strong>Average (Mean):</strong> Total execution time divided by the number of slices. It shows general performance but is heavily skewed by extreme outliers.</li>
            <li><strong>TrimMean(5%):</strong> Average after removing the fastest 5% and slowest 5% slices. It reflects typical performance while reducing outlier impact.</li>
            <li><strong>Jitter:</strong> Observed spread, calculated as Max − Min for samples in scope.</li>
            <li><strong>σ (Population Standard Deviation):</strong> Typical dispersion of all observed samples around their arithmetic mean.</li>
            <li><strong>P50 (Median):</strong> The midpoint latency where half of slices are faster and half are slower. It captures typical-case behaviour.</li>
            <li><strong>P95 (95th Percentile):</strong> The threshold under which 95% of all slices execute. It is the best metric for user experience because it ignores rare anomalies while capturing real-world slowdowns.</li>
        </ul>
    </section>

    {core_util_html}
    {tick_health_html}
    {core_breakdown_html}
    {concurrency_html}
    {switch_overhead_html}
    {task_util_html}
    <section class=\"report-card\">
    <h2>Core Migrations{_esc(scope_title)}</h2>
    <table>
      <thead><tr><th>Task</th><th>Migr</th><th>Rate</th><th>Dwell</th><th>Cores</th><th>Primary</th><th>Ping</th><th>STI±</th><th>Gap after</th><th>Gap other</th></tr></thead>
      <tbody>{"".join(_migration_row_html(r) for r in mig_rows) or '<tr><td colspan="10" class="empty">No data</td></tr>'}</tbody>
    </table>
  </section>
    {core_pair_html}
    {affinity_html}
    {lifecycle_html}
    {deadline_html}
    {_render_exec_table(exec_rows)}
    {_render_stats_table(f'Blocking Time (off-CPU gap){scope_title}', block_rows)}
    {dispatch_html}
    {_render_stats_table(f'Inter-Arrival Time{scope_title}', inter_rows)}
    <section class=\"report-card\"><h2>Preemption Chain Analysis{_esc(scope_title)}</h2>
    <table><thead><tr><th>Victim</th><th>Preemptor</th><th>Count</th><th>Total</th><th>Avg</th><th>Max</th></tr></thead>
    <tbody>{"".join(
        f"<tr><td>{_esc(r[1])}</td><td>{_esc(r[2])}</td><td>{r[3]}</td><td>{_esc(r[4])}</td><td>{_esc(r[5])}</td><td>{_esc(r[6])}</td></tr>"
        for r in preempt_rows) or "<tr><td colspan=\"6\" class=\"empty\">No preemption events found</td></tr>"}</tbody></table></section>
    {priority_html}
    {sync_html}
    {queue_html}
    {interval_html}
    {tag_html}
    <script>
    (function () {{
      function openTarget(id) {{
        var el = document.getElementById(id)
        if (el && el.tagName === 'DETAILS') el.open = true
      }}
      document.querySelectorAll('.report-toc a[href^="#"]').forEach(function (a) {{
        a.addEventListener('click', function () {{ openTarget(a.getAttribute('href').slice(1)) }})
      }})
      window.addEventListener('hashchange', function () {{ openTarget(location.hash.slice(1)) }})
      if (location.hash) openTarget(location.hash.slice(1))
    }})()
    </script>
"""

        report = btf_html_report_document(
            "Statistics Report",
            body,
            subtitle=f"Generated: {stamp}",
            extra_css=stats_extra_css,
            doc_title="BTFViewer — Statistics Report",
            report_class="report-wide",
        )

        with open(path, "w", encoding="utf-8") as f:
            nav_html, report = self._html_make_collapsible_sections(report)
            f.write(report.replace("<!--TOC-->", nav_html))

    def _export_html(self) -> None:
        if self._trace is None:
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

        try:
            self.write_statistics_html_report(path)
        except OSError as exc:
            QMessageBox.critical(self, "Export Error", f"Could not export HTML:\n{exc}")
            return

        wnd = self.window()
        if isinstance(wnd, QMainWindow):
            wnd.statusBar().showMessage(f"Exported statistics: {path}", 4000)

    def write_statistics_csv_report(self, path: str) -> None:
        trace = self._trace
        if trace is None:
            raise ValueError("no trace loaded")

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
        priority_rows_csv = _priority_stats_rows(trace, lo, hi)
        sync_rows_csv = _sync_object_stats_rows(trace, lo, hi)
        sync_issues_csv = [
            i for i in trace.sync_issues
            if _sync_in_scope(i["time_ns"], lo, hi)
        ] if trace.has_sync_object_instrumentation else []
        ctx_count, core_gaps = _scheduling_stats(trace, lo, hi)
        tick = _tick_health_report(trace, lo, hi)

        def _us(v: object) -> str:
            return str(v).replace("µs", "us").replace("μs", "us")

        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = _SafeCsvWriter(fh, quoting=csv.QUOTE_MINIMAL)

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
                if len(core_rows) >= 2:
                    _csv_pcts = [p for _, p in core_rows]
                    _csv_gini = _gini_coefficient(_csv_pcts)
                    _csv_stddev = _core_util_stddev(_csv_pcts)
                    writer.writerow(["Load Balance Score", f"{max(0.0, 100.0*(1.0-_csv_gini)):.0f}%"])
                    writer.writerow(["Core Util Std Dev (σ)", f"{_csv_stddev:.1f}%"])
                    writer.writerow(["Gini Coefficient (G)", f"{_csv_gini:.4f}"])
            else:
                writer.writerow(["No data", ""])

            writer.writerow([])
            writer.writerow([f"Trace Health (TICK){scope_suffix}"])
            if tick["tick_count"]:
                writer.writerow(["Status", tick["health"].upper()])
                writer.writerow(["Mode", "TICKLESS" if tick["is_tickless"] else "TICK"])
                writer.writerow(["Interval CV", f"{tick['tick_cv'] * 100.0:.2f}%"])
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

            bd_rows_csv = _core_time_breakdown(trace, lo, hi)
            writer.writerow([])
            writer.writerow([f"Core Time Breakdown{scope_suffix}"])
            writer.writerow(["Core", "Active %", "Idle %", "Tick %", "Gap %"])
            if bd_rows_csv:
                for core, a_ns, i_ns, t_ns, g_ns, span_ns in bd_rows_csv:
                    s = max(span_ns, 1)
                    writer.writerow([core, f"{100.0*a_ns/s:.1f}%", f"{100.0*i_ns/s:.1f}%",
                                     f"{100.0*t_ns/s:.1f}%", f"{100.0*g_ns/s:.1f}%"])
            else:
                writer.writerow(["No core data", "", "", "", ""])
            writer.writerow([])
            writer.writerow([f"Concurrent Core Active Distribution{scope_suffix}"])
            writer.writerow(["Active Cores", "Duration", "% of Span"])
            _cc_csv = _concurrent_core_active_rows(trace, lo, hi)
            if _cc_csv:
                for n_active, dur_ns, pct in _cc_csv:
                    writer.writerow([
                        n_active,
                        _us(_format_time(dur_ns, trace.time_scale)),
                        f"{pct:.1f}%",
                    ])
            else:
                writer.writerow(["No data", "", ""])

            writer.writerow([])
            writer.writerow([f"Kernel Switch Overhead{scope_suffix}"])
            writer.writerow([
                "Core", "Switches", "Min", "Avg", "Max", "Total Overhead", "% of Core",
            ])
            _sw_csv = _switch_overhead_rows(trace, lo, hi)
            if _sw_csv:
                for core, n_sw, mn, avg, mx, total, pct in _sw_csv:
                    writer.writerow([
                        core, n_sw,
                        _us(_format_time(mn, trace.time_scale)),
                        _us(_format_time(avg, trace.time_scale)),
                        _us(_format_time(mx, trace.time_scale)),
                        _us(_format_time(total, trace.time_scale)),
                        f"{pct:.2f}%",
                    ])
            else:
                writer.writerow(["No data"] + [""] * 6)

            writer.writerow([])
            writer.writerow([f"Top Tasks by CPU (excl. IDLE/TICK){scope_suffix}"])
            writer.writerow(["Task", "CPU %"])
            if task_rows:
                for _, name, pct in task_rows:
                    writer.writerow([name, f"{pct:.1f}%"])
            else:
                writer.writerow(["No data", ""])

            writer.writerow([])
            writer.writerow([f"Core Migrations{scope_suffix}"])
            writer.writerow(["Task", "Migrations", "Migr rate", "Avg dwell",
                             "Core count", "Primary core",
                             "Primary %", "Ping-pong", "STI near",
                             "Avg gap after", "Avg gap other"])
            if mig_rows:
                for row in mig_rows:
                    (_mk, name, n_mig, n_cores, _cs, primary, pct, ping, sti,
                     ga, go, migr_rate, _rps, avg_dwell, _adtu) = row
                    writer.writerow([name, n_mig, migr_rate, avg_dwell, n_cores, primary,
                                     f"{pct:.1f}", ping, sti, ga, go])
            else:
                writer.writerow(["No data", "", "", "", "", "", "", "", "", "", ""])

            pair_rows_csv = _core_pair_rows(trace, lo, hi)
            writer.writerow([])
            writer.writerow([f"Core-Pair Migration Summary{scope_suffix}"])
            writer.writerow(["From", "To", "Count", "Bounces", "Bounce %", "Avg Gap"])
            if pair_rows_csv:
                for fc, tc, cnt, bnc, avg_gap in pair_rows_csv:
                    pct_b = 100.0 * bnc / cnt if cnt else 0.0
                    writer.writerow([fc, tc, cnt, bnc, f"{pct_b:.1f}%",
                                     _us(_format_time(avg_gap, trace.time_scale))])
            else:
                writer.writerow(["No migrations in scope", "", "", "", "", ""])

            aff_rows_csv = _task_core_affinity_rows(trace, lo, hi)
            writer.writerow([])
            writer.writerow([f"Core Affinity{scope_suffix}"])
            writer.writerow(["Task", "Mask", "Observed Cores", "Violations"])
            if aff_rows_csv:
                for label, mask_hex, obs_str, viol_str in aff_rows_csv:
                    writer.writerow([label, mask_hex, obs_str, viol_str])
            else:
                writer.writerow(["No affinity_set events", "", "", ""])

            lc_rows_csv = _task_lifecycle_rows(trace, lo, hi)
            writer.writerow([])
            writer.writerow([f"Task Lifecycle{scope_suffix}"])
            writer.writerow(["Task", "Created", "Deleted", "Susp/Res", "Alive span", "Events", "Runs"])
            if lc_rows_csv:
                for mk, label, create_ns, delete_ns, n_sus, n_res, alive_ns, n_ev, n_runs in lc_rows_csv:
                    created = _us(_format_time(create_ns, trace.time_scale)) if create_ns is not None else ""
                    deleted = _us(_format_time(delete_ns, trace.time_scale)) if delete_ns is not None else ""
                    alive   = _us(_format_time(alive_ns, trace.time_scale)) if alive_ns else ""
                    writer.writerow([label, created, deleted, f"{n_sus}/{n_res}", alive, n_ev, n_runs])
            else:
                writer.writerow(["No lifecycle events", "", "", "", "", "", ""])

            # Deadlines / CPU budget
            if self._cpu_budget_pct > 0 or self._task_deadlines_ns:
                _dl_viols_csv = _deadline_violations(
                    trace, self._cpu_budget_pct, self._task_deadlines_ns, lo, hi)
                writer.writerow([])
                writer.writerow([f"Deadlines / CPU budget{scope_suffix}"])
                writer.writerow(["Slice Violations"])
                writer.writerow(["Task", "Duration", "Limit", "Over by"])
                if _dl_viols_csv["slice_violations"]:
                    for lbl, dur, lim, over, *_rest in _dl_viols_csv["slice_violations"]:
                        writer.writerow([lbl, dur, lim, over])
                else:
                    writer.writerow(["No slice violations", "", "", ""])
                writer.writerow([])
                writer.writerow(["CPU Budget Violations"])
                writer.writerow(["Task", "CPU %", "Budget"])
                if _dl_viols_csv["cpu_violations"]:
                    for lbl, pct, bgt, *_rest in _dl_viols_csv["cpu_violations"]:
                        writer.writerow([lbl, pct, bgt])
                else:
                    writer.writerow(["No CPU budget violations", "", ""])

            writer.writerow([])
            writer.writerow([f"Execution Time Per Slice{scope_suffix}"])
            writer.writerow([
                "Task", "Runs", "CPU%", "Min", "Avg", "TrimMean(5%)",
                "Max", "Jitter", "StdDev (population)", "p50", "p95",
            ])
            if exec_rows:
                for (mk_r, name, runs, cpu, mn, avg, tmean, mx,
                     jitter, stddev, p50, p95) in exec_rows:
                    writer.writerow([
                        name, runs, f"{cpu:.1f}%", _us(mn), _us(avg),
                        _us(tmean), _us(mx), _us(jitter), _us(stddev),
                        _us(p50), _us(p95),
                    ])
            else:
                writer.writerow(["No data"] + [""] * 10)

            writer.writerow([])
            writer.writerow([f"Blocking Time (off-CPU gap){scope_suffix}"])
            writer.writerow([
                "Task", "Gaps", "Min", "Avg", "TrimMean(5%)", "Max",
                "Jitter", "StdDev (population)", "p50", "p95",
            ])
            if block_rows:
                for (mk_r, name, runs, mn, avg, tmean, mx,
                     jitter, stddev, p50, p95) in block_rows:
                    writer.writerow([
                        name, runs, _us(mn), _us(avg), _us(tmean), _us(mx),
                        _us(jitter), _us(stddev), _us(p50), _us(p95),
                    ])
            else:
                writer.writerow(["No data"] + [""] * 9)

            writer.writerow([])
            writer.writerow([f"Dispatch / Scheduling Latency{scope_suffix}"])
            writer.writerow([
                "Task", "Activations", "Min", "Avg", "Max", "Jitter",
                "StdDev (population)", "p95",
            ])
            _disp_by = _dispatch_latency_by_mk(trace, lo, hi)
            _disp_any = False
            for mk_r, data in sorted(
                    _disp_by.items(),
                    key=lambda kv: (-len(kv[1]["samples"]),
                                    _task_display_name(
                                        trace.task_repr.get(kv[0], kv[0])).lower())):
                raw = trace.task_repr.get(mk_r, mk_r)
                _, _, tname = _parse_task_name(raw)
                if _is_idle_task_name(tname) or tname == "TICK":
                    continue
                summary = self._summarize_samples(data["samples"], trace.time_scale)
                if summary is None:
                    continue
                _disp_any = True
                mn, avg, mx, jitter, stddev, p95 = summary
                writer.writerow([
                    _task_display_name(raw), len(data["samples"]),
                    _us(mn), _us(avg), _us(mx), _us(jitter), _us(stddev), _us(p95),
                ])
            if not _disp_any:
                writer.writerow(["No data"] + [""] * 7)

            writer.writerow([])
            writer.writerow([f"Inter-Arrival Time{scope_suffix}"])
            writer.writerow([
                "Task", "Runs", "Min", "Avg", "TrimMean(5%)", "Max",
                "Jitter", "StdDev (population)", "p50", "p95",
            ])
            if inter_rows:
                for (mk_r, name, runs, mn, avg, tmean, mx,
                     jitter, stddev, p50, p95) in inter_rows:
                    writer.writerow([
                        name, runs, _us(mn), _us(avg), _us(tmean), _us(mx),
                        _us(jitter), _us(stddev), _us(p50), _us(p95),
                    ])
            else:
                writer.writerow(["No data"] + [""] * 9)

            writer.writerow([])
            writer.writerow([f"Preemption Chain Analysis{scope_suffix}"])
            writer.writerow(["Victim", "Preemptor", "Count", "Total", "Avg", "Max"])
            if preempt_rows_csv:
                for _mk, victim, preemptor, count, total, avg, mx in preempt_rows_csv:
                    writer.writerow([victim, preemptor, count, _us(total), _us(avg), _us(mx)])
            else:
                writer.writerow(["No preemption events found", "", "", "", "", ""])

            writer.writerow([])
            writer.writerow([f"Priority Inheritance{scope_suffix}"])
            writer.writerow(["Task", "Base", "Peak", "Boosts", "Boosted", "Pattern"])
            if priority_rows_csv:
                for _mk, label, base, peak, n_eps, total, pattern, _total_ns in priority_rows_csv:
                    writer.writerow([label, base, peak, n_eps, _us(total), pattern])
            elif trace.has_priority_instrumentation:
                writer.writerow(["No priority boosts in scope", "", "", "", "", ""])

            writer.writerow([])
            writer.writerow([f"Mutex / Semaphore{scope_suffix}"])
            writer.writerow(["Object", "Kind", "Holds", "Issues", "Bounces", "Avg hold", "Status"])
            if sync_rows_csv:
                for row_csv in sync_rows_csv:
                    _key, kind, _ptr, label = row_csv[:4]
                    holds, issues, avg, status_label = row_csv[4], row_csv[5], row_csv[6], row_csv[7]
                    bounces = row_csv[10] if len(row_csv) > 10 else 0
                    writer.writerow([label, kind, holds, issues, bounces, _us(avg), status_label])
                # Core affinity violations summary
                total_bounces = sum(r[10] for r in sync_rows_csv if len(r) > 10)
                if total_bounces > 0:
                    writer.writerow([])
                    writer.writerow([f"Core Affinity Violations (lock bounce){scope_suffix}"])
                    writer.writerow(["Object", "Bounces", "Description"])
                    for row_csv in sync_rows_csv:
                        if len(row_csv) > 10 and row_csv[10] > 0:
                            writer.writerow([row_csv[3], row_csv[10],
                                             f"{row_csv[10]} hold(s) crossed core boundaries"])
            elif trace.has_sync_object_instrumentation:
                writer.writerow(["No mutex/sem activity in scope", "", "", "", "", "", ""])

            if trace.has_sync_object_instrumentation:
                writer.writerow([])
                writer.writerow([f"Pairing Issues{scope_suffix}"])
                writer.writerow(["Object", "Time", "Detail", "Issue", "Task", "Core"])
                if sync_issues_csv:
                    for iss in sync_issues_csv:
                        writer.writerow([
                            iss.get("obj_key") or "",
                            _us(_format_time(iss["time_ns"], trace.time_scale)),
                            iss.get("detail", ""),
                            iss.get("kind", ""),
                            iss.get("task_label") or "",
                            iss.get("core") or "",
                        ])
                else:
                    writer.writerow(["No pairing issues in scope", "", "", "", "", ""])

            queue_rows_csv = _sync_object_stats_rows(trace, lo, hi, kind_filter="queue")
            writer.writerow([])
            writer.writerow([f"Queue{scope_suffix}"])
            writer.writerow(["Object", "Kind", "Holds", "Issues", "Bounces", "Avg hold", "Status"])
            if queue_rows_csv:
                for row_csv in queue_rows_csv:
                    _key, kind, _ptr, label = row_csv[:4]
                    holds, issues, avg, status_label = row_csv[4], row_csv[5], row_csv[6], row_csv[7]
                    bounces = row_csv[10] if len(row_csv) > 10 else 0
                    writer.writerow([label, kind, holds, issues, bounces, _us(avg), status_label])
            else:
                writer.writerow(["No queue activity in scope", "", "", "", "", "", ""])

            writer.writerow([])
            writer.writerow([f"Interval Analysis{scope_suffix}"])
            writer.writerow(["ID", "Label", "Count", "Min", "Avg", "Max", "p95"])
            if interval_rows_csv:
                for iid, label, count, mn, avg, mx, p95, *_raw in interval_rows_csv:
                    writer.writerow([iid, label, count, _us(mn), _us(avg), _us(mx), _us(p95)])
            else:
                writer.writerow(["No interval data", "", "", "", "", "", ""])

            tag_rows_csv = _tag_stats_rows(trace, lo, hi)
            writer.writerow([])
            writer.writerow([f"Tag Analysis{scope_suffix}"])
            writer.writerow(["Channel", "Label", "Count", "Min", "Avg", "Max", "p95"])
            if tag_rows_csv:
                for ch, label, count, mn, avg, mx, p95, *_raw in tag_rows_csv:
                    writer.writerow([ch, label, count, mn, avg, mx, p95])
            else:
                writer.writerow(["No tag data", "", "", "", "", "", ""])

    def _export_csv(self) -> None:
        if self._trace is None:
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

        try:
            self.write_statistics_csv_report(path)
        except OSError as exc:
            QMessageBox.critical(self, "Export Error", f"Could not export CSV:\n{exc}")
            return

        wnd = self.window()
        if isinstance(wnd, QMainWindow):
            wnd.statusBar().showMessage(f"Exported statistics: {path}", 4000)

    def clear_trace(self) -> None:
        """Empty Statistics when no trace tab is open (welcome / close-all)."""
        self.clear_plot_session()
        self._trace = None
        self._cursor_times = []
        self._btn_export_csv.setEnabled(False)
        self._btn_export_html.setEnabled(False)
        self._btn_compare_mig.setEnabled(False)
        self._scope_cb.setEnabled(False)
        self._clear()
        self._update_scope_header()
        self._ilay.addWidget(self._lbl(
            "Open a trace file to view statistics.",
            color="#888888",
            ui_fs=self._ui_fs(),
        ))

    def rebuild(self, trace: Optional["BtfTrace"]) -> None:
        if trace is None:
            self.clear_trace()
            return
        self._trace = trace
        defer_heavy = trace_needs_deferred_stats_load(trace)
        self._btn_export_csv.setEnabled(True)
        self._btn_export_html.setEnabled(True)
        wnd = self.window()
        self._btn_compare_mig.setEnabled(
            isinstance(wnd, QMainWindow) and len(getattr(wnd, "_tabs", ())) >= 2)
        self._clear()
        self._defer_heavy_sections = defer_heavy
        if defer_heavy and not self._defer_heavy_collapse_done:
            pinned = set(self._section_pins)
            for sid in STATS_HEAVY_SECTIONS:
                if sid in pinned:
                    continue
                self._section_collapsed[sid] = True
            self._defer_heavy_collapse_done = True
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

        _fs = self._ui_fs()

        _core_rows = self._core_util_rows(trace, lo, hi) if trace.core_names else []
        _task_rows = self._task_cpu_rows(trace, lo=lo, hi=hi)
        _util_labels = (
            [f"  {core}:" for core, _ in _core_rows]
            + [f"  {disp}" for _, disp, _ in _task_rows]
        )
        self._util_label_col_natural = self._compute_util_label_col_width(_util_labels)

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
                # Gauges live inside the util scroll so the default viewport
                # (STATS_CORES_UTIL_DEFAULT_H) shows gauges + two core rows;
                # further cores scroll within the same area.
                inner = QWidget()
                ilay = QVBoxLayout(inner)
                ilay.setContentsMargins(0, 0, 0, 0)
                ilay.setSpacing(STATS_UTIL_ROW_GAP)
                if len(_core_rows) >= 2:
                    _pcts = [p for _, p in _core_rows]
                    _lb = _load_balance_metrics(_pcts)
                    if _lb is not None:
                        ilay.addWidget(_LoadBalanceGaugeWidget(_lb))
                for core, pct in _core_rows:
                    self._add_utilisation_row(
                        ilay, _fs, f"  {core}:", pct,
                        chunk_color="#5FCF6F", pct_color="#77BB77",
                    )
                ilay.addStretch(1)
                self._wrap_util_rows_scroll(blay, inner, len(_core_rows), "cores")

            self._add_collapsible_section(
                "cores",
                f"Core Utilisation (excl. IDLE/TICK){scope}",
                _fs,
                _populate_cores,
            )

            # -- Per-core time breakdown ----------------------------------
            def _populate_core_breakdown(blay: QVBoxLayout) -> None:
                _bd_rows = _core_time_breakdown(trace, lo, hi)
                if not _bd_rows:
                    blay.addWidget(self._lbl("No core segments", color="#888888", ui_fs=_fs))
                    return
                headers = ["Core", "Active %", "Idle %", "Tick %", "Gap %"]
                tbl = QTableWidget(len(_bd_rows), len(headers))
                tbl.setHorizontalHeaderLabels(headers)
                tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
                tbl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                tbl.verticalHeader().setVisible(False)
                tbl.setShowGrid(False)
                tbl.setFrameShape(QFrame.NoFrame)
                tbl.verticalHeader().setDefaultSectionSize(STATS_TABLE_ROW_H)
                tbl.verticalHeader().setMinimumSectionSize(STATS_TABLE_ROW_H)
                tbl.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
                tbl.horizontalHeader().setFixedHeight(18)
                tbl.horizontalHeader().setSectionsClickable(True)
                tbl.horizontalHeader().setSortIndicatorShown(True)
                _item_bg = self._apply_stats_table_theme(tbl, _fs)
                for r, (core, active_ns, idle_ns, tick_ns, gap_ns, span_ns) in enumerate(_bd_rows):
                    s = max(span_ns, 1)
                    pct_a = 100.0 * active_ns / s
                    pct_i = 100.0 * idle_ns / s
                    pct_t = 100.0 * tick_ns / s
                    pct_g = 100.0 * gap_ns / s
                    for c, (val, key) in enumerate([
                        (core, core),
                        (f"{pct_a:.1f}%", pct_a),
                        (f"{pct_i:.1f}%", pct_i),
                        (f"{pct_t:.1f}%", pct_t),
                        (f"{pct_g:.1f}%", pct_g),
                    ]):
                        item = _StatsSortItem(val, key)
                        item.setTextAlignment(
                            (Qt.AlignmentFlag.AlignLeft if c == 0 else Qt.AlignmentFlag.AlignRight)
                            | Qt.AlignmentFlag.AlignVCenter)
                        item.setBackground(_item_bg)
                        if c == 0:
                            item.setData(Qt.ItemDataRole.UserRole, core)
                            item.setToolTip(f"Click to show \u2018{core}\u2019 in Core View")
                        tbl.setItem(r, c, item)
                tbl.setSortingEnabled(True)

                def _on_core_breakdown_row(row: int, _col: int) -> None:
                    item = tbl.item(row, 0)
                    if item is None:
                        return
                    core = item.data(Qt.ItemDataRole.UserRole)
                    if core:
                        self.core_clicked.emit(core)

                tbl.cellClicked.connect(_on_core_breakdown_row)
                self._wire_stats_table_click_cursor(tbl)
                self._wire_stats_table_row_hover(tbl)
                self._wrap_table_with_resizer(blay, tbl, "core_breakdown")

            self._add_collapsible_section(
                "core_breakdown",
                f"Core Time Breakdown{scope}",
                _fs,
                _populate_core_breakdown,
            )

            # -- Concurrent core active distribution ----------------------
            def _populate_concurrency(blay: QVBoxLayout) -> None:
                _cc_rows = _concurrent_core_active_rows(trace, lo, hi)
                if not _cc_rows:
                    blay.addWidget(self._lbl(
                        "No active core intervals", color="#888888", ui_fs=_fs))
                    return
                headers = ["Active Cores", "Duration", "% of Span"]
                tbl = QTableWidget(len(_cc_rows), len(headers))
                tbl.setHorizontalHeaderLabels(headers)
                tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
                tbl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                tbl.verticalHeader().setVisible(False)
                tbl.setShowGrid(False)
                tbl.setFrameShape(QFrame.NoFrame)
                tbl.verticalHeader().setDefaultSectionSize(STATS_TABLE_ROW_H)
                tbl.verticalHeader().setMinimumSectionSize(STATS_TABLE_ROW_H)
                tbl.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
                tbl.horizontalHeader().setFixedHeight(18)
                tbl.horizontalHeader().setSectionsClickable(True)
                tbl.horizontalHeader().setSortIndicatorShown(True)
                _item_bg = self._apply_stats_table_theme(tbl, _fs)
                for r, (n_active, dur_ns, pct) in enumerate(_cc_rows):
                    vals = [
                        str(n_active),
                        _format_time(dur_ns, trace.time_scale),
                        f"{pct:.1f}%",
                    ]
                    keys = [n_active, dur_ns, pct]
                    for c, (val, key) in enumerate(zip(vals, keys)):
                        item = _StatsSortItem(val, key)
                        item.setTextAlignment(
                            (Qt.AlignmentFlag.AlignLeft if c == 0
                             else Qt.AlignmentFlag.AlignRight)
                            | Qt.AlignmentFlag.AlignVCenter)
                        item.setBackground(_item_bg)
                        if c == 0:
                            item.setData(Qt.ItemDataRole.UserRole, n_active)
                            item.setToolTip(
                                f"Click to open interval-duration plot for "
                                f"{n_active} active core(s)")
                        tbl.setItem(r, c, item)
                tbl.setSortingEnabled(True)

                def _on_concurrency_row(row: int, _col: int) -> None:
                    item = tbl.item(row, 0)
                    if item is None:
                        return
                    n = item.data(Qt.ItemDataRole.UserRole)
                    if n is not None:
                        self._open_plot(trace, str(int(n)), "concurrency")

                tbl.cellClicked.connect(_on_concurrency_row)
                self._wire_stats_table_click_cursor(tbl)
                self._wire_stats_table_row_hover(tbl)
                self._wrap_table_with_resizer(blay, tbl, "concurrency")

            self._add_collapsible_section(
                "concurrency",
                f"Concurrent Core Active Distribution{scope}",
                _fs,
                _populate_concurrency,
            )

            # -- Kernel switch overhead -----------------------------------
            def _populate_switch_overhead(blay: QVBoxLayout) -> None:
                _sw_rows = _switch_overhead_rows(trace, lo, hi)
                if not _sw_rows:
                    blay.addWidget(self._lbl(
                        "No context switches", color="#888888", ui_fs=_fs))
                    return
                headers = ["Core", "Switches", "Min", "Avg", "Max",
                           "Total Overhead", "% of Core"]
                tbl = QTableWidget(len(_sw_rows), len(headers))
                tbl.setHorizontalHeaderLabels(headers)
                tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
                tbl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                tbl.verticalHeader().setVisible(False)
                tbl.setShowGrid(False)
                tbl.setFrameShape(QFrame.NoFrame)
                tbl.verticalHeader().setDefaultSectionSize(STATS_TABLE_ROW_H)
                tbl.verticalHeader().setMinimumSectionSize(STATS_TABLE_ROW_H)
                tbl.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
                tbl.horizontalHeader().setFixedHeight(18)
                tbl.horizontalHeader().setSectionsClickable(True)
                tbl.horizontalHeader().setSortIndicatorShown(True)
                _item_bg = self._apply_stats_table_theme(tbl, _fs)
                scale = trace.time_scale
                for r, (core, n_sw, mn, avg, mx, total, pct) in enumerate(_sw_rows):
                    cells = [
                        (core, core),
                        (str(n_sw), n_sw),
                        (_format_time(mn, scale), mn),
                        (_format_time(avg, scale), avg),
                        (_format_time(mx, scale), mx),
                        (_format_time(total, scale), total),
                        (f"{pct:.2f}%", pct),
                    ]
                    for c, (val, key) in enumerate(cells):
                        item = _StatsSortItem(val, key)
                        item.setTextAlignment(
                            (Qt.AlignmentFlag.AlignLeft if c == 0
                             else Qt.AlignmentFlag.AlignRight)
                            | Qt.AlignmentFlag.AlignVCenter)
                        item.setBackground(_item_bg)
                        if c == 0:
                            item.setData(Qt.ItemDataRole.UserRole, core)
                            item.setToolTip(
                                f"Click to open switch-overhead plot for {core}")
                        tbl.setItem(r, c, item)
                tbl.setSortingEnabled(True)

                def _on_switch_row(row: int, _col: int) -> None:
                    item = tbl.item(row, 0)
                    if item is None:
                        return
                    core = item.data(Qt.ItemDataRole.UserRole)
                    if core:
                        self._open_plot(trace, core, "switch_overhead")

                tbl.cellClicked.connect(_on_switch_row)
                self._wire_stats_table_click_cursor(tbl)
                self._wire_stats_table_row_hover(tbl)
                self._wrap_table_with_resizer(blay, tbl, "switch_overhead")

            self._add_collapsible_section(
                "switch_overhead",
                f"Kernel Switch Overhead{scope}",
                _fs,
                _populate_switch_overhead,
            )

        # -- Top tasks by CPU time (excl. IDLE, top 10) -------------------
        def _populate_tasks(blay: QVBoxLayout) -> None:
            if not _task_rows:
                blay.addWidget(self._lbl("No user tasks found", color="#888888", ui_fs=_fs))
                return
            inner = QWidget()
            ilay = QVBoxLayout(inner)
            ilay.setContentsMargins(0, 0, 0, 0)
            ilay.setSpacing(STATS_UTIL_ROW_GAP)
            for mk, disp, pct in _task_rows:
                self._add_utilisation_row(
                    ilay, _fs, f"  {disp}", pct,
                    chunk_color="#5B9BD5", pct_color="#6AAADD",
                    on_click=lambda key=mk: self.task_clicked.emit(key),
                    click_tip=f"Click to highlight \u2018{disp}\u2019 in the timeline",
                )
            ilay.addStretch(1)
            self._wrap_util_rows_scroll(blay, inner, len(_task_rows), "tasks")

        self._add_collapsible_section(
            "tasks",
            f"Top Tasks by CPU (excl. IDLE/TICK){scope}",
            _fs,
            _populate_tasks,
        )

        # -- Trace health (TICK) ------------------------------------------
        def _populate_health(blay: QVBoxLayout) -> None:
            _tick = _tick_health_report(trace, lo, hi)
            if _tick["tick_count"] == 0:
                blay.addWidget(self._lbl("No STI TICK events", color="#888888", ui_fs=_fs))
                return
            colors = {"good": "#5FCF6F", "warning": "#E8C84A", "critical": "#E85D5D"}

            # --- health summary (full width; wraps in narrow stats dock) ---
            mode_label = "TICKLESS" if _tick["is_tickless"] else "TICK"
            cv_pct = _tick["tick_cv"] * 100.0
            health_lbl = self._lbl(
                f"{_tick['health'].upper()}  ·  {_tick['tick_count']:,} ticks  ·  "
                f"avg {_format_time(_tick['avg_period'], trace.time_scale)}  ·  "
                f"max gap {_format_time(_tick['max_gap'], trace.time_scale)}",
                color=colors.get(_tick["health"], "#888888"),
                ui_fs=_fs,
            )
            health_lbl.setWordWrap(True)
            health_lbl.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            blay.addWidget(health_lbl)

            # --- mode badge + tick distribution (always visible when plottable) ---
            badge_row = QWidget()
            badge_lay = QHBoxLayout(badge_row)
            badge_lay.setContentsMargins(0, 0, 0, 0)
            badge_lay.setSpacing(6)
            mode_badge = QLabel(mode_label)
            mode_badge.setToolTip(
                f"{'Tickless' if _tick['is_tickless'] else 'Tick'} mode detected "
                f"(interval CV={cv_pct:.1f}%): "
                + ("tick intervals vary because the scheduler suppresses ticks during idle."
                   if _tick["is_tickless"]
                   else "tick intervals are constant.")
            )
            mode_badge.setStyleSheet(
                self._tick_mode_badge_style(self._is_dark, _tick["is_tickless"], _fs))
            badge_lay.addWidget(mode_badge, 0)
            if _tick["tick_count"] >= 2:
                badge_lay.addWidget(self._make_tick_dist_button(_fs), 0)
            badge_lay.addStretch(1)
            blay.addWidget(badge_row)

            if _tick["is_tickless"]:
                hint_lbl = self._lbl(
                    "Tickless mode: tick intervals vary.",
                    color="#888888", ui_fs=_fs)
                hint_lbl.setWordWrap(True)
                blay.addWidget(hint_lbl)

            if _tick["large_gaps"]:
                blay.addWidget(self._lbl(
                    f"{len(_tick['large_gaps'])} large gap(s) · "
                    f"~{_tick['missed_estimate']} missed ticks",
                    color="#888888", ui_fs=_fs))
                table = QTableWidget(len(_tick["large_gaps"]), 4)
                table.setHorizontalHeaderLabels(["Start", "End", "Gap", "Missed"])
                table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
                table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                table.verticalHeader().setVisible(False)
                table.horizontalHeader().setStretchLastSection(False)
                table.setShowGrid(False)
                table.setFrameShape(QFrame.NoFrame)
                table.verticalHeader().setDefaultSectionSize(STATS_TABLE_ROW_H)
                table.verticalHeader().setMinimumSectionSize(STATS_TABLE_ROW_H)
                table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
                table.horizontalHeader().setFixedHeight(18)
                table.horizontalHeader().setSectionsClickable(True)
                table.horizontalHeader().setSortIndicatorShown(True)
                table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                _item_bg = self._apply_stats_table_theme(table, _fs)
                for r, (start, end, dur, missed) in enumerate(_tick["large_gaps"]):
                    keys = (start, end, dur, missed)
                    for c, val in enumerate((
                        _format_time(start, trace.time_scale),
                        _format_time(end, trace.time_scale),
                        _format_time(dur, trace.time_scale),
                        str(missed),
                    )):
                        item = _StatsSortItem(val, keys[c])
                        item.setBackground(_item_bg)
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                        table.setItem(r, c, item)
                table.setAlternatingRowColors(False)
                table.setWordWrap(False)
                for r in range(table.rowCount()):
                    table.setRowHeight(r, STATS_TABLE_ROW_H)
                table.resizeColumnsToContents()
                table.setColumnWidth(3, min(table.columnWidth(3), 76))
                table.setSortingEnabled(True)
                self._wire_stats_table_row_hover(table)
                host = QWidget()
                hlay = QVBoxLayout(host)
                hlay.setContentsMargins(0, 0, 0, 0)
                hlay.setSpacing(4)
                self._wrap_table_with_resizer(hlay, table, "health")
                blay.addWidget(host)

        self._add_collapsible_section(
            "health",
            f"Trace Health (TICK){scope}",
            _fs,
            _populate_health,
        )

        # -- Core migrations ----------------------------------------------
        empty_mig = ("No multi-core tasks in cursor range" if scope
                     else "No tasks ran on more than one core")

        def _on_mig_row(mk: str) -> None:
            self._open_plot(trace, mk, "mig_dwell")

        def _populate_mig(blay: QVBoxLayout) -> None:
            _mig_rows = _migration_rows(trace, lo, hi)
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

        # -- Core-pair migration summary ----------------------------------
        def _populate_core_pairs(blay: QVBoxLayout) -> None:
            _pair_rows = _core_pair_rows(trace, lo, hi)
            if not _pair_rows:
                blay.addWidget(self._lbl("No migrations in scope", color="#888888", ui_fs=_fs))
                return
            ts = trace.time_scale
            headers = ["From", "To", "Count", "Bounces", "Bounce %", "Avg Gap"]
            tbl = QTableWidget(len(_pair_rows), len(headers))
            tbl.setHorizontalHeaderLabels(headers)
            tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            tbl.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            tbl.verticalHeader().setVisible(False)
            tbl.setShowGrid(False)
            tbl.setFrameShape(QFrame.NoFrame)
            tbl.verticalHeader().setDefaultSectionSize(STATS_TABLE_ROW_H)
            tbl.verticalHeader().setMinimumSectionSize(STATS_TABLE_ROW_H)
            tbl.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            tbl.horizontalHeader().setFixedHeight(18)
            tbl.horizontalHeader().setSectionsClickable(True)
            tbl.horizontalHeader().setSortIndicatorShown(True)
            tbl.setToolTip(
                "Click a row to view Gap/Rate distribution for that core pair")
            _item_bg = self._apply_stats_table_theme(tbl, _fs)
            for r, (fc, tc, cnt, bnc, avg_gap) in enumerate(_pair_rows):
                pct = 100.0 * bnc / cnt if cnt else 0.0
                for c, (val, sort_key) in enumerate([
                    (fc, fc),
                    (tc, tc),
                    (str(cnt), cnt),
                    (str(bnc), bnc),
                    (f"{pct:.1f}%", pct),
                    (_format_time(avg_gap, ts), avg_gap),
                ]):
                    item = _StatsSortItem(val, sort_key)
                    item.setTextAlignment(
                        (Qt.AlignmentFlag.AlignLeft if c <= 1 else Qt.AlignmentFlag.AlignRight)
                        | Qt.AlignmentFlag.AlignVCenter)
                    item.setBackground(_item_bg)
                    if c == 0:
                        item.setData(Qt.ItemDataRole.UserRole, (fc, tc))
                    tbl.setItem(r, c, item)
            tbl.setSortingEnabled(True)

            def _on_pair_row(row: int, _col: int) -> None:
                item = tbl.item(row, 0)
                if item is None:
                    return
                pair = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(pair, tuple) and len(pair) == 2:
                    self._open_pair_plot(trace, pair[0], pair[1])

            tbl.cellClicked.connect(_on_pair_row)
            self._wire_stats_table_row_hover(tbl)
            self._wrap_table_with_resizer(blay, tbl, "core_pairs")

        self._add_collapsible_section(
            "core_pairs",
            f"Core-Pair Migration Summary{scope}",
            _fs,
            _populate_core_pairs,
        )

        # -- Execution time per slice -------------------------------------
        empty_exec = ("No slices fully inside cursor range" if scope
                      else "No user-task slices found")

        def _populate_exec(blay: QVBoxLayout) -> None:
            _exec_rows = self._exec_slice_rows(trace, lo, hi)
            blay.addWidget(self._build_stats_table(
                _exec_rows,
                _fs,
                empty_exec,
                include_cpu=True,
                section_id="exec",
                include_variability=True,
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
        empty_block = ("No off-CPU gaps fully inside cursor range" if scope
                       else "Need at least 2 activations per task")

        def _populate_block(blay: QVBoxLayout) -> None:
            _block_rows = self._blocking_time_rows(trace, lo, hi)
            blay.addWidget(self._build_stats_table(
                _block_rows,
                _fs,
                empty_block,
                count_header="Gaps",
                section_id="block",
                include_variability=True,
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

        # -- Dispatch / scheduling latency (STI resume / create → run) ----
        empty_dispatch = (
            "No dispatch samples in cursor range (needs STI resume Name[id] "
            "or task create → first run)"
            if scope else
            "No dispatch samples — needs STI task resume Name[id] "
            "(vTaskResume) or create→first-run pairs"
        )

        def _populate_dispatch(blay: QVBoxLayout) -> None:
            _disp_rows_raw = self._dispatch_latency_rows(trace, lo, hi)
            _disp_rows = [
                (mk, label, n, mn, avg, mx, jitter, stddev, p95)
                for (mk, label, n, mn, avg, mx, jitter, stddev, p95,
                     _min_seg, _max_seg) in _disp_rows_raw
            ]
            blay.addWidget(self._lbl(
                "Ready time from STI resume / create; dispatch = next switch-in. "
                "Sync-object wakes are not attributed (no woken-task id in BTF).",
                color="#888888", ui_fs=_fs))
            blay.addWidget(self._build_stats_table(
                _disp_rows,
                _fs,
                empty_dispatch,
                count_header="Activations",
                section_id="dispatch",
                include_variability=True,
                on_row_click=lambda mk: self._open_plot(trace, mk, "dispatch"),
                on_min_click=lambda mk: self._on_dispatch_extreme_click(
                    trace, mk, lo, hi, False),
                on_max_click=lambda mk: self._on_dispatch_extreme_click(
                    trace, mk, lo, hi, True),
            ))

        self._add_collapsible_section(
            "dispatch",
            f"Dispatch / Scheduling Latency{scope}",
            _fs,
            _populate_dispatch,
        )

        # -- Inter-arrival time -------------------------------------------
        def _populate_inter(blay: QVBoxLayout) -> None:
            _inter_rows = self._inter_arrival_rows(trace, lo, hi)
            blay.addWidget(self._build_stats_table(
                _inter_rows,
                _fs,
                "Need at least 2 activations per task",
                section_id="inter",
                include_variability=True,
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
        empty_preempt = ("No preemption events in cursor range" if scope
                         else "No preemption events found (single-task or idle-only trace)")

        def _populate_preempt(blay: QVBoxLayout) -> None:
            _preempt_rows, _preempt_truncated = _preemption_chain_rows(trace, lo, hi)
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

        # -- Priority inheritance ---------------------------------------------
        if trace.has_priority_instrumentation:
            empty_priority = ("No priority boosts in cursor range" if scope
                              else "No priority boosts in trace")

            def _populate_priority(blay: QVBoxLayout) -> None:
                _priority_rows = _priority_stats_rows(trace, lo, hi)
                blay.addWidget(self._lbl(
                    "Orange/red bands on task rows mark boosted periods. "
                    "L/M/H pattern = medium-priority task between base and peak.",
                    color="#888888", ui_fs=_fs))
                host = QWidget()
                play = QVBoxLayout(host)
                play.setContentsMargins(0, 0, 0, 0)
                if not _priority_rows:
                    play.addWidget(self._lbl(empty_priority, color="#888888", ui_fs=_fs))
                else:
                    headers = ["Task", "Base", "Peak", "Boosts", "Boosted", "Pattern"]
                    table = QTableWidget(len(_priority_rows), len(headers))
                    table.setHorizontalHeaderLabels(headers)
                    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                    table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
                    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                    table.verticalHeader().setVisible(False)
                    table.horizontalHeader().setStretchLastSection(True)
                    table.setShowGrid(False)
                    table.setFrameShape(QFrame.NoFrame)
                    table.verticalHeader().setDefaultSectionSize(STATS_TABLE_ROW_H)
                    table.verticalHeader().setMinimumSectionSize(STATS_TABLE_ROW_H)
                    table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
                    table.horizontalHeader().setSectionsClickable(True)
                    table.horizontalHeader().setSortIndicatorShown(True)
                    self._apply_stats_table_theme(table, _fs)
                    _item_bg = QBrush(self._stats_table_colors()[0])
                    _priority_align = [
                        Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignRight,
                        Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignRight,
                        Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignLeft,
                    ]
                    for ri, row in enumerate(_priority_rows):
                        mk, label, base, peak, count, total, pattern, total_ns = row
                        vals = [label, str(base), str(peak), str(count), total, pattern]
                        sort_keys = [
                            label.lower(), base, peak, count, total_ns, pattern.lower(),
                        ]
                        for ci, val in enumerate(vals):
                            item = _StatsSortItem(val, sort_keys[ci])
                            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                            item.setBackground(_item_bg)
                            item.setTextAlignment(_priority_align[ci] | Qt.AlignmentFlag.AlignVCenter)
                            if ci == 0:
                                item.setData(Qt.ItemDataRole.UserRole, mk)
                            if ci == 5 and "L/M/H" in pattern:
                                item.setForeground(QBrush(QColor("#E74C3C")))
                            table.setItem(ri, ci, item)
                    table.setSortingEnabled(True)

                    def _on_priority_row_clicked(row: int, _col: int) -> None:
                        item = table.item(row, 0)
                        if item is None:
                            return
                        mk = item.data(Qt.ItemDataRole.UserRole)
                        if mk:
                            self._open_priority_plot(trace, mk)

                    table.cellClicked.connect(_on_priority_row_clicked)
                    self._wire_stats_table_click_cursor(table)
                    self._wire_stats_table_row_hover(table)
                    self._wrap_table_with_resizer(play, table, "priority")
                blay.addWidget(host)

            self._add_collapsible_section(
                "priority",
                f"Priority Inheritance{scope}",
                _fs,
                _populate_priority,
            )

        # -- Mutex / Semaphore pairing ---------------------------------------
        if trace.has_sync_object_instrumentation:
            empty_sync = ("No mutex/sem activity in cursor range" if scope
                          else "No mutex/sem STI events in trace")

            def _populate_sync(blay: QVBoxLayout) -> None:
                _sync_rows = _sync_object_stats_rows(trace, lo, hi)
                _sync_issues_scoped = [
                    i for i in trace.sync_issues
                    if _sync_in_scope(i["time_ns"], lo, hi)
                ]
                blay.addWidget(self._lbl(
                    "Pairs take/give STI events by object pointer (0x........). "
                    "Flags orphan gives, unmatched takes, delete-while-held, "
                    "and multi-mutex hold at trace end.",
                    color="#888888", ui_fs=_fs))
                host = QWidget()
                play = QVBoxLayout(host)
                play.setContentsMargins(0, 0, 0, 0)
                if not _sync_rows:
                    play.addWidget(self._lbl(empty_sync, color="#888888", ui_fs=_fs))
                else:
                    headers = ["Object", "Kind", "Holds", "Issues", "Bounces", "Avg hold", "Status"]
                    table = QTableWidget(len(_sync_rows), len(headers))
                    table.setHorizontalHeaderLabels(headers)
                    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                    table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
                    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                    table.verticalHeader().setVisible(False)
                    table.horizontalHeader().setStretchLastSection(True)
                    table.setShowGrid(False)
                    table.setFrameShape(QFrame.NoFrame)
                    table.verticalHeader().setDefaultSectionSize(STATS_TABLE_ROW_H)
                    table.verticalHeader().setMinimumSectionSize(STATS_TABLE_ROW_H)
                    table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
                    table.horizontalHeader().setSectionsClickable(True)
                    table.horizontalHeader().setSortIndicatorShown(True)
                    self._apply_stats_table_theme(table, _fs)
                    _item_bg = QBrush(self._stats_table_colors()[0])
                    _status_rank = {"error": 0, "warning": 1, "ok": 2}
                    _sync_align = [
                        Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignLeft,
                        Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignRight,
                        Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignRight,
                        Qt.AlignmentFlag.AlignLeft,
                    ]
                    for ri, row in enumerate(_sync_rows):
                        _key, kind, ptr, label, holds, issues, avg, status_label, status, avg_ns, bounces = row[:11]
                        vals = [label, kind, str(holds), str(issues), str(bounces), avg, status_label]
                        sort_keys = [
                            label.lower(), kind.lower(), holds, issues, bounces,
                            avg_ns if avg_ns is not None else -1,
                            _status_rank.get(status, 3),
                        ]
                        for ci, val in enumerate(vals):
                            item = _StatsSortItem(val, sort_keys[ci])
                            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                            item.setBackground(_item_bg)
                            item.setTextAlignment(_sync_align[ci] | Qt.AlignmentFlag.AlignVCenter)
                            if ci == 0:
                                item.setData(Qt.ItemDataRole.UserRole, _key)
                            if ci == 4 and bounces > 0:
                                item.setForeground(QBrush(QColor("#F39C12")))
                            if ci == 6 and status != "ok":
                                color = "#E74C3C" if status == "error" else "#F39C12"
                                item.setForeground(QBrush(QColor(color)))
                            table.setItem(ri, ci, item)
                    table.setSortingEnabled(True)
                    self._wire_stats_table_row_hover(table)
                    self._wrap_table_with_resizer(play, table, "sync")
                    _issues_display, _issues_cap_note = cap_stats_table_rows(
                        _sync_issues_scoped)
                    if _issues_display:
                        issue_headers = ["Object", "Time", "Detail", "Issue", "Task", "Core"]
                        itable = QTableWidget(len(_issues_display), len(issue_headers))
                        itable.setHorizontalHeaderLabels(issue_headers)
                        itable.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                        itable.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
                        itable.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                        itable.verticalHeader().setVisible(False)
                        itable.horizontalHeader().setStretchLastSection(True)
                        itable.setShowGrid(False)
                        itable.setFrameShape(QFrame.NoFrame)
                        itable.verticalHeader().setDefaultSectionSize(STATS_TABLE_ROW_H)
                        itable.verticalHeader().setMinimumSectionSize(STATS_TABLE_ROW_H)
                        itable.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
                        itable.horizontalHeader().setSectionsClickable(True)
                        itable.horizontalHeader().setSortIndicatorShown(True)
                        self._apply_stats_table_theme(itable, _fs)
                        _item_bg = QBrush(self._stats_table_colors()[0])
                        _issue_align = [
                            Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignRight,
                            Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignLeft,
                            Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignLeft,
                        ]

                        def _on_issue_row(row: int, _col: int) -> None:
                            item = itable.item(row, 0)
                            if item is None:
                                return
                            iss = item.data(Qt.ItemDataRole.UserRole)
                            if iss is None:
                                return
                            payload = SyncIssueRef(
                                time_ns=iss["time_ns"],
                                core=iss.get("core") or "",
                                kind=iss.get("kind", ""),
                                detail=iss.get("detail", ""),
                                obj_key=iss.get("obj_key"),
                                ptr=iss.get("ptr", ""),
                            )
                            self.plot_point_clicked.emit(
                                payload, iss["time_ns"], _format_sync_issue_note(iss))

                        itable.cellClicked.connect(_on_issue_row)
                        self._wire_stats_table_click_cursor(itable)
                        self._wire_stats_table_row_hover(itable)
                        for ri, iss in enumerate(_issues_display):
                            vals = [
                                iss.get("obj_key") or "—",
                                _format_time(iss["time_ns"], trace.time_scale),
                                iss.get("detail", ""),
                                iss.get("kind", ""),
                                iss.get("task_label") or "—",
                                iss.get("core") or "",
                            ]
                            sort_keys = [
                                (iss.get("obj_key") or "").lower(),
                                iss["time_ns"],
                                (iss.get("detail") or "").lower(),
                                (iss.get("kind") or "").lower(),
                                (iss.get("task_label") or "").lower(),
                                (iss.get("core") or "").lower(),
                            ]
                            tip = (f"Jump, zoom, and annotate at "
                                   f"{_format_time(iss['time_ns'], trace.time_scale)}")
                            for ci, val in enumerate(vals):
                                item = _StatsSortItem(val, sort_keys[ci])
                                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                                item.setBackground(_item_bg)
                                item.setTextAlignment(_issue_align[ci] | Qt.AlignmentFlag.AlignVCenter)
                                item.setToolTip(tip)
                                if ci == 0:
                                    item.setData(Qt.ItemDataRole.UserRole, iss)
                                if ci == 3:
                                    sev = iss.get("severity", "")
                                    if sev == "error":
                                        item.setForeground(QBrush(QColor("#E74C3C")))
                                    elif sev == "warning":
                                        item.setForeground(QBrush(QColor("#F39C12")))
                                itable.setItem(ri, ci, item)
                        itable.setSortingEnabled(True)
                        self._wrap_table_with_resizer(play, itable, "sync_issues")
                        self._add_stats_table_cap_note(play, _issues_cap_note, _fs)
                blay.addWidget(host)

            self._add_collapsible_section(
                "sync",
                f"Mutex / Semaphore{scope}",
                _fs,
                _populate_sync,
            )

            # -- Queue (send/recv pairs) ---------------------------------------
            empty_queue = ("No queue activity in cursor range" if scope
                           else "No queue send/recv STI events in trace")

            def _populate_queue(blay: QVBoxLayout) -> None:
                _queue_rows = _sync_object_stats_rows(trace, lo, hi, kind_filter="queue")
                blay.addWidget(self._lbl(
                    "Pairs send/recv STI events by queue pointer (0x........).",
                    color="#888888", ui_fs=_fs))
                if not _queue_rows:
                    blay.addWidget(self._lbl(empty_queue, color="#888888", ui_fs=_fs))
                    return
                headers = ["Object", "Kind", "Holds", "Issues", "Bounces", "Avg hold", "Status"]
                table = QTableWidget(len(_queue_rows), len(headers))
                table.setHorizontalHeaderLabels(headers)
                table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
                table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                table.verticalHeader().setVisible(False)
                table.horizontalHeader().setStretchLastSection(True)
                table.setShowGrid(False)
                table.setFrameShape(QFrame.NoFrame)
                table.verticalHeader().setDefaultSectionSize(STATS_TABLE_ROW_H)
                table.verticalHeader().setMinimumSectionSize(STATS_TABLE_ROW_H)
                table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
                table.horizontalHeader().setSectionsClickable(True)
                table.horizontalHeader().setSortIndicatorShown(True)
                self._apply_stats_table_theme(table, _fs)
                _item_bg = QBrush(self._stats_table_colors()[0])
                _status_rank = {"error": 0, "warning": 1, "ok": 2}
                _queue_align = [
                    Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignLeft,
                    Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignRight,
                    Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignRight,
                    Qt.AlignmentFlag.AlignLeft,
                ]
                for ri, row in enumerate(_queue_rows):
                    _key, kind, ptr, label, holds, issues, avg, status_label, status, avg_ns, bounces = row[:11]
                    vals = [label, kind, str(holds), str(issues), str(bounces), avg, status_label]
                    sort_keys = [
                        label.lower(), kind.lower(), holds, issues, bounces,
                        avg_ns if avg_ns is not None else -1,
                        _status_rank.get(status, 3),
                    ]
                    for ci, val in enumerate(vals):
                        item = _StatsSortItem(val, sort_keys[ci])
                        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                        item.setBackground(_item_bg)
                        item.setTextAlignment(_queue_align[ci] | Qt.AlignmentFlag.AlignVCenter)
                        if ci == 4 and bounces > 0:
                            item.setForeground(QBrush(QColor("#F39C12")))
                        if ci == 6 and status != "ok":
                            color = "#E74C3C" if status == "error" else "#F39C12"
                            item.setForeground(QBrush(QColor(color)))
                        table.setItem(ri, ci, item)
                table.setSortingEnabled(True)
                self._wire_stats_table_row_hover(table)
                self._wrap_table_with_resizer(blay, table, "queue")

            self._add_collapsible_section(
                "queue",
                f"Queue{scope}",
                _fs,
                _populate_queue,
            )

        # -- Task Lifecycle -------------------------------------------------
        empty_lifecycle = ("No task lifecycle events in cursor range" if scope
                           else "No task create/delete/suspend/resume STI events in trace")

        def _populate_lifecycle(blay: QVBoxLayout) -> None:
            lc_rows = _task_lifecycle_rows(trace, lo, hi)
            if not lc_rows:
                blay.addWidget(self._lbl(empty_lifecycle, color="#888888", ui_fs=_fs))
                return
            ts = trace.time_scale
            headers = ["Task", "Created", "Deleted", "Susp/Res", "Alive", "Events", "Runs"]
            table = QTableWidget(len(lc_rows), len(headers))
            table.setHorizontalHeaderLabels(headers)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            table.verticalHeader().setVisible(False)
            table.setShowGrid(False)
            table.setFrameShape(QFrame.NoFrame)
            table.verticalHeader().setDefaultSectionSize(STATS_TABLE_ROW_H)
            table.verticalHeader().setMinimumSectionSize(STATS_TABLE_ROW_H)
            table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            table.horizontalHeader().setFixedHeight(18)
            table.horizontalHeader().setSectionsClickable(True)
            table.horizontalHeader().setSortIndicatorShown(True)
            _item_bg = self._apply_stats_table_theme(table, _fs)
            _lc_create_ns: Dict[str, Optional[int]] = {}
            for r, row in enumerate(lc_rows):
                mk, label, create_ns, delete_ns, susp, res, alive_ns, evt_count, run_count = row
                _lc_create_ns[mk] = create_ns
                def _cell(text: str, *, align=Qt.AlignmentFlag.AlignLeft) -> QTableWidgetItem:
                    it = _StatsSortItem(text)
                    it.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    it.setBackground(_item_bg)
                    return it
                _name_item = _cell(label)
                _name_item.setData(Qt.ItemDataRole.UserRole, mk)
                _name_item.setToolTip(f"Click to highlight \u2018{label}\u2019 in the timeline")
                table.setItem(r, 0, _name_item)
                table.setItem(r, 1, _cell(_format_time(create_ns, ts) if create_ns is not None else "—",
                                          align=Qt.AlignmentFlag.AlignRight))
                table.setItem(r, 2, _cell(_format_time(delete_ns, ts) if delete_ns is not None else "—",
                                          align=Qt.AlignmentFlag.AlignRight))
                _susres_item = _cell(f"{susp}/{res}", align=Qt.AlignmentFlag.AlignRight)
                _susres_item._sort_key = susp + res
                table.setItem(r, 3, _susres_item)
                table.setItem(r, 4, _cell(_format_time(alive_ns, ts) if alive_ns is not None else "—",
                                          align=Qt.AlignmentFlag.AlignRight))
                table.setItem(r, 5, _cell(str(evt_count), align=Qt.AlignmentFlag.AlignRight))
                table.setItem(r, 6, _cell(str(run_count), align=Qt.AlignmentFlag.AlignRight))
            table.setSortingEnabled(True)

            def _on_lifecycle_row(row: int, _col: int) -> None:
                item = table.item(row, 0)
                if item is None:
                    return
                mk = item.data(Qt.ItemDataRole.UserRole)
                if not mk:
                    return
                create_ns = _lc_create_ns.get(mk)
                if create_ns is not None:
                    self.segment_jump.emit(create_ns)
                self.task_clicked.emit(mk)

            table.cellClicked.connect(_on_lifecycle_row)
            self._wire_stats_table_click_cursor(table)
            self._wire_stats_table_row_hover(table)
            self._wrap_table_with_resizer(blay, table, "lifecycle")

        self._add_collapsible_section(
            "lifecycle",
            f"Task Lifecycle{scope}",
            _fs,
            _populate_lifecycle,
        )

        # -- Core affinity ------------------------------------------------
        def _populate_affinity(blay: QVBoxLayout) -> None:
            _aff_rows = _task_core_affinity_rows(
                trace, lo, hi, include_merge_key=True)
            if not _aff_rows:
                blay.addWidget(self._lbl(
                    "No affinity_set events found", color="#888888", ui_fs=_fs))
                return
            headers = ["Task", "Mask", "Observed Cores", "Violations"]
            tbl = QTableWidget(len(_aff_rows), len(headers))
            tbl.setHorizontalHeaderLabels(headers)
            tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            tbl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            tbl.verticalHeader().setVisible(False)
            tbl.setShowGrid(False)
            tbl.setFrameShape(QFrame.NoFrame)
            tbl.verticalHeader().setDefaultSectionSize(STATS_TABLE_ROW_H)
            tbl.verticalHeader().setMinimumSectionSize(STATS_TABLE_ROW_H)
            tbl.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            tbl.horizontalHeader().setFixedHeight(18)
            tbl.horizontalHeader().setSectionsClickable(True)
            tbl.horizontalHeader().setSortIndicatorShown(True)
            for r, (mk, label, mask_hex, obs_str, viol_str) in enumerate(_aff_rows):
                for c, (val, key) in enumerate([
                    (label, label),
                    (mask_hex, mask_hex),
                    (obs_str, obs_str),
                    (viol_str, viol_str),
                ]):
                    item = _StatsSortItem(val, key)
                    item.setTextAlignment(
                        (Qt.AlignmentFlag.AlignRight if c == 3 else Qt.AlignmentFlag.AlignLeft)
                        | Qt.AlignmentFlag.AlignVCenter)
                    if viol_str != "\u2014" and c == 3:
                        item.setForeground(QColor("#E85D5D"))
                    if c == 0:
                        item.setData(Qt.ItemDataRole.UserRole, mk)
                        item.setToolTip(
                            f"Click to highlight \u2018{label}\u2019 in the timeline")
                    tbl.setItem(r, c, item)
            tbl.setSortingEnabled(True)
            self._apply_stats_table_theme(tbl, _fs)

            def _on_affinity_row(row: int, _col: int) -> None:
                item = tbl.item(row, 0)
                if item is None:
                    return
                mk = item.data(Qt.ItemDataRole.UserRole)
                if mk:
                    self.task_clicked.emit(str(mk))

            tbl.cellClicked.connect(_on_affinity_row)
            self._wire_stats_table_click_cursor(tbl)
            self._wire_stats_table_row_hover(tbl)
            self._wrap_table_with_resizer(blay, tbl, "affinity")

        self._add_collapsible_section(
            "affinity",
            f"Core Affinity{scope}",
            _fs,
            _populate_affinity,
        )

        # -- Deadlines / CPU budget ------------------------------------------
        def _populate_deadline(blay: QVBoxLayout) -> None:
            has_config = self._cpu_budget_pct > 0 or bool(self._task_deadlines_ns)
            blay.addWidget(self._deadline_settings_link(_fs, configured=has_config))
            if not has_config:
                return
            viols = _deadline_violations(
                trace, self._cpu_budget_pct, self._task_deadlines_ns, lo, hi)
            sv = viols["slice_violations"]
            cv = viols["cpu_violations"]
            if not sv and not cv:
                blay.addWidget(self._lbl("No violations in scope", color="#888888", ui_fs=_fs))
            if sv:
                hdr_lbl = QLabel("Slice over deadline")
                hdr_lbl.setStyleSheet(f"font-weight:600; font-size:{_fs};")
                blay.addWidget(hdr_lbl)
                tbl_sv = QTableWidget(min(len(sv), 20), 4)
                tbl_sv.setHorizontalHeaderLabels(["Task", "Duration", "Limit", "Over by"])
                tbl_sv.verticalHeader().setVisible(False)
                tbl_sv.verticalHeader().setDefaultSectionSize(STATS_TABLE_ROW_H)
                tbl_sv.verticalHeader().setMinimumSectionSize(STATS_TABLE_ROW_H)
                tbl_sv.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
                tbl_sv.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                tbl_sv.setShowGrid(False)
                tbl_sv.setFrameShape(QFrame.NoFrame)
                tbl_sv.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                tbl_sv.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
                tbl_sv.horizontalHeader().setFixedHeight(18)
                tbl_sv.horizontalHeader().setSectionsClickable(True)
                tbl_sv.horizontalHeader().setSortIndicatorShown(True)
                for r_i, (lbl_v, dur, lim, over, mk, start_ns, seg, dur_tu, limit_tu) in enumerate(sv[:20]):
                    sort_keys = [lbl_v.lower(), dur_tu, limit_tu, dur_tu - limit_tu]
                    for c_i, (val, key) in enumerate(zip([lbl_v, dur, lim, over], sort_keys)):
                        item = _StatsSortItem(val, key)
                        item.setTextAlignment(
                            (Qt.AlignmentFlag.AlignLeft if c_i == 0 else Qt.AlignmentFlag.AlignRight)
                            | Qt.AlignmentFlag.AlignVCenter)
                        if c_i == 3:
                            item.setForeground(QColor("#E85D5D"))
                        if c_i == 0:
                            item.setData(Qt.ItemDataRole.UserRole, (mk, start_ns, seg, lim))
                            item.setToolTip(
                                f"Click to annotate \u2018{lbl_v}\u2019 deadline slice at "
                                f"{_format_time(start_ns, trace.time_scale)}")
                        tbl_sv.setItem(r_i, c_i, item)
                tbl_sv.horizontalHeader().setStretchLastSection(True)
                tbl_sv.setSortingEnabled(True)
                self._apply_stats_table_theme(tbl_sv, _fs)

                def _on_deadline_slice_row(row: int, _col: int) -> None:
                    item = tbl_sv.item(row, 0)
                    if item is None:
                        return
                    data = item.data(Qt.ItemDataRole.UserRole)
                    if not data:
                        return
                    mk, start_ns, seg, lim = data
                    note = _format_deadline_slice_note(trace, mk, seg, lim)
                    self.plot_point_clicked.emit(seg, int(start_ns), note)

                tbl_sv.cellClicked.connect(_on_deadline_slice_row)
                self._wire_stats_table_click_cursor(tbl_sv)
                self._wire_stats_table_row_hover(tbl_sv)
                blay.addWidget(tbl_sv)
            if cv:
                hdr_lbl2 = QLabel("CPU budget exceeded")
                hdr_lbl2.setStyleSheet(f"font-weight:600; font-size:{_fs};")
                blay.addWidget(hdr_lbl2)
                tbl_cv = QTableWidget(len(cv), 3)
                tbl_cv.setHorizontalHeaderLabels(["Task", "CPU %", "Budget"])
                tbl_cv.verticalHeader().setVisible(False)
                tbl_cv.verticalHeader().setDefaultSectionSize(STATS_TABLE_ROW_H)
                tbl_cv.verticalHeader().setMinimumSectionSize(STATS_TABLE_ROW_H)
                tbl_cv.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
                tbl_cv.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                tbl_cv.setShowGrid(False)
                tbl_cv.setFrameShape(QFrame.NoFrame)
                tbl_cv.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                tbl_cv.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
                tbl_cv.horizontalHeader().setFixedHeight(18)
                tbl_cv.horizontalHeader().setSectionsClickable(True)
                tbl_cv.horizontalHeader().setSortIndicatorShown(True)
                for r_i, (lbl_v, pct, bgt, mk, pct_raw, budget_raw) in enumerate(cv):
                    sort_keys = [lbl_v.lower(), float(pct_raw), float(budget_raw)]
                    for c_i, (val, key) in enumerate(zip([lbl_v, pct, bgt], sort_keys)):
                        item = _StatsSortItem(val, key)
                        item.setTextAlignment(
                            (Qt.AlignmentFlag.AlignLeft if c_i == 0 else Qt.AlignmentFlag.AlignRight)
                            | Qt.AlignmentFlag.AlignVCenter)
                        if c_i == 1:
                            item.setForeground(QColor("#E85D5D"))
                        if c_i == 0:
                            item.setData(Qt.ItemDataRole.UserRole, mk)
                            item.setToolTip(
                                f"Click to highlight \u2018{lbl_v}\u2019 in the timeline")
                        tbl_cv.setItem(r_i, c_i, item)
                tbl_cv.horizontalHeader().setStretchLastSection(True)
                tbl_cv.setSortingEnabled(True)
                self._apply_stats_table_theme(tbl_cv, _fs)

                def _on_cpu_budget_row(row: int, _col: int) -> None:
                    item = tbl_cv.item(row, 0)
                    if item is None:
                        return
                    mk = item.data(Qt.ItemDataRole.UserRole)
                    if mk:
                        self.task_clicked.emit(str(mk))

                tbl_cv.cellClicked.connect(_on_cpu_budget_row)
                self._wire_stats_table_click_cursor(tbl_cv)
                self._wire_stats_table_row_hover(tbl_cv)
                blay.addWidget(tbl_cv)

        self._add_collapsible_section(
            "deadline",
            f"Deadlines / CPU budget{scope}",
            _fs,
            _populate_deadline,
        )

        # -- Interval Analysis ------------------------------------------------
        empty_interval = ("No interval data in cursor range" if scope
                          else "No paired interval_start / interval_stop events in trace")

        def _populate_intervals(blay: QVBoxLayout) -> None:
            _interval_rows = _interval_stats_rows(trace, lo, hi)
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

        # -- Tag Analysis ---------------------------------------------------
        empty_tag = ("No tag samples in cursor range" if scope
                     else "No tag0_event … tag7_event STI samples in trace")

        def _populate_tags(blay: QVBoxLayout) -> None:
            _tag_rows = _tag_stats_rows(trace, lo, hi)
            blay.addWidget(self._build_stats_table(
                _tag_rows,
                _fs,
                empty_tag,
                count_header="Count",
                section_id="tags",
                on_row_click=lambda ch: self._open_tag_plot(trace, ch),
            ))

        self._add_collapsible_section(
            "tags",
            f"Tag Analysis{scope}",
            _fs,
            _populate_tags,
        )

        self._flush_pending_sections()
        self._ensure_scroll_tail()
        self._update_scroll_tail_height()
        self.relax_content_width()
        self._util_label_col_w = self._resolve_util_label_width(
            self._util_label_col_natural)
        for lbl in self.findChildren(_ElidedUtilLabel):
            lbl.set_column_width(self._util_label_col_w)
        QTimer.singleShot(0, self.sync_util_layout)
        self._schedule_deferred_section_populate()

    def _add_stats_table_cap_note(self, blay: QVBoxLayout, note: Optional[str],
                                  ui_fs: str) -> None:
        if note:
            blay.addWidget(self._lbl(note, color="#888888", ui_fs=ui_fs))

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
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

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
            "show_legend":       "true",
            "show_stats":        "true",
            "show_marks":        "true",
            "show_find":         "true",
            "show_ai":           "true",
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
        "app": {
            # Optional custom taskbar/dock icon (.png, .ico, .icns, .svg).
            # Relative paths resolve from the btf_viewer.py directory.
            "icon_path": "",
        },
        "analysis": {
            # Global CPU budget threshold (0 = off)
            "cpu_budget_pct": "0",
            # Newline-separated "TaskName=nanoseconds" entries for per-task deadlines
            "task_deadlines": "",
        },
        # Each preset keeps its own base URL / model / API key so switching
        # between them does not lose credentials. Empty means "preset default".
        "ai": dict(
            {
                "enabled": "true",
                "preset": "",
                "response_language": DEFAULT_AI_RESPONSE_LANGUAGE,
                "auto_apply": "false",
                "mcp_log": "false",
            },
            **{
                f"{_pid}_{_field}": ""
                for _pid, _label, _base, _model in AI_PRESETS
                for _field in AI_PRESET_FIELDS
            },
        ),
    }

    def __init__(self) -> None:
        self._cfg = configparser.ConfigParser(interpolation=None)
        self._dirty = False
        self._last_error: str = ""
        # Seed every section/key with the compiled defaults so callers always
        # get a valid value even when the rc file is absent or incomplete.
        for section, keys in self._DEFAULTS.items():
            self._cfg[section] = dict(keys)
        # Overlay with the user's saved file (absent keys keep their defaults).
        self._cfg.read(self.RC_PATH, encoding="utf-8")
        # Upgrade legacy plaintext AI API keys to enc1: blobs on first load.
        self._migrate_encrypt_ai_api_keys()
        # Write the default file on first run so the user can inspect/edit it.
        if not os.path.isfile(self.RC_PATH):
            self._flush()

    def _migrate_encrypt_ai_api_keys(self) -> None:
        """Rewrite plaintext ``[ai] *_api_key`` values as ``enc1:`` blobs."""
        if not self._cfg.has_section("ai"):
            return
        changed = False
        for key in list(self._cfg.options("ai")):
            if not is_ai_api_key_option("ai", key):
                continue
            raw = self._cfg.get("ai", key, fallback="")
            if not raw or is_encrypted_secret(raw):
                continue
            self._cfg.set("ai", key, encrypt_secret(raw))
            changed = True
        if changed:
            self._flush()

    @staticmethod
    def _encode_rc_value(section: str, key: str, value) -> str:
        text = "" if value is None else str(value)
        if is_ai_api_key_option(section, key) and text.strip():
            return encrypt_secret(text)
        return text

    # ------------------------------------------------------------------ I/O
    def _flush(self) -> None:
        """Write current state to disk immediately."""
        try:
            with open(self.RC_PATH, "w", encoding="utf-8") as fh:
                fh.write("# btf_viewer.rc - RTOS BTF Viewer settings\n")
                fh.write("# This file is managed automatically; you may edit it by hand.\n")
                fh.write(
                    "# [ai] *_api_key values are stored encrypted (enc1:…) for "
                    "this machine.\n\n"
                )
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
        raw = self._cfg.get(section, key, fallback=fallback)
        if is_ai_api_key_option(section, key):
            return decrypt_secret(raw)
        return raw

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
        self._cfg.set(section, key, self._encode_rc_value(section, key, value))
        if flush:
            self._flush()
        else:
            self._dirty = True

    def set_many(self, section: str, pairs: Dict[str, str], *, flush: bool = True) -> None:
        """Set multiple keys at once with a single disk flush."""
        if not self._cfg.has_section(section):
            self._cfg.add_section(section)
        for key, value in pairs.items():
            self._cfg.set(section, key, self._encode_rc_value(section, key, value))
        if flush:
            self._flush()
        else:
            self._dirty = True

    def prune_section(self, section: str, keep: int, *, flush: bool = True) -> None:
        """Remove the oldest entries from *section*, keeping at most *keep* entries."""
        if not self._cfg.has_section(section):
            return
        keys = self._cfg.options(section)
        if len(keys) > keep:
            for k in keys[:-keep]:
                self._cfg.remove_option(section, k)
            if flush:
                self._flush()
            else:
                self._dirty = True

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

    # Label sizes as multiples of the application UI font, so the dialog tracks
    # Settings → Appearance → UI / menus instead of hard-coded points.
    _TITLE_SCALE = 1.75
    _SECT_SCALE  = 0.85

    def __init__(self, parent, *, is_dark: bool,
                 ui_font_size: int = UI_FONT_SIZE):
        super().__init__(parent, Qt.WindowType.Dialog)
        self.setWindowTitle("About RTOS BTF Viewer")
        self.setModal(True)

        ui_font_size = max(6, min(int(ui_font_size), 24))
        self.setFont(_application_ui_font(ui_font_size))
        fm = QFontMetrics(self.font())

        def _fs(scale: float) -> str:
            return _ui_font_stylesheet_size(
                max(6, int(round(ui_font_size * scale))))

        body_fs  = _fs(1.0)
        title_fs = _fs(self._TITLE_SCALE)
        sect_fs  = _fs(self._SECT_SCALE)
        # Font-relative geometry so nothing clips when the UI font grows.
        font_scale = ui_font_size / UI_FONT_SIZE
        key_w = fm.horizontalAdvance("Tab / Shift+Tab") + 8
        self.setMinimumWidth(int(round(380 * font_scale)))

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
        hv.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        hv.setContentsMargins(24, 28, 24, 22)
        hv.setSpacing(8)

        icon_lbl = QLabel()
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        icon_lbl.setPixmap(_pixmap_from_embedded_app_icon(72))
        hv.addWidget(icon_lbl)

        name_lbl = QLabel("RTOS BTF Viewer")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        name_lbl.setObjectName("about_title")
        hv.addWidget(name_lbl)

        sub_lbl = QLabel(f"RTOS context-switch timeline visualiser  *  v{_APP_VERSION}")
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
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
                g.addWidget(kl, r, 0, Qt.AlignmentFlag.AlignTop)
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
            ("Runtime",   f"Python {sys.version_info.major}.{sys.version_info.minor}  *  PySide6 desktop application"),
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
        btn.setFixedSize(max(88, fm.horizontalAdvance("Close") + 44),
                         max(24, fm.height() + 14))
        btn.setDefault(True)
        btn.clicked.connect(self.accept)
        fh.addWidget(btn)
        root.addWidget(foot)

        # -- Scoped stylesheet ---------------------------------------------
        self.setStyleSheet(f"""
            QDialog                     {{ background:{bg}; }}
            QWidget#about_hdr           {{ background:{hdr_bg}; }}
            QLabel#about_title          {{ color:{title_c}; font-size:{title_fs};
                                           font-weight:700; }}
            QLabel#about_sub            {{ color:{sub_c}; font-size:{body_fs}; }}
            QLabel#about_sect           {{ color:{sect_c}; font-size:{sect_fs};
                                           font-weight:700; letter-spacing:1px;
                                           margin-bottom:2px; }}
            QLabel#about_key            {{ color:{key_c}; font-size:{body_fs};
                                           font-weight:600; min-width:{key_w}px; }}
            QLabel#about_body           {{ color:{body_c}; font-size:{body_fs}; }}
            QFrame#about_block          {{ background:{blk_bg}; border:1px solid {blk_bd};
                                           border-radius:8px; }}
            QFrame#about_sep            {{ border:none; background:{sep_c};
                                           max-height:1px; }}
            QPushButton#about_btn       {{ background:{btn_bg}; color:{btn_txt};
                                           border:none; border-radius:5px;
                                           font-size:{body_fs}; font-weight:600;
                                           padding:0px 22px; }}
            QPushButton#about_btn:hover {{ background:{btn_hov}; }}
        """)

        self.adjustSize()

        # Match the web app's visual proportion: slightly wider, less tall.
        # Target ratio is width / height ~= 1.28.
        _target_ratio = 1.28
        _w = max(int(round(520 * font_scale)),
                 min(int(round(640 * font_scale)), self.sizeHint().width()))
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
    live_preview = Signal()

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
                 show_find: bool = True,
                 show_ai: bool = True,
                 show_hover_highlight: bool,
                 zoom_unit: str,
                 label_width: int, row_height: int, row_gap: int,
                 sti_row_h: int, sti_waveform_h: int, sti_line_style: str,
                 timescale_per_px_default: float,
                 is_dark: bool,
                 cpu_load_row_h: int = CPU_LOAD_ROW_H,
                 cpu_load: bool = True,
                 colorblind_safe: bool = False,
                 cpu_budget_pct: float = 0.0,
                 task_deadlines_text: str = "",
                 time_decimals: int = 3,
                 ai_enabled: bool = True,
                 ai_preset: str = DEFAULT_AI_PRESET,
                 ai_preset_settings: Optional[Dict[str, Dict[str, str]]] = None,
                 response_language: str = DEFAULT_AI_RESPONSE_LANGUAGE,
                 ai_auto_apply: bool = False,
                 ai_mcp_log: bool = False,
                 initial_page: str = "Appearance"):
        super().__init__(parent, Qt.WindowType.Dialog)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumSize(640, 400)

        # Defer heavy live-preview work until the current widget event
        # (e.g. combo popup close) has finished to keep selection responsive.
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(0)
        self._preview_timer.timeout.connect(self.live_preview.emit)

        _ui_fs = _ui_font_stylesheet_size(ui_font_size)

        # Set an explicit font on the dialog so every child widget (including
        # QListWidget which uses native rendering on macOS and ignores CSS
        # font-size) inherits the correct point size consistently regardless
        # of which app-level theme was applied most recently.
        _dlg_font = _application_ui_font(ui_font_size)
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
        self._sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._sidebar.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        _item_h = max(36, int(ui_font_size * 2.6))   # scale row height with font
        for _name in ("Appearance", "Display", "Layout", "AI"):
            _item = QListWidgetItem(_name)
            _item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
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

        def _wide_combo(combo: QComboBox, labels, *, min_w: int = 240) -> QComboBox:
            """Combo wide enough for long AI labels (not _INPUT_W=110)."""
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            fm = combo.fontMetrics()
            texts = [str(s) for s in labels if s]
            w = max((fm.horizontalAdvance(s) for s in texts), default=120) + 56
            w = max(w, min_w)
            combo.setMinimumWidth(w)
            combo.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            try:
                combo.view().setMinimumWidth(w)
            except Exception:
                pass
            return combo

        def _form(page: QWidget) -> QFormLayout:
            f = QFormLayout(page)
            f.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
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
        self._font_spin.setToolTip(
            "Font size for task / core labels drawn on the timeline "
            "(Qt points, HiDPI-scaled). The web viewer uses CSS pixels; "
            "defaults look similar, numbers are not interchangeable.")
        f1.addRow("Timeline labels:", _inp(self._font_spin))

        self._ui_font_spin = QSpinBox()
        self._ui_font_spin.setRange(8, 18)
        self._ui_font_spin.setSuffix(" pt")
        self._ui_font_spin.setValue(ui_font_size)
        self._ui_font_spin.setToolTip(
            "Font size for menus, toolbar and status bar (Qt points). "
            "The web viewer uses CSS pixels.")
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
        self._find_cb = QCheckBox("Find panel")
        self._find_cb.setChecked(show_find)
        self._ai_cb = QCheckBox("AI Assistant panel")
        self._ai_cb.setChecked(show_ai)
        v2.addWidget(self._indented(self._legend_cb))
        v2.addWidget(self._indented(self._stats_cb))
        v2.addWidget(self._indented(self._marks_cb))
        v2.addWidget(self._indented(self._find_cb))
        v2.addWidget(self._indented(self._ai_cb))
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
        v2.addWidget(self._indented(self._sti_cb))
        v2.addWidget(self._indented(self._grid_cb))
        v2.addWidget(self._indented(self._hover_hl_cb))

        v2.addSpacing(6)
        v2.addWidget(self._hline())
        v2.addSpacing(2)

        v2.addWidget(self._section("Analysis thresholds"))

        _budget_row = QWidget()
        _budget_h = QHBoxLayout(_budget_row)
        _budget_h.setContentsMargins(0, 0, 0, 0)
        _budget_h.setSpacing(8)
        _budget_h.addWidget(QLabel("CPU budget (0 = off):"))
        self._cpu_budget_spin = QDoubleSpinBox()
        self._cpu_budget_spin.setRange(0, 100)
        self._cpu_budget_spin.setSingleStep(0.1)
        self._cpu_budget_spin.setDecimals(1)
        self._cpu_budget_spin.setSuffix("%")
        self._cpu_budget_spin.setValue(cpu_budget_pct)
        self._cpu_budget_spin.setFixedWidth(self._INPUT_W)
        self._cpu_budget_spin.setToolTip(
            "Global CPU budget threshold: tasks consuming more than this\n"
            "percentage of CPU time in the current scope will be flagged.\n"
            "Set to 0 to disable.")
        _budget_h.addWidget(self._cpu_budget_spin)
        _budget_h.addStretch()
        v2.addWidget(self._indented(_budget_row))

        v2.addWidget(self._indented(QLabel("Task deadlines (ns):")))
        self._task_deadlines_edit = QPlainTextEdit()
        self._task_deadlines_edit.setPlaceholderText(
            "One entry per line:\n  TaskName=nanoseconds\n\nExample:\n  Runner1=1000000\n  Worker=500000")
        self._task_deadlines_edit.setFixedHeight(100)
        self._task_deadlines_edit.setPlainText(task_deadlines_text)
        self._task_deadlines_edit.setToolTip(
            "Per-task execution deadline in nanoseconds.\n"
            "Any execution slice longer than the limit will be flagged.\n"
            "Use the task display name (e.g. 'Runner1') or 'TaskName[id]' form.")
        v2.addWidget(self._indented(self._task_deadlines_edit))

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

        self._time_decimals_spin = QSpinBox()
        self._time_decimals_spin.setRange(0, 9)
        self._time_decimals_spin.setValue(time_decimals)
        self._time_decimals_spin.setToolTip(
            "Decimal-digit precision for times shown throughout the UI "
            "(tooltips, cursors, bookmarks, status bar, etc.) (0\u20139)")
        f3.addRow("Time display precision:", _inp(self._time_decimals_spin))

        f3.addRow(self._hline())
        f3.addRow("", self._section("CPU Load Graph"))

        self._cpu_row_h_spin = QSpinBox()
        self._cpu_row_h_spin.setRange(16, 120)
        self._cpu_row_h_spin.setSuffix(" px")
        self._cpu_row_h_spin.setValue(cpu_load_row_h)
        self._cpu_row_h_spin.setToolTip("Height of each CPU load row (16\u2013120 px) \u2014 independent of timeline row height")
        f3.addRow("Row height:", _inp(self._cpu_row_h_spin))

        self._content_stack.addWidget(p3)

        # -- Page 4: AI --------------------------------------------------------
        p4 = QWidget()
        f4 = _form(p4)
        # URLs / long combo labels need room; fixed-width spins on other pages
        # stay narrow via _inp().
        f4.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._ai_enabled_cb = QCheckBox("Enable AI Assistant")
        self._ai_enabled_cb.setChecked(ai_enabled)
        self._ai_enabled_cb.setToolTip(
            "When off, hides the AI tab. When on, the AI panel can send "
            "Analysis Findings to the configured endpoint.")
        f4.addRow("", self._ai_enabled_cb)
        self._ai_auto_apply_cb = QCheckBox("Auto-apply GUI actions")
        self._ai_auto_apply_cb.setChecked(bool(ai_auto_apply))
        self._ai_auto_apply_cb.setToolTip(
            "When on, tool calls from the model update the timeline immediately. "
            "When off, the chat shows Apply / Skip on each action card.")
        f4.addRow("", self._ai_auto_apply_cb)
        self._ai_mcp_log_cb = QCheckBox("Log MCP messages to file")
        self._ai_mcp_log_cb.setChecked(bool(ai_mcp_log))
        self._ai_mcp_log_cb.setToolTip(
            f"Debugging only. Appends to ./{AI_MCP_LOG_FILENAME} (can grow large).")
        f4.addRow("", self._ai_mcp_log_cb)
        _mcp_log_note = QLabel(
            f"Debugging only — appends to ./{AI_MCP_LOG_FILENAME} (can grow large).")
        _mcp_log_note.setWordWrap(True)
        _mcp_log_note.setStyleSheet("color:#888;")
        f4.addRow("", self._indented(_mcp_log_note))

        # Field values per preset; switching presets stashes the current inputs
        # so credentials survive a round trip.
        self._ai_preset_values: Dict[str, Dict[str, str]] = {}
        for _pid, _label, _base, _model in AI_PRESETS:
            stored = dict((ai_preset_settings or {}).get(_pid) or {})
            base = str(stored.get("base_url", "") or _base)
            self._ai_preset_values[_pid] = {
                "base_url": base,
                "model": str(stored.get("model", "") or _model),
                "api_key": str(stored.get("api_key", "") or ""),
                "auth_mode": normalize_ai_auth_mode(
                    stored.get("auth_mode", ""),
                    preset_id=_pid,
                    base_url=base,
                ),
                "tls_verify": format_ai_tls_verify(stored.get("tls_verify", "")),
            }

        self._ai_preset_combo = QComboBox()
        for _pid, _label, _base, _model in AI_PRESETS:
            self._ai_preset_combo.addItem(_label, _pid)
        self._ai_preset_combo.setCurrentIndex(
            max(0, self._ai_preset_combo.findData(normalize_ai_preset(ai_preset))))
        self._ai_preset_combo.setToolTip(
            "Ollama runs locally; OpenAI and Gemini are cloud APIs; Custom is "
            "any other OpenAI-compatible endpoint. Each preset keeps its own "
            "base URL, model, and API key.")
        _wide_combo(
            self._ai_preset_combo,
            [lab for _pid, lab, _u, _m in AI_PRESETS],
            min_w=240,
        )
        f4.addRow("Preset:", self._ai_preset_combo)

        self._ai_url_edit = QLineEdit()
        self._ai_url_edit.setPlaceholderText(DEFAULT_AI_BASE_URL)
        self._ai_url_edit.setToolTip(
            "OpenAI-compatible API root, e.g. http://localhost:11434/v1 for Ollama.")
        self._ai_url_edit.setMinimumWidth(280)
        f4.addRow("Base URL:", self._ai_url_edit)

        self._ai_model_lists: Dict[str, List[str]] = {
            _pid: [] for _pid, _lab, _u, _m in AI_PRESETS
        }
        self._ai_model_combo = QComboBox()
        self._ai_model_combo.setEditable(True)
        self._ai_model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._ai_model_combo.setToolTip(
            "Model id served by that endpoint (e.g. `ollama list` name, "
            "gpt-4o-mini, or gemini-flash-lite-latest). Refresh to list "
            "models from GET /models.")
        _wide_combo(self._ai_model_combo, [DEFAULT_AI_MODEL], min_w=240)
        _ic = "#AAAAAA" if is_dark else "#555555"
        self._ai_model_refresh = QToolButton()
        self._ai_model_refresh.setAutoRaise(True)
        self._ai_model_refresh.setIcon(_svg_icon(_IC_REFRESH, _ic, 14))
        self._ai_model_refresh.setIconSize(QSize(14, 14))
        self._ai_model_refresh.setFixedSize(26, 26)
        self._ai_model_refresh.setToolTip("Refresh model list from this endpoint")
        self._ai_model_refresh.clicked.connect(self._refresh_ai_models)
        _model_row = QWidget()
        _model_h = QHBoxLayout(_model_row)
        _model_h.setContentsMargins(0, 0, 0, 0)
        _model_h.setSpacing(6)
        _model_h.addWidget(self._ai_model_combo, 1)
        _model_h.addWidget(self._ai_model_refresh, 0)
        f4.addRow("Model:", _model_row)

        self._ai_auth_combo = QComboBox()
        for _mode, _mlabel in AI_AUTH_MODE_LABELS:
            self._ai_auth_combo.addItem(_mlabel, _mode)
        self._ai_auth_combo.setToolTip(
            "How this preset authenticates. None for a local server; API key "
            "to paste a provider key; Sign in opens the vendor page so you can "
            "log in and paste the key or token.")
        _wide_combo(
            self._ai_auth_combo,
            [lab for _m, lab in AI_AUTH_MODE_LABELS],
            min_w=200,
        )
        f4.addRow("Authentication:", self._ai_auth_combo)

        self._ai_cred_wrap = QWidget()
        _cred = QVBoxLayout(self._ai_cred_wrap)
        _cred.setContentsMargins(0, 0, 0, 0)
        _cred.setSpacing(6)
        self._ai_auth_status = QLabel("")
        self._ai_auth_status.setWordWrap(True)
        self._ai_auth_status.setStyleSheet("color:#888;")
        _cred.addWidget(self._ai_auth_status)
        self._ai_api_key_edit = QLineEdit()
        self._ai_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._ai_api_key_edit.setToolTip(
            "API key or access token for this preset (or OPENAI_API_KEY / "
            "GEMINI_API_KEY / OLLAMA_API_KEY in the environment). Local Ollama "
            "needs none. Stored per preset in btf_viewer.rc.")
        _cred.addWidget(self._ai_api_key_edit)
        _auth_btns = QWidget()
        _auth_h = QHBoxLayout(_auth_btns)
        _auth_h.setContentsMargins(0, 0, 0, 0)
        _auth_h.setSpacing(8)
        self._ai_signin_btn = QPushButton("Sign in…")
        self._ai_signin_btn.setToolTip(
            "Open the provider sign-in or API-key page in your browser, then "
            "paste the key or token above.")
        self._ai_signin_btn.clicked.connect(self._ai_open_signin)
        self._ai_logout_btn = QPushButton("Log out")
        self._ai_logout_btn.setToolTip("Clear the saved key or token for this preset.")
        self._ai_logout_btn.clicked.connect(self._ai_logout)
        _auth_h.addWidget(self._ai_signin_btn)
        _auth_h.addWidget(self._ai_logout_btn)
        _auth_h.addStretch()
        _cred.addWidget(_auth_btns)
        self._ai_cred_label = QLabel("API key:")
        f4.addRow(self._ai_cred_label, self._ai_cred_wrap)
        self._ai_auth_combo.currentIndexChanged.connect(self._on_ai_auth_mode_changed)

        self._ai_insecure_tls_cb = QCheckBox("Allow self-signed TLS")
        self._ai_insecure_tls_cb.setToolTip(
            "Skip HTTPS certificate checks for this preset (self-signed or "
            "private CA). Use only on networks you trust. Browsers cannot "
            "skip this check — trust the cert in the OS, use http:// on a "
            "private LAN, or use this Desktop app.")
        f4.addRow("", self._ai_insecure_tls_cb)

        self._response_lang_combo = QComboBox()
        self._response_lang_combo.addItems(list(AI_RESPONSE_LANGUAGES))
        _lang = (response_language or DEFAULT_AI_RESPONSE_LANGUAGE).strip()
        _idx = self._response_lang_combo.findText(_lang)
        if _idx < 0:
            self._response_lang_combo.addItem(_lang)
            _idx = self._response_lang_combo.findText(_lang)
        self._response_lang_combo.setCurrentIndex(max(0, _idx))
        self._response_lang_combo.setToolTip(
            "Language for AI Assistant replies (also available via Language… in the AI panel).")
        _wide_combo(
            self._response_lang_combo,
            list(AI_RESPONSE_LANGUAGES) + ([_lang] if _lang else []),
            min_w=280,
        )
        f4.addRow("Reply language:", self._response_lang_combo)

        _test_row = QWidget()
        _test_h = QHBoxLayout(_test_row)
        _test_h.setContentsMargins(0, 0, 0, 0)
        _test_h.setSpacing(8)
        self._ollama_test_btn = QPushButton("Test connection")
        self._ollama_test_btn.setToolTip(
            "List models and run a tiny chat probe against this endpoint. "
            "Status updates appear below — first model load can take a couple of minutes.")
        self._ollama_test_btn.clicked.connect(self._test_ollama_connection)
        _test_h.addWidget(self._ollama_test_btn)
        self._ai_import_btn = QPushButton("Import…")
        self._ai_import_btn.setToolTip(
            "Load preset, base URL, model, and API key from a JSON file "
            "(see examples/ai/ollama.json, gemini.json, openai.json, "
            "deepseek.json, grok.json, presets.json).")
        self._ai_import_btn.clicked.connect(self._import_ai_settings)
        _test_h.addWidget(self._ai_import_btn)
        _test_h.addStretch()
        f4.addRow("", _test_row)

        self._ollama_test_status = QLabel(
            "Click Test connection to verify the endpoint and model.")
        self._ollama_test_status.setWordWrap(True)
        self._ollama_test_status.setMinimumHeight(40)
        self._ollama_test_status.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._ollama_test_status.setStyleSheet(
            "color:#888; padding:4px 0; min-height:40px;")
        f4.addRow(self._ollama_test_status)

        self._ai_hint = QLabel("")
        self._ai_hint.setWordWrap(True)
        self._ai_hint.setStyleSheet("color:#888;")
        f4.addRow(self._ai_hint)

        self._ai_active_preset = normalize_ai_preset(ai_preset)
        self._load_ai_preset_fields(self._ai_active_preset)
        self._ai_preset_combo.currentIndexChanged.connect(self._on_ai_preset_changed)

        self._ollama_test_worker = None
        self._ai_list_worker = None

        self._content_stack.addWidget(p4)

        # -- Sidebar <-> stack sync ---------------------------------------------
        self._sidebar.currentRowChanged.connect(self._content_stack.setCurrentIndex)
        _page_idx = {"Appearance": 0, "Display": 1, "Layout": 2, "AI": 3}.get(initial_page, 0)
        self._sidebar.setCurrentRow(_page_idx)
        self._content_stack.setCurrentIndex(_page_idx)

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
            self._find_cb.stateChanged,
            self._ai_cb.stateChanged,
            self._cpu_load_cb.stateChanged,
            self._hover_hl_cb.stateChanged,
            self._label_width_spin.valueChanged,
            self._row_height_spin.valueChanged,
            self._row_gap_spin.valueChanged,
            self._sti_row_h_spin.valueChanged,
            self._sti_waveform_h_spin.valueChanged,
            self._sti_line_style_combo.currentIndexChanged,
            self._timescale_per_px_spin.valueChanged,
            self._cpu_row_h_spin.valueChanged,
            self._time_decimals_spin.valueChanged,
        ):
            _sig.connect(self._schedule_live_preview)

        self.adjustSize()

    # -- Reset all controls to built-in defaults ---------------------------
    def _stash_ai_preset_fields(self) -> None:
        """Remember the typed values for the preset currently shown."""
        self._ai_preset_values[self._ai_active_preset] = {
            "base_url": self._ai_url_edit.text().strip(),
            "model": self._ai_model_text(),
            "api_key": self._ai_api_key_edit.text().strip(),
            "auth_mode": normalize_ai_auth_mode(
                self._ai_auth_combo.currentData(),
                preset_id=self._ai_active_preset,
                base_url=self._ai_url_edit.text().strip(),
            ),
            "tls_verify": format_ai_tls_verify(
                not self._ai_insecure_tls_cb.isChecked()),
        }

    def _ai_model_text(self) -> str:
        return self._ai_model_combo.currentText().strip()

    def _set_ai_model_text(self, text: str) -> None:
        names = list(self._ai_model_lists.get(self._ai_active_preset) or [])
        self._fill_ai_model_combo(names, text)

    def _fill_ai_model_combo(self, names: Sequence[str], current: str) -> None:
        combo = self._ai_model_combo
        current = str(current or "").strip()
        seen: List[str] = []
        for n in names:
            s = str(n or "").strip()
            if s and s not in seen:
                seen.append(s)
        if current and current not in seen:
            seen.insert(0, current)
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(seen)
        if current:
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.setEditText(current)
        else:
            combo.setCurrentIndex(-1)
            combo.setEditText("")
        combo.blockSignals(False)
        le = combo.lineEdit()
        if le is not None:
            _pid, _lab, _b, def_model = ai_preset_info(self._ai_active_preset)
            le.setPlaceholderText(def_model or DEFAULT_AI_MODEL)

    def _load_ai_preset_fields(self, preset: str) -> None:
        _pid, label, def_base, def_model = ai_preset_info(preset)
        vals = self._ai_preset_values.get(_pid, {})
        base = vals.get("base_url", "") or def_base
        self._ai_url_edit.setText(base)
        self._set_ai_model_text(vals.get("model", "") or def_model)
        self._ai_api_key_edit.setText(vals.get("api_key", ""))
        self._ai_url_edit.setPlaceholderText(def_base or DEFAULT_AI_BASE_URL)
        mode = normalize_ai_auth_mode(
            vals.get("auth_mode", ""), preset_id=_pid, base_url=base)
        idx = self._ai_auth_combo.findData(mode)
        self._ai_auth_combo.blockSignals(True)
        self._ai_auth_combo.setCurrentIndex(max(0, idx))
        self._ai_auth_combo.blockSignals(False)
        self._ai_insecure_tls_cb.setChecked(
            not parse_ai_tls_verify(vals.get("tls_verify", ""), default=True))
        self._update_ai_auth_ui()

    def _on_ai_auth_mode_changed(self, *_args) -> None:
        self._update_ai_auth_ui()

    def _update_ai_auth_ui(self) -> None:
        _pid, label, def_base, _def_model = ai_preset_info(self._ai_active_preset)
        base = self._ai_url_edit.text().strip() or def_base
        mode = normalize_ai_auth_mode(
            self._ai_auth_combo.currentData(), preset_id=_pid, base_url=base)
        key = self._ai_api_key_edit.text().strip()
        status = ai_auth_status(
            auth_mode=mode, api_key=key, base_url=base, preset_id=_pid)
        show_cred = mode != AI_AUTH_NONE
        self._ai_cred_wrap.setVisible(show_cred)
        self._ai_cred_label.setVisible(show_cred)
        self._ai_cred_label.setText(
            "Token:" if mode == AI_AUTH_BROWSER else "API key:")
        self._ai_signin_btn.setVisible(mode == AI_AUTH_BROWSER)
        self._ai_signin_btn.setText(ai_preset_signin_label(_pid))
        self._ai_logout_btn.setVisible(mode == AI_AUTH_BROWSER and bool(key))
        if mode == AI_AUTH_NONE:
            self._ai_auth_status.setText("Local endpoint — no key needed.")
            self._ai_api_key_edit.setPlaceholderText(
                "Optional — local Ollama needs none")
        elif mode == AI_AUTH_BROWSER:
            self._ai_auth_status.setText(
                "Signed in — token saved." if status["signed_in"]
                else "Not signed in. Open the provider page, then paste the "
                "key or token below.")
            self._ai_api_key_edit.setPlaceholderText(
                "Paste key or token after signing in")
        else:
            self._ai_auth_status.setText(
                "Key saved for this preset." if key
                else "Paste a provider API key, or set OPENAI_API_KEY / "
                "GEMINI_API_KEY in the environment.")
            self._ai_api_key_edit.setPlaceholderText(
                "Required — provider API key")
        if _pid == AI_PRESET_OLLAMA and mode == AI_AUTH_NONE:
            self._ai_hint.setText(
                f"Install Ollama and pull a model (`ollama pull {DEFAULT_AI_MODEL}`); "
                "the viewer talks to its OpenAI-compatible endpoint. Context is "
                "Analysis Findings for the current Statistics scope — not the raw BTF."
            )
        else:
            key_url = AI_PRESET_KEY_URLS.get(_pid, "") or ai_preset_signin_url(
                _pid, base)
            where = f" ({label} keys come from {key_url})" if key_url else ""
            if mode == AI_AUTH_BROWSER:
                self._ai_hint.setText(
                    f"Sign in opens the {label} page in your browser. Paste the "
                    f"issued key or token here, then Test connection.{where} "
                    "Context is Analysis Findings — not the raw BTF."
                )
            else:
                self._ai_hint.setText(
                    f"{label} is an OpenAI-compatible endpoint: set Base URL, model, "
                    f"and an API key{where}. Context is Analysis Findings for the "
                    "current Statistics scope — not the raw BTF."
                )

    def _ai_open_signin(self) -> None:
        _pid, _label, def_base, _m = ai_preset_info(self._ai_active_preset)
        url = ai_preset_signin_url(
            _pid, self._ai_url_edit.text().strip() or def_base)
        if not url:
            self._set_ai_status(
                "This preset has no sign-in page. Paste a token or set Base URL.",
                "error")
            return
        QDesktopServices.openUrl(QUrl(url))
        self._set_ai_status(
            f"Opened {url}. After you sign in, paste the key or token and Test.")

    def _ai_logout(self) -> None:
        self._ai_api_key_edit.clear()
        self._update_ai_auth_ui()
        self._set_ai_status("Cleared the saved token for this preset.")

    def _on_ai_preset_changed(self, *_args) -> None:
        self._stash_ai_preset_fields()
        self._ai_active_preset = normalize_ai_preset(
            self._ai_preset_combo.currentData())
        self._load_ai_preset_fields(self._ai_active_preset)

    def _set_ai_status(self, message: str, kind: str = "info") -> None:
        color = {"ok": "#1e8449", "error": "#c0392b"}.get(kind, "#888")
        self._ollama_test_status.setStyleSheet(
            f"color:{color}; padding:4px 0; min-height:40px;")
        self._ollama_test_status.setText(message)

    def apply_ai_settings_patch(self, patch: Dict[str, str]) -> str:
        """Apply an imported settings patch to the AI page; return a summary."""
        # Keep whatever is typed for the visible preset — the file may name
        # a different one.
        self._stash_ai_preset_fields()
        touched: List[str] = []
        for pid, label, _base, _model in AI_PRESETS:
            vals = dict(self._ai_preset_values.get(pid, {}))
            changed = False
            for field in AI_PRESET_FIELDS:
                value = patch.get(f"{pid}_{field}")
                if value:
                    vals[field] = value
                    changed = True
            if changed:
                self._ai_preset_values[pid] = vals
                touched.append(label)
        language = patch.get("response_language", "")
        if language:
            idx = self._response_lang_combo.findText(language)
            if idx < 0:
                self._response_lang_combo.addItem(language)
                idx = self._response_lang_combo.findText(language)
            self._response_lang_combo.setCurrentIndex(max(0, idx))
        preset = normalize_ai_preset(patch.get("preset") or self._ai_active_preset)
        self._ai_active_preset = preset
        self._ai_preset_combo.blockSignals(True)
        self._ai_preset_combo.setCurrentIndex(
            max(0, self._ai_preset_combo.findData(preset)))
        self._ai_preset_combo.blockSignals(False)
        self._load_ai_preset_fields(preset)
        return (
            f"Imported {', '.join(touched) or 'settings'}. "
            f"Selected {ai_preset_info(preset)[1]} — review, then OK to save."
        )

    def _import_ai_settings(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import AI settings", "",
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                patch = parse_ai_settings_json(fh.read())
        except (OSError, ValueError) as exc:
            self._set_ai_status(
                f"Cannot import {os.path.basename(path)}: {exc}", "error")
            return
        self._set_ai_status(self.apply_ai_settings_patch(patch), "ok")

    def _ai_test_target(self) -> Tuple[str, str, str, bool]:
        """Typed fields, falling back to the active preset's defaults."""
        _pid, _label, def_base, def_model = ai_preset_info(self._ai_active_preset)
        return (
            self._ai_url_edit.text().strip() or def_base,
            self._ai_model_text() or def_model,
            self._ai_api_key_edit.text().strip(),
            not self._ai_insecure_tls_cb.isChecked(),
        )

    def _refresh_ai_models(self) -> None:
        """Fetch ``GET /models`` into the Model combo."""
        if self._ai_list_worker is not None or self._ollama_test_worker is not None:
            return
        url, _model, api_key, tls_verify = self._ai_test_target()
        self._ai_model_refresh.setEnabled(False)
        self._set_ai_status(f"Listing models at {url}…")
        worker = _AiListModelsWorker(
            self,
            base_url=url,
            api_key=api_key,
            tls_verify=tls_verify,
            log_mcp=self._ai_mcp_log_cb.isChecked(),
        )
        worker.finished.connect(
            self._on_ai_models_ok, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(
            self._on_ai_models_err, Qt.ConnectionType.QueuedConnection)
        self._ai_list_worker = worker
        worker.start()

    def _on_ai_models_ok(self, names: object) -> None:
        listed = [str(n) for n in (names or []) if n]
        listed.sort(key=str.lower)
        self._ai_model_lists[self._ai_active_preset] = listed
        current = self._ai_model_text()
        self._fill_ai_model_combo(listed, current)
        if listed:
            self._set_ai_status(
                f"{len(listed)} model(s) from the endpoint. "
                "Open the Model dropdown to pick one.",
                "ok")
            QTimer.singleShot(0, self._ai_model_combo.showPopup)
        else:
            self._set_ai_status("Endpoint listed no models.", "error")
        self._cleanup_ai_list_worker()

    def _on_ai_models_err(self, msg: str) -> None:
        self._set_ai_status(msg or "Cannot list models.", "error")
        self._cleanup_ai_list_worker()

    def _cleanup_ai_list_worker(self) -> None:
        self._ai_model_refresh.setEnabled(True)
        worker = self._ai_list_worker
        self._ai_list_worker = None
        if worker is not None:
            try:
                worker.finished.disconnect(self._on_ai_models_ok)
                worker.failed.disconnect(self._on_ai_models_err)
            except (TypeError, RuntimeError):
                pass
            worker.deleteLater()

    def _test_ollama_connection(self) -> None:
        """Test the configured endpoint with the typed Settings fields."""
        if self._ollama_test_worker is not None or self._ai_list_worker is not None:
            return
        url, model, api_key, tls_verify = self._ai_test_target()
        self._ollama_test_btn.setEnabled(False)
        self._ai_model_refresh.setEnabled(False)
        self._ollama_test_btn.setText("Testing…")
        self._set_ai_status(f"Starting test for {url} / {model}…")

        worker = _AiTestWorker(
            self,
            base_url=url,
            model_name=model,
            api_key=api_key,
            tls_verify=tls_verify,
            log_mcp=self._ai_mcp_log_cb.isChecked(),
        )
        # QueuedConnection: signals are emitted from a plain Python thread.
        worker.progress.connect(
            self._on_ollama_test_progress, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(
            self._on_ollama_test_ok, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(
            self._on_ollama_test_err, Qt.ConnectionType.QueuedConnection)
        self._ollama_test_worker = worker
        worker.start()

    def _on_ollama_test_progress(self, msg: str) -> None:
        self._set_ai_status(msg)

    def _on_ollama_test_ok(self, msg: str) -> None:
        self._set_ai_status(msg, "ok")
        self._cleanup_ollama_test()

    def _on_ollama_test_err(self, msg: str) -> None:
        self._set_ai_status(msg or "Connection test failed.", "error")
        self._cleanup_ollama_test()

    def _cleanup_ollama_test(self) -> None:
        self._ollama_test_btn.setEnabled(True)
        self._ai_model_refresh.setEnabled(True)
        self._ollama_test_btn.setText("Test connection")
        worker = self._ollama_test_worker
        self._ollama_test_worker = None
        if worker is not None:
            try:
                worker.progress.disconnect(self._on_ollama_test_progress)
                worker.finished.disconnect(self._on_ollama_test_ok)
                worker.failed.disconnect(self._on_ollama_test_err)
            except (TypeError, RuntimeError):
                pass
            worker.deleteLater()

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
        self._find_cb.setChecked(True)
        self._ai_cb.setChecked(True)
        self._cpu_load_cb.setChecked(True)
        self._hover_hl_cb.setChecked(_HOVER_HIGHLIGHT_ENABLED)
        self._label_width_spin.setValue(LABEL_WIDTH)
        self._row_height_spin.setValue(ROW_HEIGHT)
        self._row_gap_spin.setValue(ROW_GAP)
        self._sti_row_h_spin.setValue(STI_ROW_H)
        self._sti_waveform_h_spin.setValue(STI_WAVEFORM_H)
        self._sti_line_style_combo.setCurrentIndex(1 if STI_LINE_STYLE == "linear" else 0)
        self._timescale_per_px_spin.setValue(_TIMESCALE_PER_PX_DEFAULT)
        self._cursor_spin.setValue(_DEFAULT_MAX_CURSORS)
        self._cpu_row_h_spin.setValue(CPU_LOAD_ROW_H)
        self._cpu_budget_spin.setValue(0.0)
        self._task_deadlines_edit.setPlainText("")
        self._time_decimals_spin.setValue(_DEFAULT_TIME_DECIMALS)
        self._ai_enabled_cb.setChecked(True)
        self._ai_auto_apply_cb.setChecked(False)
        self._ai_mcp_log_cb.setChecked(False)
        for _pid, _label, _base, _model in AI_PRESETS:
            self._ai_preset_values[_pid] = {
                "base_url": _base, "model": _model, "api_key": "",
                "auth_mode": default_ai_auth_mode(_pid, _base),
                "tls_verify": "true",
            }
            self._ai_model_lists[_pid] = []
        self._ai_active_preset = DEFAULT_AI_PRESET
        self._ai_preset_combo.setCurrentIndex(
            max(0, self._ai_preset_combo.findData(DEFAULT_AI_PRESET)))
        self._load_ai_preset_fields(DEFAULT_AI_PRESET)
        self._response_lang_combo.setCurrentIndex(
            max(0, self._response_lang_combo.findText(DEFAULT_AI_RESPONSE_LANGUAGE)))

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
    def time_decimals(self) -> int:       return self._time_decimals_spin.value()
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
    def show_find(self) -> bool:          return self._find_cb.isChecked()
    @property
    def show_ai(self) -> bool:            return self._ai_cb.isChecked()
    @property
    def show_hover_highlight(self) -> bool: return self._hover_hl_cb.isChecked()
    @property
    def cpu_budget_pct(self) -> float:    return self._cpu_budget_spin.value()
    @property
    def task_deadlines_text(self) -> str: return self._task_deadlines_edit.toPlainText()
    @property
    def ai_enabled(self) -> bool:         return self._ai_enabled_cb.isChecked()
    @property
    def ai_auto_apply(self) -> bool:      return self._ai_auto_apply_cb.isChecked()
    @property
    def ai_mcp_log(self) -> bool:         return self._ai_mcp_log_cb.isChecked()
    @property
    def ai_preset(self) -> str:
        return normalize_ai_preset(self._ai_preset_combo.currentData())
    @property
    def ai_preset_settings(self) -> Dict[str, Dict[str, str]]:
        """Base URL / model / API key for every preset, not just the active one."""
        self._stash_ai_preset_fields()
        return {
            _pid: dict(self._ai_preset_values.get(_pid, {}))
            for _pid, _label, _base, _model in AI_PRESETS
        }
    @property
    def response_language(self) -> str:
        return (
            self._response_lang_combo.currentText().strip()
            or DEFAULT_AI_RESPONSE_LANGUAGE
        )
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
        self.setCursor(Qt.CursorShape.CrossCursor)

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
        if event.button() != Qt.MouseButton.LeftButton:
            return
        ed = self._editor
        if ed._text_edit_active() and ed._tool != 'text':
            ed._commit_text_edit()
        x, y = ed._to_img(event.position().x(), event.position().y())
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
                if bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                    new_idx = ed._duplicate_shape(hit)
                    ed._selected_idx = new_idx
                    ed._sync_dash_from_shape(new_idx)
                    ed._drag_idx = new_idx
                    ed._drag_prev = (x, y)
                    ed._drag_mode = 'move'
                    ed._drag_handle = ''
                    ed._drag_anchor = None
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                    self.update()
                    return
                ed._selected_idx = hit
                ed._sync_dash_from_shape(hit)
                ed._drag_idx = hit
                ed._drag_prev = (x, y)
                ed._drag_mode = 'move'
                ed._drag_handle = ''
                ed._drag_anchor = None
                self.setCursor(Qt.CursorShape.SizeAllCursor)
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
        x, y = ed._to_img(event.position().x(), event.position().y())
        if ed._drag_mode == 'handle' and ed._drag_idx >= 0 and ed._drag_handle:
            force = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
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
                force = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                d['x2'], d['y2'] = _snap_line_end(d['x1'], d['y1'], x, y, force)
            else:
                d['x2'] = x;  d['y2'] = y
                x1 = d['x1']; y1 = d['y1']
                if bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
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
            self.setCursor(Qt.CursorShape.SizeAllCursor if hit >= 0 else Qt.CursorShape.CrossCursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        ed = self._editor
        if ed._drag_mode in ('move', 'handle') and ed._drag_idx >= 0:
            ed._drag_idx = -1
            ed._drag_mode = 'none'
            ed._drag_handle = ''
            ed._drag_anchor = None
            self.setCursor(Qt.CursorShape.SizeAllCursor if ed._selected_idx >= 0 else Qt.CursorShape.CrossCursor)
            self.update()
        elif ed._drawing is not None:
            x, y = ed._to_img(event.position().x(), event.position().y())
            d = ed._drawing
            if d['type'] in SnapshotEditorDialog._LINE_TOOLS:
                force = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                d['x2'], d['y2'] = _snap_line_end(d['x1'], d['y1'], x, y, force)
            else:
                d['x2'] = x;  d['y2'] = y
                x1 = d['x1']; y1 = d['y1']
                if bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
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

        from PySide6.QtWidgets import QColorDialog, QMenu
        ed = self._editor
        # QContextMenuEvent uses .pos() - NOT .position() (QMouseEvent only)
        x, y = ed._to_img(event.pos().x(), event.pos().y())
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

        chosen = menu.exec(event.globalPos())

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
        if event.button() != Qt.MouseButton.LeftButton:
            return
        ed = self._editor
        x, y = ed._to_img(event.position().x(), event.position().y())
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

def _widget_available_geometry(widget: QWidget) -> QRect:
    """Qt6-safe available screen geometry (QApplication.desktop() was removed)."""
    win = widget.window() if widget is not None else None
    screen = win.screen() if win is not None else None
    if screen is None:
        screen = QApplication.primaryScreen()
    if screen is not None:
        return screen.availableGeometry()
    return QRect(0, 0, 1920, 1080)

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
    def __init__(self, pixmap: QPixmap, parent: Optional[QWidget] = None,
                 capture_dpr: float = 1.0) -> None:
        super().__init__(parent)
        # Flatten HiDPI grab() to 1:1 device pixels; annotation coords match pixels.
        self._orig_pixmap, detected_dpr = _normalize_grab_pixmap(pixmap)
        self._capture_dpr = capture_dpr if capture_dpr > 1.0 + 1e-6 else detected_dpr
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
        screen = _widget_available_geometry(parent or self)
        max_w = screen.width() - 120
        max_h = screen.height() - 220
        iw, ih = self._orig_pixmap.width(), self._orig_pixmap.height()
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
            btn.setIcon(_svg_icon_checked(_SNAP_TOOL_ICONS[tid]))
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
        tb.addSpacing(8)
        undo_btn = QPushButton()
        undo_btn.setIcon(_svg_icon(_IC_SNAP_UNDO, '#b0b0cc'))
        undo_btn.setIconSize(QSize(16, 16))
        undo_btn.setFixedSize(_ICON_H, _ICON_H)
        undo_btn.setToolTip("Undo (Ctrl+Z)")
        undo_btn.clicked.connect(self._undo)
        tb.addWidget(undo_btn)

        clear_btn = QPushButton()
        clear_btn.setIcon(_svg_icon(_IC_CLEAR, '#b0b0cc'))
        clear_btn.setIconSize(QSize(16, 16))
        clear_btn.setFixedSize(_ICON_H, _ICON_H)
        clear_btn.setToolTip("Clear all annotations")
        clear_btn.clicked.connect(self._clear_all)
        tb.addWidget(clear_btn)

        tb.addStretch()
        main.addLayout(tb)

        # ---- Canvas in a scroll area ----
        self._canvas = _AnnotationCanvas(self, self._disp_w, self._disp_h)
        self._canvas.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
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
        copy_btn.setIcon(_svg_icon(_IC_COPY, '#b0b0cc'))
        copy_btn.clicked.connect(self._on_copy)
        save_btn = QPushButton("Save PNG...")
        save_btn.setIcon(_svg_icon(_IC_SAVE, '#b0b0cc'))
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
        from PySide6.QtWidgets import QColorDialog  # always available, import locally
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
            if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                self._cancel_text_edit()
                return True
            if event.type() == QEvent.Type.FocusOut:
                QTimer.singleShot(0, self._deferred_commit_text_edit)
        return super().eventFilter(obj, event)

    def _deferred_commit_text_edit(self) -> None:
        if not self._text_input.isVisible():
            return
        if QApplication.focusWidget() is self._text_input:
            return
        self._commit_text_edit()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
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
        self._text_input.setFocus(Qt.FocusReason.OtherFocusReason)
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

    def _clear_all(self) -> None:
        if self._text_edit_active():
            self._cancel_text_edit()
        self._shapes.clear()
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
            return Qt.CursorShape.SizeFDiagCursor
        if handle in ('ne', 'sw'):
            return Qt.CursorShape.SizeBDiagCursor
        if handle in ('n', 's'):
            return Qt.CursorShape.SizeVerCursor
        if handle in ('e', 'w'):
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.CrossCursor

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
        sel_pen = QPen(QColor('#50beff'), max(1.0, 1.5 / max(self._scale, 0.01)), Qt.PenStyle.DashLine)
        sel_pen.setDashPattern([5.0 / max(self._scale, 0.01), 4.0 / max(self._scale, 0.01)])
        painter.setPen(sel_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
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
        cap=Qt.PenCapStyle.RoundCap,
        join=Qt.PenJoinStyle.RoundJoin,
    ) -> QPen:
        if dashed:
            pen = QPen(col, w, Qt.PenStyle.CustomDashLine, cap, join)
            pen.setDashPattern([20.0 / max(w, 1), 10.0 / max(w, 1)])
        else:
            pen = QPen(col, w, Qt.PenStyle.SolidLine, cap, join)
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
                painter.setBrush(Qt.BrushStyle.NoBrush)
                self._draw_line_with_label_gap(
                    painter,
                    shape['x1'], shape['y1'], shape['x2'], shape['y2'],
                    self._line_label_gap_half(shape),
                )
            elif t == 'rect':
                dashed = self._shape_is_dashed(shape)
                pen = self._stroke_pen(col, w, dashed, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(QRectF(shape['x'], shape['y'],
                                        shape['w'], shape['h']))
            elif t == 'circle':
                dashed = self._shape_is_dashed(shape)
                painter.setPen(self._stroke_pen(col, w, dashed))
                painter.setBrush(Qt.BrushStyle.NoBrush)
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
                QPen(col, stroke_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
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
        painter.setBrush(Qt.BrushStyle.NoBrush)
        self._draw_line_with_label_gap(
            painter, sx, sy, ex, ey, self._line_label_gap_half(shape))

        stroke_w = max(1, extra_width)
        painter.setPen(QPen(col, stroke_w, Qt.PenStyle.SolidLine))
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
                               QPen(col, stroke_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        else:
            # Colour pass: fill the glyph path
            painter.setPen(Qt.PenStyle.NoPen)
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
        _copy_pixmap_to_clipboard(self._render_final_pixmap(), self._capture_dpr)
        self._show_status("Copied to clipboard!")

    def _on_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Annotated Image", "annotated-snapshot.png",
            "PNG images (*.png);;All files (*)"
        )
        if not path:
            return
        pixmap = self._render_final_pixmap()
        if not _save_snapshot_png(pixmap, path, self._capture_dpr):
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
    return dlg.exec()

# ===========================================================================
# CPU Load Graph
# ===========================================================================
