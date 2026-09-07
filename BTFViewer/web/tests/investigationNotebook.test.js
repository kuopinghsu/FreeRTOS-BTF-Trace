import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  BM_CONCLUSION,
  BM_HYPOTHESIS,
  BM_OBSERVATION,
  BM_SUPPORTING,
  BOOKMARK_TYPES,
  INVESTIGATION_SCHEMA,
  addBookmark,
  addUnresolvedQuestion,
  conclusionEvidenceChains,
  detectBrokenReferences,
  entityBare,
  dumpInvestigation,
  emptyNotebookHistory,
  investigationFromCase,
  scaffoldInvestigationFromFindings,
  linkBookmarks,
  loadInvestigation,
  newInvestigation,
  notebookHistoryState,
  notebookRedo,
  notebookUndo,
  pushNotebookState,
  removeBookmark,
  setConclusion,
  traceIdentity,
  updateBookmark,
} from '../src/utils/investigationNotebook.js'
import { htmlInvestigationSection } from '../src/utils/statsHtmlReport.js'

const fakeTrace = (over = {}) => ({
  segments: [{ start: 0, end: 10, core: 'Core_0' }],
  stiEvents: [],
  tasks: ['Runner', 'CS'],
  coreNames: ['Core_0', 'Core_1'],
  timeScale: 'us',
  timeMin: 0,
  timeMax: 1000,
  ...over,
})

describe('model', () => {
  it('new investigation shape', () => {
    const inv = newInvestigation({ title: 'X', analysisRange: { start: 1, end: 9 } })
    assert.equal(inv.schema, INVESTIGATION_SCHEMA)
    assert.deepEqual(inv.analysis_range, { start: 1, end: 9 })
    assert.deepEqual(inv.bookmarks, [])
  })

  it('addBookmark assigns id + seq, unknown type falls back', () => {
    let inv = addBookmark(newInvestigation(), { type: 'nonsense', title: 't' })
    assert.equal(inv.bookmarks[0].type, BM_OBSERVATION)
    assert.equal(inv.bookmarks[0].seq, 1)
    assert.equal(inv.next_seq, 2)
  })

  it('refs are normalised by kind', () => {
    const inv = addBookmark(newInvestigation(), {
      type: BM_SUPPORTING, title: 'ev', refs: [
        { kind: 'finding', id: 'blocking', label: 'Off-CPU' },
        { kind: 'entity', label: 'CS' },
        { kind: 'range', range: { start: 10, end: 20 } },
        { kind: 'bogus' }, 'notadict',
      ],
    })
    const refs = inv.bookmarks[0].refs
    assert.equal(refs.length, 3)
    assert.equal(refs[0].rule_id, 'blocking')
    assert.equal(refs[1].entity, 'CS')
    assert.deepEqual(refs[2].range, { start: 10, end: 20 })
  })

  it('update + remove drops links, edits return new objects', () => {
    let inv = addBookmark(newInvestigation(), { type: BM_OBSERVATION, title: 'a', bookmarkId: 'a' })
    inv = addBookmark(inv, { type: BM_HYPOTHESIS, title: 'b', bookmarkId: 'b' })
    inv = linkBookmarks(inv, 'a', 'b', 'supports')
    const edited = updateBookmark(inv, 'a', { title: 'a2' })
    assert.equal(inv.bookmarks[0].title, 'a')
    assert.equal(edited.bookmarks[0].title, 'a2')
    inv = removeBookmark(inv, 'b')
    assert.equal(inv.bookmarks.length, 1)
    assert.deepEqual(inv.links, [])
  })

  it('link requires existing distinct bookmarks', () => {
    const inv = addBookmark(newInvestigation(), { type: BM_OBSERVATION, title: 'a', bookmarkId: 'a' })
    assert.deepEqual(linkBookmarks(inv, 'a', 'a').links, [])
    assert.deepEqual(linkBookmarks(inv, 'a', 'ghost').links, [])
  })
})

