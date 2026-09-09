import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { addBookmark, addEvidence, newInvestigation } from '../src/utils/investigationNotebook.js'
import {
  NB_AI_ACTIONS,
  NB_AI_DISABLED_REASON,
  OP_CONFIRM,
  OP_OK,
  OP_REJECTED,
  PROPOSAL_SCHEMA,
  applyProposal,
  collaborateContext,
  collaborateDigest,
  collaborateHeader,
  nbAiActionReason,
  parseQuestionSuggestion,
  proposalDiff,
  stripModelSecrets,
  validateProposal,
} from '../src/utils/investigationAi.js'

function inv() {
  let x = newInvestigation({ title: 'Why deadline miss?', traceIdentity: { hash: 'abc', file: 'run.btf' } })
  x = addEvidence(x, {
    title: '120 migrations', role: 'supporting', source: 'Statistics', kind: 'measured',
    author: 'btfviewer', value: 120, unit: 'migrations',
    refs: [{ kind: 'metric', metric: 'migrations' }], bookmarkId: 'e1',
  })
  x = addBookmark(x, { type: 'hypothesis', title: 'core thrash', bookmarkId: 'h1' })
  return x
}

function validated() {
  return validateProposal(inv(), {
    model: { model: 'gpt-x', provider: 'openai', api_key: 'sk-SECRET' },
    operations: [
      { op: 'add', role: 'supporting', title: 'AI: affinity mask', author: 'ai', evidence_ids: ['e1'], rationale: 'from e1' },
      { op: 'link', from: 'e1', to: 'h1', relation: 'supports' },
      { op: 'change_status', status: 'closed' },
      { op: 'update', bookmark_id: 'e1', changes: { value: 1 } },
    ],
  })
}

describe('§9 collaborate with AI', () => {
  it('seven focused actions (six original + refine_question for the Question step)', () => {
    assert.deepEqual(NB_AI_ACTIONS.map(a => a[0]), [
      'review_investigation', 'suggest_next_check', 'draft_hypotheses',
      'draft_conclusion', 'update_from_findings', 'compare_trace', 'refine_question',
    ])
  })
  it('disabled when AI unavailable', () => {
    assert.equal(nbAiActionReason('review_investigation', inv(), { aiEnabled: false }), NB_AI_DISABLED_REASON)
  })
  it('compare needs a second trace; conclusion needs evidence', () => {
    assert.match(nbAiActionReason('compare_trace', inv(), { aiEnabled: true }), /second trace/)
    assert.equal(nbAiActionReason('compare_trace', inv(), { aiEnabled: true, hasSecondTrace: true }), '')
    assert.match(nbAiActionReason('draft_conclusion', newInvestigation({ title: 'x' }), { aiEnabled: true }), /evidence/)
  })
  it('context sends only selected evidence (projection, not raw)', () => {
    const ctx = collaborateContext(inv(), { action: 'draft_conclusion', selectedEvidenceIds: ['e1'] })
    assert.equal(ctx.selected_evidence.length, 1)
    assert.equal(ctx.selected_evidence[0].bookmark_id, 'e1')
    assert.ok('sections' in ctx.investigation)
    assert.ok(!('bookmarks' in ctx.investigation))
  })
  it('header reports stale', () => {
    const h = collaborateHeader(inv(), { broken: { issues: [{ bookmark_id: 'e1' }] } })
    assert.match(h.stale_warning, /no longer resolve/)
  })
  it('digest is readable Markdown, never JSON', () => {
    const d = collaborateDigest(collaborateContext(inv(), { action: 'review_investigation' }))
    assert.match(d, /\*\*Question\*\*/)
    assert.match(d, /\*\*Evidence \(1\)\*\*/)
    assert.match(d, /120 migrations/)
    assert.match(d, /\*\*Conclusion\*\*/)
    assert.ok(!d.includes('{'))
    assert.ok(!d.includes('"bookmark_id"'))
    assert.equal(typeof collaborateDigest(null), 'string')
  })
})

