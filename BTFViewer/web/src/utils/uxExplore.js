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
})

export const MUTEX_HANDOFF_SLACK_NS = 1_000_000
export const PERIOD_MISS_RATIO = 1.5
export const PERIOD_EXTRA_RATIO = 0.5
export const HEALTH_MARK = Object.freeze({ ok: '✓', warn: '⚠', fail: '❌' })
export const HEALTH_BAND_SECTION = Object.freeze({
  execution: 'exec',
  blocking: 'block',
  period: 'period',
  migration: 'migrations',
  deadline: 'deadline',
  cpu: 'tasks',
})

const KIND_LABEL = {
  exec: 'execution',
  block: 'blocking',
  inter: 'inter-arrival',
  migration: 'migration',
}

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
  const rows = (events || []).filter(e => e && ['exec', 'block', 'inter'].includes(e.kind))
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

export function detectTimelineAnomalies(events, limit = 12) {
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
  return { headline, regressions: topCompareRegressions(cands, limit) }
}

export function harvestUxEvents(trace, lo = null, hi = null) {
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
  rows.sort((a, b) => Number(a.start) - Number(b.start))
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
      min_ev: evFor(minG),
      max_ev: evFor(maxG),
      p50_ev: evFor(Math.trunc(expected)),
      p95_ev: evFor(p95),
      p99_ev: evFor(p99),
      worst_ev: { ...worst },
      miss_ev: { ...(missEv || worst) },
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
