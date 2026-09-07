"""Desktop ``_ExportDialog`` ↔ web ``ExportDialog.vue``: same target labels /
hints / options, and a **fixed-size** per-target options area on both so
changing the selected target never resizes the window.
"""
from __future__ import annotations

import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
MW = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text(encoding="utf-8")
VUE = (BTF_ROOT / "web" / "src" / "components" / "ExportDialog.vue").read_text(encoding="utf-8")
ACT = (BTF_ROOT / "web" / "src" / "utils" / "exportActions.js").read_text(encoding="utf-8")
APP = (BTF_ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")

# Just the desktop dialog class so unrelated mainwindow text can't satisfy a match.
_DLG_START = MW.index("class _ExportDialog(QDialog):")
_CONSTS_START = MW.index("_EXPORT_TARGET_LABELS = {")
_DLG_END = MW.index("class _CommandPaletteDialog(QDialog):")
DLG = MW[min(_DLG_START, _CONSTS_START):_DLG_END]

_TARGET_LABELS = (
    "Portable workspace (.btfw)",
    "Perfetto / Chrome Trace JSON",
    "Cursor-range BTF file",
)
_TARGET_HINTS = (
    "Trace + view state + analysis findings + trace health + investigation "
    "notebook + a rendered HTML report, in one ZIP-compatible file.",
    "Open in https://ui.perfetto.dev — full loaded trace or the current "
    "viewport.",
    "A .btf containing only the events between the earliest and latest cursors.",
)
_WORKSPACE_SUMMARY = (
    "View state & cursors",
    "Analysis findings",
    "Trace health status",
    "Investigation notebook",
    "Rendered statistics HTML report",
)
_MISC = (
    "Embed the trace file (portable — opens anywhere)",
    "Full loaded trace",
    "Current timeline viewport only",
    "Anonymize task names (Task-1, Task-2, …)",
)


class ExportDialogParityTests(unittest.TestCase):

    def test_same_target_labels(self):
        for label in _TARGET_LABELS:
            self.assertIn(label, DLG, f"desktop missing target label {label!r}")
            self.assertIn(label, ACT, f"web missing target label {label!r}")

    def test_same_target_hints(self):
        for hint in _TARGET_HINTS:
            self.assertIn(hint, DLG, f"desktop missing hint {hint!r}")
            self.assertIn(hint, ACT, f"web missing hint {hint!r}")

    def test_same_workspace_summary_lines(self):
        for line in _WORKSPACE_SUMMARY:
            self.assertIn(line, DLG, f"desktop missing summary line {line!r}")
            vue_line = line.replace("&", "&amp;")
            self.assertIn(vue_line, VUE, f"web missing summary line {vue_line!r}")

    def test_same_option_labels(self):
        for text in _MISC:
            self.assertIn(text, DLG, f"desktop missing {text!r}")
            self.assertIn(text, VUE, f"web missing {text!r}")

    def test_desktop_options_area_is_fixed_size(self):
        # QStackedWidget reserves the tallest page on every page (desktop
        # analogue of the web grid-overlap stack); SetFixedSize keeps the
        # dialog snug and non-resizable -> constant size across selections.
        self.assertIn("QStackedWidget()", DLG)
        self.assertIn("SizeConstraint.SetFixedSize", DLG)
        # No per-widget show/hide of options (the old resize-on-toggle bug).
        self.assertNotIn("setVisible(is_ws)", DLG)
        self.assertNotIn("setVisible(is_pf)", DLG)

    def test_web_options_area_is_fixed_size(self):
        # All three panels always render, share one grid cell, and the inactive
        # ones are hidden with visibility (not display) so the box stays as tall
        # as the tallest panel -> the dialog never resizes on selection change.
        self.assertIn("exp-opts-stack", VUE)
        self.assertIn("grid-area: 1 / 1", VUE)
        self.assertIn("visibility: hidden", VUE)
        self.assertIn("'is-hidden'", VUE)
        # No v-if that would unmount a panel and collapse the box.
        self.assertNotIn('v-if="target === ', VUE)
        self.assertNotIn('v-else-if="target === ', VUE)

    def test_anonymize_option_on_both(self):
        # A single "Anonymize task names" checkbox, applying to every target,
        # emitted in the export payload on both sides.
        self.assertIn("Anonymize task names (Task-1, Task-2, …)", DLG)
        self.assertIn("Anonymize task names (Task-1, Task-2, …)", VUE)
        self.assertIn('"anonymize": self._anon_cb.isChecked()', DLG)
        self.assertIn("anonymize: anonymize.value", VUE)
        # Wired through the App/dialog dispatch to all three targets.
        self.assertIn("anonymize=anon", MW)          # desktop _on_export
        self.assertIn("anonymize: anon", APP)        # web onExportRun
        # Same shared Task-N helper drives both.
        self.assertIn("build_task_alias_map", MW)
        self.assertIn("buildTaskAliasMap", APP)

    def test_desktop_dialog_matches_web_style(self):
        # Fixed 460px width, theme-aware colours (light + dark), and a hover
        # highlight on the radio cards — the same as ExportDialog.vue.
        self.assertIn("_EXPORT_DIALOG_WIDTH = 460", DLG)
        self.assertIn("min(460px", VUE)
        self.assertIn("QFrame#exp_target_card:hover", DLG)
        self.assertIn(".exp-target:hover", VUE)
        self.assertIn("_EXPORT_THEME", DLG)
        self.assertIn('getattr(parent, "_is_dark"', DLG)
        for hexval in ("#3C3C3C", "#DDDDDD"):   # web --border dark / light
            self.assertIn(hexval, DLG)


if __name__ == "__main__":
    unittest.main()
