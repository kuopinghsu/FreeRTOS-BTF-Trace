"""Trace time_min/time_max follow painted activity, not task_create storms."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.parser import (  # noqa: E402
    StiEvent,
    TaskSegment,
    _drawable_time_range,
    _parse_btf,
)


class TestDrawableTimeRange(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertIsNone(_drawable_time_range([], [], []))

    def test_segments_only(self) -> None:
        segs = [TaskSegment(task="W", start=22_000, end=30_000, core="Core_0")]
        self.assertEqual(_drawable_time_range(segs, [], []), (22_000, 30_000))

    def test_includes_sti_and_ticks(self) -> None:
        segs = [TaskSegment(task="W", start=100, end=200, core="Core_0")]
        sti = [StiEvent(time=50, core="Core_0", target="mutex", event="trigger", note="")]
        self.assertEqual(_drawable_time_range(segs, sti, [250]), (50, 250))


class TestParseTimeBounds(unittest.TestCase):
    def test_time_min_skips_task_create_storm(self) -> None:
        text = "\n".join([
            "#version 2.2.0",
            "#timeScale us",
            "0,Core_0,0,C,Core_0,0,set_frequency,1000000",
            "100,Core_0,0,T,IDLE0,0,preempt,task_create",
            "200,Core_0,0,T,Worker,0,preempt,task_create",
            "22000,Core_0,0,T,Worker,0,resume,",
            "30000,Core_0,0,T,Worker,0,preempt,",
            "",
        ])
        with tempfile.NamedTemporaryFile("w", suffix=".btf", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(text)
            path = fh.name
        try:
            trace = _parse_btf(path)
        finally:
            Path(path).unlink(missing_ok=True)

        self.assertEqual(trace.time_min, 22_000)
        self.assertEqual(trace.time_max, 30_000)
        self.assertEqual(len(trace.segments), 1)
        self.assertEqual(trace.segments[0].start, 22_000)
        self.assertEqual(trace.segments[0].end, 30_000)


if __name__ == "__main__":
    unittest.main()
