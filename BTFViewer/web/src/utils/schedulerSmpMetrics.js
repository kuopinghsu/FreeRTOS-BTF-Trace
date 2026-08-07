/**
 * Advanced scheduler / SMP metrics (parity with desktop parser helpers).
 * Dispatch latency uses STI task resume (+ create→first-run) as t_ready.
 */

import { parseTaskName, taskMergeKey, taskDisplayName, isIdleTaskName, taskReprGet } from './colors.js'
import { formatTime } from './timeFormat.js'

const LIFECYCLE_NOTE_RE = /^(create|delete|suspend|resume)\b/i

function summarizeNs(samples, scale) {
  if (!samples?.length) return null
  const vals = [...samples].sort((a, b) => a - b)
  const n = vals.length
  const mean = vals.reduce((a, b) => a + b, 0) / n
  const avg = Math.round(mean)
  const p95Idx = Math.min(n - 1, Math.max(0, Math.ceil(n * 0.95) - 1))
  const jitter = vals[n - 1] - vals[0]
  let varSum = 0
  for (const v of vals) varSum += (v - mean) ** 2
  const stddev = Math.round(Math.sqrt(varSum / n))
  return {
    count: n,
    minNs: vals[0],
    avgNs: avg,
    maxNs: vals[n - 1],
    jitterNs: jitter,
    stddevNs: stddev,
    p95Ns: vals[p95Idx],
    min: formatTime(vals[0], scale),
    avg: formatTime(avg, scale),
    max: formatTime(vals[n - 1], scale),
    jitter: formatTime(jitter, scale),
    stddev: formatTime(stddev, scale),
    p95: formatTime(vals[p95Idx], scale),
  }
}

/**
 * Dispatch latency samples: STI resume Name[id] (or create) → next switch-in.
 * @returns {Map<string, { samples: number[], points: {xNs:number,yValue:number,payload:any}[], extrema: { minSeg, maxSeg, minNs, maxNs } }>}
 */
export function collectDispatchLatencyByMk(trace, lo, hi) {
  const byMk = new Map()

  function ensure(mk) {
    let e = byMk.get(mk)
    if (!e) {
      e = {
        samples: [],
        points: [],
        extrema: { minSeg: null, maxSeg: null, minNs: null, maxNs: null },
      }
      byMk.set(mk, e)
    }
    return e
  }

  function addSample(mk, readyNs, segs) {
    if (!segs?.length) return
    if (lo != null && hi != null && !(readyNs >= lo && readyNs <= hi)) return
    let best = null
    for (const s of segs) {
      if (s.start < readyNs) continue
      if (lo != null && hi != null && !(s.start >= lo && s.start <= hi)) continue
      if (!best || s.start < best.start) best = s
    }
    if (!best) return
    const lat = best.start - readyNs
    if (lat < 0) return
    const e = ensure(mk)
    e.samples.push(lat)
    e.points.push({ xNs: best.start, yValue: lat, payload: best })
    const ex = e.extrema
    if (ex.minNs == null || lat < ex.minNs) {
      ex.minNs = lat
      ex.minSeg = best
    }
    if (ex.maxNs == null || lat > ex.maxNs) {
      ex.maxNs = lat
      ex.maxSeg = best
    }
  }

  const createTimes = trace.taskCreateTimes
  if (createTimes instanceof Map) {
    for (const [mk, createNs] of createTimes) {
      addSample(mk, createNs, (trace.segByMergeKey || trace.segMapByMergeKey)?.get(mk) || [])
    }
  } else if (createTimes && typeof createTimes === 'object') {
    for (const [mk, createNs] of Object.entries(createTimes)) {
      addSample(mk, createNs, (trace.segByMergeKey || trace.segMapByMergeKey)?.get(mk) || [])
    }
  }

  for (const ev of trace.stiEvents || []) {
    if (ev.target !== 'task') continue
    const note = String(ev.note || '').trim()
    const m = LIFECYCLE_NOTE_RE.exec(note)
    if (!m || m[1].toLowerCase() !== 'resume') continue
    const taskLabel = note.slice(m[0].length).trim()
    if (!taskLabel) continue // resume/isr without name
    const mk = taskMergeKey(taskLabel)
    addSample(mk, ev.time, (trace.segByMergeKey || trace.segMapByMergeKey)?.get(mk) || [])
  }

  return byMk
}

/** Per-task dispatch latency rows for the Statistics table. */
export function dispatchLatencyRows(trace, lo, hi) {
  const scale = trace.timeScale || 'ns'
  const byMk = collectDispatchLatencyByMk(trace, lo, hi)
  const rows = []
  for (const [mk, data] of byMk) {
    const raw = taskReprGet(trace, mk) || mk
    const { name } = parseTaskName(raw)
    if (isIdleTaskName(name) || name === 'TICK') continue
    const summary = summarizeNs(data.samples, scale)
    if (!summary) continue
    rows.push({
      mk,
      label: taskDisplayName(raw),
      activations: summary.count,
      ...summary,
      minSeg: data.extrema.minSeg,
      maxSeg: data.extrema.maxSeg,
    })
  }
  rows.sort((a, b) => b.activations - a.activations || a.label.localeCompare(b.label))
  return rows
}

/**
 * Per-core kernel switch overhead = consecutive core_segs gap
 * (t_resume_B − t_preempt_A).
 */
