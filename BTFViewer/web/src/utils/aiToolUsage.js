/**
 * Authoritative AI tool-usage record for one investigation.
 *
 * One append-only list of per-call records lives on the Investigation Case
 * (`investigation_case.tool_usage`). Every displayed tool statistic — the
 * compact summary line, category counts, grouped `×N` rows, trace-query count,
 * the cost line's trace-query value, and the exported report — is derived from
 * `summarizeToolUsage()` so the numbers can never disagree.
 *
 * Keep in lockstep with btf_viewer_pkg/ai_tool_usage.py.
 */

export const AI_TOOL_USAGE_CATEGORIES = ['Evidence', 'Analysis', 'Verification', 'Viewer']

/** Tools that retrieve raw trace data. These count as "trace queries". */
export const AI_TOOL_USAGE_EVIDENCE_TOOLS = [
  'query_raw_metric',
  'search_timeline',
  'detect_anomalies',
  'analyze_distribution',
  'analyze_periodicity',
  'find_related_findings',
  'explain_finding',
  'check_budget',
  'compare_tasks',
  'compare_performance',
]

/** Tools that challenge or score a conclusion. */
export const AI_TOOL_USAGE_VERIFICATION_TOOLS = [
  'verify_claim',
  'challenge_conclusion',
  'detect_contradictions',
  'assess_evidence_sufficiency',
  'score_investigation',
  'close_investigation',
]

/** Tools that mutate the viewer or export. */
export const AI_TOOL_USAGE_VIEWER_TOOLS = [
  'set_cursors',
  'zoom_to_range',
  'highlight_task',
  'set_view_mode',
  'open_corridor_inspector',
  'open_statistics_section',
  'add_annotation',
  'clear_marks',
  'reset_view',
  'bookmark_finding',
  'trigger_compare',
  'export_report',
  'export_investigation',
]

const EVIDENCE_SET = new Set(AI_TOOL_USAGE_EVIDENCE_TOOLS)
const VERIFICATION_SET = new Set(AI_TOOL_USAGE_VERIFICATION_TOOLS)
const VIEWER_SET = new Set(AI_TOOL_USAGE_VIEWER_TOOLS)

/** Map a tool name to one of AI_TOOL_USAGE_CATEGORIES. Default: Analysis. */
export function aiToolUsageCategory(name) {
  const n = String(name || '').trim()
  if (EVIDENCE_SET.has(n)) return 'Evidence'
  if (VERIFICATION_SET.has(n)) return 'Verification'
  if (VIEWER_SET.has(n)) return 'Viewer'
  return 'Analysis'
}

/** A trace query is any Evidence-category call. */
export function isTraceQueryTool(name) {
  return aiToolUsageCategory(name) === 'Evidence'
}

function resultOk(result) {
  if (!result || typeof result !== 'object') return true
  if (result.ok === false) return false
  if (result.error != null && result.error !== '') return false
  const st = String(result.status || '').toLowerCase()
  if (st === 'error' || st === 'failed' || st === 'failure') return false
  return true
}

function firstSentence(text, max = 120) {
  const s = String(text || '').replace(/\s+/g, ' ').trim()
  if (!s) return ''
  const cut = s.split(/(?<=[.!?])\s/)[0] || s
  return cut.length > max ? `${cut.slice(0, max - 1).trimEnd()}…` : cut
}

const VERDICT_LABEL = {
  confirmed: 'Confirmed',
  rejected: 'Refuted',
  refuted: 'Refuted',
  inconclusive: 'Inconclusive',
}

/**
 * Short factual one-liner describing what a tool call contributed.
 * Deterministic — derived from the structured result only, never synthesised.
 * Returns '' when nothing concrete is available (the row then shows just the
 * tool name, no filler).
 */
