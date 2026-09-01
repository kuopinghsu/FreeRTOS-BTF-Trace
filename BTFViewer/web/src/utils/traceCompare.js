/**
 * Compare summary and per-task metrics between two loaded traces.
 * Optional lo/hi per trace for cursor-scoped compare.
 */

import { formatTime, formatTimeTrim } from './timeFormat.js'
import { isStiTagChannel } from '../renderer/TimelineRenderer.js'
import { parseTaskName, taskDisplayName, taskLabelForMergeKey, taskReprGet, isIdleTaskName } from './colors.js'
import { schedulingStats, blockingTimeSamples, preemptionChainRows, coreSegsInRange } from './statsAnalysis.js'
import { isMigratedTask, migrationRows } from './migrationAnalysis.js'
import { syncObjectStatsRows } from './syncObjectAnalysis.js'
import { getPlacedCursors, segFullyInRange, segOverlapNs } from './statsRange.js'
import { tickHealthReport } from './tickHealth.js'
import loadBalanceMetrics from './loadBalanceGauge.js'
import { btfHtmlReportDocument, HTML_REPORT_INTERACTIVE_SCRIPT, HTML_REPORT_TOC_CSS, HTML_REPORT_TOC_SCRIPT, htmlApplyCollapsibleToc } from './htmlReport.js'
import {
  compareAnalysisTables,
  compareNotableChanges,
  compareSummaryDecisionHtml,
  COMPARE_DELTA_FORMULA,
  COMPARE_METRIC_GLOSSARY,
  COMPARE_NOTE_SIGMA,
  COMPARE_NOTE_MIGRATION,
  COMPARE_NOTE_STI,
  COMPARE_NOTE_P99,
  compareCoreUtilChartRows,
  compareCoreUtilChartSvg,
  compareP99DeltaChartRows,
  compareP99DeltaChartSvg,
  compareSummaryChangeBarRows,
  compareSummaryChangeBarsSvg,
  compareMigrationHeatmapRows,
  compareMigrationHeatmapSvg,
  filterCompareMigrationRows,
} from './uxExplore.js'

export function cursorRangeForCursors(cursors) {
  const placed = getPlacedCursors(cursors || [])
  if (placed.length < 2) return { lo: null, hi: null }
  const sorted = [...placed].sort((a, b) => a - b)
  return { lo: sorted[0], hi: sorted[sorted.length - 1] }
}

/** Per-core active util % excluding IDLE/TICK (same as StatisticsPanel._coreUtilRows). */
export function coreUtilPctRows(trace, lo = null, hi = null) {
  if (!trace?.coreNames?.length) return []
  if (lo == null && hi == null && trace.coreUtilPct) {
    return trace.coreNames.map(core => ({
      core,
      pct: Number(trace.coreUtilPct[core] ?? 0),
    }))
  }
  const total = (lo != null && hi != null)
    ? (hi - lo)
    : (trace.timeMax - trace.timeMin)
  if (total <= 0) return []
  return trace.coreNames.map((core) => {
    const segs = coreSegsInRange(trace, core, lo, hi)
    let active = 0
    for (const s of segs) {
      const { name } = parseTaskName(s.task)
      if (name === 'TICK' || isIdleTaskName(name)) continue
      active += (lo != null && hi != null)
        ? segOverlapNs(s, lo, hi)
        : (s.end - s.start)
    }
    return { core, pct: 100.0 * active / total }
  })
}

function loadBalanceFromCoreRows(coreRows) {
  const pcts = (coreRows || []).map(r => r.pct).filter(v => v != null)
  const lb = loadBalanceMetrics(pcts)
  if (!lb) return null
  return { score: lb.score, sigma: lb.stddev, gini: lb.gini }
}

function isUnlimitedLimit(limit) {
  if (limit == null) return true
  const n = Number(limit)
  return !Number.isFinite(n) || n <= 0
}

function applyRowLimit(items, limit) {
  const seq = [...(items || [])]
  if (isUnlimitedLimit(limit)) return seq
  return seq.slice(0, Number(limit))
}

/** Slice durations fully inside [lo, hi] (or all when unscoped). */
export function execSliceSamples(segs, lo = null, hi = null) {
  const samples = []
  for (const s of segs || []) {
    const d = s.end - s.start
    if (d <= 0) continue
    if (lo != null && hi != null && !segFullyInRange(s, lo, hi)) continue
    samples.push(d)
  }
  return samples
}

/** Gaps between consecutive starts; next start must fall in range when scoped. */
export function interArrivalSamples(segs, lo = null, hi = null) {
  if (!segs || segs.length < 2) return []
  const starts = segs.map(s => s.start).sort((a, b) => a - b)
  const samples = []
  for (let i = 1; i < starts.length; i++) {
    if (lo != null && hi != null && (starts[i] < lo || starts[i] > hi)) continue
    const d = starts[i] - starts[i - 1]
    if (d > 0) samples.push(d)
  }
  return samples
}

/** Sample summary: min/avg/max/p95 with formatTime strings + ns values. */
export function summarizeTimeSamples(samples, scale) {
  if (!samples?.length) return null
  const sorted = [...samples].sort((a, b) => a - b)
  const n = sorted.length
  const sum = sorted.reduce((a, b) => a + b, 0)
  const avgNs = Math.round(sum / n)
  const p95Idx = Math.min(n - 1, Math.ceil(n * 0.95) - 1)
  const minNs = sorted[0]
  const maxNs = sorted[n - 1]
  const p95Ns = sorted[p95Idx]
  return {
    count: n,
    minNs,
    avgNs,
    maxNs,
    p95Ns,
    min: formatTime(minNs, scale),
    avg: formatTime(avgNs, scale),
    max: formatTime(maxNs, scale),
    p95: formatTime(p95Ns, scale),
  }
}

function taskMetricCompareByName(trace, sampleFn, lo, hi, {
  includeCpu = false,
  runsFromStarts = false,
} = {}) {
  const map = new Map()
  if (!trace?.segByMergeKey) return map
  const scale = trace.timeScale
  const span = (lo != null && hi != null)
    ? Math.max(1, hi - lo)
    : Math.max(1, trace.timeMax - trace.timeMin)
  for (const [mk, segs] of trace.segByMergeKey) {
    if (!segs?.length) continue
    const repr = taskReprGet(trace, mk) ?? mk
    const { name: tname } = parseTaskName(repr)
    if (isIdleTaskName(tname) || tname === 'TICK') continue
    const samples = sampleFn(segs, lo, hi)
    const summary = summarizeTimeSamples(samples, scale)
    if (!summary) continue
    const name = taskDisplayName(repr)
    let runs = summary.count
    if (runsFromStarts) {
      runs = (lo != null && hi != null)
        ? segs.filter(s => s.start >= lo && s.start <= hi).length
        : segs.length
    }
    const entry = { ...summary, runs }
    if (includeCpu) {
      const taskTotal = samples.reduce((a, b) => a + b, 0)
      entry.cpuPct = 100.0 * taskTotal / span
    }
    map.set(name, entry)
  }
  return map
}

export function traceSummarySnapshot(trace, lo = null, hi = null) {
  if (!trace) return null
  const fullSpan = trace.timeMax - trace.timeMin
  const spanNs = (lo != null && hi != null) ? Math.max(0, hi - lo) : fullSpan
  const stiEvents = (trace.stiEvents || []).filter(ev => {
    if (isStiTagChannel(ev.target)) return false
    if (lo != null && hi != null) return ev.time >= lo && ev.time <= hi
    return true
  }).length
  const { contextSwitches, coreGaps, gapMax } = schedulingStats(trace, lo, hi)
  const gapAvgNs = coreGaps.length
    ? Math.round(coreGaps.reduce((a, b) => a + b, 0) / coreGaps.length)
    : 0
  const gapMaxNs = coreGaps.length ? gapMax : 0
  let migrations = trace.migrations?.length ?? 0
  let migratedTasks = (trace.tasks || []).filter(mk => isMigratedTask(trace, mk)).length
  if (lo != null && hi != null) {
    migrations = (trace.migrations || []).filter(m => m.ns >= lo && m.ns <= hi).length
    migratedTasks = migrationRows(trace, lo, hi).length
  }

  const coreRows = coreUtilPctRows(trace, lo, hi)
  const lb = loadBalanceFromCoreRows(coreRows)
  const tick = tickHealthReport(trace, lo, hi)
  let tickMode = '—'
  if (tick.tickCount > 0) tickMode = tick.isTickless ? 'TICKLESS' : 'TICK'

  return {
    spanNs,
    tasks: trace.tasks?.length ?? 0,
    segments: lo != null && hi != null
      ? trace.segments.filter(s => s.end > lo && s.start < hi).length
      : (trace.segments?.length ?? 0),
    stiEvents,
    contextSwitches,
    gapAvgNs,
    gapMaxNs,
    migrations,
    migratedTasks,
    timeScale: trace.timeScale,
    loadBalanceScore: lb?.score ?? null,
    loadBalanceSigma: lb?.sigma ?? null,
    tickHealth: tick.tickCount ? tick.health : 'unknown',
    tickMode,
    tickCount: tick.tickCount,
    missedTicks: tick.missedTicksEstimate,
  }
}

export function crossTraceTrends(rows = []) {
  const out = []
  for (const raw of rows || []) {
    if (!raw || typeof raw !== 'object') continue
    const snap = raw.snap && typeof raw.snap === 'object' ? raw.snap : raw
    out.push({
      name: String(raw.name || snap.name || '').trim(),
      spanNs: snap.spanNs ?? snap.span_ns ?? null,
      migrations: snap.migrations ?? null,
      loadBalance: snap.loadBalanceScore ?? snap.load_balance_score ?? null,
      tickHealth: snap.tickHealth ?? snap.tick_health ?? '',
      tasks: snap.tasks ?? null,
    })
  }
  return out
}

