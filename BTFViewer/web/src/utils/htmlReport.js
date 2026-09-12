/**
 * Shared HTML report chrome for BTFViewer exports (Web).
 * Keep in sync with btf_viewer_pkg/html_report.py.
 */

export const APP_VERSION = '1.0.0'
export const PRODUCT_NAME = 'BTFViewer'
export const PRODUCT_TAGLINE = 'Portable BTF trace analysis and evidence reports'

/** Embedded app icon (same markup as Desktop About / config._APP_ICON_SVG). */
export const APP_ICON_SVG = (
  '<svg xmlns="http://www.w3.org/2000/svg" width="72" height="72" viewBox="0 0 72 72">'
  + '<rect width="72" height="72" rx="14" fill="#1C3A6E"/>'
  + '<rect x="10" y="16" width="30" height="7" rx="3.5" fill="#5B9BD5"/>'
  + '<rect x="16" y="27" width="24" height="7" rx="3.5" fill="#7EC8E3"/>'
  + '<rect x="10" y="38" width="37" height="7" rx="3.5" fill="#5B9BD5"/>'
  + '<rect x="20" y="49" width="20" height="7" rx="3.5" fill="#7EC8E3"/>'
  + '<rect x="47" y="12" width="2.5" height="48" fill="#FFC107"/>'
  + '<polygon points="43,12 54,12 48.5,19" fill="#FFC107"/>'
  + '<circle cx="53" cy="48" r="8" fill="#12263f"/>'
  + '<circle cx="53" cy="48" r="8" fill="none" stroke="#FFC107" stroke-width="1.5"/>'
  + '<circle cx="53" cy="45" r="1.4" fill="#FFC107"/>'
  + '<circle cx="50" cy="51" r="1.4" fill="#7EC8E3"/>'
  + '<circle cx="56" cy="51" r="1.4" fill="#5B9BD5"/>'
  + '<path d="M53 45 L50 51 L56 51 Z" fill="none" stroke="#FFC107" stroke-width="1" stroke-linejoin="round"/>'
  + '</svg>'
)

