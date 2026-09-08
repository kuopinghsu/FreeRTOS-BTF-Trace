"""Scope-label consistency + multi-state action disclosure
(BTFVIEWER_DESIGN_CONSISTENCY_TODO — "P1 — Scope clarity without another scope model").

- The three scope controls read `Statistics Scope` (`Limit to C1–Cn`),
  `Inspector Scope`, and `Compare Scope`.
- The Corridor Inspector's `Focus this window` action discloses every change it
  makes before it is activated.
- `Show Evidence` / Notebook `Jump to evidence` stay navigation-only (unchanged
  by this step — Operation Flow already guards them).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
STATS_PY = (BTF_ROOT / "btf_viewer_pkg" / "stats.py").read_text(encoding="utf-8")
PARSER_PY = (BTF_ROOT / "btf_viewer_pkg" / "parser.py").read_text(encoding="utf-8")
CI_VUE = (BTF_ROOT / "web" / "src" / "components" / "CorridorInspectorDialog.vue").read_text(encoding="utf-8")
CMP_VUE = (BTF_ROOT / "web" / "src" / "components" / "TraceCompareDialog.vue").read_text(encoding="utf-8")
MIG_JS = (BTF_ROOT / "web" / "src" / "utils" / "migrationAnalysis.js").read_text(encoding="utf-8")
APP_VUE = (BTF_ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")
MW_PY = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text(encoding="utf-8")

_FOCUS_CHANGES = (
    "cursors C1–C2",
    "zooms the timeline",
    "Statistics scope",
    "CPU Load",
    "Core Pair Summary",
)


class InspectorScopeLabelTests(unittest.TestCase):
    def test_corridor_inspector_scope_selector_is_inspector_scope(self) -> None:
        self.assertIn('QLabel("Inspector Scope")', STATS_PY)
        self.assertIn("Inspector Scope", CI_VUE)
        self.assertNotIn('QLabel("Analysis Scope")', STATS_PY)
        self.assertNotIn(">\n          Analysis Scope\n", CI_VUE)

    def test_inspector_scope_options_are_named_consistently(self) -> None:
        for opt in ("Follow zoom", "Viewport", "Cursor C1–Cn"):
            self.assertIn(opt, CI_VUE, opt)
            self.assertIn(opt, STATS_PY, opt)

    def test_inspector_ai_context_line_says_inspector_scope(self) -> None:
        self.assertIn("Inspector scope: ", PARSER_PY)
        self.assertIn("Inspector scope: ", MIG_JS)
        self.assertNotIn("Analysis scope: ", PARSER_PY)
        self.assertNotIn("Analysis scope: ", MIG_JS)


class CompareScopeLabelTests(unittest.TestCase):
    def test_trace_compare_cursor_range_option_is_labelled_compare_scope(self) -> None:
        self.assertIn("Compare Scope —", CMP_VUE)
        self.assertIn("Compare Scope —", STATS_PY)


class FocusThisWindowDisclosureTests(unittest.TestCase):
    def test_show_events_is_renamed_focus_this_window(self) -> None:
        self.assertIn('QPushButton("Focus this window")', STATS_PY)
        self.assertIn("Focus this window", CI_VUE)
        # The Corridor Inspector no longer labels the multi-state action
        # "Show events" / "Show on timeline".
        self.assertNotIn('QPushButton("Show events")', STATS_PY)
        ci_actions = CI_VUE[CI_VUE.index("ci-actions-row"):]
        self.assertNotIn(">\n                    Show events\n", ci_actions)

    def test_focus_this_window_tooltip_discloses_every_change(self) -> None:
        self.assertIn("_CI_FOCUS_WINDOW_TIP", STATS_PY)
        self.assertIn("FOCUS_WINDOW_TIP", CI_VUE)
        # String literals wrap across lines in both sources — compare on a
        # whitespace-collapsed view so the phrase match is line-break agnostic.
        stats_flat = re.sub(r'"\s*(?:\+\s*)?"', "", re.sub(r"\s+", " ", STATS_PY))
        ci_flat = re.sub(r"'\s*(?:\+\s*)?'", "", re.sub(r"\s+", " ", CI_VUE))
        for phrase in _FOCUS_CHANGES:
            self.assertIn(phrase, stats_flat, phrase)
            self.assertIn(phrase, ci_flat, phrase)

    def test_filter_timeline_identifies_its_target(self) -> None:
        self.assertIn("Filter the timeline to", STATS_PY)
        self.assertIn("Filter the timeline to", CI_VUE)


class ActivityRailAccessibleNameTests(unittest.TestCase):
    def test_rail_is_not_described_as_investigation_only(self) -> None:
        self.assertIn(
            'setAccessibleName("Analysis and application tools")', MW_PY
        )
        self.assertIn('aria-label="Analysis and application tools"', APP_VUE)
        self.assertNotIn('aria-label="Investigation tools"', APP_VUE)


if __name__ == "__main__":
    unittest.main()
