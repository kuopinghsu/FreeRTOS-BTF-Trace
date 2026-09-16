"""EvidenceTODO.md — move the Evidence export entry point out of the Marks
panel and onto Analysis Findings, on both Desktop and Web.

Covers:
  - btf_viewer_pkg/evidence_pack.py builds a real zip with the expected
    members / filename pattern (functional; mirrors
    web/tests/incidentEvidence.test.js's 'evidencePack' describe block).
  - Desktop's Python builder and Web's evidencePack.js builder stay in
    lockstep (same member names, README text, filename pattern) so a
    Desktop-built pack and a Web-built pack are interchangeable.
  - Desktop Marks panel never grows an Evidence button (P1.3: "Do not add
    it to the Desktop Marks panel").
  - Desktop's Analysis Findings "More" menu exposes "Export Evidence
    Pack…", wired to the new builder, and disabled while the findings
    context is stale.
  - Web's MarksPanel.vue no longer has the Evidence button/emit, and
    AnalysisFindingsDialog.vue does, wired through App.vue instead.
  - The unrelated Investigation Notebook "Evidence package…" action is
    untouched on both platforms (P1.4: keep the two workflows separate).
"""
from __future__ import annotations

import json
import re
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]

from btf_viewer_pkg.evidence_pack import build_evidence_pack_zip  # noqa: E402

