/** Phase 1–3 investigation planner. Keep in sync with btf_viewer_pkg/ai_planner.py. */

const TASK_RE = /([A-Za-z_][\w.-]*\s*\[[^\]]+\])/
const PATTERN_KEYS = [
  ['migration', ['migrat', 'thrash', 'bounce', 'ping-pong']],
  ['mutex', ['mutex', 'lock', 'contention', 'sync']],
  ['blocking', ['block', 'wait', 'hold']],
  ['deadline', ['deadline', 'miss', 'late']],
  ['load', ['imbalance', 'load', 'util']],
  ['inversion', ['inversion', 'inherit', 'boost']],
  ['preemption', ['preempt', 'interrupt']],
  ['wcet', ['wcet', 'execution', 'runtime']],
  ['tick', ['tick', 'tickless']],
]

let OUTCOMES = []

export function experimentOutcomes() {
  return OUTCOMES.map((r) => ({ ...r }))
}

export function setExperimentOutcomes(rows = []) {
  OUTCOMES = []
  for (const row of rows || []) {
    if (row && typeof row === 'object') OUTCOMES.push({ ...row })
  }
}

function blob(finding) {
  return `${finding?.title || ''} ${finding?.text || ''}`.toLowerCase()
}

function taskOf(finding) {
  const t = String(finding?.task || '').trim()
  if (t) return t
  const m = TASK_RE.exec(String(finding?.text || finding?.title || ''))
  return m ? m[1].replace(/ /g, '') : ''
}

function patterns(text) {
  const b = String(text || '').toLowerCase()
  return PATTERN_KEYS.filter(([, keys]) => keys.some((k) => b.includes(k))).map(([n]) => n)
}

function band(count, high = 3, mid = 1) {
  if (count >= high) return 'HIGH'
  if (count >= mid) return 'MEDIUM'
  return 'LOW'
}

function items(findings) {
  return (findings || []).filter((f) => f && typeof f === 'object')
}

export function scoreHypotheses(hypotheses = [], { findings = [], contradictions = [] } = {}) {
  const pool = items(findings)
  const contradicted = new Set(
    (contradictions || [])
      .filter((c) => c && String(c.verdict || '').toUpperCase() === 'CONTRADICTED')
      .map((c) => String(c.hypothesis_id || c.hypothesis || '').toLowerCase()),
  )
  const poolPat = []
  for (const f of pool) poolPat.push(...patterns(blob(f)))
  const raw = (hypotheses || []).filter((h) => h && typeof h === 'object')
  const out = raw.map((h, i) => {
    const hyp = String(h.hypothesis || h.description || '').trim()
    const hid = String(h.id || `H${i + 1}`)
    const prior = i === 0 ? 0.55 : Math.max(0.08, 0.35 / i)
    const pats = patterns(`${hyp} ${h.why || ''}`)
    let evW = Math.min(0.35, 0.12 * pats.filter((p) => poolPat.includes(p)).length)
    const status = String(h.status || '').toLowerCase()
    if (status === 'supported') evW += 0.2
    else if (status === 'rejected') evW -= 0.35
    else if (status === 'need_evidence') evW -= 0.05
    if (contradicted.has(hid.toLowerCase()) || contradicted.has(hyp.toLowerCase())) evW -= 0.4
    return { ...h, id: hid, hypothesis: hyp || hid, prior: +prior.toFixed(3), score: Math.max(0.02, Math.min(0.97, prior + evW)) }
  })
  const total = out.reduce((s, h) => s + Number(h.score || 0), 0) || 1
  for (const h of out) h.score = +(Number(h.score) / total).toFixed(3)
  out.sort((a, b) => Number(b.score || 0) - Number(a.score || 0))
  return out
}

