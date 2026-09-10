"""Desktop ``_InvestigationNotebookDialog`` <-> web
``InvestigationNotebookDialog.vue``: both now implement the same 4-step guided
flow (Question -> Evidence -> Verify -> Conclusion), replacing the old
six-section master/detail editor. A lockstep check the user asked for
explicitly — see ``web/tests/notebookDialogSections.test.js`` for the web
counterpart of most assertions here."""
from __future__ import annotations

import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
MW = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text(encoding="utf-8")
VUE = (BTF_ROOT / "web" / "src" / "components"
       / "InvestigationNotebookDialog.vue").read_text(encoding="utf-8")
APP = (BTF_ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")

# Just the step-nav widget + dialog class, so unrelated mainwindow text
# (including the retired six-section widgets kept above it) can't satisfy a
# match by accident. The old `_NotebookProposalDialog` boundary is gone — the
# AI proposal is reviewed inline now, like the web dialog — so bound on the
# next module-level helper.
_DLG_START = MW.index('_NB_STEPS = ("question", "evidence", "verify", "conclusion")')
_DLG_END = MW.index("_EXPORT_TARGET_LABELS = {")
DLG = MW[_DLG_START:_DLG_END]


class NotebookDialogParityTests(unittest.TestCase):

    def test_no_rich_text_labels_for_dynamic_content(self):
        # A QLabel showing dynamic content (an investigation title, an
        # evidence card's text, an AI reply, ...) must never use <b>/<i>/etc:
        # Qt's rich-text auto-detection paints in black regardless of the
        # QPalette, which is invisible against a dark theme. Plain text +
        # setStyleSheet("font-weight:700;") is the correct way to bold it.
        self.assertNotRegex(DLG, r'QLabel\(f?"<b>')
        self.assertNotRegex(DLG, r"QLabel\(f?'<b>")

    def test_every_font_weight_stylesheet_sets_an_explicit_color(self):
        # A bug the user hit live: several labels set only font-weight/
        # font-size via setStyleSheet() and relied on inheriting the palette
        # text color. That works under plain palette-based rendering, but a
        # widget touched by ANY stylesheet can fall back to a hardcoded
        # default (black) once the native platform style — not exercised by
        # this offscreen test suite — takes over box-model rendering. Being
        # explicit removes the ambiguity regardless of style engine.
        calls = []
        i = 0
        while True:
            i = DLG.find(".setStyleSheet(", i)
            if i < 0:
                break
            start = DLG.index("(", i) + 1
            depth, j = 1, start
            while depth and j < len(DLG):
                if DLG[j] == "(":
                    depth += 1
                elif DLG[j] == ")":
                    depth -= 1
                j += 1
            calls.append(DLG[start:j - 1])
            i = j
        risky = [c for c in calls
                 if ("font-weight" in c or "font-size" in c) and "color:" not in c]
        self.assertEqual(risky, [], f"setStyleSheet call(s) missing an explicit color: {risky}")

    def test_never_uses_palette_mid_for_dim_text(self):
        # Another live-reported bug, root-caused after the fix above: several
        # labels used palette(mid) for "dim/secondary" text. QPalette::Mid is
        # a bevel/divider shading role the app's theme setup never assigns a
        # value to, so Qt's computed default can land almost on the window
        # background — unreadable. _dim_text_color() (blended from the
        # app's real window-text/window-background colors) replaces it.
        # (Comments mentioning palette(mid) as the thing NOT to do are fine —
        # this only flags it appearing as an actual CSS value.)
        self.assertNotRegex(DLG, r"palette\(mid\)\s*[;\"'{]")
        self.assertIn("def _dim_text_color()", DLG)

    def test_four_steps_replace_six_sections(self):
        self.assertIn('_NB_STEPS = ("question", "evidence", "verify", "conclusion")', DLG)
        for label in ("Question", "Evidence", "Verify", "Conclusion"):
            self.assertIn(label, DLG, f"desktop missing step {label!r}")
            self.assertIn(label, VUE, f"web missing step {label!r}")
        # The old six-section master/detail nav must be gone from the active
        # dialog (it may still exist, unused, in the retired widget classes
        # kept above _NbStepTab — DLG is scoped to exclude those).
        self.assertNotIn("NB_SECTION_ORDER", DLG)
        self.assertNotIn("_select_section", DLG)
        self.assertNotIn("activeSection", VUE)
        self.assertNotIn("class=\"nb-nav\"", VUE)

    def test_header_actions_present_on_both(self):
        for label in (
            "Add from Findings", "History…", "New investigation…",
            "Close investigation",
        ):
            self.assertIn(label, DLG, f"desktop missing header action {label!r}")
            self.assertIn(label, VUE, f"web missing header action {label!r}")

    def test_new_investigation_is_one_undo_step_on_both(self):
        # Q1 fix: a way to clear the notebook and restart, without losing the
        # ability to undo a stray click.
        self.assertIn("_start_new_investigation", DLG)
        self.assertIn("def _start_new_investigation(self)", DLG)
        self.assertIn("new_investigation(", DLG)
        self.assertIn("startNewInvestigation", VUE)
        self.assertIn("newInvestigation(", VUE)

    def test_bulk_add_from_findings_on_both(self):
        # Q2: the header's bulk seed action (up to 8 findings at once) is
        # distinct from the per-card single-finding picker.
        self.assertIn("_add_from_findings_bulk", DLG)
        self.assertIn("scaffold_investigation_from_findings", DLG)
        # Web emits 'scaffold' from the dialog; App.vue calls the scaffold
        # helper — same seed function, different layer.
        self.assertIn("emit('scaffold')", VUE)
        self.assertIn("scaffoldInvestigationFromFindings", APP)

    def test_ai_actions_route_through_one_collaborate_helper(self):
        for action in (
            "refine_question", "draft_hypotheses", "draft_conclusion",
            "review_investigation",
        ):
            self.assertIn(f'"{action}"', DLG, f"desktop missing action {action!r}")
        self.assertIn("def _collaborate(self, action_id", DLG)
        self.assertIn("self._on_collaborate(action_id, ctx, self._step)", DLG)
        self.assertIn("function collaborate(action, extra = {})"
                      if "function collaborate(action, extra = {})" in VUE
                      else "sourceStep: view.step", VUE)

    def test_step_tagged_ai_reply_shown_inline_on_both(self):
        # Q3 fix: the AI Assistant panel sits behind (desktop: alongside, but
        # not visible without switching tabs) this dialog — the reply must be
        # readable without leaving the Notebook.
        self.assertIn("def set_last_ai_reply(self, step: str, text: str)", DLG)
        self.assertIn("_last_ai_reply", DLG)
        self.assertIn("lastAiReply", VUE)
        self.assertIn("set_notebook_reply_sink", MW)
        self.assertIn("lastAssistantText", "".join(
            (BTF_ROOT / "web" / "src" / "components" / "AiAssistantPanel.vue")
            .read_text(encoding="utf-8")))

    def test_evidence_card_actions_on_both(self):
        for token in ("View source", "Ask AI about this", "Details"):
            self.assertIn(token, DLG, f"desktop evidence card missing {token!r}")
            self.assertIn(token, VUE, f"web evidence card missing {token!r}")
        # Reordering was dropped from the redesigned card on both platforms.
        self.assertNotIn("Move up", DLG)
        self.assertNotIn("Move down", DLG)

    def test_evidence_note_is_always_visible_and_editable_on_both(self):
        # Live-asked question: "how do I use an AI reply to add evidence to
        # the note?" — by typing/pasting into this field directly. It must
        # never be gated behind Details (which holds read-only metadata
        # only): that gate was the actual bug hiding the answer.
        self.assertIn('QPlainTextEdit(str(item.get("note")', DLG)
        self.assertIn('"Explanation (your words)"', DLG)
        self.assertIn("self._ev_note(b, w.toPlainText())", DLG)
        self.assertIn('placeholder="Explanation (your words)"', VUE)
        # The note textarea must not be inside the `expanded`/Details gate.
        note_pos = DLG.index('QPlainTextEdit(str(item.get("note")')
        expanded_gate_pos = DLG.index("expanded = bid in self._expanded_evidence_ids")
        self.assertLess(note_pos, expanded_gate_pos,
                         "evidence note must render before the Details expansion gate")

    def test_verify_step_explanation_status_and_checks_on_both(self):
        for token in ("Add explanation", "Suggest explanations",
                      "SUPPORTING EVIDENCE" if "SUPPORTING EVIDENCE" in DLG
                      else "Supporting evidence", "Add a check", "Link evidence"):
            self.assertIn(token, DLG, f"desktop missing {token!r}")
        for token in ("Add explanation", "Suggest explanations", "Link evidence"):
            self.assertIn(token, VUE, f"web missing {token!r}")

    def test_conclusion_derived_sections_on_both(self):
        for token in ("Cited evidence" if "Cited evidence" in VUE else "CITED EVIDENCE",
                      "Unresolved checks" if "Unresolved checks" in VUE else "UNRESOLVED CHECKS",
                      "Stale references" if "Stale references" in VUE else "STALE REFERENCES",
                      "Limitations" if "Limitations" in VUE else "LIMITATIONS"):
            self.assertIn(token.upper(), DLG.upper(), f"desktop missing {token!r}")
            self.assertIn(token, VUE, f"web missing {token!r}")

    def test_export_report_card_points_to_the_statistics_html_report_on_both(self):
        # The Notebook export is a JSON data file; the readable HTML report is
        # the Statistics panel's "Export HTML" (bundles tables + Analysis
        # Findings). Both dialogs say so in the Conclusion step's Export card.
        for src, name in ((DLG, "desktop"), (VUE, "web")):
            self.assertIn("Export report", src, f"{name} missing Export report card")
            self.assertIn("JSON data file", src, f"{name} missing JSON-export wording")
            self.assertIn("For a formatted HTML report you can open in a browser",
                          src, f"{name} missing the HTML-report pointer")
            self.assertIn("Analysis Findings for the current scope", src,
                          f"{name} missing the HTML-report scope note")

    def test_ai_proposal_is_reviewed_inline_no_modal_on_both(self):
        # §10 — the proposal renders in the right panel with per-op checkboxes
        # + Add selected / Add all / Dismiss; the old modal is retired on both.
        self.assertIn("def set_ai_proposal(self", DLG)
        self.assertIn("_render_ai_proposal_card", DLG)
        for tok in ("AI PROPOSAL", "Add selected (", "Add all", "Dismiss",
                    "Not applicable (", "needs_confirmation"):
            self.assertIn(tok, DLG, f"desktop proposal card missing {tok!r}")
        self.assertNotIn("class _NotebookProposalDialog", MW)
        self.assertIn("set_ai_proposal(proposal)", MW)   # parent feeds it inline
        # web
        self.assertIn("aiProposal:", VUE)
        self.assertIn("nb-proposal-card", VUE)
        for tok in ("AI proposal", "Add selected (", "Add all"):
            self.assertIn(tok, VUE, f"web proposal card missing {tok!r}")
        self.assertNotIn("NotebookProposalDialog", APP)

    def test_prose_reply_renders_as_titled_blocks_on_both(self):
        self.assertIn("def _render_ai_reply_blocks(self", DLG)
        self.assertIn("parse_reply_blocks(", DLG)
        self.assertIn("btfnext|btfstats", DLG)   # link-line strip
        self.assertIn("parseReplyBlocks(", VUE)
        self.assertIn("btfnext|btfstats", VUE)

    def test_evidence_card_open_statistics_and_delete_and_close_on_nav_on_both(self):
        for tok in ("Open Statistics", "Delete evidence", "def _delete_evidence(self"):
            self.assertIn(tok, DLG, f"desktop evidence card missing {tok!r}")
        # navigation closes the (full-screen) Notebook first
        self.assertIn("self.reject()", DLG)
        self.assertIn("Open Statistics", VUE)
        self.assertIn("emit('close'); onEvidenceJump", VUE)

    def test_gather_evidence_button_on_both(self):
        self.assertIn('"gather_evidence"', DLG)
        self.assertIn("Gather evidence with AI", DLG)
        self.assertIn("'gather_evidence'", VUE)
        self.assertIn("Gather evidence with AI", VUE)

    def test_select_all_evidence_action_on_both(self):
        self.assertIn("Select all evidence", DLG)
        self.assertIn("Select all evidence", VUE)

    def test_conclusion_side_reviews_not_discusses_on_both(self):
        # the non-functional generic "Discuss in AI Assistant" link/button is
        # gone; the Conclusion AI side button is "Review investigation".
        self.assertIn("Review investigation", DLG)
        self.assertNotIn("Discuss in AI Assistant", DLG)
        self.assertIn("Review investigation", VUE)
        self.assertNotIn("Discuss in AI Assistant", VUE)

    def test_restore_evidence_scope_action_on_both(self):
        # A separate, previewable, cancelable, undoable action; never folded
        # into View source / Jump to evidence.
        self.assertIn("Restore evidence scope…", DLG)
        self.assertIn("Restore evidence scope…", VUE)
        self.assertIn("evidence_scope_restore_plan", DLG)
        self.assertIn("evidenceScopeRestorePlan", VUE)
        self.assertIn("Undo scope restore", DLG)
        self.assertIn("onRestoreEvidenceScope", APP)
        self.assertIn("onUndoScopeRestore", APP)

    def test_import_export_and_evidence_package_on_both(self):
        for label in ("Import investigation…", "Export JSON", "Evidence package…"):
            self.assertIn(label, DLG, f"desktop missing {label!r}")
        for token in ("onImportFile", "exportJson", "emitEvidencePackage"):
            self.assertIn(token, VUE, f"web missing {token!r}")


class NotebookDialogRuntimeTests(unittest.TestCase):
    """Actually build the desktop dialog and drive it through the 4-step flow
    so the wiring can't silently break at runtime (the scans above only read
    source)."""

    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    def _dialog(self, inv, **kwargs):
        from PySide6.QtWidgets import QApplication
        import btf_viewer_pkg.mainwindow as mw
        from btf_viewer_pkg.investigation_notebook import empty_notebook_history
        QApplication.instance() or QApplication([])
        kw = dict(
            investigation=inv, history=empty_notebook_history(),
            trace=None,
            findings=[
                {"rule_id": "R1", "id": "R1", "severity": "warning", "title": "Long block"},
                {"rule_id": "R2", "id": "R2", "severity": "error", "title": "WCET outlier"},
            ],
            cursor_range=None, format_ns=str,
            on_change=lambda _x: None, on_status=lambda _m: None,
        )
        kw.update(kwargs)
        return mw._InvestigationNotebookDialog(**kw)

    def test_empty_investigation_starts_on_question_step(self):
        from btf_viewer_pkg.investigation_notebook import new_investigation
        dlg = self._dialog(new_investigation())
        try:
            self.assertEqual(dlg._step, "question")
            self.assertTrue(dlg._question_editing)
        finally:
            dlg.deleteLater()

    def test_starting_investigation_moves_to_evidence_in_one_step(self):
        from btf_viewer_pkg.investigation_notebook import new_investigation
        dlg = self._dialog(new_investigation())
        try:
            dlg._question_edit.setPlainText("Why does it stall?")
            dlg._start_or_save_question()
            self.assertEqual(dlg.investigation().get("title"), "Why does it stall?")
            self.assertEqual(dlg._step, "evidence")
            self.assertEqual(dlg.history()["stack"][-1]["title"], "Why does it stall?")
        finally:
            dlg.deleteLater()

    def test_bulk_add_from_findings_seeds_multiple_items(self):
        from btf_viewer_pkg.investigation_notebook import new_investigation
        dlg = self._dialog(new_investigation(title="T"))
        try:
            dlg._select_step("evidence")
            dlg._add_from_findings_bulk()
            self.assertGreaterEqual(len(dlg._sections()["evidence"]["items"]), 2)
        finally:
            dlg.deleteLater()

    def test_evidence_selection_and_next_action_gate_on_ai(self):
        from btf_viewer_pkg.investigation_notebook import add_evidence, new_investigation
        inv = add_evidence(new_investigation(title="T"), title="ev", role="supporting")
        dlg = self._dialog(inv, ai_enabled=False)
        try:
            dlg._select_step("evidence")
            self.assertEqual(dlg._evidence_next_action()["id"], "select")
            bid = dlg._sections()["evidence"]["items"][0]["bookmark_id"]
            dlg._toggle_evidence_selected(bid, True)
            self.assertEqual(dlg._selected_evidence_ids, {bid})
            self.assertEqual(dlg._evidence_next_action()["id"], "check")
        finally:
            dlg.deleteLater()

    def test_evidence_note_field_exists_and_commits_via_ev_note(self):
        # The field itself (real widget, present and enabled — this is the
        # answer to "how do I use an AI reply to add evidence to the note?":
        # type or paste into it) plus its commit path.
        from PySide6.QtWidgets import QApplication, QPlainTextEdit
        from btf_viewer_pkg.investigation_notebook import add_evidence, new_investigation
        inv = add_evidence(new_investigation(title="T"), title="ev", role="supporting")
        dlg = self._dialog(inv)
        app = QApplication.instance()
        try:
            dlg._select_step("evidence")
            app.processEvents()
            note = next(n for n in dlg._main_host.findChildren(QPlainTextEdit)
                        if not n.isHidden() and n.placeholderText() == "Explanation (your words)")
            self.assertTrue(note.isEnabled())
            self.assertFalse(note.isReadOnly())

            bid = dlg._sections()["evidence"]["items"][0]["bookmark_id"]
            dlg._ev_note(bid, "Copied from the AI's reply: the mutex is held by Low[92].")
            b = next(x for x in dlg.investigation()["bookmarks"] if x["id"] == bid)
            self.assertEqual(
                b["note"], "Copied from the AI's reply: the mutex is held by Low[92].")
        finally:
            dlg.deleteLater()

    def _add_evidence_menu(self, dlg):
        from PySide6.QtWidgets import QToolButton
        for btn in dlg._main_host.findChildren(QToolButton):
            if not btn.isHidden() and btn.text() == "Add evidence ▾":
                return btn
        return None

    def test_current_measurement_menu_action_disabled_without_cursor_range(self):
        # Live-reported: web disables "Current measurement" when there is no
        # cursor range (:disabled="!props.cursorRange"); desktop must match.
        from btf_viewer_pkg.investigation_notebook import new_investigation
        dlg = self._dialog(new_investigation(title="T"), cursor_range=None)
        try:
            dlg._select_step("evidence")
            add_btn = self._add_evidence_menu(dlg)
            self.assertIsNotNone(add_btn)
            actions = {a.text(): a for a in add_btn.menu().actions()}
            self.assertIn("Current measurement", actions)
            self.assertFalse(actions["Current measurement"].isEnabled())
            self.assertTrue(actions["Note"].isEnabled())
        finally:
            dlg.deleteLater()

    def test_current_measurement_menu_action_enabled_with_cursor_range(self):
        from btf_viewer_pkg.investigation_notebook import new_investigation
        dlg = self._dialog(new_investigation(title="T"), cursor_range=(1000, 2000))
        try:
            dlg._select_step("evidence")
            add_btn = self._add_evidence_menu(dlg)
            actions = {a.text(): a for a in add_btn.menu().actions()}
            self.assertTrue(actions["Current measurement"].isEnabled())
        finally:
            dlg.deleteLater()

    def test_from_findings_menu_action_disabled_without_findings(self):
        from btf_viewer_pkg.investigation_notebook import new_investigation
        dlg = self._dialog(new_investigation(title="T"), findings=[])
        try:
            dlg._select_step("evidence")
            add_btn = self._add_evidence_menu(dlg)
            actions = {a.text(): a for a in add_btn.menu().actions()}
            self.assertFalse(actions["From Findings"].isEnabled())
        finally:
            dlg.deleteLater()

    def test_all_three_add_evidence_entry_points_open_the_same_shared_form(self):
        # Matches web's openEvidenceForm(kind): one shared form, pre-seeded
        # differently per entry point, not three separate dialogs.
        from btf_viewer_pkg.investigation_notebook import EVIDENCE_BOOKMARK_TYPES, new_investigation
        dlg = self._dialog(new_investigation(title="T"), cursor_range=(1000, 2000))
        try:
            dlg._select_step("evidence")

            dlg._open_evidence_form("note")
            self.assertTrue(dlg._evidence_form_open)
            self.assertFalse(dlg._ev_draft["use_range"])

            dlg._evidence_form_open = False
            dlg._ev_draft["use_range"] = False
            dlg._open_evidence_form("measurement")
            self.assertTrue(dlg._evidence_form_open)
            self.assertTrue(dlg._ev_draft["use_range"])

            dlg._evidence_form_open = False
            dlg._ev_draft["type"] = "hypothesis"
            dlg._open_evidence_form("finding")
            self.assertTrue(dlg._evidence_form_open)
            self.assertEqual(dlg._ev_draft["type"], EVIDENCE_BOOKMARK_TYPES[1])
        finally:
            dlg.deleteLater()

    def test_evidence_form_renders_type_title_note_range_and_finding_fields(self):
        from PySide6.QtWidgets import (
            QApplication, QCheckBox, QComboBox, QLineEdit, QPlainTextEdit, QPushButton,
        )
        from btf_viewer_pkg.investigation_notebook import new_investigation
        dlg = self._dialog(new_investigation(title="T"), cursor_range=(1000, 2000))
        app = QApplication.instance()
        try:
            dlg._select_step("evidence")
            dlg._open_evidence_form("note")
            app.processEvents()

            combos = [c for c in dlg._main_host.findChildren(QComboBox) if not c.isHidden()]
            self.assertGreaterEqual(len(combos), 2)  # type combo + finding-link combo

            title_edits = [
                e for e in dlg._main_host.findChildren(QLineEdit)
                if not e.isHidden() and e.placeholderText() == "Evidence title"]
            self.assertEqual(len(title_edits), 1)

            note_edits = [
                n for n in dlg._main_host.findChildren(QPlainTextEdit)
                if not n.isHidden() and n.placeholderText() == "Note (optional)"]
            self.assertEqual(len(note_edits), 1)

            add_btns = [
                b for b in dlg._main_host.findChildren(QPushButton)
                if not b.isHidden() and b.text() == "Add"]
            self.assertEqual(len(add_btns), 1)
            self.assertFalse(add_btns[0].isEnabled())  # empty title -> disabled, like web

            range_boxes = [
                c for c in dlg._main_host.findChildren(QCheckBox)
                if not c.isHidden() and "Attach current cursor range" in c.text()]
            self.assertEqual(len(range_boxes), 1)
        finally:
            dlg.deleteLater()

    def test_evidence_form_hides_range_checkbox_without_cursor_range(self):
        from PySide6.QtWidgets import QApplication, QCheckBox
        from btf_viewer_pkg.investigation_notebook import new_investigation
        dlg = self._dialog(new_investigation(title="T"), cursor_range=None)
        app = QApplication.instance()
        try:
            dlg._select_step("evidence")
            dlg._open_evidence_form("note")
            app.processEvents()
            range_boxes = [
                c for c in dlg._main_host.findChildren(QCheckBox)
                if not c.isHidden() and "Attach current cursor range" in c.text()]
            self.assertEqual(len(range_boxes), 0)
        finally:
            dlg.deleteLater()

    def test_submitting_evidence_draft_commits_a_bookmark_and_closes_the_form(self):
        from btf_viewer_pkg.investigation_notebook import new_investigation
        dlg = self._dialog(new_investigation(title="T"), cursor_range=(1000, 2000))
        try:
            dlg._select_step("evidence")
            dlg._open_evidence_form("measurement")
            dlg._ev_draft["title"] = "CPU spikes at 1.2ms"
            dlg._ev_draft["note"] = "seen on core 3"
            dlg._add_evidence_draft()

            bms = dlg.investigation().get("bookmarks") or []
            self.assertEqual(len(bms), 1)
            self.assertEqual(bms[0]["title"], "CPU spikes at 1.2ms")
            self.assertEqual(bms[0]["note"], "seen on core 3")
            refs = bms[0].get("refs") or []
            self.assertTrue(any(r.get("kind") == "range" for r in refs))

            self.assertFalse(dlg._evidence_form_open)
            self.assertEqual(dlg._ev_draft["title"], "")
        finally:
            dlg.deleteLater()

    def test_submitting_evidence_draft_with_blank_title_does_nothing(self):
        from btf_viewer_pkg.investigation_notebook import new_investigation
        dlg = self._dialog(new_investigation(title="T"))
        try:
            dlg._select_step("evidence")
            dlg._open_evidence_form("note")
            dlg._ev_draft["title"] = "   "
            dlg._add_evidence_draft()
            self.assertEqual(dlg.investigation().get("bookmarks") or [], [])
            self.assertTrue(dlg._evidence_form_open)  # form stays open, like web's early return
        finally:
            dlg.deleteLater()

    def test_zero_selected_next_action_selects_all_then_flips_to_check(self):
        # Mirrors web: the zero-selected action is an ENABLED "Select all
        # evidence" that ticks every item; the resolver then flips to
        # "Check evidence with AI". (Was a disabled dead button before.)
        from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton
        from btf_viewer_pkg.investigation_notebook import add_evidence, new_investigation
        inv = add_evidence(new_investigation(title="T"), title="ev", role="supporting")
        inv = add_evidence(inv, title="ev2", role="supporting")
        dlg = self._dialog(inv, ai_enabled=True)
        app = QApplication.instance()
        try:
            dlg._select_step("evidence")
            app.processEvents()

            def find_next_btn():
                for btn in dlg._main_host.findChildren(QPushButton):
                    if not btn.isHidden() and btn.text() in (
                            "Select all evidence", "Check evidence with AI"):
                        return btn
                return None

            self.assertEqual(dlg._evidence_next_action()["id"], "select")
            btn = find_next_btn()
            self.assertIsNotNone(btn)
            self.assertTrue(btn.isEnabled())
            self.assertEqual(btn.text(), "Select all evidence")

            dlg._on_evidence_next_action("select")
            app.processEvents()

            self.assertEqual(len(dlg._selected_evidence_ids), 2)
            self.assertEqual(dlg._evidence_next_action()["id"], "check")
            btn = find_next_btn()
            self.assertIsNotNone(btn)
            self.assertEqual(btn.text(), "Check evidence with AI")

            # unticking one narrows it, still "check"
            cb = next(c for c in dlg._main_host.findChildren(QCheckBox) if c.isChecked())
            cb.setChecked(False)
            app.processEvents()
            self.assertEqual(dlg._evidence_next_action()["id"], "check")
        finally:
            dlg.deleteLater()

    def test_collaborate_tags_the_source_step_and_is_gated_by_ai_enabled(self):
        from btf_viewer_pkg.investigation_notebook import new_investigation
        calls = []
        dlg = self._dialog(
            new_investigation(title="T"), ai_enabled=False,
            on_collaborate=lambda *a: calls.append(a))
        try:
            dlg._select_step("verify")
            dlg._collaborate("draft_hypotheses")
            self.assertEqual(calls, [])  # AI disabled -> never calls out
            dlg._ai_enabled = True
            dlg._collaborate("draft_hypotheses")
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], "draft_hypotheses")
            self.assertEqual(calls[0][2], "verify")
        finally:
            dlg.deleteLater()

    def test_last_ai_reply_only_shows_on_its_own_step(self):
        from btf_viewer_pkg.investigation_notebook import new_investigation
        dlg = self._dialog(new_investigation(title="T"), ai_enabled=True)
        try:
            dlg._select_step("question")
            dlg.set_last_ai_reply("evidence", "some reply")
            # Rendering the question step with a reply tagged for a different
            # step must not raise, and must not surface that text here.
            dlg._render_ai_side()
        finally:
            dlg.deleteLater()

    def test_new_investigation_replaces_content_in_one_undo_step(self):
        from btf_viewer_pkg.investigation_notebook import (
            add_evidence, new_investigation, empty_notebook_history, push_notebook_state)
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
        inv = add_evidence(new_investigation(title="Old question"), title="ev", role="supporting")
        # Seed history with the pre-edit state, matching real usage (the host
        # always opens the dialog with the tab's existing notebook history,
        # which already carries the current investigation as its first entry).
        dlg = self._dialog(inv, history=push_notebook_state(empty_notebook_history(), inv))
        try:
            dlg._start_new_investigation()
            self.assertEqual(dlg.investigation().get("title"), "")
            self.assertEqual(dlg.investigation().get("bookmarks"), [])
            self.assertEqual(dlg._step, "question")
            # Undo restores the old investigation in a single step.
            dlg._undo()
            self.assertEqual(dlg.investigation().get("title"), "Old question")
        finally:
            dlg.deleteLater()

    def test_verify_step_links_evidence_and_tracks_checks(self):
        from btf_viewer_pkg.investigation_notebook import (
            add_bookmark, add_evidence, link_bookmarks, new_investigation)
        inv = add_bookmark(
            add_evidence(new_investigation(title="T"), title="ev",
                         role="supporting", bookmark_id="e1"),
            type="hypothesis", title="H1", bookmark_id="h1")
        inv = link_bookmarks(inv, "e1", "h1", "supports")
        dlg = self._dialog(inv)
        try:
            dlg._select_step("verify")
            self.assertEqual(dlg._links_to("h1", {"supports"}), ["e1"])
            dlg._render_step_body()  # must not raise
        finally:
            dlg.deleteLater()

    def test_conclusion_step_commits_on_focus_out(self):
        from btf_viewer_pkg.investigation_notebook import new_investigation
        dlg = self._dialog(new_investigation(title="T"))
        try:
            dlg._select_step("conclusion")
            dlg._conclusion_edit.setPlainText("Root cause is X.")
            dlg._commit_conclusion_draft()
            self.assertEqual(dlg.investigation().get("conclusion"), "Root cause is X.")
        finally:
            dlg.deleteLater()

    def test_every_step_paints_without_error(self):
        from btf_viewer_pkg.investigation_notebook import (
            add_bookmark, add_evidence, new_investigation,
            set_conclusion, add_unresolved_question)
        inv = add_unresolved_question(
            set_conclusion(
                add_bookmark(
                    add_evidence(new_investigation(title="Q"), title="ev",
                                 role="supporting", source="Statistics",
                                 kind="derived", scope={"start": 10, "end": 90}),
                    type="hypothesis", title="H1"),
                "verdict text"),
            "why?")
        dlg = self._dialog(inv)
        try:
            for sid in ("question", "evidence", "verify", "conclusion"):
                dlg._select_step(sid)
                pm = dlg._main_host.grab()
                self.assertFalse(pm.isNull(), f"{sid} step failed to paint")
        finally:
            dlg.deleteLater()

    def test_ai_assistance_panel_text_is_selectable_and_copyable(self):
        # Live-reported bug: QLabel defaults to NoTextInteraction, so none of
        # the AI assistance card's text (status, replies, suggestions) could
        # be selected or copied — e.g. to paste into an evidence Explanation.
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QLabel
        from btf_viewer_pkg.investigation_notebook import new_investigation
        dlg = self._dialog(new_investigation(title="T"), ai_enabled=True)
        try:
            for sid in ("question", "evidence", "verify", "conclusion"):
                dlg._select_step(sid)
                dlg.set_last_ai_reply(sid, "Some AI reply text to copy.")
                labels = dlg._side_host.findChildren(QLabel)
                self.assertTrue(labels, f"no labels found on {sid} AI side panel")
                for lbl in labels:
                    self.assertTrue(
                        lbl.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse,
                        f"{sid} AI side panel label {lbl.text()!r} is not selectable")
        finally:
            dlg.deleteLater()

    def test_ai_side_panel_hidden_when_ai_disabled(self):
        from btf_viewer_pkg.investigation_notebook import new_investigation
        dlg = self._dialog(new_investigation(title="T"), ai_enabled=False)
        try:
            for sid in ("question", "evidence", "verify", "conclusion"):
                dlg._select_step(sid)
                self.assertFalse(dlg._side_host.isVisible())
        finally:
            dlg.deleteLater()

    def test_ui_font_size_scales_labels_and_text_boxes(self):
        # Live-reported bug: Settings -> UI font size had no effect on this
        # dialog's text boxes (QLineEdit/QPlainTextEdit don't inherit an
        # ancestor's font the way QLabel does) or on hardcoded-px labels.
        #
        # A MainWindow instance built by an unrelated test elsewhere in the
        # suite may leave a global `QApplication` stylesheet installed with
        # its own `QLabel { font-size: ... }` rule (app.setStyleSheet() is
        # process-wide and MainWindow never tears it down on close) — QSS
        # font-size always wins over a widget's own .setFont(), so a leaked
        # rule would flatten every QLabel in this test to one fixed size
        # regardless of what this dialog asks for. Clear it for the
        # duration of this test so it verifies this dialog's own scaling,
        # not whichever app-wide font size a previous test happened to set.
        from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit
        from btf_viewer_pkg.investigation_notebook import (
            add_bookmark, add_evidence, new_investigation)
        app = QApplication.instance()
        prev_stylesheet = app.styleSheet() if app else ""
        if app is not None:
            app.setStyleSheet("")
        inv = add_bookmark(
            add_evidence(new_investigation(title="T"), title="ev", role="supporting"),
            type="hypothesis", title="H1")
        small = self._dialog(inv, ui_font_size=8)
        big = self._dialog(inv, ui_font_size=20)
        try:
            for dlg in (small, big):
                dlg._select_step("evidence")
            small_note = next(
                n for n in small._main_host.findChildren(QPlainTextEdit) if not n.isHidden())
            big_note = next(
                n for n in big._main_host.findChildren(QPlainTextEdit) if not n.isHidden())

            def px(font):
                return font.pixelSize() if font.pixelSize() > 0 else font.pointSize()

            self.assertLess(px(small_note.font()), px(big_note.font()))
            self.assertLess(px(small._title_lbl.font()), px(big._title_lbl.font()))

            for dlg in (small, big):
                dlg._select_step("verify")
            small_le = next(
                n for n in small._main_host.findChildren(QLineEdit) if not n.isHidden())
            big_le = next(
                n for n in big._main_host.findChildren(QLineEdit) if not n.isHidden())
            self.assertLess(px(small_le.font()), px(big_le.font()))
        finally:
            small.deleteLater()
            big.deleteLater()
            if app is not None:
                app.setStyleSheet(prev_stylesheet)

    def test_ai_panel_busy_state_shows_cancel(self):
        from PySide6.QtCore import QObject, Signal
        from btf_viewer_pkg.investigation_notebook import new_investigation

        class _FakePanel(QObject):
            busy_changed = Signal(bool)
            status_changed = Signal(str)

            def request_status(self):
                return {"busy": True, "status": "Waiting for Ollama…"}

            def cancel_request(self):
                self.cancelled = True

        panel = _FakePanel()
        panel.cancelled = False
        dlg = self._dialog(new_investigation(title="T"), ai_enabled=True, ai_panel=panel)
        try:
            dlg._select_step("evidence")
            dlg._cancel_ai_request()
            self.assertTrue(panel.cancelled)
        finally:
            dlg.deleteLater()


if __name__ == "__main__":
    unittest.main()
