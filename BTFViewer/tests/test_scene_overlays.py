"""Characterization tests for timeline scene overlay bookkeeping."""
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

from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.parser import _parse_btf  # noqa: E402
from btf_viewer_pkg.view import TimelineView  # noqa: E402

EXAMPLE_BTF = Path(__file__).resolve().parents[2] / "tracedata" / "example.btf"

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

class TestSceneOverlays(_QtTestBase):
    def test_hover_line_restored_after_rebuild(self) -> None:
        view, scene, trace = self._make_timeline()
        hover_ns = (trace.time_min + trace.time_max) // 2
        scene._hover_ns = hover_ns
        scene._draw_hover_line()
        self.assertTrue(scene._hover_items)
        self.assertEqual(scene._hover_line_ns, hover_ns)

        scene.rebuild()
        self._app.processEvents()

        self.assertEqual(scene._hover_line_ns, hover_ns)
        self.assertTrue(scene._hover_items)

    def test_cursor_frozen_top_purge_on_redraw(self) -> None:
        view, scene, trace = self._make_timeline()
        self.assertTrue(scene._horizontal)
        t0 = trace.time_min + (trace.time_max - trace.time_min) // 4
        t1 = trace.time_min + (trace.time_max - trace.time_min) // 2
        scene.add_cursor(t0)
        scene.add_cursor(t1)
        self.assertTrue(scene._cursor_frozen_top_set)
        old_frozen = set(scene._cursor_frozen_top_set)

        scene.clear_cursors()
        self.assertFalse(scene._cursor_frozen_top_set)
        self.assertFalse(
            any(item in old_frozen for item, _ in scene._frozen_top_items),
            "stale cursor labels remain in _frozen_top_items",
        )

    def test_hover_frozen_purge_on_clear(self) -> None:
        view, scene, trace = self._make_timeline()
        self.assertTrue(scene._horizontal)
        scene._hover_ns = (trace.time_min + trace.time_max) // 2
        scene._draw_hover_line()
        self.assertTrue(scene._hover_frozen_top_set)
        old_frozen = set(scene._hover_frozen_top_set)

        scene.clear_hover_line()
        self.assertFalse(scene._hover_frozen_top_set)
        self.assertFalse(
            any(item in old_frozen for item, _ in scene._frozen_top_items),
            "stale hover labels remain in _frozen_top_items",
        )

if __name__ == "__main__":
    unittest.main()
