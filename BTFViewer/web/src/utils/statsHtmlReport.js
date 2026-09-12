/**
 * Statistics HTML report helpers (Web).
 * Keep in sync with btf_viewer_pkg/stats_html.py.
 */
import { htmlSectionSlug } from './htmlReport.js'
import { investigationSections, loadInvestigation } from './investigationNotebook.js'

export const STATS_TOC_GROUPS = [
  ['Overview and Findings', [
    'Performance Overview', 'Analysis Scope', 'Evidence Refs', 'Analysis Findings',
    'Trace Health Check', 'Investigation', 'Trace Metadata',
  ]],
  ['CPU and Scheduling', [
    'Core Utilization', 'Trace Health (TICK)', 'Core Time Breakdown',
    'Concurrent Core Active Distribution', 'Switch Reason Breakdown',
    'Scheduling Load Over Time', 'Kernel Switch Overhead', 'Idle Analysis',
    'Top Tasks by CPU',
  ]],
  ['Migrations and Core Affinity', [
    'Core Migration Count', 'Core-Pair Migration Summary', 'Core Affinity',
    'Task × Core', 'Core Utilization Over Time', 'Task Lifecycle',
    'Deadlines / CPU budget', 'Task Health',
  ]],
  ['Timing, Latency and Jitter', [
    'Investigate Anomalies', 'Execution Time Per Slice',
    'Off-CPU Time', 'Dispatch / Scheduling Latency', 'Inter-Arrival Time',
    'Activation Latency', 'Ready-Gap (Starvation)',
    'Period / Jitter', 'Response Time', 'Unified Jitter',
  ]],
  ['Synchronization and Custom Events', [
    'Preemption Chain Analysis', 'Preemption Matrix', 'Priority Inheritance',
    'Mutex / Semaphore', 'Waiter × Owner', 'Mutex Blocking', 'Queue',
    'Queue Backlog / Semaphore Level',
    'Interval Analysis', 'Tag Analysis', 'Statistics Notes',
  ]],
]

export const STATS_DEFAULT_EXPANDED = [
  'Analysis Scope',
  'Analysis Findings',
  'Trace Health Check',
  'Core Utilization (excl. IDLE/TICK)',
  'Trace Health (TICK)',
  'Investigate Anomalies',
]

