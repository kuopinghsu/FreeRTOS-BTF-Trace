import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  analyzeResponseTimes,
  analyzeTaskPeriods,
  bestFindingScope,
  collectWorstEvents,
  compareSummaryStrip,
  compareNotableChanges,
  compareTraceShapeWarnings,
  compareInvestigateTarget,
  compareSectionForMetric,
  compareTaskForRow,
  compareCoreUtilChartRows,
  compareMigrationDeltaHtml,
  comparePairedBarsHtml,
  compareP99DeltaChartRows,
  compareP99DeltaChartSvg,
  compareRowDeltaStatus,
  compareDirectionalDelta,
  compareDumbbellRows,
  compareSummaryChangeBarRows,
  compareSummaryChangeBarsSvg,
  compareSummaryDecisionHtml,
  compareMigrationHeatmapRows,
  filterCompareMigrationRows,
  formatBurstReason,
  formatBurstWindowNs,
  coreUtilOverTime,
  criticalPathRows,
  detectTimelineAnomalies,
  findEventAtPercentile,
  healthInputsFromEvents,
  mutexBlockingTable,
  pairMutexWaits,
  parseSignedDelta,
  compareCellSortKey,
  compareFieldSortAccessors,
  percentileIndex,
  preemptionPairs,
  preemptionStory,
  preemptorRanking,
  recurringPatterns,
  recurringPatternsAcross,
  topBlockingContributors,
  taskCoreMatrix,
  taskHealthScores,
  topCompareRegressions,
  unifiedJitter,
  waiterOwnerMatrix,
  sparkline,
  distributionExplorer,
  taskInspectorLine,
} from '../src/utils/uxExplore.js'

function ev(kind, task, start, duration) {
  return {
    kind,
    task,
    mk: task,
    start,
    stop: start + duration,
    duration,
    jump_ns: kind === 'exec' ? start : start + duration,
    section: { exec: 'exec', block: 'block', inter: 'inter' }[kind] || 'exec',
    reason: '',
  }
}

