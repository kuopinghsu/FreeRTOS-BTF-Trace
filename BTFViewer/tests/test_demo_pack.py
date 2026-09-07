"""Build the release ``.btfw`` demo package from the mirrored demo folder."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = BTF_ROOT / "scripts"
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from btf_viewer_pkg.workspace import KIND_DEMO, open_workspace  # noqa: E402
from demo_pack import (  # noqa: E402
    extract_btfw,
    filter_xml_languages,
    list_voice_packs,
    pack_demo_btfw,
    resolve_voice_selection,
    rewrite_xml_audio_ext,
)

DEMO_DIR = BTF_ROOT / "demos" / "demo_8cores"
DEMO_SCRIPT = DEMO_DIR / "demo" / "script.xml"
DEMO_VOICE = DEMO_DIR / "demo" / "voice"
DEMO_TRACE = DEMO_DIR / "trace" / "source.btf.gz"


class DemoPackTests(unittest.TestCase):
    def test_list_and_resolve_voice_packs(self) -> None:
        if not (DEMO_VOICE / "en").is_dir():
            self.skipTest("missing demo/voice/en")
        packs = list_voice_packs(DEMO_DIR, voice_root="demo/voice")
        ids = [p["id"] for p in packs]
        self.assertIn("en", ids)
        self.assertEqual(
            resolve_voice_selection(DEMO_DIR, voice_args=[], voice_root="demo/voice"),
            ["en", "zh-tw"],
        )
        self.assertEqual(
            resolve_voice_selection(DEMO_DIR, voice_args=["en"], voice_root="demo/voice"),
            ["en"],
        )
        all_ids = resolve_voice_selection(
            DEMO_DIR, voice_args=[], all_voices=True, voice_root="demo/voice")
        self.assertEqual(all_ids, ids)
        with self.assertRaises(FileNotFoundError):
            resolve_voice_selection(
                DEMO_DIR, voice_args=["no-such-lang"], voice_root="demo/voice")

    def test_filter_xml_keeps_selected_langs(self) -> None:
        src = DEMO_SCRIPT.read_text(encoding="utf-8")
        out = filter_xml_languages(src, ["en", "zh-tw"], default_lang="en")
        self.assertIn('<languages default="en">', out)
        self.assertIn('id="en"', out)
        self.assertIn('id="zh-tw"', out)
        self.assertNotIn('id="ja"', out)

    def test_rewrite_xml_audio_ext(self) -> None:
        src = '<audio file="${XML_DIR}/voice/01_title.mp3"/>'
        self.assertEqual(
            rewrite_xml_audio_ext(src),
            '<audio file="${XML_DIR}/voice/01_title.aac"/>',
        )

    def test_shipped_script_points_trace_at_the_package_member(self) -> None:
        xml = DEMO_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("<trace>${XML_DIR}/../trace/source.btf.gz</trace>", xml)

    def test_pack_demo_8cores_btfw(self) -> None:
        if not DEMO_TRACE.is_file():
            self.skipTest("missing trace/source.btf.gz")
        if not (DEMO_VOICE / "en").is_dir() or not (DEMO_VOICE / "zh-tw").is_dir():
            self.skipTest("missing demo/voice packs")
        with tempfile.TemporaryDirectory(prefix="btf_demo_pack_") as td:
            out = Path(td) / "demo_8cores.btfw"
            # Keep mp3 so the test does not require ffmpeg in every CI image.
            pack_demo_btfw(DEMO_DIR, out, ["en", "zh-tw"], to_aac=False)
            self.assertTrue(out.is_file())

            ws = open_workspace(str(out))
            self.assertEqual(ws["kind"], KIND_DEMO)
            self.assertTrue(ws["trace_bytes"].startswith(b"\x1f\x8b"))
            self.assertIn("trace/source.btf.gz", ws["manifest"]["contents"])
            files = ws["demo"]["files"]
            self.assertIn("script.xml", files)
            self.assertTrue(any(k.startswith("voice/en/") for k in files))
            self.assertTrue(any(k.startswith("voice/zh-tw/") for k in files))
            self.assertFalse(any(k.startswith("voice/ja/") for k in files))
            # narration text ships under attachments/, filtered to the langs
            self.assertTrue(any(k.startswith("text/en/") for k in ws["attachments"]))
            self.assertFalse(any(k.startswith("text/ja/") for k in ws["attachments"]))
            xml = files["script.xml"].decode("utf-8")
            self.assertNotIn('id="ja"', xml)
            self.assertIn(".mp3", xml)

            extracted = extract_btfw(out, Path(td) / "out")
            self.assertTrue((extracted / "demo" / "script.xml").is_file())
            self.assertTrue((extracted / "trace" / "source.btf").is_file())

    def test_pack_to_aac_when_ffmpeg_available(self) -> None:
        import shutil

        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg not on PATH")
        if not (DEMO_VOICE / "en" / "01_title.mp3").is_file():
            self.skipTest("missing sample mp3")
        with tempfile.TemporaryDirectory(prefix="btf_demo_aac_") as td:
            out = Path(td) / "demo.btfw"
            pack_demo_btfw(DEMO_DIR, out, ["en"], to_aac=True)
            ws = open_workspace(str(out))
            files = ws["demo"]["files"]
            self.assertTrue(any(k.endswith(".aac") for k in files))
            self.assertFalse(
                any(k.endswith(".mp3") for k in files if k.startswith("voice/")))
            xml = files["script.xml"].decode("utf-8")
            self.assertIn("voice/01_title.aac", xml)
            self.assertNotIn("voice/01_title.mp3", xml)
            self.assertIn("voice/en/voice.json", files)


if __name__ == "__main__":
    unittest.main()
