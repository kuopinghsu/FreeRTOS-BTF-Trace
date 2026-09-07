"""Trace-health overhead measurement.

Acceptance criterion (BTFVIEWER_PORTABLE_INVESTIGATION_TODO Phase 1):
"Health checks do not noticeably delay opening normal traces; measure and
document the overhead."

This test measures ``build_trace_health_result`` against a representative
multicore trace and fails only if the structural checks cost a large fraction
of a single parse (i.e. they would be noticeable when opening a trace).
"""
from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.parser import _parse_btf  # noqa: E402
from btf_viewer_pkg.trace_health import build_trace_health_result  # noqa: E402

TRACE = BTF_ROOT.parent / "tracedata" / "example-4cores.btf.gz"

# Ceiling: the check pass must stay well under a quarter of one parse and under
# an absolute 50 ms, so it is imperceptible on the trace-open path.
MAX_FRACTION_OF_PARSE = 0.25
MAX_ABS_SECONDS = 0.050


class TraceHealthPerfTest(unittest.TestCase):
    def test_overhead_is_not_noticeable(self):
        if not TRACE.exists():  # pragma: no cover - dataset optional in some checkouts
            self.skipTest(f"missing dataset {TRACE}")

        t0 = time.perf_counter()
        trace = _parse_btf(str(TRACE))
        parse_s = time.perf_counter() - t0

        # Warm once (import-time / attribute caches), then measure a few runs.
        build_trace_health_result(trace)
        runs = 5
        t0 = time.perf_counter()
        for _ in range(runs):
            result = build_trace_health_result(trace)
        health_s = (time.perf_counter() - t0) / runs

        seg_n = len(getattr(trace, "segments", []) or [])
        frac = health_s / parse_s if parse_s else 0.0
        print(
            f"\n[trace-health overhead] {TRACE.name}: {seg_n:,} segments, "
            f"{len(trace.core_names or [])} cores\n"
            f"  parse            {parse_s * 1e3:8.2f} ms\n"
            f"  health check     {health_s * 1e3:8.2f} ms  "
            f"({frac * 100:.1f}% of parse)\n"
            f"  status           {result['status']} "
            f"({result['issue_count']} issue(s))"
        )

        self.assertLess(health_s, MAX_ABS_SECONDS,
                        f"health check took {health_s * 1e3:.1f} ms")
        self.assertLess(frac, MAX_FRACTION_OF_PARSE,
                        f"health check is {frac * 100:.1f}% of parse time")


if __name__ == "__main__":
    unittest.main()
