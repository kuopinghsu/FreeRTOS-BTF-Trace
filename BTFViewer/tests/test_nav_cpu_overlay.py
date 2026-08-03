"""Navigator pan-window must clear the CPU-load overlay."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from PySide6.QtCore import QEventLoop, QPoint, QRect, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402

EXAMPLE_BTF = Path(__file__).resolve().parents[2] / "tracedata" / "example.btf.gz"


class TestNavCpuOverlay(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_navigator_clears_cpu_overlay_after_zoom(self) -> None:
        if not EXAMPLE_BTF.is_file():
            self.skipTest(f"missing trace fixture: {EXAMPLE_BTF}")

        win = MainWindow()
        win.resize(1400, 900)
        win.show()
        self._app.processEvents()
        win._open_file(str(EXAMPLE_BTF.resolve()))

        loop = QEventLoop()

        def _poll() -> None:
            tab = win._active_tab
            if tab is not None and tab.view._scene._trace is not None:
                loop.quit()
            else:
                QTimer.singleShot(100, _poll)

        QTimer.singleShot(100, _poll)
        QTimer.singleShot(15_000, loop.quit)
        loop.exec()

        tab = win._active_tab
        self.assertIsNotNone(tab)
        assert tab is not None
        view = tab.view
        stack = tab.cpu_splitter
        self.assertTrue(stack.cpu_visible())

        view._do_zoom(4.0, QPoint(500, 350))
        self._app.processEvents()
        view._show_nav()
        settle = QEventLoop()
        QTimer.singleShot(150, settle.quit)
        settle.exec()

        nav = view._nav_popup
        self.assertTrue(nav.isVisible())
        self.assertGreater(view._nav_bottom_inset, 0)

        nav_rect = QRect(
            nav.mapTo(stack, QPoint(0, 0)),
            nav.mapTo(stack, QPoint(nav.width(), nav.height())),
        )
        self.assertFalse(
            stack._cpu.geometry().intersects(nav_rect),
            f"nav {nav_rect} overlaps cpu {stack._cpu.geometry()}",
        )
        self.assertFalse(
            stack._handle.geometry().intersects(nav_rect),
            f"nav {nav_rect} overlaps handle {stack._handle.geometry()}",
        )

        win.close()
        self._app.processEvents()


if __name__ == "__main__":
    unittest.main()
