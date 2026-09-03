import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { idleAnalysisRows, syncLevelRows } from '../src/utils/idleSyncLevel.js'

describe('idleAnalysisRows', () => {
  it('per-core totals + longest all-cores-idle window', () => {
    const seg = (a, b, core, task) => ({ start: a, end: b, core, task })
    const trace = {
      timeMin: 0,
      timeMax: 100,
      coreNames: ['C0', 'C1'],
      coreSegs: new Map([
        ['C0', [seg(0, 30, 'C0', 'W[1]'), seg(30, 70, 'C0', 'IDLE'), seg(70, 100, 'C0', 'W[1]')]],
        ['C1', [seg(0, 20, 'C1', 'W[2]'), seg(20, 80, 'C1', 'IDLE'), seg(80, 100, 'C1', 'W[2]')]],
      ]),
    }
    const { rows, allIdleSpanNs, allIdleStartNs } = idleAnalysisRows(trace)
    assert.equal(allIdleSpanNs, 40)   // both idle over [30, 70]
    assert.equal(allIdleStartNs, 30)
    const c1 = rows.find(r => r.core === 'C1')
    assert.equal(c1.totalNs, 60)
    assert.equal(c1.longestNs, 60)
    assert.equal(c1.fragments, 1)
    // most-idle core first
    assert.equal(rows[0].core, 'C1')
  })

  it('empty when no idle segments', () => {
    const seg = (a, b, core, task) => ({ start: a, end: b, core, task })
    const trace = {
      timeMin: 0, timeMax: 50, coreNames: ['C0'],
      coreSegs: new Map([['C0', [seg(0, 50, 'C0', 'W[1]')]]]),
    }
    const { rows, allIdleSpanNs } = idleAnalysisRows(trace)
    assert.deepEqual(rows, [])
    assert.equal(allIdleSpanNs, 0)
  })
})

describe('syncLevelRows', () => {
  it('tracks peak / end level / starved', () => {
    const ev = (t, note) => ({ time: t, note, core: 'C0', target: 'sem' })
    const trace = {
      timeMax: 100,
      stiEventsByTarget: new Map([['sem', [
        ev(10, 'give 0x1'), ev(20, 'give 0x1'),
        ev(30, 'take 0x1'), ev(40, 'take 0x1'),
        ev(50, 'take 0x1'), // starved
      ]]]),
    }
    const rows = syncLevelRows(trace)
    assert.equal(rows.length, 1)
    assert.equal(rows[0].kind, 'sem')
    assert.equal(rows[0].maxLevel, 2)
    assert.equal(rows[0].endLevel, 0)
    assert.equal(rows[0].starved, 1)
  })

  it('empty without queue/sem events', () => {
    assert.deepEqual(syncLevelRows({ timeMax: 10, stiEventsByTarget: new Map() }), [])
  })
})
