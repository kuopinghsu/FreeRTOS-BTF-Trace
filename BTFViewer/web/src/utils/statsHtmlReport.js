/**
 * Statistics HTML report helpers (Web).
 * Keep in sync with btf_viewer_pkg/stats_html.py.
 */
import { htmlSectionSlug } from './htmlReport.js'

export const STATS_TOC_GROUPS = [
  ['Overview and Findings', [
    'Analysis Scope', 'Analysis Findings', 'Trace Metadata',
  ]],
  ['CPU and Scheduling', [
    'Core Utilisation', 'Trace Health (TICK)', 'Core Time Breakdown',
    'Concurrent Core Active Distribution', 'Kernel Switch Overhead',
    'Top Tasks by CPU',
  ]],
  ['Migrations and Core Affinity', [
    'Core Migrations', 'Core-Pair Migration Summary', 'Core Affinity',
    'Task × Core', 'Core Utilization Over Time', 'Task Lifecycle',
    'Deadlines / CPU budget', 'Task Health',
  ]],
  ['Timing, Latency and Jitter', [
    'Investigate Anomalies', 'Execution Time Per Slice',
    'Off-CPU Time', 'Dispatch / Scheduling Latency', 'Inter-Arrival Time',
    'Period / Jitter', 'Response Time', 'Unified Jitter',
  ]],
  ['Synchronization and Custom Events', [
    'Preemption Chain Analysis', 'Preemption Matrix', 'Priority Inheritance',
    'Mutex / Semaphore', 'Waiter × Owner', 'Mutex Blocking', 'Queue',
    'Interval Analysis', 'Tag Analysis', 'Statistics Notes',
  ]],
]

export const STATS_DEFAULT_EXPANDED = [
  'Analysis Scope',
  'Analysis Findings',
  'Core Utilisation (excl. IDLE/TICK)',
  'Trace Health (TICK)',
  'Investigate Anomalies',
]

