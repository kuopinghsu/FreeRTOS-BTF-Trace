/**
 * Shared HTML report chrome for BTFViewer exports (Web).
 * Keep in sync with btf_viewer_pkg/html_report.py.
 */

export const APP_VERSION = '1.4.0'
export const PRODUCT_NAME = 'BTFViewer'
export const PRODUCT_TAGLINE = 'AI assistant for RTOS trace analysis — find evidence and explain'

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
  --bg: #e9edf3;
  --paper: #ffffff;
  --ink: #182230;
  --muted: #5f6f82;
  --line: #d9e0ea;
  --header: #16324f;
  --accent: #2a6fb2;
  --user-bar: #5b9bd5;
  --asst-bar: #3d9a72;
  --user-bg: #eef5fc;
  --asst-bg: #eef7f2;
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
  border-radius: 12px;
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
  background: #f1f5fb;
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
  background: #f1f5fb;
  color: #284563;
}
table.ai-md-table td {
  background: #fff;
  color: var(--ink);
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  background: #e8eef7;
  color: #123355;
  font-size: 12px;
  font-weight: 650;
  margin-right: 6px;
}
.badge-status { background: #dfe9f8; }
.badge-ok { background: #d9f0e3; color: #1f6b45; }
.badge-warn { background: #fce8c8; color: #8a4b00; }
.warn-banner {
  background: #fff6e8;
  border: 1px solid #f0d2a0;
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
  background: #f8fafc;
}
details.report-appendix > summary {
  cursor: pointer;
  font-weight: 650;
  color: #123355;
}
.appendix-body { margin-top: 8px; }
.export-note { color: var(--muted); font-size: 12px; margin-top: 12px; }
@media print {
  details.report-appendix { break-inside: avoid; }
  .report-card { break-inside: avoid; }
}
.report-foot {
  margin-top: 18px;
  padding-top: 10px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 11px;
  text-align: center;
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
</header>
${bodyHtml}
<footer class="report-foot">
Generated by ${escapeHtml(PRODUCT_NAME)} ${escapeHtml(APP_VERSION)} — ${escapeHtml(PRODUCT_TAGLINE)}
</footer>
</div>
</body>
</html>
`
}
