import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  STATS_HEAVY_SECTIONS,
  STATS_LOAD_DEFER_CORES,
  STATS_LOAD_DEFER_SEGMENTS,
  STATS_LOAD_DEFER_SYNC_ISSUES,
  STATS_LOAD_DEFER_TASKS,
  STATS_TABLE_DISPLAY_ROW_CAP,
  capStatsTableRows,
  traceNeedsDeferredStatsLoad,
} from '../src/utils/statsLoad.js'

describe('capStatsTableRows', () => {
  it('passes through short lists', () => {
    const rows = [1, 2, 3]
    const out = capStatsTableRows(rows, 10)
    assert.equal(out.note, null)
    assert.equal(out.total, 3)
    assert.deepEqual(out.rows, rows)
  })

  it('caps oversized tables and points at Export', () => {
    const rows = Array.from({ length: STATS_TABLE_DISPLAY_ROW_CAP + 5 }, (_, i) => i)
    const out = capStatsTableRows(rows)
    assert.equal(out.rows.length, STATS_TABLE_DISPLAY_ROW_CAP)
    assert.equal(out.total, rows.length)
    assert.match(out.note, /Export/)
    assert.match(out.note, /Showing first/)
    assert.equal(out.rows[0], 0)
    assert.equal(out.rows.at(-1), STATS_TABLE_DISPLAY_ROW_CAP - 1)
  })
})

describe('traceNeedsDeferredStatsLoad', () => {
  it('uses the shared large-trace thresholds', () => {
    assert.equal(STATS_LOAD_DEFER_TASKS, 256)
    assert.equal(STATS_LOAD_DEFER_CORES, 32)
    assert.equal(STATS_LOAD_DEFER_SYNC_ISSUES, 400)
    assert.equal(STATS_LOAD_DEFER_SEGMENTS, 8000)
    assert.ok(STATS_HEAVY_SECTIONS.includes('exec'))
    assert.ok(STATS_HEAVY_SECTIONS.includes('mutex_block'))
    assert.equal(
      traceNeedsDeferredStatsLoad({
        tasks: ['t'],
        coreNames: ['Core_0'],
        syncIssues: [],
        segments: Array.from({ length: STATS_LOAD_DEFER_SEGMENTS + 1 }),
      }),
      true,
    )
    assert.equal(
      traceNeedsDeferredStatsLoad({
        tasks: ['t'],
        coreNames: ['Core_0'],
        syncIssues: [],
        segments: Array.from({ length: 16 }),
      }),
      false,
    )
  })
})
