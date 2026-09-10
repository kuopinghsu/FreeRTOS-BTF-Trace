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
  extractNotebookProposal,
  looksLikeTruncatedProposal,
  nbAiActionReason,
  parseQuestionSuggestion,
  parseReplyBlocks,
  proposalDiff,
  summarizeNotebookProposalForChat,
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
  it('eight focused actions (adds gather_evidence — an agentic tool loop — after review)', () => {
    assert.deepEqual(NB_AI_ACTIONS.map(a => a[0]), [
      'review_investigation', 'gather_evidence', 'suggest_next_check', 'draft_hypotheses',
      'draft_conclusion', 'update_from_findings', 'compare_trace', 'refine_question',
    ])
  })
  it('gather_evidence tells the model to call tools repeatedly, then emit the proposal', () => {
    const p = Object.fromEntries(NB_AI_ACTIONS.map(a => [a[0], a[2]])).gather_evidence
    assert.match(p, /CALLING BTFViewer tools/)
    assert.match(p, /as many times as needed/)
    assert.match(p, /btf-viewer-nb-proposal\/1/)
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

describe('§10 AI can add a hypothesis (demo parity: "Add hypothesis")', () => {
  it('add role:hypothesis validates OK and lands in the Hypotheses group', () => {
    const v = validateProposal(inv(), { operations: [
      { op: 'add', role: 'Hypothesis', title: 'Affinity thrash on core 1', evidence_ids: ['e1'] },
    ] })
    assert.equal(v.operations[0].status, OP_OK)
    assert.equal(v.operations[0].reason, undefined)
    const d = proposalDiff(inv(), v)
    assert.equal(d.by_section.hypotheses.length, 1)
    assert.equal(d.by_section.evidence.length, 0)
  })
  it('a hypothesis add with no cited evidence is still OK but flagged', () => {
    const v = validateProposal(inv(), { operations: [
      { op: 'add', role: 'hypothesis', title: 'no citation' },
    ] })
    assert.equal(v.operations[0].status, OP_OK)
    assert.match(v.operations[0].reason, /cites no evidence id/)
  })
  it('applying it adds a hypothesis bookmark and links each cited evidence as "supports"', () => {
    const v = validateProposal(inv(), { operations: [
      { op: 'add', role: 'hypothesis', title: 'Affinity thrash on core 1', note: 'from E1', evidence_ids: ['e1', 'missing'] },
    ] })
    const { inv: out, applied } = applyProposal(inv(), v, { acceptAll: true })
    assert.deepEqual(applied, [0])
    const hyp = out.bookmarks.find(b => b.type === 'hypothesis' && b.title === 'Affinity thrash on core 1')
    assert.ok(hyp, 'hypothesis bookmark created')
    assert.ok(!hyp.evidence, 'a hypothesis carries no evidence card')
    const link = (out.links || []).find(l =>
      String(l.from) === 'e1' && String(l.to) === String(hyp.id) && l.relation === 'supports')
    assert.ok(link, 'cited evidence linked to the hypothesis')
    assert.ok(!(out.links || []).some(l => String(l.from) === 'missing'), 'unknown id skipped, not an error')
  })
  it('a malformed role is still rejected with the widened reason', () => {
    const v = validateProposal(inv(), { operations: [{ op: 'add', role: 'not_a_role', title: 'x' }] })
    assert.equal(v.operations[0].status, OP_REJECTED)
    assert.match(v.operations[0].reason, /evidence or hypothesis role/)
  })
})

describe('§10 structured reply carries summary + notes (review-only case)', () => {
  it('validateProposal passes summary and cleaned notes through', () => {
    const v = validateProposal(inv(), {
      schema: 'btf-viewer-nb-proposal/1',
      summary: '  Two claims are unsupported.  ',
      notes: ['Max slice is treated as WCET', '', '  Migration count has no latency link  ', null],
      operations: [],
    })
    assert.equal(v.ok, false)
    assert.equal(v.summary, 'Two claims are unsupported.')
    assert.deepEqual(v.notes, ['Max slice is treated as WCET', 'Migration count has no latency link'])
  })
  it('every non-refine collaborate prompt demands the JSON envelope', () => {
    const byId = Object.fromEntries(NB_AI_ACTIONS.map(a => [a[0], a[2]]))
    for (const id of ['review_investigation', 'suggest_next_check', 'draft_hypotheses',
      'draft_conclusion', 'update_from_findings', 'compare_trace']) {
      assert.match(byId[id], /btf-viewer-nb-proposal\/1/, id)
      assert.match(byId[id], /"operations"/, id)
    }
    assert.doesNotMatch(byId.refine_question, /btf-viewer-nb-proposal/)
  })
})

describe('parseReplyBlocks (prose reply → titled sections + bullets)', () => {
  it('headings become titled sections; bullets / numbers / prose become items', () => {
    const blocks = parseReplyBlocks(
      '### 結論\nTwo claims are unsupported.\n\n'
      + '### Unsupported Claims\n1. **Max slice** is treated as WCET\n- Migration count has no latency link')
    assert.deepEqual(blocks.map(b => b.title), ['結論', 'Unsupported Claims'])
    assert.deepEqual(blocks[0].items, ['Two claims are unsupported.'])
    assert.deepEqual(blocks[1].items,
      ['Max slice is treated as WCET', 'Migration count has no latency link'])
  })
  it('a lone **Bold:** line is a heading; plain prose is one untitled block; empty → []', () => {
    assert.deepEqual(parseReplyBlocks('**Findings:**\nfoo\nbar'),
      [{ title: 'Findings', items: ['foo', 'bar'] }])
    assert.deepEqual(parseReplyBlocks('just one line'),
      [{ title: '', items: ['just one line'] }])
    assert.deepEqual(parseReplyBlocks(''), [])
    assert.deepEqual(parseReplyBlocks(null), [])
  })
})

describe('extractNotebookProposal (tolerant of how the model wraps the JSON)', () => {
  const OBJ = '{"schema":"btf-viewer-nb-proposal/1","summary":"only one measured item","notes":["no hypotheses"],"operations":[{"op":"add","role":"observation","title":"Check Mutex Blocking","note":"open the section","evidence_ids":["E1"]}]}'

  it('plain fenced block', () => {
    const p = extractNotebookProposal('```json\n' + OBJ + '\n```')
    assert.equal(p.summary, 'only one measured item')
    assert.equal(p.operations.length, 1)
  })
  it('fence + object inside a markdown list, with trailing prose and links', () => {
    const reply = [
      'AI reply', '', '* ```json', '* ' + OBJ, '* ```',
      '* Investigate the current finding. [Run](btfnext:text/0)',
      '* Investigate remaining finding [Open Statistics](btfstats:section/block)',
    ].join('\n')
    const p = extractNotebookProposal(reply)
    assert.ok(p, 'proposal must be extracted from the list-wrapped reply')
    assert.equal(p.operations[0].title, 'Check Mutex Blocking')
    assert.deepEqual(p.notes, ['no hypotheses'])
  })
  it('bare unfenced object buried in prose', () => {
    const p = extractNotebookProposal('Here is my analysis: ' + OBJ + ' — let me know.')
    assert.ok(p)
    assert.equal(p.summary, 'only one measured item')
  })
  it('review-only object with no operations key still parses (operations defaulted to [])', () => {
    const p = extractNotebookProposal('```json\n{"schema":"btf-viewer-nb-proposal/1","summary":"s","notes":["a"]}\n```')
    assert.deepEqual(p.operations, [])
  })
  it('returns null when there is no proposal', () => {
    assert.equal(extractNotebookProposal('just a normal chat answer, no json here'), null)
    assert.equal(extractNotebookProposal(''), null)
    assert.equal(extractNotebookProposal(null), null)
  })
})

describe('looksLikeTruncatedProposal (model ran out of context mid-proposal)', () => {
  const CUT = 'Here you go:\n```json\n{"schema":"btf-viewer-nb-proposal/1",'
    + '"summary":"針對 Low[266] 的 64.224 ms Off-CPU 峰值",'
    + '"notes":["有 873 次阻塞但缺乏具體時間點","需查詢 sync 與 priority_inheritance",'
    + '"需確認 Low[266] 最長阻塞是否與 PS[228] 共用同一 mut'
  it('true for an unbalanced proposal JSON block', () => {
    assert.equal(looksLikeTruncatedProposal(CUT), true)
  })
  it('false for a complete proposal, a balanced-but-malformed one, and plain text', () => {
    assert.equal(looksLikeTruncatedProposal(
      '```json\n{"schema":"btf-viewer-nb-proposal/1","summary":"s","notes":["a"],"operations":[]}\n```'), false)
    assert.equal(looksLikeTruncatedProposal('{"schema":"btf-viewer-nb-proposal/1"}'), false)
    assert.equal(looksLikeTruncatedProposal('a normal prose answer'), false)
    assert.equal(looksLikeTruncatedProposal(''), false)
    assert.equal(looksLikeTruncatedProposal(null), false)
  })
})

describe('summarizeNotebookProposalForChat (readable summary in the AI panel, not raw JSON)', () => {
  const OBJ = '{"schema":"btf-viewer-nb-proposal/1","summary":"Only one measured item so far.","notes":["No hypotheses yet","Conclusion is empty"],"operations":[{"op":"add","role":"observation","title":"Check Mutex Blocking","note":"open section","evidence_ids":["E2"]},{"op":"add","role":"observation","title":"Exec Time Max","note":"jump to max","evidence_ids":["E6"]}]}'

  it('replaces a list-wrapped proposal + btfnext link soup with a summary', () => {
    const reply = [
      '* ```json', '* ' + OBJ, '* ```',
      '* Investigate the current finding [Run](btfnext:text/0)',
      '* Investigate remaining finding [Open Statistics](btfstats:section/block)',
    ].join('\n')
    const s = summarizeNotebookProposalForChat(reply)
    assert.ok(!s.includes('btf-viewer-nb-proposal'), 'raw schema must be gone')
    assert.ok(!s.includes('btfnext:'), 'next-step links must be gone')
    assert.ok(!s.includes('```'), 'json fence must be gone')
    assert.match(s, /\*\*AI proposal for the Investigation Notebook\*\*/)
    assert.match(s, /Only one measured item so far\./)
    assert.match(s, /- No hypotheses yet/)
    assert.match(s, /2 changes proposed/)
  })
  it('review-only proposal (no ops) → "No Notebook changes proposed" line', () => {
    const s = summarizeNotebookProposalForChat('```json\n{"schema":"btf-viewer-nb-proposal/1","summary":"s","notes":["a"]}\n```')
    assert.match(s, /No Notebook changes proposed\./)
    assert.doesNotMatch(s, /open the Investigation Notebook/)
    assert.ok(!s.includes('"schema"'))
  })
  it('no proposal → text returned unchanged', () => {
    assert.equal(summarizeNotebookProposalForChat('just a normal answer'), 'just a normal answer')
    assert.equal(summarizeNotebookProposalForChat(''), '')
  })
})
