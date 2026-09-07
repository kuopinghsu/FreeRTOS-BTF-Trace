import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  FINDING_STATUS_BOOKMARKED,
  FINDING_STATUS_DISMISSED,
  FINDING_STATUS_NEW,
  FINDING_STATUS_REVIEWED,
  NO_FINDINGS_UNDER_RULES,
  RULE_CATALOG,
  RULE_IDS,
  buildInvestigationFindings,
  dedupeInvestigationFindings,
  investigationFindingExport,
  normalizeInvestigationFinding,
  parseMeasuredValues,
  rankInvestigationFindings,
  ruleSpec,
} from '../src/utils/investigationFindings.js'
import { buildWorkflowAnalysisFindings } from '../src/utils/workflowAnalysis.js'

const raw = (o = {}) => ({ severity: 'warning', title: 'T', text: 'body', id: '', evidence: [], ...o })
const n = (o) => normalizeInvestigationFinding(raw(o))

describe('model normalisation', () => {
  it('derives rule_id from id and folds a slug suffix', () => {
    assert.equal(n({ id: 'thrashing' }).rule_id, 'thrashing')
    const f = normalizeInvestigationFinding(raw({ id: 'thrashing-2' }))
    assert.equal(f.rule_id, 'thrashing')
    assert.equal(f.id, 'thrashing-2')
  })

  it('lets an explicit rule_id win', () => {
    assert.equal(n({ id: 'x9', rule_id: 'tick_health' }).rule_id, 'tick_health')
  })

  it('fills comparison_basis from the catalog but keeps an explicit one', () => {
    assert.equal(n({ id: 'load_imbalance' }).comparison_basis,
      RULE_CATALOG.load_imbalance.comparison_basis)
    assert.equal(n({ id: 'load_imbalance', comparison_basis: 'custom' }).comparison_basis, 'custom')
  })

  it('passes through structured measured_values and falls back to parsing', () => {
    const s = n({ id: 'tick_health', measured_values: [{ name: 'CV', value: 12.5, unit: '%', sample_count: 40 }] })
    assert.equal(s.measured_values[0].sample_count, 40)
    const p = n({ id: 'load_imbalance', evidence_text: 'Load Balance Score 62% (σ=24.0%, G=0.31)' })
    const names = new Set(p.measured_values.map(m => m.name))
    assert.ok(names.has('Score'))
    assert.ok(names.has('σ'))
  })

  it('parses measured values conservatively', () => {
    assert.deepEqual(parseMeasuredValues('564 migrations'), [])
    assert.deepEqual(parseMeasuredValues('Worker (Max 10us), n=3'), [
      { name: 'Max', value: 10, unit: 'µs' },
      { name: 'n', value: 3, unit: '' },
    ])
  })

  it('resolves entities from task then scraped cores', () => {
    assert.deepEqual(n({ task: 'Worker' }).entities, ['Worker'])
    assert.deepEqual(n({ text: 'Core_0→Core_1 hot pair' }).entities, ['Core_0', 'Core_1'])
  })

  it('derives affected_range from evidence times unless explicit', () => {
    assert.deepEqual(
      n({ evidence: [{ label: 'a', time: 500 }, { label: 'b', time: 100 }] }).affected_range,
      { start: 100, end: 500 })
    assert.deepEqual(
      n({ affected_range: { start: 1, end: 9 }, evidence: [{ label: 'a', time: 500 }] }).affected_range,
      { start: 1, end: 9 })
  })

  it('maps triage state to status', () => {
    const state = { reviewed: ['a'], case: ['b'], dismissed: { c: 'noise' } }
    assert.equal(normalizeInvestigationFinding(raw({ id: 'a' }), { triageState: state }).status, FINDING_STATUS_REVIEWED)
    assert.equal(normalizeInvestigationFinding(raw({ id: 'b' }), { triageState: state }).status, FINDING_STATUS_BOOKMARKED)
    assert.equal(normalizeInvestigationFinding(raw({ id: 'c' }), { triageState: state }).status, FINDING_STATUS_DISMISSED)
    assert.equal(normalizeInvestigationFinding(raw({ id: 'd' }), { triageState: state }).status, FINDING_STATUS_NEW)
  })

  it('adds a limitation for low/medium confidence only', () => {
    assert.ok(n({ confidence: 'Medium — heuristic threshold' }).limitations.length)
    assert.deepEqual(n({ confidence: 'High — measured CPU share' }).limitations, [])
  })

  it('preserves original fields', () => {
    const f = n({ id: 'tick_health', inspect: 'Trace Health (TICK)' })
    assert.equal(f.inspect, 'Trace Health (TICK)')
    assert.equal(f.title, 'T')
  })

  it('catalogs every engine rule id', () => {
    const engine = ['load_imbalance', 'load_balance_ok', 'load_balance_moderate', 'top_cpu',
      'exec_max', 'blocking', 'priority_inversion', 'thrashing', 'hot_pairs', 'deadlines',
      'tick_health', 'missed_ticks', 'sync_bounce', 'sync_issues', 'migration_burst_anomaly',
      'wcet_anomaly', 'none']
    for (const id of engine) assert.ok(RULE_IDS.includes(id), id)
  })

  it('ruleSpec lookup', () => {
    assert.equal(ruleSpec('nope'), null)
    assert.equal(ruleSpec('deadlines').severity, 'error')
  })
})

