/**
 * Cursor comparison helpers (parity with desktop _task_at_time / _rebuild_cursor_table).
 */

import { bisectRight } from './bisect.js'
import { taskDisplayName, taskReprGet } from './colors.js'
import { formatTime } from './timeFormat.js'

const NS_PER_SCALE = { ns: 1e9, us: 1e6, ms: 1e3, s: 1 }

/** Placed cursors sorted by timestamp (desktop _CursorBarWidget order). */
export function cursorSortedPlaced(cursors) {
  return (cursors || [])
    .map((t, slotIndex) => ({ t, slotIndex }))
    .filter(x => x.t != null)
    .sort((a, b) => a.t - b.t)
}

export function cursorDeltaFrequency(deltaTu, timeScale = 'ns') {
  if (deltaTu <= 0) return '∞ Hz'
  const div = NS_PER_SCALE[timeScale] || 1e9
  return `${(div / deltaTu).toFixed(1)} Hz`
}

/** Delta segments between consecutive sorted cursors (desktop status-bar format). */
export function cursorDeltaSegments(sortedPlaced, timeScale = 'ns', decimals = 3) {
  const out = []
  for (let i = 1; i < sortedPlaced.length; i++) {
    const delta = sortedPlaced[i].t - sortedPlaced[i - 1].t
    const freq = cursorDeltaFrequency(delta, timeScale)
    out.push({
      index: i,
      delta,
      freq,
      text: `Δ${i}=${formatTime(delta, timeScale, decimals)} (${freq})`,
    })
  }
  return out
}

/** Status-bar cursor pills (desktop _CursorBarWidget). */
export function cursorBarModel(cursors, timeScale = 'ns', decimals = 3) {
  const sorted = cursorSortedPlaced(cursors)
  return {
    pills: sorted.map(({ t, slotIndex }) => ({
      slotIndex,
      ns: t,
      label: `C${slotIndex + 1}: ${formatTime(t, timeScale, decimals)}`,
      tooltip: `C${slotIndex + 1}: jump to cursor`,
    })),
    deltas: cursorDeltaSegments(sorted, timeScale, decimals),
  }
}

/**
 * Tasks running at timestamp ns (comma-separated display names).
 * @param {string[]|Set<string>|null} [coreFilter] when non-empty, only count
 *   segments whose `.core` is in this set (shared with the Legend Core Filter).
 */
export function tasksAtTime(trace, ns, coreFilter = null) {
  if (!trace) return '—'
  const coreSet = coreFilter && (coreFilter.size || coreFilter.length)
    ? (coreFilter instanceof Set ? coreFilter : new Set(coreFilter))
    : null
  const names = []
  const seen = new Set()
  for (const [mk, segs] of trace.segByMergeKey || []) {
    if (!segs?.length) continue
    const starts = segs.map(s => s.start)
    const pos = bisectRight(starts, ns) - 1
    if (pos >= 0 && segs[pos].end >= ns) {
      if (coreSet && !coreSet.has(segs[pos].core)) continue
      const raw = taskReprGet(trace, mk) || mk
      const disp = taskDisplayName(raw)
      if (!seen.has(disp)) {
        seen.add(disp)
        names.push(disp)
      }
    }
  }
  return names.length ? names.join(', ') : '—'
}

/**
 * Rows for cursor comparison table.
 * @param {string[]|Set<string>|null} [coreFilter] passed through to tasksAtTime.
 */
export function cursorComparisonRows(trace, cursors, timeScale = 'ns', coreFilter = null) {
  const placed = cursors
    .map((t, i) => ({ t, i }))
    .filter(x => x.t != null)
    .sort((a, b) => a.t - b.t)
  if (!placed.length || !trace) return []
  const c1 = placed[0].t
  return placed.map(({ t, i }, row) => {
    const delta = row === 0
      ? '—'
      : `${t >= c1 ? '+' : '-'}${formatTime(Math.abs(t - c1), timeScale)}`
    return {
      idx: i,
      label: `C${row + 1}`,
      time: formatTime(t, timeScale),
      task: tasksAtTime(trace, t, coreFilter),
      delta,
      ns: t,
    }
  })
}
