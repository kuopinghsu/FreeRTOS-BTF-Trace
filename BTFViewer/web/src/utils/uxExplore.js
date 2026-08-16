/**
 * Deterministic timeline explore helpers (anomalies, worst events, scope).
 * Keep in sync with btf_viewer_pkg/ux_explore.py.
 */
import { parseTaskName, isIdleTaskName, taskDisplayName } from './colors.js'
import { segFullyInRange } from './statsRange.js'

export const KIND_SECTION = Object.freeze({
  exec: 'exec',
  block: 'block',
  inter: 'inter',
  migration: 'migrations',
  period: 'period',
  task_core: 'task_core',
  wait_owner: 'wait_owner',
  task_health: 'task_health',
  response: 'response',
  preempt: 'preempt_matrix',
  isr: 'anomalies',
  idle: 'cores',
  cpu: 'cores',
  deadline: 'deadline',
  pattern: 'patterns',
  crit_path: 'crit_path',
  jitter: 'jitter',
  mutex_block: 'mutex_block',
  core_time: 'core_time',
  distrib: 'distrib',
})

export const MUTEX_HANDOFF_SLACK_NS = 1_000_000
export const PERIOD_MISS_RATIO = 1.5
export const PERIOD_EXTRA_RATIO = 0.5
export const PERIOD_BURST_RATIO = 0.25
export const HEALTH_MARK = Object.freeze({ ok: '✓', warn: '⚠', fail: '❌' })
export const HEALTH_BAND_SECTION = Object.freeze({
  execution: 'exec',
  blocking: 'block',
  period: 'period',
  migration: 'migrations',
  deadline: 'deadline',
  cpu: 'tasks',
})

export const KIND_LABEL = {
  exec: 'execution',
  block: 'blocking',
  inter: 'inter-arrival',
  migration: 'migration',
  response: 'response',
  preempt: 'preemption',
  isr: 'ISR',
  idle: 'idle',
  cpu: 'CPU',
  deadline: 'deadline',
  crit_path: 'critical path',
  pattern: 'pattern',
  jitter: 'jitter',
  mutex_block: 'mutex blocking',
}

const ISR_RE = /(isr|irq|interrupt)/i
export const CORE_TIME_BINS = 16
export const BURST_WINDOW_NS = 1_000_000

const JUMP_RE = /jump:([0-9]+(?:\.[0-9]+)?)/gi
const TASK_RE = /\b([A-Za-z_][\w.-]*\[\d+\])/
const DELTA_RE = /^([+\-−])?\s*([\d.]+)\s*(ns|µs|us|μs|ms|s|\/s|%)?$/i
const UNIT_NS = {
  ns: 1,
  us: 1000,
  µs: 1000,
  μs: 1000,
  ms: 1_000_000,
  s: 1_000_000_000,
}
const SUMMARY_STRIP_LABELS = new Set([
  'Span',
  'Span (cursor range)',
  'Context switches',
  'Migrations (total)',
  'Missed ticks (est.)',
  'Response P99 (worst task)',
  'Mutex blocking (total)',
  'Deadline misses',
])

export function percentileIndex(n, p) {
  if (n <= 0) return 0
  const pp = Math.max(0, Math.min(1, Number(p)))
  return Math.min(n - 1, Math.max(0, Math.ceil(n * pp) - 1))
}

export function findEventAtPercentile(events, p) {
  const rows = (events || []).filter(e => e && typeof e === 'object')
  if (!rows.length) return null
  const ordered = [...rows].sort((a, b) => Number(a.duration || 0) - Number(b.duration || 0))
  return ordered[percentileIndex(ordered.length, p)]
}

export function collectWorstEvents(events, limit = 12) {
  const lim = Math.max(1, Math.min(40, Number(limit) || 12))
  const seen = new Set()
  const ranked = []
  const rows = (events || []).filter(e => e && ['exec', 'block', 'inter', 'response'].includes(e.kind))
  if (!rows.some(e => e.kind === 'response')) {
    rows.push(...(analyzeResponseTimes(events).events || []))
  }
  rows.sort((a, b) => Number(b.duration || 0) - Number(a.duration || 0)
    || Number(a.start || 0) - Number(b.start || 0))
  for (const ev of rows) {
    const key = `${ev.kind}|${ev.start}|${ev.task || ev.mk}`
    if (seen.has(key)) continue
    seen.add(key)
    ranked.push({ ...ev })
    if (ranked.length >= lim) break
  }
  return ranked
}

export function detectTimelineAnomalies(events, limit = 12, mutexWaits = null, deadlines = null) {
  const lim = Math.max(1, Math.min(40, Number(limit) || 12))
  const rows = (events || []).filter(e => e && typeof e === 'object')
  const flagged = []
  const seen = new Set()

  const add = (ev, reason) => {
    const key = `${ev.kind}|${ev.start}|${ev.task || ev.mk}`
    if (seen.has(key)) return
    seen.add(key)
    flagged.push({
      ...ev,
      reason,
      section: KIND_SECTION[ev.kind] || 'exec',
    })
  }

  const byGroup = new Map()
  for (const ev of rows) {
    if (!['exec', 'block', 'inter'].includes(ev.kind)) continue
    const task = String(ev.task || ev.mk || '')
    const gk = `${ev.kind}|${task}`
    if (!byGroup.has(gk)) byGroup.set(gk, [])
    byGroup.get(gk).push(ev)
  }
  for (const [gk, group] of byGroup) {
    if (group.length < 4) continue
    const vals = group.map(e => Number(e.duration || 0)).sort((a, b) => a - b)
    const n = vals.length
    const mean = vals.reduce((a, b) => a + b, 0) / n
    const sigma = Math.sqrt(vals.reduce((acc, v) => acc + ((v - mean) ** 2), 0) / n)
    const p99 = vals[percentileIndex(n, 0.99)]
    const thresh = sigma > 0 ? mean + 3 * sigma : p99
    const kind = gk.split('|')[0]
    const task = gk.slice(kind.length + 1)
    const label = KIND_LABEL[kind] || kind
    for (const ev of group) {
      const dur = Number(ev.duration || 0)
      if (dur <= 0) continue
      if (sigma > 0 && dur > thresh) add(ev, `${label} > mean+3σ for ${task || 'task'}`)
      else if (dur >= p99 && dur >= mean) add(ev, `${label} ≥ p99 for ${task || 'task'}`)
    }
  }
  for (const kind of ['exec', 'block']) {
    const pool = rows.filter(e => e.kind === kind)
    if (!pool.length) continue
    const best = pool.reduce((a, b) => (Number(b.duration || 0) > Number(a.duration || 0) ? b : a))
    if (Number(best.duration || 0) > 0) add(best, `longest ${KIND_LABEL[kind] || kind} in scope`)
  }
  for (const ev of migrationBursts(rows)) {
    add(ev, ev.reason || 'migration burst')
  }
  for (const ev of kindBursts(rows, 'block', BURST_WINDOW_NS, 4, 'preemption burst')) {
    add(ev, ev.reason || 'preemption burst')
  }
  for (const ev of kindBursts(rows, 'inter', BURST_WINDOW_NS, 4, 'wakeup burst')) {
    add(ev, ev.reason || 'wakeup burst')
  }
  const isrRows = rows.filter(e => e.kind === 'exec' && isIsrName(e.task))
  for (const ev of kindBursts(isrRows, 'exec', BURST_WINDOW_NS, 3, 'ISR burst')) {
    add({ ...ev, kind: 'isr' }, ev.reason || 'ISR burst')
  }
  const respEvents = analyzeResponseTimes(rows).events || []
  if (respEvents.length >= 4) {
    const vals = respEvents.map(e => Number(e.duration || 0)).sort((a, b) => a - b)
    const n = vals.length
    const mean = vals.reduce((a, b) => a + b, 0) / n
    const sigma = Math.sqrt(vals.reduce((acc, v) => acc + ((v - mean) ** 2), 0) / n)
    const p99 = vals[percentileIndex(n, 0.99)]
    const thresh = sigma > 0 ? mean + 3 * sigma : p99
    for (const ev of respEvents) {
      const dur = Number(ev.duration || 0)
      if (dur <= 0) continue
      if (sigma > 0 && dur > thresh) add(ev, `response > mean+3σ for ${ev.task || 'task'}`)
      else if (dur >= p99 && dur >= mean) add(ev, `response ≥ p99 for ${ev.task || 'task'}`)
    }
  }
  if (respEvents.length) {
    const bestR = respEvents.reduce((a, b) => (
      Number(b.duration || 0) > Number(a.duration || 0) ? b : a
    ))
    if (Number(bestR.duration || 0) > 0) add(bestR, 'longest response in scope')
  }
  const waits = [...(mutexWaits || []).filter(w => w && typeof w === 'object')]
  waits.push(...rows.filter(e => e.kind === 'mutex_block'))
  if (waits.length >= 4) {
    const vals = waits.map(w => Number(w.duration || 0)).sort((a, b) => a - b)
    const n = vals.length
    const mean = vals.reduce((s, v) => s + v, 0) / n
    const p99 = vals[percentileIndex(n, 0.99)]
    for (const w of waits) {
      const dur = Number(w.duration || 0)
      if (dur <= 0 || dur < p99 || dur < mean) continue
      add({
        ...w,
        kind: 'mutex_block',
        task: w.waiter || w.task,
        mk: w.waiter_mk || w.mk,
      }, `mutex wait spike on ${w.object || 'mutex'}`)
    }
  } else if (waits.length) {
    const bestW = waits.reduce((a, b) => (
      Number(b.duration || 0) > Number(a.duration || 0) ? b : a
    ))
    if (Number(bestW.duration || 0) > 0) {
      add({
        ...bestW,
        kind: 'mutex_block',
        task: bestW.waiter || bestW.task,
        mk: bestW.waiter_mk || bestW.mk,
      }, `mutex wait spike on ${bestW.object || 'mutex'}`)
    }
  }
  const dlMap = {}
  for (const [k, v] of Object.entries(deadlines || {})) {
    const n = Math.trunc(v || 0)
    if (n > 0) dlMap[String(k)] = n
  }
  if (Object.keys(dlMap).length) {
    for (const ev of respEvents) {
      const limNs = dlMap[String(ev.mk || '')] || dlMap[String(ev.task || '')]
      const dur = Math.trunc(ev.duration || 0)
      if (!limNs || dur <= limNs) continue
      add({ ...ev, kind: 'deadline' }, `deadline miss (${dur} > ${limNs})`)
    }
  }
  for (const ev of coreBusyAnomalies(rows)) add(ev, ev.reason || 'CPU utilization spike')
  for (const ev of idleGapAnomalies(rows)) add(ev, ev.reason || 'unusual idle')
  flagged.sort((a, b) => Number(b.duration || 0) - Number(a.duration || 0)
    || Number(a.start || 0) - Number(b.start || 0))
  return flagged.slice(0, lim)
}

