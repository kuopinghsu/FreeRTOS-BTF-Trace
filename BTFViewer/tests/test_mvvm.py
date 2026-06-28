"""Unit tests for MVVM helpers (no Qt GUI)."""
from __future__ import annotations

import unittest

from btf_viewer_pkg.mvvm.find_logic import recompute_find_hits
from btf_viewer_pkg.mvvm.models import PlotSessionState
from btf_viewer_pkg.mvvm.trace_tab_vm import TraceTabViewModel
from btf_viewer_pkg.parser import TraceAnnotation, BtfTrace


class FindLogicTests(unittest.TestCase):
    def test_empty_query_returns_no_hits(self) -> None:
        hits, status = recompute_find_hits(None, "  ", "Contains", [])
        self.assertEqual(hits, [])
        self.assertEqual(status, "0 matches")

    def test_exact_task_match(self) -> None:
        trace = BtfTrace.__new__(BtfTrace)
        trace.seg_map_by_merge_key = {"T1": [type("S", (), {"start": 100})()]}
        trace.task_repr = {"T1": "T1"}
        hits, status = recompute_find_hits(trace, "T1", "Exact", [])
        self.assertEqual(hits, [100])
        self.assertIn("1 match", status)

    def test_annotation_contains(self) -> None:
        trace = BtfTrace.__new__(BtfTrace)
        trace.seg_map_by_merge_key = {}
        trace.task_repr = {}
        ann = TraceAnnotation(1, 500, "watchdog timeout")
        hits, _ = recompute_find_hits(trace, "watch", "Contains", [ann])
        self.assertEqual(hits, [500])


class PlotSessionTests(unittest.TestCase):
    def test_interval_id_round_trip(self) -> None:
        trace = BtfTrace.__new__(BtfTrace)
        vm = TraceTabViewModel("/tmp/x.btf", trace)
        vm.set_plot_session("3", "interval", True, None, "3")
        mk, kind, open_, preemptor, iid = vm.capture_plot_session()
        self.assertEqual((mk, kind, open_, preemptor, iid),
                         ("3", "interval", True, None, "3"))
        self.assertEqual(vm.plot_interval_id, "3")


class TabViewportTests(unittest.TestCase):
    def test_viewport_json_round_trip(self) -> None:
        from btf_viewer_pkg.mvvm.models import TabViewportModel
        from btf_viewer_pkg.mvvm.tab_viewport import (
            viewport_from_json,
            viewport_to_json,
        )

        vp = TabViewportModel(
            fit_mode=False,
            zoom_tpp=12.5,
            cursors=[100, 200],
            filters={"taskFilterText": "idle"},
        )
        raw = viewport_to_json(vp)
        restored = viewport_from_json(raw)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.fit_mode, vp.fit_mode)
        self.assertEqual(restored.zoom_tpp, vp.zoom_tpp)
        self.assertEqual(restored.cursors, vp.cursors)
        self.assertEqual(restored.filters.get("taskFilterText"), "idle")


if __name__ == "__main__":
    unittest.main()
