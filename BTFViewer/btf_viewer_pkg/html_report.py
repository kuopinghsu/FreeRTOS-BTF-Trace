"""Shared HTML report chrome for BTFViewer exports (Desktop).

Keep in sync with ``web/src/utils/htmlReport.js``.
"""
from __future__ import annotations

import html
import re
from typing import Optional

from .config import _APP_ICON_SVG, _APP_VERSION

# Public aliases for exporters / tests.
APP_VERSION = _APP_VERSION
APP_ICON_SVG = _APP_ICON_SVG
PRODUCT_NAME = "BTFViewer"
PRODUCT_TAGLINE = "Portable BTF trace analysis and evidence reports"


def app_icon_svg_markup(size: int = 48) -> str:
    """Embedded app icon SVG scaled for HTML headers (no external file)."""
    sz = max(16, int(size))
    out = APP_ICON_SVG
    out = re.sub(r'\bwidth="\d+"', f'width="{sz}"', out, count=1)
    out = re.sub(r'\bheight="\d+"', f'height="{sz}"', out, count=1)
    return out


_BTF_HTML_REPORT_CSS = """
:root {
  color-scheme: light dark;
  --bg: #e9edf3;
  --bg-elev: #f3f6fa;
  --paper: #ffffff;
  --paper-2: #f1f5fb;
  --ink: #182230;
  --muted: #5f6f82;
  --line: #d9e0ea;
  --line-strong: #c3cee0;
  --header: #16324f;
  --header-2: #21496f;
  --accent: #2a6fb2;
  --accent-soft: #eaf2ff;
  --accent-2: #0f766e;
  --success: #1f6b45;
  --success-soft: #d9f0e3;
  --warning: #8a4b00;
  --warning-soft: #fce8c8;
  --danger: #b3261e;
  --danger-soft: #fdecec;
  --violet: #7357c7;
  --stripe: #f7f9fc;
  --user-bar: #5b9bd5;
  --asst-bar: #3d9a72;
  --user-bg: #eef5fc;
  --asst-bg: #eef7f2;
}
html[data-theme="dark"] {
  --bg: #14181e;
  --bg-elev: #181d24;
  --paper: #1c2128;
  --paper-2: #20262e;
  --ink: #d6dde6;
  --muted: #9aa7b4;
  --line: #2d333b;
  --line-strong: #3a4149;
  --header: #16324f;
  --header-2: #21496f;
  --accent: #6cb0e6;
  --accent-soft: #1d3348;
  --accent-2: #4ec6bb;
  --success: #57c191;
  --success-soft: #123024;
  --warning: #f0b35c;
  --warning-soft: #302410;
  --danger: #ff8585;
  --danger-soft: #33191a;
  --violet: #b3a0ff;
  --stripe: #171c22;
  --user-bg: #182634;
  --asst-bg: #17251d;
}
@media (prefers-color-scheme: dark) {
  html:not([data-theme="light"]) {
    --bg: #14181e;
    --bg-elev: #181d24;
    --paper: #1c2128;
    --paper-2: #20262e;
    --ink: #d6dde6;
    --muted: #9aa7b4;
    --line: #2d333b;
    --line-strong: #3a4149;
    --header: #16324f;
    --header-2: #21496f;
    --accent: #6cb0e6;
    --accent-soft: #1d3348;
    --accent-2: #4ec6bb;
    --success: #57c191;
    --success-soft: #123024;
    --warning: #f0b35c;
    --warning-soft: #302410;
    --danger: #ff8585;
    --danger-soft: #33191a;
    --violet: #b3a0ff;
    --stripe: #171c22;
    --user-bg: #182634;
    --asst-bg: #17251d;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 28px 20px 40px;
  font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  color: var(--ink);
  background: radial-gradient(circle at top right, #f6f8fb 0%, var(--bg) 52%, #dde4ee 100%);
  font-size: 15px;
  line-height: 1.5;
}
.report { max-width: 960px; margin: 0 auto; }
.report-head {
  display: flex;
  align-items: center;
  gap: 16px;
  background: linear-gradient(135deg, var(--header) 0%, #21496f 100%);
  color: #f3f7fd;
  border-radius: 14px;
  padding: 18px 22px;
  box-shadow: 0 10px 28px rgba(17, 44, 69, 0.24);
  margin-bottom: 18px;
}
.report-head .brand-icon {
  flex: 0 0 auto;
  width: 48px;
  height: 48px;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
  background: #1c3a6e;
}
.report-head .brand-icon svg { display: block; width: 48px; height: 48px; }
.report-head .brand-text { min-width: 0; flex: 1; }
.report-head .product {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #cfe1f7;
  margin: 0 0 2px;
}
.report-head h1 {
  margin: 0;
  font-size: 22px;
  letter-spacing: 0.2px;
  font-weight: 700;
  color: #f3f7fd;
}
.report-head .sub {
  margin-top: 4px;
  color: #cfe1f7;
  font-size: 12px;
}
.report-card {
  margin: 14px 0;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 14px 16px 16px;
  box-shadow: 0 2px 10px rgba(30, 60, 90, 0.06);
}
.report-card > h2:first-child { margin-top: 0; }
h2 {
  margin: 0 0 10px;
  color: #123355;
  font-size: 16px;
  font-weight: 650;
}
.meta-table, .gui-table, .ann-table {
  border-collapse: collapse;
  width: 100%;
  margin: 0;
}
.meta-table th, .meta-table td,
.gui-table th, .gui-table td,
.ann-table th, .ann-table td {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}
.meta-table th, .gui-table th, .ann-table th {
  color: var(--muted);
  font-weight: 600;
  width: 22%;
}
pre {
  background: var(--paper-2);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 10px 12px;
  overflow: auto;
  white-space: pre-wrap;
  margin: 0;
  color: var(--ink);
}
a { color: var(--accent); }
.msg {
  padding: 14px 0;
  border-top: 1px solid var(--line);
}
.msg:first-of-type { border-top: none; padding-top: 0; }
.msg h3 {
  font-size: 12px;
  font-weight: 700;
  margin: 0 0 6px;
  color: var(--muted);
}
.msg.user h3 { color: #2a6fb2; }
.msg.assistant h3 { color: #2f7a58; }
.msg.evidence h3 { color: #5a6a7c; }
.msg .body {
  padding: 10px 12px;
  border-left: 3px solid var(--user-bar);
  background: var(--user-bg);
  border-radius: 0 8px 8px 0;
}
.msg.assistant .body {
  border-left-color: var(--asst-bar);
  background: var(--asst-bg);
}
.msg.evidence .body {
  border-left-color: #8a96a8;
  background: #f4f6f9;
}
.ai-ev-panel-toggle {
  display: inline-block;
  margin-left: 4px;
  padding: 1px 7px;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: var(--paper);
  color: var(--muted);
  font-size: 10px;
  font-weight: 600;
  line-height: 1.3;
  cursor: pointer;
  vertical-align: middle;
}
.ai-ev-panel-toggle:hover {
  color: var(--accent);
  border-color: var(--accent);
}
details.ai-ev-fold {
  border-radius: 6px;
  padding: 2px 8px 4px;
  border: 1px solid var(--line);
  background: var(--paper);
}
details.ai-ev-fold-l1,
details.ai-ev-fold:not(.ai-ev-fold-l2) {
  margin: 8px 0 4px;
}
details.ai-ev-fold-l1 > summary,
details.ai-ev-fold:not(.ai-ev-fold-l2) > summary {
  cursor: pointer;
  font-weight: 600;
  font-size: 12px;
  color: var(--ink);
  padding: 5px 0;
  list-style: none;
}
details.ai-ev-fold-l2 {
  margin: 4px 0 4px 10px;
  border-color: var(--line);
  border-radius: 4px;
  padding: 1px 6px 3px;
  background: var(--paper-2);
}
details.ai-ev-fold-l2 > summary {
  cursor: pointer;
  font-weight: 600;
  font-size: 11px;
  color: var(--muted);
  padding: 3px 0;
  list-style: none;
}
details.ai-ev-fold > summary::-webkit-details-marker { display: none; }
details.ai-ev-fold > summary::before {
  content: '▸ ';
  display: inline-block;
}
details.ai-ev-fold[open] > summary::before { content: '▾ '; }
.ai-ev-fold-body {
  padding: 2px 0 6px;
  font-size: 12px;
  line-height: 1.45;
}
.ai-ev-fold-body details.ai-ev-fold-l2 .ai-ev-fold-body { font-size: 11px; }
.msg .body pre,
pre.code {
  background: #1a2230;
  border: 1px solid #3a4658;
  color: #dbe2ea;
  border-radius: 4px;
  padding: 8px;
  overflow: auto;
}
.msg .body code {
  font-family: Menlo, Consolas, Monaco, "Courier New", monospace;
  font-size: 12px;
}
.msg .body blockquote {
  margin: 6px 0;
  padding: 4px 10px;
  border-left: 3px solid var(--accent);
  color: #4a5d73;
}
table.ai-md-table {
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 12px;
  width: 100%;
}
table.ai-md-table th, table.ai-md-table td {
  border: 1px solid var(--line);
  padding: 4px 8px;
}
table.ai-md-table th {
  background: var(--paper-2);
  color: var(--ink);
}
table.ai-md-table td {
  background: var(--paper);
  color: var(--ink);
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--header);
  font-size: 12px;
  font-weight: 650;
  margin-right: 6px;
}
.badge-status { background: var(--accent-soft); }
.badge-ok { background: var(--success-soft); color: var(--success); }
.badge-warn { background: var(--warning-soft); color: var(--warning); }
.warn-banner {
  background: var(--warning-soft);
  border: 1px solid var(--warning);
  border-radius: 8px;
  padding: 8px 10px;
}
.report-scope { color: var(--muted); font-size: 13px; }
.status-row { margin: 0 0 8px; }
details.report-appendix {
  margin: 8px 0;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 6px 10px;
  background: var(--paper-2);
}
details.report-appendix > summary {
  cursor: pointer;
  font-weight: 650;
  color: var(--ink);
}
.appendix-body { margin-top: 8px; }
.export-note { color: var(--muted); font-size: 12px; margin-top: 12px; }
@media print {
  body { background: #fff; padding: 0; }
  .report { max-width: none; }
  .report-head { box-shadow: none; }
  details.report-appendix,
  details.report-card,
  .report-card,
  table,
  tr { break-inside: avoid; }
  details.report-card:not([open]) > *:not(summary) { display: revert; }
  details[open] > summary { list-style: none; }
  /* Interactive chrome has no place on paper. The sortable class sits on the
     <th> itself, so only its affordance is dropped — never the header cell. */
  .table-toolbar, .table-pager, .report-toc [data-toc],
  .ai-ev-panel-toggle { display: none !important; }
  .sortable { cursor: default; }
  thead th.sortable:hover { background: var(--paper-2); }
  .table-scroll { overflow: visible !important; }
  a { color: inherit; text-decoration: none; }
}
.report-foot {
  margin-top: 18px;
  padding-top: 10px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 11px;
  text-align: center;
}
.theme-toggle {
  flex: 0 0 auto;
  margin-left: auto;
  align-self: flex-start;
  background: rgba(255, 255, 255, 0.12);
  color: #f3f7fd;
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
  white-space: nowrap;
}
.theme-toggle:hover { background: rgba(255, 255, 255, 0.22); }
.report-command-bar {
  position: sticky; top: 10px; z-index: 20;
  display: flex; align-items: center; gap: 8px;
  margin: 0 0 14px; padding: 9px 10px;
  border: 1px solid var(--line); border-radius: 12px;
  background: var(--paper);
  background: color-mix(in srgb, var(--paper) 94%, transparent);
  box-shadow: 0 8px 24px rgba(15, 35, 60, 0.12);
  backdrop-filter: blur(12px);
}
.report-search-wrap { position: relative; flex: 1 1 260px; min-width: 160px; }
.report-search-icon {
  position: absolute; left: 10px; top: 50%; transform: translateY(-50%);
  color: var(--muted); pointer-events: none;
}
.report-search {
  width: 100%; min-height: 36px; padding: 7px 32px;
  border: 1px solid var(--line); border-radius: 9px;
  background: var(--paper-2); color: var(--ink); font: inherit; font-size: 13px;
}
.report-search:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 1px; border-color: var(--accent);
}
.report-search-key {
  position: absolute; right: 9px; top: 50%; transform: translateY(-50%);
  padding: 1px 5px; border: 1px solid var(--line); border-radius: 4px;
  color: var(--muted); background: var(--paper); font-size: 10px;
}
.report-match-count { color: var(--muted); font-size: 11px; white-space: nowrap; }
.report-tool-btn {
  min-height: 34px; padding: 6px 10px; border: 1px solid var(--line);
  border-radius: 8px; background: var(--paper); color: var(--ink);
  font: inherit; font-size: 12px; cursor: pointer; white-space: nowrap;
}
.report-tool-btn:hover { border-color: var(--accent); color: var(--accent); }
.section-link {
  float: right; margin: -2px 0 0 8px; padding: 3px 7px;
  border: 1px solid transparent; border-radius: 6px; background: transparent;
  color: var(--muted); font: inherit; font-size: 11px; cursor: pointer;
}
.section-link:hover { color: var(--accent); border-color: var(--line); background: var(--paper-2); }
.report-empty-results {
  margin: 14px 0; padding: 24px; border: 1px dashed var(--line-strong);
  border-radius: 14px; color: var(--muted); background: var(--paper); text-align: center;
}
.back-to-top {
  position: fixed; right: 22px; bottom: 22px; z-index: 30;
  width: 42px; height: 42px; border: 1px solid var(--line); border-radius: 50%;
  background: var(--paper); color: var(--accent); font-size: 18px; cursor: pointer;
  box-shadow: 0 8px 24px rgba(15, 35, 60, 0.18);
  opacity: 0; transform: translateY(8px); pointer-events: none;
  transition: opacity 0.16s ease, transform 0.16s ease;
}
.back-to-top.visible { opacity: 1; transform: none; pointer-events: auto; }
.scroll-progress {
  position: fixed; inset: 0 0 auto; z-index: 100; height: 3px;
  background: transparent; pointer-events: none;
}
.scroll-progress-fill {
  display: block; width: 100%; height: 100%; background: var(--accent);
  transform: scaleX(0); transform-origin: left center; transition: transform 0.08s linear;
}
.report-card.motion-ready {
  opacity: 0; transform: translateY(12px);
  transition: opacity 0.38s ease, transform 0.38s ease, box-shadow 0.2s ease;
}
.report-card.motion-ready.motion-in { opacity: 1; transform: none; }
details.report-card[open] > :not(summary) { animation: report-content-in 0.24s ease both; }
.report-toc a.active {
  color: var(--ink); font-weight: 700; text-decoration: none;
}
.report-toc a.active::after { content: " •"; color: var(--accent); }
.metric-animate { transform-origin: left center; transform: scaleX(0); }
.metric-animate.metric-in { animation: report-bar-in 0.65s cubic-bezier(.2,.8,.2,1) both; }
.chart-line.metric-animate { transform: none; stroke-dasharray: 1400; stroke-dashoffset: 1400; }
.chart-line.metric-animate.metric-in { animation: report-line-in 0.9s ease-out both; }
.chart-point.metric-animate, .pctile-bar.metric-animate { transform: none; opacity: 0; }
.chart-point.metric-animate.metric-in, .pctile-bar.metric-animate.metric-in {
  animation: report-point-in 0.35s ease-out both;
}
.kpi.kpi-animate { opacity: 0; transform: translateY(6px); }
.kpi.kpi-animate.kpi-in { animation: report-kpi-in 0.5s cubic-bezier(.2,.8,.2,1) both; }
.auto-chart-grid { display: grid; gap: 12px; margin: 10px 0 16px; }
.auto-chart-grid.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.auto-chart {
  min-width: 0; padding: 12px; border: 1px solid var(--line); border-radius: 12px;
  background: var(--paper-2); overflow: hidden;
}
.auto-chart-title { margin: 0 0 2px; color: var(--ink); font-size: 13px; font-weight: 700; }
.auto-chart-subtitle { margin: 0 0 10px; color: var(--muted); font-size: 10px; }
.auto-line-svg { display: block; width: 100%; height: auto; overflow: visible; }
.auto-grid-line { stroke: var(--chart-grid, var(--line)); stroke-width: 1; }
.auto-axis-label { fill: var(--muted); font-size: 9px; }
.auto-series { fill: none; stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; }
.auto-series-0 { stroke: var(--accent); }
.auto-series-1 { stroke: var(--success); }
.auto-series-2 { stroke: var(--warning); }
.auto-series-3 { stroke: var(--danger); }
.auto-series-4 { stroke: var(--violet); }
.auto-dot { stroke: var(--paper); stroke-width: 1.5; }
.auto-dot-0 { fill: var(--accent); }.auto-dot-1 { fill: var(--success); }
.auto-dot-2 { fill: var(--warning); }.auto-dot-3 { fill: var(--danger); }
.auto-dot-4 { fill: var(--violet); }
.auto-chart-legend { display: flex; flex-wrap: wrap; gap: 6px 12px; margin-top: 7px; }
.auto-legend-item { display: inline-flex; align-items: center; gap: 5px; color: var(--muted); font-size: 10px; }
.auto-swatch { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); }
.auto-swatch-1 { background: var(--success); }.auto-swatch-2 { background: var(--warning); }
.auto-swatch-3 { background: var(--danger); }.auto-swatch-4 { background: var(--violet); }
.auto-donut-layout { display: flex; align-items: center; gap: 16px; min-height: 150px; }
.auto-donut {
  flex: 0 0 136px; width: 136px; height: 136px; border-radius: 50%;
  position: relative; transform: rotate(-90deg) scale(.82); opacity: 0;
  box-shadow: inset 0 0 0 1px var(--line);
}
.auto-donut::after {
  content: ""; position: absolute; inset: 30px; border-radius: 50%;
  background: var(--paper-2); box-shadow: 0 0 0 1px var(--line);
}
.auto-donut-legend { min-width: 0; display: grid; gap: 4px; flex: 1; }
.auto-donut-row { display: grid; grid-template-columns: 9px minmax(0,1fr) auto; gap: 6px; align-items: center; font-size: 10px; }
.auto-donut-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); }
.auto-donut-value { color: var(--ink); font-variant-numeric: tabular-nums; }
.auto-chart.chart-active .auto-series { stroke-dasharray: 1200; animation: auto-line-draw .85s ease-out both; }
.auto-chart.chart-active .auto-dot { animation: auto-dot-in .3s ease-out both; }
.auto-chart.chart-active .auto-donut { animation: auto-donut-in .65s cubic-bezier(.2,.9,.2,1) both; }
.compare-chart-active .paired-fill,
.compare-chart-active .delta-fill,
.compare-chart-active .cmp-chart-bar {
  transform-box: fill-box; transform-origin: left center;
  animation: compare-bar-in .72s cubic-bezier(.2,.9,.2,1) both;
}
.compare-chart-active .paired-row:nth-child(2n) .paired-fill,
.compare-chart-active .delta-row:nth-child(2n) .delta-fill { animation-delay: 70ms; }
.compare-chart-active .compare-chart svg { animation: compare-chart-rise .5s ease-out both; }
.report-card.compare-chart-active .compare-verdict-banner { animation: compare-verdict-in .45s cubic-bezier(.2,.9,.2,1) both; }
@keyframes auto-line-draw { from { stroke-dashoffset: 1200; } to { stroke-dashoffset: 0; } }
@keyframes auto-dot-in { from { opacity: 0; } to { opacity: 1; } }
@keyframes auto-donut-in { to { opacity: 1; transform: rotate(-90deg) scale(1); } }
@keyframes compare-bar-in { from { transform: scaleX(0); opacity: .35; } to { transform: scaleX(1); opacity: 1; } }
@keyframes compare-chart-rise { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
@keyframes compare-verdict-in { from { opacity: 0; transform: translateY(-6px) scale(.98); } to { opacity: 1; transform: none; } }
@keyframes report-content-in {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: none; }
}
@keyframes report-bar-in { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes report-line-in { to { stroke-dashoffset: 0; } }
@keyframes report-point-in { from { opacity: 0; } to { opacity: 1; } }
@keyframes report-kpi-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
@media (max-width: 700px) {
  .report-command-bar { position: static; flex-wrap: wrap; }
  .report-search-wrap { flex-basis: 100%; }
  .report-match-count { margin-right: auto; }
  .back-to-top { right: 14px; bottom: 14px; }
  .auto-chart-grid.two { grid-template-columns: 1fr; }
  .auto-donut-layout { align-items: flex-start; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; animation: none !important; transition: none !important; }
  .report-card.motion-ready { opacity: 1; transform: none; }
  .metric-animate { transform: none; opacity: 1; stroke-dashoffset: 0; }
  .kpi-animate { opacity: 1; transform: none; }
  .auto-chart .auto-series { stroke-dashoffset: 0; }
  .auto-chart .auto-dot { opacity: 1; }
  .auto-chart .auto-donut { opacity: 1; transform: rotate(-90deg) scale(1); }
}
@media print {
  .theme-toggle, .report-command-bar, .section-link, .back-to-top, .scroll-progress,
  .report-empty-results { display: none !important; }
}
html[data-theme="dark"] body { background: #12161b; }
html[data-theme="dark"] h2 { color: #cfe1f7; }
html[data-theme="dark"] pre { background: #12161b; border-color: var(--line); color: var(--ink); }
html[data-theme="dark"] .msg.user h3 { color: #6cb0e6; }
html[data-theme="dark"] .msg.assistant h3 { color: #57c191; }
html[data-theme="dark"] .msg.evidence h3 { color: #9aa7b4; }
html[data-theme="dark"] .msg.evidence .body { background: #171b21; border-left-color: #5a6a7c; }
html[data-theme="dark"] .ai-ev-panel-toggle { background: var(--paper); color: var(--muted); }
html[data-theme="dark"] details.ai-ev-fold { background: var(--paper); }
html[data-theme="dark"] details.ai-ev-fold-l1 > summary,
html[data-theme="dark"] details.ai-ev-fold:not(.ai-ev-fold-l2) > summary { color: #b6c2cf; }
html[data-theme="dark"] details.ai-ev-fold-l2 { background: #171b21; border-color: var(--line); }
html[data-theme="dark"] details.ai-ev-fold-l2 > summary { color: var(--muted); }
@media (prefers-color-scheme: dark) {
  html:not([data-theme="light"]) body { background: #12161b; }
  html:not([data-theme="light"]) h2 { color: #cfe1f7; }
  html:not([data-theme="light"]) pre { background: #12161b; border-color: var(--line); color: var(--ink); }
  html:not([data-theme="light"]) .msg.user h3 { color: #6cb0e6; }
  html:not([data-theme="light"]) .msg.assistant h3 { color: #57c191; }
  html:not([data-theme="light"]) .msg.evidence h3 { color: #9aa7b4; }
  html:not([data-theme="light"]) .msg.evidence .body { background: #171b21; border-left-color: #5a6a7c; }
  html:not([data-theme="light"]) .ai-ev-panel-toggle { background: var(--paper); color: var(--muted); }
  html:not([data-theme="light"]) details.ai-ev-fold { background: var(--paper); }
  html:not([data-theme="light"]) details.ai-ev-fold-l1 > summary,
  html:not([data-theme="light"]) details.ai-ev-fold:not(.ai-ev-fold-l2) > summary { color: #b6c2cf; }
  html:not([data-theme="light"]) details.ai-ev-fold-l2 { background: #171b21; border-color: var(--line); }
  html:not([data-theme="light"]) details.ai-ev-fold-l2 > summary { color: var(--muted); }
}
""".strip()


