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
/** Section-header pin slot (Desktop/Web lockstep): narrow vertical bar. */
export const STATS_PIN_SLOT_W = 14
export const STATS_PIN_SLOT_H = 22
export const STATS_PIN_ICON_PX = 14

// ---- Large-trace statistics load ------------------------------------------
export const STATS_LOAD_DEFER_TASKS = 256
export const STATS_LOAD_DEFER_CORES = 32
export const STATS_LOAD_DEFER_SYNC_ISSUES = 400
export const STATS_LOAD_DEFER_SEGMENTS = 8000
export const STATS_TABLE_DISPLAY_ROW_CAP = 2000  // max rows shown per stats table
export const STATS_HEAVY_SECTIONS = [
  'migrations', 'exec', 'block', 'inter', 'health',
  'preemption', 'priority', 'sync', 'intervals', 'tags',
  'dispatch', 'switch_overhead', 'concurrency',
  'anomalies', 'worst', 'crit_path', 'patterns',
  'response', 'period', 'jitter', 'preempt_matrix',
  'task_core', 'core_time', 'wait_owner', 'mutex_block',
  'task_health',
]
// Factory default: every section starts collapsed. SMP-active traces expand+pin
// Core Utilisation via defaultStatsPresentation() (Step 1.1).
export const STATS_DEFAULT_EXPANDED_SECTIONS = []
export const COMMAND_PALETTE_ACTIONS = [
  ['analysis', 'Analysis Findings'],
  ['statistics', 'Statistics'],
  ['find', 'Find'],
  ['marks', 'Marks'],
  ['ai', 'AI Assistant'],
  ['compare', 'Trace Compare'],
  ['heatmap', 'Migration heatmap'],
  ['settings', 'Settings'],
  ['limit-scope', 'Limit to C1–Cn'],
  ['fit', 'Fit Trace'],
  ['inspect-task', 'Inspect task'],
  ['preset-triage', 'Workspace: Triage'],
  ['preset-latency', 'Workspace: Latency'],
  ['preset-smp', 'Workspace: SMP'],
  ['preset-compare', 'Workspace: Compare'],
]
/** Per-action palette chrome. Keep ACTIONS as [id, label] for compatibility.
 *  requires: none | trace | two_traces | cursors2 */
export const COMMAND_PALETTE_META = Object.freeze({
  analysis: {
    shortcut: '',
    synonyms: ['findings', 'inbox', 'triage'],
    requires: 'trace',
    disabled: 'Open a trace first',
  },
  statistics: {
    shortcut: '',
    synonyms: ['stats', 'metrics'],
    requires: 'trace',
    disabled: 'Open a trace first',
  },
  find: {
    shortcut: 'Ctrl+F',
    synonyms: ['search', 'locate'],
    requires: 'trace',
    disabled: 'Open a trace first',
  },
  marks: {
    shortcut: 'Ctrl+B',
    synonyms: ['bookmarks', 'annotations', 'notes'],
    requires: 'trace',
    disabled: 'Open a trace first',
  },
  ai: {
    shortcut: '',
    synonyms: ['assistant', 'chat', 'llm'],
    requires: 'trace',
    disabled: 'Open a trace first',
  },
  compare: {
    shortcut: '',
    synonyms: ['diff', 'regression'],
    requires: 'two_traces',
    disabled: 'Open at least two traces',
  },
  heatmap: {
    shortcut: '',
    synonyms: ['migration', 'corridor'],
    requires: 'trace',
    disabled: 'Open a trace first',
  },
  settings: {
    shortcut: 'Ctrl+,',
    synonyms: ['preferences', 'options', 'config'],
    requires: 'none',
    disabled: '',
  },
  'limit-scope': {
    shortcut: '',
    synonyms: ['scope', 'c1', 'c2'],
    requires: 'cursors2',
    disabled: 'Place at least two cursors (C1–Cn)',
  },
  fit: {
    shortcut: 'Ctrl+0',
    synonyms: ['zoom', 'reset', 'overview', 'fit trace'],
    requires: 'trace',
    disabled: 'Open a trace first',
  },
  'inspect-task': {
    shortcut: 'I',
    synonyms: ['inspector', 'task info', 'quality'],
    requires: 'trace',
    disabled: 'Open a trace first',
  },
  'preset-triage': {
    shortcut: '',
    synonyms: ['workspace', 'health'],
    requires: 'trace',
    disabled: 'Open a trace first',
  },
  'preset-latency': {
    shortcut: '',
    synonyms: ['workspace', 'timing', 'response'],
    requires: 'trace',
    disabled: 'Open a trace first',
  },
  'preset-smp': {
    shortcut: '',
    synonyms: ['workspace', 'multicore', 'cores'],
    requires: 'trace',
    disabled: 'Open a trace first',
  },
  'preset-compare': {
    shortcut: '',
    synonyms: ['workspace', 'diff'],
    requires: 'two_traces',
    disabled: 'Open at least two traces',
  },
})
export const COMMAND_PALETTE_RECENT_MAX = 8
export const WORKSPACE_PRESETS = {
  'preset-triage': ['health', 'anomalies', 'worst', 'task_health'],
  'preset-latency': ['exec', 'response', 'jitter', 'period', 'dispatch'],
  'preset-smp': ['migrations', 'core_pairs', 'affinity', 'task_core', 'cores'],
  'preset-compare': [],
}

