"""BTF Viewer — timeline_util module (source). Do not edit btf_viewer.py; run make bundle."""
from __future__ import annotations

from ._imports import *  # noqa: F403,F401
from .config import *  # noqa: F403,F401
from .parser import *  # noqa: F403,F401

# ===========================================================================

# ---------------------------------------------------------------------------
# Internal widget constants
# All user-configurable values (fonts, layout, colours, cursors, LOD) are
# in the USER CONFIGURATION block at the top of this file.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Persistent hover-info popup  (replaces QToolTip which auto-hides on scroll)
# ---------------------------------------------------------------------------

def _stable_popup_parent(*skip: QWidget) -> Optional[QWidget]:
    """Existing visible window to parent the hover box (never a new top-level).

    On Windows a parentless QWidget is a real HWND. Creating one, or changing
    Qt window flags, flashes a tiny box at (0, 0) while AI tools rebuild
    the timeline. Always parent onto a window that already exists.
    """
    app = QApplication.instance()
    if app is None:
        return None
    ignored = {s for s in skip if s is not None}
    win = app.activeWindow()
    if win is not None and win not in ignored:
        return win
    for w in app.topLevelWidgets():
        try:
            if w in ignored or not w.isWindow() or not w.isVisible():
                continue
            return w
        except RuntimeError:
            continue
    return None


