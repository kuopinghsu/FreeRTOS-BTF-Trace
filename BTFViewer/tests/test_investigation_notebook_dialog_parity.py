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

    def test_compact_context_header_present_on_both(self):
        # §7: durable status selector + scope/counts context line, driven by the
        # shared investigation_header() helper on both platforms.
        self.assertIn("investigation_header(", DLG)
        self.assertIn("investigationHeader(", VUE)
        for token in ("Scope: ", "evidence", "open check", "updated "):
            self.assertIn(token, DLG, f"desktop context line missing {token!r}")
            self.assertIn(token, VUE, f"web context line missing {token!r}")
        # Durable status is a labelled picker wired to set_status / setStatus.
        self.assertIn("set_status(", DLG)
        self.assertIn("setStatus(", VUE)
        self.assertIn("NOTEBOOK_STATUSES", DLG)
        self.assertIn("NOTEBOOK_STATUSES", VUE)

    def test_empty_state_entry_points_match(self):
        # §7: a truly empty investigation offers the same two explicit choices.
        for src, name in ((DLG, "desktop"), (VUE, "web")):
            self.assertIn("NB_EMPTY_FROM_FINDINGS"
                          if name == "desktop" else "emptyFromFindings", src, name)
            self.assertIn("NB_EMPTY_BLANK"
                          if name == "desktop" else "emptyBlank", src, name)
        # Both route "from findings" through the scaffold path.
        self.assertIn("_scaffold_from_findings", DLG)
        self.assertIn("emit('scaffold')", VUE)


class NotebookDialogRuntimeTests(unittest.TestCase):
    """Actually build the desktop dialog so the §7 header/empty-state wiring
    can't silently break at runtime (the scans above only read source)."""

    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    def _dialog(self, inv):
        from PySide6.QtWidgets import QApplication
        import btf_viewer_pkg.mainwindow as mw
        from btf_viewer_pkg.investigation_notebook import empty_notebook_history
        QApplication.instance() or QApplication([])
        return mw._InvestigationNotebookDialog(
            investigation=inv, history=empty_notebook_history(),
            trace=None,
            findings=[{"rule_id": "R1", "severity": "warning", "title": "Long block"}],
            cursor_range=None, format_ns=str,
            on_change=lambda _x: None, on_status=lambda _m: None,
        )

    def test_empty_investigation_renders_and_status_commits(self):
        from btf_viewer_pkg.investigation_notebook import new_investigation
        dlg = self._dialog(new_investigation())
        try:
            combo = dlg._nb_status_combo
            combo.setCurrentIndex((combo.currentIndex() + 1) % combo.count())
            want = combo.currentData()
            self.assertEqual(dlg._inv.get("status"), want)
            # after the status commit the context label is populated
            self.assertIn("Scope:", dlg._nb_context_lbl.text())
        finally:
            dlg.deleteLater()

    def test_adding_a_bookmark_leaves_empty_state(self):
        from btf_viewer_pkg.investigation_notebook import new_investigation
        dlg = self._dialog(new_investigation())
        try:
            dlg._new_title.setText("obs 1")
            dlg._add_bookmark()
            self.assertEqual(len(dlg._inv.get("bookmarks", [])), 1)
            dlg._render()  # must not raise
        finally:
            dlg.deleteLater()


if __name__ == "__main__":
    unittest.main()
