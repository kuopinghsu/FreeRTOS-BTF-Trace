"""Unit tests for timeline_util pure helpers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.timeline_util import (  # noqa: E402
    _format_time,
    _format_timescale_per_px,
    _nice_grid_step,
    _orth_cull_params,
    _tag_value_sort_key,
    _time_label_sort_key,
    _to_ns,
    _zoom_debounce_ms,
)

class TimeFormatTests(unittest.TestCase):
    def test_to_ns_from_microseconds(self) -> None:
        self.assertEqual(_to_ns(2.5, "us"), 2500.0)

    def test_format_time_scales_to_milliseconds(self) -> None:
        self.assertIn("ms", _format_time(1_500_000, "ns"))

    def test_format_timescale_per_px(self) -> None:
        label = _format_timescale_per_px(2.0, "ns")
        self.assertIn("/px", label)

    def test_time_label_sort_key_parses_units(self) -> None:
        self.assertAlmostEqual(_time_label_sort_key("1.5 ms"), 1_500_000.0)
        self.assertEqual(_time_label_sort_key("-"), -1.0)

    def test_tag_value_sort_key_strips_commas(self) -> None:
        self.assertAlmostEqual(_tag_value_sort_key("12,192"), 12192.0)
        self.assertEqual(_tag_value_sort_key("—"), -1.0)

class GridAndCullTests(unittest.TestCase):
    def test_nice_grid_step_picks_readable_value(self) -> None:
        step = _nice_grid_step(2.0, target_px=100.0)
        self.assertGreaterEqual(step, 200)

    def test_nice_grid_step_extends_for_long_traces(self) -> None:
        step = _nice_grid_step(5_000_000.0, target_px=100.0)
        self.assertGreaterEqual(step, 500_000_000)

    def test_orth_cull_shrinks_for_huge_traces(self) -> None:
        small_rows, small_mult = _orth_cull_params(50)
        huge_rows, huge_mult = _orth_cull_params(900)
        self.assertGreater(small_rows, huge_rows)
        self.assertGreater(small_mult, huge_mult)

    def test_zoom_debounce_increases_with_task_count(self) -> None:
        small = _zoom_debounce_ms(50)
        large = _zoom_debounce_ms(900)
        self.assertLess(small, large)

if __name__ == "__main__":
    unittest.main()
