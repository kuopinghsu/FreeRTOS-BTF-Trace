/**
 * Deterministic structural trace-health checks.
 * Keep in sync with btf_viewer_pkg/trace_health.py.
 *
 * Distinct from *Trace Health (TICK)* (tickHealth.js / traceQuality.js), which
 * only measures tick-interval regularity and surfaces BTF metadata flags. This
 * module verifies that the parsed event model is internally consistent enough
 * to trust the statistics the app derives from it, and records which metrics
 * become limited when it is not.
 *
 * buildTraceHealthResult is a pure function of the parsed trace: the same input
 * always produces the same result.
 */

export const STATUS_PASS = 'pass'
export const STATUS_CAUTION = 'caution'
export const STATUS_INSUFFICIENT = 'insufficient'

const STATUS_LABELS = {
  [STATUS_PASS]: 'Pass',
  [STATUS_CAUTION]: 'Caution',
  [STATUS_INSUFFICIENT]: 'Insufficient data',
}

export const CHECK_EMPTY_TRACE = 'empty_trace'
export const CHECK_TIMESTAMP_UNITS = 'timestamp_units'
export const CHECK_TIMESTAMP_SKIPS = 'timestamp_skips'
export const CHECK_CORE_INTERVAL_OVERLAP = 'core_interval_overlap'
export const CHECK_UNKNOWN_CORE = 'unknown_core'
export const CHECK_MISSING_TASK_IDENTITY = 'missing_task_identity'
export const CHECK_UNMATCHED_INTERVALS = 'unmatched_intervals'
export const CHECK_SYNC_PAIRING = 'sync_pairing_issues'
export const CHECK_CAPTURE_TRUNCATION = 'capture_truncation'
export const CHECK_LONG_GAP = 'long_data_gap'
export const CHECK_METRIC_PREREQUISITES = 'metric_prerequisites'

export const TRACE_HEALTH_CHECK_IDS = [
  CHECK_EMPTY_TRACE, CHECK_TIMESTAMP_UNITS, CHECK_TIMESTAMP_SKIPS,
  CHECK_CORE_INTERVAL_OVERLAP, CHECK_UNKNOWN_CORE, CHECK_MISSING_TASK_IDENTITY,
  CHECK_UNMATCHED_INTERVALS, CHECK_SYNC_PAIRING, CHECK_CAPTURE_TRUNCATION,
  CHECK_LONG_GAP, CHECK_METRIC_PREREQUISITES,
]

const SEVERITY_RANK = { info: 0, warning: 1, error: 2 }
const KNOWN_TIME_SCALES = ['ps', 'ns', 'us', 'µs', 'ms', 's']
const LONG_GAP_SPAN_FRACTION = 0.20
const OVERLAP_ERROR_RATIO = 0.02
const EVIDENCE_CAP = 4
const VALID_CORE_RE = /^(?:Core_|CPU|C)(\d{1,2})$/i
const PLACEHOLDER_TASK_RE = /^\[[^\]]*\]\s*$/

export function traceHealthStatusLabel(status) {
  return STATUS_LABELS[String(status || '')] || 'Unknown'
}

function fmt(formatNs, value) {
  if (typeof formatNs === 'function') {
    try { return String(formatNs(Number(value))) } catch { return String(Math.trunc(value)) }
  }
  return String(Math.trunc(value))
}

function nfmt(n) {
  return Number(n || 0).toLocaleString('en-US')
}

function truthyMeta(v) {
  return v === true || v === 1 || ['1', 'true', 'yes'].includes(String(v).trim().toLowerCase())
}

function scopedSegments(trace, lo, hi) {
  const segs = trace?.segments || []
  if (lo == null && hi == null) return segs
  const loV = lo == null ? -Infinity : lo
  const hiV = hi == null ? Infinity : hi
  return segs.filter(s => s.end > loV && s.start < hiV)
}

function scopedTimes(times, lo, hi) {
  const seq = times || []
  if (lo == null && hi == null) return [...seq]
  const loV = lo == null ? -Infinity : lo
  const hiV = hi == null ? Infinity : hi
  return seq.filter(t => t >= loV && t <= hiV)
}

function mkCheck(id, severity, summary, {
  affectedRange = null, affectedEntities = [], evidenceRefs = [], metricLimitations = [],
} = {}) {
  return {
    id,
    severity,
    summary,
    affectedRange,
    affectedEntities: [...affectedEntities],
    evidenceRefs: [...evidenceRefs],
    metricLimitations: [...metricLimitations],
  }
}

function checkEmpty(segs, stiTimes) {
  if (segs.length || stiTimes.length) return null
  return mkCheck(CHECK_EMPTY_TRACE, 'error',
    'No task slices or STI events in the analysed range.',
    { metricLimitations: ['All statistics'] })
}

