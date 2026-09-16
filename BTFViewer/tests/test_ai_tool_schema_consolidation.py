"""AI tool-schema consolidation.

- No two model-visible tools are functional aliases of one another.
- Every context mode returns an explicit, bounded schema list (Full Evidence no
  longer sends the whole catalog).
- Simulation / optimization / memory / clustering / export tools appear only
  when the active stage calls for them.
- Hidden aliases stay dispatchable so stored workflows do not break.
"""

from __future__ import annotations

import unittest

from btf_viewer_pkg.ai_tools import (
    AI_TOOL_CANONICAL_ALIASES,
    AI_VIEWER_TOOL_NAMES,
    ai_viewer_tools,
    ai_viewer_tools_for_mode,
    canonical_tool_name,
    validate_tool_call,
)
from btf_viewer_pkg.ai_case import tool_names_for_context_mode

_MODES = ("compact", "balanced", "full")
_STAGES = ("triage", "scope", "investigate", "verify", "experiment", "compare", "report")
_ON_REQUEST = (
    "what_if", "optimize_experiment", "recommend_experiments",
    "investigation_memory", "find_similar_investigations",
    "record_experiment_outcome", "close_investigation",
    "generate_report", "export_report", "export_investigation",
)


def _emitted() -> set:
    return {t["function"]["name"] for t in ai_viewer_tools()}


def _mode_names(mode: str, stage: str) -> set:
    return {t["function"]["name"] for t in ai_viewer_tools_for_mode(mode, stage)}


class NoModelVisibleAliasesTests(unittest.TestCase):
    def test_alias_map_targets_are_real_canonical_tools(self) -> None:
        for alias, canon in AI_TOOL_CANONICAL_ALIASES.items():
            self.assertIn(alias, AI_VIEWER_TOOL_NAMES, alias)
            self.assertIn(canon, AI_VIEWER_TOOL_NAMES, canon)
            self.assertNotIn(canon, AI_TOOL_CANONICAL_ALIASES, canon)

    def test_aliases_are_not_emitted_as_schemas(self) -> None:
        emitted = _emitted()
        for alias in AI_TOOL_CANONICAL_ALIASES:
            self.assertNotIn(alias, emitted, alias)
        # …but the canonical twin still is.
        for canon in set(AI_TOOL_CANONICAL_ALIASES.values()):
            self.assertIn(canon, emitted, canon)

    def test_emitted_schemas_are_the_name_list_minus_aliases(self) -> None:
        self.assertEqual(
            [t["function"]["name"] for t in ai_viewer_tools()],
            [n for n in AI_VIEWER_TOOL_NAMES if n not in AI_TOOL_CANONICAL_ALIASES],
        )

    def test_hidden_aliases_still_dispatch(self) -> None:
        for alias in AI_TOOL_CANONICAL_ALIASES:
            # A stored workflow or older model can still call it.
            self.assertEqual(canonical_tool_name(alias), alias)
            args, err = validate_tool_call(alias, {})
            self.assertEqual(err, "", alias)
            self.assertIsInstance(args, dict)


class BoundedContextModeTests(unittest.TestCase):
    def test_every_mode_and_stage_returns_an_explicit_bounded_list(self) -> None:
        emitted = _emitted()
        for mode in _MODES:
            for stage in _STAGES:
                names = tool_names_for_context_mode(mode, stage)
                self.assertIsInstance(names, list, (mode, stage))
                self.assertTrue(names, (mode, stage))
                self.assertTrue(
                    set(names) < emitted or set(names) == emitted and mode != "full",
                    (mode, stage, "sends everything"),
                )
                self.assertLess(len(names), len(emitted) + 1)

    def test_full_evidence_is_not_the_whole_catalog(self) -> None:
        emitted = _emitted()
        for stage in _STAGES:
            full = _mode_names("full", stage)
            self.assertTrue(full < emitted, stage)

    def test_full_evidence_keeps_the_measured_evidence_loop(self) -> None:
        full = _mode_names("full", "triage")
        for keep in (
            "investigate", "correlate_events", "find_critical_path",
            "compare_performance", "detect_anomalies", "query_raw_metric",
            "search_timeline", "regression_explain", "detect_priority_inversion",
            "verify_claim", "detect_contradictions",
        ):
            self.assertIn(keep, full, keep)


class OnRequestGatingTests(unittest.TestCase):
    def test_ordinary_triage_excludes_sim_opt_memory_clustering_export(self) -> None:
        for mode in _MODES:
            names = set(tool_names_for_context_mode(mode, "triage"))
            for gated in _ON_REQUEST + ("cluster_findings",):
                self.assertNotIn(gated, names, (mode, gated))

    def test_experiment_stage_brings_back_simulation_and_optimization(self) -> None:
        full_exp = _mode_names("full", "experiment")
        for t in ("what_if", "optimize_experiment", "recommend_experiments"):
            self.assertIn(t, full_exp, t)

    def test_report_stage_brings_back_export(self) -> None:
        full_report = _mode_names("full", "report")
        for t in ("generate_report", "export_report", "export_investigation"):
            self.assertIn(t, full_report, t)

    def test_verify_and_report_bring_back_investigation_memory(self) -> None:
        for stage in ("verify", "report"):
            names = _mode_names("full", stage)
            self.assertIn("investigation_memory", names, stage)
            self.assertIn("find_similar_investigations", names, stage)


class SnapshotTests(unittest.TestCase):
    # Model-visible schema names per (mode, stage). Update deliberately — a diff
    # here means the AI's tool surface changed.
    EXPECTED = {
        ("compact", "triage"): [
            "detect_anomalies", "suggest_scope", "search_timeline",
            "query_raw_metric", "summarize_investigation_context",
        ],
        ("compact", "report"): [
            "generate_report", "export_report", "search_timeline",
            "query_raw_metric", "summarize_investigation_context",
        ],
    }

    def test_snapshot_small_modes(self) -> None:
        for (mode, stage), expected in self.EXPECTED.items():
            got = tool_names_for_context_mode(mode, stage)
            self.assertEqual(got, expected, (mode, stage))

    def test_full_triage_snapshot_size_and_membership(self) -> None:
        full = tool_names_for_context_mode("full", "triage")
        # A stable, auditable set — not the whole catalog.
        self.assertEqual(len(full), 43)
        self.assertEqual(len(set(full)), len(full))  # no dupes


if __name__ == "__main__":
    unittest.main()
