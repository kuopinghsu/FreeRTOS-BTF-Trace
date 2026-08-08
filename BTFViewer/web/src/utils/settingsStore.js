/** Persistent web viewer settings (localStorage). Parity with desktop btf_viewer.rc / btf_viewer.py USER CONFIGURATION. */
import { syncTimelineLayoutFromSettings } from './timelineLayout.js'
import { normalizeStatsPins, normalizeStatsSectionOrder } from './statsPins.js'
import {
  AI_PRESETS,
  DEFAULT_AI_PRESET,
  DEFAULT_AI_RESPONSE_LANGUAGE,
  migrateAiSettings,
  normalizeAiPreset,
} from './ollamaClient.js'

const SETTINGS_KEY = 'btf-viewer-settings-v1'

export const MAX_CURSORS = 8

/** Defaults mirror btf_viewer.py: FONT_SIZE, UI_FONT_SIZE, LABEL_WIDTH, ROW_HEIGHT, … */
export const DEFAULT_SETTINGS = {
  darkMode: true,
  colorblindSafe: false,
  labelFontSize: 8,
  uiFontSize: 8,
  showLegend: true,
  showStats: true,
  showMarks: true,
  showCpuLoad: true,
  showSti: true,
  showGrid: true,
  hoverHighlight: false,
  // Desktop rc parity: [view] view_mode / horizontal
  viewMode: 'task',
  orientation: 'h',
  stiLogScale: false,
  labelWidth: 160,
  rowHeight: 22,
  rowGap: 4,
  stiRowH: 18,
  stiWaveformH: 80,
  stiLineStyle: 'linear',
  timescalePerPxDefault: 2,
  maxCursors: 4,
  cpuLoadRowH: 30,
  cpuBudgetPct: 0,
  taskDeadlines: {},
  timeDecimals: 3,
  statsPinnedSections: [],
  statsSectionOrder: [],
  showAi: true,
  aiEnabled: true,
  aiPreset: DEFAULT_AI_PRESET,
  // Per-preset base URL / model / API key; empty means "preset default".
  aiPresets: Object.fromEntries(
    AI_PRESETS.map((p) => [p.id, { baseUrl: '', model: '', apiKey: '' }]),
  ),
  aiResponseLanguage: DEFAULT_AI_RESPONSE_LANGUAGE,
}

/** Per-preset AI fields, migrating any pre-preset settings on the way. */
function normalizeAiPresetSettings(s) {
  const migrated = migrateAiSettings(s) || {}
  const stored = { ...(s.aiPresets || {}) }
  for (const [pid, vals] of Object.entries(migrated.aiPresets || {})) {
    stored[pid] = { ...(stored[pid] || {}), ...vals }
  }
  const out = {}
  for (const preset of AI_PRESETS) {
    const v = stored[preset.id] || {}
    out[preset.id] = {
      baseUrl: String(v.baseUrl || '').trim().replace(/\/+$/, ''),
      model: String(v.model || '').trim(),
      apiKey: String(v.apiKey || '').trim(),
    }
  }
  return { presets: out, preset: migrated.aiPreset || '' }
}

function clampInt(v, lo, hi, fallback) {
  const n = Number.parseInt(v, 10)
  if (!Number.isFinite(n)) return fallback
  return Math.max(lo, Math.min(hi, n))
}

function clampFloat(v, lo, hi, fallback) {
  const n = Number.parseFloat(v)
  if (!Number.isFinite(n)) return fallback
  return Math.max(lo, Math.min(hi, n))
}

