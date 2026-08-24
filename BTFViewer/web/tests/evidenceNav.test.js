import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  EVIDENCE_GLYPH,
  EVIDENCE_TOOLTIP,
  parseEvidenceTimestamps,
  resolveFindingEvidence,
  resolveTimestampEvidence,
} from '../src/utils/evidenceNav.js'

describe('evidenceNav', () => {
  it('exports glyph and Scope-preserving tooltip', () => {
    assert.equal(EVIDENCE_GLYPH, '\u2197')
    assert.match(EVIDENCE_TOOLTIP, /Scope or Filters/)
  })

  it('parseEvidenceTimestamps handles units and jump:', () => {
    assert.deepEqual(
      parseEvidenceTimestamps('at 1.5 ms and jump:2000 us'),
      [1_500_000, 2_000_000],
    )
  })

  it('parseEvidenceTimestamps skips ambiguous bare ints', () => {
    assert.deepEqual(parseEvidenceTimestamps('count 42 gaps'), [])
    assert.deepEqual(parseEvidenceTimestamps('1234567'), [1_234_567])
  })

  it('resolveFindingEvidence prefers latest evidence time', () => {
    const out = resolveFindingEvidence(
      {
        title: 'Tail',
        task: 'Worker[3]',
        evidence: [{ time: 1000 }, { time: 5000 }],
      },
      [],
      0,
      10_000,
    )
    assert.equal(out.ok, true)
    assert.equal(out.ns, 5000)
    assert.equal(out.multi, true)
    assert.equal(out.task, 'Worker[3]')
  })

  it('resolveFindingEvidence fails when nothing locatable', () => {
    const out = resolveFindingEvidence({ title: 'x' }, [], 0, 0)
    assert.equal(out.ok, false)
    assert.match(out.reason, /No locatable/)
  })

  it('resolveTimestampEvidence clamps and validates', () => {
    const ok = resolveTimestampEvidence(50, { task: 'T', timeMin: 100, timeMax: 200 })
    assert.equal(ok.ok, true)
    assert.equal(ok.ns, 100)
    const bad = resolveTimestampEvidence(null)
    assert.equal(bad.ok, false)
  })
})
