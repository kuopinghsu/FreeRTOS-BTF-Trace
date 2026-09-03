"""Statistics review items A/B — new compute helpers and column additions.

Phase 1: B10 (uniform Interval / Tag summary columns) and B11 (timer-resolution
awareness helper).
Phase 2: B12 (Trace Compare distribution-shape KS column).
Phase 3: A1 (Switch Reason Breakdown) + A2/A9 (Scheduling Load Over Time),
built on the shared off-CPU gap classifier.
"""
from __future__ import annotations

import math
import os
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg import parser as P  # noqa: E402

_TRACE = BTF_ROOT / "demos" / "demo_8cores" / "demo_8cores.btf.gz"


class TestSampleVariability(unittest.TestCase):
    def test_nearest_rank_index_matches_panel_convention(self) -> None:
        # ceil(p*n) - 1, clamped to [0, n-1]
        self.assertEqual(P._nearest_rank_index(10, 0.50), 4)
        self.assertEqual(P._nearest_rank_index(10, 0.95), 9)
        self.assertEqual(P._nearest_rank_index(10, 0.99), 9)
        self.assertEqual(P._nearest_rank_index(1, 0.99), 0)
        self.assertEqual(P._nearest_rank_index(200, 0.99), 197)

    def test_sample_variability_values(self) -> None:
        jitter, sigma, p50, p99 = P._sample_variability([10, 20, 30, 40, 50])
        self.assertEqual(jitter, 40)                      # 50 - 10
        self.assertEqual(p50, 30)                         # ceil(.5*5)-1 = 2
        self.assertEqual(p99, 50)
        # population stddev of 10..50 step 10 is sqrt(200) ≈ 14.142
        self.assertAlmostEqual(sigma, math.sqrt(200.0), places=6)

    def test_sample_variability_empty(self) -> None:
        self.assertEqual(P._sample_variability([]), (0.0, 0.0, 0.0, 0.0))


class TestResolutionHelpers(unittest.TestCase):
    def test_resolution_limited_pct(self) -> None:
        self.assertEqual(P._resolution_limited_pct([], 5), 0.0)
        self.assertEqual(P._resolution_limited_pct([1, 2, 3, 4], 0), 0.0)
        self.assertEqual(P._resolution_limited_pct([1, 2, 10, 20], 2), 50.0)
        self.assertEqual(P._resolution_limited_pct([5, 5, 5, 5], 5), 100.0)

    def test_nominal_resolution_gcd(self) -> None:
        class _Seg:
            def __init__(self, a, b):
                self.start, self.end = a, b

        class _T:
            time_scale = "us"
            # every boundary is a multiple of 100 -> grid = 100
            seg_map_by_merge_key = {
                "a": [_Seg(100, 300), _Seg(500, 900)],
                "b": [_Seg(1000, 1400)],
            }
        self.assertEqual(P._nominal_resolution(_T()), 100)
        # a fine-grained trace -> grid 1
        _T.seg_map_by_merge_key = {"a": [_Seg(101, 302), _Seg(507, 911)]}
        self.assertEqual(P._nominal_resolution(_T()), 1)

    def test_resolution_note_threshold(self) -> None:
        class _Seg:
            def __init__(self, a, b):
                self.start, self.end = a, b

        class _T:
            time_scale = "us"
            seg_map_by_merge_key = {"a": [_Seg(100, 300), _Seg(500, 900)]}
        # grid = 100; all-50 samples sit at or below it -> note present
        self.assertIn("quantisation", P._resolution_note(_T(), [50] * 20))
        # samples well above the grid -> no note
        self.assertEqual(P._resolution_note(_T(), [100000] * 20), "")
        self.assertEqual(P._resolution_note(_T(), []), "")
        # fine grid -> never noted
        _T.seg_map_by_merge_key = {"a": [_Seg(101, 302)]}
        self.assertEqual(P._resolution_note(_T(), [1] * 20), "")