export function bestFindingScope(finding, events, timeMin, timeMax) {
  if (!finding || typeof finding !== 'object') return null
  const tmin = Number(timeMin)
  const tmax = Number(timeMax)
  if (!Number.isFinite(tmin) || !Number.isFinite(tmax) || tmax <= tmin) return null
  const times = []
  for (const ev of finding.evidence || []) {
    if (!ev || typeof ev !== 'object') continue
    for (const key of ['time', 'start', 'stop']) {
      const n = Number(ev[key])
      if (Number.isFinite(n)) times.push(n)
    }
  }
  const blob = `${finding.title || ''} ${finding.text || ''}`
  JUMP_RE.lastIndex = 0
  let jm
  while ((jm = JUMP_RE.exec(blob))) {
    const n = Number(jm[1])
    if (Number.isFinite(n)) times.push(n)
  }
  let task = String(finding.task || '').trim()
  if (!task) {
    const tm = TASK_RE.exec(blob)
    if (tm) task = tm[1]
  }
  let section = 'exec'
  let reason = 'Evidence times from the selected finding'
  let matched = null
  if (times.length) {
    const lo0 = Math.min(...times)
    const hi0 = Math.max(...times)
    if (task) {
      const nearby = (events || []).filter(e => e && eventMatchesTask(e, task)
        && Number(e.start || 0) <= hi0
        && Number(e.stop || e.start || 0) >= lo0)
      if (nearby.length) {
        matched = nearby.reduce((a, b) => (
          Number(b.duration || 0) > Number(a.duration || 0) ? b : a
        ))
      }
    }
    if (!matched && (events || []).length) {
      const mid = (lo0 + hi0) / 2
      matched = (events || []).reduce((best, e) => {
        if (!e) return best
        if (!best) return e
        return Math.abs(Number(e.start || 0) - mid) < Math.abs(Number(best.start || 0) - mid)
          ? e : best
      }, null)
    }
  } else if (task) {
    const pool = (events || []).filter(e => e && eventMatchesTask(e, task))
    if (pool.length) {
      matched = pool.reduce((a, b) => (
        Number(b.duration || 0) > Number(a.duration || 0) ? b : a
      ))
      reason = `Worst episode for ${task}`
    }
  }
  if (!matched && (events || []).length) {
    matched = (events || []).reduce((best, e) => {
      if (!e) return best
      if (!best) return e
      return Number(e.duration || 0) > Number(best.duration || 0) ? e : best
    }, null)
    if (matched) reason = 'Longest episode in scope'
  }
  let lo
  let hi
  if (times.length) {
    lo = Math.min(...times)
    hi = Math.max(...times)
  } else if (matched) {
    lo = Number(matched.start || tmin)
    hi = Number(matched.stop || matched.start || lo)
  } else {
    return null
  }
  if (matched) {
    section = KIND_SECTION[matched.kind] || 'exec'
    if (!task) task = String(matched.task || '')
    lo = Math.min(lo, Number(matched.start || lo))
    hi = Math.max(hi, Number(matched.stop || hi))
    const nearby = (events || []).filter(e => e
      && Number(e.start || 0) <= hi
      && Number(e.stop || e.start || 0) >= lo)
    reason = scopeReason(nearby, task, reason)
  }
  const span = Math.max(tmax - tmin, 1)
  const pad = Math.max(hi - lo, span * 0.01, 1000)
  lo = Math.max(tmin, lo - pad)
  hi = Math.min(tmax, hi + pad)
  if (lo >= hi) {
    hi = Math.min(tmax, lo + Math.max(pad, 1000))
    if (lo >= hi) return null
  }
  return {
    lo: Math.trunc(lo),
    hi: Math.trunc(hi),
    reason,
    task,
    section,
    mk: String(matched?.mk || ''),
  }
}

export function findingOverlayTimes(findings, limit = 80) {
  const times = []
  const seen = new Set()
  for (const finding of findings || []) {
    if (!finding || typeof finding !== 'object') continue
    for (const ev of finding.evidence || []) {
      if (!ev || typeof ev !== 'object') continue
      for (const key of ['time', 'start', 'stop']) {
        const t = Number(ev[key])
        if (!Number.isFinite(t) || seen.has(t)) continue
        seen.add(t)
        times.push(t)
      }
    }
    const blob = `${finding.title || ''} ${finding.text || ''}`
    JUMP_RE.lastIndex = 0
    let jm
    while ((jm = JUMP_RE.exec(blob))) {
      const t = Number(jm[1])
      if (!Number.isFinite(t) || seen.has(t)) continue
      seen.add(t)
      times.push(t)
    }
    if (times.length >= limit) break
  }
  return times.slice(0, limit)
}

export function taskInspectorLine(task = '', qualityWarnings = []) {
  const name = String(task || '').trim()
  const parts = [name ? `Task ${name}` : 'No task selected']
  for (const q of qualityWarnings || []) {
    const text = String(q || '').trim()
    if (text) {
      parts.push(text.slice(0, 96))
      break
    }
  }
  return parts.join(' · ')
}

export function parseSignedDelta(text) {
  const s = String(text ?? '').trim().replace(/−/g, '-')
  if (!s || s === '—' || s === '–' || s === '-') return null
  const m = DELTA_RE.exec(s)
  if (!m) return null
  const sign = m[1] === '-' ? -1 : 1
  const val = Number(m[2])
  if (!Number.isFinite(val)) return null
  const unit = String(m[3] || '').toLowerCase()
  if (unit in UNIT_NS) return { signed: sign * val * UNIT_NS[unit], kind: 'time' }
  if (unit === '%') return { signed: sign * val, kind: 'pct' }
  if (unit === '/s') return { signed: sign * val, kind: 'rate' }
  return { signed: sign * val, kind: 'count' }
}

export function compareCandidatesFromTables(tables) {
  if (!tables || typeof tables !== 'object') return []
  const out = []
  for (const row of tables.summary || []) {
    const { label, delta } = rowLabelDelta(row, 'label', 'delta', 0, 3)
    if (!label || skipSummaryLabel(label)) continue
    const parsed = parseSignedDelta(delta)
    if (!parsed) continue
    out.push({ label, metric: 'summary', delta: String(delta), ...parsed })
  }
  const specs = [
    ['execution', 'exec max', 0, 7, 'name', 'deltaMax'],
    ['blocking', 'block avg', 0, 7, 'name', 'delta'],
    ['inter_arrival', 'inter avg', 0, 7, 'name', 'delta'],
    ['interArrival', 'inter avg', 0, 7, 'name', 'delta'],
    ['response', 'response p99', 0, 3, 'name', 'delta'],
    ['mutex_block', 'mutex block', 0, 3, 'name', 'delta'],
    ['mutexBlock', 'mutex block', 0, 3, 'name', 'delta'],
    ['deadlines', 'deadline misses', 0, 3, 'name', 'delta'],
  ]
  for (const [key, metric, nameIdx, deltaIdx, nameKey, deltaKey] of specs) {
    for (const row of tables[key] || []) {
      const { label: name, delta } = rowLabelDelta(row, nameKey, deltaKey, nameIdx, deltaIdx)
      if (!name) continue
      const parsed = parseSignedDelta(delta)
      if (!parsed) continue
      out.push({
        label: `${name} ${metric}`,
        metric,
        delta: String(delta),
        ...parsed,
      })
    }
  }
  return out
}

export function topCompareRegressions(candidates, limit = 4) {
  const lim = Math.max(1, Math.min(12, Number(limit) || 4))
  const worse = (candidates || []).filter(c => c && Number(c.signed || 0) > 0).map(c => ({ ...c }))
  const timeRows = worse.filter(c => c.kind === 'time')
    .sort((a, b) => Math.abs(Number(b.signed || 0)) - Math.abs(Number(a.signed || 0)))
  const other = worse.filter(c => c.kind !== 'time')
    .sort((a, b) => Math.abs(Number(b.signed || 0)) - Math.abs(Number(a.signed || 0)))
  const picked = timeRows.slice(0, Math.max(0, lim - 1))
  if (other.length && picked.length < lim) picked.push(other[0])
  if (picked.length < lim) {
    for (const c of [...timeRows, ...other]) {
      if (!picked.includes(c)) picked.push(c)
      if (picked.length >= lim) break
    }
  }
  return picked.slice(0, lim)
}

export function compareSummaryStrip(tables, limit = 4) {
  const cands = compareCandidatesFromTables(tables)
  const headline = []
  for (const row of tables?.summary || []) {
    const { label, delta } = rowLabelDelta(row, 'label', 'delta', 0, 3)
    if (SUMMARY_STRIP_LABELS.has(label)) {
      headline.push({ label: label.replace(' (cursor range)', ''), delta: String(delta) })
    }
  }
  const regressions = topCompareRegressions(cands, limit)
  const shared = [...(tables?.shared_patterns || tables?.sharedPatterns || [])]
  return {
    headline,
    regressions,
    shared_patterns: shared,
    why: compareWhy({ regressions, shared_patterns: shared }),
  }
}

export function prepareUxEvents(trace) {
  const cached = uxEventsCache(trace)
  if (cached) return cached
  const events = harvestUxEventsFromSegments(trace, null, null)
  if (trace) {
    trace.uxEventsFull = events
    trace.ux_events_full = events
  }
  return events
}

