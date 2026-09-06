"""QToolTip keeps its rounded QSS corners without a stray square frame.

Regression test: QToolTip is a native window that stays a plain rectangle
regardless of QSS — `border-radius` only rounds the *painted content*, so
without WA_TranslucentBackground the corners it cuts away show the native
window's real (opaque, square) shape through underneath: a visible dark
line in light theme, blending into the dark fill (so not gone, just harder
to see) in dark theme. MainWindow.eventFilter() sets that attribute the
moment Qt's internal tooltip widget is first shown — see mainwindow.py's
QToolTip QSS rule for the other half of this fix.
"""
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

from PySide6.QtCore import QElapsedTimer, QPoint, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QToolTip  # noqa: E402

from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402

from tests import destroy_main_window  # noqa: E402


def _wait_ms(app: QApplication, ms: int) -> None:
    timer = QElapsedTimer()
    timer.start()
    while timer.elapsed() < ms:
        app.processEvents()


class TooltipTranslucentTests(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])
        cls._app.setQuitOnLastWindowClosed(False)

    def test_tooltip_window_gets_translucent_background(self) -> None:
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win.show()
        _wait_ms(self._app, 200)  # let startup settle (_restoring_settings -> False)

        QToolTip.showText(win.mapToGlobal(QPoint(50, 50)), "Test tooltip", win)
        self._app.processEvents()

        # Window *type* lives in the low byte of windowFlags() (masked),
        # not as an independent bit — `flags & Qt.WindowType.ToolTip`
        # false-positives on other types with an overlapping bit (e.g.
        # Popup = 9 = 0b1001 also matches ToolTip = 13 = 0b1101).
        tip = next(
            (w for w in self._app.topLevelWidgets()
             if (w.windowFlags() & Qt.WindowType.WindowType_Mask) == Qt.WindowType.ToolTip),
            None,
        )
        self.assertIsNotNone(tip, "QToolTip's internal widget was not found")
        self.assertTrue(
            tip.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground),
            "QToolTip window is not translucent — its native square frame "
            "will show through the QSS border-radius corners",
        )


if __name__ == "__main__":
    unittest.main()
