"""AI panel widget behaviour that must match web/src/components/AiAssistantPanel.vue."""
from __future__ import annotations

import json
import os
import re
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests import reap_qt_widgets  # noqa: E402
from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from unittest.mock import patch  # noqa: E402

from PySide6.QtCore import QEvent, QPoint, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QGridLayout, QLabel, QMainWindow, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from btf_viewer_pkg.ai_assistant import (  # noqa: E402
    AI_DEFAULT_TEMPLATE_ORDER,
    AI_TEMPLATE_MENU_GROUPS,
    AI_TEMPLATE_MRU_MAX,
    AI_TEMPLATE_QUESTIONS,
    ai_entry_role,
    ai_entry_text,
    _MermaidZoomDialog,
    _qtextline_cursor_x,
    create_ai_assistant_panel,
    visible_ai_templates,
)
from btf_viewer_pkg.ai_mermaid import mermaid_zoom_token  # noqa: E402
from btf_viewer_pkg.ai_tools import (  # noqa: E402
    AI_TOOL_ADD_ANNOTATION,
    AI_TOOL_ANALYZE_TRACES,
    AI_TOOL_BASELINE_SCORE,
    AI_TOOL_BOOKMARK_FINDING,
    AI_TOOL_CHECK_BUDGET,
    AI_TOOL_CLEAR_MARKS,
    AI_TOOL_COMPARE_PERFORMANCE,
    AI_TOOL_COMPARE_TASKS,
    AI_TOOL_CORRELATE_EVENTS,
    AI_TOOL_DETECT_ANOMALIES,
    AI_TOOL_DETECT_PRIORITY_INVERSION,
    AI_TOOL_EXPLAIN_FINDING,
    AI_TOOL_EXPORT_INVESTIGATION,
    AI_TOOL_EXPORT_REPORT,
    AI_TOOL_FIND_CRITICAL_PATH,
    AI_TOOL_FIND_RELATED_FINDINGS,
    AI_TOOL_GENERATE_REPORT,
    AI_TOOL_INVESTIGATE,
    AI_TOOL_INTERPRET_QUERY,
    AI_TOOL_OPEN_STATS_SECTION,
    AI_TOOL_MANAGE_HYPOTHESES,
    AI_TOOL_PLAN_INVESTIGATION,
    AI_TOOL_SUGGEST_SCOPE,
    AI_TOOL_DETECT_CONTRADICTIONS,
    AI_TOOL_ASSESS_EVIDENCE_SUFFICIENCY,
    AI_TOOL_CLUSTER_FINDINGS,
    AI_TOOL_GENERATE_FINGERPRINT,
    AI_TOOL_FIND_SIMILAR_INVESTIGATIONS,
    AI_TOOL_REGRESSION_LOCALIZE,
    AI_TOOL_BUILD_CAUSAL_CHAIN,
    AI_TOOL_GENERATE_EXPERIMENT_PLAN,
    AI_TOOL_RECORD_EXPERIMENT_OUTCOME,
    AI_TOOL_ANALYZE_TEMPORAL_CAUSALITY,
    AI_TOOL_BUILD_TASK_DEPENDENCY_GRAPH,
    AI_TOOL_DECOMPOSE_RESPONSE_TIME,
    AI_TOOL_RANK_ROOT_CAUSES,
    AI_TOOL_VERIFY_CLAIM,
    AI_TOOL_CHALLENGE_CONCLUSION,
    AI_TOOL_INVESTIGATION_MEMORY,
    AI_TOOL_CLUSTER_INCIDENTS,
    AI_TOOL_CLOSE_INVESTIGATION,
    AI_TOOL_ANALYZE_DISTRIBUTION,
    AI_TOOL_ANALYZE_PERIODICITY,
    AI_TOOL_SUMMARIZE_INVESTIGATION_CONTEXT,
    AI_TOOL_OPTIMIZE,
    AI_TOOL_OPTIMIZE_EXPERIMENT,
    AI_TOOL_QUERY_RAW_METRIC,
    AI_TOOL_RECOMMEND_EXPERIMENTS,
    AI_TOOL_REGRESSION_EXPLAIN,
    AI_TOOL_RESET_VIEW,
    AI_TOOL_SEARCH_TIMELINE,
    AI_TOOL_TRIGGER_COMPARE,
    AI_TOOL_VALIDATE_EXPERIMENT,
    AI_TOOL_WHAT_IF,
    AI_VIEWER_TOOL_NAMES,
    max_tool_rounds,
)


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class AiPanelUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = _app()
        app.setQuitOnLastWindowClosed(False)

    @classmethod
    def tearDownClass(cls) -> None:
        reap_qt_widgets()

    def _panel(self, parent=None, **kwargs):
        kw = {
            "get_context": lambda: {"findings_text": "findings"},
            "get_settings": lambda: {"enabled": "true"},
        }
        kw.update(kwargs)
        panel = create_ai_assistant_panel(parent, **kw)
        self.addCleanup(panel.deleteLater)
        return panel

    def test_ask_needs_a_question(self) -> None:
        """Send stays disabled until the box has text (web parity)."""
        panel = self._panel()
        self.assertTrue(hasattr(panel, "_auth_chip"))
        self.assertIn("·", panel._auth_chip.text())
        self.assertTrue(panel._privacy_chip.text())
        self.assertIn("Local", panel._privacy_chip.text())
        self.assertEqual(panel._send_btn.text(), "")
        self.assertFalse(panel._send_btn.icon().isNull())
        self.assertFalse(panel._send_btn.isEnabled())
        self.assertIn("Send", panel._send_btn.toolTip())
        self.assertIn("Enter", panel._send_btn.toolTip())
        self.assertIn("Shift+Enter", panel._send_btn.toolTip())
        self.assertIn("Enter to send", panel._input.placeholderText())
        panel._input.setPlainText("why is CS[22] late?")
        self.assertTrue(panel._send_btn.isEnabled())
        with patch.object(panel, "send_current") as send:
            enter = QKeyEvent(
                QEvent.Type.KeyPress, Qt.Key.Key_Return,
                Qt.KeyboardModifier.NoModifier)
            self.assertTrue(panel.eventFilter(panel._input, enter))
            send.assert_called_once()
            send.reset_mock()
            shift_enter = QKeyEvent(
                QEvent.Type.KeyPress, Qt.Key.Key_Return,
                Qt.KeyboardModifier.ShiftModifier)
            self.assertFalse(panel.eventFilter(panel._input, shift_enter))
            send.assert_not_called()
        panel._input.setPlainText("   ")
        self.assertFalse(panel._send_btn.isEnabled())
        panel._set_busy(True)
        self.assertTrue(panel._send_btn.isEnabled())
        self.assertIn("Stop", panel._send_btn.toolTip())
        panel._set_busy(False)
        self.assertIn("Send", panel._send_btn.toolTip())
        self.assertFalse(panel._send_btn.isEnabled())
        actions = panel.findChild(QWidget, "aiActions")
        labels = [b.text() for b in actions.findChildren(QPushButton)]
        self.assertNotIn("Stop", labels)
        self.assertNotIn("Ask", labels)
        self.assertIn("Clear", labels)
        composer = panel.findChild(QWidget, "aiComposer")
        self.assertIsNotNone(composer)
        self.assertTrue(composer.isAncestorOf(panel._send_btn))
        self.assertFalse(hasattr(panel, "_stop_btn"))

    def test_guided_investigation_chrome(self) -> None:
        from btf_viewer_pkg.ai_case import GUIDED_STAGES, GUIDED_STAGE_LABELS

        panel = self._panel(get_context=lambda: {
            "findings_text": "findings",
            "findings": [{"id": "f1", "title": "Queue bounce", "task": "CS[7]"}],
        })
        panel._refresh_guide_ui()
        self.assertEqual(panel._start_inv_btn.text(), "Start Investigation")
        self.assertFalse(panel._start_inv_btn.isHidden())
        self.assertFalse(panel._start_inv_host.isHidden())
        # The workflow arrow line, intro blurb and the Finding/Task context box
        # were all removed — the Start Investigation button stands alone.
        self.assertFalse(hasattr(panel, "_start_inv_workflow"))
        self.assertFalse(hasattr(panel, "_start_inv_blurb"))
        self.assertFalse(hasattr(panel, "_start_inv_context"))
        self.assertFalse(panel._guide_host.isHidden())
        self.assertFalse(panel._guide_stepper.isHidden())
        for sid in GUIDED_STAGES:
            btn = panel._guide_step_btns[sid]
            self.assertIn(GUIDED_STAGE_LABELS[sid], btn.text())
            self.assertFalse(btn.isHidden())
        panel.apply_theme(False)
        panel._refresh_guide_ui()
        idle_ss = panel._guide_step_btns["triage"].styleSheet()
        self.assertIn("#666666", idle_ss)
        self.assertNotIn("#dbe2ea", idle_ss)
        panel._evidence_payload = {
            "finding": {"title": "Queue bounce", "task": "CS[1]"},
            "evidence": [{"label": "x", "time": 1}],
        }
        panel._refresh_guide_ui()
        self.assertTrue(panel._start_inv_btn.isHidden())
        self.assertTrue(panel._start_inv_host.isHidden())
        self.assertIn("Investigate", panel._guide_step_btns["investigate"].text())
        self.assertIn("#1E1E1E", panel._guide_step_btns["investigate"].styleSheet())
        self.assertIn("Queue bounce", panel._issue_view.text())

    def test_context_mode_chip_on_header_line(self) -> None:
        """Only the context-mode chip lives on the header line now (e.g.
        "AI Assistant · Google Gemini · Cloud · Compact"); the Statistics-scope
        chip and the old collapsible Context row are both gone."""
        panel = create_ai_assistant_panel(
            None,
            get_context=lambda: {"scope": "C1–C2"},
            get_settings=lambda: {"enabled": "true", "context_mode": "balanced"},
            on_gui_state=lambda: {"scope": "C1–C2"},
        )
        from PySide6.QtWidgets import QPushButton
        panel._refresh_context_row()
        self.assertEqual(panel._mode_chip.text(), "Balanced")
        self.assertFalse(hasattr(panel, "_scope_chip"))
        self.assertFalse(hasattr(panel, "_context_toggle"))
        self.assertFalse(hasattr(panel, "_context_body"))
        self.assertIsInstance(panel._mode_chip, QPushButton)
        hdr = panel.findChild(QWidget, "aiHeader")
        self.assertIs(panel._mode_chip.parentWidget(), hdr)
        src = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(encoding="utf-8")
        self.assertLess(
            src.index('header_row.addWidget(self._privacy_chip)'),
            src.index('header_row.addWidget(self._mode_chip)'))
        self.assertNotIn("self._scope_chip", src)

    def test_tool_cards_collapse_completed_auto_batch(self) -> None:
        from btf_viewer_pkg.ai_assistant import _ev_fold_id, _tool_cards_html
        from btf_viewer_pkg.ai_tools import AI_TOOL_SEARCH_TIMELINE

        done = [
            {"name": AI_TOOL_SEARCH_TIMELINE, "arguments": {}, "status": "done"},
            {"name": AI_TOOL_SEARCH_TIMELINE, "arguments": {}, "status": "done"},
        ]
        html_out = _tool_cards_html(done, "b1")
        self.assertIn("Evidence queries · 2 completed", html_out)
        self.assertIn("btffold:open/", html_out)
        self.assertIn('class="ai-fold-toggle ai-fold-toggle-l1"', html_out)
        self.assertIn("▸ Evidence queries · 2 completed", html_out)
        self.assertNotIn(">Show</a>", html_out)
        self.assertNotIn("Search timeline", html_out)
        fold_id = _ev_fold_id("Evidence queries · 2 completed", "b1")
        opened = _tool_cards_html(done, "b1", open_folds={fold_id})
        self.assertIn("btffold:close/", opened)
        self.assertIn("▾ Evidence queries · 2 completed", opened)
        self.assertIn("Search timeline", opened)
        pending = [
            {"name": "set_cursors", "arguments": {}, "status": "pending"},
            {"name": "set_cursors", "arguments": {}, "status": "pending"},
        ]
        pending_html = _tool_cards_html(pending, "b2")
        self.assertNotIn("Evidence queries", pending_html)
        self.assertIn("Apply", pending_html)

    def test_restore_without_chat_keeps_start_investigation(self) -> None:
        from btf_viewer_pkg.ai_case import dump_investigation_session

        payload = {
            "finding": {"title": "Queue bounce", "task": "CS[1]"},
            "evidence": [{"label": "x", "time": 1}],
        }
        blob = dump_investigation_session(
            payload=payload, plan={"goal": "g", "steps": []}, messages=[])
        panel = create_ai_assistant_panel(
            None,
            get_context=lambda: {"findings_text": "findings"},
            get_settings=lambda: {
                "enabled": "true", "investigation_session": blob,
            },
        )
        panel._restore_investigation_session()
        self.assertFalse(panel._start_inv_btn.isHidden())
        self.assertFalse(panel._start_inv_host.isHidden())
        self.assertTrue(panel._issue_view.isHidden())
        self.assertFalse((panel._issue_view.text() or "").strip())

        chat = dump_investigation_session(
            payload=payload,
            messages=[
                {"role": "user", "content": "why late?"},
                {"role": "assistant", "content": "preempt"},
            ],
        )
        panel2 = create_ai_assistant_panel(
            None,
            get_context=lambda: {"findings_text": "findings"},
            get_settings=lambda: {
                "enabled": "true", "investigation_session": chat,
            },
        )
        panel2._restore_investigation_session()
        self.assertTrue(panel2._start_inv_btn.isHidden())
        self.assertTrue(panel2._start_inv_host.isHidden())
        self.assertIn("Queue bounce", panel2._issue_view.text())

    def test_auth_forced_keeps_cta_after_401(self) -> None:
        """401 CTAs stay until a successful turn (web authForced parity)."""
        panel = self._panel()
        self.assertFalse(panel._auth_forced)
        self.assertTrue(panel._auth_cta.isHidden())
        panel._on_err("HTTP 401: unauthorized")
        self.assertTrue(panel._auth_forced)
        self.assertFalse(panel._auth_cta.isHidden())
        self.assertFalse(panel._auth_cta_signin.isHidden())
        panel._on_ok(json.dumps({"content": "ok", "tool_calls": []}))
        self.assertFalse(panel._auth_forced)
        self.assertTrue(panel._auth_cta.isHidden())
        self.assertIn("ok", panel._log.toPlainText())

    def test_on_err_shows_panel_and_window_status(self) -> None:
        """HTTP errors go to the AI status line (red) and the window status bar."""
        wnd = QMainWindow()
        panel = create_ai_assistant_panel(
            wnd,
            get_context=lambda: {"findings_text": "findings"},
            get_settings=lambda: {"enabled": "true"},
        )
        wnd.setCentralWidget(panel)
        wnd.show()
        panel._on_err("HTTP 503: This model is currently experiencing high demand.")
        self.assertIn("HTTP 503:", panel._status.text())
        self.assertIn("#e07070", panel._status.styleSheet())
        self.assertIn(
            "(Error) HTTP 503: This model is currently experiencing high demand.",
            panel._log.toPlainText(),
        )
        self.assertIn("AI: HTTP 503:", wnd.statusBar().currentMessage())
        panel._set_status("Done.")
        self.assertIn("#999", panel._status.styleSheet())
        self.assertNotIn("#e07070", panel._status.styleSheet())

    def test_log_keeps_prompt_and_reply_apart(self) -> None:
        """Template / follow-up prompts must not continue the previous assistant block."""
        panel = self._panel()
        panel._append("user", "What is wrong?")
        panel._append("assistant", "Nothing much.")
        panel._append("user", "Second prompt")
        text = panel._log.toPlainText()
        self.assertIn("What is wrong?", text)
        self.assertIn("Nothing much.", text)
        self.assertIn("Second prompt", text)
        self.assertRegex(text, r"Your prompt\s+What is wrong\?")
        self.assertRegex(text, r"AI Assistant\s+Nothing much\.")
        self.assertRegex(text, r"Your prompt\s+Second prompt")
        html = panel._log.toHtml().lower()
        # Qt may drop custom classes; bgcolor on each bubble still survives.
        self.assertGreaterEqual(html.count("#1e3348"), 2)
        self.assertGreaterEqual(html.count("#1a2620"), 1)
        # Second prompt must appear after the first reply in the rendered log.
        self.assertLess(text.index("Nothing much."), text.index("Second prompt"))

    def test_log_menu_offers_copy_and_save(self) -> None:
        panel = self._panel()
        menu = panel._log.createStandardContextMenu(QPoint(0, 0))
        menu.addSeparator()
        # Mirror _show_log_menu without opening a modal menu.
        copy_all = menu.addAction("Copy conversation")
        copy_all.setEnabled(bool(panel._entries))
        self.assertFalse(copy_all.isEnabled())

        panel._append("user", "hi")
        panel._append("assistant", "## Answer\n\nsee jump:12.")
        panel.copy_conversation()
        clip = QApplication.clipboard().text()
        self.assertIn("# BTF Viewer — AI Conversation", clip)
        self.assertIn("## Your prompt", clip)
        self.assertIn("## AI Assistant", clip)
        self.assertIn("see jump:12.", clip)
        self.assertEqual(panel._status.text(), "Copied to clipboard.")

    def test_log_menu_ask_ai_sends_selected_text(self) -> None:
        panel = self._panel()
        with patch.object(panel, "send_current") as send:
            panel._ask_log_selection("  Why is Low[266] blocked?  ")
        send.assert_called_once()
        self.assertEqual(panel._input.toPlainText(), "Why is Low[266] blocked?")
        with patch.object(panel, "send_current") as send:
            panel._ask_log_selection("   ")
        send.assert_not_called()
        with patch.object(panel, "send_current") as send:
            panel._ask_log_selection("Low[266]")
        send.assert_not_called()

        panel._append("assistant", "Critical path: Low[266]")
        found = panel._log.document().find("Low[266]")
        self.assertFalse(found.isNull())
        panel._log.setTextCursor(found)
        self.assertEqual(panel._log_selected_text(), "Low[266]")

    def test_signin_cta_opens_browser(self) -> None:
        panel = self._panel()
        opened = []
        with patch(
            "btf_viewer_pkg.ai_assistant.QDesktopServices.openUrl",
            side_effect=lambda u: opened.append(u.toString()),
        ):
            panel._open_signin_page()
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].startswith("http"))
        self.assertIn("Paste the key or token in Settings", panel._status.text())

    def test_http_links_open_in_system_browser(self) -> None:
        panel = self._panel()
        opened = []
        with patch(
            "btf_viewer_pkg.ai_assistant.QDesktopServices.openUrl",
            side_effect=lambda u: opened.append(u.toString()),
        ):
            panel._on_jump_link(QUrl("https://example.com/a"))
            panel._on_jump_link(QUrl("mailto:dev@example.com"))
        self.assertEqual(
            opened,
            ["https://example.com/a", "mailto:dev@example.com"],
        )

    def test_query_analysis_findings_uses_template(self) -> None:
        panel = self._panel()
        with patch.object(panel, "send_current") as send:
            panel.query_analysis_findings()
        send.assert_called_once()
        prompt = panel._input.toPlainText()
        self.assertIn("Analysis Findings", prompt)
        self.assertIn("severity", prompt)

    def test_jump_links_work_after_undo_refresh(self) -> None:
        jumps = []
        highlights = []

        def _exec(calls):
            return [{"ok": True, "message": "ok"} for _ in calls]

        panel = create_ai_assistant_panel(
            None,
            get_context=lambda: {"findings_text": "findings"},
            get_settings=lambda: {"enabled": "true", "auto_apply": "false"},
            on_execute_tools=_exec,
            on_jump=jumps.append,
            on_highlight=highlights.append,
        )
        panel._on_ok(json.dumps({
            "content": (
                "See jump:1100000 and jump:3200000. "
                "[Low](btfhighlight:task/Low%5B266%5D) [C0](btfhighlight:task/C0)"
            ),
            "tool_calls": [
                {"id": "c1", "name": "set_cursors",
                 "arguments": {"timestamps": [10, 20]}},
            ],
        }))
        with patch.object(panel, "_continue_with_messages"):
            panel._apply_tool_batch("b1", skipped=False)
            panel._on_tool_action("undo", "b1")
        html = panel._log.toHtml()
        self.assertIn("btfjump:time/1100000", html)
        self.assertIn("btfjump:time/3200000", html)
        panel._on_jump_link(QUrl("btfjump:time/1100000"))
        panel._on_jump_link(QUrl("btfjump:time/3200000"))
        self.assertEqual(jumps, [1100000.0, 3200000.0])
        panel._on_jump_link(QUrl("btfhighlight:task/Low%5B266%5D"))
        self.assertEqual(highlights[-1], "Low[266]")
        panel._on_jump_link(QUrl("btfhighlight:task/C0"))
        self.assertEqual(highlights[-1], "C0")

    def test_query_migration_thrash_uses_template(self) -> None:
        panel = self._panel()
        with patch.object(panel, "send_current") as send:
            panel.query_migration_thrash()
        send.assert_called_once()
        prompt = panel._input.toPlainText()
        self.assertIn("migration", prompt.lower())
        self.assertIn("ping-pong", prompt)
        self.assertIn("handoff heuristic", prompt)

    def test_apply_gui_actions_button_runs_pending_tools(self) -> None:
        executed = []

        def _exec(calls):
            executed.append(list(calls))
            return [{"ok": True, "message": "ok"} for _ in calls]

        panel = create_ai_assistant_panel(
            None,
            get_context=lambda: {"findings_text": "findings"},
            get_settings=lambda: {"enabled": "true", "auto_apply": "false"},
            on_execute_tools=_exec,
        )
        self.assertTrue(panel._tool_bar.isHidden())
        panel._on_ok(json.dumps({
            "content": "Placing annotation.",
            "tool_calls": [{
                "id": "c1",
                "name": "add_annotation",
                "arguments": {"time": 10.0, "note": "spike"},
            }],
            "message": {"role": "assistant", "content": "Placing annotation."},
        }))
        # In-log Apply/Skip cards are the primary chrome; the under-log bar
        # stays hidden when those cards exist.
        self.assertTrue(panel._tool_bar.isHidden())
        with patch.object(panel, "_continue_with_messages"):
            panel._on_jump_link(QUrl("btfaction:apply/b1"))
        self.assertEqual(len(executed), 1)
        self.assertEqual(executed[0][0]["name"], "add_annotation")
        self.assertTrue(panel._tool_bar.isHidden())

        panel2 = create_ai_assistant_panel(
            None,
            get_context=lambda: {"findings_text": "findings"},
            get_settings=lambda: {"enabled": "true", "auto_apply": "false"},
            on_execute_tools=_exec,
        )
        panel2._on_ok(json.dumps({
            "content": "Again.",
            "tool_calls": [{
                "id": "c2",
                "name": "set_view_mode",
                "arguments": {"mode": "core"},
            }],
        }))
        # Legacy colon hrefs must still Apply (QTextBrowser used to truncate them).
        with patch.object(panel2, "_continue_with_messages"):
            panel2._on_jump_link(QUrl("btfaction:apply:b1"))
        self.assertEqual(executed[-1][0]["name"], "set_view_mode")

    def test_apply_runs_each_viewer_tool(self) -> None:
        executed = []

        def _exec(calls):
            executed.append(list(calls))
            return [{"ok": True, "message": "ok"} for _ in calls]

        panel = create_ai_assistant_panel(
            None,
            get_context=lambda: {"findings_text": "findings"},
            get_settings=lambda: {"enabled": "true", "auto_apply": "false"},
            on_execute_tools=_exec,
        )
        panel._on_ok(json.dumps({
            "content": "Applying all tools.",
            "tool_calls": [
                {"id": "c1", "name": "set_cursors",
                 "arguments": {"timestamps": [10, 20]}},
                {"id": "c2", "name": "zoom_to_range",
                 "arguments": {"start_time": 20, "end_time": 10}},
                {"id": "c3", "name": "highlight_task",
                 "arguments": {"task_name_or_id": "PS[228]"}},
                {"id": "c4", "name": "set_view_mode",
                 "arguments": {"mode": "core", "orientation": "v"}},
                {"id": "c5", "name": "open_corridor_inspector",
                 "arguments": {"core_from": "0", "core_to": "1"}},
                {"id": "c5s", "name": AI_TOOL_OPEN_STATS_SECTION,
                 "arguments": {"section": "sync"}},
                {"id": "c6", "name": AI_TOOL_ADD_ANNOTATION,
                 "arguments": {"time": 99, "note": "spike"}},
                {"id": "c7", "name": AI_TOOL_QUERY_RAW_METRIC,
                 "arguments": {"task": "Low[266]", "metric": "pi"}},
                {"id": "c8", "name": AI_TOOL_EXPORT_REPORT,
                 "arguments": {"format": "html"}},
                {"id": "c9", "name": AI_TOOL_CLEAR_MARKS,
                 "arguments": {"what": "all"}},
                {"id": "c10", "name": AI_TOOL_RESET_VIEW,
                 "arguments": {}},
                {"id": "c11", "name": AI_TOOL_SEARCH_TIMELINE,
                 "arguments": {"query": "TICK", "mode": "sti"}},
                {"id": "c12", "name": AI_TOOL_TRIGGER_COMPARE,
                 "arguments": {"tab_a": "0", "tab_b": "1"}},
                {"id": "c13", "name": AI_TOOL_INVESTIGATE,
                 "arguments": {"finding_id": "x", "depth": 2}},
                {"id": "c14", "name": AI_TOOL_DETECT_ANOMALIES,
                 "arguments": {"limit": 5}},
                {"id": "c15", "name": AI_TOOL_CORRELATE_EVENTS,
                 "arguments": {"task": "CS[28]"}},
                {"id": "c15b", "name": AI_TOOL_FIND_CRITICAL_PATH,
                 "arguments": {"task": "CS[28]"}},
                {"id": "c16", "name": AI_TOOL_COMPARE_PERFORMANCE,
                 "arguments": {"tab_a": "0", "tab_b": "1"}},
                {"id": "c17", "name": AI_TOOL_GENERATE_REPORT,
                 "arguments": {"report_type": "performance"}},
                {"id": "c18", "name": AI_TOOL_CHECK_BUDGET,
                 "arguments": {}},
                {"id": "c19", "name": AI_TOOL_OPTIMIZE,
                 "arguments": {"limit": 3}},
                {"id": "c20", "name": AI_TOOL_REGRESSION_EXPLAIN,
                 "arguments": {"tab_a": "0", "tab_b": "1"}},
                {"id": "c21", "name": AI_TOOL_BOOKMARK_FINDING,
                 "arguments": {"time": 42, "kind": "evidence"}},
                {"id": "c23", "name": AI_TOOL_WHAT_IF,
                 "arguments": {"change": "pin CS[28] to Core_0", "task": "CS[28]"}},
                {"id": "c24", "name": AI_TOOL_OPTIMIZE_EXPERIMENT,
                 "arguments": {"task": "CS[28]", "limit": 3}},
                {"id": "c25", "name": AI_TOOL_ANALYZE_TRACES,
                 "arguments": {}},
                {"id": "c26", "name": AI_TOOL_BASELINE_SCORE,
                 "arguments": {"task": "CS[28]"}},
                {"id": "c27", "name": AI_TOOL_RECOMMEND_EXPERIMENTS,
                 "arguments": {"finding_id": "x", "limit": 3}},
                {"id": "c27b", "name": AI_TOOL_EXPORT_INVESTIGATION,
                 "arguments": {"finding_id": "x"}},
                {"id": "c28", "name": AI_TOOL_DETECT_PRIORITY_INVERSION,
                 "arguments": {"task": "Low[266]"}},
                {"id": "c29", "name": AI_TOOL_FIND_RELATED_FINDINGS,
                 "arguments": {"finding_id": "x", "limit": 5}},
                {"id": "c30", "name": AI_TOOL_COMPARE_TASKS,
                 "arguments": {"task_a": "Low[266]", "task_b": "High[268]"}},
                {"id": "c31", "name": AI_TOOL_EXPLAIN_FINDING,
                 "arguments": {"finding_id": "x", "level": "technical"}},
                {"id": "c32", "name": AI_TOOL_INTERPRET_QUERY,
                 "arguments": {"question": "Why is CS[28] slow?"}},
                {"id": "c33", "name": AI_TOOL_VALIDATE_EXPERIMENT,
                 "arguments": {"expected": {"migrations": -70},
                               "actual": {"migrations": -72}}},
                {"id": "c34", "name": AI_TOOL_MANAGE_HYPOTHESES,
                 "arguments": {"hypothesis_id": "h1", "status": "supported"}},
                {"id": "c35", "name": AI_TOOL_PLAN_INVESTIGATION,
                 "arguments": {"question": "Why did CS[22] miss?"}},
                {"id": "c36", "name": AI_TOOL_SUGGEST_SCOPE,
                 "arguments": {"question": "Why did CS[22] miss?"}},
                {"id": "c37", "name": AI_TOOL_DETECT_CONTRADICTIONS,
                 "arguments": {"hypothesis": "Mutex contention"}},
                {"id": "c38", "name": AI_TOOL_ASSESS_EVIDENCE_SUFFICIENCY,
                 "arguments": {"tools_run": ["investigate"]}},
                {"id": "c39", "name": AI_TOOL_CLUSTER_FINDINGS,
                 "arguments": {}},
                {"id": "c40", "name": AI_TOOL_GENERATE_FINGERPRINT,
                 "arguments": {}},
                {"id": "c41", "name": AI_TOOL_FIND_SIMILAR_INVESTIGATIONS,
                 "arguments": {"limit": 5}},
                {"id": "c42", "name": AI_TOOL_REGRESSION_LOCALIZE,
                 "arguments": {"label_a": "A", "label_b": "B"}},
                {"id": "c43", "name": AI_TOOL_BUILD_CAUSAL_CHAIN,
                 "arguments": {}},
                {"id": "c44", "name": AI_TOOL_GENERATE_EXPERIMENT_PLAN,
                 "arguments": {"task": "CS[22]", "limit": 3}},
                {"id": "c45", "name": AI_TOOL_RECORD_EXPERIMENT_OUTCOME,
                 "arguments": {"change": "pin CS[22]", "predicted": "migrations -50%",
                               "actual": "migrations -50%"}},
                {"id": "c47", "name": AI_TOOL_ANALYZE_TEMPORAL_CAUSALITY,
                 "arguments": {"task": "CS[22]"}},
                {"id": "c48", "name": AI_TOOL_BUILD_TASK_DEPENDENCY_GRAPH,
                 "arguments": {}},
                {"id": "c49", "name": AI_TOOL_DECOMPOSE_RESPONSE_TIME,
                 "arguments": {"task": "CS[22]"}},
                {"id": "c50", "name": AI_TOOL_RANK_ROOT_CAUSES,
                 "arguments": {}},
                {"id": "c51", "name": AI_TOOL_VERIFY_CLAIM,
                 "arguments": {"claim": "Mutex M blocked CS[22]"}},
                {"id": "c52", "name": AI_TOOL_CHALLENGE_CONCLUSION,
                 "arguments": {"conclusion": "mutex blocking"}},
                {"id": "c53", "name": AI_TOOL_INVESTIGATION_MEMORY,
                 "arguments": {"action": "recall"}},
                {"id": "c54", "name": AI_TOOL_CLUSTER_INCIDENTS,
                 "arguments": {}},
                {"id": "c55", "name": AI_TOOL_CLOSE_INVESTIGATION,
                 "arguments": {"conclusion": "migration thrash"}},
                {"id": "c56", "name": AI_TOOL_ANALYZE_DISTRIBUTION,
                 "arguments": {"values": [1, 2, 3]}},
                {"id": "c57", "name": AI_TOOL_ANALYZE_PERIODICITY,
                 "arguments": {"times": [1, 2, 3, 4]}},
                {"id": "c58", "name": AI_TOOL_SUMMARIZE_INVESTIGATION_CONTEXT,
                 "arguments": {"conclusion": "done"}},
            ],
        }))
        with patch.object(panel, "_continue_with_messages"):
            with patch.object(
                panel, "_export_ai_report",
                return_value={"ok": True, "message": "Saved html report"},
            ):
                panel._on_jump_link(QUrl("btfaction:apply/b1"))
        self.assertEqual(len(executed), 1)
        names = [c["name"] for c in executed[0]]
        host_names = [
            n for n in AI_VIEWER_TOOL_NAMES
            if n not in (AI_TOOL_EXPORT_REPORT, AI_TOOL_EXPORT_INVESTIGATION)
        ]
        self.assertEqual(names, host_names)
        by_name = {c["name"]: c["arguments"] for c in executed[0]}
        self.assertEqual(by_name["set_cursors"]["timestamps"], [10.0, 20.0])
        self.assertEqual(by_name["zoom_to_range"]["start_time"], 10.0)
        self.assertEqual(by_name["highlight_task"]["task_name_or_id"], "PS[228]")
        self.assertEqual(by_name["set_view_mode"]["orientation"], "vertical")
        self.assertEqual(by_name["open_corridor_inspector"]["core_from"], "0")
        self.assertEqual(by_name[AI_TOOL_ADD_ANNOTATION]["note"], "spike")
        self.assertEqual(by_name[AI_TOOL_QUERY_RAW_METRIC]["metric"], "priority_inheritance")
        self.assertEqual(by_name[AI_TOOL_CLEAR_MARKS]["what"], "all")
        self.assertEqual(by_name[AI_TOOL_SEARCH_TIMELINE]["query"], "TICK")
        self.assertEqual(by_name[AI_TOOL_TRIGGER_COMPARE]["tab_b"], "1")
        asst = [m for m in panel._chat_messages if m.get("role") == "assistant"][-1]
        self.assertEqual(
            [c["function"]["name"] for c in asst.get("tool_calls") or []],
            list(AI_VIEWER_TOOL_NAMES),
        )
        tool_msgs = [m for m in panel._chat_messages if m.get("role") == "tool"]
        self.assertEqual(
            [m.get("name") for m in tool_msgs],
            list(AI_VIEWER_TOOL_NAMES),
        )
        self.assertTrue(all(m.get("tool_call_id") for m in tool_msgs))

    def test_query_raw_metric_auto_applies(self) -> None:
        executed = []

        def _exec(calls):
            executed.append(list(calls))
            return [{"ok": True, "message": "1 episode", "data": {"count": 1}}]

        panel = create_ai_assistant_panel(
            None,
            get_context=lambda: {"findings_text": "findings"},
            get_settings=lambda: {"enabled": "true", "auto_apply": "false"},
            on_execute_tools=_exec,
        )
        with patch.object(panel, "_continue_with_messages"):
            panel._on_ok(json.dumps({
                "content": "Looking up PI.",
                "tool_calls": [{
                    "id": "q1",
                    "name": AI_TOOL_QUERY_RAW_METRIC,
                    "arguments": {"task": "Low[266]", "metric": "pi"},
                }],
            }))
        self.assertEqual(len(executed), 1)
        self.assertEqual(executed[0][0]["name"], AI_TOOL_QUERY_RAW_METRIC)

    def test_export_report_json_writes_investigation_package(self) -> None:
        import tempfile
        from btf_viewer_pkg import ai_assistant as ai_assistant_mod

        panel = create_ai_assistant_panel(
            None,
            get_context=lambda: {"findings_text": "findings"},
            get_settings=lambda: {"enabled": "true"},
            on_gui_state=lambda: {
                "findings": "findings", "file": "trace.btf",
                "span": "1.0s", "cores": 2, "scope": "full trace",
                "annotations": [],
            },
        )
        panel._append("assistant", "Root cause confirmed. See jump:12345 for evidence.")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "investigation.json")
            with patch.object(
                ai_assistant_mod.QFileDialog, "getSaveFileName",
                return_value=(path, ""),
            ):
                res = panel._export_ai_report(AI_TOOL_EXPORT_REPORT, {"format": "json"})
            self.assertTrue(res.get("ok"))
            with open(path, encoding="utf-8") as fh:
                package = json.load(fh)
        self.assertEqual(package.get("schema"), "btf-investigation-package")
        self.assertEqual(package.get("trace_name"), "trace.btf")
        self.assertEqual(package.get("scope"), "full trace")
        self.assertIn(12345.0, package.get("evidence_times") or [])
        self.assertIn("Root cause confirmed", package.get("conclusion") or "")

    def test_export_investigation_tool_uses_model_args(self) -> None:
        import tempfile
        from btf_viewer_pkg import ai_assistant as ai_assistant_mod

        panel = create_ai_assistant_panel(
            None,
            get_context=lambda: {"findings_text": "findings"},
            get_settings=lambda: {"enabled": "true"},
            on_gui_state=lambda: {
                "findings": "findings", "file": "trace.btf",
                "span": "1.0s", "cores": 2, "scope": "full trace",
                "annotations": [],
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "investigation.json")
            with patch.object(
                ai_assistant_mod.QFileDialog, "getSaveFileName",
                return_value=(path, ""),
            ):
                res = panel._export_ai_report(AI_TOOL_EXPORT_INVESTIGATION, {
                    "finding_id": "thrash_cs28",
                    "conclusion": "Confirmed: core thrashing on CS[28]",
                    "tools_run": ["investigate", "correlate_events"],
                    "evidence_times": [100.0, 200.0],
                })
            self.assertTrue(res.get("ok"))
            with open(path, encoding="utf-8") as fh:
                package = json.load(fh)
        self.assertEqual(package.get("schema"), "btf-investigation-package")
        self.assertEqual((package.get("finding") or {}).get("id"), "thrash_cs28")
        self.assertEqual(package.get("tools_run"), ["investigate", "correlate_events"])
        self.assertEqual(package.get("evidence_times"), [100.0, 200.0])
        self.assertIn("core thrashing", package.get("conclusion") or "")

    def test_qtextline_cursor_x_accepts_pyside_tuple(self) -> None:
        class _Line:
            def cursorToX(self, pos):  # noqa: N802
                return (12.5, pos)

        self.assertEqual(_qtextline_cursor_x(_Line(), 3), 12.5)

        class _Scalar:
            def cursorToX(self, pos):  # noqa: N802
                return 8.0

        self.assertEqual(_qtextline_cursor_x(_Scalar(), 1), 8.0)

    def test_mermaid_in_chat_click_does_not_crash(self) -> None:
        panel = self._panel()
        panel._append(
            "assistant",
            "```mermaid\ngraph LR\n  C0[Core_0] --> C1[Core_1]\n```",
        )
        QApplication.processEvents()
        for pt in (QPoint(10, 10), QPoint(80, 80), QPoint(200, 140)):
            panel._mermaid_img_local_pos(pt)
            panel._try_mermaid_node_click(pt)

    def test_mermaid_zoom_opens_from_chat_link(self) -> None:
        panel = self._panel()
        src = "graph LR\n  C0[Core_0] --> C1[Core_1]\n"
        token = mermaid_zoom_token(src)
        opened = []

        def fake_exec(dlg) -> int:
            opened.append(dlg._source)
            return 0

        with patch.object(_MermaidZoomDialog, "exec", fake_exec):
            panel._on_jump_link(QUrl(f"btfmermaid:zoom/{token}"))
            panel._on_jump_link(QUrl("btfmermaid:zoom/!!!"))
        self.assertEqual(opened, [src])

    def test_chat_first_layout_stretches_log(self) -> None:
        """Log stretches inside the splitter; plan starts hidden until investigation."""
        panel = self._panel()
        lay = panel.layout()
        self.assertIsInstance(lay, QVBoxLayout)
        idx = lay.indexOf(panel._split)
        self.assertGreaterEqual(idx, 0)
        self.assertEqual(lay.stretch(idx), 1)
        # Empty intent + conversation share a stacked frame under split-top
        # (Web `.ai-log > .ai-empty` parity).
        self.assertIs(panel._log.parentWidget(), panel._log_stack)
        self.assertIs(panel._log_stack.parentWidget(), panel._log_frame)
        self.assertIs(panel._log_frame.parentWidget(), panel._split_top)
        self.assertIs(panel._composer.parentWidget(), panel._split_bottom)
        self.assertFalse(isinstance(panel._log.parentWidget(), QScrollArea))
        self.assertTrue(panel._plan_host.isHidden())
        panel._set_investigation_plan({
            "goal": "Find the bottleneck",
            "steps": [{"id": "s1", "label": "Investigate", "status": "pending"}],
        })
        self.assertFalse(panel._plan_host.isHidden())
        self.assertEqual(panel._plan_view.text(), "Investigation  0/1  Investigate")
        self.assertNotIn("Goal", panel._plan_view.text())
        panel._set_investigation_plan({
            "goal": "Find the bottleneck",
            "steps": [{"id": "s1", "label": "Investigate", "status": "active"}],
        })
        self.assertEqual(panel._plan_view.text(), "Investigation  0/1  Investigate")

    def test_dynamic_chips_and_more_menu_cover_all_templates(self) -> None:
        panel = self._panel()
        expected = [
            next(lab for tid, lab, _p in AI_TEMPLATE_QUESTIONS if tid == pid)
            for pid in visible_ai_templates(recent=[], usage={})
        ]
        self.assertEqual([b.text() for b in panel._template_btns], expected)
        self.assertLessEqual(len(panel._template_btns), AI_TEMPLATE_MRU_MAX)
        from PySide6.QtWidgets import QWidget
        tpl = panel.findChild(QWidget, "aiTemplates")
        self.assertIsNotNone(tpl)
        more = [
            b.text() for b in tpl.findChildren(QPushButton)
            if b.text().replace("&", "").startswith("More")
        ]
        self.assertEqual(len(more), 1)
        self.assertEqual(panel._more_btn.text().replace("&", ""), "More…")
        menu_ids = [tid for _g, ids in AI_TEMPLATE_MENU_GROUPS for tid in ids]
        self.assertEqual(set(panel._template_actions), set(menu_ids))
        self.assertEqual(set(menu_ids), {t[0] for t in AI_TEMPLATE_QUESTIONS})
        self.assertEqual(len(menu_ids), 20)
        self.assertIsNone(panel.findChild(QWidget, "aiModes"))
        self.assertEqual(panel._mode_btns, [])
        self.assertEqual(
            panel._template_btn_ids,
            list(AI_DEFAULT_TEMPLATE_ORDER[:AI_TEMPLATE_MRU_MAX]),
        )

    def test_template_tooltips_wrap_for_qt(self) -> None:
        from btf_viewer_pkg.ai_assistant import qt_wrap_tooltip

        long_tip = (
            "Summarize up to three actionable Analysis Findings in severity order. "
            "For each, state the observed issue, strongest evidence, and one "
            "relevant Statistics page or timeline check."
        )
        wrapped = qt_wrap_tooltip(long_tip)
        self.assertTrue(wrapped.startswith("<html>"))
        self.assertIn('width="320"', wrapped)
        # One paragraph: no forced <br/> (Qt wraps on words inside the cell).
        self.assertNotIn("<br/>", wrapped)
        self.assertIn("Findings", wrapped)
        two = qt_wrap_tooltip("First sentence.\nSecond sentence.")
        self.assertIn("First sentence.<br/>Second sentence.", two)

        panel = self._panel()
        tips = [b.toolTip() for b in panel._template_btns]
        self.assertTrue(tips)
        self.assertTrue(any('width="320"' in t for t in tips), tips[0][:120])
        self.assertIn('width="320"', panel._more_btn.toolTip())
        investigate = next(iter(panel._template_actions.values()))
        self.assertIn('width="320"', investigate.toolTip())

    def test_evidence_syncs_to_log_for_export(self) -> None:
        from btf_viewer_pkg.ai_assistant import format_ai_conversation_html

        panel = self._panel()
        panel._update_evidence_from_tool_result("investigate", {
            "ok": True,
            "data": {
                "finding": {
                    "title": "Migration thrash",
                    "evidence": [{"label": "bounce", "time": 3200000.0}],
                },
                "confidence": "Medium",
            },
        })
        self.assertEqual(len(panel._entries), 1)
        self.assertEqual(ai_entry_role(panel._entries[0]), "evidence")
        self.assertIn("jump:3200000", ai_entry_text(panel._entries[0]))
        html = format_ai_conversation_html(panel._entries, "Simplified Chinese (简体中文)")
        self.assertIn("证据与验证", html)
        self.assertIn("jump:3200000", html)
        panel._update_evidence_from_tool_result("investigate", {
            "ok": True,
            "data": {
                "finding": {
                    "title": "Updated thrash",
                    "evidence": [{"label": "bounce", "time": 3300000.0}],
                },
                "confidence": "High",
            },
        })
        self.assertEqual(len(panel._entries), 1)
        self.assertIn("jump:3300000", ai_entry_text(panel._entries[0]))

    def test_evidence_sync_shows_current_issue_card(self) -> None:
        """CURRENT ISSUE card must appear from any evidence sync — e.g. the
        end-of-turn `_pin_evidence_log_entry` — not only the tool-result path
        (Web `syncEvidenceLogEntry` bumps `evidenceRev`)."""
        panel = self._panel(get_context=lambda: {
            "findings_text": "findings",
            "findings": [{"id": "f1", "title": "Queue bounce", "task": "CS[7]"}],
        })
        panel._append("user", "start investigation")
        panel._append("assistant", "Investigated. Root cause is X.")
        self.assertTrue(panel._issue_view.isHidden())
        # Evidence built outside the tool-result path (interpret / _finalize).
        panel._evidence_payload = {
            "finding": {"title": "Queue bounce", "task": "CS[7]",
                        "evidence": [{"label": "b", "time": 3200000.0}]},
            "confidence": "Medium",
        }
        panel._pin_evidence_log_entry()
        self.assertFalse(panel._issue_view.isHidden())
        self.assertIn("Queue bounce", panel._issue_view.text())

    def test_evidence_fold_toggle_does_not_scroll_to_earlier_reply(self) -> None:
        """Expanding Checks must keep Evidence in view (Web <details> lockstep)."""
        from btf_viewer_pkg.ai_investigation import format_evidence_panel_markdown

        panel = self._panel()
        app = _app()
        panel.resize(420, 360)
        panel.show()
        for i in range(10):
            panel._append(
                "assistant",
                f"AI Assistant reply {i}. " + ("blocking latency " * 24),
            )
        md = format_evidence_panel_markdown({
            "conclusion": "Mutex stall",
            "confidence": "Medium",
            "checks": [
                {"label": "Migrations", "status": "fail"},
                {"label": "Mutex blocking", "status": "fail"},
            ],
        }, "English")
        panel._append("evidence", md)
        panel._log_stack.setCurrentIndex(1)
        panel._log.setFixedHeight(160)
        app.processEvents()
        bar = panel._log.verticalScrollBar()
        bar.setValue(bar.maximum())
        app.processEvents()
        before = bar.value()
        self.assertGreater(
            before, 8,
            "log must be scrollable so a jump-to-top is detectable",
        )
        html = panel._log.toHtml()
        match = re.search(r'href="(btffold:open/[^"]+)"', html)
        self.assertIsNotNone(match, "Checks fold should expose a btffold:open link")
        href = match.group(1).replace("&amp;", "&")
        panel._on_jump_link(QUrl(href))
        for _ in range(4):
            app.processEvents()
        after = bar.value()
        self.assertGreater(after, 8, "fold toggle must not jump to the earlier AI Assistant turn")
        self.assertGreaterEqual(after, before - 24)

    def test_evidence_score_survives_late_planner_tool(self) -> None:
        """Start Investigation ends with challenge/rank tools that omit times."""
        panel = self._panel()
        panel._update_evidence_from_tool_result("correlate_events", {
            "ok": True,
            "data": {
                "task": "CS[22]",
                "events": [
                    {"kind": "migration", "detail": "c0->c1", "time": 1487000.0},
                    {"kind": "ready", "detail": "wake", "time": 1487100.0},
                ],
                "correlation": 0.9,
            },
        })
        self.assertGreaterEqual(
            int((panel._evidence_payload or {}).get("evidence_score") or 0),
            65,
        )
        panel._update_evidence_from_tool_result("challenge_conclusion", {
            "ok": True,
            "message": "Challenge: conclusion holds",
            "data": {"verdict": "Confirmed", "confidence": "High"},
        })
        payload = panel._evidence_payload or {}
        self.assertGreaterEqual(int(payload.get("evidence_score") or 0), 65)
        self.assertIn("jump:1487000", ai_entry_text(panel._entries[0]))

    def test_evidence_language_switch_chinese_to_english(self) -> None:
        settings = {
            "enabled": "true",
            "response_language": "Simplified Chinese (简体中文)",
        }
        panel = create_ai_assistant_panel(
            None,
            get_context=lambda: {},
            get_settings=lambda: dict(settings),
            on_save_settings=lambda patch: settings.update(patch),
        )
        panel._append("assistant", "结论在上方。")
        panel._update_evidence_from_tool_result("investigate", {
            "ok": True,
            "data": {
                "finding": {
                    "title": "Migration thrash",
                    "evidence": [{"label": "bounce", "time": 3200000.0}],
                },
                "confidence": "Medium",
            },
        })
        self.assertEqual(ai_entry_role(panel._entries[-1]), "evidence")
        self.assertIn("证据", ai_entry_text(panel._entries[-1]))
        self.assertIn("中", ai_entry_text(panel._entries[-1]))

        settings["response_language"] = "English"
        panel._refresh_localized_chrome("English")
        self.assertEqual(len(panel._entries), 2)
        self.assertEqual(ai_entry_role(panel._entries[-1]), "evidence")
        en = ai_entry_text(panel._entries[-1])
        self.assertIn("Evidence", en)
        self.assertIn("Confidence", en)
        self.assertIn("Medium", en)
        self.assertIn("jump:3200000", en)
        self.assertNotIn("证据", en)

        panel._append("assistant", "Final English summary.")
        panel._pin_evidence_log_entry()
        self.assertEqual(ai_entry_role(panel._entries[-1]), "evidence")
        self.assertEqual(ai_entry_role(panel._entries[-2]), "assistant")
        self.assertIn("Final English summary", ai_entry_text(panel._entries[-2]))

    def test_investigation_mode_helpers_and_hypothesis_links(self) -> None:
        from btf_viewer_pkg.ai_case import enrich_hypotheses

        panel = self._panel()
        self.assertIsNone(panel.findChild(QWidget, "aiModes"))
        self.assertEqual(panel._mode_btns, [])
        save_act = getattr(panel, "_save_investigation_template_action", None)
        self.assertIsNotNone(save_act)
        self.assertIn("Save as template", save_act.text().replace("&", ""))

        hyps = enrich_hypotheses([{"hypothesis": "Mutex contention", "why": "blocking"}])
        hid = hyps[0]["id"]
        panel._evidence_payload = {
            "hypotheses_managed": hyps,
            "hypotheses": hyps,
            "conclusion": "Mutex contention",
        }
        panel._on_jump_link(QUrl(f"btfhyp:supported/{hid}"))
        self.assertEqual(
            panel._evidence_payload["hypotheses_managed"][0]["status"],
            "supported",
        )
        with patch.object(panel, "send_current") as send:
            panel._on_jump_link(QUrl(f"btfhyp:test/{hid}"))
        send.assert_called_once()
        self.assertIn("Test hypothesis", panel._input.toPlainText())

    def test_generated_next_step_does_not_record_template_use(self) -> None:
        panel = self._panel()
        panel._evidence_payload = {
            "next_steps": [{
                "label": "Verify mutex contention",
                "prompt": "Verify mutex contention in the current scope.",
                "reason": "missing mutex",
                "kind": "verify",
            }],
        }
        with patch.object(panel, "send_current") as send, patch.object(
            panel, "_record_template_use",
        ) as rec:
            panel._on_jump_link(QUrl("btfnext:run/0"))
        send.assert_called_once()
        rec.assert_not_called()
        self.assertIn("Verify mutex contention", panel._input.toPlainText())
        self.assertTrue(panel._skip_interpret)

    def test_nextstep_tag_run_sends_tagged_sentence(self) -> None:
        zh_action = (
            "建議將 CS[20] 任務固定 (pin) 至單一核心 (設定 CPU Affinity)，"
            "以消除頻繁的上下文切換開銷與快取失效問題，隨後重新觀察系統整體"
            "遷移負載是否下降。"
        )
        english_prompt = "Inspect Core Migrations in the current scope."
        panel = self._panel()
        panel._tool_round = 8
        panel._active_template_id = "auto_investigate"
        panel._evidence_payload = {
            "conclusion": "Mutex stall",
            "coverage": {"percent": 90},
            "confidence": "high",
            "next_steps": [{
                "label": "Inspect core migrations",
                "prompt": english_prompt,
                "kind": "statistics",
            }],
        }
        panel._on_ok(json.dumps({
            "content": (
                "下一步檢查 (Next check)\n"
                f"nextstep:{{{zh_action}}}\n"
            ),
            "tool_calls": [],
        }))
        log = panel._log.toHtml()
        self.assertIn("btfnext:text/0", log)
        self.assertNotIn("btfnext:run/0", log)
        self.assertIn(zh_action, panel._log.toPlainText())
        self.assertNotIn("nextstep:", panel._log.toPlainText())
        rows = (panel._evidence_payload or {}).get("prose_nextsteps") or []
        self.assertEqual(rows[0], zh_action)
        with patch.object(panel, "send_current") as send, patch.object(
            panel, "_record_template_use",
        ) as rec:
            panel._on_jump_link(QUrl("btfnext:text/0"))
        send.assert_called_once()
        rec.assert_not_called()
        self.assertEqual(panel._input.toPlainText(), zh_action)
        self.assertNotEqual(panel._input.toPlainText(), english_prompt)
        self.assertTrue(panel._skip_interpret)

    def test_final_reply_without_tools_shows_verdict(self) -> None:
        """A text-only final reply is shown immediately."""
        executed = []

        def _exec(calls):
            executed.append([c.get("name") for c in calls])
            return [{"ok": True, "message": "ok"}]

        panel = create_ai_assistant_panel(
            None,
            get_context=lambda: {"findings_text": "findings"},
            get_settings=lambda: {"enabled": "true"},
            on_execute_tools=_exec,
        )
        panel._evidence_payload = {
            "conclusion": "Mutex stall",
            "coverage": {"percent": 35},
        }
        with patch.object(panel, "_continue_with_messages") as cont:
            panel._on_ok(json.dumps({
                "content": "Verdict: mutex stall.",
                "tool_calls": [],
            }))
        self.assertEqual(executed, [])
        cont.assert_not_called()
        self.assertIn("Verdict: mutex stall.", panel._log.toPlainText())

    def test_empty_final_reply_after_tools_uses_evidence_fallback(self) -> None:
        panel = create_ai_assistant_panel(
            None,
            get_context=lambda: {"findings_text": "findings"},
            get_settings=lambda: {"enabled": "true"},
        )
        panel._evidence_payload = {
            "conclusion": "Critical path: Low[266]",
            "next_steps": [{
                "label": "Inspect core-pair migrations",
                "prompt": "Inspect Core-Pair Migration Summary in the current scope.",
                "kind": "statistics",
            }],
        }
        panel._complete_final_assistant_reply("")
        log = panel._log.toPlainText()
        self.assertIn("Critical path: Low[266]", log)
        self.assertIn("Inspect core-pair migrations", log)

    def test_empty_final_reply_without_rich_evidence_still_shows_wrap_up(self) -> None:
        """Tools + Evidence with a thin payload must not leave the AI log blank."""
        panel = create_ai_assistant_panel(
            None,
            get_context=lambda: {"findings_text": "findings"},
            get_settings=lambda: {"enabled": "true"},
        )
        panel._evidence_payload = {"confidence": "Medium"}
        panel._complete_final_assistant_reply("")
        log = panel._log.toPlainText()
        self.assertTrue(log.strip(), "expected a synthesized assistant wrap-up")
        self.assertIn("Evidence", log)

    def test_empty_model_reply_after_tools_skips_error_bubble(self) -> None:
        panel = create_ai_assistant_panel(
            None,
            get_context=lambda: {"findings_text": "findings"},
            get_settings=lambda: {"enabled": "true"},
        )
        panel._evidence_payload = {
            "conclusion": "Critical path: Low[266]",
            "evidence": [{"label": "Blocked / off-CPU: wait", "time": 3100477}],
        }
        panel._on_err(
            "The model returned an empty assistant message (finish reason=stop)."
        )
        log = panel._log.toPlainText()
        self.assertIn("Critical path: Low[266]", log)
        self.assertIn("Blocked / off-CPU: wait", log)
        self.assertNotIn("(Error)", log)

    def test_casual_reply_without_case_is_shown(self) -> None:
        panel = self._panel()
        panel._on_ok(json.dumps({
            "content": "Hello.",
            "tool_calls": [],
        }))
        self.assertIn("Hello.", panel._log.toPlainText())

    def test_remaining_findings_next_check_gets_run_link(self) -> None:
        findings = [
            {"id": "priority_inversion", "title": "Priority inversion",
             "severity": "warning", "task": "Low[266]"},
            {"id": "thrashing", "title": "Excessive core migration",
             "severity": "warning"},
        ]
        panel = create_ai_assistant_panel(
            None,
            get_context=lambda: {"findings_text": "findings", "findings": findings},
            get_settings=lambda: {"enabled": "true"},
        )
        panel._last_analysis_findings = findings
        panel._active_template_id = "auto_investigate"
        panel._tool_round = 8
        panel._evidence_payload = {
            "conclusion": "Mutex stall",
            "coverage": {"percent": 90},
            "confidence": "high",
            "finding": {"id": "mutex", "title": "Mutex stall"},
        }
        panel._on_ok(json.dumps({
            "content": (
                "Remaining Findings (Title + Next Check)\n"
                "**Priority inversion (id=priority_inversion)**\n"
                "Title: Priority inversion (L/M/H) suspected for Low[266] and PS[228].\n"
                "nextstep:{Inspect Priority Inheritance boost episodes.}\n"
                "**Excessive core migration (id=thrashing)**\n"
                "Title: Excessive core migration for CS[20].\n"
                "Next check: Open Core Migrations.\n"
            ),
            "tool_calls": [],
        }))
        log = panel._log.toHtml()
        self.assertIn("btfnext:text/0", log)
        self.assertIn("btfstats:section/priority", log)
        self.assertIn('href="btfstats:section/priority"', log)
        self.assertIn("Open Core Migrations.", panel._log.toPlainText())
        self.assertNotIn("nextstep:", panel._log.toPlainText())
        steps = (panel._evidence_payload or {}).get("next_steps") or []
        self.assertTrue(steps)
        self.assertTrue(any("priority_inversion" in str(s.get("prompt") or "") for s in steps))

    def test_remaining_findings_prose_without_tags_gets_host_nextsteps(self) -> None:
        """Host appends nextstep tags when Remaining Findings lack them."""
        findings = [
            {"id": "blocking", "title": "Off-CPU / scheduling-delay candidates",
             "severity": "warning", "task": "Med[267]"},
            {"id": "thrashing", "title": "Excessive core migration",
             "severity": "warning", "task": "CS[20]"},
            {"id": "wcet_anomaly", "title": "Anomaly: WCET spike",
             "severity": "warning"},
        ]
        panel = create_ai_assistant_panel(
            None,
            get_context=lambda: {"findings_text": "findings", "findings": findings},
            get_settings=lambda: {"enabled": "true"},
        )
        panel._last_analysis_findings = findings
        panel._evidence_payload = {
            "conclusion": "Mutex stall",
            "coverage": {"percent": 90},
            "confidence": "high",
            "finding": {"id": "mutex", "title": "Mutex stall"},
        }
        panel._on_ok(json.dumps({
            "content": (
                "其他尚待處理的發現 (Remaining Findings)\n"
                "[WARNING] Off-CPU (id=blocking)：建議調查 Med[267]。\n"
                "[WARNING] Excessive core migration (id=thrashing)：建議調查。\n"
                "[WARNING] Anomaly: WCET spike (id=wcet_anomaly)：建議調查。\n"
            ),
            "tool_calls": [],
        }))
        log = panel._log.toHtml()
        self.assertIn("btfnext:text/0", log)
        self.assertIn("btfnext:text/1", log)
        self.assertIn("btfnext:text/2", log)
        self.assertNotIn("nextstep:", panel._log.toPlainText())

    def test_remaining_findings_two_nextsteps_get_run_links(self) -> None:
        """Two nextstep:{action} lines each get a conversation [Run]."""
        findings = [
            {"id": "priority_inversion", "title": "Priority inversion",
             "severity": "warning", "task": "Low[266]"},
            {"id": "thrashing", "title": "Excessive core migration",
             "severity": "warning"},
        ]
        panel = create_ai_assistant_panel(
            None,
            get_context=lambda: {"findings_text": "findings", "findings": findings},
            get_settings=lambda: {"enabled": "true"},
        )
        panel._last_analysis_findings = findings
        panel._evidence_payload = {
            "conclusion": "Mutex stall",
            "coverage": {"percent": 90},
            "confidence": "high",
            "finding": {"id": "mutex", "title": "Mutex stall"},
        }
        remaining = (
            "Remaining Findings\n"
            "**Priority inversion (id=priority_inversion)**\n"
            "Title: Priority inversion (L/M/H) suspected for Low[266] "
            "and PS[228].\n"
            "nextstep:{Inspect Priority Inheritance boost episodes "
            "and holding mutexes in the Mutex Blocking statistics page.}\n"
            "**Excessive core migration (id=thrashing)**\n"
            "Title: Excessive core migration for tasks such as CS[20].\n"
            "nextstep:{Inspect Core-Pair Migration Summary and Dwell Time "
            "distribution.}\n"
        )
        panel._on_ok(json.dumps({
            "content": remaining,
            "tool_calls": [],
        }))
        log = panel._log.toHtml()
        self.assertIn("btfnext:text/0", log)
        self.assertIn("btfnext:text/1", log)
        self.assertIn("btfstats:section/priority", log)
        self.assertIn("btfstats:section/migrations", log)
        self.assertIn('href="btfnext:text/0"', log)
        self.assertIn("Run Open Statistics", panel._log.toPlainText())

    def test_quick_mode_sends_without_interpret_gate(self) -> None:
        panel = self._panel()
        with patch.object(panel, "_send_query") as send, patch(
            "btf_viewer_pkg.ai_assistant.interpret_investigation_query",
        ) as interp:
            panel._run_investigation_mode("quick")
        send.assert_called_once()
        interp.assert_not_called()
        self.assertFalse(panel._skip_interpret)
        query = send.call_args[0][0]
        self.assertIn("Preferred tools", query)
        self.assertIn("detect_anomalies", query)
        self.assertNotIn("Call these tools in order", query)
        self.assertIn("detect_anomalies", query)

    def test_investigation_template_sends_without_interpret_gate(self) -> None:
        from btf_viewer_pkg.ai_case import builtin_investigation_templates

        panel = self._panel()
        tpl = builtin_investigation_templates()[0]
        with patch.object(panel, "_send_query") as send, patch(
            "btf_viewer_pkg.ai_assistant.interpret_investigation_query",
        ) as interp:
            panel._run_investigation_template(tpl)
        send.assert_called_once()
        interp.assert_not_called()

    def test_template_ux_busy_disables_chips_and_investigations(self) -> None:
        from btf_viewer_pkg.ai_assistant import AI_TEMPLATE_MENU_GROUPS
        from btf_viewer_pkg.ai_case import builtin_investigation_templates

        panel = self._panel()
        self.assertEqual(panel._mode_btns, [])
        self.assertEqual(
            list(panel._template_actions),
            [tid for _g, ids in AI_TEMPLATE_MENU_GROUPS for tid in ids],
        )
        self.assertEqual(
            list(panel._investigation_template_actions),
            [t["id"] for t in builtin_investigation_templates()],
        )
        self.assertEqual(
            [b.text().replace("&", "") for b in panel._template_btns],
            [
                next(lab for tid, lab, _p in AI_TEMPLATE_QUESTIONS if tid == pid)
                for pid in visible_ai_templates(recent=[], usage={})
            ],
        )
        panel._set_busy(True)
        self.assertFalse(panel._template_btns[0].isEnabled())
        inv_act = next(iter(panel._investigation_template_actions.values()))
        self.assertFalse(inv_act.isEnabled())
        self.assertFalse(panel._save_investigation_template_action.isEnabled())
        panel._set_busy(False)
        self.assertTrue(panel._template_btns[0].isEnabled())
        self.assertTrue(inv_act.isEnabled())
        self.assertTrue(panel._save_investigation_template_action.isEnabled())

    def test_template_chips_wrap_like_web(self) -> None:
        from PySide6.QtWidgets import QSizePolicy

        from btf_viewer_pkg.view import _in_ai_actions_bar, _relax_widget_tree

        panel = self._panel()
        self.assertIsNone(panel.findChild(QWidget, "aiModes"))
        tpls = panel.findChild(QWidget, "aiTemplates")
        self.assertTrue(tpls.layout().hasHeightForWidth())
        # One row at normal width; may wrap to two at narrow width.
        tpl_h_wide = tpls.layout().heightForWidth(800)
        tpl_h_narrow = tpls.layout().heightForWidth(180)
        self.assertLessEqual(tpl_h_wide, 40)
        self.assertGreaterEqual(tpl_h_narrow, tpl_h_wide)

        headings = [
            "Start", "Investigate", "SMP", "Compare",
            "What-if / Optimize", "Investigations", "Knowledge",
        ]
        labels = [
            w.text() for w in panel._more_menu.findChildren(QLabel)
            if w.objectName() == "aiMoreHeading"
        ]
        self.assertEqual(labels, headings)
        for btn in panel._more_menu.findChildren(QPushButton):
            if btn.objectName() == "aiMoreItem":
                self.assertTrue(btn.text().replace("&", "").strip(), btn.objectName())
        for lab in panel._more_menu.findChildren(QLabel):
            if lab.objectName() == "aiMoreHeading":
                self.assertTrue(lab.isEnabled(), lab.text())
        grid = panel._more_menu.findChild(QGridLayout)
        self.assertIsNotNone(grid)
        self.assertEqual(grid.columnCount(), 2)
        self.assertIsNone(panel._more_menu.findChild(QScrollArea))
        panel._place_more_menu()
        self.assertEqual(panel._more_menu.height(), panel._more_menu.sizeHint().height())
        self.assertGreater(panel._more_menu.height(), 200)

        _relax_widget_tree(panel)
        for btn in panel._template_btns:
            self.assertTrue(_in_ai_actions_bar(btn), btn.text())
            self.assertNotEqual(
                btn.sizePolicy().horizontalPolicy(),
                QSizePolicy.Policy.Ignored,
                btn.text(),
            )
        for sid, btn in panel._guide_step_btns.items():
            self.assertTrue(_in_ai_actions_bar(btn), sid)
            self.assertNotEqual(
                btn.sizePolicy().horizontalPolicy(),
                QSizePolicy.Policy.Ignored,
                sid,
            )
            self.assertGreater(btn.sizeHint().width(), 8, sid)
        self.assertTrue(_in_ai_actions_bar(panel._auth_chip))
        self.assertTrue(_in_ai_actions_bar(panel._privacy_chip))
        for chip in (panel._auth_chip, panel._privacy_chip):
            self.assertNotEqual(
                chip.sizePolicy().horizontalPolicy(),
                QSizePolicy.Policy.Ignored,
                chip.objectName(),
            )
            self.assertGreater(chip.sizeHint().width(), 20, chip.text())

    def test_status_shows_accumulated_cost_until_clear(self) -> None:
        from btf_viewer_pkg.ai_case import accumulate_cost, empty_cost_meter

        panel = self._panel()
        panel._set_status("Done.")
        self.assertEqual(panel._status.text(), "Done.")
        panel._cost_meter = accumulate_cost(
            empty_cost_meter(),
            prompt_tokens=1000,
            completion_tokens=200,
            tool_calls=2,
            model_time_s=1.5,
        )
        panel._set_status("Done.")
        self.assertEqual(panel._status.text(), "Done.")
        self.assertIn("Context: Balanced", panel._usage.text())
        self.assertIn("1.2k tok", panel._usage.text())
        self.assertIn("2 tools", panel._usage.text())
        self.assertIn("1.5s", panel._usage.text())
        panel._record_turn_usage(
            {"usage": {"prompt_tokens": 50, "completion_tokens": 10}},
            [],
        )
        panel._set_status("Done.")
        self.assertIn("1.3k tok", panel._usage.text())
        self.assertIn("2 tools", panel._usage.text())
        self.assertIn("1.5s", panel._usage.text())
        self.assertNotIn("input", panel._usage.text())
        self.assertNotIn("output", panel._usage.text())
        cfg = {"enabled": "true", "context_mode": "compact"}
        panel2 = create_ai_assistant_panel(
            None,
            get_context=lambda: {"findings_text": "findings"},
            get_settings=lambda: cfg,
        )
        self.addCleanup(panel2.deleteLater)
        panel2._cost_meter = dict(panel._cost_meter)
        panel2._refresh_usage()
        self.assertIn("Context: Compact", panel2._usage.text())
        self.assertIn("1.3k tok", panel2._usage.text())
        self.assertNotIn("input", panel2._usage.text())
        cfg["context_mode"] = "balanced"
        panel2._refresh_usage()
        self.assertIn("Context: Balanced", panel2._usage.text())
        self.assertIn("1.3k tok", panel2._usage.text())
        self.assertIn("2 tools", panel2._usage.text())
        self.assertIn("1.5s", panel2._usage.text())
        self.assertNotIn("input", panel2._usage.text())
        self.assertEqual(panel._status.text(), "Done.")
        panel.clear_conversation()
        self.assertEqual(panel._status.text(), "")
        self.assertEqual(panel._cost_meter["total_tokens"], 0)
        self.assertEqual(panel._cost_meter["tool_calls"], 0)
        self.assertEqual(panel._usage.text(), "Context: Balanced")
        self.assertFalse(panel._entries)
        self.assertEqual(panel._log.toPlainText().strip(), "")
        panel._append("assistant", "A long model reply")
        panel._evidence_payload = {"finding": {"title": "Queue bounce"}}
        panel.clear_conversation()
        self.assertFalse(panel._entries)
        self.assertEqual(panel._log.toPlainText().strip(), "")
        self.assertIsNone(panel._evidence_payload)
        self.assertEqual(panel._usage.text(), "Context: Balanced")

    def test_log_composer_splitter_exists(self) -> None:
        from btf_viewer_pkg.ai_assistant import _AiSplitHandle

        panel = self._panel()
        self.assertEqual(panel._split.objectName(), "aiSplit")
        self.assertEqual(panel._split_bottom.objectName(), "aiSplitBottom")
        self.assertEqual(panel._split.handleWidth(), 8)
        handle = panel._split.handle(1)
        self.assertIsInstance(handle, _AiSplitHandle)
        self.assertEqual(panel._usage.objectName(), "aiUsageBar")
        self.assertEqual(panel._usage.text(), "Context: Balanced")

    def test_disabled_template_chips_use_muted_color(self) -> None:
        from btf_viewer_pkg.ai_assistant import (
            _AI_MORE_MENU_STYLE, _AI_TPL_BTN_STYLE, _AI_TPL_DISABLED_COLOR,
        )

        panel = self._panel()
        self.assertEqual(_AI_TPL_DISABLED_COLOR, "#8a96a8")
        self.assertIn("QPushButton:disabled", _AI_TPL_BTN_STYLE)
        self.assertIn(_AI_TPL_DISABLED_COLOR, _AI_TPL_BTN_STYLE)
        self.assertIn("QPushButton#aiMoreItem:disabled", _AI_MORE_MENU_STYLE)
        self.assertIn(_AI_TPL_DISABLED_COLOR, _AI_MORE_MENU_STYLE)
        self.assertIn("background: #1a2230", _AI_MORE_MENU_STYLE)
        self.assertNotIn("background: transparent", _AI_MORE_MENU_STYLE)
        from btf_viewer_pkg.ai_assistant import _ai_more_menu_style
        light = _ai_more_menu_style(False)
        self.assertIn("background: #F5F5F5", light)
        self.assertNotIn("background: #1a2230", light)
        panel.apply_theme(False)
        self.assertIn("background: #F5F5F5", panel._more_menu.styleSheet())
        item = panel._more_menu.findChild(QPushButton, "aiMoreItem")
        self.assertIsNotNone(item)
        self.assertIn("background: #F5F5F5", item.styleSheet())
        heading = panel._more_menu.findChild(QLabel, "aiMoreHeading")
        self.assertIsNotNone(heading)
        self.assertTrue(heading.isEnabled())
        self.assertIn("background: #F5F5F5", heading.styleSheet())
        self.assertIn("color: #666666", heading.styleSheet())
        panel._append("user", "theme prompt")
        panel._append("assistant", "theme reply")
        html = panel._log.toHtml().lower()
        self.assertIn("#e8f1fa", html)
        self.assertIn("#e8f6ee", html)
        self.assertNotIn("#1a2620", html)
        panel.apply_theme(True)
        self.assertIsNone(panel.findChild(QWidget, "aiModes"))
        tpls = panel.findChild(QWidget, "aiTemplates")
        self.assertIn(_AI_TPL_DISABLED_COLOR, tpls.styleSheet())
        self.assertIn(_AI_TPL_DISABLED_COLOR, panel._more_menu.styleSheet())
        for btn in panel._template_btns:
            self.assertEqual(btn.minimumHeight(), 28, btn.text())
        more = next(
            b for b in panel.findChildren(QPushButton)
            if b.text().replace("&", "") == "More…"
        )
        self.assertEqual(more.minimumHeight(), 28)


if __name__ == "__main__":
    unittest.main()
