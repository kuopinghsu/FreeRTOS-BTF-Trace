"""Demo narration language: path candidates and XML/meta parsing."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg import demo_inapp as dr  # noqa: E402

DEMO_XML = BTF_ROOT / "demos" / "demo_8cores" / "demo_8cores.xml"


class DemoVoiceLangTests(unittest.TestCase):
    def test_normalize_and_pick(self) -> None:
        self.assertEqual(dr.normalize_voice_lang("en-US"), "en")
        self.assertEqual(dr.normalize_voice_lang("zh_TW"), "zh-tw")
        self.assertEqual(dr.normalize_voice_lang("zh-Hant"), "zh-tw")
        self.assertEqual(dr.normalize_voice_lang("zh-CN"), "zh")
        ids = ["en", "zh-tw"]
        self.assertEqual(dr.pick_voice_lang("zh-TW", ids, "en"), "zh-tw")
        self.assertEqual(dr.pick_voice_lang("zh-CN", ids, "en"), "zh-tw")
        self.assertEqual(dr.pick_voice_lang("ja", ids, "en"), "en")

    def test_voice_path_candidates_order(self) -> None:
        cands = [p.as_posix() for p in dr.voice_path_candidates(
            Path("voice/01_title.mp3"), "zh-TW", "en"
        )]
        self.assertEqual(
            cands,
            [
                "voice/zh-tw/01_title.mp3",
                "voice/01_title.mp3",
                "voice/en/01_title.mp3",
            ],
        )

    def test_parse_languages_from_shipped_xml(self) -> None:
        root = dr.load_demo_xml(DEMO_XML)
        langs = dr.parse_languages(root)
        self.assertEqual(langs["defaultId"], "en")
        self.assertEqual([x["id"] for x in langs["list"]], ["en", "zh-tw"])
        vars_ = dr.build_variables(root, DEMO_XML, {})
        self.assertNotIn("languages", vars_)

    def test_resolve_prefers_language_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_dir = Path(tmp)
            voice = xml_dir / "voice"
            zh = voice / "zh-tw"
            zh.mkdir(parents=True)
            fallback = voice / "01_title.mp3"
            localized = zh / "01_title.mp3"
            fallback.write_bytes(b"en")
            localized.write_bytes(b"zh")
            got = dr.resolve_media_path(
                str(fallback),
                {
                    "XML_DIR": str(xml_dir),
                    "CWD": str(xml_dir),
                    "BTF": str(xml_dir),
                    "REPO": str(xml_dir),
                    "LANG": "zh-tw",
                    "VOICE_LANG": "zh-tw",
                    "VOICE_DEFAULT": "en",
                },
            )
            self.assertEqual(got.resolve(), localized.resolve())
            got_en = dr.resolve_media_path(
                str(fallback),
                {
                    "XML_DIR": str(xml_dir),
                    "CWD": str(xml_dir),
                    "BTF": str(xml_dir),
                    "REPO": str(xml_dir),
                    "LANG": "en",
                    "VOICE_LANG": "en",
                    "VOICE_DEFAULT": "en",
                },
            )
            self.assertEqual(got_en.resolve(), fallback.resolve())

    def test_discover_and_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_dir = Path(tmp)
            (xml_dir / "voice").mkdir()
            (xml_dir / "voice" / "01.mp3").write_bytes(b"en")
            (xml_dir / "voice" / "ja").mkdir()
            (xml_dir / "voice" / "ja" / "01.mp3").write_bytes(b"ja")
            found = dr.discover_voice_langs(xml_dir)
            self.assertIn("en", found)
            self.assertIn("ja", found)
            merged = dr.merge_voice_langs(
                {"defaultId": "en", "list": [{"id": "en", "label": "English"}]},
                found,
            )
            self.assertEqual([x["id"] for x in merged["list"]], ["en", "ja"])

    def test_preferred_lang_ignores_process_locale(self) -> None:
        locale_env = {
            k: v for k, v in os.environ.items()
            if k not in ("LANG", "LC_ALL", "LC_MESSAGES", "BTFVIEWER_DEMO_LANG")
        }
        with mock.patch.dict(os.environ, {
            **locale_env,
            "LANG": "zh_TW.UTF-8",
            "LC_ALL": "zh_TW.UTF-8",
            "LC_MESSAGES": "zh_TW.UTF-8",
        }, clear=True):
            self.assertEqual(dr.preferred_voice_lang({}), "")
            self.assertEqual(
                dr.pick_voice_lang(
                    dr.preferred_voice_lang({}),
                    ["en", "zh-tw", "ja"],
                    "en",
                ),
                "en",
            )
            self.assertEqual(dr.preferred_voice_lang({"VOICE_LANG": "ja"}), "ja")
        with mock.patch.dict(os.environ, {"BTFVIEWER_DEMO_LANG": "zh-tw"}):
            self.assertEqual(dr.preferred_voice_lang({}), "zh-tw")


if __name__ == "__main__":
    unittest.main()
