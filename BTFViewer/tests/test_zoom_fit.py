"""Fit-to-window must undo multi-step zoom in one click."""
from __future__ import annotations

import os
import re
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

from tests import destroy_main_window  # noqa: E402

EXAMPLE_BTF = Path(__file__).resolve().parents[2] / "tracedata" / "example.btf.gz"
WEB_TIMELINE_PANEL = BTF_ROOT / "web" / "src" / "components" / "TimelinePanel.vue"


class TestZoomFit(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def _make_timeline(self, width: int = 1200, height: int = 700):
        if not EXAMPLE_BTF.is_file():
            self.skipTest(f"missing trace fixture: {EXAMPLE_BTF}")
        view = TimelineView()
        # Left undestroyed, this top-level widget (and its live QTimers) would
        # outlive the test in the shared QApplication/process and could crash
        # later GUI tests (e.g. MainWindow teardown) run in the same process.
        self.addCleanup(destroy_main_window, view)
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

    def test_zoom_fit_stays_full_trace_when_cursors_placed(self) -> None:
        """Toolbar Fit / Ctrl+0 always fits the full trace. Zoom fit to
        C1–Cn is zoom_to_cursor_range() (Ctrl+R); XML <fit_view/> uses that
        path from the demo host, not zoom_fit()."""
        view, scene, trace = self._make_timeline()
        fit_tpp = scene._timescale_per_px
        span = max(trace.time_max - trace.time_min, 1)
        scene.add_cursor(trace.time_min + span // 3)
        scene.add_cursor(trace.time_min + 2 * span // 3)
        self.assertTrue(view.zoom_to_cursor_range())
        self._app.processEvents()
        range_tpp = scene._timescale_per_px
        self.assertLess(range_tpp, fit_tpp * 0.9)
        view.zoom_fit()
        self._app.processEvents()
        self.assertAlmostEqual(
            scene._timescale_per_px, fit_tpp, delta=max(abs(fit_tpp) * 0.05, 1e-9),
            msg="toolbar Fit must not become C1–Cn when cursors exist")
        self.assertTrue(view._fit_mode)

    def test_zoom_out_at_fit_is_noop(self) -> None:
        """Ctrl+- / Zoom Out at Fit-to-window must not change the scale.
        The toolbar button is grayed; the op is a no-op. Matches Web."""
        view, scene, _trace = self._make_timeline()
        fit_tpp = scene._timescale_per_px
        self.assertTrue(view._at_fit_zoom())
        view.zoom_out()
        self._pump_ms(120)
        self.assertAlmostEqual(scene._timescale_per_px, fit_tpp)
        self.assertTrue(view._fit_mode)
        self.assertTrue(view._at_fit_zoom())

    def test_fit_reaches_trace_end_in_narrow_viewport(self) -> None:
        """Regression: _fit_viewport_size() used to floor to 800px even once
        the widget was realized, so zoom_fit() computed a scale assuming
        more pixels than a narrower (but already laid-out) viewport actually
        had. Fit then silently stopped short of the trace's true end -
        Web has no such floor and doesn't have this bug."""
        view, scene, trace = self._make_timeline(width=500, height=400)
        vp_rect = view.mapToScene(view.viewport().rect()).boundingRect()
        hi_ns = scene.scene_to_ns(vp_rect.right())
        self.assertGreaterEqual(
            hi_ns, trace.time_max - 1,
            "Fit in a narrow (<800px) viewport must still reach the trace's true end")

    def test_zoom_fit_activates_layout_without_pumping_animations(self) -> None:
        """zoom_fit() must activate the layout so a just-resized viewport is
        measured, but must not processEvents() — that pumps QVariantAnimation
        timers and can finish a <cursors zoom="true"/> range-zoom inside Fit
        before fit_to_width() overwrites it."""
        src = (BTF_ROOT / "btf_viewer_pkg" / "view.py").read_text(encoding="utf-8")
        idx = src.find("def zoom_fit")
        self.assertGreaterEqual(idx, 0)
        body = src[idx:idx + 1800]
        self.assertIn("lay.activate()", body)
        self.assertNotIn("_process_ui_events_safely()", body)
        self.assertNotIn(
            "self.zoom_to_cursor_range()", body,
            "toolbar Fit (zoom_fit) must stay Full View; C1–Cn is Ctrl+R / <fit_view/>")

    def test_web_zoom_center_caps_at_fit_like_desktop(self) -> None:
        """Source-parity: Web's zoomCenter must clamp span to the full
        trace span, matching Desktop's scene.zoom() / _do_zoom()."""
        js = WEB_TIMELINE_PANEL.read_text(encoding="utf-8")
        idx = js.find("function zoomCenter(factor")
        self.assertGreaterEqual(idx, 0)
        body = js[idx:idx + 900]
        self.assertIn("Math.min(span, fullSpan)", body)
        self.assertIn("fitToTrace()", body)

    def test_web_toolbar_grays_zoom_out_at_fit(self) -> None:
        tb = (BTF_ROOT / "web" / "src" / "components" / "Toolbar.vue").read_text(
            encoding="utf-8")
        self.assertIn("zoomOutEnabled", tb)
        self.assertIn(":disabled=\"!zoomOutEnabled\"", tb)
        self.assertIn("Already fitted to window", tb)

    def test_web_demo_fit_maps_to_cursor_range(self) -> None:
        """XML <fit_view/> on Web must use Zoom fit to C1–Cn when cursors
        exist, matching Desktop's demo op \"fit\" (not toolbar Fit)."""
        app = (BTF_ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")
        idx = app.find("fit: async () => {")
        self.assertGreaterEqual(idx, 0)
        body = app[idx:idx + 600]
        self.assertIn("zoomToCursorRange", body)
        self.assertIn("placed.length >= 2", body)
        self.assertIn("onFit()", body)

    def test_web_demo_zoom_view_maps_to_full_view(self) -> None:
        """XML <zoom_view/> on Web must call Full View (onFit), matching
        Desktop's demo op \"zoom_view\"."""
        app = (BTF_ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")
        idx = app.find("zoomView: async () => {")
        self.assertGreaterEqual(idx, 0)
        end = app.find("fit: async () => {", idx + 1)
        body = app[idx:end if end > idx else idx + 180]
        self.assertIn("onFit()", body)
        self.assertNotIn("zoomToCursorRange", body)
        js = (BTF_ROOT / "web" / "src" / "utils" / "demoRunner.js").read_text(
            encoding="utf-8")
        self.assertIn("tag === 'zoom_view'", js)
        self.assertIn("host.zoomView", js)

    def test_web_demo_move_view_lockstep_with_desktop(self) -> None:
        """XML <move_view/> on Web must pan/center like Desktop _demo_move_view."""
        app = (BTF_ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")
        idx = app.find("moveView: async")
        self.assertGreaterEqual(idx, 0)
        body = app[idx:app.find("setCursors: async", idx)]
        self.assertIn("expandCore", body)
        self.assertNotIn("expandCoresForMergeKeys", body)
        self.assertIn("ns <= tr.timeMin", body)
        js = (BTF_ROOT / "web" / "src" / "utils" / "demoRunner.js").read_text(
            encoding="utf-8")
        self.assertIn("tag === 'move_view'", js)
        self.assertIn("host.moveView", js)
        mw = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text(
            encoding="utf-8")
        self.assertIn('op in ("move_view", "move_viewport", "pan_view")', mw)
        self.assertIn("def _demo_move_view", mw)

    def test_web_demo_show_message_lockstep_with_desktop(self) -> None:
        """XML <show_message/> on Web must show/wait/clear like Desktop."""
        app = (BTF_ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")
        self.assertIn("showMessage: async", app)
        self.assertIn("clearMessage: async", app)
        self.assertIn("demo-message-overlay", app)
        js = (BTF_ROOT / "web" / "src" / "utils" / "demoRunner.js").read_text(
            encoding="utf-8")
        self.assertIn("tag === 'show_message'", js)
        self.assertIn("host.showMessage", js)
        self.assertIn("host.clearMessage", js)
        mw = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text(
            encoding="utf-8")
        self.assertIn('op == "show_message"', mw)
        self.assertIn('op == "clear_message"', mw)


if __name__ == "__main__":
    unittest.main()
