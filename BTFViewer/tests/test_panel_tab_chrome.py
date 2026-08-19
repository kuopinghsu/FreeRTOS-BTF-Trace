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

    def test_dock_title_hidden_and_tab_bars_align(self) -> None:
        win = self._make_win()
        title = win._panel_dock.titleBarWidget()
        self.assertIsNotNone(title)
        self.assertEqual(title.height(), 0)

        trace_tb = win._tab_widget.tabBar()
        panel_tb = win._panel_tabs.tabBar()
        self.assertFalse(trace_tb.expanding())
        self.assertTrue(panel_tb.expanding())
        self.assertLessEqual(
            abs(trace_tb.height() - panel_tb.height()), 2,
            "file tabs and panel tabs should share one strip height",
        )
        ty = trace_tb.mapTo(win, QPoint(0, 0)).y()
        py = panel_tb.mapTo(win, QPoint(0, 0)).y()
        self.assertLessEqual(
            abs(ty - py), 3,
            "panel tabs must sit on the same row as the task-window tabs",
        )

    def test_panel_tabs_fill_width_when_some_are_hidden(self) -> None:
        win = self._make_win()
        tb = win._panel_tabs.tabBar()
        self.assertGreaterEqual(tb.width(), win._panel_tabs.width() - 6)

        win._panel_tabs.setTabVisible(_PANEL_TAB_MARKS, False)
        win._panel_tabs.setTabVisible(_PANEL_TAB_FIND, False)
        win._panel_tabs.setTabVisible(_PANEL_TAB_LEGEND, False)
        win._panel_tabs._sync_tab_bar_width()
        self._app.processEvents()
        self.assertFalse(win._panel_tabs.isTabVisible(_PANEL_TAB_FIND))
        self.assertFalse(win._panel_tabs.isTabVisible(_PANEL_TAB_LEGEND))
        self.assertTrue(tb.expanding())
        self.assertGreaterEqual(tb.width(), win._panel_tabs.width() - 6)
        # Remaining tabs still share the strip — no leftover hole after the last tab.
        last = tb.tabAt(QPoint(tb.width() - 4, tb.height() // 2))
        self.assertNotEqual(last, -1)


if __name__ == "__main__":
    unittest.main()
