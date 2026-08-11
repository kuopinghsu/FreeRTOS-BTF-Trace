"""Find mode help / labels stay in sync with the web Find panel."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.config import _PORTABLE_FIND_MODES  # noqa: E402
from btf_viewer_pkg.mvvm.find_logic import (  # noqa: E402
    FIND_MODE_CHOICES,
    find_mode_help,
    normalize_find_mode,
)


class FindModeHelpTests(unittest.TestCase):
    def test_choices_match_portable_order(self) -> None:
        keys = [k for _lab, k, _tip in FIND_MODE_CHOICES]
        self.assertEqual(tuple(keys), _PORTABLE_FIND_MODES)

    def test_normalize_aliases(self) -> None:
        self.assertEqual(normalize_find_mode("Contains"), "contains")
        self.assertEqual(normalize_find_mode("STI events"), "sti")
        self.assertEqual(normalize_find_mode("tags"), "sti")
        self.assertEqual(normalize_find_mode("nope"), "contains")

    def test_help_nonempty(self) -> None:
        for _lab, key, tip in FIND_MODE_CHOICES:
            self.assertTrue(tip.strip())
            self.assertEqual(find_mode_help(key), tip)
            self.assertEqual(find_mode_help(_lab), tip)

    def test_desktop_and_web_help_match(self) -> None:
        js = (BTF_ROOT / "web/src/utils/findAnalysis.js").read_text(encoding="utf-8")
        vue = (BTF_ROOT / "web/src/components/FindPanel.vue").read_text(
            encoding="utf-8")
        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        self.assertIn("FIND_MODE_CHOICES", js)
        self.assertIn("findModeHelp", vue)
        self.assertRegex(
            vue,
            re.compile(
                r'<div class="find-panel">\s*'
                r'<div\s*\n?\s*class="find-status"',
                re.S,
            ),
        )
        self.assertIn("self._find_status = QLabel", mw)
        self.assertLess(
            mw.index("self._find_status = QLabel"),
            mw.index("self._find_input = QLineEdit"),
        )
        self.assertIn("_find_mode_help", mw)
        for _lab, key, tip in FIND_MODE_CHOICES:
            self.assertIn(f"key: '{key}'", js)
            self.assertIn(tip, js)
        self.assertIn("formatFindStatus", js)
        self.assertIn("migration matches", js)


if __name__ == "__main__":
    unittest.main()
