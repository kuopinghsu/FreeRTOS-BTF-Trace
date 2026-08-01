"""BTF Viewer — config module (source). Do not edit btf_viewer.py; run make bundle."""
from __future__ import annotations

from ._imports import *  # noqa: F403,F401

# ===========================================================================
# USER CONFIGURATION
# Edit the values in this section to customise the viewer.
# Everything else in the file is internal implementation detail.
# ===========================================================================

# ---- Fonts ----------------------------------------------------------------
FONT_SIZE                = 8    # Timeline label font size (pt).  Adjustable at runtime
                                # via the Font spinbox in the toolbar.
UI_FONT_SIZE             = 8    # Application UI font: menus, toolbar, status bar (pt).
# macOS Retina: pixel baseline (~11px matches PyQt5 8pt density). Override: BTF_UI_FONT_PX.
UI_FONT_PIXEL_SIZE: int = int(
    os.environ.get("BTF_UI_FONT_PX", "11" if sys.platform == "darwin" else "0")
)

def _ui_font_pixel_baseline() -> int:
    """Pixel font baseline when pt sizing is too small (macOS / BTF_UI_FONT_PX)."""
    raw = os.environ.get("BTF_UI_FONT_PX")
    if raw is not None and raw.strip():
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    if UI_FONT_PIXEL_SIZE > 0:
        return UI_FONT_PIXEL_SIZE
    return 11 if sys.platform == "darwin" else 0

def _scaled_font_pixel_size(point_size: int,
                            *, reference_pt: int = UI_FONT_SIZE) -> int | None:
    """Map a pt setting to a pixel size on HiDPI; None → use pt directly."""
    base = max(6, min(int(point_size), 24))
    px_base = _ui_font_pixel_baseline()
    if px_base > 0:
        scale = base / max(reference_pt, 1)
        return max(6, int(round(px_base * scale)))
    return None

def _application_ui_font(point_size: int = UI_FONT_SIZE) -> QFont:
    """Application UI font with platform-appropriate sizing (Qt6 HiDPI-safe)."""
    base = max(6, min(int(point_size), 24))
    # Use the real system UI font — a fresh QApplication defaults to the generic
    # "Sans Serif" alias, which triggers qt.qpa.fonts warnings on macOS/Qt 6.
    font = QFont(QFontDatabase.systemFont(QFontDatabase.GeneralFont))
    px = _scaled_font_pixel_size(base)
    if px is not None:
        font.setPixelSize(px)
    else:
        font.setPointSize(base)
    return font

def _ui_font_stylesheet_size(point_size: int = UI_FONT_SIZE) -> str:
    """CSS font-size token matching _application_ui_font()."""
    base = max(6, min(int(point_size), 24))
    px = _scaled_font_pixel_size(base)
    if px is not None:
        return f"{px}px"
    return f"{base}pt"

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
CPU_LOAD_PCT_COL_MIN     =  72  # Minimum label-column width (px) for visible + cursor % text.
CPU_LOAD_PCT_COL_PAD     =   6  # Extra padding (px) around measured % text.
STATS_UTIL_BAR_H         =   8  # Core/task CPU % bar height in Statistics panel (px).
STATS_UTIL_ROW_H         =  16  # Row height; matches stats-table row size (px).
STATS_UTIL_ROW_GAP       =   1  # Vertical gap between utilisation rows (px).
STATS_UTIL_LABEL_W       = 128  # Shared label column for core/task util rows (px).
STATS_UTIL_LABEL_MIN_W   =  48  # Minimum util label column (px).
STATS_UTIL_BAR_MIN_W     =  24  # Minimum util progress bar width (px).
STATS_UTIL_PCT_W         =  40  # Fixed CPU % column width (px).
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

# Large-trace load tuning (desktop Statistics / Legend panels).
STATS_LOAD_DEFER_TASKS       = 256   # defer heavy stats sections above this task count
STATS_LOAD_DEFER_CORES       = 32    # defer when core count exceeds this
STATS_LOAD_DEFER_SYNC_ISSUES = 400   # defer when sync-issue rows exceed this
STATS_TABLE_DISPLAY_ROW_CAP  = 2000  # max rows materialised per stats table on load
STATS_HEAVY_SECTIONS         = frozenset({
    "migrations", "exec", "block", "inter", "health",
    "preemption", "priority", "sync", "intervals", "tags",
})

