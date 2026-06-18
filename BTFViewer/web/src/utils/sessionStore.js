/** Persist web viewer layout and view options in localStorage (not open tabs). */

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

export function buildSessionSnapshot({ timelineOptions, layout }) {
  return {
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
