"""Double-click on the ruler must Fit Trace (parity with Web); empty
background double-click must not trigger any zoom action."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.parser import BtfTrace, TaskSegment, _task_merge_key  # noqa: E402
from btf_viewer_pkg.view import RULER_HEIGHT, TimelineView  # noqa: E402


def _single_core_trace() -> BtfTrace:
    core = "Core_0"
    label = "T0[0]"
    mk = _task_merge_key(label)
    seg = TaskSegment(task=label, start=0, end=1000, core=core)
    return BtfTrace(
        time_scale="ns",
        tasks=[mk],
        segments=[seg],
        sti_events=[],
        sti_channels=[],
        sti_events_by_target={},
        time_min=0,
        time_max=1000,
        seg_map_by_merge_key={mk: [seg]},
        core_names=[core],
        core_segs={core: [seg]},
        task_repr={mk: label},
    )


def _dbl_click(view: TimelineView, x: float, y: float) -> None:
    ev = QMouseEvent(
        QEvent.Type.MouseButtonDblClick,
        QPointF(x, y),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.mouseDoubleClickEvent(ev)


class RulerDoubleClickFitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _view(self) -> TimelineView:
        view = TimelineView()
        view.resize(640, 480)
        view.show()
        view._scene.set_trace(_single_core_trace(), viewport_width=640)
        self.app.processEvents()
        self.addCleanup(view.close)
        return view

    def test_ruler_double_click_calls_fit(self) -> None:
        view = self._view()
        lw = view._scene._label_width
        with patch.object(view, "zoom_fit") as fit:
            _dbl_click(view, lw + 40, RULER_HEIGHT / 2)
        fit.assert_called_once()

    def test_empty_background_double_click_does_not_fit(self) -> None:
        view = self._view()
        lw = view._scene._label_width
        with patch.object(view, "zoom_fit") as fit:
            _dbl_click(view, lw + 40, RULER_HEIGHT + 400)
        fit.assert_not_called()

    def test_label_resize_zone_double_click_does_not_fit(self) -> None:
        """The existing auto-fit-label-column double-click must still win."""
        view = self._view()
        lw = view._scene._label_width
        with patch.object(view, "zoom_fit") as fit, \
                patch.object(view, "_auto_fit_label_column") as auto_fit:
            _dbl_click(view, lw, RULER_HEIGHT / 2)
        fit.assert_not_called()
        auto_fit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
