import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  buildInvestigationCase,
  classifyPrivacy,
  evidenceQualityFromScore,
  extractClaims,
  inferModelCapability,
  interpretQuestion,
  validateAiResponse,
} from '../src/utils/aiCase.js'
import {
  buildInvestigateContext,
  extractEvidencePanelPayload,
  formatEvidencePanelMarkdown,
} from '../src/utils/aiInvestigation.js'

describe('aiCase investigation lifecycle', () => {
  it('builds a case with quality band and falsify checks', () => {
    const ctx = buildInvestigateContext([
      {
        id: 'f1',
        severity: 'warning',
        title: 'Excessive bouncing / core thrashing',
        text: 'CS[22] migrates heavily',
        evidence: [{ label: 'migrations: burst', time: 1.08 }],
      },
    ], 'f1')
    const payload = extractEvidencePanelPayload('investigate', { ok: true, ...ctx })
    assert.ok(payload.evidence_quality)
    assert.ok(payload.investigation_case)
    const md = formatEvidencePanelMarkdown(payload, 'English')
    assert.match(md, /Evidence Quality/)
  })

  it('flags invented tasks and out-of-window jumps', () => {
    const report = validateAiResponse(
      'Ghost[99] at jump:9.9 stalled CS[22]',
      { tasks: ['CS[22]'], cursor_lo: 1, cursor_hi: 2 },
    )
    assert.equal(report.ok, false)
    assert.ok(report.unverified >= 1)
  })

  it('accepts in-scope claims', () => {
    const report = validateAiResponse(
      'CS[22] migrates at jump:1.5',
      { tasks: ['CS[22]'], cursor_lo: 1, cursor_hi: 2 },
    )
    assert.equal(report.ok, true)
  })

  it('maps score to a qualitative band (not a probability)', () => {
    const q = evidenceQualityFromScore(82, [
      { label: 'Direct evidence times (jump:TIME)', delta: 40 },
    ])
    assert.ok(q.band)
    assert.ok(!String(q.bar).includes('%'))
  })

  it('interprets a latency question as diagnose', () => {
    const q = interpretQuestion('Why did TaskA become slow?')
    assert.equal(q.mode, 'diagnose')
    assert.ok(q.scope.includes('blocking') || q.scope.includes('execution'))
  })

  it('classifies local vs cloud privacy', () => {
    assert.equal(classifyPrivacy({ cloud: false }).level, 'local')
  })

  it('recommends a larger model for 3B-class ids', () => {
    const cap = inferModelCapability('phi4-mini:3.8b')
    assert.ok(cap.recommended)
    assert.match(String(cap.recommended), /7b/i)
  })

  it('extracts jump times and task names', () => {
    const claims = extractClaims('CS[22] at jump:1083 blocking')
    assert.ok(claims.tasks.includes('CS[22]'))
    assert.ok(claims.jumps.includes(1083))
    assert.ok(claims.metrics.includes('blocking'))
  })

  it('scores an offline benchmark dataset', async () => {
    const { readFileSync } = await import('node:fs')
    const { dirname, join } = await import('node:path')
    const { fileURLToPath } = await import('node:url')
    const { runOfflineBenchmark, investigationTemplatePrompt, builtinInvestigationTemplates } = await import('../src/utils/aiCase.js')
    const tpls = builtinInvestigationTemplates()
    assert.match(investigationTemplatePrompt(tpls[0]), /Call these tools/)
    const datasetPath = join(dirname(fileURLToPath(import.meta.url)), '../../tests/ai/dataset.json')
    const dataset = JSON.parse(readFileSync(datasetPath, 'utf8'))
    const result = runOfflineBenchmark(dataset, { failUnder: 50 })
    assert.equal(result.rows.length, 7)
    assert.equal(result.ok, true, result.report)
  })
})