export const STATS_HTML_EXTRA_CSS = `
:root { --line-strong: #c8d2e0; --stripe: #f7f9fc; }
.report.report-wide { max-width: 1160px; }
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}
.kpi {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px 14px;
  box-shadow: 0 2px 8px rgba(30, 60, 90, 0.06);
}
.kpi .k { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.6px; }
.kpi .v { margin-top: 4px; font-size: 20px; font-weight: 700; color: #0f2b47; }
.kpi .s { margin-top: 2px; font-size: 12px; color: var(--muted); }
.kpi.warn { border-color: #e0a020; }
.kpi.error { border-color: #c0392b; }
.kpi.ok { border-color: #5FCF6F; }
.notes { border-left: 4px solid var(--accent); }
.notes ul { margin: 8px 0 0 18px; padding: 0; }
.notes li { margin: 6px 0; line-height: 1.45; }
table { border-collapse: separate; border-spacing: 0; width: 100%; }
th, td { border-bottom: 1px solid var(--line); padding: 8px 10px; font-size: 13px; text-align: right; }
th:first-child, td:first-child { text-align: left; }
thead th {
  background: #f1f5fb;
  color: #284563;
  font-weight: 600;
  border-top: 1px solid var(--line-strong);
  border-bottom: 1px solid var(--line-strong);
}
tbody tr:nth-child(even) td { background: var(--stripe); }
.empty { text-align: center !important; color: var(--muted); }
.detail-note { margin: 6px 0 8px; font-size: 12px; color: var(--muted); }
h3.sub { margin: 14px 0 8px; font-size: 14px; color: #284563; font-weight: 600; }
.sev-error { color: #c0392b; font-weight: 600; }
.sev-warning { color: #9a4d00; font-weight: 600; }
.finding-info { color: var(--ink, var(--fg, #182230)); }
.finding-ok { color: #166534; font-weight: 600; }
.findings-list { margin: 8px 0 0 18px; padding: 0; }
.findings-list li { margin: 8px 0; line-height: 1.45; }
.analysis-findings { border-left: 4px solid #c0392b; }
.finding-cards { display: grid; gap: 10px; }
.finding-card {
  border: 1px solid var(--line);
  border-left-width: 4px;
  border-radius: 10px;
  padding: 10px 12px;
  background: #fff;
}
.finding-card.sev-error { border-left-color: #c0392b; }
.finding-card.sev-warning { border-left-color: #e0a020; }
.finding-card.finding-info { border-left-color: var(--accent); }
.finding-card.finding-ok { border-left-color: #5FCF6F; }
.finding-card h3 { margin: 0 0 6px; font-size: 14px; color: #123355; }
.finding-meta { font-size: 12px; color: var(--muted); margin: 4px 0; }
.scope-table th { width: 28%; }
.heat-wrap { overflow-x: auto; margin: 8px 0 12px; }
.heat-cell { font-size: 10px; text-anchor: middle; }
.table-tools { margin: 8px 0 12px; }
.table-toolbar {
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 6px;
}
.table-search {
  font: inherit; font-size: 12px; padding: 4px 8px; border: 1px solid var(--line);
  border-radius: 6px; min-width: 160px;
}
.table-check { font-size: 12px; color: var(--muted); display: inline-flex; gap: 4px; align-items: center; }
.table-count { font-size: 12px; color: var(--muted); margin-left: auto; }
.table-scroll { overflow-x: auto; max-width: 100%; }
.table-scroll table { min-width: 100%; }
.table-scroll thead th { position: sticky; top: 0; z-index: 2; }
.table-scroll td:first-child, .table-scroll th:first-child {
  position: sticky; left: 0; z-index: 1; background: #fff;
}
.table-scroll tbody tr:nth-child(even) td:first-child { background: var(--stripe); }
.sortable { cursor: pointer; }
.sortable:hover { color: var(--accent); }
.report-tabs .tab-bar { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 10px; }
.report-tabs .tab-btn {
  font: inherit; font-size: 12px; padding: 4px 10px; border: 1px solid var(--line);
  border-radius: 999px; background: #f1f5fb; color: var(--accent); cursor: pointer;
}
.report-tabs .tab-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.pct-bar { display: flex; align-items: center; gap: 8px; margin: 4px 0; font-size: 12px; }
.pct-bar .lab { flex: 0 0 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pct-bar .track { flex: 1; height: 10px; background: #eef2f7; border-radius: 6px; overflow: hidden; }
.pct-bar .fill { height: 100%; border-radius: 6px; }
`.trim()

