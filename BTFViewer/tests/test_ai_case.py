"""Investigation Case, validator, quality, and offline AI benchmark."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.ai_case import (  # noqa: E402
    builtin_investigation_templates,
    build_investigation_case,
    build_validation_catalog,
    classify_trace_privacy,
    compute_evidence_quality,
    enrich_hypotheses,
    evidence_quality_band,
    falsification_checks,
    format_capability_report,
    infer_model_capability,
    interpret_investigation_query,
    load_benchmark_dataset,
    match_historical_knowledge,
    quality_bar,
    run_offline_benchmark,
    set_hypothesis_status,
    validate_ai_response,
    validate_experiment,
)
from btf_viewer_pkg.ai_investigation import (  # noqa: E402
    build_investigate_context,
    extract_evidence_panel_payload,
    format_evidence_panel_markdown,
)


class InvestigationCaseTests(unittest.TestCase):
    def test_enrich_hypotheses_supported_when_times_present(self) -> None:
        hyps = enrich_hypotheses(
            [{"hypothesis": "Core thrashing / lock bounce", "why": "High migration"}],
            evidence=[{"label": "migrations: burst", "time": 1083}],
        )
        self.assertEqual(hyps[0]["status"], "supported")
        self.assertGreaterEqual(hyps[0]["confidence"], 70)

    def test_set_hypothesis_status_rejects(self) -> None:
        hyps = enrich_hypotheses(
            [{"hypothesis": "A", "why": "x"}, {"hypothesis": "B", "why": "y"}],
        )
        out = set_hypothesis_status(hyps, hyps[1]["id"], "rejected")
        self.assertEqual(out[1]["status"], "rejected")

    def test_build_case_from_investigate_context(self) -> None:
        ctx = build_investigate_context(
            [{"id": "f1", "severity": "warning",
              "title": "Excessive bouncing / core thrashing",
              "text": "CS[22] migrates heavily",
              "evidence": [{"label": "migrations: burst", "time": 1.08}]}],
            "f1",
        )
        case = build_investigation_case(ctx)
        self.assertEqual(case["schema"], "btf-investigation-case")
        self.assertTrue(case["hypotheses"])
        self.assertIn(case["evidence_quality"]["band"], (
            "strong", "medium-high", "medium", "weak", "insufficient",
        ))
        self.assertTrue(case["falsification"]["would_disprove"])
        self.assertTrue(case["evidence_graph"]["nodes"])

    def test_quality_bar_is_not_a_percent(self) -> None:
        self.assertIn("Strong", quality_bar("strong"))
        self.assertNotIn("%", quality_bar("strong"))
        self.assertEqual(evidence_quality_band(82), "strong")
        q = compute_evidence_quality(
            score=82,
            evidence=[{"time": 1, "label": "migrations: x"},
                      {"time": 2, "label": "blocking: y"}],
        )
        self.assertEqual(q["band"], "strong")
        self.assertTrue(q["flags"]["direct_evidence"])

    def test_falsify_migration(self) -> None:
        f = falsification_checks({
            "title": "Migration thrash", "text": "CS[22] bounce",
        })
        self.assertTrue(any("migration" in x.lower() for x in f["would_disprove"]))

    def test_validator_flags_invented_task_and_out_of_window_jump(self) -> None:
        report = validate_ai_response(
            "Ghost[99] at jump:9.9 caused CS[22] stall",
            known_tasks=["CS[22]"],
            cursor_lo=1.0,
            cursor_hi=2.0,
        )
        self.assertFalse(report["ok"])
        kinds = {c["kind"] for c in report["claims"] if not c["ok"]}
        self.assertIn("task", kinds)
        self.assertIn("jump", kinds)

    def test_validator_accepts_in_scope_task(self) -> None:
        report = validate_ai_response(
            "CS[22] migrates at jump:1.5",
            known_tasks=["CS[22]"],
            cursor_lo=1.0,
            cursor_hi=2.0,
        )
        self.assertTrue(report["ok"])

    def test_interpret_and_privacy_and_capability(self) -> None:
        q = interpret_investigation_query("Why did TaskA become slow?")
        self.assertEqual(q["mode"], "diagnose")
        self.assertIn("blocking", q.get("scope") or q.get("areas") or [])
        priv = classify_trace_privacy(endpoint_is_local=True)
        self.assertEqual(priv["level"], "local")
        cap = infer_model_capability("phi4-mini:3.8b")
        self.assertIn(cap["tool_calling"], ("partial", "yes", "no", "unknown"))
        self.assertIn("Chat", format_capability_report(cap))

    def test_experiment_partial(self) -> None:
        result = validate_experiment(
            {"migrations": -70, "blocking": -10, "execution": -3},
            {"migrations": -72, "blocking": 8, "execution": -3},
        )
        self.assertEqual(result["result"], "PARTIALLY VALIDATED")

    def test_templates_and_history(self) -> None:
        tpls = builtin_investigation_templates()
        self.assertTrue(tpls)
        self.assertTrue(tpls[0].get("steps"))
        hit = match_historical_knowledge(
            "CS[22]",
            current={"migrations": 47},
            history={"CS[22]": {
                "issue": "Migration thrashing",
                "fix": "Core affinity",
                "build": "1.8.3",
                "migrations": 12,
            }},
        )
        self.assertTrue(hit.get("ok"))
        self.assertTrue(hit.get("previous_issue") or hit.get("flags"))

    def test_evidence_panel_includes_quality_and_disprove(self) -> None:
        ctx = build_investigate_context(
            [{"id": "f1", "severity": "warning",
              "title": "Mutex contention",
              "text": "TASK_A[1] blocking on mutex",
              "evidence": [{"label": "blocking: stall", "time": 1.08}]}],
            "f1",
        )
        payload = extract_evidence_panel_payload("investigate", {"ok": True, **ctx})
        self.assertIsNotNone(payload)
        self.assertIn("evidence_quality", payload)
        md = format_evidence_panel_markdown(payload, "English")
        self.assertIn("Evidence Quality", md)
        self.assertIn("disprove", md.lower())
        self.assertIn("Confidence evolution", md)

    def test_investigation_template_prompt_lists_tools(self) -> None:
        from btf_viewer_pkg.ai_case import investigation_template_prompt

        tpls = builtin_investigation_templates()
        prompt = investigation_template_prompt(tpls[0])
        self.assertIn(tpls[0]["label"], prompt)
        self.assertIn(tpls[0]["steps"][0], prompt)

    def test_catalog_extracts_tasks_from_findings(self) -> None:
        cat = build_validation_catalog(findings_text="CS[22] migrates; Idle[0] idle")
        self.assertIn("CS[22]", cat["tasks"])

    def test_offline_benchmark_dataset(self) -> None:
        root = BTF_ROOT / "tests" / "ai"
        cases = load_benchmark_dataset(str(root))
        self.assertEqual(
            [c["id"] for c in cases],
            [
                "migration_thrash",
                "mutex_contention",
                "priority_inversion",
                "deadline_miss",
                "load_imbalance",
                "trace_regression",
                "explain_region",
            ],
        )
        for case in cases:
            path = Path(case["trace_path"])
            self.assertTrue(path.is_file(), case["id"])
            text = path.read_text(encoding="utf-8")
            self.assertIn("#version", text)
            self.assertIn("#scenario", text)
        result = run_offline_benchmark(root, fail_under=50)
        self.assertTrue(result["ok"], result["report"])
        self.assertEqual(len(result["rows"]), 7)

    def test_cli_ai_test_runs_dataset(self) -> None:
        from btf_viewer_pkg.cli import _cli_ai_test_run
        from argparse import Namespace

        path = str(BTF_ROOT / "tests" / "ai")
        rc = _cli_ai_test_run(Namespace(dataset=path, fail_under=50))
        self.assertEqual(rc, 0)


class InvestigationCaseParitySurfaceTests(unittest.TestCase):
    def test_js_exports_match_python_helpers(self) -> None:
        js = (BTF_ROOT / "web/src/utils/aiCase.js").read_text(encoding="utf-8")
        for name in (
            "buildInvestigationCase",
            "validateAiResponse",
            "evidenceQualityFromScore",
            "inferModelCapability",
            "classifyTracePrivacy",
            "classifyPrivacy",
            "interpretQuestion",
            "scoreBenchmarkCase",
            "runOfflineBenchmark",
            "formatPrivacyChip",
            "investigationTemplatePrompt",
        ):
            self.assertIn(name, js, name)


if __name__ == "__main__":
    unittest.main()
