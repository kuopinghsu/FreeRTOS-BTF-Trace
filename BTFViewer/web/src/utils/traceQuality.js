/**
 * Trace quality / integrity warnings from BTF metadata and parser hints.
 */

/** @returns {string[]} human-readable warning lines */
export function collectTraceQualityWarnings(trace) {
  if (!trace) return []
  const out = []
  const meta = trace.meta || {}

  if (meta._versionWarning) out.push(meta._versionWarning)
  if (meta._version_warning) out.push(meta._version_warning)
  if (meta._traceQualityWarning) out.push(meta._traceQualityWarning)

  const flags = meta.traceQuality || meta.trace_quality
  if (flags && typeof flags === 'object') {
    if (flags.ringOverflow || flags.ring_overflow) {
      out.push('Trace ring buffer overflow — oldest events may be missing.')
    }
    if (flags.taskTableOverflow || flags.task_table_overflow) {
      out.push('Task table overflow — tracing was disabled for new tasks.')
    }
    if (flags.truncated) {
      out.push('Trace was truncated before normal stop.')
    }
  } else if (typeof flags === 'string' && flags.trim()) {
    out.push(flags.trim())
  }

  for (const key of ['ringOverflow', 'taskTableOverflow', 'truncated']) {
    const v = meta[key]
    if (v === true || v === '1' || String(v).toLowerCase() === 'true') {
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

  return [...new Set(out)]
}

export function traceQualitySummary(trace) {
  const warnings = collectTraceQualityWarnings(trace)
  if (!warnings.length) return null
  return warnings.join(' · ')
}

const QUALITY_GROUPS = {
  incomplete_capture: ['ringOverflow', 'taskTableOverflow', 'truncated', 'overflow', 'truncat'],
  missing_event_type: ['sti', 'instrument', 'missing event'],
  invalid_pairing: ['pair', 'unmatched', 'interval'],
  timestamp_order: ['order', 'timestamp', 'version'],
  unsupported_measurement: ['unsupported', 'not instrumented'],
}

const AFFECTED_BY_GROUP = {
  incomplete_capture: ['Timeline Anomalies', 'Worst Events', 'Response Time', 'AI conclusions'],
  missing_event_type: ['Blocking Time', 'Mutex Blocking', 'Waiter × Owner', 'Dispatch latency'],
  invalid_pairing: ['Period / Jitter', 'Recurring Patterns', 'Intervals'],
  timestamp_order: ['All time-ordered statistics', 'Critical Path'],
  unsupported_measurement: ['Response Time', 'Task Health', 'Priority Inheritance'],
}

function classifyWarning(line) {
  const low = String(line || '').toLowerCase()
  for (const [group, needles] of Object.entries(QUALITY_GROUPS)) {
    if (needles.some(n => low.includes(n))) return group
  }
  return 'incomplete_capture'
}

export function traceQualityReport(trace) {
  const warnings = collectTraceQualityWarnings(trace)
  if (!warnings.length) {
    return { ok: true, summary: '', groups: [], actions: [] }
  }
  const grouped = {}
  for (const line of warnings) {
    const gid = classifyWarning(line)
    if (!grouped[gid]) grouped[gid] = []
    grouped[gid].push(line)
  }
  const groups = Object.entries(grouped).map(([gid, lines]) => ({
    id: gid,
    title: gid.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
    lines,
    affected: [...(AFFECTED_BY_GROUP[gid] || [])],
  }))
  return {
    ok: false,
    summary: traceQualitySummary(trace) || '',
    groups,
    actions: [
      { id: 'continue', label: 'Continue with limitations' },
      { id: 'guidance', label: 'Open capture guidance' },
    ],
  }
}
