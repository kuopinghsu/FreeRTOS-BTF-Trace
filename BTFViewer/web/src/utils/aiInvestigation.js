/**
 * Investigation plan, evidence chain, baselines, CI regression helpers.
 * Keep in sync with btf_viewer_pkg/ai_investigation.py.
 */

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
}

const AGENT_TEMPLATE_IDS = new Set([
  'investigate', 'root_cause', 'what_if', 'optimize', 'diagnostic_report',
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
    if (!item.evidence) item.evidence = []
    return item
  })
}

export function formatFindingsEvidenceChain(findings) {
  const lines = ['### Evidence chain', '']
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
      suggested_tools: [],
      plan: defaultInvestigationPlan(),
      evidence_chain: formatFindingsEvidenceChain([]),
    }
  }
  const title = String(focus.title || '')
  const text = String(focus.text || '')
  const sev = String(focus.severity || 'info')
  const hypotheses = hypothesesForFinding(title, text)
  const suggested = suggestedToolsForFinding(title, text, d)
  const related = items
    .filter(f => f.id !== focus.id)
    .slice(0, 8)
    .map(f => ({ id: f.id, severity: f.severity, title: f.title }))
  let plan = defaultInvestigationPlan(`Investigate: ${title}`)
  plan = markPlanStepsFromTools(plan, ['investigate'])
  const chain = buildRootCauseChain(focus)
  const anomalies = detectAnomalies(items, { limit: Math.max(3, d + 2) })
  return {
    ok: true,
    message: `Investigation context for ${focus.id} (${hypotheses.length} hypotheses, ${suggested.length} suggested tools)`,
    finding: {
      id: focus.id,
      severity: sev,
      title,
      text,
      evidence: focus.evidence || [],
      task: focus.task || guessTaskName(text),
    },
    related_findings: related,
    hypotheses: hypotheses.slice(0, Math.max(1, d + 1)),
    suggested_tools: suggested,
    depth: d,
    evidence_chain: formatFindingsEvidenceChain([focus]),
    root_cause_chain: chain,
    ranked_anomalies: (anomalies.anomalies || []).slice(0, Math.max(3, d)),
    plan,
  }
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
  return {
    ok: true,
    message: String(result.summary || 'compared'),
    label_a: labelA,
    label_b: labelB,
    failed: !!result.failed,
    checks: result.checks || [],
    primary_regression: primary,
    confidence,
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
  lines.push('## Key findings')
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
    '## Recommended actions',
    '1. Place cursors / zoom on the worst episode (`set_cursors`, `zoom_to_range`).',
    '2. Highlight the focus task and verify on the timeline.',
    '3. Re-run Trace Compare or `compare_performance` after a fix.',
    '',
    '## Confidence',
    'Medium — structured from Analysis Findings; confirm with tool evidence.',
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

export function explainRegression(compare, findings = null) {
  const cmp = { ...(compare || {}) }
  const primary = cmp.primary_regression || {}
  const failed = !!cmp.failed
  const labelA = cmp.label_a || 'A'
  const labelB = cmp.label_b || 'B'
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
  return {
    ok: true,
    message: failed ? 'Regression explained' : 'No regression to explain',
    failed,
    markdown: lines.join('\n'),
    primary_regression: primary,
    confidence: conf,
    suggested_tools: [
      { name: 'correlate_events', arguments: {}, reason: 'Timeline for worst metric' },
      { name: 'investigate', arguments: {}, reason: 'Root-cause chain' },
    ],
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
    finding: finding
      ? { id: finding.id, title: finding.title, severity: finding.severity }
      : null,
    steps,
    tools_run: tools,
    conclusion: String(conclusion || '').trim(),
    evidence_times: times.slice(0, 20),
    suggested_tools: suggested,
  }
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
    disclaimer: 'Heuristic simulator — not FreeRTOS kernel / not measured',
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
    disclaimer: 'Heuristic simulator — not FreeRTOS kernel / not measured',
    experiments: results,
    best,
    suggested_tools: suggested,
  }
}
