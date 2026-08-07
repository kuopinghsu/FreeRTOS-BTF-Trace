/**
 * Click-to-sort helpers for statistics panel tables (desktop parity).
 */

/** @typedef {{ col: string|null, dir: 1|-1 }} StatsTableSortState */

/** @returns {StatsTableSortState} */
export function defaultStatsTableSort() {
  return { col: null, dir: 1 }
}

/** @param {StatsTableSortState} state @param {string} col */
export function nextSortState(state, col) {
  if (state.col === col) {
    return { col, dir: /** @type {1|-1} */ (-state.dir) }
  }
  return { col, dir: 1 }
}

/**
 * @template T
 * @param {T[]} rows
 * @param {StatsTableSortState} sortState
 * @param {Record<string, (row: T) => string|number>} accessors
 * @returns {T[]}
 */
export function sortStatsRows(rows, sortState, accessors) {
  if (!rows?.length || sortState.col == null) return rows
  const acc = accessors[sortState.col]
  if (!acc) return rows
  const dir = sortState.dir
  return [...rows].sort((a, b) => {
    const av = acc(a)
    const bv = acc(b)
    let cmp = 0
    if (typeof av === 'number' && typeof bv === 'number') {
      cmp = av - bv
    } else {
      cmp = String(av).localeCompare(String(bv), undefined, {
        sensitivity: 'base',
        numeric: true,
      })
    }
    return dir * cmp
  })
}

/** @param {StatsTableSortState} sortState @param {string} col */
export function sortHeaderClass(sortState, col) {
  if (sortState.col !== col) return 'sortable'
  return sortState.dir > 0 ? 'sortable sort-asc' : 'sortable sort-desc'
}

export const MIGRATION_SORT_ACCESSORS = {
  task: r => r.name.toLowerCase(),
  migr: r => r.migrations,
  rate: r => r.ratePerS,
  dwell: r => r.avgDwellTu,
  cores: r => r.coreCount,
  primary: r => r.primaryPct,
  ping: r => r.pingPong,
  sti: r => r.stiNear,
  gapAfter: r => r.gapAfterNs,
  gapOther: r => r.gapOtherNs,
}

export const EXEC_SORT_ACCESSORS = {
  task: r => r.name.toLowerCase(),
  runs: r => r.runs,
  cpu: r => r.cpuPct,
  min: r => r.minNs,
  avg: r => r.avgNs,
  max: r => r.maxNs,
  jitter: r => r.jitterNs,
  stddev: r => r.stddevNs,
  p95: r => r.p95Ns,
}

export const BLOCK_SORT_ACCESSORS = {
  task: r => r.name.toLowerCase(),
  gaps: r => r.gaps,
  min: r => r.minNs,
  avg: r => r.avgNs,
  max: r => r.maxNs,
  jitter: r => r.jitterNs,
  stddev: r => r.stddevNs,
  p95: r => r.p95Ns,
}

export const INTER_SORT_ACCESSORS = {
  task: r => r.name.toLowerCase(),
  runs: r => r.runs,
  min: r => r.minNs,
  avg: r => r.avgNs,
  max: r => r.maxNs,
  jitter: r => r.jitterNs,
  stddev: r => r.stddevNs,
  p95: r => r.p95Ns,
}

export const HEALTH_GAP_SORT_ACCESSORS = {
  start: g => g.start,
  end: g => g.end,
  gap: g => g.duration,
  missed: g => g.missedTicks,
}

export const PREEMPTION_SORT_ACCESSORS = {
  victim: r => r.victim.toLowerCase(),
  preemptor: r => r.preemptor.toLowerCase(),
  count: r => r.count,
  total: r => r.totalNs,
  avg: r => r.avgNs,
  max: r => r.maxNs,
}

export const INTERVAL_SORT_ACCESSORS = {
  id: r => {
    const n = parseInt(r.id, 10)
    return Number.isFinite(n) ? n : r.id
  },
  count: r => r.count,
  min: r => r.minNs,
  avg: r => r.avgNs,
  max: r => r.maxNs,
  p95: r => r.p95Ns,
}

