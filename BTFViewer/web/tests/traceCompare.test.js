import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  buildCompareCsv,
  buildCompareHtml,
  buildCoreUtilCompareRows,
  buildExecutionCompareRows,
  buildInterArrivalCompareRows,
  buildSummaryCompareRows,
  coreUtilPctRows,
  execSliceSamples,
  interArrivalSamples,
  summarizeTimeSamples,
  traceSummarySnapshot,
} from '../src/utils/traceCompare.js'
import { buildMigrationIndex } from '../src/utils/migrationAnalysis.js'

function makeSeg(task, core, start, end) {
  return { task, core, start, end }
}

/** Minimal fake trace matching Trace Compare inputs. */
function makeTrace({
  timeMin = 0,
  timeMax = 10000,
  timeScale = 'us',
  segments = [],
  tickStiTimes = [],
  stiEvents = [],
  hasSyncObjectInstrumentation = false,
} = {}) {
  const tasks = []
  const taskRepr = new Map()
  const segByMergeKey = new Map()
  const coreSegs = new Map()
  const coreNames = []

  for (const s of segments) {
    const mk = s.task
    if (!segByMergeKey.has(mk)) {
      segByMergeKey.set(mk, [])
      tasks.push(mk)
      taskRepr.set(mk, mk)
    }
    segByMergeKey.get(mk).push(s)
    if (!coreSegs.has(s.core)) {
      coreSegs.set(s.core, [])
      coreNames.push(s.core)
    }
    coreSegs.get(s.core).push(s)
  }
  coreNames.sort((a, b) => {
    const na = a.startsWith('Core_') ? parseInt(a.slice(5), 10) : NaN
    const nb = b.startsWith('Core_') ? parseInt(b.slice(5), 10) : NaN
    if (!Number.isNaN(na) && !Number.isNaN(nb)) return na - nb
    return a.localeCompare(b)
  })
  for (const segs of coreSegs.values()) segs.sort((a, b) => a.start - b.start)
  for (const segs of segByMergeKey.values()) segs.sort((a, b) => a.start - b.start)

  const { migrations, migrationsByMk } = buildMigrationIndex(segByMergeKey)

  return {
    timeMin,
    timeMax,
    timeScale,
    tasks,
    taskRepr,
    segments,
    segByMergeKey,
    coreNames,
    coreSegs,
    stiEvents,
    tickStiTimes,
    migrations,
    migrationsByMk,
    hasSyncObjectInstrumentation,
  }
}

describe('traceCompare helpers', () => {
  it('summarizeTimeSamples returns min/avg/max/p95', () => {
    const s = summarizeTimeSamples([100, 200, 300, 400], 'us')
    assert.ok(s)
    assert.equal(s.count, 4)
    assert.equal(s.minNs, 100)
    assert.equal(s.maxNs, 400)
    assert.equal(s.avgNs, 250)
    assert.ok(typeof s.avg === 'string')
    assert.ok(typeof s.p95 === 'string')
  })

  it('execSliceSamples keeps fully-in-range slices only', () => {
    const segs = [
      makeSeg('Worker[1]', 'Core_0', 0, 100),
      makeSeg('Worker[1]', 'Core_0', 200, 350),
      makeSeg('Worker[1]', 'Core_0', 400, 600),
    ]
    assert.equal(execSliceSamples(segs).length, 3)
    assert.equal(execSliceSamples(segs, 50, 500).length, 1)
    assert.deepEqual(execSliceSamples(segs, 50, 500), [150])
  })

  it('interArrivalSamples uses gaps between starts', () => {
    const segs = [
      makeSeg('Worker[1]', 'Core_0', 0, 50),
      makeSeg('Worker[1]', 'Core_0', 100, 140),
      makeSeg('Worker[1]', 'Core_0', 250, 280),
    ]
    assert.deepEqual(interArrivalSamples(segs), [100, 150])
    assert.deepEqual(interArrivalSamples(segs, 90, 260), [100, 150])
    assert.deepEqual(interArrivalSamples(segs, 120, 260), [150])
  })
})