REPORT_THEME_CSS = """
:root {
  --bg: #F8FAFC;
  --bg-elev: #F1F5F9;
  --paper: #FFFFFF;
  --paper-2: #F1F5F9;
  --surface: #FFFFFF;
  --ink: #0F172A;
  --muted: #475569;
  --line: #E2E8F0;
  --line-strong: #E2E8F0;
  --stripe: #F8FAFC;
  --accent: #0284C7;
  --accent-2: #0284C7;
  --accent-soft: #E0F2FE;
  --success: #10B981;
  --success-soft: #D1FAE5;
  --warning: #D97706;
  --warning-soft: #FEF3C7;
  --danger: #E11D48;
  --danger-soft: #FFE4E6;
  --violet: #0284C7;
  --ok-border: #6EE7B7;
  --warn-border: #FBBF24;
  --error-border: #FB7185;
  --accent-border: #7DD3FC;
  --canvas-top: #FFFFFF;
  --canvas-edge: #E4EAF2;
  --bar-track-bg: #F1F5F9;
  --bar-track-border: #E2E8F0;
  --data-bar: #0284C7;
  --data-bar-soft: #BAE6FD;
  --data-0-bg: #F8FAFC; --data-0-ink: #64748B;
  --data-1-bg: #E0F2FE; --data-1-ink: #075985;
  --data-2-bg: #BAE6FD; --data-2-ink: #075985;
  --data-3-bg: #7DD3FC; --data-3-ink: #0C4A6E;
  --data-4-bg: #38BDF8; --data-4-ink: #082F49;
  --data-5-bg: #0284C7; --data-5-ink: #FFFFFF;
  --matrix-bg: #FFFFFF;
  --matrix-border: #E2E8F0;
  --matrix-label: #475569;
  --matrix-diag-bg: #F1F5F9;
  --matrix-diag-ink: #64748B;
  --chart-grid: #E2E8F0;
  --chart-axis: #475569;
  --series-a: #7DD3FC;
  --series-a-text: #075985;
  --series-b: #0284C7;
  --series-b-text: #075985;
  --row-hover-bg: #F1F5F9;
  --row-hover-edge: #CBD5E1;
  /* Theme-independent bar geometry, shared by every quantitative visual. */
  --std-bar-h: 10px;
  --std-bar-r: 5px;
}
html[data-theme="dark"] {
  --bg: #0B0F19;
  --bg-elev: #101827;
  --paper: #151D2E;
  --paper-2: #101827;
  --surface: #151D2E;
  --ink: #F1F5F9;
  --muted: #94A3B8;
  --line: #1E293B;
  --line-strong: #1E293B;
  --stripe: #111827;
  --accent: #38BDF8;
  --accent-2: #38BDF8;
  --accent-soft: #102A3A;
  --success: #34D399;
  --success-soft: #123024;
  --warning: #FB923C;
  --warning-soft: #332417;
  --danger: #FB7185;
  --danger-soft: #3F1D29;
  --violet: #38BDF8;
  --ok-border: #065F46;
  --warn-border: #9A3412;
  --error-border: #9F1239;
  --accent-border: #15506C;
  --canvas-top: #151D2E;
  --canvas-edge: #0D1218;
  --bar-track-bg: #101827;
  --bar-track-border: #1E293B;
  --data-bar: #38BDF8;
  --data-bar-soft: #15506C;
  --data-0-bg: #111827; --data-0-ink: #94A3B8;
  --data-1-bg: #102A3A; --data-1-ink: #7DD3FC;
  --data-2-bg: #123B52; --data-2-ink: #BAE6FD;
  --data-3-bg: #15506C; --data-3-ink: #E0F2FE;
  --data-4-bg: #1679A3; --data-4-ink: #FFFFFF;
  --data-5-bg: #38BDF8; --data-5-ink: #082F49;
  --matrix-bg: #151D2E;
  --matrix-border: #1E293B;
  --matrix-label: #94A3B8;
  --matrix-diag-bg: #101827;
  --matrix-diag-ink: #94A3B8;
  --chart-grid: #1E293B;
  --chart-axis: #94A3B8;
  --series-a: #0EA5E9;
  --series-a-text: #7DD3FC;
  --series-b: #38BDF8;
  --series-b-text: #BAE6FD;
  --row-hover-bg: #182235;
  --row-hover-edge: #334155;
}
@media (prefers-color-scheme: dark) {
  html:not([data-theme="light"]) {
    --bg: #0B0F19;
    --bg-elev: #101827;
    --paper: #151D2E;
    --paper-2: #101827;
    --surface: #151D2E;
    --ink: #F1F5F9;
    --muted: #94A3B8;
    --line: #1E293B;
    --line-strong: #1E293B;
    --stripe: #111827;
    --accent: #38BDF8;
    --accent-2: #38BDF8;
    --accent-soft: #102A3A;
    --success: #34D399;
    --success-soft: #123024;
    --warning: #FB923C;
    --warning-soft: #332417;
    --danger: #FB7185;
    --danger-soft: #3F1D29;
    --violet: #38BDF8;
    --ok-border: #065F46;
    --warn-border: #9A3412;
    --error-border: #9F1239;
    --accent-border: #15506C;
    --canvas-top: #151D2E;
    --canvas-edge: #0D1218;
    --bar-track-bg: #101827;
    --bar-track-border: #1E293B;
    --data-bar: #38BDF8;
    --data-bar-soft: #15506C;
    --data-0-bg: #111827; --data-0-ink: #94A3B8;
    --data-1-bg: #102A3A; --data-1-ink: #7DD3FC;
    --data-2-bg: #123B52; --data-2-ink: #BAE6FD;
    --data-3-bg: #15506C; --data-3-ink: #E0F2FE;
    --data-4-bg: #1679A3; --data-4-ink: #FFFFFF;
    --data-5-bg: #38BDF8; --data-5-ink: #082F49;
    --matrix-bg: #151D2E;
    --matrix-border: #1E293B;
    --matrix-label: #94A3B8;
    --matrix-diag-bg: #101827;
    --matrix-diag-ink: #94A3B8;
    --chart-grid: #1E293B;
    --chart-axis: #94A3B8;
    --series-a: #0EA5E9;
    --series-a-text: #7DD3FC;
    --series-b: #38BDF8;
    --series-b-text: #BAE6FD;
    --row-hover-bg: #182235;
    --row-hover-edge: #334155;
  }
}
body,
html[data-theme="dark"] body {
  background: radial-gradient(circle at 88% -10%, var(--canvas-top) 0%, var(--bg) 48%, var(--canvas-edge) 100%);
  color: var(--ink);
}
@media (prefers-color-scheme: dark) {
  html:not([data-theme="light"]) body {
    background: radial-gradient(circle at 88% -10%, var(--canvas-top) 0%, var(--bg) 48%, var(--canvas-edge) 100%);
    color: var(--ink);
  }
}
h2, h3.sub,
html[data-theme="dark"] h2,
html[data-theme="dark"] h3.sub { color: var(--ink); }
@media (prefers-color-scheme: dark) {
  html:not([data-theme="light"]) h2,
  html:not([data-theme="light"]) h3.sub { color: var(--ink); }
}
""".strip()