export function planInvestigation(findings = [], { question = '', findingId = '' } = {}) {
  const list = items(findings)
  let focus = list[0] || {}
  if (findingId) {
    const want = String(findingId).toLowerCase()
    for (const f of list) {
      if (String(f.id || '').toLowerCase().includes(want) || String(f.title || '').toLowerCase().includes(want)) {
        focus = f
        break
      }
    }
  }
  const task = taskOf(focus)
  const pats = patterns(`${blob(focus)} ${question}`)
  const labels = {
    migration: 'Migration thrashing',
    mutex: 'Mutex contention',
    inversion: 'Priority inversion',
    deadline: 'Deadline miss from execution inflation',
    load: 'Load imbalance',
    blocking: 'Blocking / wait',
    preemption: 'Preemption burst',
    wcet: 'WCET pressure',
  }
  const hyps = []
  const seen = new Set()
  for (const p of (pats.length ? pats : ['migration'])) {
    if (seen.has(p)) continue
    seen.add(p)
    hyps.push({ id: `H${hyps.length + 1}`, hypothesis: labels[p] || p, why: p })
  }
  if (!hyps.length) hyps.push({ id: 'H1', hypothesis: 'Primary finding', why: 'top finding' })
  const scored = scoreHypotheses(hyps, { findings: list })
  let steps = ['cluster_findings', 'detect_anomalies']
  if (pats.includes('migration')) steps.push('query_raw_metric:migrations', 'correlate_events')
  if (pats.includes('mutex') || pats.includes('blocking')) steps.push('query_raw_metric:blocking', 'detect_priority_inversion')
  if (pats.includes('deadline') || pats.includes('wcet')) steps.push('query_raw_metric:execution', 'find_critical_path')
  steps.push('detect_contradictions', 'assess_evidence_sufficiency')
  const uniq = []
  for (const s of steps) if (!uniq.includes(s)) uniq.push(s)
  const times = []
  for (const ev of focus.evidence || []) {
    if (ev && ev.time != null) times.push(ev.time)
  }
  return {
    ok: true,
    message: `Plan with ${scored.length} hypotheses, ${uniq.length} steps`,
    scope: {
      tasks: task ? [task] : [],
      time: times.length >= 2 ? [times[0], times[times.length - 1]] : times.slice(0, 1),
      patterns: pats,
      finding_id: focus.id || findingId,
    },
    hypotheses: scored,
    steps: uniq,
    question: String(question || ''),
  }
}

export function suggestScope(question = '', findings = [], { cursorLo = null, cursorHi = null } = {}) {
  const list = items(findings)
  const q = String(question || '').trim()
  let focus = list[0] || {}
  const qlow = q.toLowerCase()
  for (const f of list) {
    const b = blob(f)
    if (qlow.split(/\s+/).some((tok) => tok.length > 3 && b.includes(tok))) { focus = f; break }
    const t = taskOf(f)
    if (t && qlow.includes(t.toLowerCase())) { focus = f; break }
  }
  const task = taskOf(focus)
  const related = []
  for (const f of list) {
    const t = taskOf(f)
    if (t && t !== task && !related.includes(t)) related.push(t)
    if (related.length >= 3) break
  }
  const times = []
  for (const ev of focus.evidence || []) {
    if (ev && ev.time != null) {
      const n = Number(ev.time)
      if (Number.isFinite(n)) times.push(n)
    }
  }
  let lo = null
  let hi = null
  if (cursorLo != null && cursorHi != null) {
    lo = Math.min(cursorLo, cursorHi)
    hi = Math.max(cursorLo, cursorHi)
  } else if (times.length >= 2) {
    lo = Math.min(...times)
    hi = Math.max(...times)
  } else if (times.length) {
    lo = hi = times[0]
  }
  let reason = 'Top finding plus evidence times.'
  if (task && times.length) reason = `Focus ${task}; evidence clustered at ${lo}–${hi}.`
  else if (q) reason = `Interpreted from: ${q.slice(0, 120)}`
  return {
    ok: true,
    message: 'Recommended investigation scope',
    task,
    related_tasks: related,
    time_lo: lo,
    time_hi: hi,
    finding_id: focus.id,
    reason,
    apply_scope: true,
  }
}

