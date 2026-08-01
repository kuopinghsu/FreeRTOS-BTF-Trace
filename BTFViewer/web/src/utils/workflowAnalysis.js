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

const FINDING_CAP = 5
const LOAD_SIGMA_WARN = 30.0
const LOAD_SCORE_WARN = 70.0
const LOAD_SCORE_OK = 85.0
const THRASH_PING_MIN = 3
const THRASH_RATE_PER_S = 1.0
const THRASH_MIG_MIN = 10
const PAIR_BOUNCE_PCT = 25.0
const PAIR_COUNT_MIN = 5

function giniCoefficient(values) {
  const n = values.length
  if (n < 2) return 0
  const total = values.reduce((a, b) => a + b, 0)
  if (total === 0) return 0
  const sorted = [...values].sort((a, b) => a - b)
  let cumsum = 0
  let giniNum = 0
  for (let i = 0; i < n; i++) {
    cumsum += sorted[i]
    giniNum += cumsum
  }
  return Math.max(0, Math.min(1, (n + 1) / n - (2 * giniNum) / (n * total)))
}

function coreUtilStddev(values) {
  const n = values.length
  if (n < 2) return 0
  const mean = values.reduce((a, b) => a + b, 0) / n
  return Math.sqrt(values.reduce((s, v) => s + (v - mean) ** 2, 0) / n)
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
  if (pcts.length >= 2) {
    const gini = giniCoefficient(pcts)
    const sigma = coreUtilStddev(pcts)
    const score = Math.max(0, 100 * (1 - gini))
    const metrics = `Load Balance Score ${score.toFixed(0)}% (σ=${sigma.toFixed(1)}%, G=${gini.toFixed(3)})`
    if (score < LOAD_SCORE_WARN || sigma > LOAD_SIGMA_WARN) {
      findings.push({
        severity: 'warning',
        title: 'Load imbalance across cores',
        text: `${metrics}. Uneven core placement — check Core Affinity and Core Migrations.`,
      })
    } else if (score >= LOAD_SCORE_OK) {
      findings.push({
        severity: 'info',
        title: 'Core utilisation balance',
        text: `${metrics} — cores look reasonably balanced.`,
      })
    } else {
      findings.push({
        severity: 'info',
        title: 'Core utilisation balance',
        text: `${metrics} — moderate spread; review Core Utilisation if the workload is expected to be even.`,
      })
    }
  }

  if (execRows.length) {
    const top = [...execRows]
      .sort((a, b) => (b.cpuPct ?? 0) - (a.cpuPct ?? 0))
      .slice(0, FINDING_CAP)
    const names = top.map(r => `${r.name} (${(r.cpuPct ?? 0).toFixed(1)}%, Max ${r.max})`).join(', ')
    findings.push({
      severity: 'info',
      title: 'Top tasks by CPU (WCET candidates)',
      text: `Highest CPU% tasks: ${names}. Open Execution Time and click Max to jump to the worst-case slice.`,
    })
  }

  if (blockRows.length) {
    const topB = [...blockRows]
      .sort((a, b) => (b.runs ?? 0) - (a.runs ?? 0) || String(a.name).localeCompare(String(b.name)))
      .slice(0, FINDING_CAP)
    const names = topB.map(r => `${r.name} (n=${r.runs}, Max ${r.max})`).join(', ')
    findings.push({
      severity: topB[0]?.runs >= 20 ? 'warning' : 'info',
      title: 'Blocking / response-time candidates',
      text: `Tasks with the most off-CPU gaps: ${names}. Cross-check Preemption Chain and Mutex/Semaphore.`,
    })
  }

  const invRows = (priorityRows || []).filter(r => String(r.pattern || '').includes('L/M/H'))
  if (invRows.length) {
    const names = invRows.slice(0, FINDING_CAP).map(r => r.label || r.name).join(', ')
    findings.push({
      severity: 'warning',
      title: 'Priority inversion (L/M/H) suspected',
      text: `Tasks with L/M/H pattern: ${names}. Inspect Priority Inheritance boost episodes and the holding mutex.`,
    })
  }

  const thrash = []
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
  }
  if (thrash.length) {
    findings.push({
      severity: 'warning',
      title: 'Excessive bouncing / core thrashing',
      text: `High migration rate, short dwell, and/or ping-pong detected: ${thrash.slice(0, FINDING_CAP).join('; ')}. See Core-Pair Migration Summary and the Migration Heatmap.`,
    })
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
    findings.push({
      severity: 'warning',
      title: 'Hot core-pair migration traffic',
      text: `Directed pairs with heavy traffic and/or lock-bounce share: ${hotPairs.slice(0, FINDING_CAP).join('; ')}.`,
    })
  }

  if (deadlineViols) {
    const sv = deadlineViols.sliceViolations || deadlineViols.slice_violations || []
    const cv = deadlineViols.cpuViolations || deadlineViols.cpu_violations || []
    if (sv.length || cv.length) {
      const parts = []
      if (sv.length) parts.push(`${sv.length} slice deadline violation(s)`)
      if (cv.length) parts.push(`${cv.length} CPU budget violation(s)`)
      findings.push({
        severity: 'error',
        title: 'Deadline / CPU budget breaches',
        text: `${parts.join(', ')} in scope. See Deadlines / CPU budget tables below.`,
      })
    }
  }

  if (tick?.tickCount) {
    const health = String(tick.health || '').toLowerCase()
    const missed = tick.missedTicksEstimate ?? tick.missed_estimate ?? 0
    if (health && health !== 'good') {
      findings.push({
        severity: health === 'bad' ? 'error' : 'warning',
        title: `Trace Health (TICK) = ${health.toUpperCase()}`,
        text: `Mode=${tick.isTickless ? 'TICKLESS' : 'TICK'}, CV=${((tick.tickCv || 0) * 100).toFixed(2)}%, missed≈${missed}. Investigate large TICK gaps and long slices.`,
      })
    } else if (missed > 0) {
      findings.push({
        severity: 'warning',
        title: 'Estimated missed ticks',
        text: `About ${missed} missed tick(s) estimated from large gaps. See Trace Health (TICK) large-gap table.`,
      })
    }
  }

  const bounceObjs = (syncRows || []).filter(r => (r.bounceCount || 0) > 0).length
  const bounceIssues = (syncIssues || []).filter(i => {
    const kind = String(i.kind || i.type || '').toUpperCase()
    const detail = String(i.detail || '').toLowerCase()
    return kind.includes('BOUNCE') || kind.includes('MIGRATION_WHILE_HELD') || detail.includes('bounc')
  }).length
  if (bounceObjs || bounceIssues) {
    findings.push({
      severity: 'warning',
      title: 'Mutex / semaphore core-boundary bounces',
      text: `${bounceObjs} sync object(s) with Core bounce > 0${bounceIssues ? `; ${bounceIssues} CORE_MIGRATION_WHILE_HELD-style issue(s)` : ''}. Cross-check Core-Pair Migration Summary Bounce %.`,
    })
  } else if ((syncIssues || []).length > 0) {
    findings.push({
      severity: 'warning',
      title: 'Sync pairing issues',
      text: `${syncIssues.length} mutex/semaphore pairing issue(s) in scope (orphan give, unmatched take, etc.).`,
    })
  }

  const actionable = findings.filter(f => f.severity === 'warning' || f.severity === 'error')
  if (!actionable.length && !findings.some(f => f.title.startsWith('Top tasks'))) {
    findings.push({
      severity: 'info',
      title: 'No analysis heuristics flagged',
      text: 'No load-imbalance, thrashing, deadline, tick, or sync warnings in the current scope. Review the tables below for detail.',
    })
  }

  return findings
}

