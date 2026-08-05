/**
 * Compare summary and per-task metrics between two loaded traces.
 * Optional lo/hi per trace for cursor-scoped compare.
 */

import { formatTime, isStiTagChannel } from '../renderer/TimelineRenderer.js'
import { parseTaskName, taskDisplayName, taskLabelForMergeKey, taskReprGet, isIdleTaskName } from './colors.js'
import { schedulingStats, blockingTimeSamples, preemptionChainRows } from './statsAnalysis.js'
import { isMigratedTask, migrationRows } from './migrationAnalysis.js'
import { syncObjectStatsRows } from './syncObjectAnalysis.js'
import { getPlacedCursors, segFullyInRange, segOverlapNs, traceMapGet } from './statsRange.js'
import { tickHealthReport } from './tickHealth.js'
import { loadBalanceMetrics } from './loadBalanceGauge.js'

export function cursorRangeForCursors(cursors) {
  const placed = getPlacedCursors(cursors || [])
  if (placed.length < 2) return { lo: null, hi: null }
  const sorted = [...placed].sort((a, b) => a - b)
  return { lo: sorted[0], hi: sorted[sorted.length - 1] }
}

/** Per-core active util % excluding IDLE/TICK (same as StatisticsPanel._coreUtilRows). */
export function coreUtilPctRows(trace, lo = null, hi = null) {
  if (!trace?.coreNames?.length) return []
  const total = (lo != null && hi != null)
    ? (hi - lo)
    : (trace.timeMax - trace.timeMin)
  if (total <= 0) return []
  return trace.coreNames.map((core) => {
    const segs = traceMapGet(trace.coreSegs, core) || []
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
  const sorted = [...accum.entries()].sort((a, b) => b[1] - a[1]).slice(0, limit)
  const out = new Map()
  for (const [mk, t] of sorted) {
    const name = taskDisplayName(taskReprGet(trace, mk) ?? mk)
    out.set(name, 100.0 * t / total)
  }
  return out
}

function fmtSignedTime(deltaNs, scale) {
  if (deltaNs === 0) return '0'
  const sign = deltaNs > 0 ? '+' : '−'
  return `${sign}${formatTime(Math.abs(deltaNs), scale)}`
}

function fmtSignedInt(delta) {
  if (delta === 0) return '0'
  return delta > 0 ? `+${delta}` : String(delta)
}

function fmtSignedPct(delta) {
  if (Math.abs(delta) < 0.05) return '0.0'
  const sign = delta > 0 ? '+' : ''
  return `${sign}${delta.toFixed(1)}`
}

function rangeForTab(tab, scopeEnabled) {
  if (!scopeEnabled || !tab) return { lo: null, hi: null }
  return cursorRangeForCursors(tab.cursors)
}

function fmtLbScore(v) {
  return v == null ? '—' : `${Math.round(v)}%`
}

function fmtLbSigma(v) {
  return v == null ? '—' : `${v.toFixed(1)}%`
}

export function buildSummaryCompareRows(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false) {
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
  return [
    {
      label: scopeEnabled ? 'Span (cursor range)' : 'Span',
      a: formatTime(a.spanNs, scale),
      b: formatTime(b.spanNs, scale),
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
      label: 'Core gap avg',
      a: formatTime(a.gapAvgNs, scale),
      b: formatTime(b.gapAvgNs, scale),
      delta: fmtSignedTime(a.gapAvgNs - b.gapAvgNs, scale),
    },
    {
      label: 'Core gap max',
      a: formatTime(a.gapMaxNs, scale),
      b: formatTime(b.gapMaxNs, scale),
      delta: fmtSignedTime(a.gapMaxNs - b.gapMaxNs, scale),
    },
    {
      label: 'Migrations (total)',
      a: a.migrations,
      b: b.migrations,
      delta: fmtSignedInt(a.migrations - b.migrations),
    },
    {
      label: 'Migrated tasks',
      a: a.migratedTasks,
      b: b.migratedTasks,
      delta: fmtSignedInt(a.migratedTasks - b.migratedTasks),
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
  ]
}

export function buildTopTasksCompareRows(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false, limit = 10) {
  const ra = rangeForTab(tabA, scopeEnabled)
  const rb = rangeForTab(tabB, scopeEnabled)
  const mapA = topTasksCpuByName(traceA, limit, ra.lo, ra.hi)
  const mapB = topTasksCpuByName(traceB, limit, rb.lo, rb.hi)
  const names = new Set([...mapA.keys(), ...mapB.keys()])
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
    .slice(0, limit)
  const scale = traceA?.timeScale || traceB?.timeScale || 'ns'
  return names.map((name) => {
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
  const names = [...new Set([...mapA.keys(), ...mapB.keys()])]
    .sort((a, b) => {
      const va = Math.max(mapA.get(a)?.[sortKey] ?? 0, mapB.get(a)?.[sortKey] ?? 0)
      const vb = Math.max(mapB.get(b)?.[sortKey] ?? 0, mapA.get(b)?.[sortKey] ?? 0)
      return vb - va || a.localeCompare(b)
    })
    .slice(0, limit)
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
  const names = [...new Set([...mapA.keys(), ...mapB.keys()])]
    .sort((a, b) => (mapB.get(b)?.count ?? 0) - (mapA.get(a)?.count ?? 0) || a.localeCompare(b))
    .slice(0, limit)
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

function csvCell(v) {
  const s = String(v ?? '')
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`
  return s
}

function htmlCell(v) {
  return String(v ?? '')
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
  }
}

/** Build CSV text for a trace-compare export. */
export function buildCompareCsv(nameA, nameB, scopeEnabled, tables = {}) {
  const t = normalizeCompareTables(tables)
  const lines = []
  lines.push(`Trace A,${csvCell(nameA)}`)
  lines.push(`Trace B,${csvCell(nameB)}`)
  lines.push(`Cursor scope per tab,${scopeEnabled ? 'yes' : 'no'}`)
  lines.push('')

  lines.push('Summary')
  lines.push('Metric,Trace A,Trace B,Δ')
  for (const row of t.summary) {
    lines.push([csvCell(row.label), csvCell(row.a), csvCell(row.b), csvCell(row.delta)].join(','))
  }

  lines.push('')
  lines.push('Top Tasks')
  lines.push('Task,CPU% A,CPU% B,Δ')
  for (const row of t.top) {
    lines.push([csvCell(row.name), csvCell(row.cpuA), csvCell(row.cpuB), csvCell(row.delta)].join(','))
  }

  lines.push('')
  lines.push('Core Util')
  lines.push('Core,Util% A,Util% B,Δ')
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
  lines.push('Metric,Trace A,Trace B,Δ')
  for (const row of t.sync) {
    lines.push([csvCell(row.label), csvCell(row.a), csvCell(row.b), csvCell(row.delta)].join(','))
  }

  return lines.join('\n')
}

const _COMPARE_HTML_STYLE = `
  :root { --bg:#e9edf3; --paper:#fff; --ink:#182230; --muted:#5f6f82; --line:#d9e0ea; --header:#16324f; }
  * { box-sizing:border-box; }
  body { margin:0; padding:28px; font-family:"Segoe UI",Arial,sans-serif; color:var(--ink); background:var(--bg); }
  .report { max-width:min(1280px, 100%); margin:0 auto; }
  .report-head { background:linear-gradient(135deg,var(--header),#21496f); color:#f3f7fd; border-radius:14px; padding:20px 24px; margin-bottom:18px; }
  h1 { margin:0; font-size:26px; }
  .sub { margin-top:6px; color:#cfe1f7; font-size:13px; }
  .report-card { margin:14px 0; background:var(--paper); border:1px solid var(--line); border-radius:12px; padding:12px 14px; overflow:hidden; }
  h2 { margin:0 0 10px; color:#123355; font-size:17px; }
  .table-scroll { overflow-x:auto; -webkit-overflow-scrolling:touch; max-width:100%; }
  table { border-collapse:collapse; width:max-content; min-width:100%; }
  th,td { border-bottom:1px solid var(--line); padding:6px 8px; font-size:12px; text-align:right; white-space:nowrap; }
  th:first-child,td:first-child { text-align:left; }
  thead th { background:#f1f5fb; font-weight:600; }
  thead th:first-child, tbody td:first-child { position:sticky; left:0; background:#f1f5fb; z-index:1; }
  tbody td:first-child { background:#fff; }
  tbody tr:nth-child(even) td { background:#f7f9fc; }
  tbody tr:nth-child(even) td:first-child { background:#f7f9fc; }
  .empty { text-align:center; color:var(--muted); white-space:normal; }
`

function _rowsOrEmpty(rows, cols, mapFn, empty) {
  if (!rows.length) return `<tr><td colspan="${cols}" class="empty">${htmlCell(empty)}</td></tr>`
  return rows.map(mapFn).join('')
}

function _cardHtml(title, thead, tbody) {
  return `<section class="report-card"><h2>${htmlCell(title)}</h2>`
    + `<div class="table-scroll"><table><thead><tr>${thead}</tr></thead>`
    + `<tbody>${tbody}</tbody></table></div></section>`
}

/** Build standalone HTML report for trace compare. */
export function buildCompareHtml(nameA, nameB, scopeEnabled, tables = {}) {
  const t = normalizeCompareTables(tables)
  const scopeNote = scopeEnabled
    ? 'Each side uses its own tab cursor range (C1–Cn) when 2+ cursors are placed.'
    : 'Full trace span on each side.'

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

  return `<!doctype html>
<html><head><meta charset="utf-8"/><title>BTF Trace Compare</title><style>${_COMPARE_HTML_STYLE}</style></head>
<body><div class="report">
  <header class="report-head">
    <h1>Trace Compare</h1>
    <div class="sub">${htmlCell(nameA)} vs ${htmlCell(nameB)} · ${htmlCell(scopeNote)}</div>
  </header>
  ${_cardHtml('Summary', '<th>Metric</th><th>Trace A</th><th>Trace B</th><th>Δ</th>', summaryHtml)}
  ${_cardHtml('Top Tasks', '<th>Task</th><th>CPU% A</th><th>CPU% B</th><th>Δ</th>', topHtml)}
  ${_cardHtml('Core Util', '<th>Core</th><th>Util% A</th><th>Util% B</th><th>Δ</th>', coreHtml)}
  ${_cardHtml('Core Migrations',
    '<th>Task</th><th>Migr A</th><th>Migr B</th><th>Δ</th><th>Rate A</th><th>Rate B</th><th>Rate Δ</th><th>Dwell A</th><th>Dwell B</th><th>Dwell Δ</th><th>Ping A</th><th>Ping B</th><th>Cores A</th><th>Cores B</th><th>Primary A</th><th>Primary B</th>',
    migHtml)}
  ${_cardHtml('Execution Time',
    '<th>Task</th><th>Runs A</th><th>Runs B</th><th>Avg A</th><th>Avg B</th><th>Max A</th><th>Max B</th><th>Δ max</th>',
    execHtml)}
  ${_cardHtml('Blocking Time',
    '<th>Task</th><th>Gaps A</th><th>Gaps B</th><th>Avg A</th><th>Avg B</th><th>Max A</th><th>Max B</th><th>Δ avg</th>',
    blockHtml)}
  ${_cardHtml('Inter-Arrival Time',
    '<th>Task</th><th>Runs A</th><th>Runs B</th><th>Avg A</th><th>Avg B</th><th>Max A</th><th>Max B</th><th>Δ avg</th>',
    interHtml)}
  ${_cardHtml('Preemption Chains',
    '<th>Victim</th><th>Count A</th><th>Count B</th><th>Δ</th><th>Total A</th><th>Total B</th>',
    preHtml)}
  ${_cardHtml('Sync Objects', '<th>Metric</th><th>Trace A</th><th>Trace B</th><th>Δ</th>', syncHtml)}
</div></body></html>`
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