function uxEventsCache(trace) {
  if (!trace) return null
  const cached = trace.uxEventsFull || trace.ux_events_full
  return Array.isArray(cached) ? cached : null
}

function filterCachedUxEvents(events, lo, hi) {
  const out = []
  for (const ev of events || []) {
    if (!ev) continue
    const kind = String(ev.kind || '')
    const start = Math.trunc(ev.start || 0)
    const stop = Math.trunc(ev.stop || start)
    if (kind === 'migration') {
      if (start >= lo && start <= hi) out.push(ev)
    } else if (kind === 'inter') {
      const jump = Math.trunc(ev.jump_ns || stop)
      if (start >= lo && jump >= lo && jump <= hi) out.push(ev)
    } else if (start >= lo && stop <= hi) {
      out.push(ev)
    }
  }
  return out
}

export function harvestUxEvents(trace, lo = null, hi = null) {
  const cached = uxEventsCache(trace)
  if (cached) {
    if (lo == null || hi == null) return cached
    return filterCachedUxEvents(cached, lo, hi)
  }
  return harvestUxEventsFromSegments(trace, lo, hi)
}

function harvestUxEventsFromSegments(trace, lo, hi) {
  const events = []
  if (!trace) return events
  const smap = trace.seg_map_by_merge_key || trace.segByMergeKey
  if (!smap) return events
  const items = typeof smap.entries === 'function' ? smap.entries() : Object.entries(smap)
  const reprMap = trace.task_repr || trace.taskRepr || new Map()
  for (const [mk, segs] of items) {
    const raw = mapGet(reprMap, mk, mk)
    const { name: tname } = parseTaskName(String(raw))
    if (isIdleTaskName(tname) || tname === 'TICK') continue
    const name = taskDisplayName(String(raw))
    const ordered = orderedSegs(segs)
    if (!ordered.length) continue
    for (const seg of ordered) {
      const start = Number(seg.start || 0)
      const end = Number(seg.end || 0)
      const dur = end - start
      if (dur <= 0) continue
      if (lo != null && hi != null && !segFullyInRange(seg, lo, hi)) continue
      events.push(makeEvent('exec', name, String(mk), start, end, dur, start, seg.core))
    }
    for (let i = 1; i < ordered.length; i++) {
      const prev = ordered[i - 1]
      const nxt = ordered[i]
      if (lo != null && hi != null) {
        if (!segFullyInRange(prev, lo, hi) || !segFullyInRange(nxt, lo, hi)) continue
      }
      const gap = Number(nxt.start) - Number(prev.end)
      if (gap > 0) {
        events.push(makeEvent(
          'block', name, String(mk), Number(prev.end), Number(nxt.start), gap,
          Number(nxt.start), nxt.core,
        ))
      }
      const arr = Number(nxt.start) - Number(prev.start)
      if (arr > 0) {
        if (lo != null && hi != null && (Number(nxt.start) < lo || Number(nxt.start) > hi)) {
          continue
        }
        events.push(makeEvent(
          'inter', name, String(mk), Number(prev.start), Number(nxt.start), arr,
          Number(nxt.start), nxt.core,
        ))
      }
    }
  }
  for (const ev of trace.migrations || []) {
    const ns = Number(ev?.ns || 0)
    if (lo != null && hi != null && (ns < lo || ns > hi)) continue
    const mk = String(ev.merge_key || ev.mergeKey || '')
    const raw = mapGet(reprMap, mk, mk)
    const { name: tname } = parseTaskName(String(raw))
    if (isIdleTaskName(tname) || tname === 'TICK') continue
    const gap = Number(ev.gap_ns || ev.gapNs || 0)
    events.push(makeEvent(
      'migration', taskDisplayName(String(raw)), mk, ns, ns + Math.max(gap, 1),
      Math.max(gap, 1), ns, '',
    ))
  }
  return events
}

function makeEvent(kind, task, mk, start, stop, duration, jumpNs, core) {
  return {
    kind,
    task,
    mk,
    start: Math.trunc(start),
    stop: Math.trunc(stop),
    duration: Math.trunc(duration),
    jump_ns: Math.trunc(jumpNs),
    core: String(core || ''),
    section: KIND_SECTION[kind] || 'exec',
    reason: '',
  }
}

function orderedSegs(segs) {
  if (!segs) return []
  const rows = [...segs].filter(s => s && s.start != null)
  for (let i = 1; i < rows.length; i++) {
    if (Number(rows[i].start) < Number(rows[i - 1].start)) {
      rows.sort((a, b) => Number(a.start) - Number(b.start))
      break
    }
  }
  return rows
}

function mapGet(mapping, key, fallback) {
  if (!mapping) return fallback
  if (typeof mapping.get === 'function') {
    const v = mapping.get(key)
    return v == null ? fallback : v
  }
  if (mapping[key] != null) return mapping[key]
  return fallback
}

function eventMatchesTask(ev, task) {
  const t = String(task || '').trim().toLowerCase()
  if (!t) return false
  return t === String(ev.task || '').trim().toLowerCase()
    || t === String(ev.mk || '').trim().toLowerCase()
    || String(ev.task || '').toLowerCase().includes(t)
}

function migrationBursts(events, windowNs = 1000) {
  const byMk = new Map()
  for (const ev of events) {
    if (ev.kind !== 'migration') continue
    const mk = String(ev.mk || ev.task || '')
    if (!byMk.has(mk)) byMk.set(mk, [])
    byMk.get(mk).push(ev)
  }
  const out = []
  for (const group of byMk.values()) {
    group.sort((a, b) => Number(a.start || 0) - Number(b.start || 0))
    if (group.length < 3) continue
    let i = 0
    while (i < group.length) {
      let j = i
      while (j + 1 < group.length
        && Number(group[j + 1].start || 0) - Number(group[i].start || 0) <= windowNs) {
        j += 1
      }
      const count = j - i + 1
      if (count >= 3) {
        const first = group[i]
        const last = group[j]
        out.push({
          ...last,
          start: Math.trunc(first.start || 0),
          stop: Math.trunc(last.stop || last.start || 0),
          duration: Math.max(
            Math.trunc(last.stop || last.start || 0) - Math.trunc(first.start || 0),
            count,
          ),
          reason: `${count} migrations within ${windowNs} ns`,
        })
        i = j + 1
      } else {
        i += 1
      }
    }
  }
  return out
}

function rowLabelDelta(row, nameKey, deltaKey, nameIdx, deltaIdx) {
  if (row && typeof row === 'object' && !Array.isArray(row)) {
    return { label: String(row[nameKey] || row.label || ''), delta: row[deltaKey] }
  }
  if (Array.isArray(row) && row.length > Math.max(nameIdx, deltaIdx)) {
    return { label: String(row[nameIdx] || ''), delta: row[deltaIdx] }
  }
  return { label: '', delta: null }
}

function skipSummaryLabel(label) {
  const low = String(label || '').toLowerCase()
  return low.includes('load balance') || low.includes('tick health') || low.includes('tick mode')
}

export const DISTRIBUTION_KINDS = Object.freeze([
  'exec', 'block', 'inter', 'response', 'dispatch', 'wakeup', 'preempt',
])

const SPARK_BARS = '▁▂▃▄▅▆▇█'

export function sparkline(values, width = 16) {
  const vals = (values || []).map(v => Math.trunc(v || 0)).filter(v => v >= 0)
  if (!vals.length) return ''
  const w = Math.max(4, Math.min(24, Math.trunc(width || 16)))
  let series = vals
  if (vals.length > w) {
    const step = vals.length / w
    series = []
    for (let i = 0; i < w; i++) {
      const lo = Math.trunc(i * step)
      const hi = Math.max(lo + 1, Math.trunc((i + 1) * step))
      const chunk = vals.slice(lo, hi)
      series.push(chunk.length ? Math.trunc(chunk.reduce((s, x) => s + x, 0) / chunk.length) : 0)
    }
  }
  const loV = Math.min(...series)
  const hiV = Math.max(...series)
  const span = hiV - loV
  if (span <= 0) return SPARK_BARS[0].repeat(series.length)
  return series.map(v => SPARK_BARS[Math.min(7, Math.trunc((v - loV) * 7 / span))]).join('')
}

export function analyzeTaskPeriods(events, minGaps = 3) {
  const need = Math.max(2, Number(minGaps) || 3)
  const byMk = new Map()
  for (const ev of events || []) {
    if (!ev || ev.kind !== 'inter') continue
    const mk = String(ev.mk || ev.task || '')
    if (!mk) continue
    if (!byMk.has(mk)) byMk.set(mk, [])
    byMk.get(mk).push(ev)
  }
  const rows = []
  for (const [mk, group] of byMk) {
    group.sort((a, b) => Number(a.start || 0) - Number(b.start || 0))
    const gaps = group.map(e => Math.trunc(e.duration || 0)).filter(g => g > 0)
    if (gaps.length < need) continue
    const ordered = [...gaps].sort((a, b) => a - b)
    const n = ordered.length
    const mean = ordered.reduce((s, g) => s + g, 0) / n
    let expected = ordered[percentileIndex(n, 0.50)]
    if (expected <= 0) expected = Math.round(mean) || 1
    const p95 = ordered[percentileIndex(n, 0.95)]
    const p99 = ordered[percentileIndex(n, 0.99)]
    const minG = ordered[0]
    const maxG = ordered[n - 1]
    const variance = ordered.reduce((s, g) => s + (g - mean) ** 2, 0) / n
    const std = Math.sqrt(variance)
    const cv = mean ? std / mean : 0
    const rms = Math.sqrt(ordered.reduce((s, g) => s + (g - expected) ** 2, 0) / n)
    const missed = ordered.filter(g => g > expected * PERIOD_MISS_RATIO).length
    const extra = ordered.filter(g => g < expected * PERIOD_EXTRA_RATIO).length
    const burst = ordered.filter(g => g < expected * PERIOD_BURST_RATIO).length
    const evFor = (target) => {
      const hit = group.find(e => Math.trunc(e.duration || 0) === target)
      return { ...(hit || group[0]) }
    }
    const worst = group.reduce((a, b) => (
      Math.trunc(b.duration || 0) > Math.trunc(a.duration || 0) ? b : a
    ))
    let missEv = null
    for (const e of group) {
      if (Math.trunc(e.duration || 0) > expected * PERIOD_MISS_RATIO) {
        if (!missEv || Math.trunc(e.duration || 0) > Math.trunc(missEv.duration || 0)) {
          missEv = e
        }
      }
    }
    rows.push({
      task: group[0].task || mk,
      mk,
      n,
      expected_ns: Math.trunc(expected),
      min_ns: minG,
      avg_ns: Math.round(mean),
      max_ns: maxG,
      p50_ns: Math.trunc(expected),
      p95_ns: p95,
      p99_ns: p99,
      jitter_ns: maxG - minG,
      rms_ns: Math.round(rms),
      cv: Math.round(cv * 10000) / 10000,
      missed,
      extra,
      burst,
      min_ev: evFor(minG),
      max_ev: evFor(maxG),
      p50_ev: evFor(Math.trunc(expected)),
      p95_ev: evFor(p95),
      p99_ev: evFor(p99),
      worst_ev: { ...worst },
      miss_ev: { ...(missEv || worst) },
      samples: gaps,
      spark: sparkline(gaps),
      section: 'period',
    })
  }
  rows.sort((a, b) => (b.missed - a.missed) || (b.cv - a.cv) || String(a.task).localeCompare(String(b.task)))
  return rows
}

