"""Ctrl-like modifiers for the desktop measure ruler."""
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

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.parser import _parse_btf  # noqa: E402
from btf_viewer_pkg.view import (  # noqa: E402
    TimelineView,
    _ctrl_like_held,
    _is_ctrl_like_key,
)


class CtrlLikeModifierTests(unittest.TestCase):
    def test_control_and_meta_both_count(self) -> None:
        self.assertTrue(_ctrl_like_held(Qt.KeyboardModifier.ControlModifier))
        self.assertTrue(_ctrl_like_held(Qt.KeyboardModifier.MetaModifier))
        self.assertFalse(_ctrl_like_held(Qt.KeyboardModifier.ShiftModifier))
        self.assertTrue(_is_ctrl_like_key(Qt.Key.Key_Control))
        self.assertTrue(_is_ctrl_like_key(Qt.Key.Key_Meta))
        self.assertFalse(_is_ctrl_like_key(Qt.Key.Key_Shift))


class MeasureRulerMouseTests(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_macos_ctrl_left_arrives_as_right_button(self) -> None:
        example = Path(__file__).resolve().parents[2] / "tracedata" / "example.btf.gz"
        if not example.is_file():
            self.skipTest(f"missing trace fixture: {example}")
        view = TimelineView()
        view.resize(900, 600)
        view.show()
        view.load_trace(_parse_btf(str(example)))
        self._app.processEvents()
        lw = view._scene._label_width
        pos = QPointF(lw + 80, 80)
        ev = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            pos,
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.ControlModifier,
        )
        view.mousePressEvent(ev)
        self.assertIsNotNone(view._measure_press_ns)
        view.close()


if __name__ == "__main__":
    unittest.main()
