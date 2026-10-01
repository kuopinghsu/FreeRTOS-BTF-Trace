"""Expand report / Restore layout — Desktop lockstep with App.vue."""
from __future__ import annotations

import html
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
from PySide6.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402

from btf_viewer_pkg.config import _PANEL_TAB_AI, _PANEL_TAB_FIND, _PANEL_TAB_STATS  # noqa: E402
from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402
from btf_viewer_pkg.stats import _RcSettings  # noqa: E402
from btf_viewer_pkg.ui_theme import expanded_report_width  # noqa: E402

from tests import destroy_main_window  # noqa: E402


def _wait_ms(app: QApplication, ms: int) -> None:
    timer = QElapsedTimer()
    timer.start()
    while timer.elapsed() < ms:
        app.processEvents()


class ReportExpandTest(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])
        cls._app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="btf_report_expand_")
        self._orig_rc = _RcSettings.RC_PATH
        _RcSettings.RC_PATH = os.path.join(self._tmpdir, "btf_viewer.rc")
        with open(_RcSettings.RC_PATH, "w", encoding="utf-8") as fh:
            fh.write(
                "[view]\n"
                "show_stats=true\n"
                "show_legend=true\n"
                "show_marks=true\n"
                "show_find=true\n"
                "show_ai=true\n"
                "[window]\n"
                "dock_layout_version=12\n"
                "maximized=false\n"
                "width=1200\n"
                "height=800\n"
            )

    def tearDown(self) -> None:
        _RcSettings.RC_PATH = self._orig_rc

    def _make_win(self) -> MainWindow:
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win.resize(1200, 800)
        win.show()
        _wait_ms(self._app, 150)
        placeholder = QWidget()
        win._tab_widget.addTab(placeholder, "example.btf")
        win._central_stack.setCurrentIndex(1)
        self._app.processEvents()
        return win

    def test_expand_and_restore_preserves_width(self) -> None:
        win = self._make_win()
        btn = win._rp_expand_btn
        self.assertEqual(win._panel_tabs.currentIndex(), _PANEL_TAB_STATS)
        self.assertTrue(btn.isVisible())
        self.assertEqual(btn.text(), "Expand report")
        self.assertEqual(btn.accessibleName(), "Expand report")
        before = int(win._panel_dock.width())
        win._set_report_expanded(True)
        self._app.processEvents()
        self.assertTrue(win._report_expanded)
        self.assertEqual(btn.text(), "Restore layout")
        self.assertGreater(int(win._panel_dock.maximumWidth()), 520)
        self.assertGreaterEqual(
            getattr(win, "_panel_pre_expand_width", 0) or before,
            1,
        )
        win._set_report_expanded(False)
        self._app.processEvents()
        self.assertFalse(win._report_expanded)
        self.assertEqual(btn.text(), "Expand report")
        self.assertEqual(int(win._panel_dock.maximumWidth()), 520)

    def test_expand_button_survives_dock_width_relax(self) -> None:
        win = self._make_win()
        win._relax_right_dock_content_widths()
        self._app.processEvents()
        _wait_ms(self._app, 50)
        btn = win._rp_expand_btn
        self.assertGreaterEqual(btn.width(), btn.sizeHint().width() - 1)
        self.assertGreater(btn.width(), 40)

    def test_switching_to_find_restores_layout(self) -> None:
        win = self._make_win()
        win._set_report_expanded(True)
        self._app.processEvents()
        self.assertTrue(win._report_expanded)
        win._on_icon_rail_activated(_PANEL_TAB_FIND)
        self._app.processEvents()
        self.assertFalse(win._report_expanded)
        self.assertFalse(win._rp_expand_btn.isVisible())

    def test_ai_tab_keeps_expand_control(self) -> None:
        win = self._make_win()
        win._on_icon_rail_activated(_PANEL_TAB_AI)
        self._app.processEvents()
        self.assertTrue(win._rp_expand_btn.isVisible())
        self.assertEqual(win._rp_expand_btn.text(), "Expand report")

    def test_evidence_jump_reveals_timeline_and_offers_return(self) -> None:
        win = self._make_win()
        win._set_report_expanded(True)
        self._app.processEvents()
        win._record_evidence_jump({"time": 1000, "label": "x", "source": "stats"})
        self._app.processEvents()
        btn = win._rp_expand_btn
        self.assertFalse(win._report_expanded)
        self.assertEqual(btn.text(), "Back to report")
        self.assertEqual(btn.accessibleName(), "Back to report")
        btn.click()
        self._app.processEvents()
        self.assertTrue(win._report_expanded)
        self.assertEqual(btn.text(), "Restore layout")
        win._set_report_expanded(False)
        self.assertEqual(btn.text(), "Expand report")

    def test_evidence_jump_without_expansion_is_unchanged(self) -> None:
        win = self._make_win()
        win._record_evidence_jump({"time": 1000, "label": "x", "source": "stats"})
        self.assertEqual(win._rp_expand_btn.text(), "Expand report")

    def test_empty_session_restores_layout(self) -> None:
        win = self._make_win()
        win._set_report_expanded(True)
        self._app.processEvents()
        win._clear_panels_for_empty_session()
        self._app.processEvents()
        self.assertFalse(win._report_expanded)
        self.assertFalse(win._report_return_pending)
        self.assertEqual(int(win._panel_dock.maximumWidth()), 520)

    def test_narrow_window_keeps_timeline_and_report_usable(self) -> None:
        self.assertEqual(expanded_report_width(1000), 760)
        self.assertEqual(expanded_report_width(1600), 1312)
        self.assertEqual(expanded_report_width(400), 180)
        self.assertEqual(expanded_report_width(0), 180)
        self.assertEqual(expanded_report_width(618, current=450), 450)
        self.assertEqual(expanded_report_width(1600, current=450), 1312)
        for w in range(420, 3000, 37):
            got = expanded_report_width(w)
            self.assertGreaterEqual(w - got, 240, w)
            self.assertGreaterEqual(got, 180, w)

    def test_rails_expose_accessible_names_matching_web(self) -> None:
        win = self._make_win()
        app_vue = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        rail = win._icon_rail
        self.assertEqual(rail.accessibleName(), "Right panel navigation")
        self.assertIn('aria-label="Right panel navigation"', app_vue)
        for i in range(5):
            btn = rail.button(i)
            self.assertIsNotNone(btn)
            self.assertEqual(btn.accessibleName(), btn.toolTip())
            self.assertIn(f'aria-label="{btn.accessibleName()}"', app_vue)
            self.assertEqual(btn.iconSize().width(), 18)
        act = win._activity_rail
        for key in ("heatmap", "analysis", "notebook", "compare", "snapshot",
                    "help", "settings"):
            btn = act.button(key)
            self.assertIsNotNone(btn, key)
            self.assertTrue(btn.accessibleName())
            self.assertIn(f'aria-label="{html.escape(btn.accessibleName(), quote=False)}"',
                          app_vue)
            self.assertEqual(btn.iconSize().width(), 18)

    def test_controls_render_near_28px_with_focus_token(self) -> None:
        from PySide6.QtWidgets import QLineEdit, QPushButton
        from btf_viewer_pkg.ui_theme import ui_theme_tokens
        win = self._make_win()
        find = win._find_input
        self.assertIsInstance(find, QLineEdit)
        bar = find.parentWidget()
        self.assertEqual(bar.objectName(), "findbar")
        # Height follows the platform UI font (Linux CI fonts render ~3px
        # shorter than macOS), so allow a band around the 28px target.
        h = bar.sizeHint().height()
        self.assertTrue(24 <= h <= 36, h)
        probe = QPushButton("OK", win._welcome_open_btn.parentWidget())
        probe.ensurePolished()
        self.assertTrue(24 <= probe.sizeHint().height() <= 36, probe.sizeHint().height())
        qss = win.styleSheet() or self._app.styleSheet()
        focus = str(ui_theme_tokens(bool(win._is_dark))["focus"])
        self.assertIn(f"QLineEdit:focus", qss)
        self.assertIn(focus, qss)
        self.assertIn("border-radius:6px", qss)

    def test_theme_switch_refreshes_token_driven_chrome(self) -> None:
        from btf_viewer_pkg.ui_theme import ui_theme_tokens
        win = self._make_win()
        for is_dark in (False, True):
            win._apply_theme(is_dark)
            self._app.processEvents()
            qss = win.styleSheet() or self._app.styleSheet()
            ui = ui_theme_tokens(is_dark)
            for name in ("marks_empty_hint", "muted_mono", "stats_empty_hint",
                         "find_mode_help"):
                self.assertIn(f"QLabel#{name} {{ color:{ui['fg_dim']};", qss, name)
            self.assertIn(f"border:1px solid {ui['control_border']}", qss)
            self.assertIn(str(ui["focus"]), qss)

    def test_welcome_empty_state(self) -> None:
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win.show()
        _wait_ms(self._app, 80)
        self.assertEqual(win._central_stack.currentIndex(), 0)
        self.assertIsNotNone(win.findChild(QWidget, "welcome_page"))
        self.assertEqual(win._welcome_open_btn.text(), "Open…")
        self.assertEqual(win._welcome_demo_btn.text(), "Load bundled demo")
        msg = win.findChild(QLabel, "welcome_msg")
        self.assertIsNotNone(msg)
        self.assertIn("Open a BTF trace", msg.text())

    def test_marks_and_find_use_empty_catalog(self) -> None:
        win = self._make_win()
        self.assertIn("bookmarks or annotations", win._marks_empty_hint.text())
        find_text = win.findChild(QLabel, "find_empty_text")
        self.assertIsNotNone(find_text)
        self.assertIn("task name", find_text.text())


if __name__ == "__main__":
    unittest.main()
