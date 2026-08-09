import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  buildChordLayout,
  buildTaperedRibbonPath,
  chordHitRing,
  chordRingGeometry,
  distToQuadraticBezier,
  CHORD_ARC_INNER,
  CHORD_ARC_OUTER,
  traceHasCoreBounceHolds,
} from '../src/utils/migrationAnalysis.js'

describe('buildChordLayout', () => {
  it('gives every core an arc spanning a positive, non-overlapping angle range', () => {
    const cores = ['Core_0', 'Core_1', 'Core_2']
    const grid = [
      [0, 5, 0],
      [0, 0, 0],
      [2, 0, 0],
    ]
    const { arcs } = buildChordLayout(cores, grid)
    assert.equal(arcs.length, 3)
    for (const arc of arcs) {
      assert.ok(arc.endAngle > arc.startAngle)
    }
    // Arcs are laid out sequentially around the circle without overlap.
    for (let i = 1; i < arcs.length; i++) {
      assert.ok(arcs[i].startAngle >= arcs[i - 1].endAngle)
    }
  })

  it('sizes arcs proportionally to each core\'s total in+out migration volume', () => {
    const cores = ['Core_0', 'Core_1', 'Core_2']
    // Core_0 <-> Core_1 dominates; Core_2 has no traffic at all.
    const grid = [
      [0, 100, 0],
      [100, 0, 0],
      [0, 0, 0],
    ]
    const { arcs } = buildChordLayout(cores, grid)
    const spanOf = core => {
      const a = arcs.find(x => x.core === core)
      return a.endAngle - a.startAngle
    }
    assert.ok(spanOf('Core_0') > spanOf('Core_2'))
    assert.ok(spanOf('Core_1') > spanOf('Core_2'))
    // The zero-flow core should still get a visible sliver, not a zero-width arc.
    assert.ok(spanOf('Core_2') > 0)
  })

  it('assigns each connected core-pair a tick angle inside both endpoints\' arcs', () => {
    const cores = ['Core_0', 'Core_1']
    const grid = [
      [0, 3],
      [1, 0],
    ]
    const layout = buildChordLayout(cores, grid)
    const arc0 = layout.arcs[0]
    const arc1 = layout.arcs[1]
    const t01 = layout.tickAngle(0, 1)
    const t10 = layout.tickAngle(1, 0)
    assert.ok(t01 >= arc0.startAngle && t01 <= arc0.endAngle)
    assert.ok(t10 >= arc1.startAngle && t10 <= arc1.endAngle)
  })

  it('handles an all-zero matrix by distributing arcs evenly without throwing', () => {
    const cores = ['Core_0', 'Core_1']
    const grid = [
      [0, 0],
      [0, 0],
    ]
    const { arcs } = buildChordLayout(cores, grid)
    assert.equal(arcs.length, 2)
    assert.ok(arcs.every(a => a.endAngle > a.startAngle))
  })

  it('returns an empty layout for zero cores', () => {
    const { arcs } = buildChordLayout([], [])
    assert.deepEqual(arcs, [])
  })
})

describe('chordRingGeometry', () => {
  it('places egress outside ingress, ribbons inside the inner ring', () => {
    const R = 100
    const { rEgress, rIngress, rRibbon } = chordRingGeometry(R)
    assert.equal(rEgress, R)
    assert.ok(rIngress < rEgress)
    assert.ok(rRibbon < rIngress)
    assert.equal(rEgress - rIngress, CHORD_ARC_OUTER + 2)
    assert.equal(chordHitRing(R, R), 'egress')
    assert.equal(chordHitRing(rIngress, R), 'ingress')
    assert.equal(chordHitRing(0, R), null)
    assert.ok(CHORD_ARC_INNER < CHORD_ARC_OUTER)
  })
})

describe('distToQuadraticBezier', () => {
  it('is near zero on the curve and larger off the ribbon centerline', () => {
    const ribbon = buildTaperedRibbonPath(0, 0, 100, 0, Math.PI / 2, 4, 2, 0)
    const midT = distToQuadraticBezier(
      ribbon.ctrl.x * 0.5 + ribbon.p1.x * 0.25 + ribbon.p2.x * 0.25,
      ribbon.ctrl.y * 0.5 + ribbon.p1.y * 0.25 + ribbon.p2.y * 0.25,
      ribbon.p1, ribbon.ctrl, ribbon.p2,
    )
    // Sample t=0.5 on the quadratic is closer than a far-away hub miss.
    const onCurve = distToQuadraticBezier(
      0.25 * ribbon.p1.x + 0.5 * ribbon.ctrl.x + 0.25 * ribbon.p2.x,
      0.25 * ribbon.p1.y + 0.5 * ribbon.ctrl.y + 0.25 * ribbon.p2.y,
      ribbon.p1, ribbon.ctrl, ribbon.p2,
    )
    const far = distToQuadraticBezier(0, 0, ribbon.p1, ribbon.ctrl, ribbon.p2)
    assert.ok(onCurve < 1e-6)
    assert.ok(far > onCurve)
    assert.ok(midT >= 0)
  })
})

describe('traceHasCoreBounceHolds', () => {
  it('returns false when the trace has no sync-object instrumentation', () => {
    assert.equal(traceHasCoreBounceHolds({ hasSyncObjectInstrumentation: false }), false)
  })

  it('returns false when holds never cross cores', () => {
    const trace = {
      hasSyncObjectInstrumentation: true,
      syncObjects: new Map([
        ['m1', { holds: [{ takeCore: 'Core_0', giveCore: 'Core_0' }] }],
      ]),
    }
    assert.equal(traceHasCoreBounceHolds(trace), false)
  })

  it('returns true when a hold was taken on one core and given on another', () => {
    const trace = {
      hasSyncObjectInstrumentation: true,
      syncObjects: new Map([
        ['m1', { holds: [{ takeCore: 'Core_0', giveCore: 'Core_1' }] }],
      ]),
    }
    assert.equal(traceHasCoreBounceHolds(trace), true)
  })
})
