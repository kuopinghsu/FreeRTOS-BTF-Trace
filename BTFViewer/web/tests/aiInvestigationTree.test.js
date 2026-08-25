import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  buildInvestigateContext,
  buildRootCauseChain,
  computeEvidenceScore,
  enrichFindingsWithIds,
  evidenceScoreBar,
  extractEvidencePanelPayload,
  formatEvidencePanelMarkdown,
  investigationTreeMermaid,
  mergeEvidencePanelPayload,
} from '../src/utils/aiInvestigation.js'

// Phase 4: investigation tree mermaid — mirrors
// tests/test_ai_investigation.py (Python) for Desktop/Web parity.
describe('investigationTreeMermaid', () => {
  it('returns empty string with no chain and no hypotheses', () => {
    assert.equal(investigationTreeMermaid([], []), '')
    assert.equal(investigationTreeMermaid(undefined, undefined), '')
  })

  it('renders chain steps and hypotheses anchored to the first step', () => {
    const finding = {
      id: 'thrashing',
      severity: 'warning',
      title: 'Excessive bouncing / core thrashing',
      text: 'CS[28] migrates heavily',
    }
    const chain = buildRootCauseChain(finding)
    assert.ok(chain.length)
    const hyps = [
      { hypothesis: 'Core thrashing / lock bounce', why: 'High migration' },
      { hypothesis: 'Missing affinity pin', why: 'Equal-priority fan-out' },
    ]
    const src = investigationTreeMermaid(chain, hyps)
    assert.match(src, /^graph TD/)
    assert.equal((src.match(/S0\[/g) || []).length, 1)
    assert.match(src, /S0 --> S1/)
    assert.match(src, /H0\(Core thrashing/)
    assert.match(src, /S0 --> H0/)
    assert.match(src, /H1\(Missing affinity pin\)/)
    assert.doesNotMatch(src, /\[28\]/)
  })

  it('sanitizes mermaid delimiter characters out of labels', () => {
    const chain = [{ label: 'Weird [brackets] (parens) "quotes" | pipe', kind: 'finding' }]
    const src = investigationTreeMermaid(chain, [])
    assert.doesNotMatch(src, /\[brackets\]/)
    assert.doesNotMatch(src, /\(parens\)/)
    assert.doesNotMatch(src, /"/)
    assert.doesNotMatch(src, /\|/)
  })

  it('is wired into buildInvestigateContext / extractEvidencePanelPayload', () => {
    const findings = enrichFindingsWithIds([
      {
        id: 'thrashing',
        severity: 'warning',
        title: 'Excessive bouncing / core thrashing',
        text: 'CS[28] migrates heavily',
      },
    ])
    const ctx = buildInvestigateContext(findings, 'thrashing', { depth: 2 })
    const payload = extractEvidencePanelPayload('investigate', { ok: true, data: ctx })
    assert.ok(payload)
    assert.ok('root_cause_chain' in payload)
    assert.ok('hypotheses' in payload)
    const src = investigationTreeMermaid(payload.root_cause_chain, payload.hypotheses)
    assert.match(src, /^graph TD/)
  })
})

// Phase 4: AI Evidence Score heuristic — mirrors
// tests/test_ai_investigation.py (Python) for Desktop/Web parity.
describe('evidenceScoreBar', () => {
  it('formats a text meter clamped to [0, 100]', () => {
    assert.equal(evidenceScoreBar(0), `${'░'.repeat(10)} 0%`)
    assert.equal(evidenceScoreBar(100), `${'█'.repeat(10)} 100%`)
    assert.equal(evidenceScoreBar(80), `${'█'.repeat(8)}${'░'.repeat(2)} 80%`)
    assert.equal(evidenceScoreBar(-20), `${'░'.repeat(10)} 0%`)
    assert.equal(evidenceScoreBar(250), `${'█'.repeat(10)} 100%`)
  })
})

describe('computeEvidenceScore', () => {
  it('sums direct evidence, timeline, and metric correlation bonuses', () => {
    const result = computeEvidenceScore([
      { label: 'blocking: mutex wait', time: 1000 },
      { label: 'sync: mutex take', time: 1200 },
    ], {
      alternatives: [{ status: 'plausible' }],
      evidenceChain: '### Evidence chain',
      checks: [{ label: 'Migrations', status: 'fail' }],
    })
    assert.equal(result.score, 80)
    assert.equal(result.label, 'AI Evidence Score — heuristic')
    assert.equal(result.breakdown.length, 3)
    assert.match(result.bar, /80%/)
  })

  it('penalizes untested alternatives and missing evidence', () => {
    const result = computeEvidenceScore([], {
      alternatives: [
        { status: 'plausible' },
        { status: 'untested' },
        { status: 'untested' },
        { status: 'untested' },
      ],
    })
    // -10 (missing evidence) and -15 (capped at 3x -5 for untested alts).
    assert.equal(result.score, 0)
    const labels = result.breakdown.map(b => b.label)
    assert.ok(labels.some(l => l.includes('untested')))
    assert.ok(labels.some(l => l.includes('Missing direct evidence')))
  })

  it('scores partial evidence without timeline/metric correlation bonus', () => {
    const result = computeEvidenceScore([{ label: 'evidence', time: 500 }], {
      alternatives: [{ status: 'untested' }],
    })
    // +40 (has times) - 5 (one untested alternative) = 35.
    assert.equal(result.score, 35)
  })

  it('treats need_evidence aliases as untested and keeps chain +25', () => {
    for (const status of ['need_evidence', 'needs_evidence', '']) {
      const result = computeEvidenceScore(
        [{ label: 'blocking: wait', time: 100 }],
        { alternatives: [{ status }], evidenceChain: 'Finding → blocking' },
      )
      assert.equal(result.score, 60, status)
    }
  })

  it('keeps evidence_chain when timed evidence rows exist', () => {
    const payload = extractEvidencePanelPayload('investigate', {
      ok: true,
      finding: {
        title: 'Stall',
        text: 'blocked',
        evidence: [{ label: 'blocking: wait', time: 100 }],
      },
      evidence_chain: 'Finding → blocking',
      alternatives: [],
    })
    assert.equal((payload.evidence || []).length, 1)
    assert.match(String(payload.evidence_chain || ''), /Finding → blocking/)
  })

  it('promotes jump:TIME from finding text into investigate evidence', () => {
    const findings = enrichFindingsWithIds([{
      id: 'thrash',
      severity: 'warning',
      title: 'Excessive bouncing / core thrashing',
      text: 'CS[22] migrates heavily jump:2500',
    }])
    const ctx = buildInvestigateContext(findings, 'thrash')
    assert.ok((ctx.evidence_score || 0) >= 60)
    assert.ok(['medium', 'medium-high', 'strong'].includes(ctx.evidence_quality?.band))
    assert.ok((ctx.finding?.evidence || []).some(e => e.time === 2500))
  })

  it('feeds search_timeline hits into the evidence panel', () => {
    const payload = extractEvidencePanelPayload('search_timeline', {
      ok: true,
      message: '3 match(es)',
      times: [100, 200, 300],
      count: 3,
      mode: 'contains',
      query: 'CS[22]',
    })
    assert.equal((payload.evidence || []).length, 3)
    assert.ok((payload.evidence_score || 0) >= 40)
  })

  it('is wired into buildInvestigateContext', () => {
    const findings = enrichFindingsWithIds([
      {
        id: 'thrashing',
        severity: 'warning',
        title: 'Excessive bouncing / core thrashing',
        text: 'CS[28] migrates heavily',
      },
    ])
    const ctx = buildInvestigateContext(findings, 'thrashing', { depth: 2 })
    assert.ok('evidence_score' in ctx)
    assert.ok('evidence_score_breakdown' in ctx)
    assert.ok(Number.isInteger(ctx.evidence_score))
    assert.ok(ctx.evidence_score >= 0)
    assert.ok(ctx.evidence_score <= 100)
  })

  it('is wired into extractEvidencePanelPayload', () => {
    const result = {
      ok: true,
      data: {
        task: 'CS[28]',
        events: [
          { time: 100, kind: 'blocking', detail: 'wait' },
          { time: 200, kind: 'sync', detail: 'mutex take' },
        ],
        correlation: 0.8,
      },
    }
    const payload = extractEvidencePanelPayload('correlate_events', result)
    assert.ok(payload)
    assert.ok('evidence_score' in payload)
    assert.ok('evidence_score_bar' in payload)
    assert.ok(payload.evidence_score >= 40 + 25)
    assert.ok((payload.falsify || {}).supporting?.length)
    const interpreted = extractEvidencePanelPayload('interpret_query', {
      ok: true,
      data: {
        interpreted_question: 'Why is TaskA slow?',
        mode: 'diagnose',
        scope: ['execution', 'blocking'],
      },
    })
    assert.equal(interpreted.investigation_case?.conclusion, 'Why is TaskA slow?')
  })

  it('preserves task, core, and duration on evidence rows', () => {
    const corr = extractEvidencePanelPayload('correlate_events', {
      ok: true,
      data: {
        task: 'Worker[3]',
        events: [
          {
            time: 1000, kind: 'execution', detail: 'dur=500 core=Core_2',
            task: 'Worker[3]', core: 'Core_2',
            start: 1000, stop: 1500, duration: 500,
          },
          { time: 2000, kind: 'blocking', detail: '800', duration: 800 },
        ],
      },
    })
    assert.equal(corr.evidence[0].task, 'Worker[3]')
    assert.equal(corr.evidence[0].core, 'Core_2')
    assert.equal(corr.evidence[0].start, 1000)
    assert.equal(corr.evidence[0].stop, 1500)
    assert.equal(corr.evidence[1].task, 'Worker[3]')
    assert.equal(corr.evidence[1].start, 2000)
    assert.equal(corr.evidence[1].stop, 2800)
    const md = formatEvidencePanelMarkdown(corr, 'English')
    assert.match(md, /Worker\[3\]/)
    assert.match(md, /Core_2/)
    assert.doesNotMatch(md, /\| Worker\[3\] \| — \| — \|/)

    const inv = extractEvidencePanelPayload('investigate', {
      ok: true,
      data: {
        finding: {
          title: 'Stall',
          text: 'Worker[3] stalled',
          task: 'Worker[3]',
          evidence: [{ label: 'finding text', time: 42 }],
        },
      },
    })
    assert.equal(inv.evidence[0].task, 'Worker[3]')
  })

  it('extracts explain_finding / interpret_query / validate_experiment / manage_hypotheses', () => {
    const explained = extractEvidencePanelPayload('explain_finding', {
      ok: true,
      data: {
        finding: { title: 'Migration thrash', text: 'CS[22] bounce' },
        hypotheses: [{ hypothesis: 'Thrash', status: 'possible' }],
        explanation: 'Task CS[22] is bouncing.',
      },
    })
    assert.ok(explained)
    assert.match(explained.conclusion, /Migration thrash/)
    const interpreted = extractEvidencePanelPayload('interpret_query', {
      ok: true,
      data: {
        interpreted_question: 'Why is TaskA slow?',
        mode: 'diagnose',
        scope: ['execution', 'blocking'],
      },
    })
    assert.ok(interpreted)
    assert.equal(interpreted.conclusion, 'Why is TaskA slow?')
    assert.match(String(interpreted.subtitle || ''), /diagnose/)
    const validated = extractEvidencePanelPayload('validate_experiment', {
      ok: true,
      data: {
        result: 'VALIDATED',
        rows: [
          { metric: 'migrations', expected: -50, actual: -72, status: 'validated' },
        ],
      },
    })
    assert.ok(validated)
    assert.equal(validated.conclusion, 'VALIDATED')
    assert.equal(validated.checks[0].label, 'migrations')
    const managed = extractEvidencePanelPayload('manage_hypotheses', {
      ok: true,
      data: {
        finding: { title: 'Mutex contention' },
        hypotheses: [{ hypothesis: 'Lock hold', status: 'supported' }],
      },
    })
    assert.ok(managed)
    assert.equal(managed.conclusion, 'Mutex contention')
    const planned = extractEvidencePanelPayload('plan_investigation', {
      ok: true,
      message: 'Plan with 2 hypotheses, 4 steps',
      data: { steps: ['detect_contradictions'] },
    })
    assert.ok(planned)
    assert.match(planned.conclusion, /Plan with/)
  })
})

describe('mergeEvidencePanelPayload', () => {
  it('keeps timed evidence when late planner tools score 0', () => {
    const strong = extractEvidencePanelPayload('correlate_events', {
      ok: true,
      data: {
        task: 'CS[22]',
        events: [
          { kind: 'migration', detail: 'c0->c1', time: 1487000 },
          { kind: 'ready', detail: 'wake', time: 1487100 },
        ],
        correlation: 0.9,
      },
    })
    assert.ok(strong.evidence_score >= 40 + 25)
    const late = extractEvidencePanelPayload('challenge_conclusion', {
      ok: true,
      message: 'Challenge: conclusion holds',
      data: { verdict: 'Confirmed', confidence: 'High' },
    })
    assert.equal(late.evidence_score, 0)
    const merged = mergeEvidencePanelPayload(strong, late)
    assert.ok(merged.evidence_score >= 40 + 25)
    assert.equal(merged.conclusion, late.conclusion)
    assert.ok((merged.evidence || []).some(e => e.time != null))
  })

  it('keeps prior alternatives when late tool sends empty list', () => {
    const prev = extractEvidencePanelPayload('investigate', {
      ok: true,
      data: {
        finding: {
          title: 'Stall',
          evidence: [{ label: 'blocking: wait', time: 100 }],
        },
        alternatives: [{ status: 'need_evidence', hypothesis: 'alt' }],
      },
    })
    const late = extractEvidencePanelPayload('challenge_conclusion', {
      ok: true,
      message: 'Challenge: conclusion holds',
      data: { verdict: 'Confirmed', confidence: 'High', alternatives: [] },
    })
    const merged = mergeEvidencePanelPayload(prev, late)
    assert.equal((merged.alternatives || []).length, 1)
  })
})
