"""Superseded Desktop dialogs are gone.

The unified ``_CorridorInspectorDialog`` is the only migration-heatmap / chord
entry point. ``_MigrationHeatmapDialog``, ``_MigrationHeatmapWidget`` and
``_ChordDiagramDialog`` were dead code (never instantiated) and have been
removed; the shared ``_ChordDiagramWidget`` (used by the Corridor Inspector
sidebar) stays.
"""

from __future__ import annotations

import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
STATS_PY = (BTF_ROOT / "btf_viewer_pkg" / "stats.py").read_text(encoding="utf-8")
MW_PY = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text(encoding="utf-8")

_GONE = ("_MigrationHeatmapDialog", "_MigrationHeatmapWidget", "_ChordDiagramDialog")


class LegacyDialogsRemovedTests(unittest.TestCase):
    def test_classes_not_defined_in_source(self) -> None:
        for name in _GONE:
            self.assertNotIn(f"class {name}(", STATS_PY, name)

    def test_classes_never_instantiated(self) -> None:
        for name in _GONE:
            self.assertNotIn(f"{name}(", STATS_PY, name)
            self.assertNotIn(name, MW_PY, name)

    def test_shared_chord_widget_survives(self) -> None:
        self.assertIn("class _ChordDiagramWidget(QWidget):", STATS_PY)

    def test_heatmap_and_chord_route_through_corridor_inspector(self) -> None:
        for method in ("_open_migration_heatmap", "_open_chord_diagram"):
            i = MW_PY.index(f"def {method}(self)")
            body = MW_PY[i:i + 200]
            self.assertIn("_open_corridor_inspector", body, method)
        self.assertIn("dlg = _CorridorInspectorDialog(", MW_PY)

    def test_web_orphan_dialog_components_removed(self) -> None:
        comp = BTF_ROOT / "web" / "src" / "components"
        self.assertFalse((comp / "MigrationHeatmapDialog.vue").exists())
        self.assertFalse((comp / "ChordDiagramDialog.vue").exists())

    def test_generated_bundle_has_no_legacy_dialog(self) -> None:
        bundle = BTF_ROOT / "builds" / "btf_viewer.py"
        if not bundle.is_file():
            self.skipTest("btf_viewer.py not built")
        text = bundle.read_text(encoding="utf-8", errors="ignore")
        for name in _GONE:
            self.assertNotIn(f"class {name}(", text, name)


if __name__ == "__main__":
    unittest.main()
