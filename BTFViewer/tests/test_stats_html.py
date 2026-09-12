"""Statistics HTML report helpers: glossary, findings, investigate tabs."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg import _bootstrap  # noqa: E402

_bootstrap.install()

from btf_viewer_pkg.html_report import REPORT_THEME_CSS  # noqa: E402
from btf_viewer_pkg.stats_html import (  # noqa: E402
    STATS_HTML_EXTRA_CSS,
    evidence_refs_from_findings,
    html_evidence_refs_card,
    html_finding_cards,
    html_glossary,
    html_investigate_anomalies,
    html_health_bars,
    html_kpi,
    html_rank_bars,
    html_report_verdict,
    html_response_p99_chart,
    html_scheduling_balance_chart,
    html_scope_identity_card,
    html_util_bar_row,
    html_util_section,
)


class StatsHtmlHelpersTest(unittest.TestCase):
    def test_glossary_avoids_misleading_terms(self):
        html = html_glossary(range_note="<li><strong>Cursor range:</strong> C1–C2</li>")
        self.assertIn("Statistics Notes", html)
        self.assertIn("highly uneven", html)
        self.assertIn("does not prove zero system load", html)
        self.assertNotIn("best metric for user experience", html)
        self.assertNotIn("0 = overload", html)
        self.assertIn("Off-CPU Time (Blocking Time)", html)
        self.assertIn("not a stacked split", html)
        self.assertEqual(html.count("<li><li>"), 0)
        self.assertIn("Cursor range", html)

    def test_finding_cards_include_inspect_link(self):
        html = html_finding_cards([{
            "severity": "warning",
            "title": "Excessive core migration",
            "text": "CS[19] migrated often.",
            "impact": "Cache misses",
            "evidence_text": "564 migrations",
            "inspect": "Core Migrations",
            "confidence": "Medium — heuristic threshold",
        }])
        self.assertIn("finding-card", html)
        self.assertIn("href=\"#sec-core-migrations\"", html)
        self.assertIn("Impact:", html)
        self.assertNotIn("click Max", html)

    def test_evidence_refs_card(self):
        refs = evidence_refs_from_findings([
            {
                "title": "Excessive core migration",
                "evidence_text": "564 migrations",
                "evidence": [{"label": "burst", "time": 1_487_000}],
            },
        ], format_ns=lambda ns: f"{ns / 1e6:.3f} ms")
        self.assertEqual(refs[0]["label"], "Excessive core migration")
        self.assertIn("ms", refs[0]["time_text"])
        html = html_evidence_refs_card(refs)
        self.assertIn("Evidence Refs", html)
        self.assertIn("Excessive core migration", html)
        self.assertEqual(html_evidence_refs_card([]), "")

    def test_scope_card_and_investigate_tabs(self):
        scope = html_scope_identity_card(
            filename="example.btf.gz",
            scope_type="Full trace",
            start="0 us",
            end="2.4 s",
            duration="2.4 s",
            cores=4,
            filters="None",
            timestamp_mode="Trace capture origin (not wall-clock)",
            task_count=12,
        )
        self.assertIn("Analysis Scope", scope)
        self.assertIn("example.btf.gz", scope)
        html = html_investigate_anomalies(
            anomalies_table="<table></table>",
            worst_table="<table></table>",
            patterns_table="<table></table>",
            crit_path_table="<table></table>",
            crit_note="<p>overlap</p>",
        )
        self.assertIn("Investigate Anomalies", html)
        self.assertIn("data-tab=\"crit\"", html)
        self.assertIn("can overlap", html)

    def test_desktop_web_helper_css_and_export_lockstep(self):
        import re
        py = (BTF_ROOT / "btf_viewer_pkg/stats_html.py").read_text(encoding="utf-8")
        js = (BTF_ROOT / "web/src/utils/statsHtmlReport.js").read_text(encoding="utf-8")
        vue = (BTF_ROOT / "web/src/components/StatisticsPanel.vue").read_text(encoding="utf-8")
        stats = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
        css_py = re.search(
            r'STATS_HTML_EXTRA_CSS = """(.*?)"""\.strip\(\)', py, re.S).group(1).strip()
        css_js = re.search(
            r'export const STATS_HTML_EXTRA_CSS = `(.*?)`', js, re.S).group(1).strip()
        self.assertEqual(css_py, css_js)
        start = vue.find("function exportHtml(")
        end = vue.find("\nfunction ", start + 10)
        export_js = vue[start:end]
        self.assertNotIn("<h2>Cursor Range", export_js)
        self.assertIn("htmlInvestigateAnomalies", export_js)
        self.assertIn("htmlEvidenceRefsCard", export_js)
        self.assertIn("Off-CPU Time (Blocking Time)", export_js)
        self.assertIn("html_investigate_anomalies", stats)
        self.assertIn("html_evidence_refs_card", stats)
        self.assertIn("Off-CPU Time (Blocking Time)", stats)
        self.assertIn("HTML_REPORT_TOC_CSS", stats)
        self.assertIn("HTML_REPORT_TOC_CSS", export_js)
        self.assertIn("HTML_REPORT_TOC_CSS", vue)
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
            ("def html_trace_health_card", "export function htmlTraceHealthCard"),
            ("def html_investigation_section", "export function htmlInvestigationSection"),
            ("def html_report_verdict", "export function htmlReportVerdict"),
            ("def html_response_p99_chart", "export function htmlResponseP99Chart"),
            ("def html_scheduling_balance_chart", "export function htmlSchedulingBalanceChart"),
            ("def html_util_bar_row", "export function htmlUtilBarRow"),
            ("def html_util_section", "export function htmlUtilSection"),
            ("STATS_TOC_GROUPS", "export const STATS_TOC_GROUPS"),
            ("STATS_DEFAULT_EXPANDED", "export const STATS_DEFAULT_EXPANDED"),
        ):
            self.assertIn(py_name, py, py_name)
            self.assertIn(js_name, js, js_name)
        self.assertIn("htmlReportVerdict", export_js)
        self.assertIn("htmlResponseP99Chart", export_js)
        self.assertIn("htmlSchedulingBalanceChart", export_js)
        self.assertIn("html_report_verdict", stats)
        self.assertIn("html_response_p99_chart", stats)
        self.assertIn("html_scheduling_balance_chart", stats)
        self.assertIn("metric-util", export_js)
        self.assertIn("metric-latency", export_js)
        self.assertIn("metric-migration", export_js)
        self.assertIn("metric-util", stats)
        # Load-balance gauge is emitted at the same size by both exporters.
        self.assertIn("_load_balance_gauge_html(_lb, width=600)", stats)
        self.assertIn("loadBalanceGaugeHtml(loadBalanceScore.value, { width: 600 })", vue)
        self.assertIn("tbody tr:hover td,", css_py)
        # The palette lives in the shared theme constant, not per-export CSS.
        self.assertNotIn("--data-bar:", css_py)
        self.assertIn("--data-bar: #0284C7", REPORT_THEME_CSS)
        self.assertIn("--data-5-bg: #0284C7", REPORT_THEME_CSS)
        self.assertIn("--data-5-bg: #38BDF8", REPORT_THEME_CSS)
        self.assertIn("REPORT_THEME_CSS", stats)
        self.assertIn("REPORT_THEME_CSS", vue)

    def test_shared_report_theme_is_in_lockstep_and_used_by_both_exports(self):
        """One palette drives the Statistics and Trace Compare exports."""
        import re
        chrome_py = (BTF_ROOT / "btf_viewer_pkg/html_report.py").read_text(encoding="utf-8")
        chrome_js = (BTF_ROOT / "web/src/utils/htmlReport.js").read_text(encoding="utf-8")
        theme_py = re.search(
            r'REPORT_THEME_CSS = """(.*?)"""\.strip\(\)', chrome_py, re.S).group(1).strip()
        theme_js = re.search(
            r'export const REPORT_THEME_CSS = `(.*?)`\.trim\(\)', chrome_js, re.S).group(1).strip()
        self.assertEqual(theme_py, theme_js)
        self.assertEqual(theme_py, REPORT_THEME_CSS)
        # Both exports pull it in; the AI conversation export is left alone.
        parser_py = (BTF_ROOT / "btf_viewer_pkg/parser.py").read_text(encoding="utf-8")
        compare_js = (BTF_ROOT / "web/src/utils/traceCompare.js").read_text(encoding="utf-8")
        self.assertIn("REPORT_THEME_CSS", parser_py)
        self.assertIn("REPORT_THEME_CSS", compare_js)
        base_py = re.search(
            r'_BTF_HTML_REPORT_CSS = """(.*?)"""\.strip\(\)', chrome_py, re.S).group(1)
        self.assertNotIn("--data-bar", base_py)

    def test_report_components_are_defined_in_one_place(self):
        """Every statistics-export component lives in the shared helper module.

        The panels used to append a second CSS block plus their own utilisation
        bar builders, so the same component was defined twice per platform.
        """
        py = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
        vue = (BTF_ROOT / "web/src/components/StatisticsPanel.vue").read_text(encoding="utf-8")
        self.assertEqual(STATS_HTML_EXTRA_CSS.count(".util-bar {"), 1)
        for owner, src in (("stats.py", py), ("StatisticsPanel.vue", vue)):
            self.assertNotIn(".util-bar {", src, owner)
            self.assertNotIn(".util-bar-fill", src, owner)
            self.assertNotIn("_html_export_util", src, owner)
            self.assertNotIn("_htmlUtilBarRow", src, owner)
            self.assertNotIn("_htmlUtilSection", src, owner)
        self.assertIn("html_util_section(", py)
        self.assertIn("htmlUtilSection(", vue)

    def test_all_report_bars_share_one_track_geometry(self):
        """One bar component: utilisation, ranked and health bars must agree on
        height, corner radius and track palette (TODO section 10)."""
        css = STATS_HTML_EXTRA_CSS
        for name in (".util-bar {", ".rank-bar-track {", ".pct-bar .track {"):
            rule = css.split(name)[1].split("}")[0]
            self.assertIn("height: var(--std-bar-h)", rule, name)
            self.assertIn("border-radius: var(--std-bar-r)", rule, name)
            self.assertIn("var(--bar-track-bg)", rule, name)
            self.assertIn("var(--bar-track-border)", rule, name)
        for name in (".util-bar-fill, .util-row-task .util-bar-fill {",
                     ".rank-bar-fill {", ".pct-bar .fill {"):
            rule = css.split(name)[1].split("}")[0]
            self.assertIn("height: 100%", rule, name)
            self.assertIn("border-radius: calc(var(--std-bar-r) - 1px)", rule, name)
        # The heat legend key is a bar too, so it follows the same geometry.
        legend = css.split(".heat-legend-bar {")[1].split("}")[0]
        self.assertIn("height: var(--std-bar-h)", legend)
        self.assertIn("border-radius: var(--std-bar-r)", legend)
        # One geometry, declared once in the shared theme.
        self.assertIn("--std-bar-h: 10px;", REPORT_THEME_CSS)
        self.assertIn("--std-bar-r: 5px;", REPORT_THEME_CSS)
        self.assertNotIn("height: 8px", css)
        self.assertNotIn("height: 12px", css)
        self.assertEqual(css.count("border-radius: 4px"), 1)
        self.assertIn("border-radius: 4px", css.split(".heat-grid-cell {")[1].split("}")[0])

    def test_in_app_util_bar_height_is_shared_with_web(self):
        """The Statistics panel bars are 8px on both platforms; the web value is
        a CSS literal, so guard it against drifting from the desktop constant."""
        from btf_viewer_pkg.config import STATS_UTIL_BAR_H
        vue = (BTF_ROOT / "web/src/components/StatisticsPanel.vue").read_text(encoding="utf-8")
        prog_bar = vue.split(".prog-bar {")[1].split("}")[0]
        self.assertIn(f"height: {STATS_UTIL_BAR_H}px", prog_bar)

    def test_quantitative_scale_is_declared_once(self):
        """Bars and heat bins share one blue scale, declared per theme block.

        The scale used to exist twice: --data-N-* (unreferenced) alongside an
        identical --heat-N-* set that the heat classes actually read.
        """
        css = STATS_HTML_EXTRA_CSS
        self.assertNotIn("--heat-", css)
        self.assertNotIn("--heat-", REPORT_THEME_CSS)
        for i in range(6):
            self.assertIn(f".heat-{i} {{ background: var(--data-{i}-bg); color: var(--data-{i}-ink); }}", css)
        # Every bin is defined in light, explicit dark and system dark.
        for block, marker, end in (
            ("light", ":root {", "\n}"),
            ("dark", 'html[data-theme="dark"] {', "\n}"),
            ("system dark", 'html:not([data-theme="light"]) {', "\n  }"),
        ):
            palette = REPORT_THEME_CSS.split(marker)[1].split(end)[0]
            for i in range(6):
                self.assertIn(f"--data-{i}-bg:", palette, f"{block} bin {i}")
                self.assertIn(f"--data-{i}-ink:", palette, f"{block} bin {i}")
        # Legend gradient reads the same scale as the cells.
        legend = css.split(".heat-legend-bar {")[1].split("}")[0]
        self.assertIn("var(--data-0-bg), var(--data-1-bg), var(--data-2-bg)", legend)
        self.assertIn("var(--data-3-bg), var(--data-4-bg), var(--data-5-bg)", legend)
        # Light ends on Corporate Sky, dark on Vibrant Azure.
        self.assertIn("--data-5-bg: #0284C7;", REPORT_THEME_CSS)
        self.assertIn("--data-5-bg: #38BDF8;", REPORT_THEME_CSS)

    def test_util_section_places_lead_html_after_the_heading(self):
        html = html_util_section(
            "Core Utilization (excl. IDLE/TICK)",
            [("Core_0", 72.28), ("Core_1", 0.0)],
            "core",
            lead_html="<svg class='lb-gauge-svg'></svg>",
        )
        self.assertLess(html.index("lb-gauge-svg"), html.index("util-list"))
        self.assertIn('title="Core_0: 72.3%"', html)
        self.assertIn('class="util-bar-fill" style="width:72.3%"', html)
        self.assertIn("util-row-core", html)
        # Empty scopes still render the heading and the lead markup.
        empty = html_util_section("Top Tasks by CPU", [], "task", lead_html="<i>x</i>")
        self.assertIn("<i>x</i>", empty)
        self.assertIn('class="empty"', empty)
        self.assertIn("util-row-task", html_util_bar_row("W", 5, "task"))


class StatsHtmlProfessionalUiTest(unittest.TestCase):
    def test_kpi_metric_classes_and_verdict_are_theme_tokens(self):
        self.assertIn('class="kpi metric-util"', html_kpi("Core Utilization range", "1–2%", kind="metric-util"))
        self.assertIn('class="kpi metric-latency"', html_kpi("Worst response P99", "1 ms", kind="metric-latency"))
        self.assertIn('class="kpi metric-migration"', html_kpi("Migration activity", "12", kind="metric-migration"))
        html = html_report_verdict("warn", "load balance 95%")
        self.assertIn('class="report-verdict warn"', html)
        self.assertNotIn("style=", html)
        self.assertNotIn("#fdf3e3", html)
        self.assertNotIn("#9a4d00", html)
        self.assertIn("--warning-soft", STATS_HTML_EXTRA_CSS)
        self.assertIn(".kpi.metric-util", STATS_HTML_EXTRA_CSS)
        self.assertIn(".report-verdict.warn", STATS_HTML_EXTRA_CSS)

    def test_kpi_without_a_status_kind_gets_the_accent_outline(self):
        """Section KPI grids (Core-Pair Migration Summary, Core Migration Count,
        Core Utilization Over Time) pass no kind, so the base card must already
        read as a normal measurement rather than a faint neutral box."""
        css = STATS_HTML_EXTRA_CSS
        base = css.split(".kpi {")[1].split("}")[0]
        strip = css.split(".kpi::before {")[1].split("}")[0]
        self.assertIn("border: 1px solid var(--accent-border);", base)
        self.assertIn("background: var(--accent);", strip)
        self.assertNotIn("var(--line-strong)", strip)
        # Status kinds still override the neutral accent.
        self.assertIn(".kpi.ok { border-color: var(--ok-border); }", css)
        self.assertIn(".kpi.warn { border-color: var(--warn-border); }", css)
        self.assertIn(".kpi.error { border-color: var(--error-border); }", css)
        self.assertIn(".kpi.metric-migration::before { background: var(--warning); }", css)
        # A kind-less KPI is what those sections emit.
        self.assertIn('<article class="kpi">', html_kpi("Total migrations", "18,992"))

    def test_response_p99_chart_ranks_top_eight(self):
        rows = [
            {"task": f"T{i}", "p99_ns": ns}
            for i, ns in enumerate((10, 80, 30, 90, 20, 70, 40, 60, 50, 100), start=1)
        ]
        html = html_response_p99_chart(rows, format_p99=lambda ns: f"{ns} ns")
        self.assertIn("Highest response P99", html)
        self.assertIn("p99-chart", html)
        self.assertIn("T10", html)
        self.assertIn("100 ns", html)
        self.assertIn('class="rank-bar-num">1<', html)
        self.assertIn("T4", html)
        self.assertNotIn("T1<", html)
        self.assertEqual(html.count('class="rank-bar"'), 8)
        self.assertIn("style=\"width:100.0%\"", html)
        self.assertNotIn("deadline", html.lower())

    def test_load_balance_chart_plots_all_samples_and_lowest_callout(self):
        samples = [
            {"time": "1.01 s", "score": 99, "sigma": 1.1},
            {"time": "2.27 s", "score": 58, "sigma": 33.0},
            {"time": "3.22 s", "score": 13, "sigma": 29.9},
            {"time": "3.38 s", "score": 39, "sigma": 14.8},
        ]
        html = html_scheduling_balance_chart(samples)
        self.assertIn("Load balance over time", html)
        self.assertIn('aria-label="Load balance score over time"', html)
        self.assertIn("chart-point-low", html)
        self.assertEqual(html.count("<circle"), 4)
        self.assertIn(">0</text>", html)
        self.assertIn(">100</text>", html)
        self.assertIn("<strong>13</strong>", html)
        self.assertIn("at 3.22 s", html)
        self.assertIn("1.01 s · Load balance 99 · Util σ 1.1%", html)
        self.assertIn("3.22 s · Load balance 13 · Util σ 29.9%", html)
        self.assertIn("chart-line", html)
        self.assertNotIn("data:image/svg+xml", html)
        self.assertEqual(html_scheduling_balance_chart([]), "")
        self.assertEqual(html_scheduling_balance_chart([{"time": "0", "score": None}]), "")

    def test_task_health_bars_share_the_quantitative_bar_color(self):
        html = html_health_bars([
            {"task": "Worker[1]", "score": 32, "marks": {"execution": "jitter"}},
            {"task": "Idle[2]", "score": 95, "marks": {}},
        ])
        # Score magnitude uses the shared blue bar, never per-score red/amber/green.
        self.assertNotIn("var(--danger)", html)
        self.assertNotIn("var(--warning)", html)
        self.assertNotIn("var(--success)", html)
        self.assertNotIn("background:", html)
        self.assertIn('class="fill" style="width:32%"', html)
        self.assertIn(
            ".pct-bar .fill { height: 100%; border-radius: calc(var(--std-bar-r) - 1px); "
            "background: var(--data-bar); }",
            STATS_HTML_EXTRA_CSS,
        )
        # Same track geometry / palette as the ranked bars.
        track = STATS_HTML_EXTRA_CSS.split(".pct-bar .track {")[1].split("}")[0]
        for prop in ("height: var(--std-bar-h)", "border-radius: var(--std-bar-r)",
                     "var(--bar-track-bg)", "var(--bar-track-border)"):
            self.assertIn(prop, track)

    def test_bar_rows_hover_and_carry_tooltips(self):
        health = html_health_bars([{"task": "Worker[1]", "score": 32, "marks": {"execution": "jitter"}}])
        self.assertIn('title="Worker[1]: score 32/100 · execution"', health)
        ranked = html_rank_bars([("Worker[1]", 5, "5 ms")])
        self.assertIn('<div class="rank-bar" title="Worker[1]: 5 ms">', ranked)
        self.assertNotIn('class="rank-bar-label" title=', ranked)
        for rule in (
            ".util-row:hover .util-bar,",
            ".rank-bar:hover .rank-bar-track,",
            ".pct-bar:hover .track { border-color: var(--accent); }",
            ".pct-bar:hover .lab { color: var(--accent); }",
            ".pct-bar:hover .fill { filter: brightness(1.08); }",
        ):
            self.assertIn(rule, STATS_HTML_EXTRA_CSS)

    def test_table_rows_heat_cells_and_table_tools_respond_to_hover(self):
        css = STATS_HTML_EXTRA_CSS
        # Row hover covers plain cells, meta-table <th> and the sticky column.
        self.assertIn("tbody tr:hover td,", css)
        self.assertIn("tbody tr:hover th,", css)
        self.assertIn(".table-scroll tbody tr:hover td:first-child,", css)
        self.assertIn(
            ".table-scroll tbody tr:focus-within th:first-child { background: var(--row-hover-bg); }",
            css,
        )
        self.assertIn("inset 0 1px 0 var(--row-hover-edge)", css)
        self.assertIn("--row-hover-bg: #F1F5F9;", REPORT_THEME_CSS)
        self.assertIn("--row-hover-bg: #182235;", REPORT_THEME_CSS)
        # Declared after the stripe / sticky rules it has to win against.
        self.assertLess(css.index("tbody tr:nth-child(even) td {"), css.index("tbody tr:hover td,"))
        self.assertLess(
            css.index(".table-scroll tbody tr:nth-child(even) td:first-child {"),
            css.index(".table-scroll tbody tr:hover td:first-child,"),
        )
        # Heat cells outline instead of restyling: the value keeps its heat bin.
        self.assertIn(
            ".heat-grid-cell:hover { outline: 2px solid var(--accent); outline-offset: -2px; }",
            css,
        )
        for bin_rule in (".heat-0 { background: var(--data-0-bg)", ".heat-5 { background: var(--data-5-bg)"):
            self.assertIn(bin_rule, css)
        # Search / CSV / pagination controls keep their own feedback.
        self.assertIn(".table-search:hover { border-color: var(--accent); }", css)
        self.assertIn(".table-search:focus-visible {", css)
        self.assertIn(".table-action:hover { border-color: var(--accent); color: var(--accent); }", css)
        self.assertIn(".table-action:focus-visible {", css)
        self.assertIn(".table-check:hover { color: var(--accent); cursor: pointer; }", css)
        self.assertIn("thead th.sortable:hover { background: var(--accent-soft); }", css)

    def test_print_keeps_table_headers(self):
        """``.sortable`` is added to every ``<th>``, so hiding it in print used
        to erase the header row of every table in the report."""
        from btf_viewer_pkg.html_report import _BTF_HTML_REPORT_CSS
        print_css = _BTF_HTML_REPORT_CSS.split("@media print {")[1].split("\n}")[0]
        self.assertNotIn(".sortable { display: none", print_css)
        self.assertNotIn(".ai-ev-panel-toggle, .sortable", print_css)
        self.assertIn(".sortable { cursor: default; }", print_css)
        self.assertIn(".ai-ev-panel-toggle { display: none !important; }", print_css)
        self.assertIn("thead th.sortable:hover { background: var(--paper-2); }", print_css)
        js = (BTF_ROOT / "web/src/utils/htmlReport.js").read_text(encoding="utf-8")
        self.assertNotIn(".ai-ev-panel-toggle, .sortable", js)
        self.assertIn(".sortable { cursor: default; }", js)


if __name__ == "__main__":
    unittest.main()
