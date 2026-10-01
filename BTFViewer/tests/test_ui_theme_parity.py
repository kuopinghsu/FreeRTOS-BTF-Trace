"""Desktop ↔ web Modern UX token lockstep."""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.empty_state import EMPTY_STATES  # noqa: E402
from btf_viewer_pkg.ui_theme import (  # noqa: E402
    BUTTON_ROLES,
    REPORT_EXPAND_FRACTION,
    REPORT_EXPAND_TABS,
    TEXT_CONTRAST_MIN,
    UI_CONTRAST_MIN,
    UI_THEME,
    button_qss,
    contrast_ratio,
    expanded_report_width,
    report_expand_allowed,
    report_expand_button,
    ui_theme_tokens,
)


class UiThemeContrastTest(unittest.TestCase):
    """TODO P0.1 acceptance: text 4.5:1, focus / control boundaries 3:1."""

    def test_text_roles_meet_4_5(self) -> None:
        for mode, t in UI_THEME.items():
            for bg in ("workspace", "surface"):
                for fg in ("fg", "fg_dim", "warning", "success", "destructive"):
                    with self.subTest(mode=mode, fg=fg, bg=bg):
                        self.assertGreaterEqual(
                            contrast_ratio(t[fg], t[bg]), TEXT_CONTRAST_MIN)
            with self.subTest(mode=mode, pair="on_accent/accent_ui"):
                self.assertGreaterEqual(
                    contrast_ratio(t["on_accent"], t["accent_ui"]), TEXT_CONTRAST_MIN)

    def test_focus_and_control_boundaries_meet_3(self) -> None:
        for mode, t in UI_THEME.items():
            for bg in ("workspace", "surface"):
                for fg in ("focus", "control_border", "accent_ui"):
                    with self.subTest(mode=mode, fg=fg, bg=bg):
                        self.assertGreaterEqual(
                            contrast_ratio(t[fg], t[bg]), UI_CONTRAST_MIN)

    def test_desktop_shell_text_and_inputs_use_palette(self) -> None:
        from btf_viewer_pkg.mainwindow import MainWindow
        for is_dark in (True, False):
            c = MainWindow._theme_tokens(is_dark)
            ui = ui_theme_tokens(is_dark)
            self.assertEqual(c["text"], ui["fg"])
            self.assertEqual(c["muted_text"], ui["fg_dim"])
            self.assertEqual(c["input_border"], ui["control_border"])
            self.assertGreaterEqual(
                contrast_ratio(c["text"], c["win_bg"]), TEXT_CONTRAST_MIN)
            self.assertGreaterEqual(
                contrast_ratio(c["muted_text"], c["win_bg"]), TEXT_CONTRAST_MIN)
            self.assertGreaterEqual(
                contrast_ratio(c["input_border"], c["input_bg"]), UI_CONTRAST_MIN)

    def test_status_cues_pair_color_with_glyph(self) -> None:
        from btf_viewer_pkg.ui_theme import STATUS_CUES, status_cue_text
        self.assertEqual(status_cue_text("Request failed", "error"), "✖ Request failed")
        self.assertEqual(status_cue_text("✖ Request failed", "error"), "✖ Request failed")
        self.assertEqual(status_cue_text("Partial trace", "warning"), "⚠ Partial trace")
        self.assertEqual(status_cue_text("Done.", "info"), "Done.")
        self.assertEqual(status_cue_text("", "error"), "")
        js = (BTF_ROOT / "web/src/utils/uiTheme.js").read_text(encoding="utf-8")
        for sev, cue in STATUS_CUES.items():
            self.assertIn(f"{sev}: '{cue}'", js)
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        self.assertIn("statusCueText(traceQualityReportData.summary, 'warning')", app)
        ai = (BTF_ROOT / "web/src/components/AiAssistantPanel.vue").read_text(encoding="utf-8")
        self.assertIn("statusCueText(statusText, error ? 'error' : 'info')", ai)
        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        self.assertIn('status_cue_text(summary, "warning")', mw)

    def test_statistics_empty_state_and_static_skeleton(self) -> None:
        stats = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
        self.assertIn('self._lbl(empty_state_message("no_stats")', stats)
        self.assertNotIn('"Open a trace file to view statistics."', stats)
        panel = (BTF_ROOT / "web/src/components/StatisticsPanel.vue").read_text(encoding="utf-8")
        self.assertIn("emptyStateMessage('noStats')", panel)
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        self.assertIn('v-if="loading && !trace"', app)
        self.assertNotIn("tl-skel-shimmer", app)

    def test_web_writes_text_aliases(self) -> None:
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        self.assertIn("el.style.setProperty('--text', String(t.fg))", app)
        self.assertIn("el.style.setProperty('--muted', String(t.fg_dim))", app)
        self.assertIn("var(--control-border, var(--border)) !important", app)
        self.assertIn("var(--on-accent, #fff)", app)


