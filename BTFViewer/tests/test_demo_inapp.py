"""In-app desktop demo: parse, skip policy, pack discovery (Web lockstep)."""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.demo_inapp import (  # noqa: E402
    SKIP_TAGS,
    build_variables,
    discover_demo_pack,
    expand_vars,
    load_demo_xml,
    parse_defaults,
    parse_languages,
    parse_steps,
    parse_targets,
    should_skip_step,
    truthy,
    voice_path_candidates,
)
from btf_viewer_pkg.parser import _BTF_OPEN_FILTER  # noqa: E402

DEMO_XML = BTF_ROOT / "demos" / "demo_8cores" / "demo_8cores.xml"
WEB_RUNNER = BTF_ROOT / "web" / "src" / "utils" / "demoRunner.js"
WEB_APP = BTF_ROOT / "web" / "src" / "App.vue"
DESKTOP_INAPP = BTF_ROOT / "btf_viewer_pkg" / "demo_inapp.py"
DESKTOP_MW = BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py"

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<demo name="sample" version="1">
  <meta>
    <title>Sample demo</title>
    <trace>${XML_DIR}/demo.btf.gz</trace>
    <languages default="en">
      <language id="en" label="English"/>
      <language id="zh-tw" label="中文"/>
    </languages>
  </meta>
  <defaults after_voice="1.5" pause="0.8" ai_wait="35" audio_block="false"/>
  <targets>
    <point name="timeline" x="0.42" y="0.42"/>
  </targets>
  <macros>
    <macro name="fit">
      <hotkey keys="mod+0"/>
    </macro>
  </macros>
  <steps>
    <step id="1" title="Open" tags="intro">
      <audio file="${XML_DIR}/voice/01.mp3"/>
      <macro ref="fit"/>
      <view_mode mode="core"/>
      <move target="timeline" duration="0"/>
    </step>
    <step id="2" title="AI" tags="ai" optional="true">
      <confirm prompt="Click template"/>
      <wait ai="true" seconds="35"/>
    </step>
  </steps>
