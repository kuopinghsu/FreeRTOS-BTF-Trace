/**
 * Investigation plan, evidence chain, baselines, CI regression helpers.
 * Keep in sync with btf_viewer_pkg/ai_investigation.py.
 */

import {
  INVESTIGATION_SCOPE_OPTIONS,
  buildEvidenceGraph,
  buildInvestigationCase,
  computeEvidenceCoverage,
  computeEvidenceQuality,
  enrichHypotheses,
  evidenceQualityFromScore,
  falsificationChecks,
  formatConfidenceEvolution,
  formatCoverageCountLines,
  formatExperimentVerdict,
  formatQualityFlagLines,
  historicalKnowledgeForFinding,
  mermaidLabelWithTime,
} from './aiCase.js'

export const INVESTIGATION_PLAN_STEPS = [
  ['findings', 'Read Analysis Findings'],
  ['hypotheses', 'Rank hypotheses'],
  ['metrics', 'Query metrics / timeline'],
  ['narrow', 'Narrow cursors / zoom'],
  ['related', 'Inspect related tasks / sync'],
  ['validate', 'Validate root cause'],
  ['recommend', 'Recommend mitigation'],
]

const TOOL_STEP_MAP = {
  investigate: ['findings', 'hypotheses'],
  detect_anomalies: ['findings'],
  query_raw_metric: ['metrics'],
  search_timeline: ['metrics'],
  correlate_events: ['metrics', 'related'],
  find_critical_path: ['metrics', 'validate'],
  compare_performance: ['metrics', 'validate'],
  trigger_compare: ['metrics', 'related'],
  set_cursors: ['narrow'],
  zoom_to_range: ['narrow'],
  highlight_task: ['related'],
  open_corridor_inspector: ['related'],
  add_annotation: ['validate'],
  bookmark_finding: ['validate'],
  check_budget: ['metrics', 'validate'],
  optimize: ['recommend'],
  regression_explain: ['validate', 'recommend'],
  what_if: ['recommend'],
  optimize_experiment: ['recommend'],
  analyze_traces: ['metrics', 'validate'],
  investigation_replay: ['validate'],
  generate_report: ['recommend'],
  export_report: ['recommend'],
  explain_finding: ['findings', 'hypotheses'],
  interpret_query: ['findings'],
  validate_experiment: ['validate', 'recommend'],
  manage_hypotheses: ['hypotheses', 'validate'],
  plan_investigation: ['findings', 'hypotheses'],
  suggest_scope: ['findings', 'narrow'],
  detect_contradictions: ['validate'],
  assess_evidence_sufficiency: ['validate'],
  cluster_findings: ['findings'],
  generate_fingerprint: ['findings'],
  find_similar_investigations: ['recommend'],
  regression_localize: ['metrics', 'validate'],
  build_causal_chain: ['validate'],
  generate_experiment_plan: ['recommend'],
  record_experiment_outcome: ['validate', 'recommend'],
  score_investigation: ['validate'],
  analyze_temporal_causality: ['validate'],
  build_task_dependency_graph: ['validate'],
  decompose_response_time: ['metrics', 'validate'],
  rank_root_causes: ['hypotheses', 'validate'],
  verify_claim: ['validate'],
  challenge_conclusion: ['validate'],
  investigation_memory: ['recommend'],
  cluster_incidents: ['findings'],
  close_investigation: ['validate', 'recommend'],
  analyze_distribution: ['metrics'],
  analyze_periodicity: ['metrics'],
  summarize_investigation_context: ['validate'],
}

/** Tools whose results refresh the Evidence & Validation log. Keep in sync with
 *  btf_viewer_pkg/ai_investigation.py EVIDENCE_PANEL_TOOLS. */
export const EVIDENCE_PANEL_TOOLS = [
  'investigate',
  'correlate_events',
  'find_critical_path',
  'detect_priority_inversion',
  'compare_performance',
  'search_timeline',
  'explain_finding',
  'interpret_query',
  'validate_experiment',
  'manage_hypotheses',
  'plan_investigation',
  'suggest_scope',
  'detect_contradictions',
  'assess_evidence_sufficiency',
  'cluster_findings',
  'generate_fingerprint',
  'find_similar_investigations',
  'regression_localize',
  'build_causal_chain',
  'generate_experiment_plan',
  'record_experiment_outcome',
  'score_investigation',
  'analyze_temporal_causality',
  'build_task_dependency_graph',
  'decompose_response_time',
  'rank_root_causes',
  'verify_claim',
  'challenge_conclusion',
  'investigation_memory',
  'cluster_incidents',
  'close_investigation',
  'analyze_distribution',
  'analyze_periodicity',
  'summarize_investigation_context',
]

const AGENT_TEMPLATE_IDS = new Set([
  'investigate', 'root_cause', 'verify', 'what_if', 'optimize',
  'diagnostic_report', 'auto_investigate', 'explain_finding',
])

const EVIDENCE_STAGE_TEMPLATES = new Set([
  'auto_investigate', 'investigate', 'root_cause', 'verify',
])

const FINDING_ID_RE = /^[a-z][a-z0-9_]{0,47}$/

export const DEFAULT_REGRESSION_RULES = [
  {
    id: 'migrations',
    label: 'Migrations (total)',
    metric: 'migrations',
    worse_when: 'increase_pct',
    threshold: 20.0,
  },
  {
    id: 'load_balance',
    label: 'Load Balance Score',
    metric: 'load_balance_score',
    worse_when: 'decrease_abs',
    threshold: 10.0,
  },
  {
    id: 'missed_ticks',
    label: 'Missed ticks (est.)',
    metric: 'missed_ticks',
    worse_when: 'increase_abs',
    threshold: 1.0,
  },
  {
    id: 'migrated_tasks',
    label: 'Migrated tasks',
    metric: 'migrated_tasks',
    worse_when: 'increase_pct',
    threshold: 25.0,
  },
]

export function isAgentTemplate(templateId) {
  return AGENT_TEMPLATE_IDS.has(String(templateId || '').trim())
}

/** Promote triage/scope to investigate for Start Investigation-style templates. */
export function elevateGuideStageForTemplate(stage, templateId = '') {
  let sid = String(stage || '').trim().toLowerCase()
  if (!sid || sid === 'idle' || sid === 'start') sid = 'triage'
  const tid = String(templateId || '').trim()
  if (EVIDENCE_STAGE_TEMPLATES.has(tid) && (sid === 'triage' || sid === 'scope')) {
    return 'investigate'
  }
  return sid
}

export function maxToolRoundsForTemplate(templateId = '', defaultRounds = 4) {
  return isAgentTemplate(templateId) ? 8 : Number(defaultRounds) || 4
}

export function defaultInvestigationPlan(goal = '') {
  return {
    goal: String(goal || 'Investigate the main performance problem').trim(),
    steps: INVESTIGATION_PLAN_STEPS.map(([id, label]) => ({
      id, label, status: 'pending',
    })),
  }
}

export function markPlanStepsFromTools(plan, toolNames) {
  const out = plan && typeof plan === 'object'
    ? { ...plan, steps: (plan.steps || []).map(s => ({ ...s })) }
    : defaultInvestigationPlan()
  const byId = Object.fromEntries((out.steps || []).map(s => [s.id, s]))
  for (const name of toolNames || []) {
    for (const sid of (TOOL_STEP_MAP[String(name || '')] || [])) {
      if (byId[sid]) byId[sid].status = 'done'
    }
  }
  let activated = false
  for (const step of out.steps) {
    if (step.status === 'done') continue
    if (!activated) {
      step.status = 'active'
      activated = true
    } else {
      step.status = 'pending'
    }
  }
  return out
}

/** Mark every plan step done when the final assistant answer arrives. */
export function completeInvestigationPlan(plan) {
  const out = plan && typeof plan === 'object'
    ? { ...plan, steps: (plan.steps || []).map(s => ({ ...s })) }
    : defaultInvestigationPlan()
  out.steps = (out.steps || []).map(s => ({ ...s, status: 'done' }))
  return out
}

export function slugFindingId(title, used = new Set()) {
  let base = String(title || 'finding').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
  if (!base) base = 'finding'
  base = base.slice(0, 40)
  if (!FINDING_ID_RE.test(base)) base = 'finding'
  let cand = base
  let n = 2
  while (used.has(cand)) {
    cand = `${base}_${n}`
    n += 1
  }
  used.add(cand)
  return cand
}

const JUMP_IN_TEXT_RE = /jump:([0-9]+(?:\.[0-9]+)?)/i

function promoteJumpTimesFromText(item) {
  const evidence = (item.evidence || [])
    .filter(e => e && typeof e === 'object')
    .map(e => ({ ...e }))
  if (evidence.some(e => e.time != null)) {
    item.evidence = evidence
    return
  }
  const blob = `${item.title || ''} ${item.text || ''}`
  const m = JUMP_IN_TEXT_RE.exec(blob)
  if (!m) {
    item.evidence = evidence
    return
  }
  const raw = Number(m[1])
  if (!Number.isFinite(raw)) {
    item.evidence = evidence
    return
  }
  const t = Number.isInteger(raw) ? Math.trunc(raw) : raw
  evidence.push({ label: 'finding text', time: t })
  item.evidence = evidence
}

export function enrichFindingsWithIds(findings) {
  const used = new Set()
  return (findings || []).map((f) => {
    const item = { ...(f || {}) }
    let fid = String(item.id || '').trim()
    if (!fid || !FINDING_ID_RE.test(fid) || used.has(fid)) {
      fid = slugFindingId(String(item.title || 'finding'), used)
    } else {
      used.add(fid)
    }
    item.id = fid
    promoteJumpTimesFromText(item)
    return item
  })
}

export function formatFindingsEvidenceChain(findings) {
  const lines = ['## Evidence', '']
  if (!findings?.length) {
    lines.push('_No findings in scope._')
    return lines.join('\n')
  }
  for (const f of findings) {
    const sev = String(f.severity || 'info').toUpperCase()
    lines.push(`- **[${sev}] ${f.title || 'Finding'}** (\`id=${f.id || ''}\`)`)
    lines.push(`  - ${f.text || ''}`)
    for (const ev of (f.evidence || [])) {
      if (ev && typeof ev === 'object') {
        const label = ev.label || ev.text || 'evidence'
        if (ev.time != null) lines.push(`  - ${label}: jump:${ev.time}`)
        else lines.push(`  - ${label}`)
      } else {
        lines.push(`  - ${ev}`)
      }
    }
  }
  return lines.join('\n')
}

export function resolveFinding(findings, findingId = '') {
  const items = enrichFindingsWithIds(findings)
  const want = String(findingId || '').trim()
  if (!want) {
    return items.find(f => f.severity === 'warning' || f.severity === 'error') || items[0] || null
  }
  const low = want.toLowerCase()
  const byId = items.find(f => String(f.id || '').toLowerCase() === low)
  if (byId) return byId
  if (/^\d+$/.test(want)) {
    const idx = Number(want) - 1
    if (idx >= 0 && idx < items.length) return items[idx]
  }
  return items.find(f => String(f.title || '').toLowerCase().includes(low)) || null
}

function guessTaskName(text) {
  // Keep in sync with btf_viewer_pkg/ai_investigation._guess_task_name
  const bracketed = String(text || '').match(/\b[A-Za-z_][\w]*\[[0-9]+\]/g) || []
  for (const tok of bracketed) {
    const low = tok.toLowerCase()
    if (low.startsWith('core') || low === 'tick') continue
    return tok
  }
  const skip = new Set([
    'max', 'min', 'rate', 'dwell', 'ping', 'load', 'balance',
    'score', 'tick', 'mode', 'core', 'mutex', 'queue',
  ])
  const re = /\b([A-Za-z_][\w]*(?:\[[0-9]+\])?)\b/g
  let m
  while ((m = re.exec(String(text || ''))) !== null) {
    const tok = m[1]
    const low = tok.toLowerCase()
    if (skip.has(low)) continue
    if (tok.includes('[')) return tok
  }
  return bracketed[0] || ''
}

function alternativesFromHypotheses(hypotheses) {
  const alts = []
  for (let i = 0; i < (hypotheses || []).length; i += 1) {
    const h = hypotheses[i]
    if (!h || typeof h !== 'object') continue
    const hyp = String(h.hypothesis || '').trim()
    if (!hyp) continue
    alts.push({
      hypothesis: hyp,
      status: i === 0 ? 'plausible' : 'untested',
      why: String(h.why || '').trim(),
    })
  }
  return alts
}

function hypothesesForFinding(title, text) {
  const blob = `${title} ${text}`.toLowerCase()
  const hyps = []
  const add = (h, why) => hyps.push({ hypothesis: h, why })
  if (/thrash|migration|bounc/.test(blob)) {
    add('Core thrashing / lock bounce', 'High migration or bounce metrics')
    add('Missing affinity pin', 'Equal-priority fan-out across cores')
  }
  if (/block|latency|dispatch/.test(blob)) {
    add('Off-CPU blocking / mutex wait', 'Blocking gaps dominate latency')
    add('Preemption chain interference', 'Higher-priority work stretches wait')
  }
  if (/inversion|l\/m\/h|inherit/.test(blob)) {
    add('Priority inversion on shared mutex', 'L/M/H geometry in findings')
  }
  if (/wcet|cpu|execution|spike/.test(blob)) {
    add('Long execution slices / WCET spike', 'Max vs typical execution diverge')
    add('Interrupt or critical-section stretch', 'Unexplained Max growth')
  }
  if (/load|imbalance|balance/.test(blob)) {
    add('Uneven core placement', 'Load Balance Score / σ warning')
  }
  if (/tick|missed/.test(blob)) {
    add('Tick health / tickless idle gaps', 'TICK CV or missed ticks')
  }
  if (/deadline|budget/.test(blob)) {
    add('Deadline or CPU-budget breach', 'Configured thresholds exceeded')
  }
  if (!hyps.length) {
    add('Primary finding needs metric drill-down', 'No specialised heuristic match')
  }
  return hyps
}

function suggestedToolsForFinding(title, text, depth) {
  const blob = `${title} ${text}`.toLowerCase()
  const tools = []
  const task = guessTaskName(text)
  const add = (name, arguments_, reason) => {
    tools.push({ name, arguments: arguments_, reason })
  }
  if (task) {
    if (/block|inversion|latency/.test(blob)) {
      add('query_raw_metric', { task, metric: 'blocking' }, 'Inspect blocking gaps')
      add('query_raw_metric', { task, metric: 'priority_inheritance' }, 'Check inherit episodes')
    }
    if (/wcet|cpu|execution|spike/.test(blob)) {
      add('query_raw_metric', { task, metric: 'execution' }, 'Inspect execution slices')
    }
    if (/migrat|thrash|bounc/.test(blob)) {
      add('query_raw_metric', { task, metric: 'migrations' }, 'Inspect migrations')
      add('open_corridor_inspector', {}, 'Open migration inspector')
    }
    add('highlight_task', { task_name_or_id: task }, 'Highlight victim task')
    add('search_timeline', { query: task, mode: 'contains' }, 'Locate task on timeline')
  } else {
    add('query_raw_metric', { task: '*', metric: 'findings' }, 'Re-read findings lines')
    add('search_timeline', { query: 'mutex', mode: 'sti' }, 'Search sync activity')
  }
  if (depth >= 2) {
    add('detect_anomalies', { limit: 8 }, 'Rank Critical/Warning anomalies')
  }
  if (task && depth >= 2) {
    add('correlate_events', { task }, 'Cross-task event correlation')
  }
  if (depth >= 3) {
    add('trigger_compare', {}, 'Compare two open tabs if available')
    add('compare_performance', {}, 'Structured A vs B performance deltas')
  }
  if (depth >= 4) {
    add('generate_report', { report_type: 'root_cause' }, 'Structured RCA report')
    add('export_report', { format: 'html' }, 'Save diagnostic report')
  }
  return tools.slice(0, Math.max(3, depth * 2))
}

export function buildInvestigateContext(findings, findingId = '', { depth = 2 } = {}) {
  const d = Math.max(1, Math.min(5, Number(depth) || 2))
  const items = enrichFindingsWithIds(findings)
  const focus = resolveFinding(items, findingId)
  if (!focus) {
    return {
      ok: false,
      message: 'No Analysis Findings in scope',
      findings: [],
      focus: null,
      hypotheses: [],
      alternatives: [],
      suggested_tools: [],
      plan: defaultInvestigationPlan(),
      evidence_chain: formatFindingsEvidenceChain([]),
    }
  }
  const title = String(focus.title || '')
  const text = String(focus.text || '')
  const sev = String(focus.severity || 'info')
  const hypotheses = hypothesesForFinding(title, text)
  const alternatives = alternativesFromHypotheses(hypotheses)
  const suggested = suggestedToolsForFinding(title, text, d)
  const related = items
    .filter(f => f.id !== focus.id)
    .slice(0, 8)
    .map(f => ({ id: f.id, severity: f.severity, title: f.title }))
  let plan = defaultInvestigationPlan(`Investigate: ${title}`)
  plan = markPlanStepsFromTools(plan, ['investigate'])
  const chain = buildRootCauseChain(focus)
  const anomalies = detectAnomalies(items, { limit: Math.max(3, d + 2) })
  const evidenceChainText = formatFindingsEvidenceChain([focus])
  const alternativesSlice = alternatives.slice(0, Math.max(1, d + 1))
  const finding = {
    id: focus.id,
    severity: sev,
    title,
    text,
    evidence: focus.evidence || [],
    task: focus.task || guessTaskName(text),
  }
  const hyps = enrichHypotheses(hypotheses.slice(0, Math.max(1, d + 1)), {
    evidence: finding.evidence,
    alternatives: alternativesSlice,
  })
  const scoreData = computeEvidenceScore(focus.evidence || [], {
    alternatives: alternativesSlice,
    evidenceChain: evidenceChainText,
  })
  const quality = scoreData.quality || computeEvidenceQuality({
    score: scoreData.score,
    breakdown: scoreData.breakdown,
    evidence: finding.evidence,
    alternatives: alternativesSlice,
    evidenceChain: evidenceChainText,
  })
  const graph = {
    finding,
    related_findings: related,
    hypotheses: hyps,
    alternatives: alternativesSlice,
    suggested_tools: suggested,
    depth: d,
    evidence_chain: evidenceChainText,
    root_cause_chain: chain,
    ranked_anomalies: (anomalies.anomalies || []).slice(0, Math.max(3, d)),
    plan,
    evidence_score: scoreData.score,
    evidence_score_breakdown: scoreData.breakdown,
    evidence_quality: quality,
    evidence_coverage: computeEvidenceCoverage({ evidence: finding.evidence }),
    evidence_graph: buildEvidenceGraph(finding, {
      evidence: finding.evidence, hypotheses: hyps, chain,
    }),
    falsification: falsificationChecks(finding),
    historical_knowledge: historicalKnowledgeForFinding(finding),
  }
  graph.investigation_case = buildInvestigationCase(graph, { scoreData })
  return {
    ok: true,
    message: `Investigation context for ${focus.id} (${hypotheses.length} hypotheses, ${suggested.length} suggested tools)`,
    ...graph,
  }
}

const CRITICAL_PATH_KIND_ORDER = {
  blocking: 0,
  sync: 1,
  priority: 2,
  execution: 3,
  migration: 4,
  search: 5,
}

