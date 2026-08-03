"""Compressed BTF open helpers (gzip / bz2 / zip)."""
from __future__ import annotations

import gzip
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.parser import (  # noqa: E402
    _expand_open_paths,
    _list_zip_btf_members,
    _normalize_open_path,
    _open_btf_text,
    _pick_zip_btf_member,
    _sniff_compression,
    _split_zip_member_path,
    _trace_display_name,
    is_btf_open_path,
)

_MINI_BTF = """\
#version 1.0.0
#timeScale us
100,Core_0,0,T,[0/1]A,0,resume
200,Core_0,0,T,[0/1]A,0,preempt
"""

_MINI_BTF_B = """\
#version 1.0.0
#timeScale us
100,Core_0,0,T,[0/2]B,0,resume
150,Core_0,0,T,[0/2]B,0,preempt
"""


class BtfOpenPathTests(unittest.TestCase):
    def test_extensions(self):
        self.assertTrue(is_btf_open_path("a.btf"))
        self.assertTrue(is_btf_open_path("a.btf.gz"))
        self.assertTrue(is_btf_open_path("a.GZ"))
        self.assertTrue(is_btf_open_path("a.btf.bz2"))
        self.assertTrue(is_btf_open_path("trace.zip"))
        self.assertTrue(is_btf_open_path("/tmp/pack.zip::nested/a.btf"))
        self.assertFalse(is_btf_open_path("a.csv"))


class CompressionHelpersTests(unittest.TestCase):
    def test_sniff_and_read_gzip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.btf.gz"
            with gzip.open(path, "wt", encoding="utf-8") as fh:
                fh.write(_MINI_BTF)
            self.assertEqual(_sniff_compression(str(path)), "gzip")
            with _open_btf_text(str(path)) as fh:
                text = fh.read()
            self.assertIn("timeScale", text)
            self.assertIn("resume", text)

    def test_sniff_and_read_bz2(self):
        import bz2
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.btf.bz2"
            with bz2.open(path, "wt", encoding="utf-8") as fh:
                fh.write(_MINI_BTF)
            self.assertEqual(_sniff_compression(str(path)), "bz2")
            with _open_btf_text(str(path)) as fh:
                self.assertIn("preempt", fh.read())

    def test_zip_picks_btf_member(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "pack.zip"
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("readme.txt", "nope")
                zf.writestr("traces/demo.btf", _MINI_BTF)
            self.assertEqual(_sniff_compression(str(path)), "zip")
            self.assertEqual(
                _pick_zip_btf_member(["readme.txt", "traces/demo.btf"]),
                "traces/demo.btf",
            )
            with _open_btf_text(str(path)) as fh:
                self.assertIn("#version", fh.read())

    def test_zip_empty_of_btf_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _pick_zip_btf_member(["readme.txt", "notes.md"])
        self.assertIn("no .btf member", str(ctx.exception))

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "empty.zip"
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("readme.txt", "nope")
            with self.assertRaises(ValueError) as ctx2:
                _expand_open_paths(str(path))
            self.assertIn("no .btf member", str(ctx2.exception))

    def test_zip_multi_expands_to_member_paths(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "pack.zip"
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("a.btf", _MINI_BTF)
                zf.writestr("nested/b.btf", _MINI_BTF_B)
                zf.writestr("readme.txt", "x")
            members = _list_zip_btf_members(
                ["readme.txt", "a.btf", "nested/b.btf"])
            self.assertEqual(members, ["a.btf", "nested/b.btf"])
            expanded = _expand_open_paths(str(path))
            self.assertEqual(len(expanded), 2)
            self.assertTrue(all("::" in p for p in expanded))
            self.assertEqual(_trace_display_name(expanded[0]), "a.btf")
            self.assertEqual(_trace_display_name(expanded[1]), "b.btf")
            with _open_btf_text(expanded[1]) as fh:
                self.assertIn("[0/2]B", fh.read())

    def test_zip_member_path_helpers(self):
        z, m = _split_zip_member_path("/tmp/p.zip::dir/t.btf")
        self.assertEqual(z, "/tmp/p.zip")
        self.assertEqual(m, "dir/t.btf")
        norm = _normalize_open_path("/tmp/p.zip::dir/t.btf")
        self.assertTrue(norm.endswith("::dir/t.btf"))

    def test_plain_btf(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.btf"
            path.write_text(_MINI_BTF, encoding="utf-8")
            self.assertEqual(_sniff_compression(str(path)), "")
            with _open_btf_text(str(path)) as fh:
                self.assertTrue(fh.read().startswith("#version"))


if __name__ == "__main__":
    unittest.main()
