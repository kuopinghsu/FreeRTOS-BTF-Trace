"""Tick / tickless health detection from STI TICK timestamps."""
from __future__ import annotations

import sys
import unittest
from collections import defaultdict
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.parser import (  # noqa: E402
    BtfTrace,
    StiEvent,
    TaskSegment,
    _TICK_HEALTH_TICKLESS_CV,
    _tick_health_report,
    _trace_summary_snapshot,
    _build_trace_compare_rows,
    _task_merge_key,
)


def _trace_with_ticks(tick_times, *, time_max=None):
    times = list(tick_times)
    tmax = time_max if time_max is not None else (times[-1] if times else 0)
    sti = [StiEvent(t, "Core_0", "TICK", "trigger", "") for t in times]
    segs = [TaskSegment(task="Worker[1]", start=0, end=max(tmax, 1), core="Core_0")]
    return BtfTrace(
        time_scale="us",
        tasks=["Worker[1]"],
        segments=segs,
        sti_events=sti,
        sti_channels=["TICK"] if times else [],
        sti_events_by_target={"TICK": sti} if times else {},
        time_min=0,
        time_max=tmax,
        seg_map_by_merge_key={"Worker[1]": segs},
        core_names=["Core_0"],
        core_segs={"Core_0": segs},
        task_repr={"Worker[1]": "Worker[1]"},
        tick_sti_times=times,
    )


class TickHealthTests(unittest.TestCase):
    def test_tickful_regular_period_is_not_tickless(self):
        # Steady 1 ms tick → CV ≈ 0
        times = list(range(0, 10_000, 1000))
        report = _tick_health_report(_trace_with_ticks(times))
        self.assertEqual(report["tick_count"], 10)
        self.assertFalse(report["is_tickless"])
        self.assertLessEqual(report["tick_cv"], _TICK_HEALTH_TICKLESS_CV)
        self.assertEqual(report["health"], "good")
        self.assertEqual(report["missed_estimate"], 0)

    def test_tickless_idle_gaps_raise_cv(self):
        # Mix of 1× and multi-tick sleeps (tickless idle suppressing the interrupt)
        times = [0, 1000, 2000, 5000, 6000, 10_000, 11_000, 12_000]
        report = _tick_health_report(_trace_with_ticks(times))
        self.assertTrue(report["is_tickless"])
        self.assertGreater(report["tick_cv"], _TICK_HEALTH_TICKLESS_CV)
        self.assertEqual(report["health"], "warning")
        self.assertGreater(report["missed_estimate"], 0)
        self.assertGreater(report["max_gap"], 2000)

    def test_empty_ticks_unknown_not_tickless(self):
        report = _tick_health_report(_trace_with_ticks([]))
        self.assertEqual(report["tick_count"], 0)
        self.assertEqual(report["health"], "unknown")
        self.assertFalse(report["is_tickless"])

    def test_scope_busy_window_can_look_tickful(self):
        # Full trace is tickless; a busy sub-window with only 1× gaps is TICK
        times = [0, 1000, 2000, 8000, 9000, 10_000, 11_000, 12_000]
        full = _tick_health_report(_trace_with_ticks(times))
        self.assertTrue(full["is_tickless"])
        busy = _tick_health_report(_trace_with_ticks(times), lo=8000, hi=12_000)
        self.assertFalse(busy["is_tickless"])
        self.assertEqual(busy["tick_count"], 5)
        self.assertEqual(busy["missed_estimate"], 0)

    def test_summary_snapshot_tick_mode_labels(self):
        tickful = _trace_summary_snapshot(
            _trace_with_ticks(list(range(0, 5000, 1000)))
        )
        tickless = _trace_summary_snapshot(
            _trace_with_ticks([0, 1000, 4000, 5000, 9000])
        )
        self.assertEqual(tickful["tick_mode"], "TICK")
        self.assertEqual(tickless["tick_mode"], "TICKLESS")


class TicklessVsTickfulCompareTests(unittest.TestCase):
    def test_compare_reports_tick_mode_and_context_switch_delta(self):
        """Trace Compare use case: tickless vs tickful on the same workload shape."""
        # Same worker CPU, different tick STI density and an extra CS under tickful
        tickless = _trace_with_ticks(
            [0, 1000, 5000, 6000, 10_000],
            time_max=10_000,
        )
        tickful_segs = {
            "Worker[1]": [(0, 4000, "Core_0"), (5000, 9000, "Core_0")],
            "Helper[2]": [(4000, 5000, "Core_0")],
        }
        seg_map = {}
        task_repr = {}
        core_segs = defaultdict(list)
        segments = []
        for label, segs in tickful_segs.items():
            mk = _task_merge_key(label)
            task_repr[mk] = label
            built = [TaskSegment(task=label, start=s, end=e, core=c) for s, e, c in segs]
            seg_map[mk] = built
            segments.extend(built)
            for seg in built:
                core_segs[seg.core].append(seg)
        ticks = list(range(0, 10_000, 1000))
        sti = [StiEvent(t, "Core_0", "TICK", "trigger", "") for t in ticks]
        tickful = BtfTrace(
            time_scale="us",
            tasks=list(seg_map.keys()),
            segments=segments,
            sti_events=sti,
            sti_channels=["TICK"],
            sti_events_by_target={"TICK": sti},
            time_min=0,
            time_max=10_000,
            seg_map_by_merge_key=seg_map,
            core_names=["Core_0"],
            core_segs=dict(core_segs),
            task_repr=task_repr,
            tick_sti_times=ticks,
        )

        snap_a = _trace_summary_snapshot(tickless)
        snap_b = _trace_summary_snapshot(tickful)
        self.assertEqual(snap_a["tick_mode"], "TICKLESS")
        self.assertEqual(snap_b["tick_mode"], "TICK")
        self.assertLess(snap_a["tick_count"], snap_b["tick_count"])
        self.assertLess(snap_a["context_switches"], snap_b["context_switches"])

        tables = _build_trace_compare_rows(tickless, tickful)
        mode = next(r for r in tables["summary"] if r[0] == "Tick mode")
        self.assertEqual(mode[1], "TICKLESS")
        self.assertEqual(mode[2], "TICK")
        ctx = next(r for r in tables["summary"] if r[0] == "Context switches")
        self.assertLess(ctx[1], ctx[2])


if __name__ == "__main__":
    unittest.main()
