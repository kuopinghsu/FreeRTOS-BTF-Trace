"""Reset to Defaults must also clear the AI investigation session/response
history — both the visible chat and the persisted ``[ai] investigation_session``
``.rc`` key. Filed as a follow-up to the AI dynamic-preset TODO: Reset already
wiped presets/credentials but left the conversation behind.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests import destroy_main_window  # noqa: E402
from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from btf_viewer_pkg import stats as _stats  # noqa: E402
from btf_viewer_pkg.ai_assistant import (  # noqa: E402
    create_ai_assistant_panel,
    parse_ai_template_usage,
    parse_recent_ai_templates,
)
from btf_viewer_pkg.ai_case import (  # noqa: E402
    dump_investigation_session,
    investigation_session_has_chat,
    parse_investigation_session,
)
from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class AiPanelClearConversationTests(unittest.TestCase):
    """Unit-level: clear_conversation() must persist an empty session too."""

    @classmethod
    def setUpClass(cls) -> None:
        _app()

    def test_clear_conversation_persists_empty_session(self) -> None:
        saved = {}
        panel = create_ai_assistant_panel(
            None,
            get_context=lambda: {"findings_text": "findings"},
            get_settings=lambda: {"enabled": "true"},
            on_save_settings=saved.update,
        )
        self.addCleanup(panel.deleteLater)
        panel._append("user", "What caused the CPU spike at 3.2ms?")
        panel._append("assistant", "Task CS[28] held the core for 4.1ms.")
        self.assertTrue(panel._entries)
        blob_before = parse_investigation_session(saved.get("investigation_session"))
        self.assertTrue(investigation_session_has_chat(blob_before["messages"]))

        panel.clear_conversation()

        self.assertEqual(panel._entries, [])
        blob_after = parse_investigation_session(saved.get("investigation_session"))
        self.assertFalse(investigation_session_has_chat(blob_after["messages"]))


class ResetToDefaultsClearsSessionTests(unittest.TestCase):
    """End-to-end: a real MainWindow + real Settings dialog Reset flow."""

    @classmethod
    def setUpClass(cls) -> None:
        _app()

    def setUp(self) -> None:
        tmp = tempfile.mkdtemp()
        self._rc_path = os.path.join(tmp, "btf_viewer.rc")
        seed_blob = dump_investigation_session(messages=[
            {"role": "user", "content": "What caused the CPU spike at 3.2ms?"},
            {"role": "assistant", "content": "Task CS[28] held the core for 4.1ms."},
        ])
        with open(self._rc_path, "w", encoding="utf-8") as fh:
            fh.write("[ai]\ninvestigation_session = " + seed_blob + "\n")
        old = _stats._RcSettings.RC_PATH
        _stats._RcSettings.RC_PATH = self._rc_path
        self.addCleanup(setattr, _stats._RcSettings, "RC_PATH", old)

    def test_reset_to_defaults_clears_chat_and_rc(self) -> None:
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        QApplication.processEvents()  # let the deferred session restore run

        self.assertTrue(win._ai_panel._entries, "seeded chat should restore on open")

        def fake_exec(dlg, parent):
            dlg._reset_to_defaults()
            return QDialog.Accepted

        with patch("btf_viewer_pkg.mainwindow._exec_centred", side_effect=fake_exec):
            win._open_settings("AI")

        self.assertEqual(win._ai_panel._entries, [])

        cfg = win._ai_read_settings()
        parsed = parse_investigation_session(cfg.get("investigation_session"))
        self.assertFalse(investigation_session_has_chat(parsed["messages"]))

        with open(self._rc_path, encoding="utf-8") as fh:
            written = fh.read()
        self.assertNotIn("CPU spike", written)
        self.assertNotIn("CS[28]", written)

    # -- Reset must also clear AI personalization/history/baseline state ---
    # Regression coverage for TODO.bak/TODO.md P1: Reset already wiped
    # imported presets/credentials and the chat/session, but left
    # baseline_profile, user templates/knowledge, template MRU/usage, and
    # (Desktop) split_bottom behind.

    def test_reset_to_defaults_clears_ai_personalization_state(self) -> None:
        settings = _stats._RcSettings()
        settings.set_many("ai", {
            "baseline_profile": '{"samples": 3, "tasks": {}}',
            "user_investigation_templates": (
                '[{"id": "my_tpl", "label": "My Template", "steps": ["a"]}]'),
            "user_historical_knowledge": (
                '[{"id": "k1", "title": "Known issue", "text": "..."}]'),
            "recent_templates": '["explain_task", "verify_claim"]',
            "template_usage": '{"explain_task": 3}',
            "split_bottom": "180",
        }, flush=True)

        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        QApplication.processEvents()

        def fake_exec(dlg, parent):
            dlg._reset_to_defaults()
            return QDialog.Accepted

        with patch("btf_viewer_pkg.mainwindow._exec_centred", side_effect=fake_exec):
            win._open_settings("AI")

        cfg = win._ai_read_settings()
        self.assertFalse(cfg.get("baseline_profile"))
        self.assertFalse(cfg.get("user_investigation_templates"))
        self.assertFalse(cfg.get("user_historical_knowledge"))
        self.assertEqual(parse_recent_ai_templates(cfg.get("recent_templates")), [])
        self.assertEqual(parse_ai_template_usage(cfg.get("template_usage")), {})

        # Re-read from a fresh _RcSettings() instance (simulated restart) to
        # prove the wipe actually reached disk, not just the live dialog.
        reread = _stats._RcSettings()
        self.assertFalse(reread.get("ai", "baseline_profile", ""))
        self.assertFalse(reread.get("ai", "user_investigation_templates", ""))
        self.assertFalse(reread.get("ai", "user_historical_knowledge", ""))
        with open(self._rc_path, encoding="utf-8") as fh:
            written = fh.read()
        self.assertNotIn("my_tpl", written)
        self.assertNotIn("Known issue", written)
        self.assertNotIn("explain_task", written)
        self.assertNotIn("180", written)


if __name__ == "__main__":
    unittest.main()
