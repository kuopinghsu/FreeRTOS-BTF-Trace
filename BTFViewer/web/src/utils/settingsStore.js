/** Persistent web viewer settings (localStorage). Defaults live in ``src/config.js``. */
import {
  COLORBLIND_SAFE,
  CPU_BUDGET_PCT,
  CPU_LOAD_ROW_H,
  DARK_MODE,
  DEFAULT_MAX_CURSORS,
  FONT_SIZE,
  HOVER_HIGHLIGHT,
  LABEL_WIDTH,
  MAX_CURSORS,
  ORIENTATION,
  ROW_GAP,
  ROW_HEIGHT,
  SHOW_AI,
  SHOW_CPU_LOAD,
  SHOW_FIND,
  SHOW_GRID,
  SHOW_LEGEND,
  SHOW_MARKS,
  SHOW_STATS,
  SHOW_STI,
  STI_LINE_STYLE,
  STI_LOG_SCALE,
  STI_ROW_H,
  STI_WAVEFORM_H,
  TIME_DECIMALS,
  TIMESCALE_PER_PX_DEFAULT,
  UI_FONT_SIZE,
  VIEW_MODE,
} from '../config.js'
import { syncTimelineLayoutFromSettings } from './timelineLayout.js'
import { normalizeStatsPins, normalizeStatsSectionOrder } from './statsPins.js'
import {
  AI_PRESETS,
  DEFAULT_AI_PRESET,
  DEFAULT_AI_RESPONSE_LANGUAGE,
  migrateAiSettings,
  normalizeAiAuthMode,
  normalizeAiPreset,
  parseAiTlsVerify,
  parseExtraAiPresets,
  sanitizeAiPresetId,
  aiPresetDisplayLabel,
} from './ollamaClient.js'
import {
  dumpUserHistoricalKnowledge,
  dumpUserInvestigationTemplates,
  parseUserHistoricalKnowledge,
  parseUserInvestigationTemplates,
} from './aiCase.js'

const SETTINGS_KEY = 'btf-viewer-settings-v1'
// Separate key: baseline profiles grow with usage and are not GUI prefs.
const AI_BASELINE_KEY = 'btf-viewer-ai-baseline-v1'
const AI_USER_TEMPLATES_KEY = 'btf-viewer-ai-user-templates-v1'
const AI_USER_KNOWLEDGE_KEY = 'btf-viewer-ai-user-knowledge-v1'

export { MAX_CURSORS }

export const DEFAULT_SETTINGS = {
  darkMode: DARK_MODE,
  colorblindSafe: COLORBLIND_SAFE,
  labelFontSize: FONT_SIZE,
  uiFontSize: UI_FONT_SIZE,
  showLegend: SHOW_LEGEND,
  showStats: SHOW_STATS,
  showMarks: SHOW_MARKS,
  showFind: SHOW_FIND,
  showCpuLoad: SHOW_CPU_LOAD,
  showSti: SHOW_STI,
  showGrid: SHOW_GRID,
  hoverHighlight: HOVER_HIGHLIGHT,
  viewMode: VIEW_MODE,
  orientation: ORIENTATION,
  stiLogScale: STI_LOG_SCALE,
  labelWidth: LABEL_WIDTH,
  rowHeight: ROW_HEIGHT,
  rowGap: ROW_GAP,
  stiRowH: STI_ROW_H,
  stiWaveformH: STI_WAVEFORM_H,
  stiLineStyle: STI_LINE_STYLE,
  timescalePerPxDefault: TIMESCALE_PER_PX_DEFAULT,
  maxCursors: DEFAULT_MAX_CURSORS,
  cpuLoadRowH: CPU_LOAD_ROW_H,
  cpuBudgetPct: CPU_BUDGET_PCT,
  taskDeadlines: {},
  timeDecimals: TIME_DECIMALS,
  statsPinnedSections: [],
  statsSectionOrder: [],
  showAi: SHOW_AI,
  aiEnabled: true,
  aiPreset: DEFAULT_AI_PRESET,
  // Per-preset base URL / model / API key; empty means "preset default".
  aiPresets: Object.fromEntries(
    AI_PRESETS.map((p) => [p.id, { baseUrl: '', model: '', apiKey: '', authMode: '', tlsVerify: true }]),
  ),
  aiResponseLanguage: DEFAULT_AI_RESPONSE_LANGUAGE,
  aiAutoApply: false,
  aiRedactTaskNames: false,
  aiTraceSensitive: false,
  aiExtraPresets: [],
}

