/** Large-trace statistics load tuning (parity with desktop config.py). */

export const STATS_LOAD_DEFER_TASKS = 256
export const STATS_LOAD_DEFER_CORES = 32
export const STATS_LOAD_DEFER_SYNC_ISSUES = 400

export const STATS_HEAVY_SECTIONS = [
  'migrations', 'exec', 'block', 'inter', 'health',
  'preemption', 'priority', 'sync', 'intervals', 'tags',
]

export function traceNeedsDeferredStatsLoad(trace) {
  if (!trace) return false
  return (
    (trace.tasks?.length ?? 0) > STATS_LOAD_DEFER_TASKS
    || (trace.coreNames?.length ?? 0) > STATS_LOAD_DEFER_CORES
    || (trace.syncIssues?.length ?? 0) > STATS_LOAD_DEFER_SYNC_ISSUES
  )
}
