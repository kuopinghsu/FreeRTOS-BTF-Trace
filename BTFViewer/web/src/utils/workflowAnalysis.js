/**
 * Analysis Findings for Statistics HTML export and toolbar dialog
 * (parity with desktop _build_workflow_analysis_findings).
 */

import { formatTime } from './timeFormat.js'
import { parseTaskName, taskDisplayName, isIdleTaskName, taskReprGet } from './colors.js'
import { segFullyInRange, segOverlapsRange } from './statsRange.js'
import { blockingTimeSamples } from './statsAnalysis.js'
import { migrationRows, buildCorePairRows } from './migrationAnalysis.js'
import { priorityStatsRows } from './priorityAnalysis.js'
import { syncObjectStatsRows } from './syncObjectAnalysis.js'
import { tickHealthReport } from './tickHealth.js'
import { computeDeadlineViolations } from './deadlineAnalysis.js'
import loadBalanceMetrics from './loadBalanceGauge.js'
import {
  appendMigrationBurstAnomaly,
  appendWcetAnomalyFinding,
  enrichFindingsWithIds,
} from './aiInvestigation.js'
import { htmlFindingCards } from './statsHtmlReport.js'
import { formatTriageAuditText } from './findingsTriage.js'

const FINDING_CAP = 5
const LOAD_SIGMA_WARN = 30.0
const LOAD_SCORE_WARN = 70.0
const LOAD_SCORE_OK = 85.0
const THRASH_PING_MIN = 3
const THRASH_RATE_PER_S = 1.0
const THRASH_MIG_MIN = 10
const PAIR_BOUNCE_PCT = 25.0
const PAIR_COUNT_MIN = 5
const WCET_MAX_AVG_RATIO = 5.0
const MIG_BURST_RATE = 10.0

/**
 * Analysis Finding id -> Statistics section id (Step-1 item 7: non-AI
 * "Investigate" routes straight to the relevant Statistics section instead
 * of requiring the AI Assistant).
 */
export const FINDING_SECTION_MAP = Object.freeze({
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
})

function finding(severity, title, text, extra = {}) {
  return {
    severity,
    title,
    text,
    id: extra.id || '',
    task: extra.task || '',
    evidence: extra.evidence || [],
    impact: extra.impact || '',
    inspect: extra.inspect || '',
    inspect_href: extra.inspect_href || extra.inspectHref || '',
    confidence: extra.confidence || '',
    evidence_text: extra.evidence_text || extra.evidenceText || '',
  }
}

/**
 * @returns {{severity: string, title: string, text: string}[]}
 */
