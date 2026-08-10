"""AI panel widget behaviour that must match web/src/components/AiAssistantPanel.vue."""
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

from unittest.mock import patch  # noqa: E402

from PySide6.QtCore import QPoint, QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.ai_assistant import create_ai_assistant_panel  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class AiPanelUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _app()

    def _panel(self):
        return create_ai_assistant_panel(
            None,
            get_context=lambda: {"findings_text": "findings"},
            get_settings=lambda: {"enabled": "true"},
        )

    def test_ask_needs_a_question(self) -> None:
        """Ask stays disabled until the box has text (web parity)."""
        panel = self._panel()
        self.assertFalse(panel._send_btn.isEnabled())
        panel._input.setPlainText("why is CS[22] late?")
        self.assertTrue(panel._send_btn.isEnabled())
        panel._input.setPlainText("   ")
        self.assertFalse(panel._send_btn.isEnabled())

    def test_log_keeps_prompt_and_reply_apart(self) -> None:
        """Template / follow-up prompts must not continue the previous assistant block."""
        panel = self._panel()
        panel._append("user", "What is wrong?")
        panel._append("assistant", "Nothing much.")
        panel._append("user", "Second prompt")
        text = panel._log.toPlainText()
        self.assertIn("What is wrong?", text)
        self.assertIn("Nothing much.", text)
        self.assertIn("Second prompt", text)
        self.assertRegex(text, r"You\s+What is wrong\?")
        self.assertRegex(text, r"Assistant\s+Nothing much\.")
        self.assertRegex(text, r"You\s+Second prompt")
        html = panel._log.toHtml().lower()
        # Qt may drop custom classes; bgcolor on each bubble still survives.
        self.assertGreaterEqual(html.count("#1e3348"), 2)
        self.assertGreaterEqual(html.count("#1a2620"), 1)
        # Second prompt must appear after the first reply in the rendered log.
        self.assertLess(text.index("Nothing much."), text.index("Second prompt"))

    def test_log_menu_offers_copy_and_save(self) -> None:
        panel = self._panel()
        menu = panel._log.createStandardContextMenu(QPoint(0, 0))
        menu.addSeparator()
        # Mirror _show_log_menu without opening a modal menu.
        copy_all = menu.addAction("Copy conversation")
        copy_all.setEnabled(bool(panel._entries))
        self.assertFalse(copy_all.isEnabled())

        panel._append("user", "hi")
        panel._append("assistant", "## Answer\n\nsee jump:12.")
        panel.copy_conversation()
        clip = QApplication.clipboard().text()
        self.assertIn("# BTF Viewer — AI Conversation", clip)
        self.assertIn("## You", clip)
        self.assertIn("see jump:12.", clip)
        self.assertEqual(panel._status.text(), "Copied to clipboard.")

    def test_http_links_open_in_system_browser(self) -> None:
        panel = self._panel()
        opened = []
        with patch(
            "btf_viewer_pkg.ai_assistant.QDesktopServices.openUrl",
            side_effect=lambda u: opened.append(u.toString()),
        ):
            panel._on_jump_link(QUrl("https://example.com/a"))
            panel._on_jump_link(QUrl("mailto:dev@example.com"))
        self.assertEqual(
            opened,
            ["https://example.com/a", "mailto:dev@example.com"],
        )

    def test_query_analysis_findings_uses_template(self) -> None:
        panel = self._panel()
        with patch.object(panel, "send_current") as send:
            panel.query_analysis_findings()
        send.assert_called_once()
        prompt = panel._input.toPlainText()
        self.assertIn("Analysis Findings", prompt)
        self.assertIn("severity", prompt)

    def test_query_migration_thrash_uses_template(self) -> None:
        panel = self._panel()
        with patch.object(panel, "send_current") as send:
            panel.query_migration_thrash()
        send.assert_called_once()
        prompt = panel._input.toPlainText()
        self.assertIn("core thrashing", prompt)
        self.assertIn("lock-bounce", prompt)


if __name__ == "__main__":
    unittest.main()