export function workspacePresetCollapsed(presetId, defaults) {
  const flags = { ...(defaults || {}) }
  for (const sid of WORKSPACE_PRESETS[String(presetId || '')] || []) {
    if (sid in flags) flags[sid] = false
  }
  return flags
}

function commandPaletteNorm(text) {
  return String(text || '').toLowerCase().replace(/[^\w]+/g, '')
}

/** True when query matches id, label, or meta synonyms (empty query = all). */
export function commandPaletteMatch(query, actionId, label, meta) {
  const q = String(query || '').trim().toLowerCase()
  if (!q) return true
  const m = meta && typeof meta === 'object' ? meta : {}
  const parts = [String(actionId || ''), String(label || '')]
  for (const s of m.synonyms || []) parts.push(String(s))
  for (const part of parts) {
    if (part.toLowerCase().includes(q)) return true
  }
  const qn = commandPaletteNorm(q)
  if (!qn) return true
  return parts.some(part => commandPaletteNorm(part).includes(qn))
}

function commandPaletteMatchScore(query, actionId, label, meta) {
  const q = String(query || '').trim().toLowerCase()
  if (!q) return 0
  const m = meta && typeof meta === 'object' ? meta : {}
  const aid = String(actionId || '').toLowerCase()
  const lab = String(label || '').toLowerCase()
  const syns = (m.synonyms || []).map(s => String(s).toLowerCase())
  if (aid === q || lab === q) return 100
  if (syns.some(s => s === q)) return 90
  if (aid.startsWith(q) || lab.startsWith(q)) return 80
  if (syns.some(s => s.startsWith(q))) return 70
  if (aid.includes(q) || lab.includes(q)) return 50
  if (syns.some(s => s.includes(q))) return 40
  const qn = commandPaletteNorm(q)
  if (qn && commandPaletteNorm(lab).includes(qn)) return 30
  return 10
}

/**
 * Rank palette rows: recent/frequent when idle; scored matches when filtering.
 * Each row: { id, label, shortcut, available, reason }.
 * availabilityFn(aid) -> { available, reason } or [available, reason].
 */