export function buildWorkflowAnalysisFindings({
  coreRows = [],
  execRows = [],
  blockRows = [],
  migRows = [],
  pairRows = [],
  priorityRows = [],
  syncRows = [],
  syncIssues = [],
  tick = null,
  deadlineViols = null,
  timeScale = 'ns',
} = {}) {
  const findings = []

  const pcts = coreRows.map(r => (typeof r === 'object' ? r.pct : r[1])).filter(v => v != null)
  const lb = loadBalanceMetrics(pcts)
  if (lb) {
    const score = lb.score
    const gini = lb.gini
    const sigma = lb.stddev
    const metrics = `Load Balance Score ${score.toFixed(0)}% (σ=${sigma.toFixed(1)}%, G=${gini.toFixed(3)})`
    if (score < LOAD_SCORE_WARN || sigma > LOAD_SIGMA_WARN) {
      findings.push(finding(
        'warning',
        'Load imbalance across cores',
        `${metrics}. Uneven core placement — check Core Affinity and Core Migrations.`,
        {
          id: 'load_imbalance',
          impact: 'Uneven utilisation can hide a hot core even when average load looks fine.',
          inspect: 'Core Utilisation (excl. IDLE/TICK)',
          confidence: 'High — derived from measured core utilisation',
          evidence_text: metrics,
        },
      ))
    } else if (score >= LOAD_SCORE_OK) {
      findings.push(finding(
        'info',
        'Core utilisation balance',
        `${metrics} — cores look reasonably balanced. A high score means even distribution, not healthy utilisation.`,
        {
          id: 'load_balance_ok',
          inspect: 'Core Utilisation (excl. IDLE/TICK)',
          confidence: 'High — derived from measured core utilisation',
          evidence_text: metrics,
        },
      ))
    } else {
      findings.push(finding(
        'info',
        'Core utilisation balance',
        `${metrics} — moderate spread; review Core Utilisation if the workload is expected to be even.`,
        {
          id: 'load_balance_moderate',
          inspect: 'Core Utilisation (excl. IDLE/TICK)',
          confidence: 'High — derived from measured core utilisation',
          evidence_text: metrics,
        },
      ))
    }
  }

  if (execRows.length) {
    const top = [...execRows]
      .sort((a, b) => (b.cpuPct ?? 0) - (a.cpuPct ?? 0))
      .slice(0, FINDING_CAP)
    const names = top.map(r => `${r.name} (${(r.cpuPct ?? 0).toFixed(1)}%)`).join(', ')
    findings.push(finding(
      'info',
      'Highest CPU consumers',
      `Largest share of active CPU time: ${names}. High CPU share is not the same as a long worst-case slice.`,
      {
        id: 'top_cpu',
        inspect: 'Top Tasks by CPU (excl. IDLE/TICK)',
        confidence: 'High — measured CPU share',
        evidence_text: names,
      },
    ))
    const byMax = [...execRows].sort((a, b) => String(b.max || '').localeCompare(String(a.max || ''), undefined, { numeric: true }))
    const maxNames = byMax.slice(0, FINDING_CAP).map(r => `${r.name} (Max ${r.max})`).join(', ')
    if (maxNames) {
      findings.push(finding(
        'info',
        'Largest execution-time maxima',
        `Longest observed slices: ${maxNames}. See Execution Time Per Slice for the maximum observed slice. These are observed maxima, not proven WCET.`,
        {
          id: 'exec_max',
          inspect: 'Execution Time Per Slice',
          confidence: 'High — measured slice durations',
          evidence_text: maxNames,
        },
      ))
    }
  }

  if (blockRows.length) {
    const topB = [...blockRows]
      .sort((a, b) => (b.runs ?? 0) - (a.runs ?? 0) || String(a.name).localeCompare(String(b.name)))
      .slice(0, FINDING_CAP)
    const names = topB.map(r => `${r.name} (n=${r.runs}, Max ${r.max})`).join(', ')
    findings.push(finding(
      topB[0]?.runs >= 20 ? 'warning' : 'info',
      'Off-CPU / scheduling-delay candidates',
      `Tasks with the most off-CPU gaps: ${names}. Cross-check Preemption Chain and Mutex/Semaphore. Off-CPU time is not necessarily resource blocking.`,
      {
        id: 'blocking',
        inspect: 'Off-CPU Time (Blocking Time)',
        confidence: 'Medium — measured gaps, mixed causes',
        evidence_text: names,
        impact: 'Long or frequent off-CPU gaps delay the next resume.',
      },
    ))
  }

  const invRows = (priorityRows || []).filter(r => String(r.pattern || '').includes('L/M/H'))
  if (invRows.length) {
    const names = invRows.slice(0, FINDING_CAP).map(r => r.label || r.name).join(', ')
    findings.push(finding(
      'warning',
      'Priority inversion (L/M/H) suspected',
      `Tasks with L/M/H pattern: ${names}. Inspect Priority Inheritance boost episodes and the holding mutex.`,
      { id: 'priority_inversion' },
    ))
  }

  const thrash = []
  const burstRows = []
  for (const r of migRows || []) {
    const nMig = r.migrations ?? 0
    const ping = r.pingPong ?? 0
    const ratePerS = r.ratePerS ?? -1
    const dwellTu = r.avgDwellTu ?? -1
    const primaryPct = r.primaryPct ?? 100
    const coreCount = r.coreCount ?? 0
    const hot = (
      ping >= THRASH_PING_MIN
      || (ratePerS >= THRASH_RATE_PER_S && nMig >= THRASH_MIG_MIN)
      || (nMig >= THRASH_MIG_MIN && dwellTu > 0 && primaryPct < 55 && coreCount >= 2)
    )
    if (hot) {
      thrash.push(
        `${r.name} (Migr=${nMig}, Rate=${r.migrRate}, Dwell=${r.avgDwell}, Ping=${ping})`,
      )
    }
    if (Number.isFinite(ratePerS)) burstRows.push([r.name, ratePerS, nMig])
  }
  if (thrash.length) {
    findings.push(finding(
      'warning',
      'Excessive core migration',
      `High migration rate, short dwell, and/or ping-pong detected: ${thrash.slice(0, FINDING_CAP).join('; ')}. See Core Migrations and Core-Pair Migration Summary.`,
      {
        id: 'thrashing',
        inspect: 'Core Migrations',
        confidence: 'Medium — heuristic threshold',
        evidence_text: thrash.slice(0, FINDING_CAP).join('; '),
        impact: 'May increase cache misses and scheduling overhead.',
      },
    ))
  }

  const hotPairs = []
  for (const r of pairRows || []) {
    const cnt = r.count ?? 0
    const bnc = r.bounces ?? r.bounceCount ?? 0
    const bouncePct = r.bouncePct != null ? r.bouncePct : (cnt ? 100 * bnc / cnt : 0)
    const avgGapNs = r.avgGapNs ?? 0
    if (cnt >= PAIR_COUNT_MIN && bouncePct >= PAIR_BOUNCE_PCT) {
      hotPairs.push(
        `${r.fromCore}→${r.toCore} (Count=${cnt}, Bounce=${bouncePct.toFixed(0)}%, AvgGap=${avgGapNs ? formatTime(avgGapNs, timeScale) : '—'})`,
      )
    } else if (cnt >= Math.max(PAIR_COUNT_MIN * 2, 20) && !thrash.length) {
      hotPairs.push(`${r.fromCore}→${r.toCore} (Count=${cnt})`)
    }
  }
  if (hotPairs.length) {
    findings.push(finding(
      'warning',
      'Hot core-pair migration traffic',
      `Directed pairs with heavy traffic and/or lock-bounce share: ${hotPairs.slice(0, FINDING_CAP).join('; ')}.`,
      { id: 'hot_pairs' },
    ))
  }

  if (deadlineViols) {
    const sv = deadlineViols.sliceViolations || deadlineViols.slice_violations || []
    const cv = deadlineViols.cpuViolations || deadlineViols.cpu_violations || []
    if (sv.length || cv.length) {
      const parts = []
      if (sv.length) parts.push(`${sv.length} slice deadline violation(s)`)
      if (cv.length) parts.push(`${cv.length} CPU budget violation(s)`)
      findings.push(finding(
        'error',
        'Deadline / CPU budget breaches',
        `${parts.join(', ')} in scope. See Deadlines / CPU budget tables below.`,
        { id: 'deadlines' },
      ))
    }
  }

  if (tick?.tickCount) {
    const health = String(tick.health || '').toLowerCase()
    const missed = tick.missedTicksEstimate ?? tick.missed_estimate ?? 0
    if (health && health !== 'good') {
      findings.push(finding(
        health === 'bad' ? 'error' : 'warning',
        `Trace Health (TICK) = ${health.toUpperCase()}`,
        `Mode=${tick.isTickless ? 'TICKLESS' : 'TICK'}, CV=${((tick.tickCv || 0) * 100).toFixed(2)}%, missed≈${missed}. Investigate large TICK gaps and long slices.`,
        { id: 'tick_health' },
      ))
    } else if (missed > 0) {
      findings.push(finding(
        'warning',
        'Estimated missed ticks',
        `About ${missed} missed tick(s) estimated from large gaps. See Trace Health (TICK) large-gap table.`,
        { id: 'missed_ticks' },
      ))
    }
  }

  const bounceObjs = (syncRows || []).filter(r => (r.bounceCount || 0) > 0).length
  const bounceIssues = (syncIssues || []).filter(i => {
    const kind = String(i.kind || i.type || '').toUpperCase()
    const detail = String(i.detail || '').toLowerCase()
    return kind.includes('BOUNCE') || kind.includes('MIGRATION_WHILE_HELD') || detail.includes('bounc')
  }).length
  if (bounceObjs || bounceIssues) {
    findings.push(finding(
      'warning',
      'Mutex / semaphore core-boundary bounces',
      `${bounceObjs} sync object(s) with Core bounce > 0${bounceIssues ? `; ${bounceIssues} CORE_MIGRATION_WHILE_HELD-style issue(s)` : ''}. Cross-check Core-Pair Migration Summary Bounce %.`,
      { id: 'sync_bounce' },
    ))
  } else if ((syncIssues || []).length > 0) {
    findings.push(finding(
      'warning',
      'Sync pairing issues',
      `${syncIssues.length} mutex/semaphore pairing issue(s) in scope (orphan give, unmatched take, etc.).`,
      { id: 'sync_issues' },
    ))
  }

  const thrashNames = new Set(thrash.map(t => String(t).split(' ')[0]))
  appendMigrationBurstAnomaly(
    findings,
    burstRows.filter(row => !thrashNames.has(row[0])),
    { rateThreshold: MIG_BURST_RATE },
  )

  // WCET anomalies when callers pass avgNs/maxNs/runs on exec rows
  const spikeRows = []
  for (const r of execRows || []) {
    if (r.avgNs != null && r.maxNs != null && r.runs != null) {
      spikeRows.push([r.name, r.avgNs, r.maxNs, r.runs])
    }
  }
  appendWcetAnomalyFinding(findings, spikeRows, { ratioThreshold: WCET_MAX_AVG_RATIO })

  const actionable = findings.filter(f => f.severity === 'warning' || f.severity === 'error')
  if (!actionable.length && !findings.some(f => f.id === 'top_cpu')) {
    findings.push(finding(
      'info',
      'No analysis heuristics flagged',
      'No load-imbalance, thrashing, deadline, tick, or sync warnings in the current scope. Review the tables below for detail.',
      { id: 'none' },
    ))
  }

  return enrichFindingsWithIds(findings)
}