class _InfoPopup(QLabel):
    """Frameless hover-info box — shown over a segment, hidden when the pointer leaves.

    Child of the viewer (not a top-level ``Qt.ToolTip`` / ``Qt.Tool``). On
    Windows those flags and parentless widgets flash a native window.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent or _stable_popup_parent())
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setMargin(7)
        self._ss_applied_dark: Optional[bool] = None
        self._ss_applied_font: Optional[int] = None
        self._ui_font_size: int = UI_FONT_SIZE

    def _reparent(self, host: Optional[QWidget]) -> None:
        """Move onto *host* without changing Qt window flags (Windows HWND flash).

        *host* of None means hide in place. Unparenting would create a
        top-level HWND on Windows.
        """
        if host is not None and isinstance(host, QGraphicsView):
            host = host.viewport()
        if host is self:
            host = None
        if host is None:
            super().hide()
            return
        if self.parentWidget() is host:
            return
        html = self.text()
        super().hide()
        self.setParent(host)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        if html:
            self.setText(html)

    def _adopt_host(self, host: Optional[QWidget]) -> None:
        if host is None or host is self:
            super().hide()
            return
        self._reparent(host)

    def set_ui_font_size(self, ui_font_size: int) -> None:
        """Match Settings → Appearance → UI font (menus / status / tooltips)."""
        size = max(6, min(int(ui_font_size), 24))
        if size == self._ui_font_size:
            return
        self._ui_font_size = size
        self._ss_applied_dark = None
        self._ss_applied_font = None

    def _apply_stylesheet(self, is_dark: bool) -> None:
        if (self._ss_applied_dark == is_dark
                and self._ss_applied_font == self._ui_font_size):
            return
        self._ss_applied_dark = is_dark
        self._ss_applied_font = self._ui_font_size
        fam = _get_fixed_font_family()
        fs = _ui_font_stylesheet_size(self._ui_font_size)
        if is_dark:
            self.setStyleSheet(
                f"QLabel {{ background:#252526; color:#E0E0E0; "
                f"border:1px solid #666; border-radius:4px; "
                f"font-size:{fs}; font-family:'{fam}'; }}"
            )
        else:
            self.setStyleSheet(
                f"QLabel {{ background:#FFFFCC; color:#1E1E1E; "
                f"border:1px solid #AAAAAA; border-radius:4px; "
                f"font-size:{fs}; font-family:'{fam}'; }}"
            )
        self.setFont(_monospace_font(self._ui_font_size))

    def hide(self) -> None:
        try:
            self.setText("")
            # Hide in place. Reparenting recreates an HWND on Windows.
            super().hide()
        except RuntimeError:
            pass

    def show_at(self, screen_pos: QPoint, html: str, is_dark: Optional[bool] = None,
                host: Optional[QWidget] = None) -> None:
        if is_dark is None:
            app = QApplication.instance()
            if app is not None:
                is_dark = app.palette().color(QPalette.Window).lightness() < 128
            else:
                is_dark = True
        self._apply_stylesheet(bool(is_dark))
        self.setText(html)
        self.adjustSize()
        if host is None:
            host = self._fallback_show_host(screen_pos)
        if host is self:
            host = None
        self._adopt_host(host)
        overlay = self.parentWidget()
        sp = QPoint(int(screen_pos.x()), int(screen_pos.y()))
        if overlay is not None:
            local = overlay.mapFromGlobal(sp)
            self.move(local.x() + 16, local.y() + 8)
        else:
            self.move(sp.x() + 16, sp.y() + 8)
        if overlay is None:
            return
        self.show()
        self.raise_()

    @staticmethod
    def _fallback_show_host(screen_pos: QPoint) -> Optional[QWidget]:
        app = QApplication.instance()
        if app is None:
            return None
        host = app.widgetAt(QPoint(int(screen_pos.x()), int(screen_pos.y())))
        if host is not None:
            return host
        return _stable_popup_parent()


_info_popup: Optional[_InfoPopup] = None


def _popup_alive(popup: Optional[_InfoPopup]) -> bool:
    if popup is None:
        return False
    try:
        popup.isHidden()
        return True
    except RuntimeError:
        return False


def _get_popup(parent: Optional[QWidget] = None) -> _InfoPopup:
    global _info_popup
    if not _popup_alive(_info_popup):
        _info_popup = _InfoPopup(parent or _stable_popup_parent())
        return _info_popup
    if parent is not None and _info_popup.parentWidget() is None:
        _info_popup.setParent(parent)
    return _info_popup


def _hide_popup() -> None:
    """Hide the hover box without recreating a deleted C++ singleton."""
    global _info_popup
    if not _popup_alive(_info_popup):
        _info_popup = None
        return
    try:
        _info_popup.hide()
    except RuntimeError:
        _info_popup = None


def _apply_info_popup_ui_font(ui_font_size: int, parent: Optional[QWidget] = None) -> None:
    """Keep the timeline hover tip in sync with Settings → UI font."""
    _get_popup(parent).set_ui_font_size(ui_font_size)

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
    if _RENDER_RUNTIME.colorblind_active:
        palette = _PALETTE_COLORBLIND_DARK if _RENDER_RUNTIME.is_dark else _PALETTE_COLORBLIND
    else:
        palette = _PALETTE
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

def _set_render_dark_mode(is_dark: bool) -> None:
    """Track the active theme so the colorblind palette can swap black/white."""
    is_dark = bool(is_dark)
    if _RENDER_RUNTIME.is_dark == is_dark:
        return
    _RENDER_RUNTIME.is_dark = is_dark
    _clear_render_color_caches()

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

def _from_ns(ns: float, time_scale: str) -> float:
    """Convert nanoseconds to the trace's native *time_scale* unit."""
    mult = _NS_MULTIPLIERS.get(time_scale, 1) or 1
    return float(ns) / mult

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


def _format_time_trim(value: float, time_scale: str = "ns") -> str:
    """Like ``_format_time`` but drops trailing zeros (``19 µs``, not ``19.000 µs``)."""
    text = _format_time(value, time_scale, decimals=3)
    parts = text.rsplit(" ", 1)
    if len(parts) != 2:
        return text
    num, unit = parts
    if "." not in num:
        return text
    whole, frac = num.split(".", 1)
    frac = frac.rstrip("0")
    if not frac:
        return f"{whole} {unit}"
    return f"{whole}.{frac} {unit}"


