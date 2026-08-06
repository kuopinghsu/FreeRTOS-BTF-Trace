"""Deadline thresholds are nanoseconds; convert to trace-native units."""
from __future__ import annotations

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

from btf_viewer_pkg.parser import (  # noqa: E402
    BtfTrace,
    TaskSegment,
    _deadline_violations,
    _task_merge_key,
)


def _us_trace_with_slices() -> BtfTrace:
    label = "CS[16]"
    mk = _task_merge_key(label)
    segs = [
        TaskSegment(task=label, start=0, end=2, core="Core_0"),  # 2 µs
        TaskSegment(task=label, start=10, end=11, core="Core_0"),  # 1 µs
    ]
    return BtfTrace(
        time_scale="us",
        tasks=[mk],
        segments=segs,
        sti_events=[],
        sti_channels=[],
        sti_events_by_target={},
        time_min=0,
        time_max=100,
        seg_map_by_merge_key={mk: segs},
        core_names=["Core_0"],
        core_segs={"Core_0": segs},
        task_repr={mk: label},
    )


class DeadlineNsScaleTests(unittest.TestCase):
    def test_1000_ns_is_one_microsecond_on_us_trace(self) -> None:
        tr = _us_trace_with_slices()
        label = "CS[16]"
        viols = _deadline_violations(tr, 0.0, {label: 1000})
        rows = viols["slice_violations"]
        self.assertEqual(len(rows), 1)
        # limit column is index 2; mk/start/seg follow for UI clicks
        self.assertIn("µs", rows[0][2])
        self.assertNotIn("ms", rows[0][2])
        self.assertEqual(rows[0][1], "2.000 µs")  # duration
        self.assertEqual(rows[0][2], "1.000 µs")  # limit
        self.assertEqual(rows[0][4], _task_merge_key(label))
        self.assertEqual(rows[0][5], 0)
        self.assertIsNotNone(rows[0][6])
        self.assertEqual(rows[0][7], 2)  # dur_tu
        self.assertEqual(rows[0][8], 1)  # limit_tu (1000 ns → 1 µs)


if __name__ == "__main__":
    unittest.main()
