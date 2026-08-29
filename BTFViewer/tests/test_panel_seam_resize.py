"""Right-panel / timeline divider must be draggable on the desktop app."""
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

from PySide6.QtCore import QElapsedTimer, QEvent, QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402
from btf_viewer_pkg.stats import _RcSettings  # noqa: E402
from btf_viewer_pkg.view import (  # noqa: E402
    _PanelSeamResizer,
    _RIGHT_DOCK_MAX_W,
    _RIGHT_DOCK_MIN_W,
)

from tests import destroy_main_window, reap_qt_widgets  # noqa: E402


def _wait_ms(app: QApplication, ms: int) -> None:
    timer = QElapsedTimer()
    timer.start()
    while timer.elapsed() < ms:
        app.processEvents()


class PanelSeamResizeTest(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])
        cls._app.setQuitOnLastWindowClosed(False)
        reap_qt_widgets()

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="btf_seam_")
        self._orig_rc = _RcSettings.RC_PATH
        _RcSettings.RC_PATH = os.path.join(self._tmpdir, "btf_viewer.rc")
        with open(_RcSettings.RC_PATH, "w", encoding="utf-8") as fh:
            fh.write(
                "[view]\n"
                "show_stats=true\n"
                "show_legend=true\n"
                "show_marks=true\n"
                "show_find=true\n"
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
        win._sync_panel_seam_resizers()
        self._app.processEvents()
        return win

    def test_seam_resizers_exist_and_sit_on_top(self) -> None:
        win = self._make_win()
        central = win._central_seam_resizer
        dock = win._dock_seam_resizer
        self.assertIsInstance(central, _PanelSeamResizer)
        self.assertIsInstance(dock, _PanelSeamResizer)
        self.assertTrue(central.isVisible())
        self.assertTrue(dock.isVisible())
        self.assertEqual(central.width(), _PanelSeamResizer.WIDTH)
        self.assertEqual(dock.width(), _PanelSeamResizer.WIDTH)

        host = win._central_host
        pt = central.mapTo(host, QPoint(4, max(1, central.height() // 2)))
        hit = host.childAt(pt)
        self.assertIs(
            hit, central,
            "timeline content must not cover the right-panel resize grip",
        )

        tabs = win._panel_tabs
        pt = dock.mapTo(tabs, QPoint(4, max(1, dock.height() // 2)))
        hit = tabs.childAt(pt)
        self.assertIs(
            hit, dock,
            "statistics content must not cover the right-panel resize grip",
        )

    def test_drag_left_widens_statistics_panel(self) -> None:
        win = self._make_win()
        start = win._current_right_dock_width()
        self.assertGreaterEqual(start, _RIGHT_DOCK_MIN_W)
        grip = win._central_seam_resizer
        grip._begin_drag(400.0)
        grip._apply_drag(340.0)  # dx = -60 → wider panel
        self._app.processEvents()
        wider = win._current_right_dock_width()
        self.assertGreater(wider, start)
        self.assertLessEqual(wider, _RIGHT_DOCK_MAX_W)
        grip._end_drag()

    def test_stylechange_eventfilter_does_not_recurse(self) -> None:
        """App-wide filter must not re-enter during stylesheet polish."""
        win = self._make_win()
        old = sys.getrecursionlimit()
        sys.setrecursionlimit(80)
        try:
            ev = QEvent(QEvent.Type.StyleChange)
            self.assertFalse(win.eventFilter(win, ev))
            self._app.setProperty("btf_applying_theme", True)
            try:
                self.assertFalse(win.eventFilter(win, ev))
            finally:
                self._app.setProperty("btf_applying_theme", False)
        finally:
            sys.setrecursionlimit(old)

    def test_mainwindow_survives_orphaned_ai_panels(self) -> None:
        """Leaked AI panels must not hang the next MainWindow theme apply."""
        from btf_viewer_pkg.ai_assistant import create_ai_assistant_panel

        panels = [
            create_ai_assistant_panel(
                None,
                get_context=lambda: {"findings_text": "findings"},
                get_settings=lambda: {"enabled": "true"},
            )
            for _ in range(6)
        ]
        try:
            win = self._make_win()
            start = win._current_right_dock_width()
            self.assertGreaterEqual(start, _RIGHT_DOCK_MIN_W)
        finally:
            for panel in panels:
                try:
                    panel.close()
                    panel.deleteLater()
                except RuntimeError:
                    pass
            self._app.processEvents()

    def test_drag_clamps_to_min_and_max(self) -> None:
        win = self._make_win()
        grip = win._dock_seam_resizer
        grip._begin_drag(500.0)
        grip._apply_drag(500.0 + 2000.0)  # drag right → narrower
        self._app.processEvents()
        self.assertEqual(win._current_right_dock_width(), _RIGHT_DOCK_MIN_W)
        grip._apply_drag(500.0 - 2000.0)  # drag left → wider
        self._app.processEvents()
        self.assertEqual(win._current_right_dock_width(), _RIGHT_DOCK_MAX_W)
        grip._end_drag()


if __name__ == "__main__":
    unittest.main()
