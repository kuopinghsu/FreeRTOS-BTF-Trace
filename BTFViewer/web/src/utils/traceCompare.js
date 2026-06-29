/**
 * Compare summary and per-task metrics between two loaded traces.
 * Optional lo/hi per trace for cursor-scoped compare.
 */

import { formatTime, isStiTagChannel } from '../renderer/TimelineRenderer.js'
import { parseTaskName, taskDisplayName, taskLabelForMergeKey, taskReprGet, isIdleTaskName } from './colors.js'
import { schedulingStats, maxNs, blockingTimeSamples, preemptionChainRows } from './statsAnalysis.js'
import { isMigratedTask, migrationRows } from './migrationAnalysis.js'
import { syncObjectStatsRows } from './syncObjectAnalysis.js'
import { getPlacedCursors } from './statsRange.js'

export function cursorRangeForCursors(cursors) {
  const placed = getPlacedCursors(cursors || [])
  if (placed.length < 2) return { lo: null, hi: null }
  const sorted = [...placed].sort((a, b) => a - b)
  return { lo: sorted[0], hi: sorted[sorted.length - 1] }
}

export function traceSummarySnapshot(trace, lo = null, hi = null) {
  if (!trace) return null
  const fullSpan = trace.timeMax - trace.timeMin
  const spanNs = (lo != null && hi != null) ? Math.max(0, hi - lo) : fullSpan
  const stiEvents = (trace.stiEvents || []).filter(ev => {
    if (isStiTagChannel(ev.target)) return false
    if (lo != null && hi != null) return ev.time >= lo && ev.time <= hi
    return true
  }).length
  const { contextSwitches, coreGaps, gapMax } = schedulingStats(trace, lo, hi)
  const gapAvgNs = coreGaps.length
    ? Math.round(coreGaps.reduce((a, b) => a + b, 0) / coreGaps.length)
    : 0
  const gapMaxNs = coreGaps.length ? gapMax : 0
  let migrations = trace.migrations?.length ?? 0
  let migratedTasks = (trace.tasks || []).filter(mk => isMigratedTask(trace, mk)).length
  if (lo != null && hi != null) {
    migrations = (trace.migrations || []).filter(m => m.ns >= lo && m.ns <= hi).length
    migratedTasks = migrationRows(trace, lo, hi).length
  }
  return {
    spanNs,
    tasks: trace.tasks?.length ?? 0,
    segments: lo != null && hi != null
      ? trace.segments.filter(s => s.end > lo && s.start < hi).length
      : (trace.segments?.length ?? 0),
    stiEvents,
    contextSwitches,
    gapAvgNs,
    gapMaxNs,
    migrations,
    migratedTasks,
    timeScale: trace.timeScale,
  }
}

/** Top tasks by CPU% keyed by display name. */
export function topTasksCpuByName(trace, limit = 10, lo = null, hi = null) {
  if (!trace?.segByMergeKey) return new Map()
  const total = (lo != null && hi != null)
    ? Math.max(1, hi - lo)
    : Math.max(1, trace.timeMax - trace.timeMin)
  const accum = new Map()
  for (const [mk, segs] of trace.segByMergeKey) {
    const repr = taskReprGet(trace, mk) ?? mk
    const { name } = parseTaskName(repr)
    if (isIdleTaskName(name) || name === 'TICK') continue
    let t = 0
    for (const s of segs) {
      if (lo != null && hi != null) {
        if (s.end <= lo || s.start >= hi) continue
        t += Math.min(s.end, hi) - Math.max(s.start, lo)
      } else {
        t += s.end - s.start
      }
    }
    if (t > 0) accum.set(mk, t)
  }
  const sorted = [...accum.entries()].sort((a, b) => b[1] - a[1]).slice(0, limit)
  const out = new Map()
  for (const [mk, t] of sorted) {
    const name = taskDisplayName(taskReprGet(trace, mk) ?? mk)
    out.set(name, 100.0 * t / total)
  }
  return out
}

