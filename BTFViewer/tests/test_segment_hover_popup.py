"""Segment hover info popup must hide when the pointer leaves a bar."""
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

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPen  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.graphics_items import _BatchRowItem  # noqa: E402
from btf_viewer_pkg.timeline_util import _get_popup, _hide_popup  # noqa: E402
from btf_viewer_pkg.view import TimelineView  # noqa: E402


class _Seg:
    def __init__(self, task: str, start: int, end: int, core: str = "Core_0") -> None:
        self.task = task
        self.start = start
        self.end = end
        self.core = core


class SegmentHoverPopupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_contains_only_segment_bars_not_row_gaps(self) -> None:
        """A row item spans the whole lane; hover must hit bars only."""
        seg = _Seg("T[1]", 0, 100)
        bar = QRectF(10, 2, 40, 16)
        item = _BatchRowItem(
            QRectF(0, 0, 400, 20),
            [(bar, QBrush(QColor("#4488ff")), QPen(Qt.PenStyle.NoPen), seg)],
            "us",
            xs=[(10.0, 50.0, 0)],
        )
        self.assertTrue(item.contains(QPointF(30, 10)))
        self.assertFalse(item.contains(QPointF(80, 10)))
        self.assertIsNone(item._hit_seg_index(QPointF(80, 10)))
        self.assertEqual(item._hit_seg_index(QPointF(30, 10)), 0)

    def test_view_leave_hides_info_popup(self) -> None:
        view = TimelineView()
        view.resize(640, 480)
        view.show()
        self.app.processEvents()
        tip = _get_popup()
        tip.show_at(QPoint(20, 20), "<b>stay</b>", host=view.viewport())
        self.assertTrue(tip.isVisible())
        QApplication.sendEvent(view, QEvent(QEvent.Type.Leave))
        self.assertFalse(tip.isVisible())
        view.close()

    def test_mouse_move_to_empty_hides_info_popup(self) -> None:
        """Moving to another row / empty area must close the box (not only Leave)."""
        view = TimelineView()
        view.resize(640, 480)
        view.show()
        self.app.processEvents()
        tip = _get_popup()
        tip.show_at(QPoint(20, 20), "<b>stay</b>", host=view.viewport())
        self.assertTrue(tip.isVisible())
        ev = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(400.0, 400.0),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        view.mouseMoveEvent(ev)
        self.assertFalse(tip.isVisible())
        view.close()

    def test_parented_popup_is_not_tooltip_window(self) -> None:
        view = TimelineView()
        view.show()
        tip = _get_popup()
        tip.show_at(QPoint(0, 0), "<b>x</b>", host=view.viewport())
        self.assertIs(tip.parentWidget(), view.viewport())
        self.assertFalse(bool(tip.windowFlags() & Qt.WindowType.ToolTip))
        tip.hide()
        self.assertFalse(tip.isVisible())
        self.assertFalse(bool(tip.windowFlags() & Qt.WindowType.Tool))
        self.assertIsNotNone(tip.parentWidget())
        view.close()

    def test_hide_does_not_use_tool_window(self) -> None:
        """Windows flashes a tiny native window if hide() applies Qt.Tool flags."""
        src = (BTF_ROOT / "btf_viewer_pkg" / "timeline_util.py").read_text(
            encoding="utf-8")
        self.assertNotIn("def _popup_holder_widget", src)
        popup_cls = src.split("class _InfoPopup")[1].split("_GRID_STEPS")[0]
        self.assertNotIn("setWindowFlags", popup_cls)
        self.assertNotIn("self._park()", popup_cls)
        hide_body = src.split("def hide(self)")[1].split("def show_at")[0]
        self.assertNotIn("setWindowFlags", hide_body)
        view = TimelineView()
        view.show()
        tip = _get_popup()
        tip.show_at(QPoint(20, 20), "<b>x</b>", host=view.viewport())
        _hide_popup()
        self.assertFalse(tip.isVisible())
        self.assertFalse(bool(tip.windowFlags() & Qt.WindowType.Tool))
        view.close()

    def test_leave_event_hides_popup_in_source(self) -> None:
        src = (BTF_ROOT / "btf_viewer_pkg" / "view.py").read_text(encoding="utf-8")
        gi = (BTF_ROOT / "btf_viewer_pkg" / "graphics_items.py").read_text(
            encoding="utf-8")
        self.assertIn("def _sync_info_popup", src)
        self.assertIn("_hide_popup()", src)
        self.assertIn("def contains(self, point: QPointF)", gi)
        self.assertIn("def _hit_seg_index", gi)

    def test_destroying_host_view_does_not_kill_singleton(self) -> None:
        view = TimelineView()
        view.show()
        self.app.processEvents()
        tip = _get_popup()
        tip.show_at(QPoint(20, 20), "<b>x</b>", host=view.viewport())
        view.close()
        view.deleteLater()
        self.app.processEvents()
        view2 = TimelineView()
        view2.show()
        self.app.processEvents()
        tip2 = _get_popup()
        tip2.show_at(QPoint(0, 0), "<b>y</b>", host=view2.viewport())
        self.assertTrue(tip2.isVisible())
        _hide_popup()
        self.assertFalse(tip2.isVisible())
        view2.close()


if __name__ == "__main__":
    unittest.main()
