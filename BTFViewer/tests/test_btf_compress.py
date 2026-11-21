"""Compressed BTF open helpers (gzip / bz2 / zip)."""
from __future__ import annotations

import bz2
import gzip
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.parser import (  # noqa: E402
    _expand_open_paths,
    _filter_existing_open_paths,
    _list_zip_btf_members,
    _normalize_open_path,
    _open_btf_text,
    _open_path_exists,
    _parse_btf,
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
    def test_parser_caps_unterminated_lines(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "trace.btf.gz"
            with patch("btf_viewer_pkg.parser._MAX_TRACE_LINE_CHARS", 64):
                path.write_bytes(gzip.compress(b"#timeScale us\n#" + b"x" * 63))
                _parse_btf(str(path))
                path.write_bytes(gzip.compress(b"#timeScale us\n#" + b"x" * 64))
                with self.assertRaisesRegex(ValueError, "Trace line 2 exceeds the 64-character limit"):
                    _parse_btf(str(path))

    def test_expanded_byte_limit_for_all_formats(self):
        raw = _MINI_BTF.replace("\n", "\r\n").encode("utf-8")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            gz = root / "trace.btf.gz"
            bz = root / "trace.btf.bz2"
            plain = root / "trace.btf"
            archive = root / "trace.btf.zip"
            plain.write_bytes(raw)
            gz.write_bytes(gzip.compress(raw))
            bz.write_bytes(bz2.compress(raw))
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("nested/trace.btf", raw)

            for path in (plain, gz, bz, archive, f"{archive}::nested/trace.btf"):
                with self.subTest(path=path):
                    with _open_btf_text(str(path), max_expanded=len(raw)) as trace:
                        self.assertEqual(trace.read(), _MINI_BTF)
                    with self.assertRaisesRegex(ValueError, "Expanded trace exceeds"):
                        with _open_btf_text(str(path), max_expanded=len(raw) - 1) as trace:
                            trace.read()

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

    def test_session_restore_keeps_multi_zip_members(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "pack.zip"
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("a.btf", _MINI_BTF)
                zf.writestr("nested/b.btf", _MINI_BTF_B)
            a, b = _expand_open_paths(str(path))
            self.assertTrue(_open_path_exists(a))
            self.assertTrue(_open_path_exists(b))
            # Bare os.path.isfile must not be used: zip::member is virtual.
            self.assertFalse(os.path.isfile(a))
            restored = _filter_existing_open_paths([a, b, a, str(path / "missing.btf")])
            self.assertEqual(restored, [a, b])
            missing_member = f"{path}::gone.btf"
            self.assertFalse(_open_path_exists(missing_member))
            self.assertEqual(_filter_existing_open_paths([missing_member]), [])

    def test_plain_btf(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.btf"
            path.write_text(_MINI_BTF, encoding="utf-8")
            self.assertEqual(_sniff_compression(str(path)), "")
            with _open_btf_text(str(path)) as fh:
                self.assertTrue(fh.read().startswith("#version"))


if __name__ == "__main__":
    unittest.main()
