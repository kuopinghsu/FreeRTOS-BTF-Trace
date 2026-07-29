import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { formatMigrationGapTime, formatTime } from '../src/utils/timeFormat.js'

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
