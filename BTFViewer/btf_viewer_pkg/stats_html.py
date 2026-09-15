"""Statistics HTML report helpers (Desktop). Keep in sync with web statsHtmlReport.js."""
from __future__ import annotations

import html
import math
from typing import Optional, Sequence

from .html_report import html_section_slug
from .parser import _tag_axis_bounds, _tag_transform, _tag_inverse, _format_tag_value

STATS_TOC_GROUPS = (
    ("Overview and Findings", (
        "Performance Overview", "Analysis Scope", "Evidence Refs", "Analysis Findings",
        "Trace Health Check", "Investigation", "Trace Metadata",
    )),
    ("CPU and Scheduling", (
        "Core Utilization", "Trace Health (TICK)", "Core Time Breakdown",
        "Concurrent Core Active Distribution", "Switch Reason Breakdown",
        "Scheduling Load Over Time", "Kernel Switch Overhead", "Idle Analysis",
        "Top Tasks by CPU",
    )),
    ("Migrations and Core Affinity", (
        "Core Migration Count", "Core-Pair Migration Summary", "Core Affinity",
        "Task × Core", "Core Utilization Over Time", "Task Lifecycle",
        "Deadlines / CPU budget", "Task Health",
    )),
    ("Timing, Latency and Jitter", (
        "Investigate Anomalies", "Execution Time Per Slice",
        "Off-CPU Time", "Dispatch / Scheduling Latency", "Inter-Arrival Time",
        "Activation Latency", "Ready-Gap (Starvation)",
        "Period / Jitter", "Response Time", "Unified Jitter",
    )),
    ("Synchronization and Custom Events", (
        "Preemption Chain Analysis", "Preemption Matrix", "Priority Inheritance",
        "Mutex / Semaphore", "Waiter × Owner", "Mutex Blocking", "Queue",
        "Queue Backlog / Semaphore Level",
        "Interval Analysis", "Tag Analysis", "Statistics Notes",
    )),
)

STATS_DEFAULT_EXPANDED = (
    "Analysis Scope",
    "Analysis Findings",
    "Trace Health Check",
    "Core Utilization (excl. IDLE/TICK)",
    "Trace Health (TICK)",
    "Investigate Anomalies",
)

STATS_HTML_EXTRA_CSS = """
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
th, td { border-bottom: 1px solid var(--line); padding: 8px 10px; font-size: 12px; text-align: right; }
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
.lb-gauge-svg .lb-value-arc { stroke-dasharray: 100; stroke-dashoffset: 100; }
.lb-gauge-svg .lb-needle { transform: scale(0); }
.lb-gauge-svg .lb-value-ok, .lb-gauge-svg .lb-value-amber, .lb-gauge-svg .lb-value-red {
  opacity: 0; transform-box: fill-box; transform-origin: center;
}
.lb-gauge-svg.lb-gauge-active .lb-value-arc {
  animation: lb-arc-in 0.85s cubic-bezier(.2,.8,.2,1) forwards;
}
.lb-gauge-svg.lb-gauge-active .lb-needle {
  animation: lb-needle-in 0.58s cubic-bezier(.2,1.35,.35,1) 0.34s forwards;
}
.lb-gauge-svg.lb-gauge-active .lb-value-ok,
.lb-gauge-svg.lb-gauge-active .lb-value-amber,
.lb-gauge-svg.lb-gauge-active .lb-value-red {
  animation: lb-value-in 0.35s ease-out 0.62s forwards;
}
@keyframes lb-arc-in { to { stroke-dashoffset: 0; } }
@keyframes lb-needle-in { from { transform: scale(0); } to { transform: scale(1); } }
@keyframes lb-value-in {
  from { opacity: 0; transform: translateY(3px) scale(.92); }
  to { opacity: 1; transform: none; }
}
@media (prefers-reduced-motion: reduce) {
  .lb-gauge-svg .lb-value-arc { stroke-dashoffset: 0; }
  .lb-gauge-svg .lb-needle { transform: none; }
  .lb-gauge-svg .lb-value-ok, .lb-gauge-svg .lb-value-amber,
  .lb-gauge-svg .lb-value-red { opacity: 1; transform: none; }
}
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
tbody tr:focus-within td,
tbody tr:focus-within th,
tbody tr:hover td,
tbody tr:hover th,
.table-scroll tbody tr:hover td:first-child,
.table-scroll tbody tr:hover th:first-child,
.table-scroll tbody tr:focus-within td:first-child,
.table-scroll tbody tr:focus-within th:first-child { background: var(--row-hover-bg); }
tbody tr:hover, tbody tr:focus-within {
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
  box-shadow: inset 0 0 0 1px var(--bar-track-border); border-radius: var(--std-bar-r); overflow: hidden;
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
  box-shadow: inset 0 0 0 1px var(--bar-track-border); border-radius: var(--std-bar-r); overflow: hidden;
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
  white-space: nowrap; text-align: left; font-size: 12px; color: var(--ink);
}
.util-bar {
  flex: 1 1 auto; height: var(--std-bar-h); min-width: 24px; border-radius: var(--std-bar-r);
  background: var(--bar-track-bg); box-shadow: inset 0 0 0 1px var(--bar-track-border); overflow: hidden;
}
.util-bar-fill, .util-row-task .util-bar-fill {
  height: 100%; border-radius: calc(var(--std-bar-r) - 1px); background: var(--data-bar);
}
.util-pct { flex: 0 0 44px; text-align: left; font-size: 12px; }
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
  tbody tr:hover td, tbody tr:hover th, tbody tr:focus-within td, tbody tr:focus-within th,
  .table-scroll tbody tr:hover td:first-child, .table-scroll tbody tr:hover th:first-child,
  .table-scroll tbody tr:focus-within td:first-child, .table-scroll tbody tr:focus-within th:first-child { background: inherit; }
  tbody tr:hover, tbody tr:focus-within { box-shadow: none; }
  .util-row:hover .util-bar-fill, .rank-bar:hover .rank-bar-fill, .pct-bar:hover .fill { filter: none; }
  .util-row:hover .util-label, .rank-bar:hover .rank-bar-label, .pct-bar:hover .lab { color: var(--ink); }
  .metric-chart, .kpi, .report-card { box-shadow: none; }
  .theme-toggle { display: none !important; }
  .metric-chart, .kpi { break-inside: avoid; }
}
""".strip()


def _esc(v: object) -> str:
    return html.escape(str(v), quote=True)


def html_inspect_href(section_title: str) -> str:
    return f"#sec-{html_section_slug(section_title)}"


