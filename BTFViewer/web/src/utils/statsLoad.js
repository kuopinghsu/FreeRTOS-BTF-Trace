/** Large-trace statistics load tuning. Defaults live in ``src/config.js``. */

import {
  STATS_LOAD_DEFER_CORES,
  STATS_LOAD_DEFER_SYNC_ISSUES,
  STATS_LOAD_DEFER_TASKS,
} from '../config.js'

export {
  STATS_HEAVY_SECTIONS,
  STATS_LOAD_DEFER_CORES,
  STATS_LOAD_DEFER_SYNC_ISSUES,
  STATS_LOAD_DEFER_TASKS,
} from '../config.js'

export function traceNeedsDeferredStatsLoad(trace) {
  if (!trace) return false
  return (
    (trace.tasks?.length ?? 0) > STATS_LOAD_DEFER_TASKS
    || (trace.coreNames?.length ?? 0) > STATS_LOAD_DEFER_CORES
    || (trace.syncIssues?.length ?? 0) > STATS_LOAD_DEFER_SYNC_ISSUES
  )
}
