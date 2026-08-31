"""Trace-file and Statistics tab strips share one chrome row on desktop."""
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

from PySide6.QtCore import QElapsedTimer, QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from btf_viewer_pkg.config import (  # noqa: E402
    _PANEL_TAB_FIND,
    _PANEL_TAB_LEGEND,
    _PANEL_TAB_MARKS,
)
from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402
from btf_viewer_pkg.stats import _RcSettings  # noqa: E402

from tests import destroy_main_window  # noqa: E402


def _wait_ms(app: QApplication, ms: int) -> None:
    timer = QElapsedTimer()
    timer.start()
    while timer.elapsed() < ms:
        app.processEvents()


class PanelTabChromeTest(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])
        cls._app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="btf_tab_chrome_")
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
        win.show()
        _wait_ms(self._app, 150)
        placeholder = QWidget()
        win._tab_widget.addTab(placeholder, "example.btf")
        win._central_stack.setCurrentIndex(1)
        self._app.processEvents()
        return win

    def test_dock_title_hidden_and_icon_rail_replaces_tab_strip(self) -> None:
        """Web redesign: the text tab strip is gone — a vertical icon rail plus
        a per-panel header row drive the right panel (App.vue .icon-rail /
        .rp-page-header). The QTabWidget stays as the hidden content stack."""
        win = self._make_win()
        title = win._panel_dock.titleBarWidget()
        self.assertIsNotNone(title)
        self.assertEqual(title.height(), 0)

        # The panel QTabWidget's own tab bar is hidden.
        self.assertTrue(win._panel_tabs.tabBar().isHidden())

        rail = win._icon_rail
        self.assertEqual(
            [b.text() for b in rail._buttons],
            ["Statistics", "Marks", "Find", "Legend", "AI"],
        )
        self.assertEqual(rail.width(), rail.RAIL_W)
        # Header title tracks the current panel.
        self.assertEqual(
            win._rp_page_header.text(),
            win._panel_tabs.tabText(win._panel_tabs.currentIndex()),
        )
        # The active rail button matches the active panel.
        checked = [i for i, b in enumerate(rail._buttons) if b.isChecked()]
        self.assertEqual(checked, [win._panel_tabs.currentIndex()])

    def test_icon_rail_switches_panels_and_follows_visibility(self) -> None:
        win = self._make_win()
        rail = win._icon_rail

        win._on_icon_rail_activated(_PANEL_TAB_FIND)
        self._app.processEvents()
        self.assertEqual(win._panel_tabs.currentIndex(), _PANEL_TAB_FIND)
        self.assertEqual(win._rp_page_header.text(), "Find")
        self.assertTrue(rail._buttons[_PANEL_TAB_FIND].isChecked())

        # Hidden panels hide their rail button; current panel falls back to a
        # still-visible one. Toggle through the real View-menu handlers (they
        # call _sync_panel_tab_visibility synchronously); assert immediately —
        # a deferred settings-restore in the test env re-reads show_* from rc.
        _wait_ms(self._app, 50)
        win._toggle_show_find_panel()
        win._toggle_show_legend_panel()
        self.assertFalse(win._show_find)
        self.assertTrue(rail._buttons[_PANEL_TAB_FIND].isHidden())
        self.assertTrue(rail._buttons[_PANEL_TAB_LEGEND].isHidden())
        self.assertFalse(rail._buttons[_PANEL_TAB_MARKS].isHidden())
        self.assertTrue(win._panel_tabs.isTabVisible(win._panel_tabs.currentIndex()))
        self.assertEqual(
            win._rp_page_header.text(),
            win._panel_tabs.tabText(win._panel_tabs.currentIndex()),
        )


if __name__ == "__main__":
    unittest.main()
