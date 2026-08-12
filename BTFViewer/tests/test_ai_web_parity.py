"""Desktop ↔ web AI constants and call-site parity."""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg.ai_assistant import (  # noqa: E402
    AI_CHAT_TIMEOUT_S,
    AI_LIST_MODELS_TIMEOUT_S,
    AI_SYSTEM_PROMPT,
    AI_TEST_TIMEOUT_S,
    ASK_EVENT_PROMPT,
)
from btf_viewer_pkg.ai_tools import (  # noqa: E402
    AI_RAW_METRIC_NAMES,
    AI_TOOL_ADD_ANNOTATION,
    AI_TOOL_EXPORT_REPORT,
    AI_TOOL_OPTIMIZE_EXPERIMENT,
    AI_TOOL_QUERY_RAW_METRIC,
    AI_TOOL_SYSTEM_ADDENDUM,
    AI_TOOL_WHAT_IF,
    AI_VIEWER_TOOL_NAMES,
    GEMINI_SKIP_THOUGHT_SIGNATURE,
    ai_viewer_tools,
    is_query_tool,
    max_tool_rounds,
    parse_tool_calls_from_text,
    strip_parsed_tool_markup,
)


class AiWebParityTests(unittest.TestCase):
    def test_response_languages_and_evidence_labels_match_web(self) -> None:
        """Language picker + evidence chrome keys stay Desktop/Web aligned."""
        from btf_viewer_pkg.ai_assistant import AI_RESPONSE_LANGUAGES
        from btf_viewer_pkg.ai_investigation import EVIDENCE_PANEL_LABELS

        ollama = (BTF_ROOT / "web/src/utils/ollamaClient.js").read_text(
            encoding="utf-8")
        inv_js = (BTF_ROOT / "web/src/utils/aiInvestigation.js").read_text(
            encoding="utf-8")
        block = re.search(
            r"export const AI_RESPONSE_LANGUAGES = \[([\s\S]*?)\]\n", ollama)
        self.assertIsNotNone(block)
        js_langs = tuple(re.findall(r"'([^']+)'", block.group(1)))
        self.assertEqual(js_langs, AI_RESPONSE_LANGUAGES)
        self.assertEqual(set(EVIDENCE_PANEL_LABELS), set(AI_RESPONSE_LANGUAGES))
        for lang in AI_RESPONSE_LANGUAGES:
            self.assertIn(lang, inv_js)
        self.assertNotIn("Klingon", "".join(AI_RESPONSE_LANGUAGES))
        self.assertNotIn("Klingon", inv_js)
        self.assertNotIn("Klingon", ollama)
        for key in (
            "role", "evidence", "confidence", "score", "investigation",
            "high", "medium", "low",
        ):
            for labels in EVIDENCE_PANEL_LABELS.values():
                self.assertIn(key, labels)

    def test_timeouts_match_web(self) -> None:
        js = (BTF_ROOT / "web/src/utils/ollamaClient.js").read_text(encoding="utf-8")
        self.assertIn(f"AI_CHAT_TIMEOUT_MS = {int(AI_CHAT_TIMEOUT_S * 1000)}", js)
        self.assertIn(
            f"AI_LIST_MODELS_TIMEOUT_MS = {int(AI_LIST_MODELS_TIMEOUT_S * 1000)}", js)
        self.assertIn(f"AI_TEST_TIMEOUT_MS = {int(AI_TEST_TIMEOUT_S * 1000)}", js)
        self.assertEqual(AI_CHAT_TIMEOUT_S, 120.0)
        self.assertEqual(AI_LIST_MODELS_TIMEOUT_S, 12.0)
        self.assertEqual(AI_TEST_TIMEOUT_S, 120.0)

    def test_tool_rounds_match_web(self) -> None:
        js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        self.assertRegex(js, rf"MAX_TOOL_ROUNDS\s*=\s*{max_tool_rounds()}")
        self.assertEqual(max_tool_rounds(), 4)

    def test_btftool_ndjson_and_ask_event_match_web(self) -> None:
        """Text-tool fences + Ask-event prompt stay aligned with the web client."""
        js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        ollama = (BTF_ROOT / "web/src/utils/ollamaClient.js").read_text(
            encoding="utf-8")
        clause = "one object, a JSON array, or several objects"
        self.assertIn(clause, AI_TOOL_SYSTEM_ADDENDUM)
        self.assertIn(clause, js)
        self.assertIn("function loadsJsonValues", js)
        self.assertIn("def _loads_json_values", (
            BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8"))
        self.assertIn("if (textCalls.length) content = stripParsedToolMarkup", ollama)
        self.assertIn("ASK_EVENT_PROMPT", ollama)
        self.assertIn(ASK_EVENT_PROMPT.split("{task}")[0], ollama)
        self.assertIn("Call correlate_events and query_raw_metric", ollama)
        # NDJSON fence (same shape that previously leaked raw JSON in chat)
        text = (
            "Focusing the segment.\n"
            "```btftool\n"
            '{"name": "set_cursors", "arguments": {"timestamps": [1036516, 1036826]}}\n'
            '{"name": "highlight_task", "arguments": {"task_name_or_id": "CS[24]"}}\n'
            '{"name": "zoom_to_range", "arguments": '
            '{"start_time": 1036400, "end_time": 1037000}}\n'
            "```\n"
        )
        names = [c["name"] for c in parse_tool_calls_from_text(text)]
        self.assertEqual(
            names, ["set_cursors", "highlight_task", "zoom_to_range"])
        stripped = strip_parsed_tool_markup(text)
        self.assertNotIn("btftool", stripped)
        self.assertIn("Focusing the segment.", stripped)

    def test_viewer_tool_names_and_query_set_match_web(self) -> None:
        """Desktop AI_VIEWER_TOOL_NAMES / is_query_tool stay aligned with web."""
        js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        const_map = dict(re.findall(
            r"export const (AI_TOOL_\w+) = '([^']+)'", js))
        block = re.search(
            r"export const AI_VIEWER_TOOL_NAMES = \[([\s\S]*?)\]\n", js)
        self.assertIsNotNone(block)
        js_names = tuple(
            const_map[c] for c in re.findall(r"AI_TOOL_\w+", block.group(1))
            if c in const_map
        )
        self.assertEqual(js_names, AI_VIEWER_TOOL_NAMES)
        schema_names = tuple(
            t["function"]["name"] for t in ai_viewer_tools()
        )
        self.assertEqual(schema_names, AI_VIEWER_TOOL_NAMES)
        self.assertIn(AI_TOOL_WHAT_IF, AI_VIEWER_TOOL_NAMES)
        self.assertIn(AI_TOOL_OPTIMIZE_EXPERIMENT, AI_VIEWER_TOOL_NAMES)
        self.assertTrue(is_query_tool(AI_TOOL_WHAT_IF))
        self.assertTrue(is_query_tool(AI_TOOL_OPTIMIZE_EXPERIMENT))
        self.assertIn("optimize_experiment", AI_TOOL_SYSTEM_ADDENDUM)
        self.assertIn("slice-replay", AI_TOOL_SYSTEM_ADDENDUM)
        self.assertIn("optimize_experiment", js)
        self.assertIn("slice-replay", js)
        # isQueryTool list on web includes the same query tools
        qm = re.search(r"export function isQueryTool\(name\) \{([\s\S]*?)\n\}", js)
        self.assertIsNotNone(qm)
        js_query = [
            const_map[c] for c in re.findall(r"AI_TOOL_\w+", qm.group(1))
            if c in const_map
        ]
        py_query = [n for n in AI_VIEWER_TOOL_NAMES if is_query_tool(n)]
        self.assertEqual(sorted(js_query), sorted(py_query))

    def test_investigation_helpers_and_findings_ui_match_web(self) -> None:
        inv_js = (BTF_ROOT / "web/src/utils/aiInvestigation.js").read_text(
            encoding="utf-8")
        inv_py = (BTF_ROOT / "btf_viewer_pkg/ai_investigation.py").read_text(
            encoding="utf-8")
        self.assertIn("INVESTIGATION_PLAN_STEPS", inv_js)
        self.assertIn("INVESTIGATION_PLAN_STEPS", inv_py)
        self.assertIn("'what_if'", inv_js)
        self.assertIn('"what_if"', inv_py)
        self.assertIn("optimize_experiment", inv_js)
        self.assertIn("optimize_experiment", inv_py)
        self.assertIn("simulateWhatIf", inv_js)
        self.assertIn("def simulate_what_if", inv_py)
        self.assertIn("runOptimizationExperiments", inv_js)
        self.assertIn("def run_optimization_experiments", inv_py)
        self.assertIn("buildInvestigateContext", inv_js)
        self.assertIn("def build_investigate_context", inv_py)
        self.assertIn("buildCriticalPath", inv_js)
        self.assertIn("def build_critical_path", inv_py)
        tools_js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        tools_py = (BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8")
        self.assertIn("find_critical_path", tools_js)
        self.assertIn("AI_TOOL_FIND_CRITICAL_PATH", tools_py)
        self.assertIn("evaluateRegression", inv_js)
        self.assertIn("def evaluate_regression", inv_py)
        dlg = (BTF_ROOT / "web/src/components/AnalysisFindingsDialog.vue").read_text(
            encoding="utf-8")
        stats = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
        self.assertIn("Investigate…", dlg)
        self.assertIn("Root cause…", dlg)
        self.assertIn("Investigate…", stats)
        self.assertIn("Root cause…", stats)
        self.assertIn("emit('query-ai', 'investigate')", dlg)
        # Desktop wires templates via _make_ai_btn(..., template) → _query_with_ai.
        self.assertRegex(
            stats,
            re.compile(
                r'_make_ai_btn\(\s*"Investigate…".*?"investigate"',
                re.DOTALL,
            ),
        )
        self.assertIn("self._query_with_ai(", stats)
        self.assertIn("wants_ai_template", stats)
        readme = (BTF_ROOT / "README.md").read_text(encoding="utf-8")
        ai_md = (BTF_ROOT / "AI.md").read_text(encoding="utf-8")
        self.assertIn("`analyze`", ai_md)
        self.assertIn("--fail-on-regression", ai_md)
        self.assertIn("**Triage findings**", readme)
        self.assertIn("Max≫Avg", readme)
        self.assertIn("Same panel on **Desktop** and **Web**", readme)
        self.assertIn("`what_if` / `optimize_experiment`", readme)
        self.assertIn("Heuristic slice-replay", readme)
        self.assertIn("Ranked `optimize_experiment`", readme)
        self.assertIn("not FreeRTOS kernel", readme)
        self.assertIn("`optimize_experiment`", ai_md)
        self.assertIn("slice-replay", ai_md)
        self.assertIn("Workflows and use cases", ai_md)
        self.assertIn("id=\"workflows-and-use-cases\"", ai_md)
        self.assertIn("id=\"what-if-and-optimize-workflow\"", ai_md)
        self.assertIn("id=\"use-cases\"", ai_md)
        self.assertIn("Simulator limits", ai_md)
        self.assertIn(
            "`clear_marks` / `reset_view` / `search_timeline` / "
            "`trigger_compare` / `investigate` / `detect_anomalies` / "
            "`correlate_events` / `find_critical_path` / `compare_performance` / "
            "`generate_report` / `check_budget` / `optimize` / `regression_explain` / "
            "`investigation_replay` / `what_if` / `optimize_experiment` / "
            "`analyze_traces` / `baseline_score` / `recommend_experiments` / "
            "`export_investigation` / `bookmark_finding` / `detect_priority_inversion` / "
            "`find_related_findings` / `compare_tasks`",
            ai_md,
        )
        self.assertNotIn("Max≪Avg", readme)
        self.assertNotIn("Max≪Avg", ai_md)

    def test_web_execute_tools_pushes_undo(self) -> None:
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        self.assertIn("pushUndoSnapshot()", app)
        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        self.assertIn("self._push_undo_snapshot()", mw)
        self.assertIn("self._cmd_undo()", mw)

    def test_highlight_normalizes_to_merge_key(self) -> None:
        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        self.assertIn("_task_merge_key(resolved)", mw)
        self.assertIn("taskMergeKey(resolved)", app)
        self.assertIn("if resolved:", mw)
        self.assertIn("if (resolved) {", app)
        self.assertIn("resolve_core_key(key, cores)", mw)
        self.assertIn("resolveCoreKey(key, trace.value?.coreNames", app)
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(encoding="utf-8")
        self.assertIn("_try_mermaid_node_click", assist)
        self.assertIn("hit_test_mermaid", assist)

    def test_corridor_resolves_core_aliases(self) -> None:
        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        self.assertIn("resolve_core_key(src_raw, cores)", mw)
        self.assertIn("resolveCoreKey(args.core_from", app)
        self.assertIn("export function resolveCoreKey", js)

    def test_tool_names_listed_in_web(self) -> None:
        js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        ai_md = (BTF_ROOT / "AI.md").read_text(encoding="utf-8")
        readme = (BTF_ROOT / "README.md").read_text(encoding="utf-8")
        workflows = (BTF_ROOT / "WORKFLOWS.md").read_text(encoding="utf-8")
        for name in AI_VIEWER_TOOL_NAMES:
            self.assertRegex(js, re.compile(rf"['\"]{re.escape(name)}['\"]"))
            self.assertIn(f"`{name}`", ai_md)
        for metric in AI_RAW_METRIC_NAMES:
            self.assertIn(f"'{metric}'", js)
            self.assertIn(f'"{metric}"', (
                BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8"))
        self.assertIn("query_raw_metric", workflows)
        self.assertIn("add_annotation", workflows)
        self.assertIn("export_report", workflows)
        self.assertIn("search_timeline", workflows)
        self.assertIn("trigger_compare", workflows)
        self.assertIn("clear_marks", workflows)
        self.assertIn("reset_view", workflows)
        self.assertIn("`add_annotation` / `query_raw_metric` / `export_report`", ai_md)
        self.assertIn(
            "`clear_marks` / `reset_view` / `search_timeline` / "
            "`trigger_compare` / `investigate` / `detect_anomalies` / "
            "`correlate_events` / `find_critical_path` / `compare_performance` / "
            "`generate_report` / `check_budget` / `optimize` / `regression_explain` / "
            "`investigation_replay` / `what_if` / `optimize_experiment` / "
            "`analyze_traces` / `baseline_score` / `recommend_experiments` / "
            "`export_investigation` / `bookmark_finding` / `detect_priority_inversion` / "
            "`find_related_findings` / `compare_tasks`",
            ai_md,
        )
        self.assertIn("Save selection as BTF", readme)
        self.assertIn("Save selection as BTF", workflows)
        self.assertIn("MAX_SEARCH_HITS = 40", js)
        self.assertIn("_MAX_SEARCH_HITS = 40", (
            BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8"))
        self.assertIn("MAX_RAW_METRIC_ROWS = 40", js)
        self.assertIn("_MAX_RAW_METRIC_ROWS = 40", (
            BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8"))
        self.assertIn("MAX_ANNOTATION_NOTE = 240", js)
        self.assertIn("_MAX_ANNOTATION_NOTE = 240", (
            BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8"))
        self.assertIn("add_annotation", AI_TOOL_SYSTEM_ADDENDUM)
        self.assertIn("query_raw_metric", AI_TOOL_SYSTEM_ADDENDUM)
        self.assertIn("export_report", AI_TOOL_SYSTEM_ADDENDUM)
        self.assertIn("Valid tools: set_cursors, zoom_to_range, highlight_task,", js)
        self.assertIn("Valid tools: set_cursors, zoom_to_range, highlight_task,", AI_TOOL_SYSTEM_ADDENDUM)
        self.assertIn("investigate, explain", AI_TOOL_SYSTEM_ADDENDUM)
        self.assertIn("investigate, explain", js)
        ollama = (BTF_ROOT / "web/src/utils/ollamaClient.js").read_text(encoding="utf-8")
        self.assertIn("High, Medium, or Low", AI_SYSTEM_PROMPT)
        self.assertIn("High, Medium, or Low", ollama)

    def test_new_tool_dispatch_sites_match(self) -> None:
        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")
        panel = (BTF_ROOT / "web/src/components/AiAssistantPanel.vue").read_text(
            encoding="utf-8")
        self.assertIn("AI_TOOL_ADD_ANNOTATION", mw)
        self.assertIn("AI_TOOL_ADD_ANNOTATION", app)
        self.assertIn("AI_TOOL_QUERY_RAW_METRIC", mw)
        self.assertIn("AI_TOOL_QUERY_RAW_METRIC", app)
        self.assertIn("query_raw_metric(", mw)
        self.assertIn("queryRawMetric(", app)
        self.assertIn("AI_TOOL_CLEAR_MARKS", mw)
        self.assertIn("AI_TOOL_CLEAR_MARKS", app)
        self.assertIn("AI_TOOL_RESET_VIEW", mw)
        self.assertIn("AI_TOOL_RESET_VIEW", app)
        self.assertIn("AI_TOOL_SEARCH_TIMELINE", mw)
        self.assertIn("AI_TOOL_SEARCH_TIMELINE", app)
        self.assertIn("AI_TOOL_TRIGGER_COMPARE", mw)
        self.assertIn("AI_TOOL_TRIGGER_COMPARE", app)
        self.assertIn("AI_TOOL_INVESTIGATE", mw)
        self.assertIn("AI_TOOL_INVESTIGATE", app)
        self.assertIn("AI_TOOL_DETECT_ANOMALIES", mw)
        self.assertIn("AI_TOOL_DETECT_ANOMALIES", app)
        self.assertIn("AI_TOOL_CORRELATE_EVENTS", mw)
        self.assertIn("AI_TOOL_CORRELATE_EVENTS", app)
        self.assertIn("AI_TOOL_COMPARE_PERFORMANCE", mw)
        self.assertIn("AI_TOOL_COMPARE_PERFORMANCE", app)
        self.assertIn("AI_TOOL_GENERATE_REPORT", mw)
        self.assertIn("AI_TOOL_GENERATE_REPORT", app)
        self.assertIn("AI_TOOL_CHECK_BUDGET", mw)
        self.assertIn("AI_TOOL_CHECK_BUDGET", app)
        self.assertIn("AI_TOOL_OPTIMIZE", mw)
        self.assertIn("AI_TOOL_OPTIMIZE", app)
        self.assertIn("AI_TOOL_REGRESSION_EXPLAIN", mw)
        self.assertIn("AI_TOOL_REGRESSION_EXPLAIN", app)
        self.assertIn("AI_TOOL_BOOKMARK_FINDING", mw)
        self.assertIn("AI_TOOL_BOOKMARK_FINDING", app)
        self.assertIn("AI_TOOL_INVESTIGATION_REPLAY", mw)
        self.assertIn("AI_TOOL_INVESTIGATION_REPLAY", app)
        self.assertIn("AI_TOOL_WHAT_IF", mw)
        self.assertIn("AI_TOOL_WHAT_IF", app)
        self.assertIn("AI_TOOL_OPTIMIZE_EXPERIMENT", mw)
        self.assertIn("AI_TOOL_OPTIMIZE_EXPERIMENT", app)
        self.assertIn("AI_TOOL_ANALYZE_TRACES", mw)
        self.assertIn("AI_TOOL_ANALYZE_TRACES", app)
        self.assertIn("investigate_finding(", mw)
        self.assertIn("investigateFinding(", app)
        self.assertIn("detect_anomalies_finding(", mw)
        self.assertIn("detectAnomaliesFinding(", app)
        self.assertIn("correlate_task_events(", mw)
        self.assertIn("correlateTaskEvents(", app)
        self.assertIn("compare_performance_tabs(", mw)
        self.assertIn("comparePerformanceTabs(", app)
        self.assertIn("generate_report_finding(", mw)
        self.assertIn("generateReportFinding(", app)
        self.assertIn("check_budget_finding(", mw)
        self.assertIn("checkBudgetFinding(", app)
        self.assertIn("optimize_finding(", mw)
        self.assertIn("optimizeFinding(", app)
        self.assertIn("regression_explain_from_compare(", mw)
        self.assertIn("explainRegressionFromCompare(", app)
        self.assertIn("investigation_replay_finding(", mw)
        self.assertIn("investigationReplayFinding(", app)
        self.assertIn("what_if_estimate(", mw)
        self.assertIn("whatIfEstimate(", app)
        self.assertIn("optimize_experiment_finding(", mw)
        self.assertIn("optimizeExperimentFinding(", app)
        self.assertIn("gather_simulation_inputs(", mw)
        self.assertIn("gatherSimulationInputs(", app)
        self.assertIn("analyze_traces_snapshots(", mw)
        self.assertIn("analyzeTracesSnapshots(", app)
        self.assertIn("format_bookmark_label(", mw)
        self.assertIn("formatBookmarkLabel(", app)
        self.assertIn("search_timeline_hits(", mw)
        self.assertIn("searchTimelineHits(", app)
        self.assertIn("def _ai_clear_marks", mw)
        self.assertIn("def _on_export_btf_slice", mw)
        self.assertIn("function onExportBtfSlice", app)
        self.assertIn("filter_btf_file_to_range", mw)
        self.assertIn("reconstruct_btf_slice", mw)
        self.assertIn("filterBtfTextToRange", app)
        self.assertIn("reconstructBtfSlice", app)
        self.assertIn("sourceText", app)
        self.assertTrue((BTF_ROOT / "btf_viewer_pkg/btf_slice.py").is_file())
        self.assertTrue((BTF_ROOT / "web/src/utils/btfSlice.js").is_file())
        self.assertIn('"slice"', (
            BTF_ROOT / "btf_viewer_pkg/cli.py").read_text(encoding="utf-8"))
        self.assertIn('"slice"', (
            BTF_ROOT / "btf_viewer_pkg/platform.py").read_text(encoding="utf-8"))
        self.assertIn("tool_mutates_gui", mw)
        self.assertIn("toolMutatesGui", app)
        self.assertNotIn("ensureMarksPanelVisible()", app)
        self.assertIn("show_marks_panel=False", mw)
        self.assertNotIn("focus_annotation_tab=True", mw)
        self.assertIn('return f"Annotated {ns}"', mw)
        self.assertIn("return `Annotated ${ns}`", app)
        self.assertIn("def _export_ai_report", assist)
        self.assertIn("function exportAiReport", panel)
        self.assertIn("tool_batch_auto_runs", assist)
        self.assertIn("toolBatchAutoRuns", panel)
        self.assertIn("is_export_tool", assist)
        self.assertIn("isExportTool", panel)
        self.assertIn("build_ai_report_html", assist)
        self.assertIn("buildAiReportHtml", panel)
        self.assertIn(AI_TOOL_ADD_ANNOTATION, AI_VIEWER_TOOL_NAMES)
        self.assertIn(AI_TOOL_QUERY_RAW_METRIC, AI_VIEWER_TOOL_NAMES)
        self.assertIn(AI_TOOL_EXPORT_REPORT, AI_VIEWER_TOOL_NAMES)
        self.assertIn("clear_marks", AI_VIEWER_TOOL_NAMES)
        self.assertIn("search_timeline", AI_VIEWER_TOOL_NAMES)
        self.assertIn("trigger_compare", AI_VIEWER_TOOL_NAMES)
        self.assertIn("investigate", AI_VIEWER_TOOL_NAMES)
        tools_js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        self.assertIn("0-based tab index", (
            BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8"))
        self.assertIn("0-based tab index", tools_js)
        self.assertIn("AI_TOOL_INVESTIGATE", tools_js)
        self.assertIn("investigate", AI_TOOL_SYSTEM_ADDENDUM)
        # Desktop: tab-bar index first; web must match that order.
        self.assertIn(
            "0-based tab-bar index first",
            app,
        )
        self.assertIn("Tab ids start at 1", app)
        self.assertIn(
            "if 0 <= idx < len(self._tabs) and getattr(self._tabs[idx], \"trace\", None)",
            mw,
        )
        self.assertIn(
            "n < tabs.value.length && tabs.value[n]?.trace",
            app,
        )
        self.assertIn("type === 'annotation'", app)
        self.assertIn("formatFindStatus", (
            BTF_ROOT / "web/src/utils/findAnalysis.js").read_text(encoding="utf-8"))
        self.assertIn("formatFindStatus", (
            BTF_ROOT / "web/src/components/FindPanel.vue").read_text(encoding="utf-8"))
        self.assertIn("migration matches", (
            BTF_ROOT / "btf_viewer_pkg/mvvm/find_logic.py").read_text(encoding="utf-8"))
        readme = (BTF_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("reconstruct", readme)
        self.assertIn("filter source, else reconstruct", readme)
        self.assertNotIn("Desktop always re-reads the source file", readme)
        workflows = (BTF_ROOT / "WORKFLOWS.md").read_text(encoding="utf-8")
        self.assertNotIn("Export only the raw events between the earliest", workflows)
        self.assertIn("archive.zip::", (
            BTF_ROOT / "web/src/utils/btfLoad.js").read_text(encoding="utf-8"))
        self.assertIn("onMermaidZoomWheel", panel)
        self.assertIn("_scale = max(0.5, min(6.0", assist)

    def test_stats_table_annotation_does_not_switch_to_marks(self) -> None:
        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        self.assertIn("def _on_stats_plot_point_clicked", mw)
        self.assertIn("stay_tab = self._panel_tabs.currentIndex()", mw)
        self.assertIn("function onStatsPlotPointActivate", app)
        self.assertIn("const stayOnTab = rightPanelTab.value", app)
        self.assertIn("rightPanelTab.value = stayOnTab", app)
        self.assertNotIn("ensureMarksPanelVisible()", app)
        self.assertIn(
            "self._add_annotation_with_note(mark_ns, note, show_marks_panel=False)",
            mw,
        )
        readme = (BTF_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("switch to the **Marks** tab", readme)
        self.assertIn("without switching right-panel tabs", readme)

    def test_gemini_thought_signature_helpers_match(self) -> None:
        js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        py = (BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8")
        client = (BTF_ROOT / "web/src/utils/ollamaClient.js").read_text(
            encoding="utf-8")
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")
        self.assertIn(f'"{GEMINI_SKIP_THOUGHT_SIGNATURE}"', py)
        self.assertIn(f"'{GEMINI_SKIP_THOUGHT_SIGNATURE}'", js)
        self.assertIn("def ensure_gemini_thought_signatures", py)
        self.assertIn("export function ensureGeminiThoughtSignatures", js)
        self.assertIn("def needs_gemini_thought_signatures", py)
        self.assertIn("export function needsGeminiThoughtSignatures", js)
        self.assertIn("ensure_gemini_thought_signatures(messages)", assist)
        self.assertIn("ensureGeminiThoughtSignatures(chatMessages)", client)
        readme = (BTF_ROOT / "README.md").read_text(encoding="utf-8")
        ai_md = (BTF_ROOT / "AI.md").read_text(encoding="utf-8")
        self.assertIn("thought_signature", ai_md)
        workflows = (BTF_ROOT / "WORKFLOWS.md").read_text(encoding="utf-8")
        self.assertIn("thought_signature", workflows)
        self.assertIn('"preset": active["preset"]', assist)
        self.assertIn("preset: active.preset", (
            BTF_ROOT / "web/src/components/AiAssistantPanel.vue"
        ).read_text(encoding="utf-8"))

    def test_ai_model_picker_is_editable_combo(self) -> None:
        vue = (BTF_ROOT / "web/src/components/SettingsDialog.vue").read_text(
            encoding="utf-8")
        stats = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
        client = (BTF_ROOT / "web/src/utils/ollamaClient.js").read_text(
            encoding="utf-8")
        readme = (BTF_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("setEditable(True)", stats)
        self.assertIn("def _fill_ai_model_combo", stats)
        self.assertIn('role="combobox"', vue)
        self.assertIn("toggleAiModelMenu", vue)
        self.assertIn("ai-model-listbox", vue)
        self.assertIn("_ai_model_combo.showPopup", stats)
        self.assertIn("aiModelMenuOpen.value = true", vue)
        self.assertIn("AbortSignal.timeout(timeoutMs)", client)
        self.assertIn("AbortSignal.any(", client)
        self.assertNotIn("<datalist", vue)
        self.assertNotIn("datalist", readme)

    def test_ai_auth_mode_helpers_match(self) -> None:
        from btf_viewer_pkg.ai_assistant import (
            AI_AUTH_API_KEY,
            AI_AUTH_BROWSER,
            AI_AUTH_MODE_LABELS,
            AI_AUTH_NONE,
            AI_PRESET_CUSTOM,
            AI_PRESET_FIELDS,
            AI_PRESET_GEMINI,
            AI_PRESET_KEY_URLS,
            AI_PRESET_OLLAMA,
            AI_PRESET_OPENAI,
            AI_PRESET_SIGNIN_LABELS,
            LOCAL_AI_HOSTS,
            ai_auth_status,
            ai_preset_signin_label,
            ai_preset_signin_url,
            default_ai_auth_mode,
            normalize_ai_auth_mode,
        )

        js = (BTF_ROOT / "web/src/utils/ollamaClient.js").read_text(encoding="utf-8")
        vue = (BTF_ROOT / "web/src/components/SettingsDialog.vue").read_text(
            encoding="utf-8")
        stats = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
        panel = (BTF_ROOT / "web/src/components/AiAssistantPanel.vue").read_text(
            encoding="utf-8")
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")
        readme = (BTF_ROOT / "README.md").read_text(encoding="utf-8")
        ai_md = (BTF_ROOT / "AI.md").read_text(encoding="utf-8")
        workflows = (BTF_ROOT / "WORKFLOWS.md").read_text(encoding="utf-8")

        self.assertEqual(AI_AUTH_NONE, "none")
        self.assertEqual(AI_AUTH_API_KEY, "api_key")
        self.assertEqual(AI_AUTH_BROWSER, "browser")
        self.assertEqual(tuple(AI_PRESET_FIELDS), (
            "base_url", "model", "api_key", "auth_mode", "tls_verify"))
        self.assertIn("authMode", js)
        self.assertIn(
            "AI_PRESET_FIELDS = ['baseUrl', 'model', 'apiKey', 'authMode', 'tlsVerify']",
            js,
        )

        for _mode, label in AI_AUTH_MODE_LABELS:
            self.assertIn(f"'{label}'", js)
        for host in LOCAL_AI_HOSTS:
            self.assertIn(f"'{host}'", js)
        for url in AI_PRESET_KEY_URLS.values():
            self.assertIn(url, js)
            self.assertIn(url, assist)
        for label in AI_PRESET_SIGNIN_LABELS.values():
            self.assertIn(label, js)
            self.assertIn(label, assist)

        for status_label in (
            "Local", "Signed in", "Key saved", "Needs sign-in", "Needs API key",
        ):
            self.assertIn(f"'{status_label}'", js)
            self.assertIn(f'"{status_label}"', assist)

        self.assertEqual(default_ai_auth_mode(AI_PRESET_OLLAMA), AI_AUTH_NONE)
        self.assertEqual(default_ai_auth_mode(AI_PRESET_GEMINI), AI_AUTH_API_KEY)
        self.assertEqual(normalize_ai_auth_mode("sign-in"), AI_AUTH_BROWSER)
        self.assertEqual(normalize_ai_auth_mode("oauth"), AI_AUTH_BROWSER)
        self.assertIn("aistudio.google.com", ai_preset_signin_url(AI_PRESET_GEMINI))
        self.assertEqual(
            ai_preset_signin_label(AI_PRESET_OPENAI), "Sign in with OpenAI…")
        self.assertEqual(
            ai_preset_signin_label(AI_PRESET_CUSTOM), "Open provider sign-in…")
        need = ai_auth_status(
            auth_mode=AI_AUTH_API_KEY, api_key="", preset_id=AI_PRESET_GEMINI)
        self.assertTrue(need["needs_auth"])
        self.assertEqual(need["label"], "Needs API key")

        self.assertIn("def normalize_ai_auth_mode", assist)
        self.assertIn("export function normalizeAiAuthMode", js)
        self.assertIn("def strip_ai_settings_jsonc", assist)
        self.assertIn("export function stripAiSettingsJsonc", js)
        self.assertIn("strip_ai_settings_jsonc(data)", assist)
        self.assertIn("stripAiSettingsJsonc(parsed)", js)
        self.assertIn("AI_AUTH_BROWSER", assist)
        self.assertIn("AI_AUTH_BROWSER", js)
        self.assertIn("Authentication:", stats)
        self.assertIn("Authentication", vue)
        self.assertIn("_ai_signin_btn", stats)
        self.assertIn("onAiSignIn", vue)
        self.assertIn("QDesktopServices.openUrl(QUrl(url))", stats)
        self.assertIn("QDesktopServices.openUrl(QUrl(url))", assist)
        self.assertIn("window.open(url, '_blank', 'noopener,noreferrer')", vue)
        self.assertIn("window.open(url, '_blank', 'noopener,noreferrer')", panel)
        self.assertIn(
            "Opened {url}. After you sign in, paste the key or token and Test.",
            stats)
        self.assertIn(
            "Opened ${url}. After you sign in, paste the key or token and Test.",
            vue)
        self.assertIn(
            "This preset has no sign-in page. Paste a token or set Base URL.",
            stats)
        self.assertIn(
            "This preset has no sign-in page. Paste a token or set Base URL.",
            vue)
        self.assertIn("_auth_chip", assist)
        self.assertIn("ai-auth-chip", panel)
        self.assertIn("self._auth_forced", assist)
        self.assertIn("authForced", panel)
        self.assertIn("showSignInCta", panel)
        self.assertIn(
            "Opened {url}. Paste the key or token in Settings → AI.", assist)
        self.assertIn(
            "Opened ${url}. Paste the key or token in Settings → AI.", panel)
        self.assertIn("Authentication |", ai_md)
        self.assertIn("Self-signed TLS |", ai_md)
        self.assertIn("Model picker |", ai_md)
        self.assertIn("Allow self-signed TLS", stats)
        self.assertIn("Allow self-signed TLS", vue)
        self.assertIn("Allow self-signed TLS", readme)
        self.assertIn("Allow self-signed TLS", ai_md)
        self.assertIn("Allow self-signed TLS", workflows)
        self.assertIn("def parse_ai_tls_verify", assist)
        self.assertIn("export function parseAiTlsVerify", js)
        self.assertIn("ai_urlopen", assist)
        self.assertIn("aiTlsTip", js)
        self.assertIn("def _ai_timeout_error_tip", assist)
        self.assertIn("GET /models only lists ids", assist)
        self.assertIn("GET /models only lists ids", js)
        self.assertIn("BASE/chat/completions", ai_md)
        for name in (
            "ollama.json", "gemini.json", "openai.json",
            "deepseek.json", "grok.json", "presets.json",
        ):
            self.assertIn(name, ai_md)
            self.assertIn(name, workflows)
            self.assertIn(name, stats)
            self.assertIn(name, vue)
        self.assertIn("401 keeps Sign in / Settings CTAs", workflows)
        self.assertIn("open the Model dropdown", workflows)
        self.assertIn("token-efficient", ai_md)
        self.assertIn("Parameters / targets", ai_md)
        self.assertIn("qwen2.5:7b", ai_md)
        self.assertIn("qwen2.5:7b", workflows)
        self.assertIn("8k", ai_md)
        self.assertIn("examples/ai/presets.json", readme)
        self.assertIn("## GUI tools", ai_md)
        self.assertIn("triage overall findings", ai_md)
        self.assertIn("triage overall findings", workflows)
        self.assertIn(
            "Open the Model dropdown to pick one.", stats)
        self.assertIn(
            "Open the Model dropdown to pick one.", vue)

    def test_gemini_tool_result_name_helpers_match(self) -> None:
        py = (BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8")
        js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")
        vue = (BTF_ROOT / "web/src/components/AiAssistantPanel.vue").read_text(
            encoding="utf-8")
        client = (BTF_ROOT / "web/src/utils/ollamaClient.js").read_text(
            encoding="utf-8")
        self.assertIn("def normalize_tool_chat_messages", py)
        self.assertIn("export function normalizeToolChatMessages", js)
        self.assertIn("normalize_tool_chat_messages(messages)", assist)
        self.assertIn("normalizeToolChatMessages(", client)
        self.assertIn("canonical_assistant_tool_message(text, calls)", assist)
        self.assertIn("canonicalAssistantToolMessage(text, calls)", vue)
        self.assertIn("tool_result_message(", assist)
        self.assertIn("toolResultMessage(", vue)

    def test_markdown_tables_match_web(self) -> None:
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")
        js = (BTF_ROOT / "web/src/utils/aiMarkdown.js").read_text(encoding="utf-8")
        vue = (BTF_ROOT / "web/src/components/AiAssistantPanel.vue").read_text(
            encoding="utf-8")
        readme = (BTF_ROOT / "README.md").read_text(encoding="utf-8")
        ai_md = (BTF_ROOT / "AI.md").read_text(encoding="utf-8")
        self.assertIn('class="ai-md-table"', assist)
        self.assertIn('class="ai-md-table"', js)
        self.assertIn("table.ai-md-table", vue)
        self.assertIn("_sanitize_html_table_block", assist)
        self.assertIn("sanitizeHtmlTableBlock", js)
        self.assertIn("Pipe **Markdown tables**", ai_md)
        self.assertIn("In-chat Markdown / HTML tables", ai_md)

    def test_phase3_host_dispatch_matches_web(self) -> None:
        """baseline_score / recommend_experiments / PI / related / compare_tasks
        must be dispatched by both mainwindow.py and App.vue's dispatchAiTool."""
        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        for const in (
            "AI_TOOL_BASELINE_SCORE", "AI_TOOL_RECOMMEND_EXPERIMENTS",
            "AI_TOOL_DETECT_PRIORITY_INVERSION", "AI_TOOL_FIND_RELATED_FINDINGS",
            "AI_TOOL_COMPARE_TASKS",
        ):
            self.assertIn(f"if name == {const}:", mw)
            self.assertIn(f"if (name === {const}) {{", app)
        self.assertIn("def _ai_load_baseline_profile", mw)
        self.assertIn("def _ai_save_baseline_profile", mw)
        self.assertIn("baseline_profile", mw)
        self.assertIn("loadAiBaselineProfile", app)
        self.assertIn("saveAiBaselineProfile", app)
        self.assertIn("loadAiBaselineProfile", (BTF_ROOT / "web/src/utils/settingsStore.js").read_text(encoding="utf-8"))
        self.assertIn("btf-viewer-ai-baseline-v1", (BTF_ROOT / "web/src/utils/settingsStore.js").read_text(encoding="utf-8"))

    def test_export_investigation_json_matches_web(self) -> None:
        """export_investigation / export_report(format=json) must build the
        same investigation package + trigger a real file save on both sides."""
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(encoding="utf-8")
        panel = (BTF_ROOT / "web/src/components/AiAssistantPanel.vue").read_text(encoding="utf-8")
        self.assertIn("build_investigation_package", assist)
        self.assertIn("buildInvestigationPackage", panel)
        self.assertIn("AI_TOOL_EXPORT_INVESTIGATION", assist)
        self.assertIn("AI_TOOL_EXPORT_INVESTIGATION", panel)
        self.assertIn('fmt == "json"', assist)
        self.assertIn("fmt === 'json'", panel)
        self.assertIn("_export_investigation_package", assist)
        self.assertIn("exportInvestigationFile", panel)

    def test_auto_investigate_findings_dialog_button_matches_web(self) -> None:
        stats = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
        dlg = (BTF_ROOT / "web/src/components/AnalysisFindingsDialog.vue").read_text(
            encoding="utf-8")
        self.assertIn("Auto investigate…", stats)
        self.assertIn("Auto investigate…", dlg)
        self.assertIn('"auto_investigate"', stats)
        self.assertIn("'auto_investigate'", dlg)


if __name__ == "__main__":
    unittest.main()
