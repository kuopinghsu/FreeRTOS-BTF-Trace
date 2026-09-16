"""ParityFixTODO.md P1 regression tests.

Source-text presence checks (same technique as test_shortcut_parity_table.py):

1. Every Web bare-key switch case that has no dedicated modifier meaning of
   its own must be guarded by `if (!mod)` (or `!mod && ...`), so
   Ctrl/Cmd+<key> never falls through into the bare-key action.
2. Desktop registers the new bare `S` Snapshot alias and the bare `+ = - _`
   zoom aliases alongside their existing modifier shortcuts.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
MW = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text(encoding="utf-8")
APP_VUE = (BTF_ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")

# Bare-key switch cases in App.vue's onGlobalKeydown that must not leak
# through a Ctrl/Cmd modifier.
GUARDED_BARE_KEY_CASES = ["1", "2", "h", "v", "g", "i", "d", "f", "s"]


class WebBareKeyModifierGuardTests(unittest.TestCase):
    def test_bare_key_switch_cases_are_guarded_against_ctrl_or_cmd(self) -> None:
        for key in GUARDED_BARE_KEY_CASES:
            case_re = re.compile(
                r"case '" + re.escape(key) + r"':\s*\n(?:\s*//.*\n)*\s*if \(!mod",
            )
            self.assertRegex(
                APP_VUE, case_re,
                f"bare-key case {key!r} is not guarded with `if (!mod)` — "
                "Ctrl/Cmd+" + key.upper() + " would leak into the bare-key action",
            )

    def test_bare_key_b_and_a_cases_are_guarded(self) -> None:
        # 'b' and 'a' use `!mod && !e.shiftKey` / `!mod && e.shiftKey` branches
        # rather than a single leading `if (!mod)`.
        for key in ("b", "a"):
            case_re = re.compile(
                r"case '" + re.escape(key) + r"':\s*\n\s*if \(!mod &&",
            )
            self.assertRegex(
                APP_VUE, case_re,
                f"bare-key case {key!r} is not guarded against Ctrl/Cmd",
            )


class DesktopBareKeyAliasTests(unittest.TestCase):
    def test_snapshot_editor_has_bare_s_alias(self) -> None:
        self.assertRegex(
            MW,
            r'_act_save_img\.setShortcuts\(\[QKeySequence\("Ctrl\+S"\),\s*QKeySequence\("S"\)\]\)',
            "Desktop Snapshot Editor action is missing the bare `S` shortcut alias",
        )

    def test_zoom_in_has_bare_plus_equals_aliases(self) -> None:
        self.assertRegex(
            MW,
            r'_act_zoom_in\.setShortcuts\(\[\s*QKeySequence\.ZoomIn,\s*QKeySequence\("\+"\),\s*QKeySequence\("="\),',
            "Desktop Zoom In action is missing bare `+` / `=` shortcut aliases",
        )

    def test_zoom_out_has_bare_minus_underscore_aliases(self) -> None:
        self.assertRegex(
            MW,
            r'_act_zoom_out\.setShortcuts\(\[\s*QKeySequence\.ZoomOut,\s*QKeySequence\("-"\),\s*QKeySequence\("_"\),',
            "Desktop Zoom Out action is missing bare `-` / `_` shortcut aliases",
        )


if __name__ == "__main__":
    unittest.main()
