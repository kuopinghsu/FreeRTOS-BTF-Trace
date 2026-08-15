/**
 * RTOS scheduling analysis helpers (parity with desktop btf_viewer.py).
 */

import { segFullyInRange } from './statsRange.js'
import { bisectLeft, bisectRight } from './bisect.js'
import { parseTaskName, taskMergeKey, taskDisplayName, isIdleTaskName, taskReprGet } from './colors.js'
import { formatTime } from './timeFormat.js'

/** @returns {{ prev: object|null, next: object|null, index: number, total: number }} */
export function segCoreNeighbors(trace, seg) {
  const segs = trace.coreSegs?.get(seg.core) || []
  const n = segs.length
  if (!n) return { prev: null, next: null, index: 0, total: 0 }
  let idx = -1
  for (let i = 0; i < n; i++) {
    const s = segs[i]
    if (s.start === seg.start && s.end === seg.end && s.task === seg.task) {
      idx = i
      break
    }
  }
  if (idx < 0) return { prev: null, next: null, index: 0, total: n }
  return {
    prev: idx > 0 ? segs[idx - 1] : null,
    next: idx + 1 < n ? segs[idx + 1] : null,
    index: idx + 1,
    total: n,
  }
}

/** Off-CPU gaps between consecutive slices of the same task. */
export function blockingTimeSamples(segs, lo, hi) {
  if (!segs || segs.length < 2) return []
  const ordered = [...segs].sort((a, b) => a.start - b.start)
  const samples = []
  for (let i = 1; i < ordered.length; i++) {
    const prev = ordered[i - 1]
    const nxt = ordered[i]
    if (lo != null && hi != null) {
      if (!segFullyInRange(prev, lo, hi) || !segFullyInRange(nxt, lo, hi)) continue
    }
    const gap = nxt.start - prev.end
    if (gap > 0) samples.push(gap)
  }
  return samples
}

/** Plot points for blocking-time distribution (x = resume time, y = gap ns). */
export function blockingTimePlotPoints(segs, lo, hi) {
  if (!segs || segs.length < 2) return []
  const ordered = [...segs].sort((a, b) => a.start - b.start)
  const points = []
  for (let i = 1; i < ordered.length; i++) {
    const prev = ordered[i - 1]
    const nxt = ordered[i]
    if (lo != null && hi != null) {
      if (!segFullyInRange(prev, lo, hi) || !segFullyInRange(nxt, lo, hi)) continue
    }
    const gap = nxt.start - prev.end
    if (gap > 0) {
      points.push({ xNs: nxt.start, yValue: gap, payload: nxt, prev })
    }
  }
  return points
}

/** Max/min without spread — safe for very large arrays (e.g. 500k-line traces). */
export function maxNs(values) {
  if (!values?.length) return 0
  let m = values[0]
  for (let i = 1; i < values.length; i++) {
    if (values[i] > m) m = values[i]
  }
  return m
}

export function minNs(values) {
  if (!values?.length) return 0
  let m = values[0]
  for (let i = 1; i < values.length; i++) {
    if (values[i] < m) m = values[i]
  }
  return m
}

/** Core segments overlapping [lo, hi] via start-time bisect. */
export function coreSegsInRange(trace, core, lo, hi) {
  const segs = trace?.coreSegs?.get?.(core) || []
  if (!segs.length || lo == null || hi == null) return segs
  const starts = trace.coreSegStarts?.get?.(core)
  if (!starts?.length) return segs
  const i0 = Math.max(0, bisectLeft(starts, lo) - 1)
  const i1 = bisectRight(starts, hi)
  return typeof segs.slice === 'function' ? segs.slice(i0, i1) : (() => {
    const out = []
    for (let i = i0; i < i1; i++) out.push(segs[i])
    return out
  })()
}

/** Context-switch count and inter-slice core gaps within optional scope. */
export function schedulingStats(trace, lo, hi) {
  if (lo == null && hi == null
      && trace?.schedCtxSwitches != null
      && Array.isArray(trace.schedCoreGaps)) {
    return {
      contextSwitches: trace.schedCtxSwitches,
      coreGaps: trace.schedCoreGaps,
      gapMax: trace.schedGapMax ?? maxNs(trace.schedCoreGaps),
    }
  }
  let contextSwitches = 0
  const gaps = []
  let gapMax = 0
  const cores = trace.coreNames || []
  for (const core of cores) {
    const segs = coreSegsInRange(trace, core, lo, hi)
    for (let i = 1; i < segs.length; i++) {
      const prev = segs[i - 1]
      const curr = segs[i]
      if (lo != null && hi != null && !(curr.start >= lo && curr.start <= hi)) continue
      contextSwitches += 1
      const gap = curr.start - prev.end
      const g = gap > 0 ? gap : 0
      gaps.push(g)
      if (g > gapMax) gapMax = g
    }
  }
  return { contextSwitches, coreGaps: gaps, gapMax }
}

