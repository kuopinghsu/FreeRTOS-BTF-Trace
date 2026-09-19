"""Colorblind-safe (Okabe-Ito) palette: exact values, switching, and web lockstep.

See BTFViewer/TODO.bak/COLORBLIND.md items 18-21.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg import config as cfg  # noqa: E402
from btf_viewer_pkg import timeline_util as tu  # noqa: E402
from btf_viewer_pkg.graphics_items import _sti_marker_apex_flipped  # noqa: E402
from btf_viewer_pkg.parser import StiEvent  # noqa: E402

EXPECTED_LIGHT = [
    "#0072B2", "#E69F00", "#009E73", "#CC79A7",
    "#56B4E9", "#D55E00", "#F0E442", "#000000",
]
EXPECTED_DARK = EXPECTED_LIGHT[:-1] + ["#FFFFFF"]


class ColorblindPaletteValueTests(unittest.TestCase):
    """Item 18 - exact palette values."""

    def test_light_palette_matches_okabe_ito(self) -> None:
        self.assertEqual([c.upper() for c in cfg._PALETTE_COLORBLIND], EXPECTED_LIGHT)

    def test_dark_palette_swaps_black_for_white(self) -> None:
        self.assertEqual([c.upper() for c in cfg._PALETTE_COLORBLIND_DARK], EXPECTED_DARK)
        self.assertEqual(cfg._PALETTE_COLORBLIND_DARK[:-1], cfg._PALETTE_COLORBLIND[:-1])


class ColorblindTaskCoreMappingTests(unittest.TestCase):
    """Item 19 - task/core colors switch with colorblindSafe, in both themes."""

    def tearDown(self) -> None:
        tu._set_colorblind_mode(False)
        cfg._RENDER_RUNTIME.is_dark = True
        tu._clear_render_color_caches()

    def test_normal_mode_does_not_use_okabe_ito(self) -> None:
        tu._set_colorblind_mode(False)
        color = tu._task_color("Task_Alpha[1]").name().upper()
        self.assertNotIn(color, [c.upper() for c in cfg._PALETTE_COLORBLIND])

    def test_colorblind_light_mode_uses_light_palette(self) -> None:
        tu._set_colorblind_mode(True)
        cfg._RENDER_RUNTIME.is_dark = False
        tu._clear_render_color_caches()
        color = tu._task_color("Task_Alpha[1]").name().upper()
        self.assertIn(color, [c.upper() for c in cfg._PALETTE_COLORBLIND])

    def test_colorblind_dark_mode_uses_dark_palette(self) -> None:
        tu._set_colorblind_mode(True)
        cfg._RENDER_RUNTIME.is_dark = True
        tu._clear_render_color_caches()
        color = tu._task_color("Task_Alpha[1]").name().upper()
        self.assertIn(color, [c.upper() for c in cfg._PALETTE_COLORBLIND_DARK])
        # Black never appears against the dark timeline background.
        self.assertNotIn("#000000", [color])

    def test_core_color_switches_with_colorblind_flag(self) -> None:
        tu._set_colorblind_mode(False)
        normal = cfg._core_color("Core_0").upper()
        self.assertNotIn(normal, [c.upper() for c in cfg._PALETTE_COLORBLIND])

        tu._set_colorblind_mode(True)
        cfg._RENDER_RUNTIME.is_dark = False
        colorblind = cfg._core_color("Core_0").upper()
        self.assertIn(colorblind, [c.upper() for c in cfg._PALETTE_COLORBLIND])


class StiMarkerShapeTests(unittest.TestCase):
    """Item 5/21 - take/give never rely on the red/green fill alone."""

    def _ev(self, note: str) -> StiEvent:
        return StiEvent(time=0, core="Core_0", target="mutex", event="trigger", note=note)

    def test_take_mutex_flips_apex(self) -> None:
        self.assertTrue(_sti_marker_apex_flipped(self._ev("take_mutex")))

    def test_give_mutex_keeps_default_apex(self) -> None:
        self.assertFalse(_sti_marker_apex_flipped(self._ev("give_mutex")))

    def test_other_notes_keep_default_apex(self) -> None:
        self.assertFalse(_sti_marker_apex_flipped(self._ev("create_mutex")))
        self.assertFalse(_sti_marker_apex_flipped(self._ev("trigger")))
        self.assertFalse(_sti_marker_apex_flipped(None))


class ColorblindWebLockstepTests(unittest.TestCase):
    """Item 20 - Desktop and web must never diverge on palette values."""

    def test_web_palette_matches_desktop(self) -> None:
        colors_js = (BTF_ROOT / "web/src/utils/colors.js").read_text(encoding="utf-8")
        m = re.search(
            r"const PALETTE_COLORBLIND\s*=\s*\[(.*?)\]", colors_js, re.S)
        self.assertIsNotNone(m, "PALETTE_COLORBLIND not found in colors.js")
        web_light = [c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}", m.group(1))]
        self.assertEqual(web_light, [c.upper() for c in cfg._PALETTE_COLORBLIND])

    def test_web_dark_palette_swaps_black_for_white(self) -> None:
        colors_js = (BTF_ROOT / "web/src/utils/colors.js").read_text(encoding="utf-8")
        self.assertRegex(
            colors_js,
            r"PALETTE_COLORBLIND_DARK\s*=\s*\[\.\.\.PALETTE_COLORBLIND\.slice\(0,\s*-1\),\s*'#FFFFFF'\]")

    def test_web_sti_shapes_match_desktop_take_give_convention(self) -> None:
        colors_js = (BTF_ROOT / "web/src/utils/colors.js").read_text(encoding="utf-8")
        self.assertIn("export function stiMarkerShape(note)", colors_js)
        self.assertIn("if (note === 'take_mutex') return 'take'", colors_js)
        self.assertIn("if (note === 'give_mutex') return 'give'", colors_js)


class ColorblindSettingLabelTests(unittest.TestCase):
    """Item 1/2 - the setting label/tooltip describes task/core scope only."""

    def test_desktop_label_and_tooltip(self) -> None:
        stats_py = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
        self.assertIn('_switch("Colorblind-safe palette (Okabe-Ito)")', stats_py)
        self.assertNotIn("Colorblind-safe colors (Okabe-Ito palette)", stats_py)

    def test_web_label_and_tooltip(self) -> None:
        dlg_vue = (BTF_ROOT / "web/src/components/SettingsDialog.vue").read_text(encoding="utf-8")
        self.assertIn("Colorblind-safe palette (Okabe-Ito)", dlg_vue)
        self.assertNotIn("Colorblind-safe colors (Okabe-Ito palette)", dlg_vue)
        # A tooltip must exist for the checkbox (previously missing on web).
        self.assertIn(
            "Important status information also uses text, symbols, or labels", dlg_vue)


if __name__ == "__main__":
    unittest.main()
