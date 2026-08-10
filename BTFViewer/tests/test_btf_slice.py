"""Cursor-range BTF slice export (GUI + CLI)."""
from __future__ import annotations

import argparse
import gzip
import os
import sys
import tempfile
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.btf_slice import (  # noqa: E402
    filter_btf_file_to_range,
    filter_btf_text_to_range,
    reconstruct_btf_slice,
    write_btf_text,
)
from btf_viewer_pkg.cli import _cli_slice_run  # noqa: E402
from btf_viewer_pkg.parser import BtfTrace, StiEvent, TaskSegment  # noqa: E402

_SRC = """\
#version 1.0.0
#timeScale us
0,Core_0,0,C,1000000
100,Core_0,0,T,Worker,0,resume,
150,Core_0,0,T,Worker,0,preempt,
200,Core_0,0,T,Worker,0,resume,
250,Core_0,0,STI,ERR,0,trigger,boom
300,Core_0,0,T,Worker,0,preempt,
"""


class BtfSliceTests(unittest.TestCase):
    def test_filter_keeps_meta_c_and_in_range_events(self) -> None:
        text, kept = filter_btf_text_to_range(_SRC, 200, 250)
        self.assertIn("#version 1.0.0", text)
        self.assertIn("#sliced 200-250", text)
        self.assertIn("0,Core_0,0,C,1000000", text)
        self.assertIn("200,Core_0,0,T,Worker,0,resume,", text)
        self.assertIn("250,Core_0,0,STI,ERR,0,trigger,boom", text)
        self.assertNotIn("100,Core_0,0,T,Worker,0,resume,", text)
        self.assertNotIn("300,Core_0,0,T,Worker,0,preempt,", text)
        self.assertEqual(kept, 2)

    def test_filter_swaps_inverted_range(self) -> None:
        text, kept = filter_btf_text_to_range(_SRC, 250, 200)
        self.assertEqual(kept, 2)
        self.assertIn("#sliced 200-250", text)

    def test_write_gz_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "win.btf.gz"
            write_btf_text("#ok\n1,Core_0,0,T,A,0,resume,\n", str(dest))
            with gzip.open(dest, "rt", encoding="utf-8") as fh:
                body = fh.read()
            self.assertIn("#ok", body)

    def test_reconstruct_from_segments(self) -> None:
        trace = BtfTrace(
            time_scale="us",
            meta={"creator": "test"},
            tasks=["Worker"],
            segments=[
                TaskSegment(task="Worker", start=100, end=400, core="Core_0"),
            ],
            sti_events=[
                StiEvent(time=220, core="Core_0", target="ERR", event="trigger", note="boom"),
            ],
            sti_channels=[],
            sti_events_by_target={},
            time_min=100,
            time_max=400,
            task_repr={"Worker": "Worker"},
        )
        text, kept = reconstruct_btf_slice(trace, 150, 250)
        self.assertIn("#creator test", text)
        self.assertIn("#sliced 150-250", text)
        self.assertIn("150,Core_0,0,T,Worker,0,resume,", text)
        self.assertIn("250,Core_0,0,T,Worker,0,preempt,", text)
        self.assertIn("220,Core_0,0,STI,ERR,0,trigger,boom", text)
        self.assertEqual(kept, 3)

    def test_cli_slice_writes_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "full.btf"
            dest = Path(tmp) / "window.btf"
            src.write_text(_SRC, encoding="utf-8")
            rc = _cli_slice_run(argparse.Namespace(
                trace=str(src), output=str(dest), lo=200, hi=250))
            self.assertEqual(rc, 0)
            body = dest.read_text(encoding="utf-8")
            self.assertIn("200,Core_0,0,T,Worker,0,resume,", body)
            self.assertNotIn("100,Core_0,0,T,Worker,0,resume,", body)

    def test_filter_file_gz(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "full.btf.gz"
            with gzip.open(src, "wt", encoding="utf-8") as fh:
                fh.write(_SRC)
            text, kept = filter_btf_file_to_range(str(src), 200, 300)
            self.assertEqual(kept, 3)
            self.assertIn("300,Core_0,0,T,Worker,0,preempt,", text)


if __name__ == "__main__":
    unittest.main()
