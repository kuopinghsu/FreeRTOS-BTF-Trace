"""Regression: Vertical Task View must render with STI hidden.

_build_vertical() (btf_viewer_pkg/scene.py) referenced a stray ``expandable``
local at the task-column label sizing line -- that name is only ever bound
inside the later STI-channel loop, which is skipped whenever ``show_sti`` is
False (or the trace has no STI channels). The task-column loop ran first and
unconditionally read it, so switching to Vertical + Task View with STI
hidden raised ``UnboundLocalError`` on every repaint. Never caught before
because no existing test exercised vertical orientation with STI off
together; found while adding workspace/session round-trip tests that toggle
both (see test_workspace_portable_view_state.py).
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

from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402
from btf_viewer_pkg.parser import _parse_btf  # noqa: E402
from btf_viewer_pkg.stats import _RcSettings  # noqa: E402

EXAMPLE_2CORE = BTF_ROOT.parent / "tracedata" / "example-2cores.btf.gz"


def _destroy(win) -> None:
    try:
        win.close()
        win.deleteLater()
    except Exception:
        pass


class VerticalTaskViewStiOffTests(unittest.TestCase):
    _app = None
    _rc_path = None
    _rc_backup = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])
        cls._rc_path = Path(_RcSettings.RC_PATH)
        cls._rc_backup = cls._rc_path.read_bytes() if cls._rc_path.is_file() else None

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._rc_backup is not None:
            cls._rc_path.write_bytes(cls._rc_backup)
        elif cls._rc_path.is_file():
            cls._rc_path.unlink()

    def setUp(self) -> None:
        if not EXAMPLE_2CORE.is_file():
            self.skipTest(f"missing {EXAMPLE_2CORE}")
        self.trace = _parse_btf(str(EXAMPLE_2CORE))
        self.win = MainWindow()
        self.addCleanup(_destroy, self.win)
        self.tab = self.win._add_trace_tab(str(EXAMPLE_2CORE), self.trace)
        self.tab.view.load_trace(self.trace)
        self.win._tab_widget.setCurrentIndex(0)
        for _ in range(3):
            self._app.processEvents()

    def test_vertical_task_view_with_sti_hidden_does_not_raise(self) -> None:
        win, sc = self.win, self.tab.view._scene
        win._set_view_mode("task")
        win._set_orientation(False)          # vertical
        try:
            win._set_show_sti(False, persist=False)
        except Exception as exc:  # pragma: no cover - assertion message only
            self.fail(f"vertical Task View + STI off raised: {exc!r}")
        self.assertFalse(sc._horizontal)
        self.assertFalse(sc._show_sti)
        self.assertEqual(sc._view_mode, "task")

    def test_toggling_sti_back_on_still_renders(self) -> None:
        win, sc = self.win, self.tab.view._scene
        win._set_orientation(False)
        win._set_show_sti(False, persist=False)
        try:
            win._set_show_sti(True, persist=False)
        except Exception as exc:  # pragma: no cover - assertion message only
            self.fail(f"re-enabling STI after the off-state raised: {exc!r}")
        self.assertTrue(sc._show_sti)


if __name__ == "__main__":
    unittest.main()