function checkUnits(trace) {
  const scale = String(trace?.timeScale || '').trim().toLowerCase()
  if (!scale || KNOWN_TIME_SCALES.includes(scale)) return null
  return mkCheck(CHECK_TIMESTAMP_UNITS, 'error',
    `Unrecognised timestamp unit '${scale}'. Tick/cycle-to-time conversion cannot be verified, `
    + 'so every time-based value is unreliable.',
    { metricLimitations: ['All time-based statistics'] })
}

function checkSkips(trace) {
  const meta = trace?.meta || {}
  const n = Number(trace?.skippedLines ?? meta._skipped_lines ?? meta.skippedLines ?? 0)
  if (!(n > 0)) return null
  return mkCheck(CHECK_TIMESTAMP_SKIPS, 'warning',
    `${nfmt(n)} trace line(s) had an unparseable timestamp and were dropped before analysis.`,
    { metricLimitations: ['Event counts', 'Timeline coverage'] })
}

function checkCoreOverlap(segs, formatNs) {
  const byCore = new Map()
  for (const s of segs) {
    if (!byCore.has(s.core)) byCore.set(s.core, [])
    byCore.get(s.core).push(s)
  }
  let overlaps = 0
  let total = 0
  const ev = []
  const cores = []
  let rngLo = null
  let rngHi = null
  for (const [core, cs] of byCore) {
    const sorted = [...cs].sort((a, b) => (a.start - b.start) || (a.end - b.end))
    total += sorted.length
    let prevEnd = null
    let coreHit = false
    for (const s of sorted) {
      if (prevEnd != null && s.start < prevEnd) {
        overlaps++
        coreHit = true
        const loOv = s.start
        const hiOv = Math.min(prevEnd, s.end)
        rngLo = rngLo == null ? loOv : Math.min(rngLo, loOv)
        rngHi = rngHi == null ? hiOv : Math.max(rngHi, hiOv)
        if (ev.length < EVIDENCE_CAP) ev.push(`${core} @ ${fmt(formatNs, s.start)}`)
      }
      if (prevEnd == null || s.end > prevEnd) prevEnd = s.end
    }
    if (coreHit) cores.push(core)
  }
  if (!overlaps) return null
  const ratio = overlaps / Math.max(1, total)
  const severity = ratio > OVERLAP_ERROR_RATIO ? 'error' : 'warning'
  return mkCheck(CHECK_CORE_INTERVAL_OVERLAP, severity,
    `${nfmt(overlaps)} task slice(s) overlap in time on the same core `
    + `(${(ratio * 100).toFixed(1)}% of slices on ${cores.length} core(s)). Two tasks cannot run `
    + 'at once on one core, so the reconstructed schedule is inconsistent here.',
    {
      affectedRange: (rngLo != null && rngHi != null)
        ? { start: Math.trunc(rngLo), end: Math.trunc(rngHi) } : null,
      affectedEntities: [...cores].sort(),
      evidenceRefs: ev,
      metricLimitations: [
        'Core Utilisation', 'Core Time Breakdown',
        'Preemption Chain Analysis', 'Response Time',
      ],
    })
}

function checkUnknownCores(trace) {
  const bad = []
  for (const name of trace?.coreNames || []) {
    const m = VALID_CORE_RE.exec(String(name).trim())
    if (!m || !(Number(m[1]) >= 0 && Number(m[1]) <= 31)) bad.push(String(name))
  }
  if (!bad.length) return null
  return mkCheck(CHECK_UNKNOWN_CORE, 'warning',
    'Core identifier(s) outside the valid 0-31 range or in an unexpected format: '
    + `${bad.slice(0, 8).join(', ')}.`,
    {
      affectedEntities: bad,
      metricLimitations: ['Core Migrations', 'Core Affinity', 'Task × Core'],
    })
}

function checkTaskIdentity(trace) {
  const meta = trace?.meta || {}
  const overflow = truthyMeta(meta.taskTableOverflow) || truthyMeta(meta.task_table_overflow)
  let placeholders = 0
  const reprMap = trace?.taskRepr
  const names = reprMap
    ? Array.from(reprMap instanceof Map ? reprMap.values() : Object.values(reprMap))
    : (trace?.tasks || [])
  for (const name of names) {
    const text = String(name || '').trim()
    if (!text || PLACEHOLDER_TASK_RE.test(text)) placeholders++
  }
  if (!overflow && !placeholders) return null
  const bits = []
  if (overflow) bits.push('task-table overflow was flagged during capture')
  if (placeholders) bits.push(`${placeholders} task(s) have no readable name`)
  let summary = bits.join('; ')
  summary = summary.charAt(0).toUpperCase() + summary.slice(1)
  return mkCheck(CHECK_MISSING_TASK_IDENTITY, 'warning',
    `${summary}. Per-task attribution for those slices is unreliable.`,
    { metricLimitations: ['Top Tasks by CPU', 'Task × Core', 'Task Health'] })
}

