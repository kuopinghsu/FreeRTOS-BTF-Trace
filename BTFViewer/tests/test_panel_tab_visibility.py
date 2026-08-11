"""Right-panel tabs follow btf_viewer.rc, and the View menu says so."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

import tests  # noqa: F401 — applies QT_QPA_PLATFORM / QT_LOGGING_RULES

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "builds" / "btf_viewer.py"


def _load_bundle():
    spec = importlib.util.spec_from_file_location("btf_viewer_bundle", BUNDLE)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _wait_ms(app, ms: int) -> None:
    from PySide6.QtCore import QTimer

    QTimer.singleShot(ms, app.quit)
    app.exec()
    app.processEvents()


class PanelTabVisibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not BUNDLE.is_file():
            raise unittest.SkipTest(f"bundle missing: {BUNDLE}")
        cls.btf = _load_bundle()

    def _write_rc(self, marks: str, find: str) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="btf_panel_rc_")
        self.rc_path = os.path.join(self._tmpdir, "btf_viewer.rc")
        self.btf._RcSettings.RC_PATH = self.rc_path
        with open(self.rc_path, "w", encoding="utf-8") as fh:
            fh.write(
                "[view]\n"
                "show_legend=true\n"
                "show_stats=true\n"
                f"show_marks={marks}\n"
                f"show_find={find}\n"
                "show_ai=true\n"
                "[window]\n"
                "dock_layout_version=12\n"
                "maximized=false\n"
                "width=1200\n"
                "height=800\n"
            )

    def _start(self):
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        win = self.btf.MainWindow()
        win.show()
        _wait_ms(app, 400)
        return app, win

    def test_all_five_tabs_visible_by_default(self) -> None:
        self._write_rc("true", "true")
        app, win = self._start()
        try:
            for idx, name in enumerate(("Statistics", "Marks", "Find", "Legend", "AI")):
                self.assertTrue(
                    win._panel_tabs.isTabVisible(idx),
                    f"{name} tab hidden with show_* all true",
                )
        finally:
            win.close()

    def test_rc_hides_marks_and_find(self) -> None:
        """The reported symptom: only Statistics and AI survive a false-y rc."""
        self._write_rc("false", "false")
        app, win = self._start()
        try:
            self.assertTrue(win._panel_tabs.isTabVisible(self.btf._PANEL_TAB_STATS))
            self.assertFalse(win._panel_tabs.isTabVisible(self.btf._PANEL_TAB_MARKS))
            self.assertFalse(win._panel_tabs.isTabVisible(self.btf._PANEL_TAB_FIND))
            self.assertTrue(win._panel_tabs.isTabVisible(self.btf._PANEL_TAB_LEGEND))
            self.assertTrue(win._panel_tabs.isTabVisible(self.btf._PANEL_TAB_AI))
            # The View menu used to claim both panels were on regardless.
            self.assertFalse(
                win._act_show_marks.isChecked(),
                "View → Show Marks Panel checked while the tab is hidden",
            )
            self.assertFalse(
                win._act_show_find.isChecked(),
                "View → Show Find Panel checked while the tab is hidden",
            )
        finally:
            win.close()

    def test_menu_toggle_brings_hidden_tabs_back(self) -> None:
        self._write_rc("false", "false")
        app, win = self._start()
        try:
            win._act_show_marks.trigger()
            win._act_show_find.trigger()
            app.processEvents()
            self.assertTrue(win._panel_tabs.isTabVisible(self.btf._PANEL_TAB_MARKS))
            self.assertTrue(win._panel_tabs.isTabVisible(self.btf._PANEL_TAB_FIND))
            self.assertTrue(win._act_show_marks.isChecked())
            self.assertTrue(win._act_show_find.isChecked())
        finally:
            win.close()


if __name__ == "__main__":
    unittest.main()