describe('deduplication', () => {
  it('merges same rule + entity + overlapping range', () => {
    const a = n({ id: 'thrashing', task: 'CS', affected_range: { start: 0, end: 100 }, evidence: [{ label: 'x', time: 10 }] })
    const b = n({ id: 'thrashing', task: 'CS', affected_range: { start: 50, end: 200 }, evidence: [{ label: 'y', time: 120 }] })
    const out = dedupeInvestigationFindings([a, b])
    assert.equal(out.length, 1)
    assert.deepEqual(out[0].affected_range, { start: 0, end: 200 })
    assert.equal(out[0].merged_count, 2)
    assert.equal(out[0].evidence_refs.length, 2)
  })

  it('keeps disjoint ranges separate but merges touching ones', () => {
    const mk = (s, e) => n({ id: 'thrashing', task: 'CS', affected_range: { start: s, end: e } })
    assert.equal(dedupeInvestigationFindings([mk(0, 100), mk(101, 200)]).length, 2)
    assert.equal(dedupeInvestigationFindings([mk(0, 100), mk(100, 200)]).length, 1)
  })

  it('does not merge across entities or rules', () => {
    const a = n({ id: 'thrashing', task: 'CS', affected_range: { start: 0, end: 100 } })
    assert.equal(dedupeInvestigationFindings([a, n({ id: 'thrashing', task: 'Worker', affected_range: { start: 0, end: 100 } })]).length, 2)
    assert.equal(dedupeInvestigationFindings([a, n({ id: 'hot_pairs', task: 'CS', affected_range: { start: 0, end: 100 } })]).length, 2)
  })

  it('keeps the higher-severity survivor', () => {
    const a = n({ id: 'tick_health', severity: 'warning', task: 'C', affected_range: { start: 0, end: 10 } })
    const b = n({ id: 'tick_health', severity: 'error', task: 'C', affected_range: { start: 0, end: 10 } })
    assert.equal(dedupeInvestigationFindings([a, b])[0].severity, 'error')
  })

  it('is deterministic regardless of input order', () => {
    const items = [
      n({ id: 'thrashing', task: 'CS', affected_range: { start: 0, end: 100 } }),
      n({ id: 'thrashing', task: 'CS', affected_range: { start: 40, end: 90 } }),
      n({ id: 'hot_pairs', task: 'CS' }),
    ]
    assert.deepEqual(dedupeInvestigationFindings(items), dedupeInvestigationFindings([...items].reverse()))
  })
})

