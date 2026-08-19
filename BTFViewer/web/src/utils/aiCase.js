/**
 * Investigation Case lifecycle: hypotheses, evidence graph, quality, validation.
 * Keep in sync with btf_viewer_pkg/ai_case.py.
 */

import { scoreInvestigationMetrics } from './aiPlanner.js'

export const HYPOTHESIS_STATUSES = [
  'supported', 'possible', 'rejected', 'need_evidence',
]
export const EVIDENCE_QUALITY_BANDS = [
  'strong', 'medium-high', 'medium', 'weak', 'insufficient',
]
export const INVESTIGATION_MODES = [
  'quick', 'diagnose', 'compare', 'optimize', 'report',
]
export const INVESTIGATION_SCOPE_OPTIONS = [
  'execution', 'blocking', 'migrations', 'priority inheritance',
  'nearby events', 'findings', 'tick',
]
export const EXPLAIN_LEVELS = ['quick', 'technical', 'deep']
export const PRIVACY_LEVELS = ['local', 'cloud_safe', 'sensitive']
export const CASE_SCHEMA = 'btf-investigation-case'
export const CASE_VERSION = 1

const JUMP_RE = /jump:([0-9]+(?:\.[0-9]+)?)/gi
const TASK_NAME_RE = /\b([A-Za-z][A-Za-z0-9_.-]*\[\d+\])/g
const METRIC_WORDS = [
  'migrations', 'blocking', 'execution', 'wcet', 'latency',
  'priority', 'inheritance', 'mutex', 'tick', 'deadline',
  'load', 'balance', 'preemption', 'contention', 'dwell',
]
const KNOWN_METRICS = new Set([
  ...METRIC_WORDS,
  'priority_inheritance', 'sync', 'findings', 'cpu', 'response',
])
const MERMAID_STRIP_RE = /["[\]{}()|]/g

const TOOL_REASONS = {
  detect_anomalies: 'Rank Findings as Critical / Warning / Info before drilling in',
  investigate: 'Build hypotheses and an evidence chain for the focus finding',
  correlate_events: 'Check whether blocking, migrations, and sync overlap the spike',
  query_raw_metric: 'Pull a scoped per-task series instead of guessing numbers',
  find_critical_path: 'Walk preempt / block / mutex around the evidence time',
  detect_priority_inversion: 'Test L/M/H inversion as an alternative to contention',
  search_timeline: 'Locate STI / tag / task timestamps like Find',
  compare_performance: 'Measure A vs B deltas instead of narrating them',
  what_if: 'Score a concrete pin / priority / contention experiment',
  optimize_experiment: 'Rank automatic mitigation candidates',
  explain_finding: 'Produce a levelled explanation of the selected finding',
  interpret_query: "Turn the user's question into an explicit investigation scope",
  validate_experiment: 'Compare expected experiment deltas with a new capture',
  manage_hypotheses: 'Mark a hypothesis supported, rejected, or needing evidence',
  plan_investigation: 'Plan the cheapest tool sequence and rank hypotheses first',
  suggest_scope: 'Recommend task and time window before gathering evidence',
  detect_contradictions: 'Challenge the leading hypothesis against metrics',
  assess_evidence_sufficiency: 'Stop when coverage is enough',
  cluster_findings: 'Group related findings into one incident',
  generate_fingerprint: 'Compact scheduling/sync/timing signature',
  find_similar_investigations: 'Match this fingerprint to recorded outcomes',
  regression_localize: 'Pin A vs B inflation to a task and region',
  build_causal_chain: 'Causal vs correlated vs temporal edges',
  generate_experiment_plan: 'Rank concrete firmware / what-if experiments',
  record_experiment_outcome: 'Feed measured results back into recommendations',
  score_investigation: 'Evidence efficiency, cost, stop, and falsification scores',
  analyze_temporal_causality: 'Order findings into a happens-before chain',
  build_task_dependency_graph: 'Task/resource graph from BTF sync, preemption, and migration',
  decompose_response_time: 'Split delay into blocking, preemption, and execution',
  rank_root_causes: 'Rank likely causes across findings and hypotheses',
  verify_claim: 'Check a causal claim against findings and scope',
  challenge_conclusion: 'List alternatives and missing evidence',
  investigation_memory: 'Store or recall similar past investigations',
  cluster_incidents: 'Group findings by time proximity',
  close_investigation: 'Record a conclusion and close the case',
  analyze_distribution: 'p50/p90/p99/p99.9, stddev, CV, and 3-sigma outlier rate',
  analyze_periodicity: 'Period/jitter (RMS, peak-to-peak) and kind: drift vs release vs WCET vs scheduler',
  summarize_investigation_context: 'Compact findings, hypotheses, and tools run',
}

function safeInt(value, fallback = 0) {
  const n = Number(value)
  return Number.isFinite(n) ? Math.round(n) : fallback
}

function mermaidSafeLabel(text, limit = 96) {
  const cleaned = String(text ?? '').replace(/\n/g, ' ').replace(MERMAID_STRIP_RE, '')
    .replace(/\s+/g, ' ').trim()
  return (cleaned || 'Node').slice(0, limit)
}

export function mermaidLabelWithTime(text, time, limit = 96) {
  let lab = String(text ?? '').trim() || 'Node'
  const tn = Number(time)
  let tok = ''
  if (Number.isFinite(tn)) tok = Number.isInteger(tn) ? String(tn) : String(tn)
  if (tok && !lab.includes(`jump:${tok}`)) lab = `${lab} jump:${tok}`
  return mermaidSafeLabel(lab, limit)
}

export const GUIDED_STAGES = [
  'triage', 'scope', 'investigate', 'verify', 'experiment', 'compare',
]
export const GUIDED_STAGE_LABELS = {
  idle: 'Start',
  triage: 'Triage',
  scope: 'Scope',
  investigate: 'Investigate',
  verify: 'Verify',
  experiment: 'Experiment',
  compare: 'Compare',
}

export const AI_CONTEXT_MODE_COMPACT = 'compact'
export const AI_CONTEXT_MODE_BALANCED = 'balanced'
export const AI_CONTEXT_MODE_FULL = 'full'
export const AI_CONTEXT_MODES = [
  AI_CONTEXT_MODE_COMPACT, AI_CONTEXT_MODE_BALANCED, AI_CONTEXT_MODE_FULL,
]
export const DEFAULT_AI_CONTEXT_MODE = AI_CONTEXT_MODE_BALANCED
export const AI_CONTEXT_MODE_LABELS = {
  [AI_CONTEXT_MODE_COMPACT]: 'Compact',
  [AI_CONTEXT_MODE_BALANCED]: 'Balanced',
  [AI_CONTEXT_MODE_FULL]: 'Full evidence',
}
export const AI_CONTEXT_MODE_SETTINGS_TOOLTIP = (
  'How much Findings, tools, and chat history are sent to the model.'
)
export const AI_CONTEXT_MODE_SETTINGS_LINES = {
  [AI_CONTEXT_MODE_COMPACT]: (
    'Compact — fewer Findings and tools; best for small local models.'
  ),
  [AI_CONTEXT_MODE_BALANCED]: (
    'Balanced (default) — moderate Findings, tools, and history.'
  ),
  [AI_CONTEXT_MODE_FULL]: (
    'Full evidence — complete Findings, tools, and history.'
  ),
}
export const AI_CONTEXT_STAGE_TOOLS = {
  triage: ['detect_anomalies', 'cluster_findings', 'suggest_scope'],
  scope: ['set_cursors', 'zoom_to_range', 'highlight_task'],
  investigate: ['investigate', 'correlate_events', 'find_critical_path'],
  verify: ['verify_claim', 'detect_contradictions', 'challenge_conclusion'],
  experiment: ['what_if', 'optimize_experiment', 'recommend_experiments'],
  compare: ['compare_performance', 'validate_experiment'],
  report: ['generate_report', 'export_investigation'],
}
export const AI_CONTEXT_ALWAYS_TOOLS = [
  'search_timeline', 'query_raw_metric', 'summarize_investigation_context',
]
export const AI_CONTEXT_BALANCED_EXTRA_TOOLS = [
  'detect_anomalies', 'investigate', 'set_cursors', 'zoom_to_range',
  'highlight_task', 'challenge_conclusion', 'what_if',
]
const CONTEXT_TOOL_ROW_KEYS = new Set([
  'rows', 'episodes', 'slices', 'events', 'gaps', 'hits', 'times',
  'experiments', 'anomalies', 'candidates', 'samples', 'values',
])
const FINDING_ITEM_RE = /^(\d+)\. \[([A-Z]+)\]/gm
const SEV_CONTEXT_RANK = { error: 0, critical: 0, warning: 1, info: 2 }

export function normalizeAiContextMode(value) {
  const raw = String(value || '').trim().toLowerCase().replace(/[-_]/g, ' ')
  if (raw === 'compact' || raw === 'reduced' || raw === 'reduce' || raw === 'low') {
    return AI_CONTEXT_MODE_COMPACT
  }
  if (raw === 'full' || raw === 'full evidence' || raw === 'fullevidence'
      || raw === 'complete' || raw === 'max') {
    return AI_CONTEXT_MODE_FULL
  }
  return DEFAULT_AI_CONTEXT_MODE
}

export function aiContextModeLabel(mode) {
  return AI_CONTEXT_MODE_LABELS[normalizeAiContextMode(mode)]
    || AI_CONTEXT_MODE_LABELS[DEFAULT_AI_CONTEXT_MODE]
}

export function aiContextModeSettingsOverview() {
  return AI_CONTEXT_MODES.map(m => AI_CONTEXT_MODE_SETTINGS_LINES[m]).join('\n')
}

export function aiContextModeSettingsHelp(mode = null) {
  const key = normalizeAiContextMode(mode)
  return AI_CONTEXT_MODE_SETTINGS_LINES[key]
    || AI_CONTEXT_MODE_SETTINGS_LINES[DEFAULT_AI_CONTEXT_MODE]
}

export function aiContextLimits(mode = null) {
  const key = normalizeAiContextMode(mode)
  if (key === AI_CONTEXT_MODE_COMPACT) {
    return {
      findings: 5, tool_rows: 10, history_user_turns: 2,
      max_tokens: 500, what_if: 3, diagrams: 'asked',
    }
  }
  if (key === AI_CONTEXT_MODE_FULL) {
    return {
      findings: null, tool_rows: 40, history_user_turns: 20,
      max_tokens: null, what_if: 12, diagrams: 'useful',
    }
  }
  return {
    findings: 12, tool_rows: 20, history_user_turns: 6,
    max_tokens: null, what_if: 5, diagrams: 'useful',
  }
}

export function contextModeSystemAddendum(mode = null) {
  const key = normalizeAiContextMode(mode)
  const keep = 'Never omit jump:TIME, range:LO/HI, real task names, measurements '
    + 'with units, confidence, evidence quality, what-if disclaimers, or '
    + 'at least one alternative / falsification.'
  if (key === AI_CONTEXT_MODE_COMPACT) {
    return ' Context mode is Compact: keep the reply around 300–500 tokens. '
      + 'Generate mermaid diagrams only if the user asks. ' + keep
  }
  if (key === AI_CONTEXT_MODE_FULL) {
    return ' Context mode is Full evidence: you may use the complete Findings, '
      + 'tools, and history. Include mermaid when it clarifies a sequence '
      + 'or migration. ' + keep
  }
  return ' Context mode is Balanced: prefer concise evidence-backed answers. '
    + 'Include mermaid when it clarifies a sequence or migration. ' + keep
}

function stageToolNames(stage) {
  let sid = String(stage || '').trim().toLowerCase()
  if (!sid || sid === 'idle' || sid === 'start') sid = 'triage'
  return AI_CONTEXT_STAGE_TOOLS[sid] || AI_CONTEXT_STAGE_TOOLS.triage
}

export function toolNamesForContextMode(mode = null, stage = '') {
  const key = normalizeAiContextMode(mode)
  if (key === AI_CONTEXT_MODE_FULL) return null
  const names = []
  const seen = new Set()
  const add = (seq) => {
    for (const name of seq || []) {
      const n = String(name || '').trim()
      if (n && !seen.has(n)) {
        seen.add(n)
        names.push(n)
      }
    }
  }
  let sid = String(stage || '').trim().toLowerCase()
  if (!sid || sid === 'idle' || sid === 'start') sid = 'triage'
  add(stageToolNames(sid))
  add(AI_CONTEXT_ALWAYS_TOOLS)
  if (key === AI_CONTEXT_MODE_BALANCED) {
    const idx = GUIDED_STAGES.indexOf(sid)
    if (idx > 0) add(stageToolNames(GUIDED_STAGES[idx - 1]))
    if (idx >= 0 && idx + 1 < GUIDED_STAGES.length) {
      add(stageToolNames(GUIDED_STAGES[idx + 1]))
    }
    add(AI_CONTEXT_BALANCED_EXTRA_TOOLS)
    add(AI_CONTEXT_STAGE_TOOLS.report)
  }
  return names
}

export function filterToolsForContextMode(tools, mode = null, stage = '') {
  const catalog = Array.isArray(tools) ? tools.filter(t => t && typeof t === 'object') : []
  const names = toolNamesForContextMode(mode, stage)
  if (names == null) return [...catalog]
  const want = new Set(names)
  return catalog.filter((tool) => want.has(String(tool?.function?.name || '').trim()))
}

export function investigationContextSummary(payload = null) {
  if (!payload || typeof payload !== 'object') return ''
  const cse = payload.investigation_case && typeof payload.investigation_case === 'object'
    ? payload.investigation_case
    : {}
  const finding = payload.finding && typeof payload.finding === 'object'
    ? payload.finding
    : {}
  const parts = []
  const title = String(cse.goal || finding.title || finding.id || '').trim()
  if (title) parts.push(`Focus: ${title}`)
  const quality = payload.evidence_quality
  if (quality && typeof quality === 'object') {
    const band = String(quality.band || '').trim()
    if (band) parts.push(`Evidence quality: ${band}`)
  }
  const hyps = cse.hypotheses || payload.hypotheses || []
  for (const hyp of hyps) {
    if (!hyp || typeof hyp !== 'object') continue
    const text = String(hyp.hypothesis || hyp.id || '').trim()
    if (!text) continue
    const status = String(hyp.status || '').trim()
    parts.push(`- ${status ? `${status}: ` : ''}${text}`)
    if (parts.length >= 8) break
  }
  const tools = cse.tools_executed || payload.tools_executed || []
  const labels = tools.map(t => String(t || '').trim()).filter(Boolean)
  if (labels.length) parts.push(`Tools: ${labels.slice(0, 12).join(', ')}`)
  return parts.join('\n').trim()
}

function findingBlocks(text) {
  const blob = String(text || '')
  const re = new RegExp(FINDING_ITEM_RE.source, 'gm')
  const matches = [...blob.matchAll(re)]
  if (!matches.length) return { header: blob.replace(/\s+$/, ''), items: [] }
  const header = blob.slice(0, matches[0].index).replace(/\s+$/, '')
  const items = matches.map((match, i) => {
    const start = match.index
    const end = i + 1 < matches.length ? matches[i + 1].index : blob.length
    return {
      sev: String(match[2] || '').toLowerCase(),
      block: blob.slice(start, end).replace(/\s+$/, ''),
    }
  })
  return { header, items }
}

export function compactFindingsText(text, mode = null, findings = null) {
  const limits = aiContextLimits(mode)
  const cap = limits.findings
  const raw = String(text || '').replace(/\s+$/, '')
  if (cap == null || !raw) return raw
  const { header, items } = findingBlocks(raw)
  if (items.length) {
    const ranked = items.map((item, i) => ({ i, item }))
      .sort((a, b) => (SEV_CONTEXT_RANK[a.item.sev] ?? 3) - (SEV_CONTEXT_RANK[b.item.sev] ?? 3)
        || a.i - b.i)
    const kept = ranked.slice(0, Number(cap)).map(row => row.item.block)
    const omitted = Math.max(0, items.length - kept.length)
    const lines = header ? [header, ''] : []
    lines.push(...kept)
    if (omitted) {
      lines.push(
        '',
        `${omitted} more finding(s) omitted (${aiContextModeLabel(mode)}). `
          + 'Ask for Full evidence or a specific finding id if needed.',
      )
    }
    return `${lines.join('\n').replace(/\s+$/, '')}\n`
  }
  if (Array.isArray(findings) && findings.length) {
    const ranked = findings
      .map((finding, i) => ({ i, finding }))
      .filter(row => row.finding && typeof row.finding === 'object')
      .sort((a, b) => (
        (SEV_CONTEXT_RANK[String(a.finding.severity || 'info').toLowerCase()] ?? 3)
        - (SEV_CONTEXT_RANK[String(b.finding.severity || 'info').toLowerCase()] ?? 3)
      ) || a.i - b.i)
    const kept = ranked.slice(0, Number(cap)).map(row => row.finding)
    const omitted = Math.max(0, ranked.length - kept.length)
    const lines = ['Analysis Findings', '']
    kept.forEach((finding, i) => {
      const sev = String(finding.severity || 'info').toUpperCase()
      const fid = String(finding.id || '').trim()
      const idBit = fid ? ` id=${fid}` : ''
      lines.push(`${i + 1}. [${sev}]${idBit} ${finding.title || 'Finding'}`)
      lines.push(`   ${finding.text || ''}`)
      for (const ev of (finding.evidence || [])) {
        if (ev && typeof ev === 'object' && ev.time != null) {
          lines.push(`   evidence: ${ev.label || 'event'} jump:${ev.time}`)
        } else if (ev) {
          lines.push(`   evidence: ${ev}`)
        }
      }
      lines.push('')
    })
    if (omitted) {
      lines.push(`${omitted} more finding(s) omitted (${aiContextModeLabel(mode)}).`)
    }
    return `${lines.join('\n').replace(/\s+$/, '')}\n`
  }
  const key = normalizeAiContextMode(mode)
  if (raw.length > 8000 && key === AI_CONTEXT_MODE_COMPACT) {
    return `${raw.slice(0, 8000).replace(/\s+$/, '')}\n… (truncated for Compact context)\n`
  }
  if (raw.length > 20000 && key === AI_CONTEXT_MODE_BALANCED) {
    return `${raw.slice(0, 20000).replace(/\s+$/, '')}\n… (truncated for Balanced context)\n`
  }
  return raw.endsWith('\n') ? raw : `${raw}\n`
}

function truncateToolLists(obj, rowCap, whatIfCap) {
  if (Array.isArray(obj)) {
    if (obj.length > rowCap) return obj.slice(0, rowCap)
    return obj.map(v => truncateToolLists(v, rowCap, whatIfCap))
  }
  if (!obj || typeof obj !== 'object') return obj
  const out = {}
  for (const [key, value] of Object.entries(obj)) {
    if ((key === 'experiments' || key === 'candidates') && Array.isArray(value)) {
      const cap = Math.min(rowCap, whatIfCap)
      if (value.length > cap) {
        out[key] = value.slice(0, cap).map(v => truncateToolLists(v, rowCap, whatIfCap))
        out.truncated = true
        out.omitted = Math.max(Number(out.omitted || 0), value.length - cap)
      } else {
        out[key] = value.map(v => truncateToolLists(v, rowCap, whatIfCap))
      }
    } else if (CONTEXT_TOOL_ROW_KEYS.has(key) && Array.isArray(value)) {
      if (value.length > rowCap) {
        out[key] = value.slice(0, rowCap).map(v => truncateToolLists(v, rowCap, whatIfCap))
        out.truncated = true
        out.omitted = Math.max(Number(out.omitted || 0), value.length - rowCap)
      } else {
        out[key] = value.map(v => truncateToolLists(v, rowCap, whatIfCap))
      }
    } else {
      out[key] = truncateToolLists(value, rowCap, whatIfCap)
    }
  }
  return out
}

export function compactToolResultPayload(result, mode = null) {
  const limits = aiContextLimits(mode)
  const rowCap = Number(limits.tool_rows || 40)
  const whatIfCap = Number(limits.what_if || 12)
  let payload = result
  let parsedJson = false
  if (typeof result === 'string') {
    const text = result.trim()
    if (text.startsWith('{') || text.startsWith('[')) {
      try {
        payload = JSON.parse(text)
        parsedJson = true
      } catch {
        payload = result
      }
    }
  }
  if (!payload || (typeof payload !== 'object')) return result
  const compacted = truncateToolLists(payload, rowCap, whatIfCap)
  if (compacted && typeof compacted === 'object' && !Array.isArray(compacted) && compacted.omitted) {
    const msg = String(compacted.message || '').trim()
    const extra = `${compacted.omitted} more row(s) omitted (${aiContextModeLabel(mode)}).`
    compacted.message = msg ? `${msg} ${extra}` : extra
  }
  return parsedJson ? JSON.stringify(compacted) : compacted
}

export function compactChatHistory(messages, mode = null, investigationSummary = '') {
  const limits = aiContextLimits(mode)
  const keepTurns = Math.max(1, Number(limits.history_user_turns || 2))
  const msgs = (messages || []).filter(m => m && typeof m === 'object')
  const system = []
  const rest = []
  for (const msg of msgs) {
    if (String(msg.role || '') === 'system' && !rest.length) system.push({ ...msg })
    else rest.push({ ...msg })
  }
  const userIdxs = []
  rest.forEach((msg, i) => {
    if (String(msg.role || '') !== 'user') return
    const content = String(msg.content || '').toLowerCase()
    if (content.includes('tool-call limit')) return
    userIdxs.push(i)
  })
  let omitted = 0
  let kept = rest
  if (userIdxs.length > keepTurns) {
    omitted = userIdxs.length - keepTurns
    kept = rest.slice(userIdxs[userIdxs.length - keepTurns])
  }
  const extra = []
  if (omitted) {
    const summary = String(investigationSummary || '').trim()
    extra.push({
      role: 'user',
      content: summary
        ? `### Investigation summary\n${summary}`
        : `[${omitted} earlier turn(s) omitted for ${aiContextModeLabel(mode)} context.]`,
    })
    extra.push({
      role: 'assistant',
      content: 'Understood. Continue from the recent turns.',
    })
  }
  const compacted = kept.map((msg) => {
    const copied = { ...msg }
    if (String(copied.role || '') === 'tool') {
      copied.content = compactToolResultPayload(copied.content, mode)
    }
    return copied
  })
  return [...system, ...extra, ...compacted]
}

export function formatContextUsageStatus(meter = null, mode = null) {
  const label = aiContextModeLabel(mode)
  const m = meter && typeof meter === 'object' ? meter : emptyCostMeter()
  const tokens = Number(m.total_tokens || 0)
  const tools = Number(m.tool_calls || 0)
  const timeS = Number(m.model_time_s || 0)
  if (tokens <= 0 && tools <= 0 && timeS <= 0) return `Context: ${label}`
  const timePart = timeS ? `${timeS}s` : '0s'
  return `Context: ${label} · ${formatTokenCount(tokens)} tok · `
    + `${Number.isFinite(tools) ? Math.max(0, Math.trunc(tools) || 0) : 0} tools · `
    + timePart
}

export const GUIDE_STAGE_NEEDLES = {
  triage: ['finding', 'triage', 'analysis'],
  scope: ['cursor', 'scope', 'c1'],
  investigate: ['evidence', 'correlate', 'critical path', 'root cause'],
  verify: ['verify', 'contradict', 'alternative', 'sufficiency'],
  experiment: ['what-if', 'what_if', 'optimize', 'estimate'],
  compare: ['compare', 'validate_experiment', 'recapture'],
}
export const ESTIMATE_BANNER = (
  'Heuristic estimate (What-if / Optimize) — recapture a trace and Compare to measure.'
)
export const VERIFY_HINT = (
  'Verify alternatives and contradictions before treating What-if as measured.'
)

export function guideStageNeedles(stage) {
  return GUIDE_STAGE_NEEDLES[stage] || []
}

function guideToolNames(payload, plan) {
  const names = []
  if (payload && typeof payload === 'object') {
    const cse = payload.investigation_case || {}
    for (const t of (cse.tools_executed || payload.tools_executed || [])) {
      names.push(String(t || '').trim())
    }
    for (const t of (payload.suggested_tools || [])) {
      names.push(String(t?.name || t || '').trim())
    }
  }
  if (plan && typeof plan === 'object') {
    for (const s of (plan.steps || [])) {
      names.push(String(s?.id || s?.label || s || '').trim())
    }
  }
  return names.filter(Boolean)
}

export function investigationGuideStage(payload, {
  plan = null, hasCursors = false, hasTwoTraces = false,
} = {}) {
  const tools = guideToolNames(payload, plan).join(' ').toLowerCase()
  const hasPayload = !!(payload && typeof payload === 'object' && Object.keys(payload).length)
  const hasPlan = !!(plan && (plan.steps?.length || plan.goal))
  if (!hasPayload && !hasPlan) return 'idle'
  let quality = ''
  if (hasPayload && payload.evidence_quality && typeof payload.evidence_quality === 'object') {
    quality = String(payload.evidence_quality.band || '').toLowerCase()
  }
  const verified = (
    ['verify_claim', 'detect_contradictions', 'assess_evidence_sufficiency', 'challenge_conclusion']
      .some(k => tools.includes(k))
    || quality === 'strong' || quality === 'medium-high'
  )
  if (hasTwoTraces && (
    tools.includes('validate_experiment')
    || tools.includes('compare_performance')
    || tools.includes('analyze_traces')
  )) return 'compare'
  if (tools.includes('what_if') || tools.includes('optimize_experiment')) {
    return verified ? 'experiment' : 'verify'
  }
  if (verified) return 'verify'
  if (
    ['investigate', 'correlate_events', 'find_critical_path', 'rank_root_causes']
      .some(k => tools.includes(k))
    || (hasPayload && (payload.evidence?.length || payload.root_cause_chain?.length))
  ) return 'investigate'
  if (hasCursors) return 'scope'
  return 'triage'
}

export function investigationIssueCard(payload) {
  const data = payload && typeof payload === 'object' ? payload : {}
  const finding = data.finding && typeof data.finding === 'object' ? data.finding : {}
  const quality = data.evidence_quality && typeof data.evidence_quality === 'object'
    ? data.evidence_quality : {}
  const interpreted = data.interpreted && typeof data.interpreted === 'object'
    ? data.interpreted : {}
  const title = String(finding.title || data.conclusion || data.subtitle || '').trim()
  let task = ''
  for (const key of ['task', 'task_name', 'primary_task']) {
    task = String(finding[key] || interpreted[key] || '').trim()
    if (task) break
  }
  return {
    title: title || 'Investigation',
    severity: String(finding.severity || '').trim(),
    task,
    band: String(quality.band || '').replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
    scope: String(interpreted.scope || data.scope || '').trim(),
    status: String(data.conclusion || '').trim().slice(0, 120),
  }
}

export function formatInvestigationIssueCard(card) {
  const data = card && typeof card === 'object' ? card : {}
  const title = String(data.title || '').trim()
  const task = String(data.task || '').trim()
  const band = String(data.band || '').trim()
  const scope = String(data.scope || '').trim()
  if ((title === '' || title === 'Investigation') && !task && !band) return ''
  const bits = [title || 'Investigation']
  if (task) bits.push(task)
  if (band) bits.push(`Evidence ${band}`)
  if (scope) bits.push(scope)
  return `CURRENT ISSUE\n${bits.join(' · ')}`
}

export const AI_SESSION_MAX_MESSAGES = 40
export const AI_SESSION_MAX_CHARS = 80000

export function dumpInvestigationSession({ payload = null, plan = null, messages = [] } = {}) {
  const msgs = []
  let total = 0
  const src = Array.isArray(messages) ? messages.slice(-AI_SESSION_MAX_MESSAGES) : []
  for (const raw of src) {
    const role = String(raw?.role || raw?.[0] || '')
    const text = String(raw?.content || raw?.text || raw?.[1] || '')
    if (!['user', 'assistant', 'evidence'].includes(role)) continue
    if (total + text.length > AI_SESSION_MAX_CHARS) break
    total += text.length
    msgs.push({ role, content: text.slice(0, 8000) })
  }
  return JSON.stringify({
    v: 1,
    payload: payload && typeof payload === 'object' ? payload : null,
    plan: plan && typeof plan === 'object' ? plan : null,
    messages: msgs,
  })
}

export function parseInvestigationSession(raw) {
  let data = raw
  if (typeof raw === 'string') {
    const text = raw.trim()
    if (!text) return { payload: null, plan: null, messages: [] }
    try { data = JSON.parse(text) } catch { return { payload: null, plan: null, messages: [] } }
  }
  if (!data || typeof data !== 'object') return { payload: null, plan: null, messages: [] }
  const messages = []
  for (const m of (data.messages || []).slice(0, AI_SESSION_MAX_MESSAGES)) {
    if (!m || typeof m !== 'object') continue
    const role = String(m.role || '')
    if (!['user', 'assistant', 'evidence'].includes(role)) continue
    messages.push({ role, content: String(m.content || '').slice(0, 8000) })
  }
  return {
    payload: data.payload && typeof data.payload === 'object' ? data.payload : null,
    plan: data.plan && typeof data.plan === 'object' ? data.plan : null,
    messages,
  }
}

/** True when a session blob has a user or assistant turn (not evidence-only). */
export function investigationSessionHasChat(messages) {
  for (const raw of messages || []) {
    const role = String(raw?.role || raw?.[0] || '')
    const text = String(raw?.content || raw?.text || raw?.[1] || '')
    if ((role === 'user' || role === 'assistant') && text.trim()) return true
  }
  return false
}

export function emptyInvestigationCase({
  question = '', trace = '', cursorLo = null, cursorHi = null,
  tasks = [], cores = [],
} = {}) {
  return {
    schema: CASE_SCHEMA,
    version: CASE_VERSION,
    question: String(question || '').trim(),
    scope: {
      trace: String(trace || '').trim(),
      cursor_lo: cursorLo,
      cursor_hi: cursorHi,
      tasks: (tasks || []).map(t => String(t).trim()).filter(Boolean),
      cores: (cores || []).map(c => String(c).trim()).filter(Boolean),
    },
    suspected_findings: [],
    hypotheses: [],
    evidence: [],
    tools_executed: [],
    tool_reasons: [],
    evidence_timeline: [],
    evidence_graph: {},
    evidence_quality: {},
    evidence_coverage: {},
    falsification: {},
    confidence: 'Medium',
    confidence_history: [],
    conclusion: '',
    alternatives_rejected: [],
    recommended_action: '',
    validation: {},
    mode: 'diagnose',
  }
}

function findingBlob(finding) {
  if (!finding || typeof finding !== 'object') return ''
  return `${finding.title || ''} ${finding.text || ''}`
}

export function enrichHypotheses(hypotheses = [], {
  evidence = [], alternatives = [],
} = {}) {
  const ev = (evidence || []).filter(e => e && typeof e === 'object')
  const timed = ev.filter(e => e.time != null).length
  const kinds = new Set()
  for (const e of ev) {
    const label = String(e.label || e.kind || '')
    const kind = label.includes(':') ? label.split(':')[0].trim().toLowerCase() : label.toLowerCase()
    if (kind) kinds.add(kind)
  }
  const altStatus = {}
  for (const a of alternatives || []) {
    if (!a || typeof a !== 'object') continue
    altStatus[String(a.hypothesis || '').trim().toLowerCase()] = String(a.status || '').toLowerCase()
  }
  const out = []
  ;(hypotheses || []).forEach((raw, i) => {
    if (!raw || typeof raw !== 'object') return
    const hyp = String(raw.hypothesis || '').trim()
    if (!hyp) return
    const why = String(raw.why || '').trim()
    let status = String(raw.status || '').trim().toLowerCase()
    if (!HYPOTHESIS_STATUSES.includes(status)) {
      const mapped = altStatus[hyp.toLowerCase()] || ''
      if (mapped === 'rejected') status = 'rejected'
      else if (mapped === 'confirmed' || (i === 0 && timed)) status = 'supported'
      else if (i === 0) status = 'possible'
      else if (timed && [...kinds].some(k => hyp.toLowerCase().includes(k))) status = 'possible'
      else status = 'need_evidence'
    }
    let conf
    if (status === 'supported') conf = 70 + Math.min(25, 8 * timed) - 4 * i
    else if (status === 'possible') conf = 40 + Math.min(20, 5 * timed) - 6 * i
    else if (status === 'rejected') conf = Math.max(5, 18 - 4 * i)
    else conf = 22 - 4 * i
    out.push({
      id: String(raw.id || `h${i + 1}`),
      hypothesis: hyp,
      why,
      status,
      confidence: Math.max(0, Math.min(100, Math.trunc(conf))),
      evidence_count: (status === 'supported' || status === 'possible') ? timed : 0,
    })
  })
  return out
}

export function setHypothesisStatus(hypotheses, hypothesisId, status, { reason = '' } = {}) {
  const want = String(hypothesisId || '').trim().toLowerCase()
  let st = String(status || '').trim().toLowerCase()
  if (!HYPOTHESIS_STATUSES.includes(st)) st = 'need_evidence'
  const out = []
  ;(hypotheses || []).forEach((h, i) => {
    if (!h || typeof h !== 'object') return
    const item = { ...h }
    const hid = String(item.id || `h${i + 1}`).toLowerCase()
    const name = String(item.hypothesis || '').trim().toLowerCase()
    if (hid === want || name === want || String(i + 1) === want) {
      item.status = st
      if (reason) item.why = String(reason).trim()
      if (st === 'supported') item.confidence = Math.max(safeInt(item.confidence, 70), 70)
      else if (st === 'rejected') item.confidence = Math.min(safeInt(item.confidence, 18), 25)
    }
    out.push(item)
  })
  return out
}

export function compareHypotheses(hypotheses = []) {
  const items = (hypotheses || []).filter(h => h && typeof h === 'object')
  const rank = { supported: 0, possible: 1, need_evidence: 2, rejected: 3 }
  const ranked = [...items].sort((a, b) => {
    const ra = rank[String(a.status || '')] ?? 9
    const rb = rank[String(b.status || '')] ?? 9
    if (ra !== rb) return ra - rb
    return safeInt(b.confidence) - safeInt(a.confidence)
  })
  return {
    ok: true,
    ranked,
    leader: ranked[0] || null,
    supported: ranked.filter(h => h.status === 'supported'),
    rejected: ranked.filter(h => h.status === 'rejected'),
  }
}

export function buildEvidenceGraph(finding = null, {
  evidence = [], hypotheses = [], chain = [],
} = {}) {
  const nodes = []
  const edges = []
  const fid = 'F'
  if (finding && typeof finding === 'object') {
    nodes.push({
      id: fid,
      kind: 'finding',
      label: String(finding.title || finding.id || 'Finding'),
      time: null,
    })
  }
  const evItems = (evidence || []).filter(e => e && typeof e === 'object')
  evItems.slice(0, 12).forEach((ev, i) => {
    const nid = `E${i}`
    nodes.push({
      id: nid,
      kind: 'evidence',
      label: mermaidLabelWithTime(ev.label || ev.kind || 'evidence', ev.time),
      time: ev.time,
    })
    if (nodes.some(n => n.id === fid)) {
      edges.push({ from: fid, to: nid, rel: 'observed' })
    }
  })
  ;(chain || []).slice(0, 8).forEach((step, i) => {
    if (!step || typeof step !== 'object') return
    const nid = `C${i}`
    nodes.push({
      id: nid,
      kind: String(step.kind || 'step'),
      label: mermaidLabelWithTime(step.label || `Step ${i + 1}`, step.time),
      time: step.time,
    })
    if (i === 0 && nodes.some(n => n.id === fid)) {
      edges.push({ from: fid, to: nid, rel: 'chain' })
    } else if (i > 0) {
      edges.push({ from: `C${i - 1}`, to: nid, rel: 'chain' })
    }
  })
  ;(hypotheses || []).slice(0, 8).forEach((h, j) => {
    if (!h || typeof h !== 'object') return
    const nid = `H${j}`
    const status = String(h.status || 'possible')
    const rel = status === 'supported' ? 'supports'
      : (status === 'rejected' ? 'contradicts' : 'hypothesizes')
    nodes.push({
      id: nid,
      kind: 'hypothesis',
      label: String(h.hypothesis || `Hypothesis ${j + 1}`),
      status,
      time: null,
    })
    if (nodes.some(n => n.id === fid)) {
      edges.push({ from: fid, to: nid, rel })
    }
  })
  return { nodes, edges, mermaid: evidenceGraphMermaid(nodes, edges) }
}

export function evidenceGraphMermaid(nodes = [], edges = []) {
  const items = (nodes || []).filter(n => n && typeof n === 'object' && n.id)
  if (!items.length) return ''
  const lines = ['graph TD']
  for (const n of items) {
    const nid = String(n.id)
    const label = mermaidSafeLabel(n.label || nid)
    const kind = String(n.kind || '')
    if (kind === 'hypothesis') lines.push(`${nid}(${label})`)
    else if (kind === 'evidence') lines.push(`${nid}{{${label}}}`)
    else lines.push(`${nid}[${label}]`)
  }
  for (const e of edges || []) {
    if (!e || typeof e !== 'object') continue
    const src = String(e.from || '')
    const dst = String(e.to || '')
    if (!src || !dst) continue
    const rel = String(e.rel || '').trim()
    if (rel && rel !== 'observed' && rel !== 'chain') {
      lines.push(`${src} -- ${rel} --> ${dst}`)
    } else {
      lines.push(`${src} --> ${dst}`)
    }
  }
  return lines.join('\n')
}

export function evidenceQualityBand(score) {
  const n = Math.max(0, Math.min(100, safeInt(score)))
  if (n >= 80) return 'strong'
  if (n >= 65) return 'medium-high'
  if (n >= 45) return 'medium'
  if (n >= 25) return 'weak'
  return 'insufficient'
}

export function qualityBar(band, width = 10) {
  const filledMap = {
    strong: width,
    'medium-high': Math.max(1, Math.round(width * 0.8)),
    medium: Math.max(1, Math.round(width * 0.55)),
    weak: Math.max(1, Math.round(width * 0.3)),
    insufficient: 0,
  }
  const filled = filledMap[String(band || '')] ?? 0
  const label = {
    strong: 'Strong',
    'medium-high': 'Medium-High',
    medium: 'Medium',
    weak: 'Weak',
    insufficient: 'Insufficient',
  }[String(band || '')] || 'Insufficient'
  return '█'.repeat(filled) + '░'.repeat(width - filled) + ` ${label}`
}

export function computeEvidenceQuality({
  score = 0, breakdown = [], evidence = [], alternatives = [],
  checks = [], evidenceChain = '',
} = {}) {
  const ev = (evidence || []).filter(e => e && typeof e === 'object')
  const alts = (alternatives || []).filter(a => a && typeof a === 'object')
  const chks = (checks || []).filter(c => c && typeof c === 'object')
  const hasDirect = ev.some(e => e.time != null)
  const kinds = new Set()
  for (const e of ev) {
    const label = String(e.label || '')
    if (label.includes(':')) {
      const kind = label.split(':')[0].trim().toLowerCase()
      if (kind) kinds.add(kind)
    }
  }
  const hasTimeline = kinds.size >= 2 || Boolean(String(evidenceChain || '').trim())
  const hasMetric = chks.length > 0
  const untested = alts.filter(a => {
    const s = String(a.status || '').toLowerCase()
    return s === 'untested' || s === 'need_evidence' || s === ''
  })
  const altMark = alts.length && !untested.length ? 'yes' : (alts.length ? 'partial' : 'no')
  const band = evidenceQualityBand(score)
  return {
    band,
    bar: qualityBar(band),
    score: Math.max(0, Math.min(100, safeInt(score))),
    label: 'Evidence Quality',
    flags: {
      direct_evidence: hasDirect,
      timeline_correlation: hasTimeline,
      metric_correlation: hasMetric,
      alternative_tested: altMark,
    },
    breakdown: [...(breakdown || [])],
    confidence_label: {
      strong: 'High',
      'medium-high': 'Medium-High',
      medium: 'Medium',
      weak: 'Low',
      insufficient: 'Low',
    }[band] || 'Low',
  }
}

export function computeEvidenceCoverage({
  claims = [], evidence = [], knownTasks = [], knownMetrics = null,
} = {}) {
  const claimItems = (claims || []).filter(c => c && typeof c === 'object')
  const ev = (evidence || []).filter(e => e && typeof e === 'object')
  const tasks = new Set((knownTasks || []).map(t => String(t).trim().toLowerCase()).filter(Boolean))
  const metrics = new Set(
    (knownMetrics || [...KNOWN_METRICS]).map(m => String(m).trim().toLowerCase()).filter(Boolean),
  )
  const timed = new Set(ev.filter(e => e.time != null).map(e => e.time))
  let total = claimItems.length
  let observed = 0
  let timeline = 0
  let metricOk = 0
  let unverified = 0
  for (const c of claimItems) {
    const kind = String(c.kind || '')
    const ok = !!c.ok
    if (kind === 'timestamp' || kind === 'jump') {
      if (ok || timed.has(c.value)) {
        timeline += 1
        observed += 1
      } else unverified += 1
    } else if (kind === 'task') {
      const name = String(c.value || '').trim().toLowerCase()
      if (ok || tasks.has(name)) observed += 1
      else unverified += 1
    } else if (kind === 'metric') {
      const name = String(c.value || '').trim().toLowerCase()
      if (ok || metrics.has(name)) {
        metricOk += 1
        observed += 1
      } else unverified += 1
    } else if (ok) observed += 1
    else unverified += 1
  }
  const denom = total || 1
  let pct = total ? Math.round(100.0 * observed / denom) : (ev.length ? 100 : 0)
  if (!claimItems.length && ev.length) {
    observed = Math.min(ev.length, 7)
    total = Math.max(ev.length, 7)
    timeline = ev.filter(e => e.time != null).length
    pct = Math.round(100.0 * Math.min(1, observed / Math.max(total, 1)))
  }
  return {
    percent: Math.max(0, Math.min(100, pct)),
    bar: `${'█'.repeat(Math.max(0, Math.min(10, Math.round(10 * Math.max(0, Math.min(100, pct)) / 100))))}${'░'.repeat(10 - Math.max(0, Math.min(10, Math.round(10 * Math.max(0, Math.min(100, pct)) / 100))))} ${Math.max(0, Math.min(100, pct))}%`,
    directly_observed: `${observed}/${total || observed}`,
    timeline_verified: timeline,
    metric_verified: metricOk,
    unverified_assumptions: unverified,
    claims: total,
  }
}

function qualityFlagMark(value) {
  if (value === true || ['yes', 'true', '1'].includes(String(value).toLowerCase())) return '✓'
  if (['partial', 'triangle', 'maybe'].includes(String(value).toLowerCase())) return '△'
  return '○'
}

export function formatQualityFlagLines(quality = null, labels = {}) {
  const flags = quality && typeof quality === 'object' && quality.flags && typeof quality.flags === 'object'
    ? quality.flags
    : {}
  const rows = [
    ['direct_evidence', 'quality_direct', 'Direct evidence'],
    ['timeline_correlation', 'quality_timeline', 'Timeline correlation'],
    ['metric_correlation', 'quality_metric', 'Metric correlation'],
    ['alternative_tested', 'quality_alternative', 'Alternative tested'],
  ]
  return rows.map(([fk, lk, fallback]) => `- ${labels[lk] || fallback} ${qualityFlagMark(flags[fk])}`)
}

export function formatCoverageCountLines(coverage = null, labels = {}) {
  const cov = coverage && typeof coverage === 'object' ? coverage : {}
  if (cov.directly_observed == null && cov.claims == null) return []
  const denom = cov.claims != null && cov.claims !== '' ? `/${cov.claims}` : ''
  const timeline = cov.timeline_verified
  const metric = cov.metric_verified
  return [
    `- ${labels.coverage_observed || 'Directly observed'} ${cov.directly_observed}`,
    `- ${labels.coverage_timeline || 'Timeline verified'} ${timeline}${String(timeline).includes('/') ? '' : denom}`,
    `- ${labels.coverage_metric || 'Metric verified'} ${metric}${String(metric).includes('/') ? '' : denom}`,
    `- ${labels.coverage_unverified || 'Unverified assumptions'} ${cov.unverified_assumptions}`,
  ]
}

export function shouldConfirmInterpretedQuery(query = '', {
  templateId = '', alreadyInterpreted = false,
} = {}) {
  if (alreadyInterpreted || String(templateId || '').trim()) return false
  const q = String(query || '').trim()
  if (!q) return false
  if (q.includes('Investigation scope:') && q.includes('Interpreted as ')) return false
  return true
}

const COMPARE_PERCENT_ALIASES = {
  migrations: 'migrations',
  migrated_tasks: 'migrations',
  blocking: 'blocking',
  execution: 'execution',
}

export function experimentPercentsFromCompare(compare = null) {
  let data = compare && typeof compare === 'object' ? compare : {}
  if (data.data && typeof data.data === 'object' && !data.checks) data = data.data
  const out = {}
  const store = (rawKey, pct) => {
    const value = Number(pct)
    if (!Number.isFinite(value)) return
    const key = String(rawKey || '').trim().toLowerCase().replace(/ /g, '_')
    if (!key) return
    const alias = COMPARE_PERCENT_ALIASES[key] || key
    out[alias] = value
    if (alias !== key) out[key] = value
  }
  for (const c of data.checks || []) {
    if (!c || typeof c !== 'object') continue
    let mid = String(c.id || c.metric || '').trim()
    const label = String(c.label || '').toLowerCase()
    if (!mid) {
      if (label.includes('migrat')) mid = 'migrations'
      else if (label.includes('block')) mid = 'blocking'
      else if (label.includes('execut')) mid = 'execution'
    }
    const detail = String(c.detail || '')
    if (c.delta == null) continue
    if (detail.includes('%')) {
      store(mid, c.delta)
      continue
    }
    const cand = Number(c.candidate)
    const base = Number(c.baseline)
    if (Number.isFinite(cand) && Number.isFinite(base) && base) {
      store(mid, 100.0 * (cand - base) / Math.abs(base))
    }
  }
  for (const r of data.rows || []) {
    if (!r || typeof r !== 'object' || r.delta_pct == null) continue
    const field = String(r.field || '')
    if (field && field !== 'count' && field !== 'total') continue
    store(r.metric, r.delta_pct)
  }
  return out
}

const ANNOTATION_LINE_RE = /^(?:annotation|note|mark)\s*[:=]\s*.+$/gim
const ANNOTATION_INLINE_RE = /\b(?:annotation|note)\s*(?:[:=]\s*|"\s*)"[^"]*"/gi

export function sanitizeAnnotationsText(text) {
  return String(text || '').replace(ANNOTATION_LINE_RE, '[annotation]').replace(ANNOTATION_INLINE_RE, '[annotation]')
}

export function falsificationChecks(finding = null) {
  const blob = findingBlob(finding).toLowerCase()
  const title = finding && typeof finding === 'object'
    ? String(finding.title || 'this finding')
    : 'the conclusion'
  let checks = []
  let nextCheck = 'Inspect the strongest jump:TIME on the timeline'
  if (blob.includes('migrat') || blob.includes('thrash') || blob.includes('bounc')) {
    checks = [
      'No core-to-core hops in the cursor window for the named task',
      'Ping-pong / bounce count is near zero in the scoped Statistics',
      'Another task accounts for the majority of migrations',
    ]
    nextCheck = 'Open Core Migrations / Heatmap around the cited jump:TIME'
  } else if (
    blob.includes('block') || blob.includes('latency')
    || blob.includes('mutex') || blob.includes('contention')
  ) {
    checks = [
      'No corresponding mutex hold episode in the window',
      'Latency spike occurs while the task is runnable (on-CPU)',
      'Another task causes the majority of blocking',
    ]
    nextCheck = 'Inspect mutex hold / Blocking Max around the cited jump:TIME'
  } else if (blob.includes('inversion') || blob.includes('inherit')) {
    checks = [
      'No L/M/H geometry or inherit episode in the window',
      'The waiter is not blocked on the suspected mutex',
      'Priority boost duration does not overlap the latency spike',
    ]
    nextCheck = 'Open Priority Inheritance around the cited jump:TIME'
  } else if (blob.includes('wcet') || blob.includes('execution') || blob.includes('spike')) {
    checks = [
      'Max execution slice is in-family with typical (no Max≫Avg)',
      'The long slice is an ISR / TICK, not the named task',
      'Preemption, not payload, stretches the slice',
    ]
    nextCheck = 'Jump to Execution Max and confirm the task row'
  } else if (blob.includes('tick') || blob.includes('missed')) {
    checks = [
      'Tick CV is below the 5% threshold in this scope',
      'Large gaps are idle (tickless), not missed ticks under load',
    ]
    nextCheck = 'Open Trace Health (TICK) for the scoped window'
  } else if (blob.includes('load') || blob.includes('imbalance') || blob.includes('balance')) {
    checks = [
      'Load Balance Score is in the green zone for this window',
      'Concurrent-active distribution is even across cores',
    ]
    nextCheck = 'Open Core Utilisation / Load Balance Score'
  } else {
    checks = [
      'Cited jump:TIME is outside the cursor region',
      'Named task does not appear in scoped Statistics',
      'The metric named in the conclusion is not present',
    ]
  }
  return {
    conclusion: title,
    would_disprove: checks,
    disprove: checks,
    supporting: [],
    next_check: nextCheck,
  }
}

export function extractClaims(text, {
  knownTasks = [], knownMetrics = null, cursorLo = null, cursorHi = null,
} = {}) {
  const src = String(text || '')
  const tasks = new Set((knownTasks || []).map(t => String(t).trim()).filter(Boolean))
  const tasksL = {}
  for (const t of tasks) tasksL[t.toLowerCase()] = t
  const metrics = new Set(
    (knownMetrics || [...KNOWN_METRICS]).map(m => String(m).trim().toLowerCase()).filter(Boolean),
  )
  const claims = []
  const seen = new Set()
  const add = (kind, value, ok, detail = '') => {
    const key = `${kind}\0${value}`
    if (seen.has(key)) return
    seen.add(key)
    claims.push({ kind, value, ok, detail })
  }
  JUMP_RE.lastIndex = 0
  let m
  while ((m = JUMP_RE.exec(src))) {
    const t = Number(m[1])
    if (!Number.isFinite(t)) continue
    let inScope = true
    let detail = ''
    if (cursorLo != null && t < Number(cursorLo)) {
      inScope = false
      detail = 'timestamp before cursor window'
    }
    if (cursorHi != null && t > Number(cursorHi)) {
      inScope = false
      detail = 'timestamp after cursor window'
    }
    add('jump', t, inScope, detail)
  }
  TASK_NAME_RE.lastIndex = 0
  while ((m = TASK_NAME_RE.exec(src))) {
    const name = m[1]
    if (tasks.size) {
      const ok = name.toLowerCase() in tasksL
      add('task', name, ok, ok ? '' : 'task not in trace/findings')
    } else {
      add('task', name, true, 'no known-task list; accepted')
    }
  }
  const low = src.toLowerCase()
  for (const metric of [...metrics].sort()) {
    if (new RegExp(`\\b${metric.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`).test(low)) {
      add('metric', metric, true)
    }
  }
  return {
    claims,
    tasks: claims.filter(c => c.kind === 'task').map(c => String(c.value)),
    jumps: claims.filter(c => c.kind === 'jump').map(c => Number(c.value)),
    metrics: claims.filter(c => c.kind === 'metric').map(c => String(c.value)),
  }
}

export function validateAiResponse(text, opts = {}) {
  const o = opts && typeof opts === 'object' ? opts : {}
  const knownTasks = o.knownTasks || o.tasks || []
  const knownMetrics = o.knownMetrics || o.metrics || null
  const knownTimes = o.knownTimes || o.times || []
  const cursorLo = o.cursorLo ?? o.cursor_lo ?? null
  const cursorHi = o.cursorHi ?? o.cursor_hi ?? null
  const toolResults = o.toolResults || o.tool_results || []
  const allowEstimates = o.allowEstimates !== false && o.allow_estimates !== false
  const extracted = extractClaims(text, { knownTasks, knownMetrics, cursorLo, cursorHi })
  const claims = Array.isArray(extracted) ? extracted : (extracted.claims || [])
  const times = new Set()
  for (const t of knownTimes || []) {
    const n = Number(t)
    if (Number.isFinite(n)) times.add(n)
  }
  for (const res of toolResults || []) {
    if (!res || typeof res !== 'object') continue
    const data = res.data && typeof res.data === 'object' ? res.data : res
    for (const key of ['evidence', 'events', 'path']) {
      for (const item of data[key] || []) {
        if (item && typeof item === 'object' && item.time != null) {
          const n = Number(item.time)
          if (Number.isFinite(n)) times.add(n)
        }
      }
    }
  }
  const flags = []
  let unverified = 0
  for (const c of claims) {
    if (c.kind === 'jump' && times.size) {
      const val = Number(c.value)
      if (Number.isFinite(val) && !times.has(val) && ![...times].some(t => Math.abs(val - t) < 1e-6)) {
        if (!c.ok) {
          unverified += 1
          flags.push(`jump:${c.value} outside cursor window`)
        }
      }
    } else if (c.kind === 'task' && !c.ok) {
      unverified += 1
      flags.push(`unknown task ${c.value}`)
    } else if (!c.ok) {
      unverified += 1
      flags.push(String(c.detail || c.kind))
    }
  }
  const low = String(text || '').toLowerCase()
  if (!allowEstimates) {
    if ((low.includes('what_if') || low.includes('optimize_experiment'))
      && !low.includes('estimate') && !low.includes('heuristic')) {
      flags.push('simulator result not labelled as an estimate')
      unverified += 1
    }
  }
  const ok = unverified === 0
  return {
    ok,
    claims,
    unverified,
    flags,
    message: ok
      ? 'All extracted claims match trace scope'
      : `${unverified} claim(s) could not be verified against trace data`,
  }
}

export function interpretInvestigationQuery(question, {
  findings = [], cursorLo = null, cursorHi = null,
} = {}) {
  const q = String(question || '').trim()
  const blob = q.toLowerCase()
  const items = (findings || []).filter(f => f && typeof f === 'object')
  let kind = 'diagnose'
  let scopes = ['execution', 'blocking']
  if (['compar', 'regress', 'vs ', 'versus', 'before', 'after'].some(w => blob.includes(w))) {
    kind = 'compare'
    scopes = ['execution', 'blocking', 'migrations', 'tick']
  } else if (['optimi', 'faster', 'improve', 'what-if', 'what if', 'pin'].some(w => blob.includes(w))) {
    kind = 'optimize'
    scopes = ['migrations', 'blocking', 'execution']
  } else if (['report', 'write-up', 'summary for'].some(w => blob.includes(w))) {
    kind = 'report'
    scopes = ['findings']
  } else if (['why', 'cause', 'root', 'investigat', 'slow'].some(w => blob.includes(w))) {
    kind = 'diagnose'
    scopes = ['execution', 'blocking', 'migrations', 'priority inheritance']
  } else if (['what', 'explain', 'triage'].some(w => blob.includes(w))) {
    kind = 'quick'
    scopes = ['findings']
  }
  if ((blob.includes('migrat') || blob.includes('thrash')) && !scopes.includes('migrations')) {
    scopes.push('migrations')
  }
  if ((blob.includes('mutex') || blob.includes('lock') || blob.includes('invert'))
    && !scopes.includes('priority inheritance')) {
    scopes.push('priority inheritance')
  }
  let focus = items[0] || null
  if (items.length) {
    for (const f of items) {
      const title = String(f.title || '').toLowerCase()
      const task = String(f.task || '').toLowerCase()
      if (title && blob.includes(title)) { focus = f; break }
      if (task && blob.includes(task)) { focus = f; break }
    }
  }
  const window = (cursorLo != null && cursorHi != null) ? { lo: cursorLo, hi: cursorHi } : null
  const mode = INVESTIGATION_MODES.includes(kind) ? kind : 'diagnose'
  return {
    ok: true,
    interpreted_question: q || 'Investigate the main performance problem',
    kind,
    mode,
    scope: scopes,
    finding_id: String((focus || {}).id || ''),
    task: String((focus || {}).task || ''),
    cursor_window: window,
    suggested_tools: investigationModePlan(mode).tools || [],
    message: `Interpreted as ${kind} investigation`,
  }
}

export function explainFindingPayload(finding, {
  level = 'technical', hypotheses = [],
} = {}) {
  let lv = String(level || 'technical').trim().toLowerCase()
  if (!EXPLAIN_LEVELS.includes(lv)) lv = 'technical'
  if (!finding || typeof finding !== 'object') {
    return { ok: false, message: 'No finding selected', level: lv }
  }
  const title = String(finding.title || finding.id || 'Finding')
  const text = String(finding.text || '')
  const sev = String(finding.severity || 'info')
  const task = String(finding.task || '')
  const hyps = enrichHypotheses(hypotheses || [], { evidence: finding.evidence || [] })
  const quick = `${sev.toUpperCase()}: ${title}.` + (task ? ` Focus task ${task}.` : '')
  const technical = (
    `${title} (${sev}). ${text} `
    + 'Confirm the named Statistics section, then click Max / a scatter '
    + 'point to seek the timeline.'
  ).trim()
  let deep = technical
  if (hyps.length) {
    const names = hyps.slice(0, 4).map(h => `${h.hypothesis} [${h.status}]`).join('; ')
    deep = `${technical} Leading hypotheses: ${names}. `
      + 'Call investigate → correlate_events → find_critical_path → '
      + 'build_task_dependency_graph → analyze_temporal_causality → '
      + 'rank_root_causes → challenge_conclusion, '
      + 'then verify jump:TIME inside the cursor window.'
  }
  const body = { quick, technical, deep }[lv]
  return {
    ok: true,
    message: `${lv} explanation of ${finding.id || title}`,
    level: lv,
    finding: {
      id: finding.id, severity: sev, title, text, task,
      evidence: [...(finding.evidence || [])],
    },
    hypotheses: hyps,
    explanation: body,
    levels: { quick, technical, deep },
  }
}

export function investigationModePlan(mode = 'diagnose') {
  let want = String(mode || 'diagnose').trim().toLowerCase()
  if (!INVESTIGATION_MODES.includes(want)) want = 'diagnose'
  const plans = {
    quick: {
      goal: 'Find the most likely problem',
      tools: ['detect_anomalies', 'investigate'],
      template: 'triage',
    },
    diagnose: {
      goal: 'Find cause → gather evidence → verify',
      tools: [
        'investigate', 'correlate_events', 'find_critical_path',
        'build_task_dependency_graph', 'analyze_temporal_causality',
        'rank_root_causes', 'challenge_conclusion',
      ],
      template: 'investigate',
    },
    compare: {
      goal: 'Explain why A differs from B',
      tools: ['compare_performance', 'regression_explain'],
      template: 'compare',
    },
    optimize: {
      goal: 'Find cause → propose experiments → rank them',
      tools: ['investigate', 'what_if', 'optimize_experiment', 'recommend_experiments'],
      template: 'optimize',
    },
    report: {
      goal: 'Turn confirmed findings into an engineering report',
      tools: ['generate_report', 'export_report'],
      template: 'diagnostic_report',
    },
  }
  return { ...plans[want], mode: want, ok: true }
}

export const INVESTIGATION_MODE_LABELS = {
  quick: 'Quick',
  diagnose: 'Diagnose',
  compare: 'Compare',
  optimize: 'Optimize',
  report: 'Report',
}

export function investigationModePrompt(mode = 'diagnose') {
  const plan = investigationModePlan(mode)
  const listed = (plan.tools || []).filter(Boolean).join(' → ')
  const label = INVESTIGATION_MODE_LABELS[plan.mode] || plan.mode
  return (
    `${plan.goal || label}. Call these tools in order: ${listed}. `
    + 'After each tool, update hypotheses with manage_hypotheses when the '
    + 'status changes. Finish with a verdict, jump:TIME evidence, '
    + 'what would disprove this, confidence, and one next check.'
  )
}

export function parseUserInvestigationTemplates(raw) {
  let items = raw
  if (!Array.isArray(raw)) {
    try {
      items = JSON.parse(String(raw || '') || '[]')
    } catch {
      return []
    }
  }
  if (!Array.isArray(items)) return []
  const out = []
  items.forEach((it, i) => {
    if (!it || typeof it !== 'object') return
    const label = String(it.label || '').trim()
    const steps = (it.steps || []).map(s => String(s).trim()).filter(Boolean)
    if (!label || !steps.length) return
    let tid = String(it.id || '').trim()
    if (!tid) {
      tid = label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || `user_${i + 1}`
    }
    out.push({ id: tid, label, steps, user: true })
  })
  return out
}

export function dumpUserInvestigationTemplates(items = []) {
  const rows = []
  for (const it of items || []) {
    if (!it || typeof it !== 'object') continue
    const label = String(it.label || '').trim()
    const steps = (it.steps || []).map(s => String(s).trim()).filter(Boolean)
    if (!label || !steps.length) continue
    const tid = String(it.id || '').trim()
      || label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
    rows.push({ id: tid, label, steps })
  }
  return JSON.stringify(rows)
}

export function newUserInvestigationTemplate(label, steps = []) {
  const name = String(label || '').trim() || 'My Investigation'
  let seq = (steps || []).map(s => String(s).trim()).filter(Boolean)
  if (!seq.length) seq = [...(investigationModePlan('diagnose').tools || ['investigate'])]
  const tid = name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'user'
  return { id: tid, label: name, steps: seq, user: true }
}

export const VALIDATE_EXPERIMENT_PROMPT =
  'Did this before/after capture validate the experiment? Call validate_experiment. Omit actual — the host fills percents from the last Trace Compare (Scope to cursors honored). If expected deltas are known from what_if or optimize_experiment, pass them as expected; otherwise omit expected. Then report VALIDATED, PARTIALLY VALIDATED, or DISPROVED with supporting evidence and one next check.'

export function validateExperiment(expected = {}, actual = {}) {
  const exp = expected && typeof expected === 'object' ? expected : {}
  const act = actual && typeof actual === 'object' ? actual : {}
  const rows = []
  let matched = 0
  let disagreed = 0
  const keys = [...new Set([...Object.keys(exp), ...Object.keys(act)])].sort()
  for (const key of keys) {
    const e = exp[key]
    const a = act[key]
    const eN = e == null || e === '' ? null : Number(e)
    const aN = a == null || a === '' ? null : Number(a)
    const eOk = eN != null && Number.isFinite(eN)
    const aOk = aN != null && Number.isFinite(aN)
    let status = 'missing'
    if (!eOk && !aOk) status = 'missing'
    else if (!eOk) status = 'unspecified'
    else if (!aOk) status = 'unmeasured'
    else {
      const sameDir = (eN === 0 && Math.abs(aN) < 5) || (eN * aN > 0)
        || (Math.abs(eN) < 5 && Math.abs(aN) < 8)
      const close = Math.abs(aN - eN) <= Math.max(10, Math.abs(eN) * 0.5)
      if (sameDir && close) { status = 'validated'; matched += 1 }
      else if (sameDir) { status = 'partial'; matched += 1 }
      else { status = 'disproved'; disagreed += 1 }
    }
    rows.push({
      metric: String(key),
      expected: eOk ? eN : null,
      actual: aOk ? aN : null,
      status,
    })
  }
  let result = 'INCONCLUSIVE'
  if (!rows.length) result = 'INCONCLUSIVE'
  else if (disagreed && matched) result = 'PARTIALLY VALIDATED'
  else if (disagreed) result = 'DISPROVED'
  else if (matched) result = 'VALIDATED'
  return {
    ok: true, result, rows, matched, disagreed,
    message: `Experiment ${result}`,
  }
}

export function recordConfidenceStep(history = [], {
  toolName = '', score = null, band = '', note = '',
} = {}) {
  const out = (history || []).filter(s => s && typeof s === 'object').map(s => ({ ...s }))
  const entry = { tool: String(toolName || '').trim(), note: String(note || '').trim() }
  if (score != null) {
    entry.score = Math.max(0, Math.min(100, safeInt(score)))
    entry.band = band || evidenceQualityBand(score)
  } else if (band) {
    entry.band = band
  }
  out.push(entry)
  return out
}

export function formatConfidenceEvolution(history = []) {
  const lines = []
  ;(history || []).forEach((step, i) => {
    if (!step || typeof step !== 'object') return
    const tool = String(step.tool || `step ${i + 1}`)
    const prefix = i === 0 ? 'Initial' : `After ${tool}`
    const band = String(step.band || '')
    const extra = step.score != null ? ` ${step.score}%` : ''
    const note = String(step.note || '')
    let label = `${prefix}: ${band}${extra}`.trim()
    if (note) label += ` — ${note}`
    lines.push(label)
  })
  return lines.join('\n')
}

export function toolCallReason(toolName, finding = null) {
  const name = String(toolName || '').trim()
  const base = TOOL_REASONS[name] || `Run ${name} as part of the investigation plan`
  const blob = findingBlob(finding)
  if (blob) {
    const title = String((finding || {}).title || '').trim()
    if (title) return `${base}. Finding: ${title}.`
  }
  return base
}

export const AI_SPLIT_BOTTOM_DEFAULT = 80
export const AI_SPLIT_BOTTOM_MIN = 64
export const AI_SPLIT_BOTTOM_MAX = 400

export function clampAiSplitBottom(raw) {
  const n = Number.parseInt(raw, 10)
  if (!Number.isFinite(n) || n <= 0) return AI_SPLIT_BOTTOM_DEFAULT
  return Math.max(AI_SPLIT_BOTTOM_MIN, Math.min(AI_SPLIT_BOTTOM_MAX, n))
}

export function emptyCostMeter() {
  return {
    prompt_tokens: 0,
    completion_tokens: 0,
    total_tokens: 0,
    tool_calls: 0,
    trace_queries: 0,
    model_time_s: 0,
    estimated_usd: 0,
  }
}

export function accumulateCost(meter = null, {
  promptTokens = 0, completionTokens = 0, toolCalls = 0,
  traceQueries = 0, modelTimeS = 0, usdPer1k = 0,
} = {}) {
  const out = { ...(meter || emptyCostMeter()) }
  const pt = Math.max(0, safeInt(promptTokens))
  const ct = Math.max(0, safeInt(completionTokens))
  out.prompt_tokens = safeInt(out.prompt_tokens) + pt
  out.completion_tokens = safeInt(out.completion_tokens) + ct
  out.total_tokens = out.prompt_tokens + out.completion_tokens
  out.tool_calls = safeInt(out.tool_calls) + Math.max(0, safeInt(toolCalls))
  out.trace_queries = safeInt(out.trace_queries) + Math.max(0, safeInt(traceQueries))
  const prevT = Number(out.model_time_s || 0)
  const addT = Math.max(0, Number(modelTimeS || 0))
  out.model_time_s = Math.round((prevT + addT) * 1000) / 1000
  const added = (pt + ct) / 1000.0 * Math.max(0, Number(usdPer1k || 0))
  out.estimated_usd = Math.round((Number(out.estimated_usd || 0) + added) * 1e6) / 1e6
  return out
}

export function formatCostMeter(meter = null) {
  const m = meter && typeof meter === 'object' ? meter : emptyCostMeter()
  const usd = Number(m.estimated_usd || 0)
  const usdS = usd ? `$${usd.toFixed(3)}` : '—'
  return `Context ${m.total_tokens || 0} tokens · `
    + `Tool calls ${m.tool_calls || 0} · `
    + `Trace queries ${m.trace_queries || 0} · `
    + `Model time ${m.model_time_s || 0}s · `
    + `Est. ${usdS}`
}

function formatTokenCount(n) {
  const count = Number(n || 0)
  if (!Number.isFinite(count) || count < 1000) return String(Math.max(0, Math.trunc(count) || 0))
  return `${(count / 1000).toFixed(1).replace(/\.0$/, '')}k`
}

export function formatCostStatus(meter = null) {
  const m = meter && typeof meter === 'object' ? meter : emptyCostMeter()
  const tokens = Number(m.total_tokens || 0)
  const tools = Number(m.tool_calls || 0)
  const timeS = Number(m.model_time_s || 0)
  const usd = Number(m.estimated_usd || 0)
  const parts = [
    `${formatTokenCount(tokens)} tok`,
    `${Number.isFinite(tools) ? Math.max(0, Math.trunc(tools) || 0) : 0} tools`,
    `${Number.isFinite(timeS) && timeS ? timeS : 0}s`,
  ]
  if (usd) parts.push(`$${usd.toFixed(3)}`)
  return parts.join(' · ')
}

export function costMeterActive(meter = null) {
  const m = meter && typeof meter === 'object' ? meter : emptyCostMeter()
  const tokens = Number(m.total_tokens || 0)
  const tools = Number(m.tool_calls || 0)
  const timeS = Number(m.model_time_s || 0)
  const usd = Number(m.estimated_usd || 0)
  return tokens > 0 || tools > 0 || timeS > 0 || usd > 0
}

export function statusWithCost(message, meter = null) {
  const text = String(message || '').trim()
  if (!costMeterActive(meter)) return text
  const cost = formatCostStatus(meter)
  return text ? `${text} · ${cost}` : cost
}

export function chatUsageFromResponse(body) {
  const usage = body && typeof body === 'object' ? body.usage : null
  if (!usage || typeof usage !== 'object') {
    return { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 }
  }
  const pt = safeInt(usage.prompt_tokens || usage.prompt_token_count || 0)
  const ct = safeInt(
    usage.completion_tokens
    || usage.completion_token_count
    || usage.candidates_token_count
    || 0,
  )
  const tot = safeInt(usage.total_tokens || (pt + ct))
  return { prompt_tokens: pt, completion_tokens: ct, total_tokens: tot }
}

export function formatPrivacyChip(priv = null) {
  const level = String((priv || {}).level || 'local')
  return ({
    local: '🟢 Local',
    cloud_safe: '🟡 Cloud',
    sensitive: '🔴 Sensitive',
  })[level] || level.replace(/_/g, ' ')
}

export function investigationTemplatePrompt(template = null) {
  const tpl = template && typeof template === 'object' ? template : {}
  const label = String(tpl.label || 'Investigation')
  const steps = (tpl.steps || []).map(s => String(s)).filter(Boolean)
  const listed = steps.length ? steps.join(' → ') : 'investigate'
  return `Run the ${label}. Call these tools in order: ${listed}. `
    + 'After each tool, update hypotheses with manage_hypotheses when the '
    + 'status changes. Finish with a verdict, jump:TIME evidence, '
    + 'what would disprove this, confidence, and one next check.'
}

export function inferModelCapabilities(modelName, { endpointIsLocal = true } = {}) {
  const name = String(modelName || '').trim().toLowerCase()
  const cloud = (!endpointIsLocal) || [
    'gpt-', 'gemini', 'claude', 'kimi', 'moonshot', 'deepseek', 'grok', 'o1', 'o3',
  ].some(k => name.includes(k))
  const small = /(^|[^\d])([1-3]b)\b/.test(name) || name.includes('mini') || name.includes('phi')
  const largeLocal = /([7-9]b|\d{2,}b)\b/.test(name)
  const toolCalling = (cloud || largeLocal) ? 'yes' : (small ? 'partial' : 'unknown')
  const chaining = (cloud || largeLocal) ? 'yes' : 'partial'
  const longCtx = cloud ? 'yes' : 'partial'
  const reasoning = cloud ? 'yes' : 'partial'
  let recommended = ''
  if (small) recommended = 'qwen2.5:7b (or larger) for Investigation'
  return {
    ok: true,
    model: String(modelName || '').trim(),
    chat: 'yes',
    structured_output: (cloud || largeLocal) ? 'yes' : 'partial',
    tool_calling: toolCalling,
    multi_tool_chaining: chaining,
    long_context: longCtx,
    complex_reasoning: reasoning,
    recommended,
    source: 'heuristic',
  }
}

export function classifyTracePrivacy({
  endpointIsLocal = true, redactTaskNames = false, sensitive = false,
} = {}) {
  let level
  let cloudOk
  let note
  if (sensitive) {
    level = 'sensitive'
    cloudOk = false
    note = 'Cloud AI disabled — treat this trace as confidential'
  } else if (endpointIsLocal) {
    level = 'local'
    cloudOk = true
    note = 'Raw trace and Findings stay on this machine'
  } else if (redactTaskNames) {
    level = 'cloud_safe'
    cloudOk = true
    note = 'Task names anonymized; Findings still leave the machine'
  } else {
    level = 'cloud_safe'
    cloudOk = true
    note = 'Findings / metrics are sent to the configured cloud endpoint'
  }
  return {
    level,
    cloud_ok: cloudOk,
    endpoint_is_local: !!endpointIsLocal,
    redact_task_names: !!redactTaskNames,
    sensitive: !!sensitive,
    note,
  }
}

export function anonymizeTaskName(name, mapping = {}) {
  const src = String(name || '').trim()
  const mp = { ...(mapping || {}) }
  if (!src) return { alias: src, mapping: mp }
  if (src in mp) return { alias: mp[src], mapping: mp }
  const alias = `Task-${Object.keys(mp).length + 1}`
  mp[src] = alias
  return { alias, mapping: mp }
}

export function extractTaskNamesFromText(text) {
  const seen = []
  const re = new RegExp(TASK_NAME_RE.source, 'g')
  let m
  const src = String(text || '')
  while ((m = re.exec(src)) !== null) {
    if (!seen.includes(m[1])) seen.push(m[1])
  }
  return seen
}

export function anonymizeText(text, taskNames = null, mapping = {}) {
  let src = String(text || '')
  let mp = { ...(mapping || {}) }
  let names = (taskNames || []).map(n => String(n || '').trim()).filter(Boolean)
  if (!names.length) names = extractTaskNamesFromText(src)
  names = [...new Set(names)].sort((a, b) => b.length - a.length)
  for (const name of names) {
    const { alias, mapping: next } = anonymizeTaskName(name, mp)
    mp = next
    if (name && alias && src.includes(name)) src = src.split(name).join(alias)
  }
  return { text: src, mapping: mp }
}

export function applyCloudPrivacy(findingsText = '', query = '', {
  taskNames = null,
  endpointIsLocal = true,
  redactTaskNames = false,
  sensitive = false,
} = {}) {
  const privacy = classifyTracePrivacy({
    endpointIsLocal, redactTaskNames, sensitive,
  })
  const blocked = !!(sensitive && !endpointIsLocal)
  let text = String(findingsText || '')
  let q = String(query || '')
  let mapping = {}
  if (!endpointIsLocal && !blocked) {
    text = sanitizeAnnotationsText(text)
    q = sanitizeAnnotationsText(q)
  }
  if (redactTaskNames && !endpointIsLocal && !blocked) {
    let names = (taskNames || []).map(n => String(n || '').trim()).filter(Boolean)
    if (!names.length) names = extractTaskNamesFromText(`${text}\n${q}`)
    const a = anonymizeText(text, names, mapping)
    text = a.text
    mapping = a.mapping
    const b = anonymizeText(q, names, mapping)
    q = b.text
    mapping = b.mapping
  }
  return {
    ok: !blocked,
    blocked,
    findings_text: text,
    query: q,
    mapping,
    privacy,
    note: blocked
      ? 'Cloud AI disabled — treat this trace as confidential'
      : (privacy.note || ''),
  }
}

export function toggleInterpretedScope(interpreted = null, key = '', enabled = null) {
  const out = interpreted && typeof interpreted === 'object' ? { ...interpreted } : {}
  const scopes = [...(out.scope || [])].map(s => String(s)).filter(Boolean)
  const k = String(key || '').trim()
  if (k) {
    const on = enabled == null ? !scopes.includes(k) : !!enabled
    if (on && !scopes.includes(k)) scopes.push(k)
    if (!on) {
      out.scope = scopes.filter(s => s !== k)
      return out
    }
    out.scope = scopes
  }
  return out
}

export function interpretedRunPrompt(interpreted = null) {
  const data = interpreted && typeof interpreted === 'object' ? interpreted : {}
  const question = String(data.interpreted_question || data.question || '').trim()
    || 'Investigate the main performance problem'
  const mode = String(data.mode || data.kind || 'diagnose')
  const scopes = [...(data.scope || [])].map(s => String(s)).filter(Boolean)
  const scopeBit = scopes.length ? scopes.join(', ') : 'execution, blocking'
  const fid = String(data.finding_id || '').trim()
  const extra = fid ? ` finding_id=${fid}.` : ''
  return (
    `${question}\n\nInterpreted as ${mode}. `
    + `Investigation scope: ${scopeBit}.${extra} `
    + 'Call interpret_query only if the question is still ambiguous, '
    + 'then investigate and verify jump:TIME evidence.'
  )
}

export function formatExperimentVerdict(result = null) {
  const raw = result && typeof result === 'object'
    ? (result.result || result.verdict || '')
    : result
  const key = String(raw || '').trim().toUpperCase()
  return {
    VALIDATED: 'Hypothesis validated',
    DISPROVED: 'Hypothesis disproved',
    'PARTIALLY VALIDATED': 'Hypothesis partially validated',
  }[key] || 'Inconclusive'
}

export function applyExperimentToHypotheses(hypotheses = [], result = null) {
  const raw = result && typeof result === 'object' ? result.result : result
  const key = String(raw || '').trim().toUpperCase()
  const status = key === 'VALIDATED' ? 'supported' : key === 'DISPROVED' ? 'rejected' : ''
  return (hypotheses || []).filter(h => h && typeof h === 'object').map((h) => {
    const item = { ...h }
    const cur = String(item.status || '').toLowerCase()
    if (status && ['', 'possible', 'need_evidence', 'needs_evidence', 'untested'].includes(cur)) {
      item.status = status
    }
    return item
  })
}

export function parseUserHistoricalKnowledge(raw) {
  let items = []
  if (Array.isArray(raw)) items = raw
  else {
    const text = String(raw || '').trim()
    if (!text) return []
    try {
      const parsed = JSON.parse(text)
      items = Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }
  const out = []
  for (const it of items) {
    if (!it || typeof it !== 'object') continue
    const task = String(it.task || '').trim()
    const issue = String(it.issue || it.previous_issue || it.title || '').trim()
    if (!(task || issue)) continue
    out.push({
      task,
      issue,
      fix: String(it.fix || it.known_fix || '').trim(),
      build: String(it.build || it.last_occurrence || '').trim(),
      keywords: [...(it.keywords || [])],
      metrics: metricsFromMapping(it.metrics && typeof it.metrics === 'object' ? it.metrics : it),
    })
  }
  return out
}

export function dumpUserHistoricalKnowledge(items = []) {
  return JSON.stringify(parseUserHistoricalKnowledge(items))
}

export function newUserHistoricalEntry(finding = null, extras = null) {
  const f = finding && typeof finding === 'object' ? finding : {}
  const extra = extras && typeof extras === 'object' ? extras : {}
  const task = String(extra.task || f.task || '').trim()
  const issue = String(extra.issue || extra.title || f.title || '').trim() || 'Saved finding'
  const metrics = metricsFromMapping(extra.metrics && typeof extra.metrics === 'object' ? extra.metrics : extra)
  return {
    task,
    issue,
    fix: String(extra.fix || '').trim(),
    build: String(extra.build || '').trim(),
    keywords: issue.toLowerCase().split(/\W+/).filter(w => w.length > 3).slice(0, 6),
    metrics: Object.keys(metrics).length ? metrics : metricsFromMapping(f),
  }
}

const HISTORICAL_METRIC_KEYS = ['migrations', 'migration_rate', 'blocking', 'wcet']

function metricsFromMapping(src) {
  const data = src && typeof src === 'object' ? src : {}
  const out = {}
  for (const key of HISTORICAL_METRIC_KEYS) {
    if (data[key] == null) continue
    const n = Number(data[key])
    if (Number.isFinite(n)) out[key] = n
  }
  return out
}

export function rateFlagsFromMetrics(current = null, typical = null) {
  const cur = metricsFromMapping(current)
  const hist = metricsFromMapping(typical)
  const flags = []
  for (const key of HISTORICAL_METRIC_KEYS) {
    if (!(key in cur) || !(key in hist) || hist[key] === 0) continue
    const ratio = cur[key] / hist[key]
    if (ratio >= 2.0) {
      flags.push(`${key} ${cur[key]} vs typical ${hist[key]} (×${ratio.toFixed(1)})`)
    }
  }
  return flags
}

export const CAPABILITY_CHAT_PROBE = 'Reply with JSON only: {"ok":true}'

export const CAPABILITY_PROBE_TOOL = {
  type: 'function',
  function: {
    name: 'btf_ping',
    description: 'Capability probe. Call this once if you support tools.',
    parameters: { type: 'object', properties: {} },
  },
}

export const CAPABILITY_PROBE_TOOL_PONG = {
  type: 'function',
  function: {
    name: 'btf_pong',
    description: 'Second capability probe. Call after btf_ping if you can chain tools.',
    parameters: { type: 'object', properties: {} },
  },
}

export function capabilityProbeBody(model) {
  return {
    model: String(model || '').trim(),
    stream: false,
    messages: [{
      role: 'user',
      content: 'If you can call tools, call btf_ping then btf_pong. Otherwise reply PONG.',
    }],
    tools: [CAPABILITY_PROBE_TOOL, CAPABILITY_PROBE_TOOL_PONG],
    max_tokens: 64,
  }
}

export function structuredOutputFromText(text) {
  let src = String(text || '').trim()
  if (src.startsWith('```')) {
    src = src.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '')
  }
  const tryParse = (s) => {
    try {
      const obj = JSON.parse(s)
      return !!obj && typeof obj === 'object' && !Array.isArray(obj)
    } catch {
      return false
    }
  }
  if (tryParse(src)) return true
  const m = src.match(/\{[^{}]+\}/)
  return !!(m && tryParse(m[0]))
}

export function countToolCalls(body) {
  if (!body || typeof body !== 'object') return null
  const choices = body.choices
  if (!Array.isArray(choices) || !choices.length) return null
  const msg = choices[0] && typeof choices[0] === 'object' ? choices[0].message : null
  if (!msg || typeof msg !== 'object') return null
  const calls = msg.tool_calls
  let n = Array.isArray(calls) ? calls.length : 0
  if (msg.function_call) n = Math.max(n, 1)
  if (n) return n
  if (String(msg.content || '').trim()) return 0
  return null
}

export function mergeLiveCapability(cap = null, {
  chatText = '', toolBody = null, toolOk = null,
} = {}) {
  const out = cap && typeof cap === 'object' ? { ...cap } : {}
  if (structuredOutputFromText(chatText)) {
    out.structured_output = 'yes'
    out.source = 'live'
  } else if (String(chatText || '').trim()) {
    out.structured_output = 'no'
    out.source = 'live'
  }
  const n = toolBody != null ? countToolCalls(toolBody) : null
  if (toolOk === true || (n != null && n >= 1)) {
    out.tool_calling = 'yes'
    out.multi_tool_chaining = (n || 0) >= 2 ? 'yes' : 'partial'
    out.source = 'live'
  } else if (toolOk === false || n === 0) {
    out.tool_calling = 'no'
    out.multi_tool_chaining = 'no'
    out.source = 'live'
  }
  return out
}

export function toolCallingFromChatResponse(body) {
  if (!body || typeof body !== 'object') return null
  const choices = body.choices
  if (!Array.isArray(choices) || !choices.length) return null
  const msg = choices[0] && typeof choices[0] === 'object' ? choices[0].message : null
  if (!msg || typeof msg !== 'object') return null
  if (msg.tool_calls || msg.function_call) return true
  if (String(msg.content || '').trim()) return false
  return null
}

export function builtinInvestigationTemplates() {
  return [
    {
      id: 'cpu_latency',
      label: 'CPU Latency Investigation',
      steps: [
        'detect_anomalies', 'investigate', 'query_raw_metric',
        'correlate_events', 'find_critical_path',
        'build_task_dependency_graph', 'analyze_temporal_causality',
        'decompose_response_time', 'rank_root_causes', 'challenge_conclusion',
        'detect_priority_inversion',
        'generate_report',
      ],
    },
    {
      id: 'migration_thrash',
      label: 'Migration Thrash Investigation',
      steps: [
        'detect_anomalies', 'investigate', 'correlate_events',
        'query_raw_metric', 'what_if',
      ],
    },
    {
      id: 'regression',
      label: 'A/B Regression Investigation',
      steps: [
        'compare_performance', 'regression_explain',
        'validate_experiment', 'generate_report',
      ],
    },
  ]
}

export function matchHistoricalKnowledge(task, { current = {}, history = {} } = {}) {
  const name = String(task || '').trim()
  const cur = current && typeof current === 'object' ? current : {}
  const hist = history && typeof history === 'object' ? history : {}
  let prev = hist[name] && typeof hist[name] === 'object' ? hist[name] : null
  if (!prev && hist.tasks && typeof hist.tasks === 'object') {
    prev = hist.tasks[name] && typeof hist.tasks[name] === 'object' ? hist.tasks[name] : {}
  }
  if (!prev || typeof prev !== 'object') prev = {}
  const flags = rateFlagsFromMetrics(cur, prev)
  const issue = String(prev.issue || prev.previous_issue || '')
  const fix = String(prev.fix || prev.known_fix || '')
  const build = String(prev.build || prev.last_occurrence || '')
  const resembles = Boolean(issue) && flags.length > 0
  return {
    ok: true,
    task: name,
    previous_issue: issue,
    known_fix: fix,
    last_occurrence: build,
    flags,
    typical: metricsFromMapping(prev),
    current: metricsFromMapping(cur),
    resembles_previous: resembles,
    message: resembles
      ? `This resembles the ${issue} issue${build ? ` seen in ${build}` : ''}`
      : (Object.keys(prev).length ? 'Within historical range' : 'No historical match'),
  }
}

export function builtinHistoricalCatalog() {
  return [
    {
      keywords: ['thrash', 'migration', 'bounc'],
      issue: 'Migration thrashing',
      fix: 'Pin the task / set core affinity',
      build: 'typical',
    },
    {
      keywords: ['mutex', 'contention', 'blocking'],
      issue: 'Mutex contention',
      fix: 'Shorten the critical section or enable priority inheritance',
      build: 'typical',
    },
    {
      keywords: ['inversion', 'inherit'],
      issue: 'Priority inversion',
      fix: 'Priority inheritance or priority ceiling on the mutex',
      build: 'typical',
    },
    {
      keywords: ['imbalance', 'load balance'],
      issue: 'Load imbalance',
      fix: 'Rebalance placement or pin heavy tasks',
      build: 'typical',
    },
    {
      keywords: ['deadline', 'budget'],
      issue: 'Deadline miss',
      fix: 'Trim WCET or raise the budget / period',
      build: 'typical',
    },
  ]
}

export function historicalKnowledgeForFinding(finding = null, {
  history = {}, current = {}, userCatalog = [],
} = {}) {
  const f = finding && typeof finding === 'object' ? finding : {}
  const task = String(f.task || '')
  const blob = `${f.title || ''} ${f.text || ''} ${task}`.toLowerCase()
  for (const item of parseUserHistoricalKnowledge(userCatalog)) {
    const itemTask = String(item.task || '').trim()
    const keys = (item.keywords || []).map(k => String(k).toLowerCase()).filter(Boolean)
    if (
      (itemTask && itemTask.toLowerCase() === task.toLowerCase())
      || (keys.length && keys.some(k => blob.includes(k)))
      || (item.issue && blob.includes(String(item.issue).toLowerCase()))
    ) {
      const issue = String(item.issue || '')
      const fix = String(item.fix || '')
      const build = String(item.build || '')
      const typical = item.metrics && typeof item.metrics === 'object' ? item.metrics : {}
      const flags = rateFlagsFromMetrics(current, typical)
      return {
        ok: true,
        task: task || itemTask,
        previous_issue: issue,
        known_fix: fix,
        last_occurrence: build,
        flags,
        typical,
        current: metricsFromMapping(current),
        resembles_previous: true,
        source: 'user',
        message: `This resembles the ${issue} issue`
          + (build ? ` seen in ${build}` : '')
          + (fix ? ` — known fix: ${fix}` : ''),
      }
    }
  }
  const hit = matchHistoricalKnowledge(task, { current, history })
  if (hit.previous_issue || (hit.flags || []).length) return hit
  for (const item of builtinHistoricalCatalog()) {
    if ((item.keywords || []).some(k => blob.includes(k))) {
      const issue = String(item.issue || '')
      const fix = String(item.fix || '')
      const build = String(item.build || '')
      return {
        ok: true,
        task,
        previous_issue: issue,
        known_fix: fix,
        last_occurrence: build,
        flags: [],
        resembles_previous: true,
        source: 'catalog',
        message: `This resembles the ${issue} issue${fix ? ` — known fix: ${fix}` : ''}`,
      }
    }
  }
  return hit
}

export function buildInvestigationCase(investigateCtx = null, {
  question = '', trace = '', cursorLo = null, cursorHi = null,
  toolsRun = [], toolsExecuted = [], mode = 'diagnose', scoreData = null,
  finding: findingKw, hypotheses, alternatives, evidence: evidenceKw,
  conclusion = '', confidence = '', checks, plan,
} = {}) {
  const ctx = investigateCtx && typeof investigateCtx === 'object' ? { ...investigateCtx } : {}
  if (findingKw !== undefined) ctx.finding = findingKw
  if (hypotheses !== undefined) ctx.hypotheses = [...(hypotheses || [])]
  if (alternatives !== undefined) ctx.alternatives = [...(alternatives || [])]
  if (evidenceKw !== undefined) ctx.evidence = [...(evidenceKw || [])]
  if (checks !== undefined) ctx.checks = [...(checks || [])]
  if (plan !== undefined) ctx.plan = plan
  if (conclusion) ctx.conclusion = ctx.conclusion || conclusion
  const finding = ctx.finding && typeof ctx.finding === 'object' ? ctx.finding : {}
  const evidence = [
    ...((evidenceKw && evidenceKw.length ? evidenceKw : null)
      || finding.evidence
      || ctx.evidence
      || []),
  ]
  const hyps = enrichHypotheses(ctx.hypotheses || [], {
    evidence,
    alternatives: ctx.alternatives || [],
  })
  const graph = buildEvidenceGraph(Object.keys(finding).length ? finding : null, {
    evidence, hypotheses: hyps, chain: ctx.root_cause_chain || [],
  })
  const score = (scoreData && typeof scoreData === 'object')
    ? scoreData
    : (ctx.scoreData && typeof ctx.scoreData === 'object' ? ctx.scoreData
      : (ctx.score_data && typeof ctx.score_data === 'object' ? ctx.score_data : {}))
  const run = (toolsRun && toolsRun.length)
    ? toolsRun
    : (toolsExecuted && toolsExecuted.length)
      ? toolsExecuted
      : (ctx.toolsExecuted || ctx.tools_executed || ctx.suggested_tools || [])
  const quality = computeEvidenceQuality({
    score: score.score ?? ctx.evidence_score ?? 0,
    breakdown: score.breakdown || ctx.evidence_score_breakdown,
    evidence,
    alternatives: ctx.alternatives || [],
    checks: ctx.checks || [],
    evidenceChain: String(ctx.evidence_chain || ''),
  })
  const coverage = computeEvidenceCoverage({ evidence })
  const falsify = falsificationChecks(Object.keys(finding).length ? finding : null)
  if (evidence.length) {
    falsify.supporting = evidence
      .filter(e => e && typeof e === 'object')
      .slice(0, 8)
      .map(e => String(e.label || 'evidence') + (e.time != null ? ` jump:${e.time}` : ''))
  }
  const toolNames = []
  for (const t of run || []) {
    const n = t && typeof t === 'object' ? String(t.name || '').trim() : String(t || '').trim()
    if (n) toolNames.push(n)
  }
  const reasons = toolNames.map(n => ({ tool: n, reason: toolCallReason(n, finding) }))
  const caseObj = emptyInvestigationCase({
    question: question || String(ctx.message || ctx.question || ''),
    trace,
    cursorLo,
    cursorHi,
    tasks: finding.task ? [String(finding.task)] : [],
  })
  return {
    ...caseObj,
    suspected_findings: Object.keys(finding).length
      ? [finding]
      : [...(ctx.related_findings || [])],
    hypotheses: hyps,
    evidence,
    tools_executed: toolNames,
    tool_reasons: reasons,
    evidence_timeline: evidence
      .filter(e => e && typeof e === 'object' && e.time != null)
      .map(e => ({ time: e.time, label: e.label })),
    evidence_graph: graph,
    evidence_quality: quality,
    evidence_coverage: coverage,
    coverage,
    falsification: falsify,
    falsify,
    graph_mermaid: graph.mermaid || '',
    confidence: confidence || quality.confidence_label || 'Medium',
    confidence_history: recordConfidenceStep([], {
      toolName: 'investigate',
      score: quality.score,
      band: quality.band,
      note: 'Initial investigation context',
    }),
    conclusion: String(conclusion || ctx.conclusion || finding.title || ''),
    alternatives_rejected: (ctx.alternatives || []).filter(
      a => a && typeof a === 'object' && String(a.status || '').toLowerCase() === 'rejected',
    ),
    recommended_action: String(falsify.next_check || ''),
    mode: INVESTIGATION_MODES.includes(mode) ? mode : 'diagnose',
    plan: ctx.plan,
  }
}

export function updateCaseFromTool(caseObj, toolName, result = null) {
  const out = { ...(caseObj || emptyInvestigationCase()) }
  const name = String(toolName || '').trim()
  const tools = [...(out.tools_executed || [])]
  if (name && !tools.includes(name)) tools.push(name)
  out.tools_executed = tools
  const reasons = [...(out.tool_reasons || [])]
  let finding = null
  const suspected = out.suspected_findings || []
  if (suspected[0] && typeof suspected[0] === 'object') finding = suspected[0]
  reasons.push({ tool: name, reason: toolCallReason(name, finding) })
  out.tool_reasons = reasons
  let data = {}
  if (result && typeof result === 'object') {
    data = result.data && typeof result.data === 'object' ? result.data : result
  }
  const ev = [...(out.evidence || [])]
  for (const key of ['evidence', 'events', 'path']) {
    for (const item of data[key] || []) {
      if (item && typeof item === 'object') {
        ev.push({
          label: String(item.label || item.detail || item.kind || 'evidence'),
          time: item.time,
        })
      }
    }
  }
  out.evidence = ev
  let score = null
  if (typeof data.evidence_score === 'number') score = data.evidence_score
  out.confidence_history = recordConfidenceStep(out.confidence_history, {
    toolName: name,
    score,
    note: String((result || {}).message || '').slice(0, 160),
  })
  return out
}

export const BENCHMARK_METRIC_WEIGHTS = {
  finding: 0.20,
  evidence: 0.20,
  tool_use: 0.15,
  root_cause: 0.20,
  calibration: 0.10,
  safety: 0.15,
}

const NEGATION_RE = /\b(not|no|never|isn't|is not|without|reject)\b/
const METRIC_SEP_RE = /[\s/_-]+/g

/** Official Statistics page titles plus wording a model may use instead of × / slashes. */
export const STATS_UX_PAGE_ALIASES = {
  'timeline anomalies': ['timeline anomalies', 'timeline anomaly'],
  'worst events': ['worst events', 'worst event'],
  'period jitter': ['period jitter', 'period / jitter', 'period/jitter'],
  'task health': ['task health'],
  'task x core': ['task x core', 'task-core'],
  'waiter x owner': ['waiter x owner', 'waiter-owner'],
  'response time': ['response time', 'response-time'],
  'critical path': ['critical path', 'crit path'],
  'unified jitter': ['unified jitter'],
  'recurring patterns': ['recurring patterns', 'recurring pattern'],
  'preemption matrix': ['preemption matrix'],
  'mutex blocking': ['mutex blocking', 'mutex-blocking'],
  'core utilization over time': [
    'core utilization over time', 'core utilisation over time',
  ],
}

function normalizeMetricText(text) {
  return String(text || '').toLowerCase().replace(/×/g, 'x').replace(METRIC_SEP_RE, ' ').trim()
}

export function metricMentioned(blob, metric) {
  const raw = String(blob || '').toLowerCase()
  const want = String(metric || '').trim().toLowerCase()
  if (want && raw.includes(want)) return true
  const normBlob = normalizeMetricText(blob)
  const normWant = normalizeMetricText(metric)
  if (normWant && normBlob.includes(normWant)) return true
  for (const [key, needles] of Object.entries(STATS_UX_PAGE_ALIASES)) {
    const aliases = [key, ...needles]
    if (!aliases.some(a => normalizeMetricText(a) === normWant)) continue
    return needles.some(n => normBlob.includes(normalizeMetricText(n)) || raw.includes(n))
  }
  return false
}

export function blobHasPhrase(blob, phrase, allowNegation = true) {
  const text = String(blob || '').toLowerCase()
  const needle = String(phrase || '').trim().toLowerCase()
  if (!needle) return false
  const idx = text.indexOf(needle)
  if (idx < 0) return false
  if (allowNegation) {
    const window = text.slice(Math.max(0, idx - 20), idx)
    if (NEGATION_RE.test(window)) return false
  }
  return true
}

export function scoreAdversarialMetrics(expected = {}, {
  actualConclusion = '', tools = [], validation = null,
} = {}) {
  const exp = expected && typeof expected === 'object' ? expected : {}
  const conc = String(actualConclusion || '')
  const traps = (exp.trap_phrases || []).map(x => String(x)).filter(x => x.trim())
  const falseConfirmation = traps.some(p => blobHasPhrase(conc, p)) ? 100 : 0
  const causalHits = ['caused', 'because of', 'due to', 'causal']
    .some(p => blobHasPhrase(conc, p))
  const rootClass = String(exp.root_cause_class || '').toLowerCase()
  const noCausal = !!exp.no_causal || rootClass === 'no_causal' || rootClass === 'coincidence'
  const falseCausal = (noCausal && causalHits) ? 100 : (traps.length ? falseConfirmation : 0)
  const claims = ((validation && validation.claims) || []).filter(c => c && typeof c === 'object')
  const unsupported = claims.length
    ? Math.round(100 * claims.filter(c => !c.ok).length / claims.length)
    : 0
  const toolsL = (tools || []).map(t => String(t))
  const required = (exp.required_tools || []).map(t => String(t)).filter(Boolean)
  const low = conc.toLowerCase()
  const highConf = low.includes('confidence: high') || low.endsWith('high.')
  const missingRequired = required.length > 0 && !required.some(t => toolsL.includes(t))
  const premature = (
    (highConf && (falseConfirmation || missingRequired || !toolsL.length))
    || missingRequired
  ) ? 100 : 0
  return {
    false_causal_rate: falseCausal,
    false_confirmation_rate: falseConfirmation,
    unsupported_claim_rate: unsupported,
    premature_conclusion_rate: premature,
  }
}

export function scoreBenchmarkCase(expected, {
  actualFindingIds = [], actualTasks = [], actualTools = [],
  actualConclusion = '', validation = null, evidenceQuality = null,
} = {}) {
  const exp = expected && typeof expected === 'object' ? expected : {}
  const wantFindings = (exp.finding_types || []).map(x => String(x).toLowerCase())
  const gotFindings = (actualFindingIds || []).map(x => String(x).toLowerCase())
  const findingHits = wantFindings.filter(w => gotFindings.some(g => g.includes(w))).length
  const findingScore = wantFindings.length
    ? Math.round(100.0 * findingHits / wantFindings.length)
    : 100

  const wantTasks = (exp.tasks || []).map(x => String(x).toLowerCase())
  const gotTasks = (actualTasks || []).map(x => String(x).toLowerCase())
  const taskHits = wantTasks.filter(w => gotTasks.some(g => g.includes(w))).length
  let evidenceScore = wantTasks.length
    ? Math.round(100.0 * taskHits / wantTasks.length)
    : 100
  const ev = exp.evidence && typeof exp.evidence === 'object' ? exp.evidence : {}
  const wantMetrics = (ev.required_metrics || []).map(x => String(x).toLowerCase())
  if (wantMetrics.length) {
    const blob = String(actualConclusion || '')
    const metricHits = wantMetrics.filter(m => metricMentioned(blob, m)).length
    const metricScore = Math.round(100.0 * metricHits / wantMetrics.length)
    evidenceScore = wantTasks.length
      ? Math.round((evidenceScore + metricScore) / 2)
      : metricScore
  }

  const allowed = (exp.allowed_tools || []).map(x => String(x))
  const gotTools = (actualTools || []).map(x => String(x))
  let toolScore
  if (allowed.length) {
    const toolHits = gotTools.filter(t => allowed.includes(t)).length
    toolScore = Math.round(100.0 * toolHits / Math.max(allowed.length, 1))
    if (gotTools.length && toolHits === 0) toolScore = 0
    else if (gotTools.length) {
      toolScore = Math.max(toolScore, Math.round(100.0 * toolHits / gotTools.length))
    }
  } else {
    toolScore = gotTools.length ? 100 : 50
  }

  const wantClass = String(exp.root_cause_class || '').toLowerCase()
  const conc = String(actualConclusion || '').toLowerCase()
  const aliases = (exp.root_cause_aliases || []).map(x => String(x).toLowerCase()).filter(x => x.trim())
  let rootScore = 100
  if (wantClass || aliases.length) {
    const classHit = wantClass && (
      conc.includes(wantClass) || wantClass.split(/\s+/).some(w => conc.includes(w))
    )
    rootScore = (classHit || aliases.some(a => conc.includes(a))) ? 100 : 0
  }
  const adv = scoreAdversarialMetrics(exp, {
    actualConclusion, tools: actualTools, validation,
  })
  if (adv.false_confirmation_rate) rootScore = 0

  const band = String((evidenceQuality || {}).band || '')
  let cal = 80
  if (band === 'strong' || band === 'medium-high') cal = 90
  else if (band === 'medium') cal = 75
  else if (band === 'weak' || band === 'insufficient') cal = 55

  const val = validation && typeof validation === 'object' ? validation : {}
  let safety = val.ok !== false ? 100 : Math.max(0, 100 - 20 * (Number(val.unverified) || 1))
  const forbidden = exp.forbidden || {}
  if (forbidden.invented_task_names && (val.claims || []).some(
    c => c && c.kind === 'task' && !c.ok,
  )) {
    safety = Math.min(safety, 40)
  }

  const parts = {
    finding: findingScore,
    evidence: evidenceScore,
    tool_use: toolScore,
    root_cause: rootScore,
    calibration: cal,
    safety,
  }
    const overall = Math.round(Object.keys(parts).reduce(
    (s, k) => s + parts[k] * BENCHMARK_METRIC_WEIGHTS[k], 0,
  ))
  const extras = scoreInvestigationMetrics({
    expected: exp,
    actualConclusion,
    tools: actualTools,
    evidenceQuality,
    passed: rootScore >= 50 && findingScore >= 50,
    findingScore,
  })
  return { overall: Math.max(0, Math.min(100, overall)), parts, ...extras, ...adv }
}

export function formatBenchmarkScore(score) {
  const overall = safeInt((score || {}).overall)
  const filled = Math.max(0, Math.min(10, Math.round(overall / 10)))
  const bar = '█'.repeat(filled) + '░'.repeat(10 - filled)
  const parts = (score || {}).parts || {}
  const lines = ['Overall AI Diagnostic Score', `${bar} ${overall}`, '']
  const labels = {
    finding: 'Finding', evidence: 'Evidence', tool_use: 'Tool use',
    root_cause: 'Root cause', calibration: 'Calibration', safety: 'Safety / grounding',
  }
  for (const key of ['finding', 'evidence', 'tool_use', 'root_cause', 'calibration', 'safety']) {
    if (key in parts) {
      lines.push(`${labels[key].padEnd(20)} ${parts[key]}`)
    }
  }
  const extras = {
    evidence_efficiency: 'Evidence efficiency',
    investigation_cost: 'Investigation cost',
    false_confidence: 'False-confidence',
    falsification_quality: 'Falsification',
    scope_accuracy: 'Scope accuracy',
    stop_efficiency: 'Stop efficiency',
    false_causal_rate: 'False-causal rate',
    false_confirmation_rate: 'False-confirmation rate',
    unsupported_claim_rate: 'Unsupported-claim rate',
    premature_conclusion_rate: 'Premature-conclusion rate',
  }
  let shown = false
  for (const [key, label] of Object.entries(extras)) {
    if (score && key in score) {
      if (!shown) {
        lines.push('')
        shown = true
      }
      lines.push(`${label.padEnd(20)} ${score[key]}`)
    }
  }
  return lines.join('\n')
}

/** Alias used by the Evidence panel (same as computeEvidenceQuality). */
export function evidenceQualityFromScore(score, breakdown = [], extra = {}) {
  if (Array.isArray(breakdown)) {
    return computeEvidenceQuality({ score, breakdown, ...extra })
  }
  if (breakdown && typeof breakdown === 'object') {
    return computeEvidenceQuality({ score, ...breakdown })
  }
  return computeEvidenceQuality({ score, ...extra })
}

export function buildValidationCatalog({
  findingsText = '', evidence = [], tasks = [], metrics = null,
  cursorLo = null, cursorHi = null, toolTimes = [],
} = {}) {
  const knownTasks = (tasks || []).map(t => String(t)).filter(Boolean)
  const src = String(findingsText || '')
  TASK_NAME_RE.lastIndex = 0
  let m
  while ((m = TASK_NAME_RE.exec(src))) {
    if (!knownTasks.includes(m[1])) knownTasks.push(m[1])
  }
  const times = []
  for (const e of evidence || []) {
    if (e && typeof e === 'object' && e.time != null) {
      const n = Number(e.time)
      if (Number.isFinite(n)) times.push(n)
    }
  }
  for (const t of toolTimes || []) {
    const n = Number(t)
    if (Number.isFinite(n)) times.push(n)
  }
  let lo = cursorLo
  let hi = cursorHi
  lo = lo == null || lo === '' ? null : Number(lo)
  hi = hi == null || hi === '' ? null : Number(hi)
  if (!Number.isFinite(lo)) lo = null
  if (!Number.isFinite(hi)) hi = null
  return {
    tasks: knownTasks,
    metrics: [...(metrics || KNOWN_METRICS)].map(x => String(x)).sort(),
    times,
    cursor_lo: lo,
    cursor_hi: hi,
  }
}

export function inferModelCapability(modelName, {
  toolCallOk = null, chatOk = true, endpointIsLocal = true,
  chatText = '', toolBody = null,
} = {}) {
  const cap = inferModelCapabilities(modelName, { endpointIsLocal })
  cap.chat = chatOk ? 'yes' : 'no'
  if (toolCallOk === true) cap.tool_calling = 'yes'
  else if (toolCallOk === false) cap.tool_calling = 'partial'
  return mergeLiveCapability(cap, { chatText, toolBody, toolOk: toolCallOk })
}

export function formatCapabilityReport(cap = null) {
  if (!cap || typeof cap !== 'object') return ''
  const glyph = { yes: '✓', partial: '△', no: '✗', unknown: '?' }
  const g = (v) => glyph[String(v)] || String(v || '')
  const lines = [
    'Model capability',
    '',
    `${g(cap.chat)} Chat`,
    `${g(cap.structured_output)} Structured output`,
    `${g(cap.tool_calling)} Tool calling`,
    `${g(cap.multi_tool_chaining)} Multi-tool chaining`,
    `${g(cap.long_context)} Long context`,
    `${g(cap.complex_reasoning)} Complex reasoning`,
  ]
  const rec = String(cap.recommended || '').trim()
  if (rec) lines.push('', `Recommended: ${rec}`)
  return lines.join('\n')
}

export function formatBenchmarkReport(runId, rows = []) {
  const lines = [`AI Benchmark #${runId}`, '', `Cases: ${rows.length}`, '']
  for (const row of rows) {
    const name = String(row.id || '?')
    const score = row.overall
    const flag = row.error ? 'ERROR' : (row.pass ? 'PASS' : 'FAIL')
    lines.push(`  ${String(name).padEnd(24)} ${String(score).padStart(3)}  ${flag}`)
  }
  if (rows.length) {
    const avg = Math.round(rows.reduce((s, r) => s + (Number(r.overall) || 0), 0) / rows.length)
    lines.push('', `Overall ${avg}`)
  }
  return `${lines.join('\n')}\n`
}

export function classifyPrivacy({ cloud = false, redactNames = false, sensitive = false } = {}) {
  return classifyTracePrivacy({
    endpointIsLocal: !cloud,
    redactTaskNames: !!redactNames,
    sensitive: !!sensitive,
  })
}

export function interpretQuestion(text, extra = {}) {
  return interpretInvestigationQuery(text, extra)
}

export function runOfflineBenchmark(dataset, { failUnder = 0 } = {}) {
  const cases = Array.isArray(dataset)
    ? dataset
    : (dataset && Array.isArray(dataset.cases) ? dataset.cases : [])
  const rows = []
  for (const caseObj of cases) {
    if (!caseObj || typeof caseObj !== 'object') continue
    const expected = caseObj.expected && typeof caseObj.expected === 'object'
      ? caseObj.expected : caseObj
    const actual = caseObj.actual && typeof caseObj.actual === 'object'
      ? caseObj.actual : {}
    const response = String(actual.response || caseObj.response || '')
    const catalog = actual.catalog || caseObj.catalog || {}
    const report = validateAiResponse(response, {
      knownTasks: catalog.tasks,
      knownTimes: catalog.times,
      cursorLo: catalog.cursor_lo,
      cursorHi: catalog.cursor_hi,
    })
    let gotFindings = []
    if (expected.finding_types) {
      const blob = response.toLowerCase()
      gotFindings = expected.finding_types.filter(
        ft => blob.includes(String(ft).toLowerCase()),
      )
    }
    const scored = scoreBenchmarkCase(expected, {
      actualFindingIds: gotFindings,
      actualTasks: (report.claims || [])
        .filter(c => c && c.kind === 'task')
        .map(c => String(c.value)),
      actualTools: [...(actual.tools || caseObj.tools || [])],
      actualConclusion: response,
      validation: report,
    })
    const passFloor = Number(expected.pass_under || failUnder || 70)
    scored.id = caseObj.id || expected.id
    scored.pass = Number(scored.overall || 0) >= passFloor
      && Boolean(report.ok !== false || !(expected.forbidden || {}))
    const forbidden = expected.forbidden || {}
    if (forbidden.invented_task_names && !report.ok) {
      const invented = (report.claims || []).some(
        c => c && c.kind === 'task' && !c.ok,
      )
      if (invented) scored.pass = false
    }
    if (forbidden.out_of_scope_timestamps) {
      const oos = (report.claims || []).some(
        c => c && c.kind === 'jump' && !c.ok,
      )
      if (oos) scored.pass = false
    }
    if (failUnder && Number(scored.overall || 0) < Number(failUnder)) {
      scored.pass = false
    }
    scored.validation = report
    rows.push(scored)
  }
  const runId = new Date().toISOString().replace(/[-:TZ.]/g, '').slice(0, 14)
  const failed = rows.filter(r => !r.pass)
  return {
    run_id: runId,
    rows,
    failed,
    report: formatBenchmarkReport(runId, rows),
    ok: failed.length === 0,
  }
}

