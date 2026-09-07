"""CLI ``workspace`` subcommand: inspect / extract / report / errors."""
from __future__ import annotations

import io
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.cli import _cli_workspace_run  # noqa: E402
from btf_viewer_pkg.investigation_notebook import (  # noqa: E402
    add_bookmark, new_investigation, set_conclusion,
)
from btf_viewer_pkg.workspace import save_workspace  # noqa: E402

_TRACE = b"#version 2.2.0\n#timeScale us\n100,Core_0,0,T,[0/1]W,0,resume,\n"


def _args(workspace, *, extract=None, report=None, json=False):
    return types.SimpleNamespace(
        workspace=workspace, extract=extract, report=report, json=json)


class CliWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.path = str(self.tmp / "w.btfw")
        inv = set_conclusion(
            add_bookmark(new_investigation(title="Case"),
                         type="observation", title="obs", bookmark_id="o"),
            "final")
        save_workspace(self.path, trace_bytes=_TRACE, trace_name="mini.btf",
                       investigation=inv, health={"status": "pass"},
                       findings=[{"id": "f", "rule_id": "tick_health"}],
                       report_html="<html>report</html>",
                       btfviewer_version="1.4.0")

    def _run(self, args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = _cli_workspace_run(args)
        return rc, buf.getvalue()

    def test_inspect_prints_summary(self):
        rc, out = self._run(_args(self.path))
        self.assertEqual(rc, 0)
        self.assertIn("btf-viewer-workspace/1", out)
        self.assertIn("mini.btf", out)
        self.assertIn("trace hash matches", out)
        self.assertIn("investigation/bookmarks.json", out)
        self.assertIn("1 bookmark(s)", out)

    def test_json_prints_manifest(self):
        import json as _json
        rc, out = self._run(_args(self.path, json=True))
        self.assertEqual(rc, 0)
        man = _json.loads(out)
        self.assertEqual(man["schema"], "btf-viewer-workspace/1")

    def test_extract(self):
        dest = self.tmp / "x"
        rc, out = self._run(_args(self.path, extract=str(dest)))
        self.assertEqual(rc, 0)
        self.assertTrue((dest / "manifest.json").is_file())
        self.assertTrue((dest / "trace" / "source.btf").is_file())

    def test_report_extraction(self):
        rep = self.tmp / "r.html"
        rc, out = self._run(_args(self.path, report=str(rep)))
        self.assertEqual(rc, 0)
        self.assertEqual(rep.read_text(encoding="utf-8"), "<html>report</html>")

    def test_missing_file_returns_1(self):
        rc, _ = self._run(_args(str(self.tmp / "nope.btfw")))
        self.assertEqual(rc, 1)

    def test_not_a_workspace_returns_2(self):
        bad = self.tmp / "bad.btfw"
        bad.write_bytes(b"not a zip")
        rc, _ = self._run(_args(str(bad)))
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
