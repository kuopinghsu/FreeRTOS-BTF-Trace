import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  INVESTIGATION_SCHEMA,
  NB_SECTION_ORDER,
  NB_STATUS_CLOSED,
  NB_STATUS_NEEDS_EVIDENCE,
  NB_STATUS_OPEN,
  NB_STATUS_READY,
  NOTEBOOK_STATUSES,
  addBookmark,
  addUnresolvedQuestion,
  deriveStatus,
  dumpInvestigation,
  investigationHeader,
  investigationSections,
  linkBookmarks,
  loadInvestigation,
  newInvestigation,
  setConclusion,
  setStatus,
} from '../src/utils/investigationNotebook.js'

function legacyV1(extra = {}) {
  return {
    schema: 'btf-viewer-investigation/1',
    title: 'Why does CS[28] miss its deadline?',
    trace_identity: { file: 'run.btf', time_scale: 'ns' },
    analysis_range: { start: 100, end: 900 },
    bookmarks: [
      { id: 'h1', type: 'hypothesis', title: 'Core thrash', seq: 1 },
      { id: 's1', type: 'supporting', title: '120 migrations', seq: 2, refs: [{ kind: 'metric', metric: 'migrations' }] },
      { id: 'o1', type: 'observation', title: 'note', seq: 3 },
      { id: 'v1', type: 'verification', title: 'pin CS[28]', seq: 4 },
    ],
    links: [{ from: 's1', to: 'h1', relation: 'supports' }],
    conclusion: '',
    unresolved_questions: ['Is the affinity mask correct?'],
    ...extra,
  }
}

describe('notebook schema/2 migration', () => {
  it('schema is v2', () => {
    assert.equal(INVESTIGATION_SCHEMA, 'btf-viewer-investigation/2')
    assert.equal(newInvestigation().schema, INVESTIGATION_SCHEMA)
  })

  it('v1 payload upgrades without losing anything', () => {
    const loaded = loadInvestigation(legacyV1())
    assert.equal(loaded.schema, INVESTIGATION_SCHEMA)
    assert.deepEqual(loaded.bookmarks.map(b => b.id), ['h1', 's1', 'o1', 'v1'])
    assert.deepEqual(loaded.links, [{ from: 's1', to: 'h1', relation: 'supports' }])
    assert.deepEqual(loaded.unresolved_questions, ['Is the affinity mask correct?'])
    assert.ok(NOTEBOOK_STATUSES.includes(loaded.status))
  })

  it('stored status is preserved over derivation', () => {
    assert.equal(loadInvestigation(legacyV1({ status: 'closed' })).status, NB_STATUS_CLOSED)
  })

  it('round trip stays stable', () => {
    const once = dumpInvestigation(loadInvestigation(legacyV1()))
    const twice = dumpInvestigation(loadInvestigation(once))
    assert.equal(once, twice)
  })

  it('transient workflow_stage is not promoted', () => {
    const loaded = loadInvestigation(legacyV1({ workflow_stage: 'triage' }))
    assert.equal(loaded.workflow_stage, 'triage')
    assert.notEqual(loaded.status, 'triage')
  })
})

describe('deriveStatus', () => {
  it('blank is open', () => {
    assert.equal(deriveStatus(newInvestigation()), NB_STATUS_OPEN)
  })
  it('hypothesis without evidence needs evidence', () => {
    assert.equal(deriveStatus(addBookmark(newInvestigation(), { type: 'hypothesis', title: 'h' })), NB_STATUS_NEEDS_EVIDENCE)
  })
  it('open questions need evidence', () => {
    assert.equal(deriveStatus(addUnresolvedQuestion(newInvestigation(), 'why?')), NB_STATUS_NEEDS_EVIDENCE)
  })
  it('conclusion is ready, not closed', () => {
    assert.equal(deriveStatus(setConclusion(newInvestigation(), 'Confirmed')), NB_STATUS_READY)
  })
  it('never returns closed', () => {
    let inv = setConclusion(newInvestigation(), 'done')
    inv = addUnresolvedQuestion(inv, 'q')
    assert.notEqual(deriveStatus(inv), NB_STATUS_CLOSED)
  })
  it('setStatus validates', () => {
    let inv = setStatus(newInvestigation(), 'bogus')
    assert.equal(inv.status, NB_STATUS_OPEN)
    inv = setStatus(inv, 'closed', { updatedAt: '2026-09-08T00:00:00' })
    assert.equal(inv.status, NB_STATUS_CLOSED)
    assert.equal(inv.updated_at, '2026-09-08T00:00:00')
  })
})

describe('six-section projection', () => {
  it('six sections in order', () => {
    const secs = investigationSections(legacyV1())
    assert.deepEqual(secs.map(s => s.id), NB_SECTION_ORDER)
    assert.deepEqual(secs.map(s => s.title),
      ['Question', 'Scope', 'Hypotheses', 'Evidence', 'Open checks', 'Conclusion'])
  })

  it('bookmarks land in the right sections', () => {
    const secs = Object.fromEntries(investigationSections(legacyV1()).map(s => [s.id, s]))
    assert.equal(secs.question.items[0].text, 'Why does CS[28] miss its deadline?')
    assert.deepEqual(secs.hypotheses.items.map(i => i.bookmark_id), ['h1'])
    assert.equal(secs.hypotheses.items[0].status, 'supported')
    assert.deepEqual(secs.evidence.items.map(i => i.bookmark_id).sort(), ['o1', 's1'])
    assert.equal(secs.evidence.items.find(i => i.bookmark_id === 's1').kind, 'measured')
    assert.equal(secs.evidence.items.find(i => i.bookmark_id === 'o1').kind, '')
    assert.equal(secs.evidence.items.find(i => i.bookmark_id === 's1').card.source, 'Statistics')
    assert.equal(secs.evidence.items.find(i => i.bookmark_id === 'o1').card.source, 'User note')
    const openTexts = secs.open_checks.items.map(i => i.text)
    assert.ok(openTexts.includes('Is the affinity mask correct?'))
    assert.ok(openTexts.includes('pin CS[28]'))
  })

  it('contradicting link marks hypothesis', () => {
    let inv = newInvestigation()
    inv = addBookmark(inv, { type: 'hypothesis', title: 'h', bookmarkId: 'h' })
    inv = addBookmark(inv, { type: 'contradicting', title: 'counter', bookmarkId: 'c' })
    inv = linkBookmarks(inv, 'c', 'h', 'contradicts')
    const secs = Object.fromEntries(investigationSections(inv).map(s => [s.id, s]))
    assert.equal(secs.hypotheses.items[0].status, 'contradicted')
  })
})

describe('compact header', () => {
  it('counts sections', () => {
    const hdr = investigationHeader(legacyV1())
    assert.equal(hdr.trace, 'run.btf')
    assert.equal(hdr.scope, '100–900')
    assert.equal(hdr.hypothesis_count, 1)
    assert.equal(hdr.evidence_count, 2)
    assert.equal(hdr.open_check_count, 2)
    assert.equal(hdr.stale_ref_count, 0)
    assert.equal(hdr.status_label, 'Needs evidence')
  })

  it('takes a detectBrokenReferences result', () => {
    const hdr = investigationHeader(legacyV1(), { broken: { issues: [{ bookmark_id: 's1' }, { bookmark_id: 'x' }] } })
    assert.equal(hdr.stale_ref_count, 2)
  })
})