function fmtSignedTime(deltaNs, scale) {
  if (deltaNs === 0) return '0'
  const sign = deltaNs > 0 ? '+' : '−'
  return `${sign}${formatTime(Math.abs(deltaNs), scale)}`
}

function fmtSignedInt(delta) {
  if (delta === 0) return '0'
  return delta > 0 ? `+${delta}` : String(delta)
}

function fmtSignedPct(delta) {
  if (Math.abs(delta) < 0.05) return '0.0'
  const sign = delta > 0 ? '+' : ''
  return `${sign}${delta.toFixed(1)}`
}

function rangeForTab(tab, scopeEnabled) {
  if (!scopeEnabled || !tab) return { lo: null, hi: null }
  return cursorRangeForCursors(tab.cursors)
}

export function buildSummaryCompareRows(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false) {
  const ra = rangeForTab(tabA, scopeEnabled)
  const rb = rangeForTab(tabB, scopeEnabled)
  const a = traceSummarySnapshot(traceA, ra.lo, ra.hi)
  const b = traceSummarySnapshot(traceB, rb.lo, rb.hi)
  if (!a || !b) return []
  const scale = a.timeScale || b.timeScale || 'ns'
  return [
    {
      label: scopeEnabled ? 'Span (cursor range)' : 'Span',
      a: formatTime(a.spanNs, scale),
      b: formatTime(b.spanNs, scale),
      delta: fmtSignedTime(a.spanNs - b.spanNs, scale),
    },
    { label: 'Tasks', a: a.tasks, b: b.tasks, delta: fmtSignedInt(a.tasks - b.tasks) },
    { label: 'Segments', a: a.segments, b: b.segments, delta: fmtSignedInt(a.segments - b.segments) },
    { label: 'STI events', a: a.stiEvents, b: b.stiEvents, delta: fmtSignedInt(a.stiEvents - b.stiEvents) },
    {
      label: 'Context switches',
      a: a.contextSwitches,
      b: b.contextSwitches,
      delta: fmtSignedInt(a.contextSwitches - b.contextSwitches),
    },
    {
      label: 'Core gap avg',
      a: formatTime(a.gapAvgNs, scale),
      b: formatTime(b.gapAvgNs, scale),
      delta: fmtSignedTime(a.gapAvgNs - b.gapAvgNs, scale),
    },
    {
      label: 'Core gap max',
      a: formatTime(a.gapMaxNs, scale),
      b: formatTime(b.gapMaxNs, scale),
      delta: fmtSignedTime(a.gapMaxNs - b.gapMaxNs, scale),
    },
    {
      label: 'Migrations (total)',
      a: a.migrations,
      b: b.migrations,
      delta: fmtSignedInt(a.migrations - b.migrations),
    },
    {
      label: 'Migrated tasks',
      a: a.migratedTasks,
      b: b.migratedTasks,
      delta: fmtSignedInt(a.migratedTasks - b.migratedTasks),
    },
  ]
}

export function buildTopTasksCompareRows(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false, limit = 10) {
  const ra = rangeForTab(tabA, scopeEnabled)
  const rb = rangeForTab(tabB, scopeEnabled)
  const mapA = topTasksCpuByName(traceA, limit, ra.lo, ra.hi)
  const mapB = topTasksCpuByName(traceB, limit, rb.lo, rb.hi)
  const names = new Set([...mapA.keys(), ...mapB.keys()])
  return [...names]
    .sort((x, y) => {
      const maxX = Math.max(mapA.get(x) || 0, mapB.get(x) || 0)
      const maxY = Math.max(mapA.get(y) || 0, mapB.get(y) || 0)
      return maxY - maxX || x.localeCompare(y)
    })
    .map((name) => {
      const cpuA = mapA.get(name)
      const cpuB = mapB.get(name)
      const aVal = cpuA ?? 0
      const bVal = cpuB ?? 0
      return {
        name,
        cpuA: cpuA != null ? cpuA.toFixed(1) : '—',
        cpuB: cpuB != null ? cpuB.toFixed(1) : '—',
        delta: fmtSignedPct(aVal - bVal),
      }
    })
}