describe('ranking', () => {
  it('severity dominates', () => {
    const out = rankInvestigationFindings([
      n({ id: 'top_cpu', severity: 'info' }),
      n({ id: 'deadlines', severity: 'error' }),
      n({ id: 'thrashing', severity: 'warning' }),
    ])
    assert.deepEqual(out.map(f => f.severity), ['error', 'warning', 'info'])
  })

  it('duration breaks ties within a severity', () => {
    const short = n({ id: 'thrashing', severity: 'warning', affected_range: { start: 0, end: 1000 } })
    const long = n({ id: 'hot_pairs', severity: 'warning', affected_range: { start: 0, end: 300000 } })
    const out = rankInvestigationFindings([short, long], { totalSpanNs: 1000000 })
    assert.equal(out[0].id, 'hot_pairs')
  })

  it('evidence quality breaks ties', () => {
    const timed = n({ id: 'thrashing', severity: 'warning', evidence: [{ label: 'a', time: 5 }] })
    const untimed = n({ id: 'hot_pairs', severity: 'warning', evidence: [] })
    assert.equal(rankInvestigationFindings([untimed, timed])[0].id, 'thrashing')
  })

  it('is stable on a full tie', () => {
    const out = rankInvestigationFindings([n({ id: 'bbb', severity: 'info' }), n({ id: 'aaa', severity: 'info' })])
    assert.deepEqual(out.map(f => f.id), ['aaa', 'bbb'])
  })

  it('a barely-exceeded threshold still outranks a same-severity info', () => {
    const warn = n({ id: 'load_imbalance', severity: 'warning', measured_values: [{ name: 'σ', value: 30.3, unit: '%', threshold: 30.0 }] })
    const info = n({ id: 'top_cpu', severity: 'info' })
    assert.equal(rankInvestigationFindings([info, warn])[0].id, 'load_imbalance')
  })
})

describe('pipeline + export + empty state', () => {
  it('normalises, dedupes and ranks', () => {
    const out = buildInvestigationFindings([
      raw({ id: 'thrashing', severity: 'warning', task: 'CS', affected_range: { start: 0, end: 100 } }),
      raw({ id: 'thrashing', severity: 'error', task: 'CS', affected_range: { start: 50, end: 150 } }),
      raw({ id: 'top_cpu', severity: 'info', task: 'Worker' }),
    ], { totalSpanNs: 1000 })
    assert.equal(out.length, 2)
    assert.equal(out[0].rule_id, 'thrashing')
    assert.equal(out[0].severity, 'error')
    assert.ok(out[0].rank_score > out[1].rank_score)
  })

  it('can skip dedupe', () => {
    const r = [
      raw({ id: 'thrashing', task: 'CS', affected_range: { start: 0, end: 100 } }),
      raw({ id: 'thrashing', task: 'CS', affected_range: { start: 0, end: 100 } }),
    ]
    assert.equal(buildInvestigationFindings(r, { dedupe: false }).length, 2)
  })

  it('export drops display text and keeps the structured fields', () => {
    const f = buildInvestigationFindings([raw({ id: 'tick_health', severity: 'error' })])[0]
    const e = investigationFindingExport(f)
    for (const k of ['id', 'rule_id', 'severity', 'status', 'observation', 'category',
      'comparison_basis', 'affected_range', 'entities', 'measured_values', 'evidence_refs',
      'limitations', 'rank_score']) {
      assert.ok(k in e, k)
    }
    assert.ok(!('evidence_text' in e))
  })

  it('empty-state wording', () => {
    assert.equal(NO_FINDINGS_UNDER_RULES, 'No findings under the current rules')
    const out = buildWorkflowAnalysisFindings({
      coreRows: [], execRows: [], blockRows: [], migRows: [], pairRows: [],
      priorityRows: [], syncRows: [], syncIssues: [], tick: { tickCount: 0 },
    })
    const titles = out.map(f => f.title)
    assert.ok(titles.includes(NO_FINDINGS_UNDER_RULES))
    assert.ok(!titles.includes('No analysis heuristics flagged'))
  })
})
