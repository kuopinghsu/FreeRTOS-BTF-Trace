"""Shared hardened ZIP-container reader (``.btfw`` + ``.xtf``).

Parity with ``web/tests/zipContainer.test.js``.
"""
from __future__ import annotations

import os
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

from btf_viewer_pkg.zip_container import (  # noqa: E402
    CONTAINER_MAX_ENTRIES,
    CONTAINER_MAX_UNCOMPRESSED_BYTES,
    is_safe_member,
    read_zip_container,
    safe_extract_all,
)


def _zip(path, members):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            zf.writestr(name, data)
    return str(path)


class IsSafeMemberTests(unittest.TestCase):
    def test_accepts_plain_relative_paths(self):
        for n in ("a.txt", "a/b.txt", "trace/source.btf", "voice/en/01.mp3", "a/b/"):
            self.assertTrue(is_safe_member(n), n)

    def test_rejects_traversal_and_roots(self):
        for n in ("../x", "a/../b", "/x", "~/x", "C:\\x", "a\\b", " s", "",
                  "a/./b", "a\x00b"):
            self.assertFalse(is_safe_member(n), n)


class ReadZipContainerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_returns_only_safe_members_with_warnings(self):
        p = _zip(self.tmp / "c.zip", [
            ("ok/a.txt", b"a"),
            ("../evil", b"x"),
            ("/abs", b"x"),
            ("dir/", b""),
        ])
        out = read_zip_container(p)
        self.assertEqual(sorted(out["members"]), ["ok/a.txt"])
        self.assertEqual(len(out["warnings"]), 2)

    def test_rejects_non_zip(self):
        p = self.tmp / "x.zip"
        p.write_bytes(b"not a zip at all")
        with self.assertRaises(ValueError):
            read_zip_container(str(p), container_desc="zip / .xtf")

    def test_reads_from_raw_bytes_too(self):
        p = _zip(self.tmp / "b.zip", [("m.txt", b"hi")])
        out = read_zip_container(Path(p).read_bytes())
        self.assertEqual(out["members"]["m.txt"], b"hi")

    def test_too_many_entries_rejected(self):
        p = _zip(self.tmp / "many.zip",
                 [(f"f{i}.txt", b"x") for i in range(CONTAINER_MAX_ENTRIES + 2)])
        with self.assertRaises(ValueError):
            read_zip_container(p)

    def test_compression_bomb_rejected(self):
        p = _zip(self.tmp / "bomb.zip", [("big.bin", b"\0" * (4 * 1024 * 1024))])
        with self.assertRaises(ValueError):
            read_zip_container(p)

    def test_decompressed_size_cap(self):
        p = _zip(self.tmp / "big.zip", [("a.bin", os.urandom(2048))])
        with self.assertRaises(ValueError):
            read_zip_container(p, max_uncompressed=100)


class SafeExtractAllTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_extracts_safe_members_only(self):
        p = _zip(self.tmp / "e.zip", [
            ("a.txt", b"a"), ("sub/b.txt", b"b"), ("../evil", b"x")])
        dest = self.tmp / "out"
        written = safe_extract_all(p, str(dest))
        self.assertEqual(sorted(Path(x).name for x in written), ["a.txt", "b.txt"])
        self.assertTrue((dest / "a.txt").is_file())
        self.assertTrue((dest / "sub" / "b.txt").is_file())
        self.assertFalse((self.tmp / "evil").exists())


class ParityTests(unittest.TestCase):
    def test_module_and_js_in_step(self):
        py = (BTF_ROOT / "btf_viewer_pkg" / "zip_container.py").read_text("utf-8")
        js = (BTF_ROOT / "web" / "src" / "utils" / "zipContainer.js").read_text("utf-8")
        for py_name, js_name in (
            ("def is_safe_member", "export function isSafeMember"),
            ("def read_zip_container", "export function readZipContainer"),
            ("CONTAINER_MAX_ENTRIES", "CONTAINER_MAX_ENTRIES"),
            ("CONTAINER_MAX_UNCOMPRESSED_BYTES", "CONTAINER_MAX_UNCOMPRESSED_BYTES"),
            ("CONTAINER_MAX_COMPRESSION_RATIO", "CONTAINER_MAX_COMPRESSION_RATIO"),
        ):
            self.assertIn(py_name, py, py_name)
            self.assertIn(js_name, js, js_name)
        for token in ("4096", "250", "512 * 1024 * 1024", "64 * 1024"):
            self.assertIn(token, py, token)
            self.assertIn(token, js, token)
        # Same user-visible failure strings on both sides.
        for msg in ("too many entries", "compression bomb",
                    "decompressed size exceeds the limit", "not a "):
            self.assertIn(msg, py, msg)
            self.assertIn(msg, js, msg)


if __name__ == "__main__":
    unittest.main()
