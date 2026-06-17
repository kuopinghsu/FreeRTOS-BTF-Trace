/**
 * Portable session export/import (cursors, marks, viewport) — Desktop + Web compatible JSON.
 */

import { isRestorableViewport } from './sessionStore.js'
import { MAX_CURSORS } from './settingsStore.js'

export const SESSION_PORTABLE_VERSION = 1
export const SESSION_MAX_BYTES = 2 * 1024 * 1024

const PORTABLE_FIND_MODES = ['contains', 'exact', 'regex', 'migrations']
const TIMELINE_OPTION_KEYS = [
  'viewMode', 'orientation', 'showGrid', 'showSti', 'showCpuLoad', 'darkMode', 'migratedOnlyFilter',
]

export function buildPortableSession({
  traceName,
  cursors,
  marks,
  markNextId,
  timelineViewport,
  timelineOptions,
  findQuery,
  findMode,
  pinnedHighlightKey,
}) {
  return {
    version: SESSION_PORTABLE_VERSION,
    traceName: traceName || '',
    exportedAt: new Date().toISOString(),
    cursors: cursors ? [...cursors] : [],
    marks: marks ? JSON.parse(JSON.stringify(marks)) : [],
    markNextId: markNextId ?? 1,
    timelineViewport: timelineViewport ? { ...timelineViewport } : null,
    timelineOptions: timelineOptions ? {
      viewMode: timelineOptions.viewMode,
      orientation: timelineOptions.orientation,
      showGrid: timelineOptions.showGrid,
      showSti: timelineOptions.showSti,
      showCpuLoad: timelineOptions.showCpuLoad,
      darkMode: timelineOptions.darkMode,
      migratedOnlyFilter: timelineOptions.migratedOnlyFilter,
    } : null,
    findQuery: findQuery ?? '',
    findMode: findMode ?? 'contains',
    pinnedHighlightKey: pinnedHighlightKey ?? null,
  }
}

export function parsePortableSession(text) {
  if (typeof text !== 'string') throw new Error('Invalid session file')
  if (text.length > SESSION_MAX_BYTES) {
    throw new Error(`Session file too large (max ${SESSION_MAX_BYTES / (1024 * 1024)} MB)`)
  }
  const data = JSON.parse(text)
  if (!data || typeof data !== 'object') throw new Error('Invalid session file')
  if (data.version !== SESSION_PORTABLE_VERSION) {
    throw new Error(`Unsupported session version: ${data.version}`)
  }
  return data
}

function sanitizeCursors(cursors) {
  if (!Array.isArray(cursors)) return []
  return cursors.map((c) => {
    if (c == null) return null
    const n = Number.parseInt(c, 10)
    return Number.isFinite(n) ? n : null
  })
}

function sanitizeMarks(marks) {
  if (!Array.isArray(marks)) return { marks: [], markNextId: 1 }
  const out = []
  let maxId = 1
  for (const m of marks) {
    if (!m || typeof m !== 'object') continue
    const id = Number.parseInt(m.id, 10)
    const ns = Number.parseInt(m.ns, 10)
    if (!Number.isFinite(id) || !Number.isFinite(ns)) continue
    const type = m.type === 'annotation' ? 'annotation' : 'bookmark'
    out.push({
      id,
      ns,
      label: String(m.label ?? ''),
      type,
    })
    maxId = Math.max(maxId, id + 1)
  }
  return { marks: out, markNextId: maxId }
}

function sanitizeViewport(vp, trace) {
  if (!vp || typeof vp !== 'object') return null
  const t0 = Number(vp.timeStart)
  const t1 = Number(vp.timeEnd)
  if (!Number.isFinite(t0) || !Number.isFinite(t1) || t1 <= t0) return null
  const clean = {
    timeStart: t0,
    timeEnd: t1,
    scrollY: Number.isFinite(Number(vp.scrollY)) ? Number(vp.scrollY) : 0,
    scrollX: Number.isFinite(Number(vp.scrollX)) ? Number(vp.scrollX) : 0,
    canvasW: Math.max(1, Number(vp.canvasW) || 1),
    canvasH: Math.max(1, Number(vp.canvasH) || 1),
  }
  if (trace && !isRestorableViewport(clean, trace)) return null
  return clean
}

function sanitizeTimelineOptions(src) {
  if (!src || typeof src !== 'object') return null
  const out = {}
  for (const k of TIMELINE_OPTION_KEYS) {
    if (!(k in src)) continue
    const v = src[k]
    if (k === 'viewMode') {
      if (v === 'task' || v === 'core') out.viewMode = v
    } else if (k === 'orientation') {
      if (v === 'h' || v === 'v') out.orientation = v
    } else if (typeof v === 'boolean') {
      out[k] = v
    }
  }
  return Object.keys(out).length ? out : null
}

/** Cursor slot count needed after import (parity with desktop). */
export function sessionCursorsSlotCount(data, currentMax = 4) {
  if (!data?.cursors || !Array.isArray(data.cursors)) return currentMax
  const placed = data.cursors.some((c) => c != null)
  if (!placed) return currentMax
  return Math.min(MAX_CURSORS, Math.max(currentMax, data.cursors.length))
}

/**
 * @param {object} tab
 * @param {object} data parsed session
 * @param {object} [timelineOptions]
 * @param {object} [trace] loaded trace (for viewport validation)
 */
export function applyPortableSession(tab, data, timelineOptions, trace = null) {
  if (!tab || !data) return

  if (data.cursors != null) {
    tab.cursors = sanitizeCursors(data.cursors)
  }

  if (data.marks != null) {
    const { marks, markNextId } = sanitizeMarks(data.marks)
    tab.marks = marks
    if (data.markNextId != null) {
      const mid = Number.parseInt(data.markNextId, 10)
      tab.markNextId = Number.isFinite(mid) ? mid : markNextId
    } else {
      tab.markNextId = markNextId
    }
  }

  const mode = String(data.findMode || 'contains').toLowerCase()
  tab.findMode = PORTABLE_FIND_MODES.includes(mode) ? mode : 'contains'
  tab.findQuery = typeof data.findQuery === 'string' ? data.findQuery : ''

  tab.pinnedHighlightKey = (data.pinnedHighlightKey != null && data.pinnedHighlightKey !== '')
    ? String(data.pinnedHighlightKey)
    : null

  const vp = sanitizeViewport(data.timelineViewport, trace)
  if (vp) Object.assign(tab.timelineViewport, vp)

  const opts = sanitizeTimelineOptions(data.timelineOptions)
  if (timelineOptions && opts) {
    Object.assign(timelineOptions, opts)
    if (tab.pinnedHighlightKey != null) {
      timelineOptions.highlightKey = tab.pinnedHighlightKey
      timelineOptions.lockedTaskKey = tab.pinnedHighlightKey
    } else {
      timelineOptions.highlightKey = null
      timelineOptions.lockedTaskKey = null
    }
  }
}

export function downloadPortableSession(payload, filename = 'btf-session.json') {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
