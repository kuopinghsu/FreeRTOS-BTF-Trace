"""Legend tab must survive quit + restart when show_legend=true in btf_viewer.rc."""
from __future__ import annotations

import configparser
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


def _read_rc_bool(rc_path: str, key: str) -> bool:
    cfg = configparser.ConfigParser()
    cfg.read(rc_path, encoding="utf-8")
    return cfg.getboolean("view", key, fallback=False)


def _wait_ms(app, ms: int) -> None:
    from PySide6.QtCore import QTimer

    QTimer.singleShot(ms, app.quit)
    app.exec()
    app.processEvents()


class LegendTabRestoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not BUNDLE.is_file():
            raise unittest.SkipTest(f"bundle missing: {BUNDLE}")
        cls.btf = _load_bundle()

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="btf_legend_rc_")
        self.rc_path = os.path.join(self._tmpdir, "btf_viewer.rc")
        self.btf._RcSettings.RC_PATH = self.rc_path
        with open(self.rc_path, "w", encoding="utf-8") as fh:
            fh.write(
                "[view]\n"
                "show_legend=true\n"
                "show_stats=true\n"
                "show_marks=true\n"
                "show_find=true\n"
                "[window]\n"
                "dock_layout_version=12\n"
                "maximized=false\n"
                "width=1200\n"
                "height=800\n"
            )

    def _run_session(self, app, *, persist: bool) -> "btf.MainWindow":
        win = self.btf.MainWindow()
        win.show()
        _wait_ms(app, 400)
        if persist:
            win.close()
            app.processEvents()
        return win

    def test_legend_tab_visible_after_two_starts(self) -> None:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        app.setFont(self.btf._application_ui_font(self.btf.UI_FONT_SIZE))

        win1 = self._run_session(app, persist=True)
        self.assertTrue(
            _read_rc_bool(self.rc_path, "show_legend"),
            f"RC show_legend false after first exit:\n{Path(self.rc_path).read_text()}",
        )
        del win1
        app.processEvents()

        win2 = self.btf.MainWindow()
        win2.show()
        _wait_ms(app, 600)

        self.assertTrue(
            win2._show_legend,
            "view-model show_legend false on second start",
        )
        self.assertTrue(
            _read_rc_bool(self.rc_path, "show_legend"),
            f"RC show_legend false on second start:\n{Path(self.rc_path).read_text()}",
        )
        win2._apply_dock_visibility_respecting_rc()
        app.processEvents()
        self.assertTrue(
            win2._panel_tabs.isTabVisible(self.btf._PANEL_TAB_LEGEND),
            "Legend tab hidden on second start",
        )
        win2.close()

    def test_hiding_legend_tab_does_not_hide_marks(self) -> None:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        app.setFont(self.btf._application_ui_font(self.btf.UI_FONT_SIZE))

        win = self.btf.MainWindow()
        win.show()
        _wait_ms(app, 400)
        win._act_show_legend.trigger()
        app.processEvents()
        self.assertFalse(win._show_legend)
        self.assertFalse(win._panel_tabs.isTabVisible(self.btf._PANEL_TAB_LEGEND))
        self.assertTrue(win._panel_tabs.isTabVisible(self.btf._PANEL_TAB_MARKS))
        win.close()


if __name__ == "__main__":
    unittest.main()