def html_kpi(label: str, value: str, *, hint: str = "", kind: str = "") -> str:
    cls = f"kpi {kind}" if kind else "kpi"
    extra = f'<div class="s">{_esc(hint)}</div>' if hint else ""
    return (
        f'<article class="{cls}"><div class="k">{_esc(label)}</div>'
        f'<div class="v">{_esc(value)}</div>{extra}</article>'
    )


def html_scope_identity_card(
    *,
    filename: str,
    scope_type: str,
    start: str,
    end: str,
    duration: str,
    cores: int,
    filters: str,
    timestamp_mode: str,
    task_count: int,
    sample_note: str = "",
) -> str:
    rows = [
        ("Trace file", filename or "—"),
        ("Scope", scope_type),
        ("Start", start),
        ("End", end),
        ("Duration", duration),
        ("Cores", f"{cores}"),
        ("Tasks in scope", f"{task_count:,}"),
        ("Filters", filters or "None"),
        ("Timestamps", timestamp_mode),
    ]
    body = "".join(
        f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in rows
    )
    note = (
        f'<p class="detail-note">{_esc(sample_note)}</p>' if sample_note else ""
    )
    return (
        '<section class="report-card" id="sec-analysis-scope">'
        "<h2>Analysis Scope</h2>"
        f'<table class="meta-table scope-table"><tbody>{body}</tbody></table>'
        f"{note}</section>"
    )


def evidence_refs_from_findings(
    findings: Sequence[dict],
    *,
    format_ns=None,
    limit: int = 12,
) -> list:
    """Build ``{label, time_text}`` refs from Analysis Findings for HTML export."""
    out: list = []
    for f in findings or []:
        if not isinstance(f, dict):
            continue
        label = str(f.get("title") or "Finding").strip() or "Finding"
        times: list = []
        for ev in f.get("evidence") or []:
            if not isinstance(ev, dict):
                continue
            for key in ("time", "start", "stop", "ns"):
                raw = ev.get(key)
                if raw is None:
                    continue
                try:
                    times.append(int(float(raw)))
                except (TypeError, ValueError):
                    continue
                break
        time_text = ""
        if times and callable(format_ns):
            try:
                time_text = ", ".join(str(format_ns(t)) for t in times[:3])
            except Exception:
                time_text = ", ".join(str(t) for t in times[:3])
        elif times:
            time_text = ", ".join(str(t) for t in times[:3])
        if not time_text:
            et = str(f.get("evidence_text") or "").strip()
            if et:
                time_text = et[:160]
        if not time_text:
            continue
        out.append({"label": label, "time_text": time_text})
        if len(out) >= max(1, int(limit or 12)):
            break
    return out


def html_evidence_refs_card(refs: Sequence[dict]) -> str:
    """Compact Evidence refs card (label + time) for investigation exports."""
    items = [r for r in (refs or []) if isinstance(r, dict) and (
        str(r.get("label") or "").strip() or str(r.get("time_text") or "").strip()
    )]
    if not items:
        return ""
    body = "".join(
        "<tr>"
        f"<td>{_esc(r.get('label') or 'Finding')}</td>"
        f"<td>{_esc(r.get('time_text') or '—')}</td>"
        "</tr>"
        for r in items
    )
    return (
        '<section class="report-card" id="sec-evidence-refs">'
        "<h2>Evidence Refs</h2>"
        '<p class="detail-note">Timestamps and measured evidence from Analysis Findings '
        "(export context; does not jump back into BTFViewer).</p>"
        '<table class="meta-table"><thead><tr><th>Finding</th><th>Evidence / Time</th>'
        f"</tr></thead><tbody>{body}</tbody></table></section>"
    )


def html_trace_metadata_card(
    *,
    span: str,
    tasks: int,
    segments: int,
    sti_events: int,
    context_switches: int,
    core_gap_avg: str = "",
    core_gap_max: str = "",
    scope_title: str = "",
) -> str:
    rows = [
        (f"Span{scope_title}", span),
        ("Tasks", f"{tasks:,}"),
        ("Segments", f"{segments:,}"),
        ("STI events", f"{sti_events:,}"),
        (f"Context switches{scope_title}", f"{context_switches:,}"),
    ]
    if core_gap_avg:
        rows.append((f"Core gap avg{scope_title}", core_gap_avg))
    if core_gap_max:
        rows.append((f"Core gap max{scope_title}", core_gap_max))
    body = "".join(
        f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in rows
    )
    return (
        '<section class="report-card">'
        "<h2>Trace Metadata</h2>"
        '<p class="detail-note">Trace-size counts. Diagnostic KPIs above summarise health.</p>'
        f'<table class="meta-table"><tbody>{body}</tbody></table></section>'
    )


def html_diagnostic_kpi_grid(kpis: Sequence[dict]) -> str:
    parts = []
    for k in kpis or []:
        parts.append(html_kpi(
            k.get("label") or "",
            k.get("value") or "—",
            hint=k.get("hint") or "",
            kind=k.get("kind") or "",
        ))
    return f'<div class="kpi-grid">{"".join(parts)}</div>' if parts else ""


