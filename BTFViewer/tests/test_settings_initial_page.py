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
        self.assertEqual(dlg.ai_provider, "ollama")
        self.assertIn("11434", dlg.ollama_url)
        self.assertIn("openai.com", dlg.openai_base_url)
        self.assertTrue(hasattr(dlg, "_ollama_test_btn"))
        self.assertEqual(dlg._ollama_test_btn.text(), "Test connection")
        # Long provider / preset labels must not be crushed to _INPUT_W (110).
        self.assertGreaterEqual(dlg._ai_provider_combo.minimumWidth(), 180)
        self.assertGreaterEqual(dlg._openai_preset_combo.minimumWidth(), 180)
        self.assertGreaterEqual(dlg._response_lang_combo.minimumWidth(), 240)
        # Closed-state text for current items must fit (not ellided to empty).
        self.assertEqual(dlg._ai_provider_combo.currentText(), "Ollama")
        dlg._ai_provider_combo.setCurrentIndex(
            dlg._ai_provider_combo.findData("openai_compatible"))
        self.assertIn("OpenAI", dlg._ai_provider_combo.currentText())

    def test_default_appearance(self) -> None:
        dlg = self._dlg("Appearance")
        self.addCleanup(dlg.deleteLater)
        self.assertEqual(dlg._sidebar.currentRow(), 0)
        self.assertEqual(dlg._content_stack.currentIndex(), 0)


if __name__ == "__main__":
    unittest.main()
