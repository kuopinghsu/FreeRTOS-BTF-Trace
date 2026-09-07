/**
 * Compact AI evidence package (TODO Phase 6).
 * Keep in sync with btf_viewer_pkg/ai_evidence_package.py.
 *
 * Assemble only the evidence needed to answer one question — question + range,
 * trace-health status + limitations, related entities, required statistics with
 * units and sample counts, a short event context, and the picked findings /
 * bookmarks — plus stable ids and an explicit fact / inference / missing
 * instruction. Pure + deterministic; `estimateTokens` sizes it before sending
 * and `formatEvidencePackagePreview` renders exactly what goes out.
 */

export const EVIDENCE_PACKAGE_SCHEMA = 'btf-viewer-evidence/1'

export const RESPONSE_CONTRACT = [
  'Confirmed observations',
  'Possible explanations',
  'Contradicting or missing evidence',
  'Recommended verification steps',
  'Evidence references',
]

const INSTRUCTIONS =
  'Answer only from the evidence below. Separate confirmed observations from '
  + 'inferences, and name missing evidence explicitly. Every claim must cite an '
  + 'evidence id or a time/value from this package; mark any uncited statement '
  + 'as unverified. If the evidence is insufficient, say so.'

const SUMMARY_KEYS = [
  'span_ns', 'tasks', 'segments', 'sti_events', 'context_switches',
  'gap_avg_ns', 'gap_max_ns', 'migrations', 'migrated_tasks',
  'load_balance_score', 'load_balance_sigma', 'tick_health', 'missed_ticks',
  'time_scale',
]

function compactSummary(summary) {
  if (!summary || typeof summary !== 'object') return {}
  const out = {}
  for (const k of SUMMARY_KEYS) {
    if (summary[k] != null) out[k] = summary[k]
  }
  return out
}

function makeRedactor(redact) {
  const map = new Map()
  return (name) => {
    const s = String(name || '')
    if (!redact || !s) return s
    if (!map.has(s)) map.set(s, `task_${map.size + 1}`)
    return map.get(s)
  }
}

export function buildEvidencePackage({
  question = '', scope = '', analysisRange = null, traceName = '',
  traceSummary = null, health = null, findings = null, investigation = null,
  entities = null, cores = null, statistics = null, eventContext = null,
  redactNames = false,
} = {}) {
  const red = makeRedactor(redactNames)
  const inv = (investigation && typeof investigation === 'object') ? investigation : {}

  const fnd = (findings || []).filter(f => f && typeof f === 'object').map((f, i) => ({
    id: `F${i + 1}`,
    rule_id: String(f.rule_id || f.ruleId || f.id || ''),
    severity: String(f.severity || 'info'),
    observation: String(f.observation || f.title || f.text || ''),
    entities: (f.entities || []).map(red),
    measured_values: [...(f.measured_values || f.measuredValues || [])],
    comparison_basis: String(f.comparison_basis || f.comparisonBasis || ''),
    limitations: [...(f.limitations || [])],
  }))

  const bms = (inv.bookmarks || []).filter(b => b && typeof b === 'object').map(b => ({
    id: String(b.id || ''),
    type: String(b.type || 'observation'),
    title: String(b.title || ''),
    note: String(b.note || ''),
    refs: (b.refs || []).filter(r => r && typeof r === 'object').map(r => ({ ...r })),
  }))

  const stats = (statistics || []).filter(s => s && typeof s === 'object').map(s => ({
    name: String(s.name || ''),
    value: s.value ?? null,
    unit: String(s.unit || ''),
    sample_count: s.sample_count ?? s.sampleCount ?? null,
    entity: red(s.entity || ''),
  }))

  const evc = (eventContext || []).filter(e => e && typeof e === 'object').map(e => ({
    time: e.time ?? null,
    kind: String(e.kind || ''),
    detail: red(e.detail || e.task || ''),
    core: String(e.core || ''),
  }))

  let healthBlock = null
  if (health && typeof health === 'object') {
    healthBlock = {
      status: String(health.status || ''),
      issue_count: Number(health.issue_count ?? health.issueCount ?? 0) || 0,
      limitations: [...(health.metric_limitations || health.metricLimitations || [])],
    }
  }

  const pkg = {
    schema: EVIDENCE_PACKAGE_SCHEMA,
    question: String(question || '').trim(),
    scope: String(scope || '').trim(),
    analysis_range: (analysisRange && analysisRange.start != null)
      ? { start: Math.trunc(analysisRange.start), end: Math.trunc(analysisRange.end) }
      : null,
    trace: {
      name: redactNames ? '(redacted)' : String(traceName || ''),
      summary: compactSummary(traceSummary),
    },
    trace_health: healthBlock,
    entities: (entities || []).map(red),
    cores: (cores || []).map(String),
    statistics: stats,
    event_context: evc,
    findings: fnd,
    bookmarks: bms,
    conclusion_so_far: String(inv.conclusion || ''),
    unresolved_questions: (inv.unresolved_questions || []).map(String),
    instructions: INSTRUCTIONS,
    response_contract: [...RESPONSE_CONTRACT],
    redacted: !!redactNames,
  }
  if (redactNames) pkg.alias_note = 'Task names replaced with task_N aliases for privacy.'
  return pkg
}

