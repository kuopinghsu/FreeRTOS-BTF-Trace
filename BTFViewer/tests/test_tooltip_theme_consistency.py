"""QToolTip color/font consistency between dark and light theme.

Regression coverage for two issues reported on the desktop app: (1) tooltip
colors didn't match the web app's tooltip design (inverted contrast: dark
app -> light tip, light app -> dark tip — the same formula used everywhere
on web, see BTFViewer/web/src/utils/domTooltip.js), and (2) rich-text
tooltips built via qt_wrap_tooltip() (used throughout the Statistics panel
and AI assistant) rendered at a much smaller font than every plain-text
tooltip, because QToolTip.setFont() only affects plain-text tooltips —
Qt's rich-text path renders through QTextDocument and ignores it.
"""
from __future__ import annotations

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

from PySide6.QtWidgets import QApplication, QToolTip  # noqa: E402

from btf_viewer_pkg.ai_assistant import qt_wrap_tooltip  # noqa: E402
from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402

from tests import destroy_main_window  # noqa: E402


class TooltipThemeConsistencyTests(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])
        cls._app.setQuitOnLastWindowClosed(False)

    def _make_win(self) -> MainWindow:
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win.show()
        return win

    def test_tooltip_colors_are_inverted_not_matched(self) -> None:
        win = self._make_win()
        dark = win._theme_tokens(True)
        light = win._theme_tokens(False)
        # Same formula as web's domTooltip.js: background = the *other*
        # theme's own foreground/background swap, not a copy of the panel.
        self.assertEqual(dark["tooltip_bg"], light["tooltip_fg"])
        self.assertEqual(dark["tooltip_fg"], light["tooltip_bg"])
        self.assertNotEqual(dark["tooltip_bg"], dark["tooltip_fg"])

    def test_tooltip_qss_uses_tooltip_fg_and_is_compact(self) -> None:
        win = self._make_win()
        qss = self._app.styleSheet()
        m = re.search(r"QToolTip\s*\{([^}]*)\}", qss)
        self.assertIsNotNone(m, "no QToolTip rule in the app stylesheet")
        rule = m.group(1)
        tokens = win._theme_tokens(win._is_dark)
        self.assertIn(f"color:{tokens['tooltip_fg']}", rule)
        self.assertIn(f"background:{tokens['tooltip_bg']}", rule)
        pad_m = re.search(r"padding:\s*(\d+)px\s+(\d+)px", rule)
        self.assertIsNotNone(pad_m, "no padding in QToolTip rule")
        self.assertLessEqual(int(pad_m.group(1)), 2, "vertical padding should be compact")
        self.assertLessEqual(int(pad_m.group(2)), 5, "horizontal padding should be compact")

    def test_rich_text_tooltip_matches_plain_tooltip_font_size(self) -> None:
        self._make_win()
        html = qt_wrap_tooltip("Some help text that wraps across lines.")
        # Mirror _tooltip_font_css(): a font sized in points (offscreen QPA,
        # some CI) reports pixelSize() == -1, so fall back via pointSize().
        font = QToolTip.font()
        expected_px = font.pixelSize()
        if expected_px <= 0:
            pt = font.pointSize()
            expected_px = round(pt * 4 / 3) if pt > 0 else 13
        self.assertGreater(expected_px, 0)
        self.assertIn(f"font-size:{expected_px}px", html)
        # font-family must be single-quoted: it sits inside an already
        # double-quoted style="..." HTML attribute.
        self.assertNotIn('font-family:"', html)


if __name__ == "__main__":
    unittest.main()
