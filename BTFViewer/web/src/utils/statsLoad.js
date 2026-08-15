/** Large-trace statistics load tuning. Defaults live in ``src/config.js``. */

import {
  STATS_LOAD_DEFER_CORES,
  STATS_LOAD_DEFER_SEGMENTS,
  STATS_LOAD_DEFER_SYNC_ISSUES,
  STATS_LOAD_DEFER_TASKS,
  STATS_TABLE_DISPLAY_ROW_CAP,
} from '../config.js'

export {
  STATS_HEAVY_SECTIONS,
  STATS_LOAD_DEFER_CORES,
  STATS_LOAD_DEFER_SEGMENTS,
  STATS_LOAD_DEFER_SYNC_ISSUES,
  STATS_LOAD_DEFER_TASKS,
  STATS_TABLE_DISPLAY_ROW_CAP,
} from '../config.js'

/** Cap on-screen stats tables; Export still uses the full list (desktop parity). */
export function capStatsTableRows(rows, cap = STATS_TABLE_DISPLAY_ROW_CAP) {
  const list = Array.isArray(rows) ? rows : []
  const n = list.length
  if (n <= cap) return { rows: list, note: null, total: n }
  return {
    rows: list.slice(0, cap),
    note: `Showing first ${cap.toLocaleString()} of ${n.toLocaleString()} rows — use Export for the full list.`,
    total: n,
  }
}

export function traceNeedsDeferredStatsLoad(trace) {
  if (!trace) return false
  const segs = trace.segments?.length
    ?? trace.segStore?.count
    ?? 0
  return (
    (trace.tasks?.length ?? 0) > STATS_LOAD_DEFER_TASKS
    || (trace.coreNames?.length ?? 0) > STATS_LOAD_DEFER_CORES
    || (trace.syncIssues?.length ?? 0) > STATS_LOAD_DEFER_SYNC_ISSUES
    || segs > STATS_LOAD_DEFER_SEGMENTS
  )
}
