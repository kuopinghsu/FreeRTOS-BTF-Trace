import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, it } from 'node:test'

import { parseBtf } from '../src/parser/btfParser.js'
import { decompressBtfBytes } from '../src/utils/btfLoad.js'
import {
  buildCorridorInspectorModel,
  migrationHeatmapMatrix,
  migrationRows,
  migrationsInRange,
  prepareFullTraceStats,
} from '../src/utils/migrationAnalysis.js'
import { coreUtilPctRows } from '../src/utils/traceCompare.js'
import { schedulingStats } from '../src/utils/statsAnalysis.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const TRACE = join(__dirname, '../../../tracedata/example-2cores.btf.gz')

function linearMigs(trace, lo, hi) {
  return (trace.migrations || []).filter(m =>
    (lo == null || m.ns >= lo) && (hi == null || m.ns <= hi))
}

describe('migrationsInRange', () => {
  it('bisect matches linear filter', () => {
    const migrations = [
      { ns: 10, mergeKey: 'a', fromCore: 'Core_0', toCore: 'Core_1' },
      { ns: 20, mergeKey: 'a', fromCore: 'Core_1', toCore: 'Core_0' },
      { ns: 20, mergeKey: 'b', fromCore: 'Core_0', toCore: 'Core_1' },
      { ns: 50, mergeKey: 'b', fromCore: 'Core_1', toCore: 'Core_0' },
      { ns: 90, mergeKey: 'a', fromCore: 'Core_0', toCore: 'Core_1' },
    ]
    const trace = { migrations, migrationTimes: migrations.map(m => m.ns) }
    for (const [lo, hi] of [[null, null], [20, 50], [15, 80], [0, 10], [90, 90], [100, 200]]) {
      assert.deepEqual(migrationsInRange(trace, lo, hi), linearMigs(trace, lo, hi), `lo=${lo} hi=${hi}`)
    }
  })
})

describe('load-time stats snapshots', () => {
  it('parseBtf fills indexes and snapshots', async () => {
    assert.ok(existsSync(TRACE), `missing trace fixture: ${TRACE}`)
    const text = decompressBtfBytes(new Uint8Array(readFileSync(TRACE)), 'example-2cores.btf.gz')
    const trace = await parseBtf(text)

    assert.equal(trace.migrationTimes.length, trace.migrations.length)
    assert.deepEqual(trace.migrationTimes, trace.migrations.map(m => m.ns))
    assert.ok(trace.taskCpuNs?.length)
    assert.equal(typeof trace.schedCtxSwitches, 'number')
    assert.ok(Array.isArray(trace.schedCoreGaps))
    assert.ok(Array.isArray(trace.migrationRowsFull))
    assert.ok(trace.coreUtilPct)
    assert.ok(trace.migratedMks instanceof Set)

    const cachedUtil = coreUtilPctRows(trace)
    const savedUtil = trace.coreUtilPct
    trace.coreUtilPct = null
    const scannedUtil = coreUtilPctRows(trace)
    trace.coreUtilPct = savedUtil
    assert.equal(cachedUtil.length, scannedUtil.length)
    for (let i = 0; i < cachedUtil.length; i++) {
      assert.equal(cachedUtil[i].core, scannedUtil[i].core)
      assert.ok(Math.abs(cachedUtil[i].pct - scannedUtil[i].pct) < 1e-6)
    }

    const cachedRows = migrationRows(trace)
    const savedRows = trace.migrationRowsFull
    trace.migrationRowsFull = null
    const scannedRows = migrationRows(trace)
    trace.migrationRowsFull = savedRows
    assert.deepEqual(cachedRows, scannedRows)

    const cachedSched = schedulingStats(trace)
    const savedCtx = trace.schedCtxSwitches
    const savedGaps = trace.schedCoreGaps
    trace.schedCtxSwitches = null
    trace.schedCoreGaps = null
    const scannedSched = schedulingStats(trace)
    trace.schedCtxSwitches = savedCtx
    trace.schedCoreGaps = savedGaps
    assert.equal(cachedSched.contextSwitches, scannedSched.contextSwitches)
    assert.deepEqual(cachedSched.coreGaps, scannedSched.coreGaps)

    const model = buildCorridorInspectorModel(trace, null, null, { topPct: 100 })
    const { cores, grid } = migrationHeatmapMatrix(trace)
    assert.deepEqual(model.matrix.cores, cores)
    assert.deepEqual(model.matrix.grid, grid)

    const span = trace.timeMax - trace.timeMin
    if (span > 0 && trace.migrations.length) {
      const lo = trace.timeMin + Math.floor(span / 4)
      const hi = trace.timeMax - Math.floor(span / 4)
      const bisectModel = buildCorridorInspectorModel(trace, lo, hi, { topPct: 100 })
      const savedTimes = trace.migrationTimes
      trace.migrationTimes = []
      const linearModel = buildCorridorInspectorModel(trace, lo, hi, { topPct: 100 })
      trace.migrationTimes = savedTimes
      assert.deepEqual(
        bisectModel.corridors.map(c => [c.fromCore, c.toCore, c.count]),
        linearModel.corridors.map(c => [c.fromCore, c.toCore, c.count]),
      )
      assert.deepEqual(bisectModel.matrix.grid, linearModel.matrix.grid)
    }

    prepareFullTraceStats(trace)
    assert.ok(trace.migrationTimes.length === trace.migrations.length)
  })
})
