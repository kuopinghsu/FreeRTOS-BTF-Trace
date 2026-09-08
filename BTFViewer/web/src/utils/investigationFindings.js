/**
 * Investigation Findings — structured model, rule catalog, dedup, ranking.
 * Keep in sync with btf_viewer_pkg/investigation_findings.py.
 *
 * An additive layer over the loose finding dicts from
 * buildWorkflowAnalysisFindings: normalises to the canonical
 * InvestigationFinding shape (measured values kept separate from display text),
 * enumerates every deterministic rule (RULE_CATALOG), deduplicates same
 * rule+entity+overlapping-range findings, and ranks by severity / magnitude /
 * duration / evidence quality. Pure functions.
 */
import {
  QUEUE_CASE,
  QUEUE_DISMISSED,
  QUEUE_DONE,
  findingCategory,
  findingEvidenceStrength,
  findingQueueStatus,
} from './findingsTriage.js'

export const NO_FINDINGS_UNDER_RULES = 'No findings under the current rules'

export const FINDING_STATUS_NEW = 'new'
export const FINDING_STATUS_REVIEWED = 'reviewed'
export const FINDING_STATUS_BOOKMARKED = 'bookmarked'
export const FINDING_STATUS_DISMISSED = 'dismissed'
export const FINDING_STATUSES = [
  FINDING_STATUS_NEW, FINDING_STATUS_REVIEWED,
  FINDING_STATUS_BOOKMARKED, FINDING_STATUS_DISMISSED,
]

const QUEUE_TO_STATUS = {
  [QUEUE_DONE]: FINDING_STATUS_REVIEWED,
  [QUEUE_CASE]: FINDING_STATUS_BOOKMARKED,
  [QUEUE_DISMISSED]: FINDING_STATUS_DISMISSED,
}

const SEVERITY_WEIGHT = { error: 1.0, warning: 0.66, info: 0.33, ask: 0.15 }
const EVIDENCE_QUALITY = { direct: 1.0, derived: 0.6, estimated: 0.3, configured: 0.6 }
const MAGNITUDE_BY_SEVERITY = { error: 0.85, warning: 0.55, info: 0.25, ask: 0.15 }

const W_SEVERITY = 0.50
const W_MAGNITUDE = 0.25
const W_DURATION = 0.15
const W_EVIDENCE = 0.10
const DURATION_FULL_FRACTION = 0.25

const CORE_RE = /\bCore[_ ]?\d+\b/ig
const UNIT_CANON = { us: 'µs', 'μs': 'µs', 'µs': 'µs' }
const MEASURE_RE = new RegExp(
  '(?:(?<n1>[A-Za-zµσ][\\w./%-]{0,23})\\s*[=:]\\s*(?<v1>-?\\d+(?:\\.\\d+)?)\\s*(?<unit>%|ns|µs|us|μs|ms|s)?)'
  + '|(?:\\b(?<n2>Max|Min|Avg|Mean|Median|CV|G|σ|n|p50|p95|p99|Count|Migr|Rate|Score|Dwell|Ping|missed|Gap)'
  + '\\s+(?<v2>-?\\d+(?:\\.\\d+)?)\\s*(?<unit2>%|ns|µs|us|μs|ms|s)?)',
  'g',
)

function canonUnit(u) {
  return u ? (UNIT_CANON[u] || u) : ''
}

function specOf(ruleId, severity, category, observationKind, comparisonBasis, metric) {
  return { rule_id: ruleId, severity, category, observation_kind: observationKind, comparison_basis: comparisonBasis, metric }
}