def btf_html_report_document(
    title: str,
    body_html: str,
    *,
    subtitle: str = "",
    extra_css: str = "",
    doc_title: Optional[str] = None,
    report_class: str = "",
) -> str:
    """Wrap *body_html* in a professional BTFViewer report shell with SVG icon."""
    page_title = doc_title or f"{PRODUCT_NAME} — {title}"
    sub = subtitle.strip()
    if not sub:
        sub = f"{PRODUCT_TAGLINE} · v{APP_VERSION}"
    else:
        sub = f"{html.escape(sub)} · {PRODUCT_TAGLINE} · v{APP_VERSION}"
    icon = app_icon_svg_markup(48)
    css = _BTF_HTML_REPORT_CSS
    if extra_css:
        css = f"{css}\n{extra_css}"
    cls = "report"
    extra_cls = str(report_class or "").strip()
    if extra_cls:
        cls = f"{cls} {html.escape(extra_cls)}"
    return (
        "<!DOCTYPE html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "<meta charset=\"utf-8\">\n"
        f"<meta name=\"generator\" content=\"{html.escape(PRODUCT_NAME)} {html.escape(APP_VERSION)}\">\n"
        f"<title>{html.escape(page_title)}</title>\n"
        f"<style>\n{css}\n</style>\n"
        # Apply a saved theme before first paint so there is no flash of the
        # wrong theme; no saved value leaves data-theme unset so the
        # prefers-color-scheme CSS above decides.
        "<script>(function(){try{var t=localStorage.getItem('btfviewer-report-theme');"
        "if(t==='light'||t==='dark'){document.documentElement.setAttribute('data-theme',t);}"
        "}catch(e){}})();</script>\n"
        "</head>\n"
        "<body>\n"
        f"<div class=\"{cls}\">\n"
        "<header class=\"report-head\">\n"
        f"<div class=\"brand-icon\" aria-hidden=\"true\">{icon}</div>\n"
        "<div class=\"brand-text\">\n"
        f"<div class=\"product\">{html.escape(PRODUCT_NAME)}</div>\n"
        f"<h1>{html.escape(title)}</h1>\n"
        f"<div class=\"sub\">{sub}</div>\n"
        "</div>\n"
        "<button class=\"theme-toggle\" type=\"button\" aria-label=\"Toggle report theme\" "
        "onclick=\"btfToggleReportTheme()\">☾ Dark</button>\n"
        "</header>\n"
        f"{body_html}\n"
        "<footer class=\"report-foot\">\n"
        f"Generated by {html.escape(PRODUCT_NAME)} {html.escape(APP_VERSION)} — "
        f"{html.escape(PRODUCT_TAGLINE)}\n"
        "</footer>\n"
        "</div>\n"
        f"<script>\n{_BTF_THEME_TOGGLE_JS}\n</script>\n"
        "</body>\n"
        "</html>\n"
    )


