"""Statistics review items A/B — new compute helpers and column additions.

Phase 1: B10 (uniform Interval / Tag summary columns) and B11 (timer-resolution
awareness helper).
Phase 2: B12 (Trace Compare distribution-shape KS column).
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


if __name__ == "__main__":
    unittest.main()