export function commandPaletteRank(
  actions,
  query = '',
  recentIds = [],
  frequentCounts = {},
  availabilityFn = null,
) {
  const recent = (recentIds || []).map(String).filter(Boolean)
  const recentRank = new Map(recent.map((aid, i) => [aid, i]))
  const freqMap = {}
  for (const [k, v] of Object.entries(frequentCounts || {})) {
    const n = Number(v)
    if (Number.isFinite(n)) freqMap[String(k)] = n
  }
  const defaultOrder = new Map(
    (actions || []).map(([aid], i) => [String(aid), i]),
  )
  const q = String(query || '').trim()
  const rows = []
  for (const [aid, label] of actions || []) {
    const aidS = String(aid)
    const labelS = String(label)
    const meta = COMMAND_PALETTE_META[aidS] || {}
    if (q && !commandPaletteMatch(q, aidS, labelS, meta)) continue
    let available = true
    let reason = ''
    if (typeof availabilityFn === 'function') {
      try {
        const res = availabilityFn(aidS)
        if (Array.isArray(res)) {
          available = !!res[0]
          reason = String(res[1] || '')
        } else if (res && typeof res === 'object') {
          available = res.available !== false
          reason = String(res.reason || '')
        }
      } catch {
        available = true
        reason = ''
      }
    }
    if (!available && !reason) {
      reason = String(meta.disabled || 'Unavailable')
    }
    rows.push({
      id: aidS,
      label: labelS,
      shortcut: String(meta.shortcut || ''),
      available,
      reason: available ? '' : reason,
      _score: q ? commandPaletteMatchScore(q, aidS, labelS, meta) : 0,
    })
  }
  rows.sort((a, b) => {
    const aDef = defaultOrder.get(a.id) ?? 10000
    const bDef = defaultOrder.get(b.id) ?? 10000
    if (!q) {
      const aR = recentRank.has(a.id)
      const bR = recentRank.has(b.id)
      if (aR || bR) {
        if (aR && bR) return recentRank.get(a.id) - recentRank.get(b.id)
        return aR ? -1 : 1
      }
      const aF = freqMap[a.id] || 0
      const bF = freqMap[b.id] || 0
      if (aF > 0 || bF > 0) {
        if (aF !== bF) return bF - aF
        return aDef - bDef
      }
      return aDef - bDef
    }
    if (b._score !== a._score) return b._score - a._score
    const aR = recentRank.has(a.id)
    const bR = recentRank.has(b.id)
    if (aR !== bR) return aR ? -1 : 1
    if (aR && bR) return recentRank.get(a.id) - recentRank.get(b.id)
    const aF = freqMap[a.id] || 0
    const bF = freqMap[b.id] || 0
    if (aF !== bF) return bF - aF
    return aDef - bDef
  })
  for (const row of rows) delete row._score
  return rows
}

