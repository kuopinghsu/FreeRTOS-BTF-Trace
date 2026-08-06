/**
 * User-defined task deadlines and CPU budget checks.
 */

import { formatTimeFixed, nsToTraceUnits } from './timeFormat.js'
import { parseTaskName, taskDisplayName, taskReprGet, isIdleTaskName } from './colors.js'

/**
 * @param {object} trace
 * @param {object} settings { taskDeadlines?: Record<string, number>, cpuBudgetPct?: number }
 *   taskDeadlines values are nanoseconds (Settings → Display label).
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
      // Settings store true nanoseconds; segment times are trace-native units.
      const limitTu = nsToTraceUnits(limitNs, scale)
      for (const seg of segs) {
        if (lo != null && hi != null && (seg.end <= lo || seg.start >= hi)) continue
        const dur = seg.end - seg.start
        if (dur > limitTu) {
          sliceViolations.push({
            mk,
            label: disp,
            startNs: seg.start,
            endNs: seg.end,
            durationNs: dur,
            limitNs,
            limitTu,
            overTu: dur - limitTu,
            duration: formatTimeFixed(dur, scale),
            limit: formatTimeFixed(limitTu, scale),
            overBy: formatTimeFixed(dur - limitTu, scale),
            segment: seg,
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
          pctRaw: pct,
          budgetRaw: cpuBudget,
          pct: pct.toFixed(1),
          budgetPct: cpuBudget.toFixed(1),
        })
      }
    }
  }

  sliceViolations.sort((a, b) => b.durationNs - a.durationNs)
  cpuViolations.sort((a, b) => b.pctRaw - a.pctRaw)
  return { sliceViolations, cpuViolations }
}

/** Annotation note for a Slice-over-deadline stats row click (desktop parity). */
export function deadlineSliceAnnotationNote(trace, v) {
  if (!v) return ''
  const scale = trace?.timeScale || 'ns'
  const at = formatTimeFixed(v.startNs, scale)
  return `${v.label} over deadline: ${v.duration} > ${v.limit} at ${at}`
}
