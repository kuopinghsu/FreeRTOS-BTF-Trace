/**
 * Analysis Context strip + stale-result helpers.
 * Keep in sync with btf_viewer_pkg/analysis_context.py.
 */

export const PANEL_FILTER_LABELS = {
  statistics: 'Statistics filter',
  ai: 'AI context filter',
  compare: 'Compare filter',
  findings: 'Findings filter',
}

/** @param {object} [opts] */
export function buildAnalysisContext({
  traceName = '',
  scopeLabel = 'Full Trace',
  scopeDuration = '',
  filterLabels = [],
  sampleCount = null,
  cursorCount = 0,
  limitToCursors = false,
  panelFilter = '',
  panel = '',
} = {}) {
  const filters = (filterLabels || []).map(x => String(x || '').trim()).filter(Boolean)
  return {
    trace_name: String(traceName || '').trim(),
    scope_label: String(scopeLabel || 'Full Trace').trim() || 'Full Trace',
    scope_duration: String(scopeDuration || '').trim(),
    filter_labels: filters,
    sample_count: sampleCount != null ? Number(sampleCount) : null,
    cursor_count: Math.max(0, Number(cursorCount) || 0),
    limit_to_cursors: !!limitToCursors,
    panel_filter: String(panelFilter || '').trim(),
    panel: String(panel || '').trim(),
  }
}

export function contextFingerprint(ctx) {
  if (!ctx || typeof ctx !== 'object') return ''
  return [
    ctx.trace_name || '',
    ctx.scope_label || '',
    ctx.scope_duration || '',
    (ctx.filter_labels || []).join('|'),
    ctx.sample_count != null ? String(ctx.sample_count) : '',
    String(ctx.cursor_count || 0),
    ctx.limit_to_cursors ? '1' : '0',
  ].join('\x1f')
}

export function isContextStale(snapshot, current) {
  if (!snapshot || typeof snapshot !== 'object') return false
  if (!current || typeof current !== 'object') return true
  return contextFingerprint(snapshot) !== contextFingerprint(current)
}

/** Short note when cursors exist but Limit to C1–Cn is off (Statistics / plot parity). */
export const CURSORS_NOT_LIMITING_NOTE = 'Not limited to cursors'

export function formatAnalysisContextLines(ctx, {
  includePanelFilter = true,
  compact = false,
} = {}) {
  if (!ctx || typeof ctx !== 'object') return compact ? [] : ['Scope: Full Trace']
  const lines = []
  const cursorsNote = (ctx.cursor_count || 0) >= 2 && !ctx.limit_to_cursors
  // compact=true (Statistics): Scope/Filters already shown in the panel header.
  if (compact) {
    if (cursorsNote) lines.push(CURSORS_NOT_LIMITING_NOTE)
    return lines
  }
  const trace = String(ctx.trace_name || '').trim()
  if (trace) lines.push(trace)
  const scope = String(ctx.scope_label || 'Full Trace')
  const dur = String(ctx.scope_duration || '').trim()
  if (dur && scope.toLowerCase() !== 'full trace') {
    lines.push(`Scope: ${scope} · ${dur}`)
  } else {
    lines.push(`Scope: ${scope}`)
  }
  const filters = ctx.filter_labels || []
  if (filters.length) lines.push(`Filters: ${filters.join(', ')}`)
  if (ctx.sample_count != null) {
    lines.push(`Samples: ${Number(ctx.sample_count).toLocaleString('en-US')}`)
  }
  if (cursorsNote) lines.push(CURSORS_NOT_LIMITING_NOTE)
  if (includePanelFilter) {
    const pf = String(ctx.panel_filter || '').trim()
    const panel = String(ctx.panel || '').trim()
    if (pf) {
      const label = PANEL_FILTER_LABELS[panel] || panel || 'Panel filter'
      lines.push(`${label}: ${pf}`)
    }
  }
  return lines
}

export function formatAnalysisContextStrip(ctx, { compact = false } = {}) {
  return formatAnalysisContextLines(ctx, { compact }).join(' · ')
}

export function staleResultBanner(stale = false) {
  if (!stale) return null
  return {
    title: 'Results may be outdated',
    message: 'Scope or Filters changed since these results were calculated.',
    action: 'Recalculate with current context',
    live: 'polite',
  }
}
