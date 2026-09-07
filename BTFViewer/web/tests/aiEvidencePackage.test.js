import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  EVIDENCE_PACKAGE_SCHEMA,
  RESPONSE_CONTRACT,
  buildEvidencePackage,
  estimateTokens,
  evidencePackageSize,
  formatEvidencePackagePreview,
} from '../src/utils/aiEvidencePackage.js'

const SUMMARY = { span_ns: 1_000_000, tasks: 5, load_balance_score: 82, secret_extra: 9 }
const HEALTH = { status: 'caution', issueCount: 1, metricLimitations: ['Core Migrations'] }
const FINDINGS = [{
  rule_id: 'blocking', severity: 'warning', title: 'Long block',
  entities: ['ControlTask'],
  measured_values: [{ name: 'block', value: 50, unit: 'us' }],
}]
const INV = {
  bookmarks: [{ id: 'o1', type: 'observation', title: 'spike', refs: [] }],
  conclusion: 'starved', unresolved_questions: ['why now?'],
}

function pkg(extra = {}) {
  return buildEvidencePackage({
    question: 'Why does ControlTask miss its deadline?',
    scope: 'C1–C2', analysisRange: { start: 100, end: 200 },
    traceName: 'run.btf', traceSummary: SUMMARY, health: HEALTH,
    findings: FINDINGS, investigation: INV, entities: ['ControlTask', 'IDLE'],
    ...extra,
  })
}

describe('buildEvidencePackage', () => {
  it('has a stable shape + evidence ids', () => {
    const p = pkg()
    assert.equal(p.schema, EVIDENCE_PACKAGE_SCHEMA)
    assert.deepEqual(p.response_contract, RESPONSE_CONTRACT)
    assert.equal(p.findings[0].id, 'F1')
    assert.deepEqual(p.analysis_range, { start: 100, end: 200 })
    assert.equal(p.conclusion_so_far, 'starved')
    assert.equal(p.trace_health.issue_count, 1)
  })

  it('whitelists the trace summary keys', () => {
    const p = pkg()
    assert.ok('load_balance_score' in p.trace.summary)
    assert.ok(!('secret_extra' in p.trace.summary))
  })

  it('redacts structured task names consistently', () => {
    const p = pkg({ redactNames: true })
    assert.equal(p.redacted, true)
    assert.equal(p.trace.name, '(redacted)')
    const alias = p.entities[0]
    assert.match(alias, /^task_/)
    assert.equal(p.findings[0].entities[0], alias)
    const structured = JSON.stringify({ ...p, question: '' })
    assert.ok(!structured.includes('ControlTask'))
  })

  it('sizes + estimates tokens', () => {
    const p = pkg()
    const s = evidencePackageSize(p)
    assert.equal(s.approx_tokens, estimateTokens(p))
    assert.ok(s.bytes > 100)
    assert.equal(s.findings, 1)
  })

  it('preview lists the essentials', () => {
    const txt = formatEvidencePackagePreview(pkg())
    for (const t of ['Question:', 'Range: 100 – 200', 'Trace health: caution', '[F1]', 'tokens']) {
      assert.ok(txt.includes(t), t)
    }
  })

  it('empty inputs are safe', () => {
    const p = buildEvidencePackage({ question: 'q' })
    assert.deepEqual(p.findings, [])
    assert.equal(p.analysis_range, null)
    assert.equal(p.trace_health, null)
  })
})
