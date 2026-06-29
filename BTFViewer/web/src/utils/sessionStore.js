/** Persist web viewer layout, tabs, and per-trace state in localStorage. */

const SESSION_KEY = 'btf-viewer-session-v2'

export function loadSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
      || localStorage.getItem('btf-viewer-session-v1')
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function saveSession(session) {
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify(session))
  } catch {
    /* quota / private mode */
  }
}

/** Per-tab legend/heatmap filter fields. */
export function snapshotTabFilters(tab) {
  if (!tab) return null
  return {
    taskFilterText: tab.taskFilterText || '',
    migratedOnlyFilter: !!tab.migratedOnlyFilter,
    taskFilterKeys: tab.taskFilterKeys?.length ? [...tab.taskFilterKeys] : null,
    heatmapFilterLabel: tab.heatmapFilterLabel ?? null,
  }
}

export function buildTabFiltersByTraceName(tabs) {
  const out = {}
  for (const tab of tabs || []) {
    if (!tab?.name) continue
    out[tab.name] = snapshotTabFilters(tab)
  }
  return out
}

export function applyTabFilters(tab, filters) {
  if (!tab || !filters) return
  tab.taskFilterText = filters.taskFilterText ?? ''
  tab.migratedOnlyFilter = !!filters.migratedOnlyFilter
  tab.taskFilterKeys = filters.taskFilterKeys ?? null
  tab.heatmapFilterLabel = filters.heatmapFilterLabel ?? null
}

export function sanitizeTabFilters(src) {
  if (!src || typeof src !== 'object') return null
  const keys = Array.isArray(src.taskFilterKeys)
    ? src.taskFilterKeys.filter(k => k != null && String(k).length).map(String)
    : null
  return {
    taskFilterText: typeof src.taskFilterText === 'string' ? src.taskFilterText : '',
    migratedOnlyFilter: !!src.migratedOnlyFilter,
    taskFilterKeys: keys?.length ? keys : null,
    heatmapFilterLabel: src.heatmapFilterLabel != null ? String(src.heatmapFilterLabel) : null,
  }
}

function sanitizeCursors(cursors) {
  if (!Array.isArray(cursors)) return null
  return cursors.map(c => {
    if (c == null) return null
    const n = Number.parseInt(c, 10)
    return Number.isFinite(n) ? n : null
  })
}

function sanitizeMarks(marks) {
  if (!Array.isArray(marks)) return []
  const out = []
  for (const m of marks) {
    if (!m || typeof m !== 'object') continue
    const id = Number.parseInt(m.id, 10)
    const ns = Number.parseInt(m.ns, 10)
    if (!Number.isFinite(id) || !Number.isFinite(ns)) continue
    out.push({
      id,
      ns,
      label: String(m.label ?? ''),
      type: m.type === 'annotation' ? 'annotation' : 'bookmark',
    })
  }
  return out
}

function sanitizeViewport(vp) {
  if (!vp || typeof vp !== 'object') return null
  const t0 = Number(vp.timeStart)
  const t1 = Number(vp.timeEnd)
  if (!Number.isFinite(t0) || !Number.isFinite(t1)) return null
  return {
    timeStart: t0,
    timeEnd: t1,
    scrollY: Number.isFinite(Number(vp.scrollY)) ? Number(vp.scrollY) : 0,
    scrollX: Number.isFinite(Number(vp.scrollX)) ? Number(vp.scrollX) : 0,
    canvasW: Math.max(1, Number(vp.canvasW) || 1),
    canvasH: Math.max(1, Number(vp.canvasH) || 1),
  }
}

function sanitizeOpenPlot(plot) {
  if (!plot || typeof plot !== 'object') return null
  const out = { ...plot }
  if (out.mk != null) out.mk = String(out.mk)
  if (out.kind != null) out.kind = String(out.kind)
  return out
}

function sanitizeSectionCollapsed(src) {
  if (!src || typeof src !== 'object') return null
  const out = {}
  for (const [k, v] of Object.entries(src)) {
    if (typeof v === 'boolean') out[k] = v
  }
  return Object.keys(out).length ? out : null
}

/** Full per-trace tab state (viewport, cursors, marks, filters, find, stats). */
export function snapshotTabState(tab) {
  if (!tab?.trace) return null
  const filters = snapshotTabFilters(tab)
  return {
    timelineViewport: sanitizeViewport(tab.timelineViewport),
    cursors: sanitizeCursors(tab.cursors),
    marks: sanitizeMarks(tab.marks),
    markNextId: tab.markNextId ?? 1,
    findQuery: tab.findQuery ?? '',
    findMode: tab.findMode ?? 'contains',
    pinnedHighlightKey: tab.pinnedHighlightKey ?? null,
    highlightSegment: tab.highlightSegment
      ? { ...tab.highlightSegment }
      : null,
    cpuLoadExpanded: tab.cpuLoadExpanded !== false,
    scopeToCursors: tab.scopeToCursors !== false,
    openPlot: sanitizeOpenPlot(tab.openPlot),
    statsSectionCollapsed: sanitizeSectionCollapsed(tab.statsSectionCollapsed),
    ...filters,
  }
}