function checkUnmatchedIntervals(trace) {
  const n = Number(trace?.intervalUnmatchedStarts || 0)
  if (!(n > 0)) return null
  return mkCheck(CHECK_UNMATCHED_INTERVALS, 'warning',
    `${nfmt(n)} interval_start event(s) never received a matching interval_stop. `
    + 'Those spans are dropped from interval statistics.',
    { metricLimitations: ['Interval Analysis', 'Period / Jitter'] })
}

function checkSyncPairing(trace, formatNs) {
  const issues = trace?.syncIssues || []
  if (!issues.length) return null
  const ev = issues.slice(0, EVIDENCE_CAP).map((i) => {
    const kind = String(i.kind || i.detail || 'issue')
    const t = i.time_ns ?? i.timeNs
    return t != null ? `${kind} @ ${fmt(formatNs, t)}` : kind
  })
  return mkCheck(CHECK_SYNC_PAIRING, 'warning',
    `${nfmt(issues.length)} mutex/semaphore pairing issue(s) (orphan give, unmatched take, `
    + 'or lock held across a migration).',
    {
      evidenceRefs: ev,
      metricLimitations: [
        'Mutex / Semaphore', 'Mutex Blocking',
        'Waiter × Owner', 'Priority Inheritance',
      ],
    })
}

function collectQualityWarnings(trace) {
  const meta = trace?.meta || {}
  const out = []
  if (meta._versionWarning) out.push(String(meta._versionWarning).trim())
  if (meta._version_warning) out.push(String(meta._version_warning).trim())
  if (meta._traceQualityWarning) out.push(String(meta._traceQualityWarning).trim())
  const flags = meta.traceQuality || meta.trace_quality
  if (flags && typeof flags === 'object') {
    if (flags.ringOverflow || flags.ring_overflow) out.push('Trace ring buffer overflow — oldest events may be missing.')
    if (flags.taskTableOverflow || flags.task_table_overflow) out.push('Task table overflow — tracing was disabled for new tasks.')
    if (flags.truncated) out.push('Trace was truncated before normal stop.')
  } else if (typeof flags === 'string' && flags.trim()) {
    out.push(flags.trim())
  }
  for (const key of ['ringOverflow', 'taskTableOverflow', 'truncated']) {
    if (truthyMeta(meta[key])) {
      if (key === 'ringOverflow') out.push('Trace ring buffer overflow — oldest events may be missing.')
      if (key === 'taskTableOverflow') out.push('Task table overflow — tracing was disabled for new tasks.')
      if (key === 'truncated') out.push('Trace was truncated before normal stop.')
    }
  }
  if (meta.comment) {
    const c = String(meta.comment).toLowerCase()
    if (c.includes('overflow') || c.includes('truncat')) {
      const line = String(meta.comment).trim()
      if (!out.includes(line)) out.push(line)
    }
  }
  return [...new Set(out)].filter(Boolean)
}

function checkTruncation(trace) {
  const warnings = collectQualityWarnings(trace)
  if (!warnings.length) return null
  return mkCheck(CHECK_CAPTURE_TRUNCATION, 'warning', warnings.join(' '), {
    metricLimitations: [
      'Timeline Anomalies', 'Worst Events',
      'Response Time', 'Execution Time Per Slice',
    ],
  })
}

function checkLongGap(segs, lo, hi, trace, formatNs) {
  if (segs.length < 2) return null
  const spanLo = lo != null ? lo : trace?.timeMin
  const spanHi = hi != null ? hi : trace?.timeMax
  if (spanLo == null || spanHi == null || spanHi <= spanLo) return null
  const span = spanHi - spanLo
  const ordered = [...segs].sort((a, b) => a.start - b.start)
  let gap = 0
  let gapLo = 0
  let gapHi = 0
  let covered = ordered[0].end
  for (let i = 1; i < ordered.length; i++) {
    const s = ordered[i]
    if (s.start > covered) {
      const g = s.start - covered
      if (g > gap) { gap = g; gapLo = covered; gapHi = s.start }
    }
    if (s.end > covered) covered = s.end
  }
  if (gap <= span * LONG_GAP_SPAN_FRACTION) return null
  return mkCheck(CHECK_LONG_GAP, 'info',
    `No task was scheduled for ${fmt(formatNs, gap)} (${Math.round(gap / span * 100)}% of the `
    + 'analysed span). This may be genuine idle time or a gap in the capture; rates and '
    + 'utilisation include it in the denominator.',
    {
      affectedRange: { start: Math.trunc(gapLo), end: Math.trunc(gapHi) },
      metricLimitations: ['Scheduling Load Over Time', 'Core Utilisation'],
    })
}

