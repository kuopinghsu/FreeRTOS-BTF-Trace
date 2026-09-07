"""Investigation Findings — structured model, catalog, dedup, ranking, empty state.

Parity with ``web/tests/investigationFindings.test.js``.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.investigation_findings import (  # noqa: E402
    FINDING_STATUS_BOOKMARKED,
    FINDING_STATUS_DISMISSED,
    FINDING_STATUS_NEW,
    FINDING_STATUS_REVIEWED,
    NO_FINDINGS_UNDER_RULES,
    RULE_CATALOG,
    RULE_IDS,
    build_investigation_findings,
    dedupe_investigation_findings,
    investigation_finding_export,
    normalize_investigation_finding,
    parse_measured_values,
    rank_investigation_findings,
    rule_spec,
)


def _raw(**kw):
    base = dict(severity="warning", title="T", text="body", id="", evidence=[])
    base.update(kw)
    return base


class ModelTests(unittest.TestCase):
    def test_rule_id_from_id_and_slug_suffix(self):
        f = normalize_investigation_finding(_raw(id="thrashing"))
        self.assertEqual(f["rule_id"], "thrashing")
        f2 = normalize_investigation_finding(_raw(id="thrashing-2"))
        self.assertEqual(f2["rule_id"], "thrashing")  # numeric suffix folded
        self.assertEqual(f2["id"], "thrashing-2")     # per-report id preserved

    def test_rule_id_explicit_field_wins(self):
        f = normalize_investigation_finding(_raw(id="x9", rule_id="tick_health"))
        self.assertEqual(f["rule_id"], "tick_health")

    def test_comparison_basis_filled_from_catalog(self):
        f = normalize_investigation_finding(_raw(id="load_imbalance"))
        self.assertEqual(f["comparison_basis"], RULE_CATALOG["load_imbalance"].comparison_basis)
        # explicit value on the raw finding is not overwritten
        f2 = normalize_investigation_finding(_raw(id="load_imbalance", comparison_basis="custom"))
        self.assertEqual(f2["comparison_basis"], "custom")

    def test_measured_values_passthrough_and_fallback_parse(self):
        struct = normalize_investigation_finding(_raw(
            id="tick_health",
            measured_values=[{"name": "CV", "value": 12.5, "unit": "%", "sample_count": 40}],
        ))
        self.assertEqual(struct["measured_values"][0]["sample_count"], 40)
        parsed = normalize_investigation_finding(_raw(
            id="load_imbalance",
            evidence_text="Load Balance Score 62% (σ=24.0%, G=0.31)",
        ))
        names = {m["name"] for m in parsed["measured_values"]}
        self.assertIn("Score", names)
        self.assertIn("σ", names)

    def test_parse_measured_values_is_conservative(self):
        self.assertEqual(parse_measured_values("564 migrations"), [])
        got = parse_measured_values("Worker (Max 10us), n=3")
        self.assertEqual(got, [
            {"name": "Max", "value": 10, "unit": "µs"},
            {"name": "n", "value": 3, "unit": ""},
        ])

    def test_entities_from_task_then_scraped_cores(self):
        self.assertEqual(
            normalize_investigation_finding(_raw(task="Worker"))["entities"], ["Worker"])
        scraped = normalize_investigation_finding(_raw(
            text="Core_0→Core_1 hot pair"))["entities"]
        self.assertEqual(scraped, ["Core_0", "Core_1"])

    def test_affected_range_from_evidence_times(self):
        f = normalize_investigation_finding(_raw(
            evidence=[{"label": "a", "time": 500}, {"label": "b", "time": 100}]))
        self.assertEqual(f["affected_range"], {"start": 100, "end": 500})

    def test_affected_range_explicit_wins(self):
        f = normalize_investigation_finding(_raw(
            affected_range={"start": 1, "end": 9},
            evidence=[{"label": "a", "time": 500}]))
        self.assertEqual(f["affected_range"], {"start": 1, "end": 9})

    def test_status_from_triage_state(self):
        state = {"reviewed": ["a"], "case": ["b"], "dismissed": {"c": "noise"}}
        self.assertEqual(
            normalize_investigation_finding(_raw(id="a"), triage_state=state)["status"],
            FINDING_STATUS_REVIEWED)
        self.assertEqual(
            normalize_investigation_finding(_raw(id="b"), triage_state=state)["status"],
            FINDING_STATUS_BOOKMARKED)
        self.assertEqual(
            normalize_investigation_finding(_raw(id="c"), triage_state=state)["status"],
            FINDING_STATUS_DISMISSED)
        self.assertEqual(
            normalize_investigation_finding(_raw(id="d"), triage_state=state)["status"],
            FINDING_STATUS_NEW)

    def test_limitations_from_low_confidence(self):
        f = normalize_investigation_finding(_raw(confidence="Medium — heuristic threshold"))
        self.assertTrue(f["limitations"])
        f2 = normalize_investigation_finding(_raw(confidence="High — measured CPU share"))
        self.assertEqual(f2["limitations"], [])

    def test_original_fields_preserved(self):
        f = normalize_investigation_finding(_raw(id="tick_health", inspect="Trace Health (TICK)"))
        self.assertEqual(f["inspect"], "Trace Health (TICK)")
        self.assertEqual(f["title"], "T")

    def test_catalog_covers_all_engine_rule_ids(self):
        # Every fid the desktop rule engine can emit must be catalogued.
        import btf_viewer_pkg.stats as _  # noqa: F401 (ensures import path)
        engine_ids = {
            "load_imbalance", "load_balance_ok", "load_balance_moderate", "top_cpu",
            "exec_max", "blocking", "priority_inversion", "thrashing", "hot_pairs",
            "deadlines", "tick_health", "missed_ticks", "sync_bounce", "sync_issues",
            "migration_burst_anomaly", "wcet_anomaly", "none",
        }
        self.assertTrue(engine_ids <= set(RULE_IDS), engine_ids - set(RULE_IDS))

    def test_rule_spec_lookup(self):
        self.assertIsNone(rule_spec("nope"))
        self.assertEqual(rule_spec("deadlines").severity, "error")


class DedupeTests(unittest.TestCase):
    def _n(self, **kw):
        return normalize_investigation_finding(_raw(**kw))

    def test_same_rule_overlapping_range_and_entity_merges(self):
        a = self._n(id="thrashing", task="CS", affected_range={"start": 0, "end": 100},
                    evidence=[{"label": "x", "time": 10}])
        b = self._n(id="thrashing", task="CS", affected_range={"start": 50, "end": 200},
                    evidence=[{"label": "y", "time": 120}])
        out = dedupe_investigation_findings([a, b])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["affected_range"], {"start": 0, "end": 200})
        self.assertEqual(out[0]["merged_count"], 2)
        self.assertEqual(len(out[0]["evidence_refs"]), 2)

    def test_disjoint_ranges_do_not_merge(self):
        a = self._n(id="thrashing", task="CS", affected_range={"start": 0, "end": 100})
        b = self._n(id="thrashing", task="CS", affected_range={"start": 101, "end": 200})
        self.assertEqual(len(dedupe_investigation_findings([a, b])), 2)

    def test_boundary_touching_ranges_merge(self):
        a = self._n(id="thrashing", task="CS", affected_range={"start": 0, "end": 100})
        b = self._n(id="thrashing", task="CS", affected_range={"start": 100, "end": 200})
        self.assertEqual(len(dedupe_investigation_findings([a, b])), 1)

    def test_different_entities_do_not_merge(self):
        a = self._n(id="thrashing", task="CS", affected_range={"start": 0, "end": 100})
        b = self._n(id="thrashing", task="Worker", affected_range={"start": 0, "end": 100})
        self.assertEqual(len(dedupe_investigation_findings([a, b])), 2)

    def test_different_rules_do_not_merge(self):
        a = self._n(id="thrashing", task="CS", affected_range={"start": 0, "end": 100})
        b = self._n(id="hot_pairs", task="CS", affected_range={"start": 0, "end": 100})
        self.assertEqual(len(dedupe_investigation_findings([a, b])), 2)

    def test_survivor_is_higher_severity(self):
        a = self._n(id="tick_health", severity="warning", task="C",
                    affected_range={"start": 0, "end": 10})
        b = self._n(id="tick_health", severity="error", task="C",
                    affected_range={"start": 0, "end": 10})
        out = dedupe_investigation_findings([a, b])
        self.assertEqual(out[0]["severity"], "error")

    def test_dedupe_is_deterministic(self):
        items = [
            self._n(id="thrashing", task="CS", affected_range={"start": 0, "end": 100}),
            self._n(id="thrashing", task="CS", affected_range={"start": 40, "end": 90}),
            self._n(id="hot_pairs", task="CS"),
        ]
        self.assertEqual(
            dedupe_investigation_findings(items),
            dedupe_investigation_findings(list(reversed(items))),
        )


class RankingTests(unittest.TestCase):
    def _n(self, **kw):
        return normalize_investigation_finding(_raw(**kw))

    def test_severity_dominates(self):
        out = rank_investigation_findings([
            self._n(id="top_cpu", severity="info"),
            self._n(id="deadlines", severity="error"),
            self._n(id="thrashing", severity="warning"),
        ])
        self.assertEqual([f["severity"] for f in out], ["error", "warning", "info"])

    def test_duration_breaks_ties_within_severity(self):
        short = self._n(id="thrashing", severity="warning",
                        affected_range={"start": 0, "end": 1_000})
        long = self._n(id="hot_pairs", severity="warning",
                       affected_range={"start": 0, "end": 300_000})
        out = rank_investigation_findings([short, long], total_span_ns=1_000_000)
        self.assertEqual(out[0]["id"], "hot_pairs")

    def test_evidence_quality_breaks_ties(self):
        timed = self._n(id="thrashing", severity="warning",
                        evidence=[{"label": "a", "time": 5}])
        untimed = self._n(id="hot_pairs", severity="warning", evidence=[])
        out = rank_investigation_findings([untimed, timed])
        self.assertEqual(out[0]["id"], "thrashing")

    def test_stable_order_on_full_tie(self):
        a = self._n(id="aaa", severity="info", evidence=[])
        b = self._n(id="bbb", severity="info", evidence=[])
        self.assertEqual(
            [f["id"] for f in rank_investigation_findings([b, a])], ["aaa", "bbb"])

    def test_structured_threshold_does_not_sink_below_peers(self):
        # A barely-exceeded threshold should still outrank a same-severity
        # info finding.
        warn = self._n(id="load_imbalance", severity="warning",
                       measured_values=[{"name": "σ", "value": 30.3, "unit": "%",
                                         "threshold": 30.0}])
        info = self._n(id="top_cpu", severity="info")
        out = rank_investigation_findings([info, warn])
        self.assertEqual(out[0]["id"], "load_imbalance")


class PipelineTests(unittest.TestCase):
    def test_build_normalises_dedupes_ranks(self):
        raw = [
            _raw(id="thrashing", severity="warning", task="CS",
                 affected_range={"start": 0, "end": 100}),
            _raw(id="thrashing", severity="error", task="CS",
                 affected_range={"start": 50, "end": 150}),
            _raw(id="top_cpu", severity="info", task="Worker"),
        ]
        out = build_investigation_findings(raw, total_span_ns=1_000)
        self.assertEqual(len(out), 2)                # two thrashing merged
        self.assertEqual(out[0]["rule_id"], "thrashing")
        self.assertEqual(out[0]["severity"], "error")
        self.assertGreater(out[0]["rank_score"], out[1]["rank_score"])

    def test_build_can_skip_dedupe(self):
        raw = [
            _raw(id="thrashing", task="CS", affected_range={"start": 0, "end": 100}),
            _raw(id="thrashing", task="CS", affected_range={"start": 0, "end": 100}),
        ]
        self.assertEqual(len(build_investigation_findings(raw, dedupe=False)), 2)

    def test_export_shape(self):
        f = build_investigation_findings([_raw(id="tick_health", severity="error")])[0]
        e = investigation_finding_export(f)
        self.assertEqual(set(e) >= {
            "id", "rule_id", "severity", "status", "observation", "category",
            "comparison_basis", "affected_range", "entities", "measured_values",
            "evidence_refs", "limitations", "rank_score",
        }, True)
        self.assertNotIn("evidence_text", e)  # display text is dropped


class EmptyStateTests(unittest.TestCase):
    def test_constant_wording(self):
        self.assertEqual(NO_FINDINGS_UNDER_RULES, "No findings under the current rules")
        self.assertNotIn("problem", NO_FINDINGS_UNDER_RULES.lower())

    def test_engine_empty_finding_uses_the_wording(self):
        from btf_viewer_pkg._bootstrap import install
        install()
        from btf_viewer_pkg.stats import _build_workflow_analysis_findings
        out = _build_workflow_analysis_findings(
            core_rows=[], exec_rows=[], block_rows=[], mig_rows=[], pair_rows=[],
            priority_rows=[], sync_rows=[], sync_issues=[], tick={"tick_count": 0},
            deadline_viols=None, time_scale="us")
        titles = [f["title"] for f in out]
        self.assertIn(NO_FINDINGS_UNDER_RULES, titles)
        self.assertNotIn("No analysis heuristics flagged", titles)


class DesktopWebParityTests(unittest.TestCase):
    def test_module_and_js_stay_in_step(self):
        py = (BTF_ROOT / "btf_viewer_pkg" / "investigation_findings.py").read_text("utf-8")
        js = (BTF_ROOT / "web" / "src" / "utils" / "investigationFindings.js").read_text("utf-8")
        for rid in RULE_IDS:
            self.assertIn(f'"{rid}"', py, rid)
            self.assertIn(f"'{rid}'", js, rid)
        for py_name, js_name in (
            ("def build_investigation_findings", "export function buildInvestigationFindings"),
            ("def normalize_investigation_finding", "export function normalizeInvestigationFinding"),
            ("def dedupe_investigation_findings", "export function dedupeInvestigationFindings"),
            ("def rank_investigation_findings", "export function rankInvestigationFindings"),
            ("def investigation_finding_export", "export function investigationFindingExport"),
            ("def parse_measured_values", "export function parseMeasuredValues"),
            ("NO_FINDINGS_UNDER_RULES", "export const NO_FINDINGS_UNDER_RULES"),
        ):
            self.assertIn(py_name, py, py_name)
            self.assertIn(js_name, js, js_name)
        # Blend weights must match.
        for token in ("0.50", "0.25", "0.15", "0.10", "0.25"):
            self.assertIn(token, py)
            self.assertIn(token, js)

    def test_empty_state_wording_removed_everywhere(self):
        cases = (
            ("btf_viewer_pkg/stats.py", "NO_FINDINGS_UNDER_RULES"),
            ("web/src/utils/workflowAnalysis.js", "No findings under the current rules"),
        )
        for rel, want in cases:
            txt = (BTF_ROOT / rel).read_text("utf-8")
            self.assertNotIn("No analysis heuristics flagged", txt, rel)
            self.assertNotIn("No findings for the current scope", txt, rel)
            self.assertIn(want, txt, rel)


if __name__ == "__main__":
    unittest.main()