class UiThemeParityTest(unittest.TestCase):
    def test_token_tables_match_web(self) -> None:
        js = (BTF_ROOT / "web/src/utils/uiTheme.js").read_text(encoding="utf-8")
        # Hex literals in JS must match the Python table.
        for mode, table in UI_THEME.items():
            for key, value in table.items():
                if isinstance(value, str) and value.startswith("#"):
                    self.assertIn(value, js, f"{mode}.{key}")
        self.assertIn("REPORT_EXPAND_FRACTION = 0.82", js)
        self.assertIn("'stats'", js)
        self.assertIn("'ai'", js)
        for role in BUTTON_ROLES:
            self.assertIn(f"'{role}'", js)

    def test_helpers(self) -> None:
        self.assertTrue(report_expand_allowed("stats"))
        self.assertTrue(report_expand_allowed("ai"))
        self.assertFalse(report_expand_allowed("marks"))
        self.assertEqual(expanded_report_width(1000), 760)
        for expanded, pending, label in (
                (False, False, "Expand report"), (True, False, "Restore layout"),
                (False, True, "Back to report"), (True, True, "Restore layout")):
            self.assertEqual(report_expand_button(expanded, pending)["label"], label)
        js = (BTF_ROOT / "web/src/utils/uiTheme.js").read_text(encoding="utf-8")
        for text in ("Expand report", "Restore layout", "Back to report",
                     "Re-expand the report you were reading",
                     "REPORT_EXPAND_MIN_TIMELINE = 240", "REPORT_EXPAND_MIN_REPORT = 180"):
            self.assertIn(text, js)
        self.assertEqual(REPORT_EXPAND_FRACTION, 0.82)
        self.assertEqual(REPORT_EXPAND_TABS, ("stats", "ai"))
        dark = ui_theme_tokens(True)
        light = ui_theme_tokens(False)
        self.assertEqual(dark["workspace"], "#151A22")
        self.assertEqual(light["workspace"], "#F5F7FA")
        qss = button_qss("primary", dark, object_name="welcome_open_btn")
        self.assertIn("QPushButton#welcome_open_btn", qss)
        self.assertIn(dark["accent_ui"], qss)


class EmptyStateParityTest(unittest.TestCase):
    def test_empty_catalog_messages_match_web(self) -> None:
        js = (BTF_ROOT / "web/src/utils/emptyState.js").read_text(encoding="utf-8")
        for spec in EMPTY_STATES.values():
            msg = spec["message"]
            # Adjacent-string concatenations may be split across source lines.
            self.assertIn(msg[:24], js, msg)
        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")
        self.assertIn('empty_state_message("no_marks")', mw)
        self.assertIn('empty_state_message("no_find_query")', mw)
        self.assertIn('empty_state_message("no_ai")', assist)


class UiThemeParseTest(unittest.TestCase):
    def test_python_module_is_valid(self) -> None:
        src = (BTF_ROOT / "btf_viewer_pkg/ui_theme.py").read_text(encoding="utf-8")
        ast.parse(src)


if __name__ == "__main__":
    unittest.main()
