"""Export default filenames strip the full trace/archive extension
(``example-8cores.btf.gz`` → ``example-8cores.btfw``), and a ``.btfw`` whose
embedded bytes don't match the manifest's compression suffix still opens.

Lockstep between ``mainwindow._EXPORT_BASENAME_RE`` /
``_staged_trace_ext`` and ``web/src/utils/exportActions.js`` /
``web/src/App.vue``.
"""
from __future__ import annotations

import gzip
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.mainwindow import (  # noqa: E402
    _export_base_name,
    _staged_trace_ext,
)

ACT = (BTF_ROOT / "web" / "src" / "utils" / "exportActions.js").read_text("utf-8")
APP = (BTF_ROOT / "web" / "src" / "App.vue").read_text("utf-8")
MW = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text("utf-8")


class ExportBaseNameTests(unittest.TestCase):
    def test_strips_every_trace_and_archive_extension(self):
        for name, want in (
            ("/x/example-8cores.btf.gz", "/x/example-8cores"),
            ("example-8cores.btf", "example-8cores"),
            ("a.btf.bz2", "a"),
            ("b.btf.zip", "b"),
            ("c.json", "c"),
            ("d.btfw", "d"),
            ("e.gz", "e"),
            ("keep.v2", "keep.v2"),
        ):
            self.assertEqual(_export_base_name(name, "fallback"), want, name)
        self.assertEqual(_export_base_name("", "workspace"), "workspace")


class StagedTraceExtTests(unittest.TestCase):
    def test_extension_follows_the_bytes_not_the_name(self):
        self.assertEqual(_staged_trace_ext(gzip.compress(b"#v")), ".btf.gz")
        self.assertEqual(_staged_trace_ext(b"BZh91AY&SY"), ".btf.bz2")
        self.assertEqual(_staged_trace_ext(b"PK\x03\x04"), ".btf.zip")
        self.assertEqual(_staged_trace_ext(b"#version 2.2.0\n"), ".btf")
        self.assertEqual(_staged_trace_ext(b""), ".btf")


class ParityTests(unittest.TestCase):
    def test_basename_extension_set_matches_web(self):
        # Same alternation in the py regex and the js regex.
        self.assertIn(
            r"\.(btf\.gz|btf\.bz2|btf\.zip|btf|btfw|json|gz|bz2|zip)$", MW)
        self.assertIn(
            r"/\.(btf\.gz|btf\.bz2|btf\.zip|btf|btfw|json|gz|bz2|zip)$/i", ACT)

    def test_web_open_strips_stale_compression_suffix(self):
        self.assertIn(r"traceName.replace(/\.(gz|bz2|zip)$/i, '')", APP)

    def test_desktop_stages_by_content(self):
        self.assertIn("_staged_trace_ext(trace_bytes)", MW)
        self.assertIn("_export_base_name(self._current_file", MW)


if __name__ == "__main__":
    unittest.main()