describe('traceSummarySnapshot enrichment', () => {
  const traceA = makeTrace({
    timeMax: 1000,
    segments: [
      makeSeg('Worker[1]', 'Core_0', 0, 400),
      makeSeg('Worker[1]', 'Core_1', 0, 100),
      makeSeg('idle', 'Core_0', 400, 1000),
      makeSeg('idle', 'Core_1', 100, 1000),
    ],
    tickStiTimes: [0, 100, 200, 300, 400, 500, 600, 700, 800, 900],
  })
  const traceB = makeTrace({
    timeMax: 1000,
    segments: [
      makeSeg('Worker[1]', 'Core_0', 0, 200),
      makeSeg('Worker[1]', 'Core_1', 0, 200),
      makeSeg('idle', 'Core_0', 200, 1000),
      makeSeg('idle', 'Core_1', 200, 1000),
    ],
    tickStiTimes: [0, 100, 200, 500, 600, 700, 800, 900],
  })

  it('includes load balance and tick fields', () => {
    const snap = traceSummarySnapshot(traceA)
    assert.ok(snap.loadBalanceScore != null)
    assert.ok(snap.loadBalanceSigma != null)
    assert.equal(snap.tickMode, 'TICK')
    assert.equal(snap.tickCount, 10)
    assert.ok(typeof snap.tickHealth === 'string')
    assert.ok(snap.missedTicks >= 0)

    const coreRows = coreUtilPctRows(traceA)
    assert.equal(coreRows.length, 2)
    assert.ok(coreRows[0].pct > coreRows[1].pct)
  })

  it('summary compare rows include new metrics', () => {
    const rows = buildSummaryCompareRows(traceA, traceB)
    const labels = rows.map(r => r.label)
    assert.ok(labels.includes('Load Balance Score'))
    assert.ok(labels.includes('Load Balance σ'))
    assert.ok(labels.includes('Tick health'))
    assert.ok(labels.includes('Tick mode'))
    assert.ok(labels.includes('Tick count'))
    assert.ok(labels.includes('Missed ticks (est.)'))

    const tickCount = rows.find(r => r.label === 'Tick count')
    assert.equal(tickCount.a, 10)
    assert.equal(tickCount.b, 8)
  })
})

describe('new compare builders', () => {
  const traceA = makeTrace({
    timeMax: 1000,
    segments: [
      makeSeg('Worker[1]', 'Core_0', 0, 100),
      makeSeg('Worker[1]', 'Core_0', 200, 320),
      makeSeg('Worker[1]', 'Core_1', 400, 500),
      makeSeg('Helper[2]', 'Core_1', 0, 50),
      makeSeg('Helper[2]', 'Core_1', 150, 200),
    ],
  })
  const traceB = makeTrace({
    timeMax: 1000,
    segments: [
      makeSeg('Worker[1]', 'Core_0', 0, 80),
      makeSeg('Worker[1]', 'Core_0', 200, 280),
      makeSeg('Helper[2]', 'Core_1', 0, 40),
      makeSeg('Helper[2]', 'Core_1', 100, 140),
    ],
  })

  it('builds core util rows', () => {
    const rows = buildCoreUtilCompareRows(traceA, traceB)
    assert.ok(rows.length >= 1)
    assert.ok(rows.every(r => 'core' in r && 'utilA' in r && 'utilB' in r && 'delta' in r))
  })

  it('builds execution compare rows with Δ max', () => {
    const rows = buildExecutionCompareRows(traceA, traceB)
    assert.ok(rows.length >= 1)
    const worker = rows.find(r => r.name.includes('Worker'))
    assert.ok(worker)
    assert.ok(worker.runsA >= 1)
    assert.ok(worker.maxA)
    assert.ok(worker.deltaMax != null)
  })

  it('builds inter-arrival compare rows', () => {
    const rows = buildInterArrivalCompareRows(traceA, traceB)
    assert.ok(rows.length >= 1)
    const worker = rows.find(r => r.name.includes('Worker'))
    assert.ok(worker)
    assert.ok(worker.runsA >= 2)
    assert.ok(worker.avgA)
    assert.ok(worker.delta != null)
  })

  it('CSV/HTML exports include new sections', () => {
    const summary = buildSummaryCompareRows(traceA, traceB)
    const coreUtil = buildCoreUtilCompareRows(traceA, traceB)
    const execution = buildExecutionCompareRows(traceA, traceB)
    const interArrival = buildInterArrivalCompareRows(traceA, traceB)
    const tables = { summary, coreUtil, execution, interArrival, sync: [] }

    const csv = buildCompareCsv('A.btf', 'B.btf', false, tables)
    assert.match(csv, /Core Util/)
    assert.match(csv, /Execution Time/)
    assert.match(csv, /Inter-Arrival Time/)
    assert.match(csv, /Load Balance Score/)
    assert.match(csv, /Sync Objects/)

    const html = buildCompareHtml('A.btf', 'B.btf', false, tables)
    assert.match(html, /BTFViewer/)
    assert.match(html, /class="report-head"/)
    assert.match(html, /class="brand-icon"/)
    assert.match(html, /fill="#1C3A6E"/)
    assert.match(html, /<h2>Core Util<\/h2>/)
    assert.match(html, /<h2>Execution Time<\/h2>/)
    assert.match(html, /<h2>Inter-Arrival Time<\/h2>/)
  })
})
