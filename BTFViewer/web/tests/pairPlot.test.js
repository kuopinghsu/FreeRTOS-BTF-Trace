import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  PAIR_BOUNCE_POINT_COLOR,
  pairBouncePrefer,
  pairGapPlotPoints,
  pairPlotKey,
  pairRatePlotPoints,
  parsePairPlotKey,
} from '../src/utils/migrationAnalysis.js'

function makeTrace(migrations, bounceNs = []) {
  return {
    migrations,
    syncObjects: new Map(),
    hasSyncObjectInstrumentation: bounceNs.length > 0,
    _lockBounceNs: new Set(bounceNs),
  }
}

describe('pair plot key', () => {
  it('round-trips from/to cores', () => {
    const key = pairPlotKey('Core_5', 'Core_7')
    assert.deepEqual(parsePairPlotKey(key), { fromCore: 'Core_5', toCore: 'Core_7' })
  })
})

describe('pairGapPlotPoints', () => {
  it('filters directed pair and colors bounce samples', () => {
    const migs = [
      { ns: 100, fromCore: 'Core_0', toCore: 'Core_1', gapNs: 10 },
      { ns: 200, fromCore: 'Core_0', toCore: 'Core_1', gapNs: 30 },
      { ns: 300, fromCore: 'Core_1', toCore: 'Core_0', gapNs: 50 },
      { ns: 400, fromCore: 'Core_0', toCore: 'Core_1', gapNs: 0 },
    ]
    const pts = pairGapPlotPoints(makeTrace(migs, [200]), 'Core_0', 'Core_1')
    assert.equal(pts.length, 2)
    assert.equal(pts[0].xNs, 100)
    assert.equal(pts[0].fillColor, undefined)
    assert.equal(pts[1].xNs, 200)
    assert.equal(pts[1].fillColor, PAIR_BOUNCE_POINT_COLOR)
  })
})

describe('pairRatePlotPoints', () => {
  it('measures time between consecutive migrations on the same corridor', () => {
    const migs = [
      { ns: 100, fromCore: 'Core_0', toCore: 'Core_1', gapNs: 1 },
      { ns: 150, fromCore: 'Core_1', toCore: 'Core_0', gapNs: 1 },
      { ns: 250, fromCore: 'Core_0', toCore: 'Core_1', gapNs: 1 },
      { ns: 400, fromCore: 'Core_0', toCore: 'Core_1', gapNs: 1 },
    ]
    const pts = pairRatePlotPoints(makeTrace(migs, [400]), 'Core_0', 'Core_1')
    assert.deepEqual(pts.map(p => [p.xNs, p.yValue]), [[250, 150], [400, 150]])
    assert.equal(pts[1].fillColor, PAIR_BOUNCE_POINT_COLOR)
  })
})

describe('pairBouncePrefer', () => {
  it('is true when bounce share is elevated', () => {
    const migs = Array.from({ length: 8 }, (_, i) => ({
      ns: 100 + i * 10,
      fromCore: 'Core_0',
      toCore: 'Core_1',
      gapNs: 5,
    }))
    const bounce = migs.slice(0, 3).map(m => m.ns)
    assert.equal(pairBouncePrefer(makeTrace(migs, bounce), 'Core_0', 'Core_1'), true)
    assert.equal(pairBouncePrefer(makeTrace(migs, []), 'Core_0', 'Core_1'), false)
  })
})
