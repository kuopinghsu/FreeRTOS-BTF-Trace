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
from btf_viewer_pkg.stats import _RcSettings  # noqa: E402

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
        self.assertLess(body.index('target="toolbar_fit"'), body.index("<fit_view"))

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
        self.addCleanup(win.close)
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
        self.addCleanup(win.close)
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
        self.addCleanup(win.close)
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
        self.addCleanup(win.close)
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


if __name__ == "__main__":
    unittest.main()
