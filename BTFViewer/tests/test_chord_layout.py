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

from btf_viewer_pkg.parser import _build_chord_layout  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
