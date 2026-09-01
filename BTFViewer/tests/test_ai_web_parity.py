"""Desktop ↔ web AI constants and call-site parity."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg.ai_assistant import (  # noqa: E402
    AI_API_KEY_ENV_NAMES,
    AI_API_KEY_REQUIRED,
    AI_CHAT_TIMEOUT_S,
    AI_LIST_MODELS_TIMEOUT_S,
    AI_SEND_ICON_PATH,
    AI_STOP_ICON_PATH,
    AI_CORE_PROMPT,
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
    AI_TOOL_PROMPT,
    AI_MALFORMED_FUNCTION_CALL_NUDGE,
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

        ai_client_js = (BTF_ROOT / "web/src/utils/aiClient.js").read_text(
            encoding="utf-8")
        inv_js = (BTF_ROOT / "web/src/utils/aiInvestigation.js").read_text(
            encoding="utf-8")
        block = re.search(
            r"export const AI_RESPONSE_LANGUAGES = \[([\s\S]*?)\]\n", ai_client_js)
        self.assertIsNotNone(block)
        js_langs = tuple(re.findall(r"'([^']+)'", block.group(1)))
        self.assertEqual(js_langs, AI_RESPONSE_LANGUAGES)
        self.assertEqual(set(EVIDENCE_PANEL_LABELS), set(AI_RESPONSE_LANGUAGES))
        for lang in AI_RESPONSE_LANGUAGES:
            self.assertIn(lang, inv_js)
        self.assertNotIn("Klingon", "".join(AI_RESPONSE_LANGUAGES))
        self.assertNotIn("Klingon", inv_js)
        self.assertNotIn("Klingon", ai_client_js)
        for key in (
            "role", "evidence", "confidence", "score", "investigation",
            "high", "medium", "low", "quality", "coverage", "disprove",
            "supported", "need_evidence", "evolution", "cost",
            "historical", "support_action", "reject_action",
            "need_evidence_action", "test_action", "compare_action",
            "interpreted", "scope", "run_investigation", "edit_scope",
            "experiment_result", "save_knowledge",
            "quality_direct", "coverage_observed", "why_action",
            "run_next", "more_next_steps", "investigation_complete",
        ):
            for labels in EVIDENCE_PANEL_LABELS.values():
                self.assertIn(key, labels)

    def test_timeouts_match_web(self) -> None:
        js = (BTF_ROOT / "web/src/utils/aiClient.js").read_text(encoding="utf-8")
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
        ai_client_js = (BTF_ROOT / "web/src/utils/aiClient.js").read_text(
            encoding="utf-8")
        self.assertIn("Use Mermaid", AI_TOOL_SYSTEM_ADDENDUM)
        self.assertIn("Use Mermaid", js)
        self.assertEqual(AI_TOOL_PROMPT, AI_TOOL_SYSTEM_ADDENDUM)
        self.assertIn("function loadsJsonValues", js)
        self.assertIn("def _loads_json_values", (
            BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8"))
        self.assertIn(
            "if (textCalls.length) content = stripParsedToolMarkup", ai_client_js)
        self.assertIn("ASK_EVENT_PROMPT", ai_client_js)
        self.assertIn(ASK_EVENT_PROMPT.split("{task}")[0], ai_client_js)
        self.assertIn("Use correlate_events or query_raw_metric", ai_client_js)
        self.assertIn("jump:{time}", ai_client_js)
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
        self.assertIn("simulation or optimization only when requested", AI_TOOL_SYSTEM_ADDENDUM)
        self.assertIn("optimize_experiment", js)
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
        ux_py = (BTF_ROOT / "btf_viewer_pkg/ux_explore.py").read_text(encoding="utf-8")
        ux_js = (BTF_ROOT / "web/src/utils/uxExplore.js").read_text(encoding="utf-8")
        for py_name, js_name in (
            ("def format_burst_window_ns", "export function formatBurstWindowNs"),
            ("def format_burst_reason", "export function formatBurstReason"),
            ("def detect_timeline_anomalies", "export function detectTimelineAnomalies"),
            ("def collect_worst_events", "export function collectWorstEvents"),
            ("def best_finding_scope", "export function bestFindingScope"),
            ("def finding_overlay_times", "export function findingOverlayTimes"),
            ("def task_inspector_line", "export function taskInspectorLine"),
            ("def compare_summary_strip", "export function compareSummaryStrip"),
            ("def compare_summary_decision_html", "export function compareSummaryDecisionHtml"),
            ("def compare_notable_changes", "export function compareNotableChanges"),
            ("def compare_investigate_target", "export function compareInvestigateTarget"),
            ("def compare_cell_sort_key", "export function compareCellSortKey"),
            ("def compare_section_for_metric", "export function compareSectionForMetric"),
            ("def compare_task_for_row", "export function compareTaskForRow"),
            ("def compare_core_util_chart_svg", "export function compareCoreUtilChartSvg"),
            ("def compare_p99_delta_chart_svg", "export function compareP99DeltaChartSvg"),
            ("def compare_summary_change_bars_svg", "export function compareSummaryChangeBarsSvg"),
            ("def compare_summary_change_bar_rows", "export function compareSummaryChangeBarRows"),
            ("def compare_migration_heatmap_svg", "export function compareMigrationHeatmapSvg"),
            ("def compare_migration_heatmap_rows", "export function compareMigrationHeatmapRows"),
            ("def compare_row_delta_status", "export function compareRowDeltaStatus"),
            ("def compare_directional_delta", "export function compareDirectionalDelta"),
            ("def compare_dumbbell_rows", "export function compareDumbbellRows"),
            ("def filter_compare_migration_rows", "export function filterCompareMigrationRows"),
            ("COMPARE_DELTA_FORMULA", "export const COMPARE_DELTA_FORMULA"),
            ("COMPARE_METRIC_GLOSSARY", "export const COMPARE_METRIC_GLOSSARY"),
            ("COMPARE_NOTE_MIGRATION", "export const COMPARE_NOTE_MIGRATION"),
            ("def harvest_ux_events", "export function harvestUxEvents"),
            ("def prepare_ux_events", "export function prepareUxEvents"),
            ("def find_event_at_percentile", "export function findEventAtPercentile"),
            ("def analyze_task_periods", "export function analyzeTaskPeriods"),
            ("def task_core_matrix", "export function taskCoreMatrix"),
            ("def pair_mutex_waits", "export function pairMutexWaits"),
            ("def waiter_owner_matrix", "export function waiterOwnerMatrix"),
            ("def task_health_scores", "export function taskHealthScores"),
            ("def harvest_mutex_holds", "export function harvestMutexHolds"),
            ("def health_inputs_from_events", "export function healthInputsFromEvents"),
            ("def analyze_response_times", "export function analyzeResponseTimes"),
            ("def critical_path_rows", "export function criticalPathRows"),
            ("def preemption_pairs", "export function preemptionPairs"),
            ("def preemptor_ranking", "export function preemptorRanking"),
            ("def preemption_matrix", "export function preemptionMatrix"),
            ("def mutex_blocking_table", "export function mutexBlockingTable"),
            ("def core_util_over_time", "export function coreUtilOverTime"),
            ("def unified_jitter", "export function unifiedJitter"),
            ("def sparkline", "export function sparkline"),
            ("def distribution_explorer", "export function distributionExplorer"),
            ("def distribution_metric_samples", "export function distributionMetricSamples"),
            ("def recurring_patterns", "export function recurringPatterns"),
            ("def recurring_patterns_across", "export function recurringPatternsAcross"),
            ("def compare_why", "export function compareWhy"),
            ("def preemption_story", "export function preemptionStory"),
            ("def top_blocking_contributors", "export function topBlockingContributors"),
            ("def compare_analysis_tables", "export function compareAnalysisTables"),
        ):
            self.assertIn(py_name, ux_py, py_name)
            self.assertIn(js_name, ux_js, js_name)
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
        self.assertIn("Apply cursors", dlg)
        self.assertIn("Investigate…", stats)
        self.assertIn("Root cause…", stats)
        self.assertIn("Apply cursors", stats)
        self.assertIn("best_finding_scope,", stats)
        self.assertNotRegex(stats, r"(?m)^\s+from \.ux_explore import")
        # Web Ask AI menu → emit('query-ai', payload); Desktop Ask AI menu → _query_with_ai.
        self.assertIn("askAi('investigate')", dlg)
        self.assertIn('ask_menu.addAction("Investigate…")', stats)
        self.assertIn("self._query_with_ai(", stats)
        self.assertIn("wants_ai_template", stats)
        self._assert_stats_export_titles_match()
        self._assert_stats_section_ids_match()
        self._assert_stats_load_defer_match()
        self._assert_investigation_ui_match()

    def _assert_stats_export_titles_match(self) -> None:
        """UI + HTML export section titles stay Desktop / Web aligned.

        Standalone **Export CSV** was removed from both GUIs; HTML reports
        provide per-table CSV downloads. Desktop CLI still writes a full CSV
        via ``write_statistics_csv_report`` (third title site in stats.py).
        """
        titles = (
            "Task × Core",
            "Task Health",
            "Period / Jitter",
            "Waiter × Owner",
            "Response Time",
            "Unified Jitter",
            "Preemption Matrix",
            "Mutex Blocking",
            "Core Utilization Over Time",
        )
        investigate = (
            "Timeline Anomalies",
            "Worst Events",
            "Critical Path",
            "Recurring Patterns",
        )
        stats = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
        web = (BTF_ROOT / "web/src/components/StatisticsPanel.vue").read_text(
            encoding="utf-8")
        stats_html = (BTF_ROOT / "btf_viewer_pkg/stats_html.py").read_text(
            encoding="utf-8")
        web_html = (BTF_ROOT / "web/src/utils/statsHtmlReport.js").read_text(
            encoding="utf-8")
        # GUI: HTML-only export button (CSV is inside the HTML report).
        self.assertIn("Export HTML", stats)
        self.assertIn("Export HTML", web)
        self.assertNotIn("_btn_export_csv", stats)
        self.assertNotIn("exportCsv", web)
        self.assertIn("write_statistics_csv_report", stats)
        for title in titles:
            self.assertIn(f'<h2>{title}', stats.replace("{_esc(scope_title)}", ""), title)
            self.assertIn(f'<h2>{title}', web, title)
            # Desktop: UI section + HTML h2 + CLI CSV section header.
            self.assertGreaterEqual(stats.count(title), 3, title)
            # Web: UI section + HTML h2 (no standalone CSV report builder).
            self.assertGreaterEqual(web.count(title), 2, title)
            self.assertIn(f'"{title}{{scope_suffix}}"', stats, title)
        self.assertIn("<h2>Investigate Anomalies", stats_html)
        self.assertIn("<h2>Investigate Anomalies", web_html)
        self.assertIn("html_investigate_anomalies", stats)
        self.assertIn("htmlInvestigateAnomalies", web)
        self.assertIn("Off-CPU Time (Blocking Time)", stats)
        self.assertIn("Off-CPU Time (Blocking Time)", web)
        for title in investigate:
            self.assertIn(title, stats_html, title)
            self.assertIn(title, web_html, title)
            # Desktop: UI section + CLI CSV; Web: UI in panel, HTML copy in statsHtmlReport.
            self.assertGreaterEqual(stats.count(title), 2, title)
            self.assertIn(title, web, title)
            self.assertIn(f'"{title}{{scope_suffix}}"', stats, title)
        self.assertIn("Dispatch / Scheduling Latency", stats)
        self.assertIn("<th>p99</th>", stats)
        self.assertIn("toggleTableSort('period', 'p99')", web)
        self.assertIn("toggleTableSort('response', 'p99')", web)
        # Period / Response percentile columns in HTML export (CSV was removed).
        self.assertIn("<th>p95</th><th>p99</th>", web)
        self.assertIn('"p95", "p99"', stats)
        self.assertIn("hdr.setSectionsClickable(True)", stats)
        self.assertIn("thSortClass('anomalies'", web)
        self.assertIn("thSortClass('mutex_blockers'", web)
        self.assertIn("sortedPeriodRows", web)
        self.assertIn("class=\"stats-table-row clickable\"", web)

    def _assert_stats_section_ids_match(self) -> None:
        """Pinnable section IDs and always-visible lifecycle/affinity stay aligned."""
        from btf_viewer_pkg.config import STATS_PINNABLE_SECTIONS

        pins_js = (BTF_ROOT / "web/src/utils/statsPins.js").read_text(
            encoding="utf-8")
        block = re.search(
            r"export const STATS_PINNABLE_SECTIONS = Object\.freeze\(\[([\s\S]*?)\]\)",
            pins_js)
        self.assertIsNotNone(block)
        js_ids = tuple(re.findall(r"'([^']+)'", block.group(1)))
        self.assertEqual(js_ids, STATS_PINNABLE_SECTIONS)
        stats = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
        web = (BTF_ROOT / "web/src/components/StatisticsPanel.vue").read_text(
            encoding="utf-8")
        for sid in STATS_PINNABLE_SECTIONS:
            self.assertIn(f'"{sid}"', stats, sid)
            self.assertIn(f"'{sid}'", web, sid)
        self.assertNotIn('v-if="lifecycleStats.length"', web)
        self.assertNotIn('v-if="coreAffinityRows.length"', web)
        self.assertIn("Task Lifecycle", web)
        self.assertIn("Task Lifecycle", stats)
        self.assertIn("Kind", web)
        self.assertIn("'queue', 'kind'", web)
        self.assertIn("'queue', 'bounces'", web)
        self.assertNotIn('v-if="coreTimeBreakdown.length"', web)
        self.assertNotIn('v-if="corePairRows.length"', web)
        self.assertIn("No core segments", web)
        self.assertIn("No migrations in scope", web)
        self.assertIn("Load Balance Score", web)
        self.assertIn("Load Balance Score", stats)
        # Desktop CLI CSV still labels σ; Web gauge module matches that wording.
        self.assertIn("Core Util Std Dev (σ)", stats)
        lb_js = (BTF_ROOT / "web/src/utils/loadBalanceGauge.js").read_text(
            encoding="utf-8")
        self.assertIn("population stddev of core utilisation", lb_js)
        self.assertIn("def _open(_checked: bool = False)", stats)
        self.assertIn("openPreemptPlot(mk, label)", web)
        self.assertIn("Open histogram", stats)
        self.assertIn("Open histogram", web)
        self.assertIn('QLabel("Metric")', stats)
        self.assertIn('QLabel("Task")', stats)
        self.assertIn("hist_btns.addWidget(open_btn", stats)
        self.assertIn("class=\"distrib-toolbar\"", web)
        self.assertIn("class=\"stats-tool-btn\"", web)
        self.assertIn("_style_stats_tool_button", stats)
        self.assertIn("setFixedHeight(200)", stats)
        self.assertIn("tools_w = QWidget()", stats)
        self.assertIn("_sync_anomaly_investigate_btn", stats)
        self.assertIn("Investigate…", stats)
        self.assertIn("Investigate…", web)
        self.assertIn("!aiFeatureEnabled || !anomalyRows.length", web)
        self.assertRegex(
            stats,
            re.compile(
                r"def _investigate_anomaly\(.*?\n(?:.*\n){0,6}?"
                r"\s+if not self\._ai_enabled:\n\s+return",
                re.MULTILINE,
            ),
        )
        self.assertIn("distribution_metric_samples", stats)
        self.assertIn("_HistogramWidget(", stats)
        self.assertIn("distribHistogramModel", web)
        self.assertIn("distrib-hist", web)
        self.assertIn("Query with AI…", stats)
        self.assertIn("queryDistributionWithAi", web)
        self.assertIn("aiFeatureEnabled", web)
        self.assertIn("on_query_ai=self._query_plot_distribution_ai", stats)
        self.assertIn(":disabled=\"!aiFeatureEnabled\"", web)

    def _assert_stats_load_defer_match(self) -> None:
        """Large-trace defer thresholds and heavy-section IDs stay lockstep."""
        from btf_viewer_pkg.config import (
            STATS_DEFAULT_EXPANDED_SECTIONS,
            STATS_HEAVY_SECTIONS,
            STATS_LOAD_DEFER_CORES,
            STATS_LOAD_DEFER_SEGMENTS,
            STATS_LOAD_DEFER_SYNC_ISSUES,
            STATS_LOAD_DEFER_TASKS,
            default_section_collapsed,
        )

        js = (BTF_ROOT / "web/src/config.js").read_text(encoding="utf-8")
        self.assertIn(f"export const STATS_LOAD_DEFER_TASKS = {STATS_LOAD_DEFER_TASKS}", js)
        self.assertIn(f"export const STATS_LOAD_DEFER_CORES = {STATS_LOAD_DEFER_CORES}", js)
        self.assertIn(
            f"export const STATS_LOAD_DEFER_SYNC_ISSUES = {STATS_LOAD_DEFER_SYNC_ISSUES}", js)
        self.assertIn(
            f"export const STATS_LOAD_DEFER_SEGMENTS = {STATS_LOAD_DEFER_SEGMENTS}", js)
        block = re.search(
            r"export const STATS_HEAVY_SECTIONS = \[([\s\S]*?)\]", js)
        self.assertIsNotNone(block)
        js_ids = set(re.findall(r"'([^']+)'", block.group(1)))
        self.assertEqual(js_ids, set(STATS_HEAVY_SECTIONS))
        collapsed_keys = set(default_section_collapsed())
        from btf_viewer_pkg.config import COMMAND_PALETTE_ACTIONS, WORKSPACE_PRESETS
        self.assertIn("export const COMMAND_PALETTE_ACTIONS = [", js)
        for aid, label in COMMAND_PALETTE_ACTIONS:
            self.assertIn(f"['{aid}', '{label}']", js)
        self.assertIn("export const WORKSPACE_PRESETS = {", js)
        for pid, sections in WORKSPACE_PRESETS.items():
            self.assertIn(f"'{pid}':", js, pid)
            for sid in sections:
                self.assertIn(f"'{sid}'", js, f"{pid}:{sid}")
        self.assertIn("export function workspacePresetCollapsed", js)
        self.assertTrue(set(STATS_HEAVY_SECTIONS) <= collapsed_keys)
        js_exp = re.search(
            r"export const STATS_DEFAULT_EXPANDED_SECTIONS = \[([\s\S]*?)\]", js)
        self.assertIsNotNone(js_exp)
        self.assertEqual(
            set(re.findall(r"'([^']+)'", js_exp.group(1))),
            set(STATS_DEFAULT_EXPANDED_SECTIONS),
        )
        expanded = {
            sid for sid, flag in default_section_collapsed().items() if not flag
        }
        self.assertEqual(expanded, set(STATS_DEFAULT_EXPANDED_SECTIONS))
        main = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        store = (BTF_ROOT / "web/src/utils/sessionStore.js").read_text(encoding="utf-8")
        portable_js = (BTF_ROOT / "web/src/utils/sessionPortable.js").read_text(
            encoding="utf-8")
        self.assertIn("statsSectionCollapsed", main)
        self.assertIn("_apply_workspace_preset", main)
        self.assertIn("inspect-task", main)
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        self.assertIn("function applyWorkspacePreset", app)
        self.assertIn("inspect-task", app)
        self.assertIn("statsSectionCollapsed", portable_js)
        self.assertNotIn("statsSectionCollapsed:", store)
        settings = (BTF_ROOT / "web/src/utils/settingsStore.js").read_text(
            encoding="utf-8")
        self.assertIn("statsSectionCollapsed:", settings)
        self.assertIn("section_collapsed_to_rc", main)
        self.assertIn("set_section_collapsed_map", main)
        vue = (BTF_ROOT / "web/src/components/StatisticsPanel.vue").read_text(
            encoding="utf-8")
        stats = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
        self.assertIn("emitCollapsedState()", vue)
        self.assertIn("applyCollapsedState(state)", vue)
        self.assertNotIn("self._section_collapsed[sid] = True", stats)
        self.assertIn("for key in default_section_collapsed():", stats)
        self.assertIn("_reset_stats_layout_to_defaults", main)
        self.assertIn("stats_layout_reset", main)
        self.assertIn("_apply_stats_layout_defaults", main)
        self.assertIn("clear_section", stats)
        dlg = (BTF_ROOT / "web/src/components/SettingsDialog.vue").read_text(
            encoding="utf-8")
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        self.assertIn("resetLayout", dlg)
        self.assertIn("normalizeSettings(null)", dlg)
        self.assertIn("meta.resetLayout", app)
        self.assertIn("statsSectionHeights.value = {}", app)

    def test_stats_section_help_matches_web(self) -> None:
        from btf_viewer_pkg.config import STATS_PINNABLE_SECTIONS, STATS_SECTION_HELP

        js = (BTF_ROOT / "web/src/config.js").read_text(encoding="utf-8")
        hdr = (BTF_ROOT / "web/src/components/StatsSectionHeader.vue").read_text(
            encoding="utf-8")
        stats = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
        self.assertEqual(set(STATS_SECTION_HELP), set(STATS_PINNABLE_SECTIONS))
        self.assertIn("STATS_SECTION_HELP.get(section_id)", stats)
        self.assertIn("STATS_SECTION_HELP[props.sectionId]", hdr)
        for sid, text in STATS_SECTION_HELP.items():
            self.assertIn(f"  {sid}:", js, sid)
            self.assertIn(text, js, sid)

    def _assert_investigation_ui_match(self) -> None:
        stats = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
        dlg = (BTF_ROOT / "web/src/components/AnalysisFindingsDialog.vue").read_text(
            encoding="utf-8")
        compare = (BTF_ROOT / "web/src/components/TraceCompareDialog.vue").read_text(
            encoding="utf-8")
        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")
        panel = (BTF_ROOT / "web/src/components/AiAssistantPanel.vue").read_text(
            encoding="utf-8")
        for needle in ("Save recipe…", "Story…"):
            self.assertIn(needle, stats, needle)
            self.assertIn(needle, dlg, needle)
        for needle in ("Save baseline", "Score vs baseline"):
            self.assertIn(needle, stats, needle)
            self.assertIn(needle, compare, needle)
        self.assertNotIn("Investigate on Baseline", stats)
        self.assertNotIn("Investigate on Baseline", compare)
        self.assertNotIn("Investigate on Candidate", stats)
        self.assertNotIn("Investigate on Candidate", compare)
        self.assertIn("self._decision, self._summary_chart, self._summary_table", stats)
        self.assertIn("toggleTableSort('summary', 'delta')", compare)
        self.assertIn("compare_cell_sort_key(val)", stats)
        self.assertIn('addTab(self._trends_table, "Trends")', stats)
        self.assertIn("id: 'trends', label: 'Trends'", compare)
        self.assertIn("Start Investigation", assist)
        self.assertIn("Start Investigation", panel)
        self.assertIn("Inspect task", mw)
        cfg_js = (BTF_ROOT / "web/src/config.js").read_text(encoding="utf-8")
        self.assertIn("['inspect-task', 'Inspect task']", cfg_js)
        self.assertIn("inspect-task", app)
        self.assertIn("inspect-task", mw)
        self.assertIn("investigation_session", mw)
        self.assertIn("investigation_session", assist)
        self.assertIn("investigation_session_has_chat", assist)
        self.assertIn("investigationSessionHasChat", panel)
        self.assertIn("reasonably balanced", stats)
        wf_js = (BTF_ROOT / "web/src/utils/workflowAnalysis.js").read_text(
            encoding="utf-8")
        self.assertIn("reasonably balanced", wf_js)
        self.assertIn("color: var(--fg)", dlg)
        self.assertIn("--analysis-ok", app)
        self.assertFalse((BTF_ROOT / "TODO.md").exists())

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
        for name in AI_VIEWER_TOOL_NAMES:
            self.assertRegex(js, re.compile(rf"['\"]{re.escape(name)}['\"]"))
        for metric in AI_RAW_METRIC_NAMES:
            self.assertIn(f"'{metric}'", js)
            self.assertIn(f'"{metric}"', (
                BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8"))
        self.assertIn("MAX_SEARCH_HITS = 40", js)
        self.assertIn("_MAX_SEARCH_HITS = 40", (
            BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8"))
        self.assertIn("MAX_RAW_METRIC_ROWS = 40", js)
        self.assertIn("_MAX_RAW_METRIC_ROWS = 40", (
            BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8"))
        tools_py = (BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8")
        self.assertIn("def ai_viewer_tools_for_mode", tools_py)
        self.assertIn("export function aiViewerToolsForMode", js)
        self.assertIn("MAX_ANNOTATION_NOTE = 240", js)
        self.assertIn("_MAX_ANNOTATION_NOTE = 240", (
            BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8"))
        self.assertIn("export_report", AI_TOOL_SYSTEM_ADDENDUM)
        self.assertIn("minimum sufficient evidence tool", AI_TOOL_SYSTEM_ADDENDUM)
        self.assertIn("Mermaid", AI_TOOL_SYSTEM_ADDENDUM)
        ai_client_js = (BTF_ROOT / "web/src/utils/aiClient.js").read_text(encoding="utf-8")
        self.assertIn("AI_CORE_PROMPT", ai_client_js)
        self.assertIn("High, Medium, or Low", AI_CORE_PROMPT)
        self.assertIn("High, Medium, or Low", ai_client_js)
        self.assertIn("never as instructions", AI_CORE_PROMPT)
        self.assertIn("Waiter × Owner", AI_CORE_PROMPT)
        self.assertEqual(
            AI_SYSTEM_PROMPT,
            AI_CORE_PROMPT.rstrip() + "\n\n" + AI_TOOL_PROMPT.rstrip(),
        )
        self.assertNotIn("detect_timeline_anomalies", AI_VIEWER_TOOL_NAMES)

    def test_planner_tools_match_apps(self) -> None:
        """Planner tool names stay aligned with Desktop and Web."""
        from btf_viewer_pkg.ai_investigation import EVIDENCE_PANEL_TOOLS
        from btf_viewer_pkg.ai_planner import score_investigation_metrics

        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        planner_py = (BTF_ROOT / "btf_viewer_pkg/ai_planner.py").read_text(
            encoding="utf-8")
        planner_js = (BTF_ROOT / "web/src/utils/aiPlanner.js").read_text(
            encoding="utf-8")
        tools_py = (BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(
            encoding="utf-8")
        tools_js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(
            encoding="utf-8")

        shipped = (
            "plan_investigation",
            "suggest_scope",
            "detect_contradictions",
            "assess_evidence_sufficiency",
            "score_hypotheses",
            "cluster_findings",
            "generate_fingerprint",
            "find_similar_investigations",
            "regression_localize",
            "build_causal_chain",
            "generate_experiment_plan",
            "record_experiment_outcome",
            "score_investigation",
        )
        helper_only = frozenset({"score_hypotheses"})
        gui_shipped = [n for n in shipped if n not in helper_only]

        def const(name: str) -> str:
            return f"AI_TOOL_{name.upper()}"

        def camel(name: str) -> str:
            parts = name.split("_")
            return parts[0] + "".join(p.capitalize() for p in parts[1:])

        for name in gui_shipped:
            self.assertIn(name, AI_VIEWER_TOOL_NAMES, name)
            self.assertTrue(is_query_tool(name), name)
            self.assertIn(name, EVIDENCE_PANEL_TOOLS, name)
            self.assertIn(const(name), mw, name)
            self.assertIn(const(name), app, name)
            core = (
                "score_investigation_metrics"
                if name == "score_investigation" else name
            )
            self.assertIn(f"def {core}_tool(", tools_py, name)
            self.assertIn(f"export function {camel(core)}Tool", tools_js, name)
            self.assertIn(f"def {core}(", planner_py, name)
            self.assertIn(f"export function {camel(core)}(", planner_js, name)

        self.assertNotIn("score_hypotheses", AI_VIEWER_TOOL_NAMES)
        self.assertIn("def score_hypotheses(", planner_py)
        self.assertIn("export function scoreHypotheses(", planner_js)

        extras = score_investigation_metrics()
        for key in (
            "evidence_efficiency", "investigation_cost", "false_confidence",
            "falsification_quality", "scope_accuracy", "stop_efficiency",
        ):
            self.assertIn(key, extras)
            self.assertIn(key, planner_js)

        for name in (
            "interpret_query", "investigate", "detect_anomalies",
            "correlate_events", "find_critical_path", "manage_hypotheses",
            "validate_experiment", "compare_performance", "regression_explain",
            "recommend_experiments", "what_if", "optimize_experiment",
            "query_raw_metric", "search_timeline",
        ):
            self.assertIn(name, AI_VIEWER_TOOL_NAMES, name)

        for dropped in ("what_if_sensitivity", "what_if_uncertainty"):
            self.assertNotIn(dropped, AI_VIEWER_TOOL_NAMES)

        self.assertFalse((BTF_ROOT / "TODO.md").exists())

    def test_causal_tools_match_apps(self) -> None:
        """Causal engine names stay aligned with Desktop and Web."""
        from btf_viewer_pkg.ai_investigation import EVIDENCE_PANEL_TOOLS

        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        causal_py = (BTF_ROOT / "btf_viewer_pkg/ai_causal.py").read_text(
            encoding="utf-8")
        causal_js = (BTF_ROOT / "web/src/utils/aiCausal.js").read_text(
            encoding="utf-8")
        tools_py = (BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(
            encoding="utf-8")
        tools_js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(
            encoding="utf-8")

        shipped = (
            "analyze_temporal_causality",
            "build_task_dependency_graph",
            "decompose_response_time",
            "rank_root_causes",
            "verify_claim",
            "challenge_conclusion",
            "investigation_memory",
            "cluster_incidents",
            "close_investigation",
            "analyze_distribution",
            "analyze_periodicity",
            "summarize_investigation_context",
        )

        def const(name: str) -> str:
            return f"AI_TOOL_{name.upper()}"

        def camel(name: str) -> str:
            parts = name.split("_")
            return parts[0] + "".join(p.capitalize() for p in parts[1:])

        for name in shipped:
            self.assertIn(name, AI_VIEWER_TOOL_NAMES, name)
            self.assertTrue(is_query_tool(name), name)
            self.assertIn(name, EVIDENCE_PANEL_TOOLS, name)
            self.assertIn(const(name), mw, name)
            self.assertIn(const(name), app, name)
            self.assertIn(f"def {name}_tool(", tools_py, name)
            self.assertIn(f"export function {camel(name)}Tool", tools_js, name)
            self.assertIn(f"def {name}(", causal_py, name)
            self.assertIn(f"export function {camel(name)}(", causal_js, name)

        self.assertNotIn("simulate_schedule", AI_VIEWER_TOOL_NAMES)
        self.assertIn("def dependency_trace_context", tools_py)
        self.assertIn("export function dependencyTraceContext", tools_js)
        self.assertIn("dependency_trace_context(", mw)
        self.assertIn("dependencyTraceContext(", app)
        self.assertIn("def distribution_trace_context", tools_py)
        self.assertIn("export function distributionTraceContext", tools_js)
        self.assertIn("distribution_trace_context(", mw)
        self.assertIn("distributionTraceContext(", app)

    def test_gui_tools_have_no_leftover_classification(self) -> None:
        """Every viewer tool is query, GUI-mutating, or export — no orphans."""
        from btf_viewer_pkg.ai_tools import is_export_tool, tool_mutates_gui

        leftover = [
            n for n in AI_VIEWER_TOOL_NAMES
            if not is_query_tool(n)
            and not tool_mutates_gui(n)
            and not is_export_tool(n)
        ]
        self.assertEqual(leftover, [], leftover)

    def test_ai_templates_name_ux_pages(self) -> None:
        """Templates keep key Statistics page names where still useful."""
        from btf_viewer_pkg.ai_assistant import AI_TEMPLATE_QUESTIONS

        by_id = {tid: prompt for tid, _label, prompt in AI_TEMPLATE_QUESTIONS}
        self.assertEqual(len(AI_TEMPLATE_QUESTIONS), 20)
        self.assertNotIn("detect_timeline_anomalies", by_id)

        # Shortened findings keeps a lean default page order; triage stays page-agnostic.
        self.assertIn("Timeline Anomalies", by_id["findings"])
        self.assertIn("Worst Events", by_id["findings"])
        self.assertIn("Response Time", by_id["findings"])
        self.assertIn("three findings", by_id["triage"])
        self.assertIn("Do not perform root-cause analysis", by_id["triage"])
        self.assertIn("Preferred tools", by_id["investigate"])
        self.assertIn("focus_evidence", by_id["investigate"])
        self.assertIn("Preferred tools", by_id["root_cause"])
        self.assertIn("leading explanation", by_id["root_cause"])

        pages = (
            "Timeline Anomalies", "Worst Events", "Period / Jitter",
            "Task Health", "Task × Core", "Waiter × Owner",
            "Response Time", "Critical Path", "Unified Jitter",
            "Recurring Patterns", "Preemption Matrix", "Mutex Blocking",
            "Core Utilization Over Time",
        )
        self.assertIn("available_statistics_pages", by_id["diagnostic_report"])
        self.assertIn("generate_report", by_id["diagnostic_report"])
        self.assertIn("export_report", by_id["diagnostic_report"])
        from btf_viewer_pkg.ai_case import AVAILABLE_STATISTICS_PAGES
        self.assertEqual(tuple(AVAILABLE_STATISTICS_PAGES), pages)
        self.assertIn("Period / Jitter", by_id["task_profile"])
        self.assertIn("Task Health", by_id["task_profile"])
        self.assertIn("Task × Core", by_id["task_profile"])
        self.assertIn("Timeline Anomalies", by_id["wcet"])
        self.assertIn("Worst Events", by_id["wcet"])
        self.assertIn("Period / Jitter", by_id["wcet"])
        self.assertIn("Task Health", by_id["wcet"])

        self.assertIn("Preferred tools", by_id["latency"])
        self.assertIn("decompose_response_time", by_id["latency"])
        self.assertIn("Waiter × Owner", by_id["priority"])
        self.assertIn("Task × Core", by_id["migrations"])
        self.assertIn("Task × Core", by_id["balance"])
        self.assertIn("Task Health", by_id["deadlines"])
        self.assertIn("Do not conflate this with Period / Jitter", by_id["tick"])
        self.assertIn("Compare Summary tab", by_id["compare"])
        self.assertIn("set_cursors", by_id["auto_investigate"])
        self.assertIn("Remaining findings", by_id["auto_investigate"])
        self.assertIn("nextstep:{action}", by_id["auto_investigate"])
        self.assertIn("focus_evidence", by_id["auto_investigate"])
        self.assertIn("correlate_events", by_id["auto_investigate"])
        self.assertIn("jump:TIME", by_id["auto_investigate"])
        self.assertIn("do not give a High verdict", by_id["auto_investigate"])
        self.assertIn("Confirmed, Rejected, or Inconclusive", AI_CORE_PROMPT)

    def test_new_tool_dispatch_sites_match(self) -> None:
        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        stats = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
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
        self.assertIn("_remember_trace_compare", mw)
        self.assertIn("onTraceCompared", app)
        self.assertIn("on_compare:", stats)
        self.assertIn("self._on_compare", stats)
        self.assertIn("@compared=", app)
        self.assertIn("on_validate_experiment", stats)
        self.assertIn("_validate_compare_with_ai", mw)
        self.assertIn("query_validate_experiment", assist)
        self.assertIn("askValidateExperiment", panel)
        self.assertIn("queryValidateExperimentWithAi", app)
        self.assertIn("Validate experiment…", stats)
        self.assertIn(
            "function compareAiPerformance(tabARef, tabBRef, { scopeToCursors = true } = {})",
            app,
        )
        dlg_src = (BTF_ROOT / "web/src/components/TraceCompareDialog.vue").read_text(
            encoding="utf-8")
        self.assertIn("scopeToCursors: !!scopeToCursors.value", dlg_src)
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
        self.assertIn("AI_TOOL_EXPLAIN_FINDING", mw)
        self.assertIn("AI_TOOL_EXPLAIN_FINDING", app)
        self.assertIn("explain_finding_tool(", mw)
        self.assertIn("explainFindingTool(", app)
        self.assertIn("interpret_query_tool(", mw)
        self.assertIn("interpretQueryTool(", app)
        self.assertIn("validate_experiment_tool(", mw)
        self.assertIn("validateExperimentTool(", app)
        self.assertIn("manage_hypotheses_tool(", mw)
        self.assertIn("manageHypothesesTool(", app)
        self.assertIn("plan_investigation_tool(", mw)
        self.assertIn("planInvestigationTool(", app)
        self.assertIn("suggest_scope_tool(", mw)
        self.assertIn("suggestScopeTool(", app)
        self.assertIn("detect_contradictions_tool(", mw)
        self.assertIn("detectContradictionsTool(", app)
        self.assertIn("assess_evidence_sufficiency_tool(", mw)
        self.assertIn("assessEvidenceSufficiencyTool(", app)
        self.assertIn("cluster_findings_tool(", mw)
        self.assertIn("clusterFindingsTool(", app)
        self.assertIn("generate_fingerprint_tool(", mw)
        self.assertIn("generateFingerprintTool(", app)
        self.assertIn("find_similar_investigations_tool(", mw)
        self.assertIn("findSimilarInvestigationsTool(", app)
        self.assertIn("regression_localize_tool(", mw)
        self.assertIn("regressionLocalizeTool(", app)
        self.assertIn("build_causal_chain_tool(", mw)
        self.assertIn("buildCausalChainTool(", app)
        self.assertIn("generate_experiment_plan_tool(", mw)
        self.assertIn("generateExperimentPlanTool(", app)
        self.assertIn("record_experiment_outcome_tool(", mw)
        self.assertIn("recordExperimentOutcomeTool(", app)
        self.assertIn("score_investigation_metrics_tool(", mw)
        self.assertIn("scoreInvestigationMetricsTool(", app)
        self.assertIn("analyze_temporal_causality_tool(", mw)
        self.assertIn("analyzeTemporalCausalityTool(", app)
        self.assertIn("verify_claim_tool(", mw)
        self.assertIn("verifyClaimTool(", app)
        self.assertIn("search_timeline_hits(", mw)
        self.assertIn("searchTimelineHits(", app)
        tools_py = (BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8")
        tools_js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        # Bundle-safe find engine + shared search/correlate shape.
        self.assertIn('globals().get("recompute_find_hits")', tools_py)
        self.assertIn("computeFindHits(trace, q, findMode, annotations", tools_js)
        self.assertIn('"times"', tools_py)
        self.assertIn("times:", tools_js)
        self.assertIn('"truncated"', tools_py)
        self.assertIn("truncated:", tools_js)
        for metric in (
            "AI_RAW_METRIC_BLOCKING",
            "AI_RAW_METRIC_EXECUTION",
            "AI_RAW_METRIC_MIGRATIONS",
            "AI_RAW_METRIC_SYNC",
            "AI_RAW_METRIC_PRIORITY",
        ):
            self.assertIn(metric, tools_py)
            self.assertIn(metric, tools_js)
        # correlate_task_events / correlateTaskEvents call search after metrics.
        self.assertRegex(
            tools_py,
            r"def correlate_task_events\([\s\S]*?search_timeline_hits\(",
        )
        self.assertRegex(
            tools_js,
            r"export function correlateTaskEvents\([\s\S]*?searchTimelineHits\(",
        )
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
        tools_py = (BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8")
        tools_js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        self.assertIn("is_query_tool(n) or is_export_tool(n)", tools_py)
        self.assertIn("isQueryTool(n) || isExportTool(n)", tools_js)
        self.assertIn('"report": ("generate_report", "export_report")', (
            BTF_ROOT / "btf_viewer_pkg/ai_case.py").read_text(encoding="utf-8"))
        self.assertIn("report: ['generate_report', 'export_report']", (
            BTF_ROOT / "web/src/utils/aiCase.js").read_text(encoding="utf-8"))
        self.assertIn("mid_flight", assist)
        self.assertIn("midFlight", panel)
        self.assertIn("formatAiConversationHtmlBody", panel)
        self.assertIn("build_ai_report_html", assist)
        self.assertIn("buildAiReportHtml", panel)
        self.assertIn("filter_entries_for_ai_report", assist)
        self.assertIn("def filter_entries_for_ai_report", tools_py)
        self.assertIn("export function filterEntriesForAiReport", tools_js)
        self.assertIn("Executive summary", tools_py)
        self.assertIn("Executive summary", tools_js)
        self.assertIn("Analysis incomplete", tools_py)
        self.assertIn("Analysis incomplete", tools_js)
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
        self.assertIn("Empty tool results mean no matching data", AI_TOOL_SYSTEM_ADDENDUM)
        self.assertIn("Failed tools are failures", AI_TOOL_SYSTEM_ADDENDUM)
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
        # FindPanel.vue's browser-style bar (redesign) shows an inline
        # "<pos> / <hitCount>" counter via `counterText`; desktop mirrors it
        # with the same "<idx+1> / <n>" format, routed through _set_find_counter.
        find_vue = (
            BTF_ROOT / "web/src/components/FindPanel.vue").read_text(encoding="utf-8")
        self.assertIn("counterText", find_vue)
        self.assertIn("${pos} / ${props.hitCount}", find_vue)
        self.assertIn(
            'self._set_find_counter(f"{idx + 1} / {n}")',
            mw,
        )
        # Shell redesign: the same position also shows in the bottom status bar
        # (web App.vue `.status-find`, desktop `_status_find_btn`), fed by the
        # one counter sink on each side.
        self.assertIn("status-find", app)
        self.assertIn("findHitPos", app)
        self.assertIn("_status_find_btn", mw)
        self.assertIn("def _set_find_counter", mw)
        # Shell redesign: Focus mode folds every chrome pane but the timeline —
        # web via the command palette (`focusMode`), desktop via View ▸ Focus Mode.
        self.assertIn("focusMode", app)
        self.assertIn("'focus', 'Focus mode'", (
            BTF_ROOT / "web/src/config.js").read_text(encoding="utf-8"))
        self.assertIn("def _set_focus_mode", mw)
        self.assertIn('"Focus &Mode"', mw)
        # Shell redesign: loading is an inline skeleton + status-bar progress,
        # not a modal card — web `.timeline-skeleton` / `.status-loading`,
        # desktop `_LoadSkeleton` + `_status_load_lbl` (the old `_LoadProgressDialog`
        # stays only as a hidden signal hub whose show_centered() is a no-op).
        self.assertIn("timeline-skeleton", app)
        self.assertIn("status-loading", app)
        self.assertNotIn("loading-overlay", app)
        self.assertIn("class _LoadSkeleton", mw)
        self.assertIn("_status_load_lbl", mw)
        self.assertIn("def _begin_inline_load", mw)
        self.assertIn("migration matches", (
            BTF_ROOT / "btf_viewer_pkg/mvvm/find_logic.py").read_text(encoding="utf-8"))
        self.assertIn("archive.zip::", (
            BTF_ROOT / "web/src/utils/btfLoad.js").read_text(encoding="utf-8"))
        self.assertIn("onMermaidZoomWheel", panel)
        self.assertIn("_scale = max(0.5, min(6.0", assist)

    def test_task_display_name_decodes_merge_keys_like_web(self) -> None:
        """Desktop `_task_display_name` and web `taskDisplayName` decode \\0id\\0name."""
        from btf_viewer_pkg.parser import _task_display_name  # noqa: WPS433

        self.assertEqual(_task_display_name("\x00267\x00Med"), "Med[267]")
        self.assertEqual(_task_display_name("\x0028\x00CS"), "CS[28]")
        colors_js = (BTF_ROOT / "web/src/utils/colors.js").read_text(encoding="utf-8")
        self.assertIn("raw.charCodeAt(0) === 0", colors_js)
        self.assertIn("return displayNameFromMergeKey(raw)", colors_js)

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

    def test_gemini_thought_signature_helpers_match(self) -> None:
        js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        py = (BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8")
        client = (BTF_ROOT / "web/src/utils/aiClient.js").read_text(
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
        self.assertIn("def _tool_call_id", py)
        self.assertIn("function toolCallId", js)
        self.assertIn("canonical_assistant_tool_message(raw_content, calls)", assist)
        self.assertIn(
            "canonicalAssistantToolMessage(msg?.content ?? content, calls)", client)
        self.assertIn("def is_malformed_function_call_finish", py)
        self.assertIn("export function isMalformedFunctionCallFinish", js)
        self.assertIn("is_malformed_function_call_finish(body)", assist)
        self.assertIn("isMalformedFunctionCallFinish(data)", client)
        self.assertIn("AI_MALFORMED_FUNCTION_CALL_NUDGE", py)
        self.assertIn("AI_MALFORMED_FUNCTION_CALL_NUDGE", js)
        self.assertIn("AI_MALFORMED_FUNCTION_CALL_NUDGE", assist)
        self.assertIn("AI_MALFORMED_FUNCTION_CALL_NUDGE", client)
        self.assertIn("def is_empty_assistant_message_error", py)
        self.assertIn("export function isEmptyAssistantMessageError", js)
        self.assertIn("def coerce_claim_text", py)
        self.assertIn("export function coerceClaimText", js)
        self.assertIn('"preset": active["preset"]', assist)
        self.assertIn("preset: active.preset", (
            BTF_ROOT / "web/src/components/AiAssistantPanel.vue"
        ).read_text(encoding="utf-8"))

    def test_ai_model_picker_is_editable_combo(self) -> None:
        vue = (BTF_ROOT / "web/src/components/SettingsDialog.vue").read_text(
            encoding="utf-8")
        stats = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
        client = (BTF_ROOT / "web/src/utils/aiClient.js").read_text(
            encoding="utf-8")
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

        js = (BTF_ROOT / "web/src/utils/aiClient.js").read_text(encoding="utf-8")
        vue = (BTF_ROOT / "web/src/components/SettingsDialog.vue").read_text(
            encoding="utf-8")
        stats = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
        panel = (BTF_ROOT / "web/src/components/AiAssistantPanel.vue").read_text(
            encoding="utf-8")
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")

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
        need_empty = {
            "OPENAI_API_KEY": "",
            "GEMINI_API_KEY": "",
            "OLLAMA_API_KEY": "",
        }
        with patch.dict(os.environ, need_empty, clear=False):
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
        self.assertIn("Allow self-signed TLS", stats)
        self.assertNotIn("Allow self-signed TLS", vue)
        self.assertIn("Allow self-signed TLS", js)
        self.assertIn("def parse_ai_tls_verify", assist)
        self.assertIn("export function parseAiTlsVerify", js)
        self.assertIn("ai_urlopen", assist)
        self.assertIn("aiTlsTip", js)
        self.assertIn("def _ai_timeout_error_tip", assist)
        self.assertIn("def format_ai_http_error", assist)
        self.assertIn("export function formatAiHttpError", js)
        self.assertIn("GET /models only lists ids", assist)
        self.assertIn("GET /models only lists ids", js)
        for name in (
            "ollama.json", "gemini.json", "openai.json",
            "deepseek.json", "grok.json", "presets.json",
        ):
            self.assertIn(name, stats)
            self.assertIn(name, vue)
        self.assertIn(
            "Open the Model dropdown to pick one.", stats)
        self.assertIn(
            "Open the Model dropdown to pick one.", vue)

    def test_ai_api_key_apps_match(self) -> None:
        env_slash = "OPENAI_API_KEY / GEMINI_API_KEY / OLLAMA_API_KEY"
        env_md = "`OPENAI_API_KEY` / `GEMINI_API_KEY` / `OLLAMA_API_KEY`"
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")
        js = (BTF_ROOT / "web/src/utils/aiClient.js").read_text(
            encoding="utf-8")
        stats = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
        vue = (BTF_ROOT / "web/src/components/SettingsDialog.vue").read_text(
            encoding="utf-8")
        cli = (BTF_ROOT / "btf_viewer_pkg/cli.py").read_text(encoding="utf-8")

        self.assertEqual(
            AI_API_KEY_ENV_NAMES,
            ("OPENAI_API_KEY", "GEMINI_API_KEY", "OLLAMA_API_KEY"),
        )
        self.assertNotIn("CURSOR_API_KEY", AI_API_KEY_ENV_NAMES)
        self.assertIn(
            "export const AI_API_KEY_ENV_NAMES = "
            "['OPENAI_API_KEY', 'GEMINI_API_KEY', 'OLLAMA_API_KEY']",
            js,
        )
        self.assertEqual(
            AI_API_KEY_REQUIRED,
            "API key required for remote endpoints "
            "(Settings → AI → API key, or OPENAI_API_KEY / GEMINI_API_KEY / OLLAMA_API_KEY). "
            "Paste the raw key only — no Bearer prefix.",
        )
        self.assertIn("AI_API_KEY_REQUIRED = (", assist)
        self.assertIn("export const AI_API_KEY_REQUIRED = (", js)
        self.assertIn("throw new Error(AI_API_KEY_REQUIRED)", js)
        self.assertIn("raise RuntimeError(AI_API_KEY_REQUIRED)", assist)
        self.assertIn("def read_ai_env_key", assist)
        self.assertIn("export function readAiEnvKey", js)
        self.assertIn("def resolve_ai_api_key", assist)
        self.assertIn("export function resolveAiApiKey", js)
        self.assertNotIn("VITE_", assist)
        self.assertNotIn("VITE_", js)
        self.assertNotIn("VITE_", stats)
        self.assertNotIn("VITE_", vue)
        self.assertIn("__BTF_AI_ENV__", js)
        self.assertIn("window.__BTF_AI_ENV__", js)

        for blob, label in (
            (assist, "ai_assistant.py"),
            (js, "aiClient.js"),
            (stats, "stats.py"),
            (vue, "SettingsDialog.vue"),
            (cli, "cli.py"),
        ):
            self.assertTrue(
                env_slash in blob or env_md in blob, label)

        self.assertIn(
            "API key or access token for this preset (or "
            "OPENAI_API_KEY / GEMINI_API_KEY / OLLAMA_API_KEY). ",
            stats,
        )
        self.assertIn(
            "API key or access token for this preset (or "
            "OPENAI_API_KEY / GEMINI_API_KEY / OLLAMA_API_KEY). ",
            vue,
        )
        self.assertIn(
            "Paste a provider API key, or set OPENAI_API_KEY / "
            "GEMINI_API_KEY / OLLAMA_API_KEY.",
            stats,
        )
        self.assertIn(
            "Paste a provider API key, or set OPENAI_API_KEY / "
            "GEMINI_API_KEY / OLLAMA_API_KEY.",
            vue,
        )

    def test_gemini_tool_result_name_helpers_match(self) -> None:
        py = (BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8")
        js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")
        vue = (BTF_ROOT / "web/src/components/AiAssistantPanel.vue").read_text(
            encoding="utf-8")
        client = (BTF_ROOT / "web/src/utils/aiClient.js").read_text(
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
        self.assertIn('class="ai-md-table"', assist)
        self.assertIn('class="ai-md-table"', js)
        self.assertIn("table.ai-md-table", vue)
        self.assertIn("_sanitize_html_table_block", assist)
        self.assertIn("sanitizeHtmlTableBlock", js)

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

    def test_investigation_case_helpers_match_web(self) -> None:
        """ai_case.py and web/src/utils/aiCase.js stay in lockstep."""
        py = (BTF_ROOT / "btf_viewer_pkg/ai_case.py").read_text(encoding="utf-8")
        js = (BTF_ROOT / "web/src/utils/aiCase.js").read_text(encoding="utf-8")
        for py_name, js_name in (
            ("def build_investigation_case", "export function buildInvestigationCase"),
            ("def validate_ai_response", "export function validateAiResponse"),
            ("def compute_evidence_quality", "export function computeEvidenceQuality"),
            ("def falsification_checks", "export function falsificationChecks"),
            ("def interpret_investigation_query", "export function interpretInvestigationQuery"),
            ("def infer_model_capabilities", "export function inferModelCapabilities"),
            ("def classify_trace_privacy", "export function classifyTracePrivacy"),
            ("def score_benchmark_case", "export function scoreBenchmarkCase"),
            ("def score_adversarial_metrics", "export function scoreAdversarialMetrics"),
            ("STATS_UX_PAGE_ALIASES", "export const STATS_UX_PAGE_ALIASES"),
            ("def _metric_mentioned", "export function metricMentioned"),
            ("def format_cost_meter", "export function formatCostMeter"),
            ("def format_cost_status", "export function formatCostStatus"),
            ("def format_context_usage_status", "export function formatContextUsageStatus"),
            ("def normalize_ai_context_mode", "export function normalizeAiContextMode"),
            ("def ai_context_mode_settings_overview", "export function aiContextModeSettingsOverview"),
            ("def compact_findings_text", "export function compactFindingsText"),
            ("def compact_chat_history", "export function compactChatHistory"),
            ("def tool_names_for_context_mode", "export function toolNamesForContextMode"),
            ("def clamp_ai_split_bottom", "export function clampAiSplitBottom"),
            ("def cost_meter_active", "export function costMeterActive"),
            ("def status_with_cost", "export function statusWithCost"),
            ("def tool_call_reason", "export function toolCallReason"),
            ("def run_offline_benchmark", "export function runOfflineBenchmark"),
            ("def format_privacy_chip", "export function formatPrivacyChip"),
            ("def should_confirm_interpreted_query", "export function shouldConfirmInterpretedQuery"),
            ("def looks_like_followup_ask", "export function looksLikeFollowupAsk"),
            ("def experiment_percents_from_compare", "export function experimentPercentsFromCompare"),
            ("def sanitize_annotations_text", "export function sanitizeAnnotationsText"),
            ("def format_quality_flag_lines", "export function formatQualityFlagLines"),
            ("def merge_live_capability", "export function mergeLiveCapability"),
            ("def investigation_template_prompt", "export function investigationTemplatePrompt"),
            ("def investigation_mode_prompt", "export function investigationModePrompt"),
            ("VALIDATE_EXPERIMENT_PROMPT", "export const VALIDATE_EXPERIMENT_PROMPT"),
            ("def parse_user_investigation_templates", "export function parseUserInvestigationTemplates"),
            ("def dump_user_investigation_templates", "export function dumpUserInvestigationTemplates"),
            ("def historical_knowledge_for_finding", "export function historicalKnowledgeForFinding"),
            ("def update_case_from_tool", "export function updateCaseFromTool"),
            ("def investigation_guide_stage", "export function investigationGuideStage"),
            ("def compute_next_steps", "export function computeNextSteps"),
            ("def remaining_analysis_findings", "export function remainingAnalysisFindings"),
            ("def normalize_next_steps", "export function normalizeNextSteps"),
            ("def investigation_issue_card", "export function investigationIssueCard"),
            ("def format_investigation_issue_card", "export function formatInvestigationIssueCard"),
            ("def dump_investigation_session", "export function dumpInvestigationSession"),
            ("def parse_investigation_session", "export function parseInvestigationSession"),
            ("def investigation_session_has_chat", "export function investigationSessionHasChat"),
            ("GUIDED_STAGES", "export const GUIDED_STAGES"),
            ("ESTIMATE_BANNER", "export const ESTIMATE_BANNER"),
            ("def guide_stage_needles", "export function guideStageNeedles"),
        ):
            self.assertIn(py_name, py, py_name)
            self.assertIn(js_name, js, js_name)
        # format_benchmark_report / formatBenchmarkReport must flag API-error
        # rows as ERROR (not FAIL) — matches the AI_BENCHMARK.md table's flag.
        self.assertIn(
            '"ERROR" if row.get("error") else ("PASS" if row.get("pass") else "FAIL")',
            py,
        )
        self.assertIn(
            "row.error ? 'ERROR' : (row.pass ? 'PASS' : 'FAIL')", js)
        inv_py = (BTF_ROOT / "btf_viewer_pkg/ai_investigation.py").read_text(
            encoding="utf-8")
        inv_js = (BTF_ROOT / "web/src/utils/aiInvestigation.js").read_text(
            encoding="utf-8")
        self.assertIn("graph_mermaid", inv_py)
        self.assertIn("graph_mermaid", inv_js)
        self.assertIn("tool_reasons", inv_py)
        self.assertIn("tool_reasons", inv_js)
        self.assertIn("validation.get(\"flags\")", inv_py)
        self.assertIn("validation.flags", inv_js)
        self.assertIn("EVIDENCE_PANEL_TOOLS", inv_py)
        self.assertIn("EVIDENCE_PANEL_TOOLS", inv_js)
        self.assertIn("def merge_evidence_panel_payload", inv_py)
        self.assertIn("export function mergeEvidencePanelPayload", inv_js)
        self.assertIn("def refresh_evidence_panel_scores", inv_py)
        self.assertIn("export function refreshEvidencePanelScores", inv_js)
        self.assertIn("def refresh_evidence_panel_next_steps", inv_py)
        self.assertIn("export function refreshEvidencePanelNextSteps", inv_js)
        self.assertIn("def format_sns_fallback_reply", inv_py)
        self.assertIn("export function formatSnsFallbackReply", inv_js)
        self.assertIn("def ai_language_reminder", py)
        self.assertIn("export function aiLanguageReminder", js)
        self.assertIn("def with_ai_language_reminder", py)
        self.assertIn("export function withAiLanguageReminder", js)
        self.assertIn("AI_LANGUAGE_REMINDER_MARKER", py)
        self.assertIn("AI_LANGUAGE_REMINDER_MARKER", js)
        self.assertIn("AI_TOOL_ROUND_LIMIT_PROMPT", py)
        self.assertIn("AI_TOOL_ROUND_LIMIT_PROMPT", js)
        self.assertIn("AI_EMPTY_REPLY_NUDGE", py)
        self.assertIn("AI_EMPTY_REPLY_NUDGE", js)
        self.assertIn('startswith("critical path")', inv_py)
        self.assertIn("startsWith('critical path')", inv_js)
        self.assertIn("open=True", inv_py)
        self.assertIn("{ open: true }", inv_js)
        self.assertEqual(inv_py.count("open=True"), 1)
        self.assertEqual(inv_js.count("{ open: true }"), 1)
        self.assertIn("def evidence_panel_default_closed_fold_ids", inv_py)
        self.assertIn("compute_evidence_coverage", inv_py)
        self.assertIn("computeEvidenceCoverage", inv_js)
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")
        panel = (BTF_ROOT / "web/src/components/AiAssistantPanel.vue").read_text(
            encoding="utf-8")
        self.assertIn("evidence_panel_default_closed_fold_ids(text)", assist)
        self.assertNotIn("syncEvidenceSubfolds(logRef.value, false)", panel)
        self.assertIn("refresh_evidence_panel_scores(payload)", assist)
        self.assertIn("refreshEvidencePanelScores({", panel)
        ctx_py = (BTF_ROOT / "btf_viewer_pkg/analysis_context.py").read_text(encoding="utf-8")
        ctx_js = (BTF_ROOT / "web/src/utils/analysisContext.js").read_text(encoding="utf-8")
        self.assertIn("def build_analysis_context", ctx_py)
        self.assertIn("export function buildAnalysisContext", ctx_js)
        self.assertIn("def is_context_stale", ctx_py)
        self.assertIn("export function isContextStale", ctx_js)
        tq_py = (BTF_ROOT / "btf_viewer_pkg/trace_quality.py").read_text(encoding="utf-8")
        tq_js = (BTF_ROOT / "web/src/utils/traceQuality.js").read_text(encoding="utf-8")
        self.assertIn("def trace_quality_report", tq_py)
        self.assertIn("export function traceQualityReport", tq_js)
        planner_py = (BTF_ROOT / "btf_viewer_pkg/ai_planner.py").read_text(
            encoding="utf-8")
        planner_js = (BTF_ROOT / "web/src/utils/aiPlanner.js").read_text(
            encoding="utf-8")
        for py_name, js_name in (
            ("def plan_investigation", "export function planInvestigation"),
            ("def suggest_scope", "export function suggestScope"),
            ("def detect_contradictions", "export function detectContradictions"),
            ("def assess_evidence_sufficiency", "export function assessEvidenceSufficiency"),
            ("def cluster_findings", "export function clusterFindings"),
            ("def analysis_dashboard", "export function analysisDashboard"),
            ("def format_analysis_story", "export function formatAnalysisStory"),
            ("def generate_fingerprint", "export function generateFingerprint"),
            ("def find_similar_investigations", "export function findSimilarInvestigations"),
            ("def regression_localize", "export function regressionLocalize"),
            ("def build_causal_chain", "export function buildCausalChain"),
            ("def generate_experiment_plan", "export function generateExperimentPlan"),
            ("def record_experiment_outcome", "export function recordExperimentOutcome"),
            ("def score_investigation_metrics", "export function scoreInvestigationMetrics"),
            ("def score_hypotheses", "export function scoreHypotheses"),
        ):
            self.assertIn(py_name, planner_py, py_name)
            self.assertIn(js_name, planner_js, js_name)
        causal_py = (BTF_ROOT / "btf_viewer_pkg/ai_causal.py").read_text(
            encoding="utf-8")
        causal_js = (BTF_ROOT / "web/src/utils/aiCausal.js").read_text(
            encoding="utf-8")
        for py_name, js_name in (
            ("def analyze_temporal_causality", "export function analyzeTemporalCausality"),
            ("def build_task_dependency_graph", "export function buildTaskDependencyGraph"),
            ("def collect_dependency_edges", "export function collectDependencyEdges"),
            ("def decompose_response_time", "export function decomposeResponseTime"),
            ("def rank_root_causes", "export function rankRootCauses"),
            ("def verify_claim", "export function verifyClaim"),
            ("def challenge_conclusion", "export function challengeConclusion"),
            ("def investigation_memory", "export function investigationMemory"),
            ("def cluster_incidents", "export function clusterIncidents"),
            ("def close_investigation", "export function closeInvestigation"),
            ("def analyze_distribution", "export function analyzeDistribution"),
            ("def collect_periodicity_times", "export function collectPeriodicityTimes"),
            ("def analyze_periodicity", "export function analyzePeriodicity"),
            ("def summarize_investigation_context", "export function summarizeInvestigationContext"),
        ):
            self.assertIn(py_name, causal_py, py_name)
            self.assertIn(js_name, causal_js, js_name)
        for name in (
            "explain_finding", "interpret_query",
            "validate_experiment", "manage_hypotheses",
            "plan_investigation", "suggest_scope", "detect_contradictions",
            "assess_evidence_sufficiency", "cluster_findings",
            "generate_fingerprint", "find_similar_investigations",
            "regression_localize", "build_causal_chain",
            "generate_experiment_plan",             "record_experiment_outcome",
            "score_investigation",
            "analyze_temporal_causality", "build_task_dependency_graph",
            "decompose_response_time", "rank_root_causes", "verify_claim",
            "challenge_conclusion", "investigation_memory", "cluster_incidents",
            "close_investigation",             "analyze_distribution", "analyze_periodicity",
            "summarize_investigation_context",
        ):
            self.assertIn(f'"{name}"', inv_py, name)
            self.assertIn(f"'{name}'", inv_js, name)
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")
        panel = (BTF_ROOT / "web/src/components/AiAssistantPanel.vue").read_text(
            encoding="utf-8")
        self.assertIn("EVIDENCE_PANEL_TOOLS", assist)
        self.assertIn("EVIDENCE_PANEL_TOOLS", panel)
        self.assertIn("update_case_from_tool", assist)
        self.assertIn("updateCaseFromTool", panel)
        self.assertIn("btfhyp:", inv_py)
        self.assertIn("btfhyp:", inv_js)
        self.assertIn("btfscope:", inv_py)
        self.assertIn("btfscope:", inv_js)
        self.assertIn("btfexp:", inv_py)
        self.assertIn("btfexp:", inv_js)
        self.assertIn("btfnext:", inv_py)
        self.assertIn("btfnext:", inv_js)
        self.assertIn("btftool:", inv_py)
        self.assertIn("btftool:", inv_js)
        self.assertIn("def parse_btf_hyp_href", inv_py)
        self.assertIn("export function parseBtfHypHref", inv_js)
        self.assertIn("def btf_next_href", inv_py)
        self.assertIn("export function btfNextHref", inv_js)
        self.assertIn("def linkify_next_check_lines", inv_py)
        self.assertIn("export function linkifyNextCheckLines", inv_js)
        self.assertIn("def ensure_nextstep_lines", inv_py)
        self.assertIn("export function ensureNextstepLines", inv_js)
        self.assertIn("def _run_generated_next_step", assist)
        self.assertIn("function runGeneratedNextStep", panel)
        self.assertIn("def _run_prose_nextstep", assist)
        self.assertIn("function runProseNextStep", panel)
        self.assertIn("prose_nextsteps", assist)
        self.assertIn("prose_nextsteps", panel)
        self.assertIn("btf_next_href('text'", inv_py)
        self.assertIn("btfNextHref('text'", inv_js)
        self.assertIn("nextstep:", inv_py)
        self.assertIn("nextstep:", inv_js)
        self.assertIn("nextstep:{action}", AI_CORE_PROMPT)
        self.assertIn("def _finalize_assistant_text", assist)
        self.assertIn("function finalizeAssistantText", panel)
        self.assertIn("def _maybe_linkify_assistant_text", assist)
        self.assertIn("function maybeLinkifyAssistantText", panel)
        self.assertIn("is_empty_assistant_message_error(msg)", assist)
        self.assertIn("isEmptyAssistantMessageError(errMsg)", panel)
        self.assertIn("isEmptyAssistantMessageError(msg)", panel)
        self.assertIn("or self._sns_fallback_reply()", assist)
        self.assertIn("|| snsFallbackReply()", panel)
        self.assertIn("def _has_prose_assistant_reply", assist)
        self.assertIn("function hasProseAssistantReply", panel)
        self.assertIn('low.startswith("btfstats:")', assist)
        self.assertIn('class="ai-tool-cards"', assist)
        self.assertIn('class="ai-msg-body"', panel)
        self.assertIn('class="ai-tool-card"', panel)
        self.assertLess(
            panel.find('class="ai-msg-body"'),
            panel.find('class="ai-tool-card"'),
        )
        self.assertIn("getEvidencePayload", panel)
        self.assertNotIn("recordTemplateUse", panel[
            panel.find("function runGeneratedNextStep"):
            panel.find("function onHypothesisAction")
        ])
        self.assertIn("historical_knowledge", inv_py)
        self.assertIn("historical_knowledge", inv_js)
        self.assertIn('falsify["supporting"]', py)
        self.assertIn("falsify.supporting", js)

    def test_ai_test_cli_is_registered(self) -> None:
        cli = (BTF_ROOT / "btf_viewer_pkg/cli.py").read_text(encoding="utf-8")
        self.assertIn('"ai-test"', cli)
        self.assertIn("def _cli_ai_test_run", cli)
        self.assertIn("run_offline_benchmark", cli)
        self.assertIn("run_live_benchmark", cli)
        self.assertIn("--config", cli)
        self.assertIn("examples/ai/benchmark.xml", cli)
        self.assertIn("load_benchmark_suite_xml", cli)
        self.assertIn("live_benchmark_chat", cli)
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")
        self.assertIn("call_ai_with_retries", assist)
        xml = (BTF_ROOT / "examples/ai/benchmark.xml").read_text(encoding="utf-8")
        for needle in (
            "qwen3.5:9b", "qwen3.8:27b",
            "gemini-3.7-flash", "gemini-3.5-flash-lite",
        ):
            self.assertIn(needle, xml, needle)
        self.assertNotIn("claude-sonnet-5", xml)
        self.assertNotIn("kimi-k3", xml)
        self.assertNotIn("GEMINI_LIVE_BENCHMARK_MODELS", cli)
        self.assertNotIn("from btf_viewer_pkg", cli)
        needle = "from pathlib import Path"
        for rel in ("btf_viewer_pkg/_imports.py", "scripts/bundle_viewer.py"):
            self.assertIn(needle, (BTF_ROOT / rel).read_text(encoding="utf-8"), rel)

    def test_privacy_chip_and_investigation_templates_match_web(self) -> None:
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")
        panel = (BTF_ROOT / "web/src/components/AiAssistantPanel.vue").read_text(
            encoding="utf-8")
        self.assertIn("ai_privacy_chip", assist)
        self.assertIn("ai-privacy-chip", panel)
        self.assertIn('setObjectName("aiHeader")', assist)
        self.assertIn('class="ai-header"', panel)
        self.assertLess(assist.find('setObjectName("aiHeader")'),
                        assist.find('setObjectName("aiActions")'))
        self.assertLess(panel.find('class="ai-header"'),
                        panel.find('class="ai-header-actions"'))
        self.assertIn("Investigations", assist)
        self.assertIn("Investigations", panel)
        self.assertIn("builtin_investigation_templates", assist)
        self.assertIn("builtinInvestigationTemplates", panel)
        self.assertIn("_run_investigation_template", assist)
        self.assertIn("onInvestigationTemplate", panel)
        self.assertNotIn("aiModes", assist)
        self.assertNotIn("ai-modes", panel)
        self.assertIn("_run_investigation_mode", assist)
        self.assertIn("onInvestigationMode", panel)
        self.assertNotIn('v-for="mid in investigationModes"', panel)
        self.assertIn("self._skip_interpret = True", assist)
        self.assertIn("skipInterpretOnce = true", panel)
        self.assertIn('interpreted_run_prompt(interpreted)', assist)
        self.assertIn("interpretedRunPrompt(interpretedQuery || data)", panel)
        self.assertNotIn(
            "Confirm investigation scope, then Run investigation.", assist)
        self.assertNotIn(
            "Confirm investigation scope, then Run investigation.", panel)
        self.assertIn("Save as template", assist)
        self.assertIn("Save as template", panel)
        self.assertIn("user_investigation_templates", assist)
        store = (BTF_ROOT / "web/src/utils/settingsStore.js").read_text(
            encoding="utf-8")
        self.assertIn("loadAiUserInvestigationTemplates", store)
        self.assertIn("saveAiUserInvestigationTemplates", store)
        self.assertIn("btf-viewer-ai-user-templates-v1", store)
        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        self.assertIn("user_investigation_templates", mw)
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        self.assertIn("level=${level}", app)
        self.assertIn('extra = f"level={level}" if level else ""', mw)
        stats = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
        self.assertIn("wants_ai_level", stats)
        dlg = (BTF_ROOT / "web/src/components/AnalysisFindingsDialog.vue").read_text(
            encoding="utf-8")
        # Explain is an Ask AI submenu (not a standalone "Explain…" button).
        self.assertIn('ask_menu.addMenu("Explain")', stats)
        self.assertIn(">Explain</div>", dlg)
        self.assertIn('"explain_finding"', stats)
        self.assertIn("'explain_finding'", dlg)
        # Desktop Tool window ↔ Web floating tool host (not modal overlay / right dock).
        self.assertIn("self.setModal(False)", stats)
        self.assertIn("Qt.WindowType.Tool", stats)
        self.assertIn('aria-modal="false"', dlg)
        self.assertIn("analysis-tool-host", dlg)
        self.assertIn("pointer-events: none", dlg)
        self.assertIn("onHeaderPointerDown", dlg)
        self.assertIn("analysis-tool-host-free", dlg)
        self.assertNotIn("analysis-dock", dlg)
        self.assertNotIn("dialog-overlay", dlg)
        self.assertNotIn("dockRightPx", dlg)
        self.assertNotIn("dock-right-px", app)
        # Explain levels are built at runtime (Desktop .title() / Web capitalize).
        self.assertIn("EXPLAIN_LEVELS", stats)
        self.assertIn("str(level).title()", stats)
        self.assertIn("EXPLAIN_LEVELS", dlg)
        self.assertIn("explainLevels", dlg)
        self.assertIn("onHypothesisAction", panel)
        self.assertIn("_on_hypothesis_action", assist)

    def test_ai_template_ux_layout_matches_web(self) -> None:
        """Dynamic chip row, More menu, and Findings Ask-AI stay lockstep."""
        from btf_viewer_pkg.ai_assistant import (
            AI_DEFAULT_TEMPLATE_ORDER,
            AI_TEMPLATE_MENU_GROUPS,
            AI_TEMPLATE_MRU_MAX,
            AI_TEMPLATE_QUESTIONS,
            ai_template_by_id,
            visible_ai_templates,
        )
        from btf_viewer_pkg.ai_case import (
            EXPLAIN_LEVELS, INVESTIGATION_MODE_LABELS, INVESTIGATION_MODES,
            builtin_investigation_templates,
        )

        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")
        panel = (BTF_ROOT / "web/src/components/AiAssistantPanel.vue").read_text(
            encoding="utf-8")
        md_js = (BTF_ROOT / "web/src/utils/aiMarkdown.js").read_text(
            encoding="utf-8")
        stats = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
        dlg = (BTF_ROOT / "web/src/components/AnalysisFindingsDialog.vue").read_text(
            encoding="utf-8")
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        store = (BTF_ROOT / "web/src/utils/settingsStore.js").read_text(
            encoding="utf-8")

        self.assertNotIn('setObjectName("aiModes")', assist)
        self.assertNotIn('class="ai-modes"', panel)
        self.assertLess(panel.find('class="ai-plan-status"'),
                        panel.find('class="ai-templates"'))
        self.assertRegex(assist, r'QPushButton\("More(…|\\u2026)"\)')
        self.assertIn("More…", panel)
        self.assertIn(
            "Uses Analysis Findings for the current Statistics scope.", assist)
        self.assertIn(
            "Uses Analysis Findings for the current Statistics scope.", panel)
        # The Trace-Compare prerequisite text was removed (button still greys
        # out when < 2 tabs are open).
        self.assertNotIn(
            "Open at least two BTF tabs to use Trace Compare.", assist)
        self.assertNotIn(
            "Open at least two BTF tabs to use Trace Compare.", panel)
        self.assertIn("This trace has a single core — not applicable.", assist)
        self.assertIn("This trace has a single core — not applicable.", panel)
        self.assertIn("format_investigation_issue_card", assist)
        self.assertIn("formatInvestigationIssueCard", panel)
        self.assertIn("QHBoxLayout(self._guide_stepper)", assist)
        self.assertIn("guide_now", assist)
        self.assertIn("color: var(--fg, #1E1E1E)", panel)
        self.assertNotIn("Not sure where to start?", panel)
        self.assertNotIn("ai-issue-kicker", panel)
        case_py = (BTF_ROOT / "btf_viewer_pkg/ai_case.py").read_text(encoding="utf-8")
        case_js_src = (BTF_ROOT / "web/src/utils/aiCase.js").read_text(encoding="utf-8")
        self.assertIn('"CURRENT ISSUE\\n"', case_py)
        self.assertIn("CURRENT ISSUE\\n", case_js_src)

        self.assertEqual(AI_TEMPLATE_MRU_MAX, 3)
        self.assertEqual(
            visible_ai_templates(recent=[], usage={}),
            list(AI_DEFAULT_TEMPLATE_ORDER[:AI_TEMPLATE_MRU_MAX]),
        )
        self.assertIn("visible_ai_templates", assist)
        self.assertIn("visibleTemplates", panel)
        self.assertIn("record_ai_template_use", assist)
        self.assertIn("recordTemplateUse", panel)
        self.assertIn("btf.ai.recentTemplates", store)
        self.assertIn("recent_templates", assist)
        self.assertIn("recent_templates", 
                      (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8"))
        self.assertNotIn("AI_TEMPLATE_PRIMARY_IDS", assist)
        self.assertNotIn("primaryTemplateRows", panel)

        self.assertEqual(
            [INVESTIGATION_MODE_LABELS[m] for m in INVESTIGATION_MODES],
            ["Quick", "Diagnose", "Compare", "Optimize", "Report"],
        )
        self.assertNotIn("v-for=\"mid in investigationModes\"", panel)
        self.assertNotIn("for mid in INVESTIGATION_MODES", assist)
        self.assertIn("_run_investigation_mode", assist)
        self.assertIn("self._mode_btns", assist)
        self.assertIn("_investigation_template_actions", assist)
        self.assertIn("save_act.setEnabled(not busy)", assist)
        self.assertIn("class _FlowLayout", assist)
        self.assertIn("_FlowLayout(actions_host", assist)
        self.assertNotIn("_FlowLayout(mode_host", assist)
        self.assertNotIn("break_before=", assist)
        self.assertNotIn("ai_template_primary_rows", assist)
        self.assertNotIn("aiTemplatePrimaryRows", panel)
        self.assertNotIn("class=\"ai-tpl-row\"", panel)
        self.assertIn("_AI_CHIP_MIN_HEIGHT = 28", assist)
        self.assertIn("min-height: 28px", panel)
        self.assertIn("_ai_more_heading", assist)
        self.assertIn("aiMoreCol", assist)
        self.assertNotIn("getattr(more_menu, \"addSection\"", assist)
        self.assertIn("flex-wrap: wrap", panel)
        view = (BTF_ROOT / "btf_viewer_pkg/view.py").read_text(encoding="utf-8")
        in_bar = view[view.find("def _in_ai_actions_bar"):view.find("def _relax_widget_tree")]
        self.assertNotIn('"aiModes"', in_bar)
        self.assertIn('"aiTemplates"', in_bar)
        self.assertIn('"aiActions"', in_bar)
        self.assertIn('"aiHeader"', in_bar)
        self.assertIn('"aiMoreMenu"', in_bar)
        self.assertIn('"aiComposer"', in_bar)
        self.assertIn('"aiGuide"', in_bar)
        self.assertIn('"aiGuideStepper"', in_bar)
        self.assertIn("def _set_status", assist)
        self.assertIn("format_context_usage_status", assist)
        self.assertIn("formatContextUsageStatus(", panel)
        settings = (BTF_ROOT / "web/src/components/SettingsDialog.vue").read_text(
            encoding="utf-8")
        self.assertIn("_ai_context_combo", stats)
        self.assertIn("draft.aiContextMode", settings)
        self.assertIn("aiContextModeSettingsOverview", settings)
        self.assertIn("settings-help--pre", settings)
        self.assertIn("ai_context_mode_settings_overview", stats)
        self.assertIn("_SettingsHelpLabel", stats)
        self.assertIn("def _tip", stats)
        self.assertIn("def _ai_help", stats)
        self.assertIn("def _ai_field", stats)
        self.assertIn("def _wide_edit", stats)
        self.assertIn("QComboBox, QLineEdit", stats)
        self.assertIn("p4_body.addStretch", stats)
        self.assertIn("p4_tail", stats)
        self.assertIn("qt_wrap_tooltip", stats)
        self.assertIn("When off, the AI tab is hidden.", stats)
        self.assertIn("When off, the AI tab is hidden.", settings)
        self.assertIn("settings-form-field", settings)
        self.assertIn("spacing:8px", stats)
        self.assertIn("class=\"ai-usage-bar\"", panel)
        self.assertIn('setObjectName("aiUsageBar")', assist)
        self.assertIn('setObjectName("aiSplit")', assist)
        self.assertIn('setObjectName("aiSplitTop")', assist)
        self.assertIn("class=\"ai-split\"", panel)
        self.assertIn("class=\"ai-split-top\"", panel)
        self.assertIn("class=\"ai-split-handle\"", panel)
        self.assertIn(".ai-split-handle::before", panel)
        self.assertIn("stats-section-resizer",
                      (BTF_ROOT / "web/src/components/StatisticsPanel.vue").read_text(encoding="utf-8"))
        self.assertIn("class _AiSplitHandle", assist)
        self.assertIn("def _flash_main_status", assist)
        self.assertIn('getattr(wnd, "statusBar", None)', assist)
        self.assertIn('showMessage(f"AI: {short}", 6000)', assist)
        on_err = assist[assist.find("def _on_err"):assist.find("def _on_cancelled")]
        self.assertIn("error=True", on_err)
        self.assertIn("function setErrorStatus", panel)
        self.assertIn("emit('statusMessage'", panel)
        self.assertIn('@status-message="onAiStatusMessage"', app)
        self.assertIn("statusBarFlash", app)
        self.assertIn('setObjectName("aiComposer")', assist)
        self.assertIn('class="ai-composer"', panel)
        self.assertIn('setObjectName("aiComposerIcons")', assist)
        self.assertIn("ai-composer-icons", panel)
        self.assertIn(AI_SEND_ICON_PATH, assist)
        self.assertIn(AI_SEND_ICON_PATH, panel)
        self.assertIn(AI_STOP_ICON_PATH, assist)
        self.assertIn(AI_STOP_ICON_PATH, panel)
        self.assertIn("def _on_composer_action", assist)
        self.assertIn("function onComposerAction", panel)
        self.assertIn("Enter to send, Shift+Enter for a new line", assist)
        self.assertIn("Enter to send, Shift+Enter for a new line", panel)
        self.assertIn("keydown.enter.exact.prevent", panel)
        self.assertNotIn("Ctrl/Cmd+Enter to send", assist)
        self.assertNotIn("Ctrl/Cmd+Enter to send", panel)
        self.assertNotIn("{{ busy ? 'Waiting…' : 'Ask' }}", panel)
        self.assertNotIn('_send_btn.setText("Waiting…"', assist)
        clear_fn = assist[assist.find("def clear_conversation"):assist.find("def _show_log_menu")]
        self.assertIn("self._cost_meter = empty_cost_meter()", clear_fn)
        self.assertIn("_clear_evidence_log_entry", clear_fn)
        self.assertIn("_clear_investigation_plan", clear_fn)
        self.assertNotIn("self._clear_template_history()", clear_fn)
        send_fn = assist[assist.find("def _send_query"):]
        self.assertNotIn("self._cost_meter = empty_cost_meter()", send_fn)
        self.assertIn("costMeter.value = emptyCostMeter()", panel)
        self.assertIn("evidencePayload = null", panel)
        self.assertIn("investigationPlan.value = null", panel)
        self.assertIn("def _log_selected_text", assist)
        self.assertIn("function logSelectedText", panel)
        self.assertIn("def _ask_log_selection", assist)
        self.assertIn("function askSelection", panel)
        log_menu = assist[assist.find("def _show_log_menu"):assist.find("def copy_conversation")]
        self.assertIn("ask_ai_selection_menu_label(selected)", log_menu)
        self.assertIn("ask_ai_selection_can_ask(selected)", log_menu)
        self.assertIn("askAiSelectionMenuLabel(logMenu.selectedText)", panel)
        self.assertIn("askAiSelectionCanAsk(selected)", panel)
        self.assertIn('!logMenu.canAskAi', panel)
        self.assertIn("def ask_ai_selection_menu_label", assist)
        self.assertIn("def ask_ai_selection_can_ask", assist)
        self.assertIn("export function askAiSelectionMenuLabel", md_js)
        self.assertIn("export function askAiSelectionCanAsk", md_js)
        self.assertIn("ASK_AI_SELECTION_PREVIEW_CHARS = 28", assist)
        self.assertIn("ASK_AI_SELECTION_PREVIEW_CHARS = 28", md_js)
        self.assertNotIn("createStandardContextMenu", log_menu)
        self.assertLess(log_menu.find('menu.addAction("Copy")'),
                        log_menu.find("Copy conversation"))
        self.assertLess(log_menu.find("Copy conversation"),
                        log_menu.find("Save As Markdown"))
        self.assertLess(log_menu.find("Save As Markdown"),
                        log_menu.find("Save As Text"))
        self.assertLess(log_menu.find("Save As Text"),
                        log_menu.find("Save As HTML"))
        ctx = panel[panel.find('class="ai-ctx-menu"'):panel.find('class="ai-status"')]
        self.assertLess(ctx.find("askAiSelectionMenuLabel"), ctx.find("copySelection"))
        self.assertLess(ctx.find("copySelection"), ctx.find("copyConversation"))
        self.assertLess(ctx.find("copyConversation"), ctx.find("Save As Markdown"))
        self.assertLess(ctx.find("Save As Markdown"), ctx.find("Save As Text"))
        self.assertLess(ctx.find("Save As Text"), ctx.find("Save As HTML"))

        menu_ids = [tid for _g, ids in AI_TEMPLATE_MENU_GROUPS for tid in ids]
        self.assertEqual(
            [g[0] for g in AI_TEMPLATE_MENU_GROUPS],
            ["Start", "Investigate", "SMP", "Compare",
             "What-if / Optimize"],
        )
        self.assertIn("v-for=\"group in templateMenuGroups\"", panel)
        self.assertIn("class=\"ai-more-col\"", panel)
        self.assertIn("<Teleport to=\"body\">", panel)
        self.assertIn("ai-more-menu-wide", panel)
        self.assertIn("QGridLayout(more_menu)", assist)
        self.assertNotIn("more_scroll", assist)
        self.assertIn("i // 2, i % 2", assist)
        self.assertEqual(
            AI_TEMPLATE_MENU_GROUPS[-1],
            ("What-if / Optimize", ("what_if", "optimize")),
        )
        self.assertEqual(ai_template_by_id("what_if")[1], "What-if")
        self.assertIn("_AI_TPL_DISABLED_COLOR", assist)
        self.assertIn("QPushButton:disabled", assist)
        self.assertIn("QPushButton#aiMoreItem:disabled", assist)
        self.assertIn(".ai-more-item:disabled", panel)
        self.assertIn("color: var(--muted, #8a96a8)", panel)
        self.assertNotIn("analysis-btn primary", dlg)
        self.assertNotIn("background: #3498db; color: white", stats)
        self.assertIn("Investigations", assist)
        self.assertIn("Investigations", panel)
        inv_labels = [t["label"] for t in builtin_investigation_templates()]
        self.assertEqual(
            inv_labels,
            [
                "CPU Latency Investigation",
                "Migration Thrash Investigation",
                "A/B Regression Investigation",
            ],
        )
        case_py = (BTF_ROOT / "btf_viewer_pkg/ai_case.py").read_text(encoding="utf-8")
        case_js = (BTF_ROOT / "web/src/utils/aiCase.js").read_text(encoding="utf-8")
        for label in inv_labels:
            self.assertIn(label, case_py, label)
            self.assertIn(label, case_js, label)
        self.assertIn('v-for="tpl in investigationTemplates"', panel)

        findings = [
            "Query findings…", "Investigate…", "Verify…", "Explain",
            "Root cause…", "Auto investigate…", "Save recipe…", "Story…",
        ]
        for label in findings:
            self.assertIn(label, dlg, f"web findings: {label}")
        desk_row = [
            r'Ask AI',
            r'addAction\("Query findings…"',
            r'addAction\("Investigate…"',
            r'addAction\("Verify…"',
            r'addMenu\("Explain"\)',
            r'addAction\("Root cause…"',
            r'addAction\("Auto investigate…"',
            r'Save recipe…',
            r'Story…',
        ]
        pos = 0
        for pat in desk_row:
            m = re.search(pat, stats[pos:])
            self.assertIsNotNone(m, pat)
            pos += m.end()
        self.assertEqual(list(EXPLAIN_LEVELS), ["quick", "technical", "deep"])
        self.assertIn("for level in EXPLAIN_LEVELS", stats)
        self.assertIn("EXPLAIN_LEVELS.map", dlg)
        # Web Explain submenu is inline under Ask AI (no separate Explain popup).
        self.assertIn("askAiOpen", dlg)
        self.assertIn("toggleAskAi", dlg)
        self.assertIn("query_template", assist)
        self.assertIn("extra=ex", (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(
            encoding="utf-8"))
        self.assertIn("level=${level}", app)
        self.assertIn("finding_id=${findingId}", app)
        from btf_viewer_pkg.ai_case import VALIDATE_EXPERIMENT_PROMPT
        self.assertIn("Call validate_experiment. Omit actual", VALIDATE_EXPERIMENT_PROMPT)
        self.assertIn(VALIDATE_EXPERIMENT_PROMPT, case_js)
        self.assertIn("Validate experiment…", stats)
        compare_dlg = (BTF_ROOT / "web/src/components/TraceCompareDialog.vue").read_text(
            encoding="utf-8")
        self.assertIn("Validate experiment…", compare_dlg)
        self.assertIn("Save baseline", stats)
        self.assertIn("Save baseline", compare_dlg)
        self.assertIn("Score vs baseline", stats)
        self.assertIn("Score vs baseline", compare_dlg)
        self.assertIn('addTab(self._trends_table, "Trends")', stats)
        self.assertIn("id: 'trends', label: 'Trends'", compare_dlg)
        parser_py = (BTF_ROOT / "btf_viewer_pkg/parser.py").read_text(encoding="utf-8")
        cmp_js = (BTF_ROOT / "web/src/utils/traceCompare.js").read_text(encoding="utf-8")
        self.assertIn("def cross_trace_trends", parser_py)
        self.assertIn("export function crossTraceTrends", cmp_js)
        self.assertIn("HTML_REPORT_INTERACTIVE_SCRIPT", parser_py)
        self.assertIn("HTML_REPORT_INTERACTIVE_SCRIPT", cmp_js)
        self.assertIn("COMPARE_TOC_GROUPS", parser_py)
        self.assertIn("export const COMPARE_TOC_GROUPS", cmp_js)
        self.assertIn("def html_make_collapsible_sections", (
            BTF_ROOT / "btf_viewer_pkg/html_report.py").read_text(encoding="utf-8"))
        self.assertIn("export function htmlMakeCollapsibleSections", (
            BTF_ROOT / "web/src/utils/htmlReport.js").read_text(encoding="utf-8"))
        self.assertIn("def html_toc_nav", (
            BTF_ROOT / "btf_viewer_pkg/html_report.py").read_text(encoding="utf-8"))
        self.assertIn("export function htmlTocNav", (
            BTF_ROOT / "web/src/utils/htmlReport.js").read_text(encoding="utf-8"))
        self.assertIn("def html_section_slug", (
            BTF_ROOT / "btf_viewer_pkg/html_report.py").read_text(encoding="utf-8"))
        self.assertIn("export function htmlSectionSlug", (
            BTF_ROOT / "web/src/utils/htmlReport.js").read_text(encoding="utf-8"))
        self.assertIn("HTML_REPORT_INTERACTIVE_SCRIPT", (
            BTF_ROOT / "btf_viewer_pkg/html_report.py").read_text(encoding="utf-8"))
        self.assertIn("export const HTML_REPORT_INTERACTIVE_SCRIPT", (
            BTF_ROOT / "web/src/utils/htmlReport.js").read_text(encoding="utf-8"))
        stats_html_py = (BTF_ROOT / "btf_viewer_pkg/stats_html.py").read_text(encoding="utf-8")
        stats_html_js = (BTF_ROOT / "web/src/utils/statsHtmlReport.js").read_text(encoding="utf-8")
        for py_name, js_name in (
            ("def html_glossary", "export function htmlGlossary"),
            ("def html_finding_cards", "export function htmlFindingCards"),
            ("def html_investigate_anomalies", "export function htmlInvestigateAnomalies"),
            ("def html_scope_identity_card", "export function htmlScopeIdentityCard"),
            ("def html_evidence_refs_card", "export function htmlEvidenceRefsCard"),
            ("def evidence_refs_from_findings", "export function evidenceRefsFromFindings"),
            ("def html_matrix_heatmap", "export function htmlMatrixHeatmap"),
            ("def html_percentile_bars", "export function htmlPercentileBars"),
            ("def html_health_bars", "export function htmlHealthBars"),
            ("def html_tag_overview", "export function htmlTagOverview"),
            ("STATS_TOC_GROUPS", "export const STATS_TOC_GROUPS"),
            ("STATS_DEFAULT_EXPANDED", "export const STATS_DEFAULT_EXPANDED"),
        ):
            self.assertIn(py_name, stats_html_py)
            self.assertIn(js_name, stats_html_js)
        self.assertIn("html_apply_collapsible_toc", parser_py)
        self.assertIn("htmlApplyCollapsibleToc", cmp_js)
        self.assertIn("Shared Patterns", parser_py)
        self.assertIn("Shared Patterns", cmp_js)
        # Modes are not extra AI_TEMPLATE_QUESTIONS entries.
        ids = [t[0] for t in AI_TEMPLATE_QUESTIONS]
        self.assertEqual(ids[-1], "auto_investigate")
        self.assertNotIn("diagnose", ids)
        self.assertNotIn("validate_experiment", ids)
        self.assertEqual(len(menu_ids), 20)
        self.assertEqual(sorted(menu_ids), sorted(ids))

    def test_ai_panel_theme_and_mermaid_match_web(self) -> None:
        """AI log diagrams and Analysis finding ink stay Desktop/Web lockstep."""
        from btf_viewer_pkg.ai_mermaid import mermaid_palette

        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")
        mermaid_py = (BTF_ROOT / "btf_viewer_pkg/ai_mermaid.py").read_text(
            encoding="utf-8")
        mermaid_js = (BTF_ROOT / "web/src/utils/aiMermaid.js").read_text(
            encoding="utf-8")
        md_js = (BTF_ROOT / "web/src/utils/aiMarkdown.js").read_text(
            encoding="utf-8")
        panel = (BTF_ROOT / "web/src/components/AiAssistantPanel.vue").read_text(
            encoding="utf-8")
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        dlg = (BTF_ROOT / "web/src/components/AnalysisFindingsDialog.vue").read_text(
            encoding="utf-8")
        stats = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")

        self.assertIn("def mermaid_palette", mermaid_py)
        self.assertIn("export function mermaidPalette", mermaid_js)
        key_map = {
            "bg": "bg", "lane": "lane", "node_fill": "nodeFill",
            "node_stroke": "nodeStroke", "node_text": "nodeText",
            "edge": "edge", "edge_label": "edgeLabel", "arrow": "arrow",
            "msg": "msg", "note_fill": "noteFill", "note_stroke": "noteStroke",
            "note_text": "noteText",
        }
        for is_dark in (True, False):
            pal = mermaid_palette(is_dark)
            self.assertEqual(set(pal), set(key_map))
            for py_key, js_key in key_map.items():
                self.assertIn(f"{js_key}: '{pal[py_key]}'", mermaid_js, js_key)
        self.assertIn(
            "return _flowchart_svg(text, interactive=interactive, is_dark=is_dark)",
            mermaid_py)
        self.assertIn("return flowchartSvg(text, interactive, dark)", mermaid_js)
        self.assertIn(r"--\s+(.+?)\s+-->", mermaid_py)
        self.assertIn(r"--\s+(.+?)\s+-->", mermaid_js)
        self.assertIn("def actionable_diagram_highlight", mermaid_py)
        self.assertIn("export function actionableDiagramHighlight", mermaid_js)
        self.assertIn('startswith("style ")', mermaid_py)
        self.assertIn("startsWith('style ')", mermaid_js)
        self.assertIn("Models often omit", assist)
        self.assertIn("Models often omit", md_js)
        self.assertIn("graph|flowchart|sequencediagram", assist)
        self.assertIn("graph|flowchart|sequencediagram", md_js)
        self.assertIn("is_dark=is_dark)", assist)
        self.assertIn("mermaid_block_html(", assist)
        self.assertIn("dark = true", md_js)
        self.assertIn("{ inlineSvg, zoomable, dark }", md_js)
        self.assertIn("darkMode: { type: Boolean, default: true }", panel)
        self.assertIn(':dark-mode="timelineOptions.darkMode"', app)
        self.assertIn(
            "formatAiMessageHtml(role, text, { dark: props.darkMode !== false })",
            panel)
        self.assertIn("is_dark=bool(getattr(self, \"_is_dark\", True))", assist)
        self.assertIn("background: var(--panel-bg", panel)
        self.assertIn("color: var(--analysis-ok)", dlg)
        self.assertIn("color: var(--fg)", dlg)
        self.assertNotIn("color: #1E1E1E;", dlg)
        self.assertIn("--analysis-ok:", app)
        self.assertIn("#166534", stats)
        self.assertIn("load_balance_ok", stats)
        self.assertIn("analysisFindingText", stats)
        self.assertIn('ok_ink = "#7dcea0"', stats)
        self.assertIn('ok_ink = "#166534"', stats)
        self.assertIn("--analysis-ok:   #7dcea0", app)
        self.assertIn("--analysis-ok:   #166534", app)
        self.assertIn("--analysis-warn: #e67e22", app)
        self.assertIn("--analysis-err:  #e74c3c", app)
        self.assertIn("--analysis-warn: #9a4d00", app)
        self.assertIn("--analysis-err:  #c0392b", app)
        self.assertIn('ask, err, warn = "#8a8a8a", "#e74c3c", "#e67e22"', stats)
        self.assertIn('ask, err, warn = "#555555", "#c0392b", "#9a4d00"', stats)

    def _node_json(self, source: str) -> object:
        node = shutil.which("node")
        if not node:
            self.skipTest("node is required for Desktop/Web runtime parity")
        proc = subprocess.run(
            [node, "--input-type=module", "-e", source],
            cwd=BTF_ROOT / "web",
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr.strip() or proc.stdout.strip() or "node failed")
        line = (proc.stdout or "").strip().splitlines()[-1]
        return json.loads(line)

    def test_runtime_analysis_mermaid_session_match_web(self) -> None:
        """Run Analysis, mermaid palettes, and session-chat helpers on both apps."""
        from btf_viewer_pkg.ai_case import (
            dump_investigation_session,
            investigation_session_has_chat,
            parse_investigation_session,
        )
        from btf_viewer_pkg.ai_mermaid import mermaid_palette
        from btf_viewer_pkg.stats import (
            _build_workflow_analysis_findings,
            _load_balance_metrics,
        )

        vectors = [
            [40.0, 40.0, 40.0],
            [55.0, 40.0, 30.0, 20.0, 15.0, 10.0, 5.0, 2.0],
            [80.0, 10.0, 5.0, 5.0],
            [50.0, 50.0],
            [70.0, 50.0, 45.0, 40.0],
            [0.0, 0.0],
            [40.0],
        ]
        py_lb = [_load_balance_metrics(v) for v in vectors]
        py_findings = []
        for pcts in vectors:
            rows = [(f"Core_{i}", p) for i, p in enumerate(pcts)]
            found = _build_workflow_analysis_findings(
                core_rows=rows,
                exec_rows=[],
                block_rows=[],
                mig_rows=[],
                pair_rows=[],
                priority_rows=[],
                sync_rows=[],
                sync_issues=[],
                tick={"tick_count": 0},
            )
            py_findings.append([
                {
                    "id": f.get("id") or "",
                    "title": f.get("title"),
                    "severity": f.get("severity"),
                    "text": f.get("text"),
                }
                for f in found
            ])
        chat_cases = [
            [],
            [{"role": "evidence", "content": "CURRENT ISSUE"}],
            [{"role": "user", "content": "hello"}],
            [{"role": "assistant", "content": "ok"}],
            [{"role": "user", "content": "  "}],
        ]
        py_chat = [investigation_session_has_chat(c) for c in chat_cases]
        blob = dump_investigation_session(
            payload={"finding": {"title": "x"}},
            plan={"goal": "g", "steps": []},
            messages=[{"role": "user", "content": "hello"}],
        )
        py_parsed = parse_investigation_session(blob)
        pal_py = {
            "dark": mermaid_palette(True),
            "light": mermaid_palette(False),
        }

        js_src = """