/** Longest-duration slice in segs (respecting cursor scope). */
export function findWcetSegment(segs, lo, hi) {
  let best = null
  let bestD = 0
  for (const s of segs || []) {
    const d = s.end - s.start
    if (d <= 0) continue
    if (lo != null && hi != null && !segFullyInRange(s, lo, hi)) continue
    if (d > bestD) {
      bestD = d
      best = s
    }
  }
  return best
}

/** Shortest-duration slice in segs (respecting cursor scope). */
export function findBcetSegment(segs, lo, hi) {
  let best = null
  let bestD = null
  for (const s of segs || []) {
    const d = s.end - s.start
    if (d <= 0) continue
    if (lo != null && hi != null && !segFullyInRange(s, lo, hi)) continue
    if (bestD == null || d < bestD) {
      bestD = d
      best = s
    }
  }
  return best
}

/** Resume slice for min/max off-CPU gap between activations. */
export function findExtremeBlockingSegment(segs, lo, hi, findMax = true) {
  if (!segs || segs.length < 2) return null
  const ordered = [...segs].sort((a, b) => a.start - b.start)
  let bestSeg = null
  let bestGap = null
  for (let i = 1; i < ordered.length; i++) {
    const prev = ordered[i - 1]
    const nxt = ordered[i]
    if (lo != null && hi != null) {
      if (!segFullyInRange(prev, lo, hi) || !segFullyInRange(nxt, lo, hi)) continue
    }
    const gap = nxt.start - prev.end
    if (gap <= 0) continue
    if (bestGap == null || (findMax ? gap > bestGap : gap < bestGap)) {
      bestGap = gap
      bestSeg = nxt
    }
  }
  return bestSeg
}

/** Activation slice for min/max inter-arrival gap. */
export function findExtremeInterArrivalSegment(segs, lo, hi, findMax = true) {
  if (!segs || segs.length < 2) return null
  const ordered = [...segs].sort((a, b) => a.start - b.start)
  let bestSeg = null
  let bestGap = null
  for (let i = 1; i < ordered.length; i++) {
    const prev = ordered[i - 1]
    const nxt = ordered[i]
    const gap = nxt.start - prev.start
    if (gap <= 0) continue
    if (lo != null && hi != null && (nxt.start < lo || nxt.start > hi)) continue
    if (bestGap == null || (findMax ? gap > bestGap : gap < bestGap)) {
      bestGap = gap
      bestSeg = nxt
    }
  }
  return bestSeg
}

/** Index of the p-quantile in a sorted n-sample list (stats-table formula). */
export function percentileSampleIndex(n, p) {
  if (n <= 0) return 0
  return Math.min(n - 1, Math.max(0, Math.ceil(n * Number(p)) - 1))
}

/** Slice at percentile p of duration. */
export function findPercentileExecSegment(segs, p, lo, hi) {
  const samples = []
  for (const s of segs || []) {
    const d = s.end - s.start
    if (d <= 0) continue
    if (lo != null && hi != null && !segFullyInRange(s, lo, hi)) continue
    samples.push([d, s])
  }
  if (!samples.length) return null
  samples.sort((a, b) => a[0] - b[0])
  return samples[percentileSampleIndex(samples.length, p)][1]
}

/** Resume slice at percentile p of off-CPU gap. */
export function findPercentileBlockingSegment(segs, p, lo, hi) {
  if (!segs || segs.length < 2) return null
  const ordered = [...segs].sort((a, b) => a.start - b.start)
  const samples = []
  for (let i = 1; i < ordered.length; i++) {
    const prev = ordered[i - 1]
    const nxt = ordered[i]
    if (lo != null && hi != null) {
      if (!segFullyInRange(prev, lo, hi) || !segFullyInRange(nxt, lo, hi)) continue
    }
    const gap = nxt.start - prev.end
    if (gap > 0) samples.push([gap, nxt])
  }
  if (!samples.length) return null
  samples.sort((a, b) => a[0] - b[0])
  return samples[percentileSampleIndex(samples.length, p)][1]
}