export function taskCoreMatrix(events, cores = [], spanNs = 0, limit = 40) {
  const coreList = [...(cores || [])].map(c => String(c || '')).filter(Boolean)
  const byMk = new Map()
  for (const ev of events || []) {
    if (!ev || ev.kind !== 'exec') continue
    const mk = String(ev.mk || ev.task || '')
    const core = String(ev.core || '')
    const dur = Math.trunc(ev.duration || 0)
    if (!mk || !core || dur <= 0) continue
    if (!coreList.includes(core)) coreList.push(core)
    if (!byMk.has(mk)) byMk.set(mk, { task: ev.task || mk, mk, ns: {}, first: {} })
    const rec = byMk.get(mk)
    rec.ns[core] = (rec.ns[core] || 0) + dur
    if (rec.first[core] == null) rec.first[core] = ev
  }
  const span = Math.max(1, Math.trunc(spanNs || 0))
  const lim = Math.max(1, Math.min(80, Number(limit) || 40))
  const rows = []
  for (const [mk, rec] of byMk) {
    const total = Object.values(rec.ns).reduce((s, n) => s + n, 0)
    if (total <= 0) continue
    const cells = {}
    for (const c of coreList) {
      const ns = rec.ns[c] || 0
      const ev = rec.first[c]
      cells[c] = {
        ns,
        pct_span: 100 * ns / span,
        pct_task: 100 * ns / total,
        start: ev ? Math.trunc(ev.start || 0) : 0,
        stop: ev ? Math.trunc(ev.stop || 0) : 0,
        jump_ns: ev ? Math.trunc(ev.jump_ns || ev.start || 0) : 0,
      }
    }
    rows.push({ task: rec.task, mk, total_ns: total, cells, section: 'task_core' })
  }
  rows.sort((a, b) => (b.total_ns - a.total_ns) || String(a.task).localeCompare(String(b.task)))
  return { cores: coreList, rows: rows.slice(0, lim), span_ns: span }
}

export function harvestMutexHolds(trace, lo = null, hi = null) {
  const objs = trace?.sync_objects || trace?.syncObjects
  if (!objs) return []
  const values = typeof objs.values === 'function' ? [...objs.values()] : Object.values(objs)
  const out = []
  for (const obj of values) {
    if (!obj || String(obj.kind || '').toLowerCase() !== 'mutex') continue
    const key = String(obj.key || '')
    for (const h of obj.holds || []) {
      if (!h) continue
      const start = Math.trunc(h.start_ns || h.startNs || 0)
      const stop = Math.trunc(h.stop_ns || h.stopNs || 0)
      if (stop <= start) continue
      if (lo != null && hi != null && (stop < lo || start > hi)) continue
      out.push({
        object: key,
        holder: String(h.holder_label || h.holderLabel || ''),
        holder_mk: String(h.holder_mk || h.holderMk || ''),
        start,
        stop,
        duration: stop - start,
      })
    }
  }
  return out
}

export function pairMutexWaits(holds, slackNs = MUTEX_HANDOFF_SLACK_NS) {
  const byObj = new Map()
  for (const h of holds || []) {
    if (!h) continue
    const key = String(h.object || '')
    if (!byObj.has(key)) byObj.set(key, [])
    byObj.get(key).push(h)
  }
  const slack = Math.max(0, Math.trunc(slackNs || 0))
  const waits = []
  for (const [obj, group] of byObj) {
    group.sort((a, b) => Number(a.start || 0) - Number(b.start || 0))
    for (let i = 1; i < group.length; i++) {
      const prev = group[i - 1]
      const nxt = group[i]
      const oMk = String(prev.holder_mk || '')
      const wMk = String(nxt.holder_mk || '')
      if (!oMk || !wMk || oMk === wMk) continue
      const gap = Number(nxt.start || 0) - Number(prev.stop || 0)
      if (gap < -1 || gap > slack) continue
      const start = Math.trunc(prev.start || 0)
      const stop = Math.trunc(prev.stop || 0)
      waits.push({
        waiter: String(nxt.holder || wMk),
        waiter_mk: wMk,
        owner: String(prev.holder || oMk),
        owner_mk: oMk,
        object: obj,
        start,
        stop,
        duration: Math.max(1, stop - start),
        jump_ns: start,
        section: 'wait_owner',
      })
    }
  }
  return waits
}

export function waiterOwnerMatrix(waits, limit = 16) {
  const totals = new Map()
  const names = new Map()
  for (const w of waits || []) {
    if (!w) continue
    const wk = String(w.waiter_mk || '')
    const ok = String(w.owner_mk || '')
    if (!wk || !ok) continue
    const key = `${wk}|${ok}`
    const rec = totals.get(key) || { ns: 0, count: 0, worst: w }
    rec.ns += Math.trunc(w.duration || 0)
    rec.count += 1
    if (Math.trunc(w.duration || 0) > Math.trunc(rec.worst.duration || 0)) rec.worst = w
    totals.set(key, rec)
    names.set(wk, String(w.waiter || wk))
    names.set(ok, String(w.owner || ok))
  }
  const invol = new Map()
  for (const [key, rec] of totals) {
    const [wk, ok] = key.split('|')
    invol.set(wk, (invol.get(wk) || 0) + rec.ns)
    invol.set(ok, (invol.get(ok) || 0) + rec.ns)
  }
  const lim = Math.max(2, Math.min(24, Number(limit) || 16))
  const tasks = [...invol.keys()]
    .sort((a, b) => (invol.get(b) - invol.get(a)) || String(names.get(a)).localeCompare(String(names.get(b))))
    .slice(0, lim)
  const taskSet = new Set(tasks)
  const cells = {}
  for (const [key, rec] of totals) {
    const [wk, ok] = key.split('|')
    if (!taskSet.has(wk) || !taskSet.has(ok)) continue
    const worst = rec.worst
    cells[key] = {
      ns: rec.ns,
      count: rec.count,
      start: Math.trunc(worst.start || 0),
      stop: Math.trunc(worst.stop || 0),
      jump_ns: Math.trunc(worst.jump_ns || worst.start || 0),
      waiter: names.get(wk) || wk,
      owner: names.get(ok) || ok,
      waiter_mk: wk,
      owner_mk: ok,
      section: 'wait_owner',
    }
  }
  return {
    tasks: tasks.map(mk => ({ mk, task: names.get(mk) || mk })),
    cells,
  }
}

export function healthInputsFromEvents(events, spanNs = 0, deadlineMks = []) {
  const byMk = new Map()
  for (const ev of events || []) {
    if (!ev) continue
    const mk = String(ev.mk || ev.task || '')
    if (!mk) continue
    if (!byMk.has(mk)) {
      byMk.set(mk, {
        task: ev.task || mk, mk, exec: [], block: [], inter: [], mig: 0, cpuNs: 0,
      })
    }
    const rec = byMk.get(mk)
    const dur = Math.trunc(ev.duration || 0)
    if (ev.kind === 'exec' && dur > 0) {
      rec.exec.push(dur)
      rec.cpuNs += dur
    } else if (ev.kind === 'block' && dur > 0) {
      rec.block.push(dur)
    } else if (ev.kind === 'inter' && dur > 0) {
      rec.inter.push(dur)
    } else if (ev.kind === 'migration') {
      rec.mig += 1
    }
  }
  const span = Math.max(1, Math.trunc(spanNs || 0))
  const dead = new Set((deadlineMks || []).map(x => String(x || '')).filter(Boolean))
  const out = []
  for (const [mk, rec] of byMk) {
    if (!rec.exec.length) continue
    const [eCv, eRatio, eN] = sampleCvRatio(rec.exec)
    const [bCv, bRatio] = sampleCvRatio(rec.block)
    const [pCv] = sampleCvRatio(rec.inter)
    let missed = 0
    if (rec.inter.length) {
      const ordered = [...rec.inter].sort((a, b) => a - b)
      const expected = ordered[percentileIndex(ordered.length, 0.50)]
      if (expected > 0) {
        missed = ordered.filter(g => g > expected * PERIOD_MISS_RATIO).length
      }
    }
    out.push({
      task: rec.task,
      mk,
      exec_cv: eCv,
      exec_max_avg: eRatio,
      exec_n: eN,
      block_cv: bCv,
      block_max_avg: bRatio,
      period_cv: pCv,
      missed,
      mig_count: rec.mig,
      mig_ratio: rec.mig / Math.max(eN, 1),
      cpu_pct: 100 * rec.cpuNs / span,
      deadline_miss: dead.has(mk) || dead.has(String(rec.task)),
    })
  }
  return out
}

