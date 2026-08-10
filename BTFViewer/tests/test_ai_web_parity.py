"""Desktop ↔ web AI constants and call-site parity."""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg.ai_assistant import (  # noqa: E402
    AI_CHAT_TIMEOUT_S,
    AI_LIST_MODELS_TIMEOUT_S,
    AI_TEST_TIMEOUT_S,
)
from btf_viewer_pkg.ai_tools import (  # noqa: E402
    AI_RAW_METRIC_NAMES,
    AI_TOOL_ADD_ANNOTATION,
    AI_TOOL_EXPORT_REPORT,
    AI_TOOL_QUERY_RAW_METRIC,
    AI_TOOL_SYSTEM_ADDENDUM,
    AI_VIEWER_TOOL_NAMES,
    GEMINI_SKIP_THOUGHT_SIGNATURE,
    max_tool_rounds,
)


class AiWebParityTests(unittest.TestCase):
    def test_timeouts_match_web(self) -> None:
        js = (BTF_ROOT / "web/src/utils/ollamaClient.js").read_text(encoding="utf-8")
        self.assertIn(f"AI_CHAT_TIMEOUT_MS = {int(AI_CHAT_TIMEOUT_S * 1000)}", js)
        self.assertIn(
            f"AI_LIST_MODELS_TIMEOUT_MS = {int(AI_LIST_MODELS_TIMEOUT_S * 1000)}", js)
        self.assertIn(f"AI_TEST_TIMEOUT_MS = {int(AI_TEST_TIMEOUT_S * 1000)}", js)
        self.assertEqual(AI_CHAT_TIMEOUT_S, 120.0)
        self.assertEqual(AI_LIST_MODELS_TIMEOUT_S, 12.0)
        self.assertEqual(AI_TEST_TIMEOUT_S, 120.0)

    def test_tool_rounds_match_web(self) -> None:
        js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        self.assertRegex(js, rf"MAX_TOOL_ROUNDS\s*=\s*{max_tool_rounds()}")
        self.assertEqual(max_tool_rounds(), 4)

    def test_web_execute_tools_pushes_undo(self) -> None:
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        self.assertIn("pushUndoSnapshot()", app)
        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        self.assertIn("self._push_undo_snapshot()", mw)
        self.assertIn("self._cmd_undo()", mw)

    def test_highlight_normalizes_to_merge_key(self) -> None:
        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        self.assertIn("_task_merge_key(resolved)", mw)
        self.assertIn("taskMergeKey(resolved)", app)
        self.assertIn("if resolved:", mw)
        self.assertIn("if (resolved) {", app)
        self.assertIn("resolve_core_key(key, cores)", mw)
        self.assertIn("resolveCoreKey(key, trace.value?.coreNames", app)
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(encoding="utf-8")
        self.assertIn("_try_mermaid_node_click", assist)
        self.assertIn("hit_test_mermaid", assist)

    def test_corridor_resolves_core_aliases(self) -> None:
        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        self.assertIn("resolve_core_key(src_raw, cores)", mw)
        self.assertIn("resolveCoreKey(args.core_from", app)
        self.assertIn("export function resolveCoreKey", js)

    def test_tool_names_listed_in_web(self) -> None:
        js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        readme = (BTF_ROOT / "README.md").read_text(encoding="utf-8")
        workflows = (BTF_ROOT / "WORKFLOWS.md").read_text(encoding="utf-8")
        for name in AI_VIEWER_TOOL_NAMES:
            self.assertRegex(js, re.compile(rf"['\"]{re.escape(name)}['\"]"))
            self.assertIn(f"`{name}`", readme)
        for metric in AI_RAW_METRIC_NAMES:
            self.assertIn(f"'{metric}'", js)
            self.assertIn(f'"{metric}"', (
                BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8"))
        self.assertIn("query_raw_metric", workflows)
        self.assertIn("add_annotation", workflows)
        self.assertIn("export_report", workflows)
        self.assertIn("`add_annotation` / `query_raw_metric` / `export_report`", readme)
        self.assertIn("MAX_RAW_METRIC_ROWS = 40", js)
        self.assertIn("_MAX_RAW_METRIC_ROWS = 40", (
            BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8"))
        self.assertIn("MAX_ANNOTATION_NOTE = 240", js)
        self.assertIn("_MAX_ANNOTATION_NOTE = 240", (
            BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8"))
        self.assertIn("add_annotation", AI_TOOL_SYSTEM_ADDENDUM)
        self.assertIn("query_raw_metric", AI_TOOL_SYSTEM_ADDENDUM)
        self.assertIn("export_report", AI_TOOL_SYSTEM_ADDENDUM)
        self.assertIn("Valid tools: set_cursors, zoom_to_range, highlight_task,", js)
        self.assertIn("Valid tools: set_cursors, zoom_to_range, highlight_task,", AI_TOOL_SYSTEM_ADDENDUM)

    def test_new_tool_dispatch_sites_match(self) -> None:
        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")
        panel = (BTF_ROOT / "web/src/components/AiAssistantPanel.vue").read_text(
            encoding="utf-8")
        self.assertIn("AI_TOOL_ADD_ANNOTATION", mw)
        self.assertIn("AI_TOOL_ADD_ANNOTATION", app)
        self.assertIn("AI_TOOL_QUERY_RAW_METRIC", mw)
        self.assertIn("AI_TOOL_QUERY_RAW_METRIC", app)
        self.assertIn("query_raw_metric(", mw)
        self.assertIn("queryRawMetric(", app)
        self.assertIn("tool_mutates_gui", mw)
        self.assertIn("toolMutatesGui", app)
        self.assertNotIn("ensureMarksPanelVisible()", app)
        self.assertIn("show_marks_panel=False", mw)
        self.assertNotIn("focus_annotation_tab=True", mw)
        self.assertIn('return f"Annotated {ns}"', mw)
        self.assertIn("return `Annotated ${ns}`", app)
        self.assertIn("def _export_ai_report", assist)
        self.assertIn("function exportAiReport", panel)
        self.assertIn("tool_batch_auto_runs", assist)
        self.assertIn("toolBatchAutoRuns", panel)
        self.assertIn("is_export_tool", assist)
        self.assertIn("isExportTool", panel)
        self.assertIn("build_ai_report_html", assist)
        self.assertIn("buildAiReportHtml", panel)
        self.assertIn(AI_TOOL_ADD_ANNOTATION, AI_VIEWER_TOOL_NAMES)
        self.assertIn(AI_TOOL_QUERY_RAW_METRIC, AI_VIEWER_TOOL_NAMES)
        self.assertIn(AI_TOOL_EXPORT_REPORT, AI_VIEWER_TOOL_NAMES)

    def test_stats_table_annotation_does_not_switch_to_marks(self) -> None:
        mw = (BTF_ROOT / "btf_viewer_pkg/mainwindow.py").read_text(encoding="utf-8")
        app = (BTF_ROOT / "web/src/App.vue").read_text(encoding="utf-8")
        self.assertIn("def _on_stats_plot_point_clicked", mw)
        self.assertIn("stay_tab = self._panel_tabs.currentIndex()", mw)
        self.assertIn("function onStatsPlotPointActivate", app)
        self.assertIn("const stayOnTab = rightPanelTab.value", app)
        self.assertIn("rightPanelTab.value = stayOnTab", app)
        self.assertNotIn("ensureMarksPanelVisible()", app)
        self.assertIn(
            "self._add_annotation_with_note(mark_ns, note, show_marks_panel=False)",
            mw,
        )

    def test_gemini_thought_signature_helpers_match(self) -> None:
        js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        py = (BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8")
        client = (BTF_ROOT / "web/src/utils/ollamaClient.js").read_text(
            encoding="utf-8")
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")
        self.assertIn(f'"{GEMINI_SKIP_THOUGHT_SIGNATURE}"', py)
        self.assertIn(f"'{GEMINI_SKIP_THOUGHT_SIGNATURE}'", js)
        self.assertIn("def ensure_gemini_thought_signatures", py)
        self.assertIn("export function ensureGeminiThoughtSignatures", js)
        self.assertIn("def needs_gemini_thought_signatures", py)
        self.assertIn("export function needsGeminiThoughtSignatures", js)
        self.assertIn("ensure_gemini_thought_signatures(messages)", assist)
        self.assertIn("ensureGeminiThoughtSignatures(chatMessages)", client)
        readme = (BTF_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("thought_signature", readme)
        workflows = (BTF_ROOT / "WORKFLOWS.md").read_text(encoding="utf-8")
        self.assertIn("thought_signature", workflows)
        self.assertIn('"preset": active["preset"]', assist)
        self.assertIn("preset: active.preset", (
            BTF_ROOT / "web/src/components/AiAssistantPanel.vue"
        ).read_text(encoding="utf-8"))

    def test_ai_model_picker_is_editable_combo(self) -> None:
        vue = (BTF_ROOT / "web/src/components/SettingsDialog.vue").read_text(
            encoding="utf-8")
        stats = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
        client = (BTF_ROOT / "web/src/utils/ollamaClient.js").read_text(
            encoding="utf-8")
        readme = (BTF_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("setEditable(True)", stats)
        self.assertIn("def _fill_ai_model_combo", stats)
        self.assertIn('role="combobox"', vue)
        self.assertIn("toggleAiModelMenu", vue)
        self.assertIn("ai-model-listbox", vue)
        self.assertIn("_ai_model_combo.showPopup", stats)
        self.assertIn("aiModelMenuOpen.value = true", vue)
        self.assertIn("AbortSignal.timeout(timeoutMs)", client)
        self.assertIn("AbortSignal.any(", client)
        self.assertNotIn("<datalist", vue)
        self.assertNotIn("datalist", readme)

    def test_ai_auth_mode_helpers_match(self) -> None:
        from btf_viewer_pkg.ai_assistant import (
            AI_AUTH_API_KEY,
            AI_AUTH_BROWSER,
            AI_AUTH_MODE_LABELS,
            AI_AUTH_NONE,
            AI_PRESET_CUSTOM,
            AI_PRESET_FIELDS,
            AI_PRESET_GEMINI,
            AI_PRESET_KEY_URLS,
            AI_PRESET_OLLAMA,
            AI_PRESET_OPENAI,
            AI_PRESET_SIGNIN_LABELS,
            LOCAL_AI_HOSTS,
            ai_auth_status,
            ai_preset_signin_label,
            ai_preset_signin_url,
            default_ai_auth_mode,
            normalize_ai_auth_mode,
        )

        js = (BTF_ROOT / "web/src/utils/ollamaClient.js").read_text(encoding="utf-8")
        vue = (BTF_ROOT / "web/src/components/SettingsDialog.vue").read_text(
            encoding="utf-8")
        stats = (BTF_ROOT / "btf_viewer_pkg/stats.py").read_text(encoding="utf-8")
        panel = (BTF_ROOT / "web/src/components/AiAssistantPanel.vue").read_text(
            encoding="utf-8")
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")
        readme = (BTF_ROOT / "README.md").read_text(encoding="utf-8")
        workflows = (BTF_ROOT / "WORKFLOWS.md").read_text(encoding="utf-8")

        self.assertEqual(AI_AUTH_NONE, "none")
        self.assertEqual(AI_AUTH_API_KEY, "api_key")
        self.assertEqual(AI_AUTH_BROWSER, "browser")
        self.assertEqual(tuple(AI_PRESET_FIELDS), (
            "base_url", "model", "api_key", "auth_mode", "tls_verify"))
        self.assertIn("authMode", js)
        self.assertIn(
            "AI_PRESET_FIELDS = ['baseUrl', 'model', 'apiKey', 'authMode', 'tlsVerify']",
            js,
        )

        for _mode, label in AI_AUTH_MODE_LABELS:
            self.assertIn(f"'{label}'", js)
        for host in LOCAL_AI_HOSTS:
            self.assertIn(f"'{host}'", js)
        for url in AI_PRESET_KEY_URLS.values():
            self.assertIn(url, js)
            self.assertIn(url, assist)
        for label in AI_PRESET_SIGNIN_LABELS.values():
            self.assertIn(label, js)
            self.assertIn(label, assist)

        for status_label in (
            "Local", "Signed in", "Key saved", "Needs sign-in", "Needs API key",
        ):
            self.assertIn(f"'{status_label}'", js)
            self.assertIn(f'"{status_label}"', assist)

        self.assertEqual(default_ai_auth_mode(AI_PRESET_OLLAMA), AI_AUTH_NONE)
        self.assertEqual(default_ai_auth_mode(AI_PRESET_GEMINI), AI_AUTH_API_KEY)
        self.assertEqual(normalize_ai_auth_mode("sign-in"), AI_AUTH_BROWSER)
        self.assertEqual(normalize_ai_auth_mode("oauth"), AI_AUTH_BROWSER)
        self.assertIn("aistudio.google.com", ai_preset_signin_url(AI_PRESET_GEMINI))
        self.assertEqual(
            ai_preset_signin_label(AI_PRESET_OPENAI), "Sign in with OpenAI…")
        self.assertEqual(
            ai_preset_signin_label(AI_PRESET_CUSTOM), "Open provider sign-in…")
        need = ai_auth_status(
            auth_mode=AI_AUTH_API_KEY, api_key="", preset_id=AI_PRESET_GEMINI)
        self.assertTrue(need["needs_auth"])
        self.assertEqual(need["label"], "Needs API key")

        self.assertIn("def normalize_ai_auth_mode", assist)
        self.assertIn("export function normalizeAiAuthMode", js)
        self.assertIn("def strip_ai_settings_jsonc", assist)
        self.assertIn("export function stripAiSettingsJsonc", js)
        self.assertIn("strip_ai_settings_jsonc(data)", assist)
        self.assertIn("stripAiSettingsJsonc(parsed)", js)
        self.assertIn("AI_AUTH_BROWSER", assist)
        self.assertIn("AI_AUTH_BROWSER", js)
        self.assertIn("Authentication:", stats)
        self.assertIn("Authentication", vue)
        self.assertIn("_ai_signin_btn", stats)
        self.assertIn("onAiSignIn", vue)
        self.assertIn("QDesktopServices.openUrl(QUrl(url))", stats)
        self.assertIn("QDesktopServices.openUrl(QUrl(url))", assist)
        self.assertIn("window.open(url, '_blank', 'noopener,noreferrer')", vue)
        self.assertIn("window.open(url, '_blank', 'noopener,noreferrer')", panel)
        self.assertIn(
            "Opened {url}. After you sign in, paste the key or token and Test.",
            stats)
        self.assertIn(
            "Opened ${url}. After you sign in, paste the key or token and Test.",
            vue)
        self.assertIn(
            "This preset has no sign-in page. Paste a token or set Base URL.",
            stats)
        self.assertIn(
            "This preset has no sign-in page. Paste a token or set Base URL.",
            vue)
        self.assertIn("_auth_chip", assist)
        self.assertIn("ai-auth-chip", panel)
        self.assertIn("self._auth_forced", assist)
        self.assertIn("authForced", panel)
        self.assertIn("showSignInCta", panel)
        self.assertIn(
            "Opened {url}. Paste the key or token in Settings → AI.", assist)
        self.assertIn(
            "Opened ${url}. Paste the key or token in Settings → AI.", panel)
        self.assertIn("Authentication |", readme)
        self.assertIn("Self-signed TLS |", readme)
        self.assertIn("Model picker |", readme)
        self.assertIn("Allow self-signed TLS", stats)
        self.assertIn("Allow self-signed TLS", vue)
        self.assertIn("Allow self-signed TLS", readme)
        self.assertIn("Allow self-signed TLS", workflows)
        self.assertIn("def parse_ai_tls_verify", assist)
        self.assertIn("export function parseAiTlsVerify", js)
        self.assertIn("ai_urlopen", assist)
        self.assertIn("aiTlsTip", js)
        self.assertIn("def _ai_timeout_error_tip", assist)
        self.assertIn("GET /models only lists ids", assist)
        self.assertIn("GET /models only lists ids", js)
        self.assertIn("BASE/chat/completions", readme)
        for name in (
            "ollama.json", "gemini.json", "openai.json",
            "deepseek.json", "grok.json", "presets.json",
        ):
            self.assertIn(name, readme)
            self.assertIn(name, workflows)
            self.assertIn(name, stats)
            self.assertIn(name, vue)
        self.assertIn("401 keeps Sign in / Settings CTAs", workflows)
        self.assertIn("open the Model dropdown", workflows)
        self.assertIn(
            "Open the Model dropdown to pick one.", stats)
        self.assertIn(
            "Open the Model dropdown to pick one.", vue)

    def test_gemini_tool_result_name_helpers_match(self) -> None:
        py = (BTF_ROOT / "btf_viewer_pkg/ai_tools.py").read_text(encoding="utf-8")
        js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        assist = (BTF_ROOT / "btf_viewer_pkg/ai_assistant.py").read_text(
            encoding="utf-8")
        vue = (BTF_ROOT / "web/src/components/AiAssistantPanel.vue").read_text(
            encoding="utf-8")
        client = (BTF_ROOT / "web/src/utils/ollamaClient.js").read_text(
            encoding="utf-8")
        self.assertIn("def normalize_tool_chat_messages", py)
        self.assertIn("export function normalizeToolChatMessages", js)
        self.assertIn("normalize_tool_chat_messages(messages)", assist)
        self.assertIn("normalizeToolChatMessages(", client)
        self.assertIn("canonical_assistant_tool_message(text, calls)", assist)
        self.assertIn("canonicalAssistantToolMessage(text, calls)", vue)
        self.assertIn("tool_result_message(", assist)
        self.assertIn("toolResultMessage(", vue)


if __name__ == "__main__":
    unittest.main()