/** Per-preset AI fields, migrating any pre-preset settings on the way. */
function normalizeAiPresetSettings(s) {
  const migrated = migrateAiSettings(s) || {}
  const stored = { ...(s.aiPresets || {}) }
  for (const [pid, vals] of Object.entries(migrated.aiPresets || {})) {
    stored[pid] = { ...(stored[pid] || {}), ...vals }
  }
  const extra = parseExtraAiPresets(s.aiExtraPresets)
  const seen = new Set(extra.map((e) => e.id))
  for (const pid of Object.keys(stored)) {
    const id = sanitizeAiPresetId(pid)
    if (id && !AI_PRESETS.some((p) => p.id === id) && !seen.has(id)) {
      extra.push({ id, label: aiPresetDisplayLabel(id) })
      seen.add(id)
    }
  }
  const out = {}
  const catalog = [
    ...AI_PRESETS,
    ...extra.map((e) => ({ id: e.id, label: e.label, baseUrl: '', model: '' })),
  ]
  for (const preset of catalog) {
    const v = stored[preset.id] || {}
    const baseUrl = String(v.baseUrl || '').trim().replace(/\/+$/, '')
    out[preset.id] = {
      baseUrl,
      model: String(v.model || '').trim(),
      apiKey: String(v.apiKey || '').trim(),
      authMode: normalizeAiAuthMode(v.authMode, {
        presetId: preset.id,
        baseUrl: baseUrl || preset.baseUrl,
      }),
      tlsVerify: parseAiTlsVerify(v.tlsVerify, true),
    }
  }
  return { presets: out, preset: migrated.aiPreset || '', extraPresets: extra }
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
    showFind: s.showFind !== false,
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
    aiExtraPresets: ai.extraPresets || [],
    aiResponseLanguage: String(s.aiResponseLanguage || DEFAULT_SETTINGS.aiResponseLanguage).trim()
      || DEFAULT_SETTINGS.aiResponseLanguage,
    aiAutoApply: !!s.aiAutoApply,
    aiRedactTaskNames: !!s.aiRedactTaskNames,
    aiTraceSensitive: !!s.aiTraceSensitive,
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

/** Historical per-task baseline profile (see aiInvestigation.js updateBaselineProfile). */
export function loadAiBaselineProfile() {
  try {
    const raw = localStorage.getItem(AI_BASELINE_KEY)
    const data = raw ? JSON.parse(raw) : null
    return (data && typeof data === 'object') ? data : {}
  } catch {
    return {}
  }
}

export function saveAiBaselineProfile(profile) {
  try {
    localStorage.setItem(AI_BASELINE_KEY, JSON.stringify(profile || {}))
  } catch {
    /* quota / private mode */
  }
}

/** User-saved investigation sequences (More → Investigations). */
export function loadAiUserInvestigationTemplates() {
  try {
    const raw = localStorage.getItem(AI_USER_TEMPLATES_KEY)
    return parseUserInvestigationTemplates(raw || '[]')
  } catch {
    return []
  }
}

export function saveAiUserInvestigationTemplates(items) {
  try {
    localStorage.setItem(
      AI_USER_TEMPLATES_KEY,
      dumpUserInvestigationTemplates(items),
    )
  } catch {
    /* quota / private mode */
  }
}

export function loadAiUserHistoricalKnowledge() {
  try {
    const raw = localStorage.getItem(AI_USER_KNOWLEDGE_KEY)
    return parseUserHistoricalKnowledge(raw || '[]')
  } catch {
    return []
  }
}

export function saveAiUserHistoricalKnowledge(items) {
  try {
    localStorage.setItem(
      AI_USER_KNOWLEDGE_KEY,
      dumpUserHistoricalKnowledge(items),
    )
  } catch {
    /* quota / private mode */
  }
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
