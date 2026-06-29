import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  collectTraceQualityWarnings,
  traceQualitySummary,
} from '../src/utils/traceQuality.js'

function trace(meta) {
  return { meta }
}

describe('collectTraceQualityWarnings', () => {
  it('reads #ringOverflow true from flat meta', () => {
    const warnings = collectTraceQualityWarnings(trace({ ringOverflow: 'true' }))
    assert.equal(warnings.length, 1)
    assert.match(warnings[0], /ring buffer overflow/)
  })

  it('reads all three BTF quality flags', () => {
    const warnings = collectTraceQualityWarnings(trace({
      ringOverflow: 'true',
      taskTableOverflow: 'true',
      truncated: 'true',
    }))
    assert.equal(warnings.length, 3)
  })

  it('includes parser version warning', () => {
    const warnings = collectTraceQualityWarnings(trace({
      _versionWarning: 'Unsupported BTF format version: 3.0.0 (expected 2.x)',
    }))
    assert.equal(warnings.length, 1)
    assert.match(warnings[0], /Unsupported/)
  })

  it('reads nested traceQuality object', () => {
    const warnings = collectTraceQualityWarnings(trace({
      traceQuality: { ring_overflow: true },
    }))
    assert.equal(warnings.length, 1)
  })
})

describe('traceQualitySummary', () => {
  it('joins warnings with middle dot', () => {
    const text = traceQualitySummary(trace({
      ringOverflow: 'true',
      truncated: 'true',
    }))
    assert.ok(text.includes(' · '))
  })

  it('returns null for clean traces', () => {
    assert.equal(traceQualitySummary(trace({ version: '2.2.0' })), null)
  })
})
