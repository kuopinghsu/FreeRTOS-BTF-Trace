/**
 * Cursor comparison helpers (parity with desktop _task_at_time / _rebuild_cursor_table).
 */

import { bisectRight } from './bisect.js'
import { taskDisplayName, taskReprGet } from './colors.js'
import { formatTime } from './timeFormat.js'

/** Tasks running at timestamp ns (comma-separated display names). */
export function tasksAtTime(trace, ns) {
  if (!trace) return '—'
  const names = []
  const seen = new Set()
  for (const [mk, segs] of trace.segByMergeKey || []) {
    if (!segs?.length) continue
    const starts = segs.map(s => s.start)
    const pos = bisectRight(starts, ns) - 1
    if (pos >= 0 && segs[pos].end >= ns) {
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

/** Rows for cursor comparison table. */
export function cursorComparisonRows(trace, cursors, timeScale = 'ns') {
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
      task: tasksAtTime(trace, t),
      delta,
      ns: t,
    }
  })
}