function signedRateDelta(rateA, rateB) {
  if (rateA < 0 || rateB < 0) return '—'
  const d = rateA - rateB
  if (Math.abs(d) < 0.005) return '0'
  return (d >= 0 ? '+' : '') + d.toFixed(2) + '/s'
}

function signedDwellDelta(dwellA, dwellB, timeScale) {
  if (dwellA < 0 || dwellB < 0) return '—'
  const d = dwellA - dwellB
  if (d === 0) return '0'
  const sign = d > 0 ? '+' : '−'
  return sign + formatTime(Math.abs(d), timeScale)
}

export function buildMigrationCompareRows(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false) {
  const ra = rangeForTab(tabA, scopeEnabled)
  const rb = rangeForTab(tabB, scopeEnabled)
  const mapA = new Map()
  const mapB = new Map()
  if (traceA) {
    for (const row of migrationRows(traceA, ra.lo, ra.hi)) {
      mapA.set(row.mk, row)
    }
  }
  if (traceB) {
    for (const row of migrationRows(traceB, rb.lo, rb.hi)) {
      mapB.set(row.mk, row)
    }
  }
  const keys = [...new Set([...mapA.keys(), ...mapB.keys()])]
  keys.sort((a, b) => {
    const na = (mapA.get(a) || mapB.get(a))?.name ?? taskLabelForMergeKey(traceA || traceB, a)
    const nb = (mapA.get(b) || mapB.get(b))?.name ?? taskLabelForMergeKey(traceA || traceB, b)
    return na.localeCompare(nb)
  })
  const timeScale = traceA?.timeScale || traceB?.timeScale || 'us'
  return keys.map((mk) => {
    const raRow = mapA.get(mk)
    const rbRow = mapB.get(mk)
    const ma = raRow?.migrations ?? 0
    const mb = rbRow?.migrations ?? 0
    const rateA = raRow?.ratePerS ?? -1
    const rateB = rbRow?.ratePerS ?? -1
    const dwellA = raRow?.avgDwellTu ?? -1
    const dwellB = rbRow?.avgDwellTu ?? -1
    return {
      mk,
      name: raRow?.name ?? rbRow?.name ?? taskLabelForMergeKey(traceA || traceB, mk),
      migrationsA: ma,
      migrationsB: mb,
      delta: ma - mb,
      rateA: raRow?.migrRate ?? '—',
      rateB: rbRow?.migrRate ?? '—',
      rateDelta: signedRateDelta(rateA, rateB),
      dwellA: raRow?.avgDwell ?? '—',
      dwellB: rbRow?.avgDwell ?? '—',
      dwellDelta: signedDwellDelta(dwellA, dwellB, timeScale),
      pingA: raRow?.pingPong ?? 0,
      pingB: rbRow?.pingPong ?? 0,
    }
  })
}

function blockingSummaryByName(trace, lo, hi) {
  const map = new Map()
  if (!trace?.segByMergeKey) return map
  const scale = trace.timeScale
  for (const [mk, segs] of trace.segByMergeKey) {
    const samples = blockingTimeSamples(segs, lo, hi)
    if (!samples.length) continue
    const name = taskDisplayName(taskReprGet(trace, mk) ?? mk)
    const avgNs = Math.round(samples.reduce((a, b) => a + b, 0) / samples.length)
    map.set(name, { avgNs, gaps: samples.length, avg: formatTime(avgNs, scale) })
  }
  return map
}

