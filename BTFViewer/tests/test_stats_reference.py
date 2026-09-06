"""Statistics Reference viewer content contract.

Every ``STATS_PINNABLE_SECTIONS`` id must resolve to a real anchor in
STATISTICS.md — otherwise a section's ⓘ icon (desktop stats_reference.py,
web StatsReferenceViewer.vue) silently opens the reference at the top
instead of jumping to the section, with no error anywhere. Nothing else
catches this: check-docs-html (scripts/ci_gate.py) only checks file
*freshness* against STATISTICS.md, not that ids inside it still line up
with config.py.

STATISTICS_zh-TW.md must carry the exact same anchor set (build_docs_html.py
builds one independent document per language from the *same*
STATS_PINNABLE_SECTIONS ids — a language missing an anchor breaks
navigation only after switching to it, easy to miss without this check),
and btf_viewer.hlp / statistics-en.inline.html must be the JSON envelope
``{"en": ..., "zh-tw": ...}`` both platforms' viewers expect, not a bare
HTML string (a stale pre-dual-language build would silently fail to
``json.loads()`` at runtime — see stats_reference.py's ``_load_pages()``).
"""
from __future__ import annotations

import json
import os
import re
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.config import (  # noqa: E402
    STATS_PINNABLE_SECTIONS,
    STATS_SECTION_HELP,
)

STATISTICS_MD = BTF_ROOT / "STATISTICS.md"
STATISTICS_ZH_TW_MD = BTF_ROOT / "STATISTICS_zh-TW.md"
DESKTOP_HLP = BTF_ROOT / "builds" / "btf_viewer.hlp"
WEB_INLINE_HTML = BTF_ROOT / "web" / "src" / "generated" / "statistics-en.inline.html"
_ANCHOR_RE = re.compile(r'<a[^>]+id=["\']statistics-([^"\']+)["\']')


class StatsReferenceAnchorTests(unittest.TestCase):
    def test_every_pinnable_section_has_a_statistics_md_anchor(self) -> None:
        text = STATISTICS_MD.read_text(encoding="utf-8")
        anchors = set(_ANCHOR_RE.findall(text))
        missing = [sid for sid in STATS_PINNABLE_SECTIONS if sid not in anchors]
        self.assertEqual(
            missing, [],
            f"STATS_PINNABLE_SECTIONS ids with no <a id=\"statistics-<id>\"> "
            f"anchor in STATISTICS.md: {missing!r}",
        )

    def test_every_pinnable_section_has_a_statistics_zh_tw_md_anchor(self) -> None:
        text = STATISTICS_ZH_TW_MD.read_text(encoding="utf-8")
        anchors = set(_ANCHOR_RE.findall(text))
        missing = [sid for sid in STATS_PINNABLE_SECTIONS if sid not in anchors]
        self.assertEqual(
            missing, [],
            f"STATS_PINNABLE_SECTIONS ids with no <a id=\"statistics-<id>\"> "
            f"anchor in STATISTICS_zh-TW.md: {missing!r}",
        )

    def test_every_pinnable_section_has_help_text(self) -> None:
        missing = [sid for sid in STATS_PINNABLE_SECTIONS if not STATS_SECTION_HELP.get(sid)]
        self.assertEqual(
            missing, [],
            f"STATS_PINNABLE_SECTIONS ids with no STATS_SECTION_HELP entry: {missing!r}",
        )


class DualLanguageBuildTests(unittest.TestCase):
    """Covers both output copies of scripts/build_docs_html.py's JSON envelope."""

    def _load_envelope(self, path: Path) -> dict:
        if not path.is_file():
            self.skipTest(f"{path} not built — run scripts/build_docs_html.py")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            self.fail(f"{path} is not valid JSON (stale pre-dual-language build?): {exc}")
        self.assertIsInstance(data, dict)
        self.assertEqual(set(data.keys()), {"en", "zh-tw"})
        return data

    def _check_envelope(self, path: Path) -> None:
        pages = self._load_envelope(path)
        for lang, html in pages.items():
            with self.subTest(lang=lang):
                self.assertTrue(html.startswith("<!doctype html>"))
                anchors = set(_ANCHOR_RE.findall(html))
                missing = [sid for sid in STATS_PINNABLE_SECTIONS if sid not in anchors]
                self.assertEqual(missing, [], f"{path} [{lang}] missing anchors: {missing!r}")

    def test_desktop_hlp_is_dual_language_envelope(self) -> None:
        self._check_envelope(DESKTOP_HLP)

    def test_web_inline_html_is_dual_language_envelope(self) -> None:
        self._check_envelope(WEB_INLINE_HTML)

    def test_mermaid_svg_ids_are_unique_across_languages(self) -> None:
        """Regression for the mmdc default-id collision bug: with both
        languages' diagrams on the page (as siblings in one <iframe srcdoc>
        or webengine setHtml at different times but sharing an id namespace
        if never made unique), a shared id would let the last-rendered
        diagram's CSS silently win for all of them."""
        pages = self._load_envelope(DESKTOP_HLP)
        all_ids: list[str] = []
        for lang, html in pages.items():
            all_ids.extend(re.findall(r'<svg[^>]+id="(mermaid-[^"]+)"', html))
        self.assertEqual(len(all_ids), len(set(all_ids)), "duplicate mermaid svg ids across languages")

    def test_no_unrendered_markdown_bold_markers(self) -> None:
        """Regression for a class of CommonMark-spec-compliant-but-surprising
        failures found in STATISTICS_zh-TW.md: a **bold** span whose content
        ends right against CJK/ASCII punctuation (e.g. **計算方式：**next, or
        **CPU%**next) fails the emphasis "right-flanking" rule when the very
        next character isn't whitespace/punctuation, so markdown-it leaves the
        literal ** in the output instead of a <strong> tag. STATISTICS.md
        (English prose) doesn't hit this pattern, but any future zh-TW edit
        that starts a bold label with e.g. "**Foo：**接下來" (no space before
        the following character) reintroduces it — catch it here rather than
        as a visibly broken tooltip/reference page."""
        pages = self._load_envelope(DESKTOP_HLP)
        for lang, html in pages.items():
            with self.subTest(lang=lang):
                leftover = re.findall(r'.{20}\*\*.{20}', html)
                self.assertEqual(
                    leftover, [],
                    f"{lang}: literal ** survived markdown rendering (unclosed/"
                    f"unopened bold span) — see contexts above",
                )


if __name__ == "__main__":
    unittest.main()