function esc(v) {
  return String(v ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function htmlInspectHref(sectionTitle) {
  return `#sec-${htmlSectionSlug(sectionTitle)}`
}

export function htmlKpi(label, value, { hint = '', kind = '' } = {}) {
  const cls = kind ? `kpi ${kind}` : 'kpi'
  const extra = hint ? `<div class="s">${esc(hint)}</div>` : ''
  return `<article class="${cls}"><div class="k">${esc(label)}</div><div class="v">${esc(value)}</div>${extra}</article>`
}

export function htmlScopeIdentityCard({
  filename, scopeType, start, end, duration, cores, filters, timestampMode, taskCount, sampleNote = '',
}) {
  const rows = [
    ['Trace file', filename || '—'],
    ['Scope', scopeType],
    ['Start', start],
    ['End', end],
    ['Duration', duration],
    ['Cores', String(cores)],
    ['Tasks in scope', Number(taskCount || 0).toLocaleString()],
    ['Filters', filters || 'None'],
    ['Timestamps', timestampMode],
  ]
  const body = rows.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join('')
  const note = sampleNote ? `<p class="detail-note">${esc(sampleNote)}</p>` : ''
  return `<section class="report-card" id="sec-analysis-scope"><h2>Analysis Scope</h2>`
    + `<table class="meta-table scope-table"><tbody>${body}</tbody></table>${note}</section>`
}

export function htmlTraceMetadataCard({
  span, tasks, segments, stiEvents, contextSwitches, coreGapAvg = '', coreGapMax = '', scopeTitle = '',
}) {
  const rows = [
    [`Span${scopeTitle}`, span],
    ['Tasks', Number(tasks || 0).toLocaleString()],
    ['Segments', Number(segments || 0).toLocaleString()],
    ['STI events', Number(stiEvents || 0).toLocaleString()],
    [`Context switches${scopeTitle}`, Number(contextSwitches || 0).toLocaleString()],
  ]
  if (coreGapAvg) rows.push([`Core gap avg${scopeTitle}`, coreGapAvg])
  if (coreGapMax) rows.push([`Core gap max${scopeTitle}`, coreGapMax])
  const body = rows.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join('')
  return `<section class="report-card"><h2>Trace Metadata</h2>`
    + '<p class="detail-note">Trace-size counts. Diagnostic KPIs above summarise health.</p>'
    + `<table class="meta-table"><tbody>${body}</tbody></table></section>`
}

export function htmlDiagnosticKpiGrid(kpis) {
  if (!kpis?.length) return ''
  return `<section class="kpi-grid">${kpis.map(k => htmlKpi(k.label, k.value, k)).join('')}</section>`
}

export function htmlFindingCards(findings, scopeTitle = '') {
  if (!findings?.length) return ''
  const cards = findings.map((f) => {
    let cls = f.severity === 'error' ? 'sev-error' : f.severity === 'warning' ? 'sev-warning' : 'finding-info'
    if (f.id === 'load_balance_ok') cls = 'finding-ok'
    const inspect = String(f.inspect || '').trim()
    const href = String(f.inspect_href || f.inspectHref || '').trim() || (inspect ? htmlInspectHref(inspect) : '')
    const inspectHtml = inspect
      ? `<div class="finding-meta"><strong>Inspect:</strong> <a href="${esc(href)}">${esc(inspect)}</a></div>`
      : ''
    const impact = String(f.impact || '').trim()
    let evidence = String(f.evidence_text || f.evidenceText || '').trim()
    if (!evidence && Array.isArray(f.evidence) && f.evidence.length) {
      evidence = f.evidence.filter(Boolean).map(String).join('; ')
    }
    const conf = String(f.confidence || '').trim()
    const sev = String(f.severity || 'info')
    return `<article class="finding-card ${cls}">`
      + `<h3>${esc(sev[0].toUpperCase() + sev.slice(1))} · ${esc(f.title || 'Finding')}</h3>`
      + `<p>${esc(f.text || '')}</p>`
      + (impact ? `<div class="finding-meta"><strong>Impact:</strong> ${esc(impact)}</div>` : '')
      + (evidence ? `<div class="finding-meta"><strong>Evidence:</strong> ${esc(evidence)}</div>` : '')
      + inspectHtml
      + (conf ? `<div class="finding-meta"><strong>Confidence:</strong> ${esc(conf)}</div>` : '')
      + '</article>'
  }).join('')
  return `<section class="report-card notes analysis-findings">`
    + `<h2>Analysis Findings${esc(scopeTitle)}</h2>`
    + '<p class="detail-note">Heuristic summary of load balance, CPU consumers, off-CPU gaps, thrashing, deadlines, tick health, and sync. Exported links open the matching report section; they do not jump back into BTFViewer.</p>'
    + `<div class="finding-cards">${cards}</div></section>`
}

function heatColor(frac) {
  const f = Math.max(0, Math.min(1, Number(frac) || 0))
  const r = Math.round(241 + (192 - 241) * f)
  const g = Math.round(245 + (57 - 245) * f)
  const b = Math.round(251 + (43 - 251) * f)
  return `rgb(${r},${g},${b})`
}

export function htmlMatrixHeatmap(rowLabels, colLabels, cells, { title, unit = '%', width = 640 } = {}) {
  const rows = rowLabels || []
  const cols = colLabels || []
  if (!rows.length || !cols.length) return ''
  let maxV = 1
  for (const line of cells || []) {
    for (const v of line || []) maxV = Math.max(maxV, Number(v) || 0)
  }
  const labelW = 88
  const headH = 36
  const cell = 22
  const w = Math.max(width, labelW + 12 + cols.length * cell)
  const h = headH + 8 + rows.length * cell + 8
  const parts = [
    `<div class="heat-wrap"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="${esc(title)}">`,
    `<text x="8" y="16" font-size="12" fill="#123355" font-weight="600">${esc(title)}</text>`,
  ]
  cols.forEach((col, j) => {
    const x = labelW + j * cell + cell / 2
    parts.push(`<text x="${x.toFixed(1)}" y="${headH - 4}" font-size="9" fill="#5f6f82" text-anchor="middle">${esc(String(col).slice(0, 10))}</text>`)
  })
  rows.forEach((row, i) => {
    const y = headH + i * cell
    parts.push(`<text x="8" y="${y + 15}" font-size="10" fill="#182230">${esc(String(row).slice(0, 14))}</text>`)
    const line = cells[i] || []
    cols.forEach((_c, j) => {
      const val = Number(line[j]) || 0
      const x = labelW + j * cell
      const color = val > 0 ? heatColor(val / maxV) : '#f7f9fc'
      parts.push(`<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${cell - 2}" height="${cell - 2}" rx="3" fill="${color}"/>`)
      if (val > 0) {
        const label = unit === '%' ? `${val.toFixed(0)}${unit}` : `${val.toFixed(0)}`
        parts.push(`<text class="heat-cell" x="${(x + (cell - 2) / 2).toFixed(1)}" y="${(y + 14).toFixed(1)}" fill="#123355">${esc(label)}</text>`)
      }
    })
  })
  parts.push('</svg></div>')
  return parts.join('')
}

export function htmlPercentileBars(rows, { title = 'Response P50–P99', width = 640 } = {}) {
  const items = (rows || []).filter(r => r && typeof r === 'object').slice(0, 12)
  if (!items.length) return ''
  let maxV = 1
  for (const r of items) maxV = Math.max(maxV, Number(r.p99_ns || r.max_ns || 0), 1)
  const labelW = 110
  const pad = 12
  const rowH = 22
  const header = 28
  const h = header + items.length * rowH + 10
  const plotW = Math.max(80, width - labelW - pad - 80)
  const parts = [
    `<div class="heat-wrap"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${h}" width="${width}" height="${h}" role="img" aria-label="${esc(title)}">`,
    `<text x="${pad}" y="16" font-size="12" fill="#123355" font-weight="600">${esc(title)}</text>`,
    `<text x="${width - pad}" y="16" text-anchor="end" font-size="11" fill="#5f6f82">interval = P50–P99</text>`,
  ]
  items.forEach((r, i) => {
    const y = header + i * rowH
    const p50 = Number(r.p50_ns || 0)
    const p95 = Number(r.p95_ns || 0)
    const p99 = Number(r.p99_ns || 0)
    const x0 = labelW + plotW * p50 / maxV
    const x1 = labelW + plotW * Math.max(p99, p50) / maxV
    const x95 = labelW + plotW * p95 / maxV
    parts.push(`<text x="8" y="${y + 14}" font-size="11" fill="#182230">${esc(String(r.task || '').slice(0, 16))}</text>`)
    parts.push(`<rect x="${x0.toFixed(1)}" y="${y + 6}" width="${Math.max(x1 - x0, 2).toFixed(1)}" height="8" rx="3" fill="#9ec5e8"/>`)
    parts.push(`<line x1="${x95.toFixed(1)}" y1="${y + 4}" x2="${x95.toFixed(1)}" y2="${y + 16}" stroke="#2a6fb2" stroke-width="2"/>`)
  })
  parts.push('</svg></div>')
  return parts.join('')
}

export function htmlHealthBars(rows) {
  const items = [...(rows || [])].filter(r => r && typeof r === 'object')
    .sort((a, b) => (a.score || 0) - (b.score || 0))
    .slice(0, 16)
  if (!items.length) return ''
  return `<div class="health-bars">${items.map((r) => {
    const score = Number(r.score || 0)
    const marks = r.marks || {}
    const reasons = Object.keys(marks).filter(k => marks[k])
    const reason = reasons.length ? reasons.join(', ') : 'no deductions'
    const color = score < 50 ? '#c0392b' : score < 80 ? '#e0a020' : '#1a8a2a'
    return `<div class="pct-bar"><span class="lab" title="${esc(r.task || '')}">${esc(String(r.task || '').slice(0, 18))}</span>`
      + `<div class="track"><div class="fill" style="width:${score}%;background:${color}"></div></div>`
      + `<span>${score} · ${esc(reason)}</span></div>`
  }).join('')}</div>`
}

function sparkline(vals, width = 420, height = 48) {
  if (!vals || vals.length < 2) return ''
  const mn = Math.min(...vals)
  const mx = Math.max(...vals)
  const span = (mx - mn) || 1
  const n = vals.length
  const pts = vals.slice(0, 200).map((v, i) => {
    const x = 4 + (width - 8) * i / Math.max(n - 1, 1)
    const y = height - 6 - (height - 12) * ((v - mn) / span)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="Tag time series">`
    + `<polyline fill="none" stroke="#2a6fb2" stroke-width="1.5" points="${pts.join(' ')}"/></svg>`
}

export function htmlTagOverview(samples, { timeOf = (s) => s.time, maxRows = 12 } = {}) {
  const byLabel = new Map()
  for (const s of samples || []) {
    if (!s || typeof s !== 'object') continue
    const lab = String(s.label || s.tag || '')
    if (!byLabel.has(lab)) byLabel.set(lab, [])
    byLabel.get(lab).push(s)
  }
  if (!byLabel.size) return '<p class="empty">No tag samples in scope</p>'
  const blocks = []
  let n = 0
  for (const [lab, group] of byLabel) {
    if (n++ >= 8) break
    const vals = []
    for (const s of group) {
      const v = Number(String(s.value ?? '0').replace(/,/g, ''))
      if (Number.isFinite(v)) vals.push(v)
    }
    if (!vals.length) continue
    let transitions = 0
    let plateau = 1
    let run = 1
    for (let i = 1; i < vals.length; i++) {
      if (vals[i] !== vals[i - 1]) {
        transitions++
        plateau = Math.max(plateau, run)
        run = 1
      } else run++
    }
    plateau = Math.max(plateau, run)
    const unique = new Set(vals).size
    const mn = Math.min(...vals)
    const mx = Math.max(...vals)
    const extrema = [...group].sort((a, b) => Number(String(a.value).replace(/,/g, '')) - Number(String(b.value).replace(/,/g, '')))
    const shown = []
    if (extrema[0]) shown.push(extrema[0])
    if (extrema[extrema.length - 1] && extrema[extrema.length - 1] !== extrema[0]) shown.push(extrema[extrema.length - 1])
    shown.push(group[0])
    if (!shown.includes(group[group.length - 1])) shown.push(group[group.length - 1])
    const rows = shown.slice(0, maxRows).map(s =>
      `<tr><td>${esc(timeOf(s))}</td><td>${esc(s.value)}</td><td>${esc(s.core || '—')}</td></tr>`).join('')
    blocks.push(
      `<h3 class="sub">${esc(lab)}</h3>`
      + `<p class="detail-note">${group.length} samples · ${unique} distinct values · ${transitions} transitions · longest plateau ${plateau} · min ${mn} / max ${mx}</p>`
      + sparkline(vals)
      + `<table><thead><tr><th>Time</th><th>Value</th><th>Core</th></tr></thead><tbody>${rows}</tbody></table>`,
    )
  }
  return blocks.join('') || '<p class="empty">No tag samples in scope</p>'
}

export function htmlInvestigateAnomalies({
  anomaliesTable, worstTable, patternsTable, critPathTable, critNote, scopeTitle = '',
}) {
  return `<section class="report-card"><h2>Investigate Anomalies${esc(scopeTitle)}</h2>`
    + '<p class="detail-note">Timeline anomalies, longest events, repeating kinds, and the longest heuristic ready-to-completion windows. Critical Path components can overlap; they are not additive parts of Duration.</p>'
    + '<div class="report-tabs"><div class="tab-bar">'
    + '<button type="button" class="tab-btn" data-tab="anomalies">Timeline Anomalies</button>'
    + '<button type="button" class="tab-btn" data-tab="worst">Worst Events</button>'
    + '<button type="button" class="tab-btn" data-tab="patterns">Recurring Patterns</button>'
    + '<button type="button" class="tab-btn" data-tab="crit">Critical Path</button>'
    + '</div>'
    + `<div data-panel="anomalies">${anomaliesTable}</div>`
    + `<div data-panel="worst">${worstTable}</div>`
    + `<div data-panel="patterns">${patternsTable}</div>`
    + `<div data-panel="crit">${critNote || ''}${critPathTable}</div>`
    + '</div></section>'
}

export function htmlGlossary({ rangeNote = '' } = {}) {
  const items = [
    rangeNote,
    '<strong>Execution Time Per Slice:</strong> Duration of each continuous task run between two context switches.',
    '<strong>Highest CPU consumers</strong> are tasks with the largest share of active CPU time. They are not automatically WCET candidates. Largest execution-time maxima live in Execution Time Per Slice.',
    '<strong>Inter-Arrival Time:</strong> Time between consecutive activations of the same task (slice start to next slice start).',
    '<strong>Off-CPU Time (Blocking Time):</strong> Gap between the end of one slice and the start of the next for the same task. It may include preemption, suspension, periodic waiting, or scheduling delay — not necessarily resource blocking. It is not end-to-end response time.',
    '<strong>CPU% (task):</strong> Share of total non-IDLE/TICK <em>active CPU time</em> in scope, not wall-clock span and not total multicore capacity.',
    '<strong>Core utilisation:</strong> Non-IDLE/TICK active time on that core divided by the scoped wall-clock span (one-core capacity = 100%).',
    '<strong>Load Balance Score:</strong> 100% × (1 − Gini of core utilisation). 100 = evenly distributed utilisation; 0 = highly uneven. Even overload or even idle can still score high.',
    '<strong>Preemption Chain Analysis:</strong> For each off-CPU gap of a victim task, which task ran on the same core during that gap.',
    '<strong>Priority Inheritance:</strong> Tasks boosted above base priority when <code>create pri:N</code> and <code>set_priority</code> STI events are present.',
    '<strong>Mutex / Semaphore:</strong> Paired <code>take</code>/<code>give</code> STI events by object pointer.',
    '<strong>Interval Analysis:</strong> Paired <code>interval_start</code> / <code>interval_stop</code> STI events by id.',
    '<strong>Tag Analysis:</strong> Numeric samples from tag STI channels. Repeated identical values are summarised as a time series, not dumped row-by-row.',
    '<strong>Task × Core:</strong> Per-task execution share of the scoped span on each core.',
    '<strong>Task Health:</strong> Heuristic 0–100 score from measured statistics, not an AI probability.',
    '<strong>Response Time:</strong> Heuristic ready→completion from adjacent slices. Not an explicit BTF release/completion pair.',
    '<strong>Critical Path:</strong> Longest heuristic response windows. Exec is own on-CPU time; Off-CPU is Duration − Exec. Preempt, Wait, and Migration overlap and are not a stacked split of Duration.',
    '<strong>Period / Jitter:</strong> Median inter-arrival as expected period, with RMS jitter, CV, missed (&gt; 1.5×) and extra (&lt; 0.5×) activations.',
    '<strong>Min:</strong> Smallest observed sample in scope. It does not prove zero system load.',
    '<strong>Max:</strong> Largest observed sample in scope. It is an observed peak, not a guaranteed WCET.',
    '<strong>Average (Mean):</strong> Arithmetic mean; outliers can skew it.',
    '<strong>TrimMean(5%):</strong> Mean after dropping the fastest and slowest 5%.',
    '<strong>Jitter:</strong> Observed spread (Max − Min) for samples in scope.',
    '<strong>σ:</strong> Population standard deviation of samples in scope.',
    '<strong>P50 (Median):</strong> Half the samples are at or below this value.',
    '<strong>P95 / P99:</strong> Percentile of the observed distribution. Usefulness depends on the deadline or acceptance criterion; P95 is not universally the best user-experience metric for real-time systems.',
  ].filter(Boolean)
  return `<section class="report-card notes"><h2>Statistics Notes</h2>`
    + '<p class="detail-note">Glossary of metric definitions used in this report.</p>'
    + `<ul>${items.map(i => `<li>${i}</li>`).join('')}</ul></section>`
}
