import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  buildAnalysisContext,
  formatAnalysisContextStrip,
  isContextStale,
} from '../src/utils/analysisContext.js'
import { formatUseAsScopePrompt, shouldOfferUseAsScope } from '../src/utils/cursorScope.js'
import { enrichFindingCard } from '../src/utils/findingsTriage.js'
import { GUIDED_REVIEW_STEPS } from '../src/utils/guidedInvestigation.js'
import { availableSymptomCards } from '../src/utils/statsSymptomLanding.js'
import { traceQualityReport } from '../src/utils/traceQuality.js'
import { HTML_REPORT_INTERACTIVE_SCRIPT } from '../src/utils/htmlReport.js'

describe('UX Milestone A+B', () => {
  it('analysis context warns when cursors do not limit', () => {
    const ctx = buildAnalysisContext({
      scopeLabel: 'Full Trace',
      cursorCount: 2,
      limitToCursors: false,
    })
    assert.match(formatAnalysisContextStrip(ctx), /Not limited to cursors/)
    assert.equal(formatAnalysisContextStrip(ctx, { compact: true }), 'Not limited to cursors')
    assert.doesNotMatch(formatAnalysisContextStrip(ctx, { compact: true }), /Scope:|Samples:/)
  })

  it('detects stale context', () => {
    const a = buildAnalysisContext({ scopeLabel: 'Full Trace' })
    const b = buildAnalysisContext({ scopeLabel: 'C1–C2', filterLabels: ['Task: x'] })
    assert.equal(isContextStale(a, a), false)
    assert.equal(isContextStale(a, b), true)
  })

  it('offers use-as-scope prompt', () => {
    assert.equal(shouldOfferUseAsScope([1, 2], { limitToCursors: false }), true)
    assert.match(formatUseAsScopePrompt([1, 2]), /C1–C2/)
  })

  it('enriches finding triage cards', () => {
    const card = enrichFindingCard({
      title: 'Late task',
      text: 'p99 high',
      evidence: [{ label: 'rt', time: 9 }],
    })
    assert.equal(card.observation, 'Late task')
    assert.match(card.evidence_text, /jump:9/)
  })

  it('symptom landing disables sync without STI', () => {
    const sync = availableSymptomCards({ hasSti: false }).find(c => c.id === 'sync')
    assert.ok(sync.disabled)
  })

  it('trace quality report groups issues', () => {
    const rep = traceQualityReport({ meta: { traceQuality: { truncated: true } } })
    assert.equal(rep.ok, false)
    assert.ok(rep.groups.length)
  })

  it('HTML report script has a per-table CSV download button', () => {
    assert.match(HTML_REPORT_INTERACTIVE_SCRIPT, /class="table-csv"/)
    assert.match(HTML_REPORT_INTERACTIVE_SCRIPT, /text\/csv/)
    assert.match(HTML_REPORT_INTERACTIVE_SCRIPT, /lastFiltered/)
  })

  it('guided review has workflow steps', () => {
    assert.ok(GUIDED_REVIEW_STEPS.length >= 6)
  })
})