class TestIntervalTagColumns(unittest.TestCase):
    """B10 — Interval / Tag rows carry the full variability column set."""

    @classmethod
    def setUpClass(cls) -> None:
        if not _TRACE.exists():
            raise unittest.SkipTest("sample trace not present")
        cls.trace = P._parse_btf(str(_TRACE))

    def test_interval_rows_shape(self) -> None:
        rows = P._interval_stats_rows(self.trace)
        self.assertTrue(rows, "expected interval rows for the demo trace")
        for row in rows:
            # id, label, count, min, avg, max, jitter, sigma, p50, p95, p99
            self.assertEqual(len(row), 11)
            self.assertIsInstance(row[2], int)            # count
            for cell in row[3:]:
                self.assertIsInstance(cell, str)          # formatted times

    def test_tag_rows_shape(self) -> None:
        rows = P._tag_stats_rows(self.trace)
        self.assertTrue(rows, "expected tag rows for the demo trace")
        for row in rows:
            self.assertEqual(len(row), 11)
            self.assertIsInstance(row[2], int)


class TestKsStatistic(unittest.TestCase):
    """B12 — Trace Compare distribution-shape (KS) column."""

    def test_ks_identical_is_zero(self) -> None:
        a = list(range(100))
        self.assertEqual(P._ks_statistic(a, list(a)), 0.0)

    def test_ks_disjoint_is_one(self) -> None:
        self.assertEqual(P._ks_statistic([1, 2, 3], [10, 11, 12]), 1.0)

    def test_ks_shift_between_zero_and_one(self) -> None:
        a = list(range(100))
        b = [x + 50 for x in a]
        d = P._ks_statistic(a, b)
        self.assertGreater(d, 0.3)
        self.assertLess(d, 1.0)

    def test_ks_empty(self) -> None:
        self.assertEqual(P._ks_statistic([], [1, 2]), 0.0)
        self.assertEqual(P._ks_statistic([1, 2], []), 0.0)

    def test_fmt_ks(self) -> None:
        self.assertEqual(P._fmt_ks([1, 2], [1, 2, 3]), "—")     # a too small
        self.assertEqual(P._fmt_ks(None, [1, 2, 3, 4]), "—")
        self.assertEqual(P._fmt_ks(list(range(20)), list(range(20))), "0.00")
        self.assertEqual(P._fmt_ks([1, 2, 3], [9, 9, 9]), "1.00")

    def test_compare_rows_have_shape_column(self) -> None:
        if not _TRACE.exists():
            self.skipTest("sample trace not present")
        tr = P._parse_btf(str(_TRACE))
        tables = P._build_trace_compare_rows(tr, tr)   # A vs itself
        for key in ("execution", "blocking", "inter_arrival"):
            rows = tables[key]
            self.assertTrue(rows, key)
            for row in rows:
                self.assertEqual(len(row), 9, key)     # +1 for Shape Δ
                # A vs identical A -> KS 0.00 wherever both sides have >=3 samples
                self.assertIn(row[8], ("0.00", "—"))


class TestSchedulingLoadSections(unittest.TestCase):
    """Phase 3 — Switch Reason Breakdown (A1) + Scheduling Load Over Time (A2/A9)."""

    @classmethod
    def setUpClass(cls) -> None:
        from btf_viewer_pkg.config import STATS_PINNABLE_SECTIONS, STATS_SECTION_CATEGORY
        cls.CAT = STATS_SECTION_CATEGORY
        cls.SECS = STATS_PINNABLE_SECTIONS
        if not _TRACE.exists():
            raise unittest.SkipTest("sample trace not present")
        cls.trace = P._parse_btf(str(_TRACE))

    def test_sections_registered_in_sched_category(self) -> None:
        for sid in ("switch_reason", "sched_load"):
            self.assertIn(sid, self.SECS)
            self.assertEqual(self.CAT[sid], "SCHED")

    def test_classify_offcpu_gaps_kinds(self) -> None:
        by_mk = P._classify_offcpu_gaps(self.trace)
        self.assertTrue(by_mk)
        kinds = {k for gaps in by_mk.values() for _g, k in gaps}
        self.assertTrue(kinds <= set(P._OFFCPU_GAP_KINDS))
        # an SMP demo trace has at least some involuntary preemption
        self.assertIn("preempted", kinds)

    def test_classify_offcpu_gaps_idle_fill_is_period_wait(self) -> None:
        class _S:
            def __init__(s, a, b, c="C0", t="W[1]"):
                s.start, s.end, s.core, s.task = a, b, c, t

        class _T:
            time_scale = "us"
            time_min, time_max = 0, 100
            seg_map_by_merge_key = {"w": [_S(0, 10), _S(50, 60)]}
            core_segs = {"C0": [_S(0, 10), _S(10, 50, "C0", "IDLE"), _S(50, 60)]}
            task_repr = {"w": "W[1]"}
            sti_events_by_target: dict = {}
        gaps = P._classify_offcpu_gaps(_T())["w"]
        self.assertEqual(gaps, [(40, "period_wait")])

    def test_switch_reason_rows_shape(self) -> None:
        rows = P._switch_reason_rows(self.trace)
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(len(row), 9)
            # preempted + blocked + suspended + period_wait + unknown == total
            self.assertEqual(sum(row[2:7]), row[7])
        # sorted by preempted desc
        self.assertGreaterEqual(rows[0][2], rows[-1][2])

    def test_sched_load_over_time_rows(self) -> None:
        from btf_viewer_pkg.ux_explore import prepare_ux_events
        rows = P._sched_load_over_time_rows(self.trace, prepare_ux_events(self.trace))
        self.assertTrue(4 <= len(rows) <= 32)
        for r in rows:
            self.assertGreaterEqual(r["ctx"], 0)
            self.assertGreaterEqual(r["sigma_pct"], 0.0)
            self.assertTrue(r["lb_score"] is None or 0.0 <= r["lb_score"] <= 100.0)