def trace_needs_deferred_stats_load(trace: "BtfTrace") -> bool:
    """True when statistics sections should populate after the first paint."""
    return (
        len(trace.tasks) > STATS_LOAD_DEFER_TASKS
        or len(getattr(trace, "core_names", None) or []) > STATS_LOAD_DEFER_CORES
        or len(getattr(trace, "sync_issues", None) or []) > STATS_LOAD_DEFER_SYNC_ISSUES
    )

def cap_stats_table_rows(rows: list, cap: int = STATS_TABLE_DISPLAY_ROW_CAP) -> tuple:
    """Return (rows[:cap], footnote_or_none) for oversized on-screen tables."""
    n = len(rows)
    if n <= cap:
        return rows, None
    return rows[:cap], (
        f"Showing first {cap:,} of {n:,} rows — use Export for the full list."
    )

def default_section_collapsed() -> Dict[str, bool]:
    """Default collapsed flags for statistics panel sections (shared with MVVM)."""
    return {
        "cores": False,
        "tasks": False,
        "migrations": False,
        "exec": False,
        "block": False,
        "inter": False,
        "health": False,
        "preemption": False,
        "priority": False,
        "sync": False,
        "queue": False,
        "intervals": False,
        "lifecycle": False,
        "core_pairs": False,
        "core_breakdown": False,
        "affinity": False,
        "deadline": False,
    }

def default_section_table_heights() -> Dict[str, int]:
    """Default max heights for collapsible statistics tables (shared with MVVM)."""
    return {
        "cores": STATS_UTIL_DEFAULT_H,
        "tasks": STATS_UTIL_DEFAULT_H,
        "migrations": STATS_TABLE_MIG_DEFAULT_H,
        "exec": STATS_TABLE_DEFAULT_H,
        "block": STATS_TABLE_DEFAULT_H,
        "inter": STATS_TABLE_DEFAULT_H,
        "preemption": STATS_TABLE_MIG_DEFAULT_H,
        "priority": STATS_TABLE_DEFAULT_H,
        "intervals": STATS_TABLE_DEFAULT_H,
        "lifecycle": STATS_TABLE_DEFAULT_H,
        "core_pairs": STATS_TABLE_DEFAULT_H,
        "core_breakdown": STATS_TABLE_DEFAULT_H,
        "affinity": STATS_TABLE_DEFAULT_H,
        "sync": STATS_TABLE_DEFAULT_H,
        "queue": STATS_TABLE_DEFAULT_H,
        "sync_issues": STATS_TABLE_MIG_DEFAULT_H,
        "health": STATS_TABLE_DEFAULT_H,
    }

STATS_UTIL_DEFAULT_H     = ( STATS_MAX_VISIBLE_ROWS * STATS_UTIL_ROW_H
                             + max(0, STATS_MAX_VISIBLE_ROWS - 1) * STATS_UTIL_ROW_GAP + 2 )
STI_WAVEFORM_H           =  80  # Height of an expanded STI waveform row (px).
STI_LINE_STYLE           = "linear"  # Default STI waveform draw style: "step" or "linear".

# First-run window geometry defaults (used when btf_viewer.rc is absent).
DEFAULT_WINDOW_WIDTH     = 1916
DEFAULT_WINDOW_HEIGHT    = 1088
DEFAULT_WINDOW_X         = 254
DEFAULT_WINDOW_Y         = 47
DEFAULT_DOCK_LAYOUT_VERSION = "10"

# Right-panel tab indices (Statistics / Marks / Find — web parity).
_PANEL_TAB_STATS = 0
_PANEL_TAB_MARKS = 1
_PANEL_TAB_FIND  = 2
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
# Qt QScrollBar range is capped near INT_MAX; keep scene timeline width below this.
_MAX_SCENE_TIMELINE_PX   = 2_000_000_000
# Virtual time-axis scrollbar maps the full trace into this range when zoomed in.
_VIRT_SCROLL_MAX         = 2_000_000_000
_HOVER_HIGHLIGHT_ENABLED = False  # Highlight task bars when hovering the label (default off).
_DEFAULT_TIME_DECIMALS  = 3       # Decimal digits shown in UI time displays (tooltips, cursors, etc.) (0-9).
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
_AUTO_EXPAND_CORES_MAX    = 8     # match web TimelinePanel.vue; larger SMP traces start collapsed
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
_NAV_SCROLL_ACTIVE_MS     = 40    # faster minimap refresh while panning
_WINDOW_SHIFT_MIN_MS      = 150   # throttle sliding-window rebuilds at trace edges
# Never draw grid lines closer than this (px); dense lines read as solid gray.
_MIN_GRID_SPACING_PX      = 12.0
# Extra scene extent on the task axis so the last row clears scrollbar tracks.
TIMELINE_SCROLL_GUTTER   = 12
# Gap between the timeline pane and the CPU-load splitter handle (px).
TIMELINE_SPLITTER_GAP    = 4

