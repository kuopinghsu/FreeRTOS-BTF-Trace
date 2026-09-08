"""User-facing terminology normalization (BTFVIEWER_DESIGN_CONSISTENCY_TODO step 5).

Canonical spellings: `Core Utilization`, `Core Utilization Over Time`,
`Snapshot Editor`. Internal identifiers (`core_utilisation`, `coreUtil`, the
`cores` / `core_time` section ids, serialized keys) are deliberately left alone.
"""

from __future__ import annotations

import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]

DESKTOP_SRC = list((BTF_ROOT / "btf_viewer_pkg").rglob("*.py"))
WEB_SRC = (
    list((BTF_ROOT / "web" / "src").rglob("*.js"))
    + list((BTF_ROOT / "web" / "src").rglob("*.vue"))
)


def _hits(paths, needle):
    out = []
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if needle in line:
                out.append(f"{p.relative_to(BTF_ROOT)}:{i}: {line.strip()}")
    return out


class TerminologySourceTests(unittest.TestCase):
    def test_no_british_core_utilisation_in_source(self) -> None:
        hits = _hits(DESKTOP_SRC + WEB_SRC, "Core Utilisation")
        hits += _hits(DESKTOP_SRC + WEB_SRC, "Core utilisation")
        self.assertEqual(hits, [], "\n".join(hits))

    def test_no_bare_core_util_label_in_source(self) -> None:
        # "Core Util" as a standalone quoted label (tab text / CSV section).
        bad = []
        for q in ('"Core Util"', "'Core Util'"):
            bad += _hits(DESKTOP_SRC + WEB_SRC, q)
        self.assertEqual(bad, [], "\n".join(bad))

    def test_section_title_is_consistent_across_platforms(self) -> None:
        from btf_viewer_pkg.config import STATS_SECTION_TITLES

        self.assertEqual(
            STATS_SECTION_TITLES["cores"], "Core Utilization (excl. IDLE/TICK)"
        )
        self.assertEqual(
            STATS_SECTION_TITLES["core_time"], "Core Utilization Over Time"
        )
        pins = (BTF_ROOT / "web" / "src" / "utils" / "statsPins.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("cores: 'Core Utilization (excl. IDLE/TICK)'", pins)
        self.assertIn("core_time: 'Core Utilization Over Time'", pins)

    def test_command_palette_and_rail_use_corridor_inspector(self) -> None:
        from btf_viewer_pkg.config import COMMAND_PALETTE_ACTIONS

        self.assertEqual(
            dict(COMMAND_PALETTE_ACTIONS)["heatmap"],
            "Migration & Corridor Inspector",
        )
        mw = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text(encoding="utf-8")
        self.assertIn(
            '("heatmap", _RG_HEATMAP, "Migration & Corridor Inspector")', mw
        )
        self.assertIn('("snapshot", _RG_SNAPSHOT, "Snapshot Editor")', mw)
        app = (BTF_ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")
        self.assertIn("Migration &amp; Corridor Inspector</span>", app)
        self.assertIn(">Snapshot Editor</span>", app)

    def test_web_help_uses_snapshot_editor(self) -> None:
        app = (BTF_ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")
        self.assertNotIn("Open screenshot editor", app)
        self.assertNotIn("Open snapshot editor<", app)
        self.assertIn("Open Snapshot Editor</div>", app)


class TerminologyBundleTests(unittest.TestCase):
    def _bundle(self, name):
        path = BTF_ROOT / "builds" / name
        if not path.is_file():
            self.skipTest(f"{name} not built")
        return path.read_text(encoding="utf-8", errors="ignore")

    def test_desktop_bundle_has_no_british_or_stale_terms(self) -> None:
        text = self._bundle("btf_viewer.py")
        self.assertNotIn("Core Utilisation", text)
        self.assertNotIn("Screenshot editor", text)

    def test_web_bundle_has_no_british_or_stale_terms(self) -> None:
        text = self._bundle("btf_viewer.html")
        self.assertNotIn("Core Utilisation", text)
        self.assertNotIn("Screenshot editor", text)


if __name__ == "__main__":
    unittest.main()
