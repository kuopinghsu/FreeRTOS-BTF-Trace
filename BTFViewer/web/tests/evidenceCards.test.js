import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  EV_AUTHOR_AI,
  EV_AUTHOR_USER,
  EV_KIND_MEASURED,
  EV_SOURCE_AI,
  EV_SOURCE_STATISTICS,
  EV_SOURCE_USER,
  addEvidence,
  applyEvidenceEdit,
  detectBrokenReferences,
  dumpInvestigation,
  evidenceNavTargets,
  guardEvidenceChanges,
  investigationSections,
  loadInvestigation,
  newInvestigation,
  normalizeEvidenceCard,
  updateEvidenceExplanation,
} from '../src/utils/investigationNotebook.js'

function measuredInv() {
  let inv = newInvestigation({ title: 'Q', traceIdentity: { hash: 'abc', file: 'run.btf' } })
  inv = addEvidence(inv, {
    title: '120 migrations', role: 'supporting', source: EV_SOURCE_STATISTICS,
    kind: EV_KIND_MEASURED, author: 'btfviewer', value: 120, unit: 'migrations', task: 'CS[28]',
    refs: [{ kind: 'metric', metric: 'migrations' }, { kind: 'range', range: { start: 100, end: 900 } }],
    bookmarkId: 'e1', createdAt: '2026-09-08T00:00:00',
  })
  return inv
}

describe('evidence card provenance', () => {
  it('AI-authored card is never measured', () => {
    const c = normalizeEvidenceCard(
      { source: EV_SOURCE_AI, kind: 'measured', author: 'user' },
      { refs: [{ kind: 'metric', metric: 'x' }] },
    )
    assert.equal(c.author, EV_AUTHOR_AI)
    assert.notEqual(c.kind, EV_KIND_MEASURED)
  })

  it('measured needs a measured ref', () => {
    const c = normalizeEvidenceCard(
      { source: EV_SOURCE_STATISTICS, kind: 'measured', author: 'user' },
      { refs: [{ kind: 'entity', entity: 'CS[28]' }] },
    )
    assert.notEqual(c.kind, EV_KIND_MEASURED)
  })

  it('user note has no kind', () => {
    const c = normalizeEvidenceCard({ source: EV_SOURCE_USER, author: 'user' }, { refs: [] })
    assert.equal(c.kind, '')
    assert.equal(c.source, EV_SOURCE_USER)
  })
})

describe('protected fields', () => {
  it('rejects protected fields on a measured card', () => {
    const { allowed, rejected } = guardEvidenceChanges(
      { kind: EV_KIND_MEASURED, value: 120, unit: 'migrations' },
      { value: 999, unit: 'x', hypothesis_id: 'h1', note: 't' },
    )
    assert.deepEqual(rejected.sort(), ['unit', 'value'])
    assert.deepEqual(Object.keys(allowed).sort(), ['hypothesis_id', 'note'])
  })

  it('apply edit keeps measured values exactly', () => {
    const { inv, rejected } = applyEvidenceEdit(measuredInv(), 'e1', {
      value: 0, unit: 'bogus', note: 'my read of it',
    })
    const b = inv.bookmarks.find(x => x.id === 'e1')
    assert.equal(b.evidence.value, 120)
    assert.equal(b.evidence.unit, 'migrations')
    assert.equal(b.note, 'my read of it')
    assert.deepEqual(rejected.sort(), ['unit', 'value'])
  })

  it('update explanation touches only note', () => {
    const inv = updateEvidenceExplanation(measuredInv(), 'e1', 'explanation')
    const b = inv.bookmarks.find(x => x.id === 'e1')
    assert.equal(b.note, 'explanation')
    assert.equal(b.evidence.value, 120)
  })

  it('cannot promote a note to measured', () => {
    const { allowed, rejected } = guardEvidenceChanges({ kind: '' }, { kind: 'measured' })
    assert.ok(rejected.includes('kind'))
    assert.deepEqual(allowed, {})
  })
})

describe('stale + nav + reload', () => {
  it('stale evidence stays visible', () => {
    const inv = measuredInv()
    const broken = detectBrokenReferences(inv, { currentIdentity: { hash: 'DIFFERENT' } })
    const secs = Object.fromEntries(investigationSections(inv, { broken }).map(s => [s.id, s]))
    assert.equal(secs.evidence.items.length, 1)
    assert.equal(secs.evidence.items[0].stale, true)
  })

  it('nav targets resolve from refs', () => {
    const nav = evidenceNavTargets({ refs: [
      { kind: 'metric', metric: 'migrations' },
      { kind: 'range', range: { start: 10, end: 20 } },
      { kind: 'evidence', time: 1500 },
    ] })
    assert.equal(nav.stats_metric, 'migrations')
    assert.deepEqual(nav.range, [10, 20])
    assert.equal(nav.jump, 1500)
  })

  it('measured fields survive export/reload', () => {
    const once = dumpInvestigation(measuredInv())
    assert.equal(dumpInvestigation(loadInvestigation(once)), once)
    assert.equal(loadInvestigation(once).bookmarks[0].evidence.value, 120)
  })
})

describe('legacy migration', () => {
  it('v1 evidence bookmarks gain a provenance card', () => {
    const loaded = loadInvestigation({
      schema: 'btf-viewer-investigation/1',
      trace_identity: { hash: 'h1' },
      bookmarks: [
        { id: 'o', type: 'observation', title: 'bare note' },
        { id: 's', type: 'supporting', title: 'measured', refs: [{ kind: 'finding', rule_id: 'thrash' }] },
        { id: 'h', type: 'hypothesis', title: 'a guess' },
      ],
    })
    const byId = Object.fromEntries(loaded.bookmarks.map(b => [b.id, b]))
    assert.equal(byId.o.evidence.source, EV_SOURCE_USER)
    assert.equal(byId.o.evidence.kind, '')
    assert.equal(byId.s.evidence.kind, EV_KIND_MEASURED)
    assert.equal(byId.s.evidence.author, EV_AUTHOR_USER)
    assert.ok(!('evidence' in byId.h))
  })
})