MAINWINDOW = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text(encoding="utf-8")
STATS = (BTF_ROOT / "btf_viewer_pkg" / "stats.py").read_text(encoding="utf-8")
EVIDENCE_PACK_PY = (BTF_ROOT / "btf_viewer_pkg" / "evidence_pack.py").read_text(encoding="utf-8")
EVIDENCE_PACK_JS = (BTF_ROOT / "web" / "src" / "utils" / "evidencePack.js").read_text(encoding="utf-8")
MARKS_PANEL_VUE = (BTF_ROOT / "web" / "src" / "components" / "MarksPanel.vue").read_text(encoding="utf-8")
FINDINGS_DIALOG_VUE = (
    BTF_ROOT / "web" / "src" / "components" / "AnalysisFindingsDialog.vue"
).read_text(encoding="utf-8")
APP_VUE = (BTF_ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")


class BuildEvidencePackZipTests(unittest.TestCase):
    def test_builds_a_real_zip_with_findings_and_session(self) -> None:
        zip_bytes, filename = build_evidence_pack_zip(
            base_name="demo",
            findings_text="Analysis Findings\n",
            session_json='{"v":1}',
        )
        self.assertRegex(filename, r"^demo-evidence-.*\.zip$")
        self.assertGreater(len(zip_bytes), 20)
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            names = set(zf.namelist())
            self.assertIn("analysis-findings.txt", names)
            self.assertIn("session.json", names)
            self.assertIn("README.txt", names)
            self.assertNotIn("statistics-report.html", names)
            self.assertNotIn("notes.txt", names)
            self.assertEqual(
                zf.read("analysis-findings.txt").decode("utf-8"),
                "Analysis Findings\n")
            self.assertEqual(
                json.loads(zf.read("session.json")), {"v": 1})

    def test_optional_members_only_included_when_provided(self) -> None:
        zip_bytes, _ = build_evidence_pack_zip(
            base_name="demo", stats_html="<html></html>", notes="hi\n")
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            names = set(zf.namelist())
            self.assertIn("statistics-report.html", names)
            self.assertIn("notes.txt", names)
            self.assertNotIn("analysis-findings.txt", names)
            self.assertNotIn("session.json", names)

    def test_base_name_is_sanitized(self) -> None:
        _, filename = build_evidence_pack_zip(base_name="a/b c*d")
        self.assertTrue(filename.startswith("a_b_c_d-evidence-"), filename)

    def test_blank_base_name_falls_back(self) -> None:
        _, filename = build_evidence_pack_zip(base_name="")
        self.assertTrue(filename.startswith("btf-evidence-evidence-"), filename)

    def test_empty_findings_list_is_not_an_error(self) -> None:
        # P2 "Empty-state behavior": no findings under the current rules is
        # still a useful, exportable artifact.
        zip_bytes, filename = build_evidence_pack_zip(
            base_name="demo", findings_text="", session_json='{"v":1}')
        self.assertTrue(len(zip_bytes) > 0)
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            self.assertNotIn("analysis-findings.txt", zf.namelist())
            self.assertIn("session.json", zf.namelist())


class DesktopWebEvidencePackParityTests(unittest.TestCase):
    def test_member_names_match(self) -> None:
        for member in (
            "analysis-findings.txt", "session.json",
            "statistics-report.html", "notes.txt", "README.txt",
        ):
            self.assertIn(f'"{member}"', EVIDENCE_PACK_PY, member)
            self.assertIn(f"'{member}'", EVIDENCE_PACK_JS, member)

    def test_filename_pattern_matches(self) -> None:
        self.assertIn("-evidence-", EVIDENCE_PACK_PY)
        self.assertIn("-evidence-", EVIDENCE_PACK_JS)
        # Same UTC timestamp shape: YYYY-MM-DDTHH-MM-SS (19 chars).
        self.assertIn('"%Y-%m-%dT%H-%M-%S"', EVIDENCE_PACK_PY)
        self.assertIn(".slice(0, 19)", EVIDENCE_PACK_JS)

    def test_readme_text_matches(self) -> None:
        for line in (
            "BTFViewer evidence pack",
            "analysis-findings.txt — Analysis Findings snapshot",
            "session.json — portable session (marks, cursors, layout)",
        ):
            self.assertIn(line, EVIDENCE_PACK_PY, line)
            self.assertIn(line, EVIDENCE_PACK_JS, line)


class DesktopMarksPanelUnchangedTests(unittest.TestCase):
    def test_marks_io_row_has_no_evidence_button(self) -> None:
        # The six Marks buttons (Export/Import Marks, Clear B/A, Session,
        # Import Session) must never grow an "Evidence" entry (P1.3).
        marks_row = re.search(
            r"marks_io_row.*?(?=\n    def |\Z)", MAINWINDOW, re.DOTALL)
        self.assertIsNotNone(marks_row, "could not locate the Marks I/O row")
        self.assertNotIn('"Evidence', marks_row.group(0))


class DesktopAnalysisFindingsExportTests(unittest.TestCase):
    def test_more_menu_has_export_evidence_pack(self) -> None:
        self.assertIn(
            'more_menu.addAction("Export Evidence Pack…")', STATS,
            "Analysis Findings' More menu is missing Export Evidence Pack…",
        )
        self.assertIn(
            "self._export_evidence_action.triggered.connect(self._export_evidence_pack)",
            STATS,
        )

    def test_export_action_disabled_while_context_stale(self) -> None:
        self.assertRegex(
            STATS,
            r"export_action\.setEnabled\(not self\._ctx_stale\)",
            "Export Evidence Pack must be disabled while findings are stale",
        )

    def test_export_method_reuses_portable_session_and_findings_text(self) -> None:
        method = re.search(
            r"def _export_evidence_pack\(self\).*?(?=\n    def )", STATS, re.DOTALL)
        self.assertIsNotNone(method)
        body = method.group(0)
        self.assertIn("_build_portable_session_payload", body)
        self.assertIn("_format_analysis_findings_text", body)
        self.assertIn("build_evidence_pack_zip", body)


class WebMarksPanelEvidenceRemovedTests(unittest.TestCase):
    def test_evidence_button_removed(self) -> None:
        self.assertNotIn("exportEvidencePack", MARKS_PANEL_VUE)
        self.assertNotIn(">\n        Evidence\n      </button>", MARKS_PANEL_VUE)

    def test_remaining_marks_actions_untouched(self) -> None:
        for action in ("importMarks", "clearBookmarks", "clearAnnotations",
                       "exportSession", "importSession"):
            self.assertIn(action, MARKS_PANEL_VUE, action)


class WebAnalysisFindingsExportTests(unittest.TestCase):
    def test_emits_export_evidence_pack(self) -> None:
        self.assertIn("'export-evidence-pack'", FINDINGS_DIALOG_VUE)

    def test_more_menu_item_present_and_disabled_when_stale(self) -> None:
        self.assertIn("Export Evidence Pack…", FINDINGS_DIALOG_VUE)
        self.assertIn(':disabled="contextStale"', FINDINGS_DIALOG_VUE)

    def test_app_vue_wires_export_to_findings_not_marks(self) -> None:
        marks_block = re.search(
            r"<MarksPanel\b.*?/>", APP_VUE, re.DOTALL)
        findings_block = re.search(
            r"<AnalysisFindingsDialog\b.*?/>", APP_VUE, re.DOTALL)
        self.assertIsNotNone(marks_block)
        self.assertIsNotNone(findings_block)
        self.assertNotIn("export-evidence-pack", marks_block.group(0))
        self.assertIn(
            '@export-evidence-pack="onExportEvidencePack"',
            findings_block.group(0),
        )


class NotebookEvidencePackageUntouchedTests(unittest.TestCase):
    """P1.4: the Notebook's question-driven AI evidence JSON is a distinct
    workflow from Analysis Findings' portable evidence zip -- confirm both
    platforms still expose it, unmerged."""

    def test_desktop_notebook_evidence_package_still_present(self) -> None:
        self.assertIn('addAction("Evidence package…")', MAINWINDOW)
        self.assertIn("_emit_evidence_package", MAINWINDOW)

    def test_web_notebook_evidence_package_still_present(self) -> None:
        notebook_vue = (
            BTF_ROOT / "web" / "src" / "components" / "InvestigationNotebookDialog.vue"
        ).read_text(encoding="utf-8")
        self.assertIn("Evidence package…", notebook_vue)
        self.assertIn("emitEvidencePackage", notebook_vue)


import os  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from PySide6.QtWidgets import QApplication, QToolButton  # noqa: E402

from btf_viewer_pkg.stats import _AnalysisFindingsDialog  # noqa: E402


class AnalysisFindingsDialogExportActionGuiTests(unittest.TestCase):
    _app = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def _more_menu_actions(self, dlg):
        more_btn = next(
            b for b in dlg.findChildren(QToolButton)
            if "More" in b.text().replace("&", ""))
        return {
            a.text().replace("&", ""): a for a in more_btn.menu().actions()
        }

    def test_export_action_present_and_enabled_by_default(self) -> None:
        findings = [{"severity": "warning", "title": "Load imbalance", "text": "x"}]
        dlg = _AnalysisFindingsDialog(
            findings, "", ai_enabled=False,
            analysis_context={"traceName": "t.btf"},
            on_recalculate=lambda: (findings, "", {"traceName": "t.btf"}),
        )
        try:
            acts = self._more_menu_actions(dlg)
            self.assertIn("Export Evidence Pack…", acts)
            self.assertTrue(acts["Export Evidence Pack…"].isEnabled())
        finally:
            dlg.deleteLater()

    def test_export_action_disabled_once_context_marked_stale(self) -> None:
        findings = [{"severity": "warning", "title": "Load imbalance", "text": "x"}]
        dlg = _AnalysisFindingsDialog(
            findings, "", ai_enabled=False,
            analysis_context={"traceName": "t.btf"},
            on_recalculate=lambda: (findings, "", {"traceName": "t.btf"}),
        )
        try:
            acts = self._more_menu_actions(dlg)
            self.assertTrue(acts["Export Evidence Pack…"].isEnabled())
            dlg._mark_context_stale()
            self.assertFalse(acts["Export Evidence Pack…"].isEnabled())
        finally:
            dlg.deleteLater()


import tempfile  # noqa: E402
from pathlib import Path as _Path  # noqa: E402
from unittest.mock import patch  # noqa: E402

from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402
from btf_viewer_pkg.parser import _parse_btf  # noqa: E402

EXAMPLE_2CORE = BTF_ROOT.parent / "tracedata" / "example-2cores.btf.gz"


def _destroy(win) -> None:
    try:
        win.close()
        win.deleteLater()
    except Exception:
        pass


class ExportEvidencePackEndToEndTests(unittest.TestCase):
    """Full flow through the real MainWindow, matching how
    _AnalysisFindingsDialog._export_evidence_pack() reaches self.parent()
    for _build_portable_session_payload() / _current_file."""

    _app = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        if not EXAMPLE_2CORE.is_file():
            self.skipTest(f"missing {EXAMPLE_2CORE}")

    def test_export_evidence_pack_writes_a_real_zip(self) -> None:
        trace = _parse_btf(str(EXAMPLE_2CORE))
        win = MainWindow()
        self.addCleanup(_destroy, win)
        tab = win._add_trace_tab(str(EXAMPLE_2CORE), trace)
        tab.view.load_trace(trace)
        win._tab_widget.setCurrentIndex(0)
        for _ in range(3):
            self._app.processEvents()

        win._open_analysis_findings()
        dlg = win._analysis_findings_dlg
        self.assertIsNotNone(dlg)
        self.addCleanup(dlg.deleteLater)

        with tempfile.TemporaryDirectory() as tmp:
            out_path = str(_Path(tmp) / "pack.zip")
            with patch(
                "btf_viewer_pkg.stats.QFileDialog.getSaveFileName",
                return_value=(out_path, ""),
            ):
                dlg._export_evidence_pack()
            self.assertTrue(_Path(out_path).is_file())
            with zipfile.ZipFile(out_path) as zf:
                names = set(zf.namelist())
                self.assertIn("analysis-findings.txt", names)
                self.assertIn("session.json", names)
                self.assertIn("README.txt", names)
                session = json.loads(zf.read("session.json"))
                self.assertIn("timelineOptions", session)
                self.assertIn("cursors", session)


if __name__ == "__main__":
    unittest.main()