/** Top tasks by CPU% keyed by display name. */
export function topTasksCpuByName(trace, limit = 10, lo = null, hi = null) {
  if (!trace?.segByMergeKey) return new Map()
  const total = (lo != null && hi != null)
    ? Math.max(1, hi - lo)
    : Math.max(1, trace.timeMax - trace.timeMin)
  const accum = new Map()
  for (const [mk, segs] of trace.segByMergeKey) {
    const repr = taskReprGet(trace, mk) ?? mk
    const { name } = parseTaskName(repr)
    if (isIdleTaskName(name) || name === 'TICK') continue
    let t = 0
    for (const s of segs) {
      if (lo != null && hi != null) {
        if (s.end <= lo || s.start >= hi) continue
        t += Math.min(s.end, hi) - Math.max(s.start, lo)
      } else {
        t += s.end - s.start
      }
    }
    if (t > 0) accum.set(mk, t)
  }
  const sorted = [...accum.entries()].sort((a, b) => b[1] - a[1])
  const picked = applyRowLimit(sorted, limit)
  const out = new Map()
  for (const [mk, t] of picked) {
    const name = taskDisplayName(taskReprGet(trace, mk) ?? mk)
    out.set(name, 100.0 * t / total)
  }
  return out
}

function fmtSignedTime(deltaNs, scale) {
  if (deltaNs === 0) return '0'
  const sign = deltaNs > 0 ? '+' : '−'
  return `${sign}${formatTimeTrim(Math.abs(deltaNs), scale)}`
}

function fmtSignedInt(delta) {
  if (delta === 0) return '0'
  return delta > 0 ? `+${delta}` : `−${Math.abs(delta)}`
}

function fmtSignedPct(delta) {
  if (Math.abs(delta) < 0.05) return '0.0 pp'
  const sign = delta >= 0 ? '+' : '−'
  return `${sign}${Math.abs(delta).toFixed(1)} pp`
}

function fmtSignedRate(rateA, rateB) {
  if (rateA == null || rateB == null || rateA < 0 || rateB < 0) return '—'
  const d = rateA - rateB
  if (Math.abs(d) < 0.005) return '0'
  const sign = d >= 0 ? '+' : '−'
  return `${sign}${Math.abs(d).toFixed(2)}/s`
}

function perSecond(count, spanNs) {
  if (spanNs == null || spanNs <= 0) return null
  return Number(count) / (Number(spanNs) / 1e9)
}

function fmtRatePerS(rate) {
  if (rate == null) return '—'
  if (Math.abs(rate) < 0.005) return '0/s'
  return `${rate.toFixed(2)}/s`
}

function blockingTotalNs(trace, lo, hi) {
  if (!trace?.segByMergeKey) return 0
  let total = 0
  for (const [mk, segs] of trace.segByMergeKey) {
    const repr = taskReprGet(trace, mk) ?? mk
    const { name } = parseTaskName(repr)
    if (isIdleTaskName(name) || name === 'TICK') continue
    for (const gap of blockingTimeSamples(segs, lo, hi)) total += gap
  }
  return total
}

function fmtBlockingPerS(blockNs, spanNs, scale) {
  if (spanNs <= 0) return '—'
  const perS = Math.round(blockNs / (spanNs / 1e9))
  return `${formatTimeTrim(perS, scale)}/s`
}

function fmtBlockingPerSDelta(ba, bb, sa, sb, scale) {
  if (sa <= 0 || sb <= 0) return '—'
  const ra = Math.round(ba / (sa / 1e9))
  const rb = Math.round(bb / (sb / 1e9))
  const d = ra - rb
  if (d === 0) return '0'
  return `${fmtSignedTime(d, scale)}/s`
}

function rangeForTab(tab, scopeEnabled) {
  if (!scopeEnabled || !tab) return { lo: null, hi: null }
  return cursorRangeForCursors(tab.cursors)
}

function fmtLbScore(v) {
  return v == null ? '—' : `${Number(v).toFixed(1)}%`
}

function fmtLbSigma(v) {
  return v == null ? '—' : `${Number(v).toFixed(1)}%`
}

export function buildSummaryCompareRows(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false, deadlines = null) {
  const ra = rangeForTab(tabA, scopeEnabled)
  const rb = rangeForTab(tabB, scopeEnabled)
  const a = traceSummarySnapshot(traceA, ra.lo, ra.hi)
  const b = traceSummarySnapshot(traceB, rb.lo, rb.hi)
  if (!a || !b) return []
  const scale = a.timeScale || b.timeScale || 'ns'
  const scoreDelta = (a.loadBalanceScore != null && b.loadBalanceScore != null)
    ? fmtSignedPct(a.loadBalanceScore - b.loadBalanceScore)
    : '—'
  const sigmaDelta = (a.loadBalanceSigma != null && b.loadBalanceSigma != null)
    ? fmtSignedPct(a.loadBalanceSigma - b.loadBalanceSigma)
    : '—'
  const csRateA = perSecond(a.contextSwitches, a.spanNs)
  const csRateB = perSecond(b.contextSwitches, b.spanNs)
  const migRateA = perSecond(a.migrations, a.spanNs)
  const migRateB = perSecond(b.migrations, b.spanNs)
  const blockNsA = blockingTotalNs(traceA, ra.lo, ra.hi)
  const blockNsB = blockingTotalNs(traceB, rb.lo, rb.hi)
  return [
    {
      label: scopeEnabled ? 'Span (cursor range)' : 'Span',
      a: formatTimeTrim(a.spanNs, scale),
      b: formatTimeTrim(b.spanNs, scale),
      delta: fmtSignedTime(a.spanNs - b.spanNs, scale),
    },
    { label: 'Tasks', a: a.tasks, b: b.tasks, delta: fmtSignedInt(a.tasks - b.tasks) },
    { label: 'Segments', a: a.segments, b: b.segments, delta: fmtSignedInt(a.segments - b.segments) },
    { label: 'STI events', a: a.stiEvents, b: b.stiEvents, delta: fmtSignedInt(a.stiEvents - b.stiEvents) },
    {
      label: 'Context switches',
      a: a.contextSwitches,
      b: b.contextSwitches,
      delta: fmtSignedInt(a.contextSwitches - b.contextSwitches),
    },
    {
      label: 'Context switches /s',
      a: fmtRatePerS(csRateA),
      b: fmtRatePerS(csRateB),
      delta: fmtSignedRate(csRateA, csRateB),
    },
    {
      label: 'Core gap avg',
      a: formatTimeTrim(a.gapAvgNs, scale),
      b: formatTimeTrim(b.gapAvgNs, scale),
      delta: fmtSignedTime(a.gapAvgNs - b.gapAvgNs, scale),
    },
    {
      label: 'Core gap max',
      a: formatTimeTrim(a.gapMaxNs, scale),
      b: formatTimeTrim(b.gapMaxNs, scale),
      delta: fmtSignedTime(a.gapMaxNs - b.gapMaxNs, scale),
    },
    {
      label: 'Migrations (total)',
      a: a.migrations,
      b: b.migrations,
      delta: fmtSignedInt(a.migrations - b.migrations),
    },
    {
      label: 'Migrations /s',
      a: fmtRatePerS(migRateA),
      b: fmtRatePerS(migRateB),
      delta: fmtSignedRate(migRateA, migRateB),
    },
    {
      label: 'Migrated tasks',
      a: a.migratedTasks,
      b: b.migratedTasks,
      delta: fmtSignedInt(a.migratedTasks - b.migratedTasks),
    },
    {
      label: 'Blocking time /s',
      a: fmtBlockingPerS(blockNsA, a.spanNs, scale),
      b: fmtBlockingPerS(blockNsB, b.spanNs, scale),
      delta: fmtBlockingPerSDelta(blockNsA, blockNsB, a.spanNs, b.spanNs, scale),
    },
    {
      label: 'Load Balance Score',
      a: fmtLbScore(a.loadBalanceScore),
      b: fmtLbScore(b.loadBalanceScore),
      delta: scoreDelta,
    },
    {
      label: 'Load Balance σ',
      a: fmtLbSigma(a.loadBalanceSigma),
      b: fmtLbSigma(b.loadBalanceSigma),
      delta: sigmaDelta,
    },
    {
      label: 'Tick health',
      a: String(a.tickHealth || 'unknown').toUpperCase(),
      b: String(b.tickHealth || 'unknown').toUpperCase(),
      delta: '—',
    },
    {
      label: 'Tick mode',
      a: a.tickMode,
      b: b.tickMode,
      delta: '—',
    },
    {
      label: 'Tick count',
      a: a.tickCount,
      b: b.tickCount,
      delta: fmtSignedInt(a.tickCount - b.tickCount),
    },
    {
      label: 'Missed ticks (est.)',
      a: a.missedTicks,
      b: b.missedTicks,
      delta: fmtSignedInt(a.missedTicks - b.missedTicks),
    },
    ...analysisCompareSummaryRows(traceA, traceB, tabA, tabB, scopeEnabled, scale, deadlines),
  ]
}

function analysisCompareExtras(traceA, traceB, tabA, tabB, scopeEnabled, deadlines = null, rowLimit = 15) {
  const ra = rangeForTab(tabA, scopeEnabled)
  const rb = rangeForTab(tabB, scopeEnabled)
  return compareAnalysisTables(traceA, traceB, ra.lo, ra.hi, rb.lo, rb.hi, deadlines, rowLimit)
}

function fmtCompareP99(ns, task, scale) {
  const text = formatTimeTrim(ns || 0, scale)
  const name = String(task || '').trim()
  return name ? `${text} (${name})` : text
}

