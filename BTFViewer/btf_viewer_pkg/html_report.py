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
  font-size: 13px;
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
