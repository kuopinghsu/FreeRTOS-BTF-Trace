"""Focus Mode help + exit behaviour (BTFVIEWER_DESIGN_CONSISTENCY_TODO step 4).

- Desktop status text, tooltip, Help and key handling all agree: Shift+F toggles,
  Esc exits, F never toggles Focus Mode.
- Web mirrors: Shift+F toggles, Esc exits, the visible Exit control stays.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

MW_SRC = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text(encoding="utf-8")
APP_VUE = (BTF_ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")


class FocusModeSourceTests(unittest.TestCase):
    def test_desktop_status_message_names_shift_f_and_esc(self) -> None:
        self.assertIn("Focus Mode — Shift+F or Esc to exit", MW_SRC)
        self.assertNotIn("(F) to exit", MW_SRC)
        self.assertNotIn("Focus Mode (F)", MW_SRC)

    def test_desktop_focus_mode_bound_to_shift_f_not_f(self) -> None:
        block = MW_SRC[MW_SRC.index("_act_focus_mode = "):]
        block = block[: block.index("\n\n")]
        self.assertIn('QKeySequence("Shift+F")', block)
        self.assertNotIn('setShortcut(QKeySequence("F"))', block)

    def test_desktop_help_lists_focus_mode_keys(self) -> None:
        self.assertIn('("Shift+F",              "Toggle Focus Mode")', MW_SRC)
        self.assertRegex(MW_SRC, r'\("Esc",\s*"Exit Focus Mode[^"]*"\)')

    def test_desktop_esc_exit_handler_present_and_guarded(self) -> None:
        # The app-wide event filter drops Focus Mode on Esc, but only when no
        # demo / modal / popup owns the key and the user is not typing.
        idx = MW_SRC.index('and getattr(self, "_focus_mode", False)')
        window = MW_SRC[idx - 200: idx + 1000]
        self.assertIn("Key_Escape", window)
        self.assertIn("self._demo_runner is None", window)
        self.assertIn("activeModalWidget() is None", window)
        self.assertIn("_set_focus_mode(False)", window)

    def test_web_shift_f_toggles_focus_mode(self) -> None:
        m = re.search(r"case 'f':\n(.*?)\n      break", APP_VUE, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("e.shiftKey", body)
        self.assertIn("toggleFocusMode()", body)
        self.assertIn("onFit()", body)

    def test_web_esc_exits_focus_mode_after_demo_check(self) -> None:
        self.assertIn("if (focusMode.value && !demoRunning.value) {", APP_VUE)
        self.assertRegex(
            APP_VUE,
            r"focusMode\.value && !demoRunning\.value\) \{\s*\n\s*setFocusMode\(false\)",
        )

    def test_web_help_lists_focus_mode_keys(self) -> None:
        self.assertRegex(APP_VUE, r"Shift\+F\s*</div><div>Toggle Focus Mode</div>")
        self.assertRegex(APP_VUE, r">\s*Esc\s*</div><div>Exit Focus Mode</div>")

    def test_web_keeps_visible_exit_focus_control(self) -> None:
        self.assertIn('class="focus-exit"', APP_VUE)
        self.assertIn('@click="setFocusMode(false)"', APP_VUE)

    def test_generated_bundles_drop_the_stale_focus_hint(self) -> None:
        for name in ("btf_viewer.py", "btf_viewer.html"):
            path = BTF_ROOT / "builds" / name
            if not path.is_file():
                self.skipTest(f"{name} not built")
            text = path.read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn("Focus Mode (F) to exit", text, name)
            self.assertNotIn("(F) to exit", text, name)


class FocusModeEscBehaviourTest(unittest.TestCase):
    _app = None

    @classmethod
    def setUpClass(cls) -> None:
        from btf_viewer_pkg._bootstrap import install

        install()
        from PySide6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])
        cls._app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        from btf_viewer_pkg.stats import _RcSettings

        self._tmp = tempfile.mkdtemp(prefix="btf_focus_")
        self._orig_rc = _RcSettings.RC_PATH
        _RcSettings.RC_PATH = os.path.join(self._tmp, "btf_viewer.rc")
        with open(_RcSettings.RC_PATH, "w", encoding="utf-8") as fh:
            fh.write("[window]\ndock_layout_version=12\nwidth=1200\nheight=800\n")

    def tearDown(self) -> None:
        from btf_viewer_pkg.stats import _RcSettings

        _RcSettings.RC_PATH = self._orig_rc

    def test_escape_leaves_focus_mode(self) -> None:
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtWidgets import QApplication
        from btf_viewer_pkg.mainwindow import MainWindow
        from tests import destroy_main_window

        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win.resize(1200, 800)
        win.show()
        win.activateWindow()
        for _ in range(20):
            QApplication.processEvents()

        win._set_focus_mode(True, persist=False)
        self.assertTrue(win._focus_mode)

        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(win, ev)
        for _ in range(10):
            QApplication.processEvents()

        self.assertFalse(win._focus_mode)


if __name__ == "__main__":
    unittest.main()
