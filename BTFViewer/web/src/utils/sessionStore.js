/** Persist web viewer session (tab names, cursors, marks, viewport, layout) in localStorage. */

const SESSION_KEY = 'btf-viewer-session-v1'

export function loadSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
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

/** @returns {object|null} saved per-tab state keyed by tab file name */
export function getSavedTabState(tabName) {
  const session = loadSession()
  if (!session?.tabStates || !tabName) return null
  return session.tabStates[tabName] ?? null
}

export function buildSessionSnapshot({
  tabs,
  activeTabId,
  timelineOptions,
  layout,
}) {
  const tabStates = {}
  for (const tab of tabs) {
    if (!tab.name) continue
    tabStates[tab.name] = {
      cursors: tab.cursors ? [...tab.cursors] : [null, null, null, null],
      marks: tab.marks ? JSON.parse(JSON.stringify(tab.marks)) : [],
      markNextId: tab.markNextId ?? 1,
      pinnedHighlightKey: tab.pinnedHighlightKey ?? null,
      highlightSegment: tab.highlightSegment ?? null,
      timelineViewport: tab.timelineViewport
        ? { ...tab.timelineViewport }
        : null,
      findQuery: tab.findQuery ?? '',
      findMode: tab.findMode ?? 'contains',
      findHitIdx: tab.findHitIdx ?? -1,
      openPlot: tab.openPlot ? { ...tab.openPlot } : null,
    }
  }
  return {
    activeTabName: tabs.find(t => t.id === activeTabId)?.name ?? null,
    tabOrder: tabs.map(t => t.name),
    tabStates,
    timelineOptions: {
      viewMode: timelineOptions.viewMode,
      orientation: timelineOptions.orientation,
      showGrid: timelineOptions.showGrid,
      showSti: timelineOptions.showSti,
      showCpuLoad: timelineOptions.showCpuLoad,
      darkMode: timelineOptions.darkMode,
      migratedOnlyFilter: timelineOptions.migratedOnlyFilter,
    },
    layout: layout ? { ...layout } : null,
  }
}

export function applySavedTabState(tab, saved) {
  if (!tab || !saved) return
  if (saved.cursors?.length) tab.cursors = [...saved.cursors]
  if (saved.marks) tab.marks = JSON.parse(JSON.stringify(saved.marks))
  if (saved.markNextId != null) tab.markNextId = saved.markNextId
  tab.pinnedHighlightKey = saved.pinnedHighlightKey ?? null
  tab.highlightSegment = saved.highlightSegment ?? null
  if (saved.timelineViewport) {
    Object.assign(tab.timelineViewport, saved.timelineViewport)
  }
  tab.findQuery = saved.findQuery ?? ''
  tab.findMode = saved.findMode ?? 'contains'
  tab.findHitIdx = saved.findHitIdx ?? -1
  tab.openPlot = saved.openPlot ? { ...saved.openPlot } : null
}

/** True when saved viewport has a real zoom/pan window for this trace. */
export function isRestorableViewport(vp, trace) {
  if (!vp || !trace) return false
  const lo = trace.timeMin >= 0 ? Math.max(0, trace.timeMin) : trace.timeMin
  const hi = trace.timeMax
  if (hi <= lo) return false
  const vpSpan = vp.timeEnd - vp.timeStart
  // Sentinel from _emptyViewport() / resetTabForLoad before session restore
  if (vp.timeStart === 0 && vp.timeEnd === 1 && vpSpan <= 1) return false
  if (vpSpan <= 0 || vp.timeStart >= hi || vp.timeEnd <= lo) return false
  const overlapLo = Math.max(vp.timeStart, lo)
  const overlapHi = Math.min(vp.timeEnd, hi)
  const overlap = overlapHi - overlapLo
  // Reject saved zoom windows that overlap the trace by less than ~0.01% (min 1 µs/ms unit).
  const minSpan = Math.max(1000, (hi - lo) * 0.0001)
  return overlap >= minSpan
}

export function applySavedLayout(layout, targets) {
  if (!layout || !targets) return
  const { rightPanelWidth, cpuLoadPaneHeight, sectionHeights, rightPanelTab } = layout
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
  if (rightPanelTab && targets.rightPanelTab) {
    targets.rightPanelTab.value = rightPanelTab
  }
}
