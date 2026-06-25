/** Persistent web viewer settings (localStorage). Parity with desktop btf_viewer.rc / btf_viewer.py USER CONFIGURATION. */
import { syncTimelineLayoutFromSettings } from './timelineLayout.js'

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
  labelWidth: 160,
  rowHeight: 22,
  rowGap: 4,
  stiRowH: 18,
  stiWaveformH: 80,
  stiLineStyle: 'linear',
  timescalePerPxDefault: 2,
  maxCursors: 4,
  cpuLoadRowH: 30,
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