describe('evidence chains', () => {
  const build = () => {
    let inv = newInvestigation({ title: 'c' })
    inv = addBookmark(inv, { type: BM_OBSERVATION, title: 'obs', bookmarkId: 'obs', refs: [{ kind: 'entity', entity: 'CS' }] })
    inv = addBookmark(inv, { type: BM_SUPPORTING, title: 'sup', bookmarkId: 'sup', refs: [{ kind: 'finding', rule_id: 'blocking' }] })
    inv = addBookmark(inv, { type: BM_HYPOTHESIS, title: 'hyp', bookmarkId: 'hyp' })
    inv = addBookmark(inv, { type: BM_CONCLUSION, title: 'concl', bookmarkId: 'concl' })
    inv = linkBookmarks(inv, 'concl', 'hyp', 'concludes')
    inv = linkBookmarks(inv, 'hyp', 'sup', 'supports')
    return inv
  }

  it('conclusion reaches evidence via links', () => {
    const chains = conclusionEvidenceChains(build())
    assert.equal(chains.length, 1)
    assert.ok(chains[0].grounded)
    assert.deepEqual(new Set(chains[0].evidence.map(e => e.title)), new Set(['hyp', 'sup']))
  })

  it('shared reference also links evidence', () => {
    let inv = newInvestigation()
    inv = addBookmark(inv, { type: BM_SUPPORTING, title: 'sup', bookmarkId: 's', refs: [{ kind: 'entity', entity: 'Runner' }] })
    inv = addBookmark(inv, { type: BM_CONCLUSION, title: 'c', bookmarkId: 'c', refs: [{ kind: 'entity', entity: 'Runner' }] })
    const chains = conclusionEvidenceChains(inv)
    assert.ok(chains[0].grounded)
    assert.equal(chains[0].evidence[0].id, 's')
  })

  it('isolated conclusion is not grounded; result is deterministic', () => {
    const inv = addBookmark(newInvestigation(), { type: BM_CONCLUSION, title: 'lonely' })
    assert.equal(conclusionEvidenceChains(inv)[0].grounded, false)
    assert.deepEqual(conclusionEvidenceChains(build()), conclusionEvidenceChains(build()))
  })
})

