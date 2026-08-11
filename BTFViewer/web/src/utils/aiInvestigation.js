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
  query_raw_metric: ['metrics'],
  search_timeline: ['metrics'],
  trigger_compare: ['metrics', 'related'],
  set_cursors: ['narrow'],
  zoom_to_range: ['narrow'],
  highlight_task: ['related'],
  open_corridor_inspector: ['related'],
  add_annotation: ['validate'],
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
  const bracketed = String(text || '').match(/\b[A-Za-z_][\w]*\[[0-9]+\]/g) || []
  for (const tok of bracketed) {
    const low = tok.toLowerCase()
    if (low.startsWith('core') || low === 'tick') continue
    return tok
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
  if (depth >= 3) add('trigger_compare', {}, 'Compare two open tabs if available')
  if (depth >= 4) add('export_report', { format: 'html' }, 'Save diagnostic report')
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
  const hypotheses = hypothesesForFinding(title, text)
  const suggested = suggestedToolsForFinding(title, text, d)
  const related = items
    .filter(f => f.id !== focus.id)
    .slice(0, 8)
    .map(f => ({ id: f.id, severity: f.severity, title: f.title }))
  let plan = defaultInvestigationPlan(`Investigate: ${title}`)
  plan = markPlanStepsFromTools(plan, ['investigate'])
  return {
    ok: true,
    message: `Investigation context for ${focus.id} (${hypotheses.length} hypotheses, ${suggested.length} suggested tools)`,
    finding: {
      id: focus.id,
      severity: focus.severity,
      title,
      text,
      evidence: focus.evidence || [],
      task: focus.task || '',
    },
    related_findings: related,
    hypotheses: hypotheses.slice(0, Math.max(1, d + 1)),
    suggested_tools: suggested,
    depth: d,
    evidence_chain: formatFindingsEvidenceChain([focus]),
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
