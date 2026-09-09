"""Disabled QMenu actions must render visibly dimmed.

Regression coverage for a live-reported bug: the desktop Investigation
Notebook's Evidence step disables "Current measurement" in the "Add
evidence" menu when there is no cursor range (matching web's
:disabled="!props.cursorRange") — but the item didn't look disabled at
all, just silently refused clicks. Root cause: the app-wide QSS sets a
flat `QMenu { color: ...; }`, which wins over Qt's normal palette-driven
disabled-state dimming for every QMenu in the app, not just this one.
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

from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402

from tests import destroy_main_window  # noqa: E402


class MenuDisabledContrastTests(unittest.TestCase):
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

    def test_disabled_menu_item_has_its_own_dimmed_color_rule(self) -> None:
        win = self._make_win()
        qss = self._app.styleSheet()
        m = re.search(r"QMenu::item:disabled\s*\{([^}]*)\}", qss)
        self.assertIsNotNone(
            m, "no QMenu::item:disabled rule — disabled menu actions inherit "
               "QMenu's own flat `color:` and look identical to enabled ones")
        rule = m.group(1)
        tokens = win._theme_tokens(win._is_dark)
        # Must differ from the enabled-item color, and match the same
        # disabled token already used for QToolButton/QPushButton.
        self.assertIn(f"color:{tokens['tb_disabled']}", rule)
        self.assertNotEqual(tokens["tb_disabled"], tokens["text"])

    def test_disabled_rule_present_in_both_themes(self) -> None:
        win = self._make_win()
        for is_dark in (True, False):
            win._apply_theme(is_dark)
            qss = self._app.styleSheet()
            self.assertRegex(qss, r"QMenu::item:disabled\s*\{[^}]*color:")


if __name__ == "__main__":
    unittest.main()
