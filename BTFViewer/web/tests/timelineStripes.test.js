import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  stripeClassForBand,
  stripeColorForBand,
  timelineStripePalette,
} from '../src/utils/timelineStripes.js'

describe('timelineStripePalette', () => {
  it('matches desktop even/odd row colors', () => {
    const dark = timelineStripePalette(true)
    assert.equal(dark.even, '#252526')
    assert.equal(dark.odd, '#2D2D2D')
    const light = timelineStripePalette(false)
    assert.equal(light.even, '#FFFFFF')
    assert.equal(light.odd, '#F2F2F2')
  })
})

describe('stripeColorForBand', () => {
  it('interleaves task rows', () => {
    assert.equal(stripeColorForBand({ type: 'task', stripeIdx: 0 }, true), '#252526')
    assert.equal(stripeColorForBand({ type: 'task', stripeIdx: 1 }, true), '#2D2D2D')
    assert.equal(stripeColorForBand({ type: 'task', stripeIdx: 2 }, false), '#FFFFFF')
    assert.equal(stripeColorForBand({ type: 'task', stripeIdx: 3 }, false), '#F2F2F2')
  })

  it('uses core / STI specialty fills', () => {
    assert.equal(stripeColorForBand({ type: 'core', stripeIdx: 0 }, true), '#2A2A3E')
    assert.equal(stripeColorForBand({ type: 'core-task', stripeIdx: 0 }, true), '#1E1E2C')
    assert.equal(stripeColorForBand({ type: 'core-task', stripeIdx: 1 }, true), '#232330')
    assert.equal(stripeColorForBand({ type: 'sti', stripeIdx: 4 }, true), '#1A1A2E')
  })
})

describe('stripeClassForBand', () => {
  it('maps to CSS stripe classes', () => {
    assert.equal(stripeClassForBand({ type: 'task', stripeIdx: 1 }), 'stripe-odd')
    assert.equal(stripeClassForBand({ type: 'core-task', stripeIdx: 0 }), 'stripe-core-sub-even')
    assert.equal(stripeClassForBand({ type: 'interval' }), 'stripe-sti')
  })
})