describe('broken references', () => {
  it('unknown rule id flagged', () => {
    const inv = addBookmark(newInvestigation(), { type: BM_SUPPORTING, title: 'e', bookmarkId: 'e', refs: [{ kind: 'finding', rule_id: 'gone' }] })
    const res = detectBrokenReferences(inv, { knownRuleIds: ['blocking', 'thrashing'] })
    assert.equal(res.issues.length, 1)
    assert.equal(res.issues[0].bookmark_id, 'e')
  })

  it('entity + range checked against the trace', () => {
    const inv = addBookmark(newInvestigation(), {
      type: BM_OBSERVATION, title: 'o', refs: [
        { kind: 'entity', entity: 'Ghost' },
        { kind: 'range', range: { start: 5, end: 5000 } },
      ],
    })
    const res = detectBrokenReferences(inv, { trace: fakeTrace() })
    const reasons = res.issues.map(i => i.reason)
    assert.ok(reasons.some(r => r.includes('entity')))
    assert.ok(reasons.some(r => r.includes('span')))
  })

  it('stale-trace flag on identity mismatch', () => {
    const t1 = traceIdentity(fakeTrace(), 'a.btf')
    const inv = newInvestigation({ traceIdentity: t1 })
    const t2 = traceIdentity(fakeTrace({ tasks: ['Runner', 'CS', 'Extra'] }), 'a.btf')
    assert.equal(detectBrokenReferences(inv, { currentIdentity: t2 }).stale_trace, true)
    assert.equal(detectBrokenReferences(inv, { currentIdentity: t1 }).stale_trace, false)
  })

  it('clean investigation has no issues', () => {
    const inv = addBookmark(newInvestigation(), {
      type: BM_SUPPORTING, title: 'ok', refs: [
        { kind: 'finding', rule_id: 'blocking' },
        { kind: 'entity', entity: 'CS' },
        { kind: 'range', range: { start: 10, end: 500 } },
      ],
    })
    assert.deepEqual(detectBrokenReferences(inv, { trace: fakeTrace(), knownRuleIds: ['blocking'] }).issues, [])
  })

  it('entity ref resolves across decorated forms (Web↔Desktop, ±Anonymize)', () => {
    // Parser-shaped trace: merge-key task list + a taskRepr Map of decorated
    // raw reprs. Any spelling of an entity ref must still resolve — the cause
    // of "1 stale ref" after a Web→Desktop Anonymize export.
    const trace = {
      tasks: ['\x001\x00Runner', '\x005\x00CS'],
      taskRepr: new Map([
        ['\x001\x00Runner', '[0/0001]Runner'],
        ['\x005\x00CS', '[0/0005]CS'],
      ]),
      coreNames: ['Core_0', 'Core_1'],
      timeMin: 0, timeMax: 1000,
    }
    for (const ent of ['Runner', 'Runner[1]', '[0/0001]Runner', '\x001\x00Runner']) {
      const inv = addBookmark(newInvestigation(), {
        type: BM_OBSERVATION, title: 'o', refs: [{ kind: 'entity', entity: ent }],
      })
      assert.deepEqual(detectBrokenReferences(inv, { trace }).issues, [], ent)
    }
    const gone = addBookmark(newInvestigation(), {
      type: BM_OBSERVATION, title: 'o', refs: [{ kind: 'entity', entity: 'GhostTask' }],
    })
    assert.equal(detectBrokenReferences(gone, { trace }).issues.length, 1)
  })

  it('entityBare strips every decoration', () => {
    assert.equal(entityBare('[0/1]Worker'), 'Worker')
    assert.equal(entityBare('Worker[8]'), 'Worker')
    assert.equal(entityBare('Worker(0x9)'), 'Worker')
    assert.equal(entityBare('\x001\x00Worker'), 'Worker')
    assert.equal(entityBare('Task-1'), 'Task-1')
  })
})

describe('undo / redo', () => {
  it('push / undo / redo', () => {
    const inv = newInvestigation()
    let h = pushNotebookState(emptyNotebookHistory(), inv)
    h = pushNotebookState(h, setConclusion(inv, 'one'))
    h = pushNotebookState(h, addBookmark(inv, { type: BM_OBSERVATION, title: 'o' }))
    let st = notebookHistoryState(h)
    assert.equal(st.count, 3)
    assert.ok(st.can_undo && !st.can_redo)
    h = notebookUndo(h)
    st = notebookHistoryState(h)
    assert.equal(st.current.conclusion, 'one')
    assert.ok(st.can_redo)
    h = notebookUndo(h)
    assert.equal(notebookHistoryState(h).can_undo, false)
    h = notebookRedo(h)
    assert.equal(notebookHistoryState(h).current.conclusion, 'one')
  })

  it('push after undo truncates the redo branch', () => {
    const inv = newInvestigation()
    let h = pushNotebookState(emptyNotebookHistory(), inv)
    h = pushNotebookState(h, setConclusion(inv, 'a'))
    h = pushNotebookState(h, setConclusion(inv, 'b'))
    h = notebookUndo(h)
    h = pushNotebookState(h, setConclusion(inv, 'c'))
    const st = notebookHistoryState(h)
    assert.equal(st.count, 3)
    assert.equal(st.can_redo, false)
    assert.equal(st.current.conclusion, 'c')
  })

  it('identical state is not pushed twice', () => {
    const inv = addBookmark(newInvestigation(), { type: BM_OBSERVATION, title: 'o' })
    let h = pushNotebookState(emptyNotebookHistory(), inv)
    h = pushNotebookState(h, loadInvestigation(dumpInvestigation(inv)))
    assert.equal(notebookHistoryState(h).count, 1)
  })
})

