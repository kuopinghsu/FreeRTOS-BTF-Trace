import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  buildInvestigationPackage,
  classifyRegression,
  explainRegression,
  isAgentTemplate,
  recommendValidationExperiments,
  scoreAgainstBaseline,
  updateBaselineProfile,
} from '../src/utils/aiInvestigation.js'
import {
  AI_TOOL_BASELINE_SCORE,
  AI_TOOL_EXPORT_INVESTIGATION,
  AI_TOOL_RECOMMEND_EXPERIMENTS,
  AI_VIEWER_TOOL_NAMES,
  baselineScoreFinding,
  isExportTool,
  isQueryTool,
  recommendExperimentsFinding,
} from '../src/utils/aiTools.js'
import { AI_TEMPLATE_QUESTIONS } from '../src/utils/aiClient.js'

describe('Historical baseline learning', () => {
  it('updateBaselineProfile merges running mean/variance (Welford)', () => {
    let profile = updateBaselineProfile(null, { tasks: { 'CS[28]': { wcet_us: 100 } } })
    assert.equal(profile.samples, 1)
    assert.equal(profile.tasks['CS[28]'].wcet_us.n, 1)
    assert.equal(profile.tasks['CS[28]'].wcet_us.mean, 100)
    assert.equal(profile.tasks['CS[28]'].wcet_us.m2, 0)

    profile = updateBaselineProfile(profile, { tasks: { 'CS[28]': { wcet_us: 200 } } })
    assert.equal(profile.samples, 2)
    const stat = profile.tasks['CS[28]'].wcet_us
    assert.equal(stat.n, 2)
    assert.equal(stat.mean, 150)
    assert.equal(stat.m2, 5000)
  })

  it('updateBaselineProfile ignores an empty snapshot', () => {
    const profile = updateBaselineProfile({ version: 1, samples: 3, tasks: {} }, {})
    assert.equal(profile.samples, 3)
    assert.deepEqual(profile.tasks, {})
  })

  it('scoreAgainstBaseline flags |z| > threshold outliers', () => {
    let profile = null
    for (const wcet of [100, 102, 98, 101, 99]) {
      profile = updateBaselineProfile(profile, { tasks: { 'CS[28]': { wcet_us: wcet } } })
    }
    const result = scoreAgainstBaseline(profile, { tasks: { 'CS[28]': { wcet_us: 500 } } })
    assert.equal(result.ok, true)
    assert.equal(result.has_baseline, true)
    const row = result.scores.find(r => r.metric === 'wcet_us')
    assert.ok(Math.abs(row.z) > 2)
    assert.equal(row.flag, true)
    assert.equal(result.flagged.length, 1)
    assert.ok(result.suggested_tools.length)
  })

  it('scoreAgainstBaseline reports z=null with fewer than 2 samples', () => {
    const profile = updateBaselineProfile(null, { tasks: { 'CS[28]': { wcet_us: 100 } } })
    const result = scoreAgainstBaseline(profile, { tasks: { 'CS[28]': { wcet_us: 100 } } })
    const row = result.scores.find(r => r.metric === 'wcet_us')
    assert.equal(row.z, null)
    assert.equal(row.flag, false)
  })

  it('scoreAgainstBaseline with no profile reports has_baseline=false', () => {
    const result = scoreAgainstBaseline(null, { tasks: { 'CS[28]': { wcet_us: 100 } } })
    assert.equal(result.has_baseline, false)
    assert.equal(result.scores[0].n, 0)
  })

  it('baselineScoreFinding tool wrapper scopes to a task and returns data', () => {
    let profile = null
    for (const wcet of [100, 102, 98]) {
      profile = updateBaselineProfile(profile, { tasks: { 'CS[28]': { wcet_us: wcet } } })
    }
    const out = baselineScoreFinding(
      { tasks: { 'CS[28]': { wcet_us: 100 }, 'Other[1]': { wcet_us: 999 } } },
      { profile, task: 'CS[28]' },
    )
    assert.equal(out.ok, true)
    assert.ok(out.data.scores.every(r => r.task === 'CS[28]'))
  })
})

describe('CI regression explanation depth', () => {
  it('classifyRegression maps metric ids to categories', () => {
    assert.equal(classifyRegression(null), 'none')
    assert.equal(classifyRegression({ id: 'migrations' }), 'thrashing')
    assert.equal(classifyRegression({ id: 'migrated_tasks' }), 'thrashing')
    assert.equal(classifyRegression({ id: 'load_balance' }), 'load_imbalance')
    assert.equal(classifyRegression({ id: 'missed_ticks' }), 'tick_health')
    assert.equal(classifyRegression({ id: 'something_else' }), 'unclassified')
  })

  it('explainRegression includes classification, causal_chain, and suggested_tools', () => {
    const compare = {
      failed: true,
      label_a: 'A',
      label_b: 'B',
      message: 'REGRESSION DETECTED',
      primary_regression: {
        id: 'migrations', label: 'Migrations', detail: '+50%', candidate: 150, baseline: 100,
      },
      checks: [{ label: 'Migrations', status: 'fail', detail: '150 vs 100' }],
    }
    const ctx = explainRegression(compare, [])
    assert.equal(ctx.ok, true)
    assert.equal(ctx.classification, 'thrashing')
    assert.ok(ctx.causal_chain.length)
    assert.ok(ctx.suggested_tools.some(t => t.name === 'optimize_experiment'))
    assert.ok(ctx.suggested_tools.some(t => t.name === 'correlate_events'))
    assert.match(ctx.markdown, /Classification/)
    assert.match(ctx.markdown, /Causal chain/)
  })

  it('explainRegression with no failure reports classification "none"', () => {
    const ctx = explainRegression({ failed: false, label_a: 'A', label_b: 'B' })
    assert.equal(ctx.failed, false)
    assert.equal(ctx.classification, 'none')
  })
})