class TestTimingLatencySections(unittest.TestCase):
    """Phase 4 — Activation Latency (A3) + Ready-Gap / Starvation (A4)."""

    @classmethod
    def setUpClass(cls) -> None:
        from btf_viewer_pkg.config import (
            STATS_PINNABLE_SECTIONS, STATS_SECTION_CATEGORY,
        )
        cls.CAT = STATS_SECTION_CATEGORY
        cls.SECS = STATS_PINNABLE_SECTIONS
        if not _TRACE.exists():
            raise unittest.SkipTest("sample trace not present")
        cls.trace = P._parse_btf(str(_TRACE))
        from btf_viewer_pkg.ux_explore import prepare_ux_events
        cls.events = prepare_ux_events(cls.trace)

    def test_sections_registered_in_timing_category(self) -> None:
        for sid in ("activation", "ready_gap"):
            self.assertIn(sid, self.SECS)
            self.assertEqual(self.CAT[sid], "TIMING")
        # catalogue order: both sit right after inter-arrival
        self.assertEqual(
            self.SECS[self.SECS.index("inter") + 1:self.SECS.index("inter") + 3],
            ("activation", "ready_gap"),
        )

    def test_activation_latency_rows_shape(self) -> None:
        rows = P._activation_latency_rows(self.trace, self.events)
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(len(row), 11)          # variability tuple
            self.assertIsInstance(row[2], int)      # activation count
            self.assertGreaterEqual(row[2], 3)
            for cell in row[3:]:
                self.assertIsInstance(cell, str)    # formatted times

    def test_activation_latency_zero_for_perfect_grid(self) -> None:
        class _E:
            pass

        # every activation exactly on a 100-unit grid -> all errors 0
        evs = [
            {"kind": "inter", "mk": "w", "task": "W[1]",
             "start": k * 100, "duration": 100}
            for k in range(1, 12)
        ]

        class _T:
            time_scale = "us"
            task_repr = {"w": "W[1]"}
        rows = P._activation_latency_rows(_T(), evs)
        self.assertEqual(len(rows), 1)
        # min == avg == max == p50 == p95 == p99 == "0.000 ns"
        self.assertTrue(all(c == rows[0][3] for c in rows[0][3:11]))

    def test_ready_gap_rows_shape_and_order(self) -> None:
        rows = P._ready_gap_rows(self.trace)
        self.assertTrue(rows)
        for row in rows:
            _mk, name, count, longest, total, avg, p95, ppct = row
            self.assertEqual(len(row), 8)
            self.assertGreaterEqual(count, 1)
            self.assertLessEqual(longest, total)
            self.assertTrue(0.0 <= ppct <= 100.0)
        # sorted by longest gap descending
        self.assertGreaterEqual(rows[0][3], rows[-1][3])

    def test_ready_gap_excludes_suspend_and_period(self) -> None:
        class _S:
            def __init__(s, a, b, c="C0", t="W[1]"):
                s.start, s.end, s.core, s.task = a, b, c, t

        class _T:
            time_scale = "us"
            time_min, time_max = 0, 200
            # gap 10..50 is IDLE-filled -> period_wait -> excluded
            seg_map_by_merge_key = {"w": [_S(0, 10), _S(50, 60)]}
            core_segs = {"C0": [_S(0, 10), _S(10, 50, "C0", "IDLE"), _S(50, 60)]}
            task_repr = {"w": "W[1]"}
            sti_events_by_target: dict = {}
        self.assertEqual(P._ready_gap_rows(_T()), [])