export function detectContradictions(findings = [], { hypothesis = '', metrics = {} } = {}) {
  const list = items(findings)
  const hyp = String(hypothesis || '').trim() || String((list[0] || {}).title || '')
  const blobH = hyp.toLowerCase()
  const m = metrics && typeof metrics === 'object' ? metrics : {}
  const reasons = []
  let verdict = 'INSUFFICIENT'
  const num = (key) => {
    const n = Number(m[key])
    return Number.isFinite(n) ? n : null
  }
  const blocking = num('blocking') ?? num('blocking_pct')
  const execution = num('execution') ?? num('execution_pct')
  const mutex = num('mutex_hold') ?? num('hold')
  const migrations = num('migrations')
  if (blobH.includes('mutex') || blobH.includes('contention') || blobH.includes('block')) {
    if (execution != null && blocking != null && execution > blocking * 3) {
      verdict = 'CONTRADICTED'
      reasons.push('Dominant regression is execution, not synchronization.')
    }
    if (mutex != null && Math.abs(mutex) < 1e-6) {
      verdict = 'CONTRADICTED'
      reasons.push('Mutex hold time unchanged.')
    }
  }
  if (blobH.includes('migrat') || blobH.includes('thrash')) {
    if (migrations != null && migrations < 1) {
      verdict = 'CONTRADICTED'
      reasons.push('Migration count is not elevated.')
    }
  }
  const titles = list.map(blob).join(' ')
  if (blobH.includes('mutex') && titles.includes('migrat') && !titles.includes('mutex')) {
    verdict = 'CONTRADICTED'
    reasons.push('Findings emphasise migration, not mutex.')
  }
  if (!reasons.length && list.length) {
    verdict = patterns(blobH).some((p) => titles.includes(p)) ? 'SUPPORTED' : 'INSUFFICIENT'
    if (verdict === 'SUPPORTED') reasons.push('Finding text overlaps the hypothesis.')
  }
  return { ok: true, message: verdict, hypothesis: hyp, verdict, reasons, metrics: m }
}

export function assessEvidenceSufficiency(findings = [], {
  toolsRun = [], contradictions = [], coverage = {},
} = {}) {
  const list = items(findings)
  const tools = (toolsRun || []).map((t) => String(t))
  let pct = coverage?.percent
  if (pct == null) pct = Math.min(95, 20 + 15 * Math.min(list.length, 4) + 8 * Math.min(tools.length, 6))
  pct = Math.round(Number(pct) || 0)
  const contradicted = (contradictions || []).some(
    (c) => c && String(c.verdict || '').toUpperCase() === 'CONTRADICTED',
  )
  const hasAlt = list.some((f) => blob(f).includes('mutex') || blob(f).includes('migrat'))
  const stop = pct >= 80 && tools.length >= 2 && !contradicted
  let rec = stop ? 'STOP INVESTIGATION' : 'CONTINUE'
  if (contradicted) rec = 'REVISE HYPOTHESIS'
  return {
    ok: true,
    message: rec,
    coverage_percent: pct,
    recommendation: rec,
    stop,
    supporting: list.slice(0, 6).map((f) => String(f.title || f.id || '')),
    tools_run: tools,
    contradicted,
    alternative_seen: hasAlt,
  }
}

export function clusterFindings(findings = []) {
  const list = items(findings)
  const incidents = []
  const used = new Set()
  for (let i = 0; i < list.length; i += 1) {
    if (used.has(i)) continue
    const f = list[i]
    const pats = new Set(patterns(blob(f)))
    const task = taskOf(f)
    const members = [f]
    used.add(i)
    for (let j = 0; j < list.length; j += 1) {
      if (used.has(j)) continue
      const g = list[j]
      const gp = new Set(patterns(blob(g)))
      const gt = taskOf(g)
      const overlap = [...pats].some((p) => gp.has(p))
      if ((task && gt === task) || (pats.size && gp.size && overlap)) {
        members.push(g)
        used.add(j)
      }
    }
    incidents.push({
      id: `I${incidents.length + 1}`,
      root_suspect: taskOf(members[0]),
      patterns: [...pats].sort(),
      findings: members.map((m) => String(m.title || m.id || '')),
      count: members.length,
    })
  }
  return {
    ok: true,
    message: `${incidents.length} incident cluster(s) from ${list.length} findings`,
    incidents,
  }
}

