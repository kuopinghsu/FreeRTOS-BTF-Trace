/**
 * Latency metrics derived from existing trace data — parity with the desktop
 * parser helpers (`_same_core_gap_samples`, `_priority_episode_cpu_split`,
 * `_affinity_change_to_run_samples`, `_suspended_spans`, `_interval_exec_split`).
 */
import { formatTime } from './timeFormat.js'
import { parseTaskName, taskMergeKey, taskDisplayName, isIdleTaskName, taskReprGet } from './colors.js'
import { coresAllowedByMask } from './coreAffinityAnalysis.js'
import { bisectLeft } from './bisect.js'

const LIFECYCLE_NOTE_RE = /^(create|delete|suspend|resume)\b/i
const AFFINITY_NOTE_RE = /^affinity_set\s+(.+?)\s+(0x[0-9a-fA-F]+|\d+)\s*$/i

const fmtCount = n => n.toLocaleString('en-US')

export const PERCENTILE_METHOD_NOTE = 'Percentiles use nearest rank: the value at position ⌈n·p⌉ of the sorted samples.'

/** Shared metric definitions (key, term, definition, match keywords) — parity with parser.METRIC_DEFINITIONS. */
export const METRIC_DEFINITIONS = [
  ['exec', 'Execution time',
    'Duration of one continuous on-CPU slice of a task. A preempted operation appears as several slices; Max is an observed maximum, not a proven WCET.',
    ['exec', 'execution']],
  ['off_cpu_gap', 'Off-CPU gap',
    'Time from the end of one task slice to the start of the same task’s next slice. It covers preemption, sleep, waiting and suspension alike, so it is not proof of blocking.',
    ['off-cpu', 'off_cpu', 'gap', 'block']],
  ['response', 'Response time (heuristic)',
    'Estimated ready-to-completion window: from the end of the previous slice to the end of the current one. Not a recorded release/completion pair.',
    ['response']],
  ['dispatch', 'Dispatch latency',
    'Time from a recorded ready point (task create or STI resume) to the task’s next switch-in. Wakeups without a task ID are not covered; when several ready events precede one switch-in, only the earliest is kept.',
    ['dispatch', 'scheduling latency']],
  ['migration', 'Core migration',
    'A task’s consecutive slices running on different cores. The gap between them is compared against the same task’s same-core gaps as a baseline.',
    ['migration', 'migrate']],
  ['affinity', 'Affinity change to run',
    'Time from an affinity_set note to the task’s next slice on a core the new mask allows.',
    ['affinity']],
  ['priority', 'Priority inheritance episode',
    'Span from a priority_inherit note to the matching priority_restore (or the end of the trace). On-CPU and off-CPU split the span by the holder’s slices; boost→run is the delay until the holder first runs after the boost.',
    ['priority', 'inherit', 'boost']],
  ['sync_hold', 'Mutex / semaphore span',
    'Time from a take to the paired give on the same object generation. Spans are labelled by kind (owned hold, binary/counting token, or cross-task give); a recreated handle starts a new generation.',
    ['mutex', 'semaphore', 'hold', 'sync']],
  ['queue', 'Queue residence',
    'Time from a send to the receive it is paired with. Pairing assumes FIFO order, which the trace does not record directly.',
    ['queue']],
  ['interval', 'Interval instance',
    'Span between instrumented start and stop markers. On-CPU and off-CPU split the span by the task running on the start core.',
    ['interval']],
  ['suspended', 'Suspended time',
    'Time from a task’s suspend note to its resume note; spans still open at the end of the trace are counted separately.',
    ['suspend']],
  ['percentile', 'Percentiles (p50/p95/p99)',
    'Nearest-rank: the value at position ⌈n·p⌉ of the sorted samples. Below 20 samples p95 and p99 equal the max; below 100 samples p99 equals the max.',
    ['p50', 'p95', 'p99', 'percentile']],
]

/** Definitions whose keywords appear in any of `names` (case-insensitive). */
export function metricDefinitionsFor(names) {
  const low = [...(names || [])].map(n => String(n || '').toLowerCase())
  return METRIC_DEFINITIONS
    .filter(([, , , kws]) => kws.some(kw => low.some(n => n.includes(kw))))
    .map(([key, term, definition]) => ({ key, term, definition }))
}

