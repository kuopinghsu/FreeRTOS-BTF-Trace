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
    analyze_multi_traces,
    build_investigation_replay,
    build_investigate_context,
    build_optimization_advice,
    check_task_budgets,
    complete_investigation_plan,
    compare_performance_metrics,
    default_investigation_plan,
    detect_anomalies,
    enrich_findings_with_ids,
    estimate_what_if,
    run_optimization_experiments,
    simulate_what_if,
    evaluate_regression,
    explain_regression,
    format_bookmark_label,
    format_regression_report,
    generate_structured_report,
    is_agent_template,
    load_baseline_json,
    mark_plan_steps_from_tools,
    max_tool_rounds_for_template,
    save_baseline_json,
    snapshot_from_summary,
)
from btf_viewer_pkg.ai_tools import (  # noqa: E402
    AI_TOOL_ANALYZE_TRACES,
    AI_TOOL_BOOKMARK_FINDING,
    AI_TOOL_CHECK_BUDGET,
    AI_TOOL_COMPARE_PERFORMANCE,
    AI_TOOL_CORRELATE_EVENTS,
    AI_TOOL_DETECT_ANOMALIES,
    AI_TOOL_GENERATE_REPORT,
    AI_TOOL_INVESTIGATE,
    AI_TOOL_INVESTIGATION_REPLAY,
    AI_TOOL_OPTIMIZE,
    AI_TOOL_REGRESSION_EXPLAIN,
    AI_TOOL_WHAT_IF,
    AI_TOOL_OPTIMIZE_EXPERIMENT,
    AI_VIEWER_TOOL_NAMES,
    detect_anomalies_finding,
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

    def test_plan_completes_on_finish(self) -> None:
        plan = default_investigation_plan("Find thrash")
        plan = mark_plan_steps_from_tools(plan, ["investigate", "add_annotation"])
        plan = complete_investigation_plan(plan)
        self.assertTrue(all(s["status"] == "done" for s in plan["steps"]))
        self.assertEqual(plan["steps"][-1]["id"], "recommend")

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
        self.assertTrue(ctx.get("root_cause_chain"))
        self.assertTrue(ctx.get("ranked_anomalies"))

    def test_phase1_anomaly_compare_report_tools(self) -> None:
        findings = enrich_findings_with_ids([
            {"severity": "error", "title": "Deadline breach", "text": "TaskA budget"},
            {"severity": "warning", "title": "Anomaly: WCET spike", "text": "CS[28] Max/Avg"},
            {"severity": "info", "title": "Note", "text": "ok"},
        ])
        ranked = detect_anomalies(findings, limit=5)
        self.assertEqual(ranked["anomalies"][0]["band"], "critical")
        payload = detect_anomalies_finding(findings, limit=5)
        self.assertTrue(payload["ok"])
        cand = snapshot_from_summary({
            "migrations": 120, "migrated_tasks": 40,
            "load_balance_score": 70.0, "missed_ticks": 3,
        }, name="A")
        base = snapshot_from_summary({
            "migrations": 80, "migrated_tasks": 30,
            "load_balance_score": 90.0, "missed_ticks": 0,
        }, name="B")
        cmp = compare_performance_metrics(cand, base, label_a="A", label_b="B")
        self.assertTrue(cmp["failed"])
        report = generate_structured_report(
            findings, report_type="root_cause", focus_id="deadline_breach",
            compare=cmp,
        )
        self.assertIn("Root-cause", report["title"])
        self.assertIn("## Root cause chain", report["markdown"])
        for name in (
            AI_TOOL_DETECT_ANOMALIES,
            AI_TOOL_CORRELATE_EVENTS,
            AI_TOOL_COMPARE_PERFORMANCE,
            AI_TOOL_GENERATE_REPORT,
        ):
            self.assertIn(name, AI_VIEWER_TOOL_NAMES)
            args, err = validate_tool_call(name, {
                "limit": 3,
                "task": "CS[28]",
                "report_type": "performance",
            })
            self.assertEqual(err, "", name)

    def test_phase2_phase3_helpers_and_tools(self) -> None:
        findings = enrich_findings_with_ids([
            {"severity": "warning", "title": "Core thrashing", "text": "CS[28] migrates"},
        ])
        budgets = check_task_budgets(
            [{"task": "CS[28]", "wcet_us": 120, "response_us": 200}],
            {"CS[28]": {"wcet_us": 100, "response_us": 250}},
        )
        self.assertEqual(budgets["violations"], 1)
        ideas = build_optimization_advice(findings, limit=3)
        self.assertTrue(ideas["recommendations"])
        cand = snapshot_from_summary({
            "migrations": 120, "migrated_tasks": 40,
            "load_balance_score": 70.0, "missed_ticks": 3,
        }, name="A")
        base = snapshot_from_summary({
            "migrations": 80, "migrated_tasks": 30,
            "load_balance_score": 90.0, "missed_ticks": 0,
        }, name="B")
        cmp = compare_performance_metrics(cand, base, label_a="A", label_b="B")
        expl = explain_regression(cmp, findings)
        self.assertIn("Regression explanation", expl["markdown"])
        self.assertTrue(format_bookmark_label("root_cause", "Mutex3").startswith("🔴"))
        replay = build_investigation_replay(
            finding=findings[0],
            tools_run=["investigate", "correlate_events"],
            conclusion="Mutex contention",
            evidence_times=[1.0, 2.0],
        )
        self.assertEqual(replay["conclusion"], "Mutex contention")
        what = estimate_what_if(change="pin CS[28] to Core0", task="CS[28]", findings=findings)
        self.assertEqual(what["confidence"], "Medium")
        ranked = analyze_multi_traces([cand, base])
        self.assertEqual(ranked["best"], "B")
        for name in (
            AI_TOOL_CHECK_BUDGET,
            AI_TOOL_OPTIMIZE,
            AI_TOOL_REGRESSION_EXPLAIN,
            AI_TOOL_BOOKMARK_FINDING,
            AI_TOOL_INVESTIGATION_REPLAY,
            AI_TOOL_WHAT_IF,
    AI_TOOL_OPTIMIZE_EXPERIMENT,
            AI_TOOL_OPTIMIZE_EXPERIMENT,
            AI_TOOL_ANALYZE_TRACES,
        ):
            self.assertIn(name, AI_VIEWER_TOOL_NAMES)
        args, err = validate_tool_call(AI_TOOL_WHAT_IF, {"change": "pin X", "task": "X"})
        self.assertEqual(err, "")
        self.assertEqual(args["change"], "pin X")
        # Task-only calls (common after "run what_if on task 9") get a default pin.
        args, err = validate_tool_call(AI_TOOL_WHAT_IF, {"task": "9"})
        self.assertEqual(err, "")
        self.assertEqual(args["task"], "9")
        self.assertIn("pin 9", args["change"].lower())
        args, err = validate_tool_call(AI_TOOL_WHAT_IF, {})
        self.assertIsNone(args)
        self.assertIn("change must", err)
        args, err = validate_tool_call(
            AI_TOOL_BOOKMARK_FINDING, {"time": 100, "kind": "evidence", "note": "hit"})
        self.assertEqual(err, "")

        sim = simulate_what_if(
            change="pin CS[28] to Core_0",
            task="CS[28]",
            slices=[
                {"start": 0, "stop": 100, "duration": 100, "core": "Core_0"},
                {"start": 200, "stop": 250, "duration": 50, "core": "Core_1"},
            ],
            migrations=[{"time": 150, "from": "0", "to": "1"}],
            core_utils=[("Core_0", 40.0), ("Core_1", 60.0), ("Core_2", 20.0)],
        )
        self.assertEqual(sim["simulator"], "slice_replay_v1")
        self.assertEqual(sim["deltas"]["migrations"], -1)
        experiments = run_optimization_experiments(
            task="CS[28]",
            slices=sim["baseline"] and [
                {"start": 0, "stop": 100, "duration": 100, "core": "Core_0"},
                {"start": 200, "stop": 250, "duration": 50, "core": "Core_1"},
            ],
            migrations=[{"time": 150, "from": "0", "to": "1"}],
            blocking_gaps=[{"gap": 1000}],
            core_utils=[("Core_0", 40.0), ("Core_1", 60.0), ("Core_2", 20.0)],
            findings=findings,
            limit=5,
        )
        self.assertTrue(experiments["experiments"])
        self.assertIsNotNone(experiments["best"])
        args, err = validate_tool_call(
            AI_TOOL_OPTIMIZE_EXPERIMENT, {"task": "CS[28]", "limit": 3})
        self.assertEqual(err, "")
        self.assertEqual(args["limit"], 3)

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