</demo>
"""


class DemoInappParseTests(unittest.TestCase):
    def test_expand_nested_vars(self) -> None:
        vars_ = {"XML_DIR": "/pack", "voice": "${XML_DIR}/voice"}
        self.assertEqual(expand_vars("${voice}/01.mp3", vars_), "/pack/voice/01.mp3")

    def test_parse_sample_xml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml = Path(tmp) / "demo.xml"
            xml.write_text(SAMPLE, encoding="utf-8")
            (Path(tmp) / "demo.btf.gz").write_bytes(b"\x1f\x8b")
            root = load_demo_xml(xml)
            vars_ = build_variables(root, xml)
            self.assertNotIn("languages", vars_)
            self.assertEqual(vars_["trace"], f"{tmp}/demo.btf.gz")
            langs = parse_languages(root)
            self.assertEqual(langs["defaultId"], "en")
            self.assertEqual([x["id"] for x in langs["list"]], ["en", "zh-tw"])
            self.assertEqual(parse_defaults(root)["pause"], 0.8)
            self.assertFalse(bool(parse_defaults(root)["audio_block"]))
            self.assertEqual(parse_targets(root)["timeline"], (0.42, 0.42))
            steps = parse_steps(root)
            self.assertEqual(len(steps), 2)
            self.assertTrue(steps[1]["optional"])

    def test_should_skip_optional_and_tags(self) -> None:
        ai = {"optional": True, "tags": {"ai"}}
        self.assertTrue(should_skip_step(ai, skip_optional=True))
        self.assertTrue(should_skip_step(ai, skip_tags=["ai"]))
        self.assertFalse(should_skip_step(ai))

    def test_skip_tags_match_web(self) -> None:
        js = WEB_RUNNER.read_text(encoding="utf-8")
        m = re.search(r"const SKIP_TAGS = new Set\(\[([^\]]+)\]\)", js)
        self.assertIsNotNone(m)
        web = {
            t.strip().strip("'\"")
            for t in m.group(1).split(",")
            if t.strip()
        }
        self.assertEqual(web, set(SKIP_TAGS))

    def test_voice_path_candidates_strings(self) -> None:
        self.assertEqual(
            voice_path_candidates("voice/01_title.mp3", "zh-TW", "en"),
            [
                "voice/zh-tw/01_title.mp3",
                "voice/01_title.mp3",
                "voice/en/01_title.mp3",
            ],
        )

    def test_discover_demo_pack_xml_and_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            xml = folder / "demo_8cores.xml"
            xml.write_text(SAMPLE, encoding="utf-8")
            btf = folder / "demo.btf.gz"
            btf.write_bytes(b"\x1f\x8b")
            got = discover_demo_pack(str(xml))
            self.assertIsNotNone(got)
            self.assertEqual(Path(got[0]), xml)
            self.assertEqual(Path(got[1]), btf)
            got_dir = discover_demo_pack(str(folder))
            self.assertEqual(got_dir, got)
            self.assertIsNone(discover_demo_pack(str(btf)))

    def test_open_filter_includes_xml(self) -> None:
        primary = _BTF_OPEN_FILTER.split(";;")[0]
        self.assertIn("*.xtf", primary)
        self.assertIn("*.xml", primary)

    def test_truthy_matches_web(self) -> None:
        self.assertFalse(truthy("false"))
        self.assertTrue(truthy("true"))
        self.assertTrue(truthy(None, True))


class DemoInappSourceParityTests(unittest.TestCase):
    def test_banner_copy_matches_web(self) -> None:
        app = WEB_APP.read_text(encoding="utf-8")
        py = DESKTOP_INAPP.read_text(encoding="utf-8")
        mw = DESKTOP_MW.read_text(encoding="utf-8")
        self.assertIn("Esc twice to stop", app)
        self.assertIn("Esc twice to stop", py)
        self.assertIn("Paused · Esc twice to stop", app)
        self.assertIn("Paused · Esc twice to stop", py)
        self.assertIn("demo-status-banner", app)
        self.assertIn("demo_status_banner", py)
        self.assertIn("_start_pending_demo", mw)
        self.assertIn("discover_demo_pack", mw)

    def test_runner_maps_same_api_tags(self) -> None:
        py = DESKTOP_INAPP.read_text(encoding="utf-8")
        js = WEB_RUNNER.read_text(encoding="utf-8")
        for needle in (
            "analysis",
            "find",
            "settings",
            "tick_dist",
            "view_mode",
            "cpu_load",
            "clear_bookmarks",
            "clear_annotations",
            "zoom_1to1",
            "stats_section",
            "jump_wcet",
        ):
            self.assertIn(f'tag == "{needle}"' if False else needle, py)
            self.assertIn(needle, js)

    def test_hotkey_and_type_are_skipped(self) -> None:
        py = DESKTOP_INAPP.read_text(encoding="utf-8")
        js = WEB_RUNNER.read_text(encoding="utf-8")
        self.assertIn('"hotkey"', py)
        self.assertIn("'hotkey'", js)
        self.assertIn('"type"', py)
        self.assertIn("keys in (\"esc\", \"escape\")", py)
        self.assertIn("keys === 'esc'", js)

    def test_xtf_open_starts_tour_on_desktop(self) -> None:
        mw = DESKTOP_MW.read_text(encoding="utf-8")
        self.assertIn("self._pending_demo = {\"xml\": xml}", mw)
        self.assertIn("_start_pending_demo", mw)
        self.assertIn("is_xtf_open_path", mw)


class DemoInappXtfTests(unittest.TestCase):
    def test_xtf_extract_still_returns_xml(self) -> None:
        from btf_viewer_pkg.parser import extract_xtf_pack
        with tempfile.TemporaryDirectory(prefix="btf_xtf_") as td:
            xtf = Path(td) / "demo.xtf"
            with zipfile.ZipFile(xtf, "w") as zf:
                zf.writestr("demo_8cores.xml", SAMPLE.encode("utf-8"))
                zf.writestr("demo_8cores.btf.gz", b"\x1f\x8b")
            xml, btf = extract_xtf_pack(str(xtf))
            self.assertTrue(os.path.isfile(xml))
            self.assertTrue(xml.endswith("demo_8cores.xml"))
            pack = discover_demo_pack(os.path.dirname(xml))
            self.assertIsNotNone(pack)


if __name__ == "__main__":
    unittest.main()