describe('serialisation', () => {
  const rich = () => {
    let inv = newInvestigation({ title: 'T', analysisRange: { start: 0, end: 100 } })
    inv = addBookmark(inv, { type: BM_OBSERVATION, title: 'o', bookmarkId: 'o', refs: [{ kind: 'range', range: { start: 1, end: 9 } }] })
    inv = addBookmark(inv, { type: BM_CONCLUSION, title: 'c', bookmarkId: 'c' })
    inv = linkBookmarks(inv, 'c', 'o', 'concludes')
    inv = setConclusion(inv, 'final')
    inv = addUnresolvedQuestion(inv, 'why?')
    return inv
  }

  it('round trip is stable', () => {
    const once = dumpInvestigation(rich())
    assert.equal(dumpInvestigation(loadInvestigation(once)), once)
  })

  it('load repairs bad input', () => {
    const loaded = loadInvestigation({
      bookmarks: [
        { type: 'weird', title: 'a' },
        'notadict',
        { title: 'b', type: 'hypothesis', id: 'dup' },
        { title: 'c', type: 'hypothesis', id: 'dup' },
      ],
      links: [{ from: 'dup', to: 'missing', relation: 'x' }],
      unresolved_questions: ['  ', 'keep'],
    })
    assert.equal(loaded.bookmarks[0].type, 'observation')
    const ids = loaded.bookmarks.map(b => b.id)
    assert.equal(ids.length, new Set(ids).size)
    assert.deepEqual(loaded.links, [])
    assert.deepEqual(loaded.unresolved_questions, ['keep'])
    assert.equal(loaded.schema, INVESTIGATION_SCHEMA)
  })

  it('preserves unknown keys and loads from text', () => {
    assert.deepEqual(loadInvestigation({ title: 'x', _future: { k: 1 } })._future, { k: 1 })
    assert.equal(loadInvestigation(dumpInvestigation(rich())).title, 'T')
  })
})

describe('case bridge', () => {
  it('case findings become supporting bookmarks with stable refs', () => {
    const findings = [
      { id: 'blocking', rule_id: 'blocking', severity: 'warning', title: 'Off-CPU spikes', observation: 'CS off-CPU 3ms', entities: ['CS'], affected_range: { start: 10, end: 90 }, inspect: 'Off-CPU Time (Blocking Time)' },
      { id: 'thrashing', rule_id: 'thrashing', severity: 'warning', title: 'Excessive core migration', entities: ['Worker'] },
    ]
    const inv = investigationFromCase({ caseFindingIds: ['blocking'], findings, analysisRange: { start: 0, end: 100 }, title: 'Case A' })
    assert.equal(inv.bookmarks.length, 1)
    assert.equal(inv.bookmarks[0].type, BM_SUPPORTING)
    assert.deepEqual(new Set(inv.bookmarks[0].refs.map(r => r.kind)), new Set(['finding', 'entity', 'range', 'metric']))
  })

  it('missing case id is skipped', () => {
    assert.deepEqual(investigationFromCase({ caseFindingIds: ['ghost'], findings: [] }).bookmarks, [])
  })
})

