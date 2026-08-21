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


def html_toc_nav(entries) -> str:
    """Table of Contents nav with Expand all / Collapse all."""
    items = "".join(
        f'<li><a href="#{sec_id}">{title}</a></li>'
        for sec_id, title in (entries or [])
    )
    return (
        '<nav class="report-toc"><div class="report-toc-head">'
        "<h2>Table of Contents</h2>"
        '<div class="report-toc-actions">'
        '<button type="button" class="toc-btn" data-toc="expand">Expand all</button>'
        '<button type="button" class="toc-btn" data-toc="collapse">Collapse all</button>'
        "</div></div>"
        f"<ul>{items}</ul></nav>"
    )


def html_make_collapsible_sections(
    doc_html: str,
    default_expanded: tuple = (),
) -> tuple:
    """Wrap every ``<section class="report-card ...">`` in ``<details>``
    and build a table-of-contents nav. Returns ``(nav_html, new_doc_html)``.
    """
    prefixes = tuple(default_expanded or ())
    toc_entries: list = []
    counter = 0

    def _wrap(m: "re.Match") -> str:
        nonlocal counter
        classes, inner = m.group(1), m.group(2)
        h2_m = re.search(r"<h2[^>]*>.*?</h2>", inner, re.S)
        if h2_m:
            title_html = h2_m.group(0)
            title_text = re.sub(r"<[^>]+>", "", title_html)
            rest = inner[h2_m.end():]
        else:
            title_html, title_text, rest = "<h2>Section</h2>", "Section", inner
        counter += 1
        sec_id = f"sec-{counter}"
        toc_entries.append((sec_id, title_text))
        open_attr = " open" if prefixes and title_text.startswith(prefixes) else ""
        return (
            f'<details class="{classes}" id="{sec_id}"{open_attr}>'
            f"<summary>{title_html}</summary>{rest}</details>"
        )

    new_doc = re.sub(
        r'<section class="(report-card[^"]*)">(.*?)</section>',
        _wrap, doc_html, flags=re.S,
    )
    if not toc_entries:
        return "", new_doc
    return html_toc_nav(toc_entries), new_doc


def html_apply_collapsible_toc(
    document_html: str,
    *,
    default_expanded: tuple = (),
) -> str:
    """Wrap report cards, inject TOC at ``<!--TOC-->`` (or after the header)."""
    nav, doc = html_make_collapsible_sections(document_html, default_expanded)
    if not nav:
        return doc
    if "<!--TOC-->" in doc:
        return doc.replace("<!--TOC-->", nav, 1)
    return doc.replace("</header>", "</header>\n" + nav, 1)
