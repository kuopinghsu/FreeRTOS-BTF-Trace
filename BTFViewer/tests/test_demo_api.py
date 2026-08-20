"""Demo HTTP API: UI commands (view/find/analysis/panel) without mouse coords."""
from __future__ import annotations

import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.config import (  # noqa: E402
    _PANEL_TAB_FIND,
    _PANEL_TAB_STATS,
)
from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402
from btf_viewer_pkg.parser import _task_merge_key  # noqa: E402
from btf_viewer_pkg.stats import _RcSettings  # noqa: E402

from tests import destroy_main_window  # noqa: E402

DEMO_XML = BTF_ROOT / "demos" / "demo_8cores" / "demo_8cores.xml"
DEMO_BTF = BTF_ROOT / "demos" / "demo_8cores" / "demo_8cores.btf.gz"


def _clear_override_cursors() -> None:
    """Pop any leftover setOverrideCursor stack (e.g. abandoned WaitCursor)."""
    app = QApplication.instance()
    if app is None:
        return
    while app.overrideCursor() is not None:
        app.restoreOverrideCursor()


class DemoXmlUsesApiTests(unittest.TestCase):
    def test_toolbar_and_tabs_are_api_not_clicks(self) -> None:
        xml = DEMO_XML.read_text(encoding="utf-8")
        self.assertNotRegex(xml, r'<click\s+target="toolbar_')
        self.assertNotRegex(xml, r'<click\s+target="(stats_tab|ai_tab|find)')
        self.assertIn("<view_mode", xml)
        self.assertIn("<cpu_load", xml)
        self.assertIn("<analysis", xml)
        self.assertIn('<settings page="AI"/>', xml)
        self.assertIn('<settings close="true"/>', xml)
        self.assertIn('<find query="CS[27]"', xml)
        self.assertIn('<find clear="true"', xml)
        # Title step starts from a clean overlay (session leftovers).
        step1 = re.search(r'<step id="1".*?</step>', xml, re.S)
        self.assertIsNotNone(step1)
        body1 = step1.group(0)
        self.assertIn("<clear_cursors/>", body1)
        self.assertIn("<clear_bookmarks/>", body1)
        self.assertIn("<clear_annotations/>", body1)
        self.assertLess(body1.index("<clear_cursors/>"), body1.index("<audio"))
        self.assertLess(body1.index("<clear_bookmarks/>"), body1.index("<audio"))
        self.assertLess(body1.index("<clear_annotations/>"), body1.index("<audio"))
        self.assertIn('target="stats_summary"', body1)
        # Find step must not hop to Statistics after the query.
        step16 = re.search(
            r'<step id="16".*?</step>', xml, re.S)
        self.assertIsNotNone(step16)
        body = step16.group(0)
        self.assertIn("<find", body)
        self.assertNotIn("<click", body)
        self.assertNotIn("stats_tab", body)

    def test_steps_that_place_cursors_clear_them_at_end(self) -> None:
        xml = DEMO_XML.read_text(encoding="utf-8")
        for match in re.finditer(r'<step id="([^"]+)".*?</step>', xml, re.S):
            body = match.group(0)
            last_place = max(body.rfind("<cursors"), body.rfind('ref="place_cursor"'))
            if last_place < 0:
                continue
            last_clear = body.rfind("<clear_cursors/>")
            self.assertGreater(
                last_clear,
                last_place,
                f"step {match.group(1)} places cursors but does not "
                "clear them afterwards",
            )

    def test_toolbar_step_switches_task_core_view(self) -> None:
        xml = DEMO_XML.read_text(encoding="utf-8")
        step4 = re.search(r'<step id="4".*?</step>', xml, re.S)
        self.assertIsNotNone(step4)
        body = step4.group(0)
        self.assertIn('<view_mode mode="task"/>', body)
        self.assertEqual(body.count("<view_mode"), 1)
        self.assertLess(body.index("<focus/>"), body.index('<view_mode mode="task"/>'))
        self.assertLess(body.index('<view_mode mode="task"/>'), body.index("<audio"))
        self.assertNotIn("<analysis", body)
        self.assertIn('target="toolbar_task"', body)
        self.assertIn('target="toolbar_core"', body)
        self.assertIn('target="toolbar_analysis"', body)
        self.assertLess(
            body.index('target="toolbar_task"'),
            body.index('target="toolbar_core"'),
        )
        self.assertLess(
            body.index('target="toolbar_core"'),
            body.index('target="toolbar_analysis"'),
        )
        self.assertIn("<cpu_load", body)
        self.assertLess(body.index('target="toolbar_load"'), body.index("<cpu_load"))
        self.assertLess(body.index('target="stats_tab"'), body.index('<panel name="stats"/>'))
        self.assertLess(body.index('target="find_tab"'), body.index('<panel name="find"/>'))
        self.assertLess(body.index('target="ai_tab"'), body.index('<panel name="ai"/>'))

    def test_views_step_clicks_core_then_task(self) -> None:
        xml = DEMO_XML.read_text(encoding="utf-8")
        step5 = re.search(r'<step id="5".*?</step>', xml, re.S)
        self.assertIsNotNone(step5)
        body = step5.group(0)
        self.assertLess(body.index('target="toolbar_core"'), body.index('<view_mode mode="core"/>'))
        self.assertLess(body.index('<view_mode mode="core"/>'), body.index('target="toolbar_task"'))
        self.assertLess(body.index('target="toolbar_task"'), body.index('<view_mode mode="task"/>'))

    def test_open_step_moves_to_toolbar_icon(self) -> None:
        xml = DEMO_XML.read_text(encoding="utf-8")
        step2 = re.search(r'<step id="2".*?</step>', xml, re.S)
        self.assertIsNotNone(step2)
        body = step2.group(0)
        self.assertIn('target="toolbar_open"', body)

    def test_fit_step_moves_to_toolbar_icon(self) -> None:
        xml = DEMO_XML.read_text(encoding="utf-8")
        step6 = re.search(r'<step id="6".*?</step>', xml, re.S)
        self.assertIsNotNone(step6)
        body = step6.group(0)
        self.assertLess(body.index('target="toolbar_1to1"'), body.index("<zoom_1to1"))
        self.assertLess(body.index("<zoom_1to1"), body.index('target="toolbar_fit"'))
        self.assertLess(body.index('target="toolbar_fit"'), body.index("<zoom_view"))

    def test_summary_step_moves_to_stats_tab(self) -> None:
        xml = DEMO_XML.read_text(encoding="utf-8")
        step7 = re.search(r'<step id="7".*?</step>', xml, re.S)
        self.assertIsNotNone(step7)
        body = step7.group(0)
        self.assertLess(body.index('target="stats_tab"'), body.index('<panel name="stats"/>'))
        self.assertLess(body.index('<panel name="stats"/>'), body.index('target="stats_summary"'))
        self.assertLess(body.index('target="stats_summary"'), body.index('id="cores"'))

    def test_analysis_step_moves_to_toolbar_icon(self) -> None:
        xml = DEMO_XML.read_text(encoding="utf-8")
        step8 = re.search(r'<step id="8".*?</step>', xml, re.S)
        self.assertIsNotNone(step8)
        body = step8.group(0)
        self.assertLess(body.index('target="toolbar_analysis"'), body.index("<analysis/>"))

    def test_health_step_opens_tick_distribution(self) -> None:
        xml = DEMO_XML.read_text(encoding="utf-8")
        step9 = re.search(r'<step id="9".*?</step>', xml, re.S)
        self.assertIsNotNone(step9)
        body = step9.group(0)
        self.assertLess(body.index('target="stats_health"'), body.index('id="health"'))
        self.assertLess(body.index('id="health"'), body.index('target="stats_tick_dist"'))
        self.assertLess(body.index('target="stats_tick_dist"'), body.index("<tick_dist/>"))
        self.assertLess(body.index("<tick_dist/>"), body.index('<tick_dist close="true"/>'))

    def test_find_step_moves_to_find_tab(self) -> None:
        xml = DEMO_XML.read_text(encoding="utf-8")
        step16 = re.search(r'<step id="16".*?</step>', xml, re.S)
        self.assertIsNotNone(step16)
        body = step16.group(0)
        self.assertLess(body.index('target="find_tab"'), body.index("<find "))

    def test_export_step_moves_to_csv_button(self) -> None:
        xml = DEMO_XML.read_text(encoding="utf-8")
        step17 = re.search(r'<step id="17".*?</step>', xml, re.S)
        self.assertIsNotNone(step17)
        body = step17.group(0)
        self.assertIn('<panel name="stats"/>', body)
        self.assertLess(
            body.index('<panel name="stats"/>'),
            body.index('target="stats_export_csv"'),
        )

    def test_ai_setup_step_moves_to_ai_tab(self) -> None:
        xml = DEMO_XML.read_text(encoding="utf-8")
        step18 = re.search(r'<step id="18".*?</step>', xml, re.S)
        self.assertIsNotNone(step18)
        body = step18.group(0)
        self.assertLess(body.index('target="ai_tab"'), body.index('<panel name="ai"/>'))

    def test_cursors_step_fits_then_zooms_out_clears_highlight_then_tab_navs(self) -> None:
        """Step 10 <fit_view/> is Zoom fit to C1–Cn, then <zoom_out/> one
        toolbar step (stops at Full View), then clears the highlight
        and tab-navs. Cursor badges also get their own row (see
        _draw_cursors' delta_row_index), so the C1–Cn fit never squeezes
        C1/C2's labels into an unreadable overlap even when they land
        close together."""
        xml = DEMO_XML.read_text(encoding="utf-8")
        step10 = re.search(r'<step id="10".*?</step>', xml, re.S)
        self.assertIsNotNone(step10)
        body = step10.group(0)
        self.assertIn('<cursors times="3.085,3.310" unit="s" limit="true" zoom="true"/>', body)
        self.assertIn("<clear_highlight/>", body)
        self.assertIn("<tab_nav/>", body)
        self.assertIn("<zoom_view/>", body)
        cursors_idx = body.index('<cursors times="3.085,3.310"')
        reset_idx = body.index("<zoom_view/>")
        fit_idxs = [m.start() for m in re.finditer(r"<fit_view/>", body)]
        zoom_out_idxs = [m.start() for m in re.finditer(r"<zoom_out/>", body)]
        self.assertLess(reset_idx, cursors_idx)
        self.assertTrue(
            any(idx > cursors_idx for idx in fit_idxs),
            "step 10 should fit_view after the cursor zoom")
        self.assertGreaterEqual(
            len(zoom_out_idxs), 1,
            "step 10 should zoom_out after fit_view to keep C1/C2 clear of the boundary")
        clear_idx = body.index("<clear_highlight/>")
        tab_idx = body.index("<tab_nav/>")
        post_fit_idx = next(idx for idx in fit_idxs if idx > cursors_idx)
        self.assertLess(cursors_idx, post_fit_idx)
        self.assertLess(post_fit_idx, zoom_out_idxs[0])
        self.assertLess(zoom_out_idxs[-1], clear_idx)
        self.assertLess(clear_idx, tab_idx)

    def test_runner_maps_ui_tags(self) -> None:
        runner = (BTF_ROOT / "btf_viewer_pkg" / "demo_inapp.py").read_text(
            encoding="utf-8")
        for needle in (
            '"op": "analysis"',
            '"op": "find"',
            '"op": "view_mode"',
            '"op": "cpu_load"',
            '"op": "settings"',
            'tag == "analysis"',
            'tag == "find"',
            'tag == "settings"',
            'tag == "clear_bookmarks"',
            'tag == "clear_annotations"',
            '"op": "clear_bookmarks"',
            '"op": "clear_annotations"',
            '"op": "zoom_1to1"',
            'tag in ("zoom_1to1"',
            '"op": "tick_dist"',
            'tag in ("tick_dist"',
            'tag == "tab_nav"',
            '"op": "tab_nav"',
            'tag == "zoom_in"',
            'tag == "zoom_out"',
            '"op": "zoom_in"',
            '"op": "zoom_out"',
            '"op": "zoom_view"',
            'tag in ("zoom_view"',
            '"op": "move_view"',
            'tag in ("move_view"',
            '"op": "show_message"',
            'tag in ("show_message"',
            '"op": "clear_message"',
        ):
            self.assertIn(needle, runner)