export function buildBlockingCompareRows(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false, limit = 15) {
  const ra = rangeForTab(tabA, scopeEnabled)
  const rb = rangeForTab(tabB, scopeEnabled)
  const mapA = blockingSummaryByName(traceA, ra.lo, ra.hi)
  const mapB = blockingSummaryByName(traceB, rb.lo, rb.hi)
  const names = [...new Set([...mapA.keys(), ...mapB.keys()])]
    .sort((a, b) => {
      const ga = Math.max(mapA.get(a)?.gaps ?? 0, mapB.get(a)?.gaps ?? 0)
      const gb = Math.max(mapA.get(b)?.gaps ?? 0, mapB.get(b)?.gaps ?? 0)
      return gb - ga || a.localeCompare(b)
    })
    .slice(0, limit)
  const scale = traceA?.timeScale || traceB?.timeScale || 'ns'
  return names.map((name) => {
    const a = mapA.get(name)
    const b = mapB.get(name)
    const avgA = a?.avgNs ?? 0
    const avgB = b?.avgNs ?? 0
    return {
      name,
      gapsA: a?.gaps ?? 0,
      gapsB: b?.gaps ?? 0,
      avgA: a?.avg ?? '—',
      avgB: b?.avg ?? '—',
      delta: fmtSignedTime(avgA - avgB, scale),
    }
  })
}

function preemptionTotalsByVictim(trace, lo, hi) {
  const map = new Map()
  const { rows } = preemptionChainRows(trace, lo, hi)
  for (const row of rows) {
    const cur = map.get(row.victim) || { count: 0, totalNs: 0 }
    cur.count += row.count
    cur.totalNs += row.totalNs
    map.set(row.victim, cur)
  }
  return map
}

export function buildPreemptionCompareRows(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false, limit = 15) {
  const ra = rangeForTab(tabA, scopeEnabled)
  const rb = rangeForTab(tabB, scopeEnabled)
  const mapA = preemptionTotalsByVictim(traceA, ra.lo, ra.hi)
  const mapB = preemptionTotalsByVictim(traceB, rb.lo, rb.hi)
  const names = [...new Set([...mapA.keys(), ...mapB.keys()])]
    .sort((a, b) => (mapB.get(b)?.count ?? 0) - (mapA.get(a)?.count ?? 0) || a.localeCompare(b))
    .slice(0, limit)
  const scale = traceA?.timeScale || traceB?.timeScale || 'ns'
  return names.map((name) => {
    const a = mapA.get(name)
    const b = mapB.get(name)
    const ca = a?.count ?? 0
    const cb = b?.count ?? 0
    return {
      name,
      countA: ca,
      countB: cb,
      delta: fmtSignedInt(ca - cb),
      totalA: a ? formatTime(a.totalNs, scale) : '—',
      totalB: b ? formatTime(b.totalNs, scale) : '—',
    }
  })
}

function syncSummary(trace, lo, hi) {
  if (!trace?.hasSyncObjectInstrumentation) {
    return { objects: 0, holds: 0, issues: 0, queue: 0, mutex: 0, sem: 0 }
  }
  const rows = syncObjectStatsRows(trace, lo, hi)
  const out = { objects: rows.length, holds: 0, issues: 0, queue: 0, mutex: 0, sem: 0 }
  for (const row of rows) {
    out.holds += row.holdCount
    out.issues += row.issueCount
    if (row.kind === 'queue') out.queue++
    else if (row.kind === 'mutex') out.mutex++
    else if (row.kind === 'sem') out.sem++
  }
  return out
}

export function buildSyncCompareRows(traceA, traceB, tabA = null, tabB = null, scopeEnabled = false) {
  const ra = rangeForTab(tabA, scopeEnabled)
  const rb = rangeForTab(tabB, scopeEnabled)
  const a = syncSummary(traceA, ra.lo, ra.hi)
  const b = syncSummary(traceB, rb.lo, rb.hi)
  return [
    { label: 'Sync objects', a: a.objects, b: b.objects, delta: fmtSignedInt(a.objects - b.objects) },
    { label: 'Holds (paired)', a: a.holds, b: b.holds, delta: fmtSignedInt(a.holds - b.holds) },
    { label: 'Issues', a: a.issues, b: b.issues, delta: fmtSignedInt(a.issues - b.issues) },
    { label: 'Mutex objects', a: a.mutex, b: b.mutex, delta: fmtSignedInt(a.mutex - b.mutex) },
    { label: 'Semaphore objects', a: a.sem, b: b.sem, delta: fmtSignedInt(a.sem - b.sem) },
    { label: 'Queue objects', a: a.queue, b: b.queue, delta: fmtSignedInt(a.queue - b.queue) },
  ]
}

