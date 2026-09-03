import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { classifyOffCpuGaps, OFFCPU_GAP_KINDS } from '../src/utils/statsAnalysis.js'
import { switchReasonRows, schedLoadOverTimeRows } from '../src/utils/schedulingLoad.js'

// Minimal fake trace: one task on Core_0 with two IDLE-filled gaps.
function fakeTrace() {
  const seg = (a, b, core = 'Core_0', task = 'W[1]') => ({ start: a, end: b, core, task })
  return {
    timeScale: 'us',
    timeMin: 0,
    timeMax: 100,
    coreNames: ['Core_0'],
    segByMergeKey: new Map([['w', [seg(0, 10), seg(40, 50), seg(80, 90)]]]),
    coreSegs: new Map([['Core_0', [
      seg(0, 10), seg(10, 40, 'Core_0', 'IDLE'), seg(40, 50),
      seg(50, 80, 'Core_0', 'IDLE'), seg(80, 90),
    ]]]),
    taskRepr: new Map([['w', 'W[1]'], ['idle', 'IDLE']]),
    stiEventsByTarget: new Map(),
  }
}

describe('classifyOffCpuGaps', () => {
  it('labels IDLE-filled gaps as period_wait', () => {
    const byMk = classifyOffCpuGaps(fakeTrace())
    assert.deepEqual(byMk.get('w'), [[30, 'period_wait'], [30, 'period_wait']])
  })
  it('only emits known kinds', () => {
    const byMk = classifyOffCpuGaps(fakeTrace())
    for (const gaps of byMk.values()) {
      for (const [, k] of gaps) assert.ok(OFFCPU_GAP_KINDS.includes(k))
    }
  })
})

describe('switchReasonRows', () => {
  it('counts by reason, sorted by preempted desc', () => {
    const rows = switchReasonRows(fakeTrace())
    assert.equal(rows.length, 1)
    const r = rows[0]
    assert.equal(r.name, 'W[1]')
    assert.equal(r.periodWait, 2)
    assert.equal(r.preempted + r.blocked + r.suspended + r.periodWait + r.unknown, r.total)
  })
})

describe('schedLoadOverTimeRows', () => {
  it('bins context switches and load balance', () => {
    const tr = fakeTrace()
    const events = [
      { kind: 'exec', core: 'Core_0', start: 0, stop: 10 },
      { kind: 'exec', core: 'Core_0', start: 40, stop: 50 },
      { kind: 'exec', core: 'Core_0', start: 80, stop: 90 },
    ]
    const rows = schedLoadOverTimeRows(tr, events)
    assert.ok(rows.length >= 4 && rows.length <= 32)
    assert.ok(rows.every(r => r.ctx >= 0 && r.sigmaPct >= 0))
    // every per-core slice start inside the grid span (0..90): 0,10,40,50,80
    assert.equal(rows.reduce((s, r) => s + r.ctx, 0), 5)
    assert.ok(rows.every(r => r.lbScore === null)) // single core
  })
})