/** Caption for rows whose p95/p99 collapse to the max, or ''. */
export function percentileSampleNote(counts) {
  const ns = [...(counts || [])].map(Number).filter(Number.isFinite)
  const lt20 = ns.filter(n => n > 0 && n < 20).length
  const lt100 = ns.filter(n => n >= 20 && n < 100).length
  const bits = []
  if (lt20) bits.push(`${fmtCount(lt20)} row(s) with fewer than 20 samples: p95 and p99 are the max`)
  if (lt100) bits.push(`${fmtCount(lt100)} row(s) with 20–99 samples: p99 is the max`)
  if (!bits.length) return ''
  return `Small samples — ${bits.join('; ')}. ${PERCENTILE_METHOD_NOTE}`
}

export function nearestRank(sortedVals, p) {
  const n = sortedVals.length
  return sortedVals[Math.min(n - 1, Math.max(0, Math.ceil(n * p) - 1))]
}

export function avgInt(vals) {
  return vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : 0
}

function segMap(trace) {
  return trace?.segByMergeKey || trace?.segMapByMergeKey || new Map()
}

export function isBackgroundTask(trace, mk) {
  const { name } = parseTaskName(taskReprGet(trace, mk) || mk)
  return isIdleTaskName(name) || name === 'TICK'
}

function segFullyInRange(s, lo, hi) {
  return s.start >= lo && s.end <= hi
}

/** Create vs resume split of dispatch samples, or ''. */
export function dispatchSourceNote(trace, byMk) {
  const create = []
  const resume = []
  let dups = 0
  for (const [mk, data] of byMk || []) {
    if (isBackgroundTask(trace, mk)) continue
    dups += data.duplicates || 0
    const sources = data.sources || []
    ;(data.samples || []).forEach((lat, i) => {
      (sources[i] === 'create' ? create : resume).push(lat)
    })
  }
  if (!create.length && !resume.length) return ''
  const scale = trace.timeScale || 'ns'
  const bits = []
  if (create.length) bits.push(`create→first run avg ${formatTime(avgInt(create), scale)} (n=${fmtCount(create.length)})`)
  if (resume.length) bits.push(`resume→run avg ${formatTime(avgInt(resume), scale)} (n=${fmtCount(resume.length)})`)
  let note = `Ready source: ${bits.join('; ')}.`
  if (dups) note += ` ${fmtCount(dups)} repeated ready event(s) before the same switch-in were merged into the earliest.`
  return note
}

/** Off-CPU gaps where a task resumed on the core it left (no migration). */
export function sameCoreGapSamples(trace, lo = null, hi = null) {
  const out = []
  for (const [mk, segs] of segMap(trace)) {
    if (!segs || segs.length < 2 || isBackgroundTask(trace, mk)) continue
    const ordered = [...segs].sort((a, b) => a.start - b.start)
    for (let i = 1; i < ordered.length; i++) {
      const prev = ordered[i - 1]
      const nxt = ordered[i]
      if (prev.core !== nxt.core) continue
      if (lo != null && hi != null && !(segFullyInRange(prev, lo, hi) && segFullyInRange(nxt, lo, hi))) continue
      const gap = nxt.start - prev.end
      if (gap >= 0) out.push(gap)
    }
  }
  return out
}

export function migrationGapBaselineNote(trace, lo = null, hi = null) {
  const vals = sameCoreGapSamples(trace, lo, hi).sort((a, b) => a - b)
  if (!vals.length) return ''
  const scale = trace.timeScale || 'ns'
  return `Same-core baseline (task resumed on the core it left): avg ${formatTime(avgInt(vals), scale)}, `
    + `p95 ${formatTime(nearestRank(vals, 0.95), scale)} over ${fmtCount(vals.length)} gap(s). `
    + 'Compare with the Gap columns to see what a migration adds.'
}

/**
 * `{ onNs, offNs, boostToRunNs }` for one boosted episode. `boostToRunNs` is 0
 * when the task is already running at the boost and null when it never runs.
 */
export function priorityEpisodeCpuSplit(trace, ep) {
  let on = 0
  let first = null
  for (const s of segMap(trace).get(ep.mk) || []) {
    const a = Math.max(s.start, ep.startNs)
    const b = Math.min(s.end, ep.stopNs)
    if (b > a) {
      on += b - a
      if (first == null || a < first) first = a
    }
  }
  const dur = Math.max(0, ep.stopNs - ep.startNs)
  return { onNs: on, offNs: Math.max(0, dur - on), boostToRunNs: first != null ? first - ep.startNs : null }
}

export function priorityEpisodeCpuFields(trace, ep) {
  const { onNs, offNs, boostToRunNs } = priorityEpisodeCpuSplit(trace, ep)
  const scale = trace.timeScale || 'ns'
  return {
    boostToRun: boostToRunNs != null ? formatTime(boostToRunNs, scale) : 'did not run',
    onCpu: formatTime(onNs, scale),
    offCpu: formatTime(offNs, scale),
  }
}

