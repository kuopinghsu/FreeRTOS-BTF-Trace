"""_build_chord_layout — parity with the web app's buildChordLayout()
(BTFViewer/web/src/utils/migrationAnalysis.js / migrationChordLayout.test.js)."""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.parser import (  # noqa: E402
    _CHORD_ARC_INNER,
    _CHORD_ARC_OUTER,
    _build_chord_layout,
    _chord_hit_ring,
    _chord_label_step,
    _chord_label_visible,
    _chord_ring_geometry,
    _corridor_groups_by_source,
    _filter_corridors_by_task_query,
    _trace_has_core_bounce_holds,
)


class TestBuildChordLayout(unittest.TestCase):
    def test_every_core_gets_a_non_overlapping_arc(self) -> None:
        cores = ["Core_0", "Core_1", "Core_2"]
        grid = [
            [0, 5, 0],
            [0, 0, 0],
            [2, 0, 0],
        ]
        layout = _build_chord_layout(cores, grid)
        self.assertEqual(len(layout.arcs), 3)
        for arc in layout.arcs:
            self.assertGreater(arc.end_angle, arc.start_angle)
        for i in range(1, len(layout.arcs)):
            self.assertGreaterEqual(
                layout.arcs[i].start_angle, layout.arcs[i - 1].end_angle)

    def test_arc_size_proportional_to_total_migration_volume(self) -> None:
        cores = ["Core_0", "Core_1", "Core_2"]
        # Core_0 <-> Core_1 dominates; Core_2 has no traffic at all.
        grid = [
            [0, 100, 0],
            [100, 0, 0],
            [0, 0, 0],
        ]
        layout = _build_chord_layout(cores, grid)

        def span_of(core: str) -> float:
            arc = next(a for a in layout.arcs if a.core == core)
            return arc.end_angle - arc.start_angle

        self.assertGreater(span_of("Core_0"), span_of("Core_2"))
        self.assertGreater(span_of("Core_1"), span_of("Core_2"))
        # The zero-flow core should still get a visible sliver, not a zero-width arc.
        self.assertGreater(span_of("Core_2"), 0)

    def test_tick_angle_within_both_endpoints_arcs(self) -> None:
        cores = ["Core_0", "Core_1"]
        grid = [
            [0, 3],
            [1, 0],
        ]
        layout = _build_chord_layout(cores, grid)
        arc0, arc1 = layout.arcs[0], layout.arcs[1]
        t01 = layout.tick_angle(0, 1)
        t10 = layout.tick_angle(1, 0)
        self.assertTrue(arc0.start_angle <= t01 <= arc0.end_angle)
        self.assertTrue(arc1.start_angle <= t10 <= arc1.end_angle)

    def test_all_zero_matrix_distributes_arcs_evenly(self) -> None:
        cores = ["Core_0", "Core_1"]
        grid = [
            [0, 0],
            [0, 0],
        ]
        layout = _build_chord_layout(cores, grid)
        self.assertEqual(len(layout.arcs), 2)
        for arc in layout.arcs:
            self.assertGreater(arc.end_angle, arc.start_angle)

    def test_empty_cores_returns_empty_layout(self) -> None:
        layout = _build_chord_layout([], [])
        self.assertEqual(layout.arcs, [])

    def test_default_tick_angle_falls_back_to_arc_midpoint(self) -> None:
        cores = ["Core_0", "Core_1"]
        grid = [
            [0, 0],
            [0, 0],
        ]
        layout = _build_chord_layout(cores, grid)
        arc0 = layout.arcs[0]
        expected_mid = (arc0.start_angle + arc0.end_angle) / 2
        self.assertTrue(math.isclose(layout.tick_angle(0, 1), expected_mid))


    def test_egress_ingress_ticks_and_taper(self) -> None:
        cores = ["Core_0", "Core_1"]
        grid = [
            [0, 10],
            [2, 0],
        ]
        layout = _build_chord_layout(cores, grid)
        self.assertEqual(layout.arcs[0].out_total, 10)
        self.assertEqual(layout.arcs[0].in_total, 2)
        src, dst = layout.ribbon_half_widths(0, 1, 10)
        self.assertGreater(src, dst)

    def test_default_corridor_top_pct(self) -> None:
        from btf_viewer_pkg.parser import _default_corridor_top_pct
        self.assertEqual(_default_corridor_top_pct(4), 100)
        self.assertEqual(_default_corridor_top_pct(16), 25)

    def test_filter_corridors_by_direction(self) -> None:
        from btf_viewer_pkg.parser import _filter_corridors_by_direction
        rows = [
            {"from_core": "Core_0", "to_core": "Core_1", "count": 10},
            {"from_core": "Core_0", "to_core": "Core_2", "count": 4},
            {"from_core": "Core_1", "to_core": "Core_0", "count": 3},
        ]
        sel = {"from_core": "Core_0", "to_core": "Core_1"}
        self.assertEqual(len(_filter_corridors_by_direction(rows, "all", sel)), 3)
        egress = _filter_corridors_by_direction(rows, "egress", sel)
        self.assertEqual([c["to_core"] for c in egress], ["Core_1", "Core_2"])
        ingress = _filter_corridors_by_direction(rows, "ingress", sel)
        self.assertEqual(
            [(c["from_core"], c["to_core"]) for c in ingress],
            [("Core_0", "Core_1")],
        )
        self.assertEqual(_filter_corridors_by_direction(rows, "egress", None), rows)

    def test_filter_corridors_by_task_query(self) -> None:
        rows = [
            {
                "from_core": "Core_0", "to_core": "Core_1", "label": "c0→c1",
                "count": 10,
                "tasks": [{"label": "CS[22]", "mk": "cs:22"}],
            },
            {
                "from_core": "Core_2", "to_core": "Core_3", "label": "c2→c3",
                "count": 4,
                "tasks": [{"label": "Idle", "mk": "idle:0"}],
            },
        ]
        hit = _filter_corridors_by_task_query(rows, "cs[22]")
        self.assertEqual([c["label"] for c in hit], ["c0→c1"])
        by_mk = _filter_corridors_by_task_query(rows, "idle:0")
        self.assertEqual([c["label"] for c in by_mk], ["c2→c3"])
        self.assertEqual(_filter_corridors_by_task_query(rows, ""), rows)
        padded = [
            {
                "from_core": "Core_0", "to_core": "Core_1", "label": "c0→c1",
                "count": 3,
                "tasks": [{"label": "CS[11]", "mk": "\x0011\x00CS"}],
            },
            {
                "from_core": "Core_2", "to_core": "Core_3", "label": "c2→c3",
                "count": 1,
                "tasks": [{"label": "Idle", "mk": "idle:0"}],
            },
        ]
        by_id = _filter_corridors_by_task_query(padded, "11")
        self.assertEqual([c["label"] for c in by_id], ["c0→c1"])
        by_pad = _filter_corridors_by_task_query(padded, "0011")
        self.assertEqual([c["label"] for c in by_pad], ["c0→c1"])
        mixed = [
            {
                "from_core": "Core_0", "to_core": "Core_1", "label": "c0→c1",
                "count": 5, "rev_count": 0, "net": 0,
                "bins": [2, 3], "bounce_bins": [0, 0],
                "tasks": [
                    {"label": "CS[28]", "mk": "\x0028\x00CS", "count": 2,
                     "bounces": 0, "bins": [2, 0], "bounce_bins": [0, 0]},
                    {"label": "CS[128]", "mk": "\x00128\x00CS", "count": 3,
                     "bounces": 0, "bins": [0, 3], "bounce_bins": [0, 0]},
                ],
            },
            {
                "from_core": "Core_2", "to_core": "Core_3", "label": "c2→c3",
                "count": 1, "rev_count": 0, "net": 0,
                "bins": [1, 0], "bounce_bins": [0, 0],
                "tasks": [
                    {"label": "CS[128]", "mk": "\x00128\x00CS", "count": 1,
                     "bounces": 0, "bins": [1, 0], "bounce_bins": [0, 0]},
                ],
            },
        ]
        only28 = _filter_corridors_by_task_query(mixed, "28")
        self.assertEqual([c["label"] for c in only28], ["c0→c1"])
        self.assertEqual([t["label"] for t in only28[0]["tasks"]], ["CS[28]"])
        self.assertEqual(only28[0]["count"], 2)
        self.assertEqual(only28[0]["bins"], [2, 0])
        self.assertEqual(_filter_corridors_by_task_query(mixed, "128")[0]["count"], 3)
        # Core names must not masquerade as a task id.
        self.assertEqual(_filter_corridors_by_task_query(mixed, "2"), [])
        btf_raw = [{
            "from_core": "Core_0", "to_core": "Core_1", "label": "c0→c1",
            "count": 1, "bins": [1], "bounce_bins": [0],
            "tasks": [{"label": "[0/0028]CS", "mk": "[0/0028]CS", "count": 1,
                       "bins": [1], "bounce_bins": [0]}],
        }]
        self.assertEqual(len(_filter_corridors_by_task_query(btf_raw, "28")), 1)
        stripped = [{
            "from_core": "Core_0", "to_core": "Core_1", "label": "c0→c1",
            "count": 1, "bins": [1], "bounce_bins": [0],
            "tasks": [{"label": "28CS", "mk": "28CS", "count": 1,
                       "bins": [1], "bounce_bins": [0]}],
        }]
        self.assertEqual(len(_filter_corridors_by_task_query(stripped, "28")), 1)

    def test_corridor_groups_by_source(self) -> None:
        rows = [
            {"from_core": "Core_0", "to_core": "Core_1", "count": 10},
            {"from_core": "Core_0", "to_core": "Core_2", "count": 4},
            {"from_core": "Core_1", "to_core": "Core_0", "count": 3},
        ]
        groups = _corridor_groups_by_source(rows)
        self.assertEqual([g["source"] for g in groups], ["Core_0", "Core_1"])
        self.assertEqual(groups[0]["count"], 14)
        self.assertEqual(len(groups[0]["corridors"]), 2)

    def test_chord_label_step_skips_dense_cores(self) -> None:
        self.assertEqual(_chord_label_step(8), 1)
        self.assertEqual(_chord_label_step(16), 1)
        self.assertEqual(_chord_label_step(32), 2)
        self.assertEqual(_chord_label_step(64), 5)
        self.assertEqual(_chord_label_step(128), 8)
        self.assertTrue(_chord_label_visible(0, 5))
        self.assertTrue(_chord_label_visible(5, 5))
        self.assertTrue(_chord_label_visible(10, 5))
        self.assertFalse(_chord_label_visible(3, 5))
        self.assertTrue(_chord_label_visible(3, 5, {3}))
        tight = _chord_label_step(40, min_px=20.0, span_px=80.0)
        self.assertGreaterEqual(tight, 5)

    def test_split_rings_outer_egress_inner_ingress(self) -> None:
        r_e, r_i, r_rib = _chord_ring_geometry(100)
        self.assertEqual(r_e, 100)
        self.assertLess(r_i, r_e)
        self.assertLess(r_rib, r_i)
        self.assertEqual(r_e - r_i, _CHORD_ARC_OUTER + 2)
        self.assertEqual(_chord_hit_ring(100, 100), "egress")
        self.assertEqual(_chord_hit_ring(r_i, 100), "ingress")
        self.assertIsNone(_chord_hit_ring(0, 100))
        self.assertLess(_CHORD_ARC_INNER, _CHORD_ARC_OUTER)

    def test_trace_has_core_bounce_holds(self) -> None:
        class _T:
            has_sync_object_instrumentation = False
            sync_objects = {}

        t = _T()
        self.assertFalse(_trace_has_core_bounce_holds(t))
        t.has_sync_object_instrumentation = True
        t.sync_objects = {
            "m1": {"holds": [{"take_core": "Core_0", "give_core": "Core_0"}]},
        }
        self.assertFalse(_trace_has_core_bounce_holds(t))
        t.sync_objects = {
            "m1": {"holds": [{"take_core": "Core_0", "give_core": "Core_1"}]},
        }
        self.assertTrue(_trace_has_core_bounce_holds(t))


if __name__ == "__main__":
    unittest.main()
