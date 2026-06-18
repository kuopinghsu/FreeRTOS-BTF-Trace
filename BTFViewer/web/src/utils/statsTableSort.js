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
  p95: r => r.p95Ns,
}

export const BLOCK_SORT_ACCESSORS = {
  task: r => r.name.toLowerCase(),
  gaps: r => r.gaps,
  min: r => r.minNs,
  avg: r => r.avgNs,
  max: r => r.maxNs,
  p95: r => r.p95Ns,
}

export const INTER_SORT_ACCESSORS = {
  task: r => r.name.toLowerCase(),
  runs: r => r.runs,
  min: r => r.minNs,
  avg: r => r.avgNs,
  max: r => r.maxNs,
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
