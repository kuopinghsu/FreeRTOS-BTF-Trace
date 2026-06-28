import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  collectSegmentStarts,
  snapToBoundary,
} from '../src/utils/snapBoundary.js'

describe('snapToBoundary', () => {
  const trace = {
    segByMergeKey: new Map([
      ['T1', [
        { start: 1000, end: 2000 },
        { start: 3000, end: 4000 },
      ]],
    ]),
  }

  it('snaps to nearest segment start within window', () => {
    const ns = snapToBoundary(trace, 1020, 10, 8)
    assert.equal(ns, 1000)
  })

  it('snaps to segment end when closer', () => {
    const ns = snapToBoundary(trace, 1990, 10, 8)
    assert.equal(ns, 2000)
  })

  it('returns original ns when no boundary is near', () => {
    const ns = snapToBoundary(trace, 2500, 10, 2)
    assert.equal(ns, 2500)
  })
})

describe('collectSegmentStarts', () => {
  it('returns sorted unique starts', () => {
    const trace = {
      segByMergeKey: new Map([
        ['A', [{ start: 300, end: 400 }, { start: 100, end: 200 }]],
        ['B', [{ start: 200, end: 250 }]],
      ]),
    }
    assert.deepEqual(collectSegmentStarts(trace), [100, 200, 300])
  })
})