/** On/off-CPU split and boost→run for completed boost episodes, or ''. */
export function priorityHolderNote(trace, lo = null, hi = null) {
  let onT = 0
  let offT = 0
  let never = 0
  const b2r = []
  for (const ep of trace?.priorityEpisodes || []) {
    if (ep.truncated) continue
    if (lo != null && hi != null && !(lo <= ep.startNs && ep.stopNs <= hi)) continue
    const { onNs, offNs, boostToRunNs } = priorityEpisodeCpuSplit(trace, ep)
    onT += onNs
    offT += offNs
    if (boostToRunNs == null) never++
    else b2r.push(boostToRunNs)
  }
  const total = onT + offT
  if (total <= 0) return ''
  const scale = trace.timeScale || 'ns'
  let note = `While boosted, tasks were on-CPU ${formatTime(onT, scale)} `
    + `(${((100 * onT) / total).toFixed(0)}%) and off-CPU ${formatTime(offT, scale)}`
  if (b2r.length) {
    const vals = b2r.sort((a, b) => a - b)
    note += `; boost→run median ${formatTime(nearestRank(vals, 0.5), scale)}, `
      + `max ${formatTime(vals[vals.length - 1], scale)} over ${fmtCount(vals.length)} episode(s)`
  }
  if (never) note += `; ${fmtCount(never)} episode(s) ended before the task ran`
  return `${note}.`
}

function parseMask(raw) {
  try {
    return BigInt(raw)
  } catch {
    return null
  }
}

/**
 * `{ samples: [changeNs, latencyNs, mk][], noRun }` per `affinity_set`: change →
 * first slice on a core the new mask allows (0 if already running on one).
 */
export function affinityChangeToRunSamples(trace, lo = null, hi = null) {
  const histories = new Map()
  for (const ev of trace?.stiEvents || []) {
    if (ev.target !== 'task') continue
    const m = AFFINITY_NOTE_RE.exec(String(ev.note ?? '').trim())
    if (!m) continue
    const mask = parseMask(m[2])
    if (mask == null) continue
    const mk = taskMergeKey(m[1].trim())
    if (!histories.has(mk)) histories.set(mk, [])
    histories.get(mk).push([ev.time, mask])
  }
  const samples = []
  let noRun = 0
  for (const [mk, hist] of histories) {
    hist.sort((a, b) => a[0] - b[0])
    const segs = [...(segMap(trace).get(mk) || [])].sort((a, b) => a.start - b.start)
    hist.forEach(([t, mask], i) => {
      if (lo != null && hi != null && !(lo <= t && t <= hi)) return
      const allowed = coresAllowedByMask(mask, trace.coreNames || [])
      if (!allowed.size) return
      const tNext = i + 1 < hist.length ? hist[i + 1][0] : null
      let lat = null
      for (const seg of segs) {
        if (seg.end <= t) continue
        if (tNext != null && seg.start >= tNext) break
        if (allowed.has(seg.core)) {
          lat = Math.max(0, seg.start - t)
          break
        }
      }
      if (lat == null) {
        noRun++
        return
      }
      if (lo != null && hi != null && t + lat > hi) return
      samples.push([t, lat, mk])
    })
  }
  return { samples, noRun }
}

export function affinityChangeNote(trace, lo = null, hi = null) {
  const { samples, noRun } = affinityChangeToRunSamples(trace, lo, hi)
  if (!samples.length && !noRun) return ''
  const scale = trace.timeScale || 'ns'
  const bits = []
  if (samples.length) {
    const vals = samples.map(s => s[1]).sort((a, b) => a - b)
    bits.push(`Affinity change → first run on an allowed core: avg ${formatTime(avgInt(vals), scale)}, `
      + `max ${formatTime(vals[vals.length - 1], scale)} over ${fmtCount(vals.length)} change(s)`)
  }
  if (noRun) bits.push(`${fmtCount(noRun)} change(s) with no run on an allowed core before the next change or trace end`)
  return `${bits.join('; ')}.`
}