function escHtml(v) {
  return String(v)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** @param {{severity: string, title: string, text: string}[]} findings */
export function formatAnalysisFindingsText(findings, scopeSuffix = '', {
  triageState = null,
} = {}) {
  const lines = [`Analysis Findings${scopeSuffix || ''}`.trimEnd(), '']
  lines.push(
    'Heuristic summary of load balance, WCET, blocking, thrashing, deadlines, tick health, and sync.',
    '',
  )
  if (!findings?.length) {
    lines.push('No findings for the current scope')
  } else {
    findings.forEach((f, i) => {
      const sev = String(f.severity || 'info').toUpperCase()
      const fid = String(f.id || '').trim()
      const idBit = fid ? ` id=${fid}` : ''
      lines.push(`${i + 1}. [${sev}]${idBit} ${f.title || 'Finding'}`)
      lines.push(`   ${f.text || ''}`)
      for (const ev of (f.evidence || [])) {
        if (ev && typeof ev === 'object' && ev.time != null) {
          lines.push(`   evidence: ${ev.label || 'event'} jump:${ev.time}`)
        } else if (ev) {
          lines.push(`   evidence: ${ev}`)
        }
      }
      lines.push('')
    })
  }
  if (triageState) {
    const audit = formatTriageAuditText(findings, triageState)
    if (audit) {
      lines.push('')
      lines.push(audit)
    }
  }
  return `${lines.join('\n').replace(/\n+$/, '')}\n`
}

/** @param {{severity: string, title: string, text: string}[]} findings */
export function renderWorkflowAnalysisHtml(findings, scopeSuffix = '') {
  return htmlFindingCards(findings, scopeSuffix)
}

function _fmtDur(ns, scale) {
  if (ns == null || ns < 0) return '—'
  return formatTime(ns, scale)
}

function _summarizeDurs(samples, scale) {
  if (!samples.length) return null
  const sorted = [...samples].sort((a, b) => a - b)
  const n = sorted.length
  const avg = sorted.reduce((a, b) => a + b, 0) / n
  return {
    runs: n,
    min: _fmtDur(sorted[0], scale),
    avg: _fmtDur(avg, scale),
    max: _fmtDur(sorted[n - 1], scale),
  }
}

/**
 * Build findings for a loaded trace (toolbar Analysis dialog + HTML export).
 * @param {object} trace
 * @param {number|null} lo
 * @param {number|null} hi
 * @param {object} [analysisSettings]
 */
export function collectTraceAnalysisFindings(trace, lo = null, hi = null, analysisSettings = {}) {
  if (!trace) return []

  const scale = trace.timeScale || 'ns'
  const total = (lo != null && hi != null)
    ? (hi - lo)
    : (trace.timeMax - trace.timeMin)

  const coreRows = []
  for (const core of (trace.coreNames || [])) {
    const segs = trace.coreSegs?.get?.(core) || []
    let active = 0
    for (const s of segs) {
      const { name } = parseTaskName(s.task)
      if (name === 'TICK' || isIdleTaskName(name)) continue
      if (lo != null && hi != null) {
        if (!segOverlapsRange(s, lo, hi)) continue
        active += Math.min(s.end, hi) - Math.max(s.start, lo)
      } else {
        active += s.end - s.start
      }
    }
    coreRows.push({ core, pct: total > 0 ? 100 * active / total : 0 })
  }

  const execRows = []
  const blockRows = []
  for (const [mk, segs] of (trace.segByMergeKey || [])) {
    if (!segs?.length) continue
    const raw = taskReprGet(trace, mk) || mk
    const { name } = parseTaskName(raw)
    if (isIdleTaskName(name) || name === 'TICK') continue
    const disp = taskDisplayName(raw)

    const execSamples = []
    for (const s of segs) {
      const d = s.end - s.start
      if (d <= 0) continue
      if (lo != null && hi != null && !segFullyInRange(s, lo, hi)) continue
      execSamples.push(d)
    }
    const execSum = _summarizeDurs(execSamples, scale)
    if (execSum) {
      const taskTotal = execSamples.reduce((a, b) => a + b, 0)
      const avgNs = execSamples.reduce((a, b) => a + b, 0) / execSamples.length
      const maxNs = Math.max(...execSamples)
      execRows.push({
        name: disp,
        runs: execSum.runs,
        cpuPct: total > 0 ? 100 * taskTotal / total : 0,
        max: execSum.max,
        avgNs,
        maxNs,
      })
    }

    if (segs.length >= 2) {
      const gaps = blockingTimeSamples(segs, lo, hi)
      const blockSum = _summarizeDurs(gaps, scale)
      if (blockSum) {
        blockRows.push({ name: disp, runs: blockSum.runs, max: blockSum.max })
      }
    }
  }

  const syncRows = trace.hasSyncObjectInstrumentation
    ? syncObjectStatsRows(trace, lo, hi)
    : []
  const budget = Number(analysisSettings.cpuBudgetPct)
  const deadlines = analysisSettings.taskDeadlines || {}
  const hasDeadline = (Number.isFinite(budget) && budget > 0)
    || Object.keys(deadlines).length > 0

  return buildWorkflowAnalysisFindings({
    coreRows,
    execRows,
    blockRows,
    migRows: migrationRows(trace, lo, hi),
    pairRows: buildCorePairRows(trace, lo, hi),
    priorityRows: trace.hasPriorityInstrumentation
      ? priorityStatsRows(trace, lo, hi)
      : [],
    syncRows,
    syncIssues: syncRows.flatMap(r => r.issues || []),
    tick: tickHealthReport(trace, lo, hi),
    deadlineViols: hasDeadline
      ? computeDeadlineViolations(trace, analysisSettings, lo, hi)
      : null,
    timeScale: scale,
  })
}
