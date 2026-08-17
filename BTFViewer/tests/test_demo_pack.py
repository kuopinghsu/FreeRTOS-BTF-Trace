"""Pack demo folders into shareable .xtf (zip) archives."""
from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = BTF_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from demo_pack import (  # noqa: E402
    extract_xtf,
    filter_xml_languages,
    list_voice_packs,
    pack_demo_xtf,
    resolve_voice_selection,
    rewrite_xml_audio_ext,
)

DEMO_DIR = BTF_ROOT / "demos" / "demo_8cores"


class DemoPackTests(unittest.TestCase):
    def test_list_and_resolve_voice_packs(self) -> None:
        if not (DEMO_DIR / "voice" / "en").is_dir():
            self.skipTest("missing voice/en")
        packs = list_voice_packs(DEMO_DIR)
        ids = [p["id"] for p in packs]
        self.assertIn("en", ids)
        self.assertEqual(
            resolve_voice_selection(DEMO_DIR, voice_args=[]),
            ["en"],
        )
        self.assertEqual(
            resolve_voice_selection(DEMO_DIR, voice_args=["en"]),
            ["en"],
        )
        self.assertEqual(
            resolve_voice_selection(DEMO_DIR, voice_args=["en,zh-tw"]),
            ["en", "zh-tw"],
        )
        self.assertEqual(
            resolve_voice_selection(DEMO_DIR, voice_args=["en"], all_voices=False),
            ["en"],
        )
        all_ids = resolve_voice_selection(DEMO_DIR, voice_args=[], all_voices=True)
        self.assertEqual(all_ids, ids)
        with self.assertRaises(FileNotFoundError):
            resolve_voice_selection(DEMO_DIR, voice_args=["no-such-lang"])

    def test_filter_xml_keeps_selected_langs(self) -> None:
        src = (DEMO_DIR / "demo_8cores.xml").read_text(encoding="utf-8")
        out = filter_xml_languages(src, ["en", "zh-tw"], default_lang="en")
        self.assertIn('<languages default="en">', out)
        self.assertIn('id="en"', out)
        self.assertIn('id="zh-tw"', out)
        self.assertNotIn('id="ja"', out)
        self.assertIn("<language id=\"zh-tw\" label=\"中文\"/>", out)

    def test_rewrite_xml_audio_ext(self) -> None:
        src = '<audio file="${XML_DIR}/voice/01_title.mp3"/>'
        self.assertEqual(
            rewrite_xml_audio_ext(src),
            '<audio file="${XML_DIR}/voice/01_title.aac"/>',
        )
        full = (DEMO_DIR / "demo_8cores.xml").read_text(encoding="utf-8")
        out = rewrite_xml_audio_ext(full)
        self.assertIn('voice/01_title.aac"', out)
        self.assertNotIn('voice/01_title.mp3"', out)

    def test_pack_demo_8cores_xtf(self) -> None:
        if not (DEMO_DIR / "demo_8cores.btf.gz").is_file():
            self.skipTest("missing demo_8cores.btf.gz")
        if not (DEMO_DIR / "voice" / "en").is_dir():
            self.skipTest("missing voice/en")
        if not (DEMO_DIR / "voice" / "zh-tw").is_dir():
            self.skipTest("missing voice/zh-tw")
        with tempfile.TemporaryDirectory(prefix="btf_xtf_test_") as td:
            out = Path(td) / "demo_8cores.xtf"
            # Keep mp3 so the test does not require ffmpeg in every CI image.
            pack_demo_xtf(DEMO_DIR, out, ["en", "zh-tw"], to_aac=False)
            self.assertTrue(out.is_file())
            self.assertTrue(zipfile.is_zipfile(out))
            with zipfile.ZipFile(out) as zf:
                names = zf.namelist()
            self.assertIn("demo_8cores.xml", names)
            self.assertIn("demo_8cores.btf.gz", names)
            self.assertTrue(any(n.startswith("voice/en/") for n in names))
            self.assertTrue(any(n.startswith("voice/zh-tw/") for n in names))
            self.assertFalse(any(n.startswith("voice/ja/") for n in names))
            xml = zipfile.ZipFile(out).read("demo_8cores.xml").decode("utf-8")
            self.assertNotIn('id="ja"', xml)
            self.assertIn(".mp3", xml)

            extracted = extract_xtf(out, Path(td) / "out")
            self.assertTrue((extracted / "demo_8cores.xml").is_file())
            self.assertTrue((extracted / "demo_8cores.btf.gz").is_file())

    def test_pack_to_aac_when_ffmpeg_available(self) -> None:
        import shutil

        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg not on PATH")
        if not (DEMO_DIR / "voice" / "en" / "01_title.mp3").is_file():
            self.skipTest("missing sample mp3")
        with tempfile.TemporaryDirectory(prefix="btf_xtf_aac_") as td:
            out = Path(td) / "demo.xtf"
            # Pack only en to keep the test fast.
            pack_demo_xtf(DEMO_DIR, out, ["en"], to_aac=True)
            with zipfile.ZipFile(out) as zf:
                names = zf.namelist()
                xml = zf.read("demo_8cores.xml").decode("utf-8")
            self.assertTrue(any(n.endswith(".aac") for n in names))
            self.assertFalse(any(n.endswith(".mp3") for n in names if n.startswith("voice/")))
            self.assertIn("voice/01_title.aac", xml)
            self.assertNotIn("voice/01_title.mp3", xml)
            self.assertTrue(any(n == "voice/en/voice.json" for n in names))


if __name__ == "__main__":
    unittest.main()
