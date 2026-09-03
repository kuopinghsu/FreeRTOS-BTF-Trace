/**
 * Scheduling-load statistics (parity with parser.py):
 *   Switch Reason Breakdown       — review item A1
 *   Scheduling Load Over Time     — review items A2 + A9
 */
import { bisectLeft } from './bisect.js'
import { taskDisplayName, taskReprGet } from './colors.js'
import { classifyOffCpuGaps, OFFCPU_GAP_KINDS } from './statsAnalysis.js'
import { coreUtilOverTime } from './uxExplore.js'
import { giniCoefficient, coreUtilStddev } from './loadBalanceGauge.js'

const SCALE_S = { ns: 1e-9, us: 1e-6, ms: 1e-3, s: 1 }

/** Per-task off-CPU switch-reason counts — parity with `_switch_reason_rows` (A1).
 * @returns {Array<{mk, name, preempted, blocked, suspended, periodWait, unknown, total, preemptRate}>}
 */
export function switchReasonRows(trace, lo = null, hi = null) {
  const span = (lo != null && hi != null)
    ? Math.max(1, hi - lo)
    : Math.max(1, (trace?.timeMax ?? 0) - (trace?.timeMin ?? 0))
  const spanS = span * (SCALE_S[trace?.timeScale] || 1e-9)
  const byMk = classifyOffCpuGaps(trace, lo, hi)
  const rows = []
  for (const [mk, gaps] of byMk) {
    const counts = Object.fromEntries(OFFCPU_GAP_KINDS.map(k => [k, 0]))
    for (const [, kind] of gaps) counts[kind] += 1
    const name = taskDisplayName(taskReprGet(trace, mk) || mk)
    rows.push({
      mk,
      name,
      preempted: counts.preempted,
      blocked: counts.blocked,
      suspended: counts.suspended,
      periodWait: counts.period_wait,
      unknown: counts.unknown,
      total: gaps.length,
      preemptRate: spanS > 0 ? counts.preempted / spanS : 0,
    })
  }
  rows.sort((a, b) => b.preempted - a.preempted || b.total - a.total || a.name.localeCompare(b.name))
  return rows
}

/** Per-time-bin scheduling load — parity with `_sched_load_over_time_rows` (A2 + A9).
 * @returns {Array<{start, stop, jumpNs, ctx, ctxPerS, sigmaPct, lbScore, busiestCore, peakPct}>}
 */
export function schedLoadOverTimeRows(trace, events, lo = null, hi = null) {
  const grid = coreUtilOverTime(events, [...(trace?.coreNames || [])], lo, hi)
  const bins = grid.bins || []
  const cores = grid.cores || [...(trace?.coreNames || [])]
  if (!bins.length) return []
  const coreSegStarts = new Map()
  for (const c of cores) {
    const segs = trace?.coreSegs?.get?.(c) || []
    coreSegStarts.set(c, segs.map(s => s.start).sort((a, b) => a - b))
  }
  const unitS = SCALE_S[trace?.timeScale] || 1e-9
  return bins.map((b) => {
    const b0 = Math.trunc(b.start || 0)
    const b1 = Math.trunc(b.stop || b0 + 1)
    let ctx = 0
    for (const c of cores) {
      const starts = coreSegStarts.get(c) || []
      ctx += bisectLeft(starts, b1) - bisectLeft(starts, b0)
    }
    const cells = b.cells || {}
    const pcts = cores.map(c => Number(cells[c]?.pct || 0))
    const sigma = pcts.length >= 2 ? coreUtilStddev(pcts) : 0
    let lbScore = null
    if (pcts.length >= 2 && pcts.reduce((a, x) => a + x, 0) > 0) {
      lbScore = Math.max(0, 100 * (1 - giniCoefficient(pcts)))
    }
    const spanS = Math.max(1, b1 - b0) * unitS
    return {
      start: b0,
      stop: b1,
      jumpNs: b0,
      ctx,
      ctxPerS: spanS > 0 ? ctx / spanS : 0,
      sigmaPct: sigma,
      lbScore,
      busiestCore: b.peak_core || '',
      peakPct: Number(b.peak_pct || 0),
    }
  })
}