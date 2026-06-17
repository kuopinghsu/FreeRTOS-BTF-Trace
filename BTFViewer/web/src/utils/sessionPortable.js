/**
 * Portable session export/import (cursors, marks, viewport) — Desktop + Web compatible JSON.
 */

export const SESSION_PORTABLE_VERSION = 1

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
  const data = JSON.parse(text)
  if (!data || typeof data !== 'object') throw new Error('Invalid session file')
  if (data.version !== SESSION_PORTABLE_VERSION) {
    throw new Error(`Unsupported session version: ${data.version}`)
  }
  return data
}

export function applyPortableSession(tab, data, timelineOptions) {
  if (!tab || !data) return
  if (data.cursors?.length) tab.cursors = [...data.cursors]
  if (data.marks) tab.marks = JSON.parse(JSON.stringify(data.marks))
  if (data.markNextId != null) tab.markNextId = data.markNextId
  tab.findQuery = data.findQuery ?? ''
  tab.findMode = data.findMode ?? 'contains'
  tab.pinnedHighlightKey = data.pinnedHighlightKey ?? null
  if (data.timelineViewport) {
    Object.assign(tab.timelineViewport, data.timelineViewport)
  }
  if (timelineOptions && data.timelineOptions) {
    Object.assign(timelineOptions, data.timelineOptions)
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