function analysisCompareSummaryRows(traceA, traceB, tabA, tabB, scopeEnabled, scale, deadlines = null) {
  if (!traceA || !traceB) return []
  const extras = analysisCompareExtras(traceA, traceB, tabA, tabB, scopeEnabled, deadlines)
  const m = extras.metrics || {}
  const ra = rangeForTab(tabA, scopeEnabled)
  const rb = rangeForTab(tabB, scopeEnabled)
  const a = traceSummarySnapshot(traceA, ra.lo, ra.hi)
  const b = traceSummarySnapshot(traceB, rb.lo, rb.hi)
  const mutexA = m.mutex_ns_a || 0
  const mutexB = m.mutex_ns_b || 0
  return [
    {
      label: 'Response P99 (worst task)',
      a: fmtCompareP99(m.response_p99_a || 0, m.response_p99_task_a, scale),
      b: fmtCompareP99(m.response_p99_b || 0, m.response_p99_task_b, scale),
      delta: fmtSignedTime((m.response_p99_a || 0) - (m.response_p99_b || 0), scale),
    },
    {
      label: 'Mutex blocking (total)',
      a: formatTimeTrim(mutexA, scale),
      b: formatTimeTrim(mutexB, scale),
      delta: fmtSignedTime(mutexA - mutexB, scale),
    },
    {
      label: 'Mutex blocking /s',
      a: fmtBlockingPerS(mutexA, a?.spanNs || 0, scale),
      b: fmtBlockingPerS(mutexB, b?.spanNs || 0, scale),
      delta: fmtBlockingPerSDelta(mutexA, mutexB, a?.spanNs || 0, b?.spanNs || 0, scale),
    },
    {
      label: 'Deadline misses',
      a: m.deadline_misses_a || 0,
      b: m.deadline_misses_b || 0,
      delta: fmtSignedInt((m.deadline_misses_a || 0) - (m.deadline_misses_b || 0)),
    },
  ]
}

export function buildResponseCompareRows(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false, deadlines = null, rowLimit = 15) {
  const extras = analysisCompareExtras(traceA, traceB, tabA, tabB, scopeEnabled, deadlines, rowLimit)
  const scale = traceA?.timeScale || traceB?.timeScale || 'ns'
  return (extras.response || []).map(r => ({
    name: r.name,
    a: formatTime(r.p99_a || 0, scale),
    b: formatTime(r.p99_b || 0, scale),
    delta: fmtSignedTime(r.delta_ns || 0, scale),
  }))
}

export function buildMutexBlockCompareRows(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false, deadlines = null, rowLimit = 15) {
  const extras = analysisCompareExtras(traceA, traceB, tabA, tabB, scopeEnabled, deadlines, rowLimit)
  const scale = traceA?.timeScale || traceB?.timeScale || 'ns'
  return (extras.mutex_block || []).map(r => ({
    name: r.name,
    a: formatTime(r.total_a || 0, scale),
    b: formatTime(r.total_b || 0, scale),
    delta: fmtSignedTime(r.delta_ns || 0, scale),
  }))
}

export function buildSharedPatternCompareRows(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false, deadlines = null, rowLimit = 15) {
  return analysisCompareExtras(traceA, traceB, tabA, tabB, scopeEnabled, deadlines, rowLimit).shared_patterns || []
}

export function buildTopTasksCompareRows(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false, limit = 10) {
  const ra = rangeForTab(tabA, scopeEnabled)
  const rb = rangeForTab(tabB, scopeEnabled)
  const rankA = topTasksCpuByName(traceA, limit, ra.lo, ra.hi)
  const rankB = topTasksCpuByName(traceB, limit, rb.lo, rb.hi)
  const mapA = isUnlimitedLimit(limit)
    ? rankA
    : topTasksCpuByName(traceA, 0, ra.lo, ra.hi)
  const mapB = isUnlimitedLimit(limit)
    ? rankB
    : topTasksCpuByName(traceB, 0, rb.lo, rb.hi)
  const names = new Set([...rankA.keys(), ...rankB.keys()])
  return [...names]
    .sort((x, y) => {
      const maxX = Math.max(mapA.get(x) || 0, mapB.get(x) || 0)
      const maxY = Math.max(mapA.get(y) || 0, mapB.get(y) || 0)
      return maxY - maxX || x.localeCompare(y)
    })
    .map((name) => {
      const cpuA = mapA.get(name)
      const cpuB = mapB.get(name)
      const aVal = cpuA ?? 0
      const bVal = cpuB ?? 0
      return {
        name,
        cpuA: cpuA != null ? cpuA.toFixed(1) : '—',
        cpuB: cpuB != null ? cpuB.toFixed(1) : '—',
        delta: fmtSignedPct(aVal - bVal),
      }
    })
}

export function buildCoreUtilCompareRows(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false) {
  const ra = rangeForTab(tabA, scopeEnabled)
  const rb = rangeForTab(tabB, scopeEnabled)
  const mapA = new Map(coreUtilPctRows(traceA, ra.lo, ra.hi).map(r => [r.core, r.pct]))
  const mapB = new Map(coreUtilPctRows(traceB, rb.lo, rb.hi).map(r => [r.core, r.pct]))
  const cores = [...new Set([...mapA.keys(), ...mapB.keys()])]
  cores.sort((a, b) => {
    const na = a.startsWith('Core_') ? parseInt(a.slice(5), 10) : NaN
    const nb = b.startsWith('Core_') ? parseInt(b.slice(5), 10) : NaN
    if (!Number.isNaN(na) && !Number.isNaN(nb)) return na - nb
    return a.localeCompare(b)
  })
  return cores.map((core) => {
    const pa = mapA.has(core) ? mapA.get(core) : null
    const pb = mapB.has(core) ? mapB.get(core) : null
    const aVal = pa ?? 0
    const bVal = pb ?? 0
    return {
      core,
      utilA: pa != null ? pa.toFixed(1) : '—',
      utilB: pb != null ? pb.toFixed(1) : '—',
      delta: (pa != null || pb != null) ? fmtSignedPct(aVal - bVal) : '—',
    }
  })
}

function signedRateDelta(rateA, rateB) {
  if (rateA < 0 || rateB < 0) return '—'
  const d = rateA - rateB
  if (Math.abs(d) < 0.005) return '0'
  return (d >= 0 ? '+' : '') + d.toFixed(2) + '/s'
}

function signedDwellDelta(dwellA, dwellB, timeScale) {
  if (dwellA < 0 || dwellB < 0) return '—'
  const d = dwellA - dwellB
  if (d === 0) return '0'
  const sign = d > 0 ? '+' : '−'
  return sign + formatTime(Math.abs(d), timeScale)
}

function fmtPrimary(row) {
  if (!row || row.primary == null) return '—'
  const pct = row.primaryPct != null ? ` ${Math.round(row.primaryPct)}%` : ''
  return `${row.primary}${pct}`
}

export function buildMigrationCompareRows(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false) {
  const ra = rangeForTab(tabA, scopeEnabled)
  const rb = rangeForTab(tabB, scopeEnabled)
  const mapA = new Map()
  const mapB = new Map()
  if (traceA) {
    for (const row of migrationRows(traceA, ra.lo, ra.hi)) {
      mapA.set(row.mk, row)
    }
  }
  if (traceB) {
    for (const row of migrationRows(traceB, rb.lo, rb.hi)) {
      mapB.set(row.mk, row)
    }
  }
  const keys = [...new Set([...mapA.keys(), ...mapB.keys()])]
  keys.sort((a, b) => {
    const na = (mapA.get(a) || mapB.get(a))?.name ?? taskLabelForMergeKey(traceA || traceB, a)
    const nb = (mapA.get(b) || mapB.get(b))?.name ?? taskLabelForMergeKey(traceA || traceB, b)
    return na.localeCompare(nb)
  })
  const timeScale = traceA?.timeScale || traceB?.timeScale || 'us'
  return keys.map((mk) => {
    const raRow = mapA.get(mk)
    const rbRow = mapB.get(mk)
    const ma = raRow?.migrations ?? 0
    const mb = rbRow?.migrations ?? 0
    const rateA = raRow?.ratePerS ?? -1
    const rateB = rbRow?.ratePerS ?? -1
    const dwellA = raRow?.avgDwellTu ?? -1
    const dwellB = rbRow?.avgDwellTu ?? -1
    return {
      mk,
      name: raRow?.name ?? rbRow?.name ?? taskLabelForMergeKey(traceA || traceB, mk),
      migrationsA: ma,
      migrationsB: mb,
      delta: ma - mb,
      rateA: raRow?.migrRate ?? '—',
      rateB: rbRow?.migrRate ?? '—',
      rateDelta: signedRateDelta(rateA, rateB),
      dwellA: raRow?.avgDwell ?? '—',
      dwellB: rbRow?.avgDwell ?? '—',
      dwellDelta: signedDwellDelta(dwellA, dwellB, timeScale),
      pingA: raRow?.pingPong ?? 0,
      pingB: rbRow?.pingPong ?? 0,
      coresA: raRow?.coreCount ?? '—',
      coresB: rbRow?.coreCount ?? '—',
      primaryA: fmtPrimary(raRow),
      primaryB: fmtPrimary(rbRow),
    }
  })
}

function blockingSummaryByName(trace, lo, hi) {
  const map = new Map()
  if (!trace?.segByMergeKey) return map
  const scale = trace.timeScale
  for (const [mk, segs] of trace.segByMergeKey) {
    const repr = taskReprGet(trace, mk) ?? mk
    const { name: tname } = parseTaskName(repr)
    if (isIdleTaskName(tname) || tname === 'TICK') continue
    const samples = blockingTimeSamples(segs, lo, hi)
    const summary = summarizeTimeSamples(samples, scale)
    if (!summary) continue
    const name = taskDisplayName(repr)
    map.set(name, {
      avgNs: summary.avgNs,
      maxNs: summary.maxNs,
      gaps: summary.count,
      avg: summary.avg,
      max: summary.max,
    })
  }
  return map
}