/** Activation slice at percentile p of inter-arrival gap. */
export function findPercentileInterArrivalSegment(segs, p, lo, hi) {
  if (!segs || segs.length < 2) return null
  const ordered = [...segs].sort((a, b) => a.start - b.start)
  const samples = []
  for (let i = 1; i < ordered.length; i++) {
    const prev = ordered[i - 1]
    const nxt = ordered[i]
    const gap = nxt.start - prev.start
    if (gap <= 0) continue
    if (lo != null && hi != null && (nxt.start < lo || nxt.start > hi)) continue
    samples.push([gap, nxt])
  }
  if (!samples.length) return null
  samples.sort((a, b) => a[0] - b[0])
  return samples[percentileSampleIndex(samples.length, p)][1]
}

function _gapBeforeSegment(segs, seg, kind) {
  if (!segs?.length || !seg) return null
  const ordered = [...segs].sort((a, b) => a.start - b.start)
  const idx = ordered.findIndex(s => s === seg
    || (s.start === seg.start && s.end === seg.end && s.task === seg.task))
  if (idx <= 0) return null
  const prev = ordered[idx - 1]
  const nxt = ordered[idx]
  if (kind === 'inter') return nxt.start - prev.start
  return nxt.start - prev.end
}

/** Annotation note for Min/Max table navigation to an extreme segment. */
export function extremeSegmentNote(trace, mk, kind, seg, findMax) {
  if (!seg || !trace) return ''
  const repr = taskReprGet(trace, mk) || mk
  const name = taskDisplayName(repr)
  const fmt = v => formatTime(v, trace.timeScale)
  const tag = findMax ? 'max' : 'min'
  if (kind === 'exec') {
    const d = seg.end - seg.start
    return `${name} ${findMax ? 'WCET' : 'BCET'}: ${fmt(d)} at ${fmt(seg.start)}`
  }
  const segs = trace.segByMergeKey?.get(mk) || []
  const gap = _gapBeforeSegment(segs, seg, kind)
  const gapStr = gap != null ? fmt(gap) : '?'
  if (kind === 'block') {
    return `${name} ${tag} blocking: ${gapStr} before ${fmt(seg.start)}`
  }
  if (kind === 'inter') {
    return `${name} ${tag} inter-arrival: ${gapStr} at ${fmt(seg.start)}`
  }
  return `${name} at ${fmt(seg.start)}`
}

/** Build multi-line tooltip text for a segment hover. */
export function segmentTooltipLines(trace, seg, formatTimeFn, taskDisplayNameFn, decimals = 3) {
  if (!seg) return []
  const scale = trace?.timeScale || 'ns'
  const dur = seg.end - seg.start
  const lines = [
    { key: 'Task', val: seg.task, bold: true },
    { key: 'Core', val: seg.core },
    { key: 'Start', val: formatTimeFn(seg.start, scale, decimals) },
    { key: 'End', val: formatTimeFn(seg.end, scale, decimals) },
    { key: 'Duration', val: formatTimeFn(dur, scale, decimals) },
  ]
  if (trace) {
    const { prev, next, index, total } = segCoreNeighbors(trace, seg)
    if (index > 0) lines.push({ key: 'Slice', val: `#${index}/${total} on ${seg.core}` })
    if (prev) {
      lines.push({
        key: '← Prev',
        val: `${taskDisplayNameFn(prev.task)} (${formatTimeFn(prev.end, scale, decimals)})`,
      })
    }
    if (next) {
      lines.push({
        key: '→ Next',
        val: `${taskDisplayNameFn(next.task)} (${formatTimeFn(next.start, scale, decimals)})`,
      })
    }
    if (prev) {
      const gap = seg.start - prev.end
      if (gap > 0) lines.push({ key: 'Gap before', val: formatTimeFn(gap, scale, decimals) })
    }
  }
  return lines
}

/** @typedef {{ mk: string, preemptor: string, timeNs: number, durationNs: number, payload: object }} PreemptionEvent */

/** Max victim/preemptor pairs shown in the statistics table (full data may be larger). */
export const PREEMPTION_CHAIN_MAX_ROWS = 2000

