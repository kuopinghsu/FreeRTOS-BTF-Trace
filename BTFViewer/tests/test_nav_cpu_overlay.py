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

    def test_orth_scroll_grows_and_shrinks_with_cpu_overlay(self) -> None:
        """Vertical scroll range must clear the CPU overlay; hide restores it."""
        if not EXAMPLE_BTF.is_file():
            self.skipTest(f"missing trace fixture: {EXAMPLE_BTF}")

        host = QWidget()
        view = TimelineView()
        pane = _TimelinePane(view)
        cpu = QLabel("cpu")
        cpu.setMinimumHeight(CPU_LOAD_ROW_H)
        stack = _CpuLoadStack(pane, cpu, host)
        stack.set_cpu_visible(False)
        stack.setSizes([600, 180])
        host.resize(1200, 700)
        stack.setGeometry(0, 0, 1200, 700)
        host.show()
        stack.show()
        self._app.processEvents()

        trace = _parse_btf(str(EXAMPLE_BTF))
        view.load_trace(trace)
        self._app.processEvents()
        stack._reposition()
        self._app.processEvents()

        self.assertEqual(view._nav_bottom_inset, 0)
        h_hidden = view._scene.sceneRect().height()
        content = view._scene._orth_content_px
        self.assertIsNotNone(content)

        stack.set_cpu_visible(True)
        stack._reposition()
        self._app.processEvents()

        inset = view._nav_bottom_inset
        self.assertGreater(inset, 0)
        self.assertGreaterEqual(view.orth_scroll_gutter_px(), inset)
        h_shown = view._scene.sceneRect().height()
        # Scene must grow so the last task row can scroll above the overlay.
        self.assertGreaterEqual(h_shown, content + inset - 1.0)
        self.assertGreater(h_shown, h_hidden)

        stack.set_cpu_visible(False)
        stack._reposition()
        self._app.processEvents()

        self.assertEqual(view._nav_bottom_inset, 0)
        h_again = view._scene.sceneRect().height()
        self.assertLess(h_again, h_shown)
        self.assertAlmostEqual(h_again, h_hidden, delta=2.0)

        host.close()
        self._app.processEvents()

    def test_cpu_overlay_clears_vertical_scrollbar(self) -> None:
        """CPU overlay must not cover the task-axis vertical scrollbar track."""
        if not EXAMPLE_BTF.is_file():
            self.skipTest(f"missing trace fixture: {EXAMPLE_BTF}")

        host = QWidget()
        view = TimelineView()
        pane = _TimelinePane(view)
        cpu = QLabel("cpu")
        cpu.setMinimumHeight(CPU_LOAD_ROW_H)
        stack = _CpuLoadStack(pane, cpu, host)
        stack.set_cpu_visible(True)
        stack.setSizes([600, 180])
        host.resize(1200, 700)
        stack.setGeometry(0, 0, 1200, 700)
        host.show()
        stack.show()
        self._app.processEvents()

        trace = _parse_btf(str(EXAMPLE_BTF))
        view.load_trace(trace)
        self._app.processEvents()
        stack._reposition()
        self._app.processEvents()

        vbar = view.verticalScrollBar()
        self.assertIsNotNone(vbar)
        self.assertTrue(vbar.isVisible())
        self.assertGreater(vbar.width(), 0)

        vbar_rect = QRect(
            vbar.mapTo(stack, QPoint(0, 0)),
            vbar.mapTo(stack, QPoint(vbar.width(), vbar.height())),
        )
        self.assertFalse(
            stack._cpu.geometry().intersects(vbar_rect),
            f"cpu {stack._cpu.geometry()} overlaps vbar {vbar_rect}",
        )
        self.assertFalse(
            stack._handle.geometry().intersects(vbar_rect),
            f"handle {stack._handle.geometry()} overlaps vbar {vbar_rect}",
        )
        self.assertLess(stack._cpu.width(), stack.width())
        self.assertEqual(stack._cpu.width() + stack._orth_vbar_gutter_px(), stack.width())

        host.close()
        self._app.processEvents()


if __name__ == "__main__":
    unittest.main()