/** @returns {typeof DEFAULT_SETTINGS} */
export function normalizeSettings(raw) {
  const s = { ...DEFAULT_SETTINGS, ...(raw && typeof raw === 'object' ? raw : {}) }
  // Migration reads the raw object: merged defaults would mask "never set".
  const ai = normalizeAiPresetSettings(raw && typeof raw === 'object' ? raw : {})
  return {
    darkMode: !!s.darkMode,
    colorblindSafe: !!s.colorblindSafe,
    labelFontSize: clampInt(s.labelFontSize, 6, 24, DEFAULT_SETTINGS.labelFontSize),
    uiFontSize: clampInt(s.uiFontSize, 8, 18, DEFAULT_SETTINGS.uiFontSize),
    showLegend: s.showLegend !== false,
    showStats: s.showStats !== false,
    showMarks: s.showMarks !== false,
    showCpuLoad: s.showCpuLoad !== false,
    showSti: s.showSti !== false,
    showGrid: !!s.showGrid,
    hoverHighlight: !!s.hoverHighlight,
    viewMode: s.viewMode === 'core' ? 'core' : 'task',
    orientation: s.orientation === 'v' ? 'v' : 'h',
    stiLogScale: !!s.stiLogScale,
    labelWidth: clampInt(s.labelWidth, 60, 600, DEFAULT_SETTINGS.labelWidth),
    rowHeight: clampInt(s.rowHeight, 12, 60, DEFAULT_SETTINGS.rowHeight),
    rowGap: clampInt(s.rowGap, 0, 20, DEFAULT_SETTINGS.rowGap),
    stiRowH: clampInt(s.stiRowH, 12, 60, DEFAULT_SETTINGS.stiRowH),
    stiWaveformH: clampInt(s.stiWaveformH, 40, 300, DEFAULT_SETTINGS.stiWaveformH),
    stiLineStyle: s.stiLineStyle === 'step' ? 'step' : 'linear',
    timescalePerPxDefault: clampFloat(
      s.timescalePerPxDefault, 0.5, 200, DEFAULT_SETTINGS.timescalePerPxDefault),
    maxCursors: clampInt(s.maxCursors, 4, MAX_CURSORS, DEFAULT_SETTINGS.maxCursors),
    cpuLoadRowH: clampInt(s.cpuLoadRowH, 16, 120, DEFAULT_SETTINGS.cpuLoadRowH),
    cpuBudgetPct: clampFloat(s.cpuBudgetPct, 0, 100, DEFAULT_SETTINGS.cpuBudgetPct),
    taskDeadlines: (s.taskDeadlines && typeof s.taskDeadlines === 'object') ? { ...s.taskDeadlines } : {},
    timeDecimals: clampInt(s.timeDecimals, 0, 9, DEFAULT_SETTINGS.timeDecimals),
    statsPinnedSections: normalizeStatsPins(s.statsPinnedSections),
    statsSectionOrder: normalizeStatsSectionOrder(s.statsSectionOrder),
    showAi: s.showAi !== false,
    aiEnabled: s.aiEnabled !== false,
    aiPreset: normalizeAiPreset(ai.preset || s.aiPreset || DEFAULT_AI_PRESET),
    aiPresets: ai.presets,
    aiResponseLanguage: String(s.aiResponseLanguage || DEFAULT_SETTINGS.aiResponseLanguage).trim()
      || DEFAULT_SETTINGS.aiResponseLanguage,
  }
}

export function loadSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY)
    return normalizeSettings(raw ? JSON.parse(raw) : null)
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
}

export function saveSettings(settings) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(normalizeSettings(settings)))
  } catch {
    /* quota / private mode */
  }
}

export function applySettingsToRuntime(settings) {
  const s = normalizeSettings(settings)
  syncTimelineLayoutFromSettings(s)
  if (typeof document !== 'undefined') {
    document.documentElement.style.setProperty('--ui-font-size', `${s.uiFontSize}px`)
  }
  return s
}

/** Format taskDeadlines map for the Settings Display textarea. */
export function formatDeadlinesText(map) {
  if (!map || typeof map !== 'object') return ''
  return Object.entries(map)
    .map(([k, v]) => `${k}=${v}`)
    .join('\n')
}

/**
 * Parse "TaskName=ns" lines from the Settings Display textarea.
 * Incomplete lines (no `=value` yet) are ignored so live preview can run
 * without wiping in-progress edits.
 */
export function parseDeadlinesText(text) {
  const out = {}
  for (const line of String(text || '').split(/\r?\n/)) {
    const t = line.trim()
    if (!t || t.startsWith('#')) continue
    const eq = t.indexOf('=')
    if (eq <= 0) continue
    const key = t.slice(0, eq).trim()
    const val = Number.parseInt(t.slice(eq + 1).trim(), 10)
    if (key && Number.isFinite(val) && val > 0) out[key] = val
  }
  return out
}

/**
 * Whether the deadlines textarea should be replaced from props.
 * Returns false when the only change is a live-preview round-trip of the
 * same parsed map — so typing incomplete lines is not wiped.
 */
export function shouldReplaceDeadlinesText(currentText, incomingMap) {
  const incoming = formatDeadlinesText(incomingMap)
  const currentParsed = formatDeadlinesText(parseDeadlinesText(currentText))
  return incoming !== currentParsed
}

/** Resize every tab's cursor array to match maxCursors. */
export function resizeTabCursors(tabs, maxCursors) {
  const max = clampInt(maxCursors, 4, MAX_CURSORS, DEFAULT_SETTINGS.maxCursors)
  for (const tab of tabs || []) {
    const cur = Array.isArray(tab.cursors) ? [...tab.cursors] : []
    if (cur.length < max) {
      tab.cursors = [...cur, ...Array(max - cur.length).fill(null)]
    } else if (cur.length > max) {
      tab.cursors = cur.slice(0, max)
    }
  }
}
