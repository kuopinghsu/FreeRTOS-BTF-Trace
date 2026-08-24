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

export const HTML_REPORT_TOC_CSS = `
.report-toc {
  background: linear-gradient(180deg, #ffffff 0%, #f7f9fc 100%);
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
  background: #eef3f9;
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
  background: #fff;
  color: var(--accent);
  cursor: pointer;
  box-shadow: 0 1px 2px rgba(30, 60, 90, 0.04);
}
.toc-btn:hover { background: #eef4fb; border-color: #c5d4e6; }
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
  color: #1a4f80;
  text-decoration: none;
  font-size: 13px;
  line-height: 1.35;
}
.report-toc a:hover { color: var(--accent); text-decoration: underline; }
.toc-groups { display: grid; gap: 12px; }
.toc-group {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px 12px 12px;
  box-shadow: 0 1px 3px rgba(30, 60, 90, 0.04);
}
.toc-group h3 {
  margin: 0 0 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid #e8eef5;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #5f6f82;
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
  function csvEscape(v) { return /[",\\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v }
  function downloadCsv(name, rows) {
    var csv = rows.map(function (r) { return r.map(csvEscape).join(',') }).join('\\n')
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    var a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = name
    a.click()
    setTimeout(function () { URL.revokeObjectURL(a.href) }, 500)
  }
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
    wrap.insertBefore(bar, scroll)
    var q = '', problems = false, showAll = rows.length <= PAGE, sortCol = -1, sortDir = 1, page = 0
    Array.prototype.forEach.call(table.tHead.rows[0].cells, function (th) {
      th.tabIndex = 0
      th.classList.add('sortable')
      th.addEventListener('click', function () {
        var i = th.cellIndex
        if (sortCol === i) sortDir = -sortDir; else { sortCol = i; sortDir = 1 }
        apply()
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
      rows.forEach(function (tr) { tr.style.display = 'none' })
      var start = showAll ? 0 : page * PAGE
      var vis = showAll ? filtered : filtered.slice(start, start + PAGE)
      vis.forEach(function (tr) { tbody.appendChild(tr); tr.style.display = '' })
      var count = wrap.querySelector('.table-count')
      count.textContent = filtered.length === rows.length
        ? (vis.length < filtered.length ? vis.length + ' of ' + filtered.length : filtered.length + ' rows')
        : vis.length + ' of ' + filtered.length + ' (filtered)'
    }
    bar.querySelector('.table-search').addEventListener('input', function (e) {
      q = String(e.target.value || '').toLowerCase(); page = 0; apply()
    })
    var pb = bar.querySelector('[data-problems]')
    if (pb) pb.addEventListener('change', function (e) { problems = e.target.checked; page = 0; apply() })
    bar.querySelector('[data-all]').addEventListener('change', function (e) {
      showAll = e.target.checked; page = 0; apply()
    })
    if (rows.length <= PAGE) bar.querySelector('[data-all]').checked = true
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
