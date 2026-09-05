#!/usr/bin/env python3
"""Pre-render STATISTICS.md into HTML for both Desktop and Web Statistics
Reference viewers. English only — STATISTICS_zh-TW.md isn't kept in sync
with the app and isn't converted.

No markdown parsing, mermaid rendering, or math typesetting happens at
app runtime — both platforms load pre-built HTML. Screenshot images are
dropped (the live app is right there — a help viewer doesn't need a
snapshot of it, and they were the entire reason an earlier version of
this file ballooned to 16+ MB). Mermaid diagrams stay: they're workflow
diagrams, not app screenshots, and are small (rendered SVG, not photos).

GitHub renders ```math fences as LaTeX (KaTeX); MarkdownIt has no idea
what a "math" fence is and would otherwise emit a plain <pre><code> block
showing raw LaTeX source. scripts/render_math.mjs (MathJax, SVG output,
a shared glyph <defs> instead of per-formula paths or KaTeX's font
files) fixes that the same way mermaid is handled: rendered once at
build time, inlined as plain SVG.

Two output copies, because the two platforms load documents differently:

- Desktop (QWebEngineView.setHtml(...)) reads the text of a single file
  next to btf_viewer.py: BTFViewer/builds/btf_viewer.hlp. A single file,
  not a docs_html/ folder, so a release can be just btf_viewer.py +
  btf_viewer.hlp copied anywhere — no BTFViewer/ package layout needed.

- Web ships as ONE self-contained HTML file (vite-plugin-singlefile,
  see web/vite.config.js) with no server and no guaranteed sibling
  files at runtime, so its copy is imported as a raw JS string
  (`?raw`) and rendered via <iframe srcdoc>:
  web/src/generated/statistics-en.inline.html.

Requires (build-time only, not an app runtime dependency):
    pip install markdown-it-py
    mmdc (mermaid-cli) on PATH, e.g. `npm install -g @mermaid-js/mermaid-cli`
    node, and `cd scripts && npm install` (installs mathjax-full; see
    scripts/package.json — a separate, build-tools-only node_modules,
    not web/'s)

Usage:
    python3 scripts/build_docs_html.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from markdown_it import MarkdownIt

SCRIPT_DIR = Path(__file__).resolve().parent
BTF_ROOT = SCRIPT_DIR.parents[0]
DESKTOP_OUT_PATH = BTF_ROOT / "builds" / "btf_viewer.hlp"
WEB_OUT_PATH = BTF_ROOT / "web" / "src" / "generated" / "statistics-en.inline.html"
SOURCE_MD = BTF_ROOT / "STATISTICS.md"
RENDER_MATH_JS = SCRIPT_DIR / "render_math.mjs"

_MERMAID_RE = re.compile(r"```mermaid\n(.*?)\n```\n?", re.DOTALL)
_MATH_RE = re.compile(r"```math\n(.*?)\n```\n?", re.DOTALL)
_MATH_SLOT_RE = re.compile(r'<div class="math-slot" data-math-index="(\d+)"></div>')
_IMG_RE = re.compile(r"<img\b[^>]*>")

_CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
]


def _find_chrome() -> str | None:
    for cand in _CHROME_CANDIDATES:
        if Path(cand).is_file():
            return cand
    return None


def _render_mermaid_to_svg(src: str) -> str:
    """Render one mermaid diagram to an inline <svg> via mermaid-cli."""
    with tempfile.TemporaryDirectory() as td:
        mmd = Path(td) / "d.mmd"
        svg = Path(td) / "d.svg"
        mmd.write_text(src, encoding="utf-8")
        cmd = ["mmdc", "-i", str(mmd), "-o", str(svg), "-b", "transparent", "-t", "dark"]
        chrome = _find_chrome()
        if chrome:
            cfg = Path(td) / "puppeteer-config.json"
            cfg.write_text(f'{{"executablePath": {chrome!r}}}'.replace("'", '"'), encoding="utf-8")
            cmd += ["-p", str(cfg)]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return svg.read_text(encoding="utf-8")


def _extract_mermaid(text: str) -> tuple[str, list[str]]:
    """Replace ```mermaid blocks with placeholders; return (text, svgs)."""
    svgs: list[str] = []

    def _sub(m: re.Match) -> str:
        svgs.append(_render_mermaid_to_svg(m.group(1)))
        return f"\n<div class=\"mermaid-slot\" data-mermaid-index=\"{len(svgs) - 1}\"></div>\n\n"

    return _MERMAID_RE.sub(_sub, text), svgs


def _inline_mermaid(html: str, svgs: list[str]) -> str:
    def _sub(m: re.Match) -> str:
        idx = int(m.group(1))
        return f'<div class="mermaid-diagram">{svgs[idx]}</div>'

    return re.sub(
        r'<div class="mermaid-slot" data-mermaid-index="(\d+)"></div>',
        _sub, html,
    )


def _extract_math(text: str) -> tuple[str, list[str]]:
    """Replace ```math blocks with placeholders; return (text, formulas).

    GitHub renders ```math as LaTeX display math (KaTeX); MarkdownIt has no
    idea what a "math" fence is and would otherwise emit a plain
    <pre><code class="language-math"> block showing the raw LaTeX source.
    """
    formulas: list[str] = []

    def _sub(m: re.Match) -> str:
        formulas.append(m.group(1))
        return f'\n<div class="math-slot" data-math-index="{len(formulas) - 1}"></div>\n\n'

    return _MATH_RE.sub(_sub, text), formulas


def _render_math(formulas: list[str]) -> dict:
    """Render LaTeX formulas to self-contained SVG via MathJax (Node).

    A shared glyph <defs> (MathJax's "global" font cache) is emitted once
    and each formula becomes a small <mjx-container> that <use>-references
    it — far lighter than KaTeX's HTML+webfonts route, and unlike a
    'local' cache, glyph paths aren't repeated per formula.
    """
    proc = subprocess.run(
        ["node", str(RENDER_MATH_JS)],
        input=json.dumps(formulas), capture_output=True, text=True, check=True,
    )
    return json.loads(proc.stdout)


def _inline_math(html: str, math_data: dict) -> str:
    def _sub(m: re.Match) -> str:
        svg = math_data["formulas"][int(m.group(1))]
        return f'<div class="math-block">{svg}</div>'

    return _MATH_SLOT_RE.sub(_sub, html)


def _strip_images(html: str) -> str:
    """Drop every <img> — screenshots of the app aren't needed in a viewer
    that opens from inside the app itself; the decorative heading icons
    (../images/readme/h*.svg) are pure noise without a server to resolve
    them against. Mermaid diagrams are unaffected (inlined <svg>, not <img>)."""
    return _IMG_RE.sub("", html)


_PAGE_TEMPLATE = """<!doctype html>
<html data-theme="dark">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
:root {{
  --bg: #1E1E1E;
  --panel-bg: #252526;
  --border: #3C3C3C;
  --fg: #D4D4D4;
  --fg-dim: #858585;
  --accent: #4F8BFF;
  --code-bg: #2D2D2D;
  --font-ui: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}}
html[data-theme="light"] {{
  --bg: #FFFFFF;
  --panel-bg: #F5F5F5;
  --border: #DDDDDD;
  --fg: #1E1E1E;
  --fg-dim: #666666;
  --accent: #0066CC;
  --code-bg: #EEEEEE;
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}
body {{
  background: var(--bg);
  color: var(--fg);
  font-family: var(--font-ui);
  font-size: 13.5px;
  line-height: 1.65;
  padding: 28px 34px 80px;
  max-width: 860px;
}}
a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
h1, h2, h3, h4 {{ color: var(--fg); font-weight: 700; line-height: 1.3; }}
h1 {{ font-size: 22px; margin: 0 0 14px; }}
h2 {{ font-size: 18px; margin: 40px 0 14px; padding-top: 18px; border-top: 1px solid var(--border); }}
h2:first-of-type {{ border-top: none; padding-top: 0; }}
h3 {{ font-size: 15.5px; margin: 30px 0 10px; }}
p {{ margin: 0 0 14px; color: #C7C7C7; }}
html[data-theme="light"] p {{ color: #333; }}
code {{
  font-family: var(--font-mono);
  font-size: 12px;
  background: var(--code-bg);
  border-radius: 4px;
  padding: 1px 5px;
}}
pre {{ background: var(--code-bg); border-radius: 8px; padding: 12px 14px; overflow-x: auto; }}
pre code {{ background: none; padding: 0; }}
table {{ border-collapse: collapse; width: 100%; margin: 0 0 18px; font-size: 12.5px; }}
th, td {{ border: 1px solid var(--border); padding: 6px 10px; text-align: left; vertical-align: top; }}
th {{ background: var(--panel-bg); font-weight: 700; }}
.mermaid-diagram {{ margin: 0 0 18px; }}
.mermaid-diagram svg {{ max-width: 100%; height: auto; }}
.math-block {{ overflow-x: auto; margin: 0 0 18px; }}
mjx-container[jax="SVG"] {{ color: inherit; }}
blockquote {{
  margin: 0 0 14px;
  padding: 6px 14px;
  border-left: 3px solid var(--border);
  color: var(--fg-dim);
}}
hr {{ border: none; border-top: 1px solid var(--border); margin: 30px 0; }}
</style>
{math_style}
</head>
<body>
{math_defs}
{body}
<script>
window.__setDocTheme = function (t) {{
  document.documentElement.setAttribute('data-theme', t === 'light' ? 'light' : 'dark');
}};
</script>
</body>
</html>
"""


def build() -> list[Path]:
    text = SOURCE_MD.read_text(encoding="utf-8")
    text, mermaid_svgs = _extract_mermaid(text)
    text, math_formulas = _extract_math(text)

    md = MarkdownIt("commonmark").enable("table")
    html_body = md.render(text)
    html_body = _inline_mermaid(html_body, mermaid_svgs)

    math_style = ""
    math_defs = ""
    if math_formulas:
        math_data = _render_math(math_formulas)
        html_body = _inline_math(html_body, math_data)
        math_style = math_data["style"]
        math_defs = (
            '<svg aria-hidden="true" style="position:absolute;width:0;height:0" '
            f'xmlns="http://www.w3.org/2000/svg">{math_data["defs"]}</svg>'
        )
    html_body = _strip_images(html_body)

    page = _PAGE_TEMPLATE.format(
        title="BTFViewer Statistics Reference", body=html_body,
        math_style=math_style, math_defs=math_defs,
    )
    written: list[Path] = []

    DESKTOP_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DESKTOP_OUT_PATH.write_text(page, encoding="utf-8")
    written.append(DESKTOP_OUT_PATH)

    WEB_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEB_OUT_PATH.write_text(page, encoding="utf-8")
    written.append(WEB_OUT_PATH)

    return written


def main() -> int:
    if not SOURCE_MD.is_file():
        print(f"warning: missing source {SOURCE_MD}", file=sys.stderr)
        return 1
    for out_path in build():
        size_kb = out_path.stat().st_size / 1024
        print(f"wrote {out_path.relative_to(BTF_ROOT)} ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