export function buildBlockingCompareRows(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false, limit = 15) {
  const ra = rangeForTab(tabA, scopeEnabled)
  const rb = rangeForTab(tabB, scopeEnabled)
  const mapA = blockingSummaryByName(traceA, ra.lo, ra.hi)
  const mapB = blockingSummaryByName(traceB, rb.lo, rb.hi)
  const names = [...new Set([...mapA.keys(), ...mapB.keys()])]
    .sort((a, b) => {
      const ga = Math.max(mapA.get(a)?.gaps ?? 0, mapB.get(a)?.gaps ?? 0)
      const gb = Math.max(mapB.get(b)?.gaps ?? 0, mapA.get(b)?.gaps ?? 0)
      return gb - ga || a.localeCompare(b)
    })
  const limited = applyRowLimit(names, limit)
  const scale = traceA?.timeScale || traceB?.timeScale || 'ns'
  return limited.map((name) => {
    const a = mapA.get(name)
    const b = mapB.get(name)
    const avgA = a?.avgNs ?? 0
    const avgB = b?.avgNs ?? 0
    return {
      name,
      gapsA: a?.gaps ?? 0,
      gapsB: b?.gaps ?? 0,
      avgA: a?.avg ?? '—',
      avgB: b?.avg ?? '—',
      maxA: a?.max ?? '—',
      maxB: b?.max ?? '—',
      delta: fmtSignedTime(avgA - avgB, scale),
    }
  })
}

function buildNamedMetricCompareRows(mapA, mapB, scale, limit, {
  sortKey = 'runs',
  deltaField = 'avgNs',
  deltaLabel = 'delta',
} = {}) {
  const names = applyRowLimit(
    [...new Set([...mapA.keys(), ...mapB.keys()])]
      .sort((a, b) => {
        const va = Math.max(mapA.get(a)?.[sortKey] ?? 0, mapB.get(a)?.[sortKey] ?? 0)
        const vb = Math.max(mapB.get(b)?.[sortKey] ?? 0, mapA.get(b)?.[sortKey] ?? 0)
        return vb - va || a.localeCompare(b)
      }),
    limit,
  )
  return names.map((name) => {
    const a = mapA.get(name)
    const b = mapB.get(name)
    const dA = a?.[deltaField] ?? 0
    const dB = b?.[deltaField] ?? 0
    return {
      name,
      runsA: a?.runs ?? 0,
      runsB: b?.runs ?? 0,
      avgA: a?.avg ?? '—',
      avgB: b?.avg ?? '—',
      maxA: a?.max ?? '—',
      maxB: b?.max ?? '—',
      [deltaLabel]: fmtSignedTime(dA - dB, scale),
    }
  })
}

export function buildExecutionCompareRows(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false, limit = 15) {
  const ra = rangeForTab(tabA, scopeEnabled)
  const rb = rangeForTab(tabB, scopeEnabled)
  const mapA = taskMetricCompareByName(traceA, execSliceSamples, ra.lo, ra.hi)
  const mapB = taskMetricCompareByName(traceB, execSliceSamples, rb.lo, rb.hi)
  const scale = traceA?.timeScale || traceB?.timeScale || 'ns'
  return buildNamedMetricCompareRows(mapA, mapB, scale, limit, {
    sortKey: 'runs',
    deltaField: 'maxNs',
    deltaLabel: 'deltaMax',
  }).map(row => ({
    name: row.name,
    runsA: row.runsA,
    runsB: row.runsB,
    avgA: row.avgA,
    avgB: row.avgB,
    maxA: row.maxA,
    maxB: row.maxB,
    deltaMax: row.deltaMax,
  }))
}

export function buildInterArrivalCompareRows(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false, limit = 15) {
  const ra = rangeForTab(tabA, scopeEnabled)
  const rb = rangeForTab(tabB, scopeEnabled)
  const mapA = taskMetricCompareByName(traceA, interArrivalSamples, ra.lo, ra.hi, { runsFromStarts: true })
  const mapB = taskMetricCompareByName(traceB, interArrivalSamples, rb.lo, rb.hi, { runsFromStarts: true })
  const scale = traceA?.timeScale || traceB?.timeScale || 'ns'
  return buildNamedMetricCompareRows(mapA, mapB, scale, limit, {
    sortKey: 'runs',
    deltaField: 'avgNs',
    deltaLabel: 'delta',
  })
}

function preemptionTotalsByVictim(trace, lo, hi) {
  const map = new Map()
  const { rows } = preemptionChainRows(trace, lo, hi)
  for (const row of rows) {
    const cur = map.get(row.victim) || { count: 0, totalNs: 0 }
    cur.count += row.count
    cur.totalNs += row.totalNs
    map.set(row.victim, cur)
  }
  return map
}

export function buildPreemptionCompareRows(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false, limit = 15) {
  const ra = rangeForTab(tabA, scopeEnabled)
  const rb = rangeForTab(tabB, scopeEnabled)
  const mapA = preemptionTotalsByVictim(traceA, ra.lo, ra.hi)
  const mapB = preemptionTotalsByVictim(traceB, rb.lo, rb.hi)
  const names = applyRowLimit(
    [...new Set([...mapA.keys(), ...mapB.keys()])]
      .sort((a, b) => (mapB.get(b)?.count ?? 0) - (mapA.get(a)?.count ?? 0) || a.localeCompare(b)),
    limit,
  )
  const scale = traceA?.timeScale || traceB?.timeScale || 'ns'
  return names.map((name) => {
    const a = mapA.get(name)
    const b = mapB.get(name)
    const ca = a?.count ?? 0
    const cb = b?.count ?? 0
    return {
      name,
      countA: ca,
      countB: cb,
      delta: fmtSignedInt(ca - cb),
      totalA: a ? formatTime(a.totalNs, scale) : '—',
      totalB: b ? formatTime(b.totalNs, scale) : '—',
    }
  })
}

function syncSummary(trace, lo, hi) {
  if (!trace?.hasSyncObjectInstrumentation) {
    return { objects: 0, holds: 0, issues: 0, queue: 0, mutex: 0, sem: 0, bounces: 0 }
  }
  const rows = syncObjectStatsRows(trace, lo, hi)
  const out = { objects: rows.length, holds: 0, issues: 0, queue: 0, mutex: 0, sem: 0, bounces: 0 }
  for (const row of rows) {
    out.holds += row.holdCount
    out.issues += row.issueCount
    out.bounces += row.bounceCount
    if (row.kind === 'queue') out.queue++
    else if (row.kind === 'mutex') out.mutex++
    else if (row.kind === 'sem') out.sem++
  }
  return out
}

export function buildSyncCompareRows(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false) {
  const ra = rangeForTab(tabA, scopeEnabled)
  const rb = rangeForTab(tabB, scopeEnabled)
  const a = syncSummary(traceA, ra.lo, ra.hi)
  const b = syncSummary(traceB, rb.lo, rb.hi)
  return [
    { label: 'Sync objects', a: a.objects, b: b.objects, delta: fmtSignedInt(a.objects - b.objects) },
    { label: 'Holds (paired)', a: a.holds, b: b.holds, delta: fmtSignedInt(a.holds - b.holds) },
    { label: 'Issues', a: a.issues, b: b.issues, delta: fmtSignedInt(a.issues - b.issues) },
    { label: 'Core Affinity Violations (bounce)', a: a.bounces, b: b.bounces, delta: fmtSignedInt(a.bounces - b.bounces) },
    { label: 'Mutex objects', a: a.mutex, b: b.mutex, delta: fmtSignedInt(a.mutex - b.mutex) },
    { label: 'Semaphore objects', a: a.sem, b: b.sem, delta: fmtSignedInt(a.sem - b.sem) },
    { label: 'Queue objects', a: a.queue, b: b.queue, delta: fmtSignedInt(a.queue - b.queue) },
  ]
}

// Drop fixed-decimal padding from a formatted time (`945.000 µs` -> `945 µs`);
// leaves `3.292 ms` and non-time strings alone. Mirrors parser.py::_trim_time_pad.
const _TIME_PAD_RE = /^(-?\d+)\.(\d+)( (?:ns|us|µs|μs|ms|s))$/
function trimTimePad(v) {
  const m = String(v ?? '').match(_TIME_PAD_RE)
  if (!m) return String(v ?? '')
  const frac = m[2].replace(/0+$/, '')
  return frac ? `${m[1]}.${frac}${m[3]}` : `${m[1]}${m[3]}`
}

