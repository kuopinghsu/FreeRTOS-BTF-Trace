import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { wheelGesturePlan } from '../src/utils/viewportWheel.js'

function wheelEvent(overrides = {}) {
  return {
    deltaX: 0,
    deltaY: 0,
    deltaMode: 0,
    shiftKey: false,
    ...overrides,
  }
}

describe('wheelGesturePlan', () => {
  it('horizontal: vertical swipe scrolls rows (orth)', () => {
    const plan = wheelGesturePlan(wheelEvent({ deltaY: 12, deltaX: 1 }), true)
    assert.equal(plan.doOrth, true)
    assert.equal(plan.orthDelta, 12)
    assert.equal(plan.doTime, false)
  })

  it('horizontal: horizontal swipe pans time', () => {
    const plan = wheelGesturePlan(wheelEvent({ deltaX: 20, deltaY: 2 }), true)
    assert.equal(plan.doTime, true)
    assert.equal(plan.timeDelta, 20)
    assert.equal(plan.doOrth, false)
  })

  it('horizontal: shift swaps axes', () => {
    const plan = wheelGesturePlan(wheelEvent({ deltaY: 10, deltaX: 1, shiftKey: true }), true)
    assert.equal(plan.doTime, true)
    assert.equal(plan.timeDelta, 10)
    assert.equal(plan.doOrth, false)
  })

  it('vertical orientation: vertical swipe pans time', () => {
    const plan = wheelGesturePlan(wheelEvent({ deltaY: 15, deltaX: 2 }), false)
    assert.equal(plan.doTime, true)
    assert.equal(plan.timeDelta, 15)
    assert.equal(plan.doOrth, false)
  })

  it('vertical orientation: horizontal swipe scrolls columns', () => {
    const plan = wheelGesturePlan(wheelEvent({ deltaX: 18, deltaY: 3 }), false)
    assert.equal(plan.doOrth, true)
    assert.equal(plan.orthDelta, 18)
    assert.equal(plan.doTime, false)
  })

  it('prefers orth at trace end on diagonal input', () => {
    const plan = wheelGesturePlan(
      wheelEvent({ deltaX: 10, deltaY: 8 }),
      true,
      { atTraceEnd: true },
    )
    assert.equal(plan.doOrth, true)
    assert.equal(plan.doTime, false)
  })
})
