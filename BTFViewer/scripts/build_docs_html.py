#!/usr/bin/env python3
"""Pre-render STATISTICS.md and STATISTICS_zh-TW.md into HTML for both
Desktop and Web Statistics Reference viewers.

Each language becomes its own complete, independent HTML document — not
one merged document toggled by CSS (the theme is; language isn't). Both
language files share the exact same anchor ids (id="statistics-cores"
etc.), so two documents merged into one DOM would collide: whichever
language's copy of an id came first in the DOM would always win, breaking
navigation for the other. Keeping documents separate and swapping which
one is loaded (setHtml() on desktop, :srcdoc on web) sidesteps that
entirely — see stats_reference.py / StatsReferenceViewer.vue.

Mermaid diagrams are fully translated between the two source files (not
just prose), so they're rendered per-language; the ```math formulas are
byte-identical (LaTeX notation isn't prose), so they're rendered once and
reused for both — see _build_one()'s math_cache parameter.

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

Two output copies, because the two platforms load documents differently —
both hold the SAME content though: a JSON object {"en": "<!doctype ...",
"zh-tw": "<!doctype ..."}, one full HTML document string per language:

- Desktop (QWebEngineView.setHtml(...)) reads the text of a single file
  next to btf_viewer.py: BTFViewer/builds/btf_viewer.hlp, json.loads() it,
  and setHtml()s whichever language is selected. A single file, not a
  docs_html/ folder, so a release can be just btf_viewer.py + btf_viewer.hlp
  copied anywhere — no BTFViewer/ package layout needed.

- Web ships as ONE self-contained HTML file (vite-plugin-singlefile,
  see web/vite.config.js) with no server and no guaranteed sibling
  files at runtime, so its copy is imported as a raw JS string (`?raw`),
  JSON.parse()d, and rendered via <iframe :srcdoc="doc[lang]">:
  web/src/generated/statistics-en.inline.html (filename kept for git-diff
  continuity even though it now holds both languages).

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
LANGS: dict[str, Path] = {
    "en": BTF_ROOT / "STATISTICS.md",
    "zh-tw": BTF_ROOT / "STATISTICS_zh-TW.md",
}
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


# Mermaid's default edgeLabel background is a fixed mid-grey regardless of
# theme, at 50% opacity over whatever is behind it — a visible grey patch
# on a light page, and a muddy grey-on-grey blend with light edge-label
# text on a dark one. Overriding it to the page's own --bg per theme makes
# the label read as floating directly on the line (the box is invisible,
# since it's an exact color match) instead of an odd disconnected chip.
# lineColor is likewise repointed to the page's own --fg-dim so arrows
# have real contrast instead of mermaid's default. Keep in sync with
# _PAGE_TEMPLATE's :root / html[data-theme="light"] --bg / --fg-dim.
_MERMAID_THEME_VARS = {
    "dark": {"edgeLabelBackground": "#1E1E1E", "lineColor": "#858585"},
    "default": {"edgeLabelBackground": "#FFFFFF", "lineColor": "#666666"},
}


def _render_mermaid_to_svg(src: str, theme: str, svg_id: str) -> str:
    """Render one mermaid diagram to an inline <svg> via mermaid-cli.

    Node fills/text/line colors are baked into the SVG at *this* theme —
    mermaid has no runtime CSS-variable hook for it — so a diagram rendered
    once at build time would stay stuck in whichever theme it was rendered
    at, even after the page's own data-theme is switched at runtime. Called
    twice (dark + light) so both are shipped and the right one is picked at
    runtime — see _inline_mermaid()'s CSS toggle.

    ``svg_id`` MUST be unique across every call in one build: mmdc scopes
    each SVG's embedded <style> to its own element id, but always uses the
    same default id ("my-svg") unless told otherwise — with several such
    SVGs on one page, their same-id style blocks collide and the LAST one
    in the document silently wins for ALL of them (e.g. every diagram's
    edge-label colors flip to whichever diagram happens to render last).
    """
    with tempfile.TemporaryDirectory() as td:
        mmd = Path(td) / "d.mmd"
        svg = Path(td) / "d.svg"
        mmd.write_text(src, encoding="utf-8")
        mermaid_cfg = Path(td) / "mermaid-config.json"
        mermaid_cfg.write_text(
            json.dumps({"theme": theme, "themeVariables": _MERMAID_THEME_VARS[theme]}),
            encoding="utf-8",
        )
        cmd = [
            "mmdc", "-i", str(mmd), "-o", str(svg), "-b", "transparent",
            "-t", theme, "-c", str(mermaid_cfg), "-I", svg_id,
        ]
        chrome = _find_chrome()
        if chrome:
            cfg = Path(td) / "puppeteer-config.json"
            cfg.write_text(f'{{"executablePath": {chrome!r}}}'.replace("'", '"'), encoding="utf-8")
            cmd += ["-p", str(cfg)]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return svg.read_text(encoding="utf-8")


def _extract_mermaid(text: str, lang: str) -> tuple[str, list[tuple[str, str]]]:
    """Replace ```mermaid blocks with placeholders; return (text, [(dark, light), ...]).

    ``lang`` is folded into each SVG's id so the two languages' diagrams
    never collide even though this function runs once per language build
    (mermaid diagrams are fully translated, not shared — see module
    docstring), and so ids stay unique when both language documents are
    ever present in the same runtime page.
    """
    svgs: list[tuple[str, str]] = []

    def _sub(m: re.Match) -> str:
        src = m.group(1)
        idx = len(svgs)
        svgs.append((
            _render_mermaid_to_svg(src, "dark", f"mermaid-{lang}-{idx}-dark"),
            _render_mermaid_to_svg(src, "default", f"mermaid-{lang}-{idx}-light"),
        ))
        return f"\n<div class=\"mermaid-slot\" data-mermaid-index=\"{idx}\"></div>\n\n"

    return _MERMAID_RE.sub(_sub, text), svgs


def _inline_mermaid(html: str, svgs: list[tuple[str, str]]) -> str:
    def _sub(m: re.Match) -> str:
        idx = int(m.group(1))
        dark_svg, light_svg = svgs[idx]
        return (
            f'<div class="mermaid-diagram mermaid-diagram--dark">{dark_svg}</div>'
            f'<div class="mermaid-diagram mermaid-diagram--light">{light_svg}</div>'
        )

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


_SECTION_ANCHOR_RE = re.compile(r'<a id="statistics-([\w-]+)"')
_H3_RE = re.compile(r"<h3>(.*?)</h3>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _add_subsection_ids(html: str) -> tuple[str, dict]:
    """Assign ``id="statistics-<section>-<slug>"`` to every genuine <h3>
    sub-heading and collect a ``{section_id: [{id, title}, ...]}`` map, so
    the TOC can offer sub-navigation within a section instead of only
    jumping to its top.

    Position-based, not a real DOM walk: <h3>s are attributed to the
    nearest preceding ``<a id="statistics-...">`` section marker — those
    markers are hand-authored right before each STATISTICS.md heading and
    pass through MarkdownIt as raw HTML, so their order in the rendered
    output matches source order. Each section's own *title* is itself an
    <h3> (STATISTICS.md uses h3 for section titles, not h2) — the first h3
    seen right after a section's anchor is that title, not a sub-heading,
    and is left untouched.
    """
    section_markers = list(_SECTION_ANCHOR_RE.finditer(html))
    subsections: dict = {}
    seen_slugs: dict = {}
    title_seen: set = set()

    def _section_at(pos: int) -> str:
        current = ""
        for m in section_markers:
            if m.start() > pos:
                break
            current = m.group(1)
        return current

    def _sub(m: re.Match) -> str:
        section_id = _section_at(m.start())
        title_html = m.group(1)
        if not section_id:
            return m.group(0)
        if section_id not in title_seen:
            title_seen.add(section_id)  # this h3 is the section's own title
            return m.group(0)
        title_text = _TAG_RE.sub("", title_html).strip()
        slug = _SLUG_RE.sub("-", title_text.lower()).strip("-")
        if not slug:
            # _SLUG_RE only keeps a-z0-9, so a CJK title (STATISTICS_zh-TW.md)
            # strips to nothing — fall back to a position-based slug instead
            # of silently dropping the sub-heading from TOC navigation.
            slug = f"sub{sum(len(v) for v in subsections.values()) + 1}"
        key = f"{section_id}-{slug}"
        n = seen_slugs.get(key, 0)
        seen_slugs[key] = n + 1
        sub_id = key if n == 0 else f"{key}-{n}"
        subsections.setdefault(section_id, []).append({"id": sub_id, "title": title_text})
        return f'<h3 id="statistics-{sub_id}">{title_html}</h3>'

    return _H3_RE.sub(_sub, html), subsections


# Headings get a color of their own (not --accent, the link color) so they
# don't read as clickable. Each level has its own hue, matching the per-level
# palette the PDF manuals use (scripts/heading-color.tex): h1=blue,
# h2=violet, h3=teal, h4=pink, h5=orange. The light-theme values are
# identical to the PDF; the dark-theme values are lighter tints of the same
# hues, tuned for the #1E1E1E page background.
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
  --h1: #7FA9FF;
  --h2: #C4A5F5;
  --h3: #5ED9C9;
  --h4: #F79BC4;
  --h5: #F0A97A;
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
  --h1: #1D4ED8;
  --h2: #7C3AED;
  --h3: #0F766E;
  --h4: #DB2777;
  --h5: #C2410C;
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
h1, h2, h3, h4, h5 {{ font-weight: 700; line-height: 1.3; }}
h1 {{ color: var(--h1); font-size: 22px; margin: 0 0 14px; }}
h2 {{ color: var(--h2); font-size: 18px; margin: 40px 0 14px; padding-top: 18px; border-top: 1px solid var(--border); }}
h2:first-of-type {{ border-top: none; padding-top: 0; }}
h3 {{ color: var(--h3); font-size: 15.5px; margin: 30px 0 10px; }}
h4 {{ color: var(--h4); font-size: 13.5px; margin: 24px 0 8px; }}
h5 {{ color: var(--h5); font-size: 13.5px; margin: 20px 0 8px; }}
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
/* Each diagram ships as two pre-rendered SVGs (see _render_mermaid_to_svg
   in build_docs_html.py) since mermaid bakes its theme's colors into the
   SVG at render time — only one can match html[data-theme] at once. */
.mermaid-diagram--light {{ display: none; }}
html[data-theme="light"] .mermaid-diagram--dark {{ display: none; }}
html[data-theme="light"] .mermaid-diagram--light {{ display: block; }}
.math-block {{ overflow-x: auto; margin: 0 0 18px; }}
mjx-container[jax="SVG"] {{ color: inherit; }}
blockquote {{
  margin: 0 0 14px;
  padding: 6px 14px;
  border-left: 3px solid var(--border);
  color: var(--fg-dim);
}}
hr {{ border: none; border-top: 1px solid var(--border); margin: 30px 0; }}
h3[id] {{ scroll-margin-top: 12px; }}
</style>
{math_style}
</head>
<body>
{math_defs}
{body}
<script type="application/json" id="statistics-subsections">{subsections_json}</script>
<script>
window.__setDocTheme = function (t) {{
  document.documentElement.setAttribute('data-theme', t === 'light' ? 'light' : 'dark');
}};
</script>
</body>
</html>
"""


_PAGE_TITLES = {
    "en": "BTFViewer Statistics Reference",
    "zh-tw": "BTFViewer 統計參考手冊",
}


def _build_one(source_md: Path, lang: str, math_cache: dict | None) -> tuple[str, dict | None]:
    """Render one language's STATISTICS*.md into a complete HTML page.

    ``math_cache`` is the already-rendered {"style", "defs", "formulas"}
    dict from a prior language's call, or None on the first call — math
    formulas are byte-identical across languages (LaTeX notation isn't
    prose), so they're rendered once and reused rather than re-invoking
    Node/MathJax a second time. Returns (page_html, math_cache) so the
    caller can thread the cache into the next language's call.
    """
    text = source_md.read_text(encoding="utf-8")
    text, mermaid_svgs = _extract_mermaid(text, lang)
    text, math_formulas = _extract_math(text)

    md = MarkdownIt("commonmark").enable("table")
    html_body = md.render(text)
    html_body = _inline_mermaid(html_body, mermaid_svgs)

    math_style = ""
    math_defs = ""
    if math_formulas:
        if math_cache is None:
            math_cache = _render_math(math_formulas)
        html_body = _inline_math(html_body, math_cache)
        math_style = math_cache["style"]
        math_defs = (
            '<svg aria-hidden="true" style="position:absolute;width:0;height:0" '
            f'xmlns="http://www.w3.org/2000/svg">{math_cache["defs"]}</svg>'
        )
    html_body = _strip_images(html_body)
    html_body, subsections = _add_subsection_ids(html_body)
    subsections_json = json.dumps(subsections, ensure_ascii=False).replace("</script", "<\\/script")

    page = _PAGE_TEMPLATE.format(
        title=_PAGE_TITLES[lang], body=html_body,
        math_style=math_style, math_defs=math_defs,
        subsections_json=subsections_json,
    )
    return page, math_cache


def build() -> list[Path]:
    pages: dict[str, str] = {}
    math_cache: dict | None = None
    for lang, source_md in LANGS.items():
        page, math_cache = _build_one(source_md, lang, math_cache)
        pages[lang] = page

    envelope = json.dumps(pages, ensure_ascii=False)
    written: list[Path] = []

    DESKTOP_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DESKTOP_OUT_PATH.write_text(envelope, encoding="utf-8")
    written.append(DESKTOP_OUT_PATH)

    WEB_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEB_OUT_PATH.write_text(envelope, encoding="utf-8")
    written.append(WEB_OUT_PATH)

    return written


def main() -> int:
    missing = [str(p) for p in LANGS.values() if not p.is_file()]
    if missing:
        print(f"warning: missing source(s): {', '.join(missing)}", file=sys.stderr)
        return 1
    for out_path in build():
        size_kb = out_path.stat().st_size / 1024
        print(f"wrote {out_path.relative_to(BTF_ROOT)} ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