describe('refine_question suggestion parsing (bypasses the proposal machinery)', () => {
  it('extracts the suggested question, case-insensitively', () => {
    assert.equal(
      parseQuestionSuggestion('Suggested question: Why does ControlTask stall?'),
      'Why does ControlTask stall?')
    assert.equal(
      parseQuestionSuggestion('suggested question:  Why does it stall before dispatch?  '),
      'Why does it stall before dispatch?')
  })
  it('strips surrounding quotes', () => {
    assert.equal(
      parseQuestionSuggestion('Suggested question: "Why does it stall?"'),
      'Why does it stall?')
  })
  it('returns empty for non-matching text — never invents from unstructured prose', () => {
    assert.equal(parseQuestionSuggestion('Here is a general review of your investigation.'), '')
    assert.equal(parseQuestionSuggestion(''), '')
    assert.equal(parseQuestionSuggestion(null), '')
  })
})

describe('§10 proposal review', () => {
  it('AI add-measured is downgraded', () => {
    const v = validateProposal(inv(), { operations: [{ op: 'add', role: 'supporting', title: 't', kind: 'measured', author: 'ai' }] })
    assert.equal(v.operations[0].status, OP_OK)
    assert.notEqual(v.operations[0].card.kind, 'measured')
  })
  it('updating a measured field is rejected', () => {
    const v = validateProposal(inv(), { operations: [{ op: 'update', bookmark_id: 'e1', changes: { value: 999 } }] })
    assert.equal(v.operations[0].status, OP_REJECTED)
    assert.match(v.operations[0].reason, /measured data not changed/)
  })
  it('close + remove need confirmation', () => {
    const v = validateProposal(inv(), { operations: [
      { op: 'change_status', status: 'closed' },
      { op: 'remove', bookmark_id: 'e1' },
    ] })
    assert.deepEqual(v.operations.map(o => o.status), [OP_CONFIRM, OP_CONFIRM])
  })
  it('other trace without compare is rejected', () => {
    const v = validateProposal(inv(), { operations: [{ op: 'add', role: 'supporting', title: 't', trace_id: 'OTHER' }] })
    assert.equal(v.operations[0].status, OP_REJECTED)
    const v2 = validateProposal(inv(), { operations: [{ op: 'add', role: 'supporting', title: 't', trace_id: 'OTHER' }] }, { allowOtherTrace: true })
    assert.equal(v2.operations[0].status, OP_OK)
  })
  it('model secrets are stripped', () => {
    assert.deepEqual(stripModelSecrets({ model: 'm', api_key: 'k', prompt: 'p' }), { model: 'm' })
    assert.equal(validated().schema, PROPOSAL_SCHEMA)
    assert.deepEqual(validated().model, { model: 'gpt-x', provider: 'openai' })
  })
  it('only accepted OK ops apply; measured value untouched; AI provenance stamped', () => {
    const { inv: out, applied, skipped } = applyProposal(inv(), validated(), { acceptAll: true })
    assert.deepEqual(applied, [0, 1])
    assert.deepEqual(skipped.slice().sort(), [2, 3])
    const ai = out.bookmarks.filter(b => (b.evidence || {}).author === 'ai')
    assert.equal(ai.length, 1)
    assert.notEqual(ai[0].evidence.kind, 'measured')
    assert.deepEqual(ai[0].evidence.ai_provenance, { model: 'gpt-x', provider: 'openai', source_evidence_ids: ['e1'] })
    assert.equal(out.bookmarks.find(b => b.id === 'e1').evidence.value, 120)
  })
  it('confirmation gates close', () => {
    assert.ok(!applyProposal(inv(), validated(), { acceptAll: true }).applied.includes(2))
    const { inv: out, applied } = applyProposal(inv(), validated(), { acceptAll: true, confirmedIndices: [2] })
    assert.ok(applied.includes(2))
    assert.equal(out.status, 'closed')
  })
  it('proposal events recorded without secrets; nothing applies by default', () => {
    const { inv: out } = applyProposal(inv(), validated(), { acceptAll: true, now: '2026-09-08T12:00' })
    const ev = out.proposal_events[out.proposal_events.length - 1]
    assert.equal(ev.schema, PROPOSAL_SCHEMA)
    assert.deepEqual(ev.model, { model: 'gpt-x', provider: 'openai' })
    const noop = applyProposal(inv(), validated(), { acceptIndices: [] })
    assert.deepEqual(noop.applied, [])
    assert.ok(!('proposal_events' in noop.inv))
  })
  it('diff is grouped by section', () => {
    const d = proposalDiff(inv(), validated())
    assert.deepEqual(d.needs_confirmation.map(o => o.index), [2])
    assert.deepEqual(d.rejected.map(o => o.index), [3])
    assert.ok(d.by_section.evidence.length)
    assert.ok(d.by_section.links.length)
  })
})
