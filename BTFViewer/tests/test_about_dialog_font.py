"""About dialog text scales with the application UI font size."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from PySide6.QtGui import QFontInfo  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from btf_viewer_pkg.stats import _AboutDialog  # noqa: E402


def _px(widget) -> int:
    return QFontInfo(widget.font()).pixelSize()


class TestAboutDialogFont(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def _dialog(self, ui_font_size: int) -> _AboutDialog:
        dlg = _AboutDialog(None, is_dark=False, ui_font_size=ui_font_size)
        self.addCleanup(dlg.deleteLater)
        return dlg

    def test_body_text_matches_dialog_ui_font(self) -> None:
        for ui in (8, 12, 16):
            with self.subTest(ui_font_size=ui):
                dlg = self._dialog(ui)
                body = dlg.findChild(QLabel, "about_body")
                key = dlg.findChild(QLabel, "about_key")
                self.assertIsNotNone(body)
                self.assertIsNotNone(key)
                self.assertEqual(_px(body), _px(dlg))
                self.assertEqual(_px(key), _px(dlg))

    def test_title_and_section_stay_proportional(self) -> None:
        dlg = self._dialog(8)
        body_px = _px(dlg.findChild(QLabel, "about_body"))
        title_px = _px(dlg.findChild(QLabel, "about_title"))
        sect_px = _px(dlg.findChild(QLabel, "about_sect"))
        self.assertGreater(title_px, body_px)
        self.assertLessEqual(sect_px, body_px)

    def test_larger_ui_font_grows_text_and_dialog(self) -> None:
        small = self._dialog(8)
        large = self._dialog(16)
        self.assertGreater(_px(large.findChild(QLabel, "about_body")),
                           _px(small.findChild(QLabel, "about_body")))
        self.assertGreater(_px(large.findChild(QLabel, "about_title")),
                           _px(small.findChild(QLabel, "about_title")))
        self.assertGreater(large.width(), small.width())
        self.assertGreater(large.height(), small.height())


if __name__ == "__main__":
    unittest.main()
