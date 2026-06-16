/** CPU load graph helpers (parity with desktop _CpuLoadGraph). */

export const CPU_LOAD_ROW_H = 30
export const CPU_LOAD_COLLAPSED_H = 20
export const CPU_LOAD_ROW_GAP = 2
export const CPU_LOAD_MAX_VISIBLE_ROWS = 8
export const CPU_LOAD_PANE_CHROME_H = 30
export const CPU_LOAD_PANE_MIN_H = 60
export const CPU_LOAD_PANE_MAX_H = 480

export function cpuLoadRowsViewportHeight(
  visibleRows = CPU_LOAD_MAX_VISIBLE_ROWS,
  allExpanded = true,
) {
  const vis = Math.max(1, visibleRows)
  const rowH = allExpanded ? CPU_LOAD_ROW_H : CPU_LOAD_COLLAPSED_H
  return vis * rowH + Math.max(0, vis - 1) * CPU_LOAD_ROW_GAP
}

export const CPU_LOAD_PANE_DEFAULT_H =
  CPU_LOAD_PANE_CHROME_H + cpuLoadRowsViewportHeight(CPU_LOAD_MAX_VISIBLE_ROWS) + 2

export function cpuLoadRowCount(trace, viewMode, selectedTask) {
  if (!trace) return 0
  if (viewMode === 'task') return 1
  return trace.coreNames?.length ?? 0
}

/** Preferred outer pane height — up to 8 visible rows; fewer cores use actual count. */
export function cpuLoadPreferredPaneHeight(trace, viewMode, selectedTask, allExpanded = true) {
  const n = cpuLoadRowCount(trace, viewMode, selectedTask)
  if (n === 0) return CPU_LOAD_PANE_MIN_H
  const visibleRows = Math.min(n, CPU_LOAD_MAX_VISIBLE_ROWS)
  const rowsH = cpuLoadRowsViewportHeight(visibleRows, allExpanded)
  const preferred = CPU_LOAD_PANE_CHROME_H + rowsH + 2
  return Math.max(CPU_LOAD_PANE_MIN_H, Math.min(CPU_LOAD_PANE_MAX_H, preferred))
}

export function binIndicesForNsRange(trace, binW, nsLo, nsHi, numBins) {
  const tMin = trace.timeMin
  let b0 = Math.floor((nsLo - tMin) / binW)
  let b1 = Math.floor((nsHi - tMin) / binW)
  b0 = Math.max(0, Math.min(numBins - 1, b0))
  b1 = Math.max(0, Math.min(numBins - 1, b1))
  if (b1 < b0) [b0, b1] = [b1, b0]
  return { startBin: b0, endBin: b1 }
}

export function avgBinsInRange(bins, startBin, endBin) {
  if (!bins || endBin < startBin) return 0
  let sum = 0
  let count = 0
  for (let i = startBin; i <= endBin; i++) {
    sum += bins[i] || 0
    count++
  }
  return count > 0 ? sum / count : 0
}

export function avgBinsForNsRange(bins, trace, binW, nsLo, nsHi, numBins) {
  const { startBin, endBin } = binIndicesForNsRange(trace, binW, nsLo, nsHi, numBins)
  return avgBinsInRange(bins, startBin, endBin)
}

export function loadAtNs(bins, trace, binW, ns, numBins) {
  if (!bins) return 0
  const { startBin } = binIndicesForNsRange(trace, binW, ns, ns, numBins)
  return bins[startBin] || 0
}

export function getPlacedCursorRange(cursors) {
  const placed = (cursors || []).filter(c => c !== null)
  if (placed.length < 2) return null
  const sorted = [...placed].sort((a, b) => a - b)
  const lo = sorted[0]
  const hi = sorted[sorted.length - 1]
  if (hi <= lo) return null
  return { lo, hi, nCursors: placed.length }
}

export function cursorRangeShade(range, visibleStart, visibleEnd, visibleSpan, plotW) {
  if (!range) return null
  const lo = Math.max(visibleStart, range.lo)
  const hi = Math.min(visibleEnd, range.hi)
  if (hi <= lo) return null
  const x0 = ((lo - visibleStart) / visibleSpan) * plotW
  const x1 = ((hi - visibleStart) / visibleSpan) * plotW
  return { x: x0, width: Math.max(1, x1 - x0) }
}