describe('scaffold from findings', () => {
  const FINDINGS = [
    { id: 'top_cpu', rule_id: 'top_cpu', severity: 'warning', title: 'High CPU on Med', text: 'Med 17%', entities: ['Med'], affected_range: { start: 10, end: 99 }, inspect: 'Top Tasks by CPU' },
    { id: 'wcet', rule_id: 'wcet', severity: 'error', title: 'WCET outlier', entities: ['Runner'], inspect: 'Execution Time' },
    { id: 'none', rule_id: 'none', severity: 'info', title: 'No findings under the current rules' },
  ]

  it('seeds observations (error first) + hypothesis + verification when empty', () => {
    const inv = scaffoldInvestigationFromFindings(newInvestigation({ title: 'T' }), {
      findings: FINDINGS, cursorRange: { start: 5, end: 50 },
    })
    assert.deepEqual(inv.bookmarks.map(b => b.type),
      ['observation', 'observation', 'hypothesis', 'verification'])
    assert.equal(inv.bookmarks[0].title, 'WCET outlier')
    assert.deepEqual(new Set(inv.bookmarks[0].refs.map(r => r.kind)),
      new Set(['finding', 'entity', 'range', 'metric']))
  })

  it('is idempotent and adds no extra stubs on re-run', () => {
    const a = scaffoldInvestigationFromFindings(newInvestigation(), { findings: FINDINGS })
    const b = scaffoldInvestigationFromFindings(a, { findings: FINDINGS })
    assert.equal(b.bookmarks.length, a.bookmarks.length)
  })

  it('honours includeInfo + limit', () => {
    const inv = scaffoldInvestigationFromFindings(newInvestigation(), {
      findings: FINDINGS, includeInfo: true, limit: 1,
    })
    assert.equal(inv.bookmarks.filter(b => b.type === 'observation').length, 1)
  })
})

describe('html section', () => {
  const build = () => {
    let inv = newInvestigation({ title: 'Runner stall', analysisRange: { start: 0, end: 1000 } })
    inv = addBookmark(inv, { type: BM_OBSERVATION, title: 'Runner misses period', bookmarkId: 'obs', note: 'at 500us', refs: [{ kind: 'range', range: { start: 400, end: 600 } }] })
    inv = addBookmark(inv, { type: BM_HYPOTHESIS, title: 'Mutex held too long', bookmarkId: 'hyp' })
    inv = addBookmark(inv, { type: BM_SUPPORTING, title: 'CS holds 300us', bookmarkId: 'sup', refs: [{ kind: 'finding', rule_id: 'blocking' }] })
    inv = addBookmark(inv, { type: BM_CONCLUSION, title: 'Priority inversion', bookmarkId: 'con' })
    inv = linkBookmarks(inv, 'con', 'hyp', 'concludes')
    inv = linkBookmarks(inv, 'hyp', 'sup', 'supports')
    inv = addUnresolvedQuestion(inv, 'Why so long?')
    return inv
  }

  it('groups + chain + single outer section', () => {
    const inv = build()
    const html = htmlInvestigationSection(inv, {
      formatNs: ns => `${ns}us`, chains: conclusionEvidenceChains(inv), scopeTitle: ' (C1–C2)',
    })
    assert.match(html, /<h2>Investigation \(C1–C2\)<\/h2>/)
    for (const label of ['Facts', 'Hypotheses', 'Conclusions', 'Unresolved questions']) {
      assert.ok(html.includes(`${label}</h3>`), label)
    }
    assert.match(html, /Backed by:/)
    assert.match(html, /CS holds 300us/)
    assert.equal((html.match(/<section/g) || []).length, 1)
    assert.equal((html.match(/<\/section>/g) || []).length, 1)
  })

  it('shows stale references', () => {
    const html = htmlInvestigationSection(build(), {
      brokenRefs: { stale_trace: true, issues: [{ bookmark_id: 'obs', ref_index: 0, kind: 'range', reason: 'time range falls outside the trace span' }] },
    })
    assert.match(html, /Stale:/)
    assert.match(html, /source trace changed/)
  })

  it('empty investigation renders nothing', () => {
    assert.equal(htmlInvestigationSection(newInvestigation()), '')
    assert.equal(htmlInvestigationSection(null), '')
  })
})

describe('parity', () => {
  it('bookmark types exported', () => {
    assert.deepEqual(BOOKMARK_TYPES, [
      'observation', 'hypothesis', 'supporting', 'contradicting', 'verification', 'conclusion',
    ])
  })
})
