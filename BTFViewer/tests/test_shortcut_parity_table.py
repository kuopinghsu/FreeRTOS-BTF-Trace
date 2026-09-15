"""Canonical Desktop/Web keyboard-shortcut parity table.

ParityTODO.md P2 "Automated Parity Tests": a small canonical table beats
duplicated shortcut literals scattered across tests. Each row's desktop_re
and web_re must both find a real match in their respective source files, so
this fails the moment either platform's binding is renamed, removed, or
never added in the first place -- catching exactly the class of drift the
P0 Export-shortcut bug was.

This is a source-text presence check (same technique as
test_command_palette_shortcuts.py), not a live-runtime behavior test.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
MW = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text(encoding="utf-8")
VIEW = (BTF_ROOT / "btf_viewer_pkg" / "view.py").read_text(encoding="utf-8")
APP_VUE = (BTF_ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")
MW_AND_VIEW = MW + "\n" + VIEW

# (action id, desktop shortcut label, web shortcut label,
#  desktop source regex, web source regex)
SHORTCUT_PARITY_TABLE = [
    ("open", "Ctrl+O", "Ctrl/Cmd+O",
     r"QKeySequence\.Open", r"key\.toLowerCase\(\)\s*===\s*'o'"),
    ("close-tab", "Ctrl+W", "Ctrl/Cmd+W",
     r"QKeySequence\.Close", r"key\.toLowerCase\(\)\s*===\s*'w'"),
    ("snapshot", "Ctrl+S", "Ctrl/Cmd+S",
     r'"Ctrl\+S"', r"mod\s*&&\s*!e\.shiftKey\s*&&\s*e\.key\.toLowerCase\(\)\s*===\s*'s'"),
    ("save-svg", "Ctrl+Shift+S", "Ctrl/Cmd+Shift+S",
     r'"Ctrl\+Shift\+S"', r"mod\s*&&\s*e\.shiftKey\s*&&\s*e\.key\.toLowerCase\(\)\s*===\s*'s'"),
    ("copy-image", "Ctrl+Shift+C", "Ctrl/Cmd+Shift+C",
     r'"Ctrl\+Shift\+C"', r"mod\s*&&\s*e\.shiftKey\s*&&\s*e\.key\.toLowerCase\(\)\s*===\s*'c'"),
    ("export", "Ctrl+Shift+E", "Ctrl/Cmd+Shift+E",
     r'"Ctrl\+Shift\+E"', r"mod\s*&&\s*e\.shiftKey\s*&&\s*e\.key\.toLowerCase\(\)\s*===\s*'e'"),
    ("undo", "Ctrl+Z", "Ctrl/Cmd+Z",
     r"QKeySequence\.Undo", r"e\.key\.toLowerCase\(\)\s*===\s*'z'"),
    ("redo", "Ctrl+Y / Ctrl+Shift+Z", "Ctrl/Cmd+Y / Ctrl/Cmd+Shift+Z",
     r'"Ctrl\+Y".*"Ctrl\+Shift\+Z"', r"key\.toLowerCase\(\)\s*===\s*'y'.*shiftKey.*key\.toLowerCase\(\)\s*===\s*'z'"),
    ("fit", "Ctrl+0 / F", "Ctrl/Cmd+0",
     r'"Ctrl\+0".*"F"', r"e\.key\s*===\s*'0'"),
    ("fit-cursors", "Ctrl+R", "Ctrl/Cmd+R",
     r'"Ctrl\+R"', r"e\.key\.toLowerCase\(\)\s*===\s*'r'"),
    ("find", "Ctrl+F", "Ctrl/Cmd+F",
     r"QKeySequence\.Find\b", r"e\.key\.toLowerCase\(\)\s*===\s*'f'"),
    ("settings", "Ctrl+,", "Ctrl/Cmd+,",
     r'"Ctrl\+,"', r"e\.key\s*===\s*','"),
    ("palette", "Ctrl+K", "Ctrl/Cmd+K",
     r'"Ctrl\+K"', r"e\.key\.toLowerCase\(\)\s*===\s*'k'"),
    ("task-view", "1", "1",
     r'QKeySequence\("1"\)', r"case\s*'1':"),
    ("core-view", "2", "2",
     r'QKeySequence\("2"\)', r"case\s*'2':"),
    ("horizontal", "H", "H",
     r'QKeySequence\("H"\)', r"case\s*'h':"),
    ("vertical", "V", "V",
     r'QKeySequence\("V"\)', r"case\s*'v':"),
    ("theme", "D", "D",
     r'QKeySequence\("D"\)', r"case\s*'d':"),
    ("grid", "G", "G",
     r'QKeySequence\("G"\)', r"case\s*'g':"),
    ("sti", "I", "I",
     r'QKeySequence\("I"\)', r"case\s*'i':"),
    ("cursor", "C", "C",
     r'lambda:\s*self\._view\.add_cursor_at_hover_or_center\(\),\s*"C"', r"key\s*===\s*'c'\s*&&\s*!mod"),
    ("bookmark", "B / Ctrl+B", "B / Ctrl/Cmd+B",
     r'QKeySequence\("Ctrl\+B"\),\s*QKeySequence\("B"\)', r"case\s*'b':"),
    ("annotation", "A / Ctrl+Shift+B", "A / Ctrl/Cmd+Shift+B",
     r'self\._prompt_annotation_at_center,\s*"Ctrl\+Shift\+B"', r"case\s*'a':"),
    ("segment-nav", "Tab / Shift+Tab", "N/A (Web has no segment Tab-cycle)",
     r"Key_Tab,\s*Qt\.Key\.Key_Backtab", None),
    ("help", "?", "?",
     r'QKeySequence\("\?"\)', None),
]


class ShortcutParityTableTests(unittest.TestCase):
    def test_every_canonical_shortcut_has_a_desktop_handler(self) -> None:
        for action, dt_label, _web_label, dt_re, _web_re in SHORTCUT_PARITY_TABLE:
            self.assertRegex(
                MW_AND_VIEW, dt_re,
                f"{action!r} ({dt_label}) has no matching Desktop shortcut binding",
            )

    def test_every_canonical_shortcut_has_a_web_handler(self) -> None:
        for action, _dt_label, web_label, _dt_re, web_re in SHORTCUT_PARITY_TABLE:
            if web_re is None:
                continue
            self.assertRegex(
                APP_VUE, web_re,
                f"{action!r} ({web_label}) has no matching Web shortcut binding",
            )

    def test_desktop_m_bookmark_alias_was_removed(self) -> None:
        """Regression guard for ParityTODO.md P2: M must not come back as a
        bookmark alias (Web never had it)."""
        self.assertNotRegex(
            MW,
            r'QKeySequence\("Ctrl\+B"\),\s*QKeySequence\("M"\)',
            "the removed M bookmark alias has reappeared",
        )


if __name__ == "__main__":
    unittest.main()
