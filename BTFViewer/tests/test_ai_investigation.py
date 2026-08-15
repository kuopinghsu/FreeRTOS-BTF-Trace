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
    build_investigation_package,
    build_investigation_replay,
    build_investigate_context,
    build_critical_path,
    build_optimization_advice,
    build_root_cause_chain,
    check_task_budgets,
    classify_regression,
    classify_regression_type,
    compare_tasks_metrics,
    complete_investigation_plan,
    compare_performance_metrics,
    compute_evidence_score,
    default_investigation_plan,
    detect_anomalies,
    detect_priority_inversion,
    enrich_findings_with_ids,
    estimate_what_if,
    evidence_score_bar,
    extract_evidence_panel_payload,
    find_related_findings,
    investigation_tree_mermaid,
    recommend_validation_experiments,
    run_optimization_experiments,
    score_against_baseline,
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
    update_baseline_profile,
)
from btf_viewer_pkg.ai_tools import (  # noqa: E402
    AI_TOOL_ANALYZE_TRACES,
    AI_TOOL_BOOKMARK_FINDING,
    AI_TOOL_CHECK_BUDGET,
    AI_TOOL_COMPARE_PERFORMANCE,
    AI_TOOL_COMPARE_TASKS,
    AI_TOOL_CORRELATE_EVENTS,
    AI_TOOL_DETECT_PRIORITY_INVERSION,
    AI_TOOL_FIND_CRITICAL_PATH,
    AI_TOOL_DETECT_ANOMALIES,
    AI_TOOL_FIND_RELATED_FINDINGS,
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
    is_query_tool,
    max_tool_rounds,
    summarise_tool_call,
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
        self.assertIn("alternatives", ctx)
        self.assertGreaterEqual(len(ctx["alternatives"]), 2)
        self.assertEqual(ctx["alternatives"][0]["status"], "plausible")
        self.assertEqual(ctx["alternatives"][1]["status"], "untested")
        self.assertIn("why", ctx["alternatives"][1])
        payload = investigate_finding(findings, "thrashing", depth=2)
        self.assertTrue(payload["ok"])
        self.assertIn("data", payload)
        self.assertTrue(ctx.get("root_cause_chain"))
        self.assertTrue(ctx.get("ranked_anomalies"))

    def test_find_critical_path_and_validate(self) -> None:
        events = [
            {"time": 1000, "kind": "blocking", "detail": "dur=500"},
            {"time": 1200, "kind": "sync", "detail": "mutex take"},
            {"time": 1400, "kind": "execution", "detail": "dur=80 core=0"},
            {"time": 1500, "kind": "priority", "detail": "PI base=2 peak=5"},
        ]
        path = build_critical_path(events, task="CS[28]", timestamp=1300)
        self.assertTrue(path["ok"])
        self.assertEqual(len(path["path"]), 4)
        self.assertIn("confidence", path)
        args, err = validate_tool_call(
            AI_TOOL_FIND_CRITICAL_PATH, {"task": "CS[28]", "timestamp": 1300},
        )
        self.assertEqual(err, "")
        self.assertEqual(args["task"], "CS[28]")
        self.assertEqual(args["window"], 2000.0)
        self.assertEqual(args["timestamp"], 1300.0)
        self.assertIn(AI_TOOL_FIND_CRITICAL_PATH, AI_VIEWER_TOOL_NAMES)

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

    # --- Phase 4: investigation tree mermaid ------------------------------

    def test_investigation_tree_mermaid_empty(self) -> None:
        self.assertEqual(investigation_tree_mermaid([], []), "")
        self.assertEqual(investigation_tree_mermaid(None, None), "")

    def test_investigation_tree_mermaid_chain_and_hypotheses(self) -> None:
        finding = {
            "id": "thrashing",
            "severity": "warning",
            "title": "Excessive bouncing / core thrashing",
            "text": "CS[28] migrates heavily",
        }
        chain = build_root_cause_chain(finding)
        self.assertTrue(chain)
        hyps = [
            {"hypothesis": "Core thrashing / lock bounce", "why": "High migration"},
            {"hypothesis": "Missing affinity pin", "why": "Equal-priority fan-out"},
        ]
        src = investigation_tree_mermaid(chain, hyps)
        self.assertTrue(src.startswith("graph TD"))
        # One rectangle node per chain step, in order, linked S0-->S1-->...
        self.assertEqual(src.count("S0["), 1)
        self.assertIn("S0 --> S1", src)
        # Hypotheses render as rounded nodes anchored to the first (finding) step.
        self.assertIn("H0(Core thrashing", src)
        self.assertIn("S0 --> H0", src)
        self.assertIn("H1(Missing affinity pin)", src)
        # Mermaid delimiter characters must not leak into a label body.
        self.assertNotIn("[28]", src)

    def test_investigation_tree_mermaid_sanitizes_labels(self) -> None:
        chain = [{"label": 'Weird [brackets] (parens) "quotes" | pipe', "kind": "finding"}]
        src = investigation_tree_mermaid(chain, [])
        self.assertNotIn("[brackets]", src)
        self.assertNotIn("(parens)", src)
        self.assertNotIn('"', src)
        self.assertNotIn("|", src)

    def test_investigation_tree_mermaid_wired_into_investigate_context(self) -> None:
        findings = enrich_findings_with_ids([
            {
                "id": "thrashing",
                "severity": "warning",
                "title": "Excessive bouncing / core thrashing",
                "text": "CS[28] migrates heavily",
            },
        ])
        ctx = build_investigate_context(findings, "thrashing", depth=2)
        payload = extract_evidence_panel_payload(
            "investigate", {"ok": True, "data": ctx},
        )
        self.assertIsNotNone(payload)
        self.assertIn("root_cause_chain", payload)
        self.assertIn("hypotheses", payload)
        src = investigation_tree_mermaid(
            payload["root_cause_chain"], payload["hypotheses"],
        )
        self.assertTrue(src.startswith("graph TD"))

    # --- Phase 4: AI Evidence Score heuristic ------------------------------

    def test_evidence_score_bar_formatting(self) -> None:
        self.assertEqual(evidence_score_bar(0), "░" * 10 + " 0%")
        self.assertEqual(evidence_score_bar(100), "█" * 10 + " 100%")
        self.assertEqual(evidence_score_bar(80), "█" * 8 + "░" * 2 + " 80%")
        self.assertEqual(evidence_score_bar(-20), "░" * 10 + " 0%")
        self.assertEqual(evidence_score_bar(250), "█" * 10 + " 100%")

    def test_compute_evidence_score_full_evidence(self) -> None:
        result = compute_evidence_score(
            [
                {"label": "blocking: mutex wait", "time": 1000},
                {"label": "sync: mutex take", "time": 1200},
            ],
            alternatives=[{"status": "plausible"}],
            evidence_chain="### Evidence chain",
            checks=[{"label": "Migrations", "status": "fail"}],
        )
        self.assertEqual(result["score"], 80)
        self.assertEqual(result["label"], "AI Evidence Score — heuristic")
        self.assertEqual(len(result["breakdown"]), 3)
        self.assertIn("80%", result["bar"])

    def test_compute_evidence_score_missing_evidence_and_untested_alts(self) -> None:
        result = compute_evidence_score(
            [],
            alternatives=[
                {"status": "plausible"},
                {"status": "untested"},
                {"status": "untested"},
                {"status": "untested"},
            ],
        )
        # -10 (missing evidence) and -15 (capped at 3x -5 for untested alts).
        self.assertEqual(result["score"], 0)
        labels = [b["label"] for b in result["breakdown"]]
        self.assertTrue(any("untested" in l for l in labels))
        self.assertTrue(any("Missing direct evidence" in l for l in labels))

    def test_compute_evidence_score_partial_evidence(self) -> None:
        result = compute_evidence_score(
            [{"label": "evidence", "time": 500}],
            alternatives=[{"status": "untested"}],
        )
        # +40 (has times) - 5 (one untested alternative) = 35; no timeline/metric
        # correlation bonus since there is only one evidence "kind" and no chain.
        self.assertEqual(result["score"], 35)

    def test_evidence_score_wired_into_investigate_context(self) -> None:
        findings = enrich_findings_with_ids([
            {
                "id": "thrashing",
                "severity": "warning",
                "title": "Excessive bouncing / core thrashing",
                "text": "CS[28] migrates heavily",
            },
        ])
        ctx = build_investigate_context(findings, "thrashing", depth=2)
        self.assertIn("evidence_score", ctx)
        self.assertIn("evidence_score_breakdown", ctx)
        self.assertIsInstance(ctx["evidence_score"], int)
        self.assertGreaterEqual(ctx["evidence_score"], 0)
        self.assertLessEqual(ctx["evidence_score"], 100)

    def test_find_critical_path_returns_mermaid_and_graph(self) -> None:
        events = [
            {"time": 1000, "kind": "blocking", "detail": "dur=500"},
            {"time": 1200, "kind": "sync", "detail": "mutex take"},
            {"time": 1400, "kind": "execution", "detail": "dur=80 core=0"},
            {"time": 1500, "kind": "priority", "detail": "PI base=2 peak=5"},
            {"time": 1600, "kind": "migration", "detail": "Core_0 -> Core_1"},
        ]
        path = build_critical_path(events, task="CS[28]", timestamp=1300)
        self.assertTrue(path["ok"])
        self.assertIn("mermaid", path)
        self.assertTrue(path["mermaid"].startswith("graph LR"))
        self.assertEqual(len(path["graph_nodes"]), len(path["path"]))
        for node in path["graph_nodes"]:
            self.assertIn("id", node)
            self.assertIn("label", node)
            self.assertIn("kind", node)
            self.assertIn("time", node)
        blocking_kinds = {p["kind"] for p in path["blocking_steps"]}
        self.assertTrue(blocking_kinds <= {"blocking"})
        preemption_kinds = {p["kind"] for p in path["preemption_steps"]}
        self.assertTrue(preemption_kinds <= {"priority", "migration"})
        self.assertTrue(path["blocking_steps"])
        self.assertTrue(path["preemption_steps"])

    def test_find_critical_path_empty_events_has_empty_rich_fields(self) -> None:
        empty = build_critical_path([], task="CS[28]", timestamp=1300)
        self.assertFalse(empty["ok"])
        self.assertEqual(empty["mermaid"], "")
        self.assertEqual(empty["graph_nodes"], [])
        self.assertEqual(empty["blocking_steps"], [])
        self.assertEqual(empty["preemption_steps"], [])

    def test_classify_regression_type_from_metric_ids(self) -> None:
        self.assertEqual(
            classify_regression_type(None, {"id": "migrations", "label": "Migrations"}),
            "migration",
        )
        self.assertEqual(
            classify_regression_type(None, {"id": "load_balance_score", "label": "LB"}),
            "load_balance",
        )
        self.assertEqual(
            classify_regression_type(None, {"id": "missed_ticks", "label": "Missed ticks"}),
            "scheduling",
        )
        self.assertEqual(
            classify_regression_type(None, {"id": "blocking_max", "label": "Blocking max"}),
            "synchronization",
        )
        self.assertEqual(
            classify_regression_type(None, {"id": "wcet_max", "label": "WCET max"}),
            "execution",
        )
        self.assertEqual(classify_regression_type(None, None), "unknown")
        self.assertEqual(
            classify_regression_type(
                [{"id": "migrations", "label": "Migrations", "status": "fail"}], None,
            ),
            "migration",
        )

    def test_compare_performance_metrics_includes_regression_type(self) -> None:
        cand = snapshot_from_summary({
            "migrations": 120, "migrated_tasks": 40,
            "load_balance_score": 70.0, "missed_ticks": 3,
        }, name="A")
        base = snapshot_from_summary({
            "migrations": 80, "migrated_tasks": 30,
            "load_balance_score": 90.0, "missed_ticks": 0,
        }, name="B")
        cmp = compare_performance_metrics(cand, base, label_a="A", label_b="B")
        self.assertIn("regression_type", cmp)
        self.assertIn(
            cmp["regression_type"],
            {"execution", "scheduling", "synchronization", "migration", "load_balance", "unknown"},
        )

    def test_detect_priority_inversion_scans_suspect_episodes(self) -> None:
        episodes = [
            {
                "task": "Low[266]", "base_pri": 1, "peak_pri": 5,
                "start": 3100000, "stop": 3134000, "inherited": True,
                "inversion_suspect": True,
                "medium_tasks": [{"label": "Med[267]"}],
                "pattern": "Mutex inherit L/M/H (Med[267])",
            },
            {
                "task": "Idle[1]", "base_pri": 0, "peak_pri": 0,
                "start": 1000, "stop": 1100, "inherited": False,
                "inversion_suspect": False,
            },
        ]
        findings = [
            {
                "severity": "warning",
                "title": "Priority inversion suspected",
                "text": (
                    "Low[266] holds mutex(0x80018700) blocking High[268] "
                    "while Med[267] preempts"
                ),
            },
        ]
        result = detect_priority_inversion(episodes, findings)
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        inv = result["inversions"][0]
        self.assertEqual(inv["low"], "Low[266]")
        self.assertEqual(inv["medium"], "Med[267]")
        self.assertEqual(inv["high"], "High[268]")
        self.assertEqual(inv["mutex"], "0x80018700")
        self.assertEqual(inv["time"], 3100000)
        self.assertEqual(inv["duration"], 34000)
        self.assertEqual(result["confidence"], "High")

        empty = detect_priority_inversion([], [])
        self.assertTrue(empty["ok"])
        self.assertEqual(empty["count"], 0)
        self.assertEqual(empty["confidence"], "Low")

        scoped = detect_priority_inversion(episodes, findings, task="Idle[1]")
        self.assertEqual(scoped["count"], 0)

    def test_find_related_findings_scores_shared_task_and_keywords(self) -> None:
        findings = enrich_findings_with_ids([
            {
                "id": "thrashing",
                "severity": "warning",
                "title": "Excessive bouncing / core thrashing",
                "text": "CS[28] migrates heavily between cores",
                "task": "CS[28]",
            },
            {
                "id": "wcet_spike",
                "severity": "warning",
                "title": "Anomaly: WCET spike",
                "text": "CS[28] Max/Avg spike observed",
                "task": "CS[28]",
            },
            {
                "id": "unrelated",
                "severity": "info",
                "title": "Note",
                "text": "Nothing to see here",
                "task": "Idle[1]",
            },
        ])
        result = find_related_findings(findings, finding_id="thrashing")
        self.assertTrue(result["ok"])
        self.assertEqual(result["focus"]["id"], "thrashing")
        ids = [r["id"] for r in result["related"]]
        self.assertIn("wcet_spike", ids)
        self.assertNotIn("thrashing", ids)
        self.assertTrue(result["related"][0]["reasons"])

        by_task = find_related_findings(findings, task="CS[28]")
        self.assertEqual(by_task["count"], 2)

        no_findings = find_related_findings([])
        self.assertFalse(no_findings["ok"])
        self.assertEqual(no_findings["count"], 0)

        limited = find_related_findings(findings, task="CS[28]", limit=1)
        self.assertEqual(limited["count"], 1)

    def test_compare_tasks_metrics_builds_delta_rows(self) -> None:
        data_a = {
            "execution": {"count": 10, "total": 1000, "max": 200, "mean": 100},
            "blocking": {"count": 2, "total": 500, "max": 300},
        }
        data_b = {
            "execution": {"count": 5, "total": 400, "max": 100, "mean": 80},
            "blocking": {"count": 1, "total": 100, "max": 100},
        }
        result = compare_tasks_metrics(
            "Low[266]", "High[268]", data_a, data_b,
            metrics=["execution", "blocking"],
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["task_a"], "Low[266]")
        self.assertEqual(result["task_b"], "High[268]")
        self.assertTrue(result["rows"])
        self.assertIsNotNone(result["primary_difference"])
        self.assertIn(result["confidence"], {"High", "Medium", "Low"})
        row = next(r for r in result["rows"] if r["metric"] == "execution" and r["field"] == "count")
        self.assertEqual(row["a"], 10)
        self.assertEqual(row["b"], 5)
        self.assertEqual(row["delta"], 5)

        empty = compare_tasks_metrics("A", "B", {}, {})
        self.assertTrue(empty["ok"])
        self.assertEqual(empty["rows"], [])
        self.assertIsNone(empty["primary_difference"])
        self.assertEqual(empty["confidence"], "Low")

    def test_phase2_tool_wiring_validate_and_summarise(self) -> None:
        for name in (
            AI_TOOL_DETECT_PRIORITY_INVERSION,
            AI_TOOL_FIND_RELATED_FINDINGS,
            AI_TOOL_COMPARE_TASKS,
        ):
            self.assertIn(name, AI_VIEWER_TOOL_NAMES)
            self.assertTrue(is_query_tool(name))

        args, err = validate_tool_call(
            AI_TOOL_DETECT_PRIORITY_INVERSION, {"task": "Low[266]", "window": "5000"},
        )
        self.assertEqual(err, "")
        self.assertEqual(args["task"], "Low[266]")
        self.assertEqual(args["window"], 5000.0)
        self.assertTrue(summarise_tool_call(AI_TOOL_DETECT_PRIORITY_INVERSION, args))

        args, err = validate_tool_call(AI_TOOL_FIND_RELATED_FINDINGS, {"limit": 200})
        self.assertEqual(err, "")
        self.assertEqual(args["limit"], 40)
        self.assertTrue(summarise_tool_call(AI_TOOL_FIND_RELATED_FINDINGS, args))

        args, err = validate_tool_call(
            AI_TOOL_COMPARE_TASKS, {"task_a": "Low[266]", "task_b": "High[268]"},
        )
        self.assertEqual(err, "")
        self.assertEqual(args["task_a"], "Low[266]")
        self.assertEqual(args["task_b"], "High[268]")
        self.assertTrue(summarise_tool_call(AI_TOOL_COMPARE_TASKS, args))
        _, err = validate_tool_call(AI_TOOL_COMPARE_TASKS, {"task_a": "", "task_b": "High[268]"})
        self.assertNotEqual(err, "")
        _, err = validate_tool_call(AI_TOOL_COMPARE_TASKS, {"task_a": "A", "task_b": "B", "metrics": "nope"})
        self.assertNotEqual(err, "")

    def test_evidence_score_wired_into_extract_evidence_panel_payload(self) -> None:
        result = {
            "ok": True,
            "data": {
                "task": "CS[28]",
                "events": [
                    {"time": 100, "kind": "blocking", "detail": "wait"},
                    {"time": 200, "kind": "sync", "detail": "mutex take"},
                ],
                "correlation": 0.8,
            },
        }
        payload = extract_evidence_panel_payload("correlate_events", result)
        self.assertIsNotNone(payload)
        self.assertIn("evidence_score", payload)
        self.assertIn("evidence_score_bar", payload)
        self.assertGreaterEqual(payload["evidence_score"], 40 + 25)
        self.assertTrue((payload.get("falsify") or {}).get("supporting"))
        interpreted = extract_evidence_panel_payload("interpret_query", {
            "ok": True,
            "data": {
                "interpreted_question": "Why is TaskA slow?",
                "mode": "diagnose",
                "scope": ["execution", "blocking"],
            },
        })
        self.assertEqual(
            (interpreted.get("investigation_case") or {}).get("conclusion"),
            "Why is TaskA slow?",
        )

    def test_format_evidence_panel_markdown_includes_jumps(self) -> None:
        from btf_viewer_pkg.ai_assistant import format_ai_conversation_markdown
        from btf_viewer_pkg.ai_investigation import format_evidence_panel_markdown

        md = format_evidence_panel_markdown({
            "conclusion": "Core thrashing on CS[28]",
            "evidence": [{"label": "migration burst", "time": 1100000}],
            "confidence": "High",
            "evidence_score": 82,
            "evidence_score_bar": "████████░░ 82%",
        }, "Simplified Chinese (简体中文)")
        self.assertIn("Core thrashing", md)
        self.assertIn("jump:1100000", md)
        ranged = format_evidence_panel_markdown({
            "conclusion": "Critical path slice",
            "evidence": [{"label": "Blocked / off-CPU", "time": 1000,
                          "start": 1000, "stop": 1800}],
            "confidence": "Medium",
        }, "English")
        self.assertIn("range:1000/1800", ranged)
        self.assertIn("**证据**", md)
        self.assertIn("**置信度:** 高", md)
        self.assertIn("证据 / 推理", format_ai_conversation_markdown([
            ("evidence", md),
        ], response_language="Simplified Chinese (简体中文)"))

    def test_format_evidence_panel_markdown_relocalizes_chinese_to_english(self) -> None:
        from btf_viewer_pkg.ai_investigation import (
            format_evidence_panel_markdown,
            _localize_evidence_token,
            evidence_panel_labels,
        )

        en = evidence_panel_labels("English")
        self.assertEqual(_localize_evidence_token("中", en), "Medium")
        self.assertEqual(_localize_evidence_token("高", en), "High")
        self.assertEqual(
            _localize_evidence_token("关键路径: T1", en),
            "Critical path: T1",
        )
        md = format_evidence_panel_markdown({
            "conclusion": "关键路径: T1",
            "confidence": "中",
            "evidence": [{"label": "hit", "time": 42}],
        }, "English")
        self.assertIn("Critical path: T1", md)
        self.assertIn("**Confidence:** Medium", md)
        self.assertIn("jump:42", md)

    # --- Phase 3: historical baseline learning ----------------------------

    def test_update_baseline_profile_merges_running_stats(self) -> None:
        profile = update_baseline_profile(None, {"tasks": {"CS[28]": {"wcet_us": 100.0}}})
        self.assertEqual(profile["samples"], 1)
        self.assertEqual(profile["tasks"]["CS[28]"]["wcet_us"]["n"], 1)
        self.assertEqual(profile["tasks"]["CS[28]"]["wcet_us"]["mean"], 100.0)
        self.assertEqual(profile["tasks"]["CS[28]"]["wcet_us"]["m2"], 0.0)

        profile = update_baseline_profile(profile, {"tasks": {"CS[28]": {"wcet_us": 200.0}}})
        self.assertEqual(profile["samples"], 2)
        stat = profile["tasks"]["CS[28]"]["wcet_us"]
        self.assertEqual(stat["n"], 2)
        self.assertEqual(stat["mean"], 150.0)
        self.assertEqual(stat["m2"], 5000.0)  # Welford: sum((x - mean)^2)

    def test_update_baseline_profile_ignores_empty_snapshot(self) -> None:
        profile = update_baseline_profile({"version": 1, "samples": 3, "tasks": {}}, {})
        self.assertEqual(profile["samples"], 3)
        self.assertEqual(profile["tasks"], {})

    def test_score_against_baseline_flags_outliers(self) -> None:
        profile = None
        for wcet in (100.0, 102.0, 98.0, 101.0, 99.0):
            profile = update_baseline_profile(profile, {"tasks": {"CS[28]": {"wcet_us": wcet}}})
        result = score_against_baseline(profile, {"tasks": {"CS[28]": {"wcet_us": 500.0}}})
        self.assertTrue(result["ok"])
        self.assertTrue(result["has_baseline"])
        row = next(r for r in result["scores"] if r["metric"] == "wcet_us")
        self.assertIsNotNone(row["z"])
        self.assertGreater(abs(row["z"]), 2.0)
        self.assertTrue(row["flag"])
        self.assertEqual(len(result["flagged"]), 1)
        self.assertTrue(result["suggested_tools"])

    def test_score_against_baseline_insufficient_samples_returns_none_z(self) -> None:
        profile = update_baseline_profile(None, {"tasks": {"CS[28]": {"wcet_us": 100.0}}})
        result = score_against_baseline(profile, {"tasks": {"CS[28]": {"wcet_us": 100.0}}})
        row = next(r for r in result["scores"] if r["metric"] == "wcet_us")
        self.assertIsNone(row["z"])
        self.assertFalse(row["flag"])
        self.assertFalse(result["flagged"])

    def test_score_against_baseline_no_profile_reports_no_baseline(self) -> None:
        result = score_against_baseline(None, {"tasks": {"CS[28]": {"wcet_us": 100.0}}})
        self.assertFalse(result["has_baseline"])
        self.assertEqual(result["scores"][0]["n"], 0)

    # --- Phase 3: CI regression explanation depth --------------------------

    def test_classify_regression_labels(self) -> None:
        self.assertEqual(classify_regression(None), "none")
        self.assertEqual(classify_regression({"id": "migrations"}), "thrashing")
        self.assertEqual(classify_regression({"id": "migrated_tasks"}), "thrashing")
        self.assertEqual(classify_regression({"id": "load_balance"}), "load_imbalance")
        self.assertEqual(classify_regression({"id": "missed_ticks"}), "tick_health")
        self.assertEqual(classify_regression({"id": "something_else"}), "unclassified")

    def test_explain_regression_includes_classification_and_causal_chain(self) -> None:
        compare = {
            "failed": True,
            "label_a": "A", "label_b": "B",
            "message": "REGRESSION DETECTED",
            "primary_regression": {
                "id": "migrations", "label": "Migrations", "detail": "+50%",
                "candidate": 150, "baseline": 100,
            },
            "checks": [
                {"label": "Migrations", "status": "fail", "detail": "150 vs 100"},
            ],
        }
        ctx = explain_regression(compare, findings=[])
        self.assertTrue(ctx["ok"])
        self.assertEqual(ctx["classification"], "thrashing")
        self.assertTrue(ctx["causal_chain"])
        self.assertTrue(any(t["name"] == "optimize_experiment" for t in ctx["suggested_tools"]))
        self.assertTrue(any(t["name"] == "correlate_events" for t in ctx["suggested_tools"]))
        self.assertIn("Classification", ctx["markdown"])
        self.assertIn("Causal chain", ctx["markdown"])

    def test_explain_regression_no_failure_reports_none_classification(self) -> None:
        ctx = explain_regression({"failed": False, "label_a": "A", "label_b": "B"})
        self.assertFalse(ctx["failed"])
        self.assertEqual(ctx["classification"], "none")

    # --- Phase 3: AI-generated validation experiments -----------------------

    def test_recommend_validation_experiments_thrash_heuristic(self) -> None:
        findings = [{
            "id": "thrash_cs28", "title": "Core thrashing",
            "text": "CS[28] migrates repeatedly between cores", "severity": "warning",
            "task": "CS[28]",
        }]
        result = recommend_validation_experiments(findings, finding_id="thrash_cs28")
        self.assertTrue(result["ok"])
        kinds = {e["kind"] for e in result["experiments"]}
        self.assertEqual(kinds, {"simulation", "firmware", "measurement"})
        self.assertTrue(any("pin" in e["title"].lower() for e in result["experiments"]))
        self.assertIn("disclaimer", result)

    def test_recommend_validation_experiments_mutex_heuristic(self) -> None:
        findings = [{
            "id": "block_low", "title": "Priority inversion",
            "text": "Low[266] blocked on mutex held by Medium task", "severity": "error",
            "task": "Low[266]",
        }]
        result = recommend_validation_experiments(findings, finding_id="block_low", limit=3)
        self.assertTrue(result["ok"])
        self.assertLessEqual(len(result["experiments"]), 3)
        self.assertTrue(any("mutex" in e["title"].lower() or "lock" in e["title"].lower()
                             for e in result["experiments"]))

    def test_recommend_validation_experiments_empty_findings(self) -> None:
        result = recommend_validation_experiments([])
        self.assertTrue(result["ok"])
        self.assertEqual(result["experiments"], [])

    # --- Phase 3: investigation replay/export JSON package -----------------

    def test_build_investigation_package_has_schema_envelope(self) -> None:
        pkg = build_investigation_package(
            trace_name="trace.btf",
            scope="full trace",
            finding={"id": "f1", "title": "Thrashing", "severity": "warning"},
            tools_run=["investigate", "correlate_events"],
            conclusion="Confirmed: core thrashing on CS[28]",
            confidence="High",
            evidence_times=[100.0, 200.0],
            timestamp="2026-08-11T00:00:00",
        )
        self.assertEqual(pkg["schema"], "btf-investigation-package")
        self.assertEqual(pkg["version"], 1)
        self.assertEqual(pkg["trace_name"], "trace.btf")
        self.assertEqual(pkg["scope"], "full trace")
        self.assertEqual(pkg["finding"]["id"], "f1")
        self.assertEqual(pkg["tools_run"], ["investigate", "correlate_events"])
        self.assertEqual(pkg["conclusion"], "Confirmed: core thrashing on CS[28]")
        self.assertEqual(pkg["confidence"], "High")
        self.assertEqual(pkg["evidence_times"], [100.0, 200.0])
        self.assertEqual(pkg["timestamp"], "2026-08-11T00:00:00")
        json.dumps(pkg)  # must be JSON-serialisable

    def test_build_investigation_package_without_finding(self) -> None:
        pkg = build_investigation_package(trace_name="trace.btf")
        self.assertIsNone(pkg["finding"])
        self.assertEqual(pkg["tools_run"], [])
        self.assertEqual(pkg["schema"], "btf-investigation-package")

    def test_extract_evidence_panel_payload_new_investigation_tools(self) -> None:
        from btf_viewer_pkg.ai_investigation import EVIDENCE_PANEL_TOOLS

        self.assertEqual(
            EVIDENCE_PANEL_TOOLS,
            (
                "investigate",
                "correlate_events",
                "find_critical_path",
                "compare_performance",
                "explain_finding",
                "interpret_query",
                "validate_experiment",
                "manage_hypotheses",
                "plan_investigation",
                "suggest_scope",
                "detect_contradictions",
                "assess_evidence_sufficiency",
                "cluster_findings",
                "generate_fingerprint",
                "find_similar_investigations",
                "regression_localize",
                "build_causal_chain",
                "generate_experiment_plan",
                "record_experiment_outcome",
                "score_investigation",
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
            ),
        )
        explained = extract_evidence_panel_payload("explain_finding", {
            "ok": True,
            "data": {
                "finding": {"title": "Migration thrash", "text": "CS[22] bounce"},
                "hypotheses": [{"hypothesis": "Thrash", "status": "possible"}],
                "explanation": "Task CS[22] is bouncing.",
            },
        })
        self.assertIsNotNone(explained)
        self.assertIn("Migration thrash", explained["conclusion"])
        interpreted = extract_evidence_panel_payload("interpret_query", {
            "ok": True,
            "data": {
                "interpreted_question": "Why is TaskA slow?",
                "mode": "diagnose",
                "scope": ["execution", "blocking"],
            },
        })
        self.assertIsNotNone(interpreted)
        self.assertEqual(interpreted["conclusion"], "Why is TaskA slow?")
        self.assertIn("diagnose", interpreted.get("subtitle") or "")
        validated = extract_evidence_panel_payload("validate_experiment", {
            "ok": True,
            "data": {
                "result": "VALIDATED",
                "rows": [
                    {"metric": "migrations", "expected": -50, "actual": -72, "status": "validated"},
                ],
            },
        })
        self.assertIsNotNone(validated)
        self.assertEqual(validated["conclusion"], "VALIDATED")
        self.assertEqual(validated["checks"][0]["label"], "migrations")
        managed = extract_evidence_panel_payload("manage_hypotheses", {
            "ok": True,
            "data": {
                "finding": {"title": "Mutex contention"},
                "hypotheses": [{"hypothesis": "Lock hold", "status": "supported"}],
            },
        })
        self.assertIsNotNone(managed)
        self.assertEqual(managed["conclusion"], "Mutex contention")
        planned = extract_evidence_panel_payload("plan_investigation", {
            "ok": True,
            "message": "Plan with 2 hypotheses, 4 steps",
            "data": {"steps": ["detect_contradictions"]},
        })
        self.assertIsNotNone(planned)
        self.assertIn("Plan with", planned["conclusion"])


if __name__ == "__main__":
    unittest.main()
