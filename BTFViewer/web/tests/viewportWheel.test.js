import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  wheelGesturePlan,
  wheelPanDeltas,
  physicalVerticalDominant,
  mappedWheelDeltas,
  applyWheelPlanToViewport,
  clampViewportScrollY,
  clampViewportScrollX,
} from '../src/utils/viewportWheel.js'

function wheelEvent(overrides = {}) {
  return {
    deltaX: 0,
    deltaY: 0,
    deltaMode: 0,
    shiftKey: false,
    ...overrides,
  }
}

const baseVp = {
  timeStart: 100,
  timeEnd: 200,
  scrollY: 50,
  scrollX: 30,
  canvasW: 800,
  canvasH: 600,
}

describe('wheelPanDeltas', () => {
  it('recovers vertical motion from wheelDeltaY when deltaY is zero', () => {
    const { dy } = wheelPanDeltas(wheelEvent({ deltaX: 12, deltaY: 0, wheelDeltaY: -36 }))
    assert.equal(dy, 12)
  })
})

describe('physicalVerticalDominant', () => {
  it('uses wheelDelta when pixel deltas are misleading', () => {
    const e = wheelEvent({ deltaX: 20, deltaY: 2, wheelDeltaY: -60, wheelDeltaX: -5 })
    assert.equal(physicalVerticalDominant(e, 20, 2), true)
  })
})

describe('mappedWheelDeltas', () => {
  it('horizontal no shift maps dx→time and dy→orth', () => {
    assert.deepEqual(mappedWheelDeltas(true, false, 10, 5), { time: 10, orth: 5 })
  })

  it('vertical no shift maps dy→time and dx→orth', () => {
    assert.deepEqual(mappedWheelDeltas(false, false, 10, 5), { time: 5, orth: 10 })
  })
})

describe('wheelGesturePlan — horizontal orientation', () => {
  it('vertical swipe scrolls rows (no shift)', () => {
    const plan = wheelGesturePlan(wheelEvent({ deltaY: 12, deltaX: 1 }), true)
    assert.equal(plan.doOrth, true)
    assert.equal(plan.orthDelta, 12)
    assert.equal(plan.doTime, false)
  })

  it('horizontal swipe pans time (no shift)', () => {
    const plan = wheelGesturePlan(wheelEvent({ deltaX: 20, deltaY: 2 }), true)
    assert.equal(plan.doTime, true)
    assert.equal(plan.timeDelta, 20)
    assert.equal(plan.doOrth, false)
  })

  it('vertical swipe scrolls rows when motion is on deltaX (no shift)', () => {
    const plan = wheelGesturePlan(
      wheelEvent({ deltaX: 18, deltaY: 0, wheelDeltaY: -54, wheelDeltaX: -3 }),
      true,
    )
    assert.equal(plan.doOrth, true)
    assert.equal(plan.orthDelta, 18)
    assert.equal(plan.doTime, false)
  })

  it('shift+vertical swipe pans time', () => {
    const plan = wheelGesturePlan(wheelEvent({ deltaY: 10, deltaX: 1, shiftKey: true }), true)
    assert.equal(plan.doTime, true)
    assert.equal(plan.timeDelta, 10)
    assert.equal(plan.doOrth, false)
  })

  it('shift+horizontal swipe scrolls rows', () => {
    const plan = wheelGesturePlan(wheelEvent({ deltaX: 14, deltaY: 2, shiftKey: true }), true)
    assert.equal(plan.doOrth, true)
    assert.equal(plan.orthDelta, 14)
    assert.equal(plan.doTime, false)
  })
})

