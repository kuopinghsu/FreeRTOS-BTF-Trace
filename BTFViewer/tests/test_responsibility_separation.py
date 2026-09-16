"""Notebook / Findings / Statistics / Compare / AI responsibility boundaries.

- The Notebook owns durable investigation state and does not depend on AI.
- Analysis Findings stays deterministic triage.
- The AI layer never writes durable Notebook state (that path is user-accepted
  proposals only — §10 — and is not wired to auto-write).
- The Notebook header carries no AI-only score.
"""

from __future__ import annotations

import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]

from btf_viewer_pkg.investigation_notebook import (  # noqa: E402
    add_bookmark,
    investigation_header,
    investigation_sections,
    new_investigation,
    set_conclusion,
)


def _src(rel: str) -> str:
    return (BTF_ROOT / rel).read_text(encoding="utf-8")


class NotebookIsAiIndependentTests(unittest.TestCase):
    def test_notebook_module_imports_no_ai(self) -> None:
        src = _src("btf_viewer_pkg/investigation_notebook.py")
        self.assertNotIn("import ai_", src)
        self.assertNotIn("from .ai_", src)
        js = _src("web/src/utils/investigationNotebook.js")
        self.assertNotIn("aiClient", js)
        self.assertNotIn("aiCase", js)
        self.assertNotIn("aiTools", js)

    def test_projection_and_header_are_pure(self) -> None:
        inv = set_conclusion(
            add_bookmark(new_investigation(title="Q"), type="supporting",
                         title="120 migrations",
                         refs=[{"kind": "metric", "metric": "migrations"}]),
            "Confirmed: core thrash",
        )
        # No AI import is reachable — a plain call must succeed and be stable.
        secs1 = investigation_sections(inv)
        secs2 = investigation_sections(inv)
        self.assertEqual(secs1, secs2)
        self.assertEqual([s["id"] for s in secs1],
                         ["question", "scope", "hypotheses", "evidence",
                          "open_checks", "conclusion"])

    def test_notebook_header_has_no_ai_only_score(self) -> None:
        hdr = investigation_header(new_investigation(title="Q"))
        for k in hdr:
            self.assertNotIn("ai", k.lower(), k)
            self.assertNotIn("score", k.lower(), k)


class AiDoesNotWriteDurableNotebookStateTests(unittest.TestCase):
    _AI_SRC = (
        "btf_viewer_pkg/ai_assistant.py",
        "btf_viewer_pkg/ai_case.py",
        "btf_viewer_pkg/ai_tools.py",
        "btf_viewer_pkg/ai_investigation.py",
        "btf_viewer_pkg/ai_planner.py",
    )

    def test_ai_layer_never_imports_the_notebook_model(self) -> None:
        for rel in self._AI_SRC:
            src = _src(rel)
            self.assertNotIn("investigation_notebook", src, rel)
            self.assertNotIn("set_conclusion(", src, rel)
            self.assertNotIn("add_bookmark(", src, rel)

    def test_web_ai_layer_never_imports_the_notebook_model(self) -> None:
        for rel in ("web/src/utils/aiClient.js", "web/src/utils/aiCase.js",
                    "web/src/utils/aiTools.js"):
            src = _src(rel)
            self.assertNotIn("investigationNotebook", src, rel)


class FindingsStayDeterministicTests(unittest.TestCase):
    def test_findings_modules_import_no_ai(self) -> None:
        for rel in ("btf_viewer_pkg/findings_triage.py",
                    "btf_viewer_pkg/investigation_findings.py"):
            src = _src(rel)
            self.assertNotIn("from .ai_", src, rel)
            self.assertNotIn("import ai_", src, rel)

    def test_analysis_findings_are_a_pure_function_of_findings(self) -> None:
        from btf_viewer_pkg.findings_triage import sort_findings_triage
        rows = [
            {"severity": "warning", "title": "WCET spike", "text": "CS[28]"},
            {"severity": "error", "title": "Deadline breach", "text": "TaskA"},
        ]
        a = sort_findings_triage([dict(r) for r in rows])
        b = sort_findings_triage([dict(r) for r in rows])
        self.assertEqual(a, b)
        # deterministic ordering — error before warning
        self.assertEqual(a[0]["title"], "Deadline breach")


if __name__ == "__main__":
    unittest.main()
