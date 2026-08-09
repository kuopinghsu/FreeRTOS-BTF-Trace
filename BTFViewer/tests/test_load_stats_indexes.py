"""Load-time migration index + full-trace stats snapshots."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.parser import (  # noqa: E402
    MigrationEvent,
    _build_corridor_inspector_model,
    _core_util_pct_rows,
    _migration_heatmap_matrix,
    _migration_rows,
    _migrations_in_range,
    _parse_btf,
    _scheduling_stats,
    _parse_task_name,
    _is_idle_task_name,
    _seg_overlap_ns,
    _task_segs_in_range,
)

EXAMPLE = Path(__file__).resolve().parents[2] / "tracedata" / "example-2cores.btf.gz"


def _linear_migs(trace, lo, hi):
    return [
        m for m in trace.migrations
        if (lo is None or m.ns >= lo) and (hi is None or m.ns <= hi)
    ]


def _task_cpu_scan(trace, lo=None, hi=None):
    total = (hi - lo) if (lo is not None and hi is not None) else (trace.time_max - trace.time_min)
    if total <= 0:
        return []
    times = {}
    for mk, segs in trace.seg_map_by_merge_key.items():
        raw = trace.task_repr.get(mk, mk)
        tname = _parse_task_name(raw)[2]
        if _is_idle_task_name(tname) or tname == "TICK":
            continue
        if lo is not None and hi is not None:
            times[mk] = sum(
                _seg_overlap_ns(s, lo, hi) for s in _task_segs_in_range(trace, mk, lo, hi)
            )
        else:
            times[mk] = sum(s.end - s.start for s in segs)
    rows = []
    for mk, t_ns in sorted(times.items(), key=lambda kv: (-kv[1], kv[0]))[:10]:
        if t_ns > 0:
            rows.append((mk, t_ns))
    return rows


class TestMigrationsInRange(unittest.TestCase):
    def test_bisect_matches_linear_filter(self) -> None:
        migs = [
            MigrationEvent(ns=10, merge_key="a", from_core="Core_0", to_core="Core_1"),
            MigrationEvent(ns=20, merge_key="a", from_core="Core_1", to_core="Core_0"),
            MigrationEvent(ns=20, merge_key="b", from_core="Core_0", to_core="Core_1"),
            MigrationEvent(ns=50, merge_key="b", from_core="Core_1", to_core="Core_0"),
            MigrationEvent(ns=90, merge_key="a", from_core="Core_0", to_core="Core_1"),
        ]

        class T:
            migrations = migs
            migration_times = [m.ns for m in migs]

        trace = T()
        for lo, hi in ((None, None), (20, 50), (15, 80), (0, 10), (90, 90), (100, 200)):
            got = list(_migrations_in_range(trace, lo, hi))
            exp = _linear_migs(trace, lo, hi)
            self.assertEqual(got, exp, msg=f"lo={lo} hi={hi}")


class TestLoadStatsSnapshots(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not EXAMPLE.is_file():
            raise unittest.SkipTest(f"missing trace fixture: {EXAMPLE}")
        cls.trace = _parse_btf(str(EXAMPLE))

    def test_parse_fills_indexes_and_snapshots(self) -> None:
        tr = self.trace
        self.assertEqual(len(tr.migration_times), len(tr.migrations))
        self.assertEqual(tr.migration_times, [m.ns for m in tr.migrations])
        self.assertTrue(tr.task_cpu_ns)
        self.assertIsNotNone(tr.sched_ctx_switches)
        self.assertIsNotNone(tr.sched_core_gaps)
        self.assertIsNotNone(tr.migration_rows_full)
        self.assertTrue(tr.core_util_pct)
        self.assertTrue(tr.migrated_mks or not tr.migrations)

    def test_unscoped_core_util_matches_scan(self) -> None:
        tr = self.trace
        cached = _core_util_pct_rows(tr)
        saved = tr.core_util_pct
        tr.core_util_pct = {}
        try:
            scanned = _core_util_pct_rows(tr)
        finally:
            tr.core_util_pct = saved
        self.assertEqual(len(cached), len(scanned))
        for (c0, p0), (c1, p1) in zip(cached, scanned):
            self.assertEqual(c0, c1)
            self.assertAlmostEqual(p0, p1, places=6)

    def test_unscoped_task_cpu_matches_scan(self) -> None:
        tr = self.trace
        cached = sorted(tr.task_cpu_ns.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
        saved = tr.task_cpu_ns
        tr.task_cpu_ns = None
        try:
            scanned = _task_cpu_scan(tr)
        finally:
            tr.task_cpu_ns = saved
        self.assertEqual(cached, scanned)

    def test_unscoped_migration_rows_and_sched_match_scan(self) -> None:
        tr = self.trace
        cached_rows = _migration_rows(tr)
        saved_rows = tr.migration_rows_full
        tr.migration_rows_full = None
        try:
            scanned_rows = _migration_rows(tr)
        finally:
            tr.migration_rows_full = saved_rows
        self.assertEqual(cached_rows, scanned_rows)

        cached_sched = _scheduling_stats(tr)
        saved_ctx, saved_gaps = tr.sched_ctx_switches, tr.sched_core_gaps
        tr.sched_ctx_switches = None
        tr.sched_core_gaps = None
        try:
            scanned_sched = _scheduling_stats(tr)
        finally:
            tr.sched_ctx_switches = saved_ctx
            tr.sched_core_gaps = saved_gaps
        self.assertEqual(cached_sched[0], scanned_sched[0])
        self.assertEqual(cached_sched[1], scanned_sched[1])

    def test_corridor_model_matrix_matches_heatmap_helper(self) -> None:
        tr = self.trace
        model = _build_corridor_inspector_model(tr, None, None, top_pct=100)
        cores, grid = _migration_heatmap_matrix(tr)
        self.assertEqual(model["matrix"]["cores"], cores)
        self.assertEqual(model["matrix"]["grid"], grid)

    def test_scoped_corridor_matches_linear_scan(self) -> None:
        tr = self.trace
        span = tr.time_max - tr.time_min
        if span <= 0 or not tr.migrations:
            self.skipTest("trace has no migration span")
        lo = tr.time_min + span // 4
        hi = tr.time_max - span // 4
        bisect_model = _build_corridor_inspector_model(tr, lo, hi, top_pct=100)
        saved = tr.migration_times
        tr.migration_times = []
        try:
            linear_model = _build_corridor_inspector_model(tr, lo, hi, top_pct=100)
        finally:
            tr.migration_times = saved
        self.assertEqual(
            [(c["from_core"], c["to_core"], c["count"]) for c in bisect_model["corridors"]],
            [(c["from_core"], c["to_core"], c["count"]) for c in linear_model["corridors"]],
        )
        self.assertEqual(bisect_model["matrix"]["grid"], linear_model["matrix"]["grid"])


if __name__ == "__main__":
    unittest.main()
