"""Demo HTTP API: UI commands (view/find/analysis/panel) without mouse coords."""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.config import (  # noqa: E402
    _PANEL_TAB_FIND,
    _PANEL_TAB_STATS,
)
from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402
from btf_viewer_pkg.stats import _RcSettings  # noqa: E402

DEMO_XML = BTF_ROOT / "scripts" / "demos" / "demo_8cores" / "demo_8cores.xml"


class DemoXmlUsesApiTests(unittest.TestCase):
    def test_toolbar_and_tabs_are_api_not_clicks(self) -> None:
        xml = DEMO_XML.read_text(encoding="utf-8")
        self.assertNotRegex(xml, r'<click\s+target="toolbar_')
        self.assertNotRegex(xml, r'<click\s+target="(stats_tab|ai_tab|find)')
        self.assertIn("<view_mode", xml)
        self.assertIn("<cpu_load", xml)
        self.assertIn("<analysis", xml)
        self.assertIn('<find query="CS[28]"', xml)
        self.assertIn('<find clear="true"', xml)
        # Find step must not hop to Statistics after the query.
        step16 = re.search(
            r'<step id="16".*?</step>', xml, re.S)
        self.assertIsNotNone(step16)
        body = step16.group(0)
        self.assertIn("<find", body)
        self.assertNotIn("<click", body)
        self.assertNotIn("stats_tab", body)

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

    def setUp(self) -> None:
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
        _RcSettings.RC_PATH = self._orig_rc

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


if __name__ == "__main__":
    unittest.main()