/** `{ spans: [suspendNs, resumeNs, mk][], still }` from named STI notes. */
export function suspendedSpans(trace, lo = null, hi = null) {
  const openByMk = new Map()
  const spans = []
  const taskEvs = (trace?.stiEvents || []).filter(ev => ev.target === 'task')
    .sort((a, b) => a.time - b.time)
  for (const ev of taskEvs) {
    const note = String(ev.note ?? '').trim()
    const m = LIFECYCLE_NOTE_RE.exec(note)
    if (!m) continue
    const label = note.slice(m[0].length).trim()
    if (!label || label.startsWith('/')) continue
    const action = m[1].toLowerCase()
    const mk = taskMergeKey(label)
    if (action === 'suspend') {
      if (!openByMk.has(mk)) openByMk.set(mk, ev.time)
    } else if (action === 'resume') {
      const t0 = openByMk.get(mk)
      if (t0 == null) continue
      openByMk.delete(mk)
      if (lo != null && hi != null && !(lo <= t0 && ev.time <= hi)) continue
      spans.push([t0, ev.time, mk])
    } else if (action === 'delete') {
      openByMk.delete(mk)
    }
  }
  return { spans, still: openByMk.size }
}

export function suspendedDurationNote(trace, lo = null, hi = null) {
  const { spans, still } = suspendedSpans(trace, lo, hi)
  if (!spans.length && !still) return ''
  const scale = trace.timeScale || 'ns'
  const bits = []
  if (spans.length) {
    const vals = spans.map(([a, b]) => b - a).sort((a, b) => a - b)
    bits.push(`Suspended (suspend → resume of the same task): avg ${formatTime(avgInt(vals), scale)}, `
      + `max ${formatTime(vals[vals.length - 1], scale)} over ${fmtCount(vals.length)} span(s)`)
  }
  if (still) bits.push(`${fmtCount(still)} task(s) still suspended at trace end`)
  return `${bits.join('; ')}.`
}

/**
 * `{ mk, onNs, offNs }` for the task running on the start core when *inst*
 * started, or null when no task (or only idle) was running.
 */
export function intervalExecSplit(trace, inst, cache = new Map()) {
  const segs = trace?.coreSegs?.get?.(inst.startCore) || []
  if (!segs.length) return null
  const starts = trace.coreSegStarts?.get?.(inst.startCore) || segs.map(s => s.start)
  let i = bisectLeft(starts, inst.startNs + 1) - 1
  if (i < 0 || segs[i].end < inst.startNs) return null
  const mk = taskMergeKey(segs[i].task)
  if (isBackgroundTask(trace, mk)) return null
  if (!cache.has(mk)) {
    const own = [...(segMap(trace).get(mk) || [])].sort((a, b) => a.start - b.start)
    cache.set(mk, { own, ownStarts: own.map(s => s.start) })
  }
  const { own, ownStarts } = cache.get(mk)
  let on = 0
  for (let j = Math.max(0, bisectLeft(ownStarts, inst.startNs) - 1); j < own.length && own[j].start < inst.stopNs; j++) {
    const a = Math.max(own[j].start, inst.startNs)
    const b = Math.min(own[j].end, inst.stopNs)
    if (b > a) on += b - a
  }
  const dur = Math.max(0, inst.stopNs - inst.startNs)
  return { mk, onNs: on, offNs: Math.max(0, dur - on) }
}

export function intervalExecFields(trace, inst, cache) {
  const split = intervalExecSplit(trace, inst, cache)
  if (!split) return { execTask: '—', onCpu: '—', offCpu: '—' }
  const scale = trace.timeScale || 'ns'
  return {
    execTask: taskDisplayName(taskReprGet(trace, split.mk) || split.mk),
    onCpu: formatTime(split.onNs, scale),
    offCpu: formatTime(split.offNs, scale),
  }
}

export function intervalExecNote(trace, lo = null, hi = null) {
  let onT = 0
  let waitT = 0
  let n = 0
  const cache = new Map()
  for (const id of trace?.intervalIds || []) {
    for (const inst of trace.intervalInstancesById?.get(id) || []) {
      if (lo != null && hi != null && !(inst.startNs >= lo && inst.stopNs <= hi)) continue
      const split = intervalExecSplit(trace, inst, cache)
      if (!split) continue
      onT += split.onNs
      waitT += split.offNs
      n++
    }
  }
  const total = onT + waitT
  if (!n || total <= 0) return ''
  const scale = trace.timeScale || 'ns'
  return `The task running when each interval started was on-CPU ${((100 * onT) / total).toFixed(0)}% `
    + `of interval time (avg on-CPU ${formatTime(Math.floor(onT / n), scale)}, avg off-CPU `
    + `${formatTime(Math.floor(waitT / n), scale)} over ${fmtCount(n)} instance(s)); the rest is `
    + 'preemption, blocking or work done by other tasks.'
}
