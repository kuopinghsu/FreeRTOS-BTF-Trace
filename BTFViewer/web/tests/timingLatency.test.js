import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { activationLatencyRows, readyGapRows } from '../src/utils/timingLatency.js'

// Minimal fake trace: one task on Core_0 with two IDLE-filled gaps.
function fakeTrace() {
  const seg = (a, b, core = 'Core_0', task = 'W[1]') => ({ start: a, end: b, core, task })
  return {
    timeScale: 'us',
    timeMin: 0,
    timeMax: 400,
    coreNames: ['Core_0'],
    segByMergeKey: new Map([['w', [seg(0, 10), seg(100, 110), seg(200, 210)]]]),
    coreSegs: new Map([['Core_0', [
      seg(0, 10), seg(10, 100, 'Core_0', 'IDLE'), seg(100, 110),
      seg(110, 200, 'Core_0', 'IDLE'), seg(200, 210),
    ]]]),
    taskRepr: new Map([['w', 'W[1]'], ['idle', 'IDLE']]),
    stiEventsByTarget: new Map(),
  }
}

describe('activationLatencyRows', () => {
  it('is all-zero for activations that sit exactly on the grid', () => {
    const events = []
    for (let k = 1; k <= 12; k++) {
      events.push({ kind: 'inter', mk: 'w', task: 'W[1]', start: k * 100, duration: 100 })
    }
    const rows = activationLatencyRows({ taskRepr: new Map([['w', 'W[1]']]) }, events)
    assert.equal(rows.length, 1)
    const r = rows[0]
    assert.equal(r.count, 12)
    for (const v of [r.minNs, r.avgNs, r.maxNs, r.jitterNs, r.sigmaNs, r.p50Ns, r.p95Ns, r.p99Ns]) {
      assert.equal(v, 0)
    }
  })

  it('flags drift from the grid', () => {
    const events = []
    for (let k = 1; k <= 12; k++) {
      // every other activation is 20 late
      events.push({ kind: 'inter', mk: 'w', task: 'W[1]', start: k * 100 + (k % 2 ? 0 : 20), duration: 100 })
    }
    const rows = activationLatencyRows({ taskRepr: new Map([['w', 'W[1]']]) }, events)
    assert.equal(rows.length, 1)
    assert.ok(rows[0].maxNs > 0)
    assert.ok(rows[0].maxNs <= 20)
  })
})

describe('readyGapRows', () => {
  it('drops IDLE-filled (period-wait) gaps', () => {
    const rows = readyGapRows(fakeTrace())
    assert.deepEqual(rows, [])
  })

  it('keeps preempted gaps and ranks by longest', () => {
    const seg = (a, b, core = 'Core_0', task = 'W[1]') => ({ start: a, end: b, core, task })
    const tr = {
      timeScale: 'us',
      timeMin: 0,
      timeMax: 400,
      coreNames: ['Core_0'],
      segByMergeKey: new Map([['w', [seg(0, 10), seg(60, 70)]]]),
      // another real task ran on Core_0 during w's gap -> preempted
      coreSegs: new Map([['Core_0', [seg(0, 10), seg(20, 55, 'Core_0', 'Other[2]'), seg(60, 70)]]]),
      taskRepr: new Map([['w', 'W[1]'], ['o', 'Other[2]']]),
      stiEventsByTarget: new Map(),
    }
    const rows = readyGapRows(tr)
    assert.equal(rows.length, 1)
    assert.equal(rows[0].count, 1)
    assert.equal(rows[0].longestNs, 50)          // 60 - 10
    assert.equal(Math.round(rows[0].preemptPct), 100)
  })
})