describe('AI-generated validation experiments', () => {
  it('recommendValidationExperiments suggests pin/firmware/measurement for thrashing', () => {
    const findings = [{
      id: 'thrash_cs28', title: 'Core thrashing',
      text: 'CS[28] migrates repeatedly between cores', severity: 'warning', task: 'CS[28]',
    }]
    const result = recommendValidationExperiments(findings, { findingId: 'thrash_cs28' })
    assert.equal(result.ok, true)
    const kinds = new Set(result.experiments.map(e => e.kind))
    assert.deepEqual([...kinds].sort(), ['firmware', 'measurement', 'simulation'])
    assert.ok(result.experiments.some(e => e.title.toLowerCase().includes('pin')))
    assert.ok('disclaimer' in result)
  })

  it('recommendValidationExperiments suggests mutex fixes for blocking findings', () => {
    const findings = [{
      id: 'block_low', title: 'Priority inversion',
      text: 'Low[266] blocked on mutex held by Medium task', severity: 'error', task: 'Low[266]',
    }]
    const result = recommendValidationExperiments(findings, { findingId: 'block_low', limit: 3 })
    assert.equal(result.ok, true)
    assert.ok(result.experiments.length <= 3)
    assert.ok(result.experiments.some(e => /mutex|lock/i.test(e.title)))
  })

  it('recommendValidationExperiments handles empty findings', () => {
    const result = recommendValidationExperiments([])
    assert.equal(result.ok, true)
    assert.deepEqual(result.experiments, [])
  })

  it('recommendExperimentsFinding tool wrapper mirrors the helper', () => {
    const findings = [{
      id: 'thrash_cs28', title: 'Core thrashing',
      text: 'CS[28] migrates repeatedly between cores', severity: 'warning', task: 'CS[28]',
    }]
    const out = recommendExperimentsFinding(findings, { findingId: 'thrash_cs28' })
    assert.equal(out.ok, true)
    assert.ok(out.data.experiments.length)
  })
})

describe('Investigation replay/export JSON package', () => {
  it('buildInvestigationPackage adds a schema/version envelope', () => {
    const pkg = buildInvestigationPackage({
      traceName: 'trace.btf',
      scope: 'full trace',
      finding: { id: 'f1', title: 'Thrashing', severity: 'warning' },
      toolsRun: ['investigate', 'correlate_events'],
      conclusion: 'Confirmed: core thrashing on CS[28]',
      confidence: 'High',
      evidenceTimes: [100, 200],
      timestamp: '2026-08-11T00:00:00',
    })
    assert.equal(pkg.schema, 'btf-investigation-package')
    assert.equal(pkg.version, 1)
    assert.equal(pkg.trace_name, 'trace.btf')
    assert.equal(pkg.scope, 'full trace')
    assert.equal(pkg.finding.id, 'f1')
    assert.deepEqual(pkg.tools_run, ['investigate', 'correlate_events'])
    assert.equal(pkg.conclusion, 'Confirmed: core thrashing on CS[28]')
    assert.equal(pkg.confidence, 'High')
    assert.deepEqual(pkg.evidence_times, [100, 200])
    assert.equal(pkg.timestamp, '2026-08-11T00:00:00')
    assert.doesNotThrow(() => JSON.stringify(pkg))
  })

  it('buildInvestigationPackage without a finding stays JSON-safe', () => {
    const pkg = buildInvestigationPackage({ traceName: 'trace.btf' })
    assert.equal(pkg.finding, null)
    assert.deepEqual(pkg.tools_run, [])
    assert.equal(pkg.schema, 'btf-investigation-package')
  })
})

describe('Auto investigate template + tool registration (web/desktop parity)', () => {
  it('registers auto_investigate as an agent template', () => {
    assert.equal(isAgentTemplate('auto_investigate'), true)
    const tpl = AI_TEMPLATE_QUESTIONS.find(t => t.id === 'auto_investigate')
    assert.ok(tpl, 'auto_investigate must be in AI_TEMPLATE_QUESTIONS')
    assert.equal(tpl.label, 'Auto investigate')
    assert.match(tpl.prompt, /investigate/)
    assert.match(tpl.prompt, /correlate_events/)
    assert.match(tpl.prompt, /find_critical_path/)
    assert.match(tpl.prompt, /detect_priority_inversion/)
    assert.match(tpl.prompt, /what_if|optimize_experiment/)
    assert.match(tpl.prompt, /Confirmed/)
  })

  it('registers the new Phase 3 tools as viewer tools', () => {
    for (const name of [AI_TOOL_BASELINE_SCORE, AI_TOOL_RECOMMEND_EXPERIMENTS, AI_TOOL_EXPORT_INVESTIGATION]) {
      assert.ok(AI_VIEWER_TOOL_NAMES.includes(name), `${name} missing from AI_VIEWER_TOOL_NAMES`)
    }
    assert.equal(isQueryTool(AI_TOOL_BASELINE_SCORE), true)
    assert.equal(isQueryTool(AI_TOOL_RECOMMEND_EXPERIMENTS), true)
    assert.equal(isExportTool(AI_TOOL_EXPORT_INVESTIGATION), true)
  })
})