# ---- Cursors --------------------------------------------------------------
_MAX_CURSORS         = 8  # Hard upper bound - must equal len(_CURSOR_COLORS).
_DEFAULT_MAX_CURSORS = 4  # Default number of simultaneously visible cursors.

# Portable session JSON (shared with BTFViewer/web sessionPortable.js)
SESSION_PORTABLE_VERSION = 2
_PORTABLE_FIND_MODES = (
    "contains", "exact", "regex", "migrations",
    "sti", "intervals", "lifecycle", "pointers",
)

def _snapshot_tab_filters(scene) -> dict:
    """Per-tab legend/heatmap filter state (portable session + tab_view rc)."""
    mks = scene._heatmap_filter_mks
    return {
        "taskFilterText": scene._task_filter_q or "",
        "migratedOnlyFilter": bool(scene._migrated_only_filter),
        "taskFilterKeys": sorted(mks) if mks else None,
        "heatmapFilterLabel": scene._heatmap_filter_label,
    }

def _sanitize_tab_filters(src) -> Optional[dict]:
    if not isinstance(src, dict):
        return None
    keys = src.get("taskFilterKeys")
    if keys is not None:
        keys = [str(k) for k in keys if k is not None and str(k)]
        if not keys:
            keys = None
    return {
        "taskFilterText": str(src.get("taskFilterText") or ""),
        "migratedOnlyFilter": bool(src.get("migratedOnlyFilter")),
        "taskFilterKeys": keys,
        "heatmapFilterLabel": (str(src["heatmapFilterLabel"])
                               if src.get("heatmapFilterLabel") is not None else None),
    }
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

