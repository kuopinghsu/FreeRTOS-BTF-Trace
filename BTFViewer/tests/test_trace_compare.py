"""Trace Compare tables: summary extras, multi-section dict, empty sync."""
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
    _build_compare_csv,
    _build_compare_html,
    _build_trace_compare_rows,
    _task_merge_key,
    _trace_summary_snapshot,
)


def _mini_trace(
    segs_by_label,
    *,
    cores=("Core_0", "Core_1"),
    ticks=(),
    time_max=10_000,
    sync_objects=None,
    lock_bounce_migration_ns=None,
):
    seg_map = {}
    task_repr = {}
    core_segs = defaultdict(list)
    segments = []
    for label, segs in segs_by_label.items():
        mk = _task_merge_key(label)
        task_repr[mk] = label
        built = [TaskSegment(task=label, start=s, end=e, core=c) for s, e, c in segs]
        seg_map[mk] = built
        segments.extend(built)
        for seg in built:
            core_segs[seg.core].append(seg)
    tick_sti = list(ticks)
    sti = [StiEvent(t, "Core_0", "TICK", "trigger", "") for t in tick_sti]
    return BtfTrace(
        time_scale="ns",
        tasks=list(seg_map.keys()),
        segments=segments,
        sti_events=sti,
        sti_channels=["TICK"] if tick_sti else [],
        sti_events_by_target={"TICK": sti} if tick_sti else {},
        time_min=0,
        time_max=time_max,
        seg_map_by_merge_key=seg_map,
        core_names=list(cores),
        core_segs=dict(core_segs),
        task_repr=task_repr,
        tick_sti_times=tick_sti,
        sync_objects=sync_objects or {},
        has_sync_object_instrumentation=bool(sync_objects),
        lock_bounce_migration_ns=frozenset(lock_bounce_migration_ns or ()),
    )


class TraceCompareTests(unittest.TestCase):
    def test_summary_includes_load_balance_and_tick(self):
        tr = _mini_trace(
            {
                "Worker[1]": [
                    (0, 4000, "Core_0"),
                    (0, 1000, "Core_1"),
                ],
                "IDLE[0]": [(4000, 10000, "Core_0")],
            },
            ticks=(0, 1000, 2000, 3000, 4000),
            time_max=10_000,
        )
        snap = _trace_summary_snapshot(tr)
        self.assertIsNotNone(snap["load_balance_score"])
        self.assertIsNotNone(snap["load_balance_sigma"])
        self.assertEqual(snap["tick_mode"], "TICK")
        self.assertEqual(snap["tick_count"], 5)
        self.assertIn(snap["tick_health"], ("good", "warning", "critical", "unknown"))

        tables = _build_trace_compare_rows(tr, tr)
        labels = [r[0] for r in tables["summary"]]
        self.assertIn("Load Balance Score", labels)
        self.assertIn("Load Balance σ", labels)
        self.assertIn("Tick health", labels)
        self.assertIn("Tick mode", labels)
        self.assertIn("Tick count", labels)
        self.assertIn("Missed ticks (est.)", labels)
        lb_row = next(r for r in tables["summary"] if r[0] == "Load Balance Score")
        self.assertTrue(str(lb_row[1]).endswith("%"))

    def test_multi_section_dict_keys(self):
        tr_a = _mini_trace({
            "A[1]": [(0, 100, "Core_0"), (200, 350, "Core_0"), (400, 500, "Core_1")],
        })
        tr_b = _mini_trace({
            "A[1]": [(0, 80, "Core_0"), (150, 250, "Core_0")],
            "B[2]": [(0, 200, "Core_1")],
        })
        tables = _build_trace_compare_rows(tr_a, tr_b)
        expected = {
            "summary", "top", "core_util", "migrations", "execution",
            "blocking", "inter_arrival", "preemption", "sync",
        }
        self.assertEqual(set(tables.keys()), expected)
        self.assertTrue(tables["core_util"])
        self.assertTrue(tables["execution"])
        self.assertTrue(any(r[0] == "A[1]" for r in tables["blocking"]))
        self.assertTrue(any(r[0] == "A[1]" for r in tables["inter_arrival"]))

        csv = _build_compare_csv("A", "B", False, tables)
        html = _build_compare_html("A", "B", False, tables)
        self.assertIn("BTFViewer", html)
        self.assertIn('class="report-head"', html)
        self.assertIn('class="brand-icon"', html)
        self.assertIn('fill="#1C3A6E"', html)
        for section in (
            "Core Utilisation", "Execution Time", "Blocking Time",
            "Inter-Arrival", "Sync Objects",
        ):
            self.assertIn(section, csv)
            self.assertIn(section, html)
        self.assertIn("Cores A", csv)
        self.assertIn("Primary A", csv)
        self.assertIn("Max A", csv)

    def test_empty_sync_still_works(self):
        tr = _mini_trace({"T[1]": [(0, 50, "Core_0")]}, cores=("Core_0",))
        tables = _build_trace_compare_rows(tr, tr)
        sync = tables["sync"]
        self.assertTrue(sync)
        labels = [r[0] for r in sync]
        self.assertIn("Sync objects", labels)
        self.assertIn("Lock-bounce migrations", labels)
        self.assertIn("Core Affinity Violations (bounce)", labels)
        self.assertEqual(sync[0][1], 0)
        self.assertEqual(sync[0][2], 0)
        # No load balance with a single core
        snap = _trace_summary_snapshot(tr)
        self.assertIsNone(snap["load_balance_score"])
        lb = next(r for r in tables["summary"] if r[0] == "Load Balance Score")
        self.assertEqual(lb[1], "—")
        self.assertEqual(lb[2], "—")


if __name__ == "__main__":
    unittest.main()