export function taskHealthScores(inputs) {
  const rows = []
  for (const inp of inputs || []) {
    if (!inp) continue
    const bands = {}
    let pen = 0
    const [eBand, ePen] = worseBand(
      dim(Number(inp.exec_cv || 0), 0.5, 1.0, 10, 20),
      dim(Number(inp.exec_max_avg || 0), 3.0, 8.0, 10, 20),
    )
    bands.execution = eBand
    pen += ePen
    const [bBand, bPen] = worseBand(
      dim(Number(inp.block_cv || 0), 0.6, 1.2, 10, 20),
      dim(Number(inp.block_max_avg || 0), 4.0, 10.0, 10, 20),
    )
    bands.blocking = bBand
    pen += bPen
    let [pBand, pPen] = dim(Number(inp.period_cv || 0), 0.15, 0.40, 8, 16)
    const missed = Math.trunc(inp.missed || 0)
    if (missed >= 3) {
      pBand = 'fail'
      pPen = Math.max(pPen, 16)
    } else if (missed > 0 && pBand === 'ok') {
      pBand = 'warn'
      pPen = Math.max(pPen, 8)
    }
    bands.period = pBand
    pen += pPen
    const [mBand, mPen] = dim(Number(inp.mig_ratio || 0), 0.3, 0.7, 8, 16)
    bands.migration = mBand
    pen += mPen
    if (inp.deadline_miss) {
      bands.deadline = 'fail'
      pen += 30
    } else {
      bands.deadline = 'ok'
    }
    const [cBand, cPen] = dim(Number(inp.cpu_pct || 0), 80.0, 95.0, 8, 16)
    bands.cpu = cBand
    pen += cPen
    const score = Math.max(0, Math.min(100, 100 - pen))
    const marks = {}
    for (const [k, v] of Object.entries(bands)) marks[k] = HEALTH_MARK[v] || v
    rows.push({
      task: inp.task,
      mk: inp.mk,
      score,
      bands,
      marks,
      section: 'task_health',
      disclaimer: 'Heuristic score from measured statistics, not an AI probability.',
    })
  }
  rows.sort((a, b) => (a.score - b.score) || String(a.task || '').localeCompare(String(b.task || '')))
  return rows
}

function sampleCvRatio(samples) {
  const vals = (samples || []).map(v => Math.trunc(v || 0)).filter(v => v > 0)
  if (!vals.length) return [0, 0, 0]
  const n = vals.length
  const mean = vals.reduce((s, v) => s + v, 0) / n
  const variance = vals.reduce((s, v) => s + (v - mean) ** 2, 0) / n
  const cv = mean ? Math.sqrt(variance) / mean : 0
  const ratio = mean ? Math.max(...vals) / mean : 0
  return [cv, ratio, n]
}

function dim(value, warnAt, failAt, warnPen, failPen) {
  if (value >= failAt) return ['fail', failPen]
  if (value >= warnAt) return ['warn', warnPen]
  return ['ok', 0]
}

function worseBand(a, b) {
  const rank = { ok: 0, warn: 1, fail: 2 }
  const pick = (rank[a[0]] || 0) >= (rank[b[0]] || 0) ? a : b
  return [pick[0], Math.max(a[1], b[1])]
}

function isIsrName(name) {
  return ISR_RE.test(String(name || ''))
}

function scopeReason(events, task, fallback) {
  const kinds = { exec: 0, block: 0, inter: 0, migration: 0 }
  for (const e of events || []) {
    if (e?.kind in kinds) kinds[e.kind] += 1
  }
  const bits = []
  if (kinds.exec) bits.push(kinds.inter ? 'activation' : 'execution')
  if (kinds.block) bits.push(`${kinds.block} preemption/wait gap${kinds.block === 1 ? '' : 's'}`)
  if (kinds.migration) bits.push(`${kinds.migration} migration${kinds.migration === 1 ? '' : 's'}`)
  if (!bits.length) return fallback
  return `Contains${task ? ` for ${task}` : ''}: ${bits.join(', ')}`
}

function kindBursts(events, kind, windowNs, minCount, label) {
  const group = (events || [])
    .filter(e => e && e.kind === kind)
    .sort((a, b) => Number(a.start || 0) - Number(b.start || 0))
  if (group.length < minCount) return []
  const out = []
  let i = 0
  while (i < group.length) {
    let j = i
    while (j + 1 < group.length
      && Number(group[j + 1].start || 0) - Number(group[i].start || 0) <= windowNs) {
      j += 1
    }
    const count = j - i + 1
    if (count >= minCount) {
      const first = group[i]
      const last = group[j]
      const stem = String(label).replace(/ burst$/, '')
      out.push({
        ...last,
        start: Math.trunc(first.start || 0),
        stop: Math.trunc(last.stop || last.start || 0),
        duration: Math.max(
          Math.trunc(last.stop || last.start || 0) - Math.trunc(first.start || 0),
          count,
        ),
        reason: `${count} ${stem}s within ${windowNs} ns`,
      })
      i = j + 1
    } else {
      i += 1
    }
  }
  return out
}

function durationStats(samples) {
  const ordered = (samples || []).map(s => Math.trunc(s || 0)).filter(s => s > 0).sort((a, b) => a - b)
  if (!ordered.length) return null
  const n = ordered.length
  const mean = ordered.reduce((s, v) => s + v, 0) / n
  const std = Math.sqrt(ordered.reduce((s, v) => s + (v - mean) ** 2, 0) / n)
  return {
    n,
    min_ns: ordered[0],
    avg_ns: Math.round(mean),
    max_ns: ordered[n - 1],
    p50_ns: ordered[percentileIndex(n, 0.50)],
    p90_ns: ordered[percentileIndex(n, 0.90)],
    p95_ns: ordered[percentileIndex(n, 0.95)],
    p99_ns: ordered[percentileIndex(n, 0.99)],
    p999_ns: ordered[percentileIndex(n, 0.999)],
    jitter_ns: ordered[n - 1] - ordered[0],
    std_ns: Math.round(std),
    cv: Math.round(((mean ? std / mean : 0) * 10000)) / 10000,
  }
}

export function analyzeResponseTimes(events) {
  const byMk = new Map()
  for (const ev of events || []) {
    if (!ev || ev.kind !== 'exec') continue
    const mk = String(ev.mk || ev.task || '')
    if (!mk) continue
    if (!byMk.has(mk)) byMk.set(mk, [])
    byMk.get(mk).push(ev)
  }
  const respEvents = []
  const rows = []
  for (const [mk, group] of byMk) {
    group.sort((a, b) => Number(a.start || 0) - Number(b.start || 0))
    const samples = []
    const task = String(group[0].task || mk)
    for (let i = 0; i < group.length; i++) {
      const ev = group[i]
      const ready = i === 0
        ? Math.trunc(ev.start || 0)
        : Math.trunc(group[i - 1].stop || group[i - 1].start || 0)
      const complete = Math.trunc(ev.stop || ev.start || 0)
      const dur = Math.max(0, complete - ready)
      if (dur <= 0) continue
      samples.push(dur)
      const item = makeEvent('response', task, mk, ready, complete, dur, ready, ev.core)
      item.exec_ns = Math.trunc(ev.duration || 0)
      item.wait_ns = Math.max(0, dur - Math.trunc(ev.duration || 0))
      respEvents.push(item)
    }
    const stats = durationStats(samples)
    if (!stats) continue
    const slice = respEvents.slice(-samples.length)
    const worst = slice.reduce((a, b) => (
      Math.trunc(b.duration || 0) > Math.trunc(a.duration || 0) ? b : a
    ))
    const evFor = (target) => {
      const hit = slice.find(e => Math.trunc(e.duration || 0) === Math.trunc(target))
      return { ...(hit || worst) }
    }
    rows.push({
      ...stats,
      task,
      mk,
      section: 'response',
      worst_ev: { ...worst },
      min_ev: evFor(stats.min_ns),
      max_ev: evFor(stats.max_ns),
      p50_ev: evFor(stats.p50_ns),
      p90_ev: evFor(stats.p90_ns),
      p95_ev: evFor(stats.p95_ns),
      p99_ev: evFor(stats.p99_ns),
      p999_ev: evFor(stats.p999_ns),
      disclaimer: 'Heuristic ready→completion from adjacent slices, not an explicit BTF release/completion pair.',
    })
  }
  rows.sort((a, b) => (b.p99_ns - a.p99_ns) || String(a.task).localeCompare(String(b.task)))
  return { rows, events: respEvents }
}

function indexExecs(events) {
  const byCore = new Map()
  for (const ev of events || []) {
    if (!ev || ev.kind !== 'exec') continue
    const core = String(ev.core || '')
    if (!core) continue
    let rows = byCore.get(core)
    if (!rows) {
      rows = []
      byCore.set(core, rows)
    }
    rows.push(ev)
  }
  const indexed = new Map()
  for (const [core, rows] of byCore) {
    rows.sort((a, b) => Math.trunc(a.start || 0) - Math.trunc(b.start || 0))
    indexed.set(core, { rows, starts: rows.map(e => Math.trunc(e.start || 0)) })
  }
  return indexed
}

function iterOverlapping(rows, starts, lo, hi) {
  const out = []
  if (!rows?.length || hi <= lo) return out
  let i = bisectRight(starts, lo) - 1
  if (i < 0) i = 0
  while (i < rows.length) {
    const ev = rows[i]
    const a = Math.trunc(ev.start || 0)
    if (a >= hi) break
    const b = Math.trunc(ev.stop || a)
    if (b > lo) out.push(ev)
    i += 1
  }
  return out
}

function bisectRight(arr, x) {
  let lo = 0
  let hi = arr.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (arr[mid] <= x) lo = mid + 1
    else hi = mid
  }
  return lo
}

