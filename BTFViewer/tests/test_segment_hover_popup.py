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

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QBrush, QColor, QPen  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.graphics_items import _BatchRowItem  # noqa: E402
from btf_viewer_pkg.timeline_util import _get_popup  # noqa: E402
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
        tip = _get_popup()
        tip.show_at(QPointF(0, 0).toPoint(), "<b>stay</b>")
        self.assertTrue(tip.isVisible())
        QApplication.sendEvent(view, QEvent(QEvent.Type.Leave))
        self.assertFalse(tip.isVisible())
        view.deleteLater()

    def test_leave_event_hides_popup_in_source(self) -> None:
        src = (BTF_ROOT / "btf_viewer_pkg" / "view.py").read_text(encoding="utf-8")
        gi = (BTF_ROOT / "btf_viewer_pkg" / "graphics_items.py").read_text(
            encoding="utf-8")
        self.assertIn("_get_popup().hide()", src)
        self.assertIn("def contains(self, point: QPointF)", gi)
        self.assertIn("def _hit_seg_index", gi)


if __name__ == "__main__":
    unittest.main()