export function buildTabStateByTraceName(tabs) {
  const out = {}
  for (const tab of tabs || []) {
    if (!tab?.name || !tab.trace) continue
    const snap = snapshotTabState(tab)
    if (snap) out[tab.name] = snap
  }
  return out
}

export function applyTabState(tab, state) {
  if (!tab || !state) return
  const vp = sanitizeViewport(state.timelineViewport)
  if (vp) Object.assign(tab.timelineViewport, vp)
  const curs = sanitizeCursors(state.cursors)
  if (curs) tab.cursors = curs
  tab.marks = sanitizeMarks(state.marks)
  if (state.markNextId != null) {
    const mid = Number.parseInt(state.markNextId, 10)
    tab.markNextId = Number.isFinite(mid) ? mid : tab.markNextId
  }
  tab.findQuery = typeof state.findQuery === 'string' ? state.findQuery : ''
  tab.findMode = state.findMode ?? 'contains'
  tab.pinnedHighlightKey = state.pinnedHighlightKey ?? null
  tab.highlightSegment = state.highlightSegment ?? null
  if (state.cpuLoadExpanded != null) tab.cpuLoadExpanded = !!state.cpuLoadExpanded
  if (state.scopeToCursors != null) tab.scopeToCursors = !!state.scopeToCursors
  if (state.openPlot !== undefined) tab.openPlot = sanitizeOpenPlot(state.openPlot)
  if (state.statsSectionCollapsed) {
    tab.statsSectionCollapsed = sanitizeSectionCollapsed(state.statsSectionCollapsed)
  }
  applyTabFilters(tab, sanitizeTabFilters(state))
}

/** Merge legacy tabFiltersByTraceName into tabStateByTraceName on load. */
export function mergeLegacyTabFilters(tabStateByTraceName, tabFiltersByTraceName) {
  const out = { ...(tabStateByTraceName || {}) }
  if (!tabFiltersByTraceName) return out
  for (const [name, filters] of Object.entries(tabFiltersByTraceName)) {
    if (!out[name]) {
      const f = sanitizeTabFilters(filters)
      if (f) out[name] = f
    }
  }
  return out
}

export function buildSessionSnapshot({ timelineOptions, layout, tabs, activeTabId }) {
  const loaded = (tabs || []).filter(t => t?.trace)
  const activeTab = loaded.find(t => t.id === activeTabId) ?? loaded[0] ?? null
  const tabStateByTraceName = buildTabStateByTraceName(loaded)
  return {
    version: 2,
    timelineOptions: {
      viewMode: timelineOptions.viewMode,
      orientation: timelineOptions.orientation,
      showGrid: timelineOptions.showGrid,
      showSti: timelineOptions.showSti,
      showCpuLoad: timelineOptions.showCpuLoad,
      darkMode: timelineOptions.darkMode,
    },
    layout: layout ? { ...layout } : null,
    openTabNames: loaded.map(t => t.name),
    activeTabName: activeTab?.name ?? null,
    tabStateByTraceName,
    tabFiltersByTraceName: buildTabFiltersByTraceName(loaded),
  }
}

/** True when saved viewport has a real zoom/pan window for this trace. */
export function isRestorableViewport(vp, trace) {
  if (!vp || !trace) return false
  const lo = trace.timeMin >= 0 ? Math.max(0, trace.timeMin) : trace.timeMin
  const hi = trace.timeMax
  if (hi <= lo) return false
  const vpSpan = vp.timeEnd - vp.timeStart
  if (vp.timeStart === 0 && vp.timeEnd === 1 && vpSpan <= 1) return false
  if (vpSpan <= 0 || vp.timeStart >= hi || vp.timeEnd <= lo) return false
  const overlapLo = Math.max(vp.timeStart, lo)
  const overlapHi = Math.min(vp.timeEnd, hi)
  const overlap = overlapHi - overlapLo
  const minSpan = Math.max(1000, (hi - lo) * 0.0001)
  return overlap >= minSpan
}

export function applySavedLayout(layout, targets) {
  if (!layout || !targets) return
  const { rightPanelWidth, cpuLoadPaneHeight, sectionHeights } = layout
  if (rightPanelWidth != null && targets.rightPanelWidth) {
    targets.rightPanelWidth.value = rightPanelWidth
  }
  if (cpuLoadPaneHeight != null && targets.cpuLoadPaneHeight) {
    targets.cpuLoadPaneHeight.value = cpuLoadPaneHeight
  }
  if (cpuLoadPaneHeight != null && targets.setCpuLoadUserSized) {
    targets.setCpuLoadUserSized(true)
  }
  if (sectionHeights && targets.sectionHeights) {
    Object.assign(targets.sectionHeights.value, sectionHeights)
  }
}