class TestPriorityInversionDuration(unittest.TestCase):
    """Phase 6 — A6: measured priority-inversion duration columns on the
    Priority Inheritance table."""

    def test_priority_inversion_time_measures_medium_run(self) -> None:
        from btf_viewer_pkg.parser import PriorityEpisode

        class _S:
            def __init__(s, a, b, c, t):
                s.start, s.end, s.core, s.task = a, b, c, t

        class _T:
            time_scale = "ns"
            core_segs = {"C0": [
                _S(0, 10, "C0", "Low[1]"),
                _S(10, 40, "C0", "Med[2]"),   # medium runs while Low is off-CPU
                _S(40, 60, "C0", "Low[1]"),
            ]}
            seg_map_by_merge_key = {"low": [
                _S(0, 10, "C0", "Low[1]"), _S(40, 60, "C0", "Low[1]"),
            ]}
        ep = PriorityEpisode(
            mk="low", task_label="Low[1]", base_pri=2, peak_pri=4,
            start_ns=0, stop_ns=60, inherited=False, inversion_suspect=True,
            medium_tasks=["Med[2]"], pattern="L/M/H")
        med_mk = P._task_merge_key("Med[2]")
        self.assertEqual(P._priority_inversion_time(_T(), ep, {med_mk}, {}), 30)
        # no medium candidates -> 0
        self.assertEqual(P._priority_inversion_time(_T(), ep, set(), {}), 0)

    def test_priority_stats_rows_shape(self) -> None:
        if not _TRACE.exists():
            self.skipTest("sample trace not present")
        trace = P._parse_btf(str(_TRACE))
        rows = P._priority_stats_rows(trace)
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(len(row), 12)
            # invert_total_ns (raw, [11]) <= total boost ns ([9])
            self.assertLessEqual(row[11], row[9])
            self.assertLessEqual(row[10], row[11])   # worst <= total
            # "—" when zero, otherwise a formatted string
            self.assertIsInstance(row[6], str)
            self.assertIsInstance(row[7], str)

    def test_merge_and_overlap_helpers(self) -> None:
        merged = P._merge_intervals([(0, 5), (3, 8), (10, 12), (11, 15)])
        self.assertEqual(merged, [(0, 8), (10, 15)])
        self.assertEqual(
            P._intervals_overlap_measure([(0, 10)], [(2, 4), (6, 20)]), 6)


class TestSyncObjectContentionColumns(unittest.TestCase):
    """Phase 7 — A7: p95/p99 hold + Waiters + MaxNest on Mutex / Semaphore."""

    def _fake_events(self):
        from btf_viewer_pkg.parser import StiEvent

        def _e(t, note, core="C0"):
            return StiEvent(time=t, core=core, target="mutex",
                            event="trigger", note=note)
        # A holds [10,100]; B's take at 40 lands while A still held → waiter,
        # and open_takes depth reaches 2 → max_nest 2.
        return [
            _e(0, "create 0x1"),
            _e(10, "take 0x1"),
            _e(40, "take 0x1", core="C1"),
            _e(60, "give 0x1", core="C1"),
            _e(100, "give 0x1"),
        ]

    def test_build_sync_object_data_tracks_waiters_and_nest(self) -> None:
        class _S:
            def __init__(s, a, b, t):
                s.start, s.end, s.task = a, b, t

        objs, _issues, ok = P._build_sync_object_data(
            self._fake_events(),
            core_segs={
                "C0": [_S(0, 200, "A[1]")],   # 'take 0x1' events on C0 = task A
                "C1": [_S(0, 200, "B[2]")],   # contended 'take 0x1' on C1 = task B
            },
            task_repr={},
            time_max=200,
        )
        self.assertTrue(ok)
        obj = objs["mutex:0x1"]
        self.assertEqual(obj["max_nest"], 2)
        self.assertEqual(len(obj["waiters"]), 1)

    def test_sync_object_stats_rows_shape(self) -> None:
        if not _TRACE.exists():
            self.skipTest("sample trace not present")
        trace = P._parse_btf(str(_TRACE))
        rows = P._sync_object_stats_rows(trace)
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(len(row), 18)
            self.assertIsInstance(row[12], str)          # p95 hold
            self.assertIsInstance(row[13], str)          # p99 hold
            self.assertIsInstance(row[14], int)          # waiters
            self.assertIsInstance(row[15], int)          # max_nest
            self.assertGreaterEqual(row[15], 0)
            # raw p95_ns <= p99_ns
            self.assertLessEqual(row[16], row[17])

    def test_merge_helpers_still_present(self) -> None:
        # Interval helpers added for A6 remain importable (used by A7 tests too).
        self.assertEqual(
            P._merge_intervals([(1, 3), (2, 6)]), [(1, 6)])


