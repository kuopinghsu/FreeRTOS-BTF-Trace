import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  assessEvidenceSufficiency,
  buildCausalChain,
  clusterFindings,
  detectContradictions,
  findSimilarInvestigations,
  generateExperimentPlan,
  generateFingerprint,
  planInvestigation,
  recordExperimentOutcome,
  regressionLocalize,
  scoreHypotheses,
  scoreInvestigationMetrics,
  setExperimentOutcomes,
  suggestScope,
} from '../src/utils/aiPlanner.js'

const findings = [
  {
    id: 'mig1',
    title: 'Migration thrash',
    text: 'CS[22] ping-pong between cores',
    task: 'CS[22]',
    severity: 'error',
    evidence: [{ time: 1060000, label: 'migration: burst' }],
  },
  {
    id: 'dl1',
    title: 'Deadline miss',
    text: 'CS[22] missed deadline after migrations',
    task: 'CS[22]',
    severity: 'error',
  },
]

describe('aiPlanner Phase 1–3', () => {
  it('plans, scopes, and scores hypotheses', () => {
    setExperimentOutcomes([])
    const plan = planInvestigation(findings, { question: 'Why did CS[22] miss?' })
    assert.equal(plan.ok, true)
    assert.ok(plan.hypotheses.length)
    assert.ok(plan.steps.includes('detect_contradictions'))
    const scope = suggestScope('Why did CS[22] miss its deadline?', findings)
    assert.equal(scope.task, 'CS[22]')
    const hit = detectContradictions(findings, {
      hypothesis: 'Mutex contention causes deadline miss',
      metrics: { execution: 42, blocking: 3, mutex_hold: 0 },
    })
    assert.equal(hit.verdict, 'CONTRADICTED')
    const scored = scoreHypotheses(plan.hypotheses, {
      findings,
      contradictions: [hit],
    })
    assert.ok(scored.length)
    const stop = assessEvidenceSufficiency(findings, {
      toolsRun: ['investigate', 'correlate_events'],
    })
    assert.ok(['STOP INVESTIGATION', 'CONTINUE'].includes(stop.recommendation))
  })

  it('fingerprints, clusters, and learns experiment outcomes', () => {
    setExperimentOutcomes([])
    const cl = clusterFindings(findings)
    assert.ok(cl.incidents[0].count >= 1)
    const fp = generateFingerprint(findings)
    assert.ok(['HIGH', 'MEDIUM'].includes(fp.scheduling.migration))
    const rec = recordExperimentOutcome({
      change: 'pin CS[22] to Core_0',
      predicted: 'migrations -50%',
      actual: 'migrations -50%',
      findings,
    })
    assert.equal(rec.outcome.quality, 'GOOD')
    const sim = findSimilarInvestigations(findings)
    assert.ok(sim.matches.length)
    const chain = buildCausalChain(findings)
    assert.ok(chain.edges.length)
    assert.match(chain.disclaimer, /causation/i)
    const loc = regressionLocalize(
      { execution: 131, migrations: 10 },
      { execution: 100, migrations: 3 },
      { findings },
    )
    assert.match(loc.likely_mechanism, /migration/)
    const plan = generateExperimentPlan(findings)
    assert.ok(plan.experiments.length)
  })

  it('returns Phase 3 investigation metrics', () => {
    const m = scoreInvestigationMetrics({
      expected: { tasks: ['CS[22]'] },
      actualConclusion: 'CS[22] migration thrash',
      tools: ['plan_investigation', 'detect_contradictions', 'assess_evidence_sufficiency'],
      passed: true,
      findingScore: 80,
    })
    for (const key of [
      'evidence_efficiency', 'investigation_cost', 'false_confidence',
      'falsification_quality', 'scope_accuracy', 'stop_efficiency',
    ]) {
      assert.ok(key in m, key)
    }
  })
})
