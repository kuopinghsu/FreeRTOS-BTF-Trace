"""Dynamic AI preset import / persistence / Reset to Defaults.

Covers the "P0 -- Dynamic Imported Presets", "P0 -- Desktop Persistence" and
"P0 -- Reset to Defaults" sections of
``TODO.bak/BTFVIEWER_AI_SETTINGS_DYNAMIC_PRESET_TODO.md``: an unknown preset
name imported from JSON (e.g. ``openrouter``) must become a real preset,
survive a simulated app restart in ``btf_viewer.rc``, and be fully wiped by
Reset to Defaults -- including stale per-preset ``.rc`` keys and built-in
API keys.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg import stats as _stats  # noqa: E402
from btf_viewer_pkg.ai_assistant import (  # noqa: E402
    AI_PRESET_FIELDS,
    AI_PRESETS,
    DEFAULT_AI_PRESET,
    dump_extra_ai_presets,
    extra_ai_preset_ids_from_settings,
    parse_extra_ai_presets,
    sanitize_ai_preset_id,
)
from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402
from btf_viewer_pkg.stats import _SettingsDialog  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _RcHost:
    """Exercises MainWindow's AI-settings load/save contract against a
    scratch ``btf_viewer.rc``, without constructing a full MainWindow."""

    _ai_read_settings = MainWindow._ai_read_settings
    _ai_setting_keys = MainWindow._ai_setting_keys
    _AI_LEGACY_KEYS = MainWindow._AI_LEGACY_KEYS

    def __init__(self, settings) -> None:
        self._settings = settings

    def dialog_kwargs(self) -> dict:
        """Mirror MainWindow._open_settings_dialog's ai_* kwargs (mainwindow.py)."""
        cfg = self._ai_read_settings()
        return dict(
            ai_enabled=self._settings.get_bool("ai", "enabled", True),
            ai_preset=cfg["preset"],
            ai_preset_settings={
                pid: {
                    field: cfg.get(f"{pid}_{field}", "")
                    for field in AI_PRESET_FIELDS
                }
                for pid in (
                    [p[0] for p in AI_PRESETS]
                    + extra_ai_preset_ids_from_settings(cfg)
                )
            },
            ai_extra_presets=parse_extra_ai_presets(cfg.get("extra_presets")),
            response_language=cfg["response_language"],
        )

    def save_dialog_result(self, dlg: _SettingsDialog) -> None:
        """Mirror MainWindow's Settings-Accept AI persistence (mainwindow.py)."""
        ai_upd = {
            "enabled": str(dlg.ai_enabled).lower(),
            "preset": dlg.ai_preset or DEFAULT_AI_PRESET,
            "response_language": dlg.response_language,
            "mcp_log": str(dlg.ai_mcp_log).lower(),
            "redact_task_names": str(dlg.ai_redact_task_names).lower(),
            "trace_sensitive": str(dlg.ai_trace_sensitive).lower(),
            "context_mode": dlg.ai_context_mode,
            "extra_presets": dump_extra_ai_presets(dlg.ai_extra_presets),
        }
        for pid, vals in dlg.ai_preset_settings.items():
            for field in AI_PRESET_FIELDS:
                ai_upd[f"{pid}_{field}"] = vals.get(field, "")
        self._settings.set_many("ai", ai_upd)
        extra_ids = [row["id"] for row in dlg.ai_extra_presets]
        self._settings.align_section_keys("ai", set(self._ai_setting_keys(extra_ids)))
        self._settings.flush()


class AiDynamicPresetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _app()

    def setUp(self) -> None:
        tmp = tempfile.mkdtemp()
        self._rc_path = os.path.join(tmp, "btf_viewer.rc")
        with open(self._rc_path, "w", encoding="utf-8") as fh:
            fh.write("")
        old = _stats._RcSettings.RC_PATH
        _stats._RcSettings.RC_PATH = self._rc_path
        self.addCleanup(setattr, _stats._RcSettings, "RC_PATH", old)

    def _host(self) -> _RcHost:
        return _RcHost(_stats._RcSettings())

    def _dlg(self, **overrides) -> _SettingsDialog:
        kwargs = dict(
            parent=None, font_size=10, ui_font_size=11, max_cursors=2,
            show_sti=True, show_grid=True, show_legend=True, show_stats=True,
            show_marks=True, show_hover_highlight=True, zoom_unit="us",
            label_width=120, row_height=18, row_gap=2, sti_row_h=14,
            sti_waveform_h=24, sti_line_style="solid",
            timescale_per_px_default=1.0, is_dark=True, initial_page="AI",
        )
        kwargs.update(overrides)
        parent = kwargs.pop("parent")
        dlg = _SettingsDialog(parent, **kwargs)
        self.addCleanup(dlg.deleteLater)
        return dlg

    # -- 25/26: unknown preset import survives a simulated restart --------

    def test_import_unknown_preset_round_trips_through_rc(self) -> None:
        host = self._host()
        dlg = self._dlg(**host.dialog_kwargs())
        dlg.apply_ai_settings_patch({
            "preset": "openrouter",
            "extra_presets": '[{"id": "openrouter", "label": "OpenRouter"}]',
            "openrouter_base_url": "https://openrouter.ai/api/v1",
            "openrouter_model": "openai/gpt-5",
            "openrouter_api_key": "or-key",
            "openrouter_auth_mode": "api_key",
            "openrouter_tls_verify": "true",
        })
        host.save_dialog_result(dlg)

        # Recreate the settings object the way an app restart would.
        host2 = self._host()
        cfg = host2._ai_read_settings()
        self.assertEqual(cfg["preset"], "openrouter")
        self.assertEqual(cfg["openrouter_base_url"], "https://openrouter.ai/api/v1")
        self.assertEqual(cfg["openrouter_model"], "openai/gpt-5")
        self.assertEqual(cfg["openrouter_api_key"], "or-key")
        self.assertIn("openrouter", extra_ai_preset_ids_from_settings(cfg))

        dlg2 = self._dlg(**host2.dialog_kwargs())
        self.assertEqual(dlg2.ai_preset, "openrouter")
        self.assertGreaterEqual(dlg2._ai_preset_combo.findData("openrouter"), 0)
        self.assertEqual(dlg2._ai_preset_combo.currentText(), "OpenRouter")
        self.assertEqual(dlg2._ai_url_edit.text(), "https://openrouter.ai/api/v1")
        self.assertEqual(dlg2._ai_api_key_edit.text(), "or-key")

    # -- 28: re-import of an already-known preset updates, not duplicates -

    def test_duplicate_import_updates_existing_preset(self) -> None:
        host = self._host()
        dlg = self._dlg(**host.dialog_kwargs())
        dlg.apply_ai_settings_patch({
            "preset": "openrouter",
            "extra_presets": '[{"id": "openrouter", "label": "OpenRouter"}]',
            "openrouter_base_url": "https://openrouter.ai/api/v1",
            "openrouter_model": "openai/gpt-5",
        })
        host.save_dialog_result(dlg)

        host2 = self._host()
        dlg2 = self._dlg(**host2.dialog_kwargs())
        # Re-import the same provider (different case/spacing) with new values.
        dlg2.apply_ai_settings_patch({
            "preset": "OpenRouter",
            "extra_presets": '[{"id": "OpenRouter", "label": "OpenRouter"}]',
            "openrouter_model": "openai/gpt-5.1",
        })
        matches = [
            i for i in range(dlg2._ai_preset_combo.count())
            if dlg2._ai_preset_combo.itemData(i) == "openrouter"
        ]
        self.assertEqual(len(matches), 1)
        self.assertEqual(dlg2.ai_preset_settings["openrouter"]["model"], "openai/gpt-5.1")
        host.save_dialog_result(dlg2)

        host3 = self._host()
        cfg = host3._ai_read_settings()
        self.assertEqual(len(extra_ai_preset_ids_from_settings(cfg)), 1)
        self.assertEqual(cfg["openrouter_model"], "openai/gpt-5.1")

    # -- 29: multiple imported presets coexist after reload ----------------

    def test_multiple_extra_presets_coexist_after_reload(self) -> None:
        host = self._host()
        dlg = self._dlg(**host.dialog_kwargs())
        dlg.apply_ai_settings_patch({
            "preset": "openrouter",
            "extra_presets": (
                '[{"id": "openrouter", "label": "OpenRouter"}, '
                '{"id": "deepseek", "label": "DeepSeek"}]'
            ),
            "openrouter_base_url": "https://openrouter.ai/api/v1",
            "openrouter_model": "openai/gpt-5",
            "deepseek_base_url": "https://api.deepseek.com/v1",
            "deepseek_model": "deepseek-chat",
        })
        host.save_dialog_result(dlg)

        host2 = self._host()
        cfg = host2._ai_read_settings()
        ids = extra_ai_preset_ids_from_settings(cfg)
        self.assertIn("openrouter", ids)
        self.assertIn("deepseek", ids)
        self.assertEqual(cfg["deepseek_model"], "deepseek-chat")
        dlg2 = self._dlg(**host2.dialog_kwargs())
        self.assertGreaterEqual(dlg2._ai_preset_combo.findData("openrouter"), 0)
        self.assertGreaterEqual(dlg2._ai_preset_combo.findData("deepseek"), 0)

    # -- 16: import merges with, does not replace, existing extra presets --

    def test_import_merges_with_existing_extra_presets(self) -> None:
        host = self._host()
        dlg = self._dlg(**host.dialog_kwargs())
        dlg.apply_ai_settings_patch({
            "preset": "openrouter",
            "extra_presets": (
                '[{"id": "openrouter", "label": "OpenRouter"}, '
                '{"id": "deepseek", "label": "DeepSeek"}]'
            ),
        })
        host.save_dialog_result(dlg)

        host2 = self._host()
        dlg2 = self._dlg(**host2.dialog_kwargs())
        dlg2.apply_ai_settings_patch({
            "preset": "grok",
            "extra_presets": '[{"id": "grok", "label": "Grok"}]',
        })
        host.save_dialog_result(dlg2)

        host3 = self._host()
        ids = set(extra_ai_preset_ids_from_settings(host3._ai_read_settings()))
        self.assertEqual(ids, {"openrouter", "deepseek", "grok"})

    # -- 30: Reset to Defaults wipes extras + stale .rc keys + credentials -

    def test_reset_to_defaults_clears_extras_and_rc_keys(self) -> None:
        host = self._host()
        dlg = self._dlg(**host.dialog_kwargs())
        dlg.apply_ai_settings_patch({
            "preset": "openrouter",
            "extra_presets": '[{"id": "openrouter", "label": "OpenRouter"}]',
            "openrouter_base_url": "https://openrouter.ai/api/v1",
            "openrouter_model": "openai/gpt-5",
            "openrouter_api_key": "or-key",
        })
        # A credential on a built-in preset must also be cleared by reset.
        dlg._ai_preset_combo.setCurrentIndex(dlg._ai_preset_combo.findData("openai"))
        dlg._ai_api_key_edit.setText("sk-live")
        host.save_dialog_result(dlg)

        host2 = self._host()
        cfg = host2._ai_read_settings()
        self.assertEqual(cfg["openai_api_key"], "sk-live")
        self.assertIn("openrouter", extra_ai_preset_ids_from_settings(cfg))

        dlg2 = self._dlg(**host2.dialog_kwargs())
        dlg2._reset_to_defaults()
        self.assertEqual(dlg2.ai_extra_presets, [])
        self.assertEqual(dlg2.ai_preset, DEFAULT_AI_PRESET)
        self.assertEqual(dlg2.ai_preset_settings["openai"]["api_key"], "")
        # The extra preset is dropped from the catalog entirely, not just
        # credential-cleared.
        self.assertNotIn("openrouter", dlg2.ai_preset_settings)
        host.save_dialog_result(dlg2)

        host3 = self._host()
        cfg3 = host3._ai_read_settings()
        self.assertEqual(cfg3["preset"], DEFAULT_AI_PRESET)
        self.assertEqual(cfg3["extra_presets"], "[]")
        self.assertEqual(cfg3["openai_api_key"], "")
        self.assertEqual(extra_ai_preset_ids_from_settings(cfg3), [])
        with open(self._rc_path, encoding="utf-8") as fh:
            written = fh.read()
        # Stale per-preset keys for the removed extra must not linger.
        self.assertNotIn("openrouter_base_url", written)
        self.assertNotIn("openrouter_model", written)
        self.assertNotIn("openrouter_api_key", written)
        self.assertNotIn("or-key", written)
        self.assertNotIn("sk-live", written)

    # -- 32: Cancel after import must not persist the dialog's changes -----

    def test_cancel_after_import_does_not_persist(self) -> None:
        host = self._host()
        dlg = self._dlg(**host.dialog_kwargs())
        dlg.apply_ai_settings_patch({
            "preset": "openrouter",
            "extra_presets": '[{"id": "openrouter", "label": "OpenRouter"}]',
            "openrouter_base_url": "https://openrouter.ai/api/v1",
        })
        # Simulate Cancel: the dialog is discarded, save_dialog_result is
        # only reached on QDialog.Accepted in mainwindow.py.
        dlg.deleteLater()

        host2 = self._host()
        cfg = host2._ai_read_settings()
        self.assertEqual(cfg["preset"], DEFAULT_AI_PRESET)
        self.assertEqual(extra_ai_preset_ids_from_settings(cfg), [])

    # -- 17: malformed imported preset ids never become unsafe .rc keys ----

    def test_malformed_preset_ids_never_produce_unsafe_ids(self) -> None:
        # Empty / whitespace-only / control-char-only / overlong / digit-led
        # input can never form a valid preset id (no letter to anchor on,
        # or too long) and must be rejected outright.
        for bad in ("", "   ", "a" * 40, "\x00\x01", "123abc", "---"):
            self.assertEqual(sanitize_ai_preset_id(bad), "", repr(bad))
        # Path-like / punctuation-laden input is not rejected outright, but
        # the sanitizer must still never leak unsafe characters into the id
        # (it strips everything but [a-z0-9_], so the result is always a
        # safe .rc key / JS object key even for hostile input).
        sanitized = sanitize_ai_preset_id("../../etc/passwd")
        self.assertRegex(sanitized, r"^[a-z][a-z0-9_]*$")
        self.assertNotIn("/", sanitized)
        self.assertNotIn(".", sanitized)


if __name__ == "__main__":
    unittest.main()
