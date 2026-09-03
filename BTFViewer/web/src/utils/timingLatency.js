/**
 * Timing-latency statistics (parity with parser.py):
 *   Activation Latency        — review item A3
 *   Ready-Gap (Starvation)    — review item A4
 */
import { taskDisplayName, taskReprGet } from './colors.js'
import { classifyOffCpuGaps } from './statsAnalysis.js'
import { sampleVariability } from './intervalAnalysis.js'
import { analyzeTaskPeriods } from './uxExplore.js'

function nearestRank(sorted, p) {
  if (!sorted.length) return 0
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(p * sorted.length) - 1))]
}

/** Per periodic task, distance of each activation from a fitted ideal periodic
 * grid `phi + k*T` — parity with `_activation_latency_rows` (A3).
 * @returns {Array<{mk,name,count,minNs,avgNs,maxNs,jitterNs,sigmaNs,p50Ns,p95Ns,p99Ns}>}
 */
export function activationLatencyRows(trace, events, lo = null, hi = null) {
  const periodByMk = new Map()
  for (const prow of analyzeTaskPeriods(events, 3)) {
    const mk = String(prow.mk || '')
    const t = Math.trunc(prow.expected_ns || 0)
    if (mk && t > 0) periodByMk.set(mk, t)
  }
  const startsByMk = new Map()
  for (const ev of events || []) {
    if (!ev || ev.kind !== 'inter') continue
    const mk = String(ev.mk || ev.task || '')
    if (!periodByMk.has(mk)) continue
    const s = Math.trunc(ev.start || 0)
    if (lo != null && hi != null && !(s >= lo && s <= hi)) continue
    if (!startsByMk.has(mk)) startsByMk.set(mk, [])
    startsByMk.get(mk).push(s)
  }
  const rows = []
  for (const [mk, starts] of startsByMk) {
    if (starts.length < 3) continue
    starts.sort((a, b) => a - b)
    const period = periodByMk.get(mk)
    const anchor = starts[0]
    const errs = starts
      .map(t => Math.abs(t - (anchor + Math.round((t - anchor) / period) * period)))
      .sort((a, b) => a - b)
    const n = errs.length
    const total = errs.reduce((s, e) => s + e, 0)
    const { jitter, sigma, p50, p99 } = sampleVariability(errs)
    rows.push({
      mk,
      name: taskDisplayName(taskReprGet(trace, mk) || mk),
      count: n,
      minNs: errs[0],
      avgNs: Math.round(total / n),
      maxNs: errs[n - 1],
      jitterNs: jitter,
      sigmaNs: Math.round(sigma),
      p50Ns: p50,
      p95Ns: nearestRank(errs, 0.95),
      p99Ns: p99,
    })
  }
  rows.sort((a, b) => b.maxNs - a.maxNs || b.avgNs - a.avgNs || a.name.localeCompare(b.name))
  return rows
}

const READY_GAP_KINDS = new Set(['preempted', 'blocked', 'unknown'])

/** Per task, off-CPU time it spent arguably able to run — parity with
 * `_ready_gap_rows` (A4). Keeps preempted / blocked / unknown gaps; drops
 * suspended and period_wait.
 * @returns {Array<{mk,name,count,longestNs,totalNs,avgNs,p95Ns,preemptPct}>}
 */
export function readyGapRows(trace, lo = null, hi = null) {
  const byMk = classifyOffCpuGaps(trace, lo, hi)
  const rows = []
  for (const [mk, gaps] of byMk) {
    const ready = gaps.filter(([, k]) => READY_GAP_KINDS.has(k)).map(([g]) => g).sort((a, b) => a - b)
    if (!ready.length) continue
    const preemptSum = gaps.filter(([, k]) => k === 'preempted').reduce((s, [g]) => s + g, 0)
    const n = ready.length
    const total = ready.reduce((s, g) => s + g, 0)
    rows.push({
      mk,
      name: taskDisplayName(taskReprGet(trace, mk) || mk),
      count: n,
      longestNs: ready[n - 1],
      totalNs: total,
      avgNs: Math.round(total / n),
      p95Ns: nearestRank(ready, 0.95),
      preemptPct: total > 0 ? (100 * preemptSum) / total : 0,
    })
  }
  rows.sort((a, b) => b.longestNs - a.longestNs || b.totalNs - a.totalNs || a.name.localeCompare(b.name))
  return rows
}