export function criticalPathRows(events, limit = 8) {
  const resp = analyzeResponseTimes(events).events || []
  if (!resp.length) return []
  const worst = [...resp].sort((a, b) => Math.trunc(b.duration || 0) - Math.trunc(a.duration || 0))
    .slice(0, Math.max(1, Math.min(20, limit)))
  const byCore = indexExecs(events)
  const migsByMk = new Map()
  const blocksByMk = new Map()
  for (const m of events || []) {
    if (!m) continue
    const mk = String(m.mk || '')
    if (m.kind === 'migration' && mk) {
      const list = migsByMk.get(mk) || []
      list.push(m)
      migsByMk.set(mk, list)
    } else if (m.kind === 'block' && mk) {
      const list = blocksByMk.get(mk) || []
      list.push(m)
      blocksByMk.set(mk, list)
    }
  }
  return worst.map((ev) => {
    const lo = Math.trunc(ev.start || 0)
    const hi = Math.trunc(ev.stop || lo)
    const mk = String(ev.mk || '')
    const core = String(ev.core || '')
    let execNs = 0
    let preemptNs = 0
    let execEv = null
    let preemptEv = null
    const pools = core && byCore.has(core) ? [byCore.get(core)] : [...byCore.values()]
    for (const pool of pools) {
      for (const other of iterOverlapping(pool.rows, pool.starts, lo, hi)) {
        const a = Math.trunc(other.start || 0)
        const b = Math.trunc(other.stop || a)
        const overlap = Math.min(b, hi) - Math.max(a, lo)
        if (overlap <= 0) continue
        if (String(other.mk || '') === mk) {
          execNs += overlap
          if (!execEv || overlap > Math.trunc(execEv.duration || 0)) {
            execEv = { ...other, duration: overlap }
          }
        } else {
          preemptNs += overlap
          if (!preemptEv || overlap > Math.trunc(preemptEv.duration || 0)) {
            preemptEv = {
              ...other,
              start: Math.max(a, lo),
              stop: Math.min(b, hi),
              duration: overlap,
              jump_ns: Math.max(a, lo),
              section: 'preempt_matrix',
            }
          }
        }
      }
    }
    let waitNs = 0
    let waitEv = null
    for (const blk of blocksByMk.get(mk) || []) {
      const a = Math.trunc(blk.start || 0)
      const b = Math.trunc(blk.stop || a)
      const overlap = Math.min(b, hi) - Math.max(a, lo)
      if (overlap <= 0) continue
      waitNs += overlap
      if (!waitEv || overlap > Math.trunc(waitEv.duration || 0)) {
        waitEv = {
          ...blk,
          start: Math.max(a, lo),
          stop: Math.min(b, hi),
          duration: overlap,
          jump_ns: Math.max(a, lo),
        }
      }
    }
    let migNs = 0
    let migEv = null
    for (const m of migsByMk.get(mk) || []) {
      const t = Math.trunc(m.start || 0)
      if (t >= lo && t <= hi) {
        const dur = Math.trunc(m.duration || 1)
        migNs += dur
        if (!migEv || dur > Math.trunc(migEv.duration || 0)) migEv = { ...m }
      }
    }
    const total = Math.max(1, Math.trunc(ev.duration || 0))
    const otherNs = Math.max(0, total - execNs - preemptNs - waitNs - migNs)
    return {
      task: ev.task,
      mk,
      start: lo,
      stop: hi,
      jump_ns: lo,
      duration: total,
      exec_ns: execNs,
      preempt_ns: preemptNs,
      wait_ns: waitNs,
      migration_ns: migNs,
      other_ns: otherNs,
      exec_ev: execEv || { ...ev },
      preempt_ev: preemptEv,
      wait_ev: waitEv,
      mig_ev: migEv,
      other_ev: { ...ev },
      section: 'crit_path',
      kind: 'crit_path',
      reason: `exec ${execNs} · preempt ${preemptNs} · wait ${waitNs} · mig ${migNs} · other ${otherNs}`,
    }
  })
}

export function preemptionPairs(events) {
  const byCore = indexExecs(events)
  const pairs = []
  for (const block of events || []) {
    if (!block || block.kind !== 'block') continue
    const blo = Math.trunc(block.start || 0)
    const bhi = Math.trunc(block.stop || blo)
    if (bhi <= blo) continue
    const vmk = String(block.mk || '')
    const core = String(block.core || '')
    const pools = core && byCore.has(core) ? [byCore.get(core)] : [...byCore.values()]
    for (const pool of pools) {
      for (const other of iterOverlapping(pool.rows, pool.starts, blo, bhi)) {
        if (String(other.mk || '') === vmk) continue
        const a = Math.trunc(other.start || 0)
        const b = Math.trunc(other.stop || a)
        const overlap = Math.min(b, bhi) - Math.max(a, blo)
        if (overlap <= 0) continue
        pairs.push({
          victim: block.task,
          victim_mk: vmk,
          preemptor: other.task,
          preemptor_mk: String(other.mk || ''),
          core: core || other.core || '',
          start: Math.max(a, blo),
          stop: Math.min(b, bhi),
          duration: overlap,
          jump_ns: Math.max(a, blo),
          section: 'preempt_matrix',
          kind: 'preempt',
        })
      }
    }
  }
  return pairs
}

export function preemptionStory(pairs, victimMk, lo = null, hi = null) {
  const vmk = String(victimMk || '')
  const sel = []
  for (const p of pairs || []) {
    if (!p || String(p.victim_mk || '') !== vmk) continue
    const a = Math.trunc(p.start || 0)
    const b = Math.trunc(p.stop || a)
    if (lo != null && hi != null && (b <= lo || a >= hi)) continue
    sel.push(p)
  }
  sel.sort((a, b) => Math.trunc(a.start || 0) - Math.trunc(b.start || 0)
    || Math.trunc(b.duration || 0) - Math.trunc(a.duration || 0))
  const names = []
  for (const p of sel) {
    const name = String(p.preemptor || p.preemptor_mk || '')
    if (name && names[names.length - 1] !== name) names.push(name)
    if (names.length >= 6) break
  }
  const victim = String((sel[0] && sel[0].victim) || vmk)
  if (!names.length) return victim ? `${victim} → resumed` : ''
  return `${victim} → ${names.join(' → ')} → resumed`
}

export function preemptorRanking(pairs, limit = 16) {
  const byV = new Map()
  for (const p of pairs || []) {
    const vmk = String(p.victim_mk || '')
    const pmk = String(p.preemptor_mk || '')
    if (!vmk || !pmk) continue
    if (!byV.has(vmk)) {
      byV.set(vmk, {
        task: p.victim, mk: vmk, count: 0, total_ns: 0, max_ns: 0,
        preemptors: {}, worst: p, section: 'preempt_matrix',
      })
    }
    const rec = byV.get(vmk)
    rec.count += 1
    const dur = Math.trunc(p.duration || 0)
    rec.total_ns += dur
    if (dur > rec.max_ns) {
      rec.max_ns = dur
      rec.worst = p
    }
    if (!rec.preemptors[pmk]) rec.preemptors[pmk] = { task: p.preemptor, mk: pmk, count: 0, total_ns: 0 }
    rec.preemptors[pmk].count += 1
    rec.preemptors[pmk].total_ns += dur
  }
  const rows = [...byV.values()]
  for (const rec of rows) {
    rec.top = Object.values(rec.preemptors)
      .sort((a, b) => (b.count - a.count) || (b.total_ns - a.total_ns))
      .slice(0, 4)
    rec.top_label = rec.top.map(t => `${t.task} (${t.count})`).join(', ')
    rec.story = preemptionStory(pairs, rec.mk)
  }
  rows.sort((a, b) => (b.total_ns - a.total_ns) || String(a.task).localeCompare(String(b.task)))
  return rows.slice(0, Math.max(1, Math.min(40, limit)))
}

export function preemptionMatrix(pairs, limit = 12) {
  const totals = new Map()
  const names = new Map()
  const invol = new Map()
  for (const p of pairs || []) {
    const vk = String(p.victim_mk || '')
    const pk = String(p.preemptor_mk || '')
    if (!vk || !pk) continue
    const key = `${vk}|${pk}`
    const rec = totals.get(key) || { count: 0, ns: 0, worst: p }
    rec.count += 1
    rec.ns += Math.trunc(p.duration || 0)
    if (Math.trunc(p.duration || 0) > Math.trunc(rec.worst.duration || 0)) rec.worst = p
    totals.set(key, rec)
    names.set(vk, String(p.victim || vk))
    names.set(pk, String(p.preemptor || pk))
    invol.set(vk, (invol.get(vk) || 0) + Math.trunc(p.duration || 0))
    invol.set(pk, (invol.get(pk) || 0) + Math.trunc(p.duration || 0))
  }
  const lim = Math.max(2, Math.min(16, Number(limit) || 12))
  const tasks = [...invol.keys()]
    .sort((a, b) => (invol.get(b) - invol.get(a)) || String(names.get(a)).localeCompare(String(names.get(b))))
    .slice(0, lim)
  const taskSet = new Set(tasks)
  const cells = {}
  for (const [key, rec] of totals) {
    const [vk, pk] = key.split('|')
    if (!taskSet.has(vk) || !taskSet.has(pk)) continue
    cells[key] = {
      count: rec.count,
      ns: rec.ns,
      start: Math.trunc(rec.worst.start || 0),
      jump_ns: Math.trunc(rec.worst.jump_ns || rec.worst.start || 0),
      victim: names.get(vk) || vk,
      preemptor: names.get(pk) || pk,
      section: 'preempt_matrix',
    }
  }
  return { tasks: tasks.map(mk => ({ mk, task: names.get(mk) || mk })), cells }
}

export function mutexBlockingTable(waits, limit = 24) {
  const byKey = new Map()
  for (const w of waits || []) {
    if (!w) continue
    const wk = String(w.waiter_mk || '')
    const obj = String(w.object || '')
    if (!wk || !obj) continue
    const key = `${wk}|${obj}`
    const rec = byKey.get(key) || {
      task: w.waiter, mk: wk, object: obj, owner: w.owner,
      count: 0, total_ns: 0, max_ns: 0, worst: w, section: 'mutex_block',
    }
    const dur = Math.trunc(w.duration || 0)
    rec.count += 1
    rec.total_ns += dur
    if (dur > rec.max_ns) {
      rec.max_ns = dur
      rec.worst = w
      rec.owner = w.owner
    }
    byKey.set(key, rec)
  }
  return [...byKey.values()]
    .sort((a, b) => (b.total_ns - a.total_ns) || String(a.task).localeCompare(String(b.task)))
    .slice(0, Math.max(1, Math.min(60, limit)))
}

