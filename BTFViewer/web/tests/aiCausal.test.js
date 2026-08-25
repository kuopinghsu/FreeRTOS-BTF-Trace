import assert from 'node:assert/strict'
import { describe, it, beforeEach } from 'node:test'
import {
  analyzeDistribution,
  analyzePeriodicity,
  collectPeriodicityTimes,
  analyzeTemporalCausality,
  buildTaskDependencyGraph,
  collectDependencyEdges,
  challengeConclusion,
  closeInvestigation,
  clusterIncidents,
  decomposeResponseTime,
  investigationMemory,
  rankRootCauses,
  setInvestigationMemory,
  summarizeInvestigationContext,
  verifyClaim,
} from '../src/utils/aiCausal.js'

const findings = [
  {
    id: 'blk',
    title: 'Mutex blocking',
    text: 'CS[22] blocked waiting for Mutex held by Idle[1] jump:1000',
    task: 'CS[22]',
    time: 1000,
  },
  {
    id: 'pre',
    title: 'Preemption',
    text: 'High[3] preempts CS[22] jump:2000',
    task: 'High[3]',
    time: 2000,
  },
]

describe('aiCausal engines', () => {
  beforeEach(() => setInvestigationMemory([]))

  it('orders a temporal chain and dependency graph', () => {
    const chain = analyzeTemporalCausality(findings, { task: 'CS[22]' })
    assert.equal(chain.ok, true)
    assert.ok(chain.events.length >= 1)
    const graph = buildTaskDependencyGraph(findings)
    assert.ok(graph.nodes.length > 0)
    assert.equal(graph.source, 'findings')
    const parts = decomposeResponseTime(findings, { task: 'CS[22]' })
    assert.ok(parts.parts.length > 0)
    assert.ok(rankRootCauses(findings).ranked.length > 0)
  })

  it('builds a BTF wait/preempt/migrate graph', () => {
    const syncHolds = [
      {
        kind: 'mutex', key: 'mutex:M', holder: 'Holder[1]',
        start_ns: 0, stop_ns: 100, duration_ns: 100,
      },
      {
        kind: 'mutex', key: 'mutex:M', holder: 'Waiter[2]',
        start_ns: 100, stop_ns: 150, duration_ns: 50,
      },
    ]
    const preemptions = [
      { preemptor: 'Hog[3]', victim: 'Waiter[2]', count: 2, weight: 80 },
    ]
    const migrations = [
      { task: 'Waiter[2]', from_core: 'Core_0', to_core: 'Core_1' },
    ]
    const priorityEpisodes = [
      { task: 'Waiter[2]', inherited: true, medium_tasks: ['Holder[1]'] },
    ]
    const kinds = new Set(collectDependencyEdges({
      syncHolds, preemptions, migrations, priorityEpisodes,
    }).map(e => `${e.from}|${e.to}|${e.kind}`))
    assert.ok(kinds.has('Holder[1]|mutex:M|owns'))
    assert.ok(kinds.has('Waiter[2]|mutex:M|waits-for'))
    assert.ok(kinds.has('Holder[1]|Waiter[2]|blocks'))
    assert.ok(kinds.has('Hog[3]|Waiter[2]|preempts'))
    assert.ok(kinds.has('Waiter[2]|Core_1|migrates-to'))
    assert.ok(kinds.has('Waiter[2]|Holder[1]|inherits-priority-from'))
    const graph = buildTaskDependencyGraph([], {
      syncHolds, preemptions, migrations, priorityEpisodes, task: 'Waiter[2]',
    })
    assert.equal(graph.source, 'btf')
    assert.ok(graph.responsible.includes('Holder[1]'))
    assert.ok(graph.responsible.includes('Hog[3]'))
    assert.ok(graph.disclaimer.includes('BTF'))
  })

  it('verifies claims and challenges conclusions', () => {
    const hit = verifyClaim('CS[22] blocked on mutex', {
      subject: 'CS[22]',
      findings,
    })
    assert.ok(['confirmed', 'rejected', 'inconclusive'].includes(hit.verdict))
    assert.equal(challengeConclusion('mutex blocking', { findings }).ok, true)
  })

  it('stores memory and closes the case', () => {
    const stored = investigationMemory('store', {
      record: { finding: 'Mutex blocking', pattern: 'mutex', fix: 'pin' },
      findings,
    })
    assert.equal(stored.count, 1)
    assert.ok(investigationMemory('recall', { findings }).matches.length > 0)
    assert.equal(closeInvestigation('mutex', { findings }).case.status, 'closed')
  })

  it('computes distribution, periodicity, clusters, and summary', () => {
    const dist = analyzeDistribution([1, 2, 3, 10], { metric: 'ms' })
    assert.equal(dist.n, 4)
    assert.equal(dist.source, 'values')
    assert.equal(dist.p50, 3)
    assert.equal(dist.p90, 10)
    assert.equal(dist['p99.9'], 10)
    assert.ok(dist.stddev > 0)
    assert.ok(dist.cv > 0)
    assert.equal(dist.outlier_rate, 0)
    assert.ok(analyzeDistribution([...Array(50).fill(1), 100]).outlier_rate > 0)
    const found = analyzeDistribution([], { findings: [{ text: 'blocked 12 ms jump:1000' }] })
    assert.equal(found.source, 'findings')
    assert.ok(found.n >= 1)
    assert.equal(analyzePeriodicity([10, 20, 30, 40]).ok, true)
    const stable = analyzePeriodicity([10, 20, 30, 40])
    assert.equal(stable.kind, 'stable period')
    assert.equal(analyzePeriodicity([0, 12, 24, 36], { expected: 10 }).kind, 'period drift')
    assert.equal(analyzePeriodicity([0, 10, 19, 32, 41], { expected: 10 }).kind, 'release jitter')
    assert.equal(analyzePeriodicity([0, 10, 20, 50], {
      expected: 10,
      findings: [{ title: 'preempt', text: 'ISR preempts CS[22]' }],
    }).kind, 'scheduler interference')
    assert.equal(analyzePeriodicity([0, 10, 20, 30], {
      expected: 10,
      durations: [1, 8, 2, 9],
    }).kind, 'execution-time variation')
    assert.deepEqual(
      collectPeriodicityTimes([], { source: 'tick', tickTimes: [0, 1000, 2000, 3000] }),
      [0, 1000, 2000, 3000],
    )
    assert.ok(clusterIncidents(findings, { windowNs: 500 }).incidents.length > 0)
    const summary = summarizeInvestigationContext(findings, {
      toolsRun: ['investigate'],
      conclusion: 'mutex',
    })
    assert.equal(summary.summary.finding_count, 2)
  })
})