def _format_time_web(value: float, time_scale: str = "ns", decimals: int = 3) -> str:
    """1:1 port of the web app's ``formatTime`` (``web/src/utils/timeFormat.js``).

    Used only by the Marks / Cursor panels so their rows render byte-for-byte
    like the web ``CursorPanel`` / ``MarksPanel`` / cursor-range block.  It
    differs from :func:`_format_time` in the two ways the web helper is spec'd
    to behave:

    * whole values in the trace's base unit print with no decimals
      (``2 µs`` — not ``2.000 µs``);
    * a value smaller than one base unit is NOT down-shifted when
      *time_scale* is not ``ns`` (``0.5`` in a ``us`` trace → ``0.500 µs``,
      not ``500.000 ns``).

    Scaling *up* from the base unit to µs / ms / s is unchanged from
    :func:`_format_time` — keep the two in step if either side moves.
    """
    def _base(v: float, unit: str) -> str:
        return f"{int(v)} {unit}" if float(v).is_integer() else f"{v:.{decimals}f} {unit}"

    t = value
    if time_scale == "ns":
        if t >= 1e9:
            return f"{t / 1e9:.{decimals}f} s"
        if t >= 1e6:
            return f"{t / 1e6:.{decimals}f} ms"
        if t >= 1e3:
            return f"{t / 1e3:.{decimals}f} µs"
        return _base(t, "ns")
    if time_scale == "us":
        if t >= 1e6:
            return f"{t / 1e6:.{decimals}f} s"
        if t >= 1e3:
            return f"{t / 1e3:.{decimals}f} ms"
        return _base(t, "µs")
    if time_scale == "ms":
        if t >= 1e3:
            return f"{t / 1e3:.{decimals}f} s"
        return _base(t, "ms")
    return _base(t, time_scale)

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

def _tag_value_sort_key(text: str) -> float:
    """Parse a formatted tag value (e.g. 12,192 or 3.5) for numeric table sorting."""
    s = str(text).strip().replace(",", "")
    if not s or s in ("-", "—"):
        return -1.0
    try:
        return float(s)
    except ValueError:
        return 0.0

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

def _normalize_grab_pixmap(pixmap: QPixmap) -> Tuple[QPixmap, float]:
    """Flatten a QWidget.grab() pixmap to 1:1 device pixels (HiDPI-safe).

    Returns ``(pixmap, capture_dpr)`` where *capture_dpr* is the grab ratio
    (typically 2.0 on macOS Retina). Use it when writing PNG pHYs metadata so
    viewers display the image at the same physical size as on screen.
    """
    if pixmap.isNull():
        return pixmap, 1.0
    dpr = float(pixmap.devicePixelRatioF())
    if dpr <= 1.0 + 1e-6:
        out = QPixmap(pixmap)
        out.setDevicePixelRatio(1.0)
        return out, 1.0
    image = pixmap.toImage()
    out = QPixmap.fromImage(image)
    out.setDevicePixelRatio(1.0)
    return out, dpr

def _snapshot_png_dpi(capture_dpr: float) -> int:
    """PNG DPI so 1 device pixel ≈ 1/72 inch at the grab DPR (macOS/Qt convention)."""
    return max(72, int(round(72.0 * max(1.0, capture_dpr))))

def _apply_snapshot_png_dpi(image: QImage, capture_dpr: float) -> None:
    dpm = int(round(_snapshot_png_dpi(capture_dpr) / 0.0254))
    image.setDotsPerMeterX(dpm)
    image.setDotsPerMeterY(dpm)

def _save_snapshot_png(pixmap: QPixmap, path: str, capture_dpr: float = 1.0) -> bool:
    img = pixmap.toImage()
    _apply_snapshot_png_dpi(img, capture_dpr)
    return img.save(path, "PNG")

def _pixmap_to_png_bytes(pixmap: QPixmap, capture_dpr: float = 1.0) -> Tuple[bytes, QByteArray]:
    """Encode *pixmap* as PNG; return raw bytes and the backing QByteArray."""
    buf = QByteArray()
    buf_dev = QBuffer(buf)
    buf_dev.open(QIODevice.OpenModeFlag.WriteOnly)
    img = pixmap.toImage()
    _apply_snapshot_png_dpi(img, capture_dpr)
    img.save(buf_dev, 'PNG')
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

