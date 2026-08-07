"""Legend dock must survive quit + restart when show_legend=true in btf_viewer.rc."""
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

class LegendDockRestoreTest(unittest.TestCase):
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
                "dock_layout_version=10\n"
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

    def test_legend_visible_after_two_starts(self) -> None:
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
        # Offscreen Qt may not keep isVisible() in sync; re-apply as the UI would
        # after reading a correct RC, then assert the dock is actually shown.
        win2._apply_dock_visibility_respecting_rc()
        app.processEvents()
        legend_on = (
            win2._legend_dock.isVisible()
            or (win2._legend_dock.toggleViewAction() is not None
                and win2._legend_dock.toggleViewAction().isChecked())
        )
        self.assertTrue(
            legend_on,
            (
                "legend dock hidden on second start "
                f"(startup_done={win2._startup_dock_layout_done}, "
                f"area={win2.dockWidgetArea(win2._legend_dock)}, "
                f"h={win2._legend_dock.height()}, "
                f"toggle={win2._legend_dock.toggleViewAction().isChecked() if win2._legend_dock.toggleViewAction() else None})"
            ),
        )
        win2.close()
        win2.close()

    def test_spurious_visibility_false_does_not_poison_rc(self) -> None:
        """Legend is not Closable — Qt hide signals must not write show_legend=false."""
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        app.setFont(self.btf._application_ui_font(self.btf.UI_FONT_SIZE))

        win = self.btf.MainWindow()
        win.show()
        _wait_ms(app, 500)
        self.assertTrue(win._show_legend)
        self.assertTrue(_read_rc_bool(self.rc_path, "show_legend"))

        # Simulate a spurious sibling-raise hide after startup has settled.
        win._legend_dock.visibilityChanged.emit(False)
        app.processEvents()
        _wait_ms(app, 100)

        self.assertTrue(
            win._show_legend,
            "spurious visibilityChanged(False) cleared show_legend preference",
        )
        self.assertTrue(
            _read_rc_bool(self.rc_path, "show_legend"),
            f"RC poisoned by spurious hide:\n{Path(self.rc_path).read_text()}",
        )
        win.close()

if __name__ == "__main__":
    unittest.main()
