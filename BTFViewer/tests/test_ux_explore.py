"""Timeline explore helpers: anomalies, worst events, scope, compare strip."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg import _bootstrap  # noqa: E402

_bootstrap.install()

from btf_viewer_pkg.ux_explore import (  # noqa: E402
    analyze_task_periods,
    best_finding_scope,
    collect_worst_events,
    compare_summary_strip,
    detect_timeline_anomalies,
    find_event_at_percentile,
    health_inputs_from_events,
    pair_mutex_waits,
    parse_signed_delta,
    percentile_index,
    task_core_matrix,
    task_health_scores,
    top_compare_regressions,
    waiter_owner_matrix,
)


def _ev(kind, task, start, duration, mk=None):
    return {
        "kind": kind,
        "task": task,
        "mk": mk or task,
        "start": start,
        "stop": start + duration,
        "duration": duration,
        "jump_ns": start if kind == "exec" else start + duration,
        "section": {"exec": "exec", "block": "block", "inter": "inter"}.get(kind, "exec"),
        "reason": "",
    }


class UxExploreTest(unittest.TestCase):
    def test_percentile_index_matches_stats_table(self) -> None:
        self.assertEqual(percentile_index(10, 0.95), 9)
        self.assertEqual(percentile_index(20, 0.95), 18)
        self.assertEqual(percentile_index(1, 0.99), 0)

    def test_find_event_at_percentile(self) -> None:
        evs = [_ev("exec", "T[1]", i * 10, d) for i, d in enumerate((10, 20, 30, 40, 100))]
        hit = find_event_at_percentile(evs, 0.95)
        self.assertEqual(hit["duration"], 100)

    def test_worst_events_prefers_longest(self) -> None:
        evs = [
            _ev("exec", "A[1]", 0, 50),
            _ev("block", "A[1]", 50, 200),
            _ev("inter", "B[2]", 0, 80),
            _ev("exec", "B[2]", 10, 12),
        ]
        worst = collect_worst_events(evs, 2)
        self.assertEqual([e["duration"] for e in worst], [200, 80])
        self.assertEqual(worst[0]["kind"], "block")

    def test_anomalies_flag_long_tail(self) -> None:
        evs = [_ev("exec", "A[1]", i * 20, 10) for i in range(8)]
        evs.append(_ev("exec", "A[1]", 200, 500))
        found = detect_timeline_anomalies(evs, 8)
        self.assertTrue(any(e["duration"] == 500 for e in found))
        self.assertTrue(any("p99" in (e.get("reason") or "") or "3σ" in (e.get("reason") or "")
                            or "longest" in (e.get("reason") or "") for e in found))

    def test_best_scope_uses_evidence_times(self) -> None:
        finding = {
            "title": "A[1] WCET",
            "text": "spike at jump:1200",
            "task": "A[1]",
            "evidence": [{"label": "wcet", "time": 1200}],
        }
        evs = [_ev("exec", "A[1]", 1000, 400)]
        scope = best_finding_scope(finding, evs, 0, 10_000)
        self.assertIsNotNone(scope)
        self.assertLessEqual(scope["lo"], 1200)
        self.assertGreaterEqual(scope["hi"], 1200)
        self.assertEqual(scope["section"], "exec")

    def test_parse_signed_delta_and_regressions(self) -> None:
        self.assertEqual(parse_signed_delta("+12.3 µs")[0], 12300.0)
        self.assertEqual(parse_signed_delta("−2")[0], -2.0)
        tables = {
            "summary": [
                ["Span", "1 ms", "900 µs", "+100 µs"],
                ["Context switches", 10, 8, "+2"],
            ],
            "execution": [
                ["CS[22]", 4, 4, "10 µs", "10 µs", "80 µs", "20 µs", "+60 µs"],
            ],
        }
        strip = compare_summary_strip(tables, 4)
        self.assertTrue(any(h["label"] == "Span" for h in strip["headline"]))
        regs = top_compare_regressions(strip["regressions"] and [
            {"label": "CS[22] exec max", "delta": "+60 µs", "signed": 60000, "kind": "time"},
            {"label": "Context switches", "delta": "+2", "signed": 2, "kind": "count"},
        ], 4)
        self.assertGreaterEqual(len(regs), 1)
        self.assertEqual(regs[0]["kind"], "time")

    def test_period_flags_missed_and_extra(self) -> None:
        evs = [_ev("inter", "P[1]", i * 100, 100) for i in range(6)]
        evs.append(_ev("inter", "P[1]", 600, 400))
        evs.append(_ev("inter", "P[1]", 1000, 20))
        rows = analyze_task_periods(evs, 3)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["expected_ns"], 100)
        self.assertGreaterEqual(rows[0]["missed"], 1)
        self.assertGreaterEqual(rows[0]["extra"], 1)
        self.assertEqual(rows[0]["section"], "period")

    def test_task_core_matrix_percent_of_span(self) -> None:
        evs = [
            {**_ev("exec", "A[1]", 0, 80), "core": "Core_0"},
            {**_ev("exec", "A[1]", 80, 20), "core": "Core_1"},
        ]
        matrix = task_core_matrix(evs, ["Core_0", "Core_1"], 100)
        self.assertEqual(len(matrix["rows"]), 1)
        cells = matrix["rows"][0]["cells"]
        self.assertAlmostEqual(cells["Core_0"]["pct_span"], 80.0)
        self.assertAlmostEqual(cells["Core_1"]["pct_task"], 20.0)

    def test_waiter_owner_pairs_mutex_handoff(self) -> None:
        holds = [
            {"object": "mutex:0x1", "holder": "L[1]", "holder_mk": "L[1]",
             "start": 100, "stop": 500, "duration": 400},
            {"object": "mutex:0x1", "holder": "H[2]", "holder_mk": "H[2]",
             "start": 500, "stop": 600, "duration": 100},
        ]
        waits = pair_mutex_waits(holds, 1000)
        self.assertEqual(len(waits), 1)
        self.assertEqual(waits[0]["waiter_mk"], "H[2]")
        self.assertEqual(waits[0]["owner_mk"], "L[1]")
        self.assertEqual(waits[0]["duration"], 400)
        matrix = waiter_owner_matrix(waits)
        cell = matrix["cells"]["H[2]|L[1]"]
        self.assertEqual(cell["ns"], 400)
        self.assertEqual(cell["count"], 1)

    def test_task_health_is_heuristic_and_ranks_worst_first(self) -> None:
        evs = [_ev("exec", "Good[1]", i * 20, 10) for i in range(8)]
        evs += [_ev("exec", "Bad[2]", i * 20, 10) for i in range(7)]
        evs.append(_ev("exec", "Bad[2]", 200, 200))
        evs += [_ev("block", "Bad[2]", 50, 80)]
        evs += [_ev("inter", "Bad[2]", i * 100, 100) for i in range(4)]
        evs.append(_ev("inter", "Bad[2]", 400, 800))
        inputs = health_inputs_from_events(evs, 1000, deadline_mks=["Bad[2]"])
        rows = task_health_scores(inputs)
        self.assertGreaterEqual(len(rows), 2)
        self.assertLess(rows[0]["score"], rows[-1]["score"])
        worst = next(r for r in rows if r["mk"] == "Bad[2]")
        self.assertEqual(worst["bands"]["deadline"], "fail")
        self.assertIn("not an AI probability", worst["disclaimer"])


if __name__ == "__main__":
    unittest.main()
