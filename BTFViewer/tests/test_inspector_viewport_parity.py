"""Desktop ↔ Web lockstep for Migration Inspector analysis scope.

Source-string and extracted-helper checks only (no Qt import) so this stays
runnable when the rest of the desktop stack cannot start.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Tuple

BTF_ROOT = Path(__file__).resolve().parents[1]
STATS_PY = (BTF_ROOT / "btf_viewer_pkg" / "stats.py").read_text(encoding="utf-8")
MIG_JS = (BTF_ROOT / "web" / "src" / "utils" / "migrationAnalysis.js").read_text(
    encoding="utf-8")
CI_VUE = (BTF_ROOT / "web" / "src" / "components" / "CorridorInspectorDialog.vue"
          ).read_text(encoding="utf-8")
APP_VUE = (BTF_ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")
CHORD_VUE = (BTF_ROOT / "web" / "src" / "components" / "MiniChordPanel.vue"
             ).read_text(encoding="utf-8")
PLOT_VUE = (BTF_ROOT / "web" / "src" / "components" / "StatisticsPanel.vue"
            ).read_text(encoding="utf-8")
TIMELINE_VUE = (BTF_ROOT / "web" / "src" / "components" / "TimelinePanel.vue"
                ).read_text(encoding="utf-8")
PARSER_PY = (BTF_ROOT / "btf_viewer_pkg" / "parser.py").read_text(encoding="utf-8")


def _load_desktop_helpers() -> dict:
    m = re.search(
        r"(_INSPECTOR_FULL_VIEW_RATIO = 0\.92\n"
        r".*?"
        r"    return True, \"Viewport view\", detail\n)",
        STATS_PY,
        re.S,
    )
    if m is None:
        raise AssertionError(
            "could not extract inspector viewport helpers from stats.py")
    ns: dict = {
        "_format_time": lambda value, unit: f"{value}{unit}",
        "Tuple": Tuple,
    }
    exec(m.group(1), ns)  # noqa: S102 — isolated helper extract
    return ns


_HELPERS = _load_desktop_helpers()
_INSPECTOR_FULL_VIEW_RATIO = _HELPERS["_INSPECTOR_FULL_VIEW_RATIO"]
_inspector_viewport_is_full = _HELPERS["_inspector_viewport_is_full"]
_inspector_viewport_banner = _HELPERS["_inspector_viewport_banner"]


class InspectorViewportParityTests(unittest.TestCase):
    def test_full_view_ratio_matches_web(self) -> None:
        m = re.search(r"INSPECTOR_FULL_VIEW_RATIO = ([0-9.]+)", MIG_JS)
        self.assertIsNotNone(m)
        self.assertEqual(float(m.group(1)), _INSPECTOR_FULL_VIEW_RATIO)
        self.assertEqual(_INSPECTOR_FULL_VIEW_RATIO, 0.92)
        self.assertIn("return ratio >= 0.92", TIMELINE_VUE)

    def test_full_view_rules_match_in_source(self) -> None:
        self.assertIn(
            "if fit_mode or lo is None or hi is None:", STATS_PY)
        self.assertIn(
            "return (int(hi) - int(lo)) / span >= _INSPECTOR_FULL_VIEW_RATIO",
            STATS_PY)
        self.assertIn(
            "if (fitMode || lo == null || hi == null) return true", MIG_JS)
        self.assertIn(
            "return (Number(hi) - Number(lo)) / span >= INSPECTOR_FULL_VIEW_RATIO",
            MIG_JS)

    def test_analysis_scope_labels_match_web(self) -> None:
        for src in (STATS_PY, MIG_JS, PARSER_PY, CI_VUE):
            self.assertIn("Full Trace", src)
        self.assertIn("Cursor C1–Cn", STATS_PY)
        self.assertIn("Viewport", STATS_PY)
        self.assertIn('addItem("Follow zoom", "auto")', STATS_PY)
        self.assertIn('addItem("Viewport", "viewport")', STATS_PY)
        self.assertIn("value: 'auto', label: 'Follow zoom'", CI_VUE)
        self.assertIn("value: 'viewport', label: 'Viewport'", CI_VUE)
        self.assertIn("analysisMode = ref('auto')", CI_VUE)
        self.assertIn('_analysis_mode = "auto"', STATS_PY)
        self.assertIn("cursor_disabled_reason", PARSER_PY)
        self.assertIn("Place at least two cursors", PARSER_PY)
        self.assertNotIn("ci-scope-hint", CI_VUE)
        self.assertNotIn('QLabel("Place at least two cursors.")', STATS_PY)
        self.assertNotIn("_sync_scope_hint", STATS_PY)
        self.assertIn("inspectorAnalysisScope(", CI_VUE)
        self.assertIn("export function inspectorAnalysisScope", MIG_JS)
        self.assertIn("def _inspector_analysis_scope", PARSER_PY)
        self.assertIn("analysisScope.label", CI_VUE)

    def test_dialog_wires_explicit_analysis_scope(self) -> None:
        self.assertIn('setObjectName("ciScopeBanner")', STATS_PY)
        self.assertIn("_refresh_scope_banner", STATS_PY)
        self.assertIn("_inspector_analysis_scope(", STATS_PY)
        self.assertIn("class=\"ci-scope-banner\"", CI_VUE)
        self.assertIn("ci-scope-viewport", CI_VUE)
        self.assertIn("ci-scope-full", CI_VUE)
        self.assertIn(':viewport="timelineViewport"', APP_VUE)
        self.assertIn("Analysis Scope", CI_VUE)
        self.assertIn("Analysis Scope", STATS_PY)
        self.assertIn("Investigate with AI", CI_VUE)
        self.assertIn("Investigate with AI", STATS_PY)
        self.assertIn("Handoff suspects only", CI_VUE)
        self.assertIn("Handoff suspects only", STATS_PY)
        self.assertIn("Filter paths by task name or ID", CI_VUE)
        self.assertIn("Filter paths by task name or ID", STATS_PY)
        self.assertIn("Filter Inspector", CI_VUE)
        self.assertIn("Filter Inspector", STATS_PY)
        self.assertIn("_on_tree_header_clicked", STATS_PY)
        self.assertIn("_TREE_SORT_COLS", STATS_PY)
        self.assertIn("onHeadClick(col.key)", CI_VUE)
        self.assertIn("toggleTreeSort(key)", CI_VUE)
        self.assertIn("_pin_inspector_combo", STATS_PY)
        self.assertIn("_pin_inspector_combo(self._dir_combo, 108)", STATS_PY)
        self.assertIn("class _CiComboBox", STATS_PY)
        self.assertIn("def _ci_combo_menu_qss", STATS_PY)
        self.assertIn("def _ci_make_popup_menu", STATS_PY)
        self.assertIn("_sev_combo = _CiComboBox()", STATS_PY)
        self.assertIn("_style_inspector_field(combo)", STATS_PY)
        self.assertIn("def showPopup", STATS_PY)
        self.assertIn("menu.popup(", STATS_PY)
        self.assertIn("_pin_inspector_bounce", STATS_PY)
        self.assertIn("setView(QListView())", STATS_PY)
        self.assertNotIn("QListView(widget)", STATS_PY)
        self.assertIn("_CI_TREE_NUM_W = 56", PARSER_PY)
        self.assertIn("_CI_SPLIT_RATIO = (1, 2, 1)", PARSER_PY)
        self.assertIn("CI_SPLIT_RATIO = Object.freeze([1, 2, 1])", MIG_JS)
        self.assertIn("ResizeMode.Interactive", STATS_PY)
        self.assertIn("ci-col-resizer", CI_VUE)
        self.assertIn("ci-split-handle", CI_VUE)
        self.assertIn("_apply_split_layout", STATS_PY)
        self.assertIn('rc.set("inspector", "split_sizes"', STATS_PY)
        self.assertIn("inspectorSplit", CI_VUE)
        self.assertIn("_CORRIDOR_TREE_COLS", STATS_PY)
        self.assertIn("corridorTreeCell", CI_VUE)
        self.assertIn("rightPane = 'topology'", CI_VUE)
        self.assertIn("rightPane = 'info'", CI_VUE)
        self.assertIn("Path info", CI_VUE)
        self.assertIn("Path info", STATS_PY)
        self.assertIn('"Topology"', STATS_PY)
        self.assertNotIn("mainTab = 'activity'", CI_VUE)
        ci_cls = STATS_PY[
            STATS_PY.find("class _CorridorInspectorDialog"):
            STATS_PY.find("class _ChordDiagramDialog")]
        self.assertNotIn('QPushButton("Activity")', ci_cls)
        self.assertIn('QPushButton("Path info")', ci_cls)
        self.assertNotIn('QLabel("Sort by")', ci_cls)
        self.assertNotIn("_sort_combo", ci_cls)
        self.assertNotIn("ci-scope-note", CI_VUE)
        self.assertNotIn("ciScopeNote", STATS_PY)
        self.assertNotIn("inspectorViewportBanner(", CI_VUE)

    def test_show_events_jump_payload_lockstep(self) -> None:
        mw = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text(
            encoding="utf-8")
        self.assertIn('"binLo": bin_lo', STATS_PY)
        self.assertIn('"binHi": bin_hi', STATS_PY)
        self.assertIn('"lockTaskKey":', STATS_PY)
        self.assertIn('payload.get("binLo")', mw)
        self.assertIn('payload.get("binHi")', mw)
        self.assertIn("function onCorridorJump(payload)", APP_VUE)
        self.assertIn("payload.binLo", APP_VUE)
        self.assertIn("payload.binHi", APP_VUE)
        self.assertNotIn(
            "def _on_corridor_jump(self, bin_lo: int, bin_hi: int", mw)

    def test_inspector_layout_matches_web(self) -> None:
        """Desktop and Web share the same Inspector chrome order and labels."""
        vue_order = (
            "ci-overview",
            "ci-toolbar",
            "ci-scope-banner",
            "ci-filter-status",
            "ci-workspace",
            "ci-tree-pane",
            "ci-grid-pane",
            "ci-right-pane",
            "ci-footer",
        )
        vue_idx = []
        for name in vue_order:
            token = f'class="{name}"'
            i = CI_VUE.find(token)
            if i < 0:
                i = CI_VUE.find(name)
            vue_idx.append(i)
        self.assertTrue(all(i >= 0 for i in vue_idx), vue_idx)
        self.assertEqual(vue_idx, sorted(vue_idx))
        ci_py = STATS_PY[STATS_PY.find("class _CorridorInspectorDialog"):]
        desk_order = (
            "lay.addWidget(ov_wrap)",
            "lay.addWidget(tb_scroll)",
            "lay.addWidget(self._scope_banner)",
            "lay.addWidget(self._filter_bar)",
            "lay.addWidget(self._workspace, 1)",
        )
        desk_idx = [ci_py.find(s) for s in desk_order]
        self.assertTrue(all(i >= 0 for i in desk_idx), desk_idx)
        self.assertEqual(desk_idx, sorted(desk_idx))
        self.assertIn("self._workspace = QStackedWidget()", STATS_PY)
        self.assertIn("self._right_stack = QStackedWidget()", STATS_PY)
        self.assertIn("split.addWidget(self._right_wrap)", STATS_PY)
        self.assertIn("Path info", STATS_PY)
        self.assertIn("Path info", CI_VUE)
        self.assertIn('self._set_right_pane("info")', STATS_PY)
        self.assertIn("rightPane.value = 'info'", CI_VUE)
        self.assertIn("Select a core path to inspect ping-pong", STATS_PY)
        self.assertIn("Select a core path to inspect ping-pong", CI_VUE)
        self.assertIn("Show on timeline", STATS_PY)
        self.assertIn("Show on timeline", CI_VUE)
        self.assertIn("Migration activity over time", STATS_PY)
        self.assertIn("Migration activity over time", CI_VUE)
        self.assertIn("Color: migration count", STATS_PY)
        self.assertIn("Color: migration count", CI_VUE)
        self.assertIn("ci-heatmap-meta", CI_VUE)
        self.assertIn("Empty bins: no migrations in that interval", STATS_PY)
        self.assertIn("Empty bins: no migrations in that interval", CI_VUE)
        self.assertNotIn(
            "suspects ≥ {_CORRIDOR_HANDOFF_HATCH_PCT}% "
            "· Empty bins:",
            STATS_PY)
        self.assertIn("flex-wrap: nowrap", CI_VUE)
        self.assertIn("evidenceLinesText", CI_VUE)
        self.assertIn("${l.key}:  ${l.value}", CI_VUE)
        self.assertIn("_FlowLayout(btn_row", STATS_PY)
        self.assertIn('setObjectName("ciActionsRow")', STATS_PY)
        self.assertIn("ci-actions-row", CI_VUE)
        self.assertIn("ci-card-actions", CI_VUE)
        self.assertIn("flex-direction: column", CI_VUE)
        self.assertIn('QPushButton("Show events")', STATS_PY)
        self.assertIn('QPushButton("Filter timeline")', STATS_PY)
        self.assertIn('QPushButton("Inspect task")', STATS_PY)
        self.assertIn('QPushButton("Ask AI")', STATS_PY)
        self.assertIn("Filter timeline", STATS_PY)
        self.assertIn("Filter timeline", CI_VUE)
        self.assertIn("def _build_corridor_evidence", PARSER_PY)
        self.assertIn("export function buildCorridorEvidence", MIG_JS)
        self.assertNotIn('QPushButton("Jump To")', STATS_PY)
        self.assertNotIn('QLabel("Dock")', STATS_PY)
        self.assertNotIn("Inspect in Timeline", STATS_PY)
        self.assertNotIn("corridorInspectorSidebar", STATS_PY)
        self.assertNotIn("Click a corridor or chord ribbon to inspect.", STATS_PY)
        self.assertNotIn("Click a corridor or chord ribbon to inspect.", CI_VUE)
        self.assertNotIn("hatch: lock bounce", STATS_PY)
        self.assertNotIn("double-click to apply as Migration Filter", STATS_PY)
        self.assertIn("double-click to show events", STATS_PY)
        self.assertIn("double-click to show events", CI_VUE)
        self.assertIn("handoff suspect", STATS_PY)
        self.assertIn("handoff suspect", CI_VUE)
        self.assertIn("_HEAD_H = 28", STATS_PY)
        self.assertIn("GRID_HEAD_H = 28", CI_VUE)
        self.assertIn("onGridKeydown", CI_VUE)
        self.assertIn("def _handle_nav_key", STATS_PY)
        self.assertNotIn("viewportProgrammatic", CI_VUE)
        self.assertNotIn("_HINT_DEFAULT", STATS_PY)
        canvas_py = STATS_PY[
            STATS_PY.find("class _CorridorTimelineCanvas"):
            STATS_PY.find("class _CorridorTimelineGrid")]
        self.assertNotIn("lock bounce", canvas_py)
        ci_cls = STATS_PY[
            STATS_PY.find("class _CorridorInspectorDialog"):
            STATS_PY.find("class _ChordDiagramDialog")]
        tree_dbl = ci_cls[ci_cls.find("def _on_tree_dbl"):]
        tree_dbl = tree_dbl[:tree_dbl.find("\n    def ", 1)]
        self.assertIn("self._on_show_events()", tree_dbl)
        self.assertNotIn("_spotlight_corridor", tree_dbl)
        chord_dbl = ci_cls[ci_cls.find("def _on_chord_corridor_dbl"):]
        chord_dbl = chord_dbl[:chord_dbl.find("\n    def ", 1)]
        self.assertIn("self._on_show_events()", chord_dbl)
        self.assertNotIn("_spotlight_corridor", chord_dbl)

    def test_heatmap_banner_colors_match_distribution_chart(self) -> None:
        for token in ("#FF9800", "#1A1200", "#4E342E", "#FFF3E0"):
            self.assertIn(token, STATS_PY, token)
        self.assertIn("_apply_scope_banner(", STATS_PY)
        self.assertIn("def _set_scope_banner", STATS_PY)
        self.assertIn("badge.upper()", STATS_PY)
        self.assertIn("plot-scope-banner", PLOT_VUE)
        self.assertIn("plot-scope-cursor", PLOT_VUE)
        self.assertIn("plot-scope-full", PLOT_VUE)
        self.assertIn("border-left: 4px solid #ff9800", PLOT_VUE)
        self.assertIn("border-left: 4px solid #ff9800", CI_VUE)
        self.assertIn("background: #ff9800", PLOT_VUE)
        self.assertIn("background: #ff9800", CI_VUE)
        self.assertIn("color: #1a1200", PLOT_VUE)
        self.assertIn("color: #1a1200", CI_VUE)
        self.assertIn("color-mix(in srgb, #ff9800 18%, var(--panel-bg))", PLOT_VUE)
        self.assertIn("color-mix(in srgb, #ff9800 18%, var(--panel-bg))", CI_VUE)
        self.assertIn("text-transform: uppercase", PLOT_VUE)
        self.assertIn("text-transform: uppercase", CI_VUE)
        self.assertIn("def _hex_mix", STATS_PY)
        self.assertIn('"panel": "#252526"', STATS_PY)
        self.assertIn('"panel": "#F5F5F5"', STATS_PY)
        self.assertIn("IC.heatmap", CHORD_VUE)
        self.assertIn("IC.chord", CHORD_VUE)
        self.assertNotIn(">Circle<", CHORD_VUE)
        self.assertIn("AlignRight", STATS_PY)
        self.assertIn("_IC_HEATMAP", STATS_PY)
        self.assertIn("_IC_CHORD", STATS_PY)
        self.assertIn("ciCircleToggle", STATS_PY)
        self.assertIn("_matrix_pad_t", STATS_PY)
        self.assertIn("MATRIX_PAD_T = 64", CHORD_VUE)

    def test_inspector_hover_combo_and_web_drag_lockstep(self) -> None:
        self.assertIn("def _ci_button_qss", STATS_PY)
        self.assertIn("def _ci_toolbar_qss", STATS_PY)
        self.assertIn("QPushButton:hover", STATS_PY)
        self.assertIn("#ciFooter", STATS_PY)
        self.assertIn("#ciEvidence", STATS_PY)
        self.assertIn("combo_view", STATS_PY)
        self.assertIn("def _ci_combo_widget_qss", STATS_PY)
        self.assertIn("QAbstractItemView::item:hover", STATS_PY)
        self.assertIn("onHeaderPointerDown", CI_VUE)
        self.assertIn("dialogPos", CI_VUE)
        self.assertIn("ci-overlay-free", CI_VUE)
        self.assertIn("rgba(91, 155, 213, 0.18)", CI_VUE)
        self.assertIn("rgba(91, 155, 213, 0.22)", STATS_PY)
        self.assertIn("QPushButton:hover:!disabled", STATS_PY)
        self.assertIn(".ci-jump:hover:not(:disabled)", CI_VUE)
        self.assertIn(".ci-show-all:hover:not(:disabled)", CI_VUE)
        self.assertIn(".ci-show-all:disabled", CI_VUE)
        self.assertIn(".ci-jump:disabled", CI_VUE)
        self.assertIn("#ciFilterBar", STATS_PY)
        self.assertNotIn("ci-field-sort", CI_VUE)
        self.assertIn("setStretchFactor(0, 1)", STATS_PY)
        self.assertIn("setStretchFactor(1, 2)", STATS_PY)
        self.assertIn("setStretchFactor(2, 1)", STATS_PY)
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr))", CI_VUE)
        self.assertIn("const nLab = Math.max(2, Math.min(7", CI_VUE)
        self.assertIn("n_lab = max(2, min(7", STATS_PY)
        self.assertIn("_apply_split_layout", STATS_PY)
        self.assertIn("grid.addWidget(self._ov_mig, 0, 2)", STATS_PY)
        self.assertIn("self._ov_headline.setWordWrap(False)", STATS_PY)
        self.assertNotIn("ci-overview-concern", CI_VUE)
        self.assertNotIn("_ov_concern_detail", STATS_PY)
        self.assertIn('hover": "#E0E8F0"', STATS_PY)
        self.assertIn("combo_sel_fg", STATS_PY)
        self.assertIn("def _apply_ci_chrome", STATS_PY)
        self.assertIn("QApplication.instance()", STATS_PY)
        self.assertIn("plotBottom - 0.5", CI_VUE)
        self.assertIn("rgba(91, 155, 213, 0.35)", CI_VUE)
        self.assertIn("plot_bottom - 0.01", STATS_PY)
        self.assertIn("grid.setColumnStretch(0, 1)", STATS_PY)
        self.assertIn("self._ov_scope.setWordWrap(False)", STATS_PY)
        self.assertIn("#ciOverview {", STATS_PY)
        self.assertIn(
            'f" border-radius: 6px; padding: 8px 10px; }}"', STATS_PY)
        self.assertIn(".ci-toolbar .ci-field :deep(.dom-select)", CI_VUE)
        self.assertIn("border: 1px solid var(--border)", CI_VUE)

    def test_full_vs_viewport_rules_match(self) -> None:
        self.assertTrue(_inspector_viewport_is_full(None, None, 0, 1000, False))
        self.assertTrue(_inspector_viewport_is_full(10, 20, 0, 1000, True))
        self.assertFalse(_inspector_viewport_is_full(100, 200, 0, 1000, False))
        self.assertTrue(_inspector_viewport_is_full(0, 1000, 0, 1000, False))
        self.assertTrue(
            _inspector_viewport_is_full(0, 921, 0, 1000, False))
        self.assertFalse(
            _inspector_viewport_is_full(0, 919, 0, 1000, False))

    def test_banner_text_uses_the_visible_range(self) -> None:
        tr = SimpleNamespace(time_min=0, time_max=1_000_000, time_scale="ns")
        scoped, badge, detail = _inspector_viewport_banner(tr, None, None, False)
        self.assertFalse(scoped)
        self.assertEqual(badge, "Full view")
        self.assertIn("…", detail)
        scoped, badge, detail = _inspector_viewport_banner(
            tr, 10_000, 20_000, False)
        self.assertTrue(scoped)
        self.assertEqual(badge, "Viewport view")
        self.assertIn("10000ns", detail)
        scoped, badge, _ = _inspector_viewport_banner(tr, 10_000, 20_000, True)
        self.assertFalse(scoped)
        self.assertEqual(badge, "Full view")


if __name__ == "__main__":
    unittest.main()
