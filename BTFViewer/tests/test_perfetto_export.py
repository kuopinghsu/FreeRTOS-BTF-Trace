"""Unit tests for Perfetto (Chrome Trace JSON) export."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.parser import (  # noqa: E402
    IntervalInstance,
    MigrationEvent,
    StiEvent,
    TagSample,
    TaskSegment,
    _task_merge_key,
)
from btf_viewer_pkg.perfetto_export import (  # noqa: E402
    build_perfetto_chrome_events,
    build_perfetto_chrome_trace,
    export_perfetto,
)


def _mini_trace(**overrides):
    """Minimal BtfTrace-shaped object for export tests."""
    mk = _task_merge_key("[0/1]Worker")
    base = dict(
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
        sti_channels=["mutex", "interval_start", "interval_stop", "tag0_event"],
        sti_events=[
            StiEvent(time=120, core="Core_0", target="mutex",
                     event="trigger", note="take 0xabc"),
            StiEvent(time=110, core="Core_0", target="interval_start",
                     event="trigger", note="spanA tid:1"),
            StiEvent(time=140, core="Core_0", target="interval_stop",
                     event="trigger", note="spanA tid:1"),
            StiEvent(time=125, core="Core_0", target="tag0_event",
                     event="trigger", note="42"),
        ],
        tick_sti_times=[200],
        interval_ids=["spanA"],
        interval_instances=[
            IntervalInstance(
                id="spanA", start_ns=110, stop_ns=140,
                start_core="Core_0", stop_core="Core_0", task_id="1",
            ),
        ],
        tag_channels=["tag0_event"],
        tag_samples_by_channel={
            "tag0_event": [
                TagSample(channel="tag0_event", time_ns=125, value=42.0, core="Core_0"),
            ],
        },
        sync_objects={},
        has_sync_object_instrumentation=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _sync_trace():
    """Trace with one mutex hold and matching STI take/give."""
    return _mini_trace(
        has_sync_object_instrumentation=True,
        sync_objects={
            "mutex:0xabc": {
                "key": "mutex:0xabc",
                "kind": "mutex",
                "ptr": "0xabc",
                "create_ns": 105,
                "delete_ns": None,
                "holds": [{
                    "start_ns": 120,
                    "stop_ns": 145,
                    "duration_ns": 25,
                    "holder_label": "Worker",
                    "take_core": "Core_0",
                    "give_core": "Core_0",
                    "signal": False,
                }],
            },
        },
    )


class PerfettoExportTests(unittest.TestCase):
    def test_process_metadata(self) -> None:
        events = build_perfetto_chrome_events(_mini_trace())
        procs = [
            e["args"]["name"] for e in events if e.get("name") == "process_name"
        ]
        self.assertEqual(procs, ["Cores", "Tasks", "STI", "Intervals", "Tags"])

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
        self.assertNotIn("tag0_event", sti_threads)

        sti_channels = {
            e.get("args", {}).get("channel")
            for e in events
            if e.get("ph") == "i" and e.get("pid") == 3 and e.get("cat") == "sti"
        }
        self.assertNotIn("interval_start", sti_channels)
        self.assertNotIn("interval_stop", sti_channels)
        self.assertIn("mutex", sti_channels)

    def test_tag_counters_not_sti(self) -> None:
        events = build_perfetto_chrome_events(_mini_trace())
        counters = [e for e in events if e.get("ph") == "C"]
        self.assertEqual(len(counters), 1)
        self.assertEqual(counters[0]["pid"], 5)
        self.assertEqual(counters[0]["args"]["value"], 42.0)
        self.assertEqual(counters[0]["name"], "Tag 0")
        sti_tag = [
            e for e in events
            if e.get("pid") == 3 and e.get("args", {}).get("channel") == "tag0_event"
        ]
        self.assertEqual(sti_tag, [])

    def test_sync_holds_and_filters_mutex_sti(self) -> None:
        events = build_perfetto_chrome_events(_sync_trace())
        procs = [
            e["args"]["name"] for e in events if e.get("name") == "process_name"
        ]
        self.assertIn("Sync", procs)
        holds = [
            e for e in events
            if e.get("ph") == "X" and e.get("cat") == "sync"
        ]
        self.assertEqual(len(holds), 1)
        self.assertEqual(holds[0]["pid"], 6)
        self.assertEqual(holds[0]["name"], "Worker")
        self.assertEqual(holds[0]["ts"], 120)
        self.assertEqual(holds[0]["dur"], 25)
        creates = [e for e in events if e.get("name") == "create" and e.get("cat") == "sync"]
        self.assertEqual(len(creates), 1)
        sti_mutex = [
            e for e in events
            if e.get("pid") == 3 and e.get("args", {}).get("channel") == "mutex"
        ]
        self.assertEqual(sti_mutex, [])

    def test_time_range_clips_segment_and_drops_sti(self) -> None:
        events = build_perfetto_chrome_events(_mini_trace(), lo=120, hi=140)
        runs = [e for e in events if e.get("ph") == "X" and e.get("name") == "run"]
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["ts"], 120)
        self.assertEqual(runs[0]["dur"], 20)
        sti = [
            e for e in events
            if e.get("ph") == "i" and e.get("pid") == 3 and e.get("cat") == "sti"
        ]
        # mutex take at 120 is in range; tick at 200 is out
        self.assertTrue(any(e.get("args", {}).get("channel") == "mutex" for e in sti))
        self.assertFalse(any(e.get("name") == "TICK" for e in sti))
        counters = [e for e in events if e.get("ph") == "C"]
        self.assertEqual(len(counters), 1)
        self.assertEqual(counters[0]["ts"], 125)

    def test_range_half_specified_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_perfetto_chrome_events(_mini_trace(), lo=100, hi=None)

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
        payload = build_perfetto_chrome_trace(_mini_trace(), lo=100, hi=200)
        self.assertEqual(payload["displayTimeUnit"], "ns")
        self.assertEqual(payload["otherData"]["timeScale"], "us")
        self.assertEqual(payload["otherData"]["btf_meta"]["creator"], "test")
        self.assertEqual(payload["otherData"]["export_lo"], 100)
        self.assertEqual(payload["otherData"]["export_hi"], 200)
        self.assertTrue(payload["traceEvents"])

    def test_export_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.json"
            export_perfetto(_mini_trace(), str(path), lo=100, hi=200)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("traceEvents", data)
            self.assertGreater(len(data["traceEvents"]), 0)
            self.assertEqual(data["otherData"]["export_lo"], 100)


if __name__ == "__main__":
    unittest.main()
