"""Settings dialog can open directly on Display (deadline / CPU budget)."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.stats import _SettingsDialog  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class SettingsInitialPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _app()

    def _dlg(self, page: str) -> _SettingsDialog:
        return _SettingsDialog(
            None,
            font_size=10,
            ui_font_size=11,
            max_cursors=2,
            show_sti=True,
            show_grid=True,
            show_legend=True,
            show_stats=True,
            show_marks=True,
            show_hover_highlight=True,
            zoom_unit="us",
            label_width=120,
            row_height=18,
            row_gap=2,
            sti_row_h=14,
            sti_waveform_h=24,
            sti_line_style="solid",
            timescale_per_px_default=1.0,
            is_dark=True,
            initial_page=page,
        )

    def test_display_page_selected(self) -> None:
        dlg = self._dlg("Display")
        self.addCleanup(dlg.deleteLater)
        self.assertEqual(dlg._sidebar.currentRow(), 1)
        self.assertEqual(dlg._content_stack.currentIndex(), 1)

    def test_ai_page_selected(self) -> None:
        dlg = self._dlg("AI")
        self.addCleanup(dlg.deleteLater)
        self.assertEqual(dlg._sidebar.currentRow(), 3)
        self.assertEqual(dlg._content_stack.currentIndex(), 3)
        self.assertTrue(dlg.ai_enabled)
        self.assertFalse(dlg.ai_auto_apply)
        self.assertEqual(dlg.ai_preset, "ollama")
        self.assertIn("11434", dlg._ai_url_edit.text())
        self.assertTrue(hasattr(dlg, "_ollama_test_btn"))
        self.assertEqual(dlg._ollama_test_btn.text(), "Test connection")
        # Long preset labels must not be crushed to _INPUT_W (110).
        self.assertGreaterEqual(dlg._ai_preset_combo.minimumWidth(), 180)
        self.assertGreaterEqual(dlg._response_lang_combo.minimumWidth(), 240)
        # Closed-state text for current items must fit (not ellided to empty).
        self.assertEqual(dlg._ai_preset_combo.currentText(), "Ollama")

    def test_ai_preset_switch_keeps_each_preset_fields(self) -> None:
        dlg = self._dlg("AI")
        self.addCleanup(dlg.deleteLater)
        dlg._ai_model_edit.setText("llama3.2:3b")
        dlg._ai_preset_combo.setCurrentIndex(dlg._ai_preset_combo.findData("gemini"))
        self.assertIn("generativelanguage", dlg._ai_url_edit.text())
        dlg._ai_api_key_edit.setText("test-key")
        dlg._ai_preset_combo.setCurrentIndex(dlg._ai_preset_combo.findData("ollama"))
        self.assertEqual(dlg._ai_model_edit.text(), "llama3.2:3b")
        self.assertEqual(dlg._ai_api_key_edit.text(), "")
        saved = dlg.ai_preset_settings
        self.assertEqual(saved["gemini"]["api_key"], "test-key")
        self.assertEqual(saved["ollama"]["model"], "llama3.2:3b")

    def test_ai_openai_preset_fills_endpoint(self) -> None:
        dlg = self._dlg("AI")
        self.addCleanup(dlg.deleteLater)
        idx = dlg._ai_preset_combo.findData("openai")
        self.assertGreaterEqual(idx, 0)
        dlg._ai_preset_combo.setCurrentIndex(idx)
        self.assertEqual(dlg.ai_preset, "openai")
        self.assertEqual(dlg._ai_url_edit.text(), "https://api.openai.com/v1")
        self.assertTrue(dlg._ai_model_edit.text())
        self.assertIn("platform.openai.com/api-keys", dlg._ai_hint.text())

    def test_ai_test_target_uses_active_preset_defaults(self) -> None:
        """A blank field must fall back to this preset, not to Ollama."""
        dlg = self._dlg("AI")
        self.addCleanup(dlg.deleteLater)
        dlg._ai_preset_combo.setCurrentIndex(dlg._ai_preset_combo.findData("gemini"))
        dlg._ai_url_edit.clear()
        dlg._ai_model_edit.clear()
        url, model, _key = dlg._ai_test_target()
        self.assertIn("generativelanguage", url)
        self.assertIn("gemini", model)

    def test_import_ai_settings_patch(self) -> None:
        dlg = self._dlg("AI")
        self.addCleanup(dlg.deleteLater)
        dlg._ai_api_key_edit.setText("keep-ollama-key")
        summary = dlg.apply_ai_settings_patch({
            "preset": "gemini",
            "gemini_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "gemini_model": "gemini-3.6-flash",
            "gemini_api_key": "imported",
            "response_language": "Klingon (tlhIngan Hol)",
        })
        self.assertIn("Google Gemini", summary)
        self.assertEqual(dlg.ai_preset, "gemini")
        self.assertEqual(dlg._ai_model_edit.text(), "gemini-3.6-flash")
        self.assertEqual(dlg._ai_api_key_edit.text(), "imported")
        self.assertEqual(dlg.response_language, "Klingon (tlhIngan Hol)")
        # Presets the file did not name keep their settings.
        self.assertEqual(
            dlg.ai_preset_settings["ollama"]["api_key"], "keep-ollama-key")

    def test_default_appearance(self) -> None:
        dlg = self._dlg("Appearance")
        self.addCleanup(dlg.deleteLater)
        self.assertEqual(dlg._sidebar.currentRow(), 0)
        self.assertEqual(dlg._content_stack.currentIndex(), 0)


if __name__ == "__main__":
    unittest.main()