function csvCell(v) {
  const s = String(v ?? '')
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`
  return s
}

function htmlCell(v) {
  return String(v ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** Build CSV text for a trace-compare export. */
export function buildCompareCsv(
  nameA, nameB, summaryRows, topTaskRows, migrationRows, scopeEnabled,
  blockingRows = [], preemptionRows = [], syncRows = [],
) {
  const lines = []
  lines.push(`Trace A,${csvCell(nameA)}`)
  lines.push(`Trace B,${csvCell(nameB)}`)
  lines.push(`Cursor scope per tab,${scopeEnabled ? 'yes' : 'no'}`)
  lines.push('')

  lines.push('Summary')
  lines.push('Metric,Trace A,Trace B,Δ')
  for (const row of summaryRows) {
    lines.push([csvCell(row.label), csvCell(row.a), csvCell(row.b), csvCell(row.delta)].join(','))
  }

  lines.push('')
  lines.push('Top Tasks')
  lines.push('Task,CPU% A,CPU% B,Δ')
  for (const row of topTaskRows) {
    lines.push([csvCell(row.name), csvCell(row.cpuA), csvCell(row.cpuB), csvCell(row.delta)].join(','))
  }

  lines.push('')
  lines.push('Core Migrations')
  lines.push('Task,Migrations A,Migrations B,Δ,Rate A,Rate B,Rate Δ,Dwell A,Dwell B,Dwell Δ,Ping-pong A,Ping-pong B')
  for (const row of migrationRows) {
    lines.push([
      csvCell(row.name),
      csvCell(row.migrationsA),
      csvCell(row.migrationsB),
      csvCell(row.delta),
      csvCell(row.rateA),
      csvCell(row.rateB),
      csvCell(row.rateDelta),
      csvCell(row.dwellA),
      csvCell(row.dwellB),
      csvCell(row.dwellDelta),
      csvCell(row.pingA),
      csvCell(row.pingB),
    ].join(','))
  }

  if (blockingRows.length) {
    lines.push('')
    lines.push('Blocking Time')
    lines.push('Task,Gaps A,Gaps B,Avg A,Avg B,Δ avg')
    for (const row of blockingRows) {
      lines.push([
        csvCell(row.name), csvCell(row.gapsA), csvCell(row.gapsB),
        csvCell(row.avgA), csvCell(row.avgB), csvCell(row.delta),
      ].join(','))
    }
  }

  if (preemptionRows.length) {
    lines.push('')
    lines.push('Preemption Chains')
    lines.push('Victim,Count A,Count B,Δ,Total A,Total B')
    for (const row of preemptionRows) {
      lines.push([
        csvCell(row.name), csvCell(row.countA), csvCell(row.countB), csvCell(row.delta),
        csvCell(row.totalA), csvCell(row.totalB),
      ].join(','))
    }
  }

  if (syncRows.length) {
    lines.push('')
    lines.push('Sync Objects')
    lines.push('Metric,Trace A,Trace B,Δ')
    for (const row of syncRows) {
      lines.push([csvCell(row.label), csvCell(row.a), csvCell(row.b), csvCell(row.delta)].join(','))
    }
  }

  return lines.join('\n')
}

const _COMPARE_HTML_STYLE = `
  :root { --bg:#e9edf3; --paper:#fff; --ink:#182230; --muted:#5f6f82; --line:#d9e0ea; --header:#16324f; }
  * { box-sizing:border-box; }
  body { margin:0; padding:28px; font-family:"Segoe UI",Arial,sans-serif; color:var(--ink); background:var(--bg); }
  .report { max-width:960px; margin:0 auto; }
  .report-head { background:linear-gradient(135deg,var(--header),#21496f); color:#f3f7fd; border-radius:14px; padding:20px 24px; margin-bottom:18px; }
  h1 { margin:0; font-size:26px; }
  .sub { margin-top:6px; color:#cfe1f7; font-size:13px; }
  .report-card { margin:14px 0; background:var(--paper); border:1px solid var(--line); border-radius:12px; padding:12px 14px; }
  h2 { margin:0 0 10px; color:#123355; font-size:17px; }
  table { border-collapse:collapse; width:100%; }
  th,td { border-bottom:1px solid var(--line); padding:8px 10px; font-size:13px; text-align:right; }
  th:first-child,td:first-child { text-align:left; }
  thead th { background:#f1f5fb; font-weight:600; }
  tbody tr:nth-child(even) td { background:#f7f9fc; }
  .empty { text-align:center; color:var(--muted); }
`

/** Build standalone HTML report for trace compare. */
export function buildCompareHtml(
  nameA, nameB, summaryRows, topTaskRows, migrationRows, scopeEnabled,
  blockingRows = [], preemptionRows = [], syncRows = [],
) {
  const scopeNote = scopeEnabled
    ? 'Each side uses its own tab cursor range (C1–Cn) when 2+ cursors are placed.'
    : 'Full trace span on each side.'

  const summaryHtml = summaryRows.length
    ? summaryRows.map(r =>
      `<tr><td>${htmlCell(r.label)}</td><td>${htmlCell(r.a)}</td><td>${htmlCell(r.b)}</td><td>${htmlCell(r.delta)}</td></tr>`,
    ).join('')
    : '<tr><td colspan="4" class="empty">No data</td></tr>'

  const topHtml = topTaskRows.length
    ? topTaskRows.map(r =>
      `<tr><td>${htmlCell(r.name)}</td><td>${htmlCell(r.cpuA)}</td><td>${htmlCell(r.cpuB)}</td><td>${htmlCell(r.delta)}</td></tr>`,
    ).join('')
    : '<tr><td colspan="4" class="empty">No user tasks in either trace</td></tr>'

  const migHtml = migrationRows.length
    ? migrationRows.map(r =>
      `<tr><td>${htmlCell(r.name)}</td><td>${htmlCell(r.migrationsA)}</td><td>${htmlCell(r.migrationsB)}</td><td>${htmlCell(r.delta)}</td><td>${htmlCell(r.rateA)}</td><td>${htmlCell(r.rateB)}</td><td>${htmlCell(r.rateDelta)}</td><td>${htmlCell(r.dwellA)}</td><td>${htmlCell(r.dwellB)}</td><td>${htmlCell(r.dwellDelta)}</td><td>${htmlCell(r.pingA)}</td><td>${htmlCell(r.pingB)}</td></tr>`,
    ).join('')
    : '<tr><td colspan="12" class="empty">No migrated tasks in either trace</td></tr>'

  const blockHtml = blockingRows.length
    ? blockingRows.map(r =>
      `<tr><td>${htmlCell(r.name)}</td><td>${htmlCell(r.gapsA)}</td><td>${htmlCell(r.gapsB)}</td><td>${htmlCell(r.avgA)}</td><td>${htmlCell(r.avgB)}</td><td>${htmlCell(r.delta)}</td></tr>`,
    ).join('')
    : '<tr><td colspan="6" class="empty">No blocking samples in either trace</td></tr>'

  const preHtml = preemptionRows.length
    ? preemptionRows.map(r =>
      `<tr><td>${htmlCell(r.name)}</td><td>${htmlCell(r.countA)}</td><td>${htmlCell(r.countB)}</td><td>${htmlCell(r.delta)}</td><td>${htmlCell(r.totalA)}</td><td>${htmlCell(r.totalB)}</td></tr>`,
    ).join('')
    : '<tr><td colspan="6" class="empty">No preemption chains in either trace</td></tr>'

  const syncHtml = syncRows.length
    ? syncRows.map(r =>
      `<tr><td>${htmlCell(r.label)}</td><td>${htmlCell(r.a)}</td><td>${htmlCell(r.b)}</td><td>${htmlCell(r.delta)}</td></tr>`,
    ).join('')
    : '<tr><td colspan="4" class="empty">No sync instrumentation in either trace</td></tr>'

  return `<!doctype html>
<html><head><meta charset="utf-8"/><title>BTF Trace Compare</title><style>${_COMPARE_HTML_STYLE}</style></head>
<body><div class="report">
  <header class="report-head">
    <h1>Trace Compare</h1>
    <div class="sub">${htmlCell(nameA)} vs ${htmlCell(nameB)} · ${htmlCell(scopeNote)}</div>
  </header>
  <section class="report-card"><h2>Summary</h2>
    <table><thead><tr><th>Metric</th><th>Trace A</th><th>Trace B</th><th>Δ</th></tr></thead><tbody>${summaryHtml}</tbody></table>
  </section>
  <section class="report-card"><h2>Top Tasks</h2>
    <table><thead><tr><th>Task</th><th>CPU% A</th><th>CPU% B</th><th>Δ</th></tr></thead><tbody>${topHtml}</tbody></table>
  </section>
  <section class="report-card"><h2>Core Migrations</h2>
    <table><thead><tr><th>Task</th><th>Migr A</th><th>Migr B</th><th>Δ</th><th>Rate A</th><th>Rate B</th><th>Rate Δ</th><th>Dwell A</th><th>Dwell B</th><th>Dwell Δ</th><th>Ping A</th><th>Ping B</th></tr></thead><tbody>${migHtml}</tbody></table>
  </section>
  <section class="report-card"><h2>Blocking Time</h2>
    <table><thead><tr><th>Task</th><th>Gaps A</th><th>Gaps B</th><th>Avg A</th><th>Avg B</th><th>Δ avg</th></tr></thead><tbody>${blockHtml}</tbody></table>
  </section>
  <section class="report-card"><h2>Preemption Chains</h2>
    <table><thead><tr><th>Victim</th><th>Count A</th><th>Count B</th><th>Δ</th><th>Total A</th><th>Total B</th></tr></thead><tbody>${preHtml}</tbody></table>
  </section>
  <section class="report-card"><h2>Sync Objects</h2>
    <table><thead><tr><th>Metric</th><th>Trace A</th><th>Trace B</th><th>Δ</th></tr></thead><tbody>${syncHtml}</tbody></table>
  </section>
</div></body></html>`
}

export function downloadCompareCsv(
  nameA, nameB, summaryRows, topTaskRows, migrationRows, scopeEnabled,
  blockingRows = [], preemptionRows = [], syncRows = [],
) {
  const text = buildCompareCsv(
    nameA, nameB, summaryRows, topTaskRows, migrationRows, scopeEnabled,
    blockingRows, preemptionRows, syncRows,
  )
  const blob = new Blob([text], { type: 'text/csv;charset=utf-8' })
  _downloadBlob(`trace-compare-${_timestamp()}.csv`, blob)
}

export function downloadCompareHtml(
  nameA, nameB, summaryRows, topTaskRows, migrationRows, scopeEnabled,
  blockingRows = [], preemptionRows = [], syncRows = [],
) {
  const html = buildCompareHtml(
    nameA, nameB, summaryRows, topTaskRows, migrationRows, scopeEnabled,
    blockingRows, preemptionRows, syncRows,
  )
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  _downloadBlob(`trace-compare-${_timestamp()}.html`, blob)
}

function _downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function _timestamp() {
  const d = new Date()
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}