/** Every rule_id the Analysis Findings engine can emit + its stable metadata. */
export const RULE_CATALOG = Object.freeze(Object.fromEntries([
  specOf('load_imbalance', 'warning', 'load', 'load_spike', 'Gini of per-core utilization vs even distribution', 'Core Utilization (excl. IDLE/TICK)'),
  specOf('load_balance_ok', 'info', 'load', 'load_spike', 'Gini of per-core utilization vs even distribution', 'Core Utilization (excl. IDLE/TICK)'),
  specOf('load_balance_moderate', 'info', 'load', 'load_spike', 'Gini of per-core utilization vs even distribution', 'Core Utilization (excl. IDLE/TICK)'),
  specOf('top_cpu', 'info', 'execution', 'execution_time_high', 'share of active CPU time in scope', 'Top Tasks by CPU (excl. IDLE/TICK)'),
  specOf('exec_max', 'info', 'execution', 'execution_time_high', 'observed slice maxima (not proven WCET)', 'Execution Time Per Slice'),
  specOf('wcet_anomaly', 'warning', 'execution', 'execution_time_high', "slice Max vs the entity's own average", 'Execution Time Per Slice'),
  specOf('exec_p95_exceeded', 'warning', 'execution', 'execution_time_high', "slice duration vs the entity's p95", 'Execution Time Per Slice'),
  specOf('blocking', 'info', 'blocking', 'latency_outlier', 'off-CPU gap count and Max vs peers', 'Off-CPU Time (Blocking Time)'),
  specOf('wakeup_latency_outlier', 'warning', 'dispatch', 'latency_outlier', "ready-to-run delay vs the entity's p95", 'Dispatch / Scheduling Latency'),
  specOf('priority_inversion', 'warning', 'blocking', 'latency_outlier', 'L/M/H priority pattern around a held mutex', 'Priority Inheritance'),
  specOf('thrashing', 'warning', 'migration', 'migration_frequent', 'migration rate / dwell / ping-pong vs heuristic thresholds', 'Core Migrations'),
  specOf('hot_pairs', 'warning', 'migration', 'migration_frequent', 'directed core-pair traffic and lock-bounce share', 'Core-Pair Migration Summary'),
  specOf('migration_burst_anomaly', 'warning', 'migration', 'load_spike', 'migration rate in a window vs the trace mean', 'Core Migrations'),
  specOf('period_instability', 'warning', 'jitter', 'period_instability', 'inter-arrival CV and missed/extra activations vs nominal period', 'Period / Jitter'),
  specOf('deadlines', 'error', 'deadline', 'execution_time_high', 'measured slice / CPU budget vs the configured limit', 'Deadlines / CPU budget'),
  specOf('tick_health', 'warning', 'health', 'period_instability', 'TICK interval CV and large gaps vs the nominal period', 'Trace Health (TICK)'),
  specOf('missed_ticks', 'warning', 'health', 'long_gap', 'large TICK gaps vs the nominal period', 'Trace Health (TICK)'),
  specOf('long_gap', 'info', 'general', 'long_gap', 'longest unscheduled interval vs the analysed span', 'Scheduling Load Over Time'),
  specOf('sync_bounce', 'warning', 'sync', 'migration_frequent', 'sync-object core bounces vs zero', 'Mutex / Semaphore'),
  specOf('sync_issues', 'warning', 'sync', 'missing_evidence', 'unpaired take/give STI events vs zero', 'Mutex / Semaphore'),
  specOf('baseline_regression', 'warning', 'general', 'regression', 'current metric vs the saved baseline value', 'Trace Compare'),
  specOf('missing_evidence', 'info', 'general', 'missing_evidence', 'event types required by the metric vs what the trace contains', 'Trace Health Check'),
  specOf('none', 'info', 'general', 'missing_evidence', 'no rule produced a finding in scope', 'Analysis Findings'),
].map(s => [s.rule_id, s])))

export const RULE_IDS = Object.keys(RULE_CATALOG)

export function ruleSpec(ruleId) {
  return RULE_CATALOG[String(ruleId || '').trim()] || null
}

