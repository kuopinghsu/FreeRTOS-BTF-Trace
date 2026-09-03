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
PY_RUNNER = BTF_ROOT / "btf_viewer_pkg" / "demo_inapp.py"

SETTINGS_PAGES = ("Appearance", "Display", "Layout", "AI")


class DemoSettingsSourceParityTests(unittest.TestCase):
    def test_step18_opens_ai_settings_then_closes(self) -> None:
        xml = DEMO_XML.read_text(encoding="utf-8")
        step = re.search(r'<step[^>]*title="AI setup".*?</step>', xml, re.S)
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

    def test_settings_sidebar_category_icons_match(self) -> None:
        """Each category has an icon (desktop was missing them) and the four
        Bootstrap glyphs are byte-identical between config.py and the web
        SettingsDialog. The AI glyph is `robot`, not the old crescent moon."""
        cfg = (BTF_ROOT / "btf_viewer_pkg" / "config.py").read_text(encoding="utf-8")
        stats = DESKTOP_STATS.read_text(encoding="utf-8")
        vue = WEB_SETTINGS.read_text(encoding="utf-8")

        # circle-half / display / columns-gap / robot — the exact path data.
        glyphs = {
            "_IC_SET_APPEARANCE": "M8 15A7 7 0 1 0 8 1v14zm0 1A8 8 0 1 1 8 0a8 8 0 0 1 0 16z",
            "_IC_SET_DISPLAY": "M0 4s0-2 2-2h12s2 0 2 2v6s0 2-2 2h-4c0 .667.083 1.167.25 1.5H11",
            "_IC_SET_LAYOUT": "M6 1v3H1V1h5zM1 0a1 1 0 0 0-1 1v3a1 1 0 0 0 1 1h5a1 1 0 0 0 1-1V1",
            "_IC_SET_AI": "M6 12.5a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 0 1h-3a.5.5 0 0 1-.5-.5Z",
        }
        for const, needle in glyphs.items():
            self.assertIn(f"{const} = ", cfg)
            self.assertIn(needle, cfg)
            self.assertIn(needle, vue)

        # Desktop sidebar rows now carry an icon per category.
        self.assertIn("_item.setIcon(_svg_icon(_nav_icons[_name]", stats)
        self.assertIn("self._sidebar.setIconSize(QSize(16, 16))", stats)

        # The old moon path must be gone from the AI category on web.
        self.assertNotIn("M6 .278a.768.768", vue)

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

        from tests import destroy_main_window

        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win._open_settings = lambda *args, **kwargs: None
        opened = win._demo_handle({"op": "settings", "page": "ai"})
        self.assertEqual(opened.get("settings"), "AI")
        opened_exact = win._demo_handle({"op": "settings", "page": "AI"})
        self.assertEqual(opened_exact.get("settings"), "AI")

    def test_demo_api_closes_visible_settings_dialog(self) -> None:
        from PySide6.QtWidgets import QDialog
        from btf_viewer_pkg.mainwindow import MainWindow

        from tests import destroy_main_window

        # `_demo_close_settings` sweeps every top-level widget titled "Settings",
        # so a stray dialog left visible by a sibling test would be closed
        # instead of ours. Neutralise any leftovers before we start.
        for w in list(self._app.topLevelWidgets()):
            try:
                if w.windowTitle() == "Settings":
                    w.hide()
                    w.deleteLater()
            except RuntimeError:
                pass
        self._app.processEvents()

        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        dlg = QDialog()
        self.addCleanup(dlg.deleteLater)
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