describe('uxExplore', () => {
  it('formats burst windows as human units', () => {
    assert.equal(formatBurstWindowNs(1_000_000), '1 ms')
    assert.equal(formatBurstReason(9693, 'wakeup', 1_000_000), '9,693 wakeups within 1 ms')
  })

  it('percentile index matches the stats-table formula', () => {
    assert.equal(percentileIndex(10, 0.95), 9)
    assert.equal(percentileIndex(20, 0.95), 18)
    assert.equal(percentileIndex(1, 0.99), 0)
  })

  it('finds the event at p95', () => {
    const evs = [10, 20, 30, 40, 100].map((d, i) => ev('exec', 'T[1]', i * 10, d))
    assert.equal(findEventAtPercentile(evs, 0.95).duration, 100)
  })

  it('ranks worst events by duration', () => {
    const worst = collectWorstEvents([
      ev('exec', 'A[1]', 0, 50),
      ev('block', 'A[1]', 50, 200),
      ev('inter', 'B[2]', 0, 80),
      ev('exec', 'B[2]', 10, 12),
    ], 2)
    assert.deepEqual(worst.map(e => e.duration), [200, 80])
    assert.equal(worst[0].kind, 'block')
  })

  it('flags a long execution tail', () => {
    const evs = Array.from({ length: 8 }, (_, i) => ev('exec', 'A[1]', i * 20, 10))
    evs.push(ev('exec', 'A[1]', 200, 500))
    const found = detectTimelineAnomalies(evs, 8)
    assert.ok(found.some(e => e.duration === 500))
  })

  it('proposes a scope from finding evidence', () => {
    const scope = bestFindingScope({
      title: 'A[1] WCET',
      text: 'spike at jump:1200',
      task: 'A[1]',
      evidence: [{ label: 'wcet', time: 1200 }],
    }, [ev('exec', 'A[1]', 1000, 400)], 0, 10_000)
    assert.ok(scope)
    assert.ok(scope.lo <= 1200)
    assert.ok(scope.hi >= 1200)
    assert.equal(scope.section, 'exec')
  })

  it('parses compare deltas and ranks regressions', () => {
    assert.equal(parseSignedDelta('+12.3 µs').signed, 12300)
    assert.equal(parseSignedDelta('−2').signed, -2)
    assert.equal(compareCellSortKey('+12.3 µs'), 12300)
    assert.equal(compareCellSortKey('−2'), -2)
    assert.equal(compareCellSortKey(15), 15)
    assert.equal(compareCellSortKey('—'), Number.NEGATIVE_INFINITY)
    assert.equal(compareCellSortKey('Worker[1]'), 'worker[1]')
    const acc = compareFieldSortAccessors(['delta', '0'])
    assert.equal(acc.delta({ delta: '+60 µs' }), 60000)
    assert.equal(acc['0'](['+2']), 2)
    const strip = compareSummaryStrip({
      summary: [
        { label: 'Span', a: '1 ms', b: '900 µs', delta: '+100 µs' },
        { label: 'Context switches', a: 10, b: 8, delta: '+2' },
      ],
      execution: [
        { name: 'CS[22]', deltaMax: '+60 µs' },
      ],
    }, 4)
    assert.ok(strip.headline.some(h => h.label === 'Span'))
    const regs = topCompareRegressions([
      { label: 'CS[22] exec max', delta: '+60 µs', signed: 60000, kind: 'time' },
      { label: 'Context switches', delta: '+2', signed: 2, kind: 'count' },
    ], 4)
    assert.equal(regs[0].kind, 'time')
  })

  it('flags missed and extra period gaps', () => {
    const evs = Array.from({ length: 6 }, (_, i) => ev('inter', 'P[1]', i * 100, 100))
    evs.push(ev('inter', 'P[1]', 600, 400))
    evs.push(ev('inter', 'P[1]', 1000, 20))
    const rows = analyzeTaskPeriods(evs, 3)
    assert.equal(rows.length, 1)
    assert.equal(rows[0].expected_ns, 100)
    assert.ok(rows[0].missed >= 1)
    assert.ok(rows[0].extra >= 1)
    assert.equal(rows[0].section, 'period')
  })

  it('builds a per-task per-core percent matrix', () => {
    const evs = [
      { ...ev('exec', 'A[1]', 0, 80), core: 'Core_0' },
      { ...ev('exec', 'A[1]', 80, 20), core: 'Core_1' },
    ]
    const matrix = taskCoreMatrix(evs, ['Core_0', 'Core_1'], 100)
    assert.equal(matrix.rows.length, 1)
    assert.equal(matrix.rows[0].cells.Core_0.pct_span, 80)
    assert.equal(matrix.rows[0].cells.Core_1.pct_task, 20)
  })

  it('pairs mutex handoff as waiter x owner', () => {
    const waits = pairMutexWaits([
      { object: 'mutex:0x1', holder: 'L[1]', holder_mk: 'L[1]', start: 100, stop: 500, duration: 400 },
      { object: 'mutex:0x1', holder: 'H[2]', holder_mk: 'H[2]', start: 500, stop: 600, duration: 100 },
    ], 1000)
    assert.equal(waits.length, 1)
    assert.equal(waits[0].waiter_mk, 'H[2]')
    assert.equal(waits[0].owner_mk, 'L[1]')
    const matrix = waiterOwnerMatrix(waits)
    assert.equal(matrix.cells['H[2]|L[1]'].ns, 400)
  })

  it('scores task health as a labelled heuristic', () => {
    const evs = Array.from({ length: 8 }, (_, i) => ev('exec', 'Good[1]', i * 20, 10))
    for (let i = 0; i < 7; i++) evs.push(ev('exec', 'Bad[2]', i * 20, 10))
    evs.push(ev('exec', 'Bad[2]', 200, 200))
    evs.push(ev('block', 'Bad[2]', 50, 80))
    for (let i = 0; i < 4; i++) evs.push(ev('inter', 'Bad[2]', i * 100, 100))
    evs.push(ev('inter', 'Bad[2]', 400, 800))
    const rows = taskHealthScores(healthInputsFromEvents(evs, 1000, ['Bad[2]']))
    assert.ok(rows.length >= 2)
    assert.ok(rows[0].score < rows[rows.length - 1].score)
    const worst = rows.find(r => r.mk === 'Bad[2]')
    assert.equal(worst.bands.deadline, 'fail')
    assert.match(worst.disclaimer, /not an AI probability/)
  })

  it('computes heuristic response time from adjacent slices', () => {
    const model = analyzeResponseTimes([
      ev('exec', 'T[1]', 0, 10),
      ev('exec', 'T[1]', 40, 10),
    ])
    assert.equal(model.rows.length, 1)
    assert.equal(model.rows[0].n, 2)
    assert.equal(model.events[1].duration, 40)
    assert.match(model.rows[0].disclaimer, /not an explicit BTF/)
  })

  it('splits critical path into exec and preempt', () => {
    const rows = criticalPathRows([
      { ...ev('exec', 'V[1]', 0, 10), core: 'Core_0' },
      { ...ev('exec', 'P[2]', 10, 20), core: 'Core_0' },
      { ...ev('exec', 'V[1]', 30, 10), core: 'Core_0' },
    ], 4)
    assert.ok(rows.length)
    assert.equal(rows[0].section, 'crit_path')
    assert.ok(rows[0].preempt_ns > 0)
  })

  it('ranks preemptors and mutex waits', () => {
    const ranks = preemptorRanking(preemptionPairs([
      { ...ev('block', 'V[1]', 10, 20), core: 'Core_0' },
      { ...ev('exec', 'P[2]', 10, 20), core: 'Core_0' },
    ]), 8)
    assert.equal(ranks[0].mk, 'V[1]')
    assert.match(ranks[0].top_label, /P\[2\]/)
    const table = mutexBlockingTable(pairMutexWaits([
      { object: 'mutex:0x1', holder: 'L[1]', holder_mk: 'L[1]', start: 100, stop: 500, duration: 400 },
      { object: 'mutex:0x1', holder: 'H[2]', holder_mk: 'H[2]', start: 500, stop: 600, duration: 100 },
    ], 1000))
    assert.equal(table[0].mk, 'H[2]')
    assert.equal(table[0].total_ns, 400)
  })

  it('builds core-time bins, unified jitter, patterns, and compare why', () => {
    const evs = [
      { ...ev('exec', 'A[1]', 0, 90), core: 'Core_0' },
      { ...ev('exec', 'A[1]', 100, 10), core: 'Core_0' },
    ]
    const grid = coreUtilOverTime(evs, ['Core_0'], 0, 160, 4)
    assert.equal(grid.bins.length, 4)
    assert.ok(grid.bins[0].peak_pct > 0)
    const jitter = unifiedJitter(evs)
    assert.ok(jitter.length)
    assert.equal(jitter[0].section, 'jitter')
    const anoms = detectTimelineAnomalies(evs.concat([ev('exec', 'A[1]', 200, 500)]), 8)
    const pats = recurringPatterns(anoms.concat(anoms), 2)
    assert.ok(pats.some(p => p.count >= 2))
    const strip = compareSummaryStrip({
      summary: [{ label: 'Span', a: '1 ms', b: '900 µs', delta: '+100 µs' }],
      execution: [{ name: 'CS[22]', deltaMax: '+60 µs' }],
    }, 4)
    assert.ok(strip.why)
  })

  it('attaches response percentile events and includes response in worst', () => {
    const model = analyzeResponseTimes([
      ev('exec', 'T[1]', 0, 10),
      ev('exec', 'T[1]', 40, 10),
    ])
    assert.equal(model.rows[0].p99_ev.duration, 40)
    const worst = collectWorstEvents([
      ev('exec', 'A[1]', 0, 10),
      ev('exec', 'A[1]', 100, 10),
      ev('block', 'B[2]', 0, 20),
    ], 4)
    assert.ok(worst.some(e => e.kind === 'response'))
  })

  it('counts period bursts and builds a preemption story', () => {
    const evs = Array.from({ length: 6 }, (_, i) => ev('inter', 'P[1]', i * 100, 100))
    evs.push(ev('inter', 'P[1]', 600, 20))
    assert.equal(analyzeTaskPeriods(evs, 3)[0].burst, 1)
    const pairs = preemptionPairs([
      { ...ev('block', 'V[1]', 10, 20), core: 'Core_0' },
      { ...ev('exec', 'P[2]', 10, 20), core: 'Core_0' },
    ])
    assert.match(preemptionStory(pairs, 'V[1]'), /P\[2\]/)
    assert.match(preemptorRanking(pairs, 8)[0].story, /resumed/)
  })

  it('ranks top blockers and shared patterns', () => {
    const rows = topBlockingContributors([
      { ...ev('block', 'V[1]', 10, 40), core: 'Core_0' },
      { ...ev('exec', 'P[2]', 10, 40), core: 'Core_0' },
    ], [{
      waiter: 'V[1]', waiter_mk: 'V[1]', owner: 'O[3]', owner_mk: 'O[3]',
      object: 'mutex:1', start: 10, stop: 50, duration: 40,
    }], 8)
    assert.equal(rows[0].mk, 'V[1]')
    const shared = recurringPatternsAcross(
      [{ kind: 'exec', task: 'A[1]', mk: 'A[1]', duration: 10, start: 0 }],
      [{ kind: 'exec', task: 'A[1]', mk: 'A[1]', duration: 20, start: 5 }],
    )
    assert.equal(shared[0].count_a, 1)
  })

  it('compare why names response p99', () => {
    const strip = compareSummaryStrip({
      summary: [{ label: 'Response P99 (worst task)', delta: '+100 µs' }],
      response: [{ name: 'A[1]', delta: '+80 µs' }],
    }, 4)
    assert.match(strip.why.toLowerCase(), /response/)
  })

  it('notable changes classify polarity, threshold, and tick warning', () => {
    const notable = compareNotableChanges({
      summary: [
        { label: 'Migrations (total)', a: 18440, b: 19018, delta: '-578' },
        { label: 'Tick mode', a: 'TICKLESS', b: 'TICKLESS', delta: '—' },
        {
          label: 'Response P99 (worst task)',
          a: '13.698 ms (QP[198])',
          b: '29.062 ms (QP[197])',
          delta: '-15.364 ms',
        },
      ],
      response: [
        { name: 'QP[198]', a: '13.698 ms', b: '29.062 ms', delta: '-15.364 ms' },
        { name: 'QP[197]', a: '25.780 ms', b: '14.687 ms', delta: '+11.093 ms' },
      ],
    }, 8, 'tickful-8cores.btf', 'tickless-8cores.btf')
    const statuses = new Set(notable.rows.map(r => r.status))
    assert.ok(statuses.has('Regressed'))
    assert.ok(statuses.has('Improved'))
    assert.ok(notable.warnings.some(w => w.toLowerCase().includes('tickful')))
    assert.ok(notable.warnings.some(w => w.toLowerCase().includes('different tasks')))
    assert.ok(notable.cards.regressions > 0)
    assert.ok(notable.cards.improvements > 0)
    assert.match(notable.verdict, /Candidate B/)
    assert.ok(notable.rows.every(r => r.significance === 'engineering'))
    assert.ok(String(notable.next_investigation || '').startsWith('Next:'))
    assert.ok('small_omitted_count' in notable)
    assert.ok(notable.investigate)
    assert.equal(notable.investigate.section_id || notable.investigate.section, 'response')
    assert.ok(notable.rows.every(r => r.section))
    assert.equal(compareSectionForMetric('T1 exec max', 'exec max'), 'exec')
    assert.equal(compareTaskForRow('QP[198] response p99', 'response p99'), 'QP[198]')
    assert.equal(compareInvestigateTarget({ rows: [] }).section_id, 'response')
    // Structured verdict: one-word label + tone + top-change bullets.
    assert.equal(notable.verdict_label, 'MIXED')
    assert.equal(notable.verdict_tone, 'mixed')
    assert.ok(notable.verdict_bullets.length > 0 && notable.verdict_bullets.length <= 3)
    assert.ok(notable.comparability)
  })

  it('trace shape warnings feed comparability', () => {
    const warns = compareTraceShapeWarnings(
      4, 8, ['A', 'B', 'C', 'D'], ['A', 'X', 'Y', 'Z', 'W'], 1_000_000, 9_000_000)
    assert.equal(warns.length, 3)
    assert.ok(warns.some(w => w.includes('Core count differs')))
    assert.ok(warns.some(w => w.includes('Task sets differ')))
    assert.ok(warns.some(w => w.includes('durations differ')))
    assert.deepEqual(
      compareTraceShapeWarnings(4, 4, ['A', 'B', 'C'], ['A', 'B', 'C'], 1e6, 1.1e6), [])
    const notable = compareNotableChanges({
      summary: [{ label: 'Span', a: '1 ms', b: '9 ms', delta: '-8 ms' }],
      shape: {
        cores_a: 4, cores_b: 8,
        task_names_a: ['A'], task_names_b: ['B'],
        span_a_ns: 1_000_000, span_b_ns: 9_000_000,
      },
    }, 8, 'a.btf', 'b.btf')
    assert.equal(notable.comparability.comparable, false)
    assert.ok(notable.comparability.warnings.length > 0)
    assert.equal(notable.verdict_label, 'SIMILAR')
  })

  it('paired bars share one scale and carry row tooltips', () => {
    const html = comparePairedBarsHtml(
      [['CS[15]', '14.0', '14.9', '+0.9'], ['CS[16]', '9.0', '3.0', '-6.0']],
      { title: 'Top CPU consumers', subtitle: 'Largest CPU users.' },
    )
    assert.match(html, /Top CPU consumers/)
    assert.match(html, /class="paired-fill a"/)
    assert.match(html, /class="paired-fill b"/)
    assert.match(html, /--w:100\.0%/)
    assert.match(html, /--w:94\.0%/)
    assert.match(html, /<div class="paired-row" title="CS\[15\]: A 14\.0 \u00b7 B 14\.9">/)
    assert.doesNotMatch(html, /class="paired-label" title=/)
    assert.equal((html.match(/class="paired-row"/g) || []).length, 2)
    assert.equal(comparePairedBarsHtml([], { title: 'x' }), '')
  })

  it('migration delta bars diverge around zero', () => {
    const html = compareMigrationDeltaHtml([
      { name: 'CS[19]', migrationsA: 1, migrationsB: 13, delta: -12 },
      { name: 'CS[20]', migrationsA: 40, migrationsB: 2, delta: 38 },
    ])
    assert.match(html, /migration-delta-unified/)
    assert.match(html, /delta-zero/)
    assert.match(html, /class="delta-fill minus"/)
    assert.match(html, /class="delta-fill plus"/)
    assert.match(html, /<div class="delta-row" title="CS\[19\]: \u0394 \u221212">/)
    assert.equal(compareMigrationDeltaHtml([]), '')
  })

  it('compare charts and migration views', () => {
    const util = compareCoreUtilChartRows({
      coreUtil: [
        { core: 'Core_0', utilA: '40.0', utilB: '55.0', delta: '-15.0' },
        { core: 'Core_1', utilA: '10.0', utilB: '8.0', delta: '+2.0' },
      ],
    })
    const p99 = compareP99DeltaChartRows({
      response: [
        { name: 'QP[198]', a: '13 ms', b: '29 ms', delta: '-16 ms' },
        { name: 'QP[197]', a: '25 ms', b: '14 ms', delta: '+11 ms' },
      ],
    })
    assert.equal(p99[0].label, 'QP[198]')
    assert.equal(p99[0].status, 'Regressed')
    assert.equal(p99[1].status, 'Improved')
    const p99Svg = compareP99DeltaChartSvg(p99)
    // Paint comes from CSS classes: var() does not resolve inside an SVG
    // presentation attribute, so fill="var(...)" would never re-theme.
    // Bars use directional blue series (minus/plus), not green/red status.
    assert.match(p99Svg, /class="cmp-chart-bar plus"/)
    assert.match(p99Svg, /class="cmp-chart-bar minus"/)
    assert.doesNotMatch(p99Svg, /class="cmp-chart-bar regressed"/)
    assert.doesNotMatch(p99Svg, /class="cmp-chart-bar improved"/)
    assert.match(p99Svg, /class="cmp-chart-title"/)
    assert.match(p99Svg, /class="cmp-chart-axis"/)
    assert.doesNotMatch(p99Svg, /(?:fill|stroke)="(?!none)/)
    const mig = []
    for (let i = 0; i < 8; i++) {
      mig.push({
        name: `QP[${i}]`, migrationsA: 10 + i, migrationsB: 20 + i, delta: -(10 + i),
        rateA: '1/s', rateB: '2/s', rateDelta: '-1/s',
        dwellA: '1 ms', dwellB: '2 ms', dwellDelta: '-1 ms',
        pingA: 0, pingB: 1, coresA: 2, coresB: 2, primaryA: '0 90%', primaryB: '1 80%',
      })
    }
    mig.push({
      name: 'CS[1]', migrationsA: 4, migrationsB: 4, delta: 0,
      rateA: '1/s', rateB: '1/s', rateDelta: '0',
      dwellA: '1 ms', dwellB: '1 ms', dwellDelta: '0',
      pingA: 0, pingB: 0, coresA: 1, coresB: 1, primaryA: '0 100%', primaryB: '0 100%',
    })
    mig.push({
      name: 'CS[2]', migrationsA: 9, migrationsB: 1, delta: 8,
      rateA: '2/s', rateB: '0.2/s', rateDelta: '+1.8/s',
      dwellA: '2 ms', dwellB: '1 ms', dwellDelta: '+1 ms',
      pingA: 2, pingB: 0, coresA: 3, coresB: 1, primaryA: '1 70%', primaryB: '0 90%',
    })
    const top = filterCompareMigrationRows(mig, 'count', 'top', '', 10)
    assert.equal(top.shown, 9)
    assert.equal(top.headers.length, 7)
    assert.ok(top.rows.every(r => r[3] !== 0))
    assert.equal(top.sort_by, 'abs')
    const rel = filterCompareMigrationRows(mig, 'count', 'top', '', 3, 'rel')
    assert.equal(rel.sort_by, 'rel')
    assert.equal(rel.shown, 3)
    // Relative: CS[2] (+8 on base 9) outranks a mid QP absolute delta.
    assert.equal(rel.rows[0][0], 'CS[2]')
    const dwell = filterCompareMigrationRows(mig, 'dwell', 'all', 'CS', 10)
    assert.equal(dwell.view, 'dwell')
    assert.equal(dwell.headers.length, 6)
    assert.equal(dwell.shown, 2)
    const regs = filterCompareMigrationRows(mig, 'count', 'regressed')
    assert.ok(regs.rows.every(r => r[3] < 0))
    assert.ok(regs.shown > 0)

    const bars = compareSummaryChangeBarRows({
      summary: [
        { label: 'Migrations (total)', a: '10', b: '25', delta: '−15' },
        { label: 'Tasks', a: '5', b: '5', delta: '0' },
        { label: 'Blocking total', a: '1 ms', b: '4 ms', delta: '−3 ms' },
      ],
    }, 8)
    assert.equal(bars.length, 2)
    assert.ok(bars.every(r => r.cand !== 0))
    const migrationBar = bars.find(r => r.label === 'Migrations (total)')
    assert.ok(migrationBar.change.includes('%'))
    // % scale: Core gap (~20%) outranks Migrations /s (~4%); labels show %.
    const mixed = compareSummaryChangeBarRows({
      summary: [
        { label: 'Blocking time /s', a: '1000 s/s', b: '1006.387 s/s', delta: '−6.387 s/s' },
        { label: 'Core gap max', a: '32 µs', b: '40 µs', delta: '−8 µs' },
        { label: 'Migrations /s', a: '7000000/s', b: '7298265.52/s', delta: '−298265.52/s' },
        { label: 'Context switches /s', a: '1000000/s', b: '1022508.99/s', delta: '−22508.99/s' },
      ],
    })
    const byLabel = Object.fromEntries(mixed.map(r => [r.label, r]))
    assert.ok(byLabel['Core gap max'].change.includes('%'))
    assert.ok(byLabel['Migrations /s'].change.includes('%'))
    assert.ok(Math.abs(byLabel['Core gap max'].cand) > Math.abs(byLabel['Migrations /s'].cand))
    const mixedSvg = compareSummaryChangeBarsSvg(mixed)
    assert.match(mixedSvg, /bar = % of max\(A, B\)/)
    assert.match(mixedSvg, /\/ [+\-−]?\d+\.\d+%/)
    const widthAt = (label) => {
      const i = mixedSvg.indexOf(label)
      const m = mixedSvg.slice(i).match(/class="cmp-chart-bar[^"]*"\s+x="[^"]+"\s+y="[^"]+"\s+width="([^"]+)"/)
      return Number(m[1])
    }
    assert.ok(widthAt('Core gap max') > widthAt('Migrations /s'))
    const barSvg = compareSummaryChangeBarsSvg(bars)
    assert.match(barSvg, /Summary changes/)
    assert.match(barSvg, /y="16"[^>]*>Summary changes</)
    assert.match(barSvg, /y="34"[^>]*>B lower</)
    assert.match(barSvg, /y="34"[^>]*>B higher</)
    assert.match(barSvg, /class="cmp-chart-bar (minus|plus)"/)
    assert.ok(barSvg.indexOf('Summary changes') < barSvg.indexOf('>B lower<'))
    const decision = compareSummaryDecisionHtml({
      summary: [
        { label: 'Migrations (total)', a: '10', b: '25', delta: '−15' },
        { label: 'Blocking time /s', a: '1 ms', b: '4 ms', delta: '−3 ms' },
      ],
    }, 'A.btf', 'B.btf')
    assert.match(decision, /class="compare-decision"/)
    assert.match(decision, /class="compare-verdict-banner tone-/)
    assert.match(decision, /class="compare-card tone-regressed"/)
    assert.match(decision, /Biggest mover/)

    const heat = compareMigrationHeatmapRows(mig, 5)
    assert.equal(heat.length, 5)
    assert.ok(heat.every(r => r.delta !== 0))

    assert.equal(compareRowDeltaStatus('Migrations (total)', '−15'), 'Regressed')
    assert.equal(compareRowDeltaStatus('QP[1]', '+8', 'migrations'), 'Improved')
  })

  it('compareDirectionalDelta resolves arrow + word per polarity', () => {
    // Response P99 is "lower is better"; stored delta is A − B, so a Candidate
    // that got 80 µs slower stores −80 µs and the reader sees +80 µs ▲ worse.
    const worse = compareDirectionalDelta('Response P99', '−80 µs', 'response', '210 µs')
    assert.equal(worse.status, 'Regressed')
    assert.equal(worse.arrow, '▲')
    assert.equal(worse.word, 'worse')
    assert.match(worse.text, /\+80 µs · \+38\.1% ▲ worse/)

    const better = compareDirectionalDelta('Blocking time /s', '+35 µs/s', 'block', '540 µs/s')
    assert.equal(better.status, 'Improved')
    assert.equal(better.arrow, '▼')
    assert.equal(better.word, 'better')

    // Non-directional metric → flat bullet, no colour reliance.
    const flat = compareDirectionalDelta('Tasks', '+2', '')
    assert.equal(flat.arrow, '•')
    assert.equal(flat.word, 'flat')

    assert.equal(compareDirectionalDelta('Response P99', '0'), null)
    assert.equal(compareDirectionalDelta('Response P99', '—'), null)
  })

  it('compareDumbbellRows scales dots and flags the better side', () => {
    const rows = [
      { name: 'ctrl_loop', a: '210 µs', b: '290 µs' },
      { name: 'net_worker', a: '320 µs', b: '300 µs' },
      { name: 'ui_task', a: '88 µs', b: '92 µs' },
    ]
    const db = compareDumbbellRows(rows, { limit: 2 })
    assert.equal(db.length, 2)
    // Sorted by |B − A|: ctrl_loop (80) before net_worker (20).
    assert.equal(db[0].label, 'ctrl_loop')
    assert.equal(db[0].better, false)
    assert.equal(db[1].better, true)
    // Percent is of the shared max magnitude (320).
    assert.ok(db[0].bPct > db[0].aPct)
    assert.ok(db.every(r => r.aPct >= 0 && r.aPct <= 100))
  })

  it('unified jitter has dispatch/wakeup and period spark', () => {
    const evs = [
      ev('exec', 'A[1]', 0, 10),
      ev('exec', 'A[1]', 20, 10),
      ev('exec', 'A[1]', 100, 10),
    ]
    const jitter = unifiedJitter(evs, { 'A[1]': [5, 50] })
    assert.ok(jitter[0].dispatch_jitter_ns > 0)
    assert.ok(jitter[0].wakeup_jitter_ns > 0)
    const model = distributionExplorer(evs, 'exec', 'A[1]')
    assert.equal(model.n, 3)
    assert.ok(sparkline([10, 20, 30, 5]))
    const periods = analyzeTaskPeriods(
      [...Array(6)].map((_, i) => ev('inter', 'P[1]', i * 100, 100)).concat([ev('inter', 'P[1]', 600, 20)]),
      3,
    )
    assert.equal(periods[0].burst, 1)
    assert.ok(periods[0].spark)
  })
})

describe('taskInspectorLine', () => {
  it('decodes merge keys to Name[id] (no NUL glyphs)', () => {
    assert.equal(taskInspectorLine('\x0028\x00CS', []), 'Task CS[28]')
    assert.equal(taskInspectorLine('T1', ['gap']), 'Task T1 · gap')
    assert.equal(taskInspectorLine('', []), 'No task selected')
    assert.equal(taskInspectorLine('\x00267\x00Med', []).includes('\x00'), false)
  })
})
