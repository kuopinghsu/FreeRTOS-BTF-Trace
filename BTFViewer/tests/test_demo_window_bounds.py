"""Window-box selection for demo_runner fractional coordinates."""
from __future__ import annotations

import importlib.util
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

BTF_ROOT = Path(__file__).resolve().parents[1]
_RUNNER = BTF_ROOT / "scripts" / "demo_runner.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("demo_runner", _RUNNER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class DemoWindowBoundsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dr = _load_runner()

    def test_choose_largest_window(self) -> None:
        main = (100, 50, 1200, 800)
        dlg = (400, 200, 640, 611)
        self.assertEqual(
            self.dr.choose_window_bounds([dlg, main]),
            main,
        )

    def test_keep_prev_when_dialog_steals(self) -> None:
        main = (254, 47, 1200, 832)
        dlg = (534, 237, 640, 611)
        self.assertEqual(
            self.dr.choose_window_bounds([dlg], prev=main, screen=(1728, 1117)),
            main,
        )

    def test_keep_prev_over_fullscreen_guess(self) -> None:
        main = (254, 47, 1200, 832)
        full = (0, 0, 1728, 1117)
        self.assertEqual(
            self.dr.choose_window_bounds([full], prev=main, screen=(1728, 1117)),
            main,
        )

    def test_detect_window_keeps_prev_on_miss(self) -> None:
        prev = (254, 47, 1200, 832)
        pag = SimpleNamespace(size=lambda: (1728, 1117))

        # Force platform getters to miss by stubbing.
        orig_mac = self.dr._window_bounds_macos
        orig_lin = self.dr._window_bounds_linux
        orig_win = self.dr._window_bounds_windows
        self.dr._window_bounds_macos = lambda **_k: []
        self.dr._window_bounds_linux = lambda **_k: None
        self.dr._window_bounds_windows = lambda **_k: None
        try:
            got = self.dr.detect_window(pag, prev=prev)
        finally:
            self.dr._window_bounds_macos = orig_mac
            self.dr._window_bounds_linux = orig_lin
            self.dr._window_bounds_windows = orig_win
        self.assertEqual(got, prev)

    def test_parse_multi_bounds(self) -> None:
        text = "10,20,300,400;50,60,640,611\n1,2,1200,800"
        boxes = self.dr._parse_l_t_w_h_list(text)
        self.assertEqual(len(boxes), 3)
        self.assertEqual(boxes[2], (1, 2, 1200, 800))


class DoubleCtrlCTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dr = _load_runner()

    def test_first_sigint_warns_second_raises(self) -> None:
        hook = self.dr.DoubleCtrlC(window_s=5.0)
        hook._on_sigint(None, None)
        self.assertFalse(hook.exit_requested)
        with self.assertRaises(KeyboardInterrupt):
            hook._on_sigint(None, None)
        self.assertTrue(hook.exit_requested)
        with self.assertRaises(KeyboardInterrupt):
            hook.check()

    def test_first_sigint_expires_after_window(self) -> None:
        hook = self.dr.DoubleCtrlC(window_s=0.05)
        hook._on_sigint(None, None)
        time.sleep(0.08)
        hook._on_sigint(None, None)
        self.assertFalse(hook.exit_requested)


if __name__ == "__main__":
    unittest.main()
