import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  accumulateCost,
  applyCloudPrivacy,
  applyExperimentToHypotheses,
  experimentPercentsFromCompare,
  formatPrivacyChip,
  sanitizeAnnotationsText,
  shouldConfirmInterpretedQuery,
  VALIDATE_EXPERIMENT_PROMPT,
  buildInvestigationCase,
  classifyPrivacy,
  dumpUserInvestigationTemplates,
  emptyCostMeter,
  evidenceQualityFromScore,
  extractClaims,
  historicalKnowledgeForFinding,
  inferModelCapability,
  interpretQuestion,
  investigationModePrompt,
  newUserInvestigationTemplate,
  parseUserInvestigationTemplates,
  statusWithCost,
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
    assert.ok(payload.investigation_case.falsify?.supporting?.length)
    const caseObj = buildInvestigationCase(ctx)
    assert.ok(caseObj.falsification.supporting.some(s => String(s).includes('migrations')))
    const md = formatEvidencePanelMarkdown(payload, 'English')
    assert.match(md, /Evidence Quality/)
    assert.match(md, /Historical knowledge/)
    assert.match(md, /btfhyp:supported/)
    assert.match(md, /btfhyp:compare\/all/)
    assert.match(md, /Direct evidence/)
    assert.match(md, /Directly observed/)
    assert.match(md, /Supporting evidence/)
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

  it('matches catalog knowledge and round-trips user templates', () => {
    const hit = historicalKnowledgeForFinding({
      title: 'Excessive bouncing / core thrashing',
      text: 'CS[22] migrates heavily',
    })
    assert.equal(hit.previous_issue, 'Migration thrashing')
    const prompt = investigationModePrompt('diagnose')
    assert.match(prompt, /investigate/)
    assert.match(prompt, /correlate_events/)
    const tpl = newUserInvestigationTemplate('CPU Latency', ['detect_anomalies', 'investigate'])
    const parsed = parseUserInvestigationTemplates(dumpUserInvestigationTemplates([tpl]))
    assert.equal(parsed.length, 1)
    assert.equal(parsed[0].label, 'CPU Latency')
    assert.deepEqual(parsed[0].steps, ['detect_anomalies', 'investigate'])
    const blocked = applyCloudPrivacy('CS[22] stall', 'Why CS[22]?', {
      sensitive: true, endpointIsLocal: false,
    })
    assert.equal(blocked.blocked, true)
    const redacted = applyCloudPrivacy('CS[22] stall', 'Why CS[22]?', {
      endpointIsLocal: false, redactTaskNames: true,
    })
    assert.match(redacted.findings_text, /Task-1/)
    assert.doesNotMatch(redacted.findings_text, /CS\[22\]/)
    const cloudNotes = applyCloudPrivacy('Annotation: secret note\nCS[22] stall', 'Why?', {
      endpointIsLocal: false, redactTaskNames: false,
    })
    assert.match(cloudNotes.findings_text, /\[annotation\]/)
    assert.doesNotMatch(cloudNotes.findings_text, /secret note/)
    assert.equal(shouldConfirmInterpretedQuery('Why is CS[22] slow?'), true)
    assert.equal(shouldConfirmInterpretedQuery(
      'Why?\n\nInterpreted as diagnose. Investigation scope: blocking.',
    ), false)
    assert.equal(experimentPercentsFromCompare({
      checks: [{ id: 'migrations', delta: -72, detail: '-72.0% (threshold 20%)' }],
    }).migrations, -72)
    assert.match(VALIDATE_EXPERIMENT_PROMPT, /Call validate_experiment\. Omit actual/)
    assert.equal(formatPrivacyChip({ level: 'sensitive' }), '🔴 Sensitive')
    assert.match(sanitizeAnnotationsText('note: "leak"'), /\[annotation\]/)
    const hyps = applyExperimentToHypotheses(
      [{ id: 'h1', hypothesis: 'thrash', status: 'possible' }],
      { result: 'DISPROVED' },
    )
    assert.equal(hyps[0].status, 'rejected')
  })

  it('appends accumulated cost to status until the meter is empty', () => {
    assert.equal(statusWithCost('Done.', emptyCostMeter()), 'Done.')
    let meter = accumulateCost(emptyCostMeter(), {
      promptTokens: 1000, completionTokens: 200, toolCalls: 2, modelTimeS: 1.5,
    })
    meter = accumulateCost(meter, { promptTokens: 50, completionTokens: 10 })
    const text = statusWithCost('Done.', meter)
    assert.equal(text, 'Done. · 1.3k tok · 2 tools · 1.5s')
  })
})
