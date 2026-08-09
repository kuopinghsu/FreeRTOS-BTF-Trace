"""Unit tests for config helpers (minimal Qt)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.config import (  # noqa: E402
    STATS_TABLE_DISPLAY_ROW_CAP,
    _cursor_colors,
    _is_tag_sti_channel,
    _sanitize_tab_filters,
    _scaled_font_pixel_size,
    _sti_channel_sort_key,
    cap_stats_table_rows,
    default_section_collapsed,
    default_section_table_heights,
)

class StiChannelTests(unittest.TestCase):
    def test_tag_event_is_expandable(self) -> None:
        self.assertTrue(_is_tag_sti_channel("tag_event"))
        self.assertTrue(_is_tag_sti_channel("TAG3_EVENT"))

    def test_non_tag_channel_not_expandable(self) -> None:
        self.assertFalse(_is_tag_sti_channel("tick_event"))
        self.assertFalse(_is_tag_sti_channel("tag8_event"))

    def test_tag_sort_order(self) -> None:
        channels = ["tick_event", "tag2_event", "tag_event", "tag0_event", "uart_rx"]
        ordered = sorted(channels, key=_sti_channel_sort_key)
        self.assertEqual(
            ordered[:4],
            ["tag_event", "tag0_event", "tag2_event", "tick_event"],
        )
        self.assertEqual(ordered[-1], "uart_rx")

class TabFilterSanitizeTests(unittest.TestCase):
    def test_non_dict_returns_none(self) -> None:
        self.assertIsNone(_sanitize_tab_filters([]))
        self.assertIsNone(_sanitize_tab_filters("x"))

    def test_empty_task_keys_become_none(self) -> None:
        out = _sanitize_tab_filters({
            "taskFilterKeys": ["", None],
            "taskFilterText": "idle",
        })
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIsNone(out["taskFilterKeys"])
        self.assertEqual(out["taskFilterText"], "idle")

    def test_drops_heatmap_spotlight(self) -> None:
        out = _sanitize_tab_filters({
            "taskFilterKeys": ["T1", "T2"],
            "heatmapFilterLabel": "Core_0",
            "migratedOnlyFilter": True,
        })
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIsNone(out["taskFilterKeys"])
        self.assertIsNone(out["heatmapFilterLabel"])
        self.assertTrue(out["migratedOnlyFilter"])

class ConfigDefaultsTests(unittest.TestCase):
    def test_section_collapsed_keys(self) -> None:
        collapsed = default_section_collapsed()
        self.assertIn("cores", collapsed)
        self.assertIn("intervals", collapsed)
        self.assertFalse(collapsed["cores"])

    def test_section_table_heights_positive(self) -> None:
        heights = default_section_table_heights()
        for key, h in heights.items():
            self.assertGreater(h, 0, msg=key)

    def test_cores_default_shows_gauge_and_two_util_rows(self) -> None:
        from btf_viewer_pkg.config import (
            STATS_CORES_DEFAULT_VISIBLE_ROWS,
            STATS_CORES_UTIL_DEFAULT_H,
            STATS_LB_GAUGE_H,
            STATS_UTIL_DEFAULT_H,
            _stats_util_viewport_height,
        )
        self.assertEqual(STATS_CORES_DEFAULT_VISIBLE_ROWS, 2)
        self.assertEqual(
            STATS_CORES_UTIL_DEFAULT_H,
            STATS_LB_GAUGE_H + _stats_util_viewport_height(2))
        self.assertGreater(STATS_CORES_UTIL_DEFAULT_H, STATS_UTIL_DEFAULT_H)
        self.assertEqual(
            default_section_table_heights()["cores"],
            STATS_CORES_UTIL_DEFAULT_H)

    def test_cursor_palette_differs_by_theme(self) -> None:
        dark = _cursor_colors(True)
        light = _cursor_colors(False)
        self.assertEqual(len(dark), len(light))
        self.assertNotEqual(dark[0], light[0])

class StatsTableCapTests(unittest.TestCase):
    def test_cap_stats_table_rows_short(self) -> None:
        rows, note = cap_stats_table_rows([1, 2, 3], cap=10)
        self.assertEqual(rows, [1, 2, 3])
        self.assertIsNone(note)

    def test_cap_stats_table_rows_oversize(self) -> None:
        src = list(range(STATS_TABLE_DISPLAY_ROW_CAP + 5))
        rows, note = cap_stats_table_rows(src)
        self.assertEqual(len(rows), STATS_TABLE_DISPLAY_ROW_CAP)
        self.assertIsNotNone(note)
        assert note is not None
        self.assertIn("Export", note)
        self.assertIn("Showing first", note)


class FontScalingTests(unittest.TestCase):
    def test_scaled_pixel_size_clamps(self) -> None:
        px = _scaled_font_pixel_size(4)
        if px is not None:
            self.assertGreaterEqual(px, 6)
        px_hi = _scaled_font_pixel_size(99)
        if px_hi is not None:
            px_cap = _scaled_font_pixel_size(24)
            assert px_cap is not None
            # pt input is capped at 24; oversized values must not exceed 24pt in px.
            self.assertLessEqual(px_hi, px_cap)
            self.assertEqual(px_hi, px_cap)

if __name__ == "__main__":
    unittest.main()
