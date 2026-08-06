import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  defaultStatsTableSort,
  nextSortState,
  sortHeaderClass,
  sortStatsRows,
  CORE_BREAKDOWN_SORT_ACCESSORS,
  CORE_PAIR_SORT_ACCESSORS,
  LIFECYCLE_SORT_ACCESSORS,
  AFFINITY_SORT_ACCESSORS,
  DEADLINE_SLICE_SORT_ACCESSORS,
  DEADLINE_CPU_SORT_ACCESSORS,
  SYNC_OBJECT_SORT_ACCESSORS,
} from '../src/utils/statsTableSort.js'

describe('defaultStatsTableSort / nextSortState', () => {
  it('starts unsorted', () => {
    assert.deepEqual(defaultStatsTableSort(), { col: null, dir: 1 })
  })

  it('sets ascending on first click of a column', () => {
    assert.deepEqual(nextSortState(defaultStatsTableSort(), 'task'), { col: 'task', dir: 1 })
  })

  it('flips direction on repeat click of the same column', () => {
    const asc = nextSortState(defaultStatsTableSort(), 'task')
    assert.deepEqual(nextSortState(asc, 'task'), { col: 'task', dir: -1 })
  })

  it('resets to ascending when switching columns', () => {
    const asc = nextSortState(defaultStatsTableSort(), 'task')
    const desc = nextSortState(asc, 'task')
    assert.deepEqual(nextSortState(desc, 'count'), { col: 'count', dir: 1 })
  })
})

describe('sortHeaderClass', () => {
  it('is plain sortable when the column is not the active sort', () => {
    assert.equal(sortHeaderClass({ col: 'a', dir: 1 }, 'b'), 'sortable')
  })

  it('marks ascending/descending on the active column', () => {
    assert.equal(sortHeaderClass({ col: 'a', dir: 1 }, 'a'), 'sortable sort-asc')
    assert.equal(sortHeaderClass({ col: 'a', dir: -1 }, 'a'), 'sortable sort-desc')
  })
})

describe('sortStatsRows', () => {
  it('returns rows unchanged when no column is selected', () => {
    const rows = [{ n: 2 }, { n: 1 }]
    assert.equal(sortStatsRows(rows, defaultStatsTableSort(), { n: r => r.n }), rows)
  })

  it('sorts numerically ascending/descending', () => {
    const rows = [{ n: 3 }, { n: 1 }, { n: 2 }]
    const acc = { n: r => r.n }
    assert.deepEqual(sortStatsRows(rows, { col: 'n', dir: 1 }, acc).map(r => r.n), [1, 2, 3])
    assert.deepEqual(sortStatsRows(rows, { col: 'n', dir: -1 }, acc).map(r => r.n), [3, 2, 1])
  })

  it('falls back to numeric-aware locale compare for strings', () => {
    const rows = [{ s: 'Core_10' }, { s: 'Core_2' }, { s: 'Core_1' }]
    const sorted = sortStatsRows(rows, { col: 's', dir: 1 }, { s: r => r.s })
    assert.deepEqual(sorted.map(r => r.s), ['Core_1', 'Core_2', 'Core_10'])
  })

  it('does not mutate the input array', () => {
    const rows = [{ n: 2 }, { n: 1 }]
    sortStatsRows(rows, { col: 'n', dir: 1 }, { n: r => r.n })
    assert.deepEqual(rows.map(r => r.n), [2, 1])
  })
})

describe('CORE_BREAKDOWN_SORT_ACCESSORS', () => {
  const rows = [
    { core: 'Core_0', activeNs: 850, idleNs: 100, tickNs: 0, gapNs: 50, spanNs: 1000 },
    { core: 'Core_1', activeNs: 700, idleNs: 200, tickNs: 0, gapNs: 100, spanNs: 1000 },
  ]

  it('sorts by active-percentage ratio', () => {
    const sorted = sortStatsRows(rows, { col: 'active', dir: 1 }, CORE_BREAKDOWN_SORT_ACCESSORS)
    assert.deepEqual(sorted.map(r => r.core), ['Core_1', 'Core_0'])
  })
})

describe('CORE_PAIR_SORT_ACCESSORS', () => {
  const rows = [
    { fromCore: 'Core_0', toCore: 'Core_1', count: 5, bounces: 1, bouncePct: 20, avgGapNs: 500 },
    { fromCore: 'Core_1', toCore: 'Core_0', count: 9, bounces: 0, bouncePct: 0, avgGapNs: 100 },
  ]

  it('sorts by migration count descending', () => {
    const sorted = sortStatsRows(rows, { col: 'count', dir: -1 }, CORE_PAIR_SORT_ACCESSORS)
    assert.deepEqual(sorted.map(r => r.count), [9, 5])
  })
})

