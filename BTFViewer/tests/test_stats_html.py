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

from btf_viewer_pkg.stats_html import (  # noqa: E402
    evidence_refs_from_findings,
    html_evidence_refs_card,
    html_finding_cards,
    html_glossary,
    html_investigate_anomalies,
    html_scope_identity_card,
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
        start = vue.find("function exportHtml()")
        end = vue.find("\nfunction ", start + 10)
        export_js = vue[start:end]
        self.assertNotIn("<h2>Cursor Range", export_js)
        self.assertIn("htmlInvestigateAnomalies", export_js)
        self.assertIn("htmlEvidenceRefsCard", export_js)
        self.assertIn("Off-CPU Time (Blocking Time)", export_js)
        self.assertIn("html_investigate_anomalies", stats)
        self.assertIn("html_evidence_refs_card", stats)
        self.assertIn("Off-CPU Time (Blocking Time)", stats)
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
            self.assertIn(py_name, py, py_name)
            self.assertIn(js_name, js, js_name)


if __name__ == "__main__":
    unittest.main()
