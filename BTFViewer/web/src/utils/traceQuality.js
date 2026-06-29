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
