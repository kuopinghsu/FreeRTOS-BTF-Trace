"""Snapshot Editor opens at a bounded size and stays on the visible screen.

Regression for oversized / off-screen windows on multi-monitor and WSLg
setups where the window system reports a wrong or huge available geometry.
"""
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

from PySide6.QtGui import QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402

from btf_viewer_pkg.stats import (  # noqa: E402
    SnapshotEditorDialog, _widget_available_geometry,
)

try:
    from tests import destroy_qt_widget
except Exception:  # pragma: no cover
    def destroy_qt_widget(w):
        w.close()
        w.deleteLater()


class SnapshotEditorSizeTests(unittest.TestCase):
    _app = None

    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def _dialog(self, w: int, h: int) -> SnapshotEditorDialog:
        pm = QPixmap(w, h)
        pm.fill(Qt.GlobalColor.white)
        dlg = SnapshotEditorDialog(pm)
        self.addCleanup(destroy_qt_widget, dlg)
        return dlg

    def test_absolute_caps_are_sane(self):
        self.assertLessEqual(SnapshotEditorDialog._MAX_OPEN_W, 1920)
        self.assertLessEqual(SnapshotEditorDialog._MAX_OPEN_H, 1200)
        self.assertGreaterEqual(SnapshotEditorDialog._MAX_OPEN_W, 900)

    def test_huge_capture_opens_bounded(self):
        dlg = self._dialog(8000, 6000)
        scr = _widget_available_geometry(dlg)
        self.assertLessEqual(dlg.width(),
                             min(scr.width(), SnapshotEditorDialog._MAX_OPEN_W))
        self.assertLessEqual(dlg.height(),
                             min(scr.height(), SnapshotEditorDialog._MAX_OPEN_H))
        # And it never opens absurdly small either.
        self.assertGreater(dlg.width(), 200)

    def test_tiny_capture_stays_small(self):
        dlg = self._dialog(20, 20)
        self.assertLess(dlg.width(), SnapshotEditorDialog._MAX_OPEN_W)
        self.assertLess(dlg.height(), SnapshotEditorDialog._MAX_OPEN_H)

    def test_recenter_pulls_an_offscreen_window_back(self):
        dlg = self._dialog(1200, 900)
        dlg.show()
        self._app.processEvents()
        scr = _widget_available_geometry(dlg)

        dlg.move(scr.x() + scr.width() + 4000, scr.y() + scr.height() + 4000)
        dlg._recenter_on_screen()

        f = dlg.frameGeometry()
        self.assertGreaterEqual(f.x(), scr.x())
        self.assertGreaterEqual(f.y(), scr.y())
        self.assertLessEqual(f.x() + f.width(), scr.x() + scr.width())
        self.assertLessEqual(f.y() + f.height(), scr.y() + scr.height())

    def test_recenter_shrinks_a_frame_larger_than_screen(self):
        dlg = self._dialog(200, 200)
        dlg.show()
        self._app.processEvents()
        scr = _widget_available_geometry(dlg)

        dlg.resize(scr.width() + 2000, scr.height() + 2000)
        dlg._recenter_on_screen()

        f = dlg.frameGeometry()
        self.assertLessEqual(f.width(), scr.width())
        self.assertLessEqual(f.height(), scr.height())

    def test_show_event_clamps_automatically(self):
        dlg = self._dialog(400, 400)
        scr = _widget_available_geometry(dlg)
        dlg.move(scr.x() + scr.width() + 3000, scr.y())
        dlg.show()
        self._app.processEvents()
        f = dlg.frameGeometry()
        self.assertLessEqual(f.x() + f.width(), scr.x() + scr.width())


if __name__ == "__main__":
    unittest.main()