/** Help under each Statistics section title. Keep lockstep with config.py STATS_SECTION_HELP. */
export const STATS_SECTION_HELP = Object.freeze({
  cores: "Per-core busy percent excluding IDLE and TICK. The gauge scores load balance across cores. Drag the grip to show more cores.",
  health: "TICK interval regularity, missed-tick estimate, and large gaps. Click a gap to jump. Tickless traces are expected to have uneven intervals.",
  core_breakdown: "How each core's scoped span splits into active task time, IDLE, TICK, and leftover gap. Click a core to show it in Core View.",
  concurrency: "How much of the scoped span had 0, 1, 2, … cores running a user task at once. Click a row to open the concurrency plot.",
  switch_overhead: "Time from one task leaving a core to the next task running (kernel switch gap). Click a core to open the switch-overhead plot.",
  tasks: "Top user tasks by CPU share of the scoped span, excluding IDLE and TICK. Click a name to highlight that task on the timeline.",
  migrations: "Tasks that ran on more than one core: count, rate, dwell, ping-pong, and STI proximity. Click a row to open the migration plot.",
  core_pairs: "Directed core-to-core migration counts, bounce-backs, and average gap. Click a pair to open the pair plot.",
  affinity: "Last affinity mask vs cores actually used. Violations are runs outside the mask. Click a task to highlight it.",
  task_core: "Share of the scoped span each task spent on each core. Click a cell to jump to the first slice on that core.",
  core_time: "Per-core busy percent in equal time bins of the current scope. Click a bin to zoom that window.",
  lifecycle: "Create, delete, suspend, and resume STI events, plus alive span and run count. Click a task to jump to create (when present) and highlight it.",
  deadline: "Slice duration vs per-task deadline, and CPU% vs budget. Configure thresholds in Settings → Display. Click a row to jump to that slice.",
  task_health: "Heuristic score from measured statistics, not an AI probability. Click a band to open that Statistics section.",
  anomalies: "Unusual long tails, migration / preemption / ISR / wakeup bursts, CPU spikes, idle gaps, response-time tails, mutex-wait spikes, and deadline misses in the current scope. Click a row to zoom, place C1–C2, and open the matching table. Investigate… sends the selected (or top) anomaly to the AI tab.",
  worst: "Longest execution, blocking, inter-arrival, and heuristic response episodes. Click a row to jump and set cursors on that episode.",
  crit_path: "Longest heuristic ready→completion windows. Exec is own on-CPU time; Off-CPU is Duration − Exec. Preempt, Wait, and Migration overlap and are not a stacked split of Duration. Click a component to jump to that episode. Not a kernel release/completion pair.",
  patterns: "Anomaly kinds that repeat for the same task in this scope. Click a row to jump to the worst instance.",
  exec: "On-CPU slice duration per task: runs, CPU%, min/avg/max, jitter (max−min), σ, p95, and p99. Click the task for the plot; click min, max, p95, or p99 to jump to that slice.",
  block: "Off-CPU gap from one slice end to the next activation. Click the task for the plot; click min, max, p95, or p99 to jump to that gap.",
  response: "Heuristic ready→completion from the previous slice end to this slice end (first slice = exec duration). Not an explicit BTF release/completion pair. Click the task to open the Response plot; click Min / Max / p50 / p90 / p95 / p99 / p99.9 to jump to that event.",
  dispatch: "Ready time from STI resume / create; dispatch = next switch-in. Sync-object wakes are not attributed (no woken-task id in BTF).",
  inter: "Time between successive activations of the same task. Click the task for the plot; click min, max, p95, or p99 to jump to that gap.",
  period: "Expected period is the median inter-arrival. Missed = gap > 1.5× expected; extra = gap < 0.5× expected; burst = gap < 0.25× expected. Spark is inter-arrival over time. Click a time to jump; click the task to open the Inter-arrival plot.",
  jitter: "Max−min spread and CV for execution, blocking, inter-arrival, heuristic response, STI dispatch latency, and wake-to-run (response wait stand-in). Click a column to open the matching plot.",
  distrib: "Pick a metric and task, then open the existing histogram/CDF plot. Wake is heuristic response wait; dispatch uses STI resume/create → switch-in.",
  preemption: "Victim × preemptor pairs while the victim is off-CPU on the same core. Click a row to open the preemption plot for that pair.",
  preempt_matrix: "Victim × preemptor overlap during off-CPU gaps on the same core. Click a ranking row or matrix cell to jump to the longest overlap.",
  priority: "Tasks boosted above their create priority by set_priority STI events. Orange bands = boost; red = classic L/M/H pattern (medium-priority task between base and peak).",
  sync: "Pairs take/give STI events by object pointer (0x........). Flags orphan gives, unmatched takes, delete-while-held, and multi-mutex hold at trace end (deadlock risk).",
  wait_owner: "Heuristic mutex handoff matrix: the next distinct acquirer is treated as the waiter for the previous hold. Not a kernel wait queue. Click a cell to zoom the longest handoff.",
  mutex_block: "Per-task mutex wait totals from heuristic handoffs (next distinct acquirer × previous holder). Not a kernel wait queue. Click a row to jump to the longest wait.",
  queue: "Pairs send/recv STI events by queue pointer (0x........).",
  intervals: "Paired interval_start / interval_stop STI events. Click a row to open the interval plot.",
  tags: "tag0_event … tag7_event STI sample values. Click a row to open the tag plot.",
})
