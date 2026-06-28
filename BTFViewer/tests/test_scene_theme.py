"""Tests for timeline scene theme palette (offscreen Qt)."""
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

from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.scene import TimelineScene  # noqa: E402


def _luminance(hex_name: str) -> float:
    c = QColor(hex_name)
    return 0.299 * c.redF() + 0.587 * c.greenF() + 0.114 * c.blueF()


class TestSceneTheme(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_dark_row_separator_is_subtle(self) -> None:
        scene = TimelineScene()
        scene.set_theme(True, rebuild=False)
        self.assertLess(_luminance(scene._c_sep.name()), 0.35)

    def test_light_row_separator_is_lighter_than_dark(self) -> None:
        scene = TimelineScene()
        scene.set_theme(True, rebuild=False)
        dark_sep = scene._c_sep.name()
        scene.set_theme(False, rebuild=False)
        light_sep = scene._c_sep.name()
        self.assertGreater(_luminance(light_sep), _luminance(dark_sep))

    def test_theme_toggle_updates_label_background(self) -> None:
        scene = TimelineScene()
        scene.set_theme(True, rebuild=False)
        dark_lbl = scene._c_label_bg.name()
        scene.set_theme(False, rebuild=False)
        self.assertNotEqual(scene._c_label_bg.name(), dark_lbl)


if __name__ == "__main__":
    unittest.main()
