"""Unit tests for Perfetto (Chrome Trace JSON) export."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.parser import (  # noqa: E402
    IntervalInstance,
    MigrationEvent,
    StiEvent,
    TaskSegment,
    _task_merge_key,
)
from btf_viewer_pkg.perfetto_export import (  # noqa: E402
    build_perfetto_chrome_events,
    build_perfetto_chrome_trace,
    export_perfetto,
)


def _mini_trace():
    """Minimal BtfTrace-shaped object for export tests."""
    from types import SimpleNamespace

    mk = _task_merge_key("[0/1]Worker")
    return SimpleNamespace(
        time_scale="us",
        time_min=100,
        time_max=500,
        meta={"creator": "test"},
        core_names=["Core_0"],
        tasks=[mk],
        task_repr={mk: "[0/1]Worker"},
        segments=[
            TaskSegment(task="[0/1]Worker", start=100, end=150, core="Core_0"),
        ],
        migrations=[
            MigrationEvent(
                ns=150, merge_key=mk,
                from_core="Core_0", to_core="Core_1", gap_ns=0,
            ),
        ],
        sti_channels=["mutex", "interval_start", "interval_stop"],
        sti_events=[
            StiEvent(time=120, core="Core_0", target="mutex",
                     event="trigger", note="take"),
            StiEvent(time=110, core="Core_0", target="interval_start",
                     event="trigger", note="spanA tid:1"),
            StiEvent(time=140, core="Core_0", target="interval_stop",
                     event="trigger", note="spanA tid:1"),
        ],
        tick_sti_times=[200],
        interval_ids=["spanA"],
        interval_instances=[
            IntervalInstance(
                id="spanA", start_ns=110, stop_ns=140,
                start_core="Core_0", stop_core="Core_0", task_id="1",
            ),
        ],
    )


class PerfettoExportTests(unittest.TestCase):
    def test_process_metadata(self) -> None:
        events = build_perfetto_chrome_events(_mini_trace())
        procs = [
            e["args"]["name"] for e in events if e.get("name") == "process_name"
        ]
        self.assertEqual(procs, ["Cores", "Tasks", "STI", "Intervals"])

    def test_complete_slices_use_microseconds(self) -> None:
        events = build_perfetto_chrome_events(_mini_trace())
        runs = [e for e in events if e.get("ph") == "X" and e.get("name") == "run"]
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["ts"], 100)
        self.assertEqual(runs[0]["dur"], 50)
        self.assertEqual(runs[0]["args"]["core"], "Core_0")

    def test_skips_interval_markers_in_sti(self) -> None:
        events = build_perfetto_chrome_events(_mini_trace())
        sti_threads = [
            e["args"]["name"]
            for e in events
            if e.get("name") == "thread_name" and e.get("pid") == 3
        ]
        self.assertNotIn("interval_start", sti_threads)
        self.assertNotIn("interval_stop", sti_threads)
        self.assertIn("mutex", sti_threads)
        self.assertIn("TICK", sti_threads)

        sti_channels = {
            e.get("args", {}).get("channel")
            for e in events
            if e.get("ph") == "i" and e.get("pid") == 3 and e.get("cat") == "sti"
        }
        self.assertNotIn("interval_start", sti_channels)
        self.assertNotIn("interval_stop", sti_channels)
        self.assertIn("mutex", sti_channels)

    def test_emits_interval_slices_and_migration(self) -> None:
        events = build_perfetto_chrome_events(_mini_trace())
        intervals = [
            e for e in events
            if e.get("ph") == "X" and e.get("cat") == "interval"
        ]
        self.assertEqual(len(intervals), 1)
        self.assertEqual(intervals[0]["name"], "spanA")
        self.assertEqual(intervals[0]["ts"], 110)
        self.assertEqual(intervals[0]["dur"], 30)

        migs = [e for e in events if e.get("name") == "migrate"]
        self.assertEqual(len(migs), 1)
        self.assertEqual(migs[0]["args"]["from_core"], "Core_0")

    def test_payload_wrapper(self) -> None:
        payload = build_perfetto_chrome_trace(_mini_trace())
        self.assertEqual(payload["displayTimeUnit"], "ns")
        self.assertEqual(payload["otherData"]["timeScale"], "us")
        self.assertEqual(payload["otherData"]["btf_meta"]["creator"], "test")
        self.assertTrue(payload["traceEvents"])

    def test_export_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.json"
            export_perfetto(_mini_trace(), str(path))
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("traceEvents", data)
            self.assertGreater(len(data["traceEvents"]), 0)


if __name__ == "__main__":
    unittest.main()
