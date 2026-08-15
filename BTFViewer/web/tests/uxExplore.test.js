import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  analyzeTaskPeriods,
  bestFindingScope,
  collectWorstEvents,
  compareSummaryStrip,
  detectTimelineAnomalies,
  findEventAtPercentile,
  healthInputsFromEvents,
  pairMutexWaits,
  parseSignedDelta,
  percentileIndex,
  taskCoreMatrix,
  taskHealthScores,
  topCompareRegressions,
  waiterOwnerMatrix,
} from '../src/utils/uxExplore.js'

function ev(kind, task, start, duration) {
  return {
    kind,
    task,
    mk: task,
    start,
    stop: start + duration,
    duration,
    jump_ns: kind === 'exec' ? start : start + duration,
    section: { exec: 'exec', block: 'block', inter: 'inter' }[kind] || 'exec',
    reason: '',
  }
}

describe('uxExplore', () => {
  it('percentile index matches the stats-table formula', () => {
    assert.equal(percentileIndex(10, 0.95), 9)
    assert.equal(percentileIndex(20, 0.95), 18)
    assert.equal(percentileIndex(1, 0.99), 0)
  })

  it('finds the event at p95', () => {
    const evs = [10, 20, 30, 40, 100].map((d, i) => ev('exec', 'T[1]', i * 10, d))
    assert.equal(findEventAtPercentile(evs, 0.95).duration, 100)
  })

  it('ranks worst events by duration', () => {
    const worst = collectWorstEvents([
      ev('exec', 'A[1]', 0, 50),
      ev('block', 'A[1]', 50, 200),
      ev('inter', 'B[2]', 0, 80),
      ev('exec', 'B[2]', 10, 12),
    ], 2)
    assert.deepEqual(worst.map(e => e.duration), [200, 80])
    assert.equal(worst[0].kind, 'block')
  })

  it('flags a long execution tail', () => {
    const evs = Array.from({ length: 8 }, (_, i) => ev('exec', 'A[1]', i * 20, 10))
    evs.push(ev('exec', 'A[1]', 200, 500))
    const found = detectTimelineAnomalies(evs, 8)
    assert.ok(found.some(e => e.duration === 500))
  })

  it('proposes a scope from finding evidence', () => {
    const scope = bestFindingScope({
      title: 'A[1] WCET',
      text: 'spike at jump:1200',
      task: 'A[1]',
      evidence: [{ label: 'wcet', time: 1200 }],
    }, [ev('exec', 'A[1]', 1000, 400)], 0, 10_000)
    assert.ok(scope)
    assert.ok(scope.lo <= 1200)
    assert.ok(scope.hi >= 1200)
    assert.equal(scope.section, 'exec')
  })

  it('parses compare deltas and ranks regressions', () => {
    assert.equal(parseSignedDelta('+12.3 µs').signed, 12300)
    assert.equal(parseSignedDelta('−2').signed, -2)
    const strip = compareSummaryStrip({
      summary: [
        { label: 'Span', a: '1 ms', b: '900 µs', delta: '+100 µs' },
        { label: 'Context switches', a: 10, b: 8, delta: '+2' },
      ],
      execution: [
        { name: 'CS[22]', deltaMax: '+60 µs' },
      ],
    }, 4)
    assert.ok(strip.headline.some(h => h.label === 'Span'))
    const regs = topCompareRegressions([
      { label: 'CS[22] exec max', delta: '+60 µs', signed: 60000, kind: 'time' },
      { label: 'Context switches', delta: '+2', signed: 2, kind: 'count' },
    ], 4)
    assert.equal(regs[0].kind, 'time')
  })

  it('flags missed and extra period gaps', () => {
    const evs = Array.from({ length: 6 }, (_, i) => ev('inter', 'P[1]', i * 100, 100))
    evs.push(ev('inter', 'P[1]', 600, 400))
    evs.push(ev('inter', 'P[1]', 1000, 20))
    const rows = analyzeTaskPeriods(evs, 3)
    assert.equal(rows.length, 1)
    assert.equal(rows[0].expected_ns, 100)
    assert.ok(rows[0].missed >= 1)
    assert.ok(rows[0].extra >= 1)
    assert.equal(rows[0].section, 'period')
  })

  it('builds a per-task per-core percent matrix', () => {
    const evs = [
      { ...ev('exec', 'A[1]', 0, 80), core: 'Core_0' },
      { ...ev('exec', 'A[1]', 80, 20), core: 'Core_1' },
    ]
    const matrix = taskCoreMatrix(evs, ['Core_0', 'Core_1'], 100)
    assert.equal(matrix.rows.length, 1)
    assert.equal(matrix.rows[0].cells.Core_0.pct_span, 80)
    assert.equal(matrix.rows[0].cells.Core_1.pct_task, 20)
  })

  it('pairs mutex handoff as waiter x owner', () => {
    const waits = pairMutexWaits([
      { object: 'mutex:0x1', holder: 'L[1]', holder_mk: 'L[1]', start: 100, stop: 500, duration: 400 },
      { object: 'mutex:0x1', holder: 'H[2]', holder_mk: 'H[2]', start: 500, stop: 600, duration: 100 },
    ], 1000)
    assert.equal(waits.length, 1)
    assert.equal(waits[0].waiter_mk, 'H[2]')
    assert.equal(waits[0].owner_mk, 'L[1]')
    const matrix = waiterOwnerMatrix(waits)
    assert.equal(matrix.cells['H[2]|L[1]'].ns, 400)
  })

  it('scores task health as a labelled heuristic', () => {
    const evs = Array.from({ length: 8 }, (_, i) => ev('exec', 'Good[1]', i * 20, 10))
    for (let i = 0; i < 7; i++) evs.push(ev('exec', 'Bad[2]', i * 20, 10))
    evs.push(ev('exec', 'Bad[2]', 200, 200))
    evs.push(ev('block', 'Bad[2]', 50, 80))
    for (let i = 0; i < 4; i++) evs.push(ev('inter', 'Bad[2]', i * 100, 100))
    evs.push(ev('inter', 'Bad[2]', 400, 800))
    const rows = taskHealthScores(healthInputsFromEvents(evs, 1000, ['Bad[2]']))
    assert.ok(rows.length >= 2)
    assert.ok(rows[0].score < rows[rows.length - 1].score)
    const worst = rows.find(r => r.mk === 'Bad[2]')
    assert.equal(worst.bands.deadline, 'fail')
    assert.match(worst.disclaimer, /not an AI probability/)
  })
})
