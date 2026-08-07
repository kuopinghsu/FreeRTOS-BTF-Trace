"""Tests for advanced scheduler / SMP statistics helpers."""
from __future__ import annotations

import unittest

from btf_viewer_pkg import _bootstrap

_bootstrap.install()

from btf_viewer_pkg.parser import (  # noqa: E402
    TaskSegment,
    _concurrency_level_plot_points,
    _concurrent_core_active_rows,
    _dispatch_latency_by_mk,
    _dispatch_latency_plot_points,
    _switch_overhead_plot_points,
    _switch_overhead_rows,
)
from btf_viewer_pkg.config import STATS_PINNABLE_SECTIONS  # noqa: E402


def _seg(task: str, start: int, end: int, core: str) -> TaskSegment:
    return TaskSegment(task=task, start=start, end=end, core=core)


class _FakeTrace:
    def __init__(self):
        self.time_min = 0
        self.time_max = 1000
        self.time_scale = "ns"
        self.core_names = ["Core_0", "Core_1"]
        self.core_segs = {
            "Core_0": [
                _seg("A[1]", 0, 100, "Core_0"),
                _seg("idle", 100, 110, "Core_0"),
                _seg("B[2]", 120, 200, "Core_0"),
            ],
            "Core_1": [
                _seg("B[2]", 50, 150, "Core_1"),
                _seg("A[1]", 150, 250, "Core_1"),
            ],
        }
        self.seg_map_by_merge_key = {
            "\x001\x00A": [
                _seg("A[1]", 0, 100, "Core_0"),
                _seg("A[1]", 150, 250, "Core_1"),
            ],
            "\x002\x00B": [
                _seg("B[2]", 50, 150, "Core_1"),
                _seg("B[2]", 120, 200, "Core_0"),
            ],
        }
        self.task_repr = {
            "\x001\x00A": "A[1]",
            "\x002\x00B": "B[2]",
        }
        self.task_create_times = {"\x001\x00A": 0}
        self.sti_events = []


class SchedulerSmpMetricsTest(unittest.TestCase):
    def test_catalogue_includes_new_sections(self) -> None:
        for sid in ("dispatch", "switch_overhead", "concurrency"):
            self.assertIn(sid, STATS_PINNABLE_SECTIONS)

    def test_switch_overhead_gap(self) -> None:
        rows = _switch_overhead_rows(_FakeTrace())
        by_core = {r[0]: r for r in rows}
        self.assertIn("Core_0", by_core)
        _core, n_sw, _mn, _avg, mx, total, _pct = by_core["Core_0"]
        self.assertEqual(n_sw, 2)
        self.assertEqual(mx, 10)
        self.assertEqual(total, 10)

    def test_concurrent_active_distribution(self) -> None:
        rows = _concurrent_core_active_rows(_FakeTrace())
        by_n = {r[0]: r[1] for r in rows}
        self.assertTrue(any(n >= 1 for n in by_n))
        self.assertEqual(sum(by_n.values()), 1000)

    def test_dispatch_from_create(self) -> None:
        by_mk = _dispatch_latency_by_mk(_FakeTrace())
        self.assertIn("\x001\x00A", by_mk)
        self.assertEqual(by_mk["\x001\x00A"]["samples"][0], 0)

    def test_dispatch_plot_points(self) -> None:
        pts = _dispatch_latency_plot_points(_FakeTrace(), "\x001\x00A")
        self.assertEqual(len(pts), 1)
        self.assertEqual(pts[0][0], 0)  # dispatch at create/start
        self.assertEqual(pts[0][1], 0)

    def test_switch_overhead_plot_points(self) -> None:
        pts = _switch_overhead_plot_points(_FakeTrace(), "Core_0")
        self.assertEqual(len(pts), 2)
        gaps = sorted(p[1] for p in pts)
        self.assertEqual(gaps, [0, 10])

    def test_concurrency_level_plot_points(self) -> None:
        pts = _concurrency_level_plot_points(_FakeTrace(), 2)
        self.assertTrue(pts)
        self.assertEqual(sum(p[1] for p in pts), dict(
            (n, d) for n, d, _ in _concurrent_core_active_rows(_FakeTrace())
        ).get(2, 0))


if __name__ == "__main__":
    unittest.main()
