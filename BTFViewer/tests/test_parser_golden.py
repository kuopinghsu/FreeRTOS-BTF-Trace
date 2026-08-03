"""Shared parser golden vectors (Python ↔ JS parity)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.parser import _parse_btf, _sync_object_stats_rows  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "example-4cores-sync-golden.json"
TRACE = Path(__file__).resolve().parents[2] / "tracedata" / "example-4cores.btf.gz"

class TestParserGolden(unittest.TestCase):
    def test_sync_object_golden_example_4cores(self) -> None:
        if not TRACE.is_file():
            self.skipTest(f"missing trace fixture: {TRACE}")
        if not FIXTURE.is_file():
            self.skipTest(f"missing golden fixture: {FIXTURE}")

        expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        trace = _parse_btf(str(TRACE))

        self.assertTrue(trace.has_sync_object_instrumentation)
        self.assertEqual(len(trace.sync_objects), expected["syncObjectCount"])
        self.assertEqual(len(trace.sync_issues), expected["syncIssueCount"])
        self.assertEqual(
            sum(1 for o in trace.sync_objects.values() if o["kind"] == "queue"),
            expected["queueCount"],
        )

        rows = _sync_object_stats_rows(trace, None, None)
        actual = sorted(
            [
                {"kind": r[1], "ptr": r[2], "holds": r[4], "issues": r[5], "status": r[8]}
                for r in rows
            ],
            key=lambda x: (x["kind"], x["ptr"]),
        )
        self.assertEqual(actual, expected["objects"])

if __name__ == "__main__":
    unittest.main()
