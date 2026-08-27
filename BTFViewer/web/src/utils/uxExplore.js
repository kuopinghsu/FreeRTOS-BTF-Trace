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

export function formatBurstWindowNs(windowNs) {
  const ns = Math.trunc(windowNs || 0)
  if (ns <= 0) return '0 ns'
  if (ns % 1_000_000_000 === 0) return `${ns / 1_000_000_000} s`
  if (ns % 1_000_000 === 0) return `${ns / 1_000_000} ms`
  if (ns % 1_000 === 0) return `${ns / 1_000} µs`
  if (ns >= 1_000_000) return `${ns / 1_000_000} ms`
  if (ns >= 1_000) return `${ns / 1_000} µs`
  return `${ns} ns`
}

export function formatBurstReason(count, label, windowNs) {
  const stem = String(label || '').replace(/ burst$/, '').trim() || 'event'
  return `${Number(count).toLocaleString('en-US')} ${stem}s within ${formatBurstWindowNs(windowNs)}`
}

const JUMP_RE = /jump:([0-9]+(?:\.[0-9]+)?)/gi
const TASK_RE = /\b([A-Za-z_][\w.-]*\[\d+\])/
const DELTA_RE = /^([+\-−])?\s*([\d.]+)\s*(?:(ns|µs|us|μs|ms|s|\/s|%|pp)(\/s)?)?$/i
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
  'Context switches /s',
  'Migrations (total)',
  'Migrations /s',
  'Missed ticks (est.)',
  'Response P99 (worst task)',
  'Mutex blocking (total)',
  'Mutex blocking /s',
  'Blocking time /s',
  'Deadline misses',
])
export const COMPARE_DELTA_FORMULA =
  'Δ = Baseline A − Candidate B (positive means A is larger). '
  + '— = unavailable (not zero). '
  + 'pp = percentage points. '
  + 'STI = software trace item; σ = util stddev; '
  + 'Dwell = avg on-CPU slice; Ping = A↔B core ping-pong; '
  + 'P99 = 99th percentile; /tick = per TICK period.'
export const COMPARE_NOTABLE_REL = 0.05
export const COMPARE_NOTABLE_TIME_NS = 50_000
export const COMPARE_NOTABLE_COUNT = 2
export const COMPARE_NOTABLE_COUNT_ABS = 50
export const COMPARE_NOTABLE_PP = 1.0
const TASK_PAREN_RE = /\(([^)]+)\)\s*$/
const VALUE_PAREN_RE = /\s*\([^)]*\)\s*$/

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
  // Callers pass merge keys (`\0id\0name`); show Name[id], not NULs.
  const raw = String(task || '').trim()
  const name = raw ? taskDisplayName(raw) : ''
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
  let s = String(text ?? '').trim().replace(/−/g, '-').replace(/,/g, '')
  s = s.replace(VALUE_PAREN_RE, '').trim()
  if (!s || s === '—' || s === '–' || s === '-') return null
  const m = DELTA_RE.exec(s)
  if (!m) return null
  const sign = m[1] === '-' ? -1 : 1
  const val = Number(m[2])
  if (!Number.isFinite(val)) return null
  const unit = String(m[3] || '').toLowerCase()
  const perS = Boolean(m[4])
  if (unit in UNIT_NS) {
    const signedNs = sign * val * UNIT_NS[unit]
    return { signed: signedNs, kind: perS ? 'rate' : 'time' }
  }
  if (unit === '%' || unit === 'pp') return { signed: sign * val, kind: 'pct' }
  if (unit === '/s') return { signed: sign * val, kind: 'rate' }
  return { signed: sign * val, kind: 'count' }
}

/** Numeric/time-aware sort key for Trace Compare cells (desktop `_StatsSortItem` parity). */
export function compareCellSortKey(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  const parsed = parseSignedDelta(value)
  if (parsed && Number.isFinite(parsed.signed)) return parsed.signed
  const s = String(value ?? '').trim()
  if (!s || s === '—' || s === '–' || s === '-') return Number.NEGATIVE_INFINITY
  return s.toLowerCase()
}

export function compareFieldSortAccessors(keys) {
  const acc = {}
  for (const key of keys) {
    acc[key] = (row) => {
      if (Array.isArray(row)) {
        const idx = Number(key)
        return compareCellSortKey(Number.isInteger(idx) ? row[idx] : undefined)
      }
      return compareCellSortKey(row?.[key])
    }
  }
  return acc
}

