"""Unit tests for MVVM helpers (no Qt GUI)."""
from __future__ import annotations

import unittest

from btf_viewer_pkg.mvvm.app_settings import AppSettingsViewModel
from btf_viewer_pkg.mvvm.find_logic import recompute_find_hits
from btf_viewer_pkg.mvvm.models import PlotSessionState
from btf_viewer_pkg.mvvm.trace_tab_vm import TraceTabViewModel
from btf_viewer_pkg.parser import IntervalInstance, TraceAnnotation, BtfTrace

class _MockRc:
    """Minimal stand-in for _RcSettings (no disk I/O)."""

    def __init__(self, sections: dict) -> None:
        self._sections = sections

    def get(self, section: str, key: str, fallback: str = "") -> str:
        return self._sections.get(section, {}).get(key, fallback)

    def get_int(self, section: str, key: str, fallback: int = 0) -> int:
        try:
            return int(self.get(section, key, str(fallback)))
        except ValueError:
            return fallback

    def get_float(self, section: str, key: str, fallback: float = 0.0) -> float:
        try:
            return float(self.get(section, key, str(fallback)))
        except ValueError:
            return fallback

    def get_bool(self, section: str, key: str, fallback: bool = False) -> bool:
        raw = self.get(section, key, "").strip().lower()
        if not raw:
            return fallback
        return raw in ("1", "true", "yes", "on")

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

    def test_contains_task_name(self) -> None:
        trace = BtfTrace.__new__(BtfTrace)
        trace.seg_map_by_merge_key = {
            "T1": [type("S", (), {"start": 200})(), type("S", (), {"start": 300})()],
        }
        trace.task_repr = {"T1": "T1"}
        hits, status = recompute_find_hits(trace, "t1", "Contains", [])
        self.assertEqual(hits, [200, 300])
        self.assertIn("2 matches", status)

    def test_regex_invalid_returns_error(self) -> None:
        trace = BtfTrace.__new__(BtfTrace)
        trace.seg_map_by_merge_key = {}
        trace.task_repr = {}
        hits, status = recompute_find_hits(trace, "[", "Regex", [])
        self.assertEqual(hits, [])
        self.assertEqual(status, "Regex error")

    def test_regex_finds_display_name(self) -> None:
        trace = BtfTrace.__new__(BtfTrace)
        trace.seg_map_by_merge_key = {
            "k": [type("S", (), {"start": 42})()],
        }
        trace.task_repr = {"k": "[0/3]Worker"}
        hits, _ = recompute_find_hits(trace, r"Work", "Regex", [])
        self.assertEqual(hits, [42])

    def test_migrations_mode_filters_by_core(self) -> None:
        trace = BtfTrace.__new__(BtfTrace)
        trace.seg_map_by_merge_key = {}
        trace.task_repr = {"m1": "m1"}
        mig = type("M", (), {
            "merge_key": "m1",
            "from_core": "Core_0",
            "to_core": "Core_1",
            "ns": 900,
        })()
        trace.migrations = [mig]
        hits, status = recompute_find_hits(trace, "core_1", "Migrations", [])
        self.assertEqual(hits, [900])
        self.assertIn("migration", status)

    def test_intervals_mode_matches_instance_id(self) -> None:
        trace = BtfTrace.__new__(BtfTrace)
        trace.seg_map_by_merge_key = {}
        trace.task_repr = {}
        trace.sti_events = []
        trace.interval_instances = [
            IntervalInstance(id="7", start_ns=100, stop_ns=250, task_id="3"),
        ]
        hits, status = recompute_find_hits(trace, "7", "Intervals", [])
        self.assertEqual(hits, [100, 250])
        self.assertIn("2 matches", status)

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

    def test_viewport_rc_payload_round_trip(self) -> None:
        from btf_viewer_pkg.mvvm.models import TabViewportModel
        from btf_viewer_pkg.mvvm.tab_viewport import (
            viewport_from_rc_payload,
            viewport_to_rc_payload,
        )

        vp = TabViewportModel(
            fit_mode=False,
            zoom_tpp=8.0,
            cursors=[10, 20],
            filters={"taskFilterText": "spi", "migratedOnlyFilter": True},
        )
        restored = viewport_from_rc_payload(viewport_to_rc_payload(vp))
        self.assertEqual(restored.fit_mode, vp.fit_mode)
        self.assertEqual(restored.zoom_tpp, vp.zoom_tpp)
        self.assertEqual(restored.cursors, vp.cursors)
        self.assertEqual(restored.filters.get("taskFilterText"), "spi")
        self.assertTrue(restored.filters.get("migratedOnlyFilter"))

    def test_viewport_json_invalid_returns_none(self) -> None:
        from btf_viewer_pkg.mvvm.tab_viewport import viewport_from_json

        self.assertIsNone(viewport_from_json(""))
        self.assertIsNone(viewport_from_json("not-json"))
        self.assertIsNone(viewport_from_json("[]"))

class AppSettingsTests(unittest.TestCase):
    def test_load_view_prefs_from_rc(self) -> None:
        vm = AppSettingsViewModel()
        rc = _MockRc({
            "view": {
                "font_size": "10",
                "label_width": "220",
                "show_cpu_load": "false",
                "cpu_splitter_bottom_h": "140",
                "cpu_splitter_user_sized": "true",
                "colorblind_safe": "true",
            },
        })
        vm.load_view_prefs_from_rc(rc)
        self.assertEqual(vm.font_size, 10)
        self.assertEqual(vm.label_width, 220)
        self.assertFalse(vm.show_cpu_load)
        self.assertEqual(vm.cpu_splitter_bottom_h, 140)
        self.assertTrue(vm.cpu_splitter_user_sized)
        self.assertTrue(vm.colorblind)

    def test_load_theme_from_rc(self) -> None:
        vm = AppSettingsViewModel()
        vm.load_theme_from_rc(_MockRc({"view": {"theme": "light"}}))
        self.assertFalse(vm.is_dark)

    def test_label_width_clamped_by_rc_loader(self) -> None:
        vm = AppSettingsViewModel()
        rc = _MockRc({"view": {"label_width": "9999"}})
        vm.load_view_prefs_from_rc(rc)
        self.assertEqual(vm.label_width, 600)

if __name__ == "__main__":
    unittest.main()
