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
        self.assertIn('<find query="CS[27]"', xml)
        self.assertIn('<find clear="true"', xml)
        # Find step must not hop to Statistics after the query.
        step16 = re.search(
            r'<step id="16".*?</step>', xml, re.S)
        self.assertIsNotNone(step16)
        body = step16.group(0)
        self.assertIn("<find", body)
        self.assertNotIn("<click", body)
        self.assertNotIn("stats_tab", body)

    def test_toolbar_step_switches_task_core_view(self) -> None:
        xml = DEMO_XML.read_text(encoding="utf-8")
        step4 = re.search(r'<step id="4".*?</step>', xml, re.S)
        self.assertIsNotNone(step4)
        body = step4.group(0)
        self.assertIn('<view_mode mode="core"/>', body)
        self.assertIn('<view_mode mode="task"/>', body)
        self.assertIn("<cpu_load", body)

    def test_runner_maps_ui_tags(self) -> None:
        runner = (BTF_ROOT / "scripts" / "demo_runner.py").read_text(
            encoding="utf-8")
        for needle in (
            '"op": "analysis"',
            '"op": "find"',
            '"op": "view_mode"',
            '"op": "cpu_load"',
            'tag == "analysis"',
            'tag == "find"',
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

        via_ui = win._demo_handle({"op": "ui", "action": "panel", "name": "find"})
        self.assertEqual(via_ui.get("panel"), "find")
        self.assertEqual(win._panel_tabs.currentIndex(), _PANEL_TAB_FIND)

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


if __name__ == "__main__":
    unittest.main()