function escHtml(v) {
  return String(v)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** @param {{severity: string, title: string, text: string}[]} findings */
export function formatAnalysisFindingsText(findings, scopeSuffix = '') {
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
      lines.push(`${i + 1}. [${sev}] ${f.title || 'Finding'}`)
      lines.push(`   ${f.text || ''}`)
      lines.push('')
    })
  }
  return `${lines.join('\n').replace(/\n+$/, '')}\n`
}

/** @param {{severity: string, title: string, text: string}[]} findings */
export function renderWorkflowAnalysisHtml(findings, scopeSuffix = '') {
  if (!findings?.length) return ''
  const items = findings.map(f => {
    const cls = f.severity === 'error'
      ? 'sev-error'
      : f.severity === 'warning'
        ? 'sev-warning'
        : 'finding-info'
    return `<li class="${cls}"><strong>${escHtml(f.title)}</strong> — ${escHtml(f.text)}</li>`
  }).join('')
  return `<section class="report-card notes analysis-findings">
    <h2>Analysis Findings${escHtml(scopeSuffix)}</h2>
    <p class="detail-note">Heuristic summary of load balance, WCET, blocking, thrashing, deadlines, tick health, and sync.</p>
    <ul class="findings-list">${items}</ul>
  </section>`
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
      execRows.push({
        name: disp,
        runs: execSum.runs,
        cpuPct: total > 0 ? 100 * taskTotal / total : 0,
        max: execSum.max,
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