describe('wheelGesturePlan — vertical orientation', () => {
  it('vertical swipe pans time (no shift)', () => {
    const plan = wheelGesturePlan(wheelEvent({ deltaY: 15, deltaX: 2 }), false)
    assert.equal(plan.doTime, true)
    assert.equal(plan.timeDelta, 15)
    assert.equal(plan.doOrth, false)
  })

  it('horizontal swipe scrolls columns (no shift)', () => {
    const plan = wheelGesturePlan(wheelEvent({ deltaX: 18, deltaY: 3 }), false)
    assert.equal(plan.doOrth, true)
    assert.equal(plan.orthDelta, 18)
    assert.equal(plan.doTime, false)
  })

  it('horizontal swipe scrolls columns when classified via wheelDelta (no shift)', () => {
    const plan = wheelGesturePlan(
      wheelEvent({ deltaX: 16, deltaY: 1, wheelDeltaY: -4, wheelDeltaX: -48 }),
      false,
    )
    assert.equal(plan.doOrth, true)
    assert.equal(plan.orthDelta, 16)
    assert.equal(plan.doTime, false)
  })

  it('shift+vertical swipe scrolls columns', () => {
    const plan = wheelGesturePlan(wheelEvent({ deltaY: 11, deltaX: 1, shiftKey: true }), false)
    assert.equal(plan.doOrth, true)
    assert.equal(plan.orthDelta, 11)
    assert.equal(plan.doTime, false)
  })

  it('shift+horizontal swipe pans time', () => {
    const plan = wheelGesturePlan(wheelEvent({ deltaX: 16, deltaY: 2, shiftKey: true }), false)
    assert.equal(plan.doTime, true)
    assert.equal(plan.timeDelta, 16)
    assert.equal(plan.doOrth, false)
  })

  it('prefers orth at trace end on ambiguous diagonal input', () => {
    const plan = wheelGesturePlan(
      wheelEvent({ deltaX: 10, deltaY: 8, shiftKey: true }),
      false,
      { atTraceEnd: true },
    )
    assert.equal(plan.doOrth, true)
    assert.equal(plan.doTime, false)
    assert.equal(plan.orthDelta, 8)
  })
})

describe('applyWheelPlanToViewport (integration)', () => {
  it('horizontal: vertical swipe increases scrollY', () => {
    const e = wheelEvent({ deltaX: 18, deltaY: 0, wheelDeltaY: -54, wheelDeltaX: -3 })
    const plan = wheelGesturePlan(e, true)
    const vp = applyWheelPlanToViewport(plan, baseVp, true)
    assert.ok(vp.scrollY > baseVp.scrollY)
    assert.equal(vp.timeStart, baseVp.timeStart)
    assert.equal(vp.timeEnd, baseVp.timeEnd)
  })

  it('horizontal: horizontal swipe pans time, not scrollY', () => {
    const e = wheelEvent({ deltaX: 24, deltaY: 1 })
    const plan = wheelGesturePlan(e, true)
    const vp = applyWheelPlanToViewport(plan, baseVp, true)
    assert.notEqual(vp.timeStart, baseVp.timeStart)
    assert.equal(vp.scrollY, baseVp.scrollY)
  })

  it('vertical: vertical swipe pans time, not scrollX', () => {
    const e = wheelEvent({ deltaY: 20, deltaX: 1 })
    const plan = wheelGesturePlan(e, false)
    const vp = applyWheelPlanToViewport(plan, baseVp, false)
    assert.notEqual(vp.timeStart, baseVp.timeStart)
    assert.equal(vp.scrollX, baseVp.scrollX)
  })

  it('vertical: horizontal swipe increases scrollX', () => {
    const e = wheelEvent({ deltaX: 22, deltaY: 1 })
    const plan = wheelGesturePlan(e, false)
    const vp = applyWheelPlanToViewport(plan, baseVp, false)
    assert.ok(vp.scrollX > baseVp.scrollX)
    assert.equal(vp.timeStart, baseVp.timeStart)
  })

  it('clampViewportScrollY caps row scroll to content height', () => {
    const e = wheelEvent({ deltaY: 500, deltaX: 0 })
    const plan = wheelGesturePlan(e, true)
    let vp = applyWheelPlanToViewport(plan, { ...baseVp, scrollY: 900 }, true)
    vp = clampViewportScrollY(vp, 1000)
    assert.equal(vp.scrollY, 428)
  })

  it('clampViewportScrollX caps column scroll to content width', () => {
    const e = wheelEvent({ deltaX: 500, deltaY: 0 })
    const plan = wheelGesturePlan(e, false)
    let vp = applyWheelPlanToViewport(plan, { ...baseVp, scrollX: 900 }, false)
    vp = clampViewportScrollX(vp, 1200)
    assert.equal(vp.scrollX, 400)
  })
})
