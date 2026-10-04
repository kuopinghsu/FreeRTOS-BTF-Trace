"""Latency metrics derived from existing trace data (create vs resume, baselines, splits)."""
from __future__ import annotations

import os
import tempfile
import unittest

from btf_viewer_pkg import _bootstrap

_bootstrap.install()

from btf_viewer_pkg.parser import (  # noqa: E402
    _affinity_change_note,
    _affinity_change_to_run_samples,
    _dispatch_latency_by_mk,
    _dispatch_source_note,
    _interval_exec_note,
    _interval_exec_split,
    _interval_instance_detail_rows,
    _migration_gap_baseline_note,
    _parse_btf,
    _priority_episode_cpu_split,
    _priority_episode_detail_rows,
    _priority_holder_note,
    _same_core_gap_samples,
    _suspended_duration_note,
    _suspended_spans,
    _task_merge_key,
)


_TEXT = "\n".join([
    "#version 2.2.0",
    "#timeScale ns",
    "0,Core_0,0,T,[0/0001]A,0,resume,create pri:1",
    "100,Core_0,0,T,[0/0001]A,0,preempt,",
    "100,Core_0,0,T,[0/0002]B,0,resume,create pri:3",
    "150,Core_0,0,STI,interval_start,0,trigger,5",
    "200,Core_0,0,T,[0/0002]B,0,preempt,",
    "200,Core_0,0,T,[0/0001]A,0,resume,",
    "250,Core_0,0,STI,interval_stop,0,trigger,5",
    "300,Core_0,0,T,[0/0001]A,0,preempt,",
    "300,Core_0,0,T,[0/0002]B,0,resume,",
    "310,Core_0,0,STI,task,0,trigger,suspend [0/0001]A",
    "320,Core_0,0,STI,task,0,trigger,resume [0/0001]A",
    "330,Core_0,0,STI,task,0,trigger,resume [0/0001]A",
    "350,Core_0,0,STI,task,0,trigger,priority_inherit [0/0002]B pri:5",
    "400,Core_0,0,T,[0/0002]B,0,preempt,",
    "420,Core_0,0,STI,task,0,trigger,affinity_set [0/0001]A 0x2",
    "450,Core_0,0,STI,task,0,trigger,priority_disinherit [0/0002]B pri:3",
    "500,Core_1,0,T,[1/0001]A,0,resume,",
    "600,Core_1,0,T,[1/0001]A,0,preempt,",
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


class LatencyMetricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.trace = _parse(_TEXT)
        cls.mk_a = _task_merge_key("[0/0001]A")
        cls.mk_b = _task_merge_key("[0/0002]B")

    def test_dispatch_tags_source_and_merges_repeated_resume(self) -> None:
        by_mk = _dispatch_latency_by_mk(self.trace)
        a = by_mk[self.mk_a]
        self.assertEqual(a["samples"], [0, 180])
        self.assertEqual(a["sources"], ["create", "resume"])
        self.assertEqual(a["duplicates"], 1)
        note = _dispatch_source_note(self.trace, by_mk)
        self.assertIn("(n=2)", note)
        self.assertIn("resume→run avg", note)
        self.assertIn("1 repeated ready event(s)", note)

    def test_same_core_gap_baseline(self) -> None:
        self.assertEqual(sorted(_same_core_gap_samples(self.trace)), [100, 100])
        self.assertIn("over 2 gap(s)", _migration_gap_baseline_note(self.trace))

    def test_priority_boost_split(self) -> None:
        ep = self.trace.priority_episodes[0]
        self.assertEqual(_priority_episode_cpu_split(self.trace, ep), (50, 50, 0))
        row = _priority_episode_detail_rows(self.trace)[0]
        self.assertIn("on_cpu", row)
        self.assertIn("(50%)", _priority_holder_note(self.trace))

    def test_affinity_change_to_allowed_run(self) -> None:
        samples, no_run = _affinity_change_to_run_samples(self.trace)
        self.assertEqual(samples, [(420, 80, self.mk_a)])
        self.assertEqual(no_run, 0)
        self.assertIn("over 1 change(s)", _affinity_change_note(self.trace))

    def test_suspended_duration(self) -> None:
        spans, still = _suspended_spans(self.trace)
        self.assertEqual(spans, [(310, 320, self.mk_a)])
        self.assertEqual(still, 0)
        self.assertIn("over 1 span(s)", _suspended_duration_note(self.trace))

    def test_interval_exec_split(self) -> None:
        inst = self.trace.interval_instances_by_id["5"][0]
        self.assertEqual(_interval_exec_split(self.trace, inst), (self.mk_b, 50, 50))
        row = _interval_instance_detail_rows(self.trace)[0]
        self.assertEqual(row["exec_task"], "B[2]")
        self.assertIn("on-CPU 50%", _interval_exec_note(self.trace))


if __name__ == "__main__":
    unittest.main()
