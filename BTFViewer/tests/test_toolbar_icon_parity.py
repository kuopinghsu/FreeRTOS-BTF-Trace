"""Desktop ↔ web toolbar icon paths and file-action labels."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]


def _config_icon_paths() -> dict:
    src = (BTF_ROOT / "btf_viewer_pkg" / "config.py").read_text(encoding="utf-8")
    a = src.index("# Icon path data")
    b = src.index("# App icon")
    ns: dict = {}
    exec(src[a:b], ns)  # noqa: S102 — isolated icon-constant block
    return {k[4:]: v for k, v in ns.items() if k.startswith("_IC_") and isinstance(v, str)}


def _js_icon_paths() -> dict:
    src = (BTF_ROOT / "web" / "src" / "utils" / "toolbarIcons.js").read_text(encoding="utf-8")
    aliases = {"ONE_TO_ONE": "1TO1"}
    out = {}
    for m in re.finditer(r"^\s*(\w+):\s*(\".*?\")\s*,?\s*$", src, re.M):
        key = re.sub(r"([A-Z])", r"_\1", m.group(1)).upper()
        out[aliases.get(key, key)] = json.loads(m.group(2))
    return out


class ToolbarIconParityTests(unittest.TestCase):
    def test_shared_icon_paths_match_config(self) -> None:
        py = _config_icon_paths()
        js = _js_icon_paths()
        shared = sorted(set(py) & set(js) - {"DEMO"})
        self.assertTrue(shared)
        for name in shared:
            self.assertEqual(js[name], py[name], name)

    def test_desktop_file_cluster_uses_snapshot_perfetto_slice(self) -> None:
        mw = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text(encoding="utf-8")
        self.assertIn("_IC_SHOT", mw)
        self.assertIn("_IC_PERFETTO", mw)
        self.assertIn("_IC_EXPORT_SLICE", mw)
        self.assertIn('Snapshot &Editor', mw)
        self.assertIn('Open snapshot editor  (Ctrl+S)', mw)
        self.assertNotIn('_ia("Save PNG"', mw)
        self.assertIn("toolbar_right_spacer", mw)
        self.assertIn("_IC_HELP", mw)
        self.assertIn("_on_keyboard_shortcuts", mw)

    def test_limit_badge_follows_settings(self) -> None:
        tb = (BTF_ROOT / "web" / "src" / "components" / "Toolbar.vue").read_text(
            encoding="utf-8")
        mw = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text(
            encoding="utf-8")
        self.assertIn('class="tb-limit-badge"', tb)
        self.assertRegex(tb, r">\s*C1–Cn\s*<")
        self.assertNotIn("limitOn ? 'On'", tb)
        self.assertLess(tb.find('tb-limit-badge'), tb.find('loadDemo'))
        self.assertLess(tb.find('tb-limit-badge'), tb.find('showSettings'))
        self.assertIn('--badge-scope-fg', tb)
        self.assertIn('--badge-detail-fg', tb)
        start = mw.index("def _build_toolbar")
        chunk = mw[start:mw.index("def _update_trace_quality_banner")]
        self.assertIn("tbLimitBadge", chunk)
        self.assertLess(chunk.find("tbLimitBadge"), chunk.find('_ia("Settings"'))
        self.assertLess(chunk.find('_ia("Settings"'), chunk.find('_ia("Help"'))
        self.assertNotIn("setFlat", chunk)
        self.assertIn('setText("C1–Cn")', mw)
        self.assertNotIn("C1–Cn On", mw)
        self.assertNotIn("C1–Cn Off", mw)
        self.assertIn('stats_meta_chip_colors("scope"', mw)
        self.assertIn('stats_category_badge_colors("DETAIL"', mw)
        self.assertIn("_ui_font_stylesheet_size", mw[mw.index("def _update_limit_badge"):mw.index("def _on_limit_badge_clicked")])
        self.assertNotIn("min-width:64px", mw)
        app = (BTF_ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")
        self.assertIn(':limit-on="limitOn"', app)
        self.assertIn('@toggle-limit="onToggleLimit"', app)
        self.assertIn("--badge-scope-fg: #9EC5E8", app)
        self.assertIn("--badge-scope-fg: #1A5276", app)
        from btf_viewer_pkg.config import (
            stats_category_badge_colors,
            stats_meta_chip_colors,
        )
        fg, bg, border = stats_meta_chip_colors("scope", dark=True)
        self.assertIn(f"--badge-scope-fg: {fg}", app)
        self.assertIn(f"--badge-scope-bg: {bg}", app)
        self.assertIn(f"--badge-scope-border: {border}", app)
        fg, bg, border = stats_meta_chip_colors("scope", dark=False)
        self.assertIn(f"--badge-scope-fg: {fg}", app)
        det_bg, det_fg, det_border = stats_category_badge_colors("DETAIL", dark=True)
        self.assertIn(f"--badge-detail-fg: {det_fg}", app)
        self.assertIn(f"--badge-detail-bg: {det_bg}", app)

    def test_web_toolbar_uses_shared_file_icons(self) -> None:
        tb = (BTF_ROOT / "web" / "src" / "components" / "Toolbar.vue").read_text(
            encoding="utf-8")
        mw = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text(
            encoding="utf-8")
        for token in (
            "IC.open", "IC.shot", "IC.saveSvg", "IC.perfetto", "IC.exportSlice",
            "IC.oneToOne", "IC.help", "IC.settings", "IC.analysis", "IC.compare",
        ):
            self.assertIn(token, tb)
        self.assertLess(tb.find("IC.analysis"), tb.find("IC.compare"))
        self.assertLess(mw.find('_tb_analysis_btn'), mw.find('_tb_compare_btn'))
        self.assertIn("_IC_COMPARE", mw)


if __name__ == "__main__":
    unittest.main()