export function toolBriefResult(name, result) {
  const n = String(name || '').trim()
  if (!result || typeof result !== 'object') return ''
  const data = (result.data && typeof result.data === 'object') ? result.data : result

  if (n === 'verify_claim' || n === 'challenge_conclusion') {
    const raw = String(data.verdict || data.status || result.message || '').trim().toLowerCase()
    const verdict = VERDICT_LABEL[raw] || (raw ? raw[0].toUpperCase() + raw.slice(1) : '')
    const reason = String(
      data.reason || data.detail || data.summary
      || (Array.isArray(data.checks) && data.checks.find(c => c && c.ok === false)?.detail)
      || '',
    ).trim()
    if (verdict && reason) return `${verdict} — ${firstSentence(reason)}`
    if (verdict) return verdict
    return ''
  }

  if (n === 'query_raw_metric') {
    const metric = String(data.metric || data.name || '').trim()
    const idPart = (data.id != null && data.id !== '') ? `[${data.id}]` : ''
    const stat = String(data.stat || data.aggregate || '').trim()
    const val = data.value != null ? data.value : data.result
    let unit = String(data.unit || data.units || '').trim()
    if (unit && /^[A-Za-z]/.test(unit)) unit = ` ${unit}`
    if (metric && val != null) {
      const statTxt = stat ? `${stat} = ` : ''
      return `Found ${metric}${idPart} ${statTxt}${val}${unit}`.replace(/\s+/g, ' ').trim()
    }
  }

  for (const key of ['evidence', 'events', 'path', 'rows']) {
    const arr = data[key]
    if (Array.isArray(arr) && arr.length) {
      const first = arr.find(x => x && typeof x === 'object')
      const label = first ? String(first.label || first.detail || first.kind || '').trim() : ''
      const noun = key === 'rows' ? 'rows' : (key === 'path' ? 'path steps' : `${key === 'events' ? 'events' : 'evidence rows'}`)
      return label ? `${arr.length} ${noun} · ${firstSentence(label, 80)}` : `${arr.length} ${noun}`
    }
  }

  const summary = data.summary || data.message || result.message
  if (typeof summary === 'string' && summary.trim() && summary.trim().toLowerCase() !== 'ok') {
    return firstSentence(summary)
  }
  return ''
}

/**
 * Append one tool call to `usage` (returns a new object; input untouched).
 * `usage` shape: { calls: [ { name, category, ok, trace_query, brief } ] }.
 */
export function recordToolUsage(usage, { name, result = null } = {}) {
  const prev = (usage && Array.isArray(usage.calls)) ? usage.calls : []
  const n = String(name || '').trim()
  if (!n) return { calls: [...prev] }
  const category = aiToolUsageCategory(n)
  const rec = {
    name: n,
    category,
    ok: resultOk(result),
    trace_query: category === 'Evidence',
    brief: toolBriefResult(n, result),
  }
  return { calls: [...prev, rec] }
}

/** Seed `usage` from a list of tool names (no results yet). */
export function seedToolUsage(names) {
  let out = { calls: [] }
  for (const raw of names || []) {
    const nm = (raw && typeof raw === 'object') ? String(raw.name || '') : String(raw || '')
    if (nm.trim()) out = recordToolUsage(out, { name: nm })
  }
  return out
}

/**
 * Roll up `usage` into everything the UI shows.
 *   { total, unique, ok, failed, traceQueries,
 *     byCategory: { Evidence, Analysis, Verification, Viewer },
 *     groups: [ { name, category, count, ok, failed, brief } ] }
 * `groups` collapses repeated calls to one row, ordered by first occurrence.
 */
export function summarizeToolUsage(usage) {
  const calls = (usage && Array.isArray(usage.calls)) ? usage.calls : []
  const byCategory = { Evidence: 0, Analysis: 0, Verification: 0, Viewer: 0 }
  const order = []
  const byName = new Map()
  let ok = 0
  let failed = 0
  let traceQueries = 0
  for (const c of calls) {
    if (!c || typeof c !== 'object') continue
    const name = String(c.name || '').trim()
    if (!name) continue
    const category = AI_TOOL_USAGE_CATEGORIES.includes(c.category)
      ? c.category
      : aiToolUsageCategory(name)
    const callOk = c.ok !== false
    if (callOk) ok += 1
    else failed += 1
    byCategory[category] += 1
    if (c.trace_query || category === 'Evidence') traceQueries += 1
    if (!byName.has(name)) {
      order.push(name)
      byName.set(name, { name, category, count: 0, ok: 0, failed: 0, brief: '' })
    }
    const g = byName.get(name)
    g.count += 1
    if (callOk) g.ok += 1
    else g.failed += 1
    const brief = String(c.brief || '').trim()
    if (brief) g.brief = brief
  }
  return {
    total: calls.length,
    unique: order.length,
    ok,
    failed,
    traceQueries,
    byCategory,
    groups: order.map(name => byName.get(name)),
  }
}