export const STATS_HTML_EXTRA_CSS = `
.report.report-wide { max-width: 1160px; }
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}
/* A KPI with no status kind is a normal measurement, so it carries the primary
   accent outline; only ok/warn/error and migration override it. */
.kpi {
  position: relative;
  overflow: hidden;
  background: var(--paper);
  border: 1px solid var(--accent-border);
  border-radius: 12px;
  padding: 12px 14px 12px 16px;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}
.kpi::before {
  content: "";
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  background: var(--accent);
}
.kpi .k { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.6px; }
.kpi .v { margin-top: 4px; font-size: 20px; font-weight: 700; color: var(--ink); font-variant-numeric: tabular-nums; }
.kpi .s { margin-top: 2px; font-size: 12px; color: var(--muted); }
.kpi.metric-util, .kpi.metric-latency {
  border-color: var(--accent-border);
}
.kpi.metric-util::before, .kpi.metric-latency::before { background: var(--accent); }
.kpi.metric-migration {
  border-color: var(--warn-border);
}
.kpi.metric-migration::before { background: var(--warning); }
.kpi.ok { border-color: var(--ok-border); }
.kpi.ok::before { background: var(--success); }
.kpi.warn { border-color: var(--warn-border); }
.kpi.warn::before { background: var(--warning); }
.kpi.error { border-color: var(--error-border); }
.kpi.error::before { background: var(--danger); }
.report-verdict {
  margin: 0 0 14px;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 14px;
  color: var(--ink);
  background: var(--paper-2);
  border: 1px solid var(--line);
  border-left: 4px solid var(--line-strong);
}
.report-verdict.ok {
  background: var(--success-soft);
  border-color: var(--ok-border);
  border-left-color: var(--success);
}
.report-verdict.ok strong { color: var(--success); }
.report-verdict.warn {
  background: var(--warning-soft);
  border-color: var(--warn-border);
  border-left-color: var(--warning);
}
.report-verdict.warn strong { color: var(--warning); }
.report-verdict.error {
  background: var(--danger-soft);
  border-color: var(--error-border);
  border-left-color: var(--danger);
}
.report-verdict.error strong { color: var(--danger); }
.notes { border-left: 4px solid var(--accent); }
.notes ul { margin: 8px 0 0 18px; padding: 0; }
.notes li { margin: 6px 0; line-height: 1.45; }
table { border-collapse: separate; border-spacing: 0; width: 100%; }
th, td { border-bottom: 1px solid var(--line); padding: 8px 10px; font-size: 13px; text-align: right; }
th:first-child, td:first-child { text-align: left; }
thead th {
  background: var(--paper-2);
  color: var(--ink);
  font-weight: 600;
  border-top: 1px solid var(--line-strong);
  border-bottom: 1px solid var(--line-strong);
}
tbody tr:nth-child(even) td { background: var(--stripe); }
.empty { text-align: center !important; color: var(--muted); }
.detail-note { margin: 6px 0 8px; font-size: 12px; color: var(--muted); }
h3.sub { margin: 14px 0 8px; font-size: 14px; color: var(--ink); font-weight: 600; }
.sev-error { color: var(--danger); font-weight: 600; }
.sev-warning { color: var(--warning); font-weight: 600; }
.finding-info { color: var(--ink); }
.finding-ok { color: var(--success); font-weight: 600; }
.findings-list { margin: 8px 0 0 18px; padding: 0; }
.findings-list li { margin: 8px 0; line-height: 1.45; }
.analysis-findings { border-left: 4px solid var(--danger); }
.trace-health { border-left: 4px solid var(--accent); }
.trace-health-status { font-size: 14px; font-weight: 600; margin: 6px 0 10px; }
.trace-health-check { margin: 6px 0; padding: 6px 0; border-bottom: 1px solid var(--line); }
.trace-health-check:last-of-type { border-bottom: 0; }
.trace-health-check > summary { cursor: pointer; line-height: 1.45; }
.trace-health-check .finding-meta { margin-left: 16px; }
.investigation { border-left: 4px solid var(--accent); }
.investigation .finding-meta ul { margin: 4px 0 0 16px; padding: 0; }
.investigation h3.sub { margin-top: 16px; }
.finding-cards { display: grid; gap: 10px; }
.finding-card {
  border: 1px solid var(--line);
  border-left-width: 4px;
  border-radius: 10px;
  padding: 10px 12px;
  background: var(--paper);
}
.finding-card.sev-error { border-left-color: var(--danger); }
.finding-card.sev-warning { border-left-color: var(--warning); }
.finding-card.finding-info { border-left-color: var(--accent); }
.finding-card.finding-ok { border-left-color: var(--success); }
.finding-card h3 { margin: 0 0 6px; font-size: 14px; color: var(--ink); }
.finding-meta { font-size: 12px; color: var(--muted); margin: 4px 0; }
.finding-card a { color: var(--accent); }
.scope-table th { width: 28%; }
.heat-wrap { overflow-x: auto; margin: 8px 0 12px; background: var(--matrix-bg); }
.heat-cell { font-size: 10px; text-anchor: middle; }
.heat-matrix-head { margin: 4px 0 8px; }
.heat-matrix-title { font-size: 13px; font-weight: 650; color: var(--ink); }
.heat-matrix-subtitle { font-size: 11px; color: var(--muted); margin-top: 2px; }
.heat-grid {
  display: grid;
  grid-template-columns: minmax(90px, 130px) repeat(var(--col-count), minmax(44px, 1fr));
  gap: 2px;
  font-size: 11px;
  min-width: 480px;
}
.heat-grid-corner, .heat-grid-collabel, .heat-grid-rowlabel {
  display: flex; align-items: center;
  padding: 4px 6px;
  color: var(--matrix-label);
  font-weight: 600;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.heat-grid-collabel { justify-content: center; }
.heat-grid-cell {
  display: flex; align-items: center; justify-content: center;
  padding: 4px 2px;
  border-radius: 4px;
  font-variant-numeric: tabular-nums;
  min-height: 22px;
}
.heat-grid-diagonal, .heat-grid-nodata {
  background: var(--matrix-diag-bg); color: var(--matrix-diag-ink); border: 1px dashed var(--matrix-border);
}
.heat-grid-extra {
  background: var(--paper-2); color: var(--ink); border: 1px solid var(--line);
  font-weight: 600;
}
/* Six fixed bins (predictable in Qt WebEngine, no color-mix) reading the one
   quantitative scale that also drives every bar. */
.heat-0 { background: var(--data-0-bg); color: var(--data-0-ink); }
.heat-1 { background: var(--data-1-bg); color: var(--data-1-ink); }
.heat-2 { background: var(--data-2-bg); color: var(--data-2-ink); }
.heat-3 { background: var(--data-3-bg); color: var(--data-3-ink); }
.heat-4 { background: var(--data-4-bg); color: var(--data-4-ink); }
.heat-5 { background: var(--data-5-bg); color: var(--data-5-ink); }
/* Outline, not a fill change: the cell keeps its place on the quantitative
   scale while the pointer marks which row/column pair is being read. */
.heat-grid-cell:hover { outline: 2px solid var(--accent); outline-offset: -2px; }
.heat-legend { margin: 6px 0 10px; font-size: 11px; color: var(--muted); }
.heat-legend-grid {
  display: grid; grid-template-columns: auto minmax(120px, 220px) auto;
  align-items: center; gap: 2px 8px; max-width: 260px;
}
.heat-legend-bar {
  height: var(--std-bar-h); border-radius: var(--std-bar-r);
  background: linear-gradient(to right,
    var(--data-0-bg), var(--data-1-bg), var(--data-2-bg),
    var(--data-3-bg), var(--data-4-bg), var(--data-5-bg));
}
.table-tools { margin: 8px 0 12px; }
.table-toolbar {
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 6px;
}
.table-search {
  font: inherit; font-size: 12px; padding: 4px 8px; border: 1px solid var(--line);
  border-radius: 6px; min-width: 160px; background: var(--paper); color: var(--ink);
}
.table-search::placeholder { color: var(--muted); }
.table-search:hover { border-color: var(--accent); }
.table-search:focus-visible {
  border-color: var(--accent); outline: 2px solid var(--accent); outline-offset: 1px;
}
.table-check { font-size: 12px; color: var(--muted); display: inline-flex; gap: 4px; align-items: center; }
.table-check:hover { color: var(--accent); cursor: pointer; }
.table-check input[type="checkbox"] { accent-color: var(--accent); }
.table-action {
  font: inherit; font-size: 12px; padding: 2px 9px; border: 1px solid var(--line);
  border-radius: 6px; background: var(--paper-2); color: var(--ink); cursor: pointer;
}
.table-action:hover { border-color: var(--accent); color: var(--accent); }
.table-action:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.table-action:disabled { opacity: 0.55; cursor: default; }
.table-action:disabled:hover { border-color: var(--line); color: var(--ink); }
.table-pager { display: none; gap: 8px; align-items: center; margin-top: 6px; font-size: 12px; color: var(--muted); }
.lb-gauge-embed { margin: 8px 0 12px; }
.lb-gauge-svg { display: block; max-width: 100%; height: auto; }
.lb-gauge-svg .lb-bg { fill: var(--paper-2); stroke: var(--line); }
.lb-gauge-svg .lb-bg-amber { stroke: var(--warning); }
.lb-gauge-svg .lb-bg-red { stroke: var(--danger); }
.lb-gauge-svg .lb-title { fill: var(--ink); }
.lb-gauge-svg .lb-muted { fill: var(--muted); }
.lb-gauge-svg .lb-track { stroke: var(--line); }
.lb-gauge-svg .lb-needle { stroke: var(--ink); }
.lb-gauge-svg .lb-hub { fill: var(--paper); stroke: var(--ink); }
.lb-gauge-svg .lb-value-ok { fill: var(--success); }
.lb-gauge-svg .lb-value-amber { fill: var(--warning); }
.lb-gauge-svg .lb-value-red { fill: var(--danger); }
.lb-gauge-svg .lb-chip-amber { fill: var(--warning-soft); stroke: var(--warning); }
.lb-gauge-svg .lb-chip-red { fill: var(--danger-soft); stroke: var(--danger); }
.lb-gauge-svg .lb-chip-text-amber { fill: var(--warning); }
.lb-gauge-svg .lb-chip-text-red { fill: var(--danger); }
.pctile-svg { display: block; max-width: 100%; height: auto; }
.pctile-title { fill: var(--ink); }
.pctile-sub { fill: var(--muted); }
.pctile-label { fill: var(--ink); }
/* The P50-P99 band is data, so it uses the soft bar colour rather than the
   accent tint, which was too faint to see on either surface. */
.pctile-bar { fill: var(--data-bar-soft); }
.pctile-marker { stroke: var(--data-bar); }
.sparkline-line { stroke: var(--data-bar); }
.table-count { font-size: 12px; color: var(--muted); margin-left: auto; }
.table-scroll { overflow-x: auto; max-width: 100%; }
.table-scroll table { min-width: 100%; }
.table-scroll thead th { position: sticky; top: 0; z-index: 2; }
.table-scroll td:first-child, .table-scroll th:first-child {
  position: sticky; left: 0; z-index: 1; background: var(--paper);
}
.table-scroll tbody tr:nth-child(even) td:first-child { background: var(--stripe); }
/* Row hover. Declared after the stripe and sticky-column rules so the whole
   row tracks the pointer, including a sticky first cell and meta-table <th>. */
tbody tr { transition: background-color 120ms ease, box-shadow 120ms ease; }
tbody tr:hover td,
tbody tr:hover th,
.table-scroll tbody tr:hover td:first-child,
.table-scroll tbody tr:hover th:first-child { background: var(--row-hover-bg); }
tbody tr:hover {
  box-shadow: inset 0 1px 0 var(--row-hover-edge), inset 0 -1px 0 var(--row-hover-edge);
}
.sortable { cursor: pointer; }
.sortable:hover { color: var(--accent); }
thead th.sortable:hover { background: var(--accent-soft); }
.report-tabs .tab-bar { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 10px; }
.report-tabs .tab-btn {
  font: inherit; font-size: 12px; padding: 4px 10px; border: 1px solid var(--line);
  border-radius: 999px; background: var(--paper-2); color: var(--accent); cursor: pointer;
}
.report-tabs .tab-btn.active { background: var(--accent); color: var(--paper); border-color: var(--accent); }
.pct-bar { display: flex; align-items: center; gap: 8px; margin: 4px 0; font-size: 12px; }
.pct-bar .lab {
  flex: 0 0 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--ink);
}
.pct-bar .track {
  flex: 1; height: var(--std-bar-h); background: var(--bar-track-bg);
  border: 1px solid var(--bar-track-border); border-radius: var(--std-bar-r); overflow: hidden;
}
.pct-bar .fill { height: 100%; border-radius: calc(var(--std-bar-r) - 1px); background: var(--data-bar); }
.rank-bars { margin: 8px 0 4px; }
.rank-bar { display: flex; align-items: center; gap: 8px; margin: 4px 0; font-size: 12px; }
.rank-bar-num { flex: 0 0 18px; color: var(--muted); text-align: right; font-variant-numeric: tabular-nums; }
.rank-bar-label {
  flex: 0 0 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--ink);
}
.rank-bar-track {
  flex: 1; height: var(--std-bar-h); background: var(--bar-track-bg);
  border: 1px solid var(--bar-track-border); border-radius: var(--std-bar-r); overflow: hidden;
}
.rank-bar-fill { display: block; height: 100%; border-radius: calc(var(--std-bar-r) - 1px); background: var(--data-bar); }
.rank-bar-fill.accent { background: var(--data-bar); }
.rank-bar-fill.warning { background: var(--warning); }
.rank-bar-fill.danger { background: var(--danger); }
.rank-bar-fill.success { background: var(--success); }
.rank-bar-value {
  flex: 0 0 88px; text-align: right; color: var(--ink); font-variant-numeric: tabular-nums;
}
.perf-overview-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-top: 4px;
}
.perf-panel h3.sub { margin: 0 0 8px; }
.util-list { display: flex; flex-direction: column; gap: 4px; }
.util-row { display: flex; align-items: center; gap: 8px; min-height: 18px; }
.util-label {
  flex: 0 0 128px; max-width: 128px; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; text-align: left; font-size: 13px; color: var(--ink);
}
.util-bar {
  flex: 1 1 auto; height: var(--std-bar-h); min-width: 24px; border-radius: var(--std-bar-r);
  background: var(--bar-track-bg); border: 1px solid var(--bar-track-border); overflow: hidden;
}
.util-bar-fill, .util-row-task .util-bar-fill {
  height: 100%; border-radius: calc(var(--std-bar-r) - 1px); background: var(--data-bar);
}
.util-pct { flex: 0 0 44px; text-align: left; font-size: 13px; }
.util-pct-core, .util-pct-task { color: var(--data-bar); }
.util-row .util-bar, .rank-bar .rank-bar-track, .pct-bar .track,
.util-row .util-label, .rank-bar .rank-bar-label, .pct-bar .lab {
  transition: border-color 0.15s ease, color 0.15s ease;
}
.util-row:hover .util-bar,
.rank-bar:hover .rank-bar-track,
.pct-bar:hover .track { border-color: var(--accent); }
.util-row:hover .util-label,
.rank-bar:hover .rank-bar-label,
.pct-bar:hover .lab { color: var(--accent); }
.util-row:hover .util-bar-fill,
.rank-bar:hover .rank-bar-fill,
.pct-bar:hover .fill { filter: brightness(1.08); }
.metric-chart {
  margin: 12px 0 16px; padding: 14px 16px 16px;
  border: 1px solid var(--line); border-radius: 12px; background: var(--paper);
}
.metric-chart-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 16px; margin-bottom: 12px;
}
.metric-chart-title { color: var(--ink); font-size: 13px; font-weight: 700; }
.metric-chart-subtitle {
  margin-top: 2px; color: var(--muted); font-size: 11px; line-height: 1.45;
}
.chart-callout {
  flex: 0 0 auto; min-width: 82px; padding: 7px 10px;
  border: 1px solid var(--line); border-radius: 9px; background: var(--paper-2); text-align: right;
}
.chart-callout-label, .chart-callout-note { display: block; color: var(--muted); font-size: 10px; }
.chart-callout strong {
  display: block; color: var(--ink); font-size: 18px; line-height: 1.15;
  font-variant-numeric: tabular-nums;
}
.trend-svg { display: block; width: 100%; height: auto; min-height: 180px; }
.chart-gridline { stroke: var(--chart-grid); stroke-width: 1; }
.chart-axis-label {
  fill: var(--chart-axis); font-size: 10px;
  font-family: "Segoe UI", Arial, sans-serif;
}
.chart-line {
  stroke: var(--data-bar); stroke-width: 2.5; stroke-linejoin: round; stroke-linecap: round;
}
.chart-point { stroke: var(--paper); stroke-width: 2; }
.chart-point-normal { fill: var(--data-bar); }
.chart-point-low { fill: var(--warning); }
.heat-cell { fill: var(--ink); }
@media (max-width: 680px) {
  .metric-chart-head { flex-direction: column; }
  .chart-callout { text-align: left; }
  .rank-bar-label { flex-basis: 82px; }
  .rank-bar-value { flex-basis: 72px; }
}
@media print {
  body, html[data-theme="dark"] body { background: #fff !important; }
  .metric-chart, .kpi, .report-card { box-shadow: none; }
  .theme-toggle { display: none !important; }
  .metric-chart, .kpi { break-inside: avoid; }
}
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
    ['Tasks in scope', Number(taskCount || 0).toLocaleString('en-US')],
    ['Filters', filters || 'None'],
    ['Timestamps', timestampMode],
  ]
  const body = rows.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join('')
  const note = sampleNote ? `<p class="detail-note">${esc(sampleNote)}</p>` : ''
  return `<section class="report-card" id="sec-analysis-scope"><h2>Analysis Scope</h2>`
    + `<table class="meta-table scope-table"><tbody>${body}</tbody></table>${note}</section>`
}

/** Build `{label, time_text}` refs from Analysis Findings for HTML export. */
export function evidenceRefsFromFindings(findings, { formatNs = null, limit = 12 } = {}) {
  const out = []
  const lim = Math.max(1, Number(limit) || 12)
  for (const f of findings || []) {
    if (!f || typeof f !== 'object') continue
    const label = String(f.title || 'Finding').trim() || 'Finding'
    const times = []
    for (const ev of f.evidence || []) {
      if (!ev || typeof ev !== 'object') continue
      for (const key of ['time', 'start', 'stop', 'ns']) {
        if (ev[key] == null) continue
        const v = Number(ev[key])
        if (Number.isFinite(v)) {
          times.push(Math.trunc(v))
          break
        }
      }
    }
    let timeText = ''
    if (times.length && typeof formatNs === 'function') {
      try {
        timeText = times.slice(0, 3).map(t => String(formatNs(t))).join(', ')
      } catch {
        timeText = times.slice(0, 3).map(String).join(', ')
      }
    } else if (times.length) {
      timeText = times.slice(0, 3).map(String).join(', ')
    }
    if (!timeText) {
      const et = String(f.evidence_text || f.evidenceText || '').trim()
      if (et) timeText = et.slice(0, 160)
    }
    if (!timeText) continue
    out.push({ label, time_text: timeText })
    if (out.length >= lim) break
  }
  return out
}

export function htmlEvidenceRefsCard(refs) {
  const items = (refs || []).filter(r => r && typeof r === 'object' && (
    String(r.label || '').trim() || String(r.time_text || r.timeText || '').trim()
  ))
  if (!items.length) return ''
  const body = items.map(r => (
    `<tr><td>${esc(r.label || 'Finding')}</td>`
    + `<td>${esc(r.time_text || r.timeText || '—')}</td></tr>`
  )).join('')
  return `<section class="report-card" id="sec-evidence-refs"><h2>Evidence Refs</h2>`
    + '<p class="detail-note">Timestamps and measured evidence from Analysis Findings '
    + '(export context; does not jump back into BTFViewer).</p>'
    + '<table class="meta-table"><thead><tr><th>Finding</th><th>Evidence / Time</th>'
    + `</tr></thead><tbody>${body}</tbody></table></section>`
}

export function htmlTraceMetadataCard({
  span, tasks, segments, stiEvents, contextSwitches, coreGapAvg = '', coreGapMax = '', scopeTitle = '',
}) {
  const rows = [
    [`Span${scopeTitle}`, span],
    ['Tasks', Number(tasks || 0).toLocaleString('en-US')],
    ['Segments', Number(segments || 0).toLocaleString('en-US')],
    ['STI events', Number(stiEvents || 0).toLocaleString('en-US')],
    [`Context switches${scopeTitle}`, Number(contextSwitches || 0).toLocaleString('en-US')],
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
  return `<div class="kpi-grid">${kpis.map(k => htmlKpi(k.label, k.value, k)).join('')}</div>`
}

/**
 * Ranked HTML/CSS bar list (not canvas/SVG): `[[label, value, display], ...]`,
 * already in display order. The largest value in `items` (or `maxV`, if a
 * caller wants a scale independent of this particular slice) is 100% bar
 * width. `fillKind` selects the semantic color family (warning/danger/
 * accent/success) per the mini-bar-chart palette rule.
 */
export function htmlRankBars(items, { fillKind = 'accent', maxV = null } = {}) {
  const rows = (items || []).filter(Boolean)
  if (!rows.length) return ''
  const peak = Math.max(maxV || Math.max(...rows.map(([, v]) => Number(v)), 1), 1)
  const cls = fillKind ? ` ${fillKind}` : ''
  const parts = ['<div class="rank-bars">']
  rows.forEach(([label, value, display], idx) => {
    const pct = Math.max(0, Math.min(100, 100 * Number(value) / peak))
    parts.push(
      `<div class="rank-bar" title="${esc(label)}: ${esc(display)}">`
      + `<span class="rank-bar-num">${idx + 1}</span>`
      + `<span class="rank-bar-label">${esc(label)}</span>`
      + `<span class="rank-bar-track"><span class="rank-bar-fill${cls}" `
      + `style="width:${pct.toFixed(1)}%"></span></span>`
      + `<span class="rank-bar-value">${esc(display)}</span>`
      + '</div>'
    )
  })
  parts.push('</div>')
  return parts.join('')
}

/**
 * One `label + progress bar + %` row, for Core Utilization / Top Tasks by CPU
 * and the Performance Overview panels. `kind` is `core` or `task`.
 */
export function htmlUtilBarRow(label, pct, kind) {
  const pctV = Math.max(0, Math.min(100, Number(pct) || 0))
  const lab = esc(label)
  const rowCls = kind === 'core' ? 'util-row util-row-core' : 'util-row util-row-task'
  const pctCls = kind === 'core' ? 'util-pct util-pct-core' : 'util-pct util-pct-task'
  return `<div class="${rowCls}" title="${lab}: ${pctV.toFixed(1)}%">`
    + `<span class="util-label">${lab}</span>`
    + `<div class="util-bar"><div class="util-bar-fill" style="width:${pctV.toFixed(1)}%"></div></div>`
    + `<span class="${pctCls}">${pctV.toFixed(1)}%</span></div>`
}

/**
 * Report card of utilisation bar rows: `[[label, pct], ...]`.
 * `leadHtml` is placed between the heading and the bars (the Core Utilization
 * card uses it for the load-balance gauge).
 */
export function htmlUtilSection(title, rows, kind, { leadHtml = '' } = {}) {
  const items = (rows || []).map(([label, pct]) => htmlUtilBarRow(label, pct, kind)).join('')
  const body = items ? `<div class="util-list">${items}</div>` : '<p class="empty">No data</p>'
  return `<section class="report-card"><h2>${esc(title)}</h2>${leadHtml}${body}</section>`
}

/** Theme-aware verdict banner. `bodyHtml` is already escaped by the caller. */
export function htmlReportVerdict(kind, bodyHtml) {
  const k = (kind === 'ok' || kind === 'warn' || kind === 'error') ? kind : 'ok'
  return `<p class="report-verdict ${k}"><strong>Verdict:</strong> ${bodyHtml}</p>`
}

/** Top-N horizontal P99 bars from the same response-time rows as the table. */
export function htmlResponseP99Chart(rows, { formatP99, limit = 8 } = {}) {
  const items = (rows || []).filter(r => r && typeof r === 'object')
    .sort((a, b) => (Number(b.p99_ns) || 0) - (Number(a.p99_ns) || 0))
    .slice(0, Math.max(0, Number(limit) || 0))
  if (!items.length) return ''
  const bars = htmlRankBars(items.map((r) => {
    const ns = Number(r.p99_ns) || 0
    const display = typeof formatP99 === 'function' ? formatP99(ns) : String(ns)
    return [String(r.task || ''), ns, display]
  }), { fillKind: 'accent' })
  return '<div class="metric-chart p99-chart"><div class="metric-chart-head"><div>'
    + '<div class="metric-chart-title">Highest response P99</div>'
    + '<div class="metric-chart-subtitle">Top observed tasks by P99 response time. '
    + 'Full percentile data remains in the table below.</div>'
    + `</div></div>${bars}</div>`
}

/**
 * Inline SVG of Load Balance Score over time.
 * `samples` is `[{time, score, sigma}, ...]` already formatted and in
 * trace-time order. Every numeric score is plotted; Y is 0–100.
 */
export function htmlSchedulingBalanceChart(samples) {
  const pts = []
  for (const s of samples || []) {
    if (!s || typeof s !== 'object' || s.score == null) continue
    const score = Number(s.score)
    if (!Number.isFinite(score)) continue
    const sigma = Number(s.sigma)
    pts.push([String(s.time || ''), Math.max(0, Math.min(100, score)), Number.isFinite(sigma) ? sigma : 0])
  }
  if (!pts.length) return ''
  const width = 760
  const height = 230
  const padL = 52
  const padR = 20
  const padT = 24
  const padB = 38
  const plotW = width - padL - padR
  const plotH = height - padT - padB
  const n = pts.length
  const xAt = i => (n === 1 ? padL : padL + plotW * i / (n - 1))
  const yAt = score => padT + plotH * (1 - score / 100)
  let lowI = 0
  pts.forEach((p, i) => { if (p[1] < pts[lowI][1]) lowI = i })
  const grid = [0, 25, 50, 75, 100].map((mark) => {
    const gy = yAt(mark)
    return `<line class="chart-gridline" x1="${padL}" x2="${width - padR}" y1="${gy.toFixed(1)}" y2="${gy.toFixed(1)}"/>`
      + `<text class="chart-axis-label" text-anchor="end" x="${padL - 9}" y="${(gy + 4).toFixed(1)}">${mark}</text>`
  }).join('')
  const labelIdx = n === 1 ? [0] : [0, Math.floor(n / 2), n - 1]
  const seen = new Set()
  const axisX = labelIdx.filter((i) => {
    if (seen.has(i)) return false
    seen.add(i)
    return true
  }).map(i => (
    `<text class="chart-axis-label" text-anchor="middle" x="${xAt(i).toFixed(1)}" y="${height - 12}">${esc(pts[i][0])}</text>`
  )).join('')
  const poly = pts.map((p, i) => `${xAt(i).toFixed(1)},${yAt(p[1]).toFixed(1)}`).join(' ')
  const dots = pts.map((p, i) => {
    const kind = i === lowI ? 'chart-point-low' : 'chart-point-normal'
    const title = `${esc(p[0])} · Load balance ${p[1].toFixed(0)} · Util σ ${p[2].toFixed(1)}%`
    return `<circle class="chart-point ${kind}" cx="${xAt(i).toFixed(1)}" cy="${yAt(p[1]).toFixed(1)}" r="4"><title>${title}</title></circle>`
  }).join('')
  const [lowTime, lowScore] = pts[lowI]
  return '<div class="metric-chart scheduling-chart"><div class="metric-chart-head"><div>'
    + '<div class="metric-chart-title">Load balance over time</div>'
    + '<div class="metric-chart-subtitle">Lower scores indicate more uneven '
    + 'core utilization during that sample window.</div></div>'
    + `<div class="chart-callout"><span class="chart-callout-label">Lowest</span>`
    + `<strong>${lowScore.toFixed(0)}</strong>`
    + `<span class="chart-callout-note">at ${esc(lowTime)}</span></div></div>`
    + `<svg class="trend-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Load balance score over time">`
    + `${grid}${axisX}<polyline class="chart-line" fill="none" points="${poly}"/>${dots}</svg></div>`
}

/**
 * `[{name,value,unit,sample_count?}]` → "Name value unit (n=…)" list.
 * Kept separate from finding display text so exports stay reproducible.
 */
function formatMeasuredValues(values) {
  if (!Array.isArray(values)) return ''
  const parts = []
  for (const mv of values) {
    if (!mv || typeof mv !== 'object' || !('name' in mv) || !('value' in mv)) continue
    let chunk = `${mv.name} ${mv.value}${mv.unit || ''}`.trimEnd()
    if (mv.sample_count != null) chunk += ` (n=${mv.sample_count})`
    parts.push(chunk)
  }
  return parts.join('; ')
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
    const basis = String(f.comparison_basis || '').trim()
    const measured = formatMeasuredValues(f.measured_values)
    const sev = String(f.severity || 'info')
    return `<article class="finding-card ${cls}">`
      + `<h3>${esc(sev[0].toUpperCase() + sev.slice(1))} · ${esc(f.title || 'Finding')}</h3>`
      + `<p>${esc(f.text || '')}</p>`
      + (impact ? `<div class="finding-meta"><strong>Impact:</strong> ${esc(impact)}</div>` : '')
      + (measured ? `<div class="finding-meta"><strong>Measured:</strong> ${esc(measured)}</div>` : '')
      + (basis ? `<div class="finding-meta"><strong>Basis:</strong> ${esc(basis)}</div>` : '')
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

const TRACE_HEALTH_STATUS_META = {
  pass: ['finding-ok', 'Pass'],
  caution: ['sev-warning', 'Caution'],
  insufficient: ['sev-error', 'Insufficient data'],
}

/**
 * Structural Trace Health section (status + per-check detail + limited metrics).
 * Distinct from *Trace Health (TICK)*. Keep in sync with
 * ``btf_viewer_pkg/stats_html.py:html_trace_health_card``.
 */
export function htmlTraceHealthCard(result, { formatNs = null, scopeTitle = '' } = {}) {
  if (!result) return ''
  const status = String(result.status || 'pass')
  const [cls, label] = TRACE_HEALTH_STATUS_META[status] || ['finding-info', status]
  const checks = result.checks || []
  const n = Number(result.issueCount ?? result.issue_count ?? 0)
  const fmt = (v) => {
    if (typeof formatNs === 'function') {
      try { return String(formatNs(Number(v))) } catch { return String(v) }
    }
    return String(v)
  }
  const rows = checks.map((c) => {
    const sev = String(c.severity || 'info')
    const sevCls = sev === 'error' ? 'sev-error' : sev === 'warning' ? 'sev-warning' : 'finding-info'
    const bits = []
    const rng = c.affectedRange || c.affected_range
    if (rng && rng.start != null) {
      bits.push(`<strong>Range:</strong> ${esc(fmt(rng.start))} – ${esc(fmt(rng.end))}`)
    }
    const ents = (c.affectedEntities || c.affected_entities || []).map(String).filter(Boolean)
    if (ents.length) bits.push(`<strong>Affected:</strong> ${esc(ents.slice(0, 12).join(', '))}`)
    const refs = (c.evidenceRefs || c.evidence_refs || []).map(String).filter(Boolean)
    if (refs.length) bits.push(`<strong>Evidence:</strong> ${esc(refs.join('; '))}`)
    const lims = (c.metricLimitations || c.metric_limitations || []).map(String).filter(Boolean)
    if (lims.length) bits.push(`<strong>Limited:</strong> ${esc(lims.join(', '))}`)
    const meta = bits.map(b => `<div class="finding-meta">${b}</div>`).join('')
    return `<details class="trace-health-check ${sevCls}">`
      + `<summary>${esc(sev[0].toUpperCase() + sev.slice(1))} · ${esc(c.summary || '')}</summary>`
      + `${meta}</details>`
  }).join('')
  const detail = checks.length
    ? rows
    : '<p class="detail-note">No structural inconsistencies found in the parsed event model under the current checks.</p>'
  const limitations = (result.metricLimitations || result.metric_limitations || []).map(String).filter(Boolean)
  let limHtml = ''
  if (limitations.length) {
    const lis = limitations.map(m => `<li>${esc(m)}</li>`).join('')
    limHtml = '<h3 class="sub">Limited metrics</h3>'
      + '<p class="detail-note">These sections may show <em>Insufficient data</em> or a limitation notice instead of a value.</p>'
      + `<ul>${lis}</ul>`
  }
  return '<section class="report-card notes trace-health">'
    + `<h2>Trace Health Check${esc(scopeTitle)}</h2>`
    + '<p class="detail-note">Deterministic structural checks on the parsed event model. '
    + 'Independent of AI and of <em>Trace Health (TICK)</em>, which only measures tick regularity.</p>'
    + `<p class="trace-health-status"><span class="${cls}">Status: ${esc(label)}</span> &middot; ${n} issue(s)</p>`
    + `${detail}${limHtml}</section>`
}

const BM_TYPE_LABELS = {
  observation: 'Observation',
  hypothesis: 'Hypothesis',
  supporting: 'Supporting evidence',
  contradicting: 'Contradicting evidence',
  verification: 'Verification step',
  conclusion: 'Conclusion',
}
const FACT_TYPES = ['observation', 'supporting', 'verification']

function fmtRef(ref, formatNs) {
  const kind = String(ref.kind || '')
  const f = (v) => {
    if (typeof formatNs === 'function') { try { return String(formatNs(Math.trunc(v))) } catch { return String(v) } }
    return String(v)
  }
  if (kind === 'finding') return `finding <code>${esc(ref.rule_id || ref.label || '?')}</code>`
  if (kind === 'metric') return `metric “${esc(ref.metric || ref.label || '?')}”`
  if (kind === 'entity') return `entity <code>${esc(ref.entity || ref.label || '?')}</code>`
  if (kind === 'range' || kind === 'evidence') {
    const rng = ref.range || {}
    if (rng.start != null) return `range ${esc(f(rng.start))} – ${esc(f(rng.end))}`
    if (ref.time != null) return `time ${esc(f(ref.time))}`
  }
  return esc(ref.label || kind || 'ref')
}

/**
 * Investigation Bookmarks and Evidence Chain section.
 * Keep in sync with btf_viewer_pkg/stats_html.py:html_investigation_section.
 */
const EVIDENCE_KIND_LABELS_HTML = {
  measured: 'Measured', derived: 'Derived', heuristic: 'Heuristic',
  estimate: 'Simulation / estimate', '': 'User note',
}
const NB_SECTION_HEADING = {
  question: 'Question', scope: 'Scope', hypotheses: 'Hypotheses',
  evidence: 'Evidence', open_checks: 'Open checks', conclusion: 'Conclusion',
}
const NB_HTML_SECTION_ORDER = [
  'question', 'scope', 'hypotheses', 'evidence', 'open_checks', 'conclusion',
]

function nbItemRefsHtml(refs, formatNs) {
  if (!refs || !refs.length) return ''
  return `<div class="finding-meta"><strong>References:</strong><ul>${refs.map(r => `<li>${fmtRef(r, formatNs)}</li>`).join('')}</ul></div>`
}

/** Investigation Notebook section for the HTML report — the same six sections,
 *  in the same order, as the Notebook UI. Keep in sync with
 *  btf_viewer_pkg/stats_html.py:html_investigation_section. */
export function htmlInvestigationSection(investigation, {
  formatNs = null, brokenRefs = null, chains = null, scopeTitle = '',
} = {}) {
  if (!investigation) return ''
  const inv = loadInvestigation(investigation)
  if (!(inv.bookmarks || []).length
    && !String(inv.conclusion || '').trim()
    && !String(inv.title || '').trim()) return ''

  const broken = brokenRefs || {}
  const sections = Object.fromEntries(
    investigationSections(inv, { broken }).map(s => [s.id, s]),
  )
  const chainsById = {}
  for (const c of chains || []) if (c && typeof c === 'object') chainsById[String(c.conclusion_id)] = c

  const sub = (label, body) => (body ? `<h3 class="sub">${esc(label)}</h3>${body}` : '')

  const qItems = sections.question.items
  const questionHtml = qItems.length
    ? `<p class="detail-note"><strong>${esc(qItems[0].text)}</strong></p>` : ''

  const scopeBits = sections.scope.items.filter(it => it.text).map(it => esc(it.text))
  const scopeHtml = scopeBits.length ? `<p class="detail-note">${scopeBits.join(' · ')}</p>` : ''

  const hypRows = sections.hypotheses.items.map((it) => {
    const status = esc(String(it.status || 'open'))
    const note = String(it.note || '').trim()
    return `<article class="finding-card"><h3>Hypothesis · ${esc(it.text)} `
      + `<span class="finding-meta">[${status}]</span></h3>`
      + (note ? `<p>${esc(note)}</p>` : '')
      + nbItemRefsHtml(it.refs, formatNs) + '</article>'
  })
  const hypHtml = hypRows.length ? `<div class="finding-cards">${hypRows.join('')}</div>` : ''

  const evRows = sections.evidence.items.map((it) => {
    const card = it.card || {}
    const kind = EVIDENCE_KIND_LABELS_HTML[String(it.kind || '')] || 'User note'
    const source = esc(String(card.source || ''))
    const author = String(card.author || '')
    const authorTag = author === 'ai' ? ' · AI' : (author === 'btfviewer' ? ' · BTFViewer' : '')
    const note = String(it.note || '').trim()
    const staleHtml = it.stale
      ? '<div class="finding-meta sev-warning"><strong>Stale:</strong> reference no longer resolves against the current trace.</div>'
      : ''
    const roleLabel = String(it.role || 'evidence')
    return `<article class="finding-card"><h3>${esc(roleLabel[0].toUpperCase() + roleLabel.slice(1))} · `
      + `${esc(it.text)} <span class="finding-meta">[${esc(kind)}`
      + (source ? ` · ${source}` : '') + `${authorTag}]</span></h3>`
      + (note ? `<p>${esc(note)}</p>` : '')
      + nbItemRefsHtml(it.refs, formatNs) + staleHtml + '</article>'
  })
  const evHtml = evRows.length ? `<div class="finding-cards">${evRows.join('')}</div>` : ''

  const checkLis = sections.open_checks.items.map((it) => {
    const prefix = it.source === 'verification' ? 'Verify: ' : ''
    return `<li>${esc(prefix + String(it.text || ''))}</li>`
  })
  const checksHtml = checkLis.length ? `<ul>${checkLis.join('')}</ul>` : ''

  const conclRows = []
  for (const it of sections.conclusion.items) {
    if (it.kind === 'verification_state') {
      conclRows.push(`<div class="finding-meta">${esc(it.text || '')}</div>`)
      continue
    }
    const bid = String(it.bookmark_id || '')
    const chain = bid ? chainsById[bid] : null
    let chainHtml = ''
    if (chain && (chain.evidence || []).length) {
      chainHtml = `<div class="finding-meta"><strong>Backed by:</strong><ul>${chain.evidence.map(e => `<li>${esc(BM_TYPE_LABELS[e.type] || 'Bookmark')}: ${esc(e.title || e.id)}</li>`).join('')}</ul></div>`
    } else if (chain != null) {
      chainHtml = '<div class="finding-meta sev-warning"><strong>Not grounded:</strong> no linked evidence.</div>'
    }
    conclRows.push('<article class="finding-card finding-ok"><h3>Conclusion'
      + (it.bookmark_id ? ` · ${esc(it.text)}` : '') + '</h3>'
      + (!it.bookmark_id ? `<p>${esc(it.text)}</p>` : '')
      + chainHtml + '</article>')
  }
  const conclHtml = conclRows.length ? `<div class="finding-cards">${conclRows.join('')}</div>` : ''

  const staleBanner = broken.stale_trace
    ? '<p class="detail-note sev-warning">The source trace changed since these notes were written — references may not line up.</p>'
    : ''

  const bodyById = {
    question: questionHtml, scope: scopeHtml, hypotheses: hypHtml,
    evidence: evHtml, open_checks: checksHtml, conclusion: conclHtml,
  }
  const blocks = NB_HTML_SECTION_ORDER.map(sid => sub(NB_SECTION_HEADING[sid], bodyById[sid])).join('')

  return '<section class="report-card notes investigation">'
    + `<h2>Investigation${esc(scopeTitle)}</h2>`
    + '<p class="detail-note">The Notebook, in the same six sections as the app. '
    + 'Evidence keeps its provenance; notes never change measured values.</p>'
    + staleBanner + blocks
    + '</section>'
}

/** Fixed heat-0..heat-5 bin index (not a continuous color) - a Chromium /
 *  Qt WebEngine runtime theme switch cannot be relied on to re-evaluate
 *  color-mix()/computed colors, but a plain class swap always repaints. */
function heatBin(value, maxV) {
  if (value <= 0) return 0
  const normalized = value / Math.max(1, maxV)
  return Math.max(1, Math.min(5, Math.ceil(normalized * 5)))
}

/**
 * CSS-grid heat matrix with fixed heat-0..heat-5 classes (not inline SVG
 * rgb() fills - see heatBin). A cell value of `null`/`undefined` renders as
 * a dashed no-data cell, distinct from a real 0. `diagonalDash: true` treats
 * a cell whose row/col label match (self-pair) as a dashed diagonal cell
 * instead of a heat cell, e.g. Core_5 vs. Core_5. `extraCol`, if given, is
 * `[label, values, unit]`: one additional trailing column rendered as a
 * plain (non heat-colored) value per row — e.g. a derived per-sample
 * "Spread" figure that shouldn't be confused with the matrix's own
 * heat-scaled readings.
 */
export function htmlMatrixHeatmap(rowLabels, colLabels, cells, {
  title, subtitle = '', unit = '%', width = 640, diagonalDash = false,
  tooltipSep = '→', maxValueOverride = null, extraCol = null,
} = {}) {
  const rows = rowLabels || []
  const cols = colLabels || []
  if (!rows.length || !cols.length) return ''
  const [extraLabel, extraValues, extraUnit] = extraCol || [null, [], '%']
  let maxV = 0
  for (const line of cells || []) {
    for (const v of line || []) {
      if (v == null) continue
      maxV = Math.max(maxV, Number(v) || 0)
    }
  }
  maxV = (maxValueOverride != null && maxValueOverride > 0) ? Number(maxValueOverride) : Math.max(maxV, 1)
  const head = '<div class="heat-matrix-head">'
    + `<div class="heat-matrix-title">${esc(title)}</div>`
    + (subtitle ? `<div class="heat-matrix-subtitle">${esc(subtitle)}</div>` : '')
    + '</div>'
  const colCount = cols.length + (extraLabel ? 1 : 0)
  const parts = [
    '<div class="heat-wrap">',
    head,
    `<div class="heat-grid" style="--col-count:${colCount}">`,
    '<div class="heat-grid-corner"></div>',
  ]
  cols.forEach(col => {
    const colS = String(col)
    parts.push(`<div class="heat-grid-collabel" title="${esc(colS)}">${esc(colS.slice(0, 6))}</div>`)
  })
  if (extraLabel) {
    parts.push(`<div class="heat-grid-collabel" title="${esc(extraLabel)}">${esc(String(extraLabel).slice(0, 8))}</div>`)
  }
  rows.forEach((row, i) => {
    const rowS = String(row)
    parts.push(`<div class="heat-grid-rowlabel" title="${esc(rowS)}">${esc(rowS.slice(0, 16))}</div>`)
    const line = cells[i] || []
    cols.forEach((col, j) => {
      const colS = String(col)
      if (diagonalDash && rowS === colS) {
        parts.push(`<div class="heat-grid-cell heat-grid-diagonal" title="${esc(rowS)}">—</div>`)
        return
      }
      const raw = line[j]
      if (raw == null) {
        parts.push('<div class="heat-grid-cell heat-grid-nodata" title="No data">—</div>')
        return
      }
      const val = Number(raw) || 0
      const label = unit === '%' ? `${val.toFixed(0)}${unit}` : `${val.toFixed(0)}`
      const tip = `${esc(rowS)} ${tooltipSep} ${esc(colS)}: ${esc(label)}`
      parts.push(`<div class="heat-grid-cell heat-${heatBin(val, maxV)}" title="${tip}">${esc(label)}</div>`)
    })
    if (extraLabel) {
      const extraRaw = extraValues[i]
      if (extraRaw == null) {
        parts.push('<div class="heat-grid-cell heat-grid-nodata" title="No data">—</div>')
      } else {
        const extraVal = Number(extraRaw) || 0
        const extraDisp = extraUnit === '%' ? `${extraVal.toFixed(0)}${extraUnit}` : `${extraVal.toFixed(0)}`
        parts.push(`<div class="heat-grid-cell heat-grid-extra" title="${esc(rowS)}: ${esc(extraLabel)} ${esc(extraDisp)}">${esc(extraDisp)}</div>`)
      }
    }
  })
  parts.push('</div></div>')
  return parts.join('')
}

/** 0% -> 100% gradient key for the heat-0..heat-5 color scale, for a
 *  matrix where the reader benefits from an explicit low/high reference
 *  (e.g. Core Utilization Over Time). */
export function htmlHeatLegend() {
  return '<div class="heat-legend"><div class="heat-legend-grid">'
    + '<span>0%</span><div class="heat-legend-bar"></div><span>100%</span>'
    + '<span>Lower</span><span></span><span>Higher</span>'
    + '</div></div>'
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
    `<div class="heat-wrap"><svg class="pctile-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${h}" width="${width}" height="${h}" role="img" aria-label="${esc(title)}">`,
    `<text class="pctile-title" x="${pad}" y="16" font-size="12" font-weight="600">${esc(title)}</text>`,
    `<text class="pctile-sub" x="${width - pad}" y="16" text-anchor="end" font-size="11">interval = P50–P99</text>`,
  ]
  items.forEach((r, i) => {
    const y = header + i * rowH
    const p50 = Number(r.p50_ns || 0)
    const p95 = Number(r.p95_ns || 0)
    const p99 = Number(r.p99_ns || 0)
    const x0 = labelW + plotW * p50 / maxV
    const x1 = labelW + plotW * Math.max(p99, p50) / maxV
    const x95 = labelW + plotW * p95 / maxV
    parts.push(`<text class="pctile-label" x="8" y="${y + 14}" font-size="11">${esc(String(r.task || '').slice(0, 16))}</text>`)
    parts.push(`<rect class="pctile-bar" x="${x0.toFixed(1)}" y="${y + 6}" width="${Math.max(x1 - x0, 2).toFixed(1)}" height="8" rx="3"/>`)
    parts.push(`<line class="pctile-marker" x1="${x95.toFixed(1)}" y1="${y + 4}" x2="${x95.toFixed(1)}" y2="${y + 16}" stroke-width="2"/>`)
  })
  parts.push('</svg></div>')
  return parts.join('')
}

/**
 * Task Health score bars. The score is a 0-100 magnitude, so it uses the
 * shared quantitative bar component (`--data-bar`) like every other bar in the
 * report; the per-metric deductions stay in the trailing text and the table
 * below.
 */
export function htmlHealthBars(rows) {
  const items = [...(rows || [])].filter(r => r && typeof r === 'object')
    .sort((a, b) => (a.score || 0) - (b.score || 0))
    .slice(0, 16)
  if (!items.length) return ''
  return `<div class="health-bars">${items.map((r) => {
    const score = Math.max(0, Math.min(100, Number(r.score || 0)))
    const marks = r.marks || {}
    const reasons = Object.keys(marks).filter(k => marks[k])
    const reason = reasons.length ? reasons.join(', ') : 'no deductions'
    const task = String(r.task || '')
    return `<div class="pct-bar" title="${esc(task)}: score ${score}/100 · ${esc(reason)}">`
      + `<span class="lab">${esc(task.slice(0, 18))}</span>`
      + `<div class="track"><div class="fill" style="width:${score}%"></div></div>`
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
  return `<svg class="pctile-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="Tag time series">`
    + `<polyline class="sparkline-line" fill="none" stroke-width="1.5" points="${pts.join(' ')}"/></svg>`
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
  let note = String(rangeNote || '').trim()
  if (note.startsWith('<li>') && note.endsWith('</li>')) note = note.slice(4, -5).trim()
  const items = [
    note,
    '<strong>Execution Time Per Slice:</strong> Duration of each continuous task run between two context switches.',
    '<strong>Highest CPU consumers</strong> are tasks with the largest share of active CPU time. They are not automatically WCET candidates. Largest execution-time maxima live in Execution Time Per Slice.',
    '<strong>Inter-Arrival Time:</strong> Time between consecutive activations of the same task (slice start to next slice start).',
    '<strong>Off-CPU Time (Blocking Time):</strong> Gap between the end of one slice and the start of the next for the same task. It may include preemption, suspension, periodic waiting, or scheduling delay — not necessarily resource blocking. It is not end-to-end response time.',
    '<strong>CPU% (task):</strong> Share of total non-IDLE/TICK <em>active CPU time</em> in scope, not wall-clock span and not total multicore capacity.',
    '<strong>Core Utilization:</strong> Non-IDLE/TICK active time on that core divided by the scoped wall-clock span (one-core capacity = 100%).',
    '<strong>Load Balance Score:</strong> 100% × (1 − Gini of core utilization). 100 = evenly distributed utilization; 0 = highly uneven. Even overload or even idle can still score high.',
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
