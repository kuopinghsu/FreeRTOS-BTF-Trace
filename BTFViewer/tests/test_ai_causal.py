"""Causal / temporal engines (Desktop)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.ai_causal import (  # noqa: E402
    analyze_distribution,
    analyze_periodicity,
    collect_periodicity_times,
    analyze_temporal_causality,
    build_task_dependency_graph,
    collect_dependency_edges,
    challenge_conclusion,
    close_investigation,
    cluster_incidents,
    decompose_response_time,
    investigation_memory,
    rank_root_causes,
    set_investigation_memory,
    summarize_investigation_context,
    verify_claim,
)
from btf_viewer_pkg.ai_tools import (  # noqa: E402
    AI_TOOL_ANALYZE_TEMPORAL_CAUSALITY,
    AI_TOOL_BUILD_TASK_DEPENDENCY_GRAPH,
    AI_VIEWER_TOOL_NAMES,
    dependency_trace_context,
    distribution_trace_context,
    is_query_tool,
    validate_tool_call,
)


class CausalTests(unittest.TestCase):
    def setUp(self) -> None:
        set_investigation_memory([])
        self.findings = [
            {
                "id": "blk",
                "title": "Mutex blocking",
                "text": "CS[22] blocked waiting for Mutex held by Idle[1] jump:1000",
                "task": "CS[22]",
                "time": 1000,
            },
            {
                "id": "pre",
                "title": "Preemption",
                "text": "High[3] preempts CS[22] jump:2000",
                "task": "High[3]",
                "time": 2000,
            },
        ]

    def test_temporal_and_graph(self) -> None:
        chain = analyze_temporal_causality(self.findings, task="CS[22]")
        self.assertTrue(chain["ok"])
        self.assertGreaterEqual(len(chain["events"]), 1)
        graph = build_task_dependency_graph(self.findings)
        self.assertTrue(graph["nodes"])
        self.assertEqual(graph["source"], "findings")
        parts = decompose_response_time(self.findings, task="CS[22]")
        self.assertTrue(parts["parts"])
        ranked = rank_root_causes(self.findings)
        self.assertTrue(ranked["ranked"])

    def test_verify_and_challenge(self) -> None:
        hit = verify_claim(
            "CS[22] blocked on mutex",
            subject="CS[22]",
            findings=self.findings,
        )
        self.assertIn(hit["verdict"], ("SUPPORTED", "PARTIAL", "UNSUPPORTED"))
        alt = challenge_conclusion("mutex blocking", findings=self.findings)
        self.assertTrue(alt["ok"])

    def test_memory_and_close(self) -> None:
        stored = investigation_memory(
            "store",
            record={"finding": "Mutex blocking", "pattern": "mutex", "fix": "pin"},
            findings=self.findings,
        )
        self.assertEqual(stored["count"], 1)
        rec = investigation_memory("recall", findings=self.findings)
        self.assertTrue(rec["matches"])
        closed = close_investigation("mutex", findings=self.findings)
        self.assertEqual(closed["case"]["status"], "closed")

    def test_stats_and_summary(self) -> None:
        dist = analyze_distribution([1, 2, 3, 10], metric="ms")
        self.assertEqual(dist["n"], 4)
        self.assertEqual(dist["source"], "values")
        self.assertEqual(dist["p50"], 3)
        self.assertEqual(dist["p90"], 10)
        self.assertEqual(dist["p99.9"], 10)
        self.assertGreater(dist["stddev"], 0)
        self.assertGreater(dist["cv"], 0)
        self.assertEqual(dist["outlier_rate"], 0)
        tail = analyze_distribution([1] * 50 + [100])
        self.assertGreater(tail["outlier_rate"], 0)
        found = analyze_distribution(
            findings=[{"text": "blocked 12 ms jump:1000"}])
        self.assertEqual(found["source"], "findings")
        self.assertGreaterEqual(found["n"], 1)
        per = analyze_periodicity([10, 20, 30, 40])
        self.assertTrue(per["ok"])
        self.assertEqual(per["kind"], "stable period")
        self.assertEqual(per["expected"], 10)
        self.assertEqual(per["peak_to_peak"], 0)
        drift = analyze_periodicity(
            [0, 12, 24, 36], expected=10)
        self.assertEqual(drift["kind"], "period drift")
        jitter = analyze_periodicity(
            [0, 10, 19, 32, 41], expected=10)
        self.assertEqual(jitter["kind"], "release jitter")
        inter = analyze_periodicity(
            [0, 10, 20, 50],
            expected=10,
            findings=[{"title": "preempt", "text": "ISR preempts CS[22]"}],
        )
        self.assertEqual(inter["kind"], "scheduler interference")
        wcet = analyze_periodicity(
            [0, 10, 20, 30],
            expected=10,
            durations=[1, 8, 2, 9],
        )
        self.assertEqual(wcet["kind"], "execution-time variation")
        ticks = collect_periodicity_times(
            source="tick", tick_times=[0, 1000, 2000, 3000])
        self.assertEqual(ticks, [0.0, 1000.0, 2000.0, 3000.0])
        cl = cluster_incidents(self.findings, window_ns=500)
        self.assertTrue(cl["incidents"])
        summary = summarize_investigation_context(
            self.findings, tools_run=["investigate"], conclusion="mutex")
        self.assertEqual(summary["summary"]["finding_count"], 2)

    def test_btf_dependency_edges(self) -> None:
        holds = [
            {
                "kind": "mutex", "key": "mutex:M", "holder": "Holder[1]",
                "start_ns": 0, "stop_ns": 100, "duration_ns": 100,
            },
            {
                "kind": "mutex", "key": "mutex:M", "holder": "Waiter[2]",
                "start_ns": 100, "stop_ns": 150, "duration_ns": 50,
            },
        ]
        pre = [{"preemptor": "Hog[3]", "victim": "Waiter[2]", "count": 2, "weight": 80}]
        migs = [{"task": "Waiter[2]", "from_core": "Core_0", "to_core": "Core_1"}]
        pi = [{
            "task": "Waiter[2]", "inherited": True,
            "medium_tasks": ["Holder[1]"],
        }]
        kinds = {(e["from"], e["to"], e["kind"]) for e in collect_dependency_edges(
            sync_holds=holds, preemptions=pre, migrations=migs,
            priority_episodes=pi,
        )}
        self.assertIn(("Holder[1]", "mutex:M", "owns"), kinds)
        self.assertIn(("Waiter[2]", "mutex:M", "waits-for"), kinds)
        self.assertIn(("Holder[1]", "Waiter[2]", "blocks"), kinds)
        self.assertIn(("Hog[3]", "Waiter[2]", "preempts"), kinds)
        self.assertIn(("Waiter[2]", "Core_1", "migrates-to"), kinds)
        self.assertIn(("Waiter[2]", "Holder[1]", "inherits-priority-from"), kinds)
        graph = build_task_dependency_graph(
            [],
            sync_holds=holds,
            preemptions=pre,
            migrations=migs,
            priority_episodes=pi,
            task="Waiter[2]",
        )
        self.assertEqual(graph["source"], "btf")
        self.assertIn("Holder[1]", graph["responsible"])
        self.assertIn("Hog[3]", graph["responsible"])
        self.assertIn("BTF", graph["disclaimer"])

    def test_tool_registration(self) -> None:
        self.assertIn(AI_TOOL_ANALYZE_TEMPORAL_CAUSALITY, AI_VIEWER_TOOL_NAMES)
        self.assertTrue(is_query_tool(AI_TOOL_ANALYZE_TEMPORAL_CAUSALITY))
        args, err = validate_tool_call(
            AI_TOOL_ANALYZE_TEMPORAL_CAUSALITY, {"task": "CS[22]"})
        self.assertEqual(err, "")
        self.assertEqual(args["task"], "CS[22]")
        args, err = validate_tool_call(
            AI_TOOL_BUILD_TASK_DEPENDENCY_GRAPH, {"task": "Waiter[2]"})
        self.assertEqual(err, "")
        self.assertEqual(args["task"], "Waiter[2]")

    def test_dependency_trace_context_reads_sync_holds(self) -> None:
        class _Trace:
            sync_objects = {
                "mutex:M": {
                    "kind": "mutex",
                    "key": "mutex:M",
                    "ptr": "M",
                    "holds": [{
                        "start_ns": 10,
                        "stop_ns": 20,
                        "duration_ns": 10,
                        "holder_label": "A[1]",
                        "signal": False,
                    }],
                }
            }
            task_repr = {}
            priority_episodes = []

        ctx = dependency_trace_context(_Trace())
        self.assertEqual(ctx["sync_holds"][0]["holder"], "A[1]")
        self.assertEqual(ctx["sync_holds"][0]["key"], "mutex:M")

    def test_distribution_trace_context_tick_and_execution(self) -> None:
        class _Seg:
            def __init__(self, start, end):
                self.start = start
                self.end = end
                self.core = "Core_0"

        class _Trace:
            tasks = ["CS[22]"]
            tick_sti_times = [0, 1000, 2000, 4000]
            task_repr = {"CS[22]": "CS[22]"}
            seg_map_by_merge_key = {
                "CS[22]": [_Seg(0, 10), _Seg(20, 40)],
            }

        ticks = distribution_trace_context(_Trace(), metric="tick")
        self.assertEqual(ticks["values"], [1000, 1000, 2000])
        self.assertEqual(ticks["source"], "btf")
        execs = distribution_trace_context(_Trace(), "CS[22]", "execution")
        self.assertEqual(execs["values"], [10, 20])
        gaps = distribution_trace_context(_Trace(), "CS[22]", "blocking")
        self.assertEqual(gaps["values"], [10])


if __name__ == "__main__":
    unittest.main()