describe('LIFECYCLE_SORT_ACCESSORS', () => {
  const rows = [
    { label: 'CS[6]', createNs: 100, deleteNs: null, suspendCount: 1, resumeCount: 1, aliveSpanNs: 900, eventCount: 3, runCount: 40 },
    { label: 'CS[5]', createNs: 50, deleteNs: 800, suspendCount: 0, resumeCount: 0, aliveSpanNs: 750, eventCount: 1, runCount: 60 },
  ]

  it('sorts by run count', () => {
    const sorted = sortStatsRows(rows, { col: 'runs', dir: 1 }, LIFECYCLE_SORT_ACCESSORS)
    assert.deepEqual(sorted.map(r => r.label), ['CS[6]', 'CS[5]'])
  })

  it('treats a missing delete time as unbounded for sort purposes', () => {
    const sorted = sortStatsRows(rows, { col: 'deleted', dir: 1 }, LIFECYCLE_SORT_ACCESSORS)
    assert.deepEqual(sorted.map(r => r.label), ['CS[6]', 'CS[5]'])
  })
})

describe('AFFINITY_SORT_ACCESSORS', () => {
  const rows = [
    { label: 'Runner[1]', maskHex: '0x1', observedCores: 'Core_0', violations: '\u2014' },
    { label: 'CS[6]', maskHex: '0x3', observedCores: 'Core_0, Core_1', violations: 'Core_1' },
    { label: 'AffM[5]', maskHex: '0x1 → 0x8', observedCores: 'Core_0, Core_3', violations: '\u2014' },
  ]

  it('sorts by mask display string (desktop parity, incl. multi-mask)', () => {
    const sorted = sortStatsRows(rows, { col: 'mask', dir: 1 }, AFFINITY_SORT_ACCESSORS)
    assert.deepEqual(sorted.map(r => r.label), ['Runner[1]', 'AffM[5]', 'CS[6]'])
  })
})

describe('DEADLINE_SLICE_SORT_ACCESSORS', () => {
  const rows = [
    { label: 'B', durationNs: 30, limitTu: 10, overTu: 20 },
    { label: 'A', durationNs: 15, limitTu: 5, overTu: 10 },
  ]

  it('sorts by over-by ascending', () => {
    const sorted = sortStatsRows(rows, { col: 'over', dir: 1 }, DEADLINE_SLICE_SORT_ACCESSORS)
    assert.deepEqual(sorted.map(r => r.label), ['A', 'B'])
  })

  it('caps then sorts like desktop (fixed top-N set)', () => {
    const many = [
      { label: 'long', durationNs: 100, limitTu: 1, overTu: 99 },
      { label: 'mid', durationNs: 50, limitTu: 1, overTu: 49 },
      { label: 'short', durationNs: 10, limitTu: 1, overTu: 9 },
    ]
    // Simulate duration-desc list capped to 2 before user sort by task.
    const capped = many.slice(0, 2)
    const sorted = sortStatsRows(capped, { col: 'task', dir: 1 }, DEADLINE_SLICE_SORT_ACCESSORS)
    assert.deepEqual(sorted.map(r => r.label), ['long', 'mid'])
  })
})

describe('DEADLINE_CPU_SORT_ACCESSORS', () => {
  const rows = [
    { label: 'B', pctRaw: 40, budgetRaw: 20 },
    { label: 'A', pctRaw: 25, budgetRaw: 20 },
  ]

  it('sorts by cpu pct descending', () => {
    const sorted = sortStatsRows(rows, { col: 'cpu', dir: -1 }, DEADLINE_CPU_SORT_ACCESSORS)
    assert.deepEqual(sorted.map(r => r.label), ['B', 'A'])
  })
})

describe('SYNC_OBJECT_SORT_ACCESSORS (also used by the Queue table)', () => {
  const rows = [
    { label: 'queue 0x8001a090', kind: 'queue', holdCount: 72, issueCount: 0, bounceCount: 0, avgHoldNs: 160000, statusLabel: 'OK' },
    { label: 'queue 0x80012710', kind: 'queue', holdCount: 0, issueCount: 0, bounceCount: 0, avgHoldNs: 0, statusLabel: 'OK' },
  ]

  it('sorts by hold count', () => {
    const sorted = sortStatsRows(rows, { col: 'holds', dir: 1 }, SYNC_OBJECT_SORT_ACCESSORS)
    assert.deepEqual(sorted.map(r => r.holdCount), [0, 72])
  })
})
