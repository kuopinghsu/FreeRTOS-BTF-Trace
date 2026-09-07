"""CLI ``report`` command: headless Statistics export (CSV + HTML).

Regression for the headless report path, which built ``_StatsPanel`` via
``__new__`` (no window):
  * CSV crashed with ``NameError: trace_name`` / ``scope_type``.
  * HTML crashed on ``self.window()`` under newer shiboken, then on
    ``QFontDatabase`` with no QGuiApplication.
"""
from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.cli import _cli_report_run  # noqa: E402
from btf_viewer_pkg.investigation_findings import RULE_IDS as _RULE_IDS  # noqa: E402

# Two cores, a handful of switches — enough for every Statistics section to
# render without error.
_MINI_TRACE = """\
#version 1.0.0
#timeScale us
1000,Core_0,0,T,[0/1]Worker,1,resume
1000,Core_1,0,T,[0/2]Other,1,resume
1500,Core_0,0,T,[0/1]Worker,1,preempt
1500,Core_1,0,T,[0/2]Other,1,preempt
2000,Core_0,0,T,[0/1]Worker,1,resume
2600,Core_0,0,T,[0/1]Worker,1,terminate
2000,Core_1,0,T,[0/2]Other,1,resume
2800,Core_1,0,T,[0/2]Other,1,terminate
"""


def _args(trace: str, output: str, fmt: str, *, anonymize: bool = False,
          investigation: str = None, save_workspace: str = None,
          embed_trace: bool = True) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        trace=trace, output=output, format=fmt, lo=None, hi=None,
        anonymize=anonymize, investigation=investigation,
        save_workspace=save_workspace, embed_trace=embed_trace)


class CliReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.trace = self.tmp / "mini.btf"
        self.trace.write_text(_MINI_TRACE, encoding="utf-8")
        self.addCleanup(self._tmp.cleanup)

    def test_csv_report_writes_summary_rows(self) -> None:
        out = self.tmp / "r.csv"
        rc = _cli_report_run(_args(str(self.trace), str(out), "csv"))
        self.assertEqual(rc, 0)
        self.assertTrue(out.is_file())
        body = out.read_text(encoding="utf-8-sig")
        # The two previously-undefined variables land in these rows.
        self.assertIn("Trace file,mini.btf", body)
        self.assertIn("Scope,Full Trace", body)
        self.assertIn("Core Utilisation", body)

    def test_html_report_renders_without_gui(self) -> None:
        out = self.tmp / "r.html"
        rc = _cli_report_run(_args(str(self.trace), str(out), "html"))
        self.assertEqual(rc, 0)
        self.assertTrue(out.is_file())
        body = out.read_text(encoding="utf-8")
        self.assertIn("<html", body.lower())
        self.assertIn("mini.btf", body)

    def test_both_formats(self) -> None:
        stem = self.tmp / "r"
        rc = _cli_report_run(_args(str(self.trace), str(stem), "both"))
        self.assertEqual(rc, 0)
        self.assertTrue((self.tmp / "r.html").is_file())
        self.assertTrue((self.tmp / "r.csv").is_file())

    def test_all_formats(self) -> None:
        stem = self.tmp / "everything"
        rc = _cli_report_run(_args(str(self.trace), str(stem), "all"))
        self.assertEqual(rc, 0)
        self.assertTrue((self.tmp / "everything.html").is_file())
        self.assertTrue((self.tmp / "everything.csv").is_file())
        self.assertTrue((self.tmp / "everything.json").is_file())

    def test_json_report_snapshot(self) -> None:
        import json
        out = self.tmp / "r.json"
        rc = _cli_report_run(_args(str(self.trace), str(out), "json"))
        self.assertEqual(rc, 0)
        self.assertTrue(out.is_file())
        d = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(d["schema"], "btf-viewer-stats/2")
        self.assertEqual(d["trace_file"], "mini.btf")
        self.assertIn("summary", d)
        self.assertIn("tasks", d["summary"])
        self.assertIsInstance(d["findings"], list)
        self.assertIsInstance(d["core_utilisation"], list)
        self.assertEqual(d["scope"]["type"], "full")
        # Investigation Findings — the structured, reproducible model.
        self.assertIsInstance(d["investigation_findings"], list)
        for f in d["investigation_findings"]:
            self.assertIn(f["rule_id"], _RULE_IDS)
            self.assertIn(f["status"], ("new", "reviewed", "bookmarked", "dismissed"))
            self.assertIsInstance(f["measured_values"], list)
            self.assertIn("comparison_basis", f)
            self.assertNotIn("evidence_text", f)  # display text kept out of the snapshot
        if d["findings"]:
            self.assertIn("rule_id", d["findings"][0])

    def test_json_report_inferred_from_extension(self) -> None:
        out = self.tmp / "auto.json"
        rc = _cli_report_run(_args(str(self.trace), str(out), None))
        self.assertEqual(rc, 0)
        self.assertTrue(out.is_file())

    def test_investigation_section_in_html_and_json(self) -> None:
        import json
        from btf_viewer_pkg.investigation_notebook import (
            add_bookmark, dump_investigation, link_bookmarks, new_investigation,
            set_conclusion,
        )
        inv = new_investigation(title="Case", analysis_range={"start": 0, "end": 3000})
        inv = add_bookmark(inv, type="observation", title="Worker preempted",
                           bookmark_id="obs", refs=[{"kind": "entity", "entity": "Worker"}])
        inv = add_bookmark(inv, type="conclusion", title="Contention on core 0",
                           bookmark_id="con", refs=[{"kind": "entity", "entity": "Worker"}])
        inv = link_bookmarks(inv, "con", "obs", "concludes")
        inv = set_conclusion(inv, "Needs affinity change")
        inv_path = self.tmp / "case.json"
        inv_path.write_text(dump_investigation(inv), encoding="utf-8")

        stem = self.tmp / "withinv"
        rc = _cli_report_run(_args(str(self.trace), str(stem), "all",
                                   investigation=str(inv_path)))
        self.assertEqual(rc, 0)
        html = (self.tmp / "withinv.html").read_text(encoding="utf-8")
        self.assertIn("<h2>Investigation</h2>", html)
        self.assertIn("Contention on core 0", html)
        d = json.loads((self.tmp / "withinv.json").read_text(encoding="utf-8"))
        self.assertIn("investigation", d)
        self.assertEqual(d["investigation"]["schema"], "btf-viewer-investigation/1")
        self.assertTrue(d["investigation"]["chains"])
        self.assertIn("broken_references", d["investigation"])

    def test_missing_investigation_file_errors(self) -> None:
        rc = _cli_report_run(_args(str(self.trace), str(self.tmp / "x.html"),
                                   "html", investigation=str(self.tmp / "nope.json")))
        self.assertEqual(rc, 1)

    def test_save_workspace_bundles_trace_and_report(self) -> None:
        from btf_viewer_pkg.investigation_notebook import (
            add_bookmark, dump_investigation, new_investigation,
        )
        from btf_viewer_pkg.workspace import open_workspace

        inv = add_bookmark(new_investigation(title="C"), type="observation",
                           title="obs", bookmark_id="o")
        inv_path = self.tmp / "case.json"
        inv_path.write_text(dump_investigation(inv), encoding="utf-8")
        ws_path = self.tmp / "case.btfw"

        rc = _cli_report_run(_args(
            str(self.trace), str(self.tmp / "r"), "all",
            investigation=str(inv_path), save_workspace=str(ws_path)))
        self.assertEqual(rc, 0)
        self.assertTrue(ws_path.is_file())

        ws = open_workspace(str(ws_path))
        self.assertEqual(ws["trace_bytes"], self.trace.read_bytes())
        self.assertEqual(ws["manifest"]["trace"]["name"], "mini.btf")
        self.assertTrue(ws["manifest"]["trace"]["embedded"])
        self.assertIn("<html", (ws["report_html"] or "").lower())
        self.assertEqual([b["id"] for b in ws["investigation"]["bookmarks"]], ["o"])
        self.assertIsInstance(ws["health"], dict)
        self.assertIsInstance(ws["findings"], list)

    def test_save_workspace_no_embed_uses_reference(self) -> None:
        from btf_viewer_pkg.workspace import open_workspace
        ws_path = self.tmp / "ref.btfw"
        rc = _cli_report_run(_args(str(self.trace), str(self.tmp / "r2.html"),
                                   "html", save_workspace=str(ws_path),
                                   embed_trace=False))
        self.assertEqual(rc, 0)
        ws = open_workspace(str(ws_path))
        self.assertIsNone(ws["trace_bytes"])
        self.assertFalse(ws["manifest"]["trace"]["embedded"])
        self.assertEqual(ws["trace_ref"], str(self.trace))

    def test_anonymize_aliases_task_names(self) -> None:
        plain = self.tmp / "p.csv"
        anon = self.tmp / "a.csv"
        self.assertEqual(_cli_report_run(_args(str(self.trace), str(plain), "csv")), 0)
        self.assertEqual(
            _cli_report_run(_args(str(self.trace), str(anon), "csv", anonymize=True)), 0)
        p = plain.read_text(encoding="utf-8-sig")
        a = anon.read_text(encoding="utf-8-sig")
        self.assertIn("Worker", p)
        self.assertNotIn("Worker", a)
        self.assertIn("Task-", a)

    def test_anonymize_html_report_leaves_no_task_names(self) -> None:
        plain = self.tmp / "p.html"
        anon = self.tmp / "a.html"
        self.assertEqual(
            _cli_report_run(_args(str(self.trace), str(plain), "html")), 0)
        self.assertEqual(
            _cli_report_run(
                _args(str(self.trace), str(anon), "html", anonymize=True)), 0)
        self.assertIn("Worker", plain.read_text(encoding="utf-8"))
        html = anon.read_text(encoding="utf-8")
        self.assertNotIn("Worker", html)
        self.assertIn("Task-", html)

    def test_scoped_report_labels_cursor_range(self) -> None:
        out = self.tmp / "s.csv"
        args = _args(str(self.trace), str(out), "csv")
        args.lo, args.hi = 1000, 2000
        rc = _cli_report_run(args)
        self.assertEqual(rc, 0)
        body = out.read_text(encoding="utf-8-sig")
        self.assertIn("Scope,C1", body)


if __name__ == "__main__":
    unittest.main()
