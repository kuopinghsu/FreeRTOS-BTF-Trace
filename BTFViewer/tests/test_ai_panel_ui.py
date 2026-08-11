"""AI panel widget behaviour that must match web/src/components/AiAssistantPanel.vue."""
from __future__ import annotations

import json
import os
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
from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.ai_assistant import (  # noqa: E402
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
    AI_TOOL_EXPORT_INVESTIGATION,
    AI_TOOL_EXPORT_REPORT,
    AI_TOOL_FIND_CRITICAL_PATH,
    AI_TOOL_FIND_RELATED_FINDINGS,
    AI_TOOL_GENERATE_REPORT,
    AI_TOOL_INVESTIGATE,
    AI_TOOL_INVESTIGATION_REPLAY,
    AI_TOOL_OPTIMIZE,
    AI_TOOL_OPTIMIZE_EXPERIMENT,
    AI_TOOL_QUERY_RAW_METRIC,
    AI_TOOL_RECOMMEND_EXPERIMENTS,
    AI_TOOL_REGRESSION_EXPLAIN,
    AI_TOOL_RESET_VIEW,
    AI_TOOL_SEARCH_TIMELINE,
    AI_TOOL_TRIGGER_COMPARE,
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
        """Ask stays disabled until the box has text (web parity)."""
        panel = self._panel()
        self.assertTrue(hasattr(panel, "_auth_chip"))
        self.assertIn("·", panel._auth_chip.text())
        self.assertFalse(panel._send_btn.isEnabled())
        panel._input.setPlainText("why is CS[22] late?")
        self.assertTrue(panel._send_btn.isEnabled())
        panel._input.setPlainText("   ")
        self.assertFalse(panel._send_btn.isEnabled())

    def test_auth_forced_keeps_cta_after_401(self) -> None:
        """401 CTAs stay until a successful turn (web authForced parity)."""
        panel = self._panel()
        self.assertFalse(panel._auth_forced)
        self.assertTrue(panel._auth_cta.isHidden())
        panel._on_err(
            "OpenAI-compatible HTTP 401 at https://api.openai.com/v1/"
            "chat/completions: unauthorized")
        self.assertTrue(panel._auth_forced)
        self.assertFalse(panel._auth_cta.isHidden())
        self.assertFalse(panel._auth_cta_signin.isHidden())
        panel._on_ok(json.dumps({"content": "ok", "tool_calls": []}))
        self.assertFalse(panel._auth_forced)
        self.assertTrue(panel._auth_cta.isHidden())
        self.assertIn("ok", panel._log.toPlainText())

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
        self.assertFalse(panel._tool_bar.isHidden())
        self.assertFalse(panel._apply_tools_btn.isHidden())
        self.assertFalse(panel._skip_tools_btn.isHidden())
        with patch.object(panel, "_continue_with_messages"):
            panel._on_jump_link(QUrl("btfaction:apply/b1"))
        self.assertEqual(len(executed), 1)
        self.assertEqual(executed[0][0]["name"], "set_cursors")
        self.assertFalse(panel._undo_tools_btn.isHidden())
        self.assertTrue(panel._apply_tools_btn.isHidden())

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


if __name__ == "__main__":
    unittest.main()