_BTF_THEME_TOGGLE_JS = """
function btfToggleReportTheme() {
  var root = document.documentElement;
  var cur = root.getAttribute('data-theme');
  if (!cur) {
    cur = (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches)
      ? 'dark' : 'light';
  }
  var next = cur === 'dark' ? 'light' : 'dark';
  root.setAttribute('data-theme', next);
  try { localStorage.setItem('btfviewer-report-theme', next); } catch (e) {}
  btfSyncThemeToggleLabel();
}
function btfSyncThemeToggleLabel() {
  var root = document.documentElement;
  var explicit = root.getAttribute('data-theme');
  var dark = explicit
    ? explicit === 'dark'
    : !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  var btn = document.querySelector('.theme-toggle');
  if (btn) btn.textContent = dark ? '☀ Light' : '☾ Dark';
}
document.addEventListener('DOMContentLoaded', btfSyncThemeToggleLabel);
if (window.matchMedia) {
  try {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
      if (!document.documentElement.getAttribute('data-theme')) btfSyncThemeToggleLabel();
    });
  } catch (e) {}
}
""".strip()


HTML_REPORT_TOC_CSS = """
.report-toc {
  background: linear-gradient(180deg, var(--paper) 0%, var(--paper-2) 100%);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 16px 18px 18px;
  margin: 14px 0;
  box-shadow: 0 4px 16px rgba(30, 60, 90, 0.07);
  counter-reset: toc-item;
}
.report-toc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin: 0 0 6px 0;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line);
}
.report-toc-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}
.report-toc h2 {
  margin: 0;
  font-size: 15px;
  letter-spacing: 0.02em;
}
.toc-count {
  display: inline-block;
  font-size: 11px;
  font-weight: 650;
  color: var(--muted);
  background: var(--paper-2);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 2px 8px;
  white-space: nowrap;
}
.report-toc-lead {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.45;
}
.report-toc-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.toc-btn {
  font: inherit;
  font-size: 12px;
  padding: 5px 11px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: var(--paper);
  color: var(--accent);
  cursor: pointer;
  box-shadow: 0 1px 2px rgba(30, 60, 90, 0.04);
}
.toc-btn:hover { background: var(--paper-2); border-color: var(--accent); }
.report-toc ul {
  margin: 0;
  padding: 0;
  list-style: none;
  columns: 2;
  column-gap: 28px;
}
.report-toc li {
  margin: 0;
  padding: 4px 0;
  break-inside: avoid;
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.report-toc li::before {
  content: counter(toc-item, decimal-leading-zero);
  counter-increment: toc-item;
  flex: 0 0 auto;
  min-width: 1.6em;
  font-size: 11px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  color: var(--muted);
}
.report-toc a {
  color: var(--accent);
  text-decoration: none;
  font-size: 13px;
  line-height: 1.35;
}
.report-toc a:hover { color: var(--accent); text-decoration: underline; }
.toc-groups { display: grid; gap: 12px; }
.toc-group {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px 12px 12px;
  box-shadow: 0 1px 3px rgba(30, 60, 90, 0.04);
}
.toc-group h3 {
  margin: 0 0 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--line);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
}
.toc-group ul { columns: 1; }
@media (min-width: 720px) {
  .toc-groups { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 640px) {
  .report-toc ul { columns: 1; }
}
details.report-card { scroll-margin-top: 12px; }
details.report-card > summary { cursor: pointer; list-style: none; }
details.report-card > summary::-webkit-details-marker { display: none; }
details.report-card > summary h2 { display: inline-block; margin: 0; }
details.report-card > summary::before {
  content: "\\25B8";
  display: inline-block;
  width: 14px;
  margin-right: 6px;
  color: var(--accent);
  transition: transform 0.15s ease;
}
details.report-card[open] > summary::before { transform: rotate(90deg); }
""".strip()