export function generateFingerprint(findings = [], { metrics = {} } = {}) {
  const list = items(findings)
  const counts = Object.fromEntries(PATTERN_KEYS.map(([n]) => [n, 0]))
  for (const f of list) {
    for (const p of patterns(blob(f))) counts[p] = (counts[p] || 0) + 1
  }
  const m = metrics && typeof metrics === 'object' ? metrics : {}
  if (Number(m.migrations || 0) > 20) counts.migration += 2
  const scheduling = {
    migration: band(counts.migration || 0),
    load_balance: band(counts.load || 0),
    preemption: band(counts.preemption || 0),
  }
  const sync = {
    blocking: band(counts.blocking || 0),
    mutex_contention: band(counts.mutex || 0),
    pi: band(counts.inversion || 0),
  }
  const timing = {
    wcet_pressure: band(counts.wcet || 0),
    deadline_miss: band(counts.deadline || 0),
  }
  const hot = Object.entries({ ...scheduling, ...sync, ...timing }).filter(([, v]) => v === 'HIGH').map(([k]) => k)
  const pattern = hot.length ? hot.join(' + ') : 'nominal'
  return {
    ok: true,
    message: `Pattern: ${pattern}`,
    scheduling,
    synchronization: sync,
    timing,
    pattern,
    counts,
  }
}

function fpTags(fp) {
  const tags = new Set()
  for (const group of ['scheduling', 'synchronization', 'timing']) {
    const block = fp?.[group] && typeof fp[group] === 'object' ? fp[group] : {}
    for (const [k, v] of Object.entries(block)) {
      if (['HIGH', 'MEDIUM'].includes(String(v).toUpperCase())) tags.add(k)
    }
  }
  if (fp?.pattern) tags.add(String(fp.pattern).toLowerCase())
  return tags
}

export function findSimilarInvestigations(findings = [], { history = [], limit = 5 } = {}) {
  const current = generateFingerprint(findings)
  const tags = fpTags(current)
  const hist = [...(history || []).filter((h) => h && typeof h === 'object'), ...OUTCOMES]
  const scored = []
  hist.forEach((row, i) => {
    const fp = row.fingerprint && typeof row.fingerprint === 'object' ? row.fingerprint : row
    const other = fpTags(fp)
    let sim = 0
    if (tags.size || other.size) {
      const inter = [...tags].filter((t) => other.has(t)).length
      const union = new Set([...tags, ...other]).size
      sim = Math.round(100 * inter / Math.max(union, 1))
    }
    if (sim <= 0) return
    scored.push({
      id: row.id || `#${i + 1}`,
      similarity: sim,
      solution: row.solution || row.change || '',
      result: row.result || row.actual || '',
      pattern: fp.pattern || row.pattern || '',
    })
  })
  scored.sort((a, b) => b.similarity - a.similarity)
  const cap = Math.max(1, Math.min(20, Number(limit) || 5))
  return {
    ok: true,
    message: `${scored.slice(0, cap).length} similar investigation(s)`,
    current,
    matches: scored.slice(0, cap),
  }
}

export function regressionLocalize(candidate = {}, baseline = {}, {
  findings = [], labelA = 'A', labelB = 'B',
} = {}) {
  const cand = candidate && typeof candidate === 'object' ? candidate : {}
  const base = baseline && typeof baseline === 'object' ? baseline : {}
  const cm = cand.metrics && typeof cand.metrics === 'object' ? cand.metrics : cand
  const bm = base.metrics && typeof base.metrics === 'object' ? base.metrics : base
  const deltas = {}
  for (const key of ['execution', 'migrations', 'preemptions', 'blocking', 'load_balance_score']) {
    const a = Number(cm[key])
    const b = Number(bm[key])
    if (Number.isFinite(a) && Number.isFinite(b)) deltas[key] = +(a - b).toFixed(3)
  }
  const list = items(findings)
  const task = list.length ? taskOf(list[0]) : ''
  const times = []
  for (const f of list) {
    for (const ev of f.evidence || []) {
      if (ev && ev.time != null) times.push(ev.time)
    }
  }
  const region = times.length ? [Math.min(...times), Math.max(...times)] : []
  const mech = []
  if ((deltas.migrations || 0) > 0) mech.push('migration')
  if ((deltas.preemptions || 0) > 0) mech.push('preemption')
  if ((deltas.execution || 0) > 0) mech.push('execution inflation')
  return {
    ok: true,
    message: `Localized ${labelA} vs ${labelB}`,
    overall: deltas,
    task,
    region,
    likely_mechanism: mech.join(' → ') || 'unspecified',
    primary_change: deltas,
  }
}

