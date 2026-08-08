"""Fit-to-window must undo multi-step zoom in one click."""
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

from PySide6.QtCore import QEventLoop, QPoint, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.parser import _parse_btf  # noqa: E402
from btf_viewer_pkg.view import TimelineView  # noqa: E402

EXAMPLE_BTF = Path(__file__).resolve().parents[2] / "tracedata" / "example.btf.gz"


class TestZoomFit(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def _make_timeline(self, width: int = 1200, height: int = 700):
        if not EXAMPLE_BTF.is_file():
            self.skipTest(f"missing trace fixture: {EXAMPLE_BTF}")
        view = TimelineView()
        view.resize(width, height)
        view.show()
        trace = _parse_btf(str(EXAMPLE_BTF))
        view.load_trace(trace)
        self._app.processEvents()
        view.zoom_fit()
        self._app.processEvents()
        return view, view._scene, trace

    def _pump_ms(self, ms: int) -> None:
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def test_zoom_fit_cancels_pending_toolbar_zoom(self) -> None:
        view, scene, _trace = self._make_timeline()
        fit_tpp = scene._timescale_per_px
        view.zoom_in()
        view.zoom_in()
        view.zoom_in()
        self.assertTrue(view._zoom_timer.isActive())
        self.assertGreater(view._zoom_accum, 1.0)

        view.zoom_fit()

        self.assertFalse(view._zoom_timer.isActive())
        self.assertEqual(view._zoom_accum, 1.0)
        self.assertTrue(view._fit_mode)
        self.assertAlmostEqual(scene._timescale_per_px, scene._timescale_per_px_fit)
        self._pump_ms(120)
        self.assertTrue(view._fit_mode)
        self.assertAlmostEqual(scene._timescale_per_px, scene._timescale_per_px_fit)
        self.assertAlmostEqual(
            scene._timescale_per_px, fit_tpp, delta=max(abs(fit_tpp) * 0.05, 1e-9))

    def test_zoom_fit_exits_virtual_scroll_and_loads_full_span(self) -> None:
        view, scene, trace = self._make_timeline()
        view._do_zoom(8.0, QPoint(600, 350))
        self._app.processEvents()
        if not view._virtual_time_scroll_active:
            view._do_zoom(8.0, QPoint(600, 350))
            self._app.processEvents()
        self.assertTrue(view._virtual_time_scroll_active)
        self.assertFalse(view._fit_mode)
        self.assertLess(scene._timescale_per_px, scene._timescale_per_px_fit * 0.999)

        view.zoom_fit()
        self._app.processEvents()

        self.assertTrue(view._fit_mode)
        self.assertFalse(view._virtual_time_scroll_active)
        self.assertEqual(scene._scene_origin_ns, trace.time_min)
        self.assertEqual(scene._vp_ns_lo, trace.time_min)
        self.assertEqual(scene._vp_ns_hi, trace.time_max)
        self.assertAlmostEqual(scene._timescale_per_px, scene._timescale_per_px_fit)
        self._pump_ms(50)
        self.assertFalse(view._virtual_time_scroll_active)
        self.assertTrue(view._fit_mode)


if __name__ == "__main__":
    unittest.main()
