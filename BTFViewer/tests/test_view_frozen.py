"""Characterization tests for timeline view frozen overlay reposition."""
from __future__ import annotations

import os
import sys
import unittest
import warnings
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.parser import _parse_btf  # noqa: E402
from btf_viewer_pkg.view import TimelineView  # noqa: E402

EXAMPLE_BTF = Path(__file__).resolve().parents[2] / "tracedata" / "example.btf.gz"

class _QtTestBase(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def _make_timeline(self, width: int = 900, height: int = 600):
        if not EXAMPLE_BTF.is_file():
            self.skipTest(f"missing trace fixture: {EXAMPLE_BTF}")
        view = TimelineView()
        view.resize(width, height)
        view.show()
        trace = _parse_btf(str(EXAMPLE_BTF))
        view.load_trace(trace)
        self._app.processEvents()
        return view, view._scene, trace

class TestViewFrozen(_QtTestBase):
    def test_timeline_view_constructs_without_crash(self) -> None:
        view = TimelineView()
        view.resize(640, 480)
        view.show()
        self._app.processEvents()
        self.assertIsNotNone(view.verticalScrollBar())
        self.assertIsNotNone(view._time_scroll_internal)

    def test_reposition_frozen_top_after_vertical_scroll(self) -> None:
        view, scene, trace = self._make_timeline()
        self.assertTrue(scene._horizontal)
        cursor_ns = trace.time_min + (trace.time_max - trace.time_min) // 3
        scene.add_cursor(cursor_ns)
        self.assertTrue(scene._cursor_frozen_top_set)

        lbl_item = next(
            item for item in scene._cursor_frozen_top_set
            if hasattr(item, "text") and str(item.text()).startswith("C")
        )
        orig_y = next(orig for item, orig in scene._frozen_top_items if item is lbl_item)

        vbar = view.verticalScrollBar()
        if vbar.maximum() <= vbar.minimum():
            view.scrollContentsBy(0, 80)
        else:
            vbar.setValue(min(vbar.maximum(), vbar.minimum() + 80))
        self._app.processEvents()

        scene_top = view.mapToScene(QPoint(0, 0)).y()
        self.assertAlmostEqual(lbl_item.y(), scene_top + orig_y, places=1)

    def test_virtual_scroll_toggle_no_disconnect_warning(self) -> None:
        view, _scene, _trace = self._make_timeline()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            view._set_virtual_scroll_enabled(True)
            self._app.processEvents()
            view._set_virtual_scroll_enabled(False)
            self._app.processEvents()
            view._set_virtual_scroll_enabled(True)
            view._set_virtual_scroll_enabled(False)
        msgs = [
            str(w.message) for w in caught
            if issubclass(w.category, RuntimeWarning)
            and "Failed to disconnect" in str(w.message)
        ]
        self.assertEqual(msgs, [])

if __name__ == "__main__":
    unittest.main()
