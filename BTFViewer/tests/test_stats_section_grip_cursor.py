"""Stats table-height grip must not leave a stuck resize override cursor."""
from __future__ import annotations

import os
import sys
import unittest

BTF_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QCursor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from btf_viewer_pkg.stats import _StatsSectionGrip  # noqa: E402
from btf_viewer_pkg.view import _HoverCursor  # noqa: E402


def _clear_override_cursors() -> None:
    app = QApplication.instance()
    if app is None:
        return
    while app.overrideCursor() is not None:
        app.restoreOverrideCursor()


class StatsSectionGripCursorTest(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])
        cls._app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        # Earlier MainWindow load tests can leak WaitCursor into this module.
        _clear_override_cursors()
        _HoverCursor.hide()

    def tearDown(self) -> None:
        _HoverCursor.hide()
        _clear_override_cursors()

    def _make_grip(self) -> tuple[QWidget, _StatsSectionGrip]:
        host = QWidget()
        host.resize(240, 48)
        h = {"v": 120}

        def _h() -> int:
            return h["v"]

        grip = _StatsSectionGrip(True, _h, host)

        def _on_h(v: int) -> None:
            h["v"] = v

        grip.height_changed.connect(_on_h)
        grip.setGeometry(0, 20, 240, 8)
        host.show()
        self._app.processEvents()
        return host, grip

    def test_hover_uses_widget_cursor_not_app_override(self) -> None:
        host, grip = self._make_grip()
        self.addCleanup(host.close)
        QTest.mouseMove(grip, QPoint(40, 4))
        self._app.processEvents()
        self.assertIsNone(
            QApplication.overrideCursor(),
            "hover must not pin an application override cursor",
        )
        QTest.mouseMove(host, QPoint(40, 2))
        self._app.processEvents()
        self.assertIsNone(QApplication.overrideCursor())

    def test_drag_release_clears_override_even_off_grip(self) -> None:
        host, grip = self._make_grip()
        self.addCleanup(host.close)
        QTest.mousePress(
            grip, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(40, 4))
        self._app.processEvents()
        self.assertIsNotNone(QApplication.overrideCursor())
        QTest.mouseMove(host, QPoint(40, 40))
        QTest.mouseRelease(
            host, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(40, 40))
        self._app.processEvents()
        self.assertIsNone(
            QApplication.overrideCursor(),
            "release after drag must restore the normal cursor",
        )
        self.assertFalse(grip._dragging)

    def test_hide_restores_when_platform_remaps_sizever(self) -> None:
        """Cocoa often reports SizeVer as SplitV; hide must still pop the override."""
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.SplitVCursor))
        _HoverCursor._shape = Qt.CursorShape.SizeVerCursor
        _HoverCursor.hide(Qt.CursorShape.SizeVerCursor)
        self.assertIsNone(QApplication.overrideCursor())
        self.assertIsNone(_HoverCursor._shape)
