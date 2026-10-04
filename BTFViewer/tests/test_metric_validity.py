"""Metric-validity rules: truncated slices, cross-task gives, unmatched stops, windows."""
from __future__ import annotations

import os
import tempfile
import unittest

from btf_viewer_pkg import _bootstrap

_bootstrap.install()

from btf_viewer_pkg.parser import (  # noqa: E402
    _exec_slice_samples,
    _find_wcet_segment,
    _interval_boundary_count,
    _interval_stats_rows,
    _migration_gap_plot_points,
    _parse_btf,
    _sync_exclusion_note,
    _sync_object_stats_rows,
)
from btf_viewer_pkg.trace_health import _check_unmatched_intervals  # noqa: E402


_TEXT = "\n".join([
    "#version 2.2.0",
    "#timeScale ns",
    "100,Core_0,0,T,[0/0001]A,0,resume,",
    "200,Core_0,0,T,[0/0001]A,0,preempt,",
    "200,Core_0,0,T,[0/0002]B,0,resume,",
    "300,Core_0,0,T,[0/0002]B,0,preempt,",
    "300,Core_0,0,T,[0/0001]A,0,resume,",
    "310,Core_0,0,STI,mutex,0,trigger,take 0x10",
    "320,Core_0,0,STI,interval_start,0,trigger,7",
    "320,Core_0,0,STI,interval_stop,0,trigger,7",
    "330,Core_0,0,STI,interval_stop,0,trigger,9",
    "340,Core_0,0,STI,interval_start,0,trigger,8",
    "360,Core_0,0,STI,interval_stop,0,trigger,8",
    "400,Core_0,0,T,[0/0001]A,0,preempt,",
    "400,Core_0,0,T,[0/0002]B,0,resume,",
    "420,Core_0,0,STI,mutex,0,trigger,give 0x10",
    "900,Core_0,0,STI,marker,0,trigger,end",
    "",
])


def _parse(text: str):
    fd, path = tempfile.mkstemp(suffix=".btf")
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    try:
        return _parse_btf(path)
    finally:
        os.unlink(path)


class MetricValidityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.trace = _parse(_TEXT)

    def _segs(self, name: str):
        for mk, raw in self.trace.task_repr.items():
            if raw.endswith(name):
                return self.trace.seg_map_by_merge_key[mk]
        raise AssertionError(name)

    def test_open_at_end_slice_is_excluded_from_samples(self) -> None:
        tr = self.trace
        self.assertIn("[0/0002]B", tr.open_at_end_tasks)
        segs_b = self._segs("B")
        self.assertEqual(segs_b[-1].end, tr.time_max)
        self.assertEqual(_exec_slice_samples(segs_b), [100, tr.time_max - 400])
        self.assertEqual(_exec_slice_samples(segs_b, trace=tr), [100])
        wcet = _find_wcet_segment(segs_b, trace=tr)
        self.assertEqual((wcet.start, wcet.end), (200, 300))

    def test_unmatched_stop_counted_and_zero_span_kept(self) -> None:
        tr = self.trace
        self.assertEqual(tr.interval_unmatched_stops, 1)
        durations = sorted(i.stop_ns - i.start_ns for i in tr.interval_instances)
        self.assertEqual(durations, [0, 20])
        check = _check_unmatched_intervals(tr)
        self.assertIn("interval_stop event(s) had no open interval_start", check["summary"])

    def test_interval_stats_need_both_endpoints(self) -> None:
        tr = self.trace
        ids = {r[0] for r in _interval_stats_rows(tr, 330, 350)}
        self.assertNotIn("8", ids)
        self.assertEqual(_interval_boundary_count(tr, 330, 350), 1)
        ids_full = {r[0] for r in _interval_stats_rows(tr)}
        self.assertEqual(ids_full, {"7", "8"})

    def test_sync_cross_task_give_excluded(self) -> None:
        tr = self.trace
        rows = _sync_object_stats_rows(tr)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row[4], 0)
        self.assertEqual(row[18], 1)
        self.assertIn("1 cross-task mutex give", _sync_exclusion_note(rows))

    def test_zero_migration_gap_plotted(self) -> None:
        text = "\n".join([
            "#version 2.2.0",
            "#timeScale ns",
            "100,Core_0,0,T,[0/0001]A,0,resume,",
            "200,Core_0,0,T,[0/0001]A,0,preempt,",
            "200,Core_1,0,T,[1/0001]A,0,resume,",
            "300,Core_1,0,T,[1/0001]A,0,preempt,",
            "",
        ])
        tr = _parse(text)
        mk = next(iter(tr.migrations_by_mk))
        pts = _migration_gap_plot_points(tr, mk)
        self.assertEqual([p[1] for p in pts], [0])

    def test_inheritance_alone_is_not_inversion(self) -> None:
        text = "\n".join([
            "#version 2.2.0",
            "#timeScale ns",
            "0,Core_0,0,T,[0/0001]L,0,resume,create pri:1",
            "0,Core_0,0,T,[0/0001]L,0,preempt,",
            "1,Core_0,0,T,[0/0002]H,0,resume,create pri:5",
            "2,Core_0,0,T,[0/0002]H,0,preempt,",
            "10,Core_0,0,T,[0/0001]L,0,resume,",
            "20,Core_0,0,STI,task,0,trigger,priority_inherit [0/0001]L pri:5",
            "40,Core_0,0,STI,task,0,trigger,priority_disinherit [0/0001]L pri:1",
            "50,Core_0,0,T,[0/0001]L,0,preempt,",
            "",
        ])
        tr = _parse(text)
        self.assertEqual(len(tr.priority_episodes), 1)
        ep = tr.priority_episodes[0]
        self.assertTrue(ep.inherited)
        self.assertFalse(ep.inversion_suspect)


if __name__ == "__main__":
    unittest.main()
