/**
 * Cursor-range statistics (C1–Cn window) — shared by Marks panel and status bar.
 */

import { taskDisplayName, taskMergeKey } from './colors.js'
import { formatTime } from './timeFormat.js'

export function computeCursorRangeStats(trace, cursors, decimals = 3) {
  if (!trace) return null
  const placed = (cursors || []).filter(c => c !== null)
  if (placed.length < 2) return null

  const sorted = [...placed].sort((a, b) => a - b)
  const lo = sorted[0]
  const hi = sorted[sorted.length - 1]
  const dt = hi - lo
  if (dt <= 0) return null

  const scale = trace.timeScale
  const taskAcc = new Map()
  const durations = []
  let switches = 0

  for (const seg of trace.segments) {
    if (seg.end <= lo || seg.start >= hi) continue
    const ov = Math.min(seg.end, hi) - Math.max(seg.start, lo)
    if (ov <= 0) continue
    switches++
    durations.push(seg.end - seg.start)
    const mk = taskMergeKey(seg.task)
    const repr = trace.taskRepr.get(mk) || seg.task
    const disp = taskDisplayName(repr)
    taskAcc.set(disp, (taskAcc.get(disp) || 0) + ov)
  }

  let topTask = null
  let topNs = 0
  for (const [k, v] of taskAcc) {
    if (v > topNs) {
      topNs = v
      topTask = k
    }
  }

  const result = {
    span: formatTime(dt, scale, decimals),
    switches,
    topTask,
    topPct: topTask ? (100.0 * topNs / dt).toFixed(1) : null,
  }

  if (durations.length > 0) {
    const minD = Math.min(...durations)
    const maxD = Math.max(...durations)
    const avgD = Math.round(durations.reduce((a, b) => a + b, 0) / durations.length)
    result.dMin = formatTime(minD, scale, decimals)
    result.dMax = formatTime(maxD, scale, decimals)
    result.dAvg = formatTime(avgD, scale, decimals)
  }
  return result
}

/**
 * Compact status-bar Scope line (desktop _status_range), using the canonical
 * "Scope" terminology: "Scope: Full Trace" with no cursor-defined range, or
 * "Scope: C1\u2013C3 \u00b7 span" (+ optional min/max/avg) once a range is set.
 */
export function formatStatusRangeLine(stats, cursorLabel) {
  if (!stats) return 'Scope: Full Trace'
  const label = cursorLabel ? `Scope: ${cursorLabel} \u00b7 ${stats.span}` : `Scope: ${stats.span}`
  if (stats.dMin) {
    return `${label}  min ${stats.dMin}  max ${stats.dMax}  avg ${stats.dAvg}`
  }
  return label
}
