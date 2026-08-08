"""btf_viewer.rc [ai] section: per-preset keys and one-shot legacy migration."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg import stats as _stats  # noqa: E402
from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402


class _RcHost:
    """Minimal host exposing MainWindow's settings helpers."""

    _ai_read_settings = MainWindow._ai_read_settings
    _ai_setting_keys = MainWindow._ai_setting_keys
    _AI_LEGACY_KEYS = MainWindow._AI_LEGACY_KEYS

    def __init__(self, settings) -> None:
        self._settings = settings


class AiRcSettingsTests(unittest.TestCase):
    def _host(self, rc_text: str) -> _RcHost:
        tmp = tempfile.mkdtemp()
        rc_path = os.path.join(tmp, "btf_viewer.rc")
        with open(rc_path, "w", encoding="utf-8") as fh:
            fh.write(rc_text)
        self._rc_path = rc_path
        old = _stats._RcSettings.RC_PATH
        _stats._RcSettings.RC_PATH = rc_path
        self.addCleanup(setattr, _stats._RcSettings, "RC_PATH", old)
        return _RcHost(_stats._RcSettings())

    def test_defaults_for_fresh_rc(self) -> None:
        cfg = self._host("")._ai_read_settings()
        self.assertEqual(cfg["preset"], "ollama")
        self.assertEqual(cfg["ollama_base_url"], "")
        self.assertEqual(cfg["gemini_api_key"], "")

    def test_migrates_legacy_openai_provider(self) -> None:
        host = self._host(
            "[ai]\n"
            "enabled = true\n"
            "provider = openai_compatible\n"
            "openai_preset = gemini\n"
            "openai_model = gemini-3.6-flash\n"
            "openai_api_key = cloud-key\n"
            "ollama_url = http://192.168.1.5:11434\n"
        )
        cfg = host._ai_read_settings()
        self.assertEqual(cfg["preset"], "gemini")
        self.assertEqual(cfg["gemini_model"], "gemini-3.6-flash")
        self.assertEqual(cfg["gemini_api_key"], "cloud-key")
        # Native Ollama roots become the OpenAI-compatible /v1 endpoint.
        self.assertEqual(cfg["ollama_base_url"], "http://192.168.1.5:11434/v1")
        with open(self._rc_path, encoding="utf-8") as fh:
            written = fh.read()
        self.assertNotIn("openai_preset", written)
        self.assertNotIn("ollama_url =", written)
        self.assertNotIn("cloud-key", written.split("gemini_api_key")[0])
        self.assertIn("gemini_api_key = cloud-key", written)
        # Re-reading the migrated file is stable.
        self.assertEqual(host._ai_read_settings()["preset"], "gemini")

    def test_migrates_legacy_openai_vendor_to_openai_preset(self) -> None:
        host = self._host(
            "[ai]\n"
            "provider = openai_compatible\n"
            "openai_preset = openai\n"
            "openai_base_url = https://api.openai.com/v1\n"
            "openai_model = gpt-4o-mini\n"
            "openai_api_key = sk-keep\n"
        )
        cfg = host._ai_read_settings()
        # The old openai_* keys already carry the OpenAI preset's values.
        self.assertEqual(cfg["preset"], "openai")
        self.assertEqual(cfg["openai_base_url"], "https://api.openai.com/v1")
        self.assertEqual(cfg["openai_model"], "gpt-4o-mini")
        self.assertEqual(cfg["openai_api_key"], "sk-keep")
        self.assertEqual(host._ai_read_settings()["openai_api_key"], "sk-keep")

    def test_legacy_openai_vendor_becomes_custom(self) -> None:
        cfg = self._host(
            "[ai]\n"
            "provider = openai_compatible\n"
            "openai_preset = xai\n"
            "openai_base_url = https://api.x.ai/v1\n"
            "openai_api_key = grok-key\n"
        )._ai_read_settings()
        self.assertEqual(cfg["preset"], "custom")
        self.assertEqual(cfg["custom_base_url"], "https://api.x.ai/v1")
        self.assertEqual(cfg["custom_api_key"], "grok-key")
        # The vendor values must not linger as the OpenAI preset's settings.
        self.assertEqual(cfg["openai_base_url"], "")
        self.assertEqual(cfg["openai_api_key"], "")


if __name__ == "__main__":
    unittest.main()
