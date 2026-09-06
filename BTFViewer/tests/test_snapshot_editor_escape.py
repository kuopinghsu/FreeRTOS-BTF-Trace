"""Escape closes the Snapshot Editor once there's nothing left to peel back.

Regression test: Esc used to unconditionally swallow the key inside the
editor (peel back the shortcuts panel / selection / crop / tool, but never
actually close), on both desktop (SnapshotEditorDialog._handle_key in
stats.py) and web (SnapshotEditor.vue's onDocKeyDown) — inconsistent with
every other dialog in the app, which closes on Escape.
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

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.stats import SnapshotEditorDialog  # noqa: E402

from tests import destroy_qt_widget  # noqa: E402


def _escape_event() -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)


class SnapshotEditorEscapeTests(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def _make_dialog(self) -> SnapshotEditorDialog:
        pixmap = QPixmap(20, 20)
        pixmap.fill(Qt.GlobalColor.white)
        dlg = SnapshotEditorDialog(pixmap)
        self.addCleanup(destroy_qt_widget, dlg)
        dlg.show()
        return dlg

    def test_escape_closes_with_nothing_else_active(self) -> None:
        dlg = self._make_dialog()
        self.assertTrue(dlg.isVisible())
        dlg.keyPressEvent(_escape_event())
        self.assertFalse(dlg.isVisible())

    def test_escape_first_deselects_before_closing(self) -> None:
        dlg = self._make_dialog()
        dlg._shapes.append({'type': 'rect', 'x': 1, 'y': 1, 'w': 5, 'h': 5})
        dlg._select(0)
        self.assertEqual(dlg._selected_idx, 0)
        dlg.keyPressEvent(_escape_event())
        self.assertEqual(dlg._selected_idx, -1)
        self.assertTrue(dlg.isVisible(), "first Escape should deselect, not close")
        dlg.keyPressEvent(_escape_event())
        self.assertFalse(dlg.isVisible(), "second Escape should close")


if __name__ == "__main__":
    unittest.main()