export function coreUtilOverTime(events, cores = [], lo = null, hi = null, bins = CORE_TIME_BINS) {
  const execs = (events || []).filter(e => e && e.kind === 'exec')
  if (!execs.length) return { cores: [...(cores || [])], bins: [], bin_ns: 0, lo: 0, hi: 0 }
  const t0 = lo != null ? Math.trunc(lo) : Math.min(...execs.map(e => Math.trunc(e.start || 0)))
  const t1raw = hi != null ? Math.trunc(hi) : Math.max(...execs.map(e => Math.trunc(e.stop || 0)))
  const t1 = t1raw > t0 ? t1raw : t0 + 1
  const n = Math.max(4, Math.min(32, Number(bins) || CORE_TIME_BINS))
  const width = Math.max(1, (t1 - t0) / n)
  const coreList = [...(cores || [])].map(c => String(c || '')).filter(Boolean)
  const busy = new Map()
  for (const ev of execs) {
    const core = String(ev.core || '')
    if (!core) continue
    if (!coreList.includes(core)) coreList.push(core)
    if (!busy.has(core)) busy.set(core, Array(n).fill(0))
    let a = Math.trunc(ev.start || 0)
    let b = Math.trunc(ev.stop || a)
    if (b <= t0 || a >= t1) continue
    a = Math.max(a, t0)
    b = Math.min(b, t1)
    const i0 = Math.min(n - 1, Math.max(0, Math.trunc((a - t0) / width)))
    const i1 = Math.min(n - 1, Math.max(0, Math.trunc((b - 1 - t0) / width)))
    for (let i = i0; i <= i1; i++) {
      const blo = t0 + i * width
      const bhi = t0 + (i + 1) * width
      busy.get(core)[i] += Math.max(0, Math.min(b, bhi) - Math.max(a, blo))
    }
  }
  const rows = []
  for (let i = 0; i < n; i++) {
    const start = Math.trunc(t0 + i * width)
    const stop = Math.trunc(t0 + (i + 1) * width)
    const cells = {}
    let peak = 0
    let peakCore = ''
    for (const c of coreList) {
      const ns = (busy.get(c) || [])[i] || 0
      const pct = 100 * ns / width
      cells[c] = { ns: Math.trunc(ns), pct: Math.round(pct * 10) / 10 }
      if (pct > peak) {
        peak = pct
        peakCore = c
      }
    }
    rows.push({
      index: i, start, stop, jump_ns: start, cells,
      peak_pct: Math.round(peak * 10) / 10, peak_core: peakCore, section: 'core_time',
    })
  }
  return { cores: coreList, bins: rows, bin_ns: Math.trunc(width), lo: t0, hi: t1, section: 'core_time' }
}

export function coreBusyAnomalies(events, bins = CORE_TIME_BINS) {
  const grid = coreUtilOverTime(events, [], null, null, bins)
  return (grid.bins || []).filter(row => Number(row.peak_pct || 0) >= 90).map(row => ({
    kind: 'cpu',
    task: row.peak_core || 'CPU',
    mk: row.peak_core || '',
    start: row.start,
    stop: row.stop,
    duration: Math.trunc(row.stop || 0) - Math.trunc(row.start || 0),
    jump_ns: row.jump_ns,
    core: row.peak_core || '',
    section: 'cores',
    reason: `CPU ${row.peak_core} utilization spike ${row.peak_pct}%`,
  }))
}

export function idleGapAnomalies(events) {
  const byCore = new Map()
  for (const ev of events || []) {
    if (!ev || ev.kind !== 'exec' || !ev.core) continue
    const core = String(ev.core)
    if (!byCore.has(core)) byCore.set(core, [])
    byCore.get(core).push(ev)
  }
  const out = []
  for (const [core, group] of byCore) {
    group.sort((a, b) => Number(a.start || 0) - Number(b.start || 0))
    const gaps = []
    for (let i = 1; i < group.length; i++) {
      const gap = Math.trunc(group[i].start || 0) - Math.trunc(group[i - 1].stop || 0)
      if (gap > 0) gaps.push([gap, Math.trunc(group[i - 1].stop || 0), Math.trunc(group[i].start || 0)])
    }
    if (gaps.length < 4) continue
    const vals = gaps.map(g => g[0])
    const mean = vals.reduce((s, v) => s + v, 0) / vals.length
    const sigma = Math.sqrt(vals.reduce((s, v) => s + (v - mean) ** 2, 0) / vals.length)
    const thresh = sigma > 0 ? mean + 3 * sigma : Math.max(...vals)
    for (const [gap, start, stop] of gaps) {
      if (gap > thresh && gap >= mean) {
        out.push({
          kind: 'idle',
          task: core,
          mk: core,
          start,
          stop,
          duration: gap,
          jump_ns: start,
          core,
          section: 'cores',
          reason: `unusual idle on ${core}`,
        })
      }
    }
  }
  return out
}

export function distributionMetricSamples(events, kind, mk, dispatchByMk = null) {
  const k = String(kind || 'exec')
  const key = String(mk || '')
  if (!key) return []
  if (k === 'dispatch') {
    const raw = dispatchByMk?.[key] || []
    return raw.map(v => Math.trunc(v || 0)).filter(v => v > 0)
  }
  if (k === 'response' || k === 'wakeup') {
    const out = []
    for (const ev of analyzeResponseTimes(events).events || []) {
      if (String(ev.mk || ev.task || '') !== key) continue
      const dur = Math.trunc((k === 'wakeup' ? ev.wait_ns : ev.duration) || 0)
      if (dur > 0) out.push(dur)
    }
    return out
  }
  if (k === 'preempt') {
    return preemptionPairs(events)
      .filter(p => String(p.victim_mk || p.mk || '') === key)
      .map(p => Math.trunc(p.duration || 0))
      .filter(v => v > 0)
  }
  return (events || [])
    .filter(e => e && e.kind === k && String(e.mk || e.task || '') === key)
    .map(e => Math.trunc(e.duration || 0))
    .filter(v => v > 0)
}

export function distributionExplorer(events, kind, mk, dispatchByMk = null) {
  const samples = distributionMetricSamples(events, kind, mk, dispatchByMk)
  const stats = durationStats(samples)
  if (!stats) return null
  const plotKind = ({ wakeup: 'block', preempt: 'preempt' })[String(kind || '')] || String(kind || 'exec')
  return {
    ...stats,
    kind: String(kind || 'exec'),
    mk,
    spark: sparkline(samples),
    plot_kind: plotKind,
    section: 'distrib',
    n_samples: samples.length,
  }
}

export function unifiedJitter(events, dispatchByMk = null) {
  const byMk = new Map()
  const resp = analyzeResponseTimes(events).events || []

  const ensure = (mk, task) => {
    if (!byMk.has(mk)) {
      byMk.set(mk, {
        task: task || mk, mk,
        exec: [], block: [], inter: [], response: [], dispatch: [], wakeup: [],
        section: 'jitter',
      })
    }
    return byMk.get(mk)
  }

  for (const ev of [...(events || []), ...resp]) {
    if (!ev) continue
    const mk = String(ev.mk || ev.task || '')
    const kind = String(ev.kind || '')
    if (!mk || !['exec', 'block', 'inter', 'response'].includes(kind)) continue
    const rec = ensure(mk, ev.task || mk)
    const dur = Math.trunc(ev.duration || 0)
    if (dur > 0) rec[kind].push(dur)
    if (kind === 'response') {
      const wait = Math.trunc(ev.wait_ns || 0)
      if (wait > 0) rec.wakeup.push(wait)
    }
  }
  for (const [mk, samples] of Object.entries(dispatchByMk || {})) {
    const rec = ensure(String(mk), String(mk))
    rec.dispatch.push(...(samples || []).map(s => Math.trunc(s || 0)).filter(v => v > 0))
  }
  const rows = []
  const keys = ['exec', 'block', 'inter', 'response', 'dispatch', 'wakeup']
  for (const rec of byMk.values()) {
    const row = { task: rec.task, mk: rec.mk, section: 'jitter' }
    let empty = true
    for (const key of keys) {
      const stats = durationStats(rec[key])
      row[`${key}_jitter_ns`] = stats ? stats.jitter_ns : 0
      row[`${key}_cv`] = stats ? stats.cv : 0
      if (stats) empty = false
    }
    if (!empty) rows.push(row)
  }
  rows.sort((a, b) => (
    Math.max(b.response_jitter_ns, b.exec_jitter_ns, b.dispatch_jitter_ns)
    - Math.max(a.response_jitter_ns, a.exec_jitter_ns, a.dispatch_jitter_ns)
    || String(a.task).localeCompare(String(b.task))
  ))
  return rows
}

export function recurringPatterns(anomalies, minCount = 2) {
  const byKey = new Map()
  for (const ev of anomalies || []) {
    if (!ev) continue
    const task = String(ev.task || ev.mk || '')
    const kind = String(ev.kind || '')
    if (!task || !kind) continue
    const key = `${task}|${kind}`
    const rec = byKey.get(key) || {
      task, mk: ev.mk || task, kind, count: 0, worst: ev, section: 'patterns',
    }
    rec.count += 1
    if (Math.trunc(ev.duration || 0) > Math.trunc(rec.worst.duration || 0)) rec.worst = ev
    byKey.set(key, rec)
  }
  return [...byKey.values()]
    .filter(r => r.count >= minCount)
    .map((rec) => {
      const worst = rec.worst
      return {
        ...rec,
        start: worst.start,
        stop: worst.stop,
        jump_ns: worst.jump_ns || worst.start,
        duration: worst.duration,
        reason: `${rec.count}× ${KIND_LABEL[rec.kind] || rec.kind} for ${rec.task}`,
      }
    })
    .sort((a, b) => (b.count - a.count) || (Math.trunc(b.duration || 0) - Math.trunc(a.duration || 0)))
}

