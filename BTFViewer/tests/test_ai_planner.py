"""Phase 1–3 planner tools (Desktop)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.ai_planner import (  # noqa: E402
    assess_evidence_sufficiency,
    build_causal_chain,
    cluster_findings,
    detect_contradictions,
    find_similar_investigations,
    generate_experiment_plan,
    generate_fingerprint,
    plan_investigation,
    record_experiment_outcome,
    regression_localize,
    score_hypotheses,
    score_investigation_metrics,
    set_experiment_outcomes,
    suggest_scope,
)
from btf_viewer_pkg.ai_tools import (  # noqa: E402
    AI_TOOL_PLAN_INVESTIGATION,
    AI_VIEWER_TOOL_NAMES,
    is_query_tool,
    validate_tool_call,
)


class PlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        set_experiment_outcomes([])
        self.findings = [
            {
                "id": "mig1",
                "title": "Migration thrash",
                "text": "CS[22] ping-pong between cores",
                "task": "CS[22]",
                "severity": "error",
                "evidence": [{"time": 1060000, "label": "migration: burst"}],
            },
            {
                "id": "dl1",
                "title": "Deadline miss",
                "text": "CS[22] missed deadline after migrations",
                "task": "CS[22]",
                "severity": "error",
            },
        ]

    def test_plan_and_scope(self) -> None:
        plan = plan_investigation(self.findings, question="Why did CS[22] miss?")
        self.assertTrue(plan["ok"])
        self.assertTrue(plan["hypotheses"])
        self.assertIn("detect_contradictions", plan["steps"])
        scope = suggest_scope("Why did CS[22] miss its deadline?", self.findings)
        self.assertEqual(scope["task"], "CS[22]")
        self.assertTrue(scope["apply_scope"])

    def test_contradiction_and_stop(self) -> None:
        hit = detect_contradictions(
            self.findings,
            hypothesis="Mutex contention causes deadline miss",
            metrics={"execution": 42, "blocking": 3, "mutex_hold": 0},
        )
        self.assertEqual(hit["verdict"], "CONTRADICTED")
        scored = score_hypotheses(plan_investigation(self.findings)["hypotheses"],
                                  findings=self.findings, contradictions=[hit])
        self.assertTrue(scored)
        stop = assess_evidence_sufficiency(
            self.findings,
            tools_run=["investigate", "correlate_events"],
        )
        self.assertIn(stop["recommendation"], ("STOP INVESTIGATION", "CONTINUE"))

    def test_cluster_fingerprint_similar_causal_plan(self) -> None:
        cl = cluster_findings(self.findings)
        self.assertGreaterEqual(cl["incidents"][0]["count"], 1)
        fp = generate_fingerprint(self.findings)
        self.assertIn(fp["scheduling"]["migration"], ("HIGH", "MEDIUM"))
        rec = record_experiment_outcome(
            change="pin CS[22] to Core_0",
            predicted="migrations -50%",
            actual="migrations -50%",
            findings=self.findings,
        )
        self.assertEqual(rec["outcome"]["quality"], "GOOD")
        sim = find_similar_investigations(self.findings)
        self.assertTrue(sim["matches"])
        chain = build_causal_chain(self.findings)
        self.assertTrue(chain["edges"])
        self.assertIn("causation", chain["disclaimer"])
        loc = regression_localize(
            {"execution": 131, "migrations": 10},
            {"execution": 100, "migrations": 3},
            findings=self.findings,
        )
        self.assertIn("migration", loc["likely_mechanism"])
        plan = generate_experiment_plan(self.findings)
        self.assertTrue(plan["experiments"])

    def test_phase3_metrics_and_tool_schema(self) -> None:
        m = score_investigation_metrics(
            expected={"tasks": ["CS[22]"]},
            actual_conclusion="CS[22] migration thrash",
            tools=["plan_investigation", "detect_contradictions",
                   "assess_evidence_sufficiency"],
            passed=True,
            finding_score=80,
        )
        for key in (
            "evidence_efficiency", "investigation_cost", "false_confidence",
            "falsification_quality", "scope_accuracy", "stop_efficiency",
        ):
            self.assertIn(key, m)
        self.assertIn(AI_TOOL_PLAN_INVESTIGATION, AI_VIEWER_TOOL_NAMES)
        self.assertTrue(is_query_tool("plan_investigation"))
        args, err = validate_tool_call("detect_contradictions", {"hypothesis": "x"})
        self.assertFalse(err)
        self.assertEqual(args["hypothesis"], "x")


if __name__ == "__main__":
    unittest.main()
