/**
 * BTF Viewer — web user configuration.
 *
 * Edit defaults here. After first run, Settings and panel sizes persist in
 * localStorage (``btf-viewer-settings-v1`` and ``btf-viewer-session-v2``) and
 * override these values. Reset in Settings restores this file.
 *
 * Mirrors desktop ``btf_viewer_pkg/config.py`` USER CONFIGURATION. Fonts are
 * pixels on the web (desktop uses points).
 */

// ---- Fonts ----------------------------------------------------------------
export const FONT_SIZE = 12              // Timeline label font (px)
export const UI_FONT_SIZE = 12           // Menus, toolbar, dialogs (px)

// ---- Layout (Settings → Layout) ------------------------------------------
export const LABEL_WIDTH = 160           // Frozen task-label column (px)
export const RULER_HEIGHT = 40           // Time ruler row (px), horizontal mode
export const ROW_HEIGHT = 22             // Task / core row height (px)
export const ROW_GAP = 4                 // Gap between timeline rows (px)
export const STI_ROW_H = 18              // Collapsed STI row (px)
export const STI_WAVEFORM_H = 80         // Expanded STI waveform (px)
export const STI_LINE_STYLE = 'linear'   // 'step' | 'linear'
export const TIMESCALE_PER_PX_DEFAULT = 2  // Initial zoom (ns per screen pixel)
export const TIME_DECIMALS = 3           // Time display precision (0–9)
export const HOVER_HIGHLIGHT = false     // Highlight bars on label hover
export const SHOW_GRID = true
export const SHOW_STI = true
export const SHOW_LEGEND = true
export const SHOW_STATS = true
export const SHOW_MARKS = true
export const SHOW_FIND = true
export const SHOW_CPU_LOAD = true
export const SHOW_AI = true
export const DARK_MODE = true
export const COLORBLIND_SAFE = false
export const VIEW_MODE = 'task'          // 'task' | 'core'
export const ORIENTATION = 'h'           // 'h' | 'v'
export const STI_LOG_SCALE = false
export const CPU_BUDGET_PCT = 0          // 0 = off

// ---- Cursors --------------------------------------------------------------
export const MAX_CURSORS = 8             // Hard upper bound
export const DEFAULT_MAX_CURSORS = 4     // Settings default

// ---- CPU load pane --------------------------------------------------------
export const CPU_LOAD_ROW_H = 30
export const CPU_LOAD_ROW_GAP = 2
export const CPU_LOAD_COLLAPSED_H = 20
export const CPU_LOAD_PANE_CHROME_H = 30
export const CPU_LOAD_PANE_MIN_H = 60
export const CPU_LOAD_PANE_MAX_H = 480   // Legacy cap at default row height
export const CPU_LOAD_MAX_VISIBLE_ROWS = 8

// ---- Right panel (session layout, resizable) ------------------------------
// Wide enough for wrapping AI mode + template chips (shared Statistics / AI dock).
export const RIGHT_PANEL_WIDTH = 450
export const RIGHT_PANEL_MIN_W = 180
export const RIGHT_PANEL_MAX_W = 520

// ---- Statistics section viewports -----------------------------------------
export const STATS_MAX_VISIBLE_ROWS = 8
export const STATS_CORES_DEFAULT_VISIBLE_ROWS = 2
export const STATS_LB_GAUGE_H = 200
export const STATS_UTIL_ROW_H = 16
export const STATS_UTIL_ROW_GAP = 3      // Matches .stats-util CSS (desktop is 1)
export const STATS_TABLE_ROW_H = 21      // Matches .stats-table cell metrics
export const STATS_TABLE_HEADER_H = 22
export const STATS_TABLE_HSCROLL_H = 14
export const STATS_TABLE_WRAP_BORDER = 2
export const STATS_TABLE_MIN_H = 80
export const STATS_TABLE_MAX_H = 480

// ---- Large-trace statistics load ------------------------------------------
export const STATS_LOAD_DEFER_TASKS = 256
export const STATS_LOAD_DEFER_CORES = 32
export const STATS_LOAD_DEFER_SYNC_ISSUES = 400
export const STATS_TABLE_DISPLAY_ROW_CAP = 2000  // max rows shown per stats table
export const STATS_HEAVY_SECTIONS = [
  'migrations', 'exec', 'block', 'inter', 'health',
  'preemption', 'priority', 'sync', 'intervals', 'tags',
  'dispatch', 'switch_overhead', 'concurrency',
]
