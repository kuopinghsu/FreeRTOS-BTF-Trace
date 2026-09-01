"""Desktop port of the web main-window shell redesign:

* left activity rail (investigation entry points)
* unified context strip (trace-quality / evidence / cursor-scope share one zone)
* collapse-to-rail for the right panel

Mirrors web/src/App.vue `.activity-rail`, `.context-strip`, and the
`rightPanelCollapsed` behaviour.
"""
from __future__ import annotations

import os
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

from PySide6.QtCore import QElapsedTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.config import _PANEL_TAB_FIND  # noqa: E402
from btf_viewer_pkg.mainwindow import _IconRail  # noqa: E402
from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402
from btf_viewer_pkg.stats import _LoadProgressDialog, _RcSettings  # noqa: E402

from tests import destroy_main_window  # noqa: E402


def _wait_ms(app: QApplication, ms: int) -> None:
    timer = QElapsedTimer()
    timer.start()
    while timer.elapsed() < ms:
        app.processEvents()


class ShellRedesignTest(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])
        cls._app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="btf_shell_")
        self._orig_rc = _RcSettings.RC_PATH
        _RcSettings.RC_PATH = os.path.join(self._tmpdir, "btf_viewer.rc")
        with open(_RcSettings.RC_PATH, "w", encoding="utf-8") as fh:
            fh.write(
                "[view]\nshow_stats=true\nshow_legend=true\nshow_marks=true\n"
                "show_find=true\nshow_ai=true\n"
                "[window]\ndock_layout_version=12\nmaximized=false\n"
                "width=1280\nheight=800\n"
            )

    def tearDown(self) -> None:
        _RcSettings.RC_PATH = self._orig_rc

    def _make_win(self) -> MainWindow:
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win.resize(1280, 800)
        win.show()
        _wait_ms(self._app, 200)
        return win

    # ---- Left activity rail -------------------------------------------------

    def test_activity_rail_entry_points_dispatch(self) -> None:
        win = self._make_win()
        rail = win._activity_rail
        self.assertEqual(rail.width(), rail.RAIL_W)
        self.assertEqual(
            sorted(rail._buttons),
            ["analysis", "compare", "heatmap", "help", "settings", "snapshot"],
        )

        calls: list[str] = []
        for name, key in (
            ("_open_migration_heatmap", "heatmap"),
            ("_open_analysis_findings", "analysis"),
            ("_open_trace_compare", "compare"),
            ("_on_save_image", "snapshot"),
            ("_on_keyboard_shortcuts", "help"),
            ("_open_settings", "settings"),
        ):
            setattr(win, name, (lambda k=key: calls.append(k)))
        for key in ("heatmap", "analysis", "compare", "snapshot", "help", "settings"):
            win._on_activity_rail_activated(key)
        self.assertEqual(
            calls,
            ["heatmap", "analysis", "compare", "snapshot", "help", "settings"])

    def test_activity_rail_visibility_tracks_trace(self) -> None:
        win = self._make_win()
        rail = win._activity_rail
        # No trace loaded → trace-scoped entries hidden, Settings always shown.
        win._sync_activity_rail()
        self.assertFalse(rail._buttons["analysis"].isVisibleTo(rail))
        self.assertFalse(rail._buttons["snapshot"].isVisibleTo(rail))
        self.assertTrue(rail._buttons["settings"].isVisibleTo(rail))

    # ---- Unified context strip -------------------------------------------

    def test_context_strip_wraps_the_three_bars(self) -> None:
        win = self._make_win()
        strip = win._context_strip
        for bar in (win._trace_quality_banner, win._trace_quality_details,
                    win._evidence_inspector_bar, win._cursor_scope_banner):
            self.assertIs(bar.parent(), strip)
        # Nothing to show yet → the whole strip is hidden.
        win._sync_context_strip_visibility()
        self.assertFalse(strip.isVisibleTo(win))
        # One bar visible → the strip shows.
        win._cursor_scope_banner.setVisible(True)
        win._sync_context_strip_visibility()
        self.assertTrue(strip.isVisibleTo(win))

    # ---- Collapse-to-rail ------------------------------------------------

    def test_collapse_to_rail_and_reopen(self) -> None:
        win = self._make_win()
        self.assertFalse(win._panel_collapsed)
        open_w = win._panel_dock.width()
        self.assertGreater(open_w, _IconRail.RAIL_W + 8)

        win._toggle_panel_collapsed()
        _wait_ms(self._app, 100)
        self.assertTrue(win._panel_collapsed)
        self.assertFalse(win._rp_content.isVisibleTo(win))
        self.assertTrue(win._icon_rail.isVisibleTo(win))
        self.assertLessEqual(win._panel_dock.maximumWidth(), _IconRail.RAIL_W)
        self.assertTrue(win._settings.get_bool("panel", "collapsed", False))

        # Clicking any rail panel icon re-opens the panel (web selectRightPanelTab).
        win._on_icon_rail_activated(_PANEL_TAB_FIND)
        _wait_ms(self._app, 100)
        self.assertFalse(win._panel_collapsed)
        self.assertTrue(win._rp_content.isVisibleTo(win))
        self.assertEqual(win._panel_tabs.currentIndex(), _PANEL_TAB_FIND)
        self.assertFalse(win._settings.get_bool("panel", "collapsed", False))

    # ---- Status-bar Find position pill ---------------------------------

    def test_status_find_pill_tracks_counter(self) -> None:
        win = self._make_win()
        pill = win._status_find_btn
        self.assertFalse(pill.isVisibleTo(win))
        win._set_find_counter("3 / 17")
        self.assertTrue(pill.isVisibleTo(win))
        self.assertIn("3 / 17", pill.text())
        self.assertIn("Find", pill.text())
        win._set_find_counter("")
        self.assertFalse(pill.isVisibleTo(win))

    def test_collapsed_state_restores_from_rc(self) -> None:
        with open(_RcSettings.RC_PATH, "a", encoding="utf-8") as fh:
            fh.write("[panel]\ncollapsed=true\n")
        win = self._make_win()
        _wait_ms(self._app, 200)
        self.assertTrue(win._panel_collapsed)
        self.assertFalse(win._rp_content.isVisibleTo(win))

    # ---- Focus mode ---------------------------------------------------------

    def test_focus_mode_hides_chrome_and_persists(self) -> None:
        win = self._make_win()
        self.assertFalse(win._focus_mode)

        win._toggle_focus_mode()
        _wait_ms(self._app, 80)
        self.assertTrue(win._focus_mode)
        self.assertTrue(win._act_focus_mode.isChecked())
        self.assertFalse(win._activity_rail.isVisibleTo(win))
        self.assertFalse(win._panel_dock.isVisible())
        self.assertFalse(win._tab_widget.tabBar().isVisibleTo(win))
        self.assertTrue(win._settings.get_bool("view", "focus_mode", False))

        win._toggle_focus_mode()
        _wait_ms(self._app, 80)
        self.assertFalse(win._focus_mode)
        self.assertTrue(win._activity_rail.isVisibleTo(win))
        self.assertFalse(win._settings.get_bool("view", "focus_mode", False))

    # ---- Inline loading (no modal card) ---------------------------------

    def test_load_progress_dialog_never_shows(self) -> None:
        win = self._make_win()
        dlg = _LoadProgressDialog("Loading x…", win)
        self.addCleanup(dlg.deleteLater)
        dlg.show_centered(win.geometry())          # now a no-op
        self.assertFalse(dlg.isVisible())
        seen: list = []
        dlg.progressed.connect(lambda p, m: seen.append((p, m)))
        dlg.update_progress(42, "parsing")
        self.assertEqual(seen[-1][0], 42)

    def test_inline_load_uses_statusbar_and_skeleton(self) -> None:
        win = self._make_win()
        skel = win._load_skeleton
        self.assertIs(win._central_stack.widget(2), skel)
        self.assertFalse(win._status_load_lbl.isVisibleTo(win))

        win._begin_inline_load("demo_8cores.btf.gz")
        self.assertTrue(win._status_load_lbl.isVisibleTo(win))
        self.assertTrue(win._status_load_cancel.isVisibleTo(win))
        self.assertIs(win._central_stack.currentWidget(), skel)  # no trace yet

        win._on_load_progress(60, "Building timeline")
        self.assertIn("60%", win._status_load_lbl.text())
        self.assertIn("Building timeline", win._status_load_lbl.text())

        win._end_inline_load()
        self.assertFalse(win._status_load_lbl.isVisibleTo(win))
        self.assertIsNot(win._central_stack.currentWidget(), skel)

    def test_focus_mode_restores_from_rc(self) -> None:
        with open(_RcSettings.RC_PATH, "w", encoding="utf-8") as fh:
            fh.write(
                "[view]\nshow_stats=true\nshow_legend=true\nshow_marks=true\n"
                "show_find=true\nshow_ai=true\nfocus_mode=true\n"
                "[window]\ndock_layout_version=12\nmaximized=false\n"
                "width=1280\nheight=800\n"
            )
        win = self._make_win()
        _wait_ms(self._app, 200)
        self.assertTrue(win._focus_mode)
        self.assertFalse(win._activity_rail.isVisibleTo(win))


if __name__ == "__main__":
    unittest.main()
