"""A ``.btfw`` demo package: pack it, then open it through the unified reader."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))
SCRIPTS = BTF_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.parser import _BTF_OPEN_FILTER  # noqa: E402
from btf_viewer_pkg.workspace import (  # noqa: E402
    KIND_DEMO,
    open_workspace,
    save_workspace,
)

SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<demo name="t" version="1">
  <meta>
    <title>t</title>
    <cwd>.</cwd>
    <trace>${XML_DIR}/../trace/source.btf.gz</trace>
    <languages default="en">
      <language id="en" label="English"/>
      <language id="zh-tw" label="中文"/>
    </languages>
  </meta>
  <step><voice/><audio file="${XML_DIR}/voice/01_title.mp3"/></step>
</demo>
"""

MANIFEST_JSON = """{
  "schema": "btf-viewer-workspace/1",
  "kind": "demo",
  "trace": {"name": "source.btf.gz", "embedded": true},
  "demo": {"script": "demo/script.xml", "languages": ["en", "zh-tw"], "default_language": "en"}
}
"""


def _make_demo_dir(root: Path) -> Path:
    """A demo folder in the package-mirror layout (a valid unpacked .btfw)."""
    d = root / "demo_8cores"
    (d / "demo" / "voice" / "en").mkdir(parents=True)
    (d / "demo" / "voice" / "zh-tw").mkdir(parents=True)
    (d / "trace").mkdir(parents=True)
    (d / "investigation").mkdir(parents=True)
    (d / "attachments" / "text" / "en").mkdir(parents=True)
    (d / "attachments" / "text" / "zh-tw").mkdir(parents=True)
    (d / "manifest.json").write_text(MANIFEST_JSON, encoding="utf-8")
    (d / "demo" / "script.xml").write_text(SAMPLE_XML, encoding="utf-8")
    (d / "trace" / "source.btf.gz").write_bytes(b"\x1f\x8b\x08\x00demo-trace-bytes")
    for lang in ("en", "zh-tw"):
        (d / "demo" / "voice" / lang / "01_title.mp3").write_bytes(b"ID3clip")
        (d / "demo" / "voice" / lang / "voice.json").write_text("{}", encoding="utf-8")
        (d / "attachments" / "text" / lang / "01_title.txt").write_text("hi", encoding="utf-8")
    (d / "investigation" / "ai_case.json").write_text(
        '{"v": 1, "messages": [{"role": "user", "content": "why?"}]}',
        encoding="utf-8",
    )
    return d


class DemoPackageTests(unittest.TestCase):
    def test_open_filter_drops_xtf(self) -> None:
        self.assertNotIn(".xtf", _BTF_OPEN_FILTER)
        self.assertIn("*.btfw", _BTF_OPEN_FILTER.split(";;")[0])

    def test_pack_and_open_demo_btfw(self) -> None:
        from demo_pack import pack_demo_btfw

        with tempfile.TemporaryDirectory(prefix="btf_demo_pkg_") as td:
            root = Path(td)
            demo_dir = _make_demo_dir(root)
            out = root / "demo_8cores.btfw"
            pack_demo_btfw(demo_dir, out, ["en", "zh-tw"], to_aac=False)
            self.assertTrue(out.is_file())

            ws = open_workspace(str(out))
            self.assertEqual(ws["kind"], KIND_DEMO)
            self.assertEqual(ws["manifest"]["kind"], KIND_DEMO)
            self.assertTrue(ws["trace_bytes"].startswith(b"\x1f\x8b"))

            demo = ws["demo"]
            self.assertIsNotNone(demo)
            self.assertEqual(demo["script_name"], "script.xml")
            self.assertIn(b"<demo", demo["script"])
            self.assertIn("voice/en/01_title.mp3", demo["files"])
            self.assertIn("voice/zh-tw/voice.json", demo["files"])
            self.assertEqual(
                sorted(ws["manifest"]["demo"]["languages"]), ["en", "zh-tw"])

            self.assertEqual(
                ws["ai_case"]["messages"][0]["content"], "why?")

            # trace keeps its real extension; narration text ships in attachments/.
            self.assertIn("trace/source.btf.gz", ws["manifest"]["contents"])
            self.assertIn("text/en/01_title.txt", ws["attachments"])
            self.assertIn(
                b"<trace>${XML_DIR}/../trace/source.btf.gz</trace>", demo["script"])

    def test_zip_of_source_folder_is_a_valid_package(self) -> None:
        import os
        import zipfile
        from btf_viewer_pkg.workspace import read_workspace_dir

        with tempfile.TemporaryDirectory(prefix="btf_demo_zip_") as td:
            root = Path(td)
            demo_dir = _make_demo_dir(root)
            zpath = root / "raw.btfw"
            with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
                for dp, _dn, fs in os.walk(demo_dir):
                    for f in fs:
                        p = os.path.join(dp, f)
                        zf.write(p, os.path.relpath(p, demo_dir))
            for ws in (open_workspace(str(zpath)), read_workspace_dir(str(demo_dir))):
                self.assertEqual(ws["kind"], "demo")
                self.assertTrue(ws["trace_bytes"].startswith(b"\x1f\x8b"))
                self.assertIn("script.xml", ws["demo"]["files"])
                self.assertIn("text/en/01_title.txt", ws["attachments"])

    def test_save_workspace_demo_round_trip_minimal(self) -> None:
        with tempfile.TemporaryDirectory(prefix="btf_demo_min_") as td:
            out = Path(td) / "d.btfw"
            save_workspace(
                str(out),
                kind=KIND_DEMO,
                trace_bytes=b"\x1f\x8bmini",
                embed_trace=True,
                demo_xml=b"<demo/>",
                demo_voices={"en": {"01.aac": b"a", "voice.json": b"{}"}},
                demo_default_language="en",
                ai_case={"v": 1, "messages": []},
            )
            ws = open_workspace(str(out))
            self.assertEqual(ws["kind"], "demo")
            self.assertEqual(ws["demo"]["files"]["voice/en/01.aac"], b"a")
            self.assertEqual(ws["ai_case"], {"v": 1, "messages": []})


if __name__ == "__main__":
    unittest.main()
