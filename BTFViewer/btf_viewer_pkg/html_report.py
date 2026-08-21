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
PRODUCT_TAGLINE = "AI assistant for RTOS trace analysis — find evidence and explain"


def app_icon_svg_markup(size: int = 48) -> str:
    """Embedded app icon SVG scaled for HTML headers (no external file)."""
    sz = max(16, int(size))
    out = APP_ICON_SVG
    out = re.sub(r'\bwidth="\d+"', f'width="{sz}"', out, count=1)
    out = re.sub(r'\bheight="\d+"', f'height="{sz}"', out, count=1)
    return out


_BTF_HTML_REPORT_CSS = """
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
        "</header>\n"
        f"{body_html}\n"
        "<footer class=\"report-foot\">\n"
        f"Generated by {html.escape(PRODUCT_NAME)} {html.escape(APP_VERSION)} — "
        f"{html.escape(PRODUCT_TAGLINE)}\n"
        "</footer>\n"
        "</div>\n"
        "</body>\n"
        "</html>\n"
    )


HTML_REPORT_TOC_CSS = """
.report-toc {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px 14px;
  margin: 14px 0;
  box-shadow: 0 2px 10px rgba(30, 60, 90, 0.06);
}
.report-toc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin: 0 0 8px 0;
}
.report-toc h2 { margin: 0; }
.report-toc-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.toc-btn {
  font: inherit;
  font-size: 12px;
  padding: 4px 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: #f1f5fb;
  color: var(--accent);
  cursor: pointer;
}
.toc-btn:hover { background: #e4edf8; }
.report-toc ul { margin: 0; padding: 0 0 0 18px; columns: 2; column-gap: 24px; }
.report-toc li { margin: 4px 0; }
.report-toc a { color: var(--accent); text-decoration: none; }
.report-toc a:hover { text-decoration: underline; }
.toc-groups { display: grid; gap: 10px; }
.toc-group h3 {
  margin: 8px 0 4px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted);
}
.toc-group ul { columns: 1; padding-left: 16px; }
@media (min-width: 720px) {
  .toc-groups { grid-template-columns: 1fr 1fr; }
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
    document.querySelectorAll('details.report-card').forEach(function (el) {
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
  function csvEscape(v) { return /[",\\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
  function downloadCsv(name, rows) {
    var csv = rows.map(function (r) { return r.map(csvEscape).join(','); }).join('\\n');
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 500);
  }
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
    bar.innerHTML = '<input type="search" class="table-search" placeholder="Search table…">'
      + (hasProblems ? '<label class="table-check"><input type="checkbox" data-problems> Problems only</label>' : '')
      + '<label class="table-check"><input type="checkbox" data-all> Show all</label>'
      + '<button type="button" class="toc-btn" data-csv>CSV</button>'
      + '<span class="table-count"></span>';
    wrap.insertBefore(bar, scroll);
    var q = '', problems = false, showAll = rows.length <= PAGE, sortCol = -1, sortDir = 1, page = 0;
    Array.prototype.forEach.call(table.tHead.rows[0].cells, function (th, i) {
      th.tabIndex = 0;
      th.classList.add('sortable');
      th.addEventListener('click', function () {
        if (sortCol === i) sortDir = -sortDir; else { sortCol = i; sortDir = 1; }
        apply();
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
      rows.forEach(function (tr) { tr.style.display = 'none'; });
      var start = showAll ? 0 : page * PAGE;
      var vis = showAll ? filtered : filtered.slice(start, start + PAGE);
      vis.forEach(function (tr) { tbody.appendChild(tr); tr.style.display = ''; });
      var count = wrap.querySelector('.table-count');
      count.textContent = filtered.length === rows.length
        ? (vis.length < filtered.length ? vis.length + ' of ' + filtered.length : filtered.length + ' rows')
        : vis.length + ' of ' + filtered.length + ' (filtered)';
    }
    bar.querySelector('.table-search').addEventListener('input', function (e) {
      q = String(e.target.value || '').toLowerCase(); page = 0; apply();
    });
    var pb = bar.querySelector('[data-problems]');
    if (pb) pb.addEventListener('change', function (e) { problems = e.target.checked; page = 0; apply(); });
    bar.querySelector('[data-all]').addEventListener('change', function (e) {
      showAll = e.target.checked; page = 0; apply();
    });
    if (rows.length <= PAGE) bar.querySelector('[data-all]').checked = true;
    bar.querySelector('[data-csv]').addEventListener('click', function () {
      var head = Array.prototype.map.call(table.tHead.rows[0].cells, textOf);
      var body = rows.filter(function (tr) { return tr.style.display !== 'none'; })
        .map(function (tr) { return Array.prototype.map.call(tr.cells, textOf); });
      downloadCsv('statistics-table-' + (idx + 1) + '.csv', [head].concat(body));
    });
    apply();
  }
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
    grouped_items = ""
    if groups:
        remaining = list(entries or [])
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
            for sec_id, title in (entries or [])
        ) + "</ul>"
    return (
        '<nav class="report-toc"><div class="report-toc-head">'
        "<h2>Table of Contents</h2>"
        '<div class="report-toc-actions">'
        '<button type="button" class="toc-btn" data-toc="expand">Expand all</button>'
        '<button type="button" class="toc-btn" data-toc="collapse">Collapse all</button>'
        "</div></div>"
        f"{grouped_items}</nav>"
    )


def html_make_collapsible_sections(
    doc_html: str,
    default_expanded: tuple = (),
    toc_groups=None,
) -> tuple:
    """Wrap every ``<section class="report-card ...">`` in ``<details>``
    and build a table-of-contents nav. Returns ``(nav_html, new_doc_html)``.
    """
    prefixes = tuple(default_expanded or ())
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
        open_attr = " open" if prefixes and title_text.startswith(prefixes) else ""
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
