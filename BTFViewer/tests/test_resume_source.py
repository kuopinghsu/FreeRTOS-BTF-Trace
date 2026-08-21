"""Segment rebuild accepts Core or previous-task as resume <Source>."""
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

from btf_viewer_pkg.parser import _parse_btf, _task_merge_key  # noqa: E402


def _parse_text(text: str):
    with tempfile.NamedTemporaryFile("w", suffix=".btf", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(text)
        path = fh.name
    try:
        return _parse_btf(path)
    finally:
        Path(path).unlink(missing_ok=True)


def _seg_span(trace, raw_name: str):
    mk = _task_merge_key(raw_name)
    segs = trace.seg_map_by_merge_key.get(mk) or []
    return [(s.start, s.end, s.core) for s in segs]


class TestResumeSource(unittest.TestCase):
    def test_core_source_resume(self) -> None:
        # Spec-shaped: Core is resume source; same-tick preempt closes victim.
        text = "\n".join([
            "#version 2.2.0",
            "#timeScale us",
            "100,Core_0,0,T,[0/0001]A,0,resume,",
            "200,Core_0,0,T,[0/0001]A,0,preempt,",
            "200,Core_0,0,T,[0/0002]B,0,resume,",
            "300,Core_0,0,T,[0/0002]B,0,preempt,",
            "",
        ])
        tr = _parse_text(text)
        self.assertEqual(_seg_span(tr, "[0/0001]A"), [(100, 200, "Core_0")])
        self.assertEqual(_seg_span(tr, "[0/0002]B"), [(200, 300, "Core_0")])

    def test_previous_task_source_resume(self) -> None:
        # Legacy FreeRTOS dialect: resume source is the outgoing task entity.
        text = "\n".join([
            "#version 2.2.0",
            "#timeScale us",
            "100,Core_0,0,T,[0/0001]A,0,resume,",
            "200,Core_0,0,T,[0/0001]A,0,preempt,",
            "200,[0/0001]A,0,T,[0/0002]B,0,resume,",
            "300,Core_0,0,T,[0/0002]B,0,preempt,",
            "",
        ])
        tr = _parse_text(text)
        self.assertEqual(_seg_span(tr, "[0/0001]A"), [(100, 200, "Core_0")])
        self.assertEqual(_seg_span(tr, "[0/0002]B"), [(200, 300, "Core_0")])


if __name__ == "__main__":
    unittest.main()