export function switchOverheadRows(trace, lo, hi) {
  const scale = trace.timeScale || 'ns'
  const rows = []
  const cores = trace.coreNames || []
  let spanNs
  if (lo != null && hi != null) spanNs = Math.max(1, hi - lo)
  else spanNs = Math.max(1, (trace.timeMax ?? 0) - (trace.timeMin ?? 0))

  for (const core of cores) {
    const segs = trace.coreSegs?.get(core) || []
    const samples = []
    for (let i = 1; i < segs.length; i++) {
      const prev = segs[i - 1]
      const curr = segs[i]
      if (lo != null && hi != null && !(curr.start >= lo && curr.start <= hi)) continue
      const gap = curr.start - prev.end
      samples.push(gap > 0 ? gap : 0)
    }
    if (!samples.length) continue
    const summary = summarizeNs(samples, scale)
    const total = samples.reduce((a, b) => a + b, 0)
    rows.push({
      core,
      switches: samples.length,
      ...summary,
      totalNs: total,
      total: formatTime(total, scale),
      pctOfCore: (100 * total) / spanNs,
    })
  }
  return rows
}

/**
 * Time spent with N cores concurrently active (non-IDLE, non-TICK).
 * @returns {{ activeCores: number, durationNs: number, pctOfSpan: number, duration: string }[]}
 */
export function concurrentCoreActiveRows(trace, lo, hi) {
  const scale = trace.timeScale || 'ns'
  const t0 = lo != null ? lo : (trace.timeMin ?? 0)
  const t1 = hi != null ? hi : (trace.timeMax ?? 0)
  const spanNs = Math.max(1, t1 - t0)
  const nCores = (trace.coreNames || []).length
  if (nCores <= 0 || t1 <= t0) return []

  /** @type {{ t: number, d: number }[]} */
  const events = []
  for (const core of trace.coreNames || []) {
    const segs = trace.coreSegs?.get(core) || []
    for (const s of segs) {
      const { name } = parseTaskName(s.task)
      if (isIdleTaskName(name) || name === 'TICK') continue
      let a = s.start
      let b = s.end
      if (b <= t0 || a >= t1) continue
      if (a < t0) a = t0
      if (b > t1) b = t1
      if (b <= a) continue
      events.push({ t: a, d: 1 })
      events.push({ t: b, d: -1 })
    }
  }
  events.sort((x, y) => x.t - y.t || x.d - y.d)

  const dur = new Array(nCores + 1).fill(0)
  let active = 0
  let prevT = t0
  for (const ev of events) {
    if (ev.t > prevT) {
      const level = Math.max(0, Math.min(nCores, active))
      dur[level] += ev.t - prevT
      prevT = ev.t
    }
    active += ev.d
  }
  if (t1 > prevT) {
    const level = Math.max(0, Math.min(nCores, active))
    dur[level] += t1 - prevT
  }

  const rows = []
  for (let n = 0; n <= nCores; n++) {
    if (dur[n] <= 0) continue
    rows.push({
      activeCores: n,
      durationNs: dur[n],
      duration: formatTime(dur[n], scale),
      pctOfSpan: (100 * dur[n]) / spanNs,
    })
  }
  return rows
}

/** `(xNs, yValue, payload)` plot points for one task's dispatch latency. */
export function dispatchLatencyPlotPoints(trace, mk, lo, hi) {
  const data = collectDispatchLatencyByMk(trace, lo, hi).get(mk)
  return data?.points ? [...data.points] : []
}

/** Kernel switch overhead gaps on one core. */
export function switchOverheadPlotPoints(trace, core, lo, hi) {
  const segs = trace.coreSegs?.get(core) || []
  if (segs.length < 2) return []
  const points = []
  for (let i = 1; i < segs.length; i++) {
    const prev = segs[i - 1]
    const curr = segs[i]
    if (lo != null && hi != null && !(curr.start >= lo && curr.start <= hi)) continue
    const gap = curr.start - prev.end
    points.push({ xNs: curr.start, yValue: gap > 0 ? gap : 0, payload: null })
  }
  return points
}

/** Interval dwell durations while exactly `activeCores` cores are active. */
export function concurrencyLevelPlotPoints(trace, activeCores, lo, hi) {
  const t0 = lo != null ? lo : (trace.timeMin ?? 0)
  const t1 = hi != null ? hi : (trace.timeMax ?? 0)
  const nCores = (trace.coreNames || []).length
  if (nCores <= 0 || t1 <= t0) return []
  const target = Math.max(0, Math.min(nCores, Number(activeCores) | 0))

  /** @type {{ t: number, d: number }[]} */
  const events = []
  for (const core of trace.coreNames || []) {
    const segs = trace.coreSegs?.get(core) || []
    for (const s of segs) {
      const { name } = parseTaskName(s.task)
      if (isIdleTaskName(name) || name === 'TICK') continue
      let a = s.start
      let b = s.end
      if (b <= t0 || a >= t1) continue
      if (a < t0) a = t0
      if (b > t1) b = t1
      if (b <= a) continue
      events.push({ t: a, d: 1 })
      events.push({ t: b, d: -1 })
    }
  }
  events.sort((x, y) => x.t - y.t || x.d - y.d)

  const points = []
  let active = 0
  let prevT = t0
  for (const ev of events) {
    if (ev.t > prevT) {
      const level = Math.max(0, Math.min(nCores, active))
      if (level === target) {
        points.push({ xNs: prevT, yValue: ev.t - prevT, payload: null })
      }
      prevT = ev.t
    }
    active += ev.d
  }
  if (t1 > prevT) {
    const level = Math.max(0, Math.min(nCores, active))
    if (level === target) {
      points.push({ xNs: prevT, yValue: t1 - prevT, payload: null })
    }
  }
  return points
}