def _copy_pixmap_to_clipboard(pixmap: QPixmap, capture_dpr: float = 1.0) -> Optional[str]:
    """Copy *pixmap* to the system clipboard as PNG.

    Returns the external tool name used ('powershell', 'wl-copy', 'xclip',
    'xsel'), or None when the Qt clipboard fallback was used.
    """
    png_bytes, buf = _pixmap_to_png_bytes(pixmap, capture_dpr)

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
    top, _ = _normalize_grab_pixmap(top)
    bottom, _ = _normalize_grab_pixmap(bottom)
    combined = QPixmap(max(top.width(), bottom.width()),
                       top.height() + bottom.height())
    combined.fill(Qt.GlobalColor.transparent)
    combined.setDevicePixelRatio(1.0)
    painter = QPainter(combined)
    try:
        painter.drawPixmap(0, 0, top)
        painter.drawPixmap(0, top.height(), bottom)
    finally:
        painter.end()
    return combined

_monospace_font_cache: dict = {}

_GENERIC_FONT_FAMILIES = frozenset({
    "monospace", "monospaced", "fixed", "fixedsys",
    "sans serif", "sans-serif", "serif", "cursive", "fantasy",
    "system-ui", "ui-monospace", "ui-sans-serif", "ui-serif",
})

def _is_generic_font_family(name: str) -> bool:
    """True for CSS/Qt aliases that are not installed font faces."""
    return (name or "").strip().lower() in _GENERIC_FONT_FAMILIES

def _monospace_font(size: int, weight: int = QFont.Normal) -> QFont:
    """Return a cached monospace QFont using a real installed fixed face.

    Cached so family lookup runs once per (size, weight) pair. Uses the same
    macOS pixel scaling as application UI fonts. Avoids Qt's generic
    ``monospace`` / ``Monospace`` alias (qt.qpa.fonts warning on macOS).
    """
    key = (size, weight, sys.platform, _ui_font_pixel_baseline())
    f = _monospace_font_cache.get(key)
    if f is None:
        f = QFont(_get_fixed_font_family())
        px = _scaled_font_pixel_size(size, reference_pt=FONT_SIZE)
        if px is not None:
            f.setPixelSize(px)
        else:
            f.setPointSize(size)
        f.setWeight(weight)
        _monospace_font_cache[key] = f
    return f

def _make_rotated_label(scene, text: str, font: "QFont", color: "QColor",
                        x_center: float, y: float, z: float) -> "QGraphicsItem":
    """Add an antialiased rotated label to *scene*.

    *x_center* is the horizontal centre of the column the label belongs to.
    The item is horizontally centred on that column.  The *y* parameter is the
    **bottom edge** of the label in scene coordinates - the label text grows
    upward from that point.
    """
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
    item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
    item.setAcceptHoverEvents(False)
    scene.addItem(item)
    return item

# Resolved family name of a real installed fixed-pitch font (never the CSS
# generic ``monospace`` alias). Lazily initialised so import does not require
# a live QApplication.
_FIXED_FONT_FAMILY: Optional[str] = None
_SANS_FONT_FAMILY: Optional[str] = None

def _get_fixed_font_family() -> str:
    """Return an installed fixed-pitch font family, initialising lazily.

    Qt 6 on macOS reports ``QFontDatabase.FixedFont`` as ``monospace``, which
    is not an installed face and triggers ``qt.qpa.fonts`` alias warnings.
    Prefer Menlo / Consolas / DejaVu / Courier New when present.
    """
    global _FIXED_FONT_FAMILY
    if _FIXED_FONT_FAMILY is None:
        available = set(QFontDatabase.families())
        for cand in (
            "Menlo", "Monaco", "SF Mono",
            "Consolas", "Cascadia Mono", "Lucida Console",
            "DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono", "Ubuntu Mono",
            "Courier New", "Andale Mono", "PT Mono",
        ):
            if cand in available:
                _FIXED_FONT_FAMILY = cand
                break
        else:
            fam = ""
            for name in QFontDatabase.families():
                if (QFontDatabase.isFixedPitch(name)
                        and not _is_generic_font_family(name)):
                    fam = name
                    break
            _FIXED_FONT_FAMILY = fam or "Courier New"
    return _FIXED_FONT_FAMILY


