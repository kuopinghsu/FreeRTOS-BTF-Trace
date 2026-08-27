"""Status-bar / hover tips must track Settings → UI font size."""
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

from PySide6.QtWidgets import QApplication, QToolTip  # noqa: E402

from btf_viewer_pkg.config import (  # noqa: E402
    UI_FONT_SIZE,
    _application_ui_font,
    _ui_font_stylesheet_size,
)
from btf_viewer_pkg.timeline_util import (  # noqa: E402
    _InfoPopup,
    _apply_info_popup_ui_font,
    _get_popup,
)


class UiTooltipFontTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_qtooltip_setfont_in_theme_path(self) -> None:
        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        self.assertIn("QToolTip.setFont(base_font)", mw)
        self.assertIn("_apply_info_popup_ui_font(_ui_font_size", mw)

    def test_info_popup_follows_ui_font(self) -> None:
        popup = _InfoPopup()
        popup.set_ui_font_size(8)
        popup._apply_stylesheet(True)
        ss8 = popup.styleSheet()
        self.assertIn(_ui_font_stylesheet_size(8), ss8)
        popup.set_ui_font_size(16)
        popup._apply_stylesheet(True)
        ss16 = popup.styleSheet()
        self.assertIn(_ui_font_stylesheet_size(16), ss16)
        self.assertNotIn(_ui_font_stylesheet_size(8), ss16)
        self.assertNotIn("font-size:7pt", ss16)
        self.assertEqual(popup._ui_font_size, 16)

    def test_apply_info_popup_ui_font_seeds_singleton(self) -> None:
        _apply_info_popup_ui_font(14)
        tip = _get_popup()
        self.assertEqual(tip._ui_font_size, 14)

    def test_qtooltip_font_tracks_application_ui_font(self) -> None:
        big = _application_ui_font(18)
        QToolTip.setFont(big)
        tip_font = QToolTip.font()
        self.assertEqual(tip_font.pointSize(), big.pointSize())
        self.assertEqual(tip_font.pixelSize(), big.pixelSize())
        # Restore a sane default for later tests in this process.
        QToolTip.setFont(_application_ui_font(UI_FONT_SIZE))


if __name__ == "__main__":
    unittest.main()
