"""Unit tests for Statistics HTML Analysis Findings."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

import tests  # noqa: F401,E402 — applies QT_QPA_PLATFORM=offscreen

from btf_viewer_pkg.stats import (  # noqa: E402
    _build_workflow_analysis_findings,
    _format_analysis_findings_text,
    _render_workflow_analysis_html,
)


class WorkflowAnalysisFindingsTest(unittest.TestCase):
    def test_load_imbalance_and_thrashing(self):
        # Uneven cores (σ > 30%) + thrashing migration + hot bounce pair
        findings = _build_workflow_analysis_findings(
            core_rows=[("Core_0", 80.0), ("Core_1", 10.0), ("Core_2", 5.0), ("Core_3", 5.0)],
            exec_rows=[
                # mk, name, runs, cpu, min, avg, tmean, max, jitter, σ, p50, p95
                ("mk1", "Worker", 100, 40.0, "1us", "2us", "2us", "10us",
                 "9us", "3us", "2us", "8us"),
            ],
            block_rows=[],
            mig_rows=[
                (
                    "mk1", "ThrashTask", 25, 2, "Core_0, Core_1", "Core_0", 40.0,
                    5, 0, "-", "-", "2.5/s", 2.5, "50us", 50,
                ),
            ],
            pair_rows=[
                ("Core_0", "Core_1", 20, 10, 1000),
            ],
            priority_rows=[],
            sync_rows=[],
            sync_issues=[],
            tick={"tick_count": 0},
            deadline_viols=None,
            time_scale="us",
        )
        titles = [f["title"] for f in findings]
        self.assertIn("Load imbalance across cores", titles)
        self.assertIn("Excessive core migration", titles)
        self.assertIn("Hot core-pair migration traffic", titles)
        self.assertIn("Highest CPU consumers", titles)
        load = next(f for f in findings if f["title"].startswith("Load imbalance"))
        self.assertEqual(load["severity"], "warning")
        self.assertNotIn("workflow", load)

    def test_low_score_warns_even_when_sigma_below_30(self):
        # Score ≈ 59% (G≈0.41), σ≈24% — previously mislabeled as "reasonably balanced"
        findings = _build_workflow_analysis_findings(
            core_rows=[
                ("Core_0", 55.0), ("Core_1", 40.0), ("Core_2", 30.0), ("Core_3", 20.0),
                ("Core_4", 15.0), ("Core_5", 10.0), ("Core_6", 5.0), ("Core_7", 2.0),
            ],
            exec_rows=[],
            block_rows=[],
            mig_rows=[],
            pair_rows=[],
            priority_rows=[],
            sync_rows=[],
            sync_issues=[],
            tick={"tick_count": 0},
        )
        load = next(f for f in findings if "balance" in f["title"].lower() or "imbalance" in f["title"].lower())
        self.assertEqual(load["severity"], "warning")
        self.assertIn("Load imbalance", load["title"])
        self.assertNotIn("reasonably balanced", load["text"])

    def test_balanced_cores_include_score_metrics(self):
        findings = _build_workflow_analysis_findings(
            core_rows=[("Core_0", 40.0), ("Core_1", 40.0), ("Core_2", 40.0)],
            exec_rows=[],
            block_rows=[],
            mig_rows=[],
            pair_rows=[],
            priority_rows=[],
            sync_rows=[],
            sync_issues=[],
            tick={"tick_count": 0},
        )
        load = next(f for f in findings if f.get("id") == "load_balance_ok")
        self.assertEqual(load["severity"], "info")
        self.assertEqual(load["title"], "Core utilisation balance")
        self.assertIn("Load Balance Score", load["text"])
        self.assertIn("σ=", load["text"])
        self.assertIn("G=", load["text"])
        self.assertIn("reasonably balanced", load["text"])

    def test_no_load_finding_for_one_core_or_zero_util(self):
        for cores in (
            [("Core_0", 40.0)],
            [("Core_0", 0.0), ("Core_1", 0.0)],
        ):
            findings = _build_workflow_analysis_findings(
                core_rows=cores,
                exec_rows=[],
                block_rows=[],
                mig_rows=[],
                pair_rows=[],
                priority_rows=[],
                sync_rows=[],
                sync_issues=[],
                tick={"tick_count": 0},
            )
            self.assertFalse(
                any("balance" in f["title"].lower() for f in findings),
                cores,
            )

    def test_priority_lmh_uses_pattern_index(self):
        findings = _build_workflow_analysis_findings(
            core_rows=[("Core_0", 50.0), ("Core_1", 50.0)],
            exec_rows=[],
            block_rows=[],
            mig_rows=[],
            pair_rows=[],
            priority_rows=[
                ("mk", "LowTask", 1, 10, 2, "100us", "—", "—",
                 "L/M/H pattern", 100, 0, 0),
            ],
            sync_rows=[],
            sync_issues=[],
            tick={"tick_count": 0},
        )
        inv = [f for f in findings if "Priority inversion" in f["title"]]
        self.assertEqual(len(inv), 1)
        self.assertIn("LowTask", inv[0]["text"])

    def test_priority_inherit_lmh_counts_as_inversion_finding(self):
        """Mutex inherit + L/M/H aggregate must feed the PI finding (not only plain L/M/H)."""
        findings = _build_workflow_analysis_findings(
            core_rows=[("Core_0", 50.0), ("Core_1", 50.0)],
            exec_rows=[],
            block_rows=[],
            mig_rows=[],
            pair_rows=[],
            priority_rows=[
                ("mk_low", "Low[266]", 2, 4, 3, "100ms", "—", "—",
                 "Mutex inherit + L/M/H", 100, 0, 0),
                ("mk_ps", "PS[228]", 2, 4, 1, "120us", "—", "—",
                 "L/M/H pattern", 120, 0, 0),
            ],
            sync_rows=[],
            sync_issues=[],
            tick={"tick_count": 0},
        )
        inv = [f for f in findings if "Priority inversion" in f["title"]]
        self.assertEqual(len(inv), 1)
        self.assertIn("Low[266]", inv[0]["text"])
        self.assertIn("PS[228]", inv[0]["text"])

    def test_render_html_contains_section(self):
        findings = [
            {
                "severity": "warning",
                "title": "Load imbalance across cores",
                "text": "σ high",
            },
        ]
        html_out = _render_workflow_analysis_html(findings, " (cursor range C1–C2)")
        self.assertIn("Analysis Findings", html_out)
        self.assertIn("analysis-findings", html_out)
        self.assertIn("finding-card", html_out)
        self.assertIn("sev-warning", html_out)
        self.assertNotIn("WORKFLOWS", html_out)

    def test_format_findings_text(self):
        text = _format_analysis_findings_text(
            [{"severity": "warning", "title": "Load imbalance", "text": "σ high"}],
            " (scoped)",
        )
        self.assertIn("Analysis Findings (scoped)", text)
        self.assertIn("[WARNING] Load imbalance", text)
        self.assertIn("σ high", text)

    def test_empty_scope_info_finding(self):
        findings = _build_workflow_analysis_findings(
            core_rows=[],
            exec_rows=[],
            block_rows=[],
            mig_rows=[],
            pair_rows=[],
            priority_rows=[],
            sync_rows=[],
            sync_issues=[],
            tick={"tick_count": 0},
        )
        self.assertTrue(any(f["title"].startswith("No analysis heuristics") for f in findings))

    def test_analysis_dialog_uses_ui_font_size(self):
        from PySide6.QtWidgets import QApplication, QListWidgetItem
        from btf_viewer_pkg.config import UI_FONT_SIZE, _application_ui_font
        from btf_viewer_pkg.stats import _AnalysisFindingsDialog

        if QApplication.instance() is None:
            QApplication([])
        findings = [{"severity": "info", "title": "Tick OK", "text": "steady"}]
        dlg = _AnalysisFindingsDialog(
            findings, "", ai_enabled=False, ui_font_size=UI_FONT_SIZE)
        expected = _application_ui_font(UI_FONT_SIZE)
        item = dlg._list_w.item(0)
        self.assertIsInstance(item, QListWidgetItem)
        # Must track Settings → Display → UI font (not a hard-coded 11pt floor).
        self.assertEqual(item.font().pointSize(), expected.pointSize())
        self.assertEqual(item.font().pixelSize(), expected.pixelSize())
        self.assertEqual(dlg.font().pointSize(), expected.pointSize())
        self.assertEqual(dlg.font().pixelSize(), expected.pixelSize())

    def test_analysis_dialog_selects_first_finding_on_open(self):
        """Web shows the first finding's detail on open; desktop must too."""
        from PySide6.QtWidgets import QApplication
        from btf_viewer_pkg.stats import _AnalysisFindingsDialog

        if QApplication.instance() is None:
            QApplication([])
        findings = [
            {"id": "f1", "severity": "warning", "title": "Load imbalance",
             "observation": "Core 0 hot", "why_it_matters": "uneven work"},
            {"id": "f2", "severity": "info", "title": "Tick OK", "text": "steady"},
        ]
        dlg = _AnalysisFindingsDialog(findings, "", ai_enabled=False)
        self.addCleanup(dlg.deleteLater)

        sel = dlg._selected_finding()
        self.assertIsNotNone(sel)
        self.assertEqual(sel.get("id"), "f1")
        # Detail pane populated, not the empty hint (dialog never shown, so
        # use isVisibleTo() which reflects the explicit setVisible() calls).
        self.assertFalse(dlg._detail_empty.isVisibleTo(dlg))
        self.assertTrue(dlg._detail_title.isVisibleTo(dlg))
        self.assertIn("Load imbalance", dlg._detail_title.text())
        self.assertTrue(dlg._detail_body.text().strip())

    def test_analysis_dialog_add_to_case_is_undoable(self):
        from PySide6.QtWidgets import QApplication
        from btf_viewer_pkg.stats import _AnalysisFindingsDialog

        if QApplication.instance() is None:
            QApplication([])
        findings = [{"id": "f1", "severity": "warning", "title": "Load imbalance",
                     "observation": "hot", "why_it_matters": "x"}]
        dlg = _AnalysisFindingsDialog(findings, "", ai_enabled=False)
        self.addCleanup(dlg.deleteLater)

        dlg._add_to_case()
        self.assertIn("f1", dlg._triage_state.get("case") or [])

        # In the Case queue the finding is selectable and the button offers the
        # undo: it stays enabled and reads "Remove from case".
        dlg._set_queue(dlg._QUEUE_CASE)
        self.assertEqual((dlg._selected_finding() or {}).get("id"), "f1")
        self.assertTrue(dlg._case_btn.isEnabled())
        self.assertEqual(dlg._case_btn.text(), "Remove from case")

        # Clicking it undoes the add.
        dlg._add_to_case()
        self.assertNotIn("f1", dlg._triage_state.get("case") or [])

    def test_analysis_dialog_divider_ratio_persists_to_rc(self):
        import os
        import tempfile
        from PySide6.QtWidgets import QApplication, QSplitter, QWidget
        from btf_viewer_pkg import stats as _stats
        from btf_viewer_pkg.stats import (
            _AnalysisFindingsDialog, _SeamSplitterHandle,
        )
        from btf_viewer_pkg.view import _ResizeSplitter

        if QApplication.instance() is None:
            QApplication([])

        tmp = tempfile.mkdtemp()
        rc_path = os.path.join(tmp, "btf_viewer.rc")
        old = _stats._RcSettings.RC_PATH
        _stats._RcSettings.RC_PATH = rc_path
        self.addCleanup(setattr, _stats._RcSettings, "RC_PATH", old)
        rc = _stats._RcSettings()
        rc.set("analysis_findings", "split_sizes", "300,700", flush=True)

        host = QWidget()
        host._settings = rc
        self.addCleanup(host.deleteLater)

        dlg = _AnalysisFindingsDialog([], "", parent=host, ai_enabled=False)
        self.addCleanup(dlg.deleteLater)

        # Divider matches the timeline/stats seam: 8px transparent hit
        # target, thin accent bar on hover (resize-cursor handle).
        self.assertIsInstance(dlg._split, _ResizeSplitter)
        self.assertEqual(dlg._split.handleWidth(), 8)
        self.assertIn("transparent", dlg._split.styleSheet())
        # Handle paints its own hover bar (Qt ::handle:hover QSS is unreliable).
        handle = dlg._split.handle(1)
        self.assertIsInstance(handle, _SeamSplitterHandle)
        handle._hover = True
        handle.grab()  # forces paintEvent; must not raise with hover on
        # Saved ratio restored from btf_viewer.rc.
        self.assertEqual(dlg._split_ratio, [300, 700])

        # A drag writes the live pane sizes back to the same rc section
        # (exact px depend on layout; assert a valid 2-int csv round-trips).
        dlg._save_split_ratio()
        saved = _stats._RcSettings().get("analysis_findings", "split_sizes", "")
        parts = [int(p) for p in saved.split(",") if p.strip()]
        self.assertEqual(len(parts), 2)
        self.assertTrue(all(p > 0 for p in parts))

    def test_analysis_dialog_combos_use_inspector_popup(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        from btf_viewer_pkg.stats import (
            _AnalysisFindingsDialog, _CiComboBox, _CI_FIELD_H,
            _ci_combo_widget_qss,
        )

        if QApplication.instance() is None:
            QApplication([])
        dlg = _AnalysisFindingsDialog([], "", ai_enabled=False)
        dlg.show()
        QApplication.processEvents()
        for combo in (dlg._sev_combo, dlg._ev_combo, dlg._cat_combo, dlg._sort_combo):
            self.assertIsInstance(combo, _CiComboBox)
            self.assertEqual(combo.styleSheet(), _ci_combo_widget_qss(combo))
            self.assertGreaterEqual(combo.minimumHeight(), _CI_FIELD_H)
        combo = dlg._sev_combo
        combo.showPopup()
        QApplication.processEvents()
        menu = combo._popup_menu
        self.assertIsNotNone(menu)
        self.assertTrue(bool(menu.windowFlags() & Qt.WindowType.Popup))
        self.assertTrue(
            bool(dlg.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))
        self.assertTrue(
            bool(menu.windowFlags() & Qt.WindowType.WindowStaysOnTopHint),
            "Analysis Tool window would cover a menu that is not stays-on-top")
        self.assertGreaterEqual(menu.width(), combo.width())
        combo.hidePopup()
        dlg.close()
        QApplication.processEvents()

    def test_analysis_dialog_query_with_ai_button(self):
        from PySide6.QtWidgets import QApplication, QToolButton, QLabel
        from btf_viewer_pkg.stats import _AnalysisFindingsDialog

        if QApplication.instance() is None:
            QApplication([])
        findings = [{"severity": "warning", "title": "Load imbalance", "text": "σ high"}]
        dlg = _AnalysisFindingsDialog(findings, " (scoped)", ai_enabled=True)
        tool_labels = [b.text().replace("&", "") for b in dlg.findChildren(QToolButton)]
        self.assertIn("Ask AI ▾", tool_labels)
        self.assertIn("More ▾", tool_labels)
        ask_btn = next(
            b for b in dlg.findChildren(QToolButton)
            if "Ask AI" in b.text().replace("&", "")
        )
        acts = {
            a.text().replace("&", ""): a
            for a in ask_btn.menu().actions()
            if not a.isSeparator() and a.menu() is None
        }
        self.assertIn("Query findings…", acts)
        self.assertFalse(dlg.wants_ai_query)
        acts["Query findings…"].trigger()
        self.assertTrue(dlg.wants_ai_query)
        self.assertEqual(dlg.wants_ai_template, "findings")
        self.assertFalse(dlg._ai_needs_settings)
        more_btn = next(
            b for b in dlg.findChildren(QToolButton)
            if "More" in b.text().replace("&", "")
        )
        more_acts = {
            a.text().replace("&", ""): a for a in more_btn.menu().actions()
        }
        self.assertIn("Save as text…", more_acts)

    def test_analysis_dialog_light_theme_detail_ink(self):
        from PySide6.QtWidgets import QApplication, QLabel
        from btf_viewer_pkg.stats import _AnalysisFindingsDialog

        if QApplication.instance() is None:
            QApplication([])
        findings = [{"severity": "info", "title": "Tick OK", "text": "steady"}]
        dlg = _AnalysisFindingsDialog(
            findings, "", ai_enabled=False, is_dark=False)
        # Master/detail: row 0 auto-selects and populates the right-hand pane.
        body = dlg.findChild(QLabel, "analysisFindingText")
        self.assertIsNotNone(body)
        self.assertIn("steady", body.text())
        self.assertIn("color: #1E1E1E", body.styleSheet())
        self.assertNotIn("#c5d0dc", body.styleSheet())
        row_title = dlg.findChild(QLabel, "analysisFindingTitle")
        self.assertIsNotNone(row_title)
        self.assertIn("color: #1E1E1E", row_title.styleSheet())

    def test_analysis_dialog_balance_ok_shows_metrics_and_light_ok_ink(self):
        from PySide6.QtWidgets import QApplication, QLabel
        from btf_viewer_pkg.stats import _AnalysisFindingsDialog

        if QApplication.instance() is None:
            QApplication([])
        findings = [{
            "id": "load_balance_ok",
            "severity": "info",
            "title": "Core utilisation balance",
            "text": "Load Balance Score 100% (σ=0.0%, G=0.000) — cores look reasonably balanced.",
        }]
        dlg = _AnalysisFindingsDialog(
            findings, "", ai_enabled=False, is_dark=False)
        title = dlg.findChild(QLabel, "analysisFindingTitle")   # left-pane row
        body = dlg.findChild(QLabel, "analysisFindingText")     # right-pane detail
        self.assertIsNotNone(title)
        self.assertIsNotNone(body)
        self.assertIn("Core utilisation balance", title.text())
        self.assertIn("Load Balance Score 100%", body.text())
        self.assertIn("color: #166534", body.styleSheet())
        self.assertNotIn("#c5d0dc", body.styleSheet())
        self.assertNotIn("#d68910", body.styleSheet())

    def test_analysis_dialog_auto_investigate_button(self):
        from PySide6.QtWidgets import QApplication, QToolButton
        from btf_viewer_pkg.stats import _AnalysisFindingsDialog

        if QApplication.instance() is None:
            QApplication([])
        findings = [{"id": "f1", "severity": "warning", "title": "Load imbalance", "text": "σ high"}]
        dlg = _AnalysisFindingsDialog(findings, " (scoped)", ai_enabled=True)
        dlg._list_w.setCurrentRow(0)
        ask_btn = next(
            b for b in dlg.findChildren(QToolButton)
            if "Ask AI" in b.text().replace("&", "")
        )
        acts = {
            a.text().replace("&", ""): a
            for a in ask_btn.menu().actions()
            if a.menu() is None
        }
        self.assertIn("Auto investigate…", acts)
        acts["Auto investigate…"].trigger()
        self.assertTrue(dlg.wants_ai_query)
        self.assertEqual(dlg.wants_ai_template, "auto_investigate")
        self.assertEqual(dlg.wants_ai_finding_id, "f1")

    def test_analysis_dialog_explain_levels(self):
        from PySide6.QtWidgets import QApplication, QToolButton
        from btf_viewer_pkg.stats import _AnalysisFindingsDialog

        if QApplication.instance() is None:
            QApplication([])
        findings = [{"id": "f1", "severity": "warning", "title": "Load imbalance", "text": "σ high"}]
        dlg = _AnalysisFindingsDialog(findings, " (scoped)", ai_enabled=True)
        dlg._list_w.setCurrentRow(0)
        ask_btn = next(
            b for b in dlg.findChildren(QToolButton)
            if "Ask AI" in b.text().replace("&", "")
        )
        explain = next(
            a for a in ask_btn.menu().actions()
            if a.menu() is not None and "Explain" in a.text().replace("&", "")
        )
        acts = {a.text().replace("&", ""): a for a in explain.menu().actions()}
        self.assertIn("Quick", acts)
        self.assertIn("Technical", acts)
        self.assertIn("Deep", acts)
        acts["Deep"].trigger()
        self.assertTrue(dlg.wants_ai_query)
        self.assertEqual(dlg.wants_ai_template, "explain_finding")
        self.assertEqual(dlg.wants_ai_level, "deep")
        self.assertEqual(dlg.wants_ai_finding_id, "f1")

    def test_analysis_dialog_query_ai_opens_settings_when_disabled(self):
        from PySide6.QtWidgets import QApplication, QToolButton
        from btf_viewer_pkg.stats import _AnalysisFindingsDialog

        if QApplication.instance() is None:
            QApplication([])
        dlg = _AnalysisFindingsDialog([], "", ai_enabled=False)
        ask_btn = next(
            b for b in dlg.findChildren(QToolButton)
            if "Ask AI" in b.text().replace("&", "")
        )
        acts = {
            a.text().replace("&", ""): a
            for a in ask_btn.menu().actions()
            if a.menu() is None
        }
        acts["Query findings…"].trigger()
        self.assertTrue(dlg.wants_ai_query)
        self.assertTrue(dlg._ai_needs_settings)

    def test_compare_dialog_query_with_ai_button(self):
        from types import SimpleNamespace

        from PySide6.QtWidgets import QApplication, QPushButton
        from btf_viewer_pkg.stats import _TraceCompareDialog

        if QApplication.instance() is None:
            QApplication([])
        called = []
        validated = []
        win = SimpleNamespace(_tabs=[
            SimpleNamespace(path="/tmp/a.btf", trace=None),
            SimpleNamespace(path="/tmp/b.btf", trace=None),
        ])
        dlg = _TraceCompareDialog(
            win, ai_enabled=True,
            on_query_ai=lambda enabled, a, b: called.append((enabled, a, b)),
            on_validate_experiment=lambda enabled, a, b: validated.append(
                (enabled, a, b)),
        )
        labels = [b.text().replace("&", "") for b in dlg.findChildren(QPushButton)]
        self.assertIn("Ask AI about this", labels)
        self.assertIn("Validate experiment…", labels)
        ai_btn = next(
            b for b in dlg.findChildren(QPushButton)
            if "Ask AI about this" in b.text().replace("&", "")
        )
        self.assertIn("Trace Compare", ai_btn.toolTip())
        ai_btn.click()
        self.assertEqual(called, [(True, 0, 1)])
        self.assertEqual(validated, [])
        labels = [dlg._pages.tabText(i) for i in range(dlg._pages.count())]
        self.assertIn("Response", labels)
        self.assertIn("Mutex", labels)

    def test_compare_dialog_query_with_ai_passes_selected_section(self):
        from types import SimpleNamespace

        from PySide6.QtWidgets import QApplication, QPushButton
        from btf_viewer_pkg.stats import _TraceCompareDialog

        if QApplication.instance() is None:
            QApplication([])
        called = []
        win = SimpleNamespace(_tabs=[
            SimpleNamespace(path="/tmp/a.btf", trace=None),
            SimpleNamespace(path="/tmp/b.btf", trace=None),
        ])
        dlg = _TraceCompareDialog(
            win, ai_enabled=True,
            on_query_ai=lambda enabled, a, b, section="": called.append(
                (enabled, a, b, section)),
            on_validate_experiment=lambda *a: None,
        )
        sync_idx = next(
            i for i in range(dlg._pages.count())
            if dlg._pages.tabText(i) == "Sync"
        )
        dlg._pages.setCurrentIndex(sync_idx)
        ai_btn = next(
            b for b in dlg.findChildren(QPushButton)
            if "Ask AI about this" in b.text().replace("&", "")
        )
        ai_btn.click()
        self.assertEqual(called, [(True, 0, 1, "Sync")])

    def test_compare_dialog_validate_experiment_button(self):
        from types import SimpleNamespace

        from PySide6.QtWidgets import QApplication, QPushButton
        from btf_viewer_pkg.stats import _TraceCompareDialog

        if QApplication.instance() is None:
            QApplication([])
        called = []
        validated = []
        win = SimpleNamespace(_tabs=[
            SimpleNamespace(path="/tmp/a.btf", trace=None),
            SimpleNamespace(path="/tmp/b.btf", trace=None),
        ])
        dlg = _TraceCompareDialog(
            win, ai_enabled=True,
            on_query_ai=lambda enabled, a, b: called.append((enabled, a, b)),
            on_validate_experiment=lambda enabled, a, b: validated.append(
                (enabled, a, b)),
        )
        btn = next(
            b for b in dlg.findChildren(QPushButton)
            if "Validate experiment" in b.text().replace("&", "")
        )
        self.assertIn("expected vs actual", btn.toolTip())
        btn.click()
        self.assertEqual(validated, [(True, 0, 1)])
        self.assertEqual(called, [])

    def test_compare_dialog_investigate_side_opens_stats(self):
        from types import SimpleNamespace

        from PySide6.QtWidgets import QApplication, QPushButton
        from btf_viewer_pkg.stats import _TraceCompareDialog

        if QApplication.instance() is None:
            QApplication([])
        calls = []

        def investigate_compare_side(idx, **kwargs):
            calls.append((idx, kwargs))

        win = SimpleNamespace(
            _tabs=[
                SimpleNamespace(path="/tmp/a.btf", trace=None),
                SimpleNamespace(path="/tmp/b.btf", trace=None),
            ],
            _tab_widget=SimpleNamespace(setCurrentIndex=lambda _i: None),
            _investigate_compare_side=investigate_compare_side,
        )
        dlg = _TraceCompareDialog(win, ai_enabled=False)
        dlg._investigate_target = {
            "section_id": "response",
            "section": "response",
            "task": "T1",
            "section_label": "Response Time",
            "label": "T1 response p99",
        }
        labels = {b.text().replace("&", "") for b in dlg.findChildren(QPushButton)}
        self.assertNotIn("Investigate on Baseline", labels)
        self.assertNotIn("Investigate on Candidate", labels)
        # Summary tab page is a _CompareScrollPage wrapping a scrollable body.
        self.assertIs(dlg._decision.parent(), dlg._pages.widget(0).widget())
        self.assertTrue(dlg._summary_table.isSortingEnabled())
        self.assertTrue(dlg._summary_table.horizontalHeader().sectionsClickable())
        dlg._investigate_side("b")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], 1)
        self.assertEqual(calls[0][1]["section_id"], "response")
        self.assertEqual(calls[0][1]["task"], "T1")
        self.assertEqual(calls[0][1]["tab_name"], "b.btf")


if __name__ == "__main__":
    unittest.main()