class DemoApiUiTests(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])
        # Prior MainWindow tests close the last window; with the default
        # quitOnLastWindowClosed, Qt posts Quit and QEventLoop.exec returns
        # immediately — aborting BTF load waits and leaking WaitCursor.
        cls._app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        _clear_override_cursors()
        self._tmpdir = tempfile.mkdtemp(prefix="btf_demo_api_")
        self._orig_rc = _RcSettings.RC_PATH
        _RcSettings.RC_PATH = os.path.join(self._tmpdir, "btf_viewer.rc")
        with open(_RcSettings.RC_PATH, "w", encoding="utf-8") as fh:
            fh.write(
                "[view]\n"
                "show_stats=true\n"
                "show_find=true\n"
                "show_marks=true\n"
                "show_legend=true\n"
                "show_cpu_load=true\n"
                "[window]\n"
                "dock_layout_version=12\n"
                "maximized=false\n"
                "width=1200\n"
                "height=800\n"
            )

    def tearDown(self) -> None:
        _clear_override_cursors()
        _RcSettings.RC_PATH = self._orig_rc

    def _wait_trace_loaded(self, win: MainWindow, timeout_ms: int = 20000) -> None:
        """Pump the GUI until the BTF tab is ready (avoid fragile QEventLoop)."""
        win._open_file(str(DEMO_BTF.resolve()))
        deadline = time.monotonic() + (timeout_ms / 1000.0)
        while time.monotonic() < deadline:
            self._app.processEvents()
            if (
                win._tabs
                and getattr(win, "_trace", None) is not None
                and not getattr(win, "_load_in_progress", False)
            ):
                break
            time.sleep(0.02)
        self.assertTrue(
            win._tabs,
            "trace load produced no tabs "
            f"(load_in_progress={getattr(win, '_load_in_progress', None)})",
        )
        self.assertIsNotNone(win._trace)

    def test_view_find_panel_and_analysis_ops(self) -> None:
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win.show()
        self._app.processEvents()

        win._demo_handle({"op": "view_mode", "mode": "core"})
        self.assertEqual(win._view_mode, "core")
        win._demo_handle({"op": "view_mode", "mode": "task"})
        self.assertEqual(win._view_mode, "task")

        win._demo_handle({"op": "cpu_load", "on": False})
        self.assertFalse(win._tb_cpu_load_btn.isChecked())
        win._demo_handle({"op": "cpu_load", "on": True})
        self.assertTrue(win._tb_cpu_load_btn.isChecked())

        win._demo_handle({"op": "panel", "name": "find"})
        self.assertEqual(win._panel_tabs.currentIndex(), _PANEL_TAB_FIND)
        win._demo_handle({"op": "find", "query": "CS[28]", "next": False})
        self.assertEqual(win._find_input.text(), "CS[28]")
        self.assertEqual(win._panel_tabs.currentIndex(), _PANEL_TAB_FIND)
        win._demo_handle({"op": "find", "clear": True})
        self.assertEqual(win._find_input.text(), "")
        self.assertEqual(win._panel_tabs.currentIndex(), _PANEL_TAB_FIND)

        win._demo_handle({"op": "panel", "name": "stats"})
        self.assertEqual(win._panel_tabs.currentIndex(), _PANEL_TAB_STATS)

        opened = win._demo_handle({"op": "analysis"})
        self.assertEqual(opened.get("analysis"), "opening")
        closed = win._demo_handle({"op": "analysis", "close": True})
        self.assertEqual(closed.get("analysis"), "closed")

        win._open_settings = lambda *args, **kwargs: None
        settings = win._demo_handle({"op": "settings", "page": "AI"})
        self.assertEqual(settings.get("settings"), "AI")
        settings_close = win._demo_handle({"op": "settings", "close": True})
        self.assertEqual(settings_close.get("settings"), "closing")

        via_ui = win._demo_handle({"op": "ui", "action": "panel", "name": "find"})
        self.assertEqual(via_ui.get("panel"), "find")
        self.assertEqual(win._panel_tabs.currentIndex(), _PANEL_TAB_FIND)

        open_hit = win._demo_handle({"op": "target", "name": "toolbar_open"})
        open_geo = win._tb.actionGeometry(win._tb_open_btn)
        open_pt = win._tb.mapToGlobal(open_geo.center())
        self.assertEqual(open_hit.get("x"), int(open_pt.x()))
        self.assertEqual(open_hit.get("y"), int(open_pt.y()))
        snap_geo = win._tb.actionGeometry(win._tb_snap_btn)
        snap_pt = win._tb.mapToGlobal(snap_geo.center())
        self.assertLess(int(open_hit.get("x")), int(snap_pt.x()))
        core = win._demo_handle({"op": "target", "name": "toolbar_core"})
        core_geo = win._tb.actionGeometry(win._tb_core_btn)
        core_pt = win._tb.mapToGlobal(core_geo.center())
        self.assertEqual(core.get("x"), int(core_pt.x()))
        self.assertEqual(core.get("y"), int(core_pt.y()))
        fit = win._demo_handle({"op": "target", "name": "toolbar_fit"})
        fit_geo = win._tb.actionGeometry(win._tb_fit_btn)
        fit_pt = win._tb.mapToGlobal(fit_geo.center())
        self.assertEqual(fit.get("x"), int(fit_pt.x()))
        self.assertEqual(fit.get("y"), int(fit_pt.y()))
        combo_pt = win._zoom_preset_combo.mapToGlobal(
            win._zoom_preset_combo.rect().center())
        self.assertLess(int(fit.get("x")), int(combo_pt.x()))
        self.assertLess(int(fit.get("x")), int(core.get("x")))
        self.assertLess(int(open_hit.get("x")), int(fit.get("x")))
        find_tab = win._demo_handle({"op": "target", "name": "find_tab"})
        bar = win._panel_tabs.tabBar()
        tab_pt = bar.mapToGlobal(bar.tabRect(_PANEL_TAB_FIND).center())
        self.assertEqual(find_tab.get("x"), int(tab_pt.x()))
        self.assertEqual(find_tab.get("y"), int(tab_pt.y()))
        stats_hit = win._demo_handle({"op": "target", "name": "stats_summary"})
        summary = getattr(win._stats_panel, "_stats_summary", None)
        self.assertIsNotNone(summary)
        sum_pt = summary.mapToGlobal(summary.rect().center())
        self.assertEqual(stats_hit.get("x"), int(sum_pt.x()))
        self.assertEqual(stats_hit.get("y"), int(sum_pt.y()))
        alias = win._demo_handle({"op": "target", "name": "stats_panel"})
        self.assertEqual(alias.get("x"), stats_hit.get("x"))
        self.assertEqual(alias.get("y"), stats_hit.get("y"))
        cores_hdr = win._stats_panel._section_headers.get("cores")
        if cores_hdr is not None:
            cores_pt = cores_hdr.mapToGlobal(cores_hdr.rect().center())
            self.assertLess(int(stats_hit.get("y")), int(cores_pt.y()))
        with self.assertRaises(ValueError):
            win._demo_handle({"op": "target", "name": "missing_icon"})

    def test_view_mode_updates_loaded_scene(self) -> None:
        if not DEMO_BTF.is_file():
            self.skipTest(f"missing demo BTF: {DEMO_BTF}")
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win.show()
        self._app.processEvents()
        self._wait_trace_loaded(win)

        scene = win._view._scene
        result = win._demo_handle({"op": "view_mode", "mode": "core"})
        self._app.processEvents()
        self.assertEqual(result.get("view_mode"), "core")
        self.assertEqual(scene._view_mode, "core")
        self.assertTrue(win._tb_core_btn.isChecked())
        self.assertFalse(win._tb_task_btn.isChecked())

        win._demo_handle({"op": "view_mode", "mode": "task"})
        self._app.processEvents()
        self.assertEqual(scene._view_mode, "task")

    def test_stats_section_scrolls_late_section_to_top(self) -> None:
        if not DEMO_BTF.is_file():
            self.skipTest(f"missing demo BTF: {DEMO_BTF}")
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win.show()
        win.resize(1280, 800)
        self._app.processEvents()
        self._wait_trace_loaded(win)

        panel = win._stats_panel
        panel._scroll.setFixedHeight(200)
        self._app.processEvents()

        result = win._demo_handle({
            "op": "stats_section",
            "id": "priority",
            "expand": True,
            "collapse_others": True,
            "scroll": "priority",
        })
        self.assertEqual(result.get("scroll"), "priority")

        bar = panel._scroll.verticalScrollBar()
        row = panel._section_header_rows["priority"]
        header_y = row.mapTo(panel._inner, QPoint(0, 0)).y()
        top = bar.value()
        bottom = top + panel._scroll.viewport().height()
        self.assertGreater(bar.maximum(), 0)
        self.assertTrue(
            top <= header_y < bottom,
            f"priority header y={header_y} not in viewport {top}-{bottom}",
        )
        # Prefer-top: header should sit near the top of the viewport.
        self.assertLessEqual(abs(header_y - top), 24)

    def test_clear_cursors_bookmarks_and_annotations(self) -> None:
        if not DEMO_BTF.is_file():
            self.skipTest(f"missing demo BTF: {DEMO_BTF}")
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win.show()
        self._app.processEvents()
        self._wait_trace_loaded(win)

        win._demo_handle({"op": "cursors", "times": "3.085", "unit": "s"})
        self._app.processEvents()
        self.assertTrue(win._view._scene.cursor_times())
        tmin = int(win._trace.time_min)
        win._add_bookmark_at_ns(tmin)
        win._add_annotation_with_note(tmin, "demo leftover", show_marks_panel=False)
        self._app.processEvents()
        self.assertTrue(win._bookmarks)
        self.assertTrue(win._annotations)

        win._demo_handle({"op": "clear_cursors"})
        win._demo_handle({"op": "clear_bookmarks"})
        win._demo_handle({"op": "clear_annotations"})
        self._app.processEvents()
        self.assertEqual(win._view._scene.cursor_times(), [])
        self.assertEqual(list(win._bookmarks), [])
        self.assertEqual(list(win._annotations), [])

    def test_tab_nav_op_jumps_to_first_segment_after_cursor(self) -> None:
        if not DEMO_BTF.is_file():
            self.skipTest(f"missing demo BTF: {DEMO_BTF}")
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win.show()
        self._app.processEvents()
        self._wait_trace_loaded(win)

        view = win._view
        scene = view._scene
        view.zoom_fit()
        self._app.processEvents()

        win._demo_handle({
            "op": "cursors", "times": "3.085,3.310", "unit": "s", "limit": True,
        })
        self._app.processEvents()
        win._demo_handle({"op": "fit"})
        self._app.processEvents()
        win._demo_handle({"op": "clear_highlight"})
        self.assertIsNone(scene._locked_task)

        win._demo_handle({"op": "tab_nav", "forward": True})
        self._app.processEvents()
        self.assertIsNotNone(scene._locked_segment_key)
        c1_ns = min(win._view._scene.cursor_times())
        self.assertGreaterEqual(scene._locked_ns, c1_ns)

        # Alias via the generic ui/command dispatch, and Shift+Tab direction.
        win._demo_handle({"op": "ui", "action": "clear_highlight"})
        self.assertIsNone(scene._locked_task)
        win._demo_handle({"op": "ui", "action": "tab_nav", "forward": False})
        self._app.processEvents()
        self.assertIsNotNone(scene._locked_segment_key)
        self.assertGreaterEqual(scene._locked_ns, c1_ns)

    def test_zoom_in_out_ops_match_toolbar_and_zoom_out_stops_at_fit(self) -> None:
        if not DEMO_BTF.is_file():
            self.skipTest(f"missing demo BTF: {DEMO_BTF}")
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win.show()
        self._app.processEvents()
        self._wait_trace_loaded(win)

        view = win._view
        scene = view._scene
        view.zoom_fit()
        self._app.processEvents()
        fit_tpp = scene._timescale_per_px
        self.assertTrue(view._at_fit_zoom())
        self.assertFalse(win._tb_zoom_out_btn.isEnabled())

        # <zoom_out/> at Full View is a no-op; the button stays grayed.
        win._demo_handle({"op": "zoom_out"})
        self._pump_ms(150)
        self.assertAlmostEqual(scene._timescale_per_px, fit_tpp, delta=fit_tpp * 0.02)
        self.assertTrue(view._fit_mode)
        self.assertFalse(win._tb_zoom_out_btn.isEnabled())

        win._demo_handle({"op": "zoom_in"})
        self._pump_ms(150)
        win._demo_handle({"op": "zoom_in"})
        self._pump_ms(150)
        self.assertLess(scene._timescale_per_px, fit_tpp)
        self.assertFalse(view._fit_mode)
        self.assertTrue(win._tb_zoom_out_btn.isEnabled())

    def test_cursor_zoom_stays_at_range_scale_without_following_fit(self) -> None:
        """<cursors zoom="true"/> must land on the tight C1-Cn scale (~us/px),
        not full-trace Fit (~ms/px). Matches Web once the range-zoom
        animation is allowed to finish (demo settle / awaited rAF)."""
        if not DEMO_BTF.is_file():
            self.skipTest(f"missing demo BTF: {DEMO_BTF}")
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win.show()
        self._app.processEvents()
        self._wait_trace_loaded(win)

        view = win._view
        scene = view._scene
        view.zoom_fit()
        self._app.processEvents()
        fit_tpp = scene._timescale_per_px

        win._demo_handle({
            "op": "cursors", "times": "3.085,3.310", "unit": "s",
            "limit": True, "zoom": True,
        })
        self._pump_ms(500)
        self._app.processEvents()
        self.assertLess(
            scene._timescale_per_px, fit_tpp * 0.25,
            "cursor zoom must stay on C1-Cn, not snap back to full-trace Fit")
        self.assertFalse(view._fit_mode)

    def test_cursor_zoom_then_fit_zoom_out_centers_cursors(self) -> None:
        """<cursors zoom="true"/> then <fit_view/> then <zoom_out/> must
        match toolbar Zoom fit to C1–Cn + Zoom Out (not Zoom Full View):
        C1–C2 fill the view (~µs/px), zoom-out is one 1.43× step, and
        C1–C2 sit at the viewport center."""
        if not DEMO_BTF.is_file():
            self.skipTest(f"missing demo BTF: {DEMO_BTF}")
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win.show()
        self._app.processEvents()
        self._wait_trace_loaded(win)

        view = win._view
        scene = view._scene
        view.zoom_fit()
        self._app.processEvents()
        fit_tpp = scene._timescale_per_px
        c1_ns, c2_ns = 3085000, 3310000

        win._demo_handle({
            "op": "cursors", "times": "3.085,3.310", "unit": "s",
            "limit": True, "zoom": True,
        })
        self._app.processEvents()
        self.assertLess(scene._timescale_per_px, fit_tpp * 0.25)

        win._demo_handle({"op": "fit"})
        self._app.processEvents()
        range_tpp = scene._timescale_per_px
        self.assertLess(
            range_tpp, fit_tpp * 0.25,
            "Fit with C1–C2 placed must fit the cursor range, not the full trace")

        win._demo_handle({"op": "zoom_view"})
        self._app.processEvents()
        self.assertAlmostEqual(
            scene._timescale_per_px, fit_tpp, delta=fit_tpp * 0.05,
            msg="<zoom_view/> must still fit the entire trace when C1–C2 exist")
        win._demo_handle({"op": "fit"})
        self._app.processEvents()
        self.assertLess(
            scene._timescale_per_px, fit_tpp * 0.25,
            "<fit_view/> must restore C1–Cn fit after <zoom_view/>")
        range_tpp = scene._timescale_per_px

        win._demo_handle({"op": "zoom_out"})
        self._app.processEvents()
        self.assertGreater(scene._timescale_per_px, range_tpp * 1.2)
        self.assertAlmostEqual(
            scene._timescale_per_px / range_tpp, 1.43, delta=0.05)

        win._demo_handle({"op": "clear_highlight"})
        win._demo_handle({"op": "tab_nav"})
        self._pump_ms(1500)
        self._app.processEvents()
        self.assertGreater(
            scene._timescale_per_px, range_tpp * 1.2,
            "zoom_out must stay one toolbar step past the C1–C2 Fit scale")

        vp_c = view.mapToScene(view.viewport().rect().center())
        mid_coord = vp_c.x() if scene._horizontal else vp_c.y()
        cur_coord = (
            scene.ns_to_scene_coord(c1_ns) + scene.ns_to_scene_coord(c2_ns)
        ) / 2
        span = max(view.viewport().width() if scene._horizontal else view.viewport().height(), 1)
        self.assertLess(
            abs(cur_coord - mid_coord) / span, 0.08,
            "C1–C2 midpoint must sit at the viewport center after fit+zoom_out")

    def test_cursor_zoom_animation_updates_status_bar_zoom_label(self) -> None:
        """Regression: the status-bar zoom label (and zoom-preset combo) must
        track <cursors zoom="true"/>'s animated range-zoom — it used to stay
        frozen at whatever it showed before the AI-driven zoom because
        _ai_zoom_to_range mutated scene state directly without emitting
        zoom_changed (reported: Desktop's readout stuck at the pre-step
        value through fit_view + zoom_out, unlike Web)."""
        if not DEMO_BTF.is_file():
            self.skipTest(f"missing demo BTF: {DEMO_BTF}")
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win.show()
        self._app.processEvents()
        self._wait_trace_loaded(win)

        view = win._view
        scene = view._scene
        view.zoom_fit()
        self._app.processEvents()
        fit_label = win._zoom_scale_label.text()

        win._demo_handle({
            "op": "cursors", "times": "3.085,3.310", "unit": "s",
            "limit": True, "zoom": True,
        })
        self._pump_ms(500)  # matches demo XML's real <cursors zoom="true"/> settle
        self._app.processEvents()
        self.assertLess(scene._timescale_per_px, scene._timescale_per_px_fit)
        zoomed_label = win._zoom_scale_label.text()
        self.assertNotEqual(
            zoomed_label, fit_label,
            "zoom label must reflect the tight cursor-range zoom, not stay frozen")

        win._demo_handle({"op": "fit"})
        self._pump_ms(400)
        self._app.processEvents()
        range_label = win._zoom_scale_label.text()
        range_tpp = scene._timescale_per_px
        self.assertNotEqual(range_label, fit_label)
        self.assertLess(range_tpp, scene._timescale_per_px_fit * 0.25)

        win._demo_handle({"op": "zoom_out"})
        self._pump_ms(400)
        self._app.processEvents()
        self.assertGreater(scene._timescale_per_px, range_tpp * 1.2)
        self.assertNotEqual(
            win._zoom_scale_label.text(), range_label,
            "zoom label must reflect zoom_out one step past C1–C2 Fit")

    def test_cursor_zoom_then_fit_then_zoom_out_keeps_both_cursors_on_screen(self) -> None:
        """Regression: C1/C2 must stay on-screen (not clipped by the label
        column or the viewport's right edge) after fitting the view back out
        from a tight cursor zoom, even when the cursors sit close together
        near the end of the trace. A trailing <zoom_out/> after C1–Cn fit
        (still zoomed in past Full View) adds margin around the cursors."""
        if not DEMO_BTF.is_file():
            self.skipTest(f"missing demo BTF: {DEMO_BTF}")
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win.show()
        self._app.processEvents()
        self._wait_trace_loaded(win)

        view = win._view
        scene = view._scene
        view.zoom_fit()
        self._app.processEvents()

        c1_ns, c2_ns = 3085000, 3310000
        win._demo_handle({
            "op": "cursors", "times": "3.085,3.310", "unit": "s",
            "limit": True, "zoom": True,
        })
        self._pump_ms(500)
        self._app.processEvents()

        win._demo_handle({"op": "fit"})
        self._pump_ms(400)
        self._app.processEvents()
        c2_x = scene.ns_to_scene_coord(c2_ns)
        fit_right_x = view.mapToScene(view.viewport().rect()).boundingRect().right()
        fit_margin_px = fit_right_x - c2_x

        win._demo_handle({"op": "zoom_out"})
        self._pump_ms(400)
        self._app.processEvents()

        vp_rect = view.mapToScene(view.viewport().rect()).boundingRect()
        lo_ns = scene.scene_to_ns(vp_rect.left() + scene._label_width)
        hi_ns = scene.scene_to_ns(vp_rect.right())
        self.assertLess(lo_ns, c1_ns, "C1 must not be clipped by the label column")
        self.assertGreater(hi_ns, c2_ns, "C2 must not be clipped by the viewport's right edge")

        c2_x2 = scene.ns_to_scene_coord(c2_ns)
        zoomed_margin_px = vp_rect.right() - c2_x2
        self.assertGreater(
            zoomed_margin_px, fit_margin_px,
            "zoom_out after fit_view must add visible margin past C2")

    def test_cursor_badges_stay_readable_when_cursors_close_together(self) -> None:
        """The two cursors' own badges and the delta badge between them must
        never overlap on-screen, even when the cursors are close together
        (the root cause of the earlier "invisible cursor" report - it was
        actually the delta badge overlapping the later cursor's own badge,
        not the cursor itself being off-screen)."""
        if not DEMO_BTF.is_file():
            self.skipTest(f"missing demo BTF: {DEMO_BTF}")
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win.show()
        self._app.processEvents()
        self._wait_trace_loaded(win)

        view = win._view
        scene = view._scene
        view.zoom_fit()
        self._app.processEvents()

        win._demo_handle({
            "op": "cursors", "times": "3.085,3.310", "unit": "s",
            "limit": True, "zoom": True,
        })
        self._pump_ms(500)
        self._app.processEvents()
        win._demo_handle({"op": "fit"})
        self._pump_ms(400)
        self._app.processEvents()

        scene._draw_cursors()
        rows = {}
        for item in scene._cursor_items:
            rect = item.sceneBoundingRect()
            if rect.width() <= 0 or rect.height() <= 0:
                continue
            rows.setdefault(round(rect.top()), []).append(rect)
        for _y, rects in rows.items():
            rects.sort(key=lambda r: r.left())
            for a, b in zip(rects, rects[1:]):
                self.assertLessEqual(
                    a.right(), b.left() + 0.5,
                    "cursor/delta badges on the same row must not overlap")

    def test_move_view_time_and_task(self) -> None:
        """<move_view/> pans time (left vs center) and centers a task row."""
        if not DEMO_BTF.is_file():
            self.skipTest(f"missing demo BTF: {DEMO_BTF}")
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win.show()
        self._app.processEvents()
        self._wait_trace_loaded(win)

        view = win._view
        scene = view._scene
        win.resize(1200, 800)
        win._demo_handle({"op": "zoom_1to1"})
        self._pump_ms(200)
        self._app.processEvents()

        row_bar = (view.verticalScrollBar() if scene._horizontal
                   else view.horizontalScrollBar())
        if row_bar.maximum() > row_bar.minimum():
            row_bar.setValue(row_bar.maximum())
            self._app.processEvents()
            self.assertGreater(row_bar.value(), row_bar.minimum())

        win._demo_handle({"op": "move_view", "time": "3.085", "unit": "s"})
        self._pump_ms(200)
        self._app.processEvents()
        lo, hi = view._visible_time_ns_range()
        tmin = int(win._trace.time_min)
        span = max(hi - lo, 1)
        self.assertGreater(
            lo, tmin + span * 0.2,
            "zoomed 1:1 view must leave the trace start before testing leftmost pan")

        win._demo_handle({"op": "move_view", "time": "0"})
        self._pump_ms(200)
        self._app.processEvents()
        lo, hi = view._visible_time_ns_range()
        span = max(hi - lo, 1)
        self.assertLessEqual(
            abs(lo - tmin), max(5000, span * 0.08),
            "time=0 must pin the trace start to the left of the plot")
        row_bar = (view.verticalScrollBar() if scene._horizontal
                   else view.horizontalScrollBar())
        self.assertEqual(
            row_bar.value(), row_bar.minimum(),
            "time=0 with no task must scroll the task list to the top")

        target_ns = 3085000
        mk = _task_merge_key("CS[27]")
        win._demo_handle({
            "op": "move_view", "time": "3.085", "unit": "s", "task": "CS[27]",
        })
        self._pump_ms(200)
        self._app.processEvents()
        lo, hi = view._visible_time_ns_range()
        mid = (lo + hi) / 2
        span = max(hi - lo, 1)
        self.assertLessEqual(
            abs(mid - target_ns), max(10000, span * 0.25),
            "time+task must center the requested timestamp")
        orth = scene.task_orth_scene_coord(mk)
        self.assertIsNotNone(orth)
        row_h = max(float(scene._row_height), 1.0)
        self.assertLessEqual(
            abs(orth - self._viewport_orth_center(view)), row_h * 1.5,
            "time+task must keep the task row as centered as the layout allows")

        segs = win._trace.seg_map_by_merge_key.get(mk, [])
        self.assertTrue(segs, "demo trace must include CS[27] segments")
        first = min(int(s.start) for s in segs)
        win._demo_handle({"op": "move_view", "task": "CS[27]"})
        self._pump_ms(200)
        self._app.processEvents()
        lo, hi = view._visible_time_ns_range()
        mid = (lo + hi) / 2
        span = max(hi - lo, 1)
        self.assertLessEqual(
            abs(mid - first), max(10000, span * 0.25),
            "omitted time + task must center the task's first segment")
        orth = scene.task_orth_scene_coord(mk)
        self.assertLessEqual(
            abs(orth - self._viewport_orth_center(view)), row_h * 1.5)

    def _viewport_orth_center(self, view):
        scene = view._scene
        cur = view.mapToScene(view.viewport().rect().center())
        return cur.y() if scene._horizontal else cur.x()

    def _pump_ms(self, ms: int) -> None:
        from PySide6.QtCore import QEventLoop, QTimer
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()


if __name__ == "__main__":
    unittest.main()
