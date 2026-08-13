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

    def test_web_toolbar_uses_shared_file_icons(self) -> None:
        tb = (BTF_ROOT / "web" / "src" / "components" / "Toolbar.vue").read_text(
            encoding="utf-8")
        for token in (
            "IC.open", "IC.shot", "IC.saveSvg", "IC.perfetto", "IC.exportSlice",
            "IC.oneToOne", "IC.help", "IC.settings",
        ):
            self.assertIn(token, tb)


if __name__ == "__main__":
    unittest.main()