function checkPrerequisites(trace, segs, lo, hi) {
  const channels = new Set((trace?.stiChannels || []).map(c => String(c).toLowerCase()))
  const tickTimes = scopedTimes(trace?.tickStiTimes, lo, hi)
  const cores = new Set(segs.map(s => s.core))
  if (!cores.size) for (const c of trace?.coreNames || []) cores.add(c)
  const missing = []
  const limits = []
  if (!tickTimes.length) {
    missing.push('no TICK events')
    limits.push('Trace Health (TICK)')
  }
  if (!trace?.hasSyncObjectInstrumentation
      && !['mutex', 'sem', 'queue'].some(c => channels.has(c))) {
    missing.push('no mutex/semaphore/queue STI events')
    limits.push('Mutex / Semaphore', 'Mutex Blocking', 'Waiter × Owner')
  }
  const hasIntervals = (trace?.intervalIds && trace.intervalIds.length) || channels.has('interval_start')
  if (!hasIntervals) {
    missing.push('no interval_start/stop events')
    limits.push('Interval Analysis')
  }
  if (!trace?.hasPriorityInstrumentation) {
    missing.push('no priority (create pri:/set_priority) events')
    limits.push('Priority Inheritance')
  }
  if (cores.size < 2) {
    missing.push('single core in scope')
    limits.push('Core Migrations', 'Core Affinity', 'Load Balance Score')
  }
  if (!missing.length) return null
  return mkCheck(CHECK_METRIC_PREREQUISITES, 'info',
    `Some metrics need event types this trace does not contain: ${missing.join('; ')}.`,
    { metricLimitations: limits })
}

/**
 * Build a TraceHealthResult for `trace` over [lo, hi].
 * @param {object} trace   parsed trace
 * @param {?number} lo      scope start (trace time units) or null
 * @param {?number} hi      scope end or null
 * @param {?function} formatNs  optional time formatter for evidence strings
 */
export function buildTraceHealthResult(trace, lo = null, hi = null, formatNs = null) {
  if (!trace) {
    return {
      status: STATUS_INSUFFICIENT,
      checks: [mkCheck(CHECK_EMPTY_TRACE, 'error', 'No trace is loaded.',
        { metricLimitations: ['All statistics'] })],
      issueCount: 1,
      metricLimitations: ['All statistics'],
      scoped: false,
    }
  }

  const segs = scopedSegments(trace, lo, hi)
  const stiTimes = scopedTimes((trace.stiEvents || []).map(e => e.time), lo, hi)

  const checks = []
  const empty = checkEmpty(segs, stiTimes)
  if (empty) {
    checks.push(empty)
  } else {
    for (const candidate of [
      checkUnits(trace),
      checkSkips(trace),
      checkCoreOverlap(segs, formatNs),
      checkUnknownCores(trace),
      checkTaskIdentity(trace),
      checkUnmatchedIntervals(trace),
      checkSyncPairing(trace, formatNs),
      checkTruncation(trace),
      checkLongGap(segs, lo, hi, trace, formatNs),
      checkPrerequisites(trace, segs, lo, hi),
    ]) {
      if (candidate) checks.push(candidate)
    }
  }

  checks.sort((a, b) => (SEVERITY_RANK[b.severity] || 0) - (SEVERITY_RANK[a.severity] || 0)
    || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))

  const severities = new Set(checks.map(c => c.severity))
  let status = STATUS_PASS
  if (severities.has('error')) status = STATUS_INSUFFICIENT
  else if (severities.has('warning')) status = STATUS_CAUTION

  const limitations = []
  const seen = new Set()
  for (const c of checks) {
    for (const m of c.metricLimitations || []) {
      if (!seen.has(m)) { seen.add(m); limitations.push(m) }
    }
  }

  return {
    status,
    checks,
    issueCount: checks.filter(c => c.severity === 'warning' || c.severity === 'error').length,
    metricLimitations: limitations,
    scoped: lo != null || hi != null,
  }
}

/** One-line summary for KPI tiles / plain-text exports. */
export function traceHealthSummary(result) {
  if (!result) return 'Trace health: unknown'
  const status = traceHealthStatusLabel(result.status)
  const n = Number(result.issueCount || 0)
  return n ? `Trace health: ${status} · ${n} issue(s)` : `Trace health: ${status}`
}
