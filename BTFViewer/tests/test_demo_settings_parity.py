"""Desktop ↔ web demo Settings parity (AI page open/close).

Shared contract: demos/demo_8cores/demo_8cores.xml step 18
``<settings page="AI"/>`` then ``<settings close="true"/>``.
"""
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

DEMO_XML = BTF_ROOT / "demos" / "demo_8cores" / "demo_8cores.xml"
WEB_RUNNER = BTF_ROOT / "web" / "src" / "utils" / "demoRunner.js"
WEB_APP = BTF_ROOT / "web" / "src" / "App.vue"
WEB_SETTINGS = BTF_ROOT / "web" / "src" / "components" / "SettingsDialog.vue"
DESKTOP_MW = BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py"
DESKTOP_STATS = BTF_ROOT / "btf_viewer_pkg" / "stats.py"
PY_RUNNER = BTF_ROOT / "scripts" / "demo_runner.py"

SETTINGS_PAGES = ("Appearance", "Display", "Layout", "AI")


class DemoSettingsSourceParityTests(unittest.TestCase):
    def test_step18_opens_ai_settings_then_closes(self) -> None:
        xml = DEMO_XML.read_text(encoding="utf-8")
        step = re.search(r'<step id="18".*?</step>', xml, re.S)
        self.assertIsNotNone(step)
        body = step.group(0)
        self.assertIn('<settings page="AI"/>', body)
        self.assertIn('<settings close="true"/>', body)
        self.assertLess(body.index('page="AI"'), body.index('close="true"'))

    def test_settings_sidebar_pages_match(self) -> None:
        py = DESKTOP_STATS.read_text(encoding="utf-8")
        vue = WEB_SETTINGS.read_text(encoding="utf-8")
        self.assertIn(
            'for _name in ("Appearance", "Display", "Layout", "AI")', py)
        for name, label in (
            ("appearance", "Appearance"),
            ("display", "Display"),
            ("layout", "Layout"),
            ("ai", "AI"),
        ):
            self.assertIn(f"id: '{name}'", vue)
            self.assertIn(f"label: '{label}'", vue)

    def test_web_and_desktop_both_wire_open_and_close(self) -> None:
        runner = WEB_RUNNER.read_text(encoding="utf-8")
        app = WEB_APP.read_text(encoding="utf-8")
        mw = DESKTOP_MW.read_text(encoding="utf-8")
        py_runner = PY_RUNNER.read_text(encoding="utf-8")

        self.assertIn("tag === 'settings'", runner)
        self.assertIn("host.closeSettings", runner)
        self.assertIn("host.pressEscape", runner)
        self.assertIn("page: attr(el, 'page'", runner)

        self.assertIn("function demoSettingsTab(page)", app)
        self.assertIn("p.includes('ai')", app)
        self.assertIn("closeSettings:", app)
        self.assertIn("function closeSettingsDialog()", app)
        self.assertIn("openSettingsDialog(demoSettingsTab(page))", app)

        self.assertIn("def _demo_settings(", mw)
        self.assertIn("def _demo_close_settings(", mw)
        self.assertIn("def _normalize_settings_page(", mw)
        self.assertIn('return "AI"', mw)

        self.assertIn('"op": "settings"', py_runner)
        self.assertIn('for key in ("page", "name", "open", "close", "action")', py_runner)
        self.assertIn('<settings page="AI"/>', py_runner)
        self.assertIn('<settings close="true"/>', py_runner)

    def test_page_mapper_order_matches_web(self) -> None:
        """AI is matched before Display/Layout on both sides."""
        app = WEB_APP.read_text(encoding="utf-8")
        mw = DESKTOP_MW.read_text(encoding="utf-8")
        web_fn = re.search(
            r"function demoSettingsTab\(page\) \{([\s\S]*?)\n\}", app)
        py_fn = re.search(
            r"def _normalize_settings_page\(page: str\) -> str:([\s\S]*?)\n\ndef ", mw)
        self.assertIsNotNone(web_fn)
        self.assertIsNotNone(py_fn)
        web_body, py_body = web_fn.group(1), py_fn.group(1)
        self.assertLess(web_body.index("ai"), web_body.index("display"))
        self.assertLess(web_body.index("display"), web_body.index("layout"))
        self.assertLess(py_body.index('"AI"'), py_body.index('"Display"'))
        self.assertLess(py_body.index('"Display"'), py_body.index('"Layout"'))


class DemoSettingsRuntimeParityTests(unittest.TestCase):
    _app = None

    @classmethod
    def setUpClass(cls) -> None:
        from btf_viewer_pkg._bootstrap import install
        install()
        from PySide6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication([])
        cls._app.setQuitOnLastWindowClosed(False)

    def test_normalize_settings_page_matches_web_mapper(self) -> None:
        from btf_viewer_pkg.mainwindow import _normalize_settings_page
        cases = {
            "AI": "AI",
            "ai": "AI",
            "Settings → AI": "AI",
            "Display": "Display",
            "display": "Display",
            "Layout": "Layout",
            "layout": "Layout",
            "Appearance": "Appearance",
            "appearance": "Appearance",
            "": "Appearance",
            "unknown": "Appearance",
        }
        for raw, want in cases.items():
            self.assertEqual(_normalize_settings_page(raw), want, raw)

    def test_demo_api_maps_ai_page_without_opening_modal(self) -> None:
        from btf_viewer_pkg.mainwindow import MainWindow

        win = MainWindow()
        self.addCleanup(win.close)
        win._open_settings = lambda *args, **kwargs: None
        opened = win._demo_handle({"op": "settings", "page": "ai"})
        self.assertEqual(opened.get("settings"), "AI")
        opened_exact = win._demo_handle({"op": "settings", "page": "AI"})
        self.assertEqual(opened_exact.get("settings"), "AI")

    def test_demo_api_closes_visible_settings_dialog(self) -> None:
        from PySide6.QtWidgets import QDialog
        from btf_viewer_pkg.mainwindow import MainWindow

        win = MainWindow()
        self.addCleanup(win.close)
        dlg = QDialog()
        self.addCleanup(dlg.close)
        dlg.setWindowTitle("Settings")
        dlg.setModal(False)
        dlg.show()
        self._app.processEvents()
        self.assertTrue(dlg.isVisible())
        closed = win._demo_handle({"op": "settings", "close": True})
        self.assertEqual(closed.get("settings"), "closing")
        self._app.processEvents()
        self.assertFalse(dlg.isVisible())


if __name__ == "__main__":
    unittest.main()
