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
        for sid in ("cores", "tasks", "tags", "migrations",
                    "period", "task_core", "wait_owner", "task_health",
                    "response", "crit_path", "jitter", "distrib", "patterns",
                    "preempt_matrix", "mutex_block", "core_time"):
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
        self.assertEqual(moved.index("tags") + 1, moved.index("cores"))
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
        # Matches OVERVIEW → TRIAGE → TIMING … catalogue default (Step 1.1).
        self.assertEqual(
            default_stats_section_order()[:9],
            [
                "cores", "health", "task_health",
                "anomalies", "worst", "patterns",
                "response", "exec", "dispatch",
            ],
        )




class StatsPresentationTest(unittest.TestCase):
    def test_non_smp_all_collapsed(self) -> None:
        from btf_viewer_pkg.config import default_stats_presentation

        class _T:
            core_names = ["Core_0", "Core_1"]
            core_util_pct = {"Core_0": 55.0, "Core_1": 0.0}

        pins, collapsed = default_stats_presentation(_T())
        self.assertEqual(pins, [])
        self.assertTrue(all(collapsed.values()))

    def test_smp_pins_cores(self) -> None:
        from btf_viewer_pkg.config import default_stats_presentation

        class _T:
            core_names = ["Core_0", "Core_1"]
            core_util_pct = {"Core_0": 40.0, "Core_1": 25.0}

        pins, collapsed = default_stats_presentation(_T())
        self.assertEqual(pins, ["cores"])
        self.assertFalse(collapsed["cores"])
        self.assertTrue(all(v for sid, v in collapsed.items() if sid != "cores"))


class StatsCategoryBadgeColorTest(unittest.TestCase):
    def test_palette_covers_all_categories(self) -> None:
        from btf_viewer_pkg.config import (
            STATS_CATEGORY_BADGE_COLORS,
            STATS_SECTION_CATEGORIES,
            stats_category_badge_colors,
            stats_category_badge_stylesheet,
        )

        self.assertEqual(
            set(STATS_CATEGORY_BADGE_COLORS), set(STATS_SECTION_CATEGORIES))
        for cat in STATS_SECTION_CATEGORIES:
            for dark in (True, False):
                bg, fg, border = stats_category_badge_colors(cat, dark=dark)
                self.assertTrue(bg.startswith("#") and len(bg) == 7, cat)
                self.assertTrue(fg.startswith("#") and len(fg) == 7, cat)
                self.assertTrue(border.startswith("#") and len(border) == 7, cat)
                # Soft tint: background must differ from text (not a solid fill).
                self.assertNotEqual(bg.upper(), fg.upper(), cat)
                css = stats_category_badge_stylesheet(cat, dark=dark)
                self.assertIn(bg, css)
                self.assertIn(fg, css)
                self.assertIn(border, css)

    def test_hue_identity_matches_recommended_palette(self) -> None:
        from btf_viewer_pkg.config import STATS_CATEGORY_BADGE_COLORS

        # Exact Step 1.1-color table (light bg/fg/border, dark bg/fg/border).
        expected = {
            "OVERVIEW": (
                ("#E8EDF2", "#536475", "#B8C4CF"),
                ("#26313B", "#C3CED8", "#4A5966"),
            ),
            "TRIAGE": (
                ("#F7EDD7", "#8A641F", "#DFC68E"),
                ("#3A3020", "#E2C27C", "#675630"),
            ),
            "TIMING": (
                ("#E3EDF9", "#426A9E", "#AFC7E5"),
                ("#243449", "#A9C5E8", "#47658A"),
            ),
            "SCHED": (
                ("#ECE8F7", "#665A98", "#C5BCE0"),
                ("#302C44", "#C1B7E3", "#5D557B"),
            ),
            "SYNC": (
                ("#E2F1EF", "#39746F", "#ADD2CD"),
                ("#203A38", "#9DD0CA", "#426C68"),
            ),
            "DETAIL": (
                ("#ECEDEF", "#656B72", "#C8CBD0"),
                ("#303337", "#C0C4C9", "#565B61"),
            ),
        }
        for cat, (light, dark) in expected.items():
            self.assertEqual(STATS_CATEGORY_BADGE_COLORS[cat]["light"], light, cat)
            self.assertEqual(STATS_CATEGORY_BADGE_COLORS[cat]["dark"], dark, cat)


if __name__ == "__main__":
    unittest.main()
