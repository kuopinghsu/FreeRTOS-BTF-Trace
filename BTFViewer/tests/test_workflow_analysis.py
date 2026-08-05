"""Unit tests for Statistics HTML Analysis Findings."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

import tests  # noqa: F401,E402 — applies QT_QPA_PLATFORM=offscreen

from btf_viewer_pkg.stats import (  # noqa: E402
    _build_workflow_analysis_findings,
    _format_analysis_findings_text,
    _render_workflow_analysis_html,
)


class WorkflowAnalysisFindingsTest(unittest.TestCase):
    def test_load_imbalance_and_thrashing(self):
        # Uneven cores (σ > 30%) + thrashing migration + hot bounce pair
        findings = _build_workflow_analysis_findings(
            core_rows=[("Core_0", 80.0), ("Core_1", 10.0), ("Core_2", 5.0), ("Core_3", 5.0)],
            exec_rows=[
                # mk, name, runs, cpu, min, avg, tmean, max, jitter, σ, p50, p95
                ("mk1", "Worker", 100, 40.0, "1us", "2us", "2us", "10us",
                 "9us", "3us", "2us", "8us"),
            ],
            block_rows=[],
            mig_rows=[
                (
                    "mk1", "ThrashTask", 25, 2, "Core_0, Core_1", "Core_0", 40.0,
                    5, 0, "-", "-", "2.5/s", 2.5, "50us", 50,
                ),
            ],
            pair_rows=[
                ("Core_0", "Core_1", 20, 10, 1000),
            ],
            priority_rows=[],
            sync_rows=[],
            sync_issues=[],
            tick={"tick_count": 0},
            deadline_viols=None,
            time_scale="us",
        )
        titles = [f["title"] for f in findings]
        self.assertIn("Load imbalance across cores", titles)
        self.assertIn("Excessive bouncing / core thrashing", titles)
        self.assertIn("Hot core-pair migration traffic", titles)
        self.assertIn("Top tasks by CPU (WCET candidates)", titles)
        load = next(f for f in findings if f["title"].startswith("Load imbalance"))
        self.assertEqual(load["severity"], "warning")
        self.assertNotIn("workflow", load)

    def test_low_score_warns_even_when_sigma_below_30(self):
        # Score ≈ 59% (G≈0.41), σ≈24% — previously mislabeled as "reasonably balanced"
        findings = _build_workflow_analysis_findings(
            core_rows=[
                ("Core_0", 55.0), ("Core_1", 40.0), ("Core_2", 30.0), ("Core_3", 20.0),
                ("Core_4", 15.0), ("Core_5", 10.0), ("Core_6", 5.0), ("Core_7", 2.0),
            ],
            exec_rows=[],
            block_rows=[],
            mig_rows=[],
            pair_rows=[],
            priority_rows=[],
            sync_rows=[],
            sync_issues=[],
            tick={"tick_count": 0},
        )
        load = next(f for f in findings if "balance" in f["title"].lower() or "imbalance" in f["title"].lower())
        self.assertEqual(load["severity"], "warning")
        self.assertIn("Load imbalance", load["title"])
        self.assertNotIn("reasonably balanced", load["text"])

    def test_priority_lmh_uses_pattern_index(self):
        findings = _build_workflow_analysis_findings(
            core_rows=[("Core_0", 50.0), ("Core_1", 50.0)],
            exec_rows=[],
            block_rows=[],
            mig_rows=[],
            pair_rows=[],
            priority_rows=[
                ("mk", "LowTask", 1, 10, 2, "100us", "L/M/H pattern", 100),
            ],
            sync_rows=[],
            sync_issues=[],
            tick={"tick_count": 0},
        )
        inv = [f for f in findings if "Priority inversion" in f["title"]]
        self.assertEqual(len(inv), 1)
        self.assertIn("LowTask", inv[0]["text"])

    def test_render_html_contains_section(self):
        findings = [
            {
                "severity": "warning",
                "title": "Load imbalance across cores",
                "text": "σ high",
            },
        ]
        html_out = _render_workflow_analysis_html(findings, " (cursor range C1–C2)")
        self.assertIn("Analysis Findings", html_out)
        self.assertIn("analysis-findings", html_out)
        self.assertIn("sev-warning", html_out)
        self.assertNotIn("WORKFLOWS", html_out)

    def test_format_findings_text(self):
        text = _format_analysis_findings_text(
            [{"severity": "warning", "title": "Load imbalance", "text": "σ high"}],
            " (scoped)",
        )
        self.assertIn("Analysis Findings (scoped)", text)
        self.assertIn("[WARNING] Load imbalance", text)
        self.assertIn("σ high", text)

    def test_empty_scope_info_finding(self):
        findings = _build_workflow_analysis_findings(
            core_rows=[],
            exec_rows=[],
            block_rows=[],
            mig_rows=[],
            pair_rows=[],
            priority_rows=[],
            sync_rows=[],
            sync_issues=[],
            tick={"tick_count": 0},
        )
        self.assertTrue(any(f["title"].startswith("No analysis heuristics") for f in findings))


if __name__ == "__main__":
    unittest.main()