export function estimateTokens(pkg) {
  const text = JSON.stringify(sortKeys(pkg))
  return Math.max(1, Math.floor((text.length + 3) / 4))
}

export function evidencePackageSize(pkg) {
  const text = JSON.stringify(sortKeys(pkg))
  return {
    bytes: new TextEncoder().encode(text).length,
    chars: text.length,
    approx_tokens: estimateTokens(pkg),
    findings: (pkg.findings || []).length,
    bookmarks: (pkg.bookmarks || []).length,
    statistics: (pkg.statistics || []).length,
    event_context: (pkg.event_context || []).length,
  }
}

export function formatEvidencePackagePreview(pkg) {
  const size = evidencePackageSize(pkg)
  const lines = []
  lines.push(`Evidence package — ~${size.approx_tokens} tokens, `
    + `${size.bytes.toLocaleString()} bytes`
    + (pkg.redacted ? '  (task names redacted)' : ''))
  lines.push('')
  lines.push(`Question: ${pkg.question || '(none)'}`)
  if (pkg.scope) lines.push(`Scope: ${pkg.scope}`)
  if (pkg.analysis_range) lines.push(`Range: ${pkg.analysis_range.start} – ${pkg.analysis_range.end}`)
  if (pkg.trace_health) {
    const lim = pkg.trace_health.limitations?.length
      ? `; limited: ${pkg.trace_health.limitations.join(', ')}` : ''
    lines.push(`Trace health: ${pkg.trace_health.status} (${pkg.trace_health.issue_count} issue(s))${lim}`)
  }
  if (pkg.entities?.length) lines.push(`Entities: ${pkg.entities.slice(0, 20).join(', ')}`)
  if (pkg.statistics?.length) {
    lines.push(`Statistics (${pkg.statistics.length}):`)
    for (const s of pkg.statistics.slice(0, 20)) {
      const sc = s.sample_count != null ? `, n=${s.sample_count}` : ''
      const ent = s.entity ? ` [${s.entity}]` : ''
      lines.push(`  - ${s.name}${ent} = ${s.value} ${s.unit}${sc}`.trimEnd())
    }
  }
  if (pkg.findings?.length) {
    lines.push(`Findings (${pkg.findings.length}):`)
    for (const f of pkg.findings) lines.push(`  [${f.id}] ${f.severity}: ${f.observation}`)
  }
  if (pkg.bookmarks?.length) {
    lines.push(`Bookmarks (${pkg.bookmarks.length}):`)
    for (const b of pkg.bookmarks) lines.push(`  (${b.type}) ${b.title}`)
  }
  if (pkg.event_context?.length) {
    lines.push(`Event context: ${pkg.event_context.length} event(s) around the range`)
  }
  if (pkg.conclusion_so_far) lines.push(`Conclusion so far: ${pkg.conclusion_so_far}`)
  lines.push('')
  lines.push('Response contract: ' + (pkg.response_contract || []).join(' · '))
  lines.push(pkg.instructions || '')
  return lines.join('\n') + '\n'
}

function sortKeys(v) {
  if (Array.isArray(v)) return v.map(sortKeys)
  if (v && typeof v === 'object') {
    const out = {}
    for (const k of Object.keys(v).sort()) out[k] = sortKeys(v[k])
    return out
  }
  return v
}
