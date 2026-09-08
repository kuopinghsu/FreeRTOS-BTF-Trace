"""Step 1–3 operation-flow regression checks (BTFVIEWER_OPERATION_FLOW_TODO.md).

Source-level lockstep assertions that pin the "one flow, no duplicated
operations" invariants across the web (App.vue / AnalysisFindingsDialog.vue /
aiClient.js) and desktop (mainwindow.py / stats.py / ai_assistant.py) builds:

* Step 1.1 — one investigation-record action (`Add to investigation`); no
  `Add to case`.
* Step 1.2 — `Open Statistics` replaces the finding `Investigate` shortcut and
  never changes Scope / Filters / Limit-to-cursors.
* Step 1.3 — navigation actions (`Show on timeline`) do not silently change
  analysis state.
* Step 2.2 — `Root cause` is renamed `Test leading explanation` and dropped
  from every primary shortcut row (kept only under More templates…).
* Step 2.4 — Workspace presets stay layout-only.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

APP_VUE = (ROOT / "web/src/App.vue").read_text(encoding="utf-8")
DLG_VUE = (ROOT / "web/src/components/AnalysisFindingsDialog.vue").read_text(encoding="utf-8")
AICLIENT_JS = (ROOT / "web/src/utils/aiClient.js").read_text(encoding="utf-8")
MAINWINDOW_PY = (ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
STATS_PY = (ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
AI_ASSISTANT_PY = (ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(encoding="utf-8")


def _js_body(src: str, header: str) -> str:
    """Return the brace-balanced body of a JS function starting at *header*.

    Skips the parameter list (which may itself contain ``{ }`` from a
    destructured / default argument) and starts brace counting at the ``{``
    that opens the function body.
    """
    i = src.index(header)
    rest = src[i:]
    # advance past the parameter list: the first ')' at paren-depth 0
    depth = 0
    j = 0
    for j, ch in enumerate(rest):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
    body_open = rest.index("{", j)
    depth = 0
    out = []
    for ch in rest[body_open:]:
        out.append(ch)
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
    return "".join(out)


def _py_method(src: str, name: str) -> str:
    """Return the body of a Python method `def <name>(` up to the next
    line indented at or below the `def`."""
    m = re.search(rf"\n(?P<indent> *)def {re.escape(name)}\(", src)
    assert m, name
    indent = len(m.group("indent"))
    lines = src[m.start() + 1:].splitlines()
    body = [lines[0]]
    for line in lines[1:]:
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        body.append(line)
    return "\n".join(body)


class OpenStatisticsIsNavigationOnly(unittest.TestCase):
    """Step 1.2 — the finding `Open Statistics` action opens a section only."""

    def test_web_handler_does_not_touch_scope(self):
        body = _js_body(APP_VUE, "async function onOpenFindingStatistics(")
        self.assertIn("applyDemoSections", body)
        self.assertNotIn("onApplyFindingScope", body)
        self.assertNotIn("applyExploreRange", body)
        self.assertNotIn("cursors.value =", body)
        self.assertNotIn("scopeToCursors", body)

    def test_web_dialog_button_and_emit(self):
        self.assertIn("Open Statistics", DLG_VUE)
        self.assertIn("emit('open-statistics'", DLG_VUE)
        self.assertNotIn("Confirm Investigate", DLG_VUE)
        self.assertNotIn("Undo Scope", DLG_VUE)

    def test_desktop_handler_does_not_touch_scope(self):
        body = _py_method(MAINWINDOW_PY, "_open_finding_statistics")
        self.assertIn("scroll_to_section", body)
        self.assertNotIn("_apply_finding_scope", body)
        self.assertNotIn("_on_explore_range", body)

    def test_desktop_dialog_button_and_callback(self):
        self.assertIn('QPushButton("Open Statistics")', STATS_PY)
        self.assertIn("self._on_open_statistics", STATS_PY)
        self.assertNotIn("Confirm Investigate", STATS_PY)
        self.assertNotIn('QPushButton("Undo Scope")', STATS_PY)


class ShowOnTimelineIsNavigationOnly(unittest.TestCase):
    """Step 1.3 — `Show on timeline` never silently changes analysis state."""

    def test_web_guards_against_scope_cursor_write(self):
        body = _js_body(APP_VUE, "function onShowFindingEvidence(")
        self.assertIn("scopeLimiting", body)
        self.assertIn("!near && !scopeLimiting", body)
        self.assertNotIn("onApplyFindingScope", body)
        self.assertNotIn("applyExploreRange", body)

    def test_desktop_guards_against_scope_cursor_write(self):
        body = _py_method(MAINWINDOW_PY, "_show_finding_evidence")
        self.assertIn("scope_limiting", body)
        self.assertIn("not scope_limiting", body)
        self.assertNotIn("_apply_finding_scope", body)


class SingleInvestigationRecordAction(unittest.TestCase):
    """Step 1.1 — one record action; no `Add to case` / Case queue."""

    def test_web_no_add_to_case(self):
        self.assertNotIn("Add to case", DLG_VUE)
        self.assertNotIn("add-to-case", DLG_VUE)
        self.assertNotIn("@add-to-case", APP_VUE)
        self.assertNotIn("onAddFindingToCase", APP_VUE)
        self.assertIn("Add to investigation", DLG_VUE)
        self.assertIn("add-to-investigation", DLG_VUE)

    def test_desktop_no_add_to_case(self):
        self.assertNotIn('QPushButton("Add to case")', STATS_PY)
        self.assertNotIn("_add_to_case", STATS_PY)
        self.assertNotIn("on_add_to_case", MAINWINDOW_PY)
        self.assertIn('QPushButton("Add to investigation")', STATS_PY)
        self.assertIn("on_add_to_investigation", STATS_PY)

    def test_case_queue_tab_removed_from_both_dialogs(self):
        self.assertNotIn('(QUEUE_CASE, "Case")', STATS_PY)
        self.assertNotIn("{ id: QUEUE_CASE, label: 'Case' }", DLG_VUE)


class RootCauseNotAPrimaryShortcut(unittest.TestCase):
    """Step 2.2 — `Root cause` → `Test leading explanation`, demoted."""

    def test_label_renamed_both_builds(self):
        self.assertIn('"Test leading explanation"', AI_ASSISTANT_PY)
        self.assertIn("label: 'Test leading explanation'", AICLIENT_JS)
        self.assertNotIn('"root_cause",\n        "Root cause",', AI_ASSISTANT_PY)

    def test_dropped_from_findings_ask_ai_menu(self):
        self.assertNotIn("Root cause…", DLG_VUE)
        self.assertNotIn("Root cause…", STATS_PY)
        self.assertNotIn("askAi('root_cause')", DLG_VUE)

    def test_absent_from_intent_landing_present_in_more_templates(self):
        for src in (AICLIENT_JS, AI_ASSISTANT_PY):
            intent = re.search(
                r"AI_TEMPLATE_INTENT_GROUPS[^\)]*?=\s*[\(\[](?P<b>.*?)[\)\]]\s*\n\n",
                src, re.S)
            self.assertIsNotNone(intent)
            self.assertNotIn("root_cause", intent.group("b"))
            menu = re.search(
                r"AI_TEMPLATE_MENU_GROUPS[^\)]*?=\s*[\(\[](?P<b>.*?)[\)\]]\s*\n\n",
                src, re.S)
            self.assertIsNotNone(menu)
            self.assertIn("root_cause", menu.group("b"))


class VerifyDoesNotRerunFullInvestigation(unittest.TestCase):
    """Step 2.2 — `Verify finding` starts from existing evidence."""

    def test_prompt_wording_both_builds(self):
        for src in (AICLIENT_JS, AI_ASSISTANT_PY):
            self.assertIn("without rerunning a full", src)
            self.assertIn("evidence that is genuinely missing", src)
            self.assertIn("test contradicting evidence", src)


class SharedAiContextPath(unittest.TestCase):
    """Step 2.3 / 3.3 — every contextual AI action uses one context path."""

    def test_web_contextual_entry_points_route_through_focus_ai_and_ask(self):
        # Analysis Findings, Explain region, Ask-AI-event and the Corridor
        # inspector all funnel through the single focusAiAndAsk() helper.
        for fn in ("queryAnalysisWithAi", "queryExplainRegionWithAi",
                   "queryAskAiEvent", "queryCorridorWithAi"):
            body = _js_body(APP_VUE, f"async function {fn}(")
            self.assertIn("focusAiAndAsk", body, fn)
        focus = _js_body(APP_VUE, "async function focusAiAndAsk(")
        self.assertIn("askTemplate", focus)

    def test_shared_context_builder_carries_standard_fields(self):
        body = _js_body(APP_VUE, "function buildAiContext(")
        for field in ("scope:", "filters:", "cursors:", "selection:",
                      "selectedFinding:", "findings"):
            self.assertIn(field, body, field)

    def test_normalizer_carries_selection_finding_stage_both_builds(self):
        js_body = _js_body(AICLIENT_JS, "export function normalizeAiContext(")
        for key in ("selection:", "selectedFinding", "workflowStage"):
            self.assertIn(key, js_body, key)
        py_body = _py_method(AI_ASSISTANT_PY, "normalize_ai_context")
        for key in ('"selection"', '"selected_finding"', '"workflow_stage"'):
            self.assertIn(key, py_body, key)

    def test_compare_keeps_its_own_evidence_type_context(self):
        # The only permitted per-panel context (CSV compare tables).
        self.assertIn("function buildAiCompareContext(", APP_VUE)
        self.assertIn("_ai_build_compare_context", MAINWINDOW_PY)


class StatisticsNavigationHasNoSideState(unittest.TestCase):
    """Step 3.3 — all routes into a Statistics section share one navigator."""

    def test_web_routes_use_apply_demo_sections(self):
        for fn in ("onOpenFindingStatistics", "onAiOpenStats"):
            body = _js_body(APP_VUE, f"function {fn}(") \
                if f"function {fn}(" in APP_VUE \
                else _js_body(APP_VUE, f"async function {fn}(")
            self.assertIn("applyDemoSections", body, fn)
            self.assertNotIn("cursors.value =", body)
            self.assertNotIn("scopeToCursors =", body)


class WorkspacePresetsAreLayoutOnly(unittest.TestCase):
    """Step 2.4 — presets change layout, never Scope / Filters / stage."""

    def test_web_preset_only_touches_section_collapse(self):
        body = _js_body(APP_VUE, "function applyWorkspacePreset(")
        self.assertIn("statsSectionCollapsed", body)
        self.assertNotIn("cursors.value", body)
        self.assertNotIn("scopeToCursors", body)
        self.assertNotIn("clearAllActiveFilters", body)
        self.assertNotIn("guideStage", body)

    def test_desktop_preset_only_touches_section_collapse(self):
        body = _py_method(MAINWINDOW_PY, "_apply_workspace_preset")
        self.assertIn("set_section_collapsed_map", body)
        self.assertNotIn("_apply_finding_scope", body)
        self.assertNotIn("set_cursor_times", body)
        self.assertNotIn("scope_to_cursors", body)


if __name__ == "__main__":
    unittest.main()
