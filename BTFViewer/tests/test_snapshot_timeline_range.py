"""CLI snapshot timeline --lo/--hi must fill the viewport after layout."""
from __future__ import annotations

import argparse
import os
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.cli import _cli_snapshot_timeline  # noqa: E402
from btf_viewer_pkg.parser import _parse_btf  # noqa: E402

EXAMPLE_BTF = Path(__file__).resolve().parents[2] / "tracedata" / "example-8cores.btf.gz"


class TestSnapshotTimelineRange(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_lo_hi_fills_viewport_after_show(self) -> None:
        if not EXAMPLE_BTF.is_file():
            self.skipTest(f"missing trace fixture: {EXAMPLE_BTF}")

        trace = _parse_btf(str(EXAMPLE_BTF))
        span = max(trace.time_max - trace.time_min, 1)
        lo = trace.time_min + span // 4
        hi = lo + max(span // 20, 1000)
        args = argparse.Namespace(
            metric=None, task=None, lo=lo, hi=hi,
            theme="dark", width=1600, height=900,
        )
        view, err = _cli_snapshot_timeline(trace, args)
        self.assertIsNone(err)
        self.assertIsNotNone(view)
        assert view is not None

        wanted = hi - lo
        visible = view._visible_time_span_ns()
        # Allow ~15% slack for label column / rounding / edge clamp.
        self.assertLess(
            abs(visible - wanted) / wanted, 0.15,
            f"visible_span={visible} wanted={wanted} tpp={view._scene._timescale_per_px}",
        )
        ns_lo, ns_hi = view._visible_time_ns_range()
        self.assertLessEqual(ns_lo, lo + wanted * 0.1)
        self.assertGreaterEqual(ns_hi, hi - wanted * 0.1)
        view.close()
        self._app.processEvents()


if __name__ == "__main__":
    unittest.main()