export const TAG_SORT_ACCESSORS = {
  tag: r => {
    const m = /^tag([0-7])?_event$/i.exec(r.channel || '')
    if (!m) return r.label.toLowerCase()
    const digit = m[1]
    return digit != null ? parseInt(digit, 10) : -1
  },
  count: r => r.count,
  min: r => r.minVal,
  avg: r => r.avgVal,
  max: r => r.maxVal,
  p95: r => r.p95Val,
}

export const PRIORITY_SORT_ACCESSORS = {
  task: r => r.label.toLowerCase(),
  base: r => r.basePri,
  peak: r => r.peakPri,
  boosts: r => r.episodeCount,
  total: r => r.totalBoostNs,
  pattern: r => r.pattern,
}

export const SYNC_OBJECT_SORT_ACCESSORS = {
  object: r => r.label.toLowerCase(),
  kind: r => r.kind,
  holds: r => r.holdCount,
  issues: r => r.issueCount,
  bounces: r => r.bounceCount,
  avg: r => r.avgHoldNs,
  status: r => r.statusLabel,
}

export const SYNC_ISSUE_SORT_ACCESSORS = {
  time: i => i.timeNs,
  object: i => (i.objKey || '').toLowerCase(),
  issue: i => (i.kind || '').toLowerCase(),
  detail: i => (i.detail || '').toLowerCase(),
  task: i => (i.taskLabel || '').toLowerCase(),
  core: i => (i.core || '').toLowerCase(),
}

export const CORE_BREAKDOWN_SORT_ACCESSORS = {
  core: r => r.core,
  active: r => r.activeNs / r.spanNs,
  idle: r => r.idleNs / r.spanNs,
  tick: r => r.tickNs / r.spanNs,
  gap: r => r.gapNs / r.spanNs,
}

export const CONCURRENCY_SORT_ACCESSORS = {
  activeCores: r => r.activeCores,
  duration: r => r.durationNs,
  pct: r => r.pctOfSpan,
}

export const SWITCH_OVERHEAD_SORT_ACCESSORS = {
  core: r => r.core,
  switches: r => r.switches,
  min: r => r.minNs,
  avg: r => r.avgNs,
  max: r => r.maxNs,
  total: r => r.totalNs,
  pct: r => r.pctOfCore,
}

export const DISPATCH_SORT_ACCESSORS = {
  task: r => r.label.toLowerCase(),
  activations: r => r.activations,
  min: r => r.minNs,
  avg: r => r.avgNs,
  max: r => r.maxNs,
  jitter: r => r.jitterNs,
  stddev: r => r.stddevNs,
  p95: r => r.p95Ns,
}

export const CORE_PAIR_SORT_ACCESSORS = {
  from: r => r.fromCore,
  to: r => r.toCore,
  count: r => r.count,
  bounces: r => r.bounces,
  bouncePct: r => r.bouncePct,
  avgGap: r => r.avgGapNs,
}

export const LIFECYCLE_SORT_ACCESSORS = {
  task: r => r.label.toLowerCase(),
  created: r => r.createNs ?? -Infinity,
  deleted: r => r.deleteNs ?? -Infinity,
  suspRes: r => r.suspendCount + r.resumeCount,
  alive: r => r.aliveSpanNs,
  events: r => r.eventCount,
  runs: r => r.runCount,
}

export const AFFINITY_SORT_ACCESSORS = {
  task: r => r.label.toLowerCase(),
  // Display-string order (matches desktop _StatsSortItem), including
  // multi-mask histories like "0x1 → 0x8" that parseInt would truncate.
  mask: r => (r.maskHex || '').toLowerCase(),
  observed: r => r.observedCores.toLowerCase(),
  violations: r => (r.violations === '—' ? '' : r.violations.toLowerCase()),
}

export const DEADLINE_SLICE_SORT_ACCESSORS = {
  task: r => r.label.toLowerCase(),
  duration: r => r.durationNs,
  limit: r => r.limitTu ?? 0,
  over: r => r.overTu ?? (r.durationNs - (r.limitTu ?? 0)),
}

export const DEADLINE_CPU_SORT_ACCESSORS = {
  task: r => r.label.toLowerCase(),
  cpu: r => r.pctRaw,
  budget: r => r.budgetRaw ?? 0,
}
