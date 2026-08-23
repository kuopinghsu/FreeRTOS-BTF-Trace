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
    analyze_response_times,
    analyze_task_periods,
    best_finding_scope,
    collect_worst_events,
    compare_summary_strip,
    compare_notable_changes,
    compare_investigate_target,
    compare_section_for_metric,
    compare_task_for_row,
    compare_core_util_chart_rows,
    compare_core_util_chart_svg,
    compare_p99_delta_chart_rows,
    compare_p99_delta_chart_svg,
    compare_summary_change_bar_rows,
    compare_summary_change_bars_svg,
    compare_migration_heatmap_rows,
    compare_migration_heatmap_svg,
    compare_row_delta_status,
    filter_compare_migration_rows,
    format_burst_reason,
    format_burst_window_ns,
    COMPARE_DELTA_FORMULA,
    core_util_over_time,
    critical_path_rows,
    detect_timeline_anomalies,
    distribution_explorer,
    find_event_at_percentile,
    harvest_ux_events,
    health_inputs_from_events,
    mutex_blocking_table,
    pair_mutex_waits,
    parse_signed_delta,
    percentile_index,
    preemption_pairs,
    preemption_story,
    preemptor_ranking,
    recurring_patterns,
    sparkline,
    recurring_patterns_across,
    task_core_matrix,
    task_health_scores,
    top_blocking_contributors,
    top_compare_regressions,
    unified_jitter,
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
    def test_burst_reason_uses_human_window(self) -> None:
        self.assertEqual(format_burst_window_ns(1_000_000), "1 ms")
        self.assertEqual(
            format_burst_reason(9693, "wakeup", 1_000_000),
            "9,693 wakeups within 1 ms",
        )

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

    def test_finding_overlay_and_inspector(self) -> None:
        from btf_viewer_pkg.ux_explore import finding_overlay_times, task_inspector_line
        times = finding_overlay_times([{
            "title": "A[1]",
            "text": "at jump:42",
            "evidence": [{"time": 10}, {"start": 20}],
        }])
        self.assertIn(10.0, times)
        self.assertIn(42.0, times)
        self.assertIn("Task T1", task_inspector_line("T1", ["gap"]))
        self.assertIn("No task selected", task_inspector_line("", []))
        self.assertEqual(
            task_inspector_line("\x0028\x00CS", []),
            "Task CS[28]",
        )
        self.assertNotIn("\x00", task_inspector_line("\x00267\x00Med", ["warn"]))
        self.assertIn("Med[267]", task_inspector_line("\x00267\x00Med", ["warn"]))

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
        self.assertTrue(strip.get("improvements"))
        regs = top_compare_regressions([
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

    def test_response_time_is_heuristic_adjacent_slices(self) -> None:
        evs = [
            _ev("exec", "T[1]", 0, 10),
            _ev("exec", "T[1]", 40, 10),
        ]
        model = analyze_response_times(evs)
        self.assertEqual(len(model["rows"]), 1)
        self.assertEqual(model["rows"][0]["n"], 2)
        self.assertEqual(model["events"][1]["duration"], 40)
        self.assertIn("not an explicit BTF", model["rows"][0]["disclaimer"])
        self.assertEqual(model["rows"][0]["p99_ev"]["duration"], 40)
        self.assertEqual(model["rows"][0]["min_ev"]["duration"], 10)

    def test_critical_path_splits_exec_and_preempt(self) -> None:
        evs = [
            {**_ev("exec", "V[1]", 0, 10), "core": "Core_0"},
            {**_ev("exec", "P[2]", 10, 20), "core": "Core_0"},
            {**_ev("exec", "V[1]", 30, 10), "core": "Core_0"},
        ]
        rows = critical_path_rows(evs, 4)
        self.assertTrue(rows)
        self.assertEqual(rows[0]["section"], "crit_path")
        self.assertGreater(rows[0]["preempt_ns"], 0)
        self.assertIn("preempt_ev", rows[0])
        self.assertIn("other_ns", rows[0])

    def test_preemption_pairs_scales_on_same_core(self) -> None:
        evs = []
        for i in range(400):
            evs.append({**_ev("exec", "P[2]", i * 20 + 10, 10), "core": "Core_0"})
            evs.append({**_ev("block", "V[1]", i * 20 + 10, 10), "core": "Core_0"})
        pairs = preemption_pairs(evs)
        self.assertEqual(len(pairs), 400)
        self.assertEqual(pairs[0]["preemptor_mk"], "P[2]")

    def test_harvest_uses_prepared_cache(self) -> None:
        class _Trace:
            ux_events_full = [_ev("exec", "A[1]", 0, 10), _ev("block", "A[1]", 10, 5)]
            seg_map_by_merge_key = None
        evs = harvest_ux_events(_Trace(), None, None)
        self.assertEqual(len(evs), 2)
        scoped = harvest_ux_events(_Trace(), 0, 10)
        self.assertEqual([e["kind"] for e in scoped], ["exec"])

    def test_preemptor_ranking_and_mutex_table(self) -> None:
        evs = [
            {**_ev("block", "V[1]", 10, 20), "core": "Core_0"},
            {**_ev("exec", "P[2]", 10, 20), "core": "Core_0"},
        ]
        ranks = preemptor_ranking(preemption_pairs(evs), 8)
        self.assertEqual(ranks[0]["mk"], "V[1]")
        self.assertIn("P[2]", ranks[0]["top_label"])
        self.assertIn("P[2]", ranks[0]["story"])
        self.assertIn("resumed", preemption_story(preemption_pairs(evs), "V[1]"))
        waits = pair_mutex_waits([
            {"object": "mutex:0x1", "holder": "L[1]", "holder_mk": "L[1]",
             "start": 100, "stop": 500, "duration": 400},
            {"object": "mutex:0x1", "holder": "H[2]", "holder_mk": "H[2]",
             "start": 500, "stop": 600, "duration": 100},
        ], 1000)
        table = mutex_blocking_table(waits)
        self.assertEqual(table[0]["mk"], "H[2]")
        self.assertEqual(table[0]["total_ns"], 400)

    def test_core_time_jitter_patterns_and_compare_why(self) -> None:
        evs = [
            {**_ev("exec", "A[1]", 0, 90), "core": "Core_0"},
            {**_ev("exec", "A[1]", 100, 10), "core": "Core_0"},
        ]
        grid = core_util_over_time(evs, ["Core_0"], 0, 160, 4)
        self.assertEqual(len(grid["bins"]), 4)
        self.assertGreater(grid["bins"][0]["peak_pct"], 0)
        jitter = unified_jitter(evs)
        self.assertTrue(jitter)
        self.assertEqual(jitter[0]["section"], "jitter")
        anoms = detect_timeline_anomalies(
            evs + [_ev("exec", "A[1]", 200, 500)], 8)
        pats = recurring_patterns(anoms + anoms, 2)
        self.assertTrue(any(p["count"] >= 2 for p in pats))
        strip = compare_summary_strip({
            "summary": [["Span", "1 ms", "900 µs", "+100 µs"]],
            "execution": [
                ["CS[22]", 4, 4, "10 µs", "10 µs", "80 µs", "20 µs", "+60 µs"],
            ],
        }, 4)
        self.assertIn("why", strip)
        self.assertTrue(strip["why"])

    def test_worst_events_include_heuristic_response(self) -> None:
        evs = [
            _ev("exec", "A[1]", 0, 10),
            _ev("exec", "A[1]", 100, 10),
            _ev("block", "B[2]", 0, 20),
        ]
        worst = collect_worst_events(evs, 4)
        self.assertTrue(any(e.get("kind") == "response" for e in worst))
        self.assertGreaterEqual(max(e["duration"] for e in worst if e["kind"] == "response"), 100)

    def test_period_counts_burst_gaps(self) -> None:
        evs = [_ev("inter", "P[1]", i * 100, 100) for i in range(6)]
        evs.append(_ev("inter", "P[1]", 600, 20))
        rows = analyze_task_periods(evs, 3)
        self.assertEqual(rows[0]["burst"], 1)
        self.assertTrue(rows[0].get("spark"))

    def test_unified_jitter_dispatch_and_wakeup(self) -> None:
        evs = [
            _ev("exec", "A[1]", 0, 10),
            _ev("exec", "A[1]", 20, 10),
            _ev("exec", "A[1]", 100, 10),
        ]
        jitter = unified_jitter(evs, {"A[1]": [5, 50]})
        self.assertGreater(jitter[0]["dispatch_jitter_ns"], 0)
        self.assertGreater(jitter[0]["wakeup_jitter_ns"], 0)
        model = distribution_explorer(evs, "exec", "A[1]")
        self.assertEqual(model["n"], 3)
        self.assertTrue(sparkline([10, 20, 30, 5]))

    def test_top_blockers_and_shared_patterns(self) -> None:
        evs = [
            {**_ev("block", "V[1]", 10, 40), "core": "Core_0"},
            {**_ev("exec", "P[2]", 10, 40), "core": "Core_0"},
        ]
        waits = [{
            "waiter": "V[1]", "waiter_mk": "V[1]", "owner": "O[3]",
            "owner_mk": "O[3]", "object": "mutex:1",
            "start": 10, "stop": 50, "duration": 40,
        }]
        rows = top_blocking_contributors(evs, waits, 8)
        self.assertEqual(rows[0]["mk"], "V[1]")
        self.assertGreater(rows[0]["mutex_ns"], 0)
        shared = recurring_patterns_across(
            [{"kind": "exec", "task": "A[1]", "mk": "A[1]", "duration": 10, "start": 0}],
            [{"kind": "exec", "task": "A[1]", "mk": "A[1]", "duration": 20, "start": 5}],
        )
        self.assertEqual(shared[0]["count_a"], 1)
        self.assertEqual(shared[0]["count_b"], 1)

    def test_compare_why_mentions_response_p99(self) -> None:
        strip = compare_summary_strip({
            "summary": [[
                "Response P99 (worst task)", "200 µs", "100 µs", "+100 µs",
            ]],
            "response": [{"name": "A[1]", "delta": "+80 µs"}],
        }, 4)
        self.assertIn("response", strip["why"].lower())

    def test_notable_changes_polarity_threshold_and_tick_warning(self) -> None:
        notable = compare_notable_changes({
            "summary": [
                ["Migrations (total)", 18440, 19018, "-578"],
                ["Tick mode", "TICKLESS", "TICKLESS", "—"],
                ["Response P99 (worst task)",
                 "13.698 ms (QP[198])", "29.062 ms (QP[197])", "-15.364 ms"],
            ],
            "response": [
                ["QP[198]", "13.698 ms", "29.062 ms", "-15.364 ms"],
                ["QP[197]", "25.780 ms", "14.687 ms", "+11.093 ms"],
            ],
        }, 8, "tickful-8cores.btf", "tickless-8cores.btf")
        statuses = {r["status"] for r in notable["rows"]}
        self.assertIn("Regressed", statuses)
        self.assertIn("Improved", statuses)
        self.assertTrue(any("tickful" in w.lower() for w in notable["warnings"]))
        self.assertTrue(any("different tasks" in w.lower() for w in notable["warnings"]))
        self.assertEqual(notable["formula"], COMPARE_DELTA_FORMULA)
        self.assertGreater(notable["cards"]["regressions"], 0)
        self.assertGreater(notable["cards"]["improvements"], 0)
        self.assertIn("Candidate B", notable["verdict"])
        self.assertTrue(all(r.get("significance") == "engineering" for r in notable["rows"]))
        self.assertIn("next_investigation", notable)
        self.assertTrue(str(notable.get("next_investigation") or "").startswith("Next:"))
        self.assertIn("small_omitted_count", notable)
        self.assertIn("investigate", notable)
        inv = notable["investigate"]
        self.assertEqual(inv.get("section_id") or inv.get("section"), "response")
        self.assertTrue(any(r.get("section") for r in notable["rows"]))
        self.assertEqual(compare_section_for_metric("T1 exec max", "exec max"), "exec")
        self.assertEqual(
            compare_task_for_row("QP[198] response p99", "response p99"), "QP[198]")
        empty = compare_investigate_target({"rows": []})
        self.assertEqual(empty["section_id"], "response")

    def test_compare_charts_and_migration_views(self) -> None:
        util = compare_core_util_chart_rows({
            "core_util": [
                ["Core_0", "40.0", "55.0", "-15.0"],
                ["Core_1", "10.0", "8.0", "+2.0"],
            ],
        })
        self.assertEqual(util[0]["label"], "Core_0")
        svg = compare_core_util_chart_svg(util)
        self.assertIn("Core_0", svg)
        self.assertIn("#2a6fb2", svg)
        self.assertIn("#6b4ea8", svg)
        p99 = compare_p99_delta_chart_rows({
            "response": [
                ["QP[198]", "13 ms", "29 ms", "-16 ms"],
                ["QP[197]", "25 ms", "14 ms", "+11 ms"],
            ],
        })
        self.assertEqual(p99[0]["label"], "QP[198]")
        self.assertEqual(p99[0]["status"], "Regressed")
        self.assertEqual(p99[1]["status"], "Improved")
        p99_svg = compare_p99_delta_chart_svg(p99)
        self.assertIn("#c0392b", p99_svg)
        self.assertIn("#1f6b45", p99_svg)
        mig = [
            [f"QP[{i}]", 10 + i, 20 + i, -(10 + i), "1/s", "2/s", "-1/s",
             "1 ms", "2 ms", "-1 ms", 0, 1, 2, 2, "0 90%", "1 80%"]
            for i in range(8)
        ]
        mig.append(["CS[1]", 4, 4, 0, "1/s", "1/s", "0",
                    "1 ms", "1 ms", "0", 0, 0, 1, 1, "0 100%", "0 100%"])
        mig.append(["CS[2]", 9, 1, 8, "2/s", "0.2/s", "+1.8/s",
                    "2 ms", "1 ms", "+1 ms", 2, 0, 3, 1, "1 70%", "0 90%"])
        top = filter_compare_migration_rows(mig, "count", "top", "", 10)
        self.assertEqual(top["shown"], 9)
        self.assertEqual(len(top["headers"]), 7)
        self.assertTrue(all(r[3] != 0 for r in top["rows"]))
        dwell = filter_compare_migration_rows(mig, "dwell", "all", "CS", 10)
        self.assertEqual(dwell["view"], "dwell")
        self.assertEqual(len(dwell["headers"]), 6)
        self.assertEqual(dwell["shown"], 2)
        regs = filter_compare_migration_rows(mig, "count", "regressed")
        self.assertTrue(all(r[3] < 0 for r in regs["rows"]))
        rel = filter_compare_migration_rows(mig, "count", "all", "", 10, sort_by="rel")
        self.assertEqual(rel["sort_by"], "rel")
        self.assertEqual(rel["rows"][0][0], "CS[2]")
        heat = compare_migration_heatmap_rows(mig, 5)
        self.assertEqual(len(heat), 5)
        self.assertIn("Migration Δ heatmap", compare_migration_heatmap_svg(heat))
        bars = compare_summary_change_bar_rows({
            "summary": [
                ["Migrations (total)", 100, 200, "−100"],
                ["Context switches", 10, 5, "+5"],
                ["Tasks", 3, 3, "0"],
            ],
        })
        self.assertTrue(any(r["label"] == "Migrations (total)" for r in bars))
        self.assertIn("Summary changes", compare_summary_change_bars_svg(bars))
        self.assertEqual(
            compare_row_delta_status("Migrations (total)", "−100"), "Regressed")
        self.assertEqual(
            compare_row_delta_status("Load Balance Score", "−0.5 pp"), "Improved")
        self.assertIn("pp = percentage points", COMPARE_DELTA_FORMULA)
        self.assertGreater(regs["shown"], 0)

    def test_anomaly_flags_deadline_and_mutex(self) -> None:
        evs = [_ev("exec", "A[1]", i * 20, 10) for i in range(4)]
        evs.append(_ev("exec", "A[1]", 200, 80))
        found = detect_timeline_anomalies(
            evs, 8, mutex_waits=[{
                "waiter": "A[1]", "waiter_mk": "A[1]", "object": "m1",
                "start": 0, "stop": 50, "duration": 50,
            }],
            deadlines={"A[1]": 30},
        )
        self.assertTrue(any(e.get("kind") == "deadline" for e in found))
        self.assertTrue(any(e.get("kind") == "mutex_block" for e in found))


if __name__ == "__main__":
    unittest.main()
