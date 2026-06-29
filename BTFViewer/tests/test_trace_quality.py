"""Unit tests for BTF trace quality metadata warnings."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.trace_quality import (  # noqa: E402
    collect_trace_quality_warnings,
    trace_quality_summary,
)

def _trace(meta: dict) -> SimpleNamespace:
    return SimpleNamespace(meta=meta)

class TraceQualityTests(unittest.TestCase):
    def test_ring_overflow_meta_line(self) -> None:
        warnings = collect_trace_quality_warnings(_trace({"ringOverflow": "true"}))
        self.assertEqual(len(warnings), 1)
        self.assertIn("ring buffer overflow", warnings[0])

    def test_all_quality_flags(self) -> None:
        warnings = collect_trace_quality_warnings(_trace({
            "ringOverflow": "true",
            "taskTableOverflow": "true",
            "truncated": "true",
        }))
        self.assertEqual(len(warnings), 3)

    def test_version_warning_included(self) -> None:
        warnings = collect_trace_quality_warnings(_trace({
            "_version_warning": "Unsupported BTF format version: 3.0.0 (expected 2.x)",
        }))
        self.assertEqual(len(warnings), 1)
        self.assertIn("Unsupported", warnings[0])

    def test_summary_joins_messages(self) -> None:
        text = trace_quality_summary(_trace({
            "ringOverflow": "true",
            "truncated": "true",
        }))
        self.assertIsNotNone(text)
        assert text is not None
        self.assertIn(" · ", text)

    def test_clean_trace_returns_none(self) -> None:
        self.assertIsNone(trace_quality_summary(_trace({"version": "2.2.0"})))

if __name__ == "__main__":
    unittest.main()
