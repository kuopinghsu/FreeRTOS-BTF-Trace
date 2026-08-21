import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  buildCompareCsv,
  buildCompareHtml,
  buildAllCompareTables,
  buildTopTasksCompareRows,
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
    const tables = {
      summary, coreUtil, execution, interArrival, sync: [],
      trends: [{ name: 'A.btf', tasks: 2, migrations: 1, loadBalance: 90, tickHealth: 'good', spanNs: 1000 }],
      shared_patterns: [{ task: 'Worker[1]', kind: 'block', count_a: 2, count_b: 1, reason: 'block for Worker[1]' }],
    }

    const csv = buildCompareCsv('A.btf', 'B.btf', false, tables)
    assert.match(csv, /Core Util/)
    assert.match(csv, /CPU A \(%\),CPU B \(%\),Δ \(pp\)/)
    assert.match(csv, /Util A \(%\),Util B \(%\),Δ \(pp\)/)
    assert.match(csv, /Execution Time/)
    assert.match(csv, /Inter-Arrival Time/)
    assert.match(csv, /Load Balance Score/)
    assert.match(csv, /Sync Objects/)
    assert.match(csv, /Response P99/)
    assert.match(csv, /Mutex Blocking/)
    assert.match(csv, /Shared Patterns/)
    assert.match(csv, /Trends/)

    const html = buildCompareHtml('A.btf', 'B.btf', false, tables)
    assert.match(html, /BTFViewer/)
    assert.match(html, /class="report-head"/)
    assert.match(html, /class="brand-icon"/)
    assert.match(html, /fill="#1C3A6E"/)
    assert.match(html, /class="report-toc"/)
    assert.match(html, /Table of Contents/)
    assert.match(html, /<details/)
    assert.match(html, /<h2>Overview<\/h2>/)
    assert.match(html, /Notable Changes/)
    assert.match(html, /Baseline A/)
    assert.match(html, /Candidate B/)
    assert.match(html, /Δ = Baseline A/)
    assert.match(html, /CPU A \(%\)/)
    assert.match(html, /Util A \(%\)/)
    assert.match(html, /Δ \(pp\)/)
    assert.match(html, /<h2>Core Utilisation<\/h2>/)
    assert.match(html, /<h2>Execution Time<\/h2>/)
    assert.match(html, /<h2>Inter-Arrival Time<\/h2>/)
    assert.match(html, /<h2>Response P99<\/h2>/)
    assert.match(html, /<h2>Mutex Blocking<\/h2>/)
    assert.match(html, /<h2>Shared Patterns<\/h2>/)
    assert.match(html, /<h2>Trends<\/h2>/)
    assert.match(html, /<details class="report-card" id="sec-overview" open>/)
    assert.match(html, /compare-chart/)
    assert.match(html, /Core utilisation/)
    assert.match(html, /Expand all/)
    assert.match(html, /Collapse all/)
    assert.match(html, /data-toc="expand"/)
  })

  it('exports summary change bars and migration heatmap in HTML', () => {
    const summary = [
      { label: 'Migrations (total)', a: '10', b: '25', delta: '−15' },
      { label: 'Blocking total', a: '1 ms', b: '3 ms', delta: '−2 ms' },
      { label: 'Tasks', a: '5', b: '5', delta: '0' },
    ]
    const migrations = [
      {
        name: 'QP[1]', migrationsA: 2, migrationsB: 12, delta: -10,
        rateA: '1/s', rateB: '2/s', rateDelta: '−1/s',
        dwellA: '1 ms', dwellB: '2 ms', dwellDelta: '−1 ms',
        pingA: 0, pingB: 1, coresA: 2, coresB: 2, primaryA: '0 90%', primaryB: '1 80%',
      },
      {
        name: 'CS[2]', migrationsA: 8, migrationsB: 1, delta: 7,
        rateA: '2/s', rateB: '0.2/s', rateDelta: '+1.8/s',
        dwellA: '2 ms', dwellB: '1 ms', dwellDelta: '+1 ms',
        pingA: 2, pingB: 0, coresA: 3, coresB: 1, primaryA: '1 70%', primaryB: '0 90%',
      },
    ]
    const html = buildCompareHtml('A.btf', 'B.btf', false, { summary, migrations })
    assert.match(html, /Summary changes/)
    assert.match(html, /Migration Δ heatmap/)
    assert.match(html, /QP\[1\]/)
  })

  it('formats CPU/util deltas with pp and unicode minus', () => {
    const top = buildTopTasksCompareRows(traceA, traceB)
    assert.ok(top.some(r => /\bpp\b/.test(String(r.delta))))
    const util = buildCoreUtilCompareRows(traceA, traceB)
    assert.ok(util.some(r => /\bpp\b/.test(String(r.delta))))
    const neg = [...top, ...util].find(r => String(r.delta).includes('−'))
    if (neg) assert.doesNotMatch(String(neg.delta), /^-/)
  })

  it('unlimited export includes every task', () => {
    const segsA = []
    const segsB = []
    for (let i = 0; i < 16; i++) {
      segsA.push(makeSeg(`W[${i}]`, 'Core_0', 0, 50 + i))
      segsB.push(makeSeg(`W[${i}]`, 'Core_0', 0, 40 + i))
    }
    const manyA = makeTrace({ timeMax: 200, segments: segsA })
    const manyB = makeTrace({ timeMax: 200, segments: segsB })
    const capped = buildAllCompareTables(manyA, manyB)
    const full = buildAllCompareTables(manyA, manyB, null, null, false, null, 0)
    assert.equal(capped.top.length, 10)
    assert.equal(full.top.length, 16)
    assert.equal(capped.execution.length, 15)
    assert.equal(full.execution.length, 16)
    const html = buildCompareHtml('A', 'B', false, full)
    assert.match(html, /W\[15\]/)
    assert.match(html, /W\[10\]/)
  })

  it('deadline misses use Settings taskDeadlines', () => {
    const longA = makeTrace({
      timeMax: 400,
      timeScale: 'ns',
      segments: [
        makeSeg('Worker[1]', 'Core_0', 0, 100),
        makeSeg('Worker[1]', 'Core_0', 200, 400),
      ],
    })
    const shortB = makeTrace({
      timeMax: 120,
      timeScale: 'ns',
      segments: [
        makeSeg('Worker[1]', 'Core_0', 0, 50),
        makeSeg('Worker[1]', 'Core_0', 80, 120),
      ],
    })
    const none = buildSummaryCompareRows(longA, shortB)
    const dlNone = none.find(r => r.label === 'Deadline misses')
    assert.equal(dlNone.a, 0)
    assert.equal(dlNone.b, 0)

    const rows = buildSummaryCompareRows(
      longA, shortB, null, null, false, { 'Worker[1]': 150 })
    const dl = rows.find(r => r.label === 'Deadline misses')
    assert.ok(dl.a > 0)
    assert.equal(dl.b, 0)
  })

  it('top tasks lookup uses the full dataset', () => {
    const traceA = makeTrace({
      timeMax: 1000,
      timeScale: 'ns',
      segments: [
        makeSeg('W[0]', 'Core_0', 0, 1000),
        makeSeg('W[1]', 'Core_0', 0, 900),
        makeSeg('W[2]', 'Core_0', 0, 800),
        makeSeg('W[3]', 'Core_0', 0, 50),
      ],
    })
    const traceB = makeTrace({
      timeMax: 1000,
      timeScale: 'ns',
      segments: [
        makeSeg('W[0]', 'Core_0', 0, 40),
        makeSeg('W[1]', 'Core_0', 0, 30),
        makeSeg('W[2]', 'Core_0', 0, 20),
        makeSeg('W[3]', 'Core_0', 0, 900),
      ],
    })
    const rows = buildTopTasksCompareRows(traceA, traceB, null, null, false, 3)
    const byName = Object.fromEntries(rows.map(r => [r.name, r]))
    assert.ok(byName['W[2]'])
    assert.ok(byName['W[3]'])
    assert.notEqual(byName['W[2]'].cpuB, '—')
    assert.notEqual(byName['W[3]'].cpuA, '—')
    const summary = buildSummaryCompareRows(traceA, traceB)
    const p99 = summary.find(r => r.label === 'Response P99 (worst task)')
    assert.match(String(p99.a), /\(/)
    assert.match(String(p99.b), /\(/)
  })
})