import { mermaidPalette } from './src/utils/aiMermaid.js'
import {
  dumpInvestigationSession,
  investigationSessionHasChat,
  parseInvestigationSession,
} from './src/utils/aiCase.js'
import { loadBalanceMetrics } from './src/utils/loadBalanceGauge.js'
import { buildWorkflowAnalysisFindings } from './src/utils/workflowAnalysis.js'
const vectors = %s
const chatCases = %s
const blob = %s
function slim(f) {
  return { id: f.id || '', title: f.title, severity: f.severity, text: f.text }
}
function lb(v) {
  const m = loadBalanceMetrics(v)
  if (!m) return null
  return { score: m.score, gini: m.gini, stddev: m.stddev }
}
console.log(JSON.stringify({
  lb: vectors.map(lb),
  findings: vectors.map(pcts => buildWorkflowAnalysisFindings({
    coreRows: pcts.map(pct => ({ pct })),
  }).map(slim)),
  chat: chatCases.map(investigationSessionHasChat),
  parsed: parseInvestigationSession(blob),
  pal: { dark: mermaidPalette(true), light: mermaidPalette(false) },
}))
""" % (json.dumps(vectors), json.dumps(chat_cases), json.dumps(blob))
        js = self._node_json(js_src)

        for i, (a, b) in enumerate(zip(py_lb, js["lb"])):
            if a is None:
                self.assertIsNone(b, i)
                continue
            self.assertAlmostEqual(a["score"], b["score"], places=6, msg=i)
            self.assertAlmostEqual(a["gini"], b["gini"], places=6, msg=i)
            self.assertAlmostEqual(a["stddev"], b["stddev"], places=6, msg=i)
        self.assertEqual(py_findings, js["findings"])
        self.assertEqual(py_chat, js["chat"])
        self.assertEqual(
            py_parsed["payload"]["finding"]["title"],
            js["parsed"]["payload"]["finding"]["title"],
        )
        self.assertTrue(js["parsed"]["messages"][0]["content"])
        key_map = {
            "bg": "bg", "lane": "lane", "node_fill": "nodeFill",
            "node_stroke": "nodeStroke", "node_text": "nodeText",
            "edge": "edge", "edge_label": "edgeLabel", "arrow": "arrow",
            "msg": "msg", "note_fill": "noteFill", "note_stroke": "noteStroke",
            "note_text": "noteText",
        }
        for theme in ("dark", "light"):
            for py_key, js_key in key_map.items():
                self.assertEqual(
                    pal_py[theme][py_key],
                    js["pal"][theme][js_key],
                    f"{theme}.{py_key}",
                )

    def test_session_overlay_inspector_parity(self) -> None:
        """Investigation restore, finding overlays, and task inspector stay lockstep."""
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")
        panel = (BTF_ROOT / "web/src/components/AiAssistantPanel.vue").read_text(
            encoding="utf-8")
        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        scene = (BTF_ROOT / "btf_viewer_pkg/scene.py").read_text(encoding="utf-8")
        renderer = (BTF_ROOT / "web/src/renderer/TimelineRenderer.js").read_text(
            encoding="utf-8")
        store = (BTF_ROOT / "web/src/utils/sessionStore.js").read_text(
            encoding="utf-8")
        self.assertIn("_persist_investigation_session", assist)
        self.assertIn("_restore_investigation_session", assist)
        self.assertIn("investigation_session", mw)
        self.assertIn("investigationSnapshot", panel)
        self.assertIn("restoreInvestigation", panel)
        self.assertIn("aiCase:", store)
        self.assertIn("restoreInvestigation", app)
        self.assertIn("QTextEdit.ExtraSelection", assist)
        self.assertIn("ai-msg-flash", panel)
        self.assertIn("def set_finding_overlays", scene)
        self.assertIn("export function drawFindingHits", renderer)
        self.assertIn("_refresh_finding_overlays", mw)
        self.assertIn("findingHits", app)
        self.assertIn("_status_inspect", mw)
        self.assertIn("status-inspect", app)
        self.assertIn("task_inspector_line", mw)
        self.assertIn("taskInspectorLine", app)
        self.assertIn("selectedTaskFromHighlight({", app)
        self.assertIn("taskInspectorText = computed(() => taskInspectorLine(", app)
        self.assertIn("self._refresh_task_inspector()", mw)
        legend = mw[mw.find("def _on_scene_highlight_for_legend"):]
        self.assertIn("self._refresh_task_inspector()", legend[:400])

    def test_timeline_ai_context_menu_disabled_when_ai_off(self) -> None:
        view = (BTF_ROOT / "btf_viewer_pkg/view.py").read_text(encoding="utf-8")
        tl = (BTF_ROOT / "web/src/components/TimelinePanel.vue").read_text(
            encoding="utf-8")
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        self.assertIn("Ask AI about this event", view)
        self.assertIn("Ask AI about this event", tl)
        self.assertIn("Explain this region with AI", view)
        self.assertIn("Explain this region with AI", tl)
        self.assertIn("Clear all marks", view)
        self.assertIn("Clear all marks", tl)
        self.assertIn("clear_all_marks_requested", view)
        self.assertIn("onCtxClearAllMarks", tl)
        self.assertLess(view.index("Clear all marks"), view.index("Place cursor here"))
        self.assertLess(tl.index("Clear all marks"), tl.index("Place cursor here"))
        self.assertIn("self._style_ai_menu_action(act_ask)", view)
        self.assertIn("self._style_ai_menu_action(act_region)", view)
        self.assertIn('action.setEnabled(on)', view)
        self.assertIn(':class="{ disabled: !aiFeatureEnabled }"', tl)
        self.assertIn("if (!aiFeatureEnabled.value) return", tl)
        self.assertIn(':ai-enabled="appSettings.aiEnabled !== false"', app)
        self.assertIn("view.set_ai_enabled(self._ai_feature_enabled())", mw)

    def test_ai_prompts_identical_desktop_and_web(self) -> None:
        """System / template / case prompts and tool schemas must match byte-for-byte."""
        from btf_viewer_pkg.ai_assistant import (
            AI_RESPONSE_LANGUAGES,
            AI_SMP_ONLY_TEMPLATE_IDS,
            AI_TEMPLATE_INTENT_GROUPS,
            AI_TEMPLATE_MENU_GROUPS,
            AI_DEFAULT_TEMPLATE_ORDER,
            AI_TEMPLATE_QUESTIONS,
            DEFAULT_AI_RESPONSE_LANGUAGE,
            build_ai_system_prompt,
            compose_ask_event_prompt,
        )
        from btf_viewer_pkg.ai_case import (
            AI_CONTEXT_MODES,
            AI_CONTEXT_PROMPTS,
            INVESTIGATION_MODES,
            VALIDATE_EXPERIMENT_PROMPT,
            context_mode_system_addendum,
            interpreted_run_prompt,
            investigation_mode_prompt,
            investigation_template_prompt,
        )

        web = self._node_json(
            "import {\n"
            "  AI_CORE_PROMPT, AI_SYSTEM_PROMPT, AI_TEMPLATE_QUESTIONS, buildAiSystemPrompt,\n"
            "  AI_DEFAULT_TEMPLATE_ORDER, AI_TEMPLATE_MENU_GROUPS,\n"
            "  AI_TEMPLATE_INTENT_GROUPS, AI_SMP_ONLY_TEMPLATE_IDS,\n"
            "  AI_RESPONSE_LANGUAGES, DEFAULT_AI_RESPONSE_LANGUAGE,\n"
            "  ASK_EVENT_PROMPT, composeAskEventPrompt,\n"
            "} from './src/utils/aiClient.js'\n"
            "import { AI_TOOL_PROMPT, AI_TOOL_SYSTEM_ADDENDUM, AI_MALFORMED_FUNCTION_CALL_NUDGE, aiViewerTools } from './src/utils/aiTools.js'\n"
            "import {\n"
            "  VALIDATE_EXPERIMENT_PROMPT, interpretedRunPrompt,\n"
            "  investigationModePrompt, investigationTemplatePrompt,\n"
            "  contextModeSystemAddendum, AI_CONTEXT_MODES, AI_CONTEXT_PROMPTS, INVESTIGATION_MODES,\n"
            "} from './src/utils/aiCase.js'\n"
            "const event = { task: 'Med[267]', core: 'Core_0', ns: 3087194,\n"
            "  start: 3087000, end: 3087200 }\n"
            "console.log(JSON.stringify({\n"
            "  core: AI_CORE_PROMPT,\n"
            "  system: AI_SYSTEM_PROMPT,\n"
            "  addendum: AI_TOOL_SYSTEM_ADDENDUM,\n"
            "  toolPrompt: AI_TOOL_PROMPT,\n"
            "  malformedFn: AI_MALFORMED_FUNCTION_CALL_NUDGE,\n"
            "  compose_en: buildAiSystemPrompt('English'),\n"
            "  compose_bal: buildAiSystemPrompt('English', 'balanced'),\n"
            "  contextPrompts: AI_CONTEXT_PROMPTS,\n"
            "  templates: AI_TEMPLATE_QUESTIONS.map(t => (\n"
            "    { id: t.id, label: t.label, prompt: t.prompt })),\n"
            "  defaults: AI_DEFAULT_TEMPLATE_ORDER,\n"
            "  menu: AI_TEMPLATE_MENU_GROUPS,\n"
            "  intent: AI_TEMPLATE_INTENT_GROUPS,\n"
            "  smp: [...AI_SMP_ONLY_TEMPLATE_IDS].sort(),\n"
            "  langs: AI_RESPONSE_LANGUAGES,\n"
            "  defLang: DEFAULT_AI_RESPONSE_LANGUAGE,\n"
            "  ask: ASK_EVENT_PROMPT,\n"
            "  ask_compose: composeAskEventPrompt(event),\n"
            "  validate: VALIDATE_EXPERIMENT_PROMPT,\n"
            "  irp: interpretedRunPrompt('test question'),\n"
            "  itp: investigationTemplatePrompt('investigate'),\n"
            "  modes: [...AI_CONTEXT_MODES],\n"
            "  invModes: [...INVESTIGATION_MODES],\n"
            "  addenda: Object.fromEntries(\n"
            "    [...AI_CONTEXT_MODES].map(m => [m, contextModeSystemAddendum(m)])),\n"
            "  imps: Object.fromEntries(\n"
            "    [...INVESTIGATION_MODES].map(m => [m, investigationModePrompt(m)])),\n"
            "  tools: aiViewerTools(),\n"
            "}))\n"
        )
        self.assertIsInstance(web, dict)

        self.assertEqual(web["core"], AI_CORE_PROMPT)
        self.assertEqual(web["system"], AI_SYSTEM_PROMPT)
        self.assertEqual(web["addendum"], AI_TOOL_SYSTEM_ADDENDUM)
        self.assertEqual(web["toolPrompt"], AI_TOOL_PROMPT)
        self.assertEqual(web["malformedFn"], AI_MALFORMED_FUNCTION_CALL_NUDGE)
        self.assertEqual(web["compose_en"], build_ai_system_prompt("English"))
        self.assertEqual(web["compose_bal"], build_ai_system_prompt("English", "balanced"))
        self.assertEqual(web["contextPrompts"]["balanced"], AI_CONTEXT_PROMPTS["balanced"])
        self.assertEqual(web["ask"], ASK_EVENT_PROMPT)
        self.assertEqual(
            web["ask_compose"],
            compose_ask_event_prompt({
                "task": "Med[267]", "core": "Core_0", "ns": 3087194,
                "start": 3087000, "end": 3087200,
            }),
        )
        self.assertEqual(web["validate"], VALIDATE_EXPERIMENT_PROMPT)
        self.assertEqual(web["irp"], interpreted_run_prompt("test question"))
        self.assertEqual(web["itp"], investigation_template_prompt("investigate"))
        self.assertEqual(web["defLang"], DEFAULT_AI_RESPONSE_LANGUAGE)
        self.assertEqual(tuple(web["langs"]), AI_RESPONSE_LANGUAGES)
        self.assertEqual(list(web["defaults"]), list(AI_DEFAULT_TEMPLATE_ORDER))
        self.assertEqual(sorted(web["smp"]), sorted(AI_SMP_ONLY_TEMPLATE_IDS))
        self.assertEqual(list(web["modes"]), list(AI_CONTEXT_MODES))
        self.assertEqual(list(web["invModes"]), list(INVESTIGATION_MODES))

        py_menu = [{"label": g, "ids": list(ids)} for g, ids in AI_TEMPLATE_MENU_GROUPS]
        self.assertEqual(web["menu"], py_menu)
        py_intent = [
            {"label": g, "ids": list(ids)} for g, ids in AI_TEMPLATE_INTENT_GROUPS
        ]
        self.assertEqual(web["intent"], py_intent)

        py_templates = [
            {"id": tid, "label": lab, "prompt": prompt}
            for tid, lab, prompt in AI_TEMPLATE_QUESTIONS
        ]
        self.assertEqual(web["templates"], py_templates)

        for mode in AI_CONTEXT_MODES:
            self.assertEqual(
                web["addenda"][mode],
                context_mode_system_addendum(mode),
                mode,
            )
        for mode in INVESTIGATION_MODES:
            self.assertEqual(
                web["imps"][mode],
                investigation_mode_prompt(mode),
                mode,
            )

        py_tools = ai_viewer_tools()
        self.assertEqual(len(web["tools"]), len(py_tools))
        for js_t, py_t in zip(web["tools"], py_tools):
            self.assertEqual(js_t, py_t, (js_t.get("function") or {}).get("name"))


if __name__ == "__main__":
    unittest.main()