export function buildCriticalPath(events, {
  task = '', timestamp = null, limit = 20,
} = {}) {
  const lim = Math.max(1, Math.min(40, Number(limit) || 20))
  let rows = []
  for (const ev of events || []) {
    if (!ev || typeof ev !== 'object') continue
    const t = Number(ev.time)
    if (!Number.isFinite(t)) continue
    rows.push({
      time: t,
      kind: String(ev.kind || 'event'),
      detail: String(ev.detail || ev.note || ''),
      task: String(ev.task || task || ''),
    })
  }
  if (!rows.length) {
    return {
      ok: false,
      message: 'No events in scope for critical path',
      task,
      path: [],
      confidence: 'Low',
      mermaid: '',
      graph_nodes: [],
      blocking_steps: [],
      preemption_steps: [],
    }
  }
  if (timestamp != null && Number.isFinite(Number(timestamp))) {
    const ts = Number(timestamp)
    rows.sort((a, b) => {
      const da = Math.abs(a.time - ts) - Math.abs(b.time - ts)
      if (da !== 0) return da
      const ka = CRITICAL_PATH_KIND_ORDER[a.kind] ?? 9
      const kb = CRITICAL_PATH_KIND_ORDER[b.kind] ?? 9
      if (ka !== kb) return ka - kb
      return a.time - b.time
    })
  } else {
    rows.sort((a, b) => {
      const ka = CRITICAL_PATH_KIND_ORDER[a.kind] ?? 9
      const kb = CRITICAL_PATH_KIND_ORDER[b.kind] ?? 9
      if (ka !== kb) return ka - kb
      return a.time - b.time
    })
  }
  rows = rows.slice(0, lim)
  const kindLabels = {
    blocking: 'Blocked / off-CPU',
    sync: 'Sync / mutex',
    priority: 'Priority inheritance',
    execution: 'On-CPU execution',
    migration: 'Core migration',
    search: 'Timeline match',
  }
  const path = rows.map((ev, i) => {
    const label = kindLabels[ev.kind] || ev.kind
    const detail = ev.detail
    const start = ev.time
    const nxt = rows[i + 1]
    const stop = nxt && nxt.time > start ? nxt.time : start
    return {
      step: i + 1,
      time: ev.time,
      start,
      stop,
      detail: detail ? `${label}: ${detail}` : label,
      kind: ev.kind,
    }
  })
  const kinds = new Set(rows.map(r => r.kind))
  let confidence = 'Low'
  if (kinds.size >= 3 && rows.length >= 4) confidence = 'High'
  else if (rows.length >= 2) confidence = 'Medium'
  // Blocking = off-CPU waits; preemption = priority boosts / migrations that
  // reshuffled who ran (best-effort from this task's own event stream).
  const blockingSteps = path.filter(p => p.kind === 'blocking')
  const preemptionSteps = path.filter(p => p.kind === 'priority' || p.kind === 'migration')
  const graphNodes = path.map(p => ({
    id: `S${p.step}`, label: p.detail, kind: p.kind, time: p.time,
  }))
  let mermaid = ''
  if (graphNodes.length >= 2) {
    const lines = ['graph LR']
    for (const node of graphNodes) {
      const safe = String(node.label).replace(/["[\]{}()]/g, "'").slice(0, 80)
      lines.push(`  ${node.id}["${safe}"]`)
    }
    for (let i = 0; i < graphNodes.length - 1; i++) {
      lines.push(`  ${graphNodes[i].id} --> ${graphNodes[i + 1].id}`)
    }
    mermaid = lines.join('\n')
  }
  return {
    ok: true,
    message: `${path.length} step critical path for ${task || 'task'}`,
    task,
    timestamp,
    path,
    confidence,
    mermaid,
    graph_nodes: graphNodes,
    blocking_steps: blockingSteps,
    preemption_steps: preemptionSteps,
  }
}

export function extractEvidencePanelPayload(toolName, result) {
  if (!result || typeof result !== 'object' || !result.ok) return null
  const data = result.data && typeof result.data === 'object' ? { ...result.data } : {}
  for (const key of [
    'finding', 'hypotheses', 'alternatives', 'evidence_chain',
    'events', 'path', 'checks', 'confidence', 'task', 'correlation',
    'root_cause_chain', 'historical_knowledge',
  ]) {
    if (!(key in data) && key in result) data[key] = result[key]
  }
  const name = String(toolName || '')
  const payload = {}

  if (name === 'investigate' || data.finding || data.hypotheses) {
    const finding = data.finding && typeof data.finding === 'object' ? data.finding : {}
    payload.conclusion = String(finding.title || data.conclusion || '')
    payload.subtitle = String(finding.text || '')
    const evItems = []
    for (const ev of finding.evidence || []) {
      if (!ev || typeof ev !== 'object') continue
      evItems.push({
        label: String(ev.label || ev.text || 'evidence'),
        time: ev.time,
      })
    }
    if (evItems.length) payload.evidence = evItems
    if (data.evidence_chain) payload.evidence_chain = String(data.evidence_chain)
    payload.alternatives = [...(data.alternatives || [])]
    payload.confidence = String(data.confidence || 'Medium')
    if (data.hypotheses?.length) payload.hypotheses = [...data.hypotheses]
    if (data.root_cause_chain?.length) payload.root_cause_chain = [...data.root_cause_chain]
    for (const extra of [
      'evidence_quality', 'evidence_coverage', 'evidence_graph',
      'falsification', 'investigation_case', 'confidence_history',
      'historical_knowledge',
    ]) {
      if (data[extra]) payload[extra] = data[extra]
    }
    if (data.explanation && !payload.subtitle) payload.subtitle = String(data.explanation)
  } else if (name === 'find_critical_path' || data.path) {
    const task = String(data.task || '')
    payload.conclusion = task ? `Critical path: ${task}` : 'Critical path'
    payload.evidence = (data.path || [])
      .filter(p => p && typeof p === 'object')
      .map(p => ({
        label: String(p.detail || ''),
        time: p.time,
        start: p.start,
        stop: p.stop,
      }))
    payload.confidence = String(data.confidence || 'Medium')
  } else if (name === 'correlate_events' || data.events) {
    const task = String(data.task || '')
    payload.conclusion = task ? `Correlated events: ${task}` : 'Correlated events'
    payload.evidence = (data.events || [])
      .slice(0, 15)
      .filter(e => e && typeof e === 'object')
      .map(e => ({
        label: `${e.kind}: ${e.detail}`,
        time: e.time,
      }))
    payload.confidence = data.correlation != null
      ? `Correlation ${data.correlation}`
      : 'Medium'
  } else if (name === 'search_timeline' || data.times != null || result.times != null) {
    const rawTimes = data.times || result.times || []
    const times = []
    for (const t of rawTimes) {
      const n = Number(t)
      if (Number.isFinite(n)) times.push(n)
    }
    const query = String(data.query || result.query || '').trim()
    payload.conclusion = String(
      result.message
      || data.message
      || (times.length ? `${times.length} timeline hit(s)` : 'No timeline hits'),
    )
    payload.evidence = times.slice(0, 20).map((t) => ({
      label: query ? `timeline: ${query}` : 'timeline hit',
      time: Number.isInteger(t) ? Math.trunc(t) : t,
    }))
    payload.confidence = String(data.confidence || 'Medium')
  } else if (name === 'detect_priority_inversion' || data.inversions != null) {
    const inversions = (data.inversions || []).filter(inv => inv && typeof inv === 'object')
    const task = String(data.task || '')
    payload.conclusion = String(
      result.message
      || data.message
      || (inversions.length
        ? `${inversions.length} priority inversion(s)`
        : 'No priority inversion suspects'),
    )
    payload.evidence = inversions.slice(0, 15).map((inv) => {
      const pattern = String(inv.pattern || '').trim() || 'L/M/H inversion'
      let label = `priority: ${pattern}`
      if (inv.low) label += ` low=${inv.low}`
      if (inv.medium) label += ` med=${inv.medium}`
      if (inv.high) label += ` high=${inv.high}`
      const start = inv.time
      const stop = (start != null && inv.duration != null)
        ? Number(start) + Number(inv.duration)
        : start
      return { label, time: start, start, stop }
    })
    if (inversions.length) {
      payload.evidence_chain = `${inversions.length} priority-inversion episode(s)`
        + (task ? ` involving ${task}` : '')
    }
    payload.confidence = String(data.confidence || 'Medium')
  } else if (name === 'compare_performance' || data.checks) {
    const primary = data.primary
    payload.conclusion = primary && typeof primary === 'object'
      ? String(primary.label || 'Performance comparison')
      : 'Performance comparison'
    payload.confidence = String(data.confidence || 'Medium')
    payload.checks = [...(data.checks || [])]
  } else if (name === 'interpret_query' || data.interpreted_question) {
    payload.conclusion = String(data.interpreted_question || '')
    const scopes = (data.scope || []).map(s => String(s)).filter(Boolean)
    const mode = String(data.mode || data.kind || '')
    if (scopes.length) payload.subtitle = mode ? `${mode}: ${scopes.join(', ')}` : scopes.join(', ')
    else if (mode) payload.subtitle = mode
    payload.confidence = 'Medium'
    payload.interpreted = {
      interpreted_question: payload.conclusion,
      kind: data.kind || mode,
      mode,
      scope: scopes,
      finding_id: String(data.finding_id || ''),
      task: String(data.task || ''),
    }
  } else if (
    name === 'validate_experiment'
    || ['VALIDATED', 'PARTIALLY VALIDATED', 'DISPROVED', 'INCONCLUSIVE'].includes(data.result)
  ) {
    const resultLabel = String(data.result || 'INCONCLUSIVE')
    payload.conclusion = resultLabel
    payload.experiment = {
      result: resultLabel,
      verdict: formatExperimentVerdict(resultLabel),
      rows: [...(data.rows || [])],
    }
    payload.checks = (data.rows || [])
      .filter(row => row && typeof row === 'object')
      .map(row => ({
        label: String(row.metric || 'metric'),
        status: String(row.status || ''),
        detail: `expected ${row.expected} actual ${row.actual}`,
      }))
    payload.confidence = resultLabel === 'VALIDATED'
      ? 'High'
      : resultLabel === 'DISPROVED' ? 'Low' : 'Medium'
  } else if ([
    'plan_investigation', 'suggest_scope', 'detect_contradictions',
    'assess_evidence_sufficiency', 'cluster_findings', 'generate_fingerprint',
    'find_similar_investigations', 'regression_localize', 'build_causal_chain',
    'generate_experiment_plan', 'record_experiment_outcome', 'score_investigation',
    'analyze_temporal_causality', 'build_task_dependency_graph',
    'decompose_response_time', 'rank_root_causes', 'verify_claim',
    'challenge_conclusion', 'investigation_memory', 'cluster_incidents',
    'close_investigation', 'analyze_distribution', 'analyze_periodicity',
    'summarize_investigation_context',
  ].includes(name) || data.steps || data.verdict || data.pattern) {
    payload.conclusion = String(result.message || data.message || name)
    payload.confidence = String(data.confidence || 'Medium')
    if (data.mermaid) payload.evidence_chain = String(data.mermaid)
  }

  if (!(
    payload.conclusion
    || payload.evidence
    || payload.evidence_chain
    || payload.alternatives?.length
    || payload.checks?.length
  )) return null
  const scoreData = computeEvidenceScore(payload.evidence || [], {
    alternatives: payload.alternatives || [],
    evidenceChain: payload.evidence_chain || '',
    checks: payload.checks || [],
  })
  payload.evidence_score = scoreData.score
  payload.evidence_score_breakdown = scoreData.breakdown
  payload.evidence_score_bar = scoreData.bar
  const quality = computeEvidenceQuality({
    score: scoreData.score,
    breakdown: scoreData.breakdown,
    evidence: payload.evidence,
    alternatives: payload.alternatives,
    checks: payload.checks,
    evidenceChain: String(payload.evidence_chain || ''),
  })
  payload.evidence_quality = quality
  payload.evidence_quality_bar = quality.bar
  let finding = data.finding && typeof data.finding === 'object' ? data.finding : null
  if (!finding && payload.conclusion) {
    finding = {
      title: payload.conclusion,
      text: payload.subtitle || '',
      evidence: payload.evidence || [],
    }
  }
  const caseObj = buildInvestigationCase({
    finding: finding || {},
    hypotheses: payload.hypotheses || [],
    alternatives: payload.alternatives || [],
    evidence: payload.evidence || [],
    root_cause_chain: payload.root_cause_chain || [],
    plan: data.plan,
    suggested_tools: data.suggested_tools || [],
    checks: payload.checks || [],
    evidence_score: scoreData.score,
    evidence_score_breakdown: scoreData.breakdown,
    evidence_chain: payload.evidence_chain || '',
    message: payload.conclusion || '',
  }, {
    scoreData,
    toolsRun: data.suggested_tools || data.tools_executed,
    conclusion: String(payload.conclusion || ''),
    confidence: String(payload.confidence || ''),
  })
  payload.investigation_case = caseObj
  payload.coverage = caseObj.evidence_coverage || caseObj.coverage
  payload.falsify = caseObj.falsification || caseObj.falsify
  payload.graph_mermaid = caseObj.graph_mermaid
  payload.hypotheses_managed = caseObj.hypotheses
  payload.tool_reasons = caseObj.tool_reasons || []
  payload.confidence_evolution = formatConfidenceEvolution(caseObj.confidence_history)
  const hk = data.historical_knowledge || payload.historical_knowledge
  if (hk) payload.historical_knowledge = hk
  return payload
}

function evidenceItemsHaveTimes(evidence) {
  if (!Array.isArray(evidence)) return false
  return evidence.some(e => e && typeof e === 'object' && e.time != null)
}

/** Recompute heuristic score / quality fields on an Evidence panel payload. */
export function refreshEvidencePanelScores(payload) {
  const out = { ...(payload || {}) }
  const scoreData = computeEvidenceScore(out.evidence || [], {
    alternatives: out.alternatives || [],
    evidenceChain: String(out.evidence_chain || ''),
    checks: out.checks || [],
  })
  out.evidence_score = scoreData.score
  out.evidence_score_breakdown = scoreData.breakdown
  out.evidence_score_bar = scoreData.bar
  const quality = computeEvidenceQuality({
    score: scoreData.score,
    breakdown: scoreData.breakdown,
    evidence: out.evidence,
    alternatives: out.alternatives,
    checks: out.checks,
    evidenceChain: String(out.evidence_chain || ''),
  })
  out.evidence_quality = quality
  out.evidence_quality_bar = quality.bar
  return out
}

/**
 * Carry forward timed evidence when a later tool omits it.
 * Keep in sync with btf_viewer_pkg/ai_investigation.py merge_evidence_panel_payload.
 */
export function mergeEvidencePanelPayload(prev, next) {
  if (!next || typeof next !== 'object') {
    return prev && typeof prev === 'object' ? { ...prev } : next
  }
  if (!prev || typeof prev !== 'object') return { ...next }
  const out = { ...next }
  if (!evidenceItemsHaveTimes(out.evidence) && evidenceItemsHaveTimes(prev.evidence)) {
    out.evidence = [...(prev.evidence || [])]
  }
  if (!String(out.evidence_chain || '').trim() && String(prev.evidence_chain || '').trim()) {
    out.evidence_chain = prev.evidence_chain
  }
  if (!(out.checks && out.checks.length) && prev.checks?.length) {
    out.checks = [...prev.checks]
  }
  for (const key of [
    'alternatives', 'hypotheses', 'hypotheses_managed', 'root_cause_chain',
    'finding', 'subtitle',
  ]) {
    // Match Python falsy lists/strings: empty [] must not wipe prior alts.
    const cur = out[key]
    const missing = cur == null
      || (Array.isArray(cur) && cur.length === 0)
      || (typeof cur === 'string' && !String(cur).trim())
    if (missing && prev[key]) out[key] = prev[key]
  }
  return refreshEvidencePanelScores(out)
}

function evidenceJumpToken(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return String(value ?? '')
  return Number.isInteger(n) ? String(Math.trunc(n)) : String(n)
}

const BTF_HYP_HREF_RE = /btfhyp:(?:\/\/)?([a-z_]+)\/([^?\s#]*)/i

export function btfHypHref(action, hypId = '') {
  const act = String(action || '').toLowerCase().replace(/[^a-z_]/g, '') || 'test'
  const hid = String(hypId || 'all').replace(/[^A-Za-z0-9_.-]/g, '') || 'all'
  return `btfhyp:${act}/${hid}`
}

export function parseBtfHypHref(href) {
  const m = BTF_HYP_HREF_RE.exec(String(href || ''))
  if (!m) return { action: '', hypId: '' }
  return { action: String(m[1] || '').toLowerCase(), hypId: m[2] || 'all' }
}

export function formatHypothesisActionLinks(hypId, labels = {}) {
  const hid = String(hypId || 'h1')
  const parts = [
    ['supported', 'support_action', 'Support'],
    ['rejected', 'reject_action', 'Reject'],
    ['need_evidence', 'need_evidence_action', 'Need evidence'],
    ['test', 'test_action', 'Test'],
  ].map(([action, key, fallback]) => `[${labels[key] || fallback}](${btfHypHref(action, hid)})`)
  return parts.join(' · ')
}

const BTF_SCOPE_HREF_RE = /btfscope:(?:\/\/)?([a-z_]+)\/([^?\s#]*)/i
const BTF_EXP_HREF_RE = /btfexp:(?:\/\/)?([a-z_]+)\/([^?\s#]*)/i
const BTF_TOOL_HREF_RE = /btftool:(?:\/\/)?([a-z_]+)\/([^?\s#]*)/i

export function btfScopeHref(action, key = '') {
  const act = String(action || '').toLowerCase().replace(/[^a-z_]/g, '') || 'run'
  const kid = String(key || 'all').replace(/[^A-Za-z0-9_. -]/g, '').trim().replace(/ /g, '_') || 'all'
  return `btfscope:${act}/${kid}`
}

export function parseBtfScopeHref(href) {
  const m = BTF_SCOPE_HREF_RE.exec(String(href || ''))
  if (!m) return { action: '', key: '' }
  return { action: String(m[1] || '').toLowerCase(), key: String(m[2] || 'all').replace(/_/g, ' ') }
}

export function formatScopeActionLinks(interpreted = null, labels = {}) {
  const data = interpreted && typeof interpreted === 'object' ? interpreted : {}
  const scopes = [...(data.scope || [])].map(s => String(s)).filter(Boolean)
  const options = [...INVESTIGATION_SCOPE_OPTIONS]
  for (const s of scopes) {
    if (!options.includes(s)) options.push(s)
  }
  const lines = []
  const question = String(data.interpreted_question || '').trim()
  if (question) lines.push(`**${labels.interpreted || 'Interpreted question'}:** ${question}`)
  lines.push('', `**${labels.scope || 'Investigation scope'}**`)
  const onLab = labels.scope_on || 'on'
  const offLab = labels.scope_off || 'off'
  for (const opt of options) {
    const active = scopes.includes(opt)
    lines.push(`- ${active ? '✓' : '○'} ${opt} [${active ? offLab : onLab}](${btfScopeHref('toggle', opt)})`)
  }
  lines.push(
    '',
    `[${labels.run_investigation || 'Run investigation'}](${btfScopeHref('run', 'all')}) `
    + `[${labels.edit_scope || 'Edit scope'}](${btfScopeHref('edit', 'all')})`,
  )
  return lines.join('\n')
}

export function btfExpHref(action, key = 'all') {
  const act = String(action || '').toLowerCase().replace(/[^a-z_]/g, '') || 'save'
  const kid = String(key || 'all').replace(/[^A-Za-z0-9_.-]/g, '') || 'all'
  return `btfexp:${act}/${kid}`
}

export function parseBtfExpHref(href) {
  const m = BTF_EXP_HREF_RE.exec(String(href || ''))
  if (!m) return { action: '', key: '' }
  return { action: String(m[1] || '').toLowerCase(), key: m[2] || 'all' }
}

export function btfToolHref(action, name = '') {
  const act = String(action || '').toLowerCase().replace(/[^a-z_]/g, '') || 'why'
  const kid = String(name || 'tool').replace(/[^A-Za-z0-9_.-]/g, '') || 'tool'
  return `btftool:${act}/${kid}`
}

export function parseBtfToolHref(href) {
  const m = BTF_TOOL_HREF_RE.exec(String(href || ''))
  if (!m) return { action: '', name: '' }
  return { action: String(m[1] || '').toLowerCase(), name: String(m[2] || '') }
}

/** Keep in sync with btf_viewer_pkg/ai_investigation.py EVIDENCE_PANEL_LABELS (Evidence & Validation). */
export const EVIDENCE_PANEL_LABELS = {
  English: {
    role: 'Evidence & Validation', evidence: 'Evidence', evidence_chain: 'Evidence chain',
    confidence: 'Confidence', score: 'AI Evidence Score — heuristic',
    alternatives: 'Alternative hypotheses', checklist: 'Verification checklist',
    tree: 'Investigation tree', investigation: 'Investigation', done: 'done',
    critical_path: 'Critical path', correlated_events: 'Correlated events',
    performance_comparison: 'Performance comparison', correlation: 'Correlation',
    item: 'item', check: 'check', high: 'High', medium: 'Medium', low: 'Low',
    untested: 'untested', confirmed: 'confirmed', rejected: 'rejected', plausible: 'plausible',
  },
  'Traditional Chinese (繁體中文)': {
    role: '證據與驗證', evidence: '證據', evidence_chain: '證據鏈', confidence: '置信度',
    score: 'AI 證據評分 — 啟發式', alternatives: '替代假設', checklist: '驗證清單',
    tree: '調查樹', investigation: '調查', done: '完成', critical_path: '關鍵路徑',
    correlated_events: '相關事件', performance_comparison: '性能對比', correlation: '相關性',
    item: '項目', check: '檢查', high: '高', medium: '中', low: '低',
    untested: '未驗證', confirmed: '已確認', rejected: '已排除', plausible: '可能',
  },
  'Simplified Chinese (简体中文)': {
    role: '证据与验证', evidence: '证据', evidence_chain: '证据链', confidence: '置信度',
    score: 'AI 证据评分 — 启发式', alternatives: '替代假设', checklist: '验证清单',
    tree: '调查树', investigation: '调查', done: '完成', critical_path: '关键路径',
    correlated_events: '相关事件', performance_comparison: '性能对比', correlation: '相关性',
    item: '项目', check: '检查', high: '高', medium: '中', low: '低',
    untested: '未验证', confirmed: '已确认', rejected: '已排除', plausible: '可能',
  },
  'Japanese (日本語)': {
    role: '根拠と検証', evidence: '根拠', evidence_chain: '根拠チェーン', confidence: '信頼度',
    score: 'AI 根拠スコア — ヒューリスティック', alternatives: '代替仮説', checklist: '検証チェックリスト',
    tree: '調査ツリー', investigation: '調査', done: '完了', critical_path: 'クリティカルパス',
    correlated_events: '相関イベント', performance_comparison: '性能比較', correlation: '相関',
    item: '項目', check: 'チェック', high: '高', medium: '中', low: '低',
    untested: '未検証', confirmed: '確認済み', rejected: '却下', plausible: '妥当',
  },
  'Korean (한국어)': {
    role: '증거 및 검증', evidence: '증거', evidence_chain: '증거 체인', confidence: '신뢰도',
    score: 'AI 증거 점수 — 휴리스틱', alternatives: '대안 가설', checklist: '검증 체크리스트',
    tree: '조사 트리', investigation: '조사', done: '완료', critical_path: '크리티컬 패스',
    correlated_events: '상관 이벤트', performance_comparison: '성능 비교', correlation: '상관',
    item: '항목', check: '검사', high: '높음', medium: '중간', low: '낮음',
    untested: '미검증', confirmed: '확인됨', rejected: '기각', plausible: '가능',
  },
  German: {
    role: 'Belege & Validierung', evidence: 'Belege', evidence_chain: 'Belegkette',
    confidence: 'Vertrauen', score: 'AI-Belegscore — heuristisch',
    alternatives: 'Alternative Hypothesen', checklist: 'Prüfliste', tree: 'Untersuchungsbaum',
    investigation: 'Untersuchung', done: 'fertig', critical_path: 'Kritischer Pfad',
    correlated_events: 'Korrelierte Ereignisse', performance_comparison: 'Leistungsvergleich',
    correlation: 'Korrelation', item: 'Eintrag', check: 'Prüfung', high: 'Hoch', medium: 'Mittel',
    low: 'Niedrig', untested: 'ungeprüft', confirmed: 'bestätigt', rejected: 'abgelehnt',
    plausible: 'plausibel',
  },
  French: {
    role: 'Preuves et validation', evidence: 'Preuves', evidence_chain: 'Chaîne de preuves',
    confidence: 'Confiance', score: 'Score de preuve IA — heuristique',
    alternatives: 'Hypothèses alternatives', checklist: 'Liste de vérification',
    tree: 'Arbre d\'investigation', investigation: 'Investigation', done: 'terminé',
    critical_path: 'Chemin critique', correlated_events: 'Événements corrélés',
    performance_comparison: 'Comparaison de performance', correlation: 'Corrélation',
    item: 'élément', check: 'contrôle', high: 'Élevée', medium: 'Moyenne', low: 'Faible',
    untested: 'non testé', confirmed: 'confirmé', rejected: 'rejeté', plausible: 'plausible',
  },
  Spanish: {
    role: 'Evidencia y validación', evidence: 'Evidencia', evidence_chain: 'Cadena de evidencia',
    confidence: 'Confianza', score: 'Puntuación de evidencia IA — heurística',
    alternatives: 'Hipótesis alternativas', checklist: 'Lista de verificación',
    tree: 'Árbol de investigación', investigation: 'Investigación', done: 'hecho',
    critical_path: 'Ruta crítica', correlated_events: 'Eventos correlacionados',
    performance_comparison: 'Comparación de rendimiento', correlation: 'Correlación',
    item: 'elemento', check: 'comprobación', high: 'Alta', medium: 'Media', low: 'Baja',
    untested: 'sin probar', confirmed: 'confirmado', rejected: 'rechazado', plausible: 'plausible',
  },
}

const EVIDENCE_PANEL_EXTRA = {
  English: {
    quality: 'Evidence Quality', coverage: 'Evidence Coverage',
    finding: 'Finding', direct_evidence: 'Direct evidence',
    interpretation: 'Interpretation', checks: 'Checks',
    missing_evidence: 'Missing evidence', next_action: 'Next action',
    investigation_details: 'Investigation details', status: 'Status',
    status_confirmed: 'Confirmed', status_correlated: 'Correlated',
    status_suspected: 'Suspected', status_not_observed: 'Not observed',
    status_insufficient: 'Insufficient data',
    col_time: 'Time', col_event: 'Observed event', col_task: 'Task',
    col_core: 'Core', col_duration: 'Duration', check_header: 'Check',
    observed: 'Observed', not_observed: 'Not observed',
    not_evaluated: 'Not evaluated', insufficient_evidence: 'Insufficient evidence',
    disprove: 'What would disprove this', graph: 'Evidence graph',
    supported: 'supported', possible: 'possible', needs_evidence: 'needs evidence',
    unverified: 'unverified claims', next_check: 'Recommended next check',
    supporting: 'Supporting evidence', cost: 'Investigation cost',
    claims: 'Claims', validation: 'Validation',
    evolution: 'Confidence evolution', privacy: 'Privacy',
  },
  'Traditional Chinese (繁體中文)': {
    quality: '證據品質', coverage: '證據覆蓋', disprove: '如何推翻此結論', graph: '證據圖',
    supported: '已支持', possible: '可能', needs_evidence: '需要證據',
    unverified: '未驗證的主張', next_check: '建議下一步',     supporting: '支持證據',
    cost: '調查成本', claims: '主張', validation: '驗證',
    evolution: '置信度演進', privacy: '隱私',
  },
  'Simplified Chinese (简体中文)': {
    quality: '证据品质', coverage: '证据覆盖', disprove: '如何推翻此结论', graph: '证据图',
    supported: '已支持', possible: '可能', needs_evidence: '需要证据',
    unverified: '未验证的主张', next_check: '建议下一步',     supporting: '支持证据',
    cost: '调查成本', claims: '主张', validation: '验证',
    evolution: '置信度演进', privacy: '隐私',
  },
  'Japanese (日本語)': {
    quality: '根拠の質', coverage: '根拠カバレッジ', disprove: '反証になるもの', graph: '根拠グラフ',
    supported: '支持', possible: '可能性あり', needs_evidence: '根拠不足',
    unverified: '未検証の主張', next_check: '次の確認',     supporting: '支持する根拠',
    cost: '調査コスト', claims: '主張', validation: '検証',
    evolution: '信頼度の推移', privacy: 'プライバシー',
  },
  'Korean (한국어)': {
    quality: '증거 품질', coverage: '증거 커버리지', disprove: '이 결론을 뒤집는 증거', graph: '증거 그래프',
    supported: '지지됨', possible: '가능', needs_evidence: '증거 필요',
    unverified: '미검증 주장', next_check: '다음 확인',     supporting: '지지 증거',
    cost: '조사 비용', claims: '주장', validation: '검증',
    evolution: '신뢰도 변화', privacy: '개인정보',
  },
  German: {
    quality: 'Belegqualität', coverage: 'Belegabdeckung', disprove: 'Was würde das widerlegen',
    graph: 'Beleggraph', supported: 'gestützt', possible: 'möglich',
    needs_evidence: 'Belege nötig', unverified: 'unbestätigte Aussagen',
    next_check: 'Nächster Prüfpunkt', supporting: 'Stützende Belege',
    cost: 'Untersuchungskosten', claims: 'Aussagen', validation: 'Validierung',
    evolution: 'Konfidenzverlauf', privacy: 'Datenschutz',
  },
  French: {
    quality: 'Qualité des preuves', coverage: 'Couverture des preuves',
    disprove: 'Ce qui infirmerait ceci', graph: 'Graphe de preuves',
    supported: 'étayé', possible: 'possible', needs_evidence: 'preuves nécessaires',
    unverified: 'affirmations non vérifiées', next_check: 'Prochaine vérification',
    supporting: 'Preuves à l\'appui', cost: 'Coût d\'investigation',
    claims: 'Affirmations', validation: 'Validation',
    evolution: 'Évolution de la confiance', privacy: 'Confidentialité',
  },
  Spanish: {
    quality: 'Calidad de evidencia', coverage: 'Cobertura de evidencia',
    disprove: 'Qué refutaría esto', graph: 'Grafo de evidencia',
    supported: 'respaldado', possible: 'posible', needs_evidence: 'falta evidencia',
    unverified: 'afirmaciones no verificadas', next_check: 'Siguiente comprobación',
    supporting: 'Evidencia de apoyo', cost: 'Coste de investigación',
    claims: 'Afirmaciones', validation: 'Validación',
    evolution: 'Evolución de la confianza', privacy: 'Privacidad',
  },
}
const EVIDENCE_PANEL_ACTIONS = {
  English: {
    historical: 'Historical knowledge', previous_issue: 'Previous issue',
    known_fix: 'Known fix', last_occurrence: 'Last occurrence',
    support_action: 'Support', reject_action: 'Reject',
    need_evidence_action: 'Need evidence', test_action: 'Test',
    compare_action: 'Compare hypotheses',
    interpreted: 'Interpreted question', scope: 'Investigation scope',
    run_investigation: 'Run investigation', edit_scope: 'Edit scope',
    experiment_result: 'Experiment result',
    hypothesis_validated: 'Hypothesis validated',
    hypothesis_disproved: 'Hypothesis disproved',
    hypothesis_partial: 'Hypothesis partially validated',
    save_knowledge: 'Save to knowledge', scope_on: 'on', scope_off: 'off',
    quality_direct: 'Direct evidence', quality_timeline: 'Timeline correlation',
    quality_metric: 'Metric correlation', quality_alternative: 'Alternative tested',
    coverage_observed: 'Directly observed', coverage_timeline: 'Timeline verified',
    coverage_metric: 'Metric verified', coverage_unverified: 'Unverified assumptions',
    why_action: 'Why?', typical_rate: 'Typical rate', current_rate: 'Current',
  },
  'Traditional Chinese (繁體中文)': {
    historical: '歷史知識', previous_issue: '先前問題', known_fix: '已知修復',
    last_occurrence: '上次出現', support_action: '支持', reject_action: '排除',
    need_evidence_action: '需要證據', test_action: '驗證', compare_action: '比較假設',
    interpreted: '解讀後的問題', scope: '調查範圍',
    run_investigation: '開始調查', edit_scope: '編輯範圍',
    experiment_result: '實驗結果',
    hypothesis_validated: '假設已成立', hypothesis_disproved: '假設已排除',
    hypothesis_partial: '假設部分成立',     save_knowledge: '存入知識庫',
    scope_on: '開', scope_off: '關',
    quality_direct: '直接證據', quality_timeline: '時間軸相關',
    quality_metric: '指標相關', quality_alternative: '已測替代假設',
    coverage_observed: '直接觀察', coverage_timeline: '時間軸已驗證',
    coverage_metric: '指標已驗證', coverage_unverified: '未驗證假設',
    why_action: '為何？', typical_rate: '典型速率', current_rate: '目前',
  },
  'Simplified Chinese (简体中文)': {
    historical: '历史知识', previous_issue: '先前问题', known_fix: '已知修复',
    last_occurrence: '上次出现', support_action: '支持', reject_action: '排除',
    need_evidence_action: '需要证据', test_action: '验证', compare_action: '比较假设',
    interpreted: '解读后的问题', scope: '调查范围',
    run_investigation: '开始调查', edit_scope: '编辑范围',
    experiment_result: '实验结果',
    hypothesis_validated: '假设已成立', hypothesis_disproved: '假设已排除',
    hypothesis_partial: '假设部分成立',     save_knowledge: '存入知识库',
    scope_on: '开', scope_off: '关',
    quality_direct: '直接证据', quality_timeline: '时间轴相关',
    quality_metric: '指标相关', quality_alternative: '已测替代假设',
    coverage_observed: '直接观察', coverage_timeline: '时间轴已验证',
    coverage_metric: '指标已验证', coverage_unverified: '未验证假设',
    why_action: '为何？', typical_rate: '典型速率', current_rate: '当前',
  },
  'Japanese (日本語)': {
    historical: '過去の知見', previous_issue: '過去の問題', known_fix: '既知の対策',
    last_occurrence: '前回の発生', support_action: '支持', reject_action: '却下',
    need_evidence_action: '根拠不足', test_action: '検証', compare_action: '仮説を比較',
    interpreted: '解釈した質問', scope: '調査範囲',
    run_investigation: '調査を実行', edit_scope: '範囲を編集',
    experiment_result: '実験結果',
    hypothesis_validated: '仮説は妥当', hypothesis_disproved: '仮説は否定',
    hypothesis_partial: '仮説は部分的に妥当',     save_knowledge: '知見に保存',
    scope_on: 'オン', scope_off: 'オフ',
    quality_direct: '直接根拠', quality_timeline: 'タイムライン相関',
    quality_metric: '指標相関', quality_alternative: '代替仮説を検証',
    coverage_observed: '直接観測', coverage_timeline: 'タイムライン検証',
    coverage_metric: '指標検証', coverage_unverified: '未検証の仮定',
    why_action: '理由', typical_rate: '典型値', current_rate: '現在',
  },
  'Korean (한국어)': {
    historical: '과거 지식', previous_issue: '이전 이슈', known_fix: '알려진 수정',
    last_occurrence: '최근 발생', support_action: '지지', reject_action: '기각',
    need_evidence_action: '증거 필요', test_action: '검증', compare_action: '가설 비교',
    interpreted: '해석된 질문', scope: '조사 범위',
    run_investigation: '조사 실행', edit_scope: '범위 편집',
    experiment_result: '실험 결과',
    hypothesis_validated: '가설 타당', hypothesis_disproved: '가설 기각',
    hypothesis_partial: '가설 부분 타당',     save_knowledge: '지식에 저장',
    scope_on: '켜짐', scope_off: '꺼짐',
    quality_direct: '직접 증거', quality_timeline: '타임라인 상관',
    quality_metric: '메트릭 상관', quality_alternative: '대안 검증',
    coverage_observed: '직접 관측', coverage_timeline: '타임라인 검증',
    coverage_metric: '메트릭 검증', coverage_unverified: '미검증 가정',
    why_action: '이유', typical_rate: '전형 비율', current_rate: '현재',
  },
  German: {
    historical: 'Historisches Wissen', previous_issue: 'Früheres Problem',
    known_fix: 'Bekannte Lösung', last_occurrence: 'Letztes Auftreten',
    support_action: 'Stützen', reject_action: 'Ablehnen',
    need_evidence_action: 'Belege nötig', test_action: 'Prüfen',
    compare_action: 'Hypothesen vergleichen',
    interpreted: 'Interpretierte Frage', scope: 'Untersuchungsbereich',
    run_investigation: 'Untersuchung starten', edit_scope: 'Bereich bearbeiten',
    experiment_result: 'Experimentergebnis',
    hypothesis_validated: 'Hypothese bestätigt',
    hypothesis_disproved: 'Hypothese widerlegt',
    hypothesis_partial: 'Hypothese teilweise bestätigt',
    save_knowledge: 'Im Wissen speichern', scope_on: 'an', scope_off: 'aus',
    quality_direct: 'Direkte Belege', quality_timeline: 'Zeitlinienkorrelation',
    quality_metric: 'Metrikkorrelation', quality_alternative: 'Alternative geprüft',
    coverage_observed: 'Direkt beobachtet', coverage_timeline: 'Zeitlinie geprüft',
    coverage_metric: 'Metrik geprüft', coverage_unverified: 'Ungeprüfte Annahmen',
    why_action: 'Warum?', typical_rate: 'Typische Rate', current_rate: 'Aktuell',
  },
  French: {
    historical: 'Connaissances historiques', previous_issue: 'Problème antérieur',
    known_fix: 'Correctif connu', last_occurrence: 'Dernière occurrence',
    support_action: 'Étayer', reject_action: 'Rejeter',
    need_evidence_action: 'Preuves nécessaires', test_action: 'Tester',
    compare_action: 'Comparer les hypothèses',
    interpreted: 'Question interprétée', scope: 'Périmètre d\'investigation',
    run_investigation: 'Lancer l\'investigation', edit_scope: 'Modifier le périmètre',
    experiment_result: 'Résultat d\'expérience',
    hypothesis_validated: 'Hypothèse validée',
    hypothesis_disproved: 'Hypothèse infirmée',
    hypothesis_partial: 'Hypothèse partiellement validée',
    save_knowledge: 'Enregistrer dans les connaissances',
    scope_on: 'oui', scope_off: 'non',
    quality_direct: 'Preuve directe', quality_timeline: 'Corrélation temporelle',
    quality_metric: 'Corrélation métrique', quality_alternative: 'Alternative testée',
    coverage_observed: 'Directement observé', coverage_timeline: 'Chronologie vérifiée',
    coverage_metric: 'Métrique vérifiée', coverage_unverified: 'Hypothèses non vérifiées',
    why_action: 'Pourquoi ?', typical_rate: 'Taux typique', current_rate: 'Actuel',
  },
  Spanish: {
    historical: 'Conocimiento histórico', previous_issue: 'Incidencia previa',
    known_fix: 'Corrección conocida', last_occurrence: 'Última aparición',
    support_action: 'Respaldar', reject_action: 'Rechazar',
    need_evidence_action: 'Falta evidencia', test_action: 'Probar',
    compare_action: 'Comparar hipótesis',
    interpreted: 'Pregunta interpretada', scope: 'Alcance de investigación',
    run_investigation: 'Ejecutar investigación', edit_scope: 'Editar alcance',
    experiment_result: 'Resultado del experimento',
    hypothesis_validated: 'Hipótesis validada',
    hypothesis_disproved: 'Hipótesis refutada',
    hypothesis_partial: 'Hipótesis parcialmente validada',
    save_knowledge: 'Guardar en conocimiento', scope_on: 'sí', scope_off: 'no',
    quality_direct: 'Evidencia directa', quality_timeline: 'Correlación temporal',
    quality_metric: 'Correlación métrica', quality_alternative: 'Alternativa comprobada',
    coverage_observed: 'Observado directamente', coverage_timeline: 'Línea de tiempo verificada',
    coverage_metric: 'Métrica verificada', coverage_unverified: 'Supuestos no verificados',
    why_action: '¿Por qué?', typical_rate: 'Tasa típica', current_rate: 'Actual',
  },
}
for (const [lang, extra] of Object.entries(EVIDENCE_PANEL_EXTRA)) {
  extra.need_evidence = extra.need_evidence || extra.needs_evidence || 'needs evidence'
  Object.assign(EVIDENCE_PANEL_LABELS[lang], extra, EVIDENCE_PANEL_ACTIONS[lang] || {})
}

export function normalizeResponseLanguage(lang) {
  const want = String(lang || '').trim()
  if (want in EVIDENCE_PANEL_LABELS) return want
  const low = want.toLowerCase()
  for (const key of Object.keys(EVIDENCE_PANEL_LABELS)) {
    if (key.toLowerCase() === low || key.toLowerCase().includes(low) || low.includes(key.toLowerCase())) {
      return key
    }
  }
  if (want.includes('简体') || low.includes('simplified')) return 'Simplified Chinese (简体中文)'
  if (want.includes('繁體') || want.includes('繁体') || low.includes('traditional')) {
    return 'Traditional Chinese (繁體中文)'
  }
  if (want.includes('日本') || low.includes('japanese')) return 'Japanese (日本語)'
  if (want.includes('한국') || low.includes('korean')) return 'Korean (한국어)'
  return 'English'
}

export function evidencePanelLabels(responseLanguage = 'English') {
  const key = normalizeResponseLanguage(responseLanguage)
  return { ...EVIDENCE_PANEL_LABELS[key] }
}

const EVIDENCE_STATUS_KEYS = [
  'high', 'medium', 'low', 'untested', 'confirmed', 'rejected', 'plausible',
  'supported', 'possible', 'needs_evidence', 'need_evidence',
]
const EVIDENCE_PREFIX_KEYS = [
  'critical_path', 'correlated_events', 'performance_comparison',
]

function canonicalEvidenceStatus(text) {
  const t = String(text || '').trim()
  if (!t) return null
  const low = t.toLowerCase()
  for (const key of EVIDENCE_STATUS_KEYS) {
    if (low === key) return key
  }
  for (const langLabels of Object.values(EVIDENCE_PANEL_LABELS)) {
    for (const key of EVIDENCE_STATUS_KEYS) {
      if (t === langLabels[key]) return key
    }
  }
  return null
}

function localizeEvidenceToken(text, labels) {
  const t = String(text || '').trim()
  if (!t) return t
  const canon = canonicalEvidenceStatus(t)
  if (canon) return labels[canon]
  for (const langLabels of Object.values(EVIDENCE_PANEL_LABELS)) {
    const corr = String(langLabels.correlation || '').trim()
    if (corr && (t.startsWith(`${corr} `) || t === corr)) {
      return `${labels.correlation} ${t.slice(corr.length).trim()}`.trim()
    }
  }
  if (t.startsWith('Correlation ')) return `${labels.correlation} ${t.slice(12).trim()}`
  const englishPrefixes = {
    critical_path: ['Critical path:', 'Critical path'],
    correlated_events: ['Correlated events:', 'Correlated events'],
    performance_comparison: ['Performance comparison:', 'Performance comparison'],
  }
  for (const lk of EVIDENCE_PREFIX_KEYS) {
    const candidates = [...(englishPrefixes[lk] || [])]
    for (const langLabels of Object.values(EVIDENCE_PANEL_LABELS)) {
      const localized = String(langLabels[lk] || '').trim()
      if (localized) candidates.push(`${localized}:`, localized)
    }
    for (const prefix of candidates) {
      if (t === prefix.replace(/:$/, '')) return labels[lk]
      if (t.startsWith(prefix)) {
        const rest = t.slice(prefix.length).trim().replace(/^:\s*/, '')
        return rest ? `${labels[lk]}: ${rest}` : labels[lk]
      }
    }
  }
  return t
}


const TASK_IN_LABEL_RE = /\b([A-Za-z][A-Za-z0-9_.-]*\[\d+\])/
const CORE_IN_LABEL_RE = /\b(?:Core[_\s-]?(\d+)|C(\d+))\b/i

export const CONCLUSION_STATUSES = [
  'confirmed', 'correlated', 'suspected', 'not_observed', 'insufficient',
]

export function conclusionStatusFromPayload(data = null) {
  const payload = data && typeof data === 'object' ? data : {}
  const quality = payload.evidence_quality && typeof payload.evidence_quality === 'object'
    ? payload.evidence_quality : {}
  const band = String(quality.band || '').trim().toLowerCase()
  const flags = quality.flags && typeof quality.flags === 'object' ? quality.flags : {}
  const evidence = (payload.evidence || []).filter(e => e && typeof e === 'object')
  const checks = (payload.checks || []).filter(c => c && typeof c === 'object')
  const validation = payload.validation && typeof payload.validation === 'object'
    ? payload.validation : {}
  const conf = String(payload.confidence || '').trim().toLowerCase()
  if (band === 'insufficient') return 'insufficient'
  if (!evidence.length && !String(payload.conclusion || '').trim()) return 'insufficient'
  if (!evidence.length && checks.length && checks.every((c) => {
    const s = String(c.status || '').toLowerCase()
    return ['not observed', 'not_observed', 'absent', 'none', ''].includes(s)
  })) return 'not_observed'
  if (band === 'strong' && (flags.direct_evidence || evidence.length)) {
    if (validation && validation.ok === false) return 'suspected'
    return 'confirmed'
  }
  if ((band === 'medium-high' || band === 'medium') && evidence.length) return 'correlated'
  if (conf === 'high' && evidence.length && (band === 'strong' || band === 'medium-high' || band === '')) {
    if (band === 'insufficient') return 'insufficient'
    return band === 'strong' ? 'confirmed' : 'correlated'
  }
  if (evidence.length || String(payload.conclusion || '').trim()) return 'suspected'
  return 'insufficient'
}

function formatEvidenceDuration(start, stop) {
  const lo = Number(start)
  const hi = Number(stop)
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || !(hi > lo)) return ''
  const delta = hi - lo
  if (delta < 1.0) return `${Math.round(delta * 1_000_000)} µs`
  if (delta < 1000.0) return `${delta} s`
  return `${Math.round(delta)}`
}

function evidenceRowFields(ev) {
  const label = String(ev.label || '').trim() || 'item'
  let task = String(ev.task || '').trim()
  let core = String(ev.core || '').trim()
  if (!task) {
    const m = TASK_IN_LABEL_RE.exec(label)
    if (m) task = m[1]
  }
  if (!core) {
    const m = CORE_IN_LABEL_RE.exec(label)
    if (m) core = `Core ${m[1] || m[2]}`
  }
  const slo = Number(ev.start)
  const shi = Number(ev.stop)
  let timeCell = '—'
  let dur = formatEvidenceDuration(ev.start, ev.stop)
  if (Number.isFinite(slo) && Number.isFinite(shi) && shi > slo) {
    timeCell = `jump:${evidenceJumpToken(slo)}–jump:${evidenceJumpToken(shi)}`
  } else if (ev.time != null && Number.isFinite(Number(ev.time))) {
    timeCell = `jump:${evidenceJumpToken(ev.time)}`
  }
  return [timeCell, label, task || '—', core || '—', dur || '—']
}

function formatDirectEvidenceTable(evidence, labels) {
  const rows = (evidence || []).filter(e => e && typeof e === 'object')
  if (!rows.length) return []
  const lines = [
    `| ${labels.col_time || 'Time'} | ${labels.col_event || 'Observed event'} | ${labels.col_task || 'Task'} | ${labels.col_core || 'Core'} | ${labels.col_duration || 'Duration'} |`,
    '| --- | --- | --- | --- | ---: |',
  ]
  for (const ev of rows.slice(0, 20)) {
    const [timeCell, label, task, core, dur] = evidenceRowFields(ev)
    lines.push(`| ${timeCell} | ${label} | ${task} | ${core} | ${dur} |`)
  }
  return lines
}

function coverageCheckRows(coverage, checks, labels) {
  const out = []
  const cov = coverage && typeof coverage === 'object' ? coverage : {}
  for (const c of checks || []) {
    if (!c || typeof c !== 'object') continue
    const name = String(c.label || c.metric || labels.check || 'check')
    const status = localizeEvidenceToken(String(c.status || ''), labels)
    const detail = String(c.detail || '').trim()
    out.push([name, detail ? `${status} — ${detail}` : (status || labels.not_evaluated || 'Not evaluated')])
  }
  if (out.length) return out
  const observed = labels.observed || 'Observed'
  const notObs = labels.not_observed || 'Not observed'
  const insuff = labels.insufficient_evidence || 'Insufficient evidence'
  if (cov.directly_observed != null || cov.timeline_verified != null || cov.metric_verified != null) {
    for (const [key, title] of [
      ['directly_observed', labels.coverage_observed || 'Directly observed'],
      ['timeline_verified', labels.coverage_timeline || 'Timeline verified'],
      ['metric_verified', labels.coverage_metric || 'Metric verified'],
      ['unverified_assumptions', labels.coverage_unverified || 'Unverified assumptions'],
    ]) {
      const val = cov[key]
      if (val == null) continue
      const n = Number(val)
      if (!Number.isFinite(n)) {
        out.push([title, String(val)])
        continue
      }
      if (key === 'unverified_assumptions') out.push([title, n > 0 ? insuff : observed])
      else out.push([title, n > 0 ? observed : notObs])
    }
  }
  return out
}

/** Markdown for Evidence & Validation (panel + conversation log + export). */
export function formatEvidencePanelMarkdown(data, responseLanguage = 'English') {
  if (!data || typeof data !== 'object') return ''
  const labels = evidencePanelLabels(responseLanguage)
  const lines = []
  const details = []

  const statusKey = conclusionStatusFromPayload(data)
  const statusLabel = {
    confirmed: labels.status_confirmed || 'Confirmed',
    correlated: labels.status_correlated || 'Correlated',
    suspected: labels.status_suspected || 'Suspected',
    not_observed: labels.status_not_observed || 'Not observed',
    insufficient: labels.status_insufficient || 'Insufficient data',
  }[statusKey] || (labels.status_suspected || 'Suspected')
  lines.push(`**${labels.status || 'Status'}:** ${statusLabel}`)

  const conclusion = localizeEvidenceToken(String(data.conclusion || '').trim(), labels)
  if (conclusion) {
    lines.push('', `**${labels.finding || 'Finding'}**`, conclusion)
  }
  const subtitle = String(data.subtitle || '').trim()
  if (subtitle && !data.evidence_chain) lines.push(subtitle.slice(0, 320))

  const interpreted = data.interpreted
  if (interpreted && typeof interpreted === 'object'
    && (interpreted.interpreted_question || interpreted.scope)) {
    lines.push('', formatScopeActionLinks(interpreted, labels))
  }
  const experiment = data.experiment
  if (experiment && typeof experiment === 'object' && experiment.result) {
    lines.push('', `**${labels.experiment_result || 'Experiment result'}:** ${experiment.result}`)
    const verdict = String(experiment.verdict || formatExperimentVerdict(experiment)).trim()
    if (verdict) lines.push(`**${verdict}**`)
    lines.push(`[${labels.save_knowledge || 'Save to knowledge'}](${btfExpHref('save', 'all')})`)
  }

  const table = formatDirectEvidenceTable(data.evidence || [], labels)
  if (table.length) {
    lines.push('', `**${labels.direct_evidence || labels.evidence}**`, ...table)
  }
  if (data.evidence_chain) {
    lines.push(
      '',
      `**${labels.interpretation || labels.evidence_chain}**`,
      String(data.evidence_chain),
    )
  }

  const checks = (data.checks || []).filter(c => c && typeof c === 'object')
  const coverage = data.coverage && typeof data.coverage === 'object' ? data.coverage : {}
  let checkRows = coverageCheckRows(coverage, checks, labels)
  if (!checkRows.length) {
    const quality = data.evidence_quality && typeof data.evidence_quality === 'object'
      ? data.evidence_quality : {}
    const qflags = quality.flags && typeof quality.flags === 'object' ? quality.flags : {}
    const yes = labels.observed || 'Observed'
    const no = labels.not_observed || 'Not observed'
    for (const [fk, title] of [
      ['direct_evidence', labels.quality_direct || 'Direct evidence'],
      ['timeline_correlation', labels.quality_timeline || 'Timeline correlation'],
      ['metric_correlation', labels.quality_metric || 'Metric correlation'],
    ]) {
      const val = qflags[fk]
      if (val === true) checkRows.push([title, yes])
      else if (val === false) checkRows.push([title, no])
      else if (val != null) checkRows.push([title, localizeEvidenceToken(String(val), labels)])
    }
  }
  if (checkRows.length) {
    lines.push(
      '',
      `**${labels.checks || labels.checklist || 'Checks'}**`,
      `| ${labels.check_header || 'Check'} | ${labels.status || 'Status'} |`,
      '| --- | --- |',
    )
    for (const [name, cell] of checkRows.slice(0, 12)) {
      lines.push(`| ${name} | ${cell} |`)
    }
  }

  const hypsM = (data.hypotheses_managed || []).filter(h => h && typeof h === 'object')
  const alts = (data.alternatives || []).filter(a => a && typeof a === 'object')
  const altSrc = hypsM.length ? hypsM : alts
  if (altSrc.length) {
    lines.push('', `**${labels.alternatives}**`)
    for (const h of altSrc.slice(0, 8)) {
      const hyp = String(h.hypothesis || '').trim()
      if (!hyp) continue
      const status = localizeEvidenceToken(String(h.status || 'needs_evidence'), labels)
      const why = String(h.why || '').trim()
      const hid = String(h.id || '')
      const actions = hid ? formatHypothesisActionLinks(hid, labels) : ''
      let bit = `- *${hyp}* (${status})`
      if (why) bit += ` — ${why}`
      if (actions) bit += ` ${actions}`
      lines.push(bit)
    }
    if (hypsM.length) {
      lines.push(`[${labels.compare_action || 'Compare hypotheses'}](${btfHypHref('compare', 'all')})`)
    }
  }

  const falsify = data.falsify && typeof data.falsify === 'object' ? data.falsify : {}
  const supporting = (falsify.supporting || []).filter(Boolean)
  const disprove = (falsify.disprove || falsify.would_disprove || []).filter(Boolean)
  if (disprove.length) {
    lines.push('', `**${labels.missing_evidence || 'Missing evidence'}**`)
    disprove.forEach(s => lines.push(`- ${s}`))
  }
  const nxt = String(falsify.next_check || '').trim()
  if (nxt) {
    lines.push('', `**${labels.next_action || labels.next_check || 'Next action'}:** ${nxt}`)
  }

  if (supporting.length) {
    details.push(`**${labels.supporting || 'Supporting evidence'}**`)
    supporting.forEach(s => details.push(`- ${s}`))
  }
  if (data.confidence) {
    const conf = String(data.confidence)
    const showConf = !(
      statusKey === 'insufficient'
      && conf.trim().toLowerCase() === String(labels.high || 'High').toLowerCase()
    )
    if (showConf) {
      details.push(`**${labels.confidence}:** ${localizeEvidenceToken(conf, labels)}`)
    }
  }
  if (data.evidence_quality?.bar) {
    details.push(`**${labels.quality || labels.score}:** ${data.evidence_quality.bar}`)
    details.push(...formatQualityFlagLines(data.evidence_quality, labels))
  } else if (data.evidence_score != null) {
    details.push(`**${labels.score}:** ${String(data.evidence_score_bar || '')}`)
  }
  if (coverage?.bar) {
    details.push(`**${labels.coverage || 'Evidence Coverage'}:** ${coverage.bar}`)
    details.push(...formatCoverageCountLines(coverage, labels))
  }
  const hk = data.historical_knowledge
  if (hk && typeof hk === 'object' && (hk.previous_issue || hk.message || (hk.flags || []).length)) {
    details.push(`**${labels.historical || 'Historical knowledge'}**`)
    if (hk.previous_issue) {
      details.push(`- ${labels.previous_issue || 'Previous issue'}: ${hk.previous_issue}`)
    }
    if (hk.known_fix) details.push(`- ${labels.known_fix || 'Known fix'}: ${hk.known_fix}`)
    if (hk.last_occurrence) {
      details.push(`- ${labels.last_occurrence || 'Last occurrence'}: ${hk.last_occurrence}`)
    }
    for (const flag of (hk.flags || []).slice(0, 4)) details.push(`- ${flag}`)
    const typical = hk.typical && typeof hk.typical === 'object' ? hk.typical : {}
    const current = hk.current && typeof hk.current === 'object' ? hk.current : {}
    for (const key of ['migrations', 'migration_rate', 'blocking', 'wcet']) {
      if (key in typical || key in current) {
        if (typical[key] != null) {
          details.push(`- ${labels.typical_rate || 'Typical rate'} (${key}): ${typical[key]}`)
        }
        if (current[key] != null) {
          details.push(`- ${labels.current_rate || 'Current'} (${key}): ${current[key]}`)
        }
      }
    }
    const msg = String(hk.message || '').trim()
    if (msg && msg !== 'No historical match' && msg !== 'Within historical range') {
      details.push(`- ${msg}`)
    }
  }
  const validation = data.validation
  if (validation && typeof validation === 'object' && validation.ok === false) {
    const n = Number(validation.unverified || (validation.issues || []).length)
    details.push(`**${labels.validation || 'Validation'}:** ${n} ${labels.unverified || 'unverified claims'}`)
    for (const issue of (validation.issues || []).slice(0, 6)) {
      if (issue && typeof issue === 'object') details.push(`- ${issue.kind}: ${issue.detail}`)
    }
    for (const flag of (validation.flags || []).slice(0, 6)) details.push(`- ${flag}`)
  }
  const cost = String(data.cost || '').trim()
  if (cost) details.push(`**${labels.cost || 'Investigation cost'}:** ${cost}`)
  const evo = String(data.confidence_evolution || '').trim()
  if (evo) {
    details.push(`**${labels.evolution || 'Confidence evolution'}**`)
    evo.split('\n').forEach((line) => { if (line.trim()) details.push(`- ${line.trim()}`) })
  }
  const reasons = data.tool_reasons || []
  if (reasons.length) {
    details.push(`**${labels.investigation || 'Investigation'}**`)
    for (const r of reasons) {
      if (!r || typeof r !== 'object') continue
      const tool = String(r.tool || '')
      if (tool) {
        const whyLink = `[${labels.why_action || 'Why?'}](${btfToolHref('why', tool)})`
        details.push(`- ${tool}: ${String(r.reason || '')} ${whyLink}`)
      }
    }
  }
  const chain = data.root_cause_chain || []
  const hyps = data.hypotheses || []
  if (chain.length || hyps.length) {
    const treeSrc = investigationTreeMermaid(chain, hyps)
    if (treeSrc) {
      details.push(`**${labels.tree}**`, '```mermaid', treeSrc.trim(), '```')
    }
  }
  const graphSrc = String(data.graph_mermaid || '').trim()
  if (graphSrc) {
    details.push(`**${labels.graph || 'Evidence graph'}**`, '```mermaid', graphSrc, '```')
  }

  if (details.length) {
    lines.push('', `**▸ ${labels.investigation_details || 'Investigation details'}**`, ...details)
  }
  return lines.join('\n').trim()
}

export function formatInvestigationPlanStatus(plan, responseLanguage = 'English') {
  if (!plan || typeof plan !== 'object') return ''
  const labels = evidencePanelLabels(responseLanguage)
  const steps = (plan.steps || []).filter(s => s && typeof s === 'object')
  const total = steps.length
  const done = steps.filter(s => String(s.status || '') === 'done').length
  let active = steps.find(s => String(s.status || '') === 'active')
  if (!active) active = steps.find(s => String(s.status || '') !== 'done')
  const stepLabel = String(active?.label || active?.id || '').trim()
  const inv = labels.investigation
  if (!total) return inv
  if (done >= total) return `${inv}  ${done}/${total}  ${labels.done}`
  if (stepLabel) return `${inv}  ${done}/${total}  ${stepLabel}`
  return `${inv}  ${done}/${total}`
}

export function evaluateRegression(candidate, baseline, { rules = DEFAULT_REGRESSION_RULES } = {}) {
  const cand = candidate?.metrics ? candidate.metrics : (candidate || {})
  const base = baseline?.metrics ? baseline.metrics : (baseline || {})
  const checks = []
  let failed = false
  for (const rule of rules) {
    const mid = String(rule.metric || '')
    const a = cand[mid]
    const b = base[mid]
    let status = 'skip'
    let detail = 'missing metric'
    let delta = null
    if (a == null || b == null) {
      status = 'skip'
    } else {
      const av = Number(a)
      const bv = Number(b)
      if (!Number.isFinite(av) || !Number.isFinite(bv)) {
        status = 'skip'
        detail = 'non-numeric'
      } else {
        const thr = Number(rule.threshold) || 0
        const mode = String(rule.worse_when || '')
        if (mode === 'increase_pct') {
          delta = bv === 0 ? (av > 0 ? 100 : 0) : 100 * (av - bv) / Math.abs(bv)
          if (delta >= thr) {
            status = 'fail'
            failed = true
            detail = `+${delta.toFixed(1)}% (threshold ${thr}%)`
          } else {
            status = 'pass'
            detail = `${delta >= 0 ? '+' : ''}${delta.toFixed(1)}% (threshold ${thr}%)`
          }
        } else if (mode === 'decrease_abs') {
          delta = bv - av
          if (delta >= thr) {
            status = 'fail'
            failed = true
            detail = `dropped ${delta.toFixed(1)} (threshold ${thr})`
          } else {
            status = 'pass'
            detail = `Δ score ${(av - bv) >= 0 ? '+' : ''}${(av - bv).toFixed(1)} (threshold −${thr})`
          }
        } else if (mode === 'increase_abs') {
          delta = av - bv
          if (delta >= thr) {
            status = 'fail'
            failed = true
            detail = `+${delta.toFixed(1)} (threshold ${thr})`
          } else {
            status = 'pass'
            detail = `${delta >= 0 ? '+' : ''}${delta.toFixed(1)} (threshold ${thr})`
          }
        } else {
          status = 'skip'
          detail = `unknown rule ${mode}`
        }
      }
    }
    checks.push({
      id: rule.id,
      label: rule.label || mid,
      status,
      detail,
      candidate: a,
      baseline: b,
      delta,
    })
  }
  return {
    ok: !failed,
    failed,
    checks,
    summary: failed ? 'REGRESSION DETECTED' : 'No regression vs baseline',
  }
}

export function formatRegressionReport(result, { title = '' } = {}) {
  const lines = [
    `BTF AI / CI Analysis${title ? ` — ${title}` : ''}`,
    '',
    `${result.failed ? '❌' : '✅'} ${result.summary || ''}`,
    '',
  ]
  for (const c of result.checks || []) {
    const mark = { pass: '✓', fail: '✗', skip: '·' }[c.status] || '?'
    lines.push(`${mark} ${c.label}: ${c.detail} (A=${c.candidate}, B=${c.baseline})`)
  }
  lines.push('')
  lines.push(`CI status: ${result.failed ? 'FAILED' : 'PASSED'}`)
  return `${lines.join('\n')}\n`
}

export function appendWcetAnomalyFinding(findings, spikeRows, { ratioThreshold = 5.0 } = {}) {
  const spikes = []
  for (const [name, avgNs, maxNs, runs] of spikeRows || []) {
    if (runs < 5 || !(avgNs > 0)) continue
    const ratio = maxNs / avgNs
    if (ratio >= ratioThreshold) {
      spikes.push(`${name} (Max/Avg=${ratio.toFixed(1)}×, n=${runs})`)
    }
  }
  if (spikes.length) {
    findings.push({
      id: 'wcet_anomaly',
      severity: 'warning',
      title: 'Anomaly: WCET spike vs typical execution',
      text: `Execution Max is much larger than Avg — multimodal or bursty slices: ${spikes.slice(0, 5).join('; ')}. Open Execution Time and jump to Max.`,
      evidence: [],
    })
  }
  return findings
}

export function appendMigrationBurstAnomaly(findings, burstRows, { rateThreshold = 10.0 } = {}) {
  const bursts = []
  for (const [name, rate, nMig] of burstRows || []) {
    if (rate >= rateThreshold && nMig >= 10) {
      bursts.push(`${name} (${rate.toFixed(1)}/s, Migr=${nMig})`)
    }
  }
  if (bursts.length) {
    findings.push({
      id: 'migration_burst_anomaly',
      severity: 'warning',
      title: 'Anomaly: migration burst',
      text: `Migration rate far above thrash heuristic: ${bursts.slice(0, 5).join('; ')}. Check Migration Heatmap for a short thrash window.`,
      evidence: [],
    })
  }
  return findings
}

/** Baseline JSON payload from a trace summary snapshot (snake or camel keys). */
export function snapshotFromSummary(summary, { name = '' } = {}) {
  const s = summary || {}
  return {
    version: 1,
    name: name || '',
    metrics: {
      span_ns: s.span_ns ?? s.spanNs,
      tasks: s.tasks,
      segments: s.segments,
      migrations: s.migrations,
      migrated_tasks: s.migrated_tasks ?? s.migratedTasks,
      load_balance_score: s.load_balance_score ?? s.loadBalanceScore,
      load_balance_sigma: s.load_balance_sigma ?? s.loadBalanceSigma,
      missed_ticks: s.missed_ticks ?? s.missedTicks,
      tick_health: s.tick_health ?? s.tickHealth,
      context_switches: s.context_switches ?? s.contextSwitches,
    },
  }
}

const ANOMALY_ID_BOOST = new Set([
  'wcet_anomaly', 'migration_burst_anomaly', 'thrashing', 'blocking',
  'priority_inversion', 'deadlines', 'missed_ticks', 'tick_health',
  'sync_bounce', 'hot_pairs',
])
const SEV_RANK = { error: 0, warning: 1, info: 2 }

export function detectAnomalies(findings, { limit = 10 } = {}) {
  const lim = Math.max(1, Math.min(40, Number(limit) || 10))
  const items = enrichFindingsWithIds(findings)
  const ranked = items.map((f, i) => {
    const sev = String(f.severity || 'info').toLowerCase()
    const fid = String(f.id || '')
    const boost = ANOMALY_ID_BOOST.has(fid) ? 0 : 1
    return [SEV_RANK[sev] ?? 3, boost, i, f]
  })
  ranked.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2])
  const anomalies = []
  const counts = { critical: 0, warning: 0, info: 0 }
  ranked.slice(0, lim).forEach((row, idx) => {
    const f = row[3]
    const sev = String(f.severity || 'info').toLowerCase()
    const band = sev === 'error' ? 'critical' : (sev === 'warning' ? 'warning' : 'info')
    counts[band] = (counts[band] || 0) + 1
    anomalies.push({
      rank: idx + 1,
      band,
      severity: sev,
      id: f.id,
      title: f.title,
      text: f.text,
      task: f.task || guessTaskName(String(f.text || '')),
      evidence: [...(f.evidence || [])],
    })
  })
  return {
    ok: true,
    message: (
      `${anomalies.length} ranked anomal${anomalies.length === 1 ? 'y' : 'ies'} `
      + `(critical=${counts.critical}, warning=${counts.warning}, info=${counts.info})`
    ),
    anomalies,
    counts,
    total_findings: items.length,
  }
}

const MUTEX_ADDR_RE = /mutex\D{0,12}(0x[0-9a-fA-F]+)/i

function piContextFromFindings(findings, low, mediums) {
  const exclude = new Set([String(low || '').toLowerCase(), ...(mediums || []).map(m => String(m || '').toLowerCase())])
  for (const f of findings || []) {
    const blob = `${f.title || ''} ${f.text || ''}`
    if (!blob.toLowerCase().includes(String(low || '').toLowerCase())) continue
    let mutex = ''
    const m = MUTEX_ADDR_RE.exec(blob)
    if (m) mutex = m[1]
    let high = ''
    for (const tok of blob.match(/\b[A-Za-z_]\w*\[[0-9]+\]/g) || []) {
      if (!exclude.has(tok.toLowerCase())) { high = tok; break }
    }
    if (mutex || high) return [mutex, high]
  }
  return ['', '']
}

export function detectPriorityInversion(episodes, findings = null, {
  task = '', window = null,
} = {}) {
  const taskS = String(task || '').trim()
  let rows = (episodes || []).filter(e => e && typeof e === 'object')

  const rowMatchesTask = (e) => {
    if (String(e.task || '').trim().toLowerCase() === taskS.toLowerCase()) return true
    for (const m of e.medium_tasks || []) {
      const label = (m && typeof m === 'object') ? m.label : m
      if (String(label || '').trim().toLowerCase() === taskS.toLowerCase()) return true
    }
    return false
  }
  if (taskS) rows = rows.filter(rowMatchesTask)

  let win = null
  if (window != null) {
    const w = Number(window)
    if (Number.isFinite(w)) win = w
  }
  const duration = (e) => {
    if (e.duration != null) {
      const d = Number(e.duration)
      return Number.isFinite(d) ? d : null
    }
    if (e.start == null || e.stop == null) return null
    const d = Number(e.stop) - Number(e.start)
    return Number.isFinite(d) ? d : null
  }
  if (win && win > 0) {
    rows = rows.filter(e => { const d = duration(e); return d == null || d >= win })
  }

  const suspects = rows.filter(e => e.inversion_suspect)
  const items = findings ? enrichFindingsWithIds(findings) : []
  const inversions = []
  for (const e of suspects) {
    const lowLabel = String(e.task || taskS || '').trim() || '?'
    const mediums = (e.medium_tasks || [])
      .map(m => String((m && typeof m === 'object') ? m.label : m).trim())
      .filter(Boolean)
    const [mutex, high] = piContextFromFindings(items, lowLabel, mediums)
    const start = e.start
    const stop = e.stop
    let dur = e.duration
    if (dur == null && start != null && stop != null) {
      const d = Number(stop) - Number(start)
      dur = Number.isFinite(d) ? d : null
    }
    inversions.push({
      high,
      medium: mediums[0] || '',
      medium_tasks: mediums,
      low: lowLabel,
      mutex,
      time: start,
      duration: dur,
      base_pri: e.base_pri,
      peak_pri: e.peak_pri,
      pattern: e.pattern || '',
    })
  }
  inversions.sort((a, b) => {
    const at = a.time == null, bt = b.time == null
    if (at !== bt) return at ? 1 : -1
    return (a.time ?? 0) - (b.time ?? 0)
  })
  let confidence
  if (!rows.length) confidence = 'Low'
  else if (inversions.some(inv => inv.high && inv.mutex)) confidence = 'High'
  else if (inversions.length) confidence = 'Medium'
  else confidence = 'Low'
  const focusTask = taskS || (inversions.length ? inversions[0].low : '')
  return {
    ok: true,
    message: inversions.length
      ? `${inversions.length} priority inversion(s) detected`
      : 'No priority inversion suspects in scope',
    task: taskS,
    inversions,
    count: inversions.length,
    confidence,
    suggested_tools: focusTask ? [
      {
        name: 'query_raw_metric',
        arguments: { task: focusTask, metric: 'priority_inheritance' },
        reason: 'Inspect raw PI boost episodes',
      },
      {
        name: 'correlate_events',
        arguments: { task: focusTask },
        reason: 'Cross-task timeline around the inversion',
      },
    ] : [],
  }
}

const STOPWORDS = new Set([
  'the', 'a', 'an', 'and', 'or', 'of', 'to', 'in', 'on', 'for', 'with',
  'is', 'are', 'this', 'that', 'at', 'by', 'from', 'into', 'than', 'was',
  'were', 'has', 'have', 'had', 'its', "it's", 'task', 'tasks',
])

const RELATED_METRIC_KEYWORDS = {
  priority_inheritance: ['inversion', 'inherit', 'priority', 'l/m/h', 'mutex', 'boost'],
  execution: ['wcet', 'cpu', 'execution', 'spike', 'slice'],
  migrations: ['migrat', 'thrash', 'bounc', 'core'],
  blocking: ['block', 'latency', 'wait', 'dispatch'],
  sync: ['mutex', 'semaphore', 'lock', 'sync'],
  findings: [],
}

function findingKeywords(f) {
  const blob = `${f.title || ''} ${f.text || ''}`.toLowerCase()
  const tokens = blob.match(/[a-z][a-z0-9_]{3,}/g) || []
  return new Set(tokens.filter(t => !STOPWORDS.has(t)))
}

function findingEvidenceTimes(f) {
  const times = []
  for (const ev of f.evidence || []) {
    if (ev && typeof ev === 'object' && ev.time != null) {
      const t = Number(ev.time)
      if (Number.isFinite(t)) times.push(t)
    }
  }
  return times
}

export function findRelatedFindings(findings, {
  findingId = '', task = '', metric = '', window = null, limit = 10,
} = {}) {
  const lim = Math.max(1, Math.min(40, Number(limit) || 10))
  const items = enrichFindingsWithIds(findings)
  if (!items.length) {
    return {
      ok: false, message: 'No Analysis Findings in scope', focus: null, related: [], count: 0,
    }
  }
  const focus = findingId ? resolveFinding(items, findingId) : null
  const taskS = String(task || '').trim()
  const metricKey = String(metric || '').trim().toLowerCase()
  const keywords = new Set(RELATED_METRIC_KEYWORDS[metricKey] || [])
  let focusTask = ''
  let focusKeywords = new Set()
  let focusTimes = []
  if (focus) {
    focusTask = String(focus.task || guessTaskName(String(focus.text || ''))).trim()
    focusKeywords = findingKeywords(focus)
    focusTimes = findingEvidenceTimes(focus)
  }
  let win = null
  if (window != null) {
    const w = Number(window)
    if (Number.isFinite(w)) win = w
  }
  const scored = []
  for (const f of items) {
    if (focus && f.id === focus.id) continue
    const reasons = []
    let score = 0
    const fTask = String(f.task || guessTaskName(String(f.text || ''))).trim()
    if (taskS && fTask && fTask.toLowerCase() === taskS.toLowerCase()) {
      score += 2.0
      reasons.push(`shares task ${fTask}`)
    }
    if (focusTask && fTask && fTask.toLowerCase() === focusTask.toLowerCase()
      && !(taskS && fTask.toLowerCase() === taskS.toLowerCase())) {
      score += 2.0
      reasons.push(`shares task ${fTask}`)
    }
    if (keywords.size) {
      const blob = `${f.title} ${f.text}`.toLowerCase()
      const hits = [...keywords].filter(k => blob.includes(k)).sort()
      if (hits.length) {
        score += 1.0 * hits.length
        reasons.push(`mentions ${hits.join(', ')}`)
      }
    }
    if (focusKeywords.size) {
      const shared = [...focusKeywords].filter(k => findingKeywords(f).has(k)).sort()
      if (shared.length) {
        score += 0.5 * shared.length
        reasons.push(`shared keyword(s): ${shared.join(', ')}`)
      }
    }
    if (win && win > 0 && focusTimes.length) {
      const fTimes = findingEvidenceTimes(f)
      if (focusTimes.some(t => fTimes.some(ft => Math.abs(t - ft) <= win))) {
        score += 1.0
        reasons.push('within time window')
      }
    }
    if (focus && !reasons.length) {
      const fRank = SEV_RANK[String(f.severity || 'info').toLowerCase()] ?? 3
      const focusRank = SEV_RANK[String(focus.severity || 'info').toLowerCase()] ?? 3
      if (Math.abs(fRank - focusRank) <= 1) {
        score += 0.25
        reasons.push('adjacent severity')
      }
    }
    if (score > 0) scored.push([score, f, reasons])
  }
  scored.sort((a, b) => b[0] - a[0])
  const related = scored.slice(0, lim).map(([score, f, reasons]) => ({
    id: f.id,
    title: f.title,
    severity: f.severity,
    task: f.task || guessTaskName(String(f.text || '')),
    score: Math.round(score * 100) / 100,
    reasons,
  }))
  return {
    ok: true,
    message: `${related.length} related finding(s)`
      + (focus ? ` for ${focus.id}` : ''),
    focus: focus ? { id: focus.id, title: focus.title } : null,
    related,
    count: related.length,
  }
}

const COMPARE_TASK_METRIC_FIELDS = {
  execution: ['count', 'total', 'max', 'mean'],
  blocking: ['count', 'total', 'max'],
  migrations: ['count'],
  priority_inheritance: ['count'],
}

export function compareTasksMetrics(taskA, taskB, dataA, dataB, { metrics = null } = {}) {
  let wanted = (metrics || Object.keys(COMPARE_TASK_METRIC_FIELDS))
    .filter(m => COMPARE_TASK_METRIC_FIELDS[m])
  if (!wanted.length) wanted = Object.keys(COMPARE_TASK_METRIC_FIELDS)
  const da = dataA || {}
  const db = dataB || {}
  const rows = []
  for (const metric of wanted) {
    const ma = (da[metric] && typeof da[metric] === 'object') ? da[metric] : {}
    const mb = (db[metric] && typeof db[metric] === 'object') ? db[metric] : {}
    if (!Object.keys(ma).length && !Object.keys(mb).length) continue
    for (const field of COMPARE_TASK_METRIC_FIELDS[metric]) {
      const va = ma[field]
      const vb = mb[field]
      let delta = null
      let pct = null
      if (typeof va === 'number' && typeof vb === 'number') {
        delta = va - vb
        pct = vb ? (100.0 * delta / vb) : (va ? 100.0 : 0.0)
      }
      rows.push({
        metric,
        field,
        a: va ?? null,
        b: vb ?? null,
        delta,
        delta_pct: pct != null ? Math.round(pct * 10) / 10 : null,
      })
    }
  }
  const ranked = rows.filter(r => r.delta_pct != null).sort((a, b) => Math.abs(b.delta_pct) - Math.abs(a.delta_pct))
  const primary = ranked.length ? ranked[0] : null
  let confidence
  if (primary && Math.abs(primary.delta_pct || 0) >= 25) confidence = 'High'
  else if (primary) confidence = 'Medium'
  else confidence = 'Low'
  return {
    ok: true,
    message: `Compared ${taskA} vs ${taskB} across ${wanted.length} metric group(s)`,
    task_a: taskA,
    task_b: taskB,
    rows,
    primary_difference: primary,
    confidence,
    suggested_tools: [
      { name: 'correlate_events', arguments: { task: taskA }, reason: `Timeline for ${taskA}` },
      { name: 'correlate_events', arguments: { task: taskB }, reason: `Timeline for ${taskB}` },
    ],
  }
}

const MERMAID_LABEL_STRIP_RE = /["[\]{}()|]/g

function mermaidSafeLabel(text, limit = 96) {
  const cleaned = String(text ?? '').replace(/\n/g, ' ').replace(MERMAID_LABEL_STRIP_RE, '').trim()
    .replace(/\s+/g, ' ')
  return (cleaned || 'Step').slice(0, limit)
}

/**
 * Render a root-cause chain + hypotheses as a mermaid `graph TD` snippet.
 * Kept in sync with btf_viewer_pkg/ai_investigation.py investigation_tree_mermaid.
 */
export function investigationTreeMermaid(chain = [], hypotheses = []) {
  const chainItems = (chain || []).filter(c => c && typeof c === 'object')
  const hypItems = (hypotheses || []).filter(h => h && typeof h === 'object')
  if (!chainItems.length && !hypItems.length) return ''
  const lines = ['graph TD']
  const nodeIds = []
  chainItems.forEach((step, i) => {
    const nid = `S${i}`
    const label = mermaidLabelWithTime(step.label || `Step ${i + 1}`, step.time)
    lines.push(`${nid}[${label}]`)
    nodeIds.push(nid)
  })
  for (let i = 1; i < nodeIds.length; i++) {
    lines.push(`${nodeIds[i - 1]} --> ${nodeIds[i]}`)
  }
  const anchor = nodeIds[0] || null
  hypItems.forEach((h, j) => {
    const nid = `H${j}`
    const label = mermaidSafeLabel(h.hypothesis || `Hypothesis ${j + 1}`)
    lines.push(`${nid}(${label})`)
    if (anchor) lines.push(`${anchor} --> ${nid}`)
  })
  return lines.join('\n')
}

/** Text meter for the AI Evidence Score, e.g. `████████░░ 82%`. */
export function evidenceScoreBar(score, width = 10) {
  const pct = Math.max(0, Math.min(100, Math.round(Number(score) || 0)))
  const filled = Math.max(0, Math.min(width, Math.round(width * pct / 100)))
  return '█'.repeat(filled) + '░'.repeat(width - filled) + ` ${pct}%`
}

/**
 * Heuristic 0-100 "AI Evidence Score" for an investigation conclusion.
 * NOT a statistical confidence interval — see
 * btf_viewer_pkg/ai_investigation.py compute_evidence_score for the factor
 * list (kept in sync here).
 */
export function computeEvidenceScore(evidence = [], {
  alternatives = [], evidenceChain = '', checks = [],
} = {}) {
  const ev = (evidence || []).filter(e => e && typeof e === 'object')
  const alts = (alternatives || []).filter(a => a && typeof a === 'object')
  const chks = (checks || []).filter(c => c && typeof c === 'object')
  const chainText = String(evidenceChain || '').trim()
  const breakdown = []
  let score = 0

  const hasTimes = ev.some(e => e.time != null)
  if (hasTimes) {
    score += 40
    breakdown.push({ label: 'Direct evidence times (jump:TIME)', delta: 40 })
  }

  const kinds = new Set()
  for (const e of ev) {
    const label = String(e.label || '')
    if (label.includes(':')) {
      const kind = label.split(':', 1)[0].trim().toLowerCase()
      if (kind) kinds.add(kind)
    }
  }
  const hasTimelineCorr = kinds.size >= 2 || !!chainText
  if (hasTimelineCorr) {
    score += 25
    breakdown.push({ label: 'Timeline correlation', delta: 25 })
  }

  if (chks.length) {
    score += 15
    breakdown.push({ label: 'Metric correlation', delta: 15 })
  }

  const untested = alts.filter(a => {
    const s = String(a.status || '').toLowerCase()
    return (
      s === 'untested'
      || s === 'need_evidence'
      || s === 'needs_evidence'
      || s === ''
    )
  })
  if (untested.length) {
    const penalty = Math.min(15, 5 * untested.length)
    score -= penalty
    breakdown.push({ label: `${untested.length} alternative(s) untested`, delta: -penalty })
  }

  if (!ev.length && !chainText) {
    score -= 10
    breakdown.push({ label: 'Missing direct evidence', delta: -10 })
  }

  score = Math.max(0, Math.min(100, score))
  const quality = evidenceQualityFromScore(score, breakdown)
  return {
    score,
    label: 'AI Evidence Score — heuristic',
    bar: evidenceScoreBar(score),
    breakdown,
    quality,
  }
}

export function buildRootCauseChain(finding) {
  if (!finding) return []
  const title = String(finding.title || '')
  const text = String(finding.text || '')
  const blob = `${title} ${text}`.toLowerCase()
  const task = String(finding.task || '') || guessTaskName(text)
  const steps = []
  const add = (label, detail = '', kind = 'step') => {
    steps.push({ kind, label, detail, task })
  }
  add(`Finding: ${title || finding.id || 'unknown'}`, text.slice(0, 240), 'finding')
  if (task) add(`Focus task ${task}`, 'Extracted from finding text', 'task')
  if (/block|latency|dispatch/.test(blob)) {
    add('Off-CPU / blocking gap', 'Inspect Blocking Time + STI wait')
    add('Synchronization hold', 'Check mutex/semaphore owner')
  }
  if (/inversion|l\/m\/h|inherit/.test(blob)) {
    add('Priority relationship', 'L/M/H or inherit episode')
    add('Likely priority inversion', 'High confidence if PI episodes align', 'cause')
  }
  if (/migrat|thrash|bounc/.test(blob)) {
    add('Core migration / thrash', 'Corridor + migration rate')
    add('Likely affinity / lock bounce', '', 'cause')
  }
  if (/wcet|spike|execution|cpu/.test(blob)) {
    add('Execution / WCET spike', 'Jump to Max slice')
    add('Likely long critical section or preemption stretch', '', 'cause')
  }
  if (/deadline|budget/.test(blob)) {
    add('Deadline / budget breach', '', 'cause')
  }
  if (/tick|missed/.test(blob)) {
    add('Tick health / missed ticks', '', 'cause')
  }
  if (!steps.some(s => s.kind === 'cause')) {
    add('Needs metric drill-down', 'Call correlate_events / query_raw_metric', 'cause')
  }
  add('Verify on timeline', 'set_cursors + zoom_to_range + highlight_task', 'ui')
  return steps
}

export function buildCorrelationTimeline(events, {
  task = '', aroundTime = null, window = 0, limit = 40,
} = {}) {
  const lim = Math.max(1, Math.min(80, Number(limit) || 40))
  let rows = []
  for (const ev of events || []) {
    if (!ev || typeof ev !== 'object') continue
    const t = Number(ev.time)
    if (!Number.isFinite(t)) continue
    rows.push({
      time: t,
      kind: String(ev.kind || ev.metric || 'event'),
      detail: String(ev.detail || ev.note || ev.event || ''),
      task: String(ev.task || task || ''),
      core: ev.core || '',
    })
  }
  rows.sort((a, b) => a.time - b.time)
  if (aroundTime != null && window && window > 0) {
    const lo = Number(aroundTime) - Number(window)
    const hi = Number(aroundTime) + Number(window)
    rows = rows.filter(r => r.time >= lo && r.time <= hi)
  }
  const truncated = rows.length > lim
  rows = rows.slice(0, lim)
  const kinds = new Set(rows.map(r => r.kind))
  let score = 0
  if (rows.length) {
    score = Math.min(0.99, 0.35 + 0.12 * Math.max(0, kinds.size - 1) + 0.01 * Math.min(40, rows.length))
  }
  const suggested = []
  if (rows.length) {
    const t0 = rows[0].time
    const t1 = rows[rows.length - 1].time
    suggested.push({
      name: 'set_cursors',
      arguments: { timestamps: t1 !== t0 ? [t0, t1] : [t0] },
      reason: 'Bracket correlated window',
    })
    if (t1 > t0) {
      const pad = Math.max(1.0, (t1 - t0) * 0.05)
      suggested.push({
        name: 'zoom_to_range',
        arguments: { start_time: t0 - pad, end_time: t1 + pad },
        reason: 'Focus correlated range',
      })
    }
    if (task) {
      suggested.push({
        name: 'highlight_task',
        arguments: { task_name_or_id: task },
        reason: 'Highlight focus task',
      })
    }
  }
  return {
    ok: true,
    message: (
      `${rows.length} correlated event(s) for ${task || 'scope'}`
      + (truncated ? ' (truncated)' : '')
    ),
    task,
    around_time: aroundTime,
    window,
    events: rows,
    correlation: Math.round(score * 100) / 100,
    kinds: [...kinds].sort(),
    truncated,
    suggested_tools: suggested,
  }
}

const REGRESSION_TYPE_BY_METRIC = {
  migrations: 'migration',
  migrated_tasks: 'migration',
  load_balance_score: 'load_balance',
  load_balance_sigma: 'load_balance',
  missed_ticks: 'scheduling',
  tick_health: 'scheduling',
  context_switches: 'scheduling',
  blocking_max_us: 'synchronization',
  response_us: 'synchronization',
  wcet_us: 'execution',
  exec_max_us: 'execution',
}

const REGRESSION_TYPE_KEYWORDS = [
  ['migrat', 'migration'],
  ['load_balance', 'load_balance'],
  ['load balance', 'load_balance'],
  ['tick', 'scheduling'],
  ['context_switch', 'scheduling'],
  ['mutex', 'synchronization'],
  ['block', 'synchronization'],
  ['inversion', 'synchronization'],
  ['inherit', 'synchronization'],
  ['wcet', 'execution'],
  ['exec', 'execution'],
  ['cpu', 'execution'],
]

export function classifyRegressionType(checks = [], primary = null) {
  const typeFor = (check) => {
    if (!check || typeof check !== 'object') return ''
    const mid = String(check.id || '').trim().toLowerCase()
    if (REGRESSION_TYPE_BY_METRIC[mid]) return REGRESSION_TYPE_BY_METRIC[mid]
    const blob = `${check.id || ''} ${check.label || ''}`.toLowerCase()
    for (const [kw, rtype] of REGRESSION_TYPE_KEYWORDS) {
      if (blob.includes(kw)) return rtype
    }
    return ''
  }
  let rtype = typeFor(primary)
  if (rtype) return rtype
  for (const c of checks || []) {
    if (c && c.status === 'fail') {
      rtype = typeFor(c)
      if (rtype) return rtype
    }
  }
  return 'unknown'
}

export function comparePerformanceMetrics(candidate, baseline, {
  labelA = 'A', labelB = 'B',
} = {}) {
  const snapA = candidate && 'metrics' in (candidate || {})
    ? candidate
    : { metrics: { ...(candidate || {}) } }
  const snapB = baseline && 'metrics' in (baseline || {})
    ? baseline
    : { metrics: { ...(baseline || {}) } }
  const result = evaluateRegression(snapA, snapB)
  let primary = (result.checks || []).find(c => c.status === 'fail') || null
  if (!primary) primary = (result.checks || []).find(c => c.status === 'pass') || null
  const confidence = primary && primary.status === 'fail'
    ? 'High'
    : (primary ? 'Medium' : 'Low')
  const regressionType = classifyRegressionType(result.checks, primary)
  return {
    ok: true,
    message: String(result.summary || 'compared'),
    label_a: labelA,
    label_b: labelB,
    failed: !!result.failed,
    checks: result.checks || [],
    primary_regression: primary,
    confidence,
    regression_type: regressionType,
    evidence_quality: primary ? 'Directly observed' : 'Insufficient evidence',
    suggested_tools: [
      { name: 'investigate', arguments: {}, reason: 'Drill into top finding' },
      { name: 'correlate_events', arguments: {}, reason: 'Timeline correlation' },
    ],
    report: formatRegressionReport(result, { title: `${labelA} vs ${labelB}` }),
  }
}

const REPORT_TYPES = new Set([
  'executive', 'performance', 'root_cause', 'regression',
  'optimization', 'bug', 'ci',
])

function openStatisticsNextCheck(finding) {
  if (!finding || typeof finding !== 'object') return ''
  const inspect = String(finding.inspect || '').trim()
  const task = String(finding.task || '').trim()
  const fid = String(finding.id || '').trim()
  // Lockstep with workflowAnalysis FINDING_SECTION_MAP / config FINDING_SECTION_MAP
  // (inline to avoid circular import with workflowAnalysis.js).
  const SECTION_MAP = {
    load_imbalance: 'cores',
    load_balance_ok: 'cores',
    load_balance_moderate: 'cores',
    top_cpu: 'tasks',
    exec_max: 'exec',
    blocking: 'block',
    priority_inversion: 'priority',
    thrashing: 'migrations',
    hot_pairs: 'core_pairs',
    deadlines: 'deadline',
    tick_health: 'health',
    missed_ticks: 'health',
    sync_bounce: 'sync',
    sync_issues: 'sync',
    migration_burst_anomaly: 'migrations',
    wcet_anomaly: 'exec',
  }
  const sid = String(SECTION_MAP[fid] || '').trim()
  let label = ''
  if (inspect && task) {
    const section = inspect.split(' (', 2)[0].trim() || inspect
    label = `Open ${section} → ${task}`
  } else if (inspect) {
    const section = inspect.split(' (', 2)[0].trim() || inspect
    label = `Open ${section}`
  } else if (task) {
    label = `Open Statistics → ${task}`
  } else {
    return ''
  }
  if (sid) return `[${label}](btfstats:section/${sid})`
  return label
}

export function generateStructuredReport(findings, {
  reportType = 'performance', focusId = '', compare = null,
} = {}) {
  let rtype = String(reportType || 'performance').trim().toLowerCase().replace(/-/g, '_')
  if (!REPORT_TYPES.has(rtype)) rtype = 'performance'
  const items = enrichFindingsWithIds(findings)
  const focus = items.length ? resolveFinding(items, focusId) : null
  const anomalies = detectAnomalies(items, { limit: 8 })
  const chain = focus ? buildRootCauseChain(focus) : []
  const titleMap = {
    executive: 'Executive summary',
    performance: 'Performance analysis',
    root_cause: 'Root-cause analysis',
    regression: 'Regression report',
    optimization: 'Optimization report',
    bug: 'Bug report',
    ci: 'CI report',
  }
  const heading = titleMap[rtype] || 'Performance analysis'
  const lines = [`# ${heading}`, '']
  if (focus) {
    lines.push(
      '## Summary',
      `**${focus.title}** (${focus.severity})`,
      '',
      String(focus.text || ''),
      '',
    )
  } else {
    lines.push('## Summary', 'No single focus finding; ranked anomalies below.', '')
  }
  lines.push('## Evidence')
  for (const a of (anomalies.anomalies || []).slice(0, 6)) {
    lines.push(`${a.rank}. [${a.band}] ${a.title} — ${a.id}`)
  }
  lines.push('')
  if (chain.length) {
    lines.push('## Root cause chain')
    for (const step of chain) {
      lines.push(`- **${step.label}**: ${step.detail || ''}`.trimEnd())
    }
    lines.push('')
  }
  if (compare) {
    lines.push('## Comparison')
    lines.push(String(compare.report || compare.message || '').replace(/\s+$/, ''))
    lines.push('')
    const primary = compare.primary_regression
    if (primary) {
      lines.push(
        `Primary: ${primary.label} — ${primary.detail} `
        + `(confidence ${compare.confidence})`,
      )
      lines.push('')
    }
  }
  lines.push(
    '## Confidence',
    'Medium — structured from Analysis Findings; confirm with tool evidence.',
    '',
    '## Next check',
  )
  const openLine = openStatisticsNextCheck(focus)
  if (openLine) lines.push(`- ${openLine}`)
  lines.push(
    '- Place cursors / zoom on the worst episode (`set_cursors`, `zoom_to_range`).',
    '- Highlight the focus task and verify on the timeline.',
    '- Re-run Trace Compare or `compare_performance` after a fix.',
    '',
  )
  const md = lines.join('\n')
  return {
    ok: true,
    message: `${heading} (${items.length} findings)`,
    report_type: rtype,
    title: heading,
    markdown: md,
    sections: {
      summary: (focus || {}).text || '',
      findings: anomalies.anomalies || [],
      root_cause_chain: chain,
      compare,
    },
    suggested_tools: [
      {
        name: 'export_report',
        arguments: { format: 'html' },
        reason: 'Save HTML with diagrams and GUI state',
      },
    ],
  }
}

// --- Phase 2 / 3 helpers -------------------------------------------------

const BOOKMARK_KINDS = {
  root_cause: ['🔴', 'Root cause'],
  evidence: ['🟠', 'Important evidence'],
  correlated: ['🟡', 'Correlated event'],
  reference: ['🟢', 'Normal reference'],
}

export function checkTaskBudgets(metricsByTask, budgets = null) {
  const budMap = { ...(budgets || {}) }
  const rows = []
  let violations = 0
  for (const item of metricsByTask || []) {
    if (!item || typeof item !== 'object') continue
    const task = String(item.task || '').trim()
    if (!task) continue
    const bud = budMap[task] || budMap[task.split('[', 1)[0]] || {}
    const checks = []
    for (const [key, label] of [
      ['wcet_us', 'WCET'],
      ['response_us', 'Response'],
      ['deadline_us', 'Deadline'],
      ['exec_max_us', 'Exec Max'],
      ['blocking_max_us', 'Blocking Max'],
    ]) {
      const measured = item[key]
      let limit = key in bud ? bud[key] : bud[key.replace('_max', '')]
      if (measured == null) continue
      const mval = Number(measured)
      if (!Number.isFinite(mval)) continue
      let status = 'info'
      let detail = `${mval} µs`
      if (limit != null) {
        const lim = Number(limit)
        if (Number.isFinite(lim) && lim > 0) {
          const pct = 100.0 * (mval - lim) / lim
          if (mval > lim) {
            status = 'fail'
            violations += 1
            detail = `${mval} / ${lim} µs (+${pct.toFixed(1)}%)`
          } else {
            status = 'pass'
            detail = `${mval} / ${lim} µs`
          }
        }
      }
      checks.push({ metric: key, label, status, detail })
    }
    if (checks.length) rows.push({ task, checks })
  }
  return {
    ok: true,
    message: rows.length
      ? `${rows.length} task budget row(s), ${violations} violation(s)`
      : 'No budget metrics to check',
    tasks: rows,
    violations,
    budgets_applied: Object.keys(budMap).length > 0,
  }
}

export function buildOptimizationAdvice(findings, { limit = 5 } = {}) {
  const lim = Math.max(1, Math.min(20, Number(limit) || 5))
  const items = enrichFindingsWithIds(findings)
  const ranked = detectAnomalies(items, { limit: lim })
  const ideas = []
  for (const a of ranked.anomalies || []) {
    const blob = `${a.title} ${a.text}`.toLowerCase()
    const task = a.task || ''
    if (/migrat|thrash|bounc/.test(blob)) {
      ideas.push({
        title: `Pin / affinity for ${task || 'hot migrator'}`,
        expected_impact: 'High',
        risk: 'Low',
        why: a.text || a.title,
        evidence_finding: a.id,
      })
    } else if (/inversion|mutex|block/.test(blob)) {
      ideas.push({
        title: 'Reduce shared-lock contention / shorten critical section',
        expected_impact: 'High',
        risk: 'Medium',
        why: a.text || a.title,
        evidence_finding: a.id,
      })
    } else if (/wcet|spike|cpu/.test(blob)) {
      ideas.push({
        title: `Profile and trim long slices on ${task || 'hot task'}`,
        expected_impact: 'Medium',
        risk: 'Medium',
        why: a.text || a.title,
        evidence_finding: a.id,
      })
    } else if (/load|balance/.test(blob)) {
      ideas.push({
        title: 'Rebalance task placement across cores',
        expected_impact: 'Medium',
        risk: 'Low',
        why: a.text || a.title,
        evidence_finding: a.id,
      })
    } else {
      ideas.push({
        title: `Investigate ${a.title}`,
        expected_impact: 'Medium',
        risk: 'Low',
        why: a.text || '',
        evidence_finding: a.id,
      })
    }
    if (ideas.length >= lim) break
  }
  return {
    ok: true,
    message: `${ideas.length} optimization idea(s)`,
    recommendations: ideas,
    disclaimer: 'Simulation / estimate — not measured behavior',
  }
}

const REGRESSION_CLASSIFICATION_MAP = {
  migrations: 'thrashing',
  migrated_tasks: 'thrashing',
  load_balance: 'load_imbalance',
  missed_ticks: 'tick_health',
}

const REGRESSION_CLASSIFICATION_LABELS = {
  thrashing: 'Core thrashing / migration regression',
  load_imbalance: 'Load balance regression',
  tick_health: 'Tick health regression',
  unclassified: 'Unclassified regression',
  none: 'No regression',
}

export function classifyRegression(primary) {
  if (!primary) return 'none'
  return REGRESSION_CLASSIFICATION_MAP[String(primary.id || '')] || 'unclassified'
}

export function explainRegression(compare, findings = null) {
  const cmp = { ...(compare || {}) }
  const primary = cmp.primary_regression || {}
  const failed = !!cmp.failed
  const labelA = cmp.label_a || 'A'
  const labelB = cmp.label_b || 'B'
  const classification = classifyRegression(failed ? primary : null)
  const regressionType = String(
    cmp.regression_type || classifyRegressionType(cmp.checks, primary),
  )
  let causalChain = []
  if (primary && (primary.label || primary.detail)) {
    causalChain = buildRootCauseChain({
      id: 'regression_primary',
      title: `Regression: ${primary.label}`,
      text: `${primary.label} changed — ${primary.detail}`,
      severity: failed ? 'error' : 'info',
    })
  }
  const lines = [
    `# Regression explanation — ${labelA} vs ${labelB}`,
    '',
    String(cmp.message || (failed ? 'REGRESSION DETECTED' : 'No regression')),
    '',
  ]
  if (primary && (primary.label || primary.detail)) {
    lines.push(
      '## Primary change',
      `**${primary.label}**: ${primary.detail}`,
      `Candidate=${primary.candidate}, Baseline=${primary.baseline}`,
      '',
    )
  }
  lines.push('## Supporting checks')
  for (const c of cmp.checks || []) {
    const mark = { pass: '✓', fail: '✗', skip: '·' }[c.status] || '?'
    lines.push(`- ${mark} ${c.label}: ${c.detail}`)
  }
  lines.push('')
  lines.push(
    '## Classification',
    REGRESSION_CLASSIFICATION_LABELS[classification] || 'Unclassified regression',
    '',
  )
  if (causalChain.length) {
    lines.push('## Causal chain')
    for (const step of causalChain) {
      lines.push(`- **${step.label}**: ${step.detail || ''}`.trimEnd())
    }
    lines.push('')
  }
  const anomalies = findings
    ? detectAnomalies(findings, { limit: 5 })
    : { anomalies: [] }
  if (anomalies.anomalies?.length) {
    lines.push('## Related findings on candidate')
    for (const a of anomalies.anomalies.slice(0, 5)) {
      lines.push(`- [${a.band}] ${a.title} (\`${a.id}\`)`)
    }
    lines.push('')
  }
  const conf = cmp.confidence || (failed ? 'High' : 'Medium')
  lines.push(
    '## Confidence',
    `${conf} — ${cmp.evidence_quality || 'Directly observed metric deltas'}`,
    '',
  )
  const suggestedTools = [
    { name: 'correlate_events', arguments: {}, reason: 'Timeline for worst metric' },
    { name: 'investigate', arguments: {}, reason: 'Root-cause chain' },
  ]
  if (classification === 'thrashing') {
    suggestedTools.push({
      name: 'optimize_experiment', arguments: {},
      reason: 'Rank pin / affinity candidates for the thrashing task',
    })
  } else if (classification === 'load_imbalance') {
    suggestedTools.push({
      name: 'analyze_traces', arguments: {},
      reason: 'Rank all loaded traces by scheduling behavior',
    })
  } else if (classification === 'tick_health') {
    suggestedTools.push({
      name: 'check_budget', arguments: {},
      reason: 'Verify WCET/response/deadline budgets after tick regressions',
    })
  }
  return {
    ok: true,
    message: failed ? 'Regression explained' : 'No regression to explain',
    failed,
    markdown: lines.join('\n'),
    primary_regression: primary,
    classification,
    regression_type: regressionType,
    causal_chain: causalChain,
    confidence: conf,
    suggested_tools: suggestedTools,
  }
}

export function formatBookmarkLabel(kind, note = '') {
  let key = String(kind || 'evidence').trim().toLowerCase().replace(/-/g, '_').replace(/ /g, '_')
  if (['root', 'cause', 'rca'].includes(key)) key = 'root_cause'
  if (['corr', 'related'].includes(key)) key = 'correlated'
  if (['ok', 'normal', 'ref'].includes(key)) key = 'reference'
  const [emoji, role] = BOOKMARK_KINDS[key] || BOOKMARK_KINDS.evidence
  const n = String(note || '').trim()
  if (n) return `${emoji} ${role}: ${n}`.slice(0, 240)
  return `${emoji} ${role}`
}

export function buildInvestigationReplay({
  finding = null,
  plan = null,
  toolsRun = null,
  conclusion = '',
  evidenceTimes = null,
  traceName = '',
  scope = '',
  queries = null,
  evidence = null,
  confidence = '',
  alternatives = null,
  timestamp = '',
} = {}) {
  const tools = (toolsRun || []).map(t => String(t)).filter(Boolean)
  let planOut = plan || defaultInvestigationPlan(
    `Investigate: ${(finding || {}).title || 'finding'}`,
  )
  if (tools.length) planOut = markPlanStepsFromTools(planOut, tools)
  const steps = (planOut.steps || []).map(s => ({
    id: s.id,
    label: s.label,
    status: s.status,
  }))
  const times = []
  for (const t of evidenceTimes || []) {
    const n = Number(t)
    if (Number.isFinite(n)) times.push(n)
  }
  const suggested = []
  if (times.length) {
    suggested.push({
      name: 'set_cursors',
      arguments: { timestamps: times.slice(0, 8) },
      reason: 'Replay evidence cursors',
    })
  }
  suggested.push({
    name: 'generate_report',
    arguments: { report_type: 'root_cause' },
    reason: 'Save structured RCA',
  })
  return {
    ok: true,
    message: 'Investigation replay',
    trace_name: String(traceName || ''),
    scope: String(scope || ''),
    finding: finding
      ? { id: finding.id, title: finding.title, severity: finding.severity }
      : null,
    steps,
    tools_run: tools,
    queries: (queries || []).filter(q => q && typeof q === 'object').map(q => ({ ...q })),
    evidence: (evidence || []).filter(e => e && typeof e === 'object').map(e => ({ ...e })),
    conclusion: String(conclusion || '').trim(),
    confidence: String(confidence || '').trim(),
    alternatives: (alternatives || []).filter(a => a && typeof a === 'object').map(a => ({ ...a })),
    evidence_times: times.slice(0, 20),
    timestamp: String(timestamp || '').trim(),
    suggested_tools: suggested,
  }
}

export function buildInvestigationPackage({
  traceName = '',
  scope = '',
  finding = null,
  plan = null,
  toolsRun = null,
  queries = null,
  evidence = null,
  conclusion = '',
  confidence = '',
  alternatives = null,
  evidenceTimes = null,
  timestamp = '',
} = {}) {
  const pkg = buildInvestigationReplay({
    finding,
    plan,
    toolsRun,
    conclusion,
    evidenceTimes,
    traceName,
    scope,
    queries,
    evidence,
    confidence,
    alternatives,
    timestamp,
  })
  pkg.schema = 'btf-investigation-package'
  pkg.version = 1
  return pkg
}

export function estimateWhatIf({
  change = '',
  task = '',
  findings = null,
  baselineMetrics = null,
} = {}) {
  const changeS = String(change || '').trim()
  const taskS = String(task || '').trim()
  const blob = `${changeS} ${taskS}`.toLowerCase()
  const items = findings || []
  const focus = items.length
    ? resolveFinding(enrichFindingsWithIds(items), '')
    : null
  let effect = '≈'
  let reason = 'Insufficient correlated evidence for a directional estimate'
  let confidence = 'Low'
  if (/pin|affin|core/.test(blob)) {
    effect = '↓ migrations / cache miss risk'
    reason = 'Affinity reduces cross-core bounce when thrashing dominates'
    confidence = 'Medium'
  } else if (/priorit/.test(blob)) {
    effect = '↓ blocking wait for higher-priority waiter (risk: starve lower)'
    reason = 'Priority changes alter preemption and inherit geometry'
    confidence = 'Medium'
  } else if (/mutex|lock|contention/.test(blob)) {
    effect = '↓ blocking Max / response'
    reason = 'Shorter hold times cut waiters\' off-CPU gaps'
    confidence = 'Medium'
  } else if (/migrat/.test(blob)) {
    effect = '↓ migration rate; ≈ WCET if CPU-bound'
    reason = 'Migration cost is overhead, not always payload'
    confidence = 'Medium'
  }
  return {
    ok: true,
    message: 'What-if estimate (not measured)',
    disclaimer: 'Simulation / estimate — not measured behavior',
    change: changeS,
    task: taskS,
    estimated_effect: effect,
    reason,
    confidence,
    evidence_quality: 'Possible explanation',
    related_finding: focus ? focus.id : null,
    baseline_metrics: baselineMetrics || {},
    suggested_tools: [
      { name: 'optimize', arguments: {}, reason: 'Evidence-backed mitigations' },
      {
        name: 'correlate_events',
        arguments: taskS ? { task: taskS } : {},
        reason: 'Verify correlated window',
      },
    ],
  }
}

export function analyzeMultiTraces(snapshots) {
  const rows = []
  for (const snap of snapshots || []) {
    if (!snap || typeof snap !== 'object') continue
    const name = String(snap.name || snap.label || `trace${rows.length}`)
    const metrics = snap.metrics && typeof snap.metrics === 'object'
      ? snap.metrics
      : snap
    const mig = metrics.migrations
    const score = metrics.load_balance_score
    const missed = metrics.missed_ticks
    const rankKey = [
      -(score != null ? Number(score) : 0),
      mig != null ? Number(mig) : 0,
      missed != null ? Number(missed) : 0,
    ]
    rows.push({
      name,
      metrics: {
        migrations: mig,
        load_balance_score: score,
        missed_ticks: missed,
        migrated_tasks: metrics.migrated_tasks,
        context_switches: metrics.context_switches,
      },
      _key: rankKey,
    })
  }
  rows.sort((a, b) => {
    for (let i = 0; i < 3; i++) {
      if (a._key[i] !== b._key[i]) return a._key[i] - b._key[i]
    }
    return 0
  })
  rows.forEach((r, i) => {
    r.rank = i + 1
    delete r._key
  })
  const best = rows.length ? rows[0].name : null
  return {
    ok: true,
    message: rows.length ? `Ranked ${rows.length} trace(s); best≈${best}` : 'No traces',
    ranking: rows,
    best,
    suggested_tools: [
      { name: 'compare_performance', arguments: {}, reason: 'Pairwise A vs B deltas' },
      { name: 'regression_explain', arguments: {}, reason: 'Explain primary regression' },
    ],
  }
}

// --- Heuristic what-if simulator / optimization experiments ---------------

const CORE_TOKEN_RE = /(?:core[_\s-]*)?(\d+)\b|(?:c)(\d+)\b/i

function giniLocal(values) {
  const vals = (values || []).map(Number).filter(v => Number.isFinite(v))
  const n = vals.length
  if (n < 2) return 0
  const total = vals.reduce((a, b) => a + b, 0)
  if (total <= 0) return 0
  const sorted = [...vals].sort((a, b) => a - b)
  let cumsum = 0
  let giniNum = 0
  for (const v of sorted) {
    cumsum += v
    giniNum += cumsum
  }
  const gini = (n + 1) / n - (2 * giniNum) / (n * total)
  return Math.max(0, Math.min(1, gini))
}

function loadBalanceScoreFromPcts(pcts) {
  return Math.max(0, 100 * (1 - giniLocal(pcts)))
}

export function parseWhatIfChange(change, task = '') {
  const text = String(change || '').trim()
  const blob = text.toLowerCase()
  let taskS = String(task || '').trim()
  const action = { kind: 'unknown', task: taskS, raw: text }
  if (/pin|affin|bind|stick/.test(blob)) {
    action.kind = 'pin'
    const m = blob.match(CORE_TOKEN_RE)
    action.core = m ? Number(m[1] || m[2]) : null
  } else if (/priorit/.test(blob)) {
    action.kind = 'priority'
    action.direction = /raise|increase|higher|boost|\bup\b/.test(blob)
      ? 'up'
      : (/lower|decrease|reduce|\bdown\b/.test(blob) ? 'down' : 'up')
  } else if (/mutex|lock|contention|critical/.test(blob)) {
    action.kind = 'reduce_contention'
    action.factor = 0.5
    const m = blob.match(/(\d+(?:\.\d+)?)\s*%/)
    if (m) action.factor = Math.max(0.05, Math.min(0.95, Number(m[1]) / 100))
  } else if (/migrat/.test(blob)) {
    action.kind = 'reduce_migration'
    action.factor = 0.5
  }
  if (!action.task) action.task = guessTaskName(text)
  return action
}

function dominantCoreFromSlices(slices) {
  const byCore = {}
  for (const sl of slices || []) {
    const core = String(sl?.core || '').trim()
    if (!core) continue
    const dur = Number(sl?.duration || 0)
    byCore[core] = (byCore[core] || 0) + Math.max(0, Number.isFinite(dur) ? dur : 0)
  }
  const keys = Object.keys(byCore)
  if (!keys.length) return null
  const best = keys.sort((a, b) => byCore[b] - byCore[a])[0]
  const m = String(best).match(/(\d+)/)
  return m ? Number(m[1]) : null
}

function quietestCore(coreUtils) {
  let bestCore = null
  let bestPct = null
  for (const row of coreUtils || []) {
    let name
    let pct
    if (Array.isArray(row) && row.length >= 2) {
      ;[name, pct] = row
    } else if (row && typeof row === 'object') {
      name = row.core || row.name
      pct = row.pct ?? row.util
    } else continue
    const p = Number(pct)
    if (!Number.isFinite(p)) continue
    const m = String(name).match(/(\d+)/)
    if (!m) continue
    const c = Number(m[1])
    if (bestPct == null || p < bestPct) {
      bestPct = p
      bestCore = c
    }
  }
  return bestCore
}

function coreUtilMap(coreUtils) {
  const out = {}
  for (const row of coreUtils || []) {
    let name
    let pct
    if (Array.isArray(row) && row.length >= 2) {
      ;[name, pct] = row
    } else if (row && typeof row === 'object') {
      name = row.core || row.name
      pct = row.pct ?? row.util
    } else continue
    const m = String(name).match(/(\d+)/)
    if (!m) continue
    const p = Number(pct)
    if (!Number.isFinite(p)) continue
    out[Number(m[1])] = p
  }
  return out
}

export function simulateWhatIf({
  change = '',
  task = '',
  slices = null,
  migrations = null,
  blockingGaps = null,
  coreUtils = null,
  findings = null,
} = {}) {
  const sliceList = [...(slices || [])]
  const migList = [...(migrations || [])]
  const gaps = [...(blockingGaps || [])]
  const action = parseWhatIfChange(change, task)
  let taskS = action.task || task

  const baseMig = migList.length
  let baseBlock = 0
  for (const g of gaps) {
    const v = g?.gap ?? g?.duration ?? 0
    const n = Number(v)
    if (Number.isFinite(n)) baseBlock += n
  }
  const utilMap = coreUtilMap(coreUtils || [])
  const basePcts = Object.values(utilMap)
  const baseLb = loadBalanceScoreFromPcts(basePcts.length ? basePcts : [0])

  let taskNs = 0
  for (const sl of sliceList) {
    const d = Number(sl?.duration || 0)
    if (Number.isFinite(d)) taskNs += d
  }

  let simMig = baseMig
  let simBlock = baseBlock
  const simUtil = { ...utilMap }
  const notes = []
  let confidence = 'Low'
  const kind = action.kind

  if (kind === 'pin') {
    let core = action.core
    if (core == null) core = dominantCoreFromSlices(sliceList)
    if (core == null) core = quietestCore(coreUtils || [])
    action.core = core
    if (core != null) {
      simMig = 0
      const byCoreNs = {}
      for (const sl of sliceList) {
        const m = String(sl?.core || '').match(/(\d+)/)
        if (!m) continue
        const c = Number(m[1])
        const d = Number(sl?.duration || 0)
        byCoreNs[c] = (byCoreNs[c] || 0) + (Number.isFinite(d) ? d : 0)
      }
      if (taskNs > 0 && Object.keys(simUtil).length) {
        const totalUtil = Object.values(simUtil).reduce((a, b) => a + b, 0) || 1
        const taskUtilEst = Math.min(totalUtil, Math.max(1, totalUtil * 0.05))
        const cores = Object.keys(byCoreNs)
        if (cores.length) {
          for (const c of cores) {
            const share = taskUtilEst * (byCoreNs[c] / taskNs)
            const ci = Number(c)
            if (simUtil[ci] != null) simUtil[ci] = Math.max(0, simUtil[ci] - share)
          }
          simUtil[core] = (simUtil[core] || 0) + taskUtilEst
        } else {
          simUtil[core] = (simUtil[core] || 0) + taskUtilEst
        }
      }
      notes.push(`Pinned ${taskS || 'task'} → Core_${core}; migrations set to 0`)
      confidence = (sliceList.length || migList.length) ? 'Medium' : 'Low'
    } else {
      notes.push('Could not resolve target core; falling back to qualitative estimate')
      return estimateWhatIf({ change, task: taskS, findings })
    }
  } else if (kind === 'reduce_contention') {
    const factor = Number(action.factor || 0.5)
    simBlock = baseBlock * (1 - factor)
    notes.push(`Scaled blocking by ×${(1 - factor).toFixed(2)} (contention −${(factor * 100).toFixed(0)}%)`)
    confidence = gaps.length ? 'Medium' : 'Low'
  } else if (kind === 'priority') {
    if (action.direction === 'up') {
      simBlock = baseBlock * 0.75
      notes.push('Raised priority: estimated −25% blocking wait (risk: starve lower)')
    } else {
      simBlock = baseBlock * 1.15
      notes.push('Lowered priority: estimated +15% blocking wait')
    }
    confidence = 'Low'
  } else if (kind === 'reduce_migration') {
    const factor = Number(action.factor || 0.5)
    simMig = Math.round(baseMig * (1 - factor))
    notes.push(`Migration count scaled by ×${(1 - factor).toFixed(2)}`)
    confidence = migList.length ? 'Medium' : 'Low'
  } else {
    const fallback = estimateWhatIf({ change, task: taskS, findings })
    fallback.simulator = 'none'
    fallback.disclaimer =
      'Heuristic estimate only — no slice replay '
      + '(phrase change as pin/affinity/priority/mutex to run simulator)'
    return fallback
  }

  const simLb = loadBalanceScoreFromPcts(Object.values(simUtil).length ? Object.values(simUtil) : basePcts)
  const deltas = {
    migrations: simMig - baseMig,
    blocking_ns: simBlock - baseBlock,
    load_balance_score: simLb - baseLb,
  }
  const costBase = 1 * baseMig + 0.000001 * baseBlock + 0.5 * Math.max(0, 100 - baseLb)
  const costSim = 1 * simMig + 0.000001 * simBlock + 0.5 * Math.max(0, 100 - simLb)
  return {
    ok: true,
    message: 'What-if heuristic simulation',
    disclaimer: 'Heuristic simulator — not an RTOS kernel / not measured',
    simulator: 'slice_replay_v1',
    change: String(change || '').trim(),
    task: taskS,
    action,
    baseline: {
      migrations: baseMig,
      blocking_ns: baseBlock,
      load_balance_score: Math.round(baseLb * 100) / 100,
      slices: sliceList.length,
    },
    simulated: {
      migrations: simMig,
      blocking_ns: simBlock,
      load_balance_score: Math.round(simLb * 100) / 100,
    },
    deltas: {
      migrations: deltas.migrations,
      blocking_ns: deltas.blocking_ns,
      load_balance_score: Math.round(deltas.load_balance_score * 100) / 100,
      cost: Math.round((costSim - costBase) * 1000) / 1000,
    },
    cost: {
      baseline: Math.round(costBase * 1000) / 1000,
      simulated: Math.round(costSim * 1000) / 1000,
    },
    notes,
    confidence,
    evidence_quality: confidence === 'Medium' ? 'Strong correlation' : 'Possible explanation',
    estimated_effect:
      `Δmig=${deltas.migrations >= 0 ? '+' : ''}${deltas.migrations}, `
      + `Δblock_ns=${deltas.blocking_ns >= 0 ? '+' : ''}${Math.round(deltas.blocking_ns)}, `
      + `ΔLB=${deltas.load_balance_score >= 0 ? '+' : ''}${deltas.load_balance_score.toFixed(1)}`,
    suggested_tools: [
      {
        name: 'optimize_experiment',
        arguments: taskS ? { task: taskS } : {},
        reason: 'Try ranked automatic experiments',
      },
      {
        name: 'correlate_events',
        arguments: taskS ? { task: taskS } : {},
        reason: 'Verify on timeline',
      },
    ],
  }
}

export function proposeOptimizationExperiments({
  task = '',
  slices = null,
  findings = null,
  coreUtils = null,
  limit = 5,
} = {}) {
  const lim = Math.max(1, Math.min(12, Math.trunc(Number(limit) || 5)))
  let taskS = String(task || '').trim()
  if (!taskS && findings) {
    const ranked = detectAnomalies(findings, { limit: 3 })
    for (const a of ranked.anomalies || []) {
      const t = a.task || guessTaskName(String(a.text || ''))
      if (t) {
        taskS = t
        break
      }
    }
  }
  const candidates = []
  const dom = dominantCoreFromSlices(slices || [])
  const quiet = quietestCore(coreUtils || [])
  if (taskS && dom != null) {
    candidates.push({
      change: `pin ${taskS} to Core_${dom}`,
      task: taskS,
      rationale: 'Pin to dominant execution core',
    })
  }
  if (taskS && quiet != null && quiet !== dom) {
    candidates.push({
      change: `pin ${taskS} to Core_${quiet}`,
      task: taskS,
      rationale: 'Pin to quietest core for load balance',
    })
  }
  if (taskS) {
    candidates.push({
      change: `reduce mutex contention 50% for ${taskS}`,
      task: taskS,
      rationale: 'Shorten critical sections / lock hold time',
    })
    candidates.push({
      change: `raise priority of ${taskS}`,
      task: taskS,
      rationale: 'Reduce blocking wait (risk: starvation)',
    })
    candidates.push({
      change: `reduce migrations 50% for ${taskS}`,
      task: taskS,
      rationale: 'Affinity / migration throttle',
    })
  }
  for (const a of (detectAnomalies(findings || [], { limit: 3 }).anomalies || [])) {
    const t = a.task || taskS
    const blob = `${a.title || ''} ${a.text || ''}`.toLowerCase()
    if (t && (/thrash|migrat/.test(blob)) && dom != null) {
      candidates.push({
        change: `pin ${t} to Core_${dom}`,
        task: t,
        rationale: `From finding ${a.id}`,
      })
    }
  }
  const seen = new Set()
  const out = []
  for (const c of candidates) {
    if (seen.has(c.change)) continue
    seen.add(c.change)
    out.push(c)
    if (out.length >= lim) break
  }
  return out
}

export function runOptimizationExperiments({
  task = '',
  slices = null,
  migrations = null,
  blockingGaps = null,
  coreUtils = null,
  findings = null,
  limit = 5,
} = {}) {
  const cands = proposeOptimizationExperiments({
    task, slices, findings, coreUtils, limit,
  })
  const results = []
  for (const c of cands) {
    const sim = simulateWhatIf({
      change: c.change,
      task: c.task || task,
      slices,
      migrations,
      blockingGaps,
      coreUtils,
      findings,
    })
    if (sim.simulator === 'none') continue
    const costDelta = sim.deltas?.cost
    results.push({
      change: c.change,
      task: c.task || task,
      rationale: c.rationale,
      deltas: sim.deltas,
      baseline: sim.baseline,
      simulated: sim.simulated,
      cost_delta: costDelta,
      confidence: sim.confidence,
      notes: sim.notes,
    })
  }
  results.sort((a, b) => {
    const ac = a.cost_delta
    const bc = b.cost_delta
    if (ac == null && bc == null) return 0
    if (ac == null) return 1
    if (bc == null) return -1
    return ac - bc
  })
  results.forEach((r, i) => { r.rank = i + 1 })
  const best = results.length ? results[0] : null
  const suggested = []
  if (best) {
    suggested.push({
      name: 'what_if',
      arguments: { change: best.change || '', task: best.task || task },
      reason: 'Re-run best experiment detail',
    })
  }
  suggested.push({
    name: 'bookmark_finding',
    arguments: {},
    reason: 'Mark evidence on timeline',
  })
  return {
    ok: true,
    message: best
      ? `${results.length} experiment(s); best=${best.change}`
      : 'No runnable experiments (need task slices / metrics)',
    disclaimer: 'Heuristic simulator — not an RTOS kernel / not measured',
    experiments: results,
    best,
    suggested_tools: suggested,
  }
}

// --- Historical baseline learning (lightweight) ---------------------------

const BASELINE_METRIC_KEYS = ['wcet_us', 'blocking_us', 'migrations', 'response_us']

function emptyBaselineProfile() {
  return { version: 1, samples: 0, tasks: {} }
}

export function updateBaselineProfile(profile, snapshot) {
  let out
  if (profile && typeof profile === 'object') {
    const tasksIn = (profile.tasks && typeof profile.tasks === 'object') ? profile.tasks : {}
    const tasksOut = {}
    for (const [t, m] of Object.entries(tasksIn)) {
      if (!m || typeof m !== 'object') continue
      const bucket = {}
      for (const [k, v] of Object.entries(m)) {
        if (v && typeof v === 'object') bucket[String(k)] = { ...v }
      }
      tasksOut[String(t)] = bucket
    }
    out = {
      version: Number(profile.version) || 1,
      samples: Number(profile.samples) || 0,
      tasks: tasksOut,
    }
  } else {
    out = emptyBaselineProfile()
  }
  const tasksIn = (snapshot && typeof snapshot === 'object') ? snapshot.tasks : null
  if (!tasksIn || typeof tasksIn !== 'object' || !Object.keys(tasksIn).length) {
    return out
  }
  for (const [taskRaw, metrics] of Object.entries(tasksIn)) {
    if (!metrics || typeof metrics !== 'object') continue
    const task = String(taskRaw).trim()
    if (!task) continue
    if (!out.tasks[task]) out.tasks[task] = {}
    const bucket = out.tasks[task]
    for (const key of BASELINE_METRIC_KEYS) {
      const val = metrics[key]
      if (val == null) continue
      const x = Number(val)
      if (!Number.isFinite(x)) continue
      const stat = bucket[key] || { n: 0, mean: 0.0, m2: 0.0 }
      const n = Number(stat.n || 0) + 1
      let mean = Number(stat.mean || 0.0)
      let m2 = Number(stat.m2 || 0.0)
      const delta = x - mean
      mean += delta / n
      m2 += delta * (x - mean)
      bucket[key] = { n, mean, m2 }
    }
  }
  out.samples = Number(out.samples || 0) + 1
  return out
}

export function scoreAgainstBaseline(profile, snapshot, { zThreshold = 2.0 } = {}) {
  const z_threshold = Number(zThreshold) || 2.0
  const tasksProfile = (profile && typeof profile === 'object' && profile.tasks
    && typeof profile.tasks === 'object') ? profile.tasks : {}
  const tasksIn = (snapshot && typeof snapshot === 'object' && snapshot.tasks
    && typeof snapshot.tasks === 'object') ? snapshot.tasks : {}
  const scores = []
  const flagged = []
  for (const [taskRaw, metrics] of Object.entries(tasksIn)) {
    if (!metrics || typeof metrics !== 'object') continue
    const task = String(taskRaw).trim()
    const baseBucket = (tasksProfile[task] && typeof tasksProfile[task] === 'object')
      ? tasksProfile[task] : {}
    for (const key of BASELINE_METRIC_KEYS) {
      const val = metrics[key]
      if (val == null) continue
      const x = Number(val)
      if (!Number.isFinite(x)) continue
      const stat = baseBucket[key]
      const row = {
        task, metric: key, value: x,
        n: 0, mean: null, std: null, z: null, flag: false,
      }
      if (stat && typeof stat === 'object' && Number(stat.n || 0) >= 2) {
        const n = Number(stat.n)
        const mean = Number(stat.mean || 0.0)
        const variance = Number(stat.m2 || 0.0) / Math.max(1, n - 1)
        const std = Math.sqrt(variance)
        row.n = n
        row.mean = Math.round(mean * 10000) / 10000
        row.std = Math.round(std * 10000) / 10000
        if (std > 1e-9) {
          const z = (x - mean) / std
          row.z = Math.round(z * 1000) / 1000
          row.flag = Math.abs(z) > z_threshold
        } else {
          row.z = 0.0
        }
      }
      scores.push(row)
      if (row.flag) flagged.push(row)
    }
  }
  flagged.sort((a, b) => Math.abs(b.z || 0) - Math.abs(a.z || 0))
  return {
    ok: true,
    message: `${scores.length} metric score(s); ${flagged.length} flagged `
      + `(|z|>${z_threshold})`,
    scores,
    flagged,
    z_threshold,
    has_baseline: Object.keys(tasksProfile).length > 0,
    suggested_tools: flagged.length
      ? [{ name: 'investigate', arguments: {}, reason: 'Drill into flagged task' }]
      : [],
  }
}

// --- AI-generated validation experiments ----------------------------------

export function recommendValidationExperiments(findings, {
  findingId = '', task = '', limit = 5,
} = {}) {
  const lim = Math.max(1, Math.min(20, Number(limit) || 5))
  const items = enrichFindingsWithIds(findings || [])
  let focus = null
  if (findingId) focus = resolveFinding(items, findingId)
  if (!focus && task) {
    const want = String(task).trim().toLowerCase()
    for (const f of items) {
      const t = String(f.task || guessTaskName(String(f.text || '')) || '')
      if (t && t.toLowerCase() === want) { focus = f; break }
    }
  }
  let pool
  if (focus) {
    pool = [focus]
  } else if (items.length) {
    const anomalies = detectAnomalies(items, { limit: Math.max(3, lim) })
    pool = (anomalies.anomalies || []).map(a => ({
      id: a.id, title: a.title, text: a.text, severity: a.severity, task: a.task,
    }))
  } else {
    pool = []
  }

  const experiments = []
  const seenTitles = new Set()
  const add = (title, kind, steps, rationale, fid) => {
    if (seenTitles.has(title)) return
    seenTitles.add(title)
    experiments.push({
      title,
      kind,
      steps: (steps || []).map(s => String(s)),
      rationale,
      evidence_finding: fid,
    })
  }

  for (const f of pool) {
    if (experiments.length >= lim) break
    const title = String(f.title || '')
    const text = String(f.text || '')
    const blob = `${title} ${text}`.toLowerCase()
    const t = String(f.task || guessTaskName(text) || task || '').trim()
    const fid = f.id
    const tname = t || 'the hot task'
    if (/thrash|migrat|bounc/.test(blob)) {
      add(
        `Simulate pinning ${tname} to its dominant core`,
        'simulation',
        [`what_if(change='pin ${tname} to Core_N')`, 'Compare migrations / load-balance deltas'],
        'Migration/thrash finding suggests core affinity fixes the bounce',
        fid,
      )
      add(
        `Pin ${tname} in firmware (vTaskCoreAffinitySet)`,
        'firmware',
        [`Call vTaskCoreAffinitySet(${tname}, mask) at startup / after creation`,
          'Re-run the same workload and re-capture a trace'],
        'Confirms the simulated affinity fix on real hardware',
        fid,
      )
      add(
        `Measure migration rate for ${tname} before/after the affinity fix`,
        'measurement',
        ['Capture baseline trace', 'Apply the affinity fix',
          'Capture candidate trace', 'Run compare_performance A vs B'],
        'Directly measures whether thrashing is resolved',
        fid,
      )
    } else if (/block|mutex|inversion|inherit/.test(blob)) {
      add(
        `Simulate reduced lock contention for ${tname}`,
        'simulation',
        [`what_if(change='reduce mutex contention 50% for ${tname}')`,
          'Compare blocking Max / response deltas'],
        'Blocking/mutex finding suggests shortening the critical section',
        fid,
      )
      add(
        `Shorten the critical section for ${tname} (firmware)`,
        'firmware',
        ['Reduce work performed while the mutex is held',
          'Or switch to a priority-inheritance mutex (xSemaphoreCreateMutex, not a binary semaphore)'],
        'Addresses priority inversion / long hold times at the source',
        fid,
      )
      add(
        `Measure blocking Max for ${tname} before/after the fix`,
        'measurement',
        ['Capture baseline trace', 'Apply the fix', 'Capture candidate trace',
          `query_raw_metric(task=${tname}, metric=blocking) on both`],
        'Confirms blocking wait actually dropped',
        fid,
      )
    } else if (/wcet|spike|execution|cpu/.test(blob)) {
      add(
        `Profile execution slices for ${tname}`,
        'measurement',
        [`query_raw_metric(task=${tname}, metric=execution)`,
          'Jump to the Max slice and inspect surrounding events'],
        'WCET/CPU spike finding needs a profiling pass before code changes',
        fid,
      )
      add(
        `Trim or split the long slice on ${tname} (firmware)`,
        'firmware',
        ['Break the long critical section / loop into smaller chunks',
          'Re-measure Max execution after the change'],
        'Directly reduces WCET at the source',
        fid,
      )
    } else if (/load|balance/.test(blob)) {
      add(
        'Simulate rebalanced task placement',
        'simulation',
        ['optimize_experiment() to rank candidate placements',
          'Compare Load Balance Score deltas'],
        'Load-balance finding suggests a placement change',
        fid,
      )
      add(
        'Measure Load Balance Score before/after static affinity',
        'measurement',
        ['Capture baseline trace', 'Apply static core assignment',
          'Capture candidate trace', 'Run analyze_traces or compare_performance'],
        'Confirms the placement change improves balance',
        fid,
      )
    } else if (/deadline|budget/.test(blob)) {
      add(
        `Re-check budget compliance for ${tname} after a fix`,
        'measurement',
        ['check_budget() with the configured WCET/response/deadline budgets'],
        'Deadline/budget finding needs a direct budget re-check',
        fid,
      )
    } else {
      add(
        `Investigate ${title || 'this finding'} further`,
        'measurement',
        ['investigate(finding_id) for a root-cause chain', 'correlate_events for supporting evidence'],
        'No specialised heuristic match — needs more evidence first',
        fid,
      )
    }
  }
  const finalExperiments = experiments.slice(0, lim)
  return {
    ok: true,
    message: `${finalExperiments.length} validation experiment(s) suggested`,
    experiments: finalExperiments,
    disclaimer: 'Simulation / estimate — not measured behavior; firmware steps '
      + 'are suggestions to implement and re-trace, not applied automatically',
  }
}
