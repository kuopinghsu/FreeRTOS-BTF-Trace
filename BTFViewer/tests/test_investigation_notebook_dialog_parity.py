"""Desktop ``_InvestigationNotebookDialog`` ↔ web ``InvestigationNotebookDialog.vue``:
same buttons, same order, same labels / tooltips / placeholders, same Scaffold
behaviour and note — a lockstep check the user asked for explicitly."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
MW = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text(encoding="utf-8")
VUE = (BTF_ROOT / "web" / "src" / "components"
       / "InvestigationNotebookDialog.vue").read_text(encoding="utf-8")
APP = (BTF_ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")

# Just the desktop dialog class, so unrelated mainwindow text can't satisfy a match.
_DLG_START = MW.index("class _InvestigationNotebookDialog(QDialog):")
_ROW_START = MW.index("class _NotebookBookmarkRow(QWidget):")
_DLG_END = MW.index("class _ExportDialog(QDialog):")
DLG = MW[min(_DLG_START, _ROW_START):_DLG_END]


class NotebookDialogParityTests(unittest.TestCase):

    def test_same_button_labels(self):
        for label in (
            "✦ Scaffold", "↶ Undo", "↷ Redo", "Import…", "Export…",
            "Evidence pack…", "✕", "Link", "🗑", "Close",
        ):
            self.assertIn(label, DLG, f"desktop missing button {label!r}")
            self.assertIn(label, VUE, f"web missing button {label!r}")
        # "Add" is used for both the bookmark and the question rows on each side.
        self.assertGreaterEqual(DLG.count('QPushButton("Add")'), 2)
        self.assertGreaterEqual(len(re.findall(r">\s*Add\s*<", VUE)), 2)

    def test_same_button_tooltips(self):
        for tip in (
            "Seed observations from the current Analysis findings, plus a "
            "hypothesis + verification stub",
            "No Analysis findings to seed from",
            "Undo (notebook)",
            "Redo (notebook)",
            "Import a saved investigation (.json)",
            "Save this investigation as .json",
            "Build a compact AI evidence package from this investigation",
            "Remove bookmark",
        ):
            self.assertIn(tip, DLG, f"desktop missing tooltip {tip!r}")
            self.assertIn(tip, VUE, f"web missing tooltip {tip!r}")

    def test_header_action_order_is_identical(self):
        order = ["✦ Scaffold", "↶ Undo", "↷ Redo", "Import…", "Export…",
                 "Evidence pack…"]
        for src, name in ((DLG, "desktop"), (VUE, "web")):
            pos = [src.index(x) for x in order]
            self.assertEqual(pos, sorted(pos), f"{name} header action order differs")

    def test_body_section_order_is_identical(self):
        # Title -> Add bookmark -> Conclusion -> Links -> Unresolved questions
        for src, markers, name in (
            (DLG,
             ['"What is this investigation about?"', '"Bookmark title"',
              '"What does the evidence support', 'QLabel("Links")',
              'QLabel("Unresolved questions")'],
             "desktop"),
            (VUE,
             ['What is this investigation about?', 'Bookmark title',
              'What does the evidence support', '>Links<', '>Unresolved questions<'],
             "web"),
        ):
            pos = [src.index(m) for m in markers]
            self.assertEqual(pos, sorted(pos), f"{name} body section order differs")

    def test_same_placeholders(self):
        for ph in (
            "What is this investigation about?",
            "Bookmark title",
            "Note (optional)",
            "What does the evidence support? Leave blank until it does.",
            "Add a question",
        ):
            self.assertIn(ph, DLG, f"desktop missing placeholder {ph!r}")
            self.assertIn(ph, VUE, f"web missing placeholder {ph!r}")

    def test_scaffold_behaviour_and_note_match(self):
        # Scaffold's user-facing messages are identical, word for word. On the
        # desktop they are shown by the dialog itself; on the web the dialog
        # emits 'scaffold' and App.vue shows the toast — so check both places.
        nothing = "Nothing new to scaffold — every finding is already in the notebook."
        self.assertIn(nothing, DLG)
        self.assertIn(nothing, APP)
        for src, name in ((DLG, "desktop"), (APP, "web")):
            self.assertIn("Scaffolded ", src, name)
            self.assertIn(" from findings", src, name)
            # pluralised ("bookmark" + a conditional "s"), not the terse "bookmark(s)"
            self.assertNotIn("bookmark(s) from findings", src, name)
            self.assertIn("else 's'" if name == "desktop" else "'' : 's'", src, name)
        self.assertIn("@click=\"emit('scaffold')\"", VUE)
        # Same underlying pure helper drives both.
        self.assertIn("scaffold_investigation_from_findings", DLG)
        self.assertIn("scaffoldInvestigationFromFindings", APP)

    def test_same_grouping_and_count_label(self):
        # "<Type> (N)" group headers + "N bookmark(s)" footer count on both.
        self.assertIn("bookmark(s)", DLG)
        self.assertIn("bookmark(s)", VUE)
        self.assertIn("stale ref", DLG)
        self.assertIn("stale ref", VUE)


if __name__ == "__main__":
    unittest.main()