def _svg_icon_checked(path_data: str, off: str = "#b0b0cc", on: str = "#e3f2fd",
                      size: int = 16) -> "QIcon":
    """Checkable toolbar icon (normal + checked tints)."""
    icon = QIcon()
    icon.addPixmap(_svg_icon(path_data, off, size).pixmap(QSize(size, size)),
                   QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(_svg_icon(path_data, on, size).pixmap(QSize(size, size)),
                   QIcon.Mode.Normal, QIcon.State.On)
    return icon

def _svg_pixmap(path_data: str, color: str = "#9E9E9E", size: int = 16) -> QPixmap:
    """Rasterise an SVG path to a pixmap (for QLabel icons)."""
    return _svg_icon(path_data, color, size).pixmap(QSize(size, size))

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
_IC_FIND   = ("M6.5 1a5.5 5.5 0 1 0 3.89 9.4l3.4 3.4.7-.7-3.4-3.4A5.5 5.5 0 0 0 6.5 1"
              "zm0 1a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9z")
_IC_FIT    = "M1.5 1h5v1h-4v4h-1V1.5a.5.5 0 0 1 .5-.5zm13 0a.5.5 0 0 1 .5.5V6h-1V2h-4V1h4.5zM1 10h1v4h4v1H1.5a.5.5 0 0 1-.5-.5V10zm14 0v4.5a.5.5 0 0 1-.5.5H10v-1h4v-4h1z"
_IC_CURSOR = "M1 1l5 12 2-4 4 4 1-1-4-4 4-2L1 1z"
_IC_MARK   = "M3 2a1 1 0 0 1 1-1h8a1 1 0 0 1 1 1v12.5a.5.5 0 0 1-.777.416L8 12.101l-4.223 2.815A.5.5 0 0 1 3 14.5V2z"
_IC_CLEAR  = "M2 2.5l.5-.5 5.5 5.5 5.5-5.5.5.5L8.5 8 14 13.5l-.5.5L8 8.5 2.5 14l-.5-.5L7.5 8 2 2.5z"
# Snapshot editor annotation tools (Bootstrap Icons paths — same style as main toolbar)
_IC_SNAP_ARROW = (
    "M14 0.5a.5.5 0 0 0-.5-.5h-6a.5.5 0 0 0 0 1h4.793L2.146 13.146a.5.5 0 0 0 .708.708L13 2.707V7.5a.5.5 0 0 0 1 0v-7z"
)
_IC_SNAP_DBLARROW = (
    "M3.854 4.146a.5.5 0 0 1 0 .708L1.707 7H14.5a.5.5 0 0 1 0 1H1.707l2.147 2.146a.5.5 0 0 1-.708.708l-3-3a.5.5 0 0 1 0-.708l3-3a.5.5 0 0 1 .708 0zm8.292 0a.5.5 0 0 0 0 .708L14.293 7H1.5a.5.5 0 0 0 0 1h12.793l-2.147 2.146a.5.5 0 0 0 .708.708l3-3a.5.5 0 0 0 0-.708l-3-3a.5.5 0 0 0-.708 0z"
)
_IC_SNAP_LINE = "M13.854 2.146a.5.5 0 0 1 0 .708l-11 11a.5.5 0 0 1-.708-.708l11-11a.5.5 0 0 1 .708 0z"
_IC_SNAP_RECT = (
    "M14 1a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1h12z"
    "M2 0a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V2a2 2 0 0 0-2-2H2z"
)
_IC_SNAP_CIRCLE = "M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z"
_IC_SNAP_TEXT = "M3 2h10v1.5H9.25V13h-2.5V3.5H3V2z"
_IC_SNAP_UNDO = (
    "M8 3a5 5 0 1 0 4.546 2.914.5.5 0 0 1 .908-.417A6 6 0 1 1 8 2v1z"
    "M8 4.466V.534a.25.25 0 0 1 .41-.192l2.36 1.966c.12.1.12.284 0 .384L8.41 4.658A.25.25 0 0 1 8 4.466z"
)
_SNAP_TOOL_ICONS = {
    'arrow':    _IC_SNAP_ARROW,
    'dblarrow': _IC_SNAP_DBLARROW,
    'line':     _IC_SNAP_LINE,
    'rect':     _IC_SNAP_RECT,
    'circle':   _IC_SNAP_CIRCLE,
    'text':     _IC_SNAP_TEXT,
}
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
_IC_CHORD = ("M8 1 A7 7 0 1 0 8 15 A7 7 0 1 0 8 1 Z"
             "M8 3.5 A4.5 4.5 0 1 0 8 12.5 A4.5 4.5 0 1 0 8 3.5 Z"
             "M4 6 L5 5 L12 10 L11 11 Z"
             "M11 5 L12 6 L5 11 L4 10 Z")
_IC_ANALYSIS = (
    "M2 1.5A.5.5 0 0 1 2.5 1h9A1.5 1.5 0 0 1 13 2.5v11a1.5 1.5 0 0 1-1.5 1.5h-9"
    "A.5.5 0 0 1 2 14.5v-13zM3 2v12h8.5a.5.5 0 0 0 .5-.5v-11a.5.5 0 0 0-.5-.5H3z"
    "M4.5 4h6v1h-6V4zm0 2.5h6v1h-6v-1zm0 2.5h4v1h-4V9z"
)
_IC_EXPORT_CSV = ("M2 1h12a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1zm0 1v12h12V2H2zm2 2h8v1H4V4zm0 2h8v1H4V6zm0 2h5v1H4V8z")
_IC_TICK_DIST = ("M1.5 12.5h2.5V8H1.5v4.5zm3.5 0H7.5V5H5v7.5zm3.5 0h2.5V2H8.5v10.5zm3.5 0H14v-5h-2.5v5.5z")
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
_APP_VERSION = "1.3.2"
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

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
# User-supplied icons next to btf_viewer.py (or via btf_viewer.rc / BTF_VIEWER_ICON).
# When none are present, _APP_ICON_SVG is rasterised in-process (no external file).
_APP_ICON_CANDIDATES = (
    os.path.join(_APP_DIR, "app_icon.icns"),
    os.path.join(_APP_DIR, "app_icon.ico"),
    os.path.join(_APP_DIR, "app_icon.png"),
    os.path.join(os.path.dirname(_APP_DIR), "images", "app_icon.png"),
)
_APP_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
_APP_ICON_CACHE: Optional["QIcon"] = None

def _icon_add_pixmap(icon: QIcon, pm: QPixmap) -> None:
    """Register one pixmap for all standard QIcon modes."""
    if pm.isNull():
        return
    for mode in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Selected):
        icon.addPixmap(pm, mode, QIcon.State.Off)