export function buildCausalChain(findings = [], { events = [] } = {}) {
  const list = items(findings)
  const pats = []
  for (const f of list) {
    for (const p of patterns(blob(f))) {
      if (!pats.includes(p)) pats.push(p)
    }
  }
  const order = ['migration', 'preemption', 'wcet', 'blocking', 'deadline']
  let nodes = order.filter((p) => pats.includes(p))
  if (!nodes.length) nodes = pats.slice(0, 4).length ? pats.slice(0, 4) : ['finding']
  const edges = []
  for (let i = 0; i < nodes.length - 1; i += 1) {
    const a = nodes[i]
    const b = nodes[i + 1]
    let rel = (a === 'migration' || a === 'preemption') ? 'temporal' : 'correlated'
    if (a === 'migration' && (b === 'preemption' || b === 'wcet')) rel = 'causal'
    edges.push({
      from: a,
      to: b,
      relationship: rel,
      confidence: rel !== 'causal' ? 'Medium' : 'Low',
      evidence: list.slice(0, 3).map((f) => String(f.title || '')),
    })
  }
  const lines = ['graph TD']
  nodes.forEach((n, i) => lines.push(`N${i}[${n}]`))
  for (let i = 1; i < nodes.length; i += 1) lines.push(`N${i - 1} --> N${i}`)
  return {
    ok: true,
    message: `${nodes.length}-step causal chain`,
    nodes,
    edges,
    mermaid: lines.join('\n'),
    event_count: (events || []).filter((e) => e && typeof e === 'object').length,
    disclaimer: 'correlation should never silently become causation',
  }
}

export function generateExperimentPlan(findings = [], { task = '', limit = 3 } = {}) {
  const list = items(findings)
  const t = String(task || '').trim() || (list.length ? taskOf(list[0]) : 'the hot task')
  const b = list.map(blob).join(' ')
  const plans = []
  if (b.includes('migrat') || b.includes('thrash') || !b) {
    plans.push({
      title: `Pin ${t} to Core_0`,
      change: `pin ${t} to Core_0`,
      expected: 'migrations -40~60%',
      risk: 'load imbalance',
    })
  }
  if (b.includes('mutex') || b.includes('block')) {
    plans.push({
      title: 'Reduce mutex hold time 30%',
      change: `reduce mutex contention 30% for ${t}`,
      expected: 'blocking -25~35%',
      risk: 'throughput on holder',
    })
  }
  if (b.includes('invert') || b.includes('priorit')) {
    plans.push({
      title: `Raise waiter priority / shorten inherit for ${t}`,
      change: `raise priority of waiter of ${t}`,
      expected: 'PI duration -20%',
      risk: 'starve lower tasks',
    })
  }
  if (b.includes('deadline') || b.includes('wcet')) {
    plans.push({
      title: `Trim WCET of ${t}`,
      change: `reduce execution of ${t} 20%`,
      expected: 'deadline misses down',
      risk: 'feature cut',
    })
  }
  const cap = Math.max(1, Math.min(8, Number(limit) || 3))
  const sliced = plans.slice(0, cap)
  return {
    ok: true,
    message: `${sliced.length} experiment plan(s)`,
    task: t,
    experiments: sliced,
    actions: ['what_if', 'optimize_experiment', 'validate_experiment'],
  }
}

