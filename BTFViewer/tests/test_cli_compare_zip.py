"""CLI compare: two paths or one multi-BTF zip."""
from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

BTF_ROOT = Path(__file__).resolve().parents[1]
REPO = BTF_ROOT.parent
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.cli import (  # noqa: E402
    _cli_compare_pair_members,
    _cli_compare_run,
    _cli_resolve_compare_traces,
)
from btf_viewer_pkg.parser import _ZIP_MEMBER_SEP  # noqa: E402

_MINI_A = """\
#version 1.0.0
#timeScale us
100,Core_0,0,T,[0/1]A,0,resume
200,Core_0,0,T,[0/1]A,0,preempt
"""

_MINI_B = """\
#version 1.0.0
#timeScale us
100,Core_0,0,T,[0/2]B,0,resume
180,Core_0,0,T,[0/2]B,0,preempt
"""


class ComparePairResolveTests(unittest.TestCase):
    def test_two_paths(self):
        a, b, err = _cli_resolve_compare_traces(["/tmp/a.btf", "/tmp/b.btf"])
        self.assertIsNone(err)
        self.assertTrue(a.endswith("a.btf"))
        self.assertTrue(b.endswith("b.btf"))

    def test_pair_members_prefers_top_level(self):
        members = [
            "tickful-8cores.btf",
            "tickless-8cores.btf",
            "tracedata/tickful-8cores.btf",
            "tracedata/tickless-8cores.btf",
        ]
        picked = _cli_compare_pair_members(members)
        self.assertEqual(
            picked, ["tickful-8cores.btf", "tickless-8cores.btf"])

    def test_pair_members_rejects_ambiguous(self):
        self.assertIsNone(_cli_compare_pair_members([
            "a.btf", "b.btf", "c.btf"]))
        self.assertIsNone(_cli_compare_pair_members(["only.btf"]))

    def test_zip_with_two_root_members(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "pair.zip"
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("alpha.btf", _MINI_A)
                zf.writestr("beta.btf", _MINI_B)
                zf.writestr("nested/alpha.btf", _MINI_A)
                zf.writestr("nested/beta.btf", _MINI_B)
            a, b, err = _cli_resolve_compare_traces([str(path)])
            self.assertIsNone(err)
            self.assertTrue(a.endswith(f"{_ZIP_MEMBER_SEP}alpha.btf"))
            self.assertTrue(b.endswith(f"{_ZIP_MEMBER_SEP}beta.btf"))

    def test_zip_with_exactly_two_nested(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "pair.zip"
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("dir/a.btf", _MINI_A)
                zf.writestr("dir/b.btf", _MINI_B)
            a, b, err = _cli_resolve_compare_traces([str(path)])
            self.assertIsNone(err)
            self.assertIn("dir/a.btf", a)
            self.assertIn("dir/b.btf", b)

    def test_zip_three_root_errors(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "many.zip"
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("a.btf", _MINI_A)
                zf.writestr("b.btf", _MINI_B)
                zf.writestr("c.btf", _MINI_A)
            _a, _b, err = _cli_resolve_compare_traces([str(path)])
            self.assertIsNotNone(err)
            self.assertIn("3 .btf members", err)

    def test_single_btf_errors(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "alone.btf"
            path.write_text(_MINI_A, encoding="utf-8")
            _a, _b, err = _cli_resolve_compare_traces([str(path)])
            self.assertIsNotNone(err)
            self.assertIn("two traces", err)

    def test_compare_run_from_zip(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            zpath = td_path / "pair.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr("tickful.btf", _MINI_A)
                zf.writestr("tickless.btf", _MINI_B)
            out = td_path / "cmp.csv"
            args = argparse.Namespace(
                traces=[str(zpath)],
                output=str(out),
                format="csv",
                name_a=None,
                name_b=None,
                lo=None,
                hi=None,
                lo_a=None,
                hi_a=None,
                lo_b=None,
                hi_b=None,
            )
            with mock.patch("sys.stdout"):
                rc = _cli_compare_run(args)
            self.assertEqual(rc, 0)
            text = out.read_text(encoding="utf-8-sig")
            self.assertIn("tickful.btf", text)
            self.assertIn("tickless.btf", text)
            self.assertIn("Summary", text)


@unittest.skipUnless(
    (REPO / "tracedata" / "tickless-8cores.zip").is_file(),
    "tracedata/tickless-8cores.zip not present",
)
class CompareSampleZipTests(unittest.TestCase):
    def test_resolve_tickless_8cores_zip(self):
        zpath = REPO / "tracedata" / "tickless-8cores.zip"
        a, b, err = _cli_resolve_compare_traces([str(zpath)])
        self.assertIsNone(err)
        self.assertTrue(a.endswith(f"{_ZIP_MEMBER_SEP}tickful-8cores.btf"))
        self.assertTrue(b.endswith(f"{_ZIP_MEMBER_SEP}tickless-8cores.btf"))
        # Prefer archive-root members over nested tracedata/ duplicates.
        self.assertFalse(a.split(_ZIP_MEMBER_SEP, 1)[1].startswith("tracedata/"))
        self.assertFalse(b.split(_ZIP_MEMBER_SEP, 1)[1].startswith("tracedata/"))


if __name__ == "__main__":
    unittest.main()