def _get_sans_font_family() -> str:
    """Return an installed proportional sans family (never CSS ``sans-serif``).

    Qt SVG looks up ``sans-serif`` as the face ``Sans-serif`` and emits
    ``qt.qpa.fonts`` missing-family warnings. Prefer a real installed face.
    When the usual Latin UI faces lack Hangul (common on Linux/WSL), prefer a
    CJK-capable face so AI Korean replies and mermaid labels are not tofu.
    """
    global _SANS_FONT_FAMILY
    if QApplication.instance() is None:
        return _SANS_FONT_FAMILY or "Arial"
    _ensure_cjk_application_fonts()
    cjk = _cjk_capable_ui_family()
    if _SANS_FONT_FAMILY is not None:
        if _font_family_covers(_SANS_FONT_FAMILY, _CJK_PROBE) or cjk is None:
            return _SANS_FONT_FAMILY
        # Cached Latin-only face before CJK fonts were registered — upgrade.
        _SANS_FONT_FAMILY = cjk
        return _SANS_FONT_FAMILY
    available = set(QFontDatabase.families())
    for cand in (
        "Helvetica Neue", "Helvetica", "Arial", "Segoe UI",
        "Lucida Grande", "Verdana", "Tahoma",
        "DejaVu Sans", "Liberation Sans", "Noto Sans", "Ubuntu",
        "FreeSans", "Cantarell",
    ):
        if cand in available and _font_family_covers(cand, _CJK_PROBE):
            _SANS_FONT_FAMILY = cand
            return _SANS_FONT_FAMILY
    if cjk:
        _SANS_FONT_FAMILY = cjk
        return _SANS_FONT_FAMILY
    for cand in (
        "Helvetica Neue", "Helvetica", "Arial", "Segoe UI",
        "Lucida Grande", "Verdana", "Tahoma",
        "DejaVu Sans", "Liberation Sans", "Noto Sans", "Ubuntu",
        "FreeSans", "Cantarell",
    ):
        if cand in available:
            _SANS_FONT_FAMILY = cand
            break
    else:
        fam = ""
        for name in QFontDatabase.families():
            low = (name or "").lower()
            if _is_generic_font_family(name):
                continue
            if any(tok in low for tok in ("mono", "courier", "console", "fixed")):
                continue
            fam = name
            break
        _SANS_FONT_FAMILY = fam or "Arial"
    return _SANS_FONT_FAMILY

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
    prev_bin: Optional[int] = None
    for seg in segs:
        b = math.floor(offset + (seg.start - time_min) * px_per_ns)
        if prev_bin is None or b != prev_bin:
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

@contextmanager
def _svg_safe_app_style():
    """Temporarily force Fusion so ``QWidget.render`` into ``QSvgGenerator`` works.

    macOS ``QMacStyle`` draws via CoreGraphics and fails with::

        QMacCGContext:: Unsupported paint engine type 8

    (SVG is paint-engine type 8) plus ``qt.widgets.styles.macos`` nullptr
    graphics-context warnings for combo boxes, frames, and splitters.
    Fusion paints with plain ``QPainter`` primitives that SVG accepts.
    No-op when not on Darwin or when Fusion is already active.
    """
    app = QApplication.instance()
    if app is None or sys.platform != "darwin":
        yield
        return
    prev = app.style()
    prev_name = (prev.objectName() if prev is not None else "").strip()
    if prev_name.lower() == "fusion":
        yield
        return
    fusion = QStyleFactory.create("Fusion")
    if fusion is None:
        yield
        return
    app.setStyle(fusion)
    try:
        yield
    finally:
        restored = QStyleFactory.create(prev_name) if prev_name else None
        if restored is not None:
            app.setStyle(restored)


def _force_fusion_style(app: Optional[QApplication] = None) -> None:
    """Force Fusion for a short-lived headless QApplication (CLI snapshot)."""
    app = app or QApplication.instance()
    if app is None:
        return
    cur = app.style()
    if cur is not None and cur.objectName().lower() == "fusion":
        return
    fusion = QStyleFactory.create("Fusion")
    if fusion is not None:
        app.setStyle(fusion)


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

