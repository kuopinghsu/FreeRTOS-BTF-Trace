/**
 * User-defined task deadlines and CPU budget checks.
 */

import { formatTime } from './timeFormat.js'
import { parseTaskName, taskDisplayName, taskMergeKey, taskReprGet, isIdleTaskName } from './colors.js'

/**
 * @param {object} trace
 * @param {object} settings { taskDeadlines?: Record<string, number>, cpuBudgetPct?: number }
 * @param {number|null} lo cursor range lo
 * @param {number|null} hi cursor range hi
 */
export function computeDeadlineViolations(trace, settings = {}, lo = null, hi = null) {
  if (!trace?.segByMergeKey) return { sliceViolations: [], cpuViolations: [] }

  const deadlines = settings.taskDeadlines || {}
  const cpuBudget = Number(settings.cpuBudgetPct)
  const scale = trace.timeScale
  const sliceViolations = []
  const cpuViolations = []

  for (const [mk, segs] of trace.segByMergeKey) {
    const repr = taskReprGet(trace, mk) ?? mk
    const { name } = parseTaskName(repr)
    if (isIdleTaskName(name) || name === 'TICK') continue

    const disp = taskDisplayName(repr)
    const keys = [mk, name, disp]
    let limitNs = null
    for (const k of keys) {
      if (deadlines[k] != null) {
        limitNs = Number(deadlines[k])
        break
      }
    }
    if (limitNs != null && Number.isFinite(limitNs) && limitNs > 0) {
      for (const seg of segs) {
        if (lo != null && hi != null && (seg.end <= lo || seg.start >= hi)) continue
        const dur = seg.end - seg.start
        if (dur > limitNs) {
          sliceViolations.push({
            mk,
            label: disp,
            startNs: seg.start,
            endNs: seg.end,
            durationNs: dur,
            limitNs,
            duration: formatTime(dur, scale),
            limit: formatTime(limitNs, scale),
            overBy: formatTime(dur - limitNs, scale),
          })
        }
      }
    }

    if (Number.isFinite(cpuBudget) && cpuBudget > 0) {
      const span = (lo != null && hi != null)
        ? Math.max(1, hi - lo)
        : Math.max(1, trace.timeMax - trace.timeMin)
      let active = 0
      for (const seg of segs) {
        if (lo != null && hi != null) {
          if (seg.end <= lo || seg.start >= hi) continue
          active += Math.min(seg.end, hi) - Math.max(seg.start, lo)
        } else {
          active += seg.end - seg.start
        }
      }
      const pct = 100 * active / span
      if (pct > cpuBudget) {
        cpuViolations.push({
          mk,
          label: disp,
          pct: pct.toFixed(1),
          budgetPct: cpuBudget.toFixed(1),
        })
      }
    }
  }

  sliceViolations.sort((a, b) => b.durationNs - a.durationNs)
  cpuViolations.sort((a, b) => Number(b.pct) - Number(a.pct))
  return { sliceViolations, cpuViolations }
}
