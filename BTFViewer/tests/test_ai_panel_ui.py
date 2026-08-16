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

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from unittest.mock import patch  # noqa: E402

from PySide6.QtCore import QPoint, QUrl  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QGridLayout, QLabel, QMainWindow, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from btf_viewer_pkg.ai_assistant import (  # noqa: E402
    AI_TEMPLATE_MENU_GROUPS,
    AI_TEMPLATE_PRIMARY_IDS,
    AI_TEMPLATE_QUESTIONS,
    ai_entry_role,
    ai_entry_text,
    _MermaidZoomDialog,
    _qtextline_cursor_x,
    create_ai_assistant_panel,
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
    AI_TOOL_INVESTIGATION_REPLAY,
    AI_TOOL_INTERPRET_QUERY,
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
    AI_TOOL_SCORE_INVESTIGATION,
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
)


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class AiPanelUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _app()

    def _panel(self):
        return create_ai_assistant_panel(
            None,
            get_context=lambda: {"findings_text": "findings"},
            get_settings=lambda: {"enabled": "true"},
        )

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
        panel._input.setPlainText("why is CS[22] late?")
        self.assertTrue(panel._send_btn.isEnabled())
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

        panel = self._panel()
        self.assertEqual(panel._start_inv_btn.text(), "Start Investigation")
        self.assertFalse(panel._start_inv_btn.isHidden())
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
        self.assertIn("Investigate", panel._guide_step_btns["investigate"].text())
        self.assertIn("#1E1E1E", panel._guide_step_btns["investigate"].styleSheet())
        self.assertIn("Queue bounce", panel._issue_view.text())

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
        self.assertIn("core thrashing", prompt)
        self.assertIn("lock-bounce", prompt)

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
            "content": "Placing cursors.",
            "tool_calls": [{
                "id": "c1",
                "name": "set_cursors",
                "arguments": {"timestamps": [10.0, 20.0]},
            }],
            "message": {"role": "assistant", "content": "Placing cursors."},
        }))
        # In-log Apply/Skip cards are the primary chrome; the under-log bar
        # stays hidden when those cards exist.
        self.assertTrue(panel._tool_bar.isHidden())
        with patch.object(panel, "_continue_with_messages"):
            panel._on_jump_link(QUrl("btfaction:apply/b1"))
        self.assertEqual(len(executed), 1)
        self.assertEqual(executed[0][0]["name"], "set_cursors")
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
                "name": "highlight_task",
                "arguments": {"task_name_or_id": "Low[266]"},
            }],
        }))
        # Legacy colon hrefs must still Apply (QTextBrowser used to truncate them).
        with patch.object(panel2, "_continue_with_messages"):
            panel2._on_jump_link(QUrl("btfaction:apply:b1"))
        self.assertEqual(executed[-1][0]["name"], "highlight_task")

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
                {"id": "c22", "name": AI_TOOL_INVESTIGATION_REPLAY,
                 "arguments": {"finding_id": "x"}},
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
                {"id": "c46", "name": AI_TOOL_SCORE_INVESTIGATION,
                 "arguments": {"conclusion": "migration thrash"}},
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
        self.assertIs(panel._log.parentWidget(), panel._split_top)
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

    def test_primary_chips_and_more_menu_cover_all_templates(self) -> None:
        panel = self._panel()
        primary_labels = [b.text() for b in panel._template_btns]
        expected_primary = [
            next(lab for tid, lab, _p in AI_TEMPLATE_QUESTIONS if tid == pid)
            for pid in AI_TEMPLATE_PRIMARY_IDS
        ]
        self.assertEqual(primary_labels, expected_primary)
        from PySide6.QtWidgets import QWidget
        tpl = panel.findChild(QWidget, "aiTemplates")
        self.assertIsNotNone(tpl)
        more = [
            b.text() for b in tpl.findChildren(QPushButton)
            if b.text().startswith("More templates")
        ]
        self.assertEqual(len(more), 1)
        self.assertEqual(
            panel._template_btns[-1].text().replace("&", ""),
            "Auto investigate",
        )
        self.assertEqual(panel._more_btn.text().replace("&", ""), "More templates…")
        menu_ids = [tid for _g, ids in AI_TEMPLATE_MENU_GROUPS for tid in ids]
        self.assertEqual(set(panel._template_actions), set(menu_ids))
        reachable = set(AI_TEMPLATE_PRIMARY_IDS) | set(panel._template_actions)
        self.assertEqual(reachable, {t[0] for t in AI_TEMPLATE_QUESTIONS})
        self.assertEqual(len(reachable), 20)

    def test_template_tooltips_wrap_for_qt(self) -> None:
        from btf_viewer_pkg.ai_assistant import qt_wrap_tooltip

        long_tip = (
            "Walk through the Analysis Findings in the context. For each finding, "
            "state its severity, what it means for this RTOS/SMP system, and which "
            "Statistics section or timeline check to open next."
        )
        wrapped = qt_wrap_tooltip(long_tip)
        self.assertTrue(wrapped.startswith("<html>"))
        self.assertIn('width="320"', wrapped)
        # One paragraph: no forced <br/> (Qt wraps on words inside the cell).
        self.assertNotIn("<br/>", wrapped)
        self.assertIn("finding,", wrapped)
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
        self.assertIn("证据 / 推理", html)
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

    def test_investigation_mode_chips_and_hypothesis_links(self) -> None:
        from btf_viewer_pkg.ai_case import enrich_hypotheses

        panel = self._panel()
        host = panel.findChild(QWidget, "aiModes")
        self.assertIsNotNone(host)
        labels = [b.text().replace("&", "") for b in host.findChildren(QPushButton)]
        self.assertEqual(
            labels[:5],
            ["Quick", "Diagnose", "Compare", "Optimize", "Report"],
        )
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
        self.assertIn("Call these tools in order", query)
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

    def test_template_ux_busy_disables_modes_and_investigations(self) -> None:
        from btf_viewer_pkg.ai_assistant import (
            AI_TEMPLATE_MENU_GROUPS, AI_TEMPLATE_PRIMARY_IDS,
        )
        from btf_viewer_pkg.ai_case import (
            INVESTIGATION_MODE_LABELS, INVESTIGATION_MODES,
            builtin_investigation_templates,
        )

        panel = self._panel()
        self.assertEqual(
            [b.text().replace("&", "") for b in panel._mode_btns],
            [INVESTIGATION_MODE_LABELS[m] for m in INVESTIGATION_MODES],
        )
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
                for pid in AI_TEMPLATE_PRIMARY_IDS
            ],
        )
        panel._set_busy(True)
        self.assertFalse(panel._mode_btns[0].isEnabled())
        self.assertFalse(panel._template_btns[0].isEnabled())
        inv_act = next(iter(panel._investigation_template_actions.values()))
        self.assertFalse(inv_act.isEnabled())
        self.assertFalse(panel._save_investigation_template_action.isEnabled())
        panel._set_busy(False)
        self.assertTrue(panel._mode_btns[0].isEnabled())
        self.assertTrue(panel._template_btns[0].isEnabled())
        self.assertTrue(inv_act.isEnabled())
        self.assertTrue(panel._save_investigation_template_action.isEnabled())

    def test_mode_and_template_chips_wrap_like_web(self) -> None:
        from PySide6.QtWidgets import QSizePolicy

        from btf_viewer_pkg.view import _in_ai_actions_bar, _relax_widget_tree

        panel = self._panel()
        modes = panel.findChild(QWidget, "aiModes")
        tpls = panel.findChild(QWidget, "aiTemplates")
        self.assertTrue(modes.layout().hasHeightForWidth())
        self.assertTrue(tpls.layout().hasHeightForWidth())
        mode_h_wide = modes.layout().heightForWidth(800)
        mode_h_narrow = modes.layout().heightForWidth(180)
        self.assertGreater(mode_h_narrow, mode_h_wide)
        # Forced wrap: Auto investigate + More stay on the last row even when wide.
        self.assertGreaterEqual(tpls.layout().heightForWidth(800), 56)
        tpl_h_wide = tpls.layout().heightForWidth(800)
        tpl_h_narrow = tpls.layout().heightForWidth(180)
        self.assertGreater(tpl_h_narrow, tpl_h_wide)

        headings = [
            "Diagnose", "Compare", "Metrics", "What-if / Optimize",
            "Investigations", "Knowledge",
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
        for btn in panel._mode_btns + panel._template_btns:
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
        self.assertIn("1.2k tok", panel._usage.text())
        self.assertIn("2 tools", panel._usage.text())
        self.assertIn("1.5s", panel._usage.text())
        panel._record_turn_usage(
            {"usage": {"prompt_tokens": 50, "completion_tokens": 10}},
            [],
        )
        panel._set_status("Done.")
        self.assertIn("1.3k tok", panel._usage.text())
        self.assertEqual(panel._status.text(), "Done.")
        panel.clear_conversation()
        self.assertEqual(panel._status.text(), "")
        self.assertEqual(panel._cost_meter["total_tokens"], 1260)
        self.assertEqual(panel._cost_meter["tool_calls"], 2)
        self.assertIn("1.3k tok", panel._usage.text())
        self.assertFalse(panel._entries)
        self.assertEqual(panel._log.toPlainText().strip(), "")
        panel._append("assistant", "A long model reply")
        panel._evidence_payload = {"finding": {"title": "Queue bounce"}}
        panel.clear_conversation()
        self.assertFalse(panel._entries)
        self.assertEqual(panel._log.toPlainText().strip(), "")
        self.assertEqual(panel._evidence_payload["finding"]["title"], "Queue bounce")
        self.assertIn("1.3k tok", panel._usage.text())

    def test_log_composer_splitter_exists(self) -> None:
        panel = self._panel()
        self.assertEqual(panel._split.objectName(), "aiSplit")
        self.assertEqual(panel._split_bottom.objectName(), "aiSplitBottom")
        self.assertEqual(panel._usage.objectName(), "aiUsageBar")
        self.assertIn("0 tok", panel._usage.text())

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
        modes = panel.findChild(QWidget, "aiModes")
        tpls = panel.findChild(QWidget, "aiTemplates")
        self.assertIn(_AI_TPL_DISABLED_COLOR, modes.styleSheet())
        self.assertIn(_AI_TPL_DISABLED_COLOR, tpls.styleSheet())
        self.assertIn(_AI_TPL_DISABLED_COLOR, panel._more_menu.styleSheet())
        for btn in panel._mode_btns + panel._template_btns:
            self.assertEqual(btn.minimumHeight(), 28, btn.text())
        more = next(
            b for b in panel.findChildren(QPushButton)
            if b.text().replace("&", "") == "More templates…"
        )
        self.assertEqual(more.minimumHeight(), 28)


if __name__ == "__main__":
    unittest.main()