export function appIconSvgMarkup(size = 48) {
  const sz = Math.max(16, Number(size) || 48)
  return APP_ICON_SVG
    .replace(/\bwidth="\d+"/, `width="${sz}"`)
    .replace(/\bheight="\d+"/, `height="${sz}"`)
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export const BTF_HTML_REPORT_CSS = `
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
@media print {
  .theme-toggle { display: none !important; }
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
`.trim()

export const REPORT_THEME_CSS = `
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
`.trim()

/**
 * Wrap bodyHtml in a professional BTFViewer report shell with embedded SVG icon.
 */
export function btfHtmlReportDocument(title, bodyHtml, {
  subtitle = '',
  extraCss = '',
  docTitle = '',
  reportClass = '',
} = {}) {
  const pageTitle = docTitle || `${PRODUCT_NAME} — ${title}`
  let sub = String(subtitle || '').trim()
  if (!sub) {
    sub = `${PRODUCT_TAGLINE} · v${APP_VERSION}`
  } else {
    sub = `${escapeHtml(sub)} · ${PRODUCT_TAGLINE} · v${APP_VERSION}`
  }
  const css = extraCss ? `${BTF_HTML_REPORT_CSS}\n${extraCss}` : BTF_HTML_REPORT_CSS
  const icon = appIconSvgMarkup(48)
  const cls = reportClass ? `report ${escapeHtml(String(reportClass).trim())}` : 'report'
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="generator" content="${escapeHtml(PRODUCT_NAME)} ${escapeHtml(APP_VERSION)}">
<title>${escapeHtml(pageTitle)}</title>
<style>
${css}
</style>
<script>(function(){try{var t=localStorage.getItem('btfviewer-report-theme');if(t==='light'||t==='dark'){document.documentElement.setAttribute('data-theme',t);}}catch(e){}})();</script>
</head>
<body>
<div class="${cls}">
<header class="report-head">
<div class="brand-icon" aria-hidden="true">${icon}</div>
<div class="brand-text">
<div class="product">${escapeHtml(PRODUCT_NAME)}</div>
<h1>${escapeHtml(title)}</h1>
<div class="sub">${sub}</div>
</div>
<button class="theme-toggle" type="button" aria-label="Toggle report theme" onclick="btfToggleReportTheme()">☾ Dark</button>
</header>
${bodyHtml}
<footer class="report-foot">
Generated by ${escapeHtml(PRODUCT_NAME)} ${escapeHtml(APP_VERSION)} — ${escapeHtml(PRODUCT_TAGLINE)}
</footer>
</div>
<script>
${BTF_THEME_TOGGLE_JS}
</script>
</body>
</html>
`
}

export const BTF_THEME_TOGGLE_JS = `
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
`.trim()

export const HTML_REPORT_TOC_CSS = `
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
`.trim()

export const HTML_REPORT_TOC_SCRIPT = `
<script>
(function () {
  function openTarget(id) {
    var el = document.getElementById(id)
    if (el && el.tagName === 'DETAILS') el.open = true
    if (el && el.closest) {
      var host = el.closest('details.report-card')
      if (host) host.open = true
    }
  }
  function setAllOpen(open) {
    document.querySelectorAll(
      'details.report-card, details.report-appendix'
    ).forEach(function (el) {
      el.open = open
    })
  }
  document.querySelectorAll('.report-toc a[href^="#"]').forEach(function (a) {
    a.addEventListener('click', function () { openTarget(a.getAttribute('href').slice(1)) })
  })
  document.querySelectorAll('[data-toc="expand"]').forEach(function (btn) {
    btn.addEventListener('click', function () { setAllOpen(true) })
  })
  document.querySelectorAll('[data-toc="collapse"]').forEach(function (btn) {
    btn.addEventListener('click', function () { setAllOpen(false) })
  })
  window.addEventListener('hashchange', function () { openTarget(location.hash.slice(1)) })
  if (location.hash) openTarget(location.hash.slice(1))
})()
</` + `script>
`.trim()

export const HTML_REPORT_INTERACTIVE_SCRIPT = `
<script>
(function () {
  var PAGE = 20
  function textOf(el) { return (el && (el.textContent || '')).replace(/\\s+/g, ' ').trim() }
  function parseVal(s) {
    s = String(s || '').trim()
    if (!s || s === '—' || s === '-') return NaN
    var n = Number(s.replace(/[% ,]/g, ''))
    if (!isNaN(n) && /[-+0-9]/.test(s[0] || '')) return n
    var m = s.match(/^(-?[0-9.]+)\\s*(ns|µs|us|ms|s)\\b/i)
    if (!m) return NaN
    var v = Number(m[1]), u = m[2].toLowerCase()
    return v * (u === 's' ? 1e9 : u === 'ms' ? 1e6 : (u === 'us' || u === 'µs') ? 1e3 : 1)
  }
  function enhanceTable(table, idx) {
    if (!table.tHead || !table.tBodies.length) return
    if (table.closest('.kpi-grid, .finding-card, .meta-table, .scope-table')) return
    var tbody = table.tBodies[0]
    var rows = Array.prototype.slice.call(tbody.rows)
    if (!rows.length) return
    var hasProblems = !!table.querySelector('.sev-error, .sev-warning')
    var wrap = document.createElement('div')
    wrap.className = 'table-tools'
    var scroll = document.createElement('div')
    scroll.className = 'table-scroll'
    table.parentNode.insertBefore(wrap, table)
    wrap.appendChild(scroll)
    scroll.appendChild(table)
    var bar = document.createElement('div')
    bar.className = 'table-toolbar'
    bar.innerHTML = '<input type="search" class="table-search" placeholder="Search table…">'
      + (hasProblems ? '<label class="table-check"><input type="checkbox" data-problems> Problems only</label>' : '')
      + '<label class="table-check"><input type="checkbox" data-all> Show all</label>'
      + '<span class="table-count"></span>'
      + '<button type="button" class="table-csv table-action">CSV</button>'
    wrap.insertBefore(bar, scroll)
    var csvBtn = bar.querySelector('.table-csv')
    if (csvBtn) {
      csvBtn.title = 'Download the filtered rows as a CSV file'
    }
    var pager = document.createElement('div')
    pager.className = 'table-pager'
    pager.innerHTML = '<button type="button" data-pg="prev" class="table-action">\\u2039 Prev</button>'
      + '<span data-pg="label"></span>'
      + '<button type="button" data-pg="next" class="table-action">Next \\u203a</button>'
    wrap.appendChild(pager)
    var pgPrev = pager.querySelector('[data-pg="prev"]')
    var pgNext = pager.querySelector('[data-pg="next"]')
    var pgLabel = pager.querySelector('[data-pg="label"]')
    var headTxt = Array.prototype.map.call(
      table.tHead.rows[0].cells, function (th) { return th.textContent })
    var q = '', problems = false, showAll = rows.length <= PAGE, sortCol = -1, sortDir = 1, page = 0
    var lastFiltered = rows
    Array.prototype.forEach.call(table.tHead.rows[0].cells, function (th) {
      th.tabIndex = 0
      th.classList.add('sortable')
      th.addEventListener('click', function () {
        var i = th.cellIndex
        if (sortCol === i) sortDir = -sortDir; else { sortCol = i; sortDir = 1 }
        page = 0; apply()
      })
    })
    function apply() {
      var filtered = rows.filter(function (tr) {
        if (problems && !tr.querySelector('.sev-error, .sev-warning')) return false
        if (q && textOf(tr).toLowerCase().indexOf(q) < 0) return false
        return true
      })
      if (sortCol >= 0) {
        filtered.sort(function (a, b) {
          var av = textOf(a.cells[sortCol]), bv = textOf(b.cells[sortCol])
          var an = parseVal(av), bn = parseVal(bv)
          var cmp = (!isNaN(an) && !isNaN(bn)) ? an - bn : av.localeCompare(bv)
          return cmp * sortDir
        })
      }
      lastFiltered = filtered
      Array.prototype.forEach.call(table.tHead.rows[0].cells, function (th, i) {
        var on = i === sortCol
        th.textContent = headTxt[i] + (on ? (sortDir > 0 ? ' \\u25b2' : ' \\u25bc') : '')
        th.setAttribute('aria-sort', on ? (sortDir > 0 ? 'ascending' : 'descending') : 'none')
      })
      var pages = showAll ? 1 : Math.max(1, Math.ceil(filtered.length / PAGE))
      if (page > pages - 1) page = pages - 1
      if (page < 0) page = 0
      rows.forEach(function (tr) { tr.style.display = 'none' })
      var start = showAll ? 0 : page * PAGE
      var vis = showAll ? filtered : filtered.slice(start, start + PAGE)
      vis.forEach(function (tr) { tbody.appendChild(tr); tr.style.display = '' })
      var count = wrap.querySelector('.table-count')
      count.textContent = filtered.length === rows.length
        ? (vis.length < filtered.length ? vis.length + ' of ' + filtered.length : filtered.length + ' rows')
        : vis.length + ' of ' + filtered.length + ' (filtered)'
      if (!showAll && filtered.length > PAGE) {
        pager.style.display = 'flex'
        pgLabel.textContent = 'Page ' + (page + 1) + ' / ' + pages
        pgPrev.disabled = page <= 0
        pgNext.disabled = page >= pages - 1
        pgPrev.style.opacity = pgPrev.disabled ? '0.4' : '1'
        pgNext.style.opacity = pgNext.disabled ? '0.4' : '1'
      } else {
        pager.style.display = 'none'
      }
    }
    pgPrev.addEventListener('click', function () { if (page > 0) { page -= 1; apply() } })
    pgNext.addEventListener('click', function () { page += 1; apply() })
    bar.querySelector('.table-search').addEventListener('input', function (e) {
      q = String(e.target.value || '').toLowerCase(); page = 0; apply()
    })
    var pb = bar.querySelector('[data-problems]')
    if (pb) pb.addEventListener('change', function (e) { problems = e.target.checked; page = 0; apply() })
    bar.querySelector('[data-all]').addEventListener('change', function (e) {
      showAll = e.target.checked; page = 0; apply()
    })
    if (rows.length <= PAGE) bar.querySelector('[data-all]').checked = true
    if (csvBtn) csvBtn.addEventListener('click', function () {
      function esc(v) {
        v = String(v == null ? '' : v).replace(/\\s+/g, ' ').trim()
        return /["\\r\\n,]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v
      }
      var lines = [headTxt.map(esc).join(',')]
      lastFiltered.forEach(function (tr) {
        lines.push(Array.prototype.map.call(tr.cells, function (td) {
          return esc(textOf(td))
        }).join(','))
      })
      var csv = '\\ufeff' + lines.join('\\r\\n') + '\\r\\n'
      var card = table.closest('details.report-card')
      var sm = card && card.querySelector('summary')
      var name = (sm ? textOf(sm) : '').toLowerCase()
        .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || ('table-' + (idx + 1))
      var a = document.createElement('a')
      a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
      a.download = name + '.csv'
      document.body.appendChild(a)
      a.click()
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove() }, 0)
    })
    apply()
  }
  document.querySelectorAll('details.report-card table').forEach(enhanceTable)
  document.querySelectorAll('.report-tabs').forEach(function (tabs) {
    var btns = tabs.querySelectorAll('[data-tab]')
    var panels = tabs.querySelectorAll('[data-panel]')
    function show(id) {
      btns.forEach(function (b) { b.classList.toggle('active', b.getAttribute('data-tab') === id) })
      panels.forEach(function (p) { p.hidden = p.getAttribute('data-panel') !== id })
    }
    btns.forEach(function (b) {
      b.addEventListener('click', function () { show(b.getAttribute('data-tab')) })
    })
    var first = tabs.querySelector('[data-tab]')
    if (first) show(first.getAttribute('data-tab'))
  })
})()
</` + `script>
`.trim()

const SCOPE_SUFFIX_RE = /\s*\(cursor range[^)]*\)\s*$/i

export function htmlSectionSlug(title) {
  const text = String(title || '').replace(SCOPE_SUFFIX_RE, '').trim()
  const slug = text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  return (slug || 'section').slice(0, 72)
}

function attrValue(attrs, name) {
  const m = String(attrs || '').match(new RegExp('\\b' + name + '="([^"]*)"'))
  return m ? m[1] : ''
}

export function htmlTocNav(entries, groups = null) {
  const items = [...(entries || [])]
  const n = items.length
  const countLabel = n === 1 ? '1 section' : `${n} sections`
  let groupedItems = ''
  if (groups && groups.length) {
    let remaining = items
    const blocks = []
    for (const [groupTitle, prefixes] of groups) {
      const pref = prefixes || []
      const chosen = []
      const keep = []
      for (const item of remaining) {
        if (pref.some(p => String(item.title).startsWith(p))) chosen.push(item)
        else keep.push(item)
      }
      remaining = keep
      if (!chosen.length) continue
      const lis = chosen.map(t => `<li><a href="#${t.id}">${escapeHtml(t.title)}</a></li>`).join('')
      blocks.push(`<div class="toc-group"><h3>${escapeHtml(groupTitle)}</h3><ul>${lis}</ul></div>`)
    }
    if (remaining.length) {
      const lis = remaining.map(t => `<li><a href="#${t.id}">${escapeHtml(t.title)}</a></li>`).join('')
      blocks.push(`<div class="toc-group"><h3>Other</h3><ul>${lis}</ul></div>`)
    }
    groupedItems = `<div class="toc-groups">${blocks.join('')}</div>`
  } else {
    groupedItems = '<ul>' + items.map(t => `<li><a href="#${t.id}">${escapeHtml(t.title)}</a></li>`).join('') + '</ul>'
  }
  return `<nav class="report-toc" aria-label="Table of Contents">`
    + '<div class="report-toc-head">'
    + '<div class="report-toc-title">'
    + '<h2>Table of Contents</h2>'
    + `<span class="toc-count">${escapeHtml(countLabel)}</span>`
    + '</div>'
    + '<div class="report-toc-actions">'
    + '<button type="button" class="toc-btn" data-toc="expand">Expand all</button>'
    + '<button type="button" class="toc-btn" data-toc="collapse">Collapse all</button>'
    + '</div></div>'
    + '<p class="report-toc-lead">Jump to a section below. Expand all opens every card; '
    + 'Collapse all closes them.</p>'
    + `${groupedItems}</nav>`
}

/** Wrap every ``<section class="report-card ...">`` in ``<details>`` and build TOC nav. */
export function htmlMakeCollapsibleSections(docHtml, defaultExpanded = [], tocGroups = null) {
  const prefixes = defaultExpanded || []
  const toc = []
  const used = new Set()
  let counter = 0
  const newDoc = String(docHtml || '').replace(
    /<section class="(report-card[^"]*)"([^>]*)>([\s\S]*?)<\/section>/g,
    (_match, classes, attrs, inner) => {
      const h2Match = inner.match(/<h2[^>]*>[\s\S]*?<\/h2>/)
      const titleHtml = h2Match ? h2Match[0] : '<h2>Section</h2>'
      const titleText = titleHtml.replace(/<[^>]+>/g, '')
      const rest = h2Match ? inner.slice(h2Match.index + h2Match[0].length) : inner
      counter++
      let id = attrValue(attrs, 'id')
      if (!id) {
        const slug = htmlSectionSlug(titleText)
        id = `sec-${slug}`
        let n = 2
        while (used.has(id)) {
          id = `sec-${slug}-${n}`
          n++
        }
      }
      used.add(id)
      toc.push({ id, title: titleText })
      const openAttr = prefixes.some(t => titleText.startsWith(t)) ? ' open' : ''
      const extra = String(attrs || '').replace(/\s*\bid="[^"]*"/, '').trim()
      const extraAttr = extra ? ` ${extra}` : ''
      return `<details class="${classes}" id="${id}"${extraAttr}${openAttr}><summary>${titleHtml}</summary>${rest}</details>`
    },
  )
  if (!toc.length) return { nav: '', html: newDoc }
  return { nav: htmlTocNav(toc, tocGroups), html: newDoc }
}

/** Wrap report cards and inject TOC at ``<!--TOC-->`` (or after the header). */
export function htmlApplyCollapsibleToc(documentHtml, defaultExpanded = [], tocGroups = null) {
  const { nav, html } = htmlMakeCollapsibleSections(documentHtml, defaultExpanded, tocGroups)
  if (!nav) return html
  if (html.includes('<!--TOC-->')) return html.replace('<!--TOC-->', nav)
  return html.replace('</header>', `</header>\n${nav}`)
}
