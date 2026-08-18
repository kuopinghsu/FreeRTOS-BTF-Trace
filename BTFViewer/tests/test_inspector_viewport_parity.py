"""Desktop ↔ Web lockstep for the Migration heatmap Full view / Viewport view banner.

Source-string and extracted-helper checks only (no Qt import) so this stays
runnable when the rest of the desktop stack cannot start.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Tuple

BTF_ROOT = Path(__file__).resolve().parents[1]
STATS_PY = (BTF_ROOT / "btf_viewer_pkg" / "stats.py").read_text(encoding="utf-8")
MIG_JS = (BTF_ROOT / "web" / "src" / "utils" / "migrationAnalysis.js").read_text(
    encoding="utf-8")
CI_VUE = (BTF_ROOT / "web" / "src" / "components" / "CorridorInspectorDialog.vue"
          ).read_text(encoding="utf-8")
PLOT_VUE = (BTF_ROOT / "web" / "src" / "components" / "StatisticsPanel.vue"
            ).read_text(encoding="utf-8")
TIMELINE_VUE = (BTF_ROOT / "web" / "src" / "components" / "TimelinePanel.vue"
                ).read_text(encoding="utf-8")


def _load_desktop_helpers() -> dict:
    m = re.search(
        r"(_INSPECTOR_FULL_VIEW_RATIO = 0\.92\n"
        r".*?"
        r"    return True, \"Viewport view\", detail\n)",
        STATS_PY,
        re.S,
    )
    if m is None:
        raise AssertionError(
            "could not extract inspector viewport helpers from stats.py")
    ns: dict = {
        "_format_time": lambda value, unit: f"{value}{unit}",
        "Tuple": Tuple,
    }
    exec(m.group(1), ns)  # noqa: S102 — isolated helper extract
    return ns


_HELPERS = _load_desktop_helpers()
_INSPECTOR_FULL_VIEW_RATIO = _HELPERS["_INSPECTOR_FULL_VIEW_RATIO"]
_inspector_viewport_is_full = _HELPERS["_inspector_viewport_is_full"]
_inspector_viewport_banner = _HELPERS["_inspector_viewport_banner"]


class InspectorViewportParityTests(unittest.TestCase):
    def test_full_view_ratio_matches_web(self) -> None:
        m = re.search(r"INSPECTOR_FULL_VIEW_RATIO = ([0-9.]+)", MIG_JS)
        self.assertIsNotNone(m)
        self.assertEqual(float(m.group(1)), _INSPECTOR_FULL_VIEW_RATIO)
        self.assertEqual(_INSPECTOR_FULL_VIEW_RATIO, 0.92)
        self.assertIn("return ratio >= 0.92", TIMELINE_VUE)

    def test_full_view_rules_match_in_source(self) -> None:
        self.assertIn(
            "if fit_mode or lo is None or hi is None:", STATS_PY)
        self.assertIn(
            "return (int(hi) - int(lo)) / span >= _INSPECTOR_FULL_VIEW_RATIO",
            STATS_PY)
        self.assertIn(
            "if (fitMode || lo == null || hi == null) return true", MIG_JS)
        self.assertIn(
            "return (Number(hi) - Number(lo)) / span >= INSPECTOR_FULL_VIEW_RATIO",
            MIG_JS)

    def test_badge_labels_match_web(self) -> None:
        for src in (STATS_PY, MIG_JS):
            self.assertIn("Full view", src)
            self.assertIn("Viewport view", src)
        self.assertIn('"Full view"', STATS_PY)
        self.assertIn('"Viewport view"', STATS_PY)
        self.assertIn("'Full view'", MIG_JS)
        self.assertIn("'Viewport view'", MIG_JS)
        self.assertIn("scopeBanner.badge", CI_VUE)

    def test_dialog_wires_the_banner_on_both_apps(self) -> None:
        self.assertIn('setObjectName("ciScopeBanner")', STATS_PY)
        self.assertIn("_refresh_scope_banner", STATS_PY)
        self.assertIn("_inspector_viewport_banner(", STATS_PY)
        self.assertIn("class=\"ci-scope-banner\"", CI_VUE)
        self.assertIn("ci-scope-viewport", CI_VUE)
        self.assertIn("ci-scope-full", CI_VUE)
        self.assertIn("inspectorViewportBanner(", CI_VUE)
        self.assertIn("export function inspectorViewportBanner", MIG_JS)
        self.assertIn("export function inspectorViewportIsFull", MIG_JS)
        self.assertNotIn("ci-scope-note", CI_VUE)
        self.assertNotIn("ciScopeNote", STATS_PY)
        self.assertNotIn("(viewport:", CI_VUE)

    def test_heatmap_banner_colors_match_distribution_chart(self) -> None:
        for token in ("#FF9800", "#1A1200", "#4E342E", "#FFF3E0"):
            self.assertIn(token, STATS_PY, token)
        self.assertIn("_apply_scope_banner(", STATS_PY)
        self.assertIn("def _set_scope_banner", STATS_PY)
        self.assertIn("badge.upper()", STATS_PY)
        self.assertIn("plot-scope-banner", PLOT_VUE)
        self.assertIn("plot-scope-cursor", PLOT_VUE)
        self.assertIn("plot-scope-full", PLOT_VUE)
        self.assertIn("border-left: 4px solid #ff9800", PLOT_VUE)
        self.assertIn("border-left: 4px solid #ff9800", CI_VUE)
        self.assertIn("background: #ff9800", PLOT_VUE)
        self.assertIn("background: #ff9800", CI_VUE)
        self.assertIn("color: #1a1200", PLOT_VUE)
        self.assertIn("color: #1a1200", CI_VUE)
        self.assertIn("color-mix(in srgb, #ff9800 18%, var(--panel-bg))", PLOT_VUE)
        self.assertIn("color-mix(in srgb, #ff9800 18%, var(--panel-bg))", CI_VUE)
        self.assertIn("text-transform: uppercase", PLOT_VUE)
        self.assertIn("text-transform: uppercase", CI_VUE)

    def test_full_vs_viewport_rules_match(self) -> None:
        self.assertTrue(_inspector_viewport_is_full(None, None, 0, 1000, False))
        self.assertTrue(_inspector_viewport_is_full(10, 20, 0, 1000, True))
        self.assertFalse(_inspector_viewport_is_full(100, 200, 0, 1000, False))
        self.assertTrue(_inspector_viewport_is_full(0, 1000, 0, 1000, False))
        self.assertTrue(
            _inspector_viewport_is_full(0, 921, 0, 1000, False))
        self.assertFalse(
            _inspector_viewport_is_full(0, 919, 0, 1000, False))

    def test_banner_text_uses_the_visible_range(self) -> None:
        tr = SimpleNamespace(time_min=0, time_max=1_000_000, time_scale="ns")
        scoped, badge, detail = _inspector_viewport_banner(tr, None, None, False)
        self.assertFalse(scoped)
        self.assertEqual(badge, "Full view")
        self.assertIn("…", detail)
        scoped, badge, detail = _inspector_viewport_banner(
            tr, 10_000, 20_000, False)
        self.assertTrue(scoped)
        self.assertEqual(badge, "Viewport view")
        self.assertIn("10000ns", detail)
        scoped, badge, _ = _inspector_viewport_banner(tr, 10_000, 20_000, True)
        self.assertFalse(scoped)
        self.assertEqual(badge, "Full view")


if __name__ == "__main__":
    unittest.main()
