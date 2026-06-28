import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  computeFindHits,
  stepFindHitIndex,
} from '../src/utils/findAnalysis.js'

function makeTrace({ segs = [], migrations = [], taskRepr = new Map() } = {}) {
  return {
    segByMergeKey: new Map(segs),
    migrations,
    taskRepr,
  }
}

describe('computeFindHits', () => {
  it('returns empty for blank query', () => {
    const trace = makeTrace()
    assert.deepEqual(computeFindHits(trace, '  ', 'contains'), { hits: [], error: null })
  })

  it('finds exact task merge key', () => {
    const trace = makeTrace({
      segs: [['T1', [{ start: 100, end: 200 }]]],
      taskRepr: new Map([['T1', 'T1']]),
    })
    const { hits, error } = computeFindHits(trace, 'T1', 'exact')
    assert.equal(error, null)
    assert.deepEqual(hits, [100])
  })

  it('contains mode is case-insensitive', () => {
    const trace = makeTrace({
      segs: [['k', [{ start: 50, end: 60 }, { start: 70, end: 80 }]]],
      taskRepr: new Map([['k', 'Worker']]),
    })
    const { hits } = computeFindHits(trace, 'work', 'contains')
    assert.deepEqual(hits, [50, 70])
  })

  it('regex mode reports invalid patterns', () => {
    const trace = makeTrace()
    const { hits, error } = computeFindHits(trace, '[', 'regex')
    assert.deepEqual(hits, [])
    assert.equal(error, 'Regex error')
  })

  it('migrations mode filters by destination core', () => {
    const trace = makeTrace({
      migrations: [{
        mergeKey: 'm1',
        fromCore: 'Core_0',
        toCore: 'Core_2',
        ns: 900,
      }],
      taskRepr: new Map([['m1', 'm1']]),
    })
    const { hits } = computeFindHits(trace, 'core_2', 'migrations')
    assert.deepEqual(hits, [900])
  })

  it('searches annotation labels', () => {
    const trace = makeTrace()
    const { hits } = computeFindHits(trace, 'watch', 'contains', [
      { ns: 500, label: 'watchdog timeout' },
    ])
    assert.deepEqual(hits, [500])
  })
})

describe('stepFindHitIndex', () => {
  const hits = [100, 200, 300]

  it('wraps forward from last hit', () => {
    assert.equal(stepFindHitIndex(hits, 2, 250, true), 0)
  })

  it('steps backward from first hit', () => {
    assert.equal(stepFindHitIndex(hits, 0, 250, false), 2)
  })

  it('picks nearest hit from centre when index unset', () => {
    assert.equal(stepFindHitIndex(hits, -1, 210, true), 2)
    assert.equal(stepFindHitIndex(hits, -1, 210, false), 1)
  })
})