HTML_REPORT_TOC_SCRIPT = """
<script>
(function () {
  function openTarget(id) {
    var el = document.getElementById(id);
    if (el && el.tagName === 'DETAILS') el.open = true;
    if (el && el.closest) {
      var host = el.closest('details.report-card');
      if (host) host.open = true;
    }
  }
  function setAllOpen(open) {
    document.querySelectorAll(
      'details.report-card, details.report-appendix'
    ).forEach(function (el) {
      el.open = open;
    });
  }
  document.querySelectorAll('.report-toc a[href^="#"]').forEach(function (a) {
    a.addEventListener('click', function () { openTarget(a.getAttribute('href').slice(1)); });
  });
  document.querySelectorAll('[data-toc="expand"]').forEach(function (btn) {
    btn.addEventListener('click', function () { setAllOpen(true); });
  });
  document.querySelectorAll('[data-toc="collapse"]').forEach(function (btn) {
    btn.addEventListener('click', function () { setAllOpen(false); });
  });
  window.addEventListener('hashchange', function () { openTarget(location.hash.slice(1)); });
  if (location.hash) openTarget(location.hash.slice(1));
})();
</script>
""".strip()

HTML_REPORT_INTERACTIVE_SCRIPT = """
<script>
(function () {
  var PAGE = 20;
  function textOf(el) { return (el && (el.textContent || '')).replace(/\\s+/g, ' ').trim(); }
  function parseVal(s) {
    s = String(s || '').trim();
    if (!s || s === '—' || s === '-') return NaN;
    var n = Number(s.replace(/[% ,]/g, ''));
    if (!isNaN(n) && /[-+0-9]/.test(s[0] || '')) return n;
    var m = s.match(/^(-?[0-9.]+)\\s*(ns|µs|us|ms|s)\\b/i);
    if (!m) return NaN;
    var v = Number(m[1]), u = m[2].toLowerCase();
    return v * (u === 's' ? 1e9 : u === 'ms' ? 1e6 : (u === 'us' || u === 'µs') ? 1e3 : 1);
  }
  function compactVal(v, duration) {
    if (!isFinite(v)) return '—';
    if (duration) {
      if (v >= 1e9) return (v / 1e9).toFixed(1) + ' s';
      if (v >= 1e6) return (v / 1e6).toFixed(1) + ' ms';
      if (v >= 1e3) return (v / 1e3).toFixed(1) + ' µs';
      return Math.round(v) + ' ns';
    }
    if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
    if (v >= 1e3) return (v / 1e3).toFixed(1) + 'k';
    return v >= 100 ? Math.round(v).toString() : v.toFixed(v < 10 ? 1 : 0);
  }
  function tableData(card, requiredHead) {
    var tables = Array.prototype.slice.call(card ? card.querySelectorAll('table') : []);
    var table = tables.find(function (t) {
      if (!t.tHead || !t.tBodies.length) return false;
      return !requiredHead || textOf(t.tHead).indexOf(requiredHead) >= 0;
    });
    if (!table) return null;
    return {
      heads: Array.prototype.map.call(table.tHead.rows[0].cells, textOf),
      rows: Array.prototype.map.call(table.tBodies[0].rows, function (tr) {
        return Array.prototype.map.call(tr.cells, textOf);
      }).filter(function (row) { return row.length > 1 && row.join('').indexOf('No data') < 0; })
    };
  }
  function chartHost(card, title, subtitle) {
    if (!card) return null;
    var grid = card.querySelector('.auto-chart-grid');
    if (!grid) {
      grid = document.createElement('div'); grid.className = 'auto-chart-grid';
      var summary = card.querySelector('summary'); summary.parentNode.insertBefore(grid, summary.nextSibling);
    } else { grid.classList.add('two'); }
    var host = document.createElement('div'); host.className = 'auto-chart';
    var h = document.createElement('div'); h.className = 'auto-chart-title'; h.textContent = title;
    var sub = document.createElement('div'); sub.className = 'auto-chart-subtitle'; sub.textContent = subtitle;
    host.appendChild(h); host.appendChild(sub); grid.appendChild(host); return host;
  }
  function addLineChart(card, title, subtitle, labels, series, duration) {
    var valid = series.some(function (s) { return s.values.some(isFinite); });
    if (!card || labels.length < 2 || !valid) return;
    var step = Math.max(1, Math.ceil(labels.length / 64));
    var keep = labels.map(function (_v, i) { return i; }).filter(function (i) {
      return i % step === 0 || i === labels.length - 1;
    });
    labels = keep.map(function (i) { return labels[i]; });
    series = series.slice(0, 5).map(function (s) {
      return { name: s.name, values: keep.map(function (i) { return s.values[i]; }) };
    });
    var all = [];
    series.forEach(function (s) { s.values.forEach(function (v) { if (isFinite(v)) all.push(v); }); });
    var max = Math.max.apply(Math, all.concat([1]));
    var host = chartHost(card, title, subtitle); if (!host) return;
    var NS = 'http://www.w3.org/2000/svg', w = 720, h = 220, l = 54, r = 14, t = 12, b = 30;
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('class', 'auto-line-svg'); svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    function add(tag, attrs, value) {
      var el = document.createElementNS(NS, tag);
      Object.keys(attrs || {}).forEach(function (k) { el.setAttribute(k, attrs[k]); });
      if (value != null) el.textContent = value; svg.appendChild(el); return el;
    }
    for (var g = 0; g <= 4; g += 1) {
      var y = t + (h - t - b) * g / 4;
      add('line', { x1: l, x2: w - r, y1: y, y2: y, class: 'auto-grid-line' });
      add('text', { x: l - 7, y: y + 3, 'text-anchor': 'end', class: 'auto-axis-label' }, compactVal(max * (4 - g) / 4, duration));
    }
    var xAt = function (i) { return l + (w - l - r) * i / Math.max(1, labels.length - 1); };
    var yAt = function (v) { return t + (h - t - b) * (1 - Math.max(0, v) / max); };
    series.forEach(function (s, si) {
      var pts = s.values.map(function (v, i) { return isFinite(v) ? xAt(i) + ',' + yAt(v) : ''; }).filter(Boolean);
      if (pts.length > 1) add('polyline', { points: pts.join(' '), class: 'auto-series auto-series-' + si });
      s.values.forEach(function (v, i) {
        if (!isFinite(v) || (labels.length > 24 && i % Math.ceil(labels.length / 18))) return;
        var dot = add('circle', { cx: xAt(i), cy: yAt(v), r: 3, class: 'auto-dot auto-dot-' + si });
        var tip = document.createElementNS(NS, 'title'); tip.textContent = labels[i] + ' · ' + s.name + ': ' + compactVal(v, duration); dot.appendChild(tip);
      });
    });
    [0, Math.floor((labels.length - 1) / 2), labels.length - 1].forEach(function (i) {
      add('text', { x: xAt(i), y: h - 9, 'text-anchor': i === 0 ? 'start' : (i === labels.length - 1 ? 'end' : 'middle'), class: 'auto-axis-label' }, labels[i]);
    });
    host.appendChild(svg);
    var legend = document.createElement('div'); legend.className = 'auto-chart-legend';
    series.forEach(function (s, i) {
      var item = document.createElement('span'); item.className = 'auto-legend-item';
      item.innerHTML = '<i class="auto-swatch auto-swatch-' + i + '"></i>'; item.appendChild(document.createTextNode(s.name)); legend.appendChild(item);
    });
    host.appendChild(legend);
  }
  function addDonutChart(card, title, subtitle, items, duration) {
    items = items.filter(function (it) { return isFinite(it.value) && it.value > 0; })
      .sort(function (a, b) { return b.value - a.value; });
    if (!card || !items.length) return;
    if (items.length > 7) {
      var other = items.slice(7).reduce(function (n, it) { return n + it.value; }, 0);
      items = items.slice(0, 7).concat([{ label: 'Other', value: other }]);
    }
    var total = items.reduce(function (n, it) { return n + it.value; }, 0);
    var host = chartHost(card, title, subtitle), layout = document.createElement('div');
    layout.className = 'auto-donut-layout';
    var donut = document.createElement('div'); donut.className = 'auto-donut';
    var at = 0, stops = items.map(function (it, i) {
      var from = at; at += 100 * it.value / total;
      return 'var(--auto-c' + i + ') ' + from.toFixed(2) + '% ' + at.toFixed(2) + '%';
    });
    var colors = ['var(--accent)', 'var(--success)', 'var(--warning)', 'var(--danger)', 'var(--violet)', '#64748b', '#14b8a6', '#f97316'];
    colors.forEach(function (c, i) { donut.style.setProperty('--auto-c' + i, c); });
    donut.style.background = 'conic-gradient(' + stops.join(',') + ')'; layout.appendChild(donut);
    var legend = document.createElement('div'); legend.className = 'auto-donut-legend';
    items.forEach(function (it, i) {
      var row = document.createElement('div'); row.className = 'auto-donut-row';
      var sw = document.createElement('i'); sw.className = 'auto-swatch'; sw.style.background = colors[i];
      var lab = document.createElement('span'); lab.className = 'auto-donut-label'; lab.textContent = it.label;
      var val = document.createElement('span'); val.className = 'auto-donut-value'; val.textContent = compactVal(it.value, duration) + ' · ' + (100 * it.value / total).toFixed(1) + '%';
      row.appendChild(sw); row.appendChild(lab); row.appendChild(val); legend.appendChild(row);
    });
    layout.appendChild(legend); host.appendChild(layout);
  }
  function hydrateTraceCompareCharts() {
    if (!document.querySelector('.report-compare')) return;
    function compareLine(id, title, subtitle, labelHead, aHead, bHead, duration) {
      var c = document.getElementById(id), d = tableData(c, labelHead); if (!d || d.rows.length < 2) return;
      var li = d.heads.indexOf(labelHead), ai = d.heads.indexOf(aHead), bi = d.heads.indexOf(bHead);
      if (li < 0 || ai < 0 || bi < 0) return;
      addLineChart(c, title, subtitle, d.rows.map(function (row) { return row[li]; }), [
        { name: 'Baseline A', values: d.rows.map(function (row) { return parseVal(row[ai]); }) },
        { name: 'Candidate B', values: d.rows.map(function (row) { return parseVal(row[bi]); }) }
      ], duration);
    }
    function trendLine(title, valueHead) {
      var c = document.getElementById('sec-trends'), d = tableData(c, 'Trace'); if (!d || d.rows.length < 2) return;
      var li = d.heads.indexOf('Trace'), vi = d.heads.indexOf(valueHead); if (li < 0 || vi < 0) return;
      addLineChart(c, title, 'Trace order follows the multi-trace summary',
        d.rows.map(function (row) { return row[li]; }),
        [{ name: valueHead, values: d.rows.map(function (row) { return parseVal(row[vi]); }) }], false);
    }
    compareLine('sec-preemption-chains', 'Preemption count profile', 'Victim order follows the comparison table', 'Victim', 'Count A', 'Count B', false);
    compareLine('sec-preemption-chains', 'Preemption duration profile', 'Total preempted time by victim', 'Victim', 'Total A', 'Total B', true);
    compareLine('sec-sync-objects', 'Synchronization activity profile', 'Instrumented object metrics on a shared scale', 'Metric', 'Baseline A', 'Candidate B', false);
    trendLine('Task-count trend', 'Tasks');
    trendLine('Migration trend', 'Migrations');
    trendLine('Load-balance trend', 'Load balance');
  }
  function hydrateStatisticsCharts() {
    hydrateTraceCompareCharts();
    function card(id) { return document.getElementById(id); }
    function line(id, title, subtitle, labelHead, valueHeads, duration, requiredHead) {
      var c = card(id), d = tableData(c, requiredHead || labelHead); if (!d || !d.rows.length) return;
      var li = d.heads.indexOf(labelHead);
      var ss = valueHeads.map(function (name) {
        var ci = d.heads.indexOf(name);
        return { name: name, values: d.rows.map(function (row) { return parseVal(row[ci]); }) };
      }).filter(function (s) { return s.values.some(isFinite); });
      addLineChart(c, title, subtitle, d.rows.map(function (row) { return row[li]; }), ss, duration);
    }
    var cu = card('sec-core-utilization-over-time'), cud = tableData(cu, 'Time');
    if (cud) line('sec-core-utilization-over-time', 'Core utilization trend', 'Per-core utilization across exported windows', 'Time', cud.heads.slice(1).filter(function (h) { return h !== 'Spread'; }), false);
    line('sec-scheduling-load-over-time', 'Scheduling activity trend', 'Context-switch volume and rate by window', 'Time', ['Ctx sw', 'Ctx sw/s'], false);
    line('sec-scheduling-load-over-time', 'Balance health trend', 'Utilization spread and Load Balance Score', 'Time', ['Util σ', 'LB score'], false);
    line('sec-response-time', 'Response latency profile', 'Task order follows the exported statistics table', 'Task', ['p50', 'p95', 'p99'], true);
    line('sec-dispatch-scheduling-latency', 'Dispatch latency profile', 'p50, p95, and p99 by task', 'Task', ['p50', 'p95', 'p99'], true);
    line('sec-activation-latency', 'Activation latency profile', 'p50, p95, and p99 by task', 'Task', ['p50', 'p95', 'p99'], true);
    line('sec-idle-analysis', 'Idle-duration profile', 'Total, longest, and p95 idle spans by core', 'Core', ['Idle total', 'Longest', 'p95'], true);
    line('sec-queue-backlog-semaphore-level', 'Queue / semaphore level profile', 'Peak and ending level by object', 'Object', ['Peak', 'End level'], false);
    line('sec-trace-health-tick', 'TICK gap trend', 'Observed large gaps in timestamp order', 'Start', ['Gap'], true, 'Gap');
    line('sec-trace-health-tick', 'Estimated missed TICKs', 'Estimated misses for each large gap', 'Start', ['Missed'], false, 'Gap');
    function columnDonut(id, title, subtitle, names, duration) {
      var c = card(id), d = tableData(c, names[0]); if (!d) return;
      addDonutChart(c, title, subtitle, names.map(function (name) {
        var ci = d.heads.indexOf(name);
        return { label: name, value: d.rows.reduce(function (n, row) { var v = parseVal(row[ci]); return n + (isFinite(v) ? v : 0); }, 0) };
      }), duration);
    }
    columnDonut('sec-core-time-breakdown', 'Core time composition', 'Aggregate share across all cores', ['Active %', 'Idle %', 'Tick %', 'Gap %'], false);
    columnDonut('sec-switch-reason-breakdown', 'Switch reason composition', 'Aggregate scheduler transition reasons', ['Preempted', 'Blocked', 'Suspended', 'Period', 'Other'], false);
    var top = card('sec-top-tasks-by-cpu-excl-idle-tick');
    if (top) addDonutChart(top, 'Task CPU share', 'Top tasks plus an Other remainder when needed', Array.prototype.map.call(top.querySelectorAll('.util-row-task'), function (row) {
      return { label: textOf(row.querySelector('.util-label')), value: parseVal(textOf(row.querySelector('.util-pct'))) };
    }), false);
    var mig = card('sec-core-pair-migration-summary'), md = tableData(mig, 'From');
    if (md) addDonutChart(mig, 'Migration flow share', 'Busiest source → destination routes', md.rows.map(function (row) {
      return { label: row[0] + ' → ' + row[1], value: parseVal(row[2]) };
    }), false);
    var mutex = card('sec-mutex-blocking'), mud = tableData(mutex, 'Object');
    if (mud) {
      var oi = mud.heads.indexOf('Object'), ti = mud.heads.indexOf('Total'), byObj = {};
      mud.rows.forEach(function (row) { var v = parseVal(row[ti]); if (isFinite(v)) byObj[row[oi]] = (byObj[row[oi]] || 0) + v; });
      addDonutChart(mutex, 'Blocking-time composition', 'Total blocking time grouped by synchronization object', Object.keys(byObj).map(function (k) { return { label: k, value: byObj[k] }; }), true);
    }
  }
  function enhanceReportNavigation() {
    var report = document.querySelector('.report');
    var cards = Array.prototype.slice.call(document.querySelectorAll('details.report-card'));
    if (!report || !cards.length) return;
    var toc = report.querySelector('.report-toc');
    hydrateStatisticsCharts();
    var tools = document.createElement('div');
    tools.className = 'report-command-bar';
    tools.setAttribute('role', 'search');
    tools.innerHTML = '<label class="report-search-wrap"><span class="report-search-icon" aria-hidden="true">⌕</span>'
      + '<input type="search" class="report-search" aria-label="Search report sections" placeholder="Search sections and values…">'
      + '<span class="report-search-key" aria-hidden="true">/</span></label>'
      + '<span class="report-match-count" aria-live="polite"></span>'
      + '<button type="button" class="report-tool-btn" data-report-expand>Expand results</button>'
      + '<button type="button" class="report-tool-btn" data-report-reset>Reset</button>'
      + '<button type="button" class="report-tool-btn" data-report-print>Print</button>';
    report.insertBefore(tools, toc || cards[0]);
    var input = tools.querySelector('.report-search');
    var count = tools.querySelector('.report-match-count');
    var empty = document.createElement('div');
    empty.className = 'report-empty-results';
    empty.textContent = 'No report sections match this search.';
    empty.hidden = true;
    tools.parentNode.insertBefore(empty, tools.nextSibling);
    cards.forEach(function (card) {
      card._reportSearchText = textOf(card).toLowerCase();
      var summary = card.querySelector('summary');
      if (!summary || !card.id) return;
      var link = document.createElement('button');
      link.type = 'button';
      link.className = 'section-link';
      link.textContent = 'Copy link';
      link.title = 'Copy a direct link to this section';
      link.addEventListener('click', function (e) {
        e.preventDefault(); e.stopPropagation();
        try { history.replaceState(null, '', '#' + card.id); } catch (err) {}
        var done = function () {
          link.textContent = 'Copied';
          setTimeout(function () { link.textContent = 'Copy link'; }, 1200);
        };
        var legacyCopy = function () {
          var field = document.createElement('textarea');
          field.value = location.href; field.style.position = 'fixed'; field.style.opacity = '0';
          document.body.appendChild(field); field.select();
          var ok = false;
          try { ok = document.execCommand('copy'); } catch (err) {}
          field.remove();
          if (ok) done(); else link.textContent = 'Link ready';
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(location.href).then(done, legacyCopy);
        } else { legacyCopy(); }
      });
      summary.appendChild(link);
    });
    function applySearch() {
      var terms = String(input.value || '').toLowerCase().trim().split(/\\s+/).filter(Boolean);
      var visible = 0;
      cards.forEach(function (card) {
        var hit = !terms.length || terms.every(function (term) {
          return card._reportSearchText.indexOf(term) >= 0;
        });
        card.hidden = !hit;
        if (hit) { visible += 1; if (terms.length) card.open = true; }
        var navLink = toc && toc.querySelector('a[href="#' + card.id + '"]');
        var li = navLink && navLink.closest('li');
        if (li) li.hidden = !hit;
      });
      if (toc) toc.querySelectorAll('.toc-group').forEach(function (group) {
        group.hidden = !group.querySelector('li:not([hidden])');
      });
      count.textContent = visible + ' of ' + cards.length + ' sections';
      empty.hidden = visible !== 0;
    }
    input.addEventListener('input', applySearch);
    tools.querySelector('[data-report-expand]').addEventListener('click', function () {
      cards.forEach(function (card) { if (!card.hidden) card.open = true; });
    });
    tools.querySelector('[data-report-reset]').addEventListener('click', function () {
      input.value = ''; applySearch(); input.focus();
    });
    tools.querySelector('[data-report-print]').addEventListener('click', function () { window.print(); });
    document.addEventListener('keydown', function (e) {
      var tag = String(e.target && e.target.tagName || '').toLowerCase();
      if (e.key === '/' && tag !== 'input' && tag !== 'textarea' && !e.target.isContentEditable) {
        e.preventDefault(); input.focus();
      } else if (e.key === 'Escape' && document.activeElement === input) {
        input.value = ''; applySearch(); input.blur();
      }
    });
    var top = document.createElement('button');
    top.type = 'button'; top.className = 'back-to-top'; top.textContent = '↑';
    top.title = 'Back to top'; top.setAttribute('aria-label', 'Back to top');
    top.addEventListener('click', function () { window.scrollTo({ top: 0, behavior: 'smooth' }); });
    document.body.appendChild(top);
    var progress = document.createElement('div');
    progress.className = 'scroll-progress';
    progress.innerHTML = '<span class="scroll-progress-fill"></span>';
    document.body.appendChild(progress);
    var progressFill = progress.firstElementChild;
    function syncScrollUi() {
      top.classList.toggle('visible', window.scrollY > 500);
      var max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
      progressFill.style.transform = 'scaleX(' + Math.min(1, window.scrollY / max) + ')';
    }
    window.addEventListener('scroll', syncScrollUi, { passive: true });
    window.addEventListener('resize', syncScrollUi);
    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    function countUpKpi(el, delayMs) {
      if (reduceMotion) return;
      if (el.dataset.kpiRaw === undefined) el.dataset.kpiRaw = el.textContent;
      var raw = el.dataset.kpiRaw;
      var m = /^([^0-9]*?)(-?[0-9][0-9,]*(?:\\.[0-9]+)?)([^0-9]*)$/.exec(raw);
      if (!m) return;
      var prefix = m[1], numText = m[2], suffix = m[3];
      var target = parseFloat(numText.replace(/,/g, ''));
      if (!isFinite(target)) return;
      var decimals = (numText.split('.')[1] || '').length;
      var grouped = numText.indexOf(',') >= 0;
      var duration = 700, start = null;
      function frame(ts) {
        if (start === null) start = ts;
        var p = Math.min(1, (ts - start) / duration);
        var eased = 1 - Math.pow(1 - p, 3);
        var val = target * eased;
        el.textContent = prefix + val.toLocaleString(undefined, {
          minimumFractionDigits: decimals, maximumFractionDigits: decimals, useGrouping: grouped
        }) + suffix;
        if (p < 1) requestAnimationFrame(frame); else el.textContent = raw;
      }
      window.setTimeout(function () { requestAnimationFrame(frame); }, delayMs);
    }
    function animateKpis(root) {
      root.querySelectorAll('.kpi').forEach(function (tile, i) {
        var delay = Math.min(i * 45, 360);
        tile.classList.remove('kpi-in'); tile.classList.add('kpi-animate');
        tile.style.animationDelay = delay + 'ms';
        requestAnimationFrame(function () { tile.classList.add('kpi-in'); });
        var valueEl = tile.querySelector('.v');
        if (valueEl) countUpKpi(valueEl, delay);
      });
    }
    function animateMetrics(root) {
      root.classList.remove('compare-chart-active');
      root.getBoundingClientRect();
      requestAnimationFrame(function () { root.classList.add('compare-chart-active'); });
      root.querySelectorAll(
        '.util-bar-fill, .rank-bar-fill, .pct-bar .fill, .chart-line, .chart-point, .pctile-bar'
      ).forEach(function (el, i) {
        el.classList.remove('metric-in'); el.classList.add('metric-animate');
        el.style.animationDelay = Math.min(i * 24, 240) + 'ms';
        requestAnimationFrame(function () { el.classList.add('metric-in'); });
      });
      root.querySelectorAll('.lb-gauge-svg').forEach(function (gauge) {
        gauge.classList.remove('lb-gauge-active');
        gauge.getBoundingClientRect();
        requestAnimationFrame(function () { gauge.classList.add('lb-gauge-active'); });
      });
      root.querySelectorAll('.auto-chart').forEach(function (chart) {
        chart.classList.remove('chart-active'); chart.getBoundingClientRect();
        requestAnimationFrame(function () { chart.classList.add('chart-active'); });
      });
      animateKpis(root);
    }
    cards.forEach(function (card) {
      card.addEventListener('toggle', function () { if (card.open) animateMetrics(card); });
    });
    if ('IntersectionObserver' in window) {
      var reveal = new IntersectionObserver(function (entries, observer) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          entry.target.classList.add('motion-in'); animateMetrics(entry.target); observer.unobserve(entry.target);
        });
      }, { rootMargin: '0px 0px -8% 0px', threshold: 0.04 });
      cards.forEach(function (card) { card.classList.add('motion-ready'); reveal.observe(card); });
      var spy = new IntersectionObserver(function (entries) {
        var current = entries.filter(function (entry) { return entry.isIntersecting; })
          .sort(function (a, b) { return Math.abs(a.boundingClientRect.top) - Math.abs(b.boundingClientRect.top); })[0];
        if (!current || !toc) return;
        toc.querySelectorAll('a.active').forEach(function (a) { a.classList.remove('active'); });
        var active = toc.querySelector('a[href="#' + current.target.id + '"]');
        if (active) active.classList.add('active');
      }, { rootMargin: '-12% 0px -72% 0px', threshold: 0 });
      cards.forEach(function (card) { spy.observe(card); });
    } else { cards.forEach(animateMetrics); }
    syncScrollUi();
    applySearch();
  }
  function enhanceTable(table, idx) {
    if (!table.tHead || !table.tBodies.length) return;
    if (table.closest('.kpi-grid, .finding-card, .meta-table, .scope-table')) return;
    var tbody = table.tBodies[0];
    var rows = Array.prototype.slice.call(tbody.rows);
    if (!rows.length) return;
    var hasProblems = !!table.querySelector('.sev-error, .sev-warning');
    var wrap = document.createElement('div');
    wrap.className = 'table-tools';
    var scroll = document.createElement('div');
    scroll.className = 'table-scroll';
    table.parentNode.insertBefore(wrap, table);
    wrap.appendChild(scroll);
    scroll.appendChild(table);
    var bar = document.createElement('div');
    bar.className = 'table-toolbar';
    bar.innerHTML = '<input type="search" class="table-search" aria-label="Search table rows" placeholder="Search table…">'
      + (hasProblems ? '<label class="table-check"><input type="checkbox" data-problems> Problems only</label>' : '')
      + '<label class="table-check"><input type="checkbox" data-all> Show all</label>'
      + '<span class="table-count"></span>'
      + '<button type="button" class="table-csv table-action">CSV</button>';
    wrap.insertBefore(bar, scroll);
    var csvBtn = bar.querySelector('.table-csv');
    if (csvBtn) {
      csvBtn.title = 'Download the filtered rows as a CSV file';
    }
    var pager = document.createElement('div');
    pager.className = 'table-pager';
    pager.innerHTML = '<button type="button" data-pg="prev" class="table-action">\\u2039 Prev</button>'
      + '<span data-pg="label"></span>'
      + '<button type="button" data-pg="next" class="table-action">Next \\u203a</button>';
    wrap.appendChild(pager);
    var pgPrev = pager.querySelector('[data-pg="prev"]');
    var pgNext = pager.querySelector('[data-pg="next"]');
    var pgLabel = pager.querySelector('[data-pg="label"]');
    var headTxt = Array.prototype.map.call(
      table.tHead.rows[0].cells, function (th) { return th.textContent; });
    var q = '', problems = false, showAll = rows.length <= PAGE, sortCol = -1, sortDir = 1, page = 0;
    var lastFiltered = rows;
    Array.prototype.forEach.call(table.tHead.rows[0].cells, function (th, i) {
      th.tabIndex = 0;
      th.setAttribute('role', 'button');
      th.classList.add('sortable');
      th.addEventListener('click', function () {
        if (sortCol === i) sortDir = -sortDir; else { sortCol = i; sortDir = 1; }
        page = 0; apply();
      });
      th.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); th.click(); }
      });
    });
    function apply() {
      var filtered = rows.filter(function (tr) {
        if (problems && !tr.querySelector('.sev-error, .sev-warning')) return false;
        if (q && textOf(tr).toLowerCase().indexOf(q) < 0) return false;
        return true;
      });
      if (sortCol >= 0) {
        filtered.sort(function (a, b) {
          var av = textOf(a.cells[sortCol]), bv = textOf(b.cells[sortCol]);
          var an = parseVal(av), bn = parseVal(bv);
          var cmp = (!isNaN(an) && !isNaN(bn)) ? an - bn : av.localeCompare(bv);
          return cmp * sortDir;
        });
      }
      lastFiltered = filtered;
      Array.prototype.forEach.call(table.tHead.rows[0].cells, function (th, i) {
        var on = i === sortCol;
        th.textContent = headTxt[i] + (on ? (sortDir > 0 ? ' \\u25b2' : ' \\u25bc') : '');
        th.setAttribute('aria-sort', on ? (sortDir > 0 ? 'ascending' : 'descending') : 'none');
      });
      var pages = showAll ? 1 : Math.max(1, Math.ceil(filtered.length / PAGE));
      if (page > pages - 1) page = pages - 1;
      if (page < 0) page = 0;
      rows.forEach(function (tr) { tr.style.display = 'none'; });
      var start = showAll ? 0 : page * PAGE;
      var vis = showAll ? filtered : filtered.slice(start, start + PAGE);
      vis.forEach(function (tr) { tbody.appendChild(tr); tr.style.display = ''; });
      var count = wrap.querySelector('.table-count');
      count.textContent = filtered.length === rows.length
        ? (vis.length < filtered.length ? vis.length + ' of ' + filtered.length : filtered.length + ' rows')
        : vis.length + ' of ' + filtered.length + ' (filtered)';
      if (!showAll && filtered.length > PAGE) {
        pager.style.display = 'flex';
        pgLabel.textContent = 'Page ' + (page + 1) + ' / ' + pages;
        pgPrev.disabled = page <= 0;
        pgNext.disabled = page >= pages - 1;
        pgPrev.style.opacity = pgPrev.disabled ? '0.4' : '1';
        pgNext.style.opacity = pgNext.disabled ? '0.4' : '1';
      } else {
        pager.style.display = 'none';
      }
    }
    pgPrev.addEventListener('click', function () { if (page > 0) { page -= 1; apply(); } });
    pgNext.addEventListener('click', function () { page += 1; apply(); });
    bar.querySelector('.table-search').addEventListener('input', function (e) {
      q = String(e.target.value || '').toLowerCase(); page = 0; apply();
    });
    var pb = bar.querySelector('[data-problems]');
    if (pb) pb.addEventListener('change', function (e) { problems = e.target.checked; page = 0; apply(); });
    bar.querySelector('[data-all]').addEventListener('change', function (e) {
      showAll = e.target.checked; page = 0; apply();
    });
    if (rows.length <= PAGE) bar.querySelector('[data-all]').checked = true;
    if (csvBtn) csvBtn.addEventListener('click', function () {
      function esc(v) {
        v = String(v == null ? '' : v).replace(/\\s+/g, ' ').trim();
        return /["\\r\\n,]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
      }
      var lines = [headTxt.map(esc).join(',')];
      lastFiltered.forEach(function (tr) {
        lines.push(Array.prototype.map.call(tr.cells, function (td) {
          return esc(textOf(td));
        }).join(','));
      });
      var csv = '\\ufeff' + lines.join('\\r\\n') + '\\r\\n';
      var card = table.closest('details.report-card');
      var sm = card && card.querySelector('summary');
      var name = (sm ? textOf(sm) : '').toLowerCase()
        .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || ('table-' + (idx + 1));
      var a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
      a.download = name + '.csv';
      document.body.appendChild(a);
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 0);
    });
    apply();
  }
  enhanceReportNavigation();
  document.querySelectorAll('details.report-card table').forEach(enhanceTable);
  document.querySelectorAll('.report-tabs').forEach(function (tabs) {
    var btns = tabs.querySelectorAll('[data-tab]');
    var panels = tabs.querySelectorAll('[data-panel]');
    function show(id) {
      btns.forEach(function (b) { b.classList.toggle('active', b.getAttribute('data-tab') === id); });
      panels.forEach(function (p) { p.hidden = p.getAttribute('data-panel') !== id; });
    }
    btns.forEach(function (b) {
      b.addEventListener('click', function () { show(b.getAttribute('data-tab')); });
    });
    var first = tabs.querySelector('[data-tab]');
    if (first) show(first.getAttribute('data-tab'));
  });
})();
</script>
""".strip()


