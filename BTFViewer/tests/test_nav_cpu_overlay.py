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
from PySide6.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402

from btf_viewer_pkg.config import CPU_LOAD_ROW_H  # noqa: E402
from btf_viewer_pkg.mainwindow import _CpuLoadStack, _TimelinePane  # noqa: E402
from btf_viewer_pkg.parser import _parse_btf  # noqa: E402
from btf_viewer_pkg.view import TimelineView  # noqa: E402

EXAMPLE_BTF = Path(__file__).resolve().parents[2] / "tracedata" / "example-2cores.btf.gz"


class TestNavCpuOverlay(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_navigator_clears_cpu_overlay_after_zoom(self) -> None:
        """CPU-load overlay must not cover the navigator minimap after zoom."""
        if not EXAMPLE_BTF.is_file():
            self.skipTest(f"missing trace fixture: {EXAMPLE_BTF}")

        # Build the same stack hierarchy as a tab, without MainWindow (avoids
        # session-restore races that leave _active_tab unset in CI/discover).
        host = QWidget()
        view = TimelineView()
        pane = _TimelinePane(view)
        cpu = QLabel("cpu")
        cpu.setMinimumHeight(CPU_LOAD_ROW_H)
        stack = _CpuLoadStack(pane, cpu, host)
        stack.set_cpu_visible(True)
        stack.setSizes([600, CPU_LOAD_ROW_H])
        host.resize(1400, 900)
        stack.setGeometry(0, 0, 1400, 900)
        host.show()
        stack.show()
        self._app.processEvents()
        stack._reposition()

        trace = _parse_btf(str(EXAMPLE_BTF))
        view.load_trace(trace)
        self._app.processEvents()
        stack._reposition()

        self.assertTrue(stack.cpu_visible())
        self.assertGreater(view._nav_bottom_inset, 0)

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

        host.close()
        self._app.processEvents()


if __name__ == "__main__":
    unittest.main()