export function recordExperimentOutcome({
  change = '', predicted = '', actual = '', quality = '', fingerprint = null, findings = [],
} = {}) {
  const pred = String(predicted || '')
  const act = String(actual || '')
  let q = String(quality || '').trim().toUpperCase()
  if (!q) q = (pred && act && pred.slice(0, 8) === act.slice(0, 8)) ? 'GOOD' : (act ? 'PARTIAL' : 'UNKNOWN')
  const fp = fingerprint && typeof fingerprint === 'object' ? fingerprint : generateFingerprint(findings)
  const row = {
    id: `E${OUTCOMES.length + 1}`,
    change: String(change || ''),
    predicted: pred,
    actual: act,
    quality: q,
    fingerprint: fp,
    solution: String(change || ''),
    result: act,
    confidence_delta: q === 'GOOD' ? 1 : (q === 'BAD' ? -1 : 0),
  }
  OUTCOMES.push(row)
  return {
    ok: true,
    message: `Recorded outcome ${row.id} (${q})`,
    outcome: row,
    history_size: OUTCOMES.length,
    future_recommendation_confidence: row.confidence_delta > 0 ? 'up' : (row.confidence_delta < 0 ? 'down' : 'unchanged'),
  }
}

export function scoreInvestigationMetrics({
  expected = {},
  actualConclusion = '',
  tools = [],
  elapsedS = null,
  evidenceQuality = {},
  catalog = {},
  passed = true,
  confidence = '',
  findingScore = 0,
} = {}) {
  const toolsL = (tools || []).map((t) => String(t))
  const nTools = Math.max(toolsL.length, 1)
  const exp = expected && typeof expected === 'object' ? expected : {}
  const fs = Number.parseInt(findingScore, 10) || 0
  const evidenceEfficiency = Math.round(Math.min(100, fs / nTools * (nTools <= 3 ? 3 : 1)))
  const lat = elapsedS == null ? 0 : Number(elapsedS) || 0
  const investigationCost = Math.max(0, Math.min(100, 100 - 4 * toolsL.length - Math.min(40, lat)))
  const conf = String(confidence || '').toLowerCase()
  const bandQ = String(evidenceQuality?.band || '').toLowerCase()
  const highConf = conf.includes('high') || bandQ === 'strong' || bandQ === 'medium-high'
  const falseConfidence = (highConf && !passed) ? 0 : 100
  const falsifyTools = new Set(['detect_contradictions', 'manage_hypotheses', 'assess_evidence_sufficiency'])
  const falsificationQuality = toolsL.some((t) => falsifyTools.has(t))
    ? 100
    : (toolsL.includes('investigate') ? 60 : 30)
  const cat = catalog && typeof catalog === 'object' ? catalog : {}
  const wantTasks = [...(exp.tasks || cat.tasks || [])].map((x) => String(x).toLowerCase())
  const conc = String(actualConclusion || '').toLowerCase()
  let scopeAccuracy = 100
  if (wantTasks.length) {
    const hits = wantTasks.filter((t) => conc.includes(t)).length
    scopeAccuracy = Math.round(100 * hits / wantTasks.length)
  }
  let stopEfficiency = 100
  if (!toolsL.includes('assess_evidence_sufficiency')) {
    stopEfficiency = toolsL.length <= 6 ? 80 : Math.max(20, 80 - 8 * (toolsL.length - 6))
  }
  return {
    evidence_efficiency: evidenceEfficiency,
    investigation_cost: Math.round(investigationCost),
    false_confidence: falseConfidence,
    falsification_quality: falsificationQuality,
    scope_accuracy: scopeAccuracy,
    stop_efficiency: stopEfficiency,
  }
}

export function scoreInvestigationTool(findings = [], {
  toolsRun = [], elapsedS = null, conclusion = '', confidence = '',
} = {}) {
  const list = items(findings)
  const metrics = scoreInvestigationMetrics({
    actualConclusion: conclusion,
    tools: toolsRun,
    elapsedS,
    passed: true,
    confidence,
    findingScore: Math.min(100, 20 * list.length),
    catalog: { tasks: list.map(taskOf).filter(Boolean) },
  })
  return { ok: true, message: 'Investigation scores', ...metrics, tools_run: [...(toolsRun || [])] }
}
