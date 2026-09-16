"""P.md — Web keyboard: BTFViewer must not consume Alt-modified browser/OS
shortcuts (Alt+Left/Right for Back/Forward above all), and must not let
Ctrl/Cmd+Arrow fall into the bare arrow-navigation handler either.

Source-text presence/ordering check (same technique as
test_bare_key_modifier_parity.py and test_shortcut_parity_table.py): this
suite has no DOM/event-simulation harness for App.vue's Composition-API
`onGlobalKeydown`, so pin the fix's shape directly in source rather than
its runtime behavior.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
APP_VUE = (BTF_ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")

_FN_START = "function onGlobalKeydown(e) {"


def _handler_body() -> str:
    start = APP_VUE.index(_FN_START)
    # Bounded to the next unindented top-level declaration so we don't
    # accidentally match text from a later, unrelated function.
    m = re.search(r"\n(?:function |const |async function )", APP_VUE[start + len(_FN_START):])
    end = start + len(_FN_START) + (m.start() if m else 6000)
    return APP_VUE[start:end]


class WebAltModifierGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = _handler_body()

    def test_centralized_alt_guard_present(self) -> None:
        self.assertIn(
            "if (e.altKey) return", self.body,
            "onGlobalKeydown is missing the centralized Alt guard — "
            "BTFViewer owns no Alt shortcuts, so Alt-modified keys must "
            "never reach the bare-key/arrow handling below it",
        )

    def test_alt_guard_runs_before_arrow_handling(self) -> None:
        alt_idx = self.body.index("if (e.altKey) return")
        arrow_idx = self.body.index("'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'")
        self.assertLess(
            alt_idx, arrow_idx,
            "the Alt guard must run before arrow-key handling, or "
            "Alt+Left/Alt+Right would still move the timeline instead of "
            "reaching the browser's Back/Forward navigation",
        )

    def test_alt_guard_runs_before_bare_key_switch(self) -> None:
        alt_idx = self.body.index("if (e.altKey) return")
        switch_idx = self.body.index("switch (key) {")
        self.assertLess(
            alt_idx, switch_idx,
            "the Alt guard must run before the bare-key switch, or "
            "Alt+1/2/H/V/G/I/D/F/S/B/A/+/-/= would still trigger "
            "BTFViewer actions",
        )

    def test_alt_guard_runs_after_explicit_ctrl_cmd_shortcuts(self) -> None:
        # Explicit Ctrl/Cmd shortcuts (Undo/Redo/Find/Home/End/Export/...)
        # must still be processed even if a stray Alt happens to be held
        # (e.g. Ctrl+Alt+Z on some layouts) -- only pure bare/Alt paths are
        # meant to be gated.
        alt_idx = self.body.index("if (e.altKey) return")
        last_ctrl_cmd_idx = self.body.rindex("if (mod &&")
        self.assertLess(
            last_ctrl_cmd_idx, alt_idx,
            "the Alt guard must come after the explicit Ctrl/Cmd shortcut "
            "checks, not before them",
        )

    def test_arrow_navigation_excludes_ctrl_cmd(self) -> None:
        self.assertRegex(
            self.body,
            r"if \(trace\.value && !mod && \['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'\]",
            "arrow-key navigation must exclude Ctrl/Cmd (`!mod`) so "
            "Ctrl/Cmd+Arrow does not enter the bare arrow handler",
        )


if __name__ == "__main__":
    unittest.main()
