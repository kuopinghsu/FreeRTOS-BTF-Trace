"""Tests for statistics section pin and order helpers."""
from __future__ import annotations

import unittest

from btf_viewer_pkg import _bootstrap

_bootstrap.install()

from btf_viewer_pkg.config import (  # noqa: E402
    STATS_PINNABLE_SECTIONS,
    move_stats_section,
    normalize_stats_pins,
    normalize_stats_section_order,
    stats_pins_to_rc,
    stats_section_order_to_rc,
)


class StatsPinsTest(unittest.TestCase):
    def test_normalize_dedupes_and_filters(self) -> None:
        self.assertEqual(normalize_stats_pins("cores,bogus,tasks,cores"), ["cores", "tasks"])
        self.assertEqual(normalize_stats_pins(["tags", "tags", ""]), ["tags"])
        self.assertEqual(normalize_stats_pins(None), [])

    def test_rc_roundtrip(self) -> None:
        pins = ["migrations", "exec"]
        self.assertEqual(normalize_stats_pins(stats_pins_to_rc(pins)), pins)

    def test_catalogue_includes_common_sections(self) -> None:
        for sid in ("cores", "tasks", "tags", "migrations"):
            self.assertIn(sid, STATS_PINNABLE_SECTIONS)


class StatsSectionOrderTest(unittest.TestCase):
    def test_normalize_fills_catalogue(self) -> None:
        order = normalize_stats_section_order("tags,cores")
        self.assertEqual(order[:2], ["tags", "cores"])
        self.assertEqual(len(order), len(STATS_PINNABLE_SECTIONS))
        self.assertEqual(set(order), set(STATS_PINNABLE_SECTIONS))

    def test_move_section(self) -> None:
        base = list(STATS_PINNABLE_SECTIONS)
        moved = move_stats_section(base, "tags", "cores")
        self.assertEqual(moved[0], "tags")
        self.assertEqual(moved[1], "cores")
        self.assertEqual(len(moved), len(base))

    def test_rc_roundtrip(self) -> None:
        order = ["tags", "intervals", "cores"]
        self.assertEqual(
            normalize_stats_section_order(stats_section_order_to_rc(order))[:3],
            ["tags", "intervals", "cores"],
        )

    def test_default_order_helpers(self) -> None:
        from btf_viewer_pkg.config import (
            default_stats_section_order,
            is_default_stats_section_order,
        )
        self.assertTrue(is_default_stats_section_order(None))
        self.assertTrue(is_default_stats_section_order(default_stats_section_order()))
        self.assertFalse(is_default_stats_section_order(["tags", "cores"]))
        # Matches builds/btf_viewer.rc section_order used as the catalogue default.
        self.assertEqual(
            default_stats_section_order()[:9],
            [
                "cores", "health", "core_breakdown", "tasks", "migrations",
                "core_pairs", "affinity", "lifecycle", "deadline",
            ],
        )


if __name__ == "__main__":
    unittest.main()
