import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  formatSemanticDelta,
  semanticLabel,
  SEMANTIC_GLYPHS,
} from '../src/utils/semanticColors.js'
import { COMMAND_PALETTE_ACTIONS, COMMAND_PALETTE_META } from '../src/config.js'
import { formatFindStatus } from '../src/utils/findAnalysis.js'
import { EVIDENCE_TOOLTIP } from '../src/utils/evidenceNav.js'

describe('step3 ux polish', () => {
  it('semanticLabel prefixes glyphs in colorblind mode', () => {
    assert.equal(semanticLabel('Improved', 'improved', true), `${SEMANTIC_GLYPHS.improved} Improved`)
    assert.equal(semanticLabel('Regressed', 'regressed', true), `${SEMANTIC_GLYPHS.regressed} Regressed`)
    assert.equal(semanticLabel('Improved', 'improved', false), 'Improved')
  })

  it('formatSemanticDelta maps Improved/Regressed roles', () => {
    assert.match(formatSemanticDelta('+12 µs', 'Regressed', true), /↑/)
    assert.match(formatSemanticDelta('−3 µs', 'Improved', true), /↓/)
    assert.equal(formatSemanticDelta('+12 µs', 'Regressed', false), '+12 µs')
  })

  it('command palette Fit Trace label and shortcuts', () => {
    const fit = COMMAND_PALETTE_ACTIONS.find(([id]) => id === 'fit')
    assert.equal(fit?.[1], 'Fit Trace')
    assert.equal(COMMAND_PALETTE_META.fit.shortcut, 'Ctrl+0')
    assert.equal(COMMAND_PALETTE_META.find.shortcut, 'Ctrl+F')
    assert.equal(COMMAND_PALETTE_META.marks.shortcut, 'Ctrl+B')
  })

  it('command palette offers Focus mode (needs a trace)', () => {
    const focus = COMMAND_PALETTE_ACTIONS.find(([id]) => id === 'focus')
    assert.equal(focus?.[1], 'Focus mode')
    assert.equal(COMMAND_PALETTE_META.focus.requires, 'trace')
    assert.ok(COMMAND_PALETTE_META.focus.synonyms.includes('zen'))
  })

  it('Find status stays concise without Match Mode lecture', () => {
    const text = formatFindStatus({
      hitCount: 0,
      hitIndex: -1,
      mode: 'contains',
      query: 'Worker',
      error: '',
    })
    assert.match(text, /0 matches/)
    assert.doesNotMatch(text, /Match Mode/)
  })

  it('Evidence tooltip mentions Scope or Filters', () => {
    assert.match(EVIDENCE_TOOLTIP, /Scope or Filters/)
  })
})