export function parseMeasuredValues(text) {
  const out = []
  const seen = new Set()
  const src = String(text || '')
  MEASURE_RE.lastIndex = 0
  let m
  while ((m = MEASURE_RE.exec(src)) !== null) {
    const g = m.groups || {}
    const name = (g.n1 || g.n2 || '').replace(/^[\s.:=-]+|[\s.:=-]+$/g, '') || 'value'
    const rawVal = g.v1 ?? g.v2
    const unit = canonUnit(g.unit || g.unit2)
    const value = Number(rawVal)
    if (!Number.isFinite(value)) continue
    const v = Number.isInteger(value) ? value : value
    const key = `${name.toLowerCase()}|${v}|${unit}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push({ name, value: v, unit })
    if (out.length >= 8) break
  }
  return out
}

function normalizeMeasuredValues(raw, fallbackText) {
  const items = []
  if (Array.isArray(raw)) {
    for (const mv of raw) {
      if (!mv || typeof mv !== 'object') continue
      if (!('name' in mv) || !('value' in mv)) continue
      const item = { name: String(mv.name), value: mv.value, unit: canonUnit(String(mv.unit || '')) }
      if (mv.sample_count != null && Number.isFinite(Number(mv.sample_count))) {
        item.sample_count = Number(mv.sample_count)
      }
      if (mv.threshold != null) item.threshold = mv.threshold
      items.push(item)
    }
  }
  return items.length ? items : parseMeasuredValues(fallbackText)
}

function entitiesOf(raw) {
  let out = []
  if (Array.isArray(raw.entities)) out = raw.entities.map(String).map(s => s.trim()).filter(Boolean)
  if (!out.length && String(raw.task || '').trim()) out = [String(raw.task).trim()]
  if (!out.length) {
    const blob = `${raw.title || ''} ${raw.text || ''} ${raw.evidence_text || ''}`
    const found = blob.match(CORE_RE) || []
    for (const tok of found) {
      const t = tok.replace(/ /g, '_')
      if (!out.includes(t)) out.push(t)
    }
  }
  const seen = new Set()
  const uniq = []
  for (const e of out) { if (!seen.has(e)) { seen.add(e); uniq.push(e) } }
  return uniq
}

function evidenceRefsOf(raw) {
  const refs = []
  for (const ev of raw.evidence || []) {
    if (ev && typeof ev === 'object') {
      const label = String(ev.label || ev.text || 'evidence')
      let t = ev.time
      if (t == null) {
        for (const k of ['start', 'ns', 'stop']) { if (ev[k] != null) { t = ev[k]; break } }
      }
      const ref = { label }
      if (t != null && Number.isFinite(Number(t))) ref.time = Math.trunc(Number(t))
      refs.push(ref)
    } else if (ev) {
      refs.push({ label: String(ev) })
    }
  }
  return refs
}

function affectedRangeOf(raw, refs) {
  const rng = raw.affected_range
  if (rng && typeof rng === 'object' && rng.start != null && rng.end != null
      && Number.isFinite(Number(rng.start)) && Number.isFinite(Number(rng.end))) {
    return { start: Math.trunc(Number(rng.start)), end: Math.trunc(Number(rng.end)) }
  }
  const times = refs.filter(r => 'time' in r).map(r => r.time).sort((a, b) => a - b)
  if (!times.length) return null
  return { start: Math.trunc(times[0]), end: Math.trunc(times[times.length - 1]) }
}

function limitationsOf(raw) {
  if (Array.isArray(raw.limitations)) {
    const out = raw.limitations.map(String).map(s => s.trim()).filter(Boolean)
    if (out.length) return out
  }
  const conf = String(raw.confidence || '').trim()
  const low = conf.toLowerCase()
  if (/^(low|medium)/.test(low) || low.includes('heuristic') || low.includes('estimate')) {
    return conf ? [`Confidence: ${conf}`] : ['Heuristic — verify on the timeline.']
  }
  return []
}

function statusOf(raw, fid, triageState) {
  if (triageState != null && fid) {
    return QUEUE_TO_STATUS[findingQueueStatus(fid, triageState)] || FINDING_STATUS_NEW
  }
  const st = String(raw.status || '').trim().toLowerCase()
  return FINDING_STATUSES.includes(st) ? st : FINDING_STATUS_NEW
}

export function normalizeInvestigationFinding(raw, { triageState = null, totalSpanNs = null } = {}) {
  raw = { ...(raw || {}) }
  const fid = String(raw.id || '').trim()
  let ruleId = String(raw.rule_id || raw.fid || fid || '').trim()
  if (ruleId && !RULE_CATALOG[ruleId]) {
    const base = ruleId.replace(/-\d+$/, '')
    if (RULE_CATALOG[base]) ruleId = base
  }
  const spec = RULE_CATALOG[ruleId]
  const severity = String(raw.severity || (spec ? spec.severity : 'info')).toLowerCase()
  const observation = String(raw.observation || raw.text || raw.title || '').trim()
  const fallbackText = `${raw.evidence_text || ''} ${raw.text || ''}`
  const refs = evidenceRefsOf(raw)
  const evStrength = String(raw.evidence_strength || findingEvidenceStrength(raw)).toLowerCase()

  const out = {
    ...raw,
    id: fid || ruleId,
    rule_id: ruleId || 'general',
    severity,
    observation,
    affected_range: affectedRangeOf(raw, refs),
    entities: entitiesOf(raw),
    measured_values: normalizeMeasuredValues(raw.measured_values, fallbackText),
    comparison_basis: String(raw.comparison_basis || (spec ? spec.comparison_basis : '')),
    evidence_refs: refs,
    limitations: limitationsOf(raw),
    status: statusOf(raw, fid, triageState),
    category: String(raw.category || (spec ? spec.category : findingCategory(raw))),
    observation_kind: String(raw.observation_kind || (spec ? spec.observation_kind : 'general')),
    evidence_strength: evStrength,
  }
  out.rank_score = rankScore(out, totalSpanNs)
  return out
}

function magnitude(f) {
  const base = MAGNITUDE_BY_SEVERITY[String(f.severity || 'info')] ?? 0.25
  for (const mv of f.measured_values || []) {
    const name = String(mv.name || '').toLowerCase()
    if (['ratio', 'excess', 'ratio_over_avg', 'over'].includes(name)) {
      const r = Number(mv.value) / 10.0
      if (Number.isFinite(r)) return Math.max(0, Math.min(1, r))
    }
    if (mv.threshold != null && Number(mv.threshold) !== 0) {
      const r = Math.abs(Number(mv.value) / Number(mv.threshold))
      // A structured threshold refines magnitude but never sinks a finding
      // far below its same-severity peers.
      if (Number.isFinite(r)) return Math.max(0.5 * base, Math.min(1, r - 1.0))
    }
  }
  const nEv = (f.evidence_refs || []).length
  return Math.min(1.0, base + Math.min(0.10, 0.02 * nEv))
}

function durationNorm(f, totalSpanNs) {
  const rng = f.affected_range
  if (!(rng && typeof rng === 'object' && totalSpanNs > 0)) return 0.0
  const span = Math.max(0, Math.trunc(rng.end) - Math.trunc(rng.start))
  return Math.max(0, Math.min(1, (span / totalSpanNs) / DURATION_FULL_FRACTION))
}

export function rankScore(f, totalSpanNs = null) {
  const sev = SEVERITY_WEIGHT[String(f.severity || 'info')] ?? 0.33
  const mag = magnitude(f)
  const dur = durationNorm(f, totalSpanNs)
  const evq = EVIDENCE_QUALITY[String(f.evidence_strength || 'estimated')] ?? 0.3
  return Math.round((W_SEVERITY * sev + W_MAGNITUDE * mag + W_DURATION * dur + W_EVIDENCE * evq) * 1e6) / 1e6
}

export function rankInvestigationFindings(findings, { totalSpanNs = null } = {}) {
  const items = (findings || []).filter(f => f && typeof f === 'object').map((f) => {
    const g = { ...f }
    g.rank_score = rankScore(g, totalSpanNs)
    return g
  })
  items.sort((a, b) => (b.rank_score - a.rank_score) || String(a.id || '').localeCompare(String(b.id || '')))
  return items
}

const SEV_RANK = { error: 3, warning: 2, info: 1, ask: 0 }

function rangesOverlap(a, b) {
  if (a == null || b == null) return true
  return Math.trunc(a.start) <= Math.trunc(b.end) && Math.trunc(b.start) <= Math.trunc(a.end)
}

function entitiesIntersect(a, b) {
  if (!a.length || !b.length) return !a.length && !b.length
  const sb = new Set(b)
  return a.some(x => sb.has(x))
}

function mergePair(keep, drop) {
  const out = { ...keep }
  out.entities = [...new Set([...(keep.entities || []), ...(drop.entities || [])])].sort()
  const a = keep.affected_range
  const b = drop.affected_range
  if (a && b) out.affected_range = { start: Math.min(a.start, b.start), end: Math.max(a.end, b.end) }
  else if (b && !a) out.affected_range = b
  const seen = new Set((keep.evidence_refs || []).map(r => `${r.label}|${r.time}`))
  const refs = [...(keep.evidence_refs || [])]
  for (const r of drop.evidence_refs || []) {
    const k = `${r.label}|${r.time}`
    if (!seen.has(k)) { seen.add(k); refs.push(r) }
  }
  out.evidence_refs = refs
  out.merged_count = (keep.merged_count || 1) + (drop.merged_count || 1)
  return out
}

function preferKey(f) {
  return [
    -(SEV_RANK[String(f.severity || 'info')] ?? 1),
    -(f.rank_score || 0),
    -((f.evidence_refs || []).length),
    String(f.id || ''),
  ]
}

function preferLE(a, b) {
  const ka = preferKey(a)
  const kb = preferKey(b)
  for (let i = 0; i < ka.length; i++) {
    if (ka[i] < kb[i]) return true
    if (ka[i] > kb[i]) return false
  }
  return true
}

export function dedupeInvestigationFindings(findings) {
  const items = (findings || []).filter(f => f && typeof f === 'object').map(f => ({ ...f }))
  items.sort((a, b) => String(a.rule_id || '').localeCompare(String(b.rule_id || ''))
    || String(a.id || '').localeCompare(String(b.id || '')))

  const survivors = []
  for (const f of items) {
    const rid = String(f.rule_id || '')
    let merged = false
    for (let i = 0; i < survivors.length; i++) {
      const s = survivors[i]
      if (String(s.rule_id || '') !== rid) continue
      if (!entitiesIntersect(f.entities || [], s.entities || [])) continue
      if (!rangesOverlap(s.affected_range, f.affected_range)) continue
      const [keep, drop] = preferLE(s, f) ? [s, f] : [f, s]
      survivors[i] = mergePair(keep, drop)
      merged = true
      break
    }
    if (!merged) survivors.push({ ...f, merged_count: f.merged_count || 1 })
  }
  return survivors
}

export function buildInvestigationFindings(rawFindings, {
  triageState = null, totalSpanNs = null, dedupe = true,
} = {}) {
  let norm = (rawFindings || []).filter(f => f && typeof f === 'object')
    .map(f => normalizeInvestigationFinding(f, { triageState, totalSpanNs }))
  if (dedupe) norm = dedupeInvestigationFindings(norm)
  return rankInvestigationFindings(norm, { totalSpanNs })
}

export function investigationFindingExport(f) {
  return {
    id: f.id || '',
    rule_id: f.rule_id || 'general',
    severity: f.severity || 'info',
    status: f.status || FINDING_STATUS_NEW,
    observation: f.observation || '',
    category: f.category || 'general',
    comparison_basis: f.comparison_basis || '',
    affected_range: f.affected_range || null,
    entities: [...(f.entities || [])],
    measured_values: [...(f.measured_values || [])],
    evidence_refs: [...(f.evidence_refs || [])],
    limitations: [...(f.limitations || [])],
    rank_score: f.rank_score,
  }
}
