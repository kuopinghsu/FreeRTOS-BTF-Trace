"""Reports and AI context state the trace identity and the scope actually used
for their measurements.

Verified against the existing report / context builders and locked here so a
regression can't drop the provenance.
"""

from __future__ import annotations

import unittest

from btf_viewer_pkg.analysis_context import (
    build_analysis_context,
    format_analysis_context_lines,
)
from btf_viewer_pkg.stats_html import html_scope_identity_card


class HtmlReportScopeSectionTests(unittest.TestCase):
    def test_scope_section_names_trace_scope_and_filters(self) -> None:
        html = html_scope_identity_card(
            filename="run.btf",
            scope_type="C1–C2",
            start="100", end="900", duration="800 µs",
            cores=8, filters="task=CS[28]", timestamp_mode="raw",
            task_count=40,
        )
        self.assertIn("<h2>Analysis Scope</h2>", html)
        self.assertIn("run.btf", html)
        self.assertIn("C1–C2", html)          # the scope actually used
        self.assertIn("task=CS[28]", html)    # filters in effect
        self.assertIn("800 µs", html)


class AiContextProvenanceTests(unittest.TestCase):
    def test_context_lines_carry_trace_and_scope(self) -> None:
        ctx = build_analysis_context(
            trace_name="run.btf", scope_label="C1–C3",
            scope_duration="1.2 ms", filter_labels=["core=Core_0"],
            cursor_count=3, limit_to_cursors=True,
        )
        lines = format_analysis_context_lines(ctx)
        self.assertIn("run.btf", lines)
        self.assertTrue(any(l.startswith("Scope: C1–C3") for l in lines))
        self.assertTrue(any("core=Core_0" in l for l in lines))

    def test_full_trace_scope_is_still_stated(self) -> None:
        lines = format_analysis_context_lines(
            build_analysis_context(trace_name="t.btf", scope_label="Full Trace"),
        )
        self.assertIn("Scope: Full Trace", lines)

    def test_missing_context_still_states_a_scope(self) -> None:
        self.assertEqual(format_analysis_context_lines(None), ["Scope: Full Trace"])


class DesktopWebParityTests(unittest.TestCase):
    def test_lockstep(self) -> None:
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        py = (root / "btf_viewer_pkg" / "analysis_context.py").read_text(encoding="utf-8")
        js = (root / "web" / "src" / "utils" / "analysisContext.js").read_text(encoding="utf-8")
        for a, b in (
            ("def build_analysis_context", "export function buildAnalysisContext"),
            ("def format_analysis_context_lines", "export function formatAnalysisContextLines"),
        ):
            self.assertIn(a, py)
            self.assertIn(b, js)
        for token in ('"Scope: ', "'Scope: "):
            pass
        self.assertIn('f"Scope: {scope}"', py)
        self.assertIn('`Scope: ${scope}`', js)


if __name__ == "__main__":
    unittest.main()