def _resolve_app_icon_path() -> Optional[str]:
    """Return path to a user/bundled app icon, or None for the built-in SVG."""
    env = os.environ.get("BTF_VIEWER_ICON", "").strip()
    if env:
        env = os.path.expanduser(env)
        if os.path.isfile(env):
            return env
    rc_path = os.path.join(_APP_DIR, "btf_viewer.rc")
    if os.path.isfile(rc_path):
        cfg = configparser.ConfigParser()
        cfg.read(rc_path, encoding="utf-8")
        custom = cfg.get("app", "icon_path", fallback="").strip()
        if custom:
            custom = os.path.expanduser(custom)
            if not os.path.isabs(custom):
                custom = os.path.normpath(os.path.join(_APP_DIR, custom))
            if os.path.isfile(custom):
                return custom
    for path in _APP_ICON_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None

def _icon_from_native_file(path: str) -> Optional[QIcon]:
    """Load a multi-resolution .ico / .icns (Windows / macOS)."""
    if not path.lower().endswith((".ico", ".icns")):
        return None
    icon = QIcon(path)
    return icon if not icon.isNull() else None

def _pixmap_from_app_svg(size: int) -> QPixmap:
    svg = (
        _APP_ICON_SVG
        .replace('width="72"', f'width="{size}"')
        .replace('height="72"', f'height="{size}"')
    )
    pm = QPixmap()
    pm.loadFromData(QByteArray(svg.encode()), "SVG")
    return pm

def _pixmap_from_embedded_app_icon(size: int) -> QPixmap:
    """Rasterise the built-in app icon without any external file."""
    if sys.platform != "win32":
        pm = _pixmap_from_app_svg(size)
        if not pm.isNull():
            return pm
    # Windows often lacks the Qt SVG plugin; QPainter path is always available.
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    s = size / 72.0

    def _rr(x: float, y: float, w: float, h: float, r: float, color: str) -> None:
        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(x * s, y * s, w * s, h * s), r * s, r * s)

    _rr(3, 3, 66, 66, 14, "#1C3A6E")
    _rr(10, 17, 29, 7, 3.5, "#5B9BD5")
    _rr(16, 28, 22, 7, 3.5, "#7EC8E3")
    _rr(10, 39, 36, 7, 3.5, "#5B9BD5")
    _rr(20, 50, 18, 7, 3.5, "#7EC8E3")
    _rr(46, 13, 2, 46, 0, "#FFC107")
    p.setBrush(QBrush(QColor("#FFC107")))
    p.drawPolygon(QPolygonF([
        QPointF(42 * s, 13 * s),
        QPointF(50 * s, 13 * s),
        QPointF(46 * s, 20 * s),
    ]))
    p.end()
    return pm

def _embedded_app_icon() -> QIcon:
    """Default icon compiled into the app (vector fallback, no external file)."""
    icon = QIcon()
    for sz in _APP_ICON_SIZES:
        _icon_add_pixmap(icon, _pixmap_from_embedded_app_icon(sz))
    return icon

def _build_app_icon(icon_path: Optional[str] = None) -> QIcon:
    """Build a multi-resolution QIcon for window title bar and OS taskbar/dock."""
    path = icon_path if icon_path is not None else _resolve_app_icon_path()
    if path and os.path.isfile(path):
        native = _icon_from_native_file(path)
        if native is not None:
            return native
        icon = QIcon()
        if path.lower().endswith(".svg"):
            with open(path, encoding="utf-8") as fh:
                svg_data = fh.read()
            for sz in _APP_ICON_SIZES:
                sized = (
                    svg_data
                    .replace('width="72"', f'width="{sz}"')
                    .replace('height="72"', f'height="{sz}"')
                )
                pm = QPixmap()
                if pm.loadFromData(QByteArray(sized.encode()), "SVG") and not pm.isNull():
                    _icon_add_pixmap(icon, pm)
            if not icon.isNull():
                return icon
        else:
            source = QPixmap(path)
            if not source.isNull():
                for sz in _APP_ICON_SIZES:
                    _icon_add_pixmap(icon, source.scaled(
                        sz, sz,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    ))
                if not icon.isNull():
                    return icon
    return _embedded_app_icon()

def app_icon() -> QIcon:
    """Cached application icon (taskbar / dock / window chrome)."""
    global _APP_ICON_CACHE
    if _APP_ICON_CACHE is None:
        _APP_ICON_CACHE = _build_app_icon()
    return _APP_ICON_CACHE

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

