"""Product positioning (BTFVIEWER_DESIGN_CONSISTENCY_TODO — "P2 — Product positioning").

Desktop, Web, CLI and exports use `BTFViewer` and a viewer-first, AI-optional
description.
"""

from __future__ import annotations

import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]

TAGLINE = "Portable BTF trace analysis and evidence reports"
AI_DESC = "Optional AI-assisted investigation"

_USER_FACING = {
    "btf_viewer_pkg/stats.py": None,
    "btf_viewer_pkg/mainwindow.py": None,
    "btf_viewer_pkg/cli.py": None,
    "btf_viewer_pkg/ai_assistant.py": None,
    "btf_viewer_pkg/perfetto_export.py": None,
    "btf_viewer_pkg/html_report.py": None,
    "web/src/App.vue": None,
    "web/src/components/Toolbar.vue": None,
    "web/src/utils/htmlReport.js": None,
    "web/src/utils/aiMarkdown.js": None,
    "web/src/utils/perfettoExport.js": None,
}


def _read(rel):
    return (BTF_ROOT / rel).read_text(encoding="utf-8")


class ProductNameTests(unittest.TestCase):
    def test_no_user_facing_rtos_btf_viewer_name(self) -> None:
        for rel in _USER_FACING:
            self.assertNotIn("RTOS BTF Viewer", _read(rel), rel)

    def test_ai_conversation_export_uses_btfviewer(self) -> None:
        for rel in ("btf_viewer_pkg/ai_assistant.py", "web/src/utils/aiMarkdown.js"):
            src = _read(rel)
            self.assertIn("BTFViewer — AI Conversation", src, rel)
            self.assertNotIn("BTF Viewer — AI Conversation", src, rel)

    def test_perfetto_export_source_is_btfviewer(self) -> None:
        self.assertIn('"source": "BTFViewer"', _read("btf_viewer_pkg/perfetto_export.py"))
        self.assertIn("source: 'BTFViewer'", _read("web/src/utils/perfettoExport.js"))

    def test_html_report_product_name_and_tagline(self) -> None:
        for rel in ("btf_viewer_pkg/html_report.py", "web/src/utils/htmlReport.js"):
            src = _read(rel)
            self.assertRegex(src, r'PRODUCT_NAME\s*=\s*[\'"]BTFViewer[\'"]')
            self.assertIn(TAGLINE, src, rel)
            self.assertNotIn("AI assistant for RTOS trace analysis", src, rel)

    def test_desktop_app_name(self) -> None:
        cli = _read("btf_viewer_pkg/cli.py")
        self.assertIn('setApplicationName("BTFViewer")', cli)
        self.assertIn('setApplicationDisplayName("BTFViewer")', cli)


class ProductDescriptionTests(unittest.TestCase):
    def test_primary_tagline_is_viewer_first(self) -> None:
        # No mention of AI *before* the viewer identity in the tagline itself.
        self.assertNotIn("assistant", TAGLINE.lower())
        for rel in ("btf_viewer_pkg/stats.py", "web/src/App.vue"):
            self.assertIn(TAGLINE, _read(rel), rel)

    def test_about_describes_ai_as_optional(self) -> None:
        for rel in ("btf_viewer_pkg/stats.py", "web/src/App.vue"):
            self.assertIn(AI_DESC, _read(rel), rel)

    def test_cli_description_is_viewer_first_ai_optional(self) -> None:
        cli = _read("btf_viewer_pkg/cli.py")
        self.assertNotIn("AI assistant for RTOS trace analysis (interactive GUI)", cli)
        self.assertIn("portable BTF trace analysis and evidence reports", cli)
        self.assertIn("optional AI-assisted", cli)

    def test_generated_bundles_drop_the_old_tagline(self) -> None:
        for name in ("btf_viewer.py", "btf_viewer.html"):
            p = BTF_ROOT / "builds" / name
            if not p.is_file():
                self.skipTest(f"{name} not built")
            text = p.read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn("AI assistant for RTOS trace analysis", text, name)
            # The .py bundle's top-of-file usage docstring is pulled verbatim from
            # the committed bundle by scripts/bundle_viewer.py, so it only loses
            # the old "Single-file RTOS BTF Viewer" line once a fixed bundle is
            # committed. Check everything past that leading """...""" block.
            body = text
            if name.endswith(".py"):
                first = text.find('"""')
                end = text.find('"""', first + 3)
                if first != -1 and end != -1:
                    body = text[end + 3:]
            self.assertNotIn("RTOS BTF Viewer", body, name)


if __name__ == "__main__":
    unittest.main()