def html_rank_bars(
    items: Sequence[tuple],
    *,
    fill_kind: str = "accent",
    max_v: Optional[float] = None,
) -> str:
    """Ranked HTML/CSS bar list (not canvas/SVG): ``[(label, value, display), ...]``,
    already in display order. The largest value in *items* (or ``max_v``, if
    a caller wants a scale independent of this particular slice) is 100% bar
    width. ``fill_kind`` selects the semantic color family (accent/warning/
    danger/success). Quantitative magnitude uses ``accent`` / ``--data-bar``."""
    rows = [it for it in (items or []) if it]
    if not rows:
        return ""
    peak = float(max_v) if max_v else max((float(v) for _l, v, _d in rows), default=1.0)
    peak = max(peak, 1.0)
    cls = f" {fill_kind}" if fill_kind else ""
    parts = ['<div class="rank-bars">']
    for i, (label, value, display) in enumerate(rows, start=1):
        pct = max(0.0, min(100.0, 100.0 * float(value) / peak))
        parts.append(
            f'<div class="rank-bar" title="{_esc(str(label))}: {_esc(str(display))}">'
            f'<span class="rank-bar-num">{i}</span>'
            f'<span class="rank-bar-label">{_esc(str(label))}</span>'
            f'<span class="rank-bar-track"><span class="rank-bar-fill{cls}" '
            f'style="width:{pct:.1f}%"></span></span>'
            f'<span class="rank-bar-value">{_esc(str(display))}</span>'
            "</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def html_util_bar_row(label: str, pct: float, kind: str) -> str:
    """One ``label + progress bar + %`` row, for Core Utilization / Top Tasks
    by CPU and the Performance Overview panels. *kind* is ``core`` or ``task``."""
    pct_v = max(0.0, min(100.0, float(pct)))
    lab = _esc(str(label))
    row_cls = "util-row util-row-core" if kind == "core" else "util-row util-row-task"
    pct_cls = "util-pct util-pct-core" if kind == "core" else "util-pct util-pct-task"
    return (
        f'<div class="{row_cls}" title="{lab}: {pct_v:.1f}%">'
        f'<span class="util-label">{lab}</span>'
        f'<div class="util-bar"><div class="util-bar-fill" '
        f'style="width:{pct_v:.1f}%"></div></div>'
        f'<span class="{pct_cls}">{pct_v:.1f}%</span>'
        "</div>"
    )


def html_util_section(
    title: str,
    rows: Sequence[tuple],
    kind: str,
    *,
    lead_html: str = "",
) -> str:
    """Report card of utilisation bar rows: ``[(label, pct), ...]``.

    *lead_html* is placed between the heading and the bars (the Core
    Utilization card uses it for the load-balance gauge).
    """
    if not rows:
        body = '<p class="empty">No data</p>'
    else:
        items = "".join(html_util_bar_row(label, pct, kind) for label, pct in rows)
        body = f'<div class="util-list">{items}</div>'
    return (
        f'<section class="report-card"><h2>{_esc(title)}</h2>'
        f"{lead_html}{body}</section>"
    )


def html_report_verdict(kind: str, body_html: str) -> str:
    """Theme-aware verdict banner. *body_html* is already escaped by the caller."""
    k = kind if kind in ("ok", "warn", "error") else "ok"
    return (
        f'<p class="report-verdict {k}">'
        f"<strong>Verdict:</strong> {body_html}</p>"
    )


def html_response_p99_chart(
    rows: Sequence[dict],
    *,
    format_p99,
    limit: int = 8,
) -> str:
    """Top-N horizontal P99 bars from the same response-time rows as the table."""
    items = [r for r in (rows or []) if isinstance(r, dict)]
    items.sort(key=lambda r: int(r.get("p99_ns") or 0), reverse=True)
    items = items[: max(0, int(limit))]
    if not items:
        return ""
    bars = html_rank_bars(
        [
            (
                str(r.get("task") or ""),
                float(r.get("p99_ns") or 0),
                format_p99(int(r.get("p99_ns") or 0)) if callable(format_p99)
                else str(r.get("p99_ns") or 0),
            )
            for r in items
        ],
        fill_kind="accent",
    )
    return (
        '<div class="metric-chart p99-chart">'
        '<div class="metric-chart-head"><div>'
        '<div class="metric-chart-title">Highest response P99</div>'
        '<div class="metric-chart-subtitle">Top observed tasks by P99 response time. '
        "Full percentile data remains in the table below.</div>"
        f"</div></div>{bars}</div>"
    )


def html_scheduling_balance_chart(samples: Sequence[dict]) -> str:
    """Inline SVG of Load Balance Score over time.

    *samples* is ``[{time, score, sigma}, ...]`` already formatted and in
    trace-time order. Every numeric score is plotted; Y is 0–100.
    """
    pts = []
    for s in samples or []:
        if not isinstance(s, dict):
            continue
        raw = s.get("score")
        if raw is None:
            continue
        try:
            score = float(raw)
        except (TypeError, ValueError):
            continue
        if score != score:
            continue
        score = max(0.0, min(100.0, score))
        try:
            sigma = float(s.get("sigma") or 0.0)
        except (TypeError, ValueError):
            sigma = 0.0
        pts.append((str(s.get("time") or ""), score, sigma))
    if not pts:
        return ""
    width, height = 760, 230
    pad_l, pad_r, pad_t, pad_b = 52, 20, 24, 38
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n = len(pts)

    def _x(i: int) -> float:
        return pad_l if n == 1 else pad_l + plot_w * i / (n - 1)

    def _y(score: float) -> float:
        return pad_t + plot_h * (1.0 - score / 100.0)

    low_i = min(range(n), key=lambda i: (pts[i][1], i))
    grid = []
    for mark in (0, 25, 50, 75, 100):
        gy = _y(float(mark))
        grid.append(
            f'<line class="chart-gridline" x1="{pad_l}" x2="{width - pad_r}" '
            f'y1="{gy:.1f}" y2="{gy:.1f}"/>'
            f'<text class="chart-axis-label" text-anchor="end" '
            f'x="{pad_l - 9}" y="{gy + 4:.1f}">{mark}</text>'
        )
    label_idx = [0] if n == 1 else [0, n // 2, n - 1]
    seen = set()
    axis_x = []
    for i in label_idx:
        if i in seen:
            continue
        seen.add(i)
        axis_x.append(
            f'<text class="chart-axis-label" text-anchor="middle" '
            f'x="{_x(i):.1f}" y="{height - 12}">{_esc(pts[i][0])}</text>'
        )
    poly = " ".join(f"{_x(i):.1f},{_y(score):.1f}" for i, (_t, score, _s) in enumerate(pts))
    dots = []
    for i, (time_txt, score, sigma) in enumerate(pts):
        kind = "chart-point-low" if i == low_i else "chart-point-normal"
        title = (
            f"{_esc(time_txt)} · Load balance {score:.0f} · "
            f"Util σ {sigma:.1f}%"
        )
        dots.append(
            f'<circle class="chart-point {kind}" cx="{_x(i):.1f}" '
            f'cy="{_y(score):.1f}" r="4"><title>{title}</title></circle>'
        )
    low_time, low_score, _sig = pts[low_i]
    return (
        '<div class="metric-chart scheduling-chart">'
        '<div class="metric-chart-head"><div>'
        '<div class="metric-chart-title">Load balance over time</div>'
        '<div class="metric-chart-subtitle">Lower scores indicate more uneven '
        "core utilization during that sample window.</div></div>"
        '<div class="chart-callout"><span class="chart-callout-label">Lowest</span>'
        f"<strong>{low_score:.0f}</strong>"
        f'<span class="chart-callout-note">at {_esc(low_time)}</span></div></div>'
        f'<svg class="trend-svg" xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" role="img" '
        'aria-label="Load balance score over time">'
        f"{''.join(grid)}{''.join(axis_x)}"
        f'<polyline class="chart-line" fill="none" points="{poly}"/>'
        f"{''.join(dots)}</svg></div>"
    )


def _format_measured_values(values) -> str:
    """``[{name,value,unit,sample_count?}]`` → "Name value unit (n=…)" list.

    Kept separate from finding display text so exports stay reproducible and
    localizable (Investigation Findings data model).
    """
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return ""
    parts = []
    for mv in values:
        if not isinstance(mv, dict) or "name" not in mv or "value" not in mv:
            continue
        unit = str(mv.get("unit") or "")
        chunk = f"{mv['name']} {mv['value']}{unit}".rstrip()
        if mv.get("sample_count") is not None:
            chunk += f" (n={mv['sample_count']})"
        parts.append(chunk)
    return "; ".join(parts)


def html_finding_cards(findings: Sequence[dict], scope_title: str = "") -> str:
    if not findings:
        return ""
    cards = []
    for f in findings:
        sev = str(f.get("severity") or "info")
        cls = {
            "error": "sev-error",
            "warning": "sev-warning",
            "info": "finding-info",
        }.get(sev, "finding-info")
        if f.get("id") == "load_balance_ok":
            cls = "finding-ok"
        inspect = str(f.get("inspect") or "").strip()
        href = str(f.get("inspect_href") or "").strip()
        if inspect and not href:
            href = html_inspect_href(inspect)
        inspect_html = (
            f'<div class="finding-meta"><strong>Inspect:</strong> '
            f'<a href="{_esc(href)}">{_esc(inspect)}</a></div>'
            if inspect else ""
        )
        impact = str(f.get("impact") or "").strip()
        evidence = str(f.get("evidence_text") or "").strip()
        if not evidence:
            ev = f.get("evidence")
            if isinstance(ev, list) and ev:
                evidence = "; ".join(str(x) for x in ev if x)
            elif ev:
                evidence = str(ev)
        conf = str(f.get("confidence") or "").strip()
        basis = str(f.get("comparison_basis") or "").strip()
        measured = _format_measured_values(f.get("measured_values"))
        cards.append(
            f'<article class="finding-card {cls}">'
            f'<h3>{_esc(sev.title())} · {_esc(f.get("title") or "Finding")}</h3>'
            f'<p>{_esc(f.get("text") or "")}</p>'
            + (f'<div class="finding-meta"><strong>Impact:</strong> {_esc(impact)}</div>' if impact else "")
            + (f'<div class="finding-meta"><strong>Measured:</strong> {_esc(measured)}</div>' if measured else "")
            + (f'<div class="finding-meta"><strong>Basis:</strong> {_esc(basis)}</div>' if basis else "")
            + (f'<div class="finding-meta"><strong>Evidence:</strong> {_esc(evidence)}</div>' if evidence else "")
            + inspect_html
            + (f'<div class="finding-meta"><strong>Confidence:</strong> {_esc(conf)}</div>' if conf else "")
            + "</article>"
        )
    return (
        f'<section class="report-card notes analysis-findings">'
        f"<h2>Analysis Findings{_esc(scope_title)}</h2>"
        '<p class="detail-note">Heuristic summary of load balance, CPU consumers, '
        "off-CPU gaps, thrashing, deadlines, tick health, and sync. "
        "Exported links open the matching report section; they do not jump back into BTFViewer.</p>"
        f'<div class="finding-cards">{"".join(cards)}</div></section>'
    )


_TRACE_HEALTH_STATUS_META = {
    "pass": ("finding-ok", "Pass"),
    "caution": ("sev-warning", "Caution"),
    "insufficient": ("sev-error", "Insufficient data"),
}


def html_trace_health_card(
    result: dict,
    *,
    format_ns=None,
    scope_title: str = "",
) -> str:
    """Structural Trace Health section (status + per-check detail + limitations).

    Distinct from *Trace Health (TICK)*: this reports whether the parsed event
    model is internally consistent enough to trust the derived statistics.
    Keep in sync with ``web/src/utils/statsHtmlReport.js``.
    """
    if not result:
        return ""
    status = str(result.get("status") or "pass")
    cls, label = _TRACE_HEALTH_STATUS_META.get(status, ("finding-info", status.title()))
    checks = list(result.get("checks") or [])
    n = int(result.get("issue_count") or 0)

    def _fmt(v) -> str:
        if callable(format_ns):
            try:
                return str(format_ns(int(v)))
            except Exception:
                return str(v)
        return str(v)

    rows = []
    for c in checks:
        sev = str(c.get("severity") or "info")
        sev_cls = {"error": "sev-error", "warning": "sev-warning"}.get(sev, "finding-info")
        meta_bits = []
        rng = c.get("affected_range")
        if isinstance(rng, dict) and rng.get("start") is not None:
            meta_bits.append(
                f"<strong>Range:</strong> {_esc(_fmt(rng.get('start')))} – "
                f"{_esc(_fmt(rng.get('end')))}"
            )
        ents = [str(e) for e in (c.get("affected_entities") or []) if str(e)]
        if ents:
            meta_bits.append(
                f"<strong>Affected:</strong> {_esc(', '.join(ents[:12]))}"
            )
        refs = [str(r) for r in (c.get("evidence_refs") or []) if str(r)]
        if refs:
            meta_bits.append(
                f"<strong>Evidence:</strong> {_esc('; '.join(refs))}"
            )
        lims = [str(m) for m in (c.get("metric_limitations") or []) if str(m)]
        if lims:
            meta_bits.append(
                f"<strong>Limited:</strong> {_esc(', '.join(lims))}"
            )
        meta_html = "".join(
            f'<div class="finding-meta">{bit}</div>' for bit in meta_bits
        )
        rows.append(
            f'<details class="trace-health-check {sev_cls}">'
            f"<summary>{_esc(sev.title())} · {_esc(c.get('summary') or '')}</summary>"
            f"{meta_html}</details>"
        )

    if checks:
        detail = "".join(rows)
    else:
        detail = (
            '<p class="detail-note">No structural inconsistencies found in the '
            "parsed event model under the current checks.</p>"
        )

    limitations = [str(m) for m in (result.get("metric_limitations") or []) if str(m)]
    lim_html = ""
    if limitations:
        lis = "".join(f"<li>{_esc(m)}</li>" for m in limitations)
        lim_html = (
            '<h3 class="sub">Limited metrics</h3>'
            '<p class="detail-note">These sections may show <em>Insufficient data</em> '
            "or a limitation notice instead of a value.</p>"
            f"<ul>{lis}</ul>"
        )

    return (
        '<section class="report-card notes trace-health">'
        f"<h2>Trace Health Check{_esc(scope_title)}</h2>"
        '<p class="detail-note">Deterministic structural checks on the parsed '
        "event model. Independent of AI and of <em>Trace Health (TICK)</em>, "
        "which only measures tick regularity.</p>"
        f'<p class="trace-health-status"><span class="{cls}">Status: {_esc(label)}</span>'
        f" &middot; {n} issue(s)</p>"
        f"{detail}{lim_html}</section>"
    )


def _heat_bin(value: float, max_v: float) -> int:
    """Fixed heat-0..heat-5 bin index (not a continuous color) - a Chromium /
    Qt WebEngine runtime theme switch cannot be relied on to re-evaluate
    color-mix()/computed colors, but a plain class swap always repaints."""
    if value <= 0:
        return 0
    normalized = value / max(1.0, max_v)
    return max(1, min(5, math.ceil(normalized * 5)))


def html_matrix_heatmap(
    row_labels: Sequence[str],
    col_labels: Sequence[str],
    cells: Sequence[Sequence[Optional[float]]],
    *,
    title: str,
    subtitle: str = "",
    unit: str = "%",
    width: int = 640,
    diagonal_dash: bool = False,
    tooltip_sep: str = "→",
    max_value_override: Optional[float] = None,
    extra_col: Optional[tuple] = None,
) -> str:
    """CSS-grid heat matrix with fixed heat-0..heat-5 classes (not inline
    SVG rgb() fills - see _heat_bin). A cell value of ``None`` renders as a
    dashed no-data cell, distinct from a real 0. ``diagonal_dash=True``
    treats a cell whose row/col label match (self-pair) as a dashed
    diagonal cell instead of a heat cell, e.g. Core_5 vs. Core_5.
    ``extra_col``, if given, is ``(label, values, unit)``: one additional
    trailing column rendered as a plain (non heat-colored) value per row —
    e.g. a derived per-sample "Spread" figure that shouldn't be confused
    with the matrix's own heat-scaled readings."""
    rows = list(row_labels or [])
    cols = list(col_labels or [])
    if not rows or not cols:
        return ""
    extra_label, extra_values, extra_unit = extra_col if extra_col else (None, [], "%")
    max_v = 0.0
    for line in cells or []:
        for v in line:
            if v is None:
                continue
            try:
                max_v = max(max_v, float(v))
            except (TypeError, ValueError):
                pass
    if max_value_override is not None and max_value_override > 0:
        max_v = float(max_value_override)
    else:
        max_v = max(max_v, 1.0)
    head = (
        '<div class="heat-matrix-head">'
        f'<div class="heat-matrix-title">{_esc(title)}</div>'
        + (f'<div class="heat-matrix-subtitle">{_esc(subtitle)}</div>' if subtitle else "")
        + "</div>"
    )
    col_count = len(cols) + (1 if extra_label else 0)
    parts = [
        '<div class="heat-wrap">',
        head,
        f'<div class="heat-grid" style="--col-count:{col_count}">',
        '<div class="heat-grid-corner"></div>',
    ]
    for col in cols:
        col_s = str(col)
        parts.append(
            f'<div class="heat-grid-collabel" title="{_esc(col_s)}">{_esc(col_s[:6])}</div>'
        )
    if extra_label:
        parts.append(
            f'<div class="heat-grid-collabel" title="{_esc(extra_label)}">{_esc(str(extra_label)[:8])}</div>'
        )
    for i, row in enumerate(rows):
        row_s = str(row)
        parts.append(
            f'<div class="heat-grid-rowlabel" title="{_esc(row_s)}">{_esc(row_s[:16])}</div>'
        )
        line = cells[i] if i < len(cells) else []
        for j, col in enumerate(cols):
            col_s = str(col)
            if diagonal_dash and row_s == col_s:
                parts.append(
                    f'<div class="heat-grid-cell heat-grid-diagonal" '
                    f'title="{_esc(row_s)}">—</div>'
                )
                continue
            raw = line[j] if j < len(line) else None
            if raw is None:
                parts.append(
                    '<div class="heat-grid-cell heat-grid-nodata" title="No data">—</div>'
                )
                continue
            try:
                val = float(raw)
            except (TypeError, ValueError):
                val = 0.0
            label = f"{val:.0f}{unit}" if unit == "%" else f"{val:.0f}"
            tip = f"{_esc(row_s)} {tooltip_sep} {_esc(col_s)}: {_esc(label)}"
            parts.append(
                f'<div class="heat-grid-cell heat-{_heat_bin(val, max_v)}" '
                f'title="{tip}">{_esc(label)}</div>'
            )
        if extra_label:
            extra_raw = extra_values[i] if i < len(extra_values) else None
            if extra_raw is None:
                parts.append(
                    '<div class="heat-grid-cell heat-grid-nodata" title="No data">—</div>'
                )
            else:
                extra_val = float(extra_raw)
                extra_disp = f"{extra_val:.0f}{extra_unit}" if extra_unit == "%" else f"{extra_val:.0f}"
                parts.append(
                    f'<div class="heat-grid-cell heat-grid-extra" '
                    f'title="{_esc(row_s)}: {_esc(extra_label)} {_esc(extra_disp)}">{_esc(extra_disp)}</div>'
                )
    parts.append("</div></div>")
    return "".join(parts)


def html_heat_legend() -> str:
    """0% -> 100% gradient key for the heat-0..heat-5 color scale, for a
    matrix where the reader benefits from an explicit low/high reference
    (e.g. Core Utilization Over Time)."""
    return (
        '<div class="heat-legend"><div class="heat-legend-grid">'
        "<span>0%</span><div class=\"heat-legend-bar\"></div><span>100%</span>"
        "<span>Lower</span><span></span><span>Higher</span>"
        "</div></div>"
    )


def html_percentile_bars(
    rows: Sequence[dict],
    *,
    title: str = "Response P50–P99",
    width: int = 640,
) -> str:
    items = [r for r in (rows or []) if isinstance(r, dict)][:12]
    if not items:
        return ""
    max_v = 1.0
    for r in items:
        max_v = max(max_v, float(r.get("p99_ns") or r.get("max_ns") or 0), 1.0)
    label_w = 110
    pad = 12
    row_h = 22
    header = 28
    h = header + len(items) * row_h + 10
    plot_w = max(80.0, width - label_w - pad - 80)
    parts = [
        f'<div class="heat-wrap"><svg class="pctile-svg" xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {h}" width="{width}" height="{h}" role="img" '
        f'aria-label="{_esc(title)}">',
        f'<text class="pctile-title" x="{pad}" y="16" font-size="12" font-weight="600">'
        f"{_esc(title)}</text>",
        f'<text class="pctile-sub" x="{width - pad}" y="16" text-anchor="end" font-size="11">'
        "interval = P50–P99</text>",
    ]
    for i, r in enumerate(items):
        y = header + i * row_h
        lab = _esc(str(r.get("task") or "")[:16])
        p50 = float(r.get("p50_ns") or 0)
        p95 = float(r.get("p95_ns") or 0)
        p99 = float(r.get("p99_ns") or 0)
        x0 = label_w + plot_w * p50 / max_v
        x1 = label_w + plot_w * max(p99, p50) / max_v
        x95 = label_w + plot_w * p95 / max_v
        parts.append(f'<text class="pctile-label" x="8" y="{y + 14}" font-size="11">{lab}</text>')
        parts.append(
            f'<rect class="pctile-bar" x="{x0:.1f}" y="{y + 6}" '
            f'width="{max(x1 - x0, 2):.1f}" height="8" rx="3"/>'
        )
        parts.append(
            f'<line class="pctile-marker" x1="{x95:.1f}" y1="{y + 4}" '
            f'x2="{x95:.1f}" y2="{y + 16}" stroke-width="2"/>'
        )
    parts.append("</svg></div>")
    return "".join(parts)


def html_health_bars(rows: Sequence[dict], *, width: int = 640) -> str:
    """Task Health score bars. The score is a 0-100 magnitude, so it uses the
    shared quantitative bar component (``--data-bar``) like every other bar in
    the report; the per-metric deductions stay in the trailing text and the
    table below."""
    items = [r for r in (rows or []) if isinstance(r, dict)]
    items = sorted(items, key=lambda r: int(r.get("score") or 0))[:16]
    if not items:
        return ""
    parts = ['<div class="health-bars">']
    for r in items:
        score = max(0, min(100, int(r.get("score") or 0)))
        marks = r.get("marks") or {}
        reasons = [k for k, v in marks.items() if v]
        reason = ", ".join(reasons) if reasons else "no deductions"
        task = str(r.get("task") or "")
        parts.append(
            f'<div class="pct-bar" title="{_esc(task)}: score {score}/100 · {_esc(reason)}">'
            f'<span class="lab">{_esc(task[:18])}</span>'
            f'<div class="track"><div class="fill" style="width:{score}%"></div></div>'
            f'<span>{score} · {_esc(reason)}</span></div>'
        )
    parts.append("</div>")
    del width
    return "".join(parts)


def html_tag_overview(
    samples: Sequence[dict],
    *,
    time_fmt,
    max_rows: int = 12,
) -> str:
    by_label: dict = {}
    for s in samples or []:
        if not isinstance(s, dict):
            continue
        lab = str(s.get("label") or s.get("tag") or "")
        by_label.setdefault(s.get("channel") or lab, []).append(s)
    if not by_label:
        return '<p class="empty">No tag samples in scope</p>'
    blocks = []
    for _channel, group in list(by_label.items())[:8]:
        lab = str(group[0].get("label") or group[0].get("tag") or _channel)
        group.sort(key=lambda s: s.get("time_ns", 0))
        vals = []
        for s in group:
            try:
                vals.append(s.get("value_num", float(str(s.get("value") or "0").replace(",", ""))))
            except (TypeError, ValueError):
                continue
        if not vals:
            continue
        transitions = 0
        plateau = 1
        run = 1
        for i in range(1, len(vals)):
            if vals[i] != vals[i - 1]:
                transitions += 1
                plateau = max(plateau, run)
                run = 1
            else:
                run += 1
        plateau = max(plateau, run)
        unique = len(set(vals))
        mn, mx = min(vals), max(vals)
        spark = _sparkline(vals, preferences=group[0].get("preferences"), times=[s.get("time_ns", 0) for s in group])
        extrema = sorted(group, key=lambda s: float(str(s.get("value") or 0).replace(",", "") or 0))
        shown = []
        if extrema:
            shown.append(extrema[0])
            if extrema[-1] is not extrema[0]:
                shown.append(extrema[-1])
            shown.append(group[0])
            if group[-1] not in shown:
                shown.append(group[-1])
        rows = "".join(
            f"<tr><td>{_esc(s.get('time') if not callable(time_fmt) else time_fmt(s))}</td>"
            f"<td>{_esc(s.get('value'))}</td><td>{_esc(s.get('core') or '—')}</td></tr>"
            for s in shown[:max_rows]
        )
        blocks.append(
            f"<h3 class=\"sub\">{_esc(lab)}</h3>"
            f'<p class="detail-note">{len(group)} samples · {unique} distinct values · '
            f"{transitions} transitions · longest plateau {plateau} · "
            f"min {mn:g} / max {mx:g}</p>"
            f"{spark}"
            f"<table><thead><tr><th>Time</th><th>Value</th><th>Core</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    return "".join(blocks) or '<p class="empty">No tag samples in scope</p>'


def _sparkline(vals, *, preferences=None, times=None, width=640, height=180):
    if not vals:
        return ""
    lo, hi = _tag_axis_bounds(vals, preferences)
    low = _tag_transform(lo, preferences)
    span = _tag_transform(hi, preferences) - low
    left, right, top, bottom = 100, width - 16, 16, height - 30
    times = times or list(range(len(vals)))
    t0, t1 = times[0], times[-1]
    pts = " ".join(f"{left + (right-left)*(t-t0)/(t1-t0 or 1):.2f},{bottom-(bottom-top)*(_tag_transform(v, preferences)-low)/span:.2f}" for t, v in zip(times, vals))
    ticks = []
    for i in range(5):
        y = bottom - (bottom-top)*i/4
        label = _esc(_format_tag_value(_tag_inverse(low+span*i/4, preferences)))
        ticks.append(f'<path d="M{left} {y}H{right}" stroke="#94a3b8" opacity=".3"/><text x="{left-6}" y="{y+4}" text-anchor="end" fill="currentColor" font-size="11">{label}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="Tag time series, value versus time" style="width:100%;max-width:{width}px">'
            + "".join(ticks) + f'<path d="M{left} {top}V{bottom}H{right}" fill="none" stroke="currentColor"/><polyline class="sparkline-line" fill="none" stroke-width="1.5" points="{pts}"/>'
            + f'<text x="{left}" y="{height-8}" fill="currentColor" font-size="11">{t0} ns</text><text x="{right}" y="{height-8}" text-anchor="end" fill="currentColor" font-size="11">{t1} ns</text></svg>')


_BM_TYPE_LABELS = {
    "observation": "Observation",
    "hypothesis": "Hypothesis",
    "supporting": "Supporting evidence",
    "contradicting": "Contradicting evidence",
    "verification": "Verification step",
    "conclusion": "Conclusion",
}
_FACT_TYPES = ("observation", "supporting", "verification")


def _fmt_ref(ref: dict, format_ns=None) -> str:
    kind = str(ref.get("kind") or "")
    if kind == "finding":
        return f"finding <code>{_esc(ref.get('rule_id') or ref.get('label') or '?')}</code>"
    if kind == "metric":
        return f"metric “{_esc(ref.get('metric') or ref.get('label') or '?')}”"
    if kind == "entity":
        return f"entity <code>{_esc(ref.get('entity') or ref.get('label') or '?')}</code>"
    if kind in ("range", "evidence"):
        rng = ref.get("range") or {}
        def _f(v):
            if callable(format_ns):
                try:
                    return str(format_ns(int(v)))
                except Exception:
                    return str(v)
            return str(v)
        if rng.get("start") is not None:
            return f"range {_esc(_f(rng['start']))} – {_esc(_f(rng['end']))}"
        if ref.get("time") is not None:
            return f"time {_esc(_f(ref['time']))}"
    return _esc(ref.get("label") or kind or "ref")


_EVIDENCE_KIND_LABELS = {
    "measured": "Measured", "derived": "Derived", "heuristic": "Heuristic",
    "estimate": "Simulation / estimate", "": "User note",
}
_NB_HTML_SECTION_ORDER = (
    "question", "scope", "hypotheses", "evidence", "open_checks", "conclusion",
)
NB_SECTION_HEADING = {
    "question": "Question",
    "scope": "Scope",
    "hypotheses": "Hypotheses",
    "evidence": "Evidence",
    "open_checks": "Open checks",
    "conclusion": "Conclusion",
}


def _nb_item_refs_html(refs, format_ns) -> str:
    if not refs:
        return ""
    items = "".join(f"<li>{_fmt_ref(r, format_ns)}</li>" for r in refs)
    return f'<div class="finding-meta"><strong>References:</strong><ul>{items}</ul></div>'


def html_investigation_section(
    investigation: dict,
    *,
    format_ns=None,
    broken_refs: dict = None,
    chains: "Sequence[dict]" = None,
    scope_title: str = "",
) -> str:
    """Investigation Notebook section for the HTML report — the same six
    sections, in the same order, as the Notebook UI (Question, Scope,
    Hypotheses, Evidence, Open checks, Conclusion).

    Evidence carries its provenance badge (Measured / Derived / User note …),
    source and author; stale references stay visible and flagged. Keep in sync
    with ``web/src/utils/statsHtmlReport.js:htmlInvestigationSection``.
    """
    if not investigation:
        return ""
    from .investigation_notebook import investigation_sections, load_investigation

    inv = load_investigation(investigation)
    if not (inv.get("bookmarks") or str(inv.get("conclusion") or "").strip()
            or str(inv.get("title") or "").strip()):
        return ""

    broken = broken_refs or {}
    sections = {
        s["id"]: s for s in investigation_sections(inv, broken=broken)
    }
    chains_by_id = {
        str(c.get("conclusion_id")): c for c in (chains or [])
        if isinstance(c, dict)
    }

    def _sub(label: str, body: str) -> str:
        return (
            f'<h3 class="sub">{_esc(label)}</h3>{body}' if body else ""
        )

    # 1 — Question
    q_items = sections["question"]["items"]
    question_html = (
        f'<p class="detail-note"><strong>{_esc(q_items[0]["text"])}</strong></p>'
        if q_items else ""
    )
    # 2 — Scope
    scope_bits = [_esc(it["text"]) for it in sections["scope"]["items"] if it.get("text")]
    scope_html = (
        f'<p class="detail-note">{" · ".join(scope_bits)}</p>' if scope_bits else ""
    )
    # 3 — Hypotheses
    hyp_rows = []
    for it in sections["hypotheses"]["items"]:
        status = _esc(str(it.get("status") or "open"))
        note = str(it.get("note") or "").strip()
        hyp_rows.append(
            f'<article class="finding-card"><h3>Hypothesis · {_esc(it["text"])} '
            f'<span class="finding-meta">[{status}]</span></h3>'
            + (f"<p>{_esc(note)}</p>" if note else "")
            + _nb_item_refs_html(it.get("refs"), format_ns)
            + "</article>"
        )
    hyp_html = (
        f'<div class="finding-cards">{"".join(hyp_rows)}</div>' if hyp_rows else ""
    )
    # 4 — Evidence (cards with provenance)
    ev_rows = []
    for it in sections["evidence"]["items"]:
        card = it.get("card") or {}
        kind = _EVIDENCE_KIND_LABELS.get(str(it.get("kind") or ""), "User note")
        source = _esc(str(card.get("source") or ""))
        author = str(card.get("author") or "")
        author_tag = " · AI" if author == "ai" else (" · BTFViewer" if author == "btfviewer" else "")
        note = str(it.get("note") or "").strip()
        stale_html = (
            '<div class="finding-meta sev-warning"><strong>Stale:</strong> '
            "reference no longer resolves against the current trace.</div>"
            if it.get("stale") else ""
        )
        ev_rows.append(
            f'<article class="finding-card"><h3>{_esc(it.get("role") or "evidence").title()} · '
            f'{_esc(it["text"])} <span class="finding-meta">[{_esc(kind)}'
            + (f" · {source}" if source else "") + f"{author_tag}]</span></h3>"
            + (f"<p>{_esc(note)}</p>" if note else "")
            + _nb_item_refs_html(it.get("refs"), format_ns)
            + stale_html + "</article>"
        )
    ev_html = (
        f'<div class="finding-cards">{"".join(ev_rows)}</div>' if ev_rows else ""
    )
    # 5 — Open checks
    check_lis = []
    for it in sections["open_checks"]["items"]:
        src = str(it.get("source") or "")
        prefix = "Verify: " if src == "verification" else ""
        check_lis.append(f"<li>{_esc(prefix + str(it.get('text') or ''))}</li>")
    checks_html = f"<ul>{''.join(check_lis)}</ul>" if check_lis else ""
    # 6 — Conclusion (+ grounding chains)
    concl_rows = []
    for it in sections["conclusion"]["items"]:
        if it.get("kind") == "verification_state":
            concl_rows.append(
                f'<div class="finding-meta">{_esc(it.get("text") or "")}</div>'
            )
            continue
        bid = str(it.get("bookmark_id") or "")
        chain = chains_by_id.get(bid) if bid else None
        chain_html = ""
        if chain and chain.get("evidence"):
            lis = "".join(
                f"<li>{_esc(_BM_TYPE_LABELS.get(e.get('type'), 'Bookmark'))}: "
                f"{_esc(e.get('title') or e.get('id'))}</li>"
                for e in chain["evidence"]
            )
            chain_html = (
                f'<div class="finding-meta"><strong>Backed by:</strong><ul>{lis}</ul></div>'
            )
        elif chain is not None:
            chain_html = (
                '<div class="finding-meta sev-warning"><strong>Not grounded:</strong> '
                "no linked evidence.</div>"
            )
        concl_rows.append(
            f'<article class="finding-card finding-ok"><h3>Conclusion'
            + (f" · {_esc(it['text'])}" if it.get("bookmark_id") else "")
            + "</h3>"
            + (f"<p>{_esc(it['text'])}</p>" if not it.get("bookmark_id") else "")
            + chain_html + "</article>"
        )
    concl_html = (
        f'<div class="finding-cards">{"".join(concl_rows)}</div>' if concl_rows else ""
    )

    stale_banner = ""
    if broken.get("stale_trace"):
        stale_banner = (
            '<p class="detail-note sev-warning">The source trace changed since '
            "these notes were written — references may not line up.</p>"
        )

    body_by_id = {
        "question": question_html,
        "scope": scope_html,
        "hypotheses": hyp_html,
        "evidence": ev_html,
        "open_checks": checks_html,
        "conclusion": concl_html,
    }
    blocks = "".join(
        _sub(NB_SECTION_HEADING[sid], body_by_id[sid])
        for sid in _NB_HTML_SECTION_ORDER
    )
    heading = f"Investigation{_esc(scope_title)}"
    return (
        '<section class="report-card notes investigation">'
        f"<h2>{heading}</h2>"
        + '<p class="detail-note">The Notebook, in the same six sections as the '
        "app. Evidence keeps its provenance; notes never change measured "
        "values.</p>"
        + stale_banner + blocks
        + "</section>"
    )


def html_investigate_anomalies(
    *,
    anomalies_table: str,
    worst_table: str,
    patterns_table: str,
    crit_path_table: str,
    crit_note: str,
    scope_title: str = "",
) -> str:
    return (
        f'<section class="report-card"><h2>Investigate Anomalies{_esc(scope_title)}</h2>'
        '<p class="detail-note">Timeline anomalies, longest events, repeating kinds, '
        "and the longest heuristic ready-to-completion windows. "
        "Critical Path components can overlap; they are not additive parts of Duration.</p>"
        '<div class="report-tabs">'
        '<div class="tab-bar">'
        '<button type="button" class="tab-btn" data-tab="anomalies">Timeline Anomalies</button>'
        '<button type="button" class="tab-btn" data-tab="worst">Worst Events</button>'
        '<button type="button" class="tab-btn" data-tab="patterns">Recurring Patterns</button>'
        '<button type="button" class="tab-btn" data-tab="crit">Critical Path</button>'
        "</div>"
        f'<div data-panel="anomalies">{anomalies_table}</div>'
        f'<div data-panel="worst">{worst_table}</div>'
        f'<div data-panel="patterns">{patterns_table}</div>'
        f'<div data-panel="crit">{crit_note}{crit_path_table}</div>'
        "</div></section>"
    )


def html_glossary(*, range_note: str = "") -> str:
    note = (range_note or "").strip()
    if note.startswith("<li>") and note.endswith("</li>"):
        note = note[4:-5].strip()
    items = [
        note,
        "<strong>Execution Time Per Slice:</strong> Duration of each continuous task run between two context switches.",
        "<strong>Highest CPU consumers</strong> are tasks with the largest share of active CPU time. "
        "They are not automatically WCET candidates. Largest execution-time maxima live in Execution Time Per Slice.",
        "<strong>Inter-Arrival Time:</strong> Time between consecutive activations of the same task (slice start to next slice start).",
        "<strong>Off-CPU Time (Blocking Time):</strong> Gap between the end of one slice and the start of the next for the same task. "
        "It may include preemption, suspension, periodic waiting, or scheduling delay — not necessarily resource blocking. "
        "It is not end-to-end response time.",
        "<strong>CPU% (task):</strong> Share of total non-IDLE/TICK <em>active CPU time</em> in scope, not wall-clock span and not total multicore capacity.",
        "<strong>Core Utilization:</strong> Non-IDLE/TICK active time on that core divided by the scoped wall-clock span (one-core capacity = 100%).",
        "<strong>Load Balance Score:</strong> 100% × (1 − Gini of core utilization). "
        "100 = evenly distributed utilization; 0 = highly uneven. Even overload or even idle can still score high.",
        "<strong>Preemption Chain Analysis:</strong> For each off-CPU gap of a victim task, which task ran on the same core during that gap.",
        "<strong>Priority Inheritance:</strong> Tasks boosted above base priority when <code>create pri:N</code> and <code>set_priority</code> STI events are present.",
        "<strong>Mutex / Semaphore:</strong> Paired <code>take</code>/<code>give</code> STI events by object pointer.",
        "<strong>Interval Analysis:</strong> Paired <code>interval_start</code> / <code>interval_stop</code> STI events by id.",
        "<strong>Tag Analysis:</strong> Numeric samples from tag STI channels. Repeated identical values are summarised as a time series, not dumped row-by-row.",
        "<strong>Task × Core:</strong> Per-task execution share of the scoped span on each core.",
        "<strong>Task Health:</strong> Heuristic 0–100 score from measured statistics, not an AI probability.",
        "<strong>Response Time:</strong> Heuristic ready→completion from adjacent slices. Not an explicit BTF release/completion pair.",
        "<strong>Critical Path:</strong> Longest heuristic response windows. Exec is own on-CPU time; Off-CPU is Duration − Exec. "
        "Preempt, Wait, and Migration overlap and are not a stacked split of Duration.",
        "<strong>Period / Jitter:</strong> Median inter-arrival as expected period, with RMS jitter, CV, missed (&gt; 1.5×) and extra (&lt; 0.5×) activations.",
        "<strong>Min:</strong> Smallest observed sample in scope. It does not prove zero system load.",
        "<strong>Max:</strong> Largest observed sample in scope. It is an observed peak, not a guaranteed WCET.",
        "<strong>Average (Mean):</strong> Arithmetic mean; outliers can skew it.",
        "<strong>TrimMean(5%):</strong> Mean after dropping the fastest and slowest 5%.",
        "<strong>Jitter:</strong> Observed spread (Max − Min) for samples in scope.",
        "<strong>σ:</strong> Population standard deviation of samples in scope.",
        "<strong>P50 (Median):</strong> Half the samples are at or below this value.",
        "<strong>P95 / P99:</strong> Percentile of the observed distribution. Usefulness depends on the deadline or acceptance criterion; P95 is not universally the best user-experience metric for real-time systems.",
    ]
    lis = "".join(f"<li>{item}</li>" for item in items if item)
    return (
        '<section class="report-card notes"><h2>Statistics Notes</h2>'
        '<p class="detail-note">Glossary of metric definitions used in this report.</p>'
        f"<ul>{lis}</ul></section>"
    )
