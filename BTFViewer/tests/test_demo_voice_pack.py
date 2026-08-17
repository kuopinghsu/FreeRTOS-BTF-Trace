"""Uniform demo voice packs: install / export / normalize."""
from __future__ import annotations

import importlib.util
import json
import os
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

from btf_viewer_pkg import demo_inapp as dr  # noqa: E402

DEMO_DIR = BTF_ROOT / "demos" / "demo_8cores"


def _load_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


dv = _load_mod("demo_voice", BTF_ROOT / "scripts" / "demo_voice.py")


class DemoVoicePackTests(unittest.TestCase):
    def test_shipped_demo_uses_lang_folders(self) -> None:
        self.assertTrue((DEMO_DIR / "text" / "en" / "01_title.txt").is_file())
        self.assertTrue((DEMO_DIR / "text" / "en" / "voice.json").is_file())
        self.assertTrue((DEMO_DIR / "voice" / "en" / "01_title.mp3").is_file())
        self.assertTrue((DEMO_DIR / "voice" / "en" / "voice.json").is_file())
        recs = {r["id"]: r for r in dv.iter_lang_records(DEMO_DIR)}
        self.assertIn("en", recs)
        self.assertIn("zh-tw", recs)
        self.assertNotIn("ja", recs)
        self.assertGreaterEqual(len(recs["en"]["scripts"]), 20)
        self.assertEqual(len(recs["zh-tw"]["scripts"]), len(recs["en"]["scripts"]))
        self.assertGreaterEqual(len(recs["en"]["clips"]), 20)
        data = json.loads((DEMO_DIR / "voice" / "en" / "voice.json").read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "btf-demo-voice")
        self.assertEqual(data["id"], "en")

    def test_runner_resolves_voice_en_without_flat_files(self) -> None:
        clip = DEMO_DIR / "voice" / "en" / "01_title.mp3"
        got = dr.resolve_media_path(
            str(DEMO_DIR / "voice" / "01_title.mp3"),
            {
                "XML_DIR": str(DEMO_DIR),
                "CWD": str(DEMO_DIR),
                "BTF": str(DEMO_DIR),
                "REPO": str(DEMO_DIR),
                "LANG": "en",
                "VOICE_LANG": "en",
                "VOICE_DEFAULT": "en",
            },
        )
        self.assertEqual(got.resolve(), clip.resolve())

    def test_normalize_moves_flat_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp)
            (demo / "text").mkdir()
            (demo / "voice").mkdir()
            (demo / "text" / "01_title.txt").write_text("hello", encoding="utf-8")
            (demo / "voice" / "01_title.mp3").write_bytes(b"en")
            stats = dv.normalize_demo(demo, "en")
            self.assertEqual(stats["moved"], 2)
            self.assertTrue((demo / "text" / "en" / "01_title.txt").is_file())
            self.assertTrue((demo / "voice" / "en" / "01_title.mp3").is_file())
            self.assertFalse((demo / "text" / "01_title.txt").exists())
            self.assertFalse((demo / "voice" / "01_title.mp3").exists())

    def test_export_install_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            dst = Path(tmp) / "dst"
            zip_path = Path(tmp) / "zh-tw.zip"
            (src / "text" / "zh-tw").mkdir(parents=True)
            (src / "voice" / "zh-tw").mkdir(parents=True)
            (src / "text" / "zh-tw" / "01_title.txt").write_text("你好", encoding="utf-8")
            (src / "voice" / "zh-tw" / "01_title.mp3").write_bytes(b"zh")
            dv.write_manifest(src / "voice" / "zh-tw" / "voice.json", "zh-tw", "中文")
            out = dv.export_pack(src, "zh-tw", zip_path)
            self.assertTrue(out.is_file())
            with zipfile.ZipFile(out) as zf:
                names = set(zf.namelist())
            self.assertEqual(
                names,
                {"voice.json", "text/01_title.txt", "voice/01_title.mp3"},
            )
            (dst / "text" / "en").mkdir(parents=True)
            info = dv.install_pack(dst, out)
            self.assertEqual(info["lang"], "zh-tw")
            self.assertEqual(info["copied"]["text"], 1)
            self.assertEqual(info["copied"]["voice"], 1)
            self.assertEqual(
                (dst / "text" / "zh-tw" / "01_title.txt").read_text(encoding="utf-8"),
                "你好",
            )
            self.assertEqual((dst / "voice" / "zh-tw" / "01_title.mp3").read_bytes(), b"zh")
            man = json.loads((dst / "voice" / "zh-tw" / "voice.json").read_text(encoding="utf-8"))
            self.assertEqual(man["id"], "zh-tw")
            self.assertEqual(man["label"], "中文")

    def test_install_loose_files_with_lang_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "demo"
            pack = Path(tmp) / "loose"
            demo.mkdir()
            pack.mkdir()
            (pack / "01_title.txt").write_text("Hallo", encoding="utf-8")
            (pack / "01_title.mp3").write_bytes(b"de")
            info = dv.install_pack(demo, pack, lang="de", label="Deutsch")
            self.assertEqual(info["lang"], "de")
            self.assertTrue((demo / "text" / "de" / "01_title.txt").is_file())
            self.assertTrue((demo / "voice" / "de" / "01_title.mp3").is_file())

    def test_sync_xml_rewrites_languages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp)
            (demo / "text" / "en").mkdir(parents=True)
            (demo / "voice" / "ja").mkdir(parents=True)
            (demo / "text" / "en" / "01.txt").write_text("hi", encoding="utf-8")
            (demo / "voice" / "ja" / "01.mp3").write_bytes(b"ja")
            xml = demo / "demo.xml"
            xml.write_text(
                '<?xml version="1.0"?>\n<demo>\n  <meta>\n    <title>x</title>\n  </meta>\n</demo>\n',
                encoding="utf-8",
            )
            dv.sync_xml_languages(demo, "en")
            body = xml.read_text(encoding="utf-8")
            self.assertIn('<languages default="en">', body)
            self.assertIn('<language id="en" label="English"/>', body)
            self.assertIn('<language id="ja" label="日本語"/>', body)

    def test_rejects_zip_slip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(tmp) / "demo"
            demo.mkdir()
            zpath = Path(tmp) / "bad.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr("../escape.mp3", b"nope")
            with self.assertRaises(ValueError):
                dv.install_pack(demo, zpath, lang="en")


if __name__ == "__main__":
    unittest.main()