_SCOPE_SUFFIX_RE = re.compile(r"\s*\(cursor range[^)]*\)\s*$", re.I)


def html_section_slug(title: str) -> str:
    """Stable HTML id fragment from a report-card heading."""
    text = _SCOPE_SUFFIX_RE.sub("", str(title or "")).strip()
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:72] or "section"


def _attr_value(attrs: str, name: str) -> str:
    m = re.search(rf'\b{name}="([^"]*)"', attrs or "")
    return m.group(1) if m else ""


def html_toc_nav(entries, groups=None) -> str:
    """Table of Contents nav with Expand all / Collapse all.

    *groups* is an optional sequence of ``(group_title, title_prefixes)``.
    """
    items = list(entries or [])
    n = len(items)
    count_label = f"{n} section" if n == 1 else f"{n} sections"
    grouped_items = ""
    if groups:
        remaining = items
        blocks = []
        for group_title, prefixes in groups:
            pref = tuple(prefixes or ())
            chosen = []
            keep = []
            for sec_id, title in remaining:
                if pref and str(title).startswith(pref):
                    chosen.append((sec_id, title))
                else:
                    keep.append((sec_id, title))
            remaining = keep
            if not chosen:
                continue
            lis = "".join(
                f'<li><a href="#{sec_id}">{html.escape(str(title))}</a></li>'
                for sec_id, title in chosen
            )
            blocks.append(
                f'<div class="toc-group"><h3>{html.escape(str(group_title))}</h3>'
                f"<ul>{lis}</ul></div>"
            )
        if remaining:
            lis = "".join(
                f'<li><a href="#{sec_id}">{html.escape(str(title))}</a></li>'
                for sec_id, title in remaining
            )
            blocks.append(f'<div class="toc-group"><h3>Other</h3><ul>{lis}</ul></div>')
        grouped_items = f'<div class="toc-groups">{"".join(blocks)}</div>'
    else:
        grouped_items = "<ul>" + "".join(
            f'<li><a href="#{sec_id}">{html.escape(str(title))}</a></li>'
            for sec_id, title in items
        ) + "</ul>"
    return (
        '<nav class="report-toc" aria-label="Table of Contents">'
        '<div class="report-toc-head">'
        '<div class="report-toc-title">'
        "<h2>Table of Contents</h2>"
        f'<span class="toc-count">{html.escape(count_label)}</span>'
        "</div>"
        '<div class="report-toc-actions">'
        '<button type="button" class="toc-btn" data-toc="expand">Expand all</button>'
        '<button type="button" class="toc-btn" data-toc="collapse">Collapse all</button>'
        "</div></div>"
        '<p class="report-toc-lead">Jump to a section below. Expand all opens every card; '
        "Collapse all closes them.</p>"
        f"{grouped_items}</nav>"
    )


