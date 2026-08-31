"""Settings dialog can open directly on Display (deadline / CPU budget)."""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.stats import _SettingsDialog, _SettingsHelpLabel  # noqa: E402


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
        self.assertEqual(dlg.ai_context_mode, "balanced")
        self.assertFalse(dlg.ai_mcp_log)
        self.assertEqual(dlg.ai_preset, "ollama")
        self.assertIn("11434", dlg._ai_url_edit.text())
        self.assertTrue(hasattr(dlg, "_ollama_test_btn"))
        self.assertEqual(dlg._ollama_test_btn.text(), "Test connection")
        self.assertTrue(hasattr(dlg, "_ai_model_refresh"))
        self.assertTrue(dlg._ai_model_combo.isEditable())
        self.assertTrue(hasattr(dlg, "_ai_mcp_log_cb"))
        self.assertIn("debugging", dlg._ai_mcp_log_cb.toolTip().lower())
        # Long preset labels must not be crushed to _INPUT_W (110).
        self.assertGreaterEqual(dlg._ai_preset_combo.minimumWidth(), 180)
        self.assertGreaterEqual(dlg._response_lang_combo.minimumWidth(), 240)
        # Closed-state text for current items must fit (not ellided to empty).
        self.assertEqual(dlg._ai_preset_combo.currentText(), "Ollama")
        self.assertEqual(dlg._ai_auth_combo.currentData(), "none")
        self.assertTrue(dlg._ai_cred_wrap.isHidden())
        self.assertFalse(dlg._ai_insecure_tls_cb.isChecked())
        help_texts = " ".join(
            lbl.text() for lbl in dlg.findChildren(type(dlg._ai_context_help)))
        self.assertIn("When off, the AI tab is hidden.", help_texts)
        help_lbl = dlg.findChild(type(dlg._ai_context_help), "aiEnabledHelp")
        self.assertIsNotNone(help_lbl)
        self.assertEqual(dlg._ai_enabled_cb.text().replace("&", ""), "Enable AI Assistant")
        dlg.resize(720, 520)
        dlg.show()
        QApplication.processEvents()
        enable_x = dlg._ai_enabled_cb.mapTo(dlg, dlg._ai_enabled_cb.rect().topLeft()).x()
        auto_x = dlg._ai_auto_apply_cb.mapTo(dlg, dlg._ai_auto_apply_cb.rect().topLeft()).x()
        help_x = help_lbl.mapTo(dlg, help_lbl.rect().topLeft()).x()
        ctx_x = dlg._ai_context_help.mapTo(dlg, dlg._ai_context_help.rect().topLeft()).x()
        self.assertEqual(enable_x, auto_x)
        self.assertEqual(help_x, ctx_x)
        self.assertIn("Compact", dlg._ai_context_help.text())
        self.assertIn("Balanced (default)", dlg._ai_context_help.text())
        self.assertIn("Full Evidence", dlg._ai_context_help.text())
        self.assertIn("\n", dlg._ai_context_help.text())
        self.assertGreaterEqual(dlg._ai_context_help.minimumWidth(), 280)
        self.assertLess(dlg._ai_context_help.heightForWidth(360), 80)
        self.assertLess(dlg._ollama_test_status.heightForWidth(360), 80)
        self.assertIn('width="320"', dlg._ai_enabled_cb.toolTip())
        self.assertIn('width="320"', dlg._ai_preset_combo.toolTip())
        self.assertIn("How much Findings", dlg._ai_context_combo.toolTip())
        self.assertEqual(dlg._ai_url_edit.width(), dlg._ai_preset_combo.width())
        self.assertGreaterEqual(
            dlg._ai_url_edit.height(), dlg._ai_preset_combo.height() - 4)

    def test_ai_preset_switch_keeps_each_preset_fields(self) -> None:
        dlg = self._dlg("AI")
        self.addCleanup(dlg.deleteLater)
        dlg._set_ai_model_text("llama3.2:3b")
        dlg._ai_preset_combo.setCurrentIndex(dlg._ai_preset_combo.findData("gemini"))
        self.assertIn("generativelanguage", dlg._ai_url_edit.text())
        self.assertEqual(dlg._ai_auth_combo.currentData(), "api_key")
        self.assertFalse(dlg._ai_cred_wrap.isHidden())
        dlg._ai_api_key_edit.setText("test-key")
        dlg._ai_preset_combo.setCurrentIndex(dlg._ai_preset_combo.findData("ollama"))
        self.assertEqual(dlg._ai_model_text(), "llama3.2:3b")
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
        self.assertTrue(dlg._ai_model_text())
        self.assertIn("platform.openai.com/api-keys", dlg._ai_hint.text())
        self.assertEqual(dlg._ai_auth_combo.currentData(), "api_key")
        idx_browser = dlg._ai_auth_combo.findData("browser")
        dlg._ai_auth_combo.setCurrentIndex(idx_browser)
        self.assertFalse(dlg._ai_signin_btn.isHidden())
        self.assertIn("OpenAI", dlg._ai_signin_btn.text())

    def test_ai_test_target_uses_active_preset_defaults(self) -> None:
        """A blank field must fall back to this preset, not to Ollama."""
        dlg = self._dlg("AI")
        self.addCleanup(dlg.deleteLater)
        dlg._ai_preset_combo.setCurrentIndex(dlg._ai_preset_combo.findData("gemini"))
        dlg._ai_url_edit.clear()
        dlg._set_ai_model_text("")
        url, model, _key, tls_verify = dlg._ai_test_target()
        self.assertIn("generativelanguage", url)
        self.assertIn("gemini", model)
        self.assertTrue(tls_verify)

    def test_import_ai_settings_patch(self) -> None:
        dlg = self._dlg("AI")
        self.addCleanup(dlg.deleteLater)
        dlg._ai_api_key_edit.setText("keep-ollama-key")
        summary = dlg.apply_ai_settings_patch({
            "preset": "gemini",
            "gemini_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "gemini_model": "gemini-3.6-flash",
            "gemini_api_key": "imported",
            "gemini_auth_mode": "browser",
            "gemini_tls_verify": "false",
            "response_language": "Klingon (tlhIngan Hol)",
        })
        self.assertIn("Google Gemini", summary)
        self.assertEqual(dlg.ai_preset, "gemini")
        self.assertEqual(dlg._ai_model_text(), "gemini-3.6-flash")
        self.assertEqual(dlg._ai_api_key_edit.text(), "imported")
        self.assertEqual(dlg._ai_auth_combo.currentData(), "browser")
        self.assertTrue(dlg._ai_insecure_tls_cb.isChecked())
        self.assertEqual(dlg.response_language, "Klingon (tlhIngan Hol)")
        # Presets the file did not name keep their settings.
        self.assertEqual(
            dlg.ai_preset_settings["ollama"]["api_key"], "keep-ollama-key")

    def test_import_ai_settings_adds_unknown_preset_and_checkboxes(self) -> None:
        dlg = self._dlg("AI")
        self.addCleanup(dlg.deleteLater)
        dlg._ai_enabled_cb.setChecked(True)
        dlg._ai_auto_apply_cb.setChecked(False)
        summary = dlg.apply_ai_settings_patch({
            "preset": "deepseek",
            "extra_presets": '[{"id": "deepseek", "label": "DeepSeek"}]',
            "deepseek_base_url": "https://api.deepseek.com/v1",
            "deepseek_model": "deepseek-v4-flash",
            "deepseek_auth_mode": "api_key",
            "enabled": "true",
            "auto_apply": "true",
            "context_mode": "compact",
            "redact_task_names": "true",
            "trace_sensitive": "false",
            "mcp_log": "true",
        })
        self.assertIn("DeepSeek", summary)
        self.assertEqual(dlg.ai_preset, "deepseek")
        self.assertGreaterEqual(dlg._ai_preset_combo.findData("deepseek"), 0)
        self.assertEqual(dlg._ai_url_edit.text(), "https://api.deepseek.com/v1")
        self.assertEqual(dlg._ai_model_text(), "deepseek-v4-flash")
        self.assertTrue(dlg.ai_enabled)
        self.assertTrue(dlg.ai_auto_apply)
        self.assertEqual(dlg.ai_context_mode, "compact")
        self.assertTrue(dlg.ai_redact_task_names)
        self.assertFalse(dlg.ai_trace_sensitive)
        self.assertTrue(dlg.ai_mcp_log)
        extras = dlg.ai_extra_presets
        self.assertEqual(extras[0]["id"], "deepseek")
        self.assertIn("deepseek", dlg.ai_preset_settings)

    def test_ai_model_refresh_fills_combo(self) -> None:
        dlg = self._dlg("AI")
        self.addCleanup(dlg.deleteLater)
        current = dlg._ai_model_text()
        dlg._on_ai_models_ok(["zeta-model", "alpha-model"])
        items = [dlg._ai_model_combo.itemText(i) for i in range(dlg._ai_model_combo.count())]
        self.assertIn("alpha-model", items)
        self.assertIn("zeta-model", items)
        self.assertEqual(dlg._ai_model_text(), current)
        self.assertLess(items.index("alpha-model"), items.index("zeta-model"))
        if current and current not in ("alpha-model", "zeta-model"):
            self.assertIn(current, items)
        self.assertIn("Open the Model dropdown to pick one.", dlg._ollama_test_status.text())

    def test_ai_signin_opens_browser(self) -> None:
        dlg = self._dlg("AI")
        self.addCleanup(dlg.deleteLater)
        dlg._ai_preset_combo.setCurrentIndex(dlg._ai_preset_combo.findData("gemini"))
        dlg._ai_auth_combo.setCurrentIndex(dlg._ai_auth_combo.findData("browser"))
        opened = []
        with patch(
            "btf_viewer_pkg.stats.QDesktopServices.openUrl",
            side_effect=lambda u: opened.append(u.toString()),
        ):
            dlg._ai_open_signin()
        self.assertEqual(len(opened), 1)
        self.assertIn("aistudio.google.com", opened[0])
        self.assertIn("Opened ", dlg._ollama_test_status.text())

    def test_ai_test_status_shows_full_capability_report(self) -> None:
        from PySide6.QtWidgets import QScrollArea

        from btf_viewer_pkg.ai_case import format_capability_report

        dlg = self._dlg("AI")
        self.addCleanup(dlg.deleteLater)
        self.assertIsNotNone(dlg.findChild(QScrollArea, "aiSettingsScroll"))
        dlg.resize(720, 520)
        dlg.show()
        QApplication.processEvents()
        ctx_h = dlg._ai_context_help.height()
        redact_y = dlg._ai_redact_cb.mapTo(dlg, dlg._ai_redact_cb.rect().topLeft()).y()
        tls_y = dlg._ai_insecure_tls_cb.mapTo(
            dlg, dlg._ai_insecure_tls_cb.rect().topLeft()).y()
        auth_h = dlg._ai_cred_wrap.height()
        cap = format_capability_report({
            "chat": "yes",
            "structured_output": "yes",
            "tool_calling": "yes",
            "multi_tool_chaining": "partial",
            "long_context": "yes",
            "complex_reasoning": "yes",
            "recommended": "Investigation modes",
        })
        dlg._set_ai_status(
            "Starting test for http://127.0.0.1:11434/v1 / llama3.2…")
        QApplication.processEvents()
        self.assertEqual(dlg._ai_context_help.height(), ctx_h)
        self.assertEqual(
            dlg._ai_redact_cb.mapTo(
                dlg, dlg._ai_redact_cb.rect().topLeft()).y(),
            redact_y)
        self.assertEqual(
            dlg._ai_insecure_tls_cb.mapTo(
                dlg, dlg._ai_insecure_tls_cb.rect().topLeft()).y(),
            tls_y)
        self.assertEqual(dlg._ai_cred_wrap.height(), auth_h)
        msg = (
            "Connected to http://localhost:11434/v1. Model llama3 ready.\n\n"
            + cap
        )
        dlg._set_ai_status(msg, "ok")
        QApplication.processEvents()
        shown = dlg._ollama_test_status.text()
        self.assertIn("Model capability", shown)
        self.assertIn("Tool calling", shown)
        self.assertIn("Recommended:", shown)
        wrap_h = dlg._ollama_test_status.heightForWidth(360)
        self.assertGreater(wrap_h, 40, shown)
        self.assertLess(wrap_h, 320, wrap_h)
        self.assertGreater(
            dlg._ollama_test_status.sizeHint().height(), 40, shown)
        st = dlg._ollama_test_status
        st_w = max(st.width(), 280)
        self.assertGreaterEqual(st.height(), st.heightForWidth(st_w) - 6, shown)
        self.assertTrue(st.hasHeightForWidth())
        self.assertEqual(dlg._ai_context_help.height(), ctx_h)
        self.assertEqual(
            dlg._ai_redact_cb.mapTo(
                dlg, dlg._ai_redact_cb.rect().topLeft()).y(),
            redact_y)
        self.assertEqual(
            dlg._ai_insecure_tls_cb.mapTo(
                dlg, dlg._ai_insecure_tls_cb.rect().topLeft()).y(),
            tls_y)
        self.assertEqual(dlg._ai_cred_wrap.height(), auth_h)
        self.assertLess(dlg._ai_context_help.heightForWidth(0), 80)
        self.assertLess(dlg._ai_context_help.heightForWidth(20), 80)
        self.assertEqual(
            dlg._ollama_test_status.heightForWidth(0),
            dlg._ollama_test_status.heightForWidth(280))
        self.assertTrue(dlg._ollama_test_status.hasHeightForWidth())

    def test_ai_test_status_does_not_move_tls_when_auth_shown(self) -> None:
        dlg = self._dlg("AI")
        self.addCleanup(dlg.deleteLater)
        dlg.resize(720, 520)
        dlg.show()
        QApplication.processEvents()
        dlg._ai_preset_combo.setCurrentIndex(
            dlg._ai_preset_combo.findData("gemini"))
        QApplication.processEvents()
        self.assertFalse(dlg._ai_cred_wrap.isHidden())
        self.assertGreaterEqual(
            dlg._ai_api_key_edit.minimumWidth(), 240)
        self.assertEqual(
            dlg._ai_api_key_edit.width(), dlg._ai_preset_combo.width())
        self.assertGreaterEqual(
            dlg._ai_api_key_edit.height(), dlg._ai_preset_combo.height() - 4)
        auth = dlg._ai_auth_status
        auth_w = max(auth.width(), 280)
        self.assertGreaterEqual(
            auth.height(), auth.heightForWidth(auth_w) - 6, auth.text())
        tls_y = dlg._ai_insecure_tls_cb.mapTo(
            dlg, dlg._ai_insecure_tls_cb.rect().topLeft()).y()
        cred_h = dlg._ai_cred_wrap.height()
        dlg._set_ai_status(
            "Starting test for https://generativelanguage.googleapis.com/v1beta/openai / gemini-flash-lite-latest…")
        QApplication.processEvents()
        self.assertEqual(
            dlg._ai_insecure_tls_cb.mapTo(
                dlg, dlg._ai_insecure_tls_cb.rect().topLeft()).y(),
            tls_y)
        self.assertEqual(dlg._ai_cred_wrap.height(), cred_h)

    def test_settings_help_label_hfw_zero_matches_min_width(self) -> None:
        lbl = _SettingsHelpLabel("Paste a provider API key, or set "
                                 "OPENAI_API_KEY / GEMINI_API_KEY / OLLAMA_API_KEY.")
        self.addCleanup(lbl.deleteLater)
        self.assertTrue(lbl.hasHeightForWidth())
        self.assertEqual(lbl.heightForWidth(0), lbl.heightForWidth(280))
        self.assertLess(lbl.heightForWidth(0), 80)

    def test_bundle_qtgui_includes_desktop_services(self) -> None:
        """The single-file app must import QDesktopServices (Sign in)."""
        imports = (BTF_ROOT / "btf_viewer_pkg/_imports.py").read_text(
            encoding="utf-8")
        script = (BTF_ROOT / "scripts/bundle_viewer.py").read_text(
            encoding="utf-8")
        bundle = (BTF_ROOT / "builds/btf_viewer.py").read_text(encoding="utf-8")
        pat = re.compile(
            r"from PySide6\.QtGui import \(\s*(.*?)\s*\)", re.S)
        for src, label in (
            (imports, "_imports.py"),
            (script, "bundle_viewer.py"),
            (bundle, "builds/btf_viewer.py"),
        ):
            m = pat.search(src)
            self.assertIsNotNone(m, label)
            names = {n.strip() for n in m.group(1).split(",") if n.strip()}
            self.assertIn("QDesktopServices", names, label)

    def test_bundle_imports_guide_stepper_jump_symbols(self) -> None:
        """``_jump_guide_stage`` selects log text with QTextCursor /
        QTextCharFormat / QTextEdit — the bundler's SHARED_IMPORTS must carry
        them (per-module ``from ._imports import *`` is stripped when bundling)."""
        imports = (BTF_ROOT / "btf_viewer_pkg/_imports.py").read_text(
            encoding="utf-8")
        script = (BTF_ROOT / "scripts/bundle_viewer.py").read_text(
            encoding="utf-8")
        bundle = (BTF_ROOT / "builds/btf_viewer.py").read_text(encoding="utf-8")
        gui_pat = re.compile(
            r"from PySide6\.QtGui import \(\s*(.*?)\s*\)", re.S)
        wid_pat = re.compile(
            r"from PySide6\.QtWidgets import \(\s*(.*?)\s*\)", re.S)
        for src, label in (
            (imports, "_imports.py"),
            (script, "bundle_viewer.py"),
            (bundle, "builds/btf_viewer.py"),
        ):
            gui = gui_pat.search(src)
            wid = wid_pat.search(src)
            self.assertIsNotNone(gui, label)
            self.assertIsNotNone(wid, label)
            gui_names = {n.strip() for n in gui.group(1).split(",") if n.strip()}
            wid_names = {n.strip() for n in wid.group(1).split(",") if n.strip()}
            self.assertIn("QTextCursor", gui_names, label)
            self.assertIn("QTextCharFormat", gui_names, label)
            self.assertIn("QTextEdit", wid_names, label)

    def test_bundle_includes_html_parser(self) -> None:
        """Markdown HTML-table sanitizer needs HTMLParser in the monolith."""
        needle = "from html.parser import HTMLParser"
        for rel in (
            "btf_viewer_pkg/_imports.py",
            "scripts/bundle_viewer.py",
        ):
            text = (BTF_ROOT / rel).read_text(encoding="utf-8")
            self.assertIn(needle, text, rel)

    def test_bundle_includes_demo_http_server(self) -> None:
        """Demo API needs http.server in SHARED_IMPORTS (per-module imports are stripped)."""
        needle = "from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer"
        for rel in (
            "btf_viewer_pkg/_imports.py",
            "scripts/bundle_viewer.py",
        ):
            text = (BTF_ROOT / rel).read_text(encoding="utf-8")
            self.assertIn(needle, text, rel)
        bundled = BTF_ROOT / "builds" / "btf_viewer.py"
        if bundled.is_file():
            self.assertIn(needle, bundled.read_text(encoding="utf-8"))

    def test_bundle_includes_rc_secret_imports(self) -> None:
        """Monolith strips per-module imports; enc1: crypto needs these."""
        text = (BTF_ROOT / "scripts" / "bundle_viewer.py").read_text(encoding="utf-8")
        for needle in (
            "import secrets",
            "import hmac",
            "import getpass",
            "import platform",
        ):
            self.assertIn(needle, text, needle)
        bundled = BTF_ROOT / "builds" / "btf_viewer.py"
        if bundled.is_file():
            bundled_text = bundled.read_text(encoding="utf-8")
            for needle in (
                "import secrets",
                "import hmac",
                "import getpass",
                "import platform",
            ):
                self.assertIn(needle, bundled_text, needle)

    def test_default_appearance(self) -> None:
        dlg = self._dlg("Appearance")
        self.addCleanup(dlg.deleteLater)
        self.assertEqual(dlg._sidebar.currentRow(), 0)
        self.assertEqual(dlg._content_stack.currentIndex(), 0)


if __name__ == "__main__":
    unittest.main()