export function compareCandidatesFromTables(tables) {
  if (!tables || typeof tables !== 'object') return []
  const out = []
  for (const row of tables.summary || []) {
    const { label, delta, a, b } = rowCells(row, 'label', 'delta', 0, 3)
    if (!label || skipSummaryLabel(label)) continue
    const parsed = parseSignedDelta(delta)
    if (!parsed) continue
    out.push({ label, metric: 'summary', delta: String(delta), a, b, ...parsed })
  }
  const specs = [
    ['execution', 'exec max', 0, 7, 'name', 'deltaMax', 5, 6, 'maxA', 'maxB'],
    ['blocking', 'block avg', 0, 7, 'name', 'delta', 3, 4, 'avgA', 'avgB'],
    ['inter_arrival', 'inter avg', 0, 7, 'name', 'delta', 3, 4, 'avgA', 'avgB'],
    ['interArrival', 'inter avg', 0, 7, 'name', 'delta', 3, 4, 'avgA', 'avgB'],
    ['response', 'response p99', 0, 3, 'name', 'delta', 1, 2, 'a', 'b'],
    ['mutex_block', 'mutex block', 0, 3, 'name', 'delta', 1, 2, 'a', 'b'],
    ['mutexBlock', 'mutex block', 0, 3, 'name', 'delta', 1, 2, 'a', 'b'],
    ['deadlines', 'deadline misses', 0, 3, 'name', 'delta', 1, 2, 'a', 'b'],
  ]
  for (const [key, metric, nameIdx, deltaIdx, nameKey, deltaKey, aIdx, bIdx, aKey, bKey] of specs) {
    for (const row of tables[key] || []) {
      const { label: name, delta, a, b } = rowCells(
        row, nameKey, deltaKey, nameIdx, deltaIdx, aKey, bKey, aIdx, bIdx)
      if (!name) continue
      const parsed = parseSignedDelta(delta)
      if (!parsed) continue
      out.push({
        label: `${name} ${metric}`,
        metric,
        delta: String(delta),
        a,
        b,
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

export function compareSummaryStrip(tables, limit = 4, nameA = '', nameB = '') {
  const headline = []
  for (const row of tables?.summary || []) {
    const { label, delta } = rowLabelDelta(row, 'label', 'delta', 0, 3)
    if (SUMMARY_STRIP_LABELS.has(label)) {
      headline.push({ label: label.replace(' (cursor range)', ''), delta: String(delta) })
    }
  }
  const notable = compareNotableChanges(tables, limit, nameA, nameB)
  const rows = [...(notable.rows || [])]
  const regressions = rows.filter(r => r.status === 'Regressed')
  const improvements = rows.filter(r => r.status === 'Improved')
  const shared = [...(tables?.shared_patterns || tables?.sharedPatterns || [])]
  let why = String(notable.verdict || '').trim()
  const hint = compareWhy({ regressions, shared_patterns: shared })
  if (hint && !hint.startsWith('No positive')) why = `${why} ${hint}`.trim()
  return {
    headline,
    regressions,
    improvements,
    notable,
    warnings: [...(notable.warnings || [])],
    shared_patterns: shared,
    why: why || hint,
    formula: COMPARE_DELTA_FORMULA,
  }
}

/** Dialog-matching regression result for the Trace Compare HTML Summary card. */
export function compareSummaryDecisionHtml(tables, nameA = '', nameB = '') {
  const data = compareSummaryStrip(tables, 4, nameA, nameB)
  const notable = data.notable || {}
  const identity = notable.identity || {}
  const idA = identity.a || {}
  const idB = identity.b || {}
  const cards = notable.cards || {}
  const regs = data.regressions || []
  const nReg = Number(cards.regressions ?? regs.length) || 0
  const nImp = Number(cards.improvements ?? (data.improvements || []).length) || 0
  const nWarn = Number(cards.warnings ?? (data.warnings || []).length) || 0
  const top = regs[0]
  const largest = top
    ? `Largest regression — ${top.label}: ${top.change}`
    : (String(notable.verdict || '').trim() || 'No significant regressions')
  const why = String(data.why || '').trim()
  const next = String(notable.next_investigation || '').trim()
  const omitted = Number(notable.small_omitted_count || 0) || 0
  const sigNote = (Number(cards.significant || 0) || omitted)
    ? 'Showing engineering-significant deltas only (small changes omitted)'
    : ''
  const visible = !!(nReg || nImp || nWarn || top || why || next || notable.verdict)
  if (!visible) return ''
  const ident =
    `Baseline: ${nameA || 'Baseline'} · Scope ${idA.span || 'Full Trace'}    |    ` +
    `Candidate: ${nameB || 'Candidate'} · Scope ${idB.span || 'Full Trace'}`
  const counts =
    `${nReg} REGRESSIONS    ${nImp} IMPROVEMENTS` +
    (nWarn ? `    ${nWarn} WARNING${nWarn === 1 ? '' : 'S'}` : '')
  const parts = [
    '<div class="compare-decision">',
    `<div class="compare-decision-identity">${svgEscape(ident)}</div>`,
    `<div class="compare-decision-counts">${svgEscape(counts)}</div>`,
    `<div class="compare-decision-largest">${svgEscape(largest)}</div>`,
  ]
  if (why) parts.push(`<div class="compare-decision-why">Why? ${svgEscape(why)}</div>`)
  if (next) parts.push(`<div class="compare-decision-next">${svgEscape(next)}</div>`)
  if (sigNote) parts.push(`<div class="compare-decision-sig">${svgEscape(sigNote)}</div>`)
  parts.push('</div>')
  return parts.join('')
}

function compareSummaryPair(tables, prefix) {
  for (const row of tables?.summary || []) {
    const { label, a, b } = rowCells(row, 'label', 'delta', 0, 3)
    if (label === prefix || (prefix === 'Span' && String(label).startsWith('Span'))) {
      return [a != null ? String(a) : '—', b != null ? String(b) : '—']
    }
  }
  return ['—', '—']
}

export function compareTickModeWarnings(nameA, nameB, modeA, modeB) {
  const warnings = []
  const ma = String(modeA || '').trim().toUpperCase()
  const mb = String(modeB || '').trim().toUpperCase()
  const skip = new Set(['', '—', '-', 'UNKNOWN'])
  if (!skip.has(ma) && !skip.has(mb) && ma !== mb) {
    warnings.push(`Tick mode differs: Baseline A is ${ma}, Candidate B is ${mb}.`)
  }
  for (const [name, mode, side] of [[nameA, ma, 'Baseline A'], [nameB, mb, 'Candidate B']]) {
    const low = String(name || '').toLowerCase()
    if (low.includes('tickful') && mode === 'TICKLESS') {
      warnings.push(`${side} filename suggests tickful, but detection is ${mode}.`)
    }
    if (low.includes('tickless') && mode === 'TICK') {
      warnings.push(`${side} filename suggests tickless, but detection is ${mode}.`)
    }
  }
  return warnings
}

function compareMetricPolarity(label, metric = '') {
  const blob = `${label} ${metric}`.toLowerCase()
  if (blob.includes('tick health') || blob.includes('tick mode')) return null
  if (blob.includes('load balance score')) return 'better'
  if (['response', 'mutex', 'deadline', 'block', 'migrat', 'core gap',
    'context switch', 'missed tick', 'preempt', 'ping', 'σ', 'sigma',
    'bounce', 'affinity', 'issues', 'exec max'].some(k => blob.includes(k))) {
    return 'worse'
  }
  if (blob.includes('inter')) return 'worse'
  return null
}

function compareChangeIsSignificant(signed, kind, aMag, bMag) {
  const mag = Math.abs(Number(signed || 0))
  if (mag <= 0) return false
  const base = Math.max(Number(aMag || 0), Number(bMag || 0), 1e-12)
  const rel = mag / base
  if (kind === 'time') return mag >= COMPARE_NOTABLE_TIME_NS || rel >= COMPARE_NOTABLE_REL
  if (kind === 'pct') return mag >= COMPARE_NOTABLE_PP
  if (kind === 'count') {
    return mag >= COMPARE_NOTABLE_COUNT_ABS
      || (mag >= COMPARE_NOTABLE_COUNT && rel >= COMPARE_NOTABLE_REL)
  }
  if (kind === 'rate') return rel >= COMPARE_NOTABLE_REL
  return rel >= COMPARE_NOTABLE_REL
}

function compareStatus(polarity, signed) {
  if (polarity === 'worse') {
    if (signed < 0) return 'Regressed'
    if (signed > 0) return 'Improved'
  } else if (polarity === 'better') {
    if (signed > 0) return 'Regressed'
    if (signed < 0) return 'Improved'
  }
  return 'Changed'
}

function cellMagnitude(text) {
  const parsed = parseSignedDelta(text)
  return parsed ? Math.abs(Number(parsed.signed)) : null
}

function flipDeltaText(text) {
  const s = String(text || '').trim()
  if (!s || s === '—' || s === '–' || s === '0' || s === '0.0') return s
  if (s[0] === '+') return `−${s.slice(1)}`
  if (s[0] === '-' || s[0] === '−') return `+${s.slice(1)}`
  return `+${s}`
}

function taskFromCell(text) {
  const m = TASK_PAREN_RE.exec(String(text || ''))
  return m ? m[1].trim() : ''
}

export const COMPARE_INVESTIGATE_FALLBACK_SECTION = 'response'
export const COMPARE_SECTION_LABELS = Object.freeze({
  response: 'Response Time',
  exec: 'Execution Time',
  block: 'Blocking Time',
  inter: 'Inter-Arrival Time',
  mutex_block: 'Mutex Blocking',
  deadline: 'Deadlines / CPU budget',
  migrations: 'Core Migrations',
  cores: 'Core utilisation',
  health: 'Trace Health (TICK)',
  preempt_matrix: 'Preemption Chain',
  switch_overhead: 'Switch Overhead',
  sync: 'Sync',
})

const COMPARE_METRIC_SECTION = Object.freeze({
  'response p99': 'response',
  'exec max': 'exec',
  'block avg': 'block',
  'inter avg': 'inter',
  'mutex block': 'mutex_block',
  'deadline misses': 'deadline',
  summary: '',
})

/** Map a Compare row label/metric to a Statistics section id. */
export function compareSectionForMetric(label = '', metric = '') {
  const met = String(metric || '').trim().toLowerCase()
  if (met in COMPARE_METRIC_SECTION && COMPARE_METRIC_SECTION[met]) {
    return COMPARE_METRIC_SECTION[met]
  }
  const blob = `${label} ${metric}`.toLowerCase()
  if (blob.includes('response')) return 'response'
  if (blob.includes('exec')) return 'exec'
  if (blob.includes('mutex')) return 'mutex_block'
  if (blob.includes('deadline') || blob.includes('budget')) return 'deadline'
  if (blob.includes('block')) return 'block'
  if (blob.includes('inter')) return 'inter'
  if (blob.includes('migrat') || blob.includes('ping') || blob.includes('dwell')) return 'migrations'
  if (blob.includes('load balance') || blob.includes('core util')
    || blob.includes('utilisation') || blob.includes('utilization')) {
    return 'cores'
  }
  if (blob.includes('tick') || blob.includes('missed')) return 'health'
  if (blob.includes('preempt')) return 'preempt_matrix'
  if (blob.includes('context switch') || blob.includes('switch')) return 'switch_overhead'
  if (blob.includes('sync') || blob.includes('bounce')) return 'sync'
  return COMPARE_INVESTIGATE_FALLBACK_SECTION
}

/** Best-effort task name from a Compare notable/candidate row. */
export function compareTaskForRow(label = '', metric = '', a = null, b = null) {
  for (const cell of [a, b]) {
    const t = taskFromCell(cell)
    if (t) return t
  }
  const lab = String(label || '').trim()
  const met = String(metric || '').trim()
  if (lab && met && met.toLowerCase() !== 'summary') {
    const suffix = ` ${met}`
    if (lab.toLowerCase().endsWith(suffix.toLowerCase())) {
      const name = lab.slice(0, -suffix.length).trim()
      if (name) return name
    }
  }
  return taskFromCell(lab)
}

/** Pick Statistics section (+ optional task) for Compare Investigate buttons. */
export function compareInvestigateTarget(notable = null) {
  const data = notable && typeof notable === 'object' ? notable : {}
  const rows = (data.rows || []).filter(r => r && typeof r === 'object')
  const regs = rows.filter(r => r.status === 'Regressed')
  const imps = rows.filter(r => r.status === 'Improved')
  const pick = regs[0] || imps[0] || null
  if (!pick) {
    const sid = COMPARE_INVESTIGATE_FALLBACK_SECTION
    return {
      section_id: sid,
      section: sid,
      task: '',
      label: '',
      section_label: COMPARE_SECTION_LABELS[sid] || sid,
    }
  }
  const sid = String(pick.section || '').trim()
    || compareSectionForMetric(String(pick.label || ''), String(pick.metric || ''))
  const task = String(pick.task || '').trim()
    || compareTaskForRow(String(pick.label || ''), String(pick.metric || ''), pick.a, pick.b)
  const label = String(pick.label || '')
  return {
    section_id: sid,
    section: sid,
    task,
    label,
    section_label: COMPARE_SECTION_LABELS[sid] || sid,
  }
}

function extraSummaryCandidates(tables) {
  const extra = []
  for (const row of tables?.summary || []) {
    const { label, delta, a, b } = rowCells(row, 'label', 'delta', 0, 3)
    const low = String(label).toLowerCase()
    if (!low.includes('load balance score')
      && !(low.includes('load balance') && (label.includes('σ') || low.includes('sigma')))) {
      continue
    }
    const parsed = parseSignedDelta(delta)
    if (!parsed) continue
    extra.push({
      label, metric: 'summary', delta: String(delta), a, b, ...parsed,
    })
  }
  return extra
}

export function compareNotableChanges(tables, limit = 8, nameA = '', nameB = '') {
  const lim = Math.max(1, Math.min(16, Number(limit) || 8))
  const cands = [...compareCandidatesFromTables(tables), ...extraSummaryCandidates(tables)]
  const classified = []
  let smallOmitted = 0
  for (const cand of cands) {
    if (!cand || typeof cand !== 'object') continue
    const signed = Number(cand.signed || 0)
    const kind = String(cand.kind || 'count')
    const aMag = cellMagnitude(cand.a)
    const bMag = cellMagnitude(cand.b)
    if (Math.abs(signed) <= 0) continue
    if (!compareChangeIsSignificant(signed, kind, aMag, bMag)) {
      smallOmitted += 1
      continue
    }
    const polarity = compareMetricPolarity(String(cand.label || ''), String(cand.metric || ''))
    const status = compareStatus(polarity, signed)
    const aTxt = cand.a == null ? '—' : String(cand.a)
    const bTxt = cand.b == null ? '—' : String(cand.b)
    const deltaTxt = String(cand.delta || '')
    const candTxt = flipDeltaText(deltaTxt)
    let change = candTxt
    if (aMag && aMag > 0) {
      const rel = (-signed) * 100 / aMag
      const relTxt = `${rel >= 0 ? '+' : ''}${rel.toFixed(1)}%`
      change = `${candTxt} / ${relTxt}`
    }
    classified.push({
      status,
      label: String(cand.label || ''),
      metric: String(cand.metric || ''),
      a: aTxt,
      b: bTxt,
      delta: deltaTxt,
      change,
      signed,
      kind,
      significance: 'engineering',
      section: compareSectionForMetric(String(cand.label || ''), String(cand.metric || '')),
      task: compareTaskForRow(String(cand.label || ''), String(cand.metric || ''), aTxt, bTxt),
    })
  }
  classified.sort((a, b) => Math.abs(b.signed) - Math.abs(a.signed))
  const [modeA, modeB] = compareSummaryPair(tables, 'Tick mode')
  const warnings = compareTickModeWarnings(nameA, nameB, modeA, modeB)
  const [p99A, p99B] = compareSummaryPair(tables, 'Response P99 (worst task)')
  const taskA = taskFromCell(p99A)
  const taskB = taskFromCell(p99B)
  if (taskA && taskB && taskA !== taskB) {
    warnings.push(
      `Worst response P99 compares different tasks (Baseline A: ${taskA}, Candidate B: ${taskB}).`,
    )
  }
  const nReg = classified.filter(r => r.status === 'Regressed').length
  const nImp = classified.filter(r => r.status === 'Improved').length
  const cards = {
    regressions: nReg,
    improvements: nImp,
    significant: classified.length,
    warnings: warnings.length,
  }
  const rows = classified.slice(0, lim)
  const regs = classified.filter(r => r.status === 'Regressed')
  const imps = classified.filter(r => r.status === 'Improved')
  const tickNote = warnings.some(w => w.toLowerCase().includes('tick'))
    ? ' Tick-mode detection requires verification.'
    : ''
  let verdict
  let nextInvestigation = ''
  if (nReg && nImp) {
    verdict = `Overall: Mixed — Candidate B has ${nReg} regression(s) and ${nImp} improvement(s) above threshold.${tickNote}`
    nextInvestigation = 'Next: Investigate on Candidate for the largest regression, then verify on Timeline Evidence'
  } else if (nReg) {
    const top = regs[0]
    verdict = `Overall: Candidate B regressed on ${top.label} (${top.change}).${tickNote}`
    if (warnings.length) {
      nextInvestigation = 'Next: Investigate on Candidate for the largest regression, then verify on Timeline Evidence'
    }
  } else if (nImp) {
    const top = imps[0]
    verdict = `Overall: Candidate B improved on ${top.label} (${top.change}).${tickNote}`
    if (warnings.length) {
      nextInvestigation = 'Next: Spot-check Response P99 and Migration rate if you still expect a change'
    }
  } else if (warnings.length) {
    verdict = `Overall: Mostly similar. ${warnings[0]}`
    nextInvestigation = 'Next: Spot-check Response P99 and Migration rate if you still expect a change'
  } else {
    verdict = 'Overall: Mostly similar; no significant improvements or regressions above the compare threshold.'
    nextInvestigation = 'Next: Spot-check Response P99 and Migration rate if you still expect a change'
  }
  const [spanA, spanB] = compareSummaryPair(tables, 'Span')
  return {
    verdict: verdict.trim(),
    formula: COMPARE_DELTA_FORMULA,
    identity: {
      a: { file: nameA || 'Trace A', span: spanA, tick_mode: modeA },
      b: { file: nameB || 'Trace B', span: spanB, tick_mode: modeB },
    },
    cards,
    rows,
    warnings,
    next_investigation: nextInvestigation,
    small_omitted_count: smallOmitted,
    investigate: compareInvestigateTarget({ rows }),
  }
}

export const COMPARE_CHART_BASELINE = '#2a6fb2'
export const COMPARE_CHART_CANDIDATE = '#6b4ea8'
export const COMPARE_CHART_REGRESSED = '#c0392b'
export const COMPARE_CHART_IMPROVED = '#1f6b45'
export const COMPARE_MIG_VIEWS = Object.freeze(['count', 'dwell', 'cores'])
export const COMPARE_MIG_FILTERS = Object.freeze(['top', 'changed', 'regressed', 'all'])
const MIG_VIEW_SPEC = {
  count: {
    headers: ['Task', 'Migr A', 'Migr B', 'Δ', 'Rate A', 'Rate B', 'Rate Δ'],
    idx: [0, 1, 2, 3, 4, 5, 6],
    keys: ['name', 'migrationsA', 'migrationsB', 'delta', 'rateA', 'rateB', 'rateDelta'],
  },
  dwell: {
    headers: ['Task', 'Dwell A', 'Dwell B', 'Dwell Δ', 'Ping A', 'Ping B'],
    idx: [0, 7, 8, 9, 10, 11],
    keys: ['name', 'dwellA', 'dwellB', 'dwellDelta', 'pingA', 'pingB'],
  },
  cores: {
    headers: ['Task', 'Cores A', 'Cores B', 'Primary A', 'Primary B'],
    idx: [0, 12, 13, 14, 15],
    keys: ['name', 'coresA', 'coresB', 'primaryA', 'primaryB'],
  },
}
const MIG_FAMILY_RE = /^([A-Za-z_][\w.-]*)/

function svgEscape(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function compareCoreUtilChartRows(tables) {
  const rows = tables?.core_util || tables?.coreUtil || []
  const out = []
  for (const row of rows) {
    let label = ''
    let aRaw
    let bRaw
    if (row && typeof row === 'object' && !Array.isArray(row)) {
      label = String(row.core || row.label || '')
      aRaw = 'utilA' in row ? row.utilA : row.a
      bRaw = 'utilB' in row ? row.utilB : row.b
    } else if (Array.isArray(row) && row.length >= 3) {
      label = String(row[0] || '')
      aRaw = row[1]
      bRaw = row[2]
    } else continue
    if (!label) continue
    out.push({ label, a: cellMagnitude(aRaw) || 0, b: cellMagnitude(bRaw) || 0 })
  }
  return out
}

export function compareP99DeltaChartRows(tables, limit = 12) {
  const lim = Math.max(1, Math.min(24, Number(limit) || 12))
  const rows = tables?.response || []
  const out = []
  for (const row of rows) {
    let label = ''
    let delta
    if (row && typeof row === 'object' && !Array.isArray(row)) {
      label = String(row.name || row.label || '')
      delta = row.delta
    } else if (Array.isArray(row) && row.length >= 4) {
      label = String(row[0] || '')
      delta = row[3]
    } else continue
    const parsed = parseSignedDelta(delta)
    if (!parsed || !label) continue
    const cand = -parsed.signed
    if (cand === 0) continue
    out.push({
      label,
      signed: parsed.signed,
      cand,
      status: cand > 0 ? 'Regressed' : 'Improved',
      delta: String(delta),
      change: flipDeltaText(delta),
    })
  }
  out.sort((a, b) => Math.abs(b.cand) - Math.abs(a.cand))
  return out.slice(0, lim)
}

export function compareCoreUtilChartSvg(rows, width = 640) {
  const items = (rows || []).filter(r => r && typeof r === 'object')
  if (!items.length) return ''
  const w = Math.max(280, Number(width) || 640)
  const labelW = 78
  const pad = 12
  const rowH = 32
  const header = 22
  const pctW = 52
  const h = header + pad + items.length * rowH + 8
  let maxV = 1
  for (const r of items) maxV = Math.max(maxV, Number(r.a || 0), Number(r.b || 0))
  const plotW = Math.max(80, w - labelW - pad - pctW)
  const ax = labelW
  const parts = [
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Core utilisation Baseline A vs Candidate B">`,
    `<text x="${pad}" y="16" font-size="12" fill="#123355" font-weight="600">Core utilisation</text>`,
    `<text x="${w - pad}" y="16" text-anchor="end" font-size="11" fill="#5f6f82">`,
    `<tspan fill="${COMPARE_CHART_BASELINE}">Baseline A</tspan>`,
    '<tspan fill="#5f6f82"> · </tspan>',
    `<tspan fill="${COMPARE_CHART_CANDIDATE}">Candidate B</tspan></text>`,
  ]
  items.forEach((row, i) => {
    const y = header + pad + i * rowH
    const lab = svgEscape(String(row.label || '').slice(0, 18))
    const aV = Math.max(0, Number(row.a || 0))
    const bV = Math.max(0, Number(row.b || 0))
    const aw = plotW * aV / maxV
    const bw = plotW * bV / maxV
    parts.push(`<text x="${pad}" y="${y + 14}" font-size="11" fill="#182230">${lab}</text>`)
    parts.push(`<rect x="${ax.toFixed(1)}" y="${y}" width="${Math.max(aw, 0.5).toFixed(1)}" height="9" rx="3" fill="${COMPARE_CHART_BASELINE}"/>`)
    parts.push(`<rect x="${ax.toFixed(1)}" y="${y + 12}" width="${Math.max(bw, 0.5).toFixed(1)}" height="9" rx="3" fill="${COMPARE_CHART_CANDIDATE}"/>`)
    parts.push(`<text x="${(ax + plotW + 6).toFixed(1)}" y="${y + 9}" font-size="10" fill="${COMPARE_CHART_BASELINE}">${aV.toFixed(1)}%</text>`)
    parts.push(`<text x="${(ax + plotW + 6).toFixed(1)}" y="${y + 21}" font-size="10" fill="${COMPARE_CHART_CANDIDATE}">${bV.toFixed(1)}%</text>`)
  })
  parts.push('</svg>')
  return parts.join('')
}

export function compareP99DeltaChartSvg(rows, width = 640) {
  const items = (rows || []).filter(r => r && typeof r === 'object')
  if (!items.length) return ''
  const w = Math.max(280, Number(width) || 640)
  const labelW = 96
  const pad = 12
  const rowH = 22
  const header = 44
  const changeW = 88
  const h = header + items.length * rowH + 16
  let maxV = 1
  for (const r of items) maxV = Math.max(maxV, Math.abs(Number(r.cand || 0)))
  const plotW = Math.max(80, w - labelW - pad - changeW)
  const mid = labelW + plotW / 2
  const half = plotW / 2
  const axisY = 34
  const parts = [
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Response P99 change Candidate B minus Baseline A">`,
    `<text x="${pad}" y="16" font-size="12" fill="#123355" font-weight="600">Response P99 change</text>`,
    `<text x="${w - pad}" y="16" text-anchor="end" font-size="11" fill="#5f6f82">Candidate B − Baseline A</text>`,
    `<text x="${labelW.toFixed(1)}" y="${axisY}" font-size="9" fill="${COMPARE_CHART_IMPROVED}">Improved</text>`,
    `<text x="${(labelW + plotW).toFixed(1)}" y="${axisY}" text-anchor="end" font-size="9" fill="${COMPARE_CHART_REGRESSED}">Regressed</text>`,
    `<line x1="${mid.toFixed(1)}" y1="${header - 2}" x2="${mid.toFixed(1)}" y2="${h - 10}" stroke="#d9e0ea" stroke-width="1"/>`,
  ]
  items.forEach((row, i) => {
    const y = header + i * rowH
    const lab = svgEscape(String(row.label || '').slice(0, 16))
    const cand = Number(row.cand || 0)
    const barW = Math.abs(cand) / maxV * half
    const color = cand > 0 ? COMPARE_CHART_REGRESSED : COMPARE_CHART_IMPROVED
    const x = cand >= 0 ? mid : mid - barW
    parts.push(`<text x="${pad}" y="${y + 14}" font-size="11" fill="#182230">${lab}</text>`)
    parts.push(`<rect x="${x.toFixed(1)}" y="${y + 4}" width="${Math.max(barW, 0.8).toFixed(1)}" height="12" rx="2" fill="${color}"/>`)
    parts.push(`<text x="${(mid + half + 8).toFixed(1)}" y="${y + 14}" font-size="10" fill="${color}">${svgEscape(row.change || '')}</text>`)
  })
  parts.push('</svg>')
  return parts.join('')
}

function migName(row) {
  if (row && typeof row === 'object' && !Array.isArray(row)) return String(row.name || row.label || '')
  if (Array.isArray(row) && row.length) return String(row[0] || '')
  return ''
}

function migFamily(name) {
  const m = String(name || '').trim().match(MIG_FAMILY_RE)
  return m ? m[1] : String(name || '').trim()
}

function migDeltaNum(row) {
  let raw
  if (row && typeof row === 'object' && !Array.isArray(row)) raw = row.delta
  else if (Array.isArray(row) && row.length > 3) raw = row[3]
  const n = Number(raw)
  if (Number.isFinite(n)) return n
  const parsed = parseSignedDelta(raw)
  return parsed ? parsed.signed : 0
}

export function compareMigrationFamilies(rows) {
  const fams = new Set()
  for (const row of rows || []) {
    const name = migName(row)
    if (name) fams.add(migFamily(name))
  }
  return [...fams].filter(Boolean).sort()
}

function migProject(row, spec) {
  if (row && typeof row === 'object' && !Array.isArray(row)) {
    const out = {}
    for (const k of spec.keys) out[k] = row[k]
    return out
  }
  const cells = spec.idx.map(i => (Array.isArray(row) && row.length > i ? row[i] : ''))
  const out = {}
  spec.keys.forEach((k, i) => { out[k] = cells[i] })
  return out
}

export function filterCompareMigrationRows(rows, view = 'count', filt = 'top', family = '', limit = 10, sortBy = 'abs') {
  const useView = COMPARE_MIG_VIEWS.includes(view) ? view : 'count'
  const spec = MIG_VIEW_SPEC[useView]
  const useFilt = COMPARE_MIG_FILTERS.includes(filt) ? filt : 'top'
  const useSort = sortBy === 'rel' ? 'rel' : 'abs'
  let items = [...(rows || [])]
  const fam = String(family || '').trim()
  if (fam) items = items.filter(r => migFamily(migName(r)) === fam)
  if (useFilt === 'changed') items = items.filter(r => migDeltaNum(r) !== 0)
  else if (useFilt === 'regressed') items = items.filter(r => migDeltaNum(r) < 0)
  else if (useFilt === 'top') items = items.filter(r => migDeltaNum(r) !== 0)

  const sortKey = (r) => {
    const d = Math.abs(migDeltaNum(r))
    if (useSort === 'rel') {
      let base = 1
      if (r && typeof r === 'object' && !Array.isArray(r)) {
        base = Math.max(Math.abs(Number(r.migrationsA) || 0), Math.abs(Number(r.migrationsB) || 0), 1)
      } else if (Array.isArray(r) && r.length > 2) {
        base = Math.max(Math.abs(Number(r[1]) || 0), Math.abs(Number(r[2]) || 0), 1)
      }
      return -d / base
    }
    return -d
  }
  items.sort((a, b) => sortKey(a) - sortKey(b) || migName(a).localeCompare(migName(b)))
  if (useFilt === 'top') items = items.slice(0, Math.max(1, Number(limit) || 10))
  const objects = items.map(r => migProject(r, spec))
  return {
    view: useView,
    filter: useFilt,
    sort_by: useSort,
    headers: [...spec.headers],
    rows: objects.map(obj => spec.keys.map(k => obj[k])),
    objects,
    families: compareMigrationFamilies(rows),
    shown: objects.length,
    total: (rows || []).length,
  }
}

export function compareRowDeltaStatus(label, delta, metric = '') {
  const parsed = parseSignedDelta(delta)
  if (!parsed) return null
  if (Number(parsed.signed) === 0) return null
  let pol = compareMetricPolarity(label, metric)
  if (!pol && metric) pol = compareMetricPolarity(metric)
  if (!pol) return 'Changed'
  return compareStatus(pol, parsed.signed)
}

export function compareSummaryChangeBarRows(tables, limit = 8) {
  const lim = Math.max(1, Math.min(16, Number(limit) || 8))
  const out = []
  for (const row of tables?.summary || []) {
    let label = ''
    let delta
    if (row && typeof row === 'object' && !Array.isArray(row)) {
      label = String(row.label || '')
      delta = row.delta
    } else if (Array.isArray(row) && row.length >= 4) {
      label = String(row[0] || '')
      delta = row[3]
    } else continue
    const low = label.toLowerCase()
    if (low.startsWith('tick ') || ['tasks', 'segments', 'sti events'].includes(low)) continue
    const parsed = parseSignedDelta(delta)
    if (!parsed || parsed.signed === 0) continue
    const cand = -parsed.signed
    out.push({
      label,
      signed: parsed.signed,
      cand,
      kind: parsed.kind,
      status: compareRowDeltaStatus(label, delta) || 'Changed',
      delta: String(delta),
      change: flipDeltaText(delta),
    })
  }
  out.sort((a, b) => Math.abs(b.cand) - Math.abs(a.cand))
  return out.slice(0, lim)
}

export function compareSummaryChangeBarsSvg(rows, width = 640) {
  return compareP99DeltaChartSvg(
    (rows || []).filter(r => r && typeof r === 'object').map(r => ({
      ...r,
      label: String(r.label || '').slice(0, 22),
    })),
    width,
  )
    .replace(/Response P99 change/g, 'Summary changes')
}

export function compareMigrationHeatmapRows(rows, limit = 16) {
  const lim = Math.max(1, Math.min(40, Number(limit) || 16))
  const items = [...(rows || [])].filter(r => migDeltaNum(r) !== 0)
  items.sort((a, b) => Math.abs(migDeltaNum(b)) - Math.abs(migDeltaNum(a)) || migName(a).localeCompare(migName(b)))
  return items.slice(0, lim).map((r) => {
    const d = migDeltaNum(r)
    let aV = 0
    let bV = 0
    if (r && typeof r === 'object' && !Array.isArray(r)) {
      aV = Number(r.migrationsA) || 0
      bV = Number(r.migrationsB) || 0
    } else if (Array.isArray(r)) {
      aV = Number(r[1]) || 0
      bV = Number(r[2]) || 0
    }
    return {
      label: migName(r),
      a: aV,
      b: bV,
      delta: d,
      status: d < 0 ? 'Regressed' : (d > 0 ? 'Improved' : 'Changed'),
    }
  })
}

export function compareMigrationHeatmapSvg(rows, width = 640) {
  const items = (rows || []).filter(r => r && typeof r === 'object')
  if (!items.length) return ''
  const w = Math.max(280, Number(width) || 640)
  const labelW = 110
  const pad = 12
  const rowH = 18
  const header = 24
  const h = header + items.length * rowH + 10
  let maxV = 1
  for (const r of items) maxV = Math.max(maxV, Math.abs(Number(r.delta) || 0))
  const barW = Math.max(80, w - labelW - pad - 60)
  const parts = [
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Migration count change heatmap">`,
    `<text x="${pad}" y="16" font-size="12" fill="#123355" font-weight="600">Migration Δ heatmap</text>`,
    `<text x="${w - pad}" y="16" text-anchor="end" font-size="11" fill="#5f6f82">Δ = A − B</text>`,
  ]
  items.forEach((row, i) => {
    const y = header + i * rowH
    const lab = svgEscape(String(row.label || '').slice(0, 18))
    const d = Number(row.delta) || 0
    const frac = Math.abs(d) / maxV
    const color = d > 0 ? COMPARE_CHART_IMPROVED : COMPARE_CHART_REGRESSED
    const sign = d > 0 ? '+' : (d < 0 ? '−' : '')
    parts.push(`<text x="${pad}" y="${y + 13}" font-size="11" fill="#182230">${lab}</text>`)
    parts.push(`<rect x="${labelW.toFixed(1)}" y="${y + 3}" width="${Math.max(barW * frac, 2).toFixed(1)}" height="12" rx="2" fill="${color}" opacity="0.85"/>`)
    parts.push(`<text x="${(labelW + barW + 8).toFixed(1)}" y="${y + 13}" font-size="10" fill="${color}">${sign}${Math.abs(Math.trunc(d))}</text>`)
  })
  parts.push('</svg>')
  return parts.join('')
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
          reason: formatBurstReason(count, 'migration', windowNs),
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

function rowCells(row, nameKey, deltaKey, nameIdx, deltaIdx, aKey = 'a', bKey = 'b', aIdx = 1, bIdx = 2) {
  const { label, delta } = rowLabelDelta(row, nameKey, deltaKey, nameIdx, deltaIdx)
  let a = null
  let b = null
  if (row && typeof row === 'object' && !Array.isArray(row)) {
    a = row[aKey] ?? row.a
    b = row[bKey] ?? row.b
  } else if (Array.isArray(row)) {
    if (row.length > aIdx) a = row[aIdx]
    if (row.length > bIdx) b = row[bIdx]
  }
  return { label, delta, a, b }
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
      out.push({
        ...last,
        start: Math.trunc(first.start || 0),
        stop: Math.trunc(last.stop || last.start || 0),
        duration: Math.max(
          Math.trunc(last.stop || last.start || 0) - Math.trunc(first.start || 0),
          count,
        ),
        reason: formatBurstReason(count, label, windowNs),
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

export function compareAnalysisTables(traceA, traceB, loA = null, hiA = null, loB = null, hiB = null, deadlines = null, rowLimit = 15) {
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
  let worstTaskA = ''
  let worstTaskB = ''
  for (const name of names) {
    const pa = Math.trunc(byA.get(name)?.p99_ns || 0)
    const pb = Math.trunc(byB.get(name)?.p99_ns || 0)
    if (pa > worstP99A) {
      worstP99A = pa
      worstTaskA = name
    }
    if (pb > worstP99B) {
      worstP99B = pb
      worstTaskB = name
    }
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
  let unlimited = rowLimit == null
  let n = 15
  if (!unlimited) {
    n = Number(rowLimit)
    if (!Number.isFinite(n) || n <= 0) unlimited = true
  }
  return {
    response: unlimited ? [...responseRows] : responseRows.slice(0, n),
    mutex_block: unlimited ? [...mutexRows] : mutexRows.slice(0, n),
    metrics: {
      response_p99_a: worstP99A,
      response_p99_b: worstP99B,
      response_p99_task_a: worstTaskA,
      response_p99_task_b: worstTaskB,
      mutex_ns_a: mutexNsA,
      mutex_ns_b: mutexNsB,
      deadline_misses_a: missesA,
      deadline_misses_b: missesB,
    },
    shared_patterns: unlimited ? [...shared] : shared.slice(0, n === 15 ? 6 : n),
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
    let reason = 'anomaly'
    if (top && typeof top === 'object' && !Array.isArray(top)) {
      reason = top.reason || top.kind || 'anomaly'
    } else if (Array.isArray(top)) {
      reason = top[4] || top[1] || 'anomaly'
    } else if (top) {
      reason = String(top)
    }
    why += ` Shared pattern: ${reason}.`
  }
  return why
}
