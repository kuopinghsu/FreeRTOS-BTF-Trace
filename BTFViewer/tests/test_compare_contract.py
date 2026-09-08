"""Trace Compare A/B contract (BTFVIEWER_DESIGN_CONSISTENCY_TODO step 1).

Public contract:
- Trace A is Baseline A, Trace B is Candidate B.
- ``compare_performance_metrics`` / ``compare_performance_tabs`` take Baseline A
  first and Candidate B second.
- Verdicts describe Candidate B relative to Baseline A: a lower-is-better metric
  regresses when Candidate B is higher; a higher-is-better metric improves when
  Candidate B is higher.
- The displayed table delta stays ``A - B``; the low-level
  ``evaluate_regression(candidate, baseline)`` contract is unchanged.
"""

import os
import unittest

from btf_viewer_pkg.ai_investigation import (
    compare_performance_metrics,
    evaluate_regression,
    normalize_compare_payload,
    snapshot_from_summary,
)
from btf_viewer_pkg.ai_tools import AI_TOOL_PROMPT, compare_performance_tabs


BUILDS = os.path.join(os.path.dirname(__file__), os.pardir, "builds")


def _metrics(**kw):
    base = {
        "migrations": 100,
        "migrated_tasks": 20,
        "load_balance_score": 90.0,
        "missed_ticks": 0,
    }
    base.update(kw)
    return snapshot_from_summary(base, name=kw.get("name", ""))


class CompareContractTest(unittest.TestCase):
    def test_lower_is_better_regresses_when_candidate_b_higher(self) -> None:
        baseline_a = _metrics(migrations=100)
        candidate_b = _metrics(migrations=200)  # more migrations on B -> worse
        cmp = compare_performance_metrics(
            baseline_a, candidate_b, label_a="A", label_b="B",
        )
        self.assertTrue(cmp["failed"])
        self.assertEqual((cmp["primary_regression"] or {}).get("id"), "migrations")

    def test_lower_is_better_no_regression_when_candidate_b_lower(self) -> None:
        baseline_a = _metrics(migrations=200)
        candidate_b = _metrics(migrations=100)  # fewer migrations on B -> better
        cmp = compare_performance_metrics(baseline_a, candidate_b)
        self.assertFalse(cmp["failed"])

    def test_higher_is_better_improves_when_candidate_b_higher(self) -> None:
        baseline_a = _metrics(load_balance_score=60.0)
        candidate_b = _metrics(load_balance_score=95.0)  # better balance on B
        cmp = compare_performance_metrics(baseline_a, candidate_b)
        self.assertFalse(cmp["failed"])
        lb = next(c for c in cmp["checks"] if c["id"] == "load_balance")
        self.assertEqual(lb["status"], "pass")
        # Candidate B scores 35 points higher than Baseline A: an improvement.
        self.assertIn("Δ score +35.0", lb["detail"])

    def test_higher_is_better_regresses_when_candidate_b_lower(self) -> None:
        baseline_a = _metrics(load_balance_score=95.0)
        candidate_b = _metrics(load_balance_score=60.0)  # worse balance on B
        cmp = compare_performance_metrics(baseline_a, candidate_b)
        self.assertTrue(cmp["failed"])
        self.assertEqual((cmp["primary_regression"] or {}).get("id"), "load_balance")

    def test_swapping_inputs_flips_the_verdict(self) -> None:
        good = _metrics(migrations=80, load_balance_score=95.0)
        bad = _metrics(migrations=180, load_balance_score=60.0)
        forward = compare_performance_metrics(good, bad)   # Baseline good, Cand bad
        reverse = compare_performance_metrics(bad, good)   # Baseline bad, Cand good
        self.assertTrue(forward["failed"])
        self.assertFalse(reverse["failed"])

    def test_payload_carries_explicit_baseline_a_and_candidate_b(self) -> None:
        cmp = compare_performance_metrics(
            _metrics(migrations=100), _metrics(migrations=150),
        )
        self.assertEqual(cmp["baseline_a"]["migrations"], 100)
        self.assertEqual(cmp["candidate_b"]["migrations"], 150)

    def test_report_columns_are_baseline_a_then_candidate_b(self) -> None:
        cmp = compare_performance_metrics(
            _metrics(migrations=100), _metrics(migrations=150),
        )
        # A column shows Baseline A (100); B column shows Candidate B (150).
        self.assertIn("(A=100, B=150)", cmp["report"])

    def test_evaluate_regression_low_level_contract_unchanged(self) -> None:
        # First arg is the candidate under test, second is the baseline.
        cand = snapshot_from_summary({"migrations": 200}, name="cand")
        base = snapshot_from_summary({"migrations": 100}, name="base")
        self.assertTrue(evaluate_regression(cand, base)["failed"])
        self.assertFalse(evaluate_regression(base, cand)["failed"])

    def test_compare_performance_tabs_direction_and_fields(self) -> None:
        payload = compare_performance_tabs(
            {"migrations": 100, "missed_ticks": 0},   # Baseline A
            {"migrations": 220, "missed_ticks": 0},   # Candidate B
            label_a="before", label_b="after",
        )
        data = payload["data"]
        self.assertTrue(data["failed"])
        self.assertEqual(data["baseline_a"]["migrations"], 100)
        self.assertEqual(data["candidate_b"]["migrations"], 220)

    def test_normalize_compare_payload_reads_new_fields(self) -> None:
        payload = compare_performance_tabs(
            {"migrations": 100}, {"migrations": 150}, label_a="A", label_b="B",
        )
        norm = normalize_compare_payload(payload)
        self.assertEqual(norm["baseline_a"]["migrations"], 100)
        self.assertEqual(norm["candidate_b"]["migrations"], 150)

    def test_normalize_compare_payload_reads_legacy_a_b_shape(self) -> None:
        legacy = {
            "data": {
                "a": {"metrics": {"migrations": 100}},
                "b": {"metrics": {"migrations": 150}},
                "label_a": "old-a",
                "label_b": "old-b",
                "checks": [],
            },
        }
        norm = normalize_compare_payload(legacy)
        self.assertEqual(norm["baseline_a"]["migrations"], 100)
        self.assertEqual(norm["candidate_b"]["migrations"], 150)
        self.assertEqual(norm["label_a"], "old-a")

    def test_normalize_compare_payload_reads_legacy_candidate_baseline(self) -> None:
        legacy = {
            "candidate": {"migrations": 150},
            "baseline": {"migrations": 100},
            "checks": [{"id": "migrations"}],
        }
        norm = normalize_compare_payload(legacy)
        self.assertEqual(norm["baseline_a"]["migrations"], 100)
        self.assertEqual(norm["candidate_b"]["migrations"], 150)

    def test_ai_prompt_states_the_a_b_contract(self) -> None:
        self.assertNotIn("A is candidate, B is baseline", AI_TOOL_PROMPT)
        self.assertIn(
            "A is Baseline A, B is Candidate B, table delta = A - B, "
            "and verdicts describe Candidate B versus Baseline A.",
            AI_TOOL_PROMPT,
        )

    def test_generated_bundles_drop_the_retired_role_string(self) -> None:
        for name in ("btf_viewer.py", "btf_viewer.html"):
            path = os.path.join(BUILDS, name)
            if not os.path.isfile(path):
                self.skipTest(f"{name} not built")
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            self.assertNotIn("A is candidate, B is baseline", text, name)


if __name__ == "__main__":
    unittest.main()