export function topBlockingContributors(events, mutexWaits = null, limit = 12) {
  const pairs = preemptionPairs(events)
  const preempt = new Map()
  for (const p of pairs) {
    const mk = String(p.victim_mk || '')
    if (!mk) continue
    const rec = preempt.get(mk) || { task: p.victim || mk, ns: 0, worst: p }
    const dur = Math.trunc(p.duration || 0)
    rec.ns += dur
    if (dur > Math.trunc(rec.worst.duration || 0)) rec.worst = p
    preempt.set(mk, rec)
  }
  const mutex = new Map()
  for (const w of mutexWaits || []) {
    if (!w) continue
    const mk = String(w.waiter_mk || w.mk || '')
    if (!mk) continue
    const rec = mutex.get(mk) || { task: w.waiter || w.task || mk, ns: 0, worst: w }
    const dur = Math.trunc(w.duration || 0)
    rec.ns += dur
    if (dur > Math.trunc(rec.worst.duration || 0)) rec.worst = w
    mutex.set(mk, rec)
  }
  const block = new Map()
  for (const ev of events || []) {
    if (!ev || ev.kind !== 'block') continue
    const mk = String(ev.mk || '')
    if (!mk) continue
    const rec = block.get(mk) || { task: ev.task || mk, ns: 0, worst: ev }
    const dur = Math.trunc(ev.duration || 0)
    rec.ns += dur
    if (dur > Math.trunc(rec.worst.duration || 0)) rec.worst = ev
    block.set(mk, rec)
  }
  const keys = new Set([...preempt.keys(), ...mutex.keys(), ...block.keys()])
  const rows = []
  for (const mk of keys) {
    const mutexNs = Math.trunc(mutex.get(mk)?.ns || 0)
    const preemptNs = Math.trunc(preempt.get(mk)?.ns || 0)
    const blockNs = Math.trunc(block.get(mk)?.ns || 0)
    const idleNs = Math.max(0, blockNs - preemptNs)
    const total = mutexNs + preemptNs + idleNs
    if (total <= 0) continue
    let worst = null
    for (const src of [mutex.get(mk), preempt.get(mk), block.get(mk)]) {
      const cand = src?.worst
      if (!cand) continue
      if (!worst || Math.trunc(cand.duration || 0) > Math.trunc(worst.duration || 0)) worst = cand
    }
    rows.push({
      task: mutex.get(mk)?.task || preempt.get(mk)?.task || block.get(mk)?.task || mk,
      mk,
      mutex_ns: mutexNs,
      preempt_ns: preemptNs,
      idle_ns: idleNs,
      total_ns: total,
      worst: worst || {},
      section: 'mutex_block',
      reason: `mutex ${mutexNs} · preempt ${preemptNs} · idle ${idleNs}`,
    })
  }
  rows.sort((a, b) => (b.total_ns - a.total_ns) || String(a.task).localeCompare(String(b.task)))
  return rows.slice(0, Math.max(1, Math.min(40, Number(limit) || 12)))
}

export function recurringPatternsAcross(anomaliesA, anomaliesB, minCount = 1) {
  const index = (anoms) => {
    const byKey = new Map()
    for (const ev of anoms || []) {
      if (!ev) continue
      const task = String(ev.task || ev.mk || '')
      const kind = String(ev.kind || '')
      if (!task || !kind) continue
      const key = `${task}|${kind}`
      const rec = byKey.get(key) || { count: 0, worst: ev }
      rec.count += 1
      if (Math.trunc(ev.duration || 0) > Math.trunc(rec.worst.duration || 0)) rec.worst = ev
      byKey.set(key, rec)
    }
    return byKey
  }
  const need = Math.max(1, Number(minCount) || 1)
  const a = index(anomaliesA)
  const b = index(anomaliesB)
  const rows = []
  for (const key of a.keys()) {
    if (!b.has(key)) continue
    if (a.get(key).count < need || b.get(key).count < need) continue
    const [task, kind] = key.split('|')
    const wa = a.get(key).worst
    const wb = b.get(key).worst
    const worst = Math.trunc(wa.duration || 0) >= Math.trunc(wb.duration || 0) ? wa : wb
    rows.push({
      task,
      mk: worst.mk || task,
      kind,
      count_a: a.get(key).count,
      count_b: b.get(key).count,
      worst,
      start: worst.start,
      stop: worst.stop,
      jump_ns: worst.jump_ns || worst.start,
      duration: worst.duration,
      section: 'patterns',
      reason: `${a.get(key).count}× / ${b.get(key).count}× ${KIND_LABEL[kind] || kind} for ${task}`,
    })
  }
  rows.sort((x, y) => (
    (y.count_a + y.count_b) - (x.count_a + x.count_b)
    || Math.trunc(y.duration || 0) - Math.trunc(x.duration || 0)
  ))
  return rows
}

export function compareAnalysisTables(traceA, traceB, loA = null, hiA = null, loB = null, hiB = null, deadlines = null) {
  const evsA = harvestUxEvents(traceA, loA, hiA)
  const evsB = harvestUxEvents(traceB, loB, hiB)
  const waitsA = pairMutexWaits(harvestMutexHolds(traceA, loA, hiA))
  const waitsB = pairMutexWaits(harvestMutexHolds(traceB, loB, hiB))
  const ra = analyzeResponseTimes(evsA).rows || []
  const rb = analyzeResponseTimes(evsB).rows || []
  const byA = new Map(ra.map(r => [String(r.task || r.mk), r]))
  const byB = new Map(rb.map(r => [String(r.task || r.mk), r]))
  const names = [...new Set([...byA.keys(), ...byB.keys()])].sort()
  const responseRows = []
  let worstP99A = 0
  let worstP99B = 0
  for (const name of names) {
    const pa = Math.trunc(byA.get(name)?.p99_ns || 0)
    const pb = Math.trunc(byB.get(name)?.p99_ns || 0)
    worstP99A = Math.max(worstP99A, pa)
    worstP99B = Math.max(worstP99B, pb)
    if (pa || pb) responseRows.push({ name, p99_a: pa, p99_b: pb, delta_ns: pa - pb })
  }
  responseRows.sort((a, b) => Math.abs(b.delta_ns) - Math.abs(a.delta_ns))
  const ma = mutexBlockingTable(waitsA)
  const mb = mutexBlockingTable(waitsB)
  const mutexA = new Map(ma.map(r => [String(r.task || r.mk), r]))
  const mutexB = new Map(mb.map(r => [String(r.task || r.mk), r]))
  const mutexRows = []
  let mutexNsA = 0
  let mutexNsB = 0
  for (const name of [...new Set([...mutexA.keys(), ...mutexB.keys()])].sort()) {
    const ta = Math.trunc(mutexA.get(name)?.total_ns || 0)
    const tb = Math.trunc(mutexB.get(name)?.total_ns || 0)
    mutexNsA += ta
    mutexNsB += tb
    mutexRows.push({ name, total_a: ta, total_b: tb, delta_ns: ta - tb })
  }
  mutexRows.sort((a, b) => Math.abs(b.delta_ns) - Math.abs(a.delta_ns))
  const dlMap = {}
  for (const [k, v] of Object.entries(deadlines || {})) {
    const n = Math.trunc(v || 0)
    if (n > 0) dlMap[String(k)] = n
  }
  let missesA = 0
  let missesB = 0
  if (Object.keys(dlMap).length) {
    for (const ev of analyzeResponseTimes(evsA).events || []) {
      const lim = dlMap[String(ev.mk || '')] || dlMap[String(ev.task || '')]
      if (lim && Math.trunc(ev.duration || 0) > lim) missesA += 1
    }
    for (const ev of analyzeResponseTimes(evsB).events || []) {
      const lim = dlMap[String(ev.mk || '')] || dlMap[String(ev.task || '')]
      if (lim && Math.trunc(ev.duration || 0) > lim) missesB += 1
    }
  }
  const shared = recurringPatternsAcross(
    detectTimelineAnomalies(evsA, 12, waitsA, dlMap),
    detectTimelineAnomalies(evsB, 12, waitsB, dlMap),
  )
  return {
    response: responseRows.slice(0, 15),
    mutex_block: mutexRows.slice(0, 15),
    metrics: {
      response_p99_a: worstP99A,
      response_p99_b: worstP99B,
      mutex_ns_a: mutexNsA,
      mutex_ns_b: mutexNsB,
      deadline_misses_a: missesA,
      deadline_misses_b: missesB,
    },
    shared_patterns: shared.slice(0, 6),
  }
}

export function compareWhy(strip) {
  const regs = [...(strip?.regressions || [])]
  const shared = [...(strip?.shared_patterns || strip?.sharedPatterns || [])]
  if (!regs.length && !shared.length) return 'No positive regressions in the compared tables.'
  const blob = regs.map(r => String(r.label || '')).join(' ').toLowerCase()
  let why
  if (regs.length) {
    const parts = regs.slice(0, 4).map(r => `${r.label} ${r.delta}`)
    why = `Largest regressions: ${parts.join('; ')}.`
  } else {
    why = 'No positive regressions in the compared tables.'
  }
  if (blob.includes('deadline')) {
    why += ' Open Deadlines / CPU budget and Timeline Anomalies.'
  } else if (blob.includes('response') && (blob.includes('mutex') || blob.includes('block'))) {
    why += ' Response P99 moved with blocking — check Mutex Blocking and Critical Path.'
  } else if (blob.includes('response')) {
    why += ' Open Response Time and click p99.'
  } else if (blob.includes('mutex')) {
    why += ' Open Mutex Blocking and Waiter × Owner.'
  } else if (blob.includes('block') && (blob.includes('exec') || blob.includes('max'))) {
    why += ' Blocking and execution tails moved together — check Waiter × Owner and Worst Events.'
  } else if (blob.includes('migrat')) {
    why += ' Open Task × Core and Timeline Anomalies for migration bursts.'
  } else if (blob.includes('block')) {
    why += ' Open Waiter × Owner and Blocking p95/p99.'
  } else if (regs.length) {
    why += ' Open the matching Statistics table and click p95/p99.'
  }
  if (shared.length) {
    const top = shared[0]
    why += ` Shared pattern: ${top.reason || top.kind || 'anomaly'}.`
  }
  return why
}