def html_make_collapsible_sections(
    doc_html: str,
    default_expanded: tuple = (),
    toc_groups=None,
) -> tuple:
    """Wrap every ``<section class="report-card ...">`` in ``<details>``
    and build a table-of-contents nav. Returns ``(nav_html, new_doc_html)``.
    Pass ``default_expanded=True`` to open every section by default.
    """
    expand_all = default_expanded is True
    prefixes = () if expand_all else tuple(default_expanded or ())
    toc_entries: list = []
    used_ids: set = set()
    counter = 0

    def _wrap(m: "re.Match") -> str:
        nonlocal counter
        classes, attrs, inner = m.group(1), m.group(2) or "", m.group(3)
        h2_m = re.search(r"<h2[^>]*>.*?</h2>", inner, re.S)
        if h2_m:
            title_html = h2_m.group(0)
            title_text = re.sub(r"<[^>]+>", "", title_html)
            rest = inner[h2_m.end():]
        else:
            title_html, title_text, rest = "<h2>Section</h2>", "Section", inner
        counter += 1
        existing = _attr_value(attrs, "id")
        if existing:
            sec_id = existing
        else:
            slug = html_section_slug(title_text)
            sec_id = f"sec-{slug}"
            n = 2
            while sec_id in used_ids:
                sec_id = f"sec-{slug}-{n}"
                n += 1
        used_ids.add(sec_id)
        toc_entries.append((sec_id, title_text))
        open_attr = " open" if (expand_all or title_text.startswith(prefixes)) else ""
        extra = re.sub(r'\s*\bid="[^"]*"', "", attrs).strip()
        extra_attr = f" {extra}" if extra else ""
        return (
            f'<details class="{classes}" id="{sec_id}"{extra_attr}{open_attr}>'
            f"<summary>{title_html}</summary>{rest}</details>"
        )

    new_doc = re.sub(
        r'<section class="(report-card[^"]*)"([^>]*)>(.*?)</section>',
        _wrap, doc_html, flags=re.S,
    )
    if not toc_entries:
        return "", new_doc
    return html_toc_nav(toc_entries, groups=toc_groups), new_doc


def html_apply_collapsible_toc(
    document_html: str,
    *,
    default_expanded: tuple = (),
    toc_groups=None,
) -> str:
    """Wrap report cards, inject TOC at ``<!--TOC-->`` (or after the header)."""
    nav, doc = html_make_collapsible_sections(
        document_html, default_expanded, toc_groups=toc_groups)
    if not nav:
        return doc
    if "<!--TOC-->" in doc:
        return doc.replace("<!--TOC-->", nav, 1)
    return doc.replace("</header>", "</header>\n" + nav, 1)
