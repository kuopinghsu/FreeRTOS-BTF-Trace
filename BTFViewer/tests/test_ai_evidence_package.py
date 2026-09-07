"""Compact AI evidence package (TODO Phase 6): assembly, size, preview, parity."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.ai_evidence_package import (  # noqa: E402
    EVIDENCE_PACKAGE_SCHEMA, RESPONSE_CONTRACT, build_evidence_package,
    estimate_tokens, evidence_package_size, format_evidence_package_preview,
)

_SUMMARY = {"span_ns": 1_000_000, "tasks": 5, "load_balance_score": 82.0,
            "tick_health": "GOOD", "secret_extra": 999}
_HEALTH = {"status": "caution", "issue_count": 1,
           "metric_limitations": ["Core Migrations"]}
_FINDINGS = [
    {"rule_id": "blocking", "severity": "warning", "title": "Long block",
     "entities": ["ControlTask"],
     "measured_values": [{"name": "block", "value": 50, "unit": "us"}]},
]
_INV = {"bookmarks": [
    {"id": "o1", "type": "observation", "title": "spike", "note": "n",
     "refs": [{"kind": "finding", "rule_id": "blocking"}]}],
    "conclusion": "control loop starved", "unresolved_questions": ["why now?"]}


class BuildTests(unittest.TestCase):
    def _pkg(self, **kw):
        base = dict(
            question="Why does ControlTask miss its deadline?",
            scope="C1–C2", analysis_range={"start": 100, "end": 200},
            trace_name="run.btf", trace_summary=_SUMMARY, health=_HEALTH,
            findings=_FINDINGS, investigation=_INV,
            entities=["ControlTask", "IDLE"], cores=["Core_0", "Core_1"])
        base.update(kw)
        return build_evidence_package(**base)

    def test_shape_and_stable_ids(self):
        p = self._pkg()
        self.assertEqual(p["schema"], EVIDENCE_PACKAGE_SCHEMA)
        self.assertEqual(p["response_contract"], RESPONSE_CONTRACT)
        self.assertEqual(p["findings"][0]["id"], "F1")
        self.assertEqual(p["analysis_range"], {"start": 100, "end": 200})
        self.assertEqual(p["bookmarks"][0]["title"], "spike")
        self.assertEqual(p["conclusion_so_far"], "control loop starved")
        self.assertIn("unverified", p["instructions"])

    def test_summary_is_whitelisted(self):
        p = self._pkg()
        self.assertIn("load_balance_score", p["trace"]["summary"])
        self.assertNotIn("secret_extra", p["trace"]["summary"])

    def test_redaction_aliases_task_names_consistently(self):
        p = self._pkg(redact_names=True)
        self.assertTrue(p["redacted"])
        self.assertEqual(p["trace"]["name"], "(redacted)")
        # ControlTask -> the same alias everywhere it appears.
        alias = p["entities"][0]
        self.assertTrue(alias.startswith("task_"))
        self.assertEqual(p["findings"][0]["entities"][0], alias)
        # Structured task-name fields are aliased (the user's free-text question
        # is left as written).
        structured = json.dumps({k: v for k, v in p.items() if k != "question"})
        self.assertNotIn("ControlTask", structured)

    def test_size_and_token_estimate(self):
        p = self._pkg()
        size = evidence_package_size(p)
        self.assertEqual(size["approx_tokens"], estimate_tokens(p))
        self.assertGreater(size["bytes"], 100)
        self.assertEqual(size["findings"], 1)

    def test_preview_lists_the_essentials(self):
        txt = format_evidence_package_preview(self._pkg())
        for token in ("Question:", "Range: 100 – 200", "Trace health: caution",
                      "[F1]", "Response contract:", "tokens"):
            self.assertIn(token, txt)

    def test_empty_inputs_are_safe(self):
        p = build_evidence_package(question="q")
        self.assertEqual(p["findings"], [])
        self.assertEqual(p["bookmarks"], [])
        self.assertIsNone(p["analysis_range"])
        self.assertIsNone(p["trace_health"])


class ParityTests(unittest.TestCase):
    def test_module_and_js_in_step(self):
        py = (BTF_ROOT / "btf_viewer_pkg" / "ai_evidence_package.py").read_text("utf-8")
        js = (BTF_ROOT / "web" / "src" / "utils" / "aiEvidencePackage.js").read_text("utf-8")
        self.assertIn('EVIDENCE_PACKAGE_SCHEMA = "btf-viewer-evidence/1"', py)
        self.assertIn("EVIDENCE_PACKAGE_SCHEMA = 'btf-viewer-evidence/1'", js)
        for key in ("schema", "question", "analysis_range", "trace_health",
                    "response_contract", "redacted", "conclusion_so_far"):
            self.assertIn(f'"{key}"', py, key)
            self.assertIn(key, js, key)
        for py_fn, js_fn in (
            ("def build_evidence_package", "export function buildEvidencePackage"),
            ("def estimate_tokens", "export function estimateTokens"),
            ("def format_evidence_package_preview",
             "export function formatEvidencePackagePreview"),
        ):
            self.assertIn(py_fn, py)
            self.assertIn(js_fn, js)


class CliReportAiPackageTests(unittest.TestCase):
    def setUp(self):
        self.trace = BTF_ROOT.parent / "tracedata" / "example-2cores.btf.gz"
        if not self.trace.is_file():
            self.skipTest(f"missing {self.trace}")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_report_writes_ai_package_and_prints_estimate(self):
        from btf_viewer_pkg.cli import _cli_report_run
        out_html = self.tmp / "r.html"
        out_pkg = self.tmp / "pkg.json"
        args = types.SimpleNamespace(
            trace=str(self.trace), output=str(out_html), format="html",
            lo=None, hi=None, investigation=None, save_workspace=None,
            embed_trace=True, ai_package=str(out_pkg),
            question="Is SMP load balanced?", redact_names=False)
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            code = _cli_report_run(args)
        self.assertEqual(code, 0)
        self.assertTrue(out_pkg.is_file())
        pkg = json.loads(out_pkg.read_text("utf-8"))
        self.assertEqual(pkg["question"], "Is SMP load balanced?")
        self.assertEqual(pkg["schema"], EVIDENCE_PACKAGE_SCHEMA)
        self.assertIn("tokens", buf_err.getvalue())
        self.assertIn(str(out_pkg), buf_out.getvalue())


if __name__ == "__main__":
    unittest.main()
