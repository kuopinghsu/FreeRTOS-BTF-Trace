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
    _open_btf_text,
    _pick_zip_btf_member,
    _sniff_compression,
    is_btf_open_path,
)

_MINI_BTF = """\
#version 1.0.0
#timeScale us
100,Core_0,0,T,[0/1]A,0,resume
200,Core_0,0,T,[0/1]A,0,preempt
"""


class BtfOpenPathTests(unittest.TestCase):
    def test_extensions(self):
        self.assertTrue(is_btf_open_path("a.btf"))
        self.assertTrue(is_btf_open_path("a.btf.gz"))
        self.assertTrue(is_btf_open_path("a.GZ"))
        self.assertTrue(is_btf_open_path("a.btf.bz2"))
        self.assertTrue(is_btf_open_path("trace.zip"))
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

    def test_plain_btf(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.btf"
            path.write_text(_MINI_BTF, encoding="utf-8")
            self.assertEqual(_sniff_compression(str(path)), "")
            with _open_btf_text(str(path)) as fh:
                self.assertTrue(fh.read().startswith("#version"))


if __name__ == "__main__":
    unittest.main()
