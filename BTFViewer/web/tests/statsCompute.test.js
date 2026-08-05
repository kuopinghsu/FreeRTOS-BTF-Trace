import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { computeStatsTables } from '../src/parser/statsCompute.js'

function makeStore(starts, ends) {
  return {
    starts,
    ends,
    getSeg(index) {
      return { start: starts[index], end: ends[index] }
    },
  }
}

describe('computeStatsTables variability metrics', () => {
  it('calculates jitter and population standard deviation', () => {
    const store = makeStore([0, 20, 60], [10, 40, 90])
    const result = computeStatsTables(store, {
      tasks: ['Task:1'],
      taskRepr: new Map([['Task:1', 'Task[1]']]),
      segIndicesByMk: new Map([['Task:1', [0, 1, 2]]]),
      lo: null,
      hi: null,
      totalNs: 100,
    })

    assert.equal(result.exec.length, 1)
    assert.equal(result.exec[0].jitter, 20) // durations: 10, 20, 30
    assert.equal(result.exec[0].stddev, 8) // population σ ≈ 8.165

    assert.equal(result.block.length, 1)
    assert.equal(result.block[0].jitter, 10) // gaps: 10, 20
    assert.equal(result.block[0].stddev, 5)

    assert.equal(result.inter.length, 1)
    assert.equal(result.inter[0].jitter, 20) // starts: deltas 20, 40
    assert.equal(result.inter[0].stddev, 10)
  })

  it('returns zero jitter and stddev for a single sample', () => {
    const store = makeStore([0], [42])
    const result = computeStatsTables(store, {
      tasks: ['Task:1'],
      taskRepr: new Map([['Task:1', 'Task[1]']]),
      segIndicesByMk: new Map([['Task:1', [0]]]),
      lo: null,
      hi: null,
      totalNs: 42,
    })

    assert.equal(result.exec.length, 1)
    assert.equal(result.exec[0].jitter, 0)
    assert.equal(result.exec[0].stddev, 0)
    assert.equal(result.block.length, 0)
    assert.equal(result.inter.length, 0)
  })
})
