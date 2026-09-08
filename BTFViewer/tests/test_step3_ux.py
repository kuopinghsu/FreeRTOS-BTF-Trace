"""Step 3 semantic / palette / evidence lockstep checks."""
from __future__ import annotations

import unittest

from btf_viewer_pkg.config import COMMAND_PALETTE_ACTIONS, COMMAND_PALETTE_META
from btf_viewer_pkg.evidence_nav import EVIDENCE_TOOLTIP
from btf_viewer_pkg.semantic_colors import format_semantic_delta, semantic_label


class Step3UxTests(unittest.TestCase):
    def test_fit_trace_palette_label(self):
        labels = dict(COMMAND_PALETTE_ACTIONS)
        self.assertEqual(labels["fit"], "Fit Trace")
        self.assertEqual(COMMAND_PALETTE_META["fit"]["shortcut"], "Ctrl+0")
        self.assertEqual(COMMAND_PALETTE_META["marks"]["shortcut"], "Ctrl+B")

    def test_palette_dropped_false_inspect_task_shortcut(self):
        ids = [aid for aid, _ in COMMAND_PALETTE_ACTIONS]
        self.assertNotIn("inspect-task", ids)
        self.assertNotIn("inspect-task", COMMAND_PALETTE_META)
        # `I` is STI-only; no palette item may advertise it.
        for meta in COMMAND_PALETTE_META.values():
            self.assertNotEqual(meta.get("shortcut"), "I")

    def test_palette_statistics_preset_labels(self):
        labels = dict(COMMAND_PALETTE_ACTIONS)
        self.assertEqual(labels["preset-triage"], "Statistics preset: Triage")
        self.assertEqual(labels["preset-latency"], "Statistics preset: Latency")
        self.assertEqual(labels["preset-smp"], "Statistics preset: SMP")
        self.assertNotIn("preset-compare", labels)
        self.assertIn("workspace", COMMAND_PALETTE_META["preset-triage"]["synonyms"])
        self.assertEqual(labels["heatmap"], "Migration & Corridor Inspector")

    def test_palette_has_notebook_and_focus(self):
        labels = dict(COMMAND_PALETTE_ACTIONS)
        self.assertEqual(labels["notebook"], "Investigation Notebook")
        self.assertEqual(labels["focus"], "Focus Mode")
        self.assertEqual(COMMAND_PALETTE_META["notebook"]["requires"], "trace")
        self.assertEqual(COMMAND_PALETTE_META["focus"]["requires"], "trace")

    def test_semantic_delta_glyphs(self):
        self.assertIn("↑", format_semantic_delta("+12 µs", "Regressed", True))
        self.assertIn("↓", format_semantic_delta("−3 µs", "Improved", True))
        self.assertEqual(format_semantic_delta("+12 µs", "Regressed", False), "+12 µs")

    def test_semantic_label_colorblind(self):
        self.assertTrue(semantic_label("Improved", "improved", True).startswith("↓"))
        self.assertEqual(semantic_label("Improved", "improved", False), "Improved")

    def test_evidence_tooltip(self):
        self.assertIn("Scope or Filters", EVIDENCE_TOOLTIP)


if __name__ == "__main__":
    unittest.main()
