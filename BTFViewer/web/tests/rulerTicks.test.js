import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  formatTime,
  firstTickOnOrBefore,
  firstTickOnOrAfter,
  niceStep,
  tickOrigin,
} from '../src/renderer/TimelineRenderer.js'

describe('ruler ticks anchored at timeMin', () => {
  it('example-8cores start is 1.014 s, not 1.000 s', () => {
    // BTF timeScale=us; first event at 1014005 µs.
    assert.equal(formatTime(1014005, 'us'), '1.014 s')
  })

  it('fit-to-window first tick is timeMin (desktop parity)', () => {
    const timeMin = 1014005
    const timeMax = 1014005 + 5_000_000
    const step = niceStep(timeMax - timeMin)
    const origin = tickOrigin({ timeMin })
    const first = firstTickOnOrBefore(timeMin, step, origin)
    assert.equal(first, timeMin)
    assert.equal(formatTime(first, 'us'), '1.014 s')
  })

  it('does not place an absolute 1.000 s tick before a 1.014 s start', () => {
    const timeMin = 1014005
    const step = 200000 // 0.2 s in µs
    const origin = tickOrigin({ timeMin })
    const absSnap = Math.ceil(timeMin / step) * step // old web behavior
    assert.ok(absSnap >= 1_000_000)
    // Origin-anchored first tick stays at timeMin when fitting.
    assert.equal(firstTickOnOrBefore(timeMin, step, origin), timeMin)
    assert.equal(firstTickOnOrAfter(timeMin, step, origin), timeMin)
  })
})