/** @returns {PreemptionEvent[]} */
export function collectPreemptionEvents(trace, lo, hi) {
  const coreSegs = trace?.coreSegs
  if (!coreSegs || !trace?.segByMergeKey) return []

  const coreStarts = new Map()
  for (const [core, segs] of coreSegs) {
    coreStarts.set(core, segs.map(s => s.start))
  }

  const events = []
  for (const [mk, segs] of trace.segByMergeKey) {
    if (!segs || segs.length < 2) continue
    const repr = taskReprGet(trace, mk) || mk
    const { name } = parseTaskName(repr)
    if (isIdleTaskName(name) || name === 'TICK') continue

    const ordered = [...segs].sort((a, b) => a.start - b.start)
    for (let i = 1; i < ordered.length; i++) {
      const prev = ordered[i - 1]
      const nxt = ordered[i]
      const gapStart = prev.end
      const gapEnd = nxt.start
      if (gapEnd <= gapStart) continue
      if (lo != null && hi != null) {
        if (!segFullyInRange(prev, lo, hi) || !segFullyInRange(nxt, lo, hi)) continue
      }

      // Preemptors ran on the same core the victim was on when descheduled (prev slice).
      const core = prev.core
      const coreSegList = coreSegs.get(core)
      if (!coreSegList) continue
      const starts = coreStarts.get(core)
      const i0 = bisectRight(starts, gapEnd - 1)
      const iStart = Math.max(0, i0 - 1)
      for (let j = iStart; j < coreSegList.length; j++) {
        const cs = coreSegList[j]
        if (cs.start >= gapEnd) break
        if (cs.end <= gapStart) continue
        const preemptorMk = taskMergeKey(cs.task)
        if (preemptorMk === mk) continue
        const preRepr = taskReprGet(trace, preemptorMk) || cs.task
        const { name: preName } = parseTaskName(preRepr)
        if (isIdleTaskName(preName)) continue
        const ovLo = Math.max(cs.start, gapStart)
        const ovHi = Math.min(cs.end, gapEnd)
        const overlap = ovHi - ovLo
        if (overlap <= 0) continue
        events.push({
          mk,
          preemptor: taskDisplayName(preRepr),
          timeNs: ovLo,
          durationNs: overlap,
          payload: cs,
        })
      }
    }
  }
  return events
}

/**
 * Preemption Chain Analysis.
 * For each blocking gap of a victim task, finds which tasks ran on the same
 * core during that gap (the preemptors).
 *
 * @param {object} trace
 * @param {number|null} lo
 * @param {number|null} hi
 * @returns {{ rows: Array, truncated: boolean }}
 */
export function preemptionChainRows(trace, lo, hi) {
  const scale = trace?.timeScale || 'ns'
  const data = new Map()

  for (const ev of collectPreemptionEvents(trace, lo, hi)) {
    if (!data.has(ev.mk)) data.set(ev.mk, new Map())
    const victimMap = data.get(ev.mk)
    if (!victimMap.has(ev.preemptor)) victimMap.set(ev.preemptor, [])
    victimMap.get(ev.preemptor).push(ev.durationNs)
  }

  const rows = []
  for (const [mk, preemptors] of data) {
    const repr = taskReprGet(trace, mk) || mk
    const victimDisp = taskDisplayName(repr)
    for (const [preDisp, samples] of preemptors) {
      const total = samples.reduce((a, b) => a + b, 0)
      const count = samples.length
      const avg = Math.round(total / count)
      const max = maxNs(samples)
      rows.push({
        mk,
        victim: victimDisp,
        preemptor: preDisp,
        count,
        totalNs: total,
        avgNs: avg,
        maxNs: max,
        total: formatTime(total, scale),
        avg: formatTime(avg, scale),
        max: formatTime(max, scale),
      })
    }
  }

  rows.sort((a, b) => b.totalNs - a.totalNs || a.victim.localeCompare(b.victim) || a.preemptor.localeCompare(b.preemptor))
  const truncated = rows.length > PREEMPTION_CHAIN_MAX_ROWS
  const out = truncated ? rows.slice(0, PREEMPTION_CHAIN_MAX_ROWS) : rows
  return { rows: out, truncated }
}

/** Plot points for one victim/preemptor pair. */
export function preemptionChainPlotPoints(trace, victimMk, preemptorDisp, lo, hi) {
  return collectPreemptionEvents(trace, lo, hi)
    .filter(ev => ev.mk === victimMk && ev.preemptor === preemptorDisp)
    .map(ev => ({
      xNs: ev.timeNs,
      yValue: ev.durationNs,
      payload: ev.payload,
    }))
}