class TestIdleSyncLevelSections(unittest.TestCase):
    """Phase 5 — Idle Analysis (A5) + Queue Backlog / Semaphore Level (A8)."""

    @classmethod
    def setUpClass(cls) -> None:
        from btf_viewer_pkg.config import (
            STATS_PINNABLE_SECTIONS, STATS_SECTION_CATEGORY,
        )
        cls.CAT = STATS_SECTION_CATEGORY
        cls.SECS = STATS_PINNABLE_SECTIONS
        if not _TRACE.exists():
            raise unittest.SkipTest("sample trace not present")
        cls.trace = P._parse_btf(str(_TRACE))

    def test_sections_registered(self) -> None:
        self.assertEqual(self.CAT["idle"], "DETAIL")
        self.assertEqual(self.CAT["sync_level"], "SYNC")
        for sid in ("idle", "sync_level"):
            self.assertIn(sid, self.SECS)

    def test_idle_analysis_rows_shape(self) -> None:
        rows, all_span, all_start = P._idle_analysis_rows(self.trace)
        for core, total, longest, start, frags, p95 in rows:
            self.assertEqual(len((core, total, longest, start, frags, p95)), 6)
            self.assertLessEqual(longest, total)
            self.assertGreaterEqual(frags, 1)
            self.assertGreaterEqual(p95, 0)
        # most-idle core first
        if len(rows) >= 2:
            self.assertGreaterEqual(rows[0][1], rows[-1][1])
        self.assertGreaterEqual(all_span, 0)
        self.assertIsInstance(all_start, int)

    def test_idle_all_cores_window(self) -> None:
        class _S:
            def __init__(s, a, b, c, t):
                s.start, s.end, s.core, s.task = a, b, c, t

        class _T:
            time_scale = "us"
            time_min, time_max = 0, 100
            core_names = ["C0", "C1"]
            core_segs = {
                # both cores IDLE over [30, 70] -> all-idle window 40
                "C0": [_S(0, 30, "C0", "W[1]"), _S(30, 70, "C0", "IDLE"),
                       _S(70, 100, "C0", "W[1]")],
                "C1": [_S(0, 20, "C1", "W[2]"), _S(20, 80, "C1", "IDLE"),
                       _S(80, 100, "C1", "W[2]")],
            }
        rows, span, start = P._idle_analysis_rows(_T())
        self.assertEqual((span, start), (40, 30))
        self.assertEqual({r[0] for r in rows}, {"C0", "C1"})

    def test_sync_level_rows_shape(self) -> None:
        rows = P._sync_level_rows(self.trace)
        for key, kind, ptr, label, peak, tam, endl, starv in rows:
            self.assertEqual(
                len((key, kind, ptr, label, peak, tam, endl, starv)), 8)
            self.assertIn(kind, ("queue", "sem"))
            self.assertGreaterEqual(peak, 0)
            self.assertGreaterEqual(tam, 0)
            self.assertGreaterEqual(starv, 0)
        if len(rows) >= 2:
            self.assertGreaterEqual(rows[0][4], rows[-1][4])   # peak desc

    def test_sync_level_counts_and_starve(self) -> None:
        class _E:
            def __init__(s, t, note):
                s.time, s.note, s.core, s.target = t, note, "C0", "sem"

        class _T:
            time_scale = "us"
            time_max = 100
            sti_events_by_target = {"sem": [
                _E(10, "give 0x1"), _E(20, "give 0x1"),  # level 1 -> 2
                _E(30, "take 0x1"), _E(40, "take 0x1"),  # level 1 -> 0
                _E(50, "take 0x1"),                       # starved (empty)
            ]}
        rows = P._sync_level_rows(_T())
        self.assertEqual(len(rows), 1)
        _k, kind, _p, _l, peak, _tam, endl, starv = rows[0]
        self.assertEqual((kind, peak, endl, starv), ("sem", 2, 0, 1))


if __name__ == "__main__":
    unittest.main()