function csvCell(v) {
  const s = trimTimePad(v)
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`
  return s
}

function htmlCell(v) {
  return trimTimePad(v)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function normalizeCompareTables(tables = {}) {
  return {
    summary: tables.summary || [],
    top: tables.top || tables.topTasks || [],
    coreUtil: tables.coreUtil || [],
    migrations: tables.migrations || [],
    execution: tables.execution || [],
    blocking: tables.blocking || [],
    interArrival: tables.interArrival || [],
    preemption: tables.preemption || [],
    sync: tables.sync || [],
    response: tables.response || [],
    mutex_block: tables.mutex_block || tables.mutexBlock || [],
    shared_patterns: tables.shared_patterns || tables.sharedPatterns || [],
    trends: tables.trends || tables.trend || [],
    shape: tables.shape || null,
  }
}

function sharedPatternCells(row) {
  if (!row || typeof row !== 'object' || Array.isArray(row)) {
    const cells = Array.isArray(row) ? row : []
    return {
      task: cells[0] ?? '',
      kind: cells[1] ?? '',
      countA: cells[2] ?? '',
      countB: cells[3] ?? '',
      reason: cells[4] ?? '',
    }
  }
  return {
    task: row.task || row.name || '',
    kind: row.kind || '',
    countA: row.count_a ?? row.countA ?? '',
    countB: row.count_b ?? row.countB ?? '',
    reason: row.reason || '',
  }
}

function trendCells(row) {
  if (Array.isArray(row)) {
    return {
      name: row[0] ?? '',
      tasks: row[1] ?? '—',
      migrations: row[2] ?? '—',
      loadBalance: row[3] ?? '—',
      tickHealth: row[4] ?? '—',
      spanNs: row[5] ?? '—',
    }
  }
  const lb = row?.loadBalance ?? row?.load_balance
  let lbText = '—'
  if (typeof lb === 'number') lbText = `${Math.round(lb)}%`
  else if (lb != null && lb !== '') lbText = String(lb)
  return {
    name: row?.name || '',
    tasks: row?.tasks ?? '—',
    migrations: row?.migrations ?? '—',
    loadBalance: lbText,
    tickHealth: row?.tickHealth || row?.tick_health || '—',
    spanNs: row?.spanNs ?? row?.span_ns ?? '—',
  }
}

/** Build all Trace Compare table sets (same as TraceCompareDialog export).
 *  Pass ``rowLimit`` 0/null for every row (HTML/CSV export). */
export function buildAllCompareTables(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false, deadlines = null, rowLimit = 15) {
  const cap = isUnlimitedLimit(rowLimit) ? 0 : rowLimit
  const topCap = isUnlimitedLimit(rowLimit) ? 0 : 10
  return {
    summary: buildSummaryCompareRows(traceA, traceB, tabA, tabB, scopeEnabled, deadlines),
    top: buildTopTasksCompareRows(traceA, traceB, tabA, tabB, scopeEnabled, topCap),
    coreUtil: buildCoreUtilCompareRows(traceA, traceB, tabA, tabB, scopeEnabled),
    migrations: buildMigrationCompareRows(traceA, traceB, tabA, tabB, scopeEnabled),
    execution: buildExecutionCompareRows(traceA, traceB, tabA, tabB, scopeEnabled, cap),
    blocking: buildBlockingCompareRows(traceA, traceB, tabA, tabB, scopeEnabled, cap),
    interArrival: buildInterArrivalCompareRows(traceA, traceB, tabA, tabB, scopeEnabled, cap),
    preemption: buildPreemptionCompareRows(traceA, traceB, tabA, tabB, scopeEnabled, cap),
    sync: buildSyncCompareRows(traceA, traceB, tabA, tabB, scopeEnabled),
    response: buildResponseCompareRows(traceA, traceB, tabA, tabB, scopeEnabled, deadlines, cap),
    mutex_block: buildMutexBlockCompareRows(traceA, traceB, tabA, tabB, scopeEnabled, deadlines, cap),
    shared_patterns: buildSharedPatternCompareRows(traceA, traceB, tabA, tabB, scopeEnabled, deadlines, cap),
    shape: compareTraceShapeInfo(traceA, traceB, tabA, tabB, scopeEnabled),
  }
}

/** Structural fingerprint of the two traces for the comparability check. */
export function compareTraceShapeInfo(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false) {
  const ra = rangeForTab(tabA, scopeEnabled)
  const rb = rangeForTab(tabB, scopeEnabled)
  const spanOf = (trace, r) => {
    if (!trace) return 0
    if (r && r.lo != null && r.hi != null) return Math.max(0, r.hi - r.lo)
    return Math.max(0, (trace.timeMax ?? 0) - (trace.timeMin ?? 0))
  }
  const names = trace => [...new Set(
    (trace?.tasks || []).map(mk => taskDisplayName(taskReprGet(trace, mk) || mk)),
  )].sort()
  return {
    cores_a: (traceA?.coreNames || []).length,
    cores_b: (traceB?.coreNames || []).length,
    task_names_a: names(traceA),
    task_names_b: names(traceB),
    span_a_ns: spanOf(traceA, ra),
    span_b_ns: spanOf(traceB, rb),
  }
}

/** Build CSV text for a trace-compare export. */
export function buildCompareCsv(nameA, nameB, scopeEnabled, tables = {}) {
  const t = normalizeCompareTables(tables)
  const notable = compareNotableChanges(t, 8, nameA, nameB) || {}
  const ident = notable.identity || {}
  const identA = ident.a || {}
  const identB = ident.b || {}
  const lines = []
  lines.push(`Baseline A (Trace A),${csvCell(identA.file || nameA)}`)
  lines.push(`Candidate B (Trace B),${csvCell(identB.file || nameB)}`)
  lines.push(`Delta formula,${csvCell(COMPARE_DELTA_FORMULA)}`)
  lines.push(`Metric glossary,${csvCell(COMPARE_METRIC_GLOSSARY)}`)
  lines.push(`Cursor scope per tab,${scopeEnabled ? 'yes' : 'no'}`)
  lines.push('')
  lines.push('Overview')
  lines.push(`Verdict,${csvCell(notable.verdict_label || 'SIMILAR')}`)
  for (const b of notable.verdict_bullets || []) {
    lines.push(`Verdict change,${csvCell(b.status)},${csvCell(b.label)},${csvCell(b.change)}`)
  }
  const comp = notable.comparability || {}
  lines.push(`Comparability,${comp.comparable === false ? 'WARNING' : 'ok'}`)
  for (const cw of comp.warnings || []) lines.push(`Comparability warning,${csvCell(cw)}`)
  const nxt = String(notable.next_investigation || '').trim()
  if (nxt) lines.push(`Next investigation,${csvCell(nxt)}`)
  const omitted = Number(notable.small_omitted_count || 0) || 0
  const cards = notable.cards || {}
  if (omitted || Number(cards.significant || 0)) {
    lines.push(
      'Significance note,Showing engineering-significant deltas only (small changes omitted)',
    )
  }
  lines.push(
    `Status cards,regressions ${Number(cards.regressions || 0)},`
    + `improvements ${Number(cards.improvements || 0)},`
    + `significant ${Number(cards.significant || 0)},`
    + `warnings ${Number(cards.warnings || 0)}`,
  )
  for (const warn of notable.warnings || []) {
    lines.push(`Warning,${csvCell(warn)}`)
  }
  lines.push('Status,Metric,Baseline A,Candidate B,Change')
  for (const row of notable.rows || []) {
    lines.push([
      csvCell(row.status), csvCell(row.label), csvCell(row.a),
      csvCell(row.b), csvCell(row.change),
    ].join(','))
  }
  const evRefs = []
  for (const row of t.shared_patterns || t.sharedPatterns || []) {
    let task = 'pattern'
    let reason = ''
    if (row && typeof row === 'object' && !Array.isArray(row)) {
      task = String(row.task || row.name || 'pattern')
      reason = String(row.reason || '')
    } else if (Array.isArray(row) && row.length >= 5) {
      task = String(row[0] || 'pattern')
      reason = String(row[4] || '')
    } else continue
    const low = reason.toLowerCase()
    if (low.includes(' ms') || low.includes(' µs') || low.includes(' us')
      || low.includes(' ns') || low.includes('jump:')) {
      evRefs.push([task, reason.slice(0, 120)])
    }
    if (evRefs.length >= 4) break
  }
  if (evRefs.length) {
    lines.push('')
    lines.push('Evidence refs')
    lines.push('Finding,Evidence / Time')
    for (const [lab, ttxt] of evRefs) {
      lines.push(`${csvCell(lab)},${csvCell(ttxt)}`)
    }
  }
  lines.push('')

  lines.push('Summary')
  lines.push('Metric,Baseline A,Candidate B,Δ')
  for (const row of t.summary) {
    lines.push([csvCell(row.label), csvCell(row.a), csvCell(row.b), csvCell(row.delta)].join(','))
  }

  lines.push('')
  lines.push('Top Tasks')
  lines.push('Task,CPU A (%),CPU B (%),Δ (pp)')
  for (const row of t.top) {
    lines.push([csvCell(row.name), csvCell(row.cpuA), csvCell(row.cpuB), csvCell(row.delta)].join(','))
  }

  lines.push('')
  lines.push('Core Util')
  lines.push('Core,Util A (%),Util B (%),Δ (pp)')
  for (const row of t.coreUtil) {
    lines.push([csvCell(row.core), csvCell(row.utilA), csvCell(row.utilB), csvCell(row.delta)].join(','))
  }

  lines.push('')
  lines.push('Core Migrations')
  lines.push('Task,Migrations A,Migrations B,Δ,Rate A,Rate B,Rate Δ,Dwell A,Dwell B,Dwell Δ,Ping-pong A,Ping-pong B,Cores A,Cores B,Primary A,Primary B')
  for (const row of t.migrations) {
    lines.push([
      csvCell(row.name),
      csvCell(row.migrationsA),
      csvCell(row.migrationsB),
      csvCell(row.delta),
      csvCell(row.rateA),
      csvCell(row.rateB),
      csvCell(row.rateDelta),
      csvCell(row.dwellA),
      csvCell(row.dwellB),
      csvCell(row.dwellDelta),
      csvCell(row.pingA),
      csvCell(row.pingB),
      csvCell(row.coresA),
      csvCell(row.coresB),
      csvCell(row.primaryA),
      csvCell(row.primaryB),
    ].join(','))
  }

  lines.push('')
  lines.push('Execution Time')
  lines.push('Task,Runs A,Runs B,Avg A,Avg B,Max A,Max B,Δ max')
  for (const row of t.execution) {
    lines.push([
      csvCell(row.name), csvCell(row.runsA), csvCell(row.runsB),
      csvCell(row.avgA), csvCell(row.avgB), csvCell(row.maxA), csvCell(row.maxB),
      csvCell(row.deltaMax),
    ].join(','))
  }

  lines.push('')
  lines.push('Blocking Time')
  lines.push('Task,Gaps A,Gaps B,Avg A,Avg B,Max A,Max B,Δ avg')
  for (const row of t.blocking) {
    lines.push([
      csvCell(row.name), csvCell(row.gapsA), csvCell(row.gapsB),
      csvCell(row.avgA), csvCell(row.avgB), csvCell(row.maxA), csvCell(row.maxB),
      csvCell(row.delta),
    ].join(','))
  }

  lines.push('')
  lines.push('Inter-Arrival Time')
  lines.push('Task,Runs A,Runs B,Avg A,Avg B,Max A,Max B,Δ avg')
  for (const row of t.interArrival) {
    lines.push([
      csvCell(row.name), csvCell(row.runsA), csvCell(row.runsB),
      csvCell(row.avgA), csvCell(row.avgB), csvCell(row.maxA), csvCell(row.maxB),
      csvCell(row.delta),
    ].join(','))
  }

  lines.push('')
  lines.push('Preemption Chains')
  lines.push('Victim,Count A,Count B,Δ,Total A,Total B')
  for (const row of t.preemption) {
    lines.push([
      csvCell(row.name), csvCell(row.countA), csvCell(row.countB), csvCell(row.delta),
      csvCell(row.totalA), csvCell(row.totalB),
    ].join(','))
  }

  lines.push('')
  lines.push('Sync Objects')
  lines.push('Metric,Baseline A,Candidate B,Δ')
  for (const row of t.sync) {
    lines.push([csvCell(row.label), csvCell(row.a), csvCell(row.b), csvCell(row.delta)].join(','))
  }

  lines.push('')
  lines.push('Response P99')
  lines.push('Task,P99 A,P99 B,Δ')
  for (const row of t.response) {
    lines.push([csvCell(row.name), csvCell(row.a), csvCell(row.b), csvCell(row.delta)].join(','))
  }

  lines.push('')
  lines.push('Mutex Blocking')
  lines.push('Task,Total A,Total B,Δ')
  for (const row of t.mutex_block) {
    lines.push([csvCell(row.name), csvCell(row.a), csvCell(row.b), csvCell(row.delta)].join(','))
  }

  lines.push('')
  lines.push('Shared Patterns')
  lines.push('Task,Kind,Count A,Count B,Description')
  for (const row of t.shared_patterns) {
    const c = sharedPatternCells(row)
    lines.push([csvCell(c.task), csvCell(c.kind), csvCell(c.countA), csvCell(c.countB), csvCell(c.reason)].join(','))
  }

  lines.push('')
  lines.push('Trends')
  lines.push('Trace,Tasks,Migrations,Load balance,Tick health,Span')
  for (const row of t.trends) {
    const c = trendCells(row)
    lines.push([
      csvCell(c.name), csvCell(c.tasks), csvCell(c.migrations),
      csvCell(c.loadBalance), csvCell(c.tickHealth), csvCell(c.spanNs),
    ].join(','))
  }

  return lines.join('\n')
}

const _COMPARE_HTML_EXTRA_CSS = `
.report.report-compare { max-width: min(1280px, 100%); }
.report-card { overflow: hidden; }
.table-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; max-width: 100%; }
table { border-collapse: collapse; width: max-content; min-width: 100%; }
th, td {
  border-bottom: 1px solid var(--line);
  padding: 6px 8px;
  font-size: 12px;
  text-align: right;
  white-space: nowrap;
}
th:first-child, td:first-child { text-align: left; }
thead th { background: #f1f5fb; font-weight: 600; }
thead th:first-child, tbody td:first-child { position: sticky; left: 0; z-index: 1; }
thead th:first-child { background: #f1f5fb; }
tbody td:first-child { background: #fff; }
tbody tr:nth-child(even) td { background: #f7f9fc; }
tbody tr:nth-child(even) td:first-child { background: #f7f9fc; }
.empty { text-align: center; color: var(--muted); white-space: normal; }
.detail-note { margin: 6px 0 10px; font-size: 12px; color: var(--muted); line-height: 1.45; }
.overview-why { color: var(--muted); margin: 0 0 10px; }
.overview-sub { margin: 12px 0 6px; font-size: 13px; color: #123355; }
.overview-formula { color: var(--muted); font-size: 12px; margin: 0 0 10px; }
.col-baseline { color: #2a6fb2; }
.col-candidate { color: #6b4ea8; }
.status-cards { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0 12px; }
.status-card {
  flex: 1 1 120px; border: 1px solid var(--line); border-radius: 8px;
  padding: 8px 10px; background: #fff;
}
.status-card .n { font-size: 20px; font-weight: 700; line-height: 1.1; }
.status-regressed { border-left: 4px solid #c0392b; }
.status-improved { border-left: 4px solid #1f6b45; }
.status-changed { border-left: 4px solid #2a6fb2; }
.status-warn { border-left: 4px solid #c87a12; }
.badge-regressed { background: #fde8e6; color: #9b2c2c; }
.badge-changed { background: #e8eef7; color: #123355; }
.compare-decision {
  margin: 0 0 12px; padding: 8px 10px; border-radius: 6px;
  background: rgba(52, 152, 219, 0.10); font-size: 12px; line-height: 1.45; color: #3d4f63;
}
.compare-decision-identity { font-size: 11px; color: #5f6f82; }
.compare-decision-counts { margin-top: 4px; font-weight: 600; color: #123355; }
.compare-decision-largest { margin-top: 4px; color: #182230; }
.compare-decision-why, .compare-decision-next { margin-top: 2px; font-size: 11px; color: #5f6f82; }
.compare-decision-sig { margin-top: 2px; font-size: 10px; color: #7a8690; }
.compare-verdict { margin-top: 6px; }
.compare-verdict-chip {
  display: inline-block; padding: 2px 10px; border-radius: 999px;
  font-weight: 700; font-size: 12px; letter-spacing: 0.04em; color: #fff;
}
.compare-verdict-chip.tone-regressed { background: #c0392b; }
.compare-verdict-chip.tone-improved { background: #1f6b45; }
.compare-verdict-chip.tone-mixed { background: #c87a12; }
.compare-verdict-chip.tone-neutral { background: #6b7a8d; }
.compare-verdict-bullets { margin: 6px 0 0; padding-left: 18px; }
.compare-verdict-bullets li { margin: 1px 0; color: #182230; }
.compare-verdict-bullets li.reg { color: #9b2c2c; }
.compare-verdict-bullets li.imp { color: #1f6b45; }
.compare-verdict-none { margin-top: 6px; color: #5f6f82; font-size: 11px; }
/* Redesigned verdict: full-width banner + stat cards (arrow glyph carries
   meaning without colour). */
.compare-verdict-banner {
  display: flex; gap: 10px; align-items: flex-start;
  margin: 6px 0 10px; padding: 10px 12px; border-radius: 8px; border: 1px solid #d9e0ea;
}
.compare-verdict-glyph { font-size: 15px; line-height: 1.3; }
.compare-verdict-main { display: flex; flex-direction: column; gap: 2px; }
.compare-verdict-label { font-weight: 700; font-size: 13px; letter-spacing: 0.04em; }
.compare-verdict-sentence { font-size: 12px; color: #3d4f63; }
.compare-verdict-banner.tone-regressed { background: #fdecea; border-color: #e6b3ac; }
.compare-verdict-banner.tone-regressed .compare-verdict-label,
.compare-verdict-banner.tone-regressed .compare-verdict-glyph { color: #b23125; }
.compare-verdict-banner.tone-improved { background: #e9f5ee; border-color: #a9d3ba; }
.compare-verdict-banner.tone-improved .compare-verdict-label,
.compare-verdict-banner.tone-improved .compare-verdict-glyph { color: #1f6b45; }
.compare-verdict-banner.tone-mixed { background: #fdf3e2; border-color: #e2c48a; }
.compare-verdict-banner.tone-mixed .compare-verdict-label,
.compare-verdict-banner.tone-mixed .compare-verdict-glyph { color: #b4670e; }
.compare-verdict-banner.tone-neutral { background: #eef1f5; border-color: #d1d8e0; }
.compare-cards { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0 10px; }
.compare-card {
  flex: 1 1 120px; border: 1px solid var(--line); border-radius: 8px;
  padding: 8px 10px; background: #fff; display: flex; flex-direction: column; gap: 3px;
}
.compare-card-k { font-size: 10px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.compare-card-v { font-size: 18px; font-weight: 700; line-height: 1.1; }
.compare-card.tone-regressed { border-left: 4px solid #c0392b; }
.compare-card.tone-regressed .compare-card-v { color: #b23125; }
.compare-card.tone-improved { border-left: 4px solid #1f6b45; }
.compare-card.tone-improved .compare-card-v { color: #1f6b45; }
.compare-card.tone-warn { border-left: 4px solid #c87a12; }
.compare-card.tone-warn .compare-card-v { color: #b4670e; }
.compare-card-mover { flex: 2 1 200px; }
.compare-card-mover .compare-card-v { font-size: 13px; font-weight: 600; }
.compare-next { margin: 6px 0 4px; font-size: 12px; font-weight: 600; color: #123355; }
.compare-comparability-warn {
  margin: 0 0 8px; padding: 8px 10px; border-radius: 6px;
  background: #fdf0e2; border-left: 4px solid #c87a12; color: #6b4a12;
}
.compare-comparability-head { font-weight: 700; }
.compare-comparability-warn ul { margin: 4px 0 0; padding-left: 18px; }
.compare-comparability-warn li { margin: 1px 0; }
.compare-chart { margin: 0 0 12px; overflow-x: auto; }
.compare-chart svg { max-width: 100%; height: auto; display: block; }
.table-tools { margin: 8px 0 12px; }
.table-toolbar {
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 6px;
}
.table-search {
  font: inherit; font-size: 12px; padding: 4px 8px; border: 1px solid var(--line);
  border-radius: 6px; min-width: 160px;
}
.table-check { font-size: 12px; color: var(--muted); display: inline-flex; gap: 4px; align-items: center; }
.table-count { font-size: 12px; color: var(--muted); margin-left: auto; }
.table-scroll table { min-width: 100%; }
.sortable { cursor: pointer; }
.sortable:hover { color: var(--accent); }
@media (prefers-color-scheme: dark) {
  .compare-card { background: var(--paper); }
  .compare-card.tone-regressed .compare-card-v { color: #e5776a; }
  .compare-card.tone-improved .compare-card-v { color: #57c191; }
  .compare-card.tone-warn .compare-card-v { color: #e0a44a; }
  .compare-next { color: #cfe1f7; }
  .compare-comparability-warn {
    background: #2a2114; border-left-color: #c87a12; color: #e6cfa6;
  }
  .table-search { background: var(--paper); color: var(--ink); }
}
${HTML_REPORT_TOC_CSS}
`.trim()

// Same grouping as the Trace Compare dialog's nav rail (pageTabs `group`).
export const COMPARE_TOC_GROUPS = [
  ['Overview', ['Overview', 'Summary']],
  ['CPU & Cores', ['Top Tasks', 'Core Utilisation', 'Core Migrations']],
  ['Timing', ['Execution Time', 'Blocking Time', 'Inter-Arrival Time', 'Response P99']],
  ['Contention', ['Preemption Chains', 'Sync Objects', 'Mutex Blocking']],
  ['Cross-trace', ['Shared Patterns', 'Trends']],
]

function _rowsOrEmpty(rows, cols, mapFn, empty) {
  if (!rows.length) return `<tr><td colspan="${cols}" class="empty">${htmlCell(empty)}</td></tr>`
  return rows.map(mapFn).join('')
}

function _cardHtml(title, thead, tbody, leadHtml = '', note = '') {
  const noteHtml = note ? `<p class="detail-note">${htmlCell(note)}</p>` : ''
  return `<section class="report-card"><h2>${htmlCell(title)}</h2>`
    + noteHtml
    + (leadHtml || '')
    + `<table><thead><tr>${thead}</tr></thead>`
    + `<tbody>${tbody}</tbody></table></section>`
}

/** Build standalone HTML report for trace compare. */
export function buildCompareHtml(nameA, nameB, scopeEnabled, tables = {}) {
  const t = normalizeCompareTables(tables)
  const scopeNote = scopeEnabled
    ? 'Each side uses its own tab cursor range (C1–Cn) when 2+ cursors are placed.'
    : 'Full trace span on each side.'

  const notable = compareNotableChanges(t, 8, nameA, nameB) || {}
  const ident = notable.identity || {}
  const identA = ident.a || {}
  const identB = ident.b || {}
  const cards = notable.cards || {}
  const badge = { Regressed: 'badge-regressed', Improved: 'badge-ok', Changed: 'badge-changed' }
  const identRows = [
    ['File', identA.file || nameA, identB.file || nameB],
    ['Range', identA.span || '—', identB.span || '—'],
    ['Tick mode', identA.tick_mode || '—', identB.tick_mode || '—'],
  ]
  const notableRows = (notable.rows || []).filter(r => r && typeof r === 'object')
  const verdictLabel = String(notable.verdict_label || 'SIMILAR')
  const verdictTone = String(notable.verdict_tone || 'neutral')
  const compWarnings = (notable.comparability || {}).warnings || []
  const nextInv = String(notable.next_investigation || '').trim()
  const omitted = Number(notable.small_omitted_count || 0) || 0
  const warnHtml = (notable.warnings || []).map(w => `<p class="warn-banner">${htmlCell(w)}</p>`).join('')
  const notableBody = notableRows.length
    ? notableRows.map(r => {
      const cls = badge[r.status] || 'badge-changed'
      return `<tr><td><span class="badge ${cls}">${htmlCell(r.status)}</span></td>`
        + `<td>${htmlCell(r.label)}</td><td>${htmlCell(r.a)}</td>`
        + `<td>${htmlCell(r.b)}</td><td>${htmlCell(r.change)}</td></tr>`
    }).join('')
    : '<tr><td colspan="5" class="empty">No significant improvements or regressions above threshold</td></tr>'
  const evRefs = []
  for (const row of t.shared_patterns || t.sharedPatterns || []) {
    let task = 'pattern'
    let reason = ''
    if (row && typeof row === 'object' && !Array.isArray(row)) {
      task = String(row.task || row.name || 'pattern')
      reason = String(row.reason || '')
    } else if (Array.isArray(row) && row.length >= 5) {
      task = String(row[0] || 'pattern')
      reason = String(row[4] || '')
    } else continue
    const low = reason.toLowerCase()
    if (low.includes(' ms') || low.includes(' µs') || low.includes(' us')
      || low.includes(' ns') || low.includes('jump:')) {
      evRefs.push([task, reason.slice(0, 120)])
    }
    if (evRefs.length >= 4) break
  }
  const evHtml = evRefs.length
    ? '<h3 class="overview-sub">Evidence refs</h3>'
      + '<div class="table-scroll"><table><thead><tr><th>Finding</th>'
      + '<th>Evidence / Time</th></tr></thead><tbody>'
      + evRefs.map(r => `<tr><td>${htmlCell(r[0])}</td><td>${htmlCell(r[1])}</td></tr>`).join('')
      + '</tbody></table></div>'
    : ''
  const verdictSentence = String(notable.verdict || '').replace(/^Overall:\s*/i, '').trim()
  const verdictGlyph = { regressed: '▲', improved: '▼', mixed: '◆' }[verdictTone] || '●'
  const moverRow = notableRows.find(r => r.status === 'Regressed')
    || notableRows.find(r => r.status === 'Improved') || null
  const moverText = moverRow ? `${moverRow.label}: ${moverRow.change}` : '—'
  const overviewHtml = `<section class="report-card"><h2>Overview</h2>`
    + '<p class="detail-note">Verdict, identity, and engineering-significant '
    + 'deltas between Baseline A and Candidate B.</p>'
    + (compWarnings.length
      ? '<div class="compare-comparability-warn"><div class="compare-comparability-head">'
        + '⚠ Traces may not be directly comparable</div><ul>'
        + compWarnings.map(w => `<li>${htmlCell(w)}</li>`).join('') + '</ul></div>'
      : '')
    + `<div class="compare-verdict-banner tone-${htmlCell(verdictTone)}">`
    + `<span class="compare-verdict-glyph">${verdictGlyph}</span>`
    + '<span class="compare-verdict-main">'
    + `<span class="compare-verdict-label">${htmlCell(verdictLabel)}</span>`
    + (verdictSentence ? `<span class="compare-verdict-sentence">${htmlCell(verdictSentence)}</span>` : '')
    + '</span></div>'
    + (nextInv ? `<p class="compare-next">${htmlCell(nextInv)}</p>` : '')
    + ((omitted || Number(cards.significant || 0))
      ? '<p class="overview-formula">Showing engineering-significant deltas only (small changes omitted)</p>'
      : '')
    + `<p class="overview-formula">${htmlCell(COMPARE_DELTA_FORMULA)}</p>`
    + '<div class="compare-cards">'
    + `<div class="compare-card tone-regressed"><span class="compare-card-k">Regressions</span><span class="compare-card-v">${Number(cards.regressions || 0)}</span></div>`
    + `<div class="compare-card tone-improved"><span class="compare-card-k">Improvements</span><span class="compare-card-v">${Number(cards.improvements || 0)}</span></div>`
    + `<div class="compare-card tone-warn"><span class="compare-card-k">Warnings</span><span class="compare-card-v">${Number(cards.warnings || 0)}</span></div>`
    + `<div class="compare-card compare-card-mover"><span class="compare-card-k">Biggest mover</span><span class="compare-card-v">${htmlCell(moverText)}</span></div>`
    + '</div>'
    + warnHtml
    + '<h3 class="overview-sub">Comparison identity</h3>'
    + '<div class="table-scroll"><table><thead><tr><th></th>'
    + '<th class="col-baseline">Baseline A</th><th class="col-candidate">Candidate B</th></tr></thead><tbody>'
    + _rowsOrEmpty(identRows, 3,
      r => `<tr><td>${htmlCell(r[0])}</td><td>${htmlCell(r[1])}</td><td>${htmlCell(r[2])}</td></tr>`,
      'No identity')
    + '</tbody></table></div>'
    + evHtml
    + '<h3 class="overview-sub">Notable Changes</h3>'
    + '<div class="table-scroll"><table><thead><tr><th>Status</th><th>Metric</th>'
    + '<th class="col-baseline">Baseline A</th><th class="col-candidate">Candidate B</th>'
    + '<th>Change</th></tr></thead><tbody>'
    + notableBody
    + '</tbody></table></div></section>'

  const summaryHtml = _rowsOrEmpty(t.summary, 4,
    r => `<tr><td>${htmlCell(r.label)}</td><td>${htmlCell(r.a)}</td><td>${htmlCell(r.b)}</td><td>${htmlCell(r.delta)}</td></tr>`,
    'No data')

  const topHtml = _rowsOrEmpty(t.top, 4,
    r => `<tr><td>${htmlCell(r.name)}</td><td>${htmlCell(r.cpuA)}</td><td>${htmlCell(r.cpuB)}</td><td>${htmlCell(r.delta)}</td></tr>`,
    'No user tasks in either trace')

  const coreHtml = _rowsOrEmpty(t.coreUtil, 4,
    r => `<tr><td>${htmlCell(r.core)}</td><td>${htmlCell(r.utilA)}</td><td>${htmlCell(r.utilB)}</td><td>${htmlCell(r.delta)}</td></tr>`,
    'No core utilisation data')

  const migHtml = _rowsOrEmpty(t.migrations, 16,
    r => `<tr><td>${htmlCell(r.name)}</td><td>${htmlCell(r.migrationsA)}</td><td>${htmlCell(r.migrationsB)}</td><td>${htmlCell(r.delta)}</td><td>${htmlCell(r.rateA)}</td><td>${htmlCell(r.rateB)}</td><td>${htmlCell(r.rateDelta)}</td><td>${htmlCell(r.dwellA)}</td><td>${htmlCell(r.dwellB)}</td><td>${htmlCell(r.dwellDelta)}</td><td>${htmlCell(r.pingA)}</td><td>${htmlCell(r.pingB)}</td><td>${htmlCell(r.coresA)}</td><td>${htmlCell(r.coresB)}</td><td>${htmlCell(r.primaryA)}</td><td>${htmlCell(r.primaryB)}</td></tr>`,
    'No migrated tasks in either trace')

  const execHtml = _rowsOrEmpty(t.execution, 8,
    r => `<tr><td>${htmlCell(r.name)}</td><td>${htmlCell(r.runsA)}</td><td>${htmlCell(r.runsB)}</td><td>${htmlCell(r.avgA)}</td><td>${htmlCell(r.avgB)}</td><td>${htmlCell(r.maxA)}</td><td>${htmlCell(r.maxB)}</td><td>${htmlCell(r.deltaMax)}</td></tr>`,
    'No execution samples in either trace')

  const blockHtml = _rowsOrEmpty(t.blocking, 8,
    r => `<tr><td>${htmlCell(r.name)}</td><td>${htmlCell(r.gapsA)}</td><td>${htmlCell(r.gapsB)}</td><td>${htmlCell(r.avgA)}</td><td>${htmlCell(r.avgB)}</td><td>${htmlCell(r.maxA)}</td><td>${htmlCell(r.maxB)}</td><td>${htmlCell(r.delta)}</td></tr>`,
    'No blocking samples in either trace')

  const interHtml = _rowsOrEmpty(t.interArrival, 8,
    r => `<tr><td>${htmlCell(r.name)}</td><td>${htmlCell(r.runsA)}</td><td>${htmlCell(r.runsB)}</td><td>${htmlCell(r.avgA)}</td><td>${htmlCell(r.avgB)}</td><td>${htmlCell(r.maxA)}</td><td>${htmlCell(r.maxB)}</td><td>${htmlCell(r.delta)}</td></tr>`,
    'No inter-arrival samples in either trace')

  const preHtml = _rowsOrEmpty(t.preemption, 6,
    r => `<tr><td>${htmlCell(r.name)}</td><td>${htmlCell(r.countA)}</td><td>${htmlCell(r.countB)}</td><td>${htmlCell(r.delta)}</td><td>${htmlCell(r.totalA)}</td><td>${htmlCell(r.totalB)}</td></tr>`,
    'No preemption chains in either trace')

  const syncHtml = _rowsOrEmpty(t.sync, 4,
    r => `<tr><td>${htmlCell(r.label)}</td><td>${htmlCell(r.a)}</td><td>${htmlCell(r.b)}</td><td>${htmlCell(r.delta)}</td></tr>`,
    'No sync instrumentation in either trace')

  const responseHtml = _rowsOrEmpty(t.response, 4,
    r => `<tr><td>${htmlCell(r.name)}</td><td>${htmlCell(r.a)}</td><td>${htmlCell(r.b)}</td><td>${htmlCell(r.delta)}</td></tr>`,
    'No response samples in either trace')

  const mutexHtml = _rowsOrEmpty(t.mutex_block, 4,
    r => `<tr><td>${htmlCell(r.name)}</td><td>${htmlCell(r.a)}</td><td>${htmlCell(r.b)}</td><td>${htmlCell(r.delta)}</td></tr>`,
    'No mutex blocking in either trace')

  const sharedHtml = _rowsOrEmpty(t.shared_patterns, 5, (r) => {
    const c = sharedPatternCells(r)
    return `<tr><td>${htmlCell(c.task)}</td><td>${htmlCell(c.kind)}</td><td>${htmlCell(c.countA)}</td><td>${htmlCell(c.countB)}</td><td>${htmlCell(c.reason)}</td></tr>`
  }, 'No shared anomaly patterns')

  const trendHtml = _rowsOrEmpty(t.trends, 6, (r) => {
    const c = trendCells(r)
    return `<tr><td>${htmlCell(c.name)}</td><td>${htmlCell(c.tasks)}</td><td>${htmlCell(c.migrations)}</td><td>${htmlCell(c.loadBalance)}</td><td>${htmlCell(c.tickHealth)}</td><td>${htmlCell(c.spanNs)}</td></tr>`
  }, 'Open 2+ traces to trend summaries')

  const utilSvg = compareCoreUtilChartSvg(compareCoreUtilChartRows(t))
  const p99Svg = compareP99DeltaChartSvg(compareP99DeltaChartRows(t, 12))
  const sumSvg = compareSummaryChangeBarsSvg(compareSummaryChangeBarRows(t, 8))
  const heatSvg = compareMigrationHeatmapSvg(compareMigrationHeatmapRows(t.migrations, 12))
  const decisionHtml = compareSummaryDecisionHtml(t, nameA, nameB)
  const utilLead = utilSvg ? `<div class="compare-chart">${utilSvg}</div>` : ''
  const p99Lead = p99Svg ? `<div class="compare-chart">${p99Svg}</div>` : ''
  const sumLead = (decisionHtml || '') + (sumSvg ? `<div class="compare-chart">${sumSvg}</div>` : '')
  const heatLead = heatSvg ? `<div class="compare-chart">${heatSvg}</div>` : ''
  const migTop = filterCompareMigrationRows(t.migrations, 'count', 'top', '', 10)
  let migLead = heatLead
  if (migTop.rows?.length) {
    const migTh = (migTop.headers || []).map(h => `<th>${htmlCell(h)}</th>`).join('')
    const migBody = _rowsOrEmpty(migTop.rows, (migTop.headers || []).length,
      r => `<tr>${r.map(c => `<td>${htmlCell(c)}</td>`).join('')}</tr>`,
      'No migration count changes')
    migLead += `<h3 class="overview-sub">Largest changes (count &amp; rate)</h3>`
      + `<p class="overview-formula">${migTop.shown} of ${migTop.total} migrated tasks</p>`
      + `<div class="table-scroll"><table><thead><tr>${migTh}</tr></thead><tbody>${migBody}</tbody></table></div>`
      + '<h3 class="overview-sub">All columns</h3>'
  }

  const report = btfHtmlReportDocument('Trace Compare', [
    '<!--TOC-->',
    overviewHtml,
    _cardHtml('Summary', '<th>Metric</th><th>Baseline A</th><th>Candidate B</th><th>Δ</th>', summaryHtml, sumLead,
      `KPI-style totals and rates. Δ = Baseline A − Candidate B (positive means A is numerically larger). ${COMPARE_NOTE_SIGMA}`),
    _cardHtml('Top Tasks', '<th>Task</th><th>CPU A (%)</th><th>CPU B (%)</th><th>Δ (pp)</th>', topHtml, '',
      'Highest CPU consumers excluding IDLE/TICK. Δ is percentage points (pp).'),
    _cardHtml('Core Utilisation', '<th>Core</th><th>Util A (%)</th><th>Util B (%)</th><th>Δ (pp)</th>', coreHtml, utilLead,
      'Per-core active util % excluding IDLE/TICK over each side\'s scoped wall-clock span.'),
    _cardHtml('Core Migrations',
      '<th>Task</th><th>Migr A</th><th>Migr B</th><th>Δ</th><th>Rate A</th><th>Rate B</th><th>Rate Δ</th><th>Dwell A</th><th>Dwell B</th><th>Dwell Δ</th><th>Ping A</th><th>Ping B</th><th>Cores A</th><th>Cores B</th><th>Primary A</th><th>Primary B</th>',
      migHtml, migLead,
      `Migration count, rate, dwell, ping-pong, and primary-core affinity for tasks that ran on more than one core. ${COMPARE_NOTE_MIGRATION}`),
    _cardHtml('Execution Time',
      '<th>Task</th><th>Runs A</th><th>Runs B</th><th>Avg A</th><th>Avg B</th><th>Max A</th><th>Max B</th><th>Δ max</th>',
      execHtml, '',
      'Per-slice run durations between consecutive context switches.'),
    _cardHtml('Blocking Time',
      '<th>Task</th><th>Gaps A</th><th>Gaps B</th><th>Avg A</th><th>Avg B</th><th>Max A</th><th>Max B</th><th>Δ avg</th>',
      blockHtml, '',
      'Off-CPU gaps between consecutive slices of the same task (preemption, wait, or scheduling delay).'),
    _cardHtml('Inter-Arrival Time',
      '<th>Task</th><th>Runs A</th><th>Runs B</th><th>Avg A</th><th>Avg B</th><th>Max A</th><th>Max B</th><th>Δ avg</th>',
      interHtml, '',
      'Time between consecutive activations of the same task (slice start to next slice start).'),
    _cardHtml('Preemption Chains',
      '<th>Victim</th><th>Count A</th><th>Count B</th><th>Δ</th><th>Total A</th><th>Total B</th>',
      preHtml, '',
      'Victim/preemptor pairs for off-CPU gaps on the same core.'),
    _cardHtml('Sync Objects', '<th>Metric</th><th>Baseline A</th><th>Candidate B</th><th>Δ</th>', syncHtml, '',
      `Mutex, semaphore, and queue STI instrumentation totals. ${COMPARE_NOTE_STI}`),
    _cardHtml('Response P99', '<th>Task</th><th>P99 A</th><th>P99 B</th><th>Δ</th>', responseHtml, p99Lead,
      `Heuristic ready→completion P99 from adjacent slices (not an explicit BTF release/completion pair). ${COMPARE_NOTE_P99}`),
    _cardHtml('Mutex Blocking', '<th>Task</th><th>Total A</th><th>Total B</th><th>Δ</th>', mutexHtml, '',
      'Total mutex-attributed blocking time per task.'),
    _cardHtml('Shared Patterns',
      '<th>Task</th><th>Kind</th><th>Count A</th><th>Count B</th><th>Description</th>',
      sharedHtml, '',
      'Anomaly kinds present on both sides with counts and a short reason.'),
    _cardHtml('Trends',
      '<th>Trace</th><th>Tasks</th><th>Migrations</th><th>Load balance</th><th>Tick health</th><th>Span</th>',
      trendHtml, '',
      'Multi-trace summary when two or more traces are open.'),
    HTML_REPORT_TOC_SCRIPT,
    HTML_REPORT_INTERACTIVE_SCRIPT,
  ].join('\n'), {
    subtitle: `Baseline A: ${nameA} vs Candidate B: ${nameB} · ${scopeNote}`,
    extraCss: _COMPARE_HTML_EXTRA_CSS,
    docTitle: 'BTFViewer — Trace Compare',
    reportClass: 'report-compare',
  })
  return htmlApplyCollapsibleToc(report, ['Overview', 'Summary'], COMPARE_TOC_GROUPS)
}

export function downloadCompareCsv(nameA, nameB, scopeEnabled, tables = {}) {
  const text = buildCompareCsv(nameA, nameB, scopeEnabled, tables)
  const blob = new Blob([text], { type: 'text/csv;charset=utf-8' })
  _downloadBlob(`trace-compare-${_timestamp()}.csv`, blob)
}

export function downloadCompareHtml(nameA, nameB, scopeEnabled, tables = {}) {
  const html = buildCompareHtml(nameA, nameB, scopeEnabled, tables)
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  _downloadBlob(`trace-compare-${_timestamp()}.html`, blob)
}

function _downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function _timestamp() {
  const d = new Date()
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}
