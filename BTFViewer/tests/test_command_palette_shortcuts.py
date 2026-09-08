"""Command Palette shortcut hygiene + Desktop/Web parity.

BTFVIEWER_DESIGN_CONSISTENCY_TODO step 2:
- The `I` key only toggles STI visibility; no palette item may advertise it.
- Desktop and Web palettes expose the same action IDs, labels, and metadata.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from btf_viewer_pkg.config import COMMAND_PALETTE_ACTIONS, COMMAND_PALETTE_META

BTF_ROOT = Path(__file__).resolve().parent.parent
MW = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text(encoding="utf-8")
CONFIG_JS = (BTF_ROOT / "web" / "src" / "config.js").read_text(encoding="utf-8")


def _js_block(name: str, open_token: str, close_token: str) -> str:
    m = re.search(
        re.escape(name) + r"\s*=\s*" + re.escape(open_token) + r"\n(.*?)\n"
        + re.escape(close_token),
        CONFIG_JS, re.DOTALL,
    )
    assert m, f"{name} not found in web/src/config.js"
    return m.group(1)


def _js_palette_actions() -> list[tuple[str, str]]:
    body = _js_block("COMMAND_PALETTE_ACTIONS", "[", "]")
    return re.findall(r"\['([^']+)',\s*'([^']*)'\]", body)


def _js_palette_meta_keys() -> set[str]:
    body = _js_block("COMMAND_PALETTE_META", "Object.freeze({", "})")
    return set(re.findall(r"^  '?([\w-]+)'?:\s*\{", body, re.MULTILINE))


class CommandPaletteShortcutTests(unittest.TestCase):
    def test_no_duplicate_palette_shortcuts(self) -> None:
        seen: dict[str, str] = {}
        for aid, meta in COMMAND_PALETTE_META.items():
            sc = str(meta.get("shortcut") or "")
            if not sc:
                continue
            self.assertNotIn(
                sc, seen,
                f"palette shortcut {sc!r} on {aid!r} collides with {seen.get(sc)!r}",
            )
            seen[sc] = aid

    def test_palette_shortcuts_are_never_bare_single_keys(self) -> None:
        # Bare letters (I, G, D, F, …) are global timeline toggles; the palette
        # only advertises modified chords (Ctrl+F, Ctrl+B, Ctrl+0, Ctrl+,).
        for aid, meta in COMMAND_PALETTE_META.items():
            sc = str(meta.get("shortcut") or "")
            if not sc:
                continue
            self.assertFalse(
                re.fullmatch(r"[A-Za-z0-9]", sc),
                f"{aid!r} advertises bare key {sc!r}",
            )

    def test_no_palette_item_advertises_the_I_key(self) -> None:
        for aid, meta in COMMAND_PALETTE_META.items():
            self.assertNotEqual(
                str(meta.get("shortcut") or ""), "I",
                f"{aid!r} advertises the STI-only `I` key",
            )

    def test_inspect_task_is_gone_from_the_palette(self) -> None:
        ids = [aid for aid, _ in COMMAND_PALETTE_ACTIONS]
        self.assertNotIn("inspect-task", ids)
        self.assertNotIn("inspect-task", COMMAND_PALETTE_META)
        self.assertNotIn("inspect-task", CONFIG_JS)
        self.assertNotIn("inspect-task", MW)

    def test_I_key_binds_only_to_sti_toggle(self) -> None:
        hits = [
            m for m in re.finditer(r'QKeySequence\("I"\)', MW)
        ]
        self.assertEqual(len(hits), 1, "expected exactly one QKeySequence(\"I\")")
        line_start = MW.rfind("\n", 0, hits[0].start()) + 1
        line_end = MW.find("\n", hits[0].start())
        line = MW[line_start:line_end].lower()
        self.assertIn("sti", line)

    def test_keyboard_help_lists_I_once_as_sti(self) -> None:
        rows = re.findall(r'\("I",\s*"([^"]+)"\)', MW)
        self.assertEqual(len(rows), 1, rows)
        self.assertIn("STI", rows[0])

    def test_desktop_web_palette_action_ids_in_parity(self) -> None:
        py_ids = [aid for aid, _ in COMMAND_PALETTE_ACTIONS]
        js_ids = [aid for aid, _ in _js_palette_actions()]
        self.assertEqual(py_ids, js_ids)

    def test_desktop_web_palette_labels_in_parity(self) -> None:
        self.assertEqual(
            dict(COMMAND_PALETTE_ACTIONS), dict(_js_palette_actions()),
        )

    def test_desktop_web_palette_meta_keys_in_parity(self) -> None:
        self.assertEqual(set(COMMAND_PALETTE_META), _js_palette_meta_keys())

    def test_desktop_web_palette_meta_requires_in_parity(self) -> None:
        js_body = _js_block("COMMAND_PALETTE_META", "Object.freeze({", "})")
        for aid, meta in COMMAND_PALETTE_META.items():
            entry = re.search(
                rf"^  '?{re.escape(aid)}'?:\s*\{{\n(.*?)\n  \}},?$",
                js_body, re.DOTALL | re.MULTILINE,
            )
            self.assertIsNotNone(entry, aid)
            m_req = re.search(r"requires:\s*'([^']*)'", entry.group(1))
            self.assertEqual(
                str(meta.get("requires") or ""),
                m_req.group(1) if m_req else "",
                f"requires mismatch for {aid!r}",
            )


if __name__ == "__main__":
    unittest.main()
