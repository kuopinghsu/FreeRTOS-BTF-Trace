import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { formatMigrationGapTime, formatTime, formatTimeFixed } from '../src/utils/timeFormat.js'

describe('formatTime', () => {
  it('scales nanoseconds to milliseconds', () => {
    assert.match(formatTime(1_500_000, 'ns'), /ms/)
  })

  it('keeps sub-microsecond values in ns', () => {
    assert.equal(formatTime(42, 'ns'), '42 ns')
  })

  it('formats microsecond trace scale', () => {
    assert.match(formatTime(2500, 'us'), /ms/)
  })

  it('rounds fractional base-unit values instead of leaking float noise (desktop parity)', () => {
    // Desktop `_format_time` always formats via a fixed-decimals string, so a
    // fractional native-unit value (e.g. from a pixel-to-time hover conversion)
    // never shows raw binary-fp residue like JS's default `0.1 + 0.2` would.
    assert.equal(formatTime(0.1 + 0.2, 'us'), '0.300 µs')
    assert.equal(formatTime(500.7, 'us'), '500.700 µs')
    assert.equal(formatTime(42.5, 'ns', 1), '42.5 ns')
  })
})

describe('formatTimeFixed', () => {
  it('always uses fixed decimals like desktop _format_time', () => {
    assert.equal(formatTimeFixed(2, 'us'), '2.000 µs')
    assert.equal(formatTimeFixed(42, 'ns'), '42.000 ns')
    assert.equal(formatTimeFixed(1000, 'ns'), '1.000 µs')
  })
})

describe('formatMigrationGapTime', () => {
  it('returns dash for non-finite input', () => {
    assert.equal(formatMigrationGapTime(NaN, 'ns'), '-')
  })

  it('truncates (does not round) native-unit gaps, matching desktop parity', () => {
    // Desktop: `_format_time(int(avg), scale)` truncates before formatting.
    assert.equal(formatMigrationGapTime(4.6, 'us'), '4 µs')
  })
})
