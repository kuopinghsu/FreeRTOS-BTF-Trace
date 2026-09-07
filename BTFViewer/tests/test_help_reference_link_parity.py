"""The Help / Shortcuts dialog on both platforms carries **one** full-width
"Statistics Reference" link that opens the reference viewer — no redundant
wrapper card leaving a blank box (web) and the same entry point on desktop.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
APP = (BTF_ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")
MW = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text(encoding="utf-8")

_LINK_TEXT = "Statistics Reference — full documentation for every stat →"

# Just the desktop shortcuts dialog.
_KS_START = MW.index("def _on_keyboard_shortcuts(self)")
_KS_END = MW.index("def _on_about(self)")
KS = MW[_KS_START:_KS_END]


class HelpReferenceLinkParityTests(unittest.TestCase):

    def test_same_link_label_on_both(self):
        self.assertIn(_LINK_TEXT, APP)
        self.assertIn(_LINK_TEXT, KS)
        # Exactly one on each side (no duplicate entry points in the dialog).
        self.assertEqual(APP.count(_LINK_TEXT), 1)
        self.assertEqual(KS.count(_LINK_TEXT), 1)

    def test_web_link_is_a_full_width_banner_not_a_wrapper_card(self):
        # The link sits directly in .help-body and spans the 2-col grid; it is
        # NOT wrapped in a .help-section (that wrapper is what left the blank).
        m = re.search(
            r'<div class="help-body">\s*<button type="button" class="help-reference-link"',
            APP)
        self.assertIsNotNone(
            m, "reference link must be the first child of .help-body, unwrapped")
        self.assertIn("grid-column: 1 / -1", APP)
        self.assertNotIn(
            '<div class="help-section">\n            <button type="button" class="help-reference-link"',
            APP)

    def test_web_link_opens_the_reference_viewer(self):
        self.assertIn('@click="openStatsReference"', APP)
        self.assertIn("function openStatsReference()", APP)
        self.assertIn("onStatsReferenceRequested(", APP)

    def test_desktop_link_opens_the_reference_viewer(self):
        self.assertIn("QPushButton(", KS)
        self.assertIn("self._open_stats_reference(\"\")", KS)
        self.assertIn("layout.addWidget(_ref_btn)", KS)


if __name__ == "__main__":
    unittest.main()
