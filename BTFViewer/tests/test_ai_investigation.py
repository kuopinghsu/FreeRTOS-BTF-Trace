"""Unit tests for AI investigation helpers (Phase 2/3)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.ai_investigation import (  # noqa: E402
    build_investigate_context,
    default_investigation_plan,
    enrich_findings_with_ids,
    evaluate_regression,
    format_regression_report,
    is_agent_template,
    load_baseline_json,
    mark_plan_steps_from_tools,
    max_tool_rounds_for_template,
    save_baseline_json,
    snapshot_from_summary,
)
from btf_viewer_pkg.ai_tools import (  # noqa: E402
    AI_TOOL_INVESTIGATE,
    AI_VIEWER_TOOL_NAMES,
    investigate_finding,
    max_tool_rounds,
    validate_tool_call,
)


class AiInvestigationTests(unittest.TestCase):
    def test_agent_templates_and_rounds(self) -> None:
        self.assertTrue(is_agent_template("investigate"))
        self.assertFalse(is_agent_template("latency"))
        self.assertEqual(max_tool_rounds_for_template("investigate"), 8)
        self.assertEqual(max_tool_rounds("investigate"), 8)
        self.assertEqual(max_tool_rounds(""), 4)

    def test_plan_advances_from_tools(self) -> None:
        plan = default_investigation_plan("Find thrash")
        plan = mark_plan_steps_from_tools(plan, ["investigate", "query_raw_metric"])
        by_id = {s["id"]: s["status"] for s in plan["steps"]}
        self.assertEqual(by_id["findings"], "done")
        self.assertEqual(by_id["hypotheses"], "done")
        self.assertEqual(by_id["metrics"], "done")
        self.assertEqual(by_id["narrow"], "active")

    def test_investigate_context_and_tool(self) -> None:
        findings = enrich_findings_with_ids([
            {
                "id": "thrashing",
                "severity": "warning",
                "title": "Excessive bouncing / core thrashing",
                "text": "CS[28] migrates heavily",
            },
            {
                "severity": "info",
                "title": "Top tasks by CPU (WCET candidates)",
                "text": "CS[28] (15%)",
            },
        ])
        self.assertEqual(findings[0]["id"], "thrashing")
        ctx = build_investigate_context(findings, "thrashing", depth=3)
        self.assertTrue(ctx["ok"])
        self.assertTrue(ctx["hypotheses"])
        self.assertTrue(ctx["suggested_tools"])
        payload = investigate_finding(findings, "thrashing", depth=2)
        self.assertTrue(payload["ok"])
        self.assertIn("data", payload)

    def test_validate_investigate_tool(self) -> None:
        self.assertIn(AI_TOOL_INVESTIGATE, AI_VIEWER_TOOL_NAMES)
        args, err = validate_tool_call(AI_TOOL_INVESTIGATE, {"finding_id": "x", "depth": 9})
        self.assertEqual(err, "")
        self.assertEqual(args["depth"], 5)

    def test_regression_gate(self) -> None:
        cand = snapshot_from_summary({
            "migrations": 120, "migrated_tasks": 40,
            "load_balance_score": 70.0, "missed_ticks": 3,
        }, name="cand")
        base = snapshot_from_summary({
            "migrations": 80, "migrated_tasks": 30,
            "load_balance_score": 90.0, "missed_ticks": 0,
        }, name="base")
        result = evaluate_regression(cand, base)
        self.assertTrue(result["failed"])
        text = format_regression_report(result)
        self.assertIn("FAILED", text)
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "base.json")
            save_baseline_json(path, base)
            loaded = load_baseline_json(path)
            self.assertEqual(loaded["metrics"]["migrations"], 80)


if __name__ == "__main__":
    unittest.main()
